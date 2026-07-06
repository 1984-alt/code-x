"""
cmd_packet: packet-contents floor (P-PROP-001) — proves the frozen packet CONTAINS
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
  - locked_style_direction (P-PROP-002): when coverage category 14 (UI/workflow
    locked designs) is DONE, the packet's PRODUCT-TASTE-LOCK must carry a
    COMPLETE locked_style_direction block (Style-Select outcome) — without it
    the taste lock is incomplete and G7 blocks. Category 14 N/A = not user-facing
    = clause silent.
  - clarify-before-freeze (P-PROP-003a): a STRUCTURED clarification-sweep.yaml
    records the WRITING-stage ambiguity pass; every clarification it lists must
    RESOLVE to a real CEO-DECISION-LEDGER row (no inline free-text dismissal); any
    unresolved [NEEDS-CLARIFICATION: …] marker surviving in a content doc (any
    non-binary file; only the root sweep is excluded) blocks freeze.
  - testable acceptance criterion (P-PROP-003b): every BUILDING requirement carries
    a structured acceptance_criterion {pass_condition, evidence_type,
    verification_ref}, present + non-placeholder STRING. PRESENCE/structure only —
    the cold-reader completeness audit judges whether the criterion is testable.
  - Given/When/Then examples (PB-PROP-003 Unit 1): a BUILDING requirement's
    acceptance_criterion carries >=1 well-formed {given, when, then} example UNLESS
    the row declares a typed + anchored non_behavioral_exemption {reason, artifact_ref}
    (reason in a frozen 6-value vocabulary; artifact_ref resolves to a real in-packet
    file/manifest/registry anchor). Authoring examples is LITE-relaxable ceremony;
    exemption validity + shape of any present examples are enforced at every tier.
"""

import hashlib
import re
from pathlib import Path

from cx_common import VALID_RISK_TIERS, findings_report, load_yaml, resolve_risk_tier

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


# SOP coverage map (PBAF-PROP-001 Lever B): all 13 SOP layers, each with a
# verdict (APPLIES/PARTIAL/N_A) + the driving build-fact (A1-A9) behind any N/A.
SOP_COVERAGE_FILE = "sop-coverage-map.yaml"
SOP_REQUIRED_LAYER_IDS = set(range(1, 14))
SOP_VALID_VERDICTS = {"APPLIES", "PARTIAL", "N_A"}


def _check_sop_coverage_map(packet_dir: Path, findings: list) -> None:
    """Validate sop-coverage-map.yaml (PBAF-PROP-001 Lever B / SOP-BIND-COVERAGE-MAP)."""
    cov_path = packet_dir / SOP_COVERAGE_FILE
    loc = str(cov_path)

    if not cov_path.is_file():
        findings.append(("P1", loc,
            f"SOP-BIND-COVERAGE-MAP: {SOP_COVERAGE_FILE} missing — a Planning packet with no SOP "
            "coverage map (all 13 layers, each APPLIES/PARTIAL/N/A + driving fact) has not scoped "
            "the standard (PBAF-PROP-001 Lever B)"))
        return

    data, err = load_yaml(str(cov_path))
    if err or not isinstance(data, dict):
        findings.append(("P1", loc,
            f"SOP-BIND-COVERAGE-MAP: {SOP_COVERAGE_FILE} unreadable: {err or 'not a YAML mapping'}"))
        return

    rows = data.get("layers")
    if not isinstance(rows, list) or not rows:
        findings.append(("P1", loc,
            "SOP-BIND-COVERAGE-MAP: coverage map missing non-empty 'layers' list"))
        return

    seen_ids: set[int] = set()
    for i, row in enumerate(rows):
        row_loc = f"{loc}#layers[{i}]"
        if not isinstance(row, dict):
            findings.append(("P1", row_loc, "SOP-BIND-COVERAGE-MAP: layer row is not a mapping"))
            continue
        try:
            lid = int(row.get("id"))
        except (TypeError, ValueError):
            findings.append(("P1", row_loc,
                f"SOP-BIND-COVERAGE-MAP: layer id '{row.get('id')}' is not an integer"))
            continue
        seen_ids.add(lid)
        verdict = str(row.get("verdict", "")).strip()
        if verdict not in SOP_VALID_VERDICTS:
            findings.append(("P1", row_loc,
                f"SOP-BIND-COVERAGE-MAP: layer {lid} verdict '{verdict}' — must be one of "
                f"{sorted(SOP_VALID_VERDICTS)}"))
        elif verdict == "N_A" and not str(row.get("driving_fact", "")).strip():
            findings.append(("P1", row_loc,
                f"SOP-BIND-COVERAGE-MAP: layer {lid} verdict N_A with no 'driving_fact' — N/A must be "
                "derived from a named build-fact, never asserted by opinion (PBAF-PROP-001 Rule 1)"))

    missing = SOP_REQUIRED_LAYER_IDS - seen_ids
    if missing:
        findings.append(("P1", loc,
            f"SOP-BIND-COVERAGE-MAP: coverage map missing layer ids {sorted(missing)} — "
            "all 13 SOP layers must be accounted for"))


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


# P-PROP-002: coverage category for UI / workflow locked designs (PACKET-CONTENTS.md row 14).
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
    """P-PROP-002: category 14 DONE requires a complete locked_style_direction block."""
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
            "taste lock has no locked_style_direction block (P-PROP-002) — Style-Select outcome "
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


# PBF-PROP-019 (design v2 §1, P2-6): risk_tier is declared as a top-level scalar in
# requirements-manifest.yaml (the one packet doc every project has, UI or not — unlike
# the optional PRODUCT-TASTE-LOCK). This is its OWN explicit parser+validator — it does
# NOT reuse _check_style_direction (that precedent gives enum-validation + ledger-ref
# resolution ONLY, per the v2 design note; absent->STRICT is written explicitly here).
RISK_TIER_DECISION_REF_FIELD = "risk_tier_decision_ref"


