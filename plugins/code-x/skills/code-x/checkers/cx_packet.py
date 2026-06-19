"""
cmd_packet: packet-contents floor (PROP-014) — proves the frozen packet CONTAINS
the required planning substance before the deck is cut. Mechanical half of the
completeness-audit gate; the semantic half (fresh cold reader tracing every CEO
ask) stays a model step — this check never claims to replace it.

cx check packet <packet-dir>

Contract (canon: PACKET-CONTENTS.md):
  - coverage-map.yaml INSIDE the packet dir; all 20 category rows present;
    each row status DONE (+ existing, non-trivial file inside the packet) or
    N/A (+ na_because text); always-on categories may never be N/A;
  - requirements-manifest.yaml present (content checked by cx check deck);
  - CEO-DECISION-LEDGER.md present with BOTH required sections
    ("## CEO Asks Register" + "## Decisions"); no ask left MISSING/PARTIAL;
  - completeness-audit.md present, non-trivial, no MISSING/PARTIAL verdicts;
  - locked_style_direction (PROP-016): when coverage category 14 (UI/workflow
    locked designs) is DONE, the packet's PRODUCT-TASTE-LOCK must carry a
    COMPLETE locked_style_direction block (Style-Select outcome) — without it
    the taste lock is incomplete and G7 blocks. Category 14 N/A = not user-facing
    = clause silent.
"""

import re
from pathlib import Path

from cx_common import findings_report, load_yaml

# The 20 V1 coverage categories (PACKET-CONTENTS.md is canon; ids are stable).
REQUIRED_CATEGORY_IDS = set(range(1, 21))

# "always" categories — a packet may never N/A these (the thin-packet floor).
ALWAYS_DONE_IDS = {1, 2, 3, 4, 10, 11, 12, 13, 15, 16, 19, 20}

# Mechanical non-trivial floor for DONE files and the completeness audit.
NON_TRIVIAL_BYTES = 200

LEDGER_FILE = "CEO-DECISION-LEDGER.md"
AUDIT_FILE = "completeness-audit.md"
MANIFEST_FILE = "requirements-manifest.yaml"
COVERAGE_FILE = "coverage-map.yaml"
LEDGER_REQUIRED_SECTIONS = ("## CEO Asks Register", "## Decisions")

# Open-item scan: matches `status: MISSING` / `status: PARTIAL` and the
# table-cell forms `| MISSING |` / `| PARTIAL |` — not bare prose mentions.
OPEN_ITEM_RE = re.compile(r"(?:status:\s*|\|\s*)(MISSING|PARTIAL)\b")


def _resolve_inside(packet_dir: Path, rel: str) -> Path | None:
    """Resolve rel inside packet_dir; None on absolute path or '..' escape."""
    raw = Path(str(rel))
    if raw.is_absolute():
        return None
    candidate = (packet_dir / raw).resolve()
    try:
        candidate.relative_to(packet_dir.resolve())
    except ValueError:
        return None
    return candidate


