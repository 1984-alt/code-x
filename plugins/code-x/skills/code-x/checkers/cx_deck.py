"""
cmd_deck: reverse-coverage gate — checks that every requirement in the manifest
is accounted for across work-order cards, and that no card claims unknown
requirements.

cx check deck <cards-dir> <packet-dir> [--manifest <path>]

PINNED HASH RECIPE (sha256 over sorted files in packet-dir, recursive):
  For every regular file under <packet-dir> (recursive, sorted by POSIX relpath):
    hash.update(relpath_bytes + b"\\0" + file_bytes)
  Hex digest is the locked_packet_hash. The manifest lives inside packet-dir,
  so it is part of the hash — any manifest edit changes the hash.
"""

import hashlib
import os
import re
from pathlib import Path

from cx_common import findings_report, load_yaml, field_present


# Valid disposition values
VALID_DISPOSITIONS = {"BUILDING", "NOT_BUILDING", "NOT_APPLICABLE", "CEO_DEFERRED"}

# PROP-014: every ceo_decision_ref must resolve to a CEO-DECISION-LEDGER.md row id.
# Row ids look like CEO-D-001 / CEO-D-LEGACY-001 ("decision lives in chat" is the hole).
LEDGER_FILE = "CEO-DECISION-LEDGER.md"
LEDGER_ROW_ID_RE = re.compile(r"\bCEO-D-[A-Z0-9][A-Z0-9-]*\b")


def _compute_packet_hash(packet_dir: Path) -> str:
    """
    sha256 over the concatenation, for every regular file under packet_dir
    (recursive, sorted by POSIX relpath), of: relpath bytes + b"\\0" + file bytes.
    Returns hex digest.

    A frozen packet MUST be self-contained: any symlink under packet_dir raises
    ValueError (V1.10 R4 — GPT cross-review P0). Following a symlink would hash the
    TARGET's bytes, letting "a file inside the packet" resolve to content OUTSIDE it
    — which defeats the content binding AND the canonical-registry identity check
    (a `<packet>/MODULE-REGISTRY.yaml` symlinked to an external trimmed registry).
    Fail-closed: no symlinks, so the hash and the bytes it covers are exactly the
    files committed inside the packet.
    """
    base = Path(packet_dir)
    if base.is_symlink():
        raise ValueError(
            f"packet dir is itself a symlink: {base} — a frozen packet must be a real, "
            "self-contained directory; a symlinked packet root resolves to bytes OUTSIDE the "
            "intended packet (GPT R6)")
    files = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        d = Path(dirpath)
        for name in dirnames:
            sub = d / name
            if sub.is_symlink():
                raise ValueError(
                    f"packet contains a symlinked directory: "
                    f"{sub.relative_to(base).as_posix()} — a frozen packet must be "
                    "self-contained (no symlinks); hashing outside bytes would break the "
                    "content binding")
        for name in filenames:
            p = d / name
            if p.is_symlink():
                raise ValueError(
                    f"packet contains a symlink: {p.relative_to(base).as_posix()} — a "
                    "frozen packet must be self-contained (no symlinks); hashing the "
                    "symlink target's bytes would let content resolve outside the packet")
            if p.is_file():
                files.append(p)
    files.sort(key=lambda p: p.relative_to(base).as_posix())
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(base).as_posix().encode("utf-8"))
        h.update(b"\x00")
        h.update(p.read_bytes())
    return h.hexdigest()


def _resolve_manifest_path(packet_dir: Path, manifest_arg: str | None) -> tuple[Path | None, str | None]:
    """
    Resolve manifest path. Default: <packet-dir>/requirements-manifest.yaml.
    If --manifest is given, it MUST resolve to a path inside packet-dir.
    Rejects absolute escapes and '..' components (like cx_consistency for registry).
    Returns (resolved_path, error_string_or_None).
    """
    packet_resolved = packet_dir.resolve()

    if manifest_arg is None:
        return packet_resolved / "requirements-manifest.yaml", None

    raw = Path(manifest_arg)
    if raw.is_absolute():
        return None, f"--manifest path '{manifest_arg}' is absolute — must be a relative path inside <packet-dir>"

    # Resolve relative to packet_dir
    candidate = (packet_resolved / raw).resolve()
    try:
        candidate.relative_to(packet_resolved)
    except ValueError:
        return None, f"--manifest path '{manifest_arg}' escapes <packet-dir> via '..' — rejected"

    return candidate, None