def _check_risk_tier(packet_dir: Path, findings: list) -> None:
    """PACKET-RISK-TIER-WELL-FORMED (P0): a present-but-invalid risk_tier value fails;
    a declared LITE/STANDARD without a resolving risk_tier_decision_ref fails. STRICT
    (declared or defaulted) needs no ref. PACKET-RISK-TIER-DEFAULTS-STRICT: absence
    resolves STRICT — proven by cx_common.resolve_risk_tier + the tier-dodge eval, not
    a written flag here (an absent field is NOT a finding)."""
    manifest_path = packet_dir / MANIFEST_FILE
    data, err = load_yaml(str(manifest_path))
    if err or not isinstance(data, dict):
        return  # manifest missing/malformed is already flagged elsewhere in cmd_packet
    if "risk_tier" not in data or data.get("risk_tier") is None:
        return  # absent — resolves STRICT, no error (PACKET-RISK-TIER-DEFAULTS-STRICT)

    raw = data.get("risk_tier")
    val = str(raw).strip().upper() if isinstance(raw, str) else None
    if val not in VALID_RISK_TIERS:
        findings.append(("P0", str(manifest_path),
            f"risk_tier '{raw!r}' is not one of LITE/STANDARD/STRICT — a present-but-invalid "
            "risk tier is never silently coerced to a default "
            "(PACKET-RISK-TIER-WELL-FORMED, PBF-PROP-019)"))
        return

    if val in ("LITE", "STANDARD"):
        ref = str(data.get(RISK_TIER_DECISION_REF_FIELD, "") or "").strip()
        ledger_ids = _ledger_row_ids(packet_dir)
        if not _LEDGER_ROW_ID_RE.fullmatch(ref) or ref not in ledger_ids:
            findings.append(("P0", str(manifest_path),
                f"risk_tier: {val} declared without a resolving {RISK_TIER_DECISION_REF_FIELD} — "
                "choosing a lighter-than-STRICT tier is a CEO decision and must resolve to a real "
                f"{LEDGER_FILE} row id (CEO-D-NNN), never inline free text "
                "(PACKET-RISK-TIER-WELL-FORMED, PBF-PROP-019)"))


# CX-PB003-002 FIX-FIRST (xfam finding 2, P1): the PB-PROP-003 §R5 capability marker — mirrors
# cx_module_acceptance._PB_PROP_003_MARKER_FIELD (same field, same manifest, checked at the OTHER
# end of its lifecycle: freeze-time here vs acceptance-time there).
PB_PROP_003_WIRING_FIELD = "pb_prop_003_wiring"


def _check_pb_prop_003_wiring_marker(packet_dir: Path, findings: list) -> None:
    """PACKET-PB-PROP-003-MARKER-WELL-FORMED (P1): mirrors _check_risk_tier's "absence is fine,
    a present-but-invalid value is not" precedent. A packet that never declares the marker gets
    the legacy carve-out at acceptance time (fine, no finding here). A packet that DOES declare it
    but with a non-boolean-true value (a quoted "true"/"yes", 1, etc.) is malformed — caught here
    at freeze so it never reaches acceptance-time and silently falls to the legacy carve-out there
    (the exact bug xfam finding CX-PB003-002 closes)."""
    manifest_path = packet_dir / MANIFEST_FILE
    data, err = load_yaml(str(manifest_path))
    if err or not isinstance(data, dict):
        return  # manifest missing/malformed is already flagged elsewhere in cmd_packet
    if PB_PROP_003_WIRING_FIELD not in data:
        return  # absent — legitimate legacy carve-out, no finding
    if data.get(PB_PROP_003_WIRING_FIELD) is not True:
        findings.append(("P1", str(manifest_path),
            f"{PB_PROP_003_WIRING_FIELD}: {data.get(PB_PROP_003_WIRING_FIELD)!r} is present but not "
            "a real boolean true — a packet that TRIED to opt into the PB-PROP-003 wiring gate and "
            "botched the marker must fail closed at freeze, not silently fall to the legacy "
            "carve-out at acceptance time (only genuine ABSENCE of this field is a legitimate "
            "non-opt-in) (PACKET-PB-PROP-003-MARKER-WELL-FORMED, PB-PROP-003 §R5, xfam finding "
            "CX-PB003-002)"))


# B-PROP-013 §4 (design-history/b-prop-013-forge-parity-design-2026-07-06.md, the "ships-dark
# fix" — council fix #1): mirrors cx_module_acceptance.FORGE_PARITY_MARKER_FIELD (same field,
# same manifest, checked at the OTHER end of the lifecycle: freeze here vs acceptance there).
# UNLIKE PB_PROP_003_WIRING_FIELD above (where absence is a legitimate legacy carve-out), this
# marker is REQUIRED-TRUE for every NEW packet — a marker left absent would ride the legacy
# presence-only acceptance path forever, making "on now" on-paper only. --legacy-migration is
# the SAME escape hatch cx_design_fidelity.py already uses for a genuinely in-flight project's
# documented migration debt (already-shipped apps) — never for a new packet.
FORGE_PARITY_MARKER_FIELD = "b_prop_013_forge_parity"

# FIX-FIRST (B-PROP-013 xfam P1): --legacy-migration used to be a BLANKET self-waiver — any NEW
# packet could pass the bare flag and skip the required-true marker forever, defeating the
# ships-dark closer §4 was built to close. It must now carry a TYPED, resolvable proof:
#   (a) --migration-ref <CEO-D-NNN> resolving to a REAL row in the PROTOCOL-level
#       MEMORY/CEO-DECISION-LEDGER.md (repo-root, NOT the packet's own ledger — a migration
#       waiver is a protocol-level decision) — a ref that merely LOOKS like an id but names no
#       real row does not count (mirrors _check_clarification_sweep's ledger-resolution
#       precedent), or
#   (b) the packet already carries a pre-existing frozen MODULE-REGISTRY.yaml with a non-empty
#       module_registry.frozen_packet_hash — proof the packet was ALREADY frozen (genuinely
#       in-flight), not merely asserted by the flag.
# A bare --legacy-migration with neither proof does NOT waive — it falls through to the same
# marker-required check a packet with no flag at all gets.
_THIS_DIR = Path(__file__).resolve().parent


def _protocol_ledger_row_ids() -> set:
    """Real CEO-D-NNN row ids in the PROTOCOL-level MEMORY/CEO-DECISION-LEDGER.md (repo root) —
    distinct from _ledger_row_ids, which reads the PACKET's own ledger file."""
    led = _THIS_DIR.parent / "MEMORY" / LEDGER_FILE
    if not led.is_file():
        return set()
    return set(_LEDGER_ROW_ID_RE.findall(led.read_text(encoding="utf-8", errors="replace")))


def _legacy_migration_proven(packet_dir: Path, migration_ref: str) -> bool:
    """FIX-FIRST (B-PROP-013 §4): True only when --legacy-migration carries one of the two typed
    proofs documented above. See module-level comment for the full rationale."""
    ref = str(migration_ref or "").strip()
    if ref and _LEDGER_ROW_ID_RE.fullmatch(ref) and ref in _protocol_ledger_row_ids():
        return True
    reg_path = packet_dir / REGISTRY_FILE
    if reg_path.is_file():
        rdata, rerr = load_yaml(str(reg_path))
        mr = rdata.get("module_registry") if isinstance(rdata, dict) else None
        fph = str(mr.get("frozen_packet_hash", "") or "").strip() if isinstance(mr, dict) else ""
        if not rerr and fph:
            return True
    return False