def _check_coverage_map(packet_dir: Path, findings: list) -> tuple[int, int]:
    """Validate coverage-map.yaml. Returns (done_count, na_count)."""
    cov_path = packet_dir / COVERAGE_FILE
    loc = str(cov_path)

    if not cov_path.is_file():
        findings.append(("P1", loc,
            f"{COVERAGE_FILE} missing — the packet floor starts with the coverage map "
            "(every category DONE-with-file or 'N/A because', inside the frozen hash)"))
        return 0, 0

    data, err = load_yaml(str(cov_path))
    if err or not isinstance(data, dict):
        findings.append(("P1", loc, f"coverage map unreadable: {err or 'not a YAML mapping'}"))
        return 0, 0

    rows = data.get("categories")
    if not isinstance(rows, list) or not rows:
        findings.append(("P1", loc, "coverage map missing non-empty 'categories' list"))
        return 0, 0

    seen_ids: set[int] = set()
    done = na = 0

    for i, row in enumerate(rows):
        row_loc = f"{loc}#categories[{i}]"
        if not isinstance(row, dict):
            findings.append(("P1", row_loc, "category row is not a mapping"))
            continue

        try:
            cid = int(row.get("id"))
        except (TypeError, ValueError):
            findings.append(("P1", row_loc, f"category id '{row.get('id')}' is not an integer"))
            continue

        if cid in seen_ids:
            findings.append(("P1", loc, f"duplicate category id {cid}"))
            continue
        seen_ids.add(cid)

        status = str(row.get("status", "")).strip()

        if status == "DONE":
            done += 1
            rel = row.get("file")
            if not rel:
                findings.append(("P1", row_loc, f"category {cid} DONE but names no 'file'"))
                continue
            target = _resolve_inside(packet_dir, str(rel))
            if target is None:
                findings.append(("P1", row_loc,
                    f"category {cid} file '{rel}' escapes the packet dir — "
                    "packet contents must live inside the frozen hash"))
            elif not target.is_file():
                findings.append(("P1", row_loc,
                    f"category {cid} DONE but file '{rel}' does not exist in the packet"))
            elif target.stat().st_size < NON_TRIVIAL_BYTES:
                findings.append(("P1", row_loc,
                    f"category {cid} file '{rel}' is trivial "
                    f"(<{NON_TRIVIAL_BYTES} bytes) — a stub is not a packet content"))
        elif status == "N/A":
            na += 1
            if cid in ALWAYS_DONE_IDS:
                findings.append(("P1", row_loc,
                    f"category {cid} is always-on and may never be N/A — "
                    "a thin packet must not pass green"))
            elif not str(row.get("na_because", "")).strip():
                findings.append(("P1", row_loc,
                    f"category {cid} N/A without 'na_because' text — skips are written"))
        else:
            findings.append(("P1", row_loc,
                f"category {cid} status '{status}' — must be DONE or N/A"))

    missing = REQUIRED_CATEGORY_IDS - seen_ids
    if missing:
        findings.append(("P1", loc,
            f"coverage map missing category ids {sorted(missing)} — "
            "all 20 categories must be accounted for"))

    return done, na


def _check_ledger(packet_dir: Path, findings: list) -> None:
    led_path = packet_dir / LEDGER_FILE
    loc = str(led_path)

    if not led_path.is_file():
        findings.append(("P1", loc,
            f"{LEDGER_FILE} missing — CEO asks + decisions must live inside the packet, "
            "not in a chat transcript"))
        return

    text = led_path.read_text(encoding="utf-8", errors="replace")
    for section in LEDGER_REQUIRED_SECTIONS:
        if section not in text:
            findings.append(("P1", loc,
                f"ledger missing required section '{section}' — a decision ledger without "
                "the CEO Asks Register lets an ask vanish before it becomes a requirement"))

    open_hits = sorted(set(OPEN_ITEM_RE.findall(text)))
    if open_hits:
        findings.append(("P1", loc,
            f"ledger has open CEO asks ({'/'.join(open_hits)}) — "
            "cannot freeze a packet with MISSING or PARTIAL asks"))


def _check_audit(packet_dir: Path, findings: list) -> None:
    audit_path = packet_dir / AUDIT_FILE
    loc = str(audit_path)

    if not audit_path.is_file():
        findings.append(("P1", loc,
            f"{AUDIT_FILE} missing — the completeness audit (fresh cold reader) must be "
            "appended to the packet before CEO validation and freeze"))
        return

    if audit_path.stat().st_size < NON_TRIVIAL_BYTES:
        findings.append(("P1", loc,
            f"{AUDIT_FILE} is trivial (<{NON_TRIVIAL_BYTES} bytes) — not a real audit"))
        return

    text = audit_path.read_text(encoding="utf-8", errors="replace")
    open_hits = sorted(set(OPEN_ITEM_RE.findall(text)))
    if open_hits:
        findings.append(("P1", loc,
            f"completeness audit has open items ({'/'.join(open_hits)}) — "
            "any MISSING or PARTIAL returns the packet to writing"))


# PROP-016: coverage category for UI / workflow locked designs (PACKET-CONTENTS.md row 14).
STYLE_CATEGORY_ID = 14
STYLE_REQUIRED_KEYS = ("chosen_variant_id", "chosen_variant_path", "accepted_by", "accepted_at")

# A value that is only underscores / angle-bracket placeholder text is not filled in.
_PLACEHOLDER_RE = re.compile(r"^(_{2,}|<[^>]*>)$")


