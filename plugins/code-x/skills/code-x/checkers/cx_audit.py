# cmd_audit: the Audit stage checker (A-PROP-001 + PBAF-PROP-001).
#
#   cx check audit <audit-dir> --state <state> [--final] [--repo-root <root>] [--decision-ledger <path>]
#
# Verifies an audit report directory against the AUDIT-STAGE-* biting clauses
# (checkers/check-contracts.yaml). Posture = verify: this checker never edits
# code, it only judges an already-produced audit report.
#
# Input shape (audit-dir):
#   AUDIT-SUMMARY.md        — presence = the audit receipt exists (Lever A)
#   applicability.yaml      — {facts: {A1..A9, A5: E0|E1|E2|E3}, layers: [{id, verdict, subitems:[...]}]}
#   angle-A.yaml / angle-B.yaml / angle-C.yaml — presence-checked (requirements/asks/reality angles)
#   angle-D.yaml             — {items: [{layer_id, subitem, applicable, driving_fact, disposition}]}
#   review-ladder.yaml       — {builder_family, receipts: [{stage, family, order, artifact,
#                                sha256, verdict, reviewed_ref}]}
#
# Mirrors cx_kaizen.py / cx_graduation.py structure: findings list of
# (severity, location, message) tuples, printed via findings_report().
import hashlib
import re
from pathlib import Path

from cx_common import findings_report, load_yaml, safe_repo_ref

_THIS_DIR = Path(__file__).resolve().parent
_APPLICABILITY_TABLE = _THIS_DIR / "sop_applicability.yaml"

_SUMMARY_FILE = "AUDIT-SUMMARY.md"
_APPLICABILITY_FILE = "applicability.yaml"
_ANGLE_FILES = {"A": "angle-A.yaml", "B": "angle-B.yaml", "C": "angle-C.yaml", "D": "angle-D.yaml"}
_REVIEW_LADDER_FILE = "review-ladder.yaml"
_VALID_DISPOSITIONS = {"pass", "fix", "ceo_waive"}
_LADDER_ORDER = ["coderabbit", "self_review", "cross_family"]
_TIERS = {"E0": 0, "E1": 1, "E2": 2, "E3": 3}

# X1 (v1.22 xfam fix): builder_family is DERIVED from the loaded state's active_build_engine,
# never trusted as a self-declared review-ladder field. Mirrors cx_state.ENGINE_TO_FAMILY but in
# the ladder's own family vocabulary (the review-ladder fixtures already use claude/gpt/coderabbit,
# not ANTHROPIC/CODEX) — one small local table, not a second copy of cx_state's engine enum.
_ENGINE_TO_LADDER_FAMILY = {"CLAUDE_CODE": "claude", "CODEX_APP": "gpt"}

_LEDGER_FILE = "CEO-DECISION-LEDGER.md"
_LEDGER_ROW_ID_RE = re.compile(r"\bCEO-D-[A-Z0-9][A-Z0-9-]*\b")