def _check_forge_parity_marker_required(packet_dir: Path, findings: list, legacy_migration: bool,
                                        migration_ref: str = "") -> None:
    """PACKET-FORGE-PARITY-MARKER-REQUIRED (P1): a NEW packet's requirements-manifest.yaml must
    declare b_prop_013_forge_parity: true (a real boolean true) — absence OR a botched value
    (quoted "true"/"yes", 1, etc.) both fail here for a new packet. --legacy-migration exempts a
    genuinely in-flight, already-frozen project ONLY when it carries a typed, resolvable proof
    (--migration-ref resolving to a real protocol ledger row, OR a pre-existing frozen
    MODULE-REGISTRY.yaml hash) — a bare --legacy-migration with no proof does NOT waive (FIX-FIRST:
    was previously an unconditional self-waiver, closed per xfam P1)."""
    if legacy_migration and _legacy_migration_proven(packet_dir, migration_ref):
        return  # grandfathered in-flight packet WITH resolvable proof — exempt
    manifest_path = packet_dir / MANIFEST_FILE
    data, err = load_yaml(str(manifest_path))
    if err or not isinstance(data, dict):
        return  # manifest missing/malformed is already flagged elsewhere in cmd_packet
    if data.get(FORGE_PARITY_MARKER_FIELD) is not True:
        proof_note = (
            " (--legacy-migration was passed but carries NO resolvable proof — a bare flag is "
            "not a waiver; supply --migration-ref <CEO-D-NNN> resolving to a real MEMORY/"
            "CEO-DECISION-LEDGER.md row, or freeze the packet with a pre-existing MODULE-"
            "REGISTRY.yaml frozen_packet_hash)"
        ) if legacy_migration else ""
        findings.append(("P1", str(manifest_path),
            f"{FORGE_PARITY_MARKER_FIELD} is not declared as a real boolean true{proof_note} — "
            "every NEW packet must opt into the B-PROP-013 forge-parity acceptance-recompute "
            "guard at the WRITING floor (a marker left absent rides the legacy presence-only "
            "acceptance path forever, making 'on now' on-paper only, the ships-dark hole "
            "B-PROP-013 §4 closes); pass --legacy-migration WITH resolvable proof ONLY for a "
            "genuinely in-flight project's documented migration debt, never for a new packet "
            "(PACKET-FORGE-PARITY-MARKER-REQUIRED, B-PROP-013 §4)"))


# P-PROP-004: external-visual-reference must be captured + locked.
SCREENS_FILE = "screens-manifest.yaml"
EXTERNAL_REF_FILE = "external-visual-references.yaml"
VALID_PROVENANCE = {"original", "external_reference", "derived_from_locked_style"}
G6_AXES = {"density", "typography", "color_mood", "layout_character"}
# Advisory heuristic only (never blocks): fidelity language pointing at an external look.
_FIDELITY_LANG_RE = re.compile(
    r"\b(?:looks?|feels?)\s+like\b|\blike\s+the\b|\bsame\s+as\b|\bmatch(?:es|ing)?\b|"
    r"\bclone\s+of\b|\bjust\s+like\b", re.IGNORECASE)
# A declared hash must be a lowercase-hex sha256 prefix (12–64 chars) — a 1–2 char
# "hash" must never pass via startswith (GPT built-code review P1).
_HEX_HASH_RE = re.compile(r"[0-9a-f]{12,64}")


def _packet_path_unsafe(ref, base: Path) -> str | None:
    """P-PROP-004 / v1.10 path-safety: reject empty, absolute, '..'-escape, symlink, or
    out-of-packet. Returns a reason string when unsafe, else None (captures live INSIDE
    the frozen packet — self-contained)."""
    if not ref or not isinstance(ref, str):
        return "empty / non-string path"
    if Path(ref).is_absolute() or ".." in Path(ref).parts:
        return "absolute path or '..' escape"
    try:
        rp = base / ref
        if rp.is_symlink() or not rp.resolve().is_relative_to(base.resolve()):
            return "symlink or resolves outside the packet"
    except OSError as e:
        return f"unresolvable path: {e}"
    return None


def _cat14_done(packet_dir: Path) -> bool:
    """True when coverage category 14 (UI/workflow locked designs) is DONE = user-facing app."""
    data, err = load_yaml(str(packet_dir / COVERAGE_FILE))
    if err or not isinstance(data, dict) or not isinstance(data.get("categories"), list):
        return False
    cat = next((r for r in data["categories"] if isinstance(r, dict)
                and str(r.get("id")) == str(STYLE_CATEGORY_ID)), None)
    return cat is not None and str(cat.get("status", "")).strip() == "DONE"


def _check_capture_manifest(ext_path: Path, packet_dir: Path, rdata: dict,
                            findings: list) -> dict:
    """P-PROP-004 clause (2): integrity-check the external-visual-references.yaml capture
    manifest — every capture pinned + path-safe + file_hash matches the real bytes, and
    a manifest_hash binds the declared (ref_id · file_hash · file_path · viewport) set, and no
    duplicate ref_id is allowed. Returns the ref index."""
    refs = [r for r in rdata.get("references", []) if isinstance(r, dict)]
    index = {}
    seen_ids = set()
    for r in refs:
        rid = str(r.get("ref_id", "?"))
        if rid in seen_ids:
            findings.append(("P1", str(ext_path),
                f"duplicate ref_id '{rid}' in {EXTERNAL_REF_FILE} — one ref_id binds one capture "
                "(P-PROP-004)"))
        seen_ids.add(rid)
        index[rid] = r
        unsafe = _packet_path_unsafe(r.get("file_path"), packet_dir)
        if unsafe:
            findings.append(("P1", str(ext_path),
                f"reference '{rid}' file_path unsafe — {unsafe} (P-PROP-004)"))
            continue
        fpath = packet_dir / str(r.get("file_path"))
        if not fpath.is_file():
            findings.append(("P1", str(ext_path),
                f"reference '{rid}' file_path '{r.get('file_path')}' is not a pinned file inside "
                "the packet — a chat 'I confirmed the UX' is not a captured reference (P-PROP-004)"))
            continue
        declared = str(r.get("file_hash", "")).strip().lower()
        actual = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if not _HEX_HASH_RE.fullmatch(declared):
            findings.append(("P1", str(ext_path),
                f"reference '{rid}' file_hash '{declared[:16]}' is not a lowercase-hex sha256 prefix "
                "(12–64 chars) — the capture is not hash-bound (P-PROP-004)"))
        elif not actual.startswith(declared):
            findings.append(("P1", str(ext_path),
                f"reference '{rid}' file_hash mismatch — declared {declared[:12]}…, actual "
                f"{actual[:12]}… (the capture changed since freeze, P-PROP-004)"))
    # manifest_hash binds EVERY field the gates trust (ref_id · file_hash · file_path · viewport),
    # so a tampered path or viewport cannot change behavior without breaking the hash.
    expected = hashlib.sha256("\n".join(
        f"{r.get('ref_id')}:{str(r.get('file_hash', '')).strip().lower()}:"
        f"{r.get('file_path')}:{r.get('viewport')}"
        for r in sorted(refs, key=lambda x: str(x.get("ref_id", "")))).encode()).hexdigest()
    declared_m = str(rdata.get("manifest_hash", "")).strip().lower()
    if not _HEX_HASH_RE.fullmatch(declared_m):
        findings.append(("P1", str(ext_path),
            f"{EXTERNAL_REF_FILE} manifest_hash '{declared_m[:16]}' missing or not a lowercase-hex "
            "sha256 prefix (12–64 chars) binding the capture set (P-PROP-004)"))
    elif not expected.startswith(declared_m):
        findings.append(("P1", str(ext_path),
            f"manifest_hash mismatch — declared {declared_m[:12]}…, computed {expected[:12]}… "
            "(the captured set changed since freeze, P-PROP-004)"))
    return index