def _collect_card_data(cards_dir: Path) -> tuple[dict, list]:
    """
    Read every *.yaml card in cards_dir (non-recursive).
    Returns:
      - req_ids_by_card: {card_filename: set(requirement_ids)}
      - hashes_by_card:  [(card_filename, locked_packet_hash)]
    and a list of (card_filename, error) for load failures.
    """
    req_ids_by_card = {}  # filename -> set of req ids
    hashes_by_card = []   # [(filename, hash_str)]
    errors = []

    for card_path in sorted(cards_dir.glob("*.yaml")):
        data, err = load_yaml(str(card_path))
        if err:
            errors.append((card_path.name, f"could not load card: {err}"))
            continue
        if not isinstance(data, dict):
            errors.append((card_path.name, "card is not a YAML mapping"))
            continue

        # Collect requirement_ids from source_map.source_sections[].requirement_ids
        ids = set()
        sections = (
            data.get("source_map", {}).get("source_sections", [])
            if isinstance(data.get("source_map"), dict)
            else []
        )
        if isinstance(sections, list):
            for sec in sections:
                if isinstance(sec, dict):
                    rids = sec.get("requirement_ids", [])
                    if isinstance(rids, list):
                        for r in rids:
                            if r:
                                ids.add(str(r))

        req_ids_by_card[card_path.name] = ids

        # Collect locked_packet_hash
        sm = data.get("source_map", {})
        if isinstance(sm, dict):
            h = sm.get("locked_packet_hash")
            if h:
                hashes_by_card.append((card_path.name, str(h)))

    return req_ids_by_card, hashes_by_card, errors


