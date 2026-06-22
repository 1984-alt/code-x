# cmd_drift: the DRIFT ALARM (PROP-034 Lever C, fold v1.15).
#
#   cx check drift --state <CODE-X-STATE.yaml> --repo-root <dir> --cards-dir <dir>
#                  [--at-acceptance] [--module-id <id>]
#
# TWO LAYERS, honest split (CX-CHECK-SPEC demands stated limits — no green over-claim):
#
#   LAYER 1 — deterministic, BITES.  Three computable divergences over the WORKING SET:
#     (a) a working-set card references a requirement_id NOT present in the frozen manifest
#         — UNLESS the card is a deviation_class: SCOPE_CHANGE authorized fix (LOCK-FIDELITY-
#         DRIFT-UNLOGGED feeds off this);
#     (b) a BUILDING requirement in the frozen manifest with ZERO covering open-or-closed card
#         in the live deck — i.e. silently dropped DURING build;
#     (c) a fix card touches files OUTSIDE its anchored card's allowed_files — file/path over-reach
#         (LOCK-FIDELITY-RESTORE-OVERREACH, deterministic; reuses the allowed_files machinery).
#
#   LAYER 2 — advisory WARN only.  Semantic "the built behavior exceeds the anchored requirement" is
#     NOT mechanically decidable — surfaced as WARN: lines for the opposite-family reviewer lens,
#     NEVER a blocking exit code. (Same advisory-until-provable pattern PROP-033 used for golden-drift.)
#
# WORKING SET (concretely defined — the input had to be checkable, not prose):
#   = the cards in CODE-X-STATE that are open/in-progress + the requirement_ids those cards declare.
#   Open is the SAME recomputed open-card set Lever B uses (frozen registry module not in
#   accepted_modules); in-progress = state.current_card. Each working-set card_id is matched to a
#   card file in --cards-dir (by its `id`); its requirement_ids come from source_map + lock_anchor_ref.
#
# RUNS: session-start = ADVISORY (Layer 1 + 2 both informational, never blocks a boot — invoked
#   without --at-acceptance). At module-acceptance = BLOCKING for Layer 1 only (--at-acceptance);
#   an unlogged Layer-1 divergence at the Andon wall is a P1. An OPEN lock_deviation row also blocks
#   module-acceptance (enforced by cx_module_acceptance, which calls open_lock_deviation_blockers).
#
# GREEN means "no Layer-1 divergence" — explicitly NOT "no semantic drift" (Layer 2 stays WARN).
# READ-ONLY: never builds, routes, edits source, or writes state.

from pathlib import Path

from cx_common import findings_report, load_yaml, nested_get
from cx_lock_fidelity import (
    recompute_open_cards, frozen_requirement_ids, card_requirement_ids,
    accepted_module_ids,
)


def _load_cards_by_id(cards_dir: Path) -> dict:
    """Read every *.yaml card in cards_dir (non-recursive); index by the card's `id` field."""
    by_id = {}
    for card_path in sorted(cards_dir.glob("*.yaml")):
        data, err = load_yaml(str(card_path))
        if err or not isinstance(data, dict):
            continue
        cid = str(data.get("id", "") or "").strip()
        if cid:
            by_id[cid] = (data, card_path)
    return by_id


def _working_set_card_ids(repo_root: str, packet_dir_rel: str, state: dict,
                          state_loc: str | None = None) -> tuple[list, str | None]:
    """The working set = recomputed open cards + state.current_card (in-progress)."""
    open_cards, oerr = recompute_open_cards(repo_root, packet_dir_rel, state, state_loc)
    if oerr or open_cards is None:
        return [], oerr
    ws = set(open_cards)
    cur = str(state.get("current_card", "") or "").strip()
    if cur:
        ws.add(cur)
    return sorted(ws), None


def _scope_overreach(card: dict, cards_by_id: dict) -> list:
    """Layer-1 (c): a fix card whose changed_files / declared touched files fall OUTSIDE its
    anchored card's allowed_files. Deterministic, reuses the allowed_files machinery. We compare
    the fix card's OWN allowed_files (the files it is permitted to touch) against the anchored
    card's allowed_files — a fix may only touch files the anchored card itself was allowed to.
    Returns LOCK-FIDELITY-RESTORE-OVERREACH findings."""
    findings = []
    if str(card.get("mode", "")) != "FIX":
        return findings
    anchor = card.get("lock_anchor_ref")
    anchored_card_id = str(anchor.get("card_id", "") or "").strip() if isinstance(anchor, dict) else ""
    if not anchored_card_id or anchored_card_id not in cards_by_id:
        return findings  # anchor resolution is cx check card's job; here we only over-reach-check resolvable anchors
    anchored_card, _ = cards_by_id[anchored_card_id]
    anchored_allowed = set(str(f) for f in (anchored_card.get("allowed_files") or []))
    fix_files = set(str(f) for f in (card.get("allowed_files") or []))
    outside = sorted(fix_files - anchored_allowed)
    if outside:
        findings.append(("P1",
            f"fix card '{card.get('id')}'",
            f"deviation_class fix touches files OUTSIDE its anchored card '{anchored_card_id}' "
            f"allowed_files {sorted(anchored_allowed)}: {outside} — a RESTORE may only touch files "
            "the anchored card was allowed to touch (PROP-034 Lever C / LOCK-FIDELITY-RESTORE-OVERREACH)"))
    return findings