def _check_visual_provenance(packet_dir: Path, findings: list) -> None:
    """P-PROP-004: every user-facing screen declares visual_provenance; external_reference
    screens require a captured, pinned, hash-bound reference + scope + viewport coverage.
    Gated on category 14 DONE (user-facing app); category 14 N/A = clause silent.
    GREEN MEANS the real reference was captured/pinned/bound — NOT that fidelity was
    achieved (that stays the CEO's taste gate)."""
    if not _cat14_done(packet_dir):
        return

    screens_path = packet_dir / SCREENS_FILE
    sdata, serr = load_yaml(str(screens_path))
    if serr or not isinstance(sdata, dict) or not isinstance(sdata.get("screens"), list):
        findings.append(("P1", str(screens_path),
            f"category {STYLE_CATEGORY_ID} (user-facing app) is DONE but {SCREENS_FILE} is missing "
            "or has no 'screens:' list — EVERY user-facing screen must declare its visual_provenance "
            f"({sorted(VALID_PROVENANCE)}); 'like MM' can no longer be a silent prose aside (P-PROP-004)"))
        return

    raw_rows = sdata["screens"]
    screens = [s for s in raw_rows if isinstance(s, dict)]
    if len(screens) != len(raw_rows):
        findings.append(("P1", str(screens_path),
            "screens-manifest has non-mapping screen rows — every screen entry must be a mapping "
            "carrying a visual_provenance (P-PROP-004)"))
    if not [s for s in screens if s.get("user_facing") is not False]:
        findings.append(("P1", str(screens_path),
            f"category {STYLE_CATEGORY_ID} is DONE but screens-manifest declares no user-facing "
            "screen — a user-facing app has user-facing screens to give provenance for; an empty "
            "list cannot pass the provenance gate (P-PROP-004)"))
    ext_path = packet_dir / EXTERNAL_REF_FILE
    ref_index, refs_loaded = {}, False

    def _refs():
        nonlocal ref_index, refs_loaded
        if not refs_loaded:
            refs_loaded = True
            rdata, rerr = load_yaml(str(ext_path))
            if not rerr and isinstance(rdata, dict) and isinstance(rdata.get("references"), list):
                ref_index = _check_capture_manifest(ext_path, packet_dir, rdata, findings)
            else:
                ref_index = None  # missing / malformed manifest
        return ref_index

    for s in screens:
        if s.get("user_facing") is False:
            continue
        sid = str(s.get("id", "?"))
        prov = str(s.get("visual_provenance", "")).strip()
        blob = " ".join(str(v) for v in s.values())
        if prov not in VALID_PROVENANCE:
            findings.append(("P1", str(screens_path),
                f"screen '{sid}' visual_provenance '{prov or '(missing)'}' is not one of "
                f"{sorted(VALID_PROVENANCE)} — a screen cannot reach build with its look-source "
                "unstated (P-PROP-004)"))
            if _FIDELITY_LANG_RE.search(blob):
                print(f"WARN: screen '{sid}' reads like an external reference but declares no valid "
                      "visual_provenance — declare external_reference or dismiss "
                      "(P-PROP-004 advisory, non-blocking)")
            continue
        if prov != "external_reference":
            if _FIDELITY_LANG_RE.search(blob):
                print(f"WARN: screen '{sid}' reads like an external reference but is declared "
                      f"'{prov}' — confirm intentional (P-PROP-004 advisory, non-blocking)")
            continue

        # external_reference screen: binding + scope + viewport coverage.
        index = _refs()
        if index is None:
            findings.append(("P1", str(ext_path),
                f"screen '{sid}' is visual_provenance: external_reference but {EXTERNAL_REF_FILE} "
                "is missing or malformed — the captured reference must be pinned inside the packet "
                "(P-PROP-004)"))
            continue
        ids = [str(x) for x in (s.get("external_reference_ids") or [])]
        viewports = [str(x) for x in (s.get("target_viewports") or [])]
        missing = [f for f, v in (("external_reference_ids", ids),
                                  ("target_viewports", viewports)) if not v]
        if s.get("borrowed_axes") is None:
            missing.append("borrowed_axes")
        if s.get("excluded_axes") is None:
            missing.append("excluded_axes")
        if missing:
            findings.append(("P1", str(screens_path),
                f"screen '{sid}' (external_reference) missing scope/binding fields {missing} — "
                "borrowed/excluded axes make 'like MM for layout, original for content' explicit, "
                "not guessed (P-PROP-004)"))
        for axis in ([str(a) for a in (s.get("borrowed_axes") or [])]
                     + [str(a) for a in (s.get("excluded_axes") or [])]):
            if axis not in G6_AXES and not axis.startswith("region:"):
                findings.append(("P2", str(screens_path),
                    f"screen '{sid}' axis '{axis}' is not a G6 axis {sorted(G6_AXES)} nor a "
                    "'region:<name>' — scope is unclear (P-PROP-004)"))
        for rid in ids:
            if rid not in index:
                findings.append(("P1", str(ext_path),
                    f"screen '{sid}' references ref_id '{rid}' absent from {EXTERNAL_REF_FILE} "
                    "(P-PROP-004)"))
        covered = {str(index[rid].get("viewport", "")) for rid in ids if rid in index}
        for vp in viewports:
            if vp not in covered:
                findings.append(("P1", str(ext_path),
                    f"screen '{sid}' target viewport '{vp}' has no reference capture at that "
                    "viewport — a mobile-only capture cannot authorize other viewports (P-PROP-004)"))