def cmd_deck(args) -> int:
    cards_dir = Path(args.cards_dir)
    packet_dir = Path(args.packet_dir)
    manifest_arg = getattr(args, "manifest", None)

    findings = []

    # ── Validate cards-dir and packet-dir exist ────────────────────────────
    if not cards_dir.is_dir():
        print(f"FIX-FIRST\n  [P0] {args.cards_dir} — cards-dir not found or not a directory")
        return 1

    if not packet_dir.is_dir():
        print(f"FIX-FIRST\n  [P0] {args.packet_dir} — packet-dir not found or not a directory")
        return 1

    # ── Resolve manifest path (path-escape check) ─────────────────────────
    manifest_path, manifest_err = _resolve_manifest_path(packet_dir, manifest_arg)
    if manifest_err:
        print(f"FIX-FIRST\n  [P1] --manifest — {manifest_err}")
        return 1

    loc_manifest = str(manifest_path)

    # ── Load and validate manifest ─────────────────────────────────────────
    # GATE 6: manifest missing/unparseable
    manifest_data, load_err = load_yaml(str(manifest_path))
    if load_err:
        findings.append(("P1", loc_manifest, f"manifest missing or unparseable: {load_err}"))
        return findings_report(findings)

    if not isinstance(manifest_data, dict):
        findings.append(("P1", loc_manifest, "manifest is not a YAML mapping"))
        return findings_report(findings)

    rows = manifest_data.get("requirements")
    if rows is None:
        findings.append(("P1", loc_manifest, "manifest missing 'requirements' key"))
        return findings_report(findings)

    if not isinstance(rows, list):
        findings.append(("P1", loc_manifest, "'requirements' must be a list"))
        return findings_report(findings)

    # GATE 6: empty requirements list
    if len(rows) == 0:
        findings.append(("P1", loc_manifest, "'requirements' list is empty — nothing to cover is not a pass"))
        return findings_report(findings)

    # Parse manifest rows; collect per-disposition sets
    manifest_ids: dict[str, str] = {}  # id -> disposition
    seen_ids: set[str] = set()
    ceo_refs: list[tuple[str, str, str]] = []  # (row_loc, req_id, ceo_decision_ref)

    for i, row in enumerate(rows):
        row_loc = f"{loc_manifest}#requirements[{i}]"

        if not isinstance(row, dict):
            findings.append(("P1", row_loc, "requirement row is not a mapping"))
            continue

        rid = row.get("id")
        if not rid:
            findings.append(("P1", row_loc, "requirement row missing 'id'"))
            continue
        rid = str(rid)

        # GATE 6: duplicate ids
        if rid in seen_ids:
            findings.append(("P1", loc_manifest, f"duplicate requirement id '{rid}'"))
            continue
        seen_ids.add(rid)

        disp = row.get("disposition")
        if not disp:
            findings.append(("P1", row_loc, f"requirement '{rid}' missing 'disposition'"))
            continue
        disp = str(disp)

        if disp not in VALID_DISPOSITIONS:
            findings.append((
                "P1", row_loc,
                f"requirement '{rid}' has unknown disposition '{disp}' — must be one of {sorted(VALID_DISPOSITIONS)}"
            ))
            continue

        # GATE 3: NOT_APPLICABLE requires reason
        if disp == "NOT_APPLICABLE":
            if not row.get("reason"):
                findings.append(("P1", row_loc, f"requirement '{rid}' disposition=NOT_APPLICABLE missing 'reason'"))

        # GATE 2: NOT_BUILDING and CEO_DEFERRED require ceo_decision_ref
        if disp in ("NOT_BUILDING", "CEO_DEFERRED"):
            if not row.get("ceo_decision_ref"):
                findings.append((
                    "P1", row_loc,
                    f"requirement '{rid}' disposition={disp} missing 'ceo_decision_ref'"
                ))
            else:
                ceo_refs.append((row_loc, rid, str(row.get("ceo_decision_ref"))))

        manifest_ids[rid] = disp

    # Stop here if manifest parsing produced findings — no reliable data for further gates
    if findings:
        return findings_report(findings)

    # ── GATE 7 (PROP-014): every ceo_decision_ref resolves to a ledger row (P1) ──
    if ceo_refs:
        ledger_path = packet_dir / LEDGER_FILE
        if not ledger_path.is_file():
            findings.append((
                "P1", str(ledger_path),
                f"manifest carries ceo_decision_ref(s) but {LEDGER_FILE} is missing from the packet "
                "— a decision that lives in chat is not a decision"
            ))
        else:
            ledger_ids = set(LEDGER_ROW_ID_RE.findall(
                ledger_path.read_text(encoding="utf-8", errors="replace")))
            for row_loc, rid, ref in ceo_refs:
                if ref not in ledger_ids:
                    findings.append((
                        "P1", row_loc,
                        f"requirement '{rid}' ceo_decision_ref '{ref}' does not resolve to a "
                        f"{LEDGER_FILE} row id (CEO-D-NNN) — migrate legacy decisions as CEO-D-LEGACY rows"
                    ))

    # ── Load cards ─────────────────────────────────────────────────────────
    req_ids_by_card, hashes_by_card, card_errors = _collect_card_data(cards_dir)

    for card_name, card_err in card_errors:
        findings.append(("P1", f"{args.cards_dir}/{card_name}", card_err))

    # Aggregate all requirement ids claimed by any card
    all_card_req_ids: set[str] = set()
    for ids in req_ids_by_card.values():
        all_card_req_ids.update(ids)

    # ── GATE 1: BUILDING requirement with no card coverage (P0) ───────────
    for rid, disp in manifest_ids.items():
        if disp == "BUILDING" and rid not in all_card_req_ids:
            findings.append((
                "P0", loc_manifest,
                f"requirement '{rid}' disposition=BUILDING but appears in NO card's requirement_ids — dropped at compile"
            ))

    # ── GATE 4: GHOST requirements (P1) ───────────────────────────────────
    for card_name, card_ids in req_ids_by_card.items():
        card_loc = f"{args.cards_dir}/{card_name}"
        for rid in sorted(card_ids):
            if rid not in manifest_ids:
                findings.append((
                    "P1", card_loc,
                    f"card claims requirement '{rid}' which is not in the manifest — ghost requirement"
                ))

    # ── GATE 5: frozen-hash mismatch (P0) ─────────────────────────────────
    # Recompute packet hash and compare against every card's locked_packet_hash
    try:
        real_hash = _compute_packet_hash(packet_dir)
    except Exception as e:
        findings.append(("P1", args.packet_dir, f"could not compute packet hash: {e}"))
        real_hash = None

    if real_hash is not None:
        for card_name, card_hash in hashes_by_card:
            if card_hash != real_hash:
                findings.append((
                    "P0", f"{args.cards_dir}/{card_name}",
                    f"frozen-hash mismatch: card has '{card_hash}', packet hashes to '{real_hash}' "
                    f"— packet edited after deck cut, or manifest outside frozen hash"
                ))

    # ── Emit result ────────────────────────────────────────────────────────
    if findings:
        return findings_report(findings)

    # PASS: emit coverage summary + list non-BUILDING requirements
    building_ids = [rid for rid, d in manifest_ids.items() if d == "BUILDING"]
    not_building_ids = [(rid, d) for rid, d in manifest_ids.items() if d == "NOT_BUILDING"]
    na_ids = [(rid, d) for rid, d in manifest_ids.items() if d == "NOT_APPLICABLE"]
    deferred_ids = [(rid, d) for rid, d in manifest_ids.items() if d == "CEO_DEFERRED"]

    print("PASS")
    print(
        f"  coverage: {len(building_ids)} building/covered, "
        f"{len(not_building_ids)} not_building, "
        f"{len(na_ids)} not_applicable, "
        f"{len(deferred_ids)} ceo_deferred"
    )
    non_building = [(rid, d) for rid, d in manifest_ids.items() if d != "BUILDING"]
    if non_building:
        print("  dispositioned-out requirements (CEO-visible):")
        for rid, d in non_building:
            print(f"    {rid}: {d}")
    return 0