def compute_layer1_findings(repo_root: str, packet_dir_rel: str, state: dict, cards_dir: Path,
                            state_loc: str | None = None) -> tuple[list, list, str | None]:
    """Compute the BLOCKING Layer-1 drift findings + the advisory Layer-2 WARNs over the working set.
    Returns (layer1_findings, layer2_advisories, fatal_error). A fatal_error (non-None) means the
    frozen lock or working set could not be read — the caller MUST fail closed, not pass. Reused by
    cmd_drift AND by cx_module_acceptance so module-acceptance fails closed on Layer-1 drift (F7)."""
    findings, advisories = [], []
    req_ids, rerr = frozen_requirement_ids(repo_root, packet_dir_rel)
    if rerr or req_ids is None:
        return [], [], f"cannot read the frozen lock to run drift: {rerr}"
    cards_by_id = _load_cards_by_id(cards_dir)
    working_set, werr = _working_set_card_ids(repo_root, packet_dir_rel, state, state_loc)
    if werr:
        return [], [], f"cannot derive the working set: {werr}"

    # ── LAYER 1 (a): a working-set card references a requirement_id NOT in the frozen manifest ──
    # UNLESS the card is an authorized SCOPE_CHANGE fix (logged scope expansion is not silent drift).
    for cid in working_set:
        entry = cards_by_id.get(cid)
        if entry is None:
            continue  # a working-set card with no card file is a deck-staleness pre-existing condition
        card, _path = entry
        is_authorized_scope_change = (
            str(card.get("mode", "")) == "FIX"
            and str(card.get("deviation_class", "")) == "SCOPE_CHANGE"
            and str(card.get("ceo_decision_ref", "") or "").strip()
            and str(card.get("packet_amendment_ref", "") or "").strip())
        for rid in sorted(card_requirement_ids(card)):
            if rid not in req_ids and not is_authorized_scope_change:
                findings.append(("P1", f"card '{cid}'",
                    f"working-set card references requirement_id '{rid}' NOT in the frozen manifest "
                    "and is not an authorized SCOPE_CHANGE fix — unlogged scope drift away from the "
                    "lock (PROP-034 Lever C / LOCK-FIDELITY-DRIFT-UNLOGGED)"))

    # ── LAYER 1 (b): a BUILDING requirement with ZERO covering open-or-closed card ──
    all_covered = set()
    for cid, (card, _p) in cards_by_id.items():
        all_covered.update(card_requirement_ids(card))
    for rid, disp in req_ids.items():
        if disp == "BUILDING" and rid not in all_covered:
            findings.append(("P1", "frozen manifest",
                f"BUILDING requirement '{rid}' has ZERO covering card in the live deck — silently "
                "dropped during build (deck proved coverage at compile; drift re-proves it as the "
                "build progresses) (PROP-034 Lever C / LOCK-FIDELITY-DRIFT-UNLOGGED)"))

    # ── LAYER 1 (c): fix-card file over-reach (RESTORE-OVERREACH) ──
    for cid in working_set:
        entry = cards_by_id.get(cid)
        if entry is None:
            continue
        card, _path = entry
        findings.extend(_scope_overreach(card, cards_by_id))

    # ── LAYER 2 — advisory WARN only (semantic drift is not mechanically decidable) ──
    for cid in working_set:
        entry = cards_by_id.get(cid)
        if entry is None:
            continue
        card, _path = entry
        if str(card.get("mode", "")) == "FIX" and str(card.get("deviation_class", "")) == "AMBIGUITY_RESOLVED":
            advisories.append(
                f"WARN: fix card '{cid}' is AMBIGUITY_RESOLVED — a reviewer must confirm the chosen "
                "reading does not silently exceed the anchored requirement (Layer 2 advisory; semantic "
                "'behavior exceeds requirement' is not mechanically decidable) (PROP-034 Lever C)")
    return findings, advisories, None