# P-PROP-003(a): clarify-before-freeze. A STRUCTURED sweep artifact (clarification-sweep.yaml)
# records the WRITING-stage ambiguity pass; every clarification it lists must resolve to a
# CEO-DECISION-LEDGER row (no inline free-text dismissal), and no [NEEDS-CLARIFICATION] marker
# may survive in a content doc. (Built-code GPT/Codex review fix: a structured artifact closes
# the fake-ref / case-variant / false-positive bypasses a free-text doc could not.)
SWEEP_FILE = "clarification-sweep.yaml"
CLARIFY_MARKER = "[NEEDS-CLARIFICATION"
# Binary captures (P-PROP-004 pngs, fonts, archives) are skipped; EVERYTHING else is scanned —
# a denylist (not a text-extension allowlist) so a marker hidden in .json / a no-extension
# file cannot dodge the scan (built-code review P1).
_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svgz",
                    ".pdf", ".zip", ".gz", ".tar", ".tgz", ".woff", ".woff2", ".ttf",
                    ".otf", ".eot", ".mp4", ".mov", ".webm", ".mp3", ".wav", ".so",
                    ".dylib", ".pyc"}
# Real ledger row ids (mirror cx_deck.LEDGER_ROW_ID_RE) — a ceo_decision_ref must RESOLVE to
# one of these, not merely look like one (a fake CEO-D-99999 must NOT pass — built-code review P1).
_LEDGER_ROW_ID_RE = re.compile(r"\bCEO-D-[A-Z0-9][A-Z0-9-]*\b")

# P-PROP-003(b): testable acceptance criterion on BUILDING rows — structured STRING fields,
# present + non-placeholder. This is a PRESENCE + structure gate, NOT an English-quality gate:
# the cold-reader completeness audit (Piece 2 semantic half) judges whether the criterion is
# actually testable. A literal "is this measurable" checker would over-claim — the cardinal sin.
ACCEPTANCE_FIELD = "acceptance_criterion"
ACCEPTANCE_KEYS = ("pass_condition", "evidence_type", "verification_ref")
# PB-PROP-003 Unit 1 (packet stage, Design Resolution v2 §R4): a BUILDING requirement's
# non_behavioral_exemption reason, frozen vocabulary — no free-text hatch. Deliberately excludes
# accessibility/performance (those are runtime-testable behavior, not exempt).
NON_BEHAVIORAL_EXEMPTION_REASONS = {"visual", "data_shape", "config", "content",
                                     "operational", "security_invariant"}
# Obvious non-answers — a blank or placeholder is not a filled-in criterion.
_AC_PLACEHOLDER_TOKENS = {"", "tbd", "tba", "todo", "fixme", "n/a", "na", "none", "null",
                         "?", "??", "???", ".", "..", "...", "-", "x", "xxx",
                         "placeholder", "pending", "wip"}


def _ac_is_placeholder(val) -> bool:
    """True when val is not a real written criterion: a non-string (bool / number / list /
    dict — built-code review P1: `pass_condition: true` must not pass via str-coercion), or a
    blank / placeholder string. NOT an English-quality judgment — the cold-reader audit judges
    whether a real value is testable (P-PROP-003b)."""
    if not isinstance(val, str):
        return True
    v = val.strip()
    if not v or _PLACEHOLDER_RE.match(v):
        return True
    return v.lower() in _AC_PLACEHOLDER_TOKENS


def _ledger_row_ids(packet_dir: Path) -> set:
    """Real CEO-D-NNN row ids declared in the packet's decision ledger (for ref resolution)."""
    led = packet_dir / LEDGER_FILE
    if not led.is_file():
        return set()
    return set(_LEDGER_ROW_ID_RE.findall(led.read_text(encoding="utf-8", errors="replace")))


def _check_clarification_sweep(packet_dir: Path, findings: list) -> None:
    """P-PROP-003(a): a STRUCTURED clarification-sweep.yaml records the WRITING-stage ambiguity
    pass; every clarification it lists RESOLVES to a real CEO-DECISION-LEDGER row (no inline
    free-text dismissal); and no [NEEDS-CLARIFICATION] marker survives in any content doc.
    GREEN = the sweep ran + every raised point is ledger-bound — NOT that the packet is
    unambiguous (the cold reader still judges that). Empty clarifications list = swept, none
    raised = PASS."""
    sweep_path = packet_dir / SWEEP_FILE
    if not sweep_path.is_file():
        findings.append(("P1", str(sweep_path),
            f"{SWEEP_FILE} missing — the clarify-before-freeze ambiguity sweep must run and be "
            "recorded (structured); absence of markers is not proof the sweep ran (P-PROP-003a)"))
    else:
        data, err = load_yaml(str(sweep_path))
        block = data.get("clarification_sweep") if isinstance(data, dict) else None
        rows = block.get("clarifications") if isinstance(block, dict) else None
        if err or not isinstance(block, dict) or not isinstance(rows, list):
            findings.append(("P1", str(sweep_path),
                f"{SWEEP_FILE} malformed — needs a 'clarification_sweep.clarifications' list "
                "(may be empty when nothing was raised); a doc that does not parse is not a "
                f"sweep ({err or 'wrong shape'}, P-PROP-003a)"))
        else:
            ledger_ids = _ledger_row_ids(packet_dir)
            for j, row in enumerate(rows):
                row_loc = f"{sweep_path}#clarifications[{j}]"
                if not isinstance(row, dict):
                    findings.append(("P1", row_loc, "clarification row is not a mapping (P-PROP-003a)"))
                    continue
                ref = str(row.get("ceo_decision_ref", "")).strip()
                if not _LEDGER_ROW_ID_RE.fullmatch(ref) or ref not in ledger_ids:
                    findings.append(("P1", row_loc,
                        f"clarification ceo_decision_ref '{ref or '(missing)'}' does not resolve to "
                        f"a {LEDGER_FILE} row id (CEO-D-NNN) — every clarification (incl. a "
                        "NOT_APPLICABLE dismissal) must be ledger-bound, never inline free text; "
                        "a ref that merely looks valid but names no real row is the self-exemption "
                        "escape hatch P-PROP-003 rejects (P-PROP-003a)"))

                # RULE-CONFLICT-IS-OPEN-CLARIFICATION (PBF-PROP-020 Rule 5): a rule-conflict
                # clarification resolves only with BOTH a resolution_lock_ref (a mockup showing
                # the resolved look, ties to Rule 6 replace) AND a resolved ceo_decision_ref
                # (checked above) — no loose list, this rides the SAME sweep machinery.
                if str(row.get("kind", "") or "").strip() == "rule-conflict":
                    rlr = str(row.get("resolution_lock_ref", "") or "").strip()
                    target = _resolve_inside(packet_dir, rlr) if rlr else None
                    if not rlr or target is None or not target.is_file():
                        findings.append(("P1", row_loc,
                            "rule-conflict clarification has no resolving resolution_lock_ref — a "
                            "rule-conflict resolves only with a mockup showing the resolved look "
                            "(ties to Rule 6 replace), never CEO decision text alone "
                            "(RULE-CONFLICT-IS-OPEN-CLARIFICATION, PBF-PROP-020 Rule 5)"))

    # Any unresolved marker in a CONTENT doc blocks freeze. Only the ROOT sweep file is excluded
    # (by resolved path — a nested sub/clarification-sweep.yaml hiding a marker cannot pass).
    sweep_resolved = sweep_path.resolve()
    for path in sorted(packet_dir.rglob("*")):
        if (not path.is_file() or path.suffix.lower() in _BINARY_SUFFIXES
                or path.resolve() == sweep_resolved):
            continue
        if CLARIFY_MARKER in path.read_text(encoding="utf-8", errors="replace"):
            findings.append(("P1", str(path),
                f"unresolved '{CLARIFY_MARKER}: …]' marker — every clarification must resolve to "
                "a CEO-DECISION-LEDGER row (and the marker be removed) before freeze (P-PROP-003a)"))