def _style_block_values(text: str) -> dict | None:
    """Extract the locked_style_direction block's key/value pairs from taste-lock text.
    Returns None when no locked_style_direction line exists. Comments stripped."""
    match = re.search(r"^\s*locked_style_direction:\s*$\n((?:[ \t]+\S.*\n?)*)",
                      text, re.MULTILINE)
    if match is None:
        return None
    values = {}
    for line in match.group(1).splitlines():
        kv = re.match(r"^[ \t]+([A-Za-z_]+):[ \t]*(.*)$", line)
        if kv:
            val = kv.group(2).split("#", 1)[0].strip()
            values[kv.group(1)] = "" if _PLACEHOLDER_RE.match(val) else val
    return values


def _check_style_direction(packet_dir: Path, findings: list) -> None:
    """PROP-016: category 14 DONE requires a complete locked_style_direction block."""
    data, err = load_yaml(str(packet_dir / COVERAGE_FILE))
    if err or not isinstance(data, dict):
        return  # coverage clauses already flag an unreadable map
    rows = data.get("categories")
    if not isinstance(rows, list):
        return
    cat = next((r for r in rows if isinstance(r, dict)
                and str(r.get("id")) == str(STYLE_CATEGORY_ID)), None)
    if cat is None or str(cat.get("status", "")).strip() != "DONE":
        return  # missing id / N/A handled by the coverage clauses; N/A = not user-facing

    locks = sorted(p for p in packet_dir.rglob("*")
                   if p.is_file() and "product-taste-lock" in p.name.lower())
    if not locks:
        findings.append(("P1", str(packet_dir),
            f"category {STYLE_CATEGORY_ID} (UI/workflow locked designs) is DONE but the packet "
            "has no PRODUCT-TASTE-LOCK file — locked_style_direction unverifiable; G7 blocks"))
        return

    lock_path = locks[0]
    loc = str(lock_path)
    block = _style_block_values(lock_path.read_text(encoding="utf-8", errors="replace"))
    if block is None:
        findings.append(("P1", loc,
            "taste lock has no locked_style_direction block (PROP-016) — Style-Select outcome "
            "not recorded; the taste lock is incomplete and G7 blocks"))
        return

    applicable = block.get("applicable", "")
    if not applicable:
        findings.append(("P1", loc,
            "locked_style_direction.applicable empty — must be 'yes' or 'NOT_APPLICABLE (why: ...)'"))
    elif applicable.lower().startswith("yes"):
        missing = [k for k in STYLE_REQUIRED_KEYS if not block.get(k)]
        if missing:
            findings.append(("P1", loc,
                f"locked_style_direction applicable but incomplete — missing {missing}; "
                "an unfilled style lock is not a CEO pick and G7 blocks"))
    elif "not_applicable" in applicable.lower():
        if not re.search(r"why\s*:\s*\S", applicable, re.IGNORECASE):
            findings.append(("P1", loc,
                "locked_style_direction NOT_APPLICABLE without a written why — skips are written"))
    else:
        findings.append(("P1", loc,
            f"locked_style_direction.applicable '{applicable}' — must be 'yes' or "
            "'NOT_APPLICABLE (why: ...)'"))


def cmd_packet(args) -> int:
    packet_dir = Path(args.packet_dir)

    if not packet_dir.is_dir():
        print(f"FIX-FIRST\n  [P0] {args.packet_dir} — packet-dir not found or not a directory")
        return 1

    findings: list[tuple[str, str, str]] = []

    done, na = _check_coverage_map(packet_dir, findings)

    manifest = packet_dir / MANIFEST_FILE
    if not manifest.is_file():
        findings.append(("P1", str(manifest),
            f"{MANIFEST_FILE} missing — the manifest lives inside the frozen packet hash "
            "(content is cx check deck's contract)"))

    _check_ledger(packet_dir, findings)
    _check_audit(packet_dir, findings)
    _check_style_direction(packet_dir, findings)

    if findings:
        return findings_report(findings)

    print("PASS")
    print(f"  coverage: {done} categories DONE, {na} written-N/A (all 20 accounted for)")
    print(f"  floor: {COVERAGE_FILE} · {MANIFEST_FILE} · {LEDGER_FILE} (asks+decisions) · {AUDIT_FILE}")
    return 0