def cmd_drift(args) -> int:
    state_path = getattr(args, "state", None)
    repo_root = getattr(args, "repo_root", None)
    cards_dir_arg = getattr(args, "cards_dir", None)
    at_acceptance = bool(getattr(args, "at_acceptance", False))

    if not state_path or not repo_root or not cards_dir_arg:
        print("FIX-FIRST\n  [P0] cx check drift requires --state, --repo-root, and --cards-dir")
        return 1

    state, serr = load_yaml(state_path)
    if serr or not isinstance(state, dict):
        print(f"FIX-FIRST\n  [P0] {state_path} — {serr or 'not a YAML mapping'}")
        return 1

    cards_dir = Path(cards_dir_arg)
    if not cards_dir.is_dir():
        print(f"FIX-FIRST\n  [P0] {cards_dir_arg} — cards-dir not found or not a directory")
        return 1

    packet_dir_rel = str(state.get("packet_dir", "") or "").strip()

    findings, advisories, fatal = compute_layer1_findings(
        repo_root, packet_dir_rel, state, cards_dir, state_path)
    if fatal:
        # Cannot read the frozen lock / working set at all — fail closed (a real divergence).
        print(f"FIX-FIRST\n  [P1] {state_path} — {fatal}")
        return 1

    working_set, _werr = _working_set_card_ids(repo_root, packet_dir_rel, state, state_path)

    # ── Emit ──
    if at_acceptance:
        # BLOCKING for Layer 1 only; Layer 2 advisories still print but never change the exit code.
        rc = findings_report(findings)
        for w in advisories:
            print(f"  {w}")
        return rc

    # session-start = advisory: print everything, NEVER block a boot.
    print("PASS (advisory)")
    print(f"  [INFO] working set: {working_set or '(none open)'}")
    for sev, loc, msg in findings:
        print(f"  WARN[{sev}-at-acceptance] {loc} — {msg}")
    for w in advisories:
        print(f"  {w}")
    if not findings and not advisories:
        print("  [INFO] no Layer-1 divergence; no Layer-2 advisory (NOT a claim of zero semantic drift)")
    return 0


def open_lock_deviation_blockers(state: dict, loc: str, gate: str) -> list:
    """Shared helper (PROP-034): an OPEN lock_deviation row blocks the named accept gate.
    Returns a list of (severity, loc, msg) findings — EMPTY means no open deviation blocks <gate>.
    Called by cx check module-acceptance (the Andon wall) so logged ambiguity can never quietly ship."""
    findings = []
    rows = state.get("lock_deviations") if isinstance(state, dict) else None
    if rows is None:
        return findings
    if not isinstance(rows, list):
        findings.append(("P1", loc,
            "lock_deviations must be a list of typed rows (PROP-034)"))
        return findings
    from cx_lock_fidelity import VALID_DEVIATION_CLASSES, path_is_unsafe
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            findings.append(("P1", loc, f"lock_deviations[{i}] is not a mapping (PROP-034)"))
            continue
        for key in ("deviation_id", "card_id", "lock_anchor_ref", "deviation_class", "reason",
                    "status", "surfaced_at_gate"):
            if not row.get(key):
                findings.append(("P1", loc,
                    f"lock_deviations[{i}].{key} missing — a typed deviation row carries "
                    "{deviation_id, card_id, lock_anchor_ref, deviation_class, reason, status, "
                    "surfaced_at_gate} (PROP-034)"))
        dc = str(row.get("deviation_class", ""))
        if dc and dc not in VALID_DEVIATION_CLASSES:
            findings.append(("P1", loc,
                f"lock_deviations[{i}].deviation_class '{dc}' not in {sorted(VALID_DEVIATION_CLASSES)} "
                "(PROP-034)"))
        # SCOPE_CHANGE deviations carry the authorizing refs; path-safety-validate them.
        if dc == "SCOPE_CHANGE":
            for refk in ("ceo_decision_ref", "packet_amendment_ref"):
                if not row.get(refk):
                    findings.append(("P1", loc,
                        f"lock_deviations[{i}] is SCOPE_CHANGE without {refk} (PROP-034)"))
        for refk in ("ceo_decision_ref", "packet_amendment_ref"):
            v = str(row.get(refk, "") or "").strip()
            if v and path_is_unsafe(v) and "/" in v:
                findings.append(("P1", loc,
                    f"lock_deviations[{i}].{refk} '{v}' is an unsafe path (absolute / '..') (PROP-034)"))
        # status is an ENUM: only CEO_REVIEWED is nonblocking. OPEN blocks (a logged ambiguity not yet
        # reviewed); ANY other/unknown value (CLOSED/DONE/REVIEWED/typo/blank) fails closed too — a row
        # whose status the wall does not understand must NOT slip through as if reviewed (PROP-034 xfam F8).
        status = str(row.get("status", "")).strip().upper()
        VALID_DEVIATION_STATUSES = {"OPEN", "CEO_REVIEWED"}
        if status == "OPEN":
            findings.append(("P1", loc,
                f"lock_deviations[{i}] '{row.get('deviation_id')}' is OPEN at the {gate} gate — a "
                "logged AMBIGUITY/scope deviation must be CEO_REVIEWED before the module is accepted; "
                "logged ambiguity can never quietly ship (PROP-034)"))
        elif status not in VALID_DEVIATION_STATUSES:
            findings.append(("P1", loc,
                f"lock_deviations[{i}] '{row.get('deviation_id')}' has status '{row.get('status')}' "
                f"— only {sorted(VALID_DEVIATION_STATUSES)} are valid, and ONLY CEO_REVIEWED is "
                f"nonblocking at the {gate} gate; an unknown/typo status (CLOSED/DONE/blank) must "
                "fail closed, never slip through as reviewed (PROP-034)"))
    return findings