def _check_acceptance_criteria(packet_dir: Path, findings: list) -> None:
    """P-PROP-003(b): every BUILDING requirement carries a structured acceptance_criterion
    {pass_condition, evidence_type, verification_ref}, present + non-placeholder STRING. Scoped
    to BUILDING — dispositioned-out rows already carry ref/reason semantics (cx check deck)."""
    manifest = packet_dir / MANIFEST_FILE
    if not manifest.is_file():
        return  # the manifest-missing P1 already fires in cmd_packet
    data, err = load_yaml(str(manifest))
    if err or not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        return  # malformed manifest content is cx check deck's contract, not this clause
    for i, row in enumerate(data["requirements"]):
        if not isinstance(row, dict) or str(row.get("disposition", "")).strip() != "BUILDING":
            continue
        rid = str(row.get("id", "?"))
        row_loc = f"{manifest}#requirements[{i}]"
        ac = row.get(ACCEPTANCE_FIELD)
        if not isinstance(ac, dict):
            findings.append(("P1", row_loc,
                f"BUILDING requirement '{rid}' has no '{ACCEPTANCE_FIELD}' block "
                f"{{{', '.join(ACCEPTANCE_KEYS)}}} — a requirement with no testable acceptance "
                "criterion is exactly what drifts undetected to acceptance (P-PROP-003b)"))
            continue
        missing = [k for k in ACCEPTANCE_KEYS if _ac_is_placeholder(ac.get(k))]
        if missing:
            findings.append(("P1", row_loc,
                f"BUILDING requirement '{rid}' acceptance_criterion missing/placeholder/non-string "
                f"{missing} — present + non-placeholder string is mechanical; the cold-reader "
                "audit judges testability (P-PROP-003b)"))


def _gwt_artifact_ref_resolves(packet_dir: Path, ref: str) -> bool:
    """PB-PROP-003 §R4: general (reason-agnostic) in-packet anchor resolution for a
    non_behavioral_exemption.artifact_ref — an existing file path under packet_dir, OR a
    requirement/module/screen id already declared in the packet's manifest/registry.
    Deliberately kept GENERAL (presence + resolves-in-packet) — a per-reason-type resolver is
    out of scope (simplicity-first; the whole-packet cold-reader review audits whether the
    reason itself fits, this only proves the ref is not a dangling/bare claim).

    NOT a raw full-text substring scan of the manifest: the artifact_ref is itself WRITTEN
    inside requirements-manifest.yaml, so a blind substring search would trivially "resolve"
    any string against the very field declaring it. Matching against structured id fields
    (requirement id / module_id / screen_id) closes that self-reference loophole.

    CX-PB003-003 FIX-FIRST (xfam finding 3, P1): the SAME self-reference hole existed one layer
    down — a file-path artifact_ref pointing at the manifest ITSELF (or the module registry) is
    a real, existing file, so the naive `target.is_file()` check "resolved" it too (e.g.
    artifact_ref: requirements-manifest.yaml "anchoring" against the very manifest that declares
    the exemption). An anchor must be a DIFFERENT in-packet artifact (a real screen/ui-lock/
    schema/config/content file, or a declared requirement/module/screen id) — never the manifest
    or registry that CARRIES the declaration. Rejected by resolved-absolute-path comparison, kept
    general (not a per-reason-type resolver)."""
    target = _resolve_inside(packet_dir, ref)
    if target is not None and target.is_file():
        manifest_path = (packet_dir / MANIFEST_FILE).resolve()
        registry_path = (packet_dir / REGISTRY_FILE).resolve()
        if target == manifest_path or target == registry_path:
            return False
        return True

    anchors: set = set()
    mdata, _ = load_yaml(str(packet_dir / MANIFEST_FILE))
    if isinstance(mdata, dict) and isinstance(mdata.get("requirements"), list):
        for row in mdata["requirements"]:
            if isinstance(row, dict) and row.get("id"):
                anchors.add(str(row["id"]).strip())
    reg_path = packet_dir / REGISTRY_FILE
    if reg_path.is_file():
        rdata, _ = load_yaml(str(reg_path))
        mr = rdata.get("module_registry") if isinstance(rdata, dict) else None
        rows = mr.get("modules") if isinstance(mr, dict) else None
        if isinstance(rows, list):
            for m in rows:
                if not isinstance(m, dict):
                    continue
                for key in ("module_id", "screen_id"):
                    if m.get(key):
                        anchors.add(str(m[key]).strip())
    return ref in anchors