# X2: the 9 build-facts, strictly typed. A1-A4/A6-A9 are real Python bool; A5 is one of the
# 4 literal exposure-tier strings. Python's `bool("false") is True` (any non-empty string is
# truthy) is exactly the silent-pass hole this closes — isinstance(x, bool) rejects the string.
_BOOL_FACT_KEYS = ["A1", "A2", "A3", "A4", "A6", "A7", "A8", "A9"]
_ALL_FACT_KEYS = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"]
_VALID_A5 = {"E0", "E1", "E2", "E3"}


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _coerce_layer_id(raw):
    """Coerce a layer id to int for cross-table lookup. Returns None if unparseable
    (F4: string/int mismatch between applicability.yaml's report ids and the SOP layer
    table's ids used to silently SKIP the Rule 2 cross-check — fail-open on type
    mismatch. Callers must treat None as a fail-closed finding, never a silent skip)."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _tier_at_least(facts: dict, min_tier: str) -> bool:
    a5 = str(facts.get("A5", "E0"))
    return _TIERS.get(a5, 0) >= _TIERS.get(min_tier, 0)


def _eval_condition(cond: str, facts: dict) -> bool:
    """Tiny evaluator for the applies_when / when_false expressions in
    sop_applicability.yaml. Supports: 'always', bare fact names (A1..A9 as
    truthy), 'A5>=E2' / 'A5==E3' tier comparisons, and 'X and Y' conjunctions."""
    cond = cond.strip()
    if cond == "always":
        return True
    if " and " in cond:
        return all(_eval_condition(part, facts) for part in cond.split(" and "))
    if " or " in cond:
        return any(_eval_condition(part, facts) for part in cond.split(" or "))
    if ">=" in cond:
        fact, tier = cond.split(">=")
        return _tier_at_least(facts, tier.strip())
    if "==" in cond:
        fact, tier = cond.split("==")
        return str(facts.get(fact.strip(), "E0")) == tier.strip()
    if cond == "not_solo_manual_deploy":
        return bool(facts.get("not_solo_manual_deploy", False))
    return bool(facts.get(cond, False))


def _layer_should_apply(layer: dict, facts: dict) -> bool:
    """True if ANY applies_when condition holds — i.e. the layer is not a
    whole-layer N/A under the recorded facts."""
    conds = layer.get("applies_when") or []
    return any(_eval_condition(c, facts) for c in conds)


def _validate_facts_strict(facts: dict) -> list[tuple[str, str, str]]:
    """X2 (v1.22 xfam fix): fail-closed schema validation for the 9 build-facts, run BEFORE
    any evaluation logic touches them. A missing fact, a non-bool value on a boolean fact
    (the string "false" is truthy in Python — silently passing checks it should fail), or an
    A5 value outside {E0,E1,E2,E3} is a P1 finding, never a silent default."""
    findings: list[tuple[str, str, str]] = []
    loc = "applicability.yaml#facts"
    for key in _ALL_FACT_KEYS:
        if key not in facts:
            findings.append(("P1", loc,
                f"AUDIT-STAGE-FACTS-MISSING: build-fact '{key}' absent from applicability.yaml facts — "
                "a missing fact must never silently default to false/E0 (PBAF-PROP-001 Rule 1, F X2)"))
    for key in _BOOL_FACT_KEYS:
        if key in facts and not isinstance(facts[key], bool):
            findings.append(("P1", loc,
                f"AUDIT-STAGE-FACTS-TYPE: build-fact '{key}'={facts[key]!r} is not a real boolean "
                "(a string like \"false\" is truthy in Python and would silently pass) — facts A1-A4/"
                "A6-A9 must be YAML true/false, never a string (F X2)"))
    if "A5" in facts and str(facts["A5"]) not in _VALID_A5:
        findings.append(("P1", loc,
            f"AUDIT-STAGE-FACTS-A5-INVALID: build-fact A5='{facts['A5']}' is not one of "
            f"{sorted(_VALID_A5)} — an invalid tier must fail closed, never fall back to E0 (F X2)"))
    return findings


def _layer_expected_items(layer: dict, facts: dict) -> dict[str, bool]:
    """X3: the FULL expected sub-item registry for one SOP layer, computed from the
    canonical table (na_subitems + hard_rule), transcribed faithfully from
    SOP/APPLICABILITY-MODEL.md — never invented. A layer with no named sub-item in the
    locked table (e.g. Frontend, Load Balancing, Error Tracking/Logs) is represented by
    ONE synthetic '__layer__' item whose applicability is the layer's own applies_when —
    the doc names no finer sub-item for these layers, so the layer IS the sub-item."""
    items: dict[str, bool] = {}
    for ns in layer.get("na_subitems") or []:
        name = ns.get("subitem")
        cond = ns.get("when_false")
        if name and cond:
            items[name] = _eval_condition(cond, facts)
    hard_rule = layer.get("hard_rule")
    if isinstance(hard_rule, dict) and hard_rule.get("subitem"):
        name = hard_rule["subitem"]
        cond = hard_rule.get("mandatory_when", "always")
        applicable = _eval_condition(cond, facts)
        items[name] = items.get(name, False) or applicable
    if not items:
        items["__layer__"] = _layer_should_apply(layer, facts)
    return items


def _expected_subitem_registry(table_layers: list, facts: dict) -> dict[tuple[int, str], bool]:
    """X3: {(layer_id, subitem_name): applicable_bool} across ALL 13 layers, derived from
    the validated facts. This is the EXPECTED set angle-D must disposition exactly once per
    applicable entry — the audit-dodging blind spot (an omitted sub-item just never gets
    checked) closes because the registry is computed from the table, not read off whatever
    angle-D.yaml happens to already list."""
    expected: dict[tuple[int, str], bool] = {}
    for layer in table_layers:
        lid = _coerce_layer_id(layer.get("id"))
        if lid is None:
            continue
        for name, applicable in _layer_expected_items(layer, facts).items():
            expected[(lid, name)] = applicable
    return expected


def _driving_fact_named_false(driving_fact: str, facts: dict) -> bool:
    """True iff `driving_fact` names at least one A1-A9 fact token AND (for the boolean
    facts) that fact is actually recorded false — i.e. the N/A is backed by a real,
    checkable fact, not an opinion string that happens to mention a fact's name. A5 tier
    comparisons (e.g. 'A5<E3') are accepted on token presence since the comparison direction
    is already encoded in the driving_fact text itself, not re-parsed here."""
    tokens = re.findall(r"\bA[1-9]\b", str(driving_fact or ""))
    if not tokens:
        return False
    for tok in tokens:
        if tok == "A5":
            return True
        if facts.get(tok) is False:
            return True
    return False


def _validate_ladder_receipts(receipts: list, repo_root: Path) -> list[tuple[str, str, str]]:
    """X1: receipts must be EVIDENCE, not declarations. Every receipt entry must carry an
    artifact path (repo-relative, non-symlink, must exist on disk), a sha256 of that
    artifact VERIFIED against the actual file, a reviewer family, a verdict, and a
    reviewed_ref (the commit/card id under review). A stub receipt missing any of these is
    a P1 finding, fail-closed — this is the shared check whichever stage (coderabbit /
    self_review / cross_family) the receipt belongs to."""
    findings: list[tuple[str, str, str]] = []
    for i, r in enumerate(receipts):
        loc = f"{_REVIEW_LADDER_FILE}#receipts[{i}]"
        if not isinstance(r, dict):
            findings.append(("P1", loc, "AUDIT-STAGE-RECEIPT-EVIDENCE: receipt entry is not a mapping"))
            continue
        stage = r.get("stage", "?")
        family = str(r.get("family", "") or "").strip()
        verdict = str(r.get("verdict", "") or "").strip()
        reviewed_ref = str(r.get("reviewed_ref", "") or "").strip()
        artifact = str(r.get("artifact", "") or "").strip()
        sha256_claim = str(r.get("sha256", "") or "").strip()

        missing = []
        if not family:
            missing.append("family (reviewer family)")
        if not verdict:
            missing.append("verdict")
        if not reviewed_ref:
            missing.append("reviewed_ref (commit/card id under review)")
        if not artifact:
            missing.append("artifact (repo-relative path)")
        if not sha256_claim:
            missing.append("sha256")
        if missing:
            findings.append(("P1", loc,
                f"AUDIT-STAGE-RECEIPT-EVIDENCE: {stage} receipt is a STUB, missing {', '.join(missing)} "
                "— a review receipt with no bound artifact is a declaration, not evidence (X1)"))
            continue

        art_path, reason = safe_repo_ref(artifact, repo_root)
        if art_path is None:
            findings.append(("P1", loc,
                f"AUDIT-STAGE-RECEIPT-EVIDENCE: {stage} receipt artifact '{artifact}' {reason} (X1)"))
            continue
        if not art_path.is_file():
            findings.append(("P1", loc,
                f"AUDIT-STAGE-RECEIPT-EVIDENCE: {stage} receipt artifact '{artifact}' does not exist "
                "on disk — an unbound claim is not evidence (X1)"))
            continue
        actual = _sha256(art_path)
        if actual is None or actual != sha256_claim:
            findings.append(("P1", loc,
                f"AUDIT-STAGE-RECEIPT-EVIDENCE: {stage} receipt sha256 does not match the artifact at "
                f"'{artifact}' — the recorded review is not bound to THIS artifact (fabricated/stale "
                "hash) (X1)"))
    return findings


def collect_audit_findings(audit_dir: Path, final: bool = False, state_path=None,
                            repo_root: Path | None = None,
                            decision_ledger_path: Path | None = None) -> list[tuple[str, str, str]]:
    """Judge an audit report directory and return its findings list (no printing).
    Shared by `cmd_audit` (the `cx check audit` CLI) and `cx_final_ready.py`'s
    AUDIT-STAGE-FINAL-READY-CHAIN check — both must apply the exact same judgment,
    never two divergent copies of the audit logic (F1, v1.22 self-review).

    state_path/repo_root/decision_ledger_path (X1, v1.22 xfam fix): the state file is now
    LOADED (never just accepted as a flag) so builder_family is DERIVED from
    active_build_engine, and receipt artifacts/CEO-decision-refs resolve against a real
    repo root + ledger rather than being trusted as bare strings."""
    findings: list[tuple[str, str, str]] = []

    if repo_root is None:
        repo_root = Path(state_path).resolve().parent if state_path else Path(audit_dir).resolve().parent
    repo_root = Path(repo_root)
    if decision_ledger_path is None:
        decision_ledger_path = repo_root / _LEDGER_FILE
    decision_ledger_path = Path(decision_ledger_path)

    # X1: LOAD the state — derive builder_family from it, never trust a self-declared field.
    derived_builder_family = None
    if state_path is not None:
        state_data, state_err = load_yaml(str(state_path))
        if state_err or not isinstance(state_data, dict):
            findings.append(("P1", str(state_path),
                f"AUDIT-STAGE-STATE-REQUIRED: --state '{state_path}' unreadable: "
                f"{state_err or 'not a YAML mapping'} — builder_family cannot be derived from an "
                "unreadable state (X1)"))
        else:
            engine = str(state_data.get("active_build_engine", "") or "")
            derived_builder_family = _ENGINE_TO_LADDER_FAMILY.get(engine)
            if derived_builder_family is None:
                findings.append(("P1", str(state_path),
                    f"AUDIT-STAGE-STATE-REQUIRED: state active_build_engine='{engine}' not in "
                    f"{sorted(_ENGINE_TO_LADDER_FAMILY)} — builder_family cannot be derived (X1)"))
    else:
        findings.append(("P1", str(audit_dir),
            "AUDIT-STAGE-STATE-REQUIRED: no --state supplied — builder_family cannot be derived "
            "from bound state (X1)"))

    if not audit_dir.is_dir() or not (audit_dir / _SUMMARY_FILE).is_file():
        findings.append(("P1", str(audit_dir),
            f"AUDIT-STAGE-ENTRY-REQUIRED: {_SUMMARY_FILE} missing — a build that reaches "
            "final-ready with no audit receipt skipped the Audit stage entirely (A-PROP-001 Lever A)"))
        return findings

    applicability_path = audit_dir / _APPLICABILITY_FILE
    applicability, err = load_yaml(str(applicability_path))
    if err or not isinstance(applicability, dict):
        findings.append(("P1", str(applicability_path),
            f"{_APPLICABILITY_FILE} unreadable: {err or 'not a YAML mapping'}"))
        return findings

    facts = applicability.get("facts") or {}
    layers = applicability.get("layers") or []

    # X2: strict schema validation BEFORE any evaluation logic touches the facts.
    fact_findings = _validate_facts_strict(facts)
    findings.extend(fact_findings)
    facts_ok = not fact_findings

    table, terr = load_yaml(str(_APPLICABILITY_TABLE))
    table_layers = (table or {}).get("layers", []) if not terr else []
    table_by_id = {}
    for l in table_layers:
        cid = _coerce_layer_id(l.get("id"))
        if cid is not None:
            table_by_id[cid] = l

    for layer in layers:
        lid = layer.get("id")
        verdict = layer.get("verdict")
        loc = f"{applicability_path}#layers[{lid}]"

        cid = _coerce_layer_id(lid)
        if cid is None:
            findings.append(("P1", loc,
                f"AUDIT-STAGE-LAYER-ID-UNPARSEABLE: layer id '{lid}' is not an integer — cannot "
                "cross-check it against the SOP layer table (PBAF-PROP-001 Rule 2 cross-check "
                "fail-closed rather than silently skipped on a type mismatch)"))

        if verdict == "N_A":
            driving_fact = layer.get("driving_fact")
            if not driving_fact:
                findings.append(("P1", loc,
                    "AUDIT-STAGE-APPLICABILITY-DERIVED: layer marked N/A with no driving build-fact "
                    "(A1-A9) recorded — asserting N/A by opinion, not derivation (PBAF-PROP-001 Rule 1)"))
            if facts_ok:
                table_layer = table_by_id.get(cid) if cid is not None else None
                if table_layer and _layer_should_apply(table_layer, facts):
                    findings.append(("P1", loc,
                        "AUDIT-STAGE-WHOLE-LAYER-NA-WITH-LIVE-SUBITEM: layer marked N/A but at least one "
                        "sub-item is applicable under the recorded facts (PBAF-PROP-001 Rule 2 — per "
                        "sub-item, not per layer)"))

    for angle in ("A", "B", "C"):
        fpath = audit_dir / _ANGLE_FILES[angle]
        if not fpath.is_file():
            findings.append(("P1", str(fpath),
                f"AUDIT-STAGE-ENTRY-REQUIRED: {_ANGLE_FILES[angle]} missing — angle {angle} not run"))

    angle_d_path = audit_dir / _ANGLE_FILES["D"]
    angle_d, derr = load_yaml(str(angle_d_path))
    items = (angle_d or {}).get("items", []) if not derr and isinstance(angle_d, dict) else []
    if derr or not isinstance(angle_d, dict):
        findings.append(("P1", str(angle_d_path),
            f"AUDIT-STAGE-ENTRY-REQUIRED: {_ANGLE_FILES['D']} unreadable: {derr or 'not a YAML mapping'}"))

    unresolved_final = 0
    for i, item in enumerate(items):
        iloc = f"{angle_d_path}#items[{i}]"
        applicable = item.get("applicable", True)
        disposition = item.get("disposition")
        if applicable:
            if disposition not in _VALID_DISPOSITIONS:
                findings.append(("P1", iloc,
                    "AUDIT-STAGE-SHIPGATE-DISPOSITION: applicable SOP ship-gate sub-item has no "
                    "disposition (pass / fix / CEO-waive) — a live standard unproven (A-PROP-001 Lever C)"))
            elif final and disposition == "fix":
                unresolved_final += 1

    if final and unresolved_final:
        findings.append(("P1", str(angle_d_path),
            f"AUDIT-STAGE-FAILCLOSED-FINAL: {unresolved_final} applicable ship-gate item(s) unresolved "
            "('fix', no pass/ceo_waive) at the final audit — forward-shipping a known standard failure "
            "(A-PROP-001 Lever E)"))

    # X3: expected-set enforcement — Rule 1 + Rule 2 made real. Compute the FULL expected
    # applicable/N-A sub-item set from the validated facts and require angle-D to disposition
    # every expected-applicable sub-item exactly once (unknown / duplicate / omitted / an N/A
    # not backed by a specifically-named false fact are all P1, fail-closed).
    if facts_ok and not derr and isinstance(angle_d, dict):
        expected = _expected_subitem_registry(table_layers, facts)
        seen: set[tuple[int, str]] = set()
        for i, item in enumerate(items):
            iloc = f"{angle_d_path}#items[{i}]"
            lid = _coerce_layer_id(item.get("layer_id"))
            subitem = item.get("subitem")
            key = (lid, subitem) if lid is not None else None
            applicable = item.get("applicable", True)
            if key is None or key not in expected:
                findings.append(("P1", iloc,
                    f"AUDIT-STAGE-EXPECTED-SET-UNKNOWN-SUBITEM: angle-D item (layer_id={item.get('layer_id')}, "
                    f"subitem={subitem}) does not match any sub-item in the SOP layer registry — cannot be "
                    "a real disposition of a real ship-gate item (PBAF-PROP-001 Rule 2, X3)"))
                continue
            if key in seen:
                findings.append(("P1", iloc,
                    f"AUDIT-STAGE-EXPECTED-SET-DUPLICATE: angle-D item (layer_id={lid}, subitem={subitem}) "
                    "dispositioned more than once (X3)"))
            seen.add(key)
            expected_applicable = expected[key]
            if expected_applicable and not applicable:
                findings.append(("P1", iloc,
                    f"AUDIT-STAGE-EXPECTED-SET-NA-MISMATCH: angle-D marks (layer_id={lid}, subitem="
                    f"{subitem}) N/A but the recorded facts say it is applicable — an N/A that "
                    "contradicts the derived facts (PBAF-PROP-001 Rule 1, X3)"))
            if not applicable:
                driving_fact = item.get("driving_fact")
                if not driving_fact:
                    findings.append(("P1", iloc,
                        f"AUDIT-STAGE-EXPECTED-SET-NA-NO-FACT: angle-D item (layer_id={lid}, subitem="
                        f"{subitem}) marked N/A with no driving_fact recorded (PBAF-PROP-001 Rule 1, X3)"))
                elif not _driving_fact_named_false(driving_fact, facts):
                    findings.append(("P1", iloc,
                        f"AUDIT-STAGE-EXPECTED-SET-NA-UNBACKED: angle-D item (layer_id={lid}, subitem="
                        f"{subitem}) marked N/A with driving_fact '{driving_fact}' that does not name an "
                        "actually-false build-fact — an N/A disposition must be backed by a specifically "
                        "named false fact, not an opinion string (PBAF-PROP-001 Rule 1, X3)"))

        for key, expected_applicable in expected.items():
            if expected_applicable and key not in seen:
                lid, subitem = key
                findings.append(("P1", str(angle_d_path),
                    f"AUDIT-STAGE-EXPECTED-SET-OMITTED: expected-applicable sub-item (layer_id={lid}, "
                    f"subitem={subitem}) is never dispositioned in angle-D — an omitted item is the "
                    "audit-dodging blind spot, not compliance (PBAF-PROP-001 Rule 2, X3)"))

    ladder_path = audit_dir / _REVIEW_LADDER_FILE
    ladder, lerr = load_yaml(str(ladder_path))
    if lerr or not isinstance(ladder, dict):
        findings.append(("P1", str(ladder_path),
            f"AUDIT-STAGE-REVIEW-LADDER: {_REVIEW_LADDER_FILE} unreadable: {lerr or 'not a YAML mapping'}"))
    else:
        builder_family = ladder.get("builder_family")
        receipts = ladder.get("receipts") or []

        # X1: builder_family must MATCH the derived state family — a forged/self-declared
        # value that contradicts the loaded state is a P1 finding, not a trusted declaration.
        if derived_builder_family is not None and builder_family and \
                str(builder_family).strip().lower() != derived_builder_family:
            findings.append(("P1", str(ladder_path),
                f"AUDIT-STAGE-BUILDER-FAMILY-FORGED: review-ladder builder_family='{builder_family}' "
                f"contradicts the loaded state's derived family '{derived_builder_family}' (from "
                "active_build_engine) — builder_family is derived evidence, not a self-declaration (X1)"))

        findings.extend(_validate_ladder_receipts(receipts, repo_root))

        receipts_sorted = sorted(receipts, key=lambda r: r.get("order", 0))
        stages_in_order = [r.get("stage") for r in receipts_sorted]
        cross_receipts = [r for r in receipts_sorted if r.get("stage") == "cross_family"]

        for cr in cross_receipts:
            idx = stages_in_order.index("cross_family") if "cross_family" in stages_in_order else -1
            preceding = stages_in_order[:idx] if idx >= 0 else []
            if "coderabbit" not in preceding or "self_review" not in preceding or \
               preceding.index("coderabbit") > preceding.index("self_review"):
                findings.append(("P1", str(ladder_path),
                    "AUDIT-STAGE-REVIEW-LADDER: cross-family audit receipt not preceded, in order, by "
                    "a CodeRabbit review receipt and a same-family self-review receipt — skips the "
                    "ratified review ladder (A-PROP-001 Lever D)"))
                break

        for cr in cross_receipts:
            if builder_family and cr.get("family") == builder_family:
                findings.append(("P1", str(ladder_path),
                    "AUDIT-STAGE-XFAM-RECEIPT: audit receipt authored by the same model family as the "
                    "builder is not a cross-family audit (A-PROP-001 Lever D)"))

        # F7 (v1.22 self-review, CEO ruling 2026-07-02): the ladder clauses above only fire ON a
        # cross_family receipt — a FINAL audit with ZERO cross_family receipts sailed through
        # (fail-open; order-only enforcement). At --final, no cross-family receipt = P1 unless a
        # TYPED escape is present, mirroring the stage_1 discipline (GATES.md BF-PROP-005 / G8):
        #   (a) xfam_capability_evidence — repo-relative ref to the manual scrubbed cross-family
        #       paste evidence, MUST exist on disk (X1: an escape hatch must resolve, not just
        #       reference).
        #   (b) ceo_decision_ref — the standard typed CEO risk-waiver reference, MUST resolve
        #       against the CEO-DECISION-LEDGER (X1).
        if final and not cross_receipts:
            ev = str(ladder.get("xfam_capability_evidence", "") or "").strip()
            waiver = str(ladder.get("ceo_decision_ref", "") or "").strip()
            ev_ok = bool(ev)
            if ev and (Path(ev).is_absolute() or ".." in Path(ev).parts):
                ev_ok = False
                findings.append(("P1", str(ladder_path),
                    f"AUDIT-STAGE-FINAL-XFAM-REQUIRED: xfam_capability_evidence '{ev}' must be a "
                    "repo-relative path (no absolute path / .. escape) — the stage_1 manual-paste "
                    "evidence is an in-tree artifact (BF-PROP-005 / GPT review F6)"))
            elif ev:
                ev_path, ev_reason = safe_repo_ref(ev, repo_root)
                if ev_path is None:
                    ev_ok = False
                    findings.append(("P1", str(ladder_path),
                        f"AUDIT-STAGE-FINAL-XFAM-REQUIRED: xfam_capability_evidence '{ev}' {ev_reason} (X1)"))
                elif not ev_path.is_file():
                    ev_ok = False
                    findings.append(("P1", str(ladder_path),
                        f"AUDIT-STAGE-FINAL-XFAM-REQUIRED: xfam_capability_evidence '{ev}' does not exist "
                        "on disk — the escape hatch must RESOLVE to a real hashed artifact, not just "
                        "reference a path (X1)"))
            waiver_ok = bool(waiver)
            if waiver and waiver_ok:
                if not decision_ledger_path.is_file():
                    waiver_ok = False
                    findings.append(("P1", str(ladder_path),
                        f"AUDIT-STAGE-FINAL-XFAM-REQUIRED: ceo_decision_ref '{waiver}' cannot resolve — "
                        f"{decision_ledger_path} is missing from the packet (X1)"))
                else:
                    ledger_ids = set(_LEDGER_ROW_ID_RE.findall(
                        decision_ledger_path.read_text(encoding="utf-8", errors="replace")))
                    if waiver not in ledger_ids:
                        waiver_ok = False
                        findings.append(("P1", str(ladder_path),
                            f"AUDIT-STAGE-FINAL-XFAM-REQUIRED: ceo_decision_ref '{waiver}' does not resolve "
                            f"to a {_LEDGER_FILE} row id (CEO-D-NNN) — a decision that lives in chat is not "
                            "a decision (X1)"))
            if not ev_ok and not waiver_ok:
                findings.append(("P1", str(ladder_path),
                    "AUDIT-STAGE-FINAL-XFAM-REQUIRED: final audit has ZERO cross_family receipts and "
                    "no RESOLVED typed escape — before ship a TRUE opposite-family review is required, or "
                    "the stage_1 path: xfam_capability_evidence (manual scrubbed cross-family paste, must "
                    "exist on disk) or an explicit ceo_decision_ref risk waiver (must resolve in the "
                    "ledger) (A-PROP-001 Lever D / BF-PROP-005 stage_1; CEO ruling 2026-07-02)"))

    # F2 (v1.22 self-review): drive ALL locked hard_rules GENERICALLY from
    # sop_applicability.yaml's hard_rules table — not just HTTPS_E2 hardcoded here.
    # An OMITTED ship-gate sub-item (never mentioned in the report) is treated as the
    # same finding as an explicit applicable:false — omission is not compliance.
    if facts_ok:
        hard_rules = (table or {}).get("hard_rules", []) or []
        for rule in hard_rules:
            rid = rule.get("id") or ""
            cond = rule.get("condition", "")
            subitem_name = rule.get("subitem")
            if not rid or not cond or not subitem_name:
                continue
            if not _eval_condition(cond, facts):
                continue
            tag = f"AUDIT-STAGE-{rid.replace('_', '-')}"
            matches = [sub for layer in layers for sub in (layer.get("subitems") or [])
                       if sub.get("name") == subitem_name]
            if not matches:
                findings.append(("P1", str(applicability_path),
                    f"{tag}: hard rule '{rid}' ({rule.get('description', '')}) triggers under the "
                    f"recorded build-facts but ship-gate sub-item '{subitem_name}' is entirely absent "
                    "from the audit report — an omitted item is not compliance, it is an unproven "
                    "hard rule (PBAF-PROP-001 Lever E)"))
            elif any(m.get("applicable") is False for m in matches):
                findings.append(("P1", str(applicability_path),
                    f"{tag}: hard rule '{rid}' ({rule.get('description', '')}) triggers under the "
                    f"recorded build-facts but ship-gate sub-item '{subitem_name}' is marked N/A — this "
                    "locked hard rule cannot be waived by marking N/A (PBAF-PROP-001 Lever E)"))

    return findings


def cmd_audit(args) -> int:
    repo_root = Path(args.repo_root) if getattr(args, "repo_root", None) \
        else Path(args.state).resolve().parent
    decision_ledger_path = Path(args.decision_ledger) if getattr(args, "decision_ledger", None) \
        else repo_root / _LEDGER_FILE
    findings = collect_audit_findings(
        Path(args.audit_dir), final=getattr(args, "final", False), state_path=args.state,
        repo_root=repo_root, decision_ledger_path=decision_ledger_path)
    return findings_report(findings)