def _check_gwt_examples(packet_dir: Path, findings: list) -> None:
    """PB-PROP-003 Unit 1 (packet stage): a BUILDING requirement's acceptance_criterion carries
    >=1 well-formed Given/When/Then example UNLESS the row declares a typed + anchored
    non_behavioral_exemption (absence of the exemption = behavioral, fail-closed default per
    Design v1 "the crux"). Structure-only shape-check — reuses _ac_is_placeholder; NEVER an
    English-quality judgment (same constitutional line as _check_acceptance_criteria, :598-601).

    Tier split (Design Resolution v2 §R3): only the "examples must be AUTHORED" requirement is
    ceremony (LITE-relaxable, PACKET-GWT-LITE-RELAXES-AUTHORING); exemption validity and the
    shape of any examples that ARE present are SPINE — enforced at every tier.

    Fails CLOSED on a malformed/unreadable manifest (PACKET-GWT-MANIFEST-MALFORMED-FAILS-CLOSED,
    §R8) — unlike _check_acceptance_criteria's silent return (that clause defers malformed YAML
    to `cx check deck`; this one must not let malformed YAML dodge the G/W/T gate)."""
    manifest = packet_dir / MANIFEST_FILE
    if not manifest.is_file():
        return  # the manifest-missing P1 already fires in cmd_packet
    data, err = load_yaml(str(manifest))
    if err or not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        findings.append(("P1", str(manifest),
            f"{MANIFEST_FILE} unreadable/malformed ({err or 'no requirements list'}) — the G/W/T "
            "check fails CLOSED rather than silently skipping the clause (PACKET-GWT-MANIFEST-"
            "MALFORMED-FAILS-CLOSED, PB-PROP-003)"))
        return

    tier = resolve_risk_tier(packet_dir)

    for i, row in enumerate(data["requirements"]):
        if not isinstance(row, dict) or str(row.get("disposition", "")).strip() != "BUILDING":
            continue
        rid = str(row.get("id", "?"))
        row_loc = f"{manifest}#requirements[{i}]"
        exemption = row.get("non_behavioral_exemption")

        if exemption is not None:
            reason = exemption.get("reason") if isinstance(exemption, dict) else None
            artifact_ref = exemption.get("artifact_ref") if isinstance(exemption, dict) else None
            reason_ok = isinstance(reason, str) and reason.strip() in NON_BEHAVIORAL_EXEMPTION_REASONS
            ref_ok = (not _ac_is_placeholder(artifact_ref)
                      and _gwt_artifact_ref_resolves(packet_dir, str(artifact_ref).strip()))
            if not isinstance(exemption, dict) or not reason_ok or not ref_ok:
                findings.append(("P1", row_loc,
                    f"BUILDING requirement '{rid}' non_behavioral_exemption is untyped or "
                    "unanchored — must be a mapping {reason, artifact_ref} with reason in "
                    f"{sorted(NON_BEHAVIORAL_EXEMPTION_REASONS)} and artifact_ref RESOLVING to a "
                    "real in-packet file / manifest / registry anchor, not a bare claim "
                    "(PACKET-EXEMPTION-UNTYPED-OR-UNANCHORED, PB-PROP-003)"))
            continue  # exempt row (valid or not) — never required to carry examples

        # Behavioral (no exemption declared). Authoring examples is CEREMONY (LITE-relaxable);
        # shape-checking anything present is SPINE regardless of tier.
        ac = row.get(ACCEPTANCE_FIELD)
        examples = ac.get("examples") if isinstance(ac, dict) else None
        if not examples:
            if tier != "LITE":
                findings.append(("P1", row_loc,
                    f"BUILDING requirement '{rid}' is behavioral (no non_behavioral_exemption) but "
                    f"'{ACCEPTANCE_FIELD}.examples' is missing/empty — a behavioral requirement "
                    "needs >=1 Given/When/Then example (PACKET-GWT-EXAMPLE-REQUIRED, PB-PROP-003)"))
            continue

        if not isinstance(examples, list):
            findings.append(("P1", row_loc,
                f"BUILDING requirement '{rid}' {ACCEPTANCE_FIELD}.examples is not a list "
                "(PACKET-GWT-EXAMPLE-MALFORMED, PB-PROP-003)"))
            continue

        for j, ex in enumerate(examples):
            ex_loc = f"{row_loc}.{ACCEPTANCE_FIELD}.examples[{j}]"
            if not isinstance(ex, dict):
                findings.append(("P1", ex_loc,
                    f"BUILDING requirement '{rid}' example is not a mapping {{given, when, then}} "
                    "(PACKET-GWT-EXAMPLE-MALFORMED, PB-PROP-003)"))
                continue
            bad_keys = [k for k in ("given", "when", "then") if _ac_is_placeholder(ex.get(k))]
            if bad_keys:
                findings.append(("P1", ex_loc,
                    f"BUILDING requirement '{rid}' example missing/placeholder/non-string "
                    f"{bad_keys} — structure only, never an English-quality judgment "
                    "(PACKET-GWT-EXAMPLE-MALFORMED, PB-PROP-003)"))


# P-PROP-005 (v1.18): packet-floor registry coverage. For a screen/module-first project (a planning
# MODULE-REGISTRY.yaml drafted in the packet), the registry must cover every screen/shared module +
# every BUILDING requirement id BEFORE the packet freezes — so the freeze→G1 sequence binds a registry
# that already accounts for the whole plan. Cards still bind to the frozen hash (G1 order unchanged).
# Fires ONLY when the planning registry is present; legacy packets are untouched (clause silent).
REGISTRY_FILE = "MODULE-REGISTRY.yaml"
SCREENS_MANIFEST_FILE = "screens-manifest.yaml"


def _check_module_registry_coverage(packet_dir: Path, findings: list) -> None:
    reg_path = packet_dir / REGISTRY_FILE
    if not reg_path.is_file():
        return  # not a screen/module-first packet — clauses silent (legacy untouched)
    rdata, rerr = load_yaml(str(reg_path))
    mr = rdata.get("module_registry") if isinstance(rdata, dict) else None
    rows = mr.get("modules") if isinstance(mr, dict) else (
        rdata.get("modules") if isinstance(rdata, dict) else None)
    if rerr or not isinstance(rows, list) or not rows:
        findings.append(("P1", str(reg_path),
            f"{REGISTRY_FILE} present but has no module_registry.modules list — a screen/module-first "
            "packet must carry a real registry covering the plan (PACKET-MODULE-REGISTRY-COVERS-SCREENS, "
            "P-PROP-005)"))
        return

    # ── CHECK #1 (PB-PROP-002): frozen_packet_hash must be present in the planning registry ──────────
    fph = str(mr.get("frozen_packet_hash", "") or "").strip() if isinstance(mr, dict) else ""
    if not fph:
        findings.append(("P0", str(reg_path),
            "MODULE-REGISTRY.yaml module_registry has no frozen_packet_hash — "
            "an UNBOUND registry is not frozen (PACKET-MODULE-REGISTRY-FROZEN-HASH-PRESENT, PB-PROP-002)"))

    # ── CHECK #3 (PB-PROP-002): dependency_modules must form a DAG (no cycles, no unknown refs) ──────
    from cx_module_acceptance import validate_registry_build_shape
    _, dag_findings = validate_registry_build_shape(rows, str(reg_path))
    findings.extend(dag_findings)

    registry_modules = {str(m.get("module_id")).strip() for m in rows
                        if isinstance(m, dict) and m.get("module_id")}
    registry_screens = {str(m.get("screen_id")).strip() for m in rows
                       if isinstance(m, dict) and m.get("screen_id")
                       and str(m.get("kind", "")).strip() == "screen"}

    # ── ONE-LIVE-LOCK-PER-SCREEN (P0, PBF-PROP-020 Rule 6a) ─────────────────────────────────────
    # Each screen_id must have exactly ONE live (non-tombstoned) lock_ref. A superseded lock is
    # recorded with superseded_by + tombstoned (reuses the cx_accepted_surface superseded_by_lock_ref
    # pattern) — era-layered locks (e.g. light+dark+nav-shell all claiming "live") is the P0-3 hole
    # this closes. A live lock_ref reused as another screen's live lock is the same P0 class.
    by_screen: dict = {}
    for m in rows:
        if not isinstance(m, dict):
            continue
        sid = str(m.get("screen_id", "") or "").strip()
        if not sid:
            continue
        lr = str(m.get("lock_ref", "") or "").strip()
        if not lr:
            # Forward-scope (built-code xfam P0-2 resolution): a screen row with NO lock_ref is
            # skipped, not failed — Rule 6a's job is "no era-layered MULTIPLE live locks", never
            # "every screen must own a lock" (that would retro-break pre-020 registries). The
            # "a look-CHANGE needs a current lock" requirement is Rule 1's fail-closed card-time gate.
            continue
        tombstoned = bool(str(m.get("tombstoned", "") or "").strip())
        by_screen.setdefault(sid, []).append((lr, tombstoned))
    lock_owner: dict = {}
    for sid, entries in by_screen.items():
        live = [lr for lr, tomb in entries if not tomb]
        if len(set(live)) > 1:
            findings.append(("P0", str(reg_path),
                f"screen_id '{sid}' has MULTIPLE live lock_refs {sorted(set(live))} in "
                f"{REGISTRY_FILE} — era-layered locks (e.g. light+dark+nav-shell all claiming "
                "live) are P0; a superseded lock must carry superseded_by + tombstoned "
                "(ONE-LIVE-LOCK-PER-SCREEN, PBF-PROP-020 Rule 6a)"))
        for lr in set(live):
            if lr in lock_owner and lock_owner[lr] != sid:
                findings.append(("P0", str(reg_path),
                    f"lock_ref '{lr}' is the live lock for BOTH screen_id '{lock_owner[lr]}' and "
                    f"'{sid}' in {REGISTRY_FILE} — a live lock file must belong to exactly one "
                    "screen (ONE-LIVE-LOCK-PER-SCREEN, PBF-PROP-020 Rule 6a)"))
            else:
                lock_owner[lr] = sid

    # ── PACKET-MODULE-REGISTRY-COVERS-SCREENS (P1) ──────────────────────────────────────────────
    screens_path = packet_dir / SCREENS_MANIFEST_FILE
    sdata, serr = load_yaml(str(screens_path))
    screens = sdata.get("screens") if isinstance(sdata, dict) else None
    if isinstance(screens, list):
        for s in screens:
            if not isinstance(s, dict) or s.get("user_facing") is False:
                continue
            sid = str(s.get("id", "") or "").strip()
            if sid and sid not in registry_screens and sid not in registry_modules:
                findings.append(("P1", str(reg_path),
                    f"screen '{sid}' (in {SCREENS_MANIFEST_FILE}) is not covered by a registry "
                    "screen module — the planning MODULE-REGISTRY must cover every screen before the "
                    "packet freezes; an uncovered screen drifts unbuilt "
                    "(PACKET-MODULE-REGISTRY-COVERS-SCREENS, P-PROP-005)"))

    # ── PACKET-MODULE-REGISTRY-COVERS-REQUIREMENTS (P1) ─────────────────────────────────────────
    mdata, merr = load_yaml(str(packet_dir / MANIFEST_FILE))
    reqs = mdata.get("requirements") if isinstance(mdata, dict) else None
    if isinstance(reqs, list):
        covered = set()
        for m in rows:
            if isinstance(m, dict):
                for rid in (m.get("requirement_ids") or []):
                    if rid:
                        covered.add(str(rid).strip())
        for row in reqs:
            if not isinstance(row, dict) or str(row.get("disposition", "")).strip() != "BUILDING":
                continue
            rid = str(row.get("id", "") or "").strip()
            if rid and rid not in covered:
                findings.append(("P1", str(reg_path),
                    f"BUILDING requirement '{rid}' is in no registry module's requirement_ids — the "
                    "planning MODULE-REGISTRY must cover every requirement before freeze; an uncovered "
                    "requirement has no module to build it "
                    "(PACKET-MODULE-REGISTRY-COVERS-REQUIREMENTS, P-PROP-005)"))


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
    _check_clarification_sweep(packet_dir, findings)
    _check_acceptance_criteria(packet_dir, findings)
    _check_gwt_examples(packet_dir, findings)
    _check_style_direction(packet_dir, findings)
    _check_risk_tier(packet_dir, findings)
    _check_pb_prop_003_wiring_marker(packet_dir, findings)
    _check_forge_parity_marker_required(packet_dir, findings, getattr(args, "legacy_migration", False),
                                        getattr(args, "migration_ref", ""))
    _check_visual_provenance(packet_dir, findings)
    _check_module_registry_coverage(packet_dir, findings)
    _check_sop_coverage_map(packet_dir, findings)

    if findings:
        return findings_report(findings)

    print("PASS")
    print(f"  coverage: {done} categories DONE, {na} written-N/A (all 20 accounted for)")
    print(f"  floor: {COVERAGE_FILE} · {MANIFEST_FILE} · {LEDGER_FILE} (asks+decisions) · {AUDIT_FILE}")
    print(f"  writing-stage: {SWEEP_FILE} (ledger-bound clarify-before-freeze) · BUILDING acceptance_criterion present · G/W/T examples or typed exemption")
    return 0
