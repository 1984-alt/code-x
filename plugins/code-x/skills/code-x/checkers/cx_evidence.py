# cmd_evidence: checks that all evidence_required paths exist and are valid.
# B-PROP-004 (proof-card honesty): also re-reads typed evidence_claims rows —
# a verdict is never a sentence next to a log path.
import re
from pathlib import Path

from cx_common import findings_report, load_yaml, scan_faked_pass
from cx_scope import _parse_touched_files, _file_matches

# B-PROP-004: claim types whose green run REQUIRES a demonstrated red run
# (positive control) — "green ≠ enforcing", applied to project proof tests.
POSITIVE_CONTROL_CLAIM_TYPES = {
    "design_fidelity", "interaction", "click", "swipe", "source_truth",
    "money_invariant", "security_boundary", "import", "dedupe", "recovery",
    "destructive",
}
INTERACTION_CLAIM_TYPES = {"interaction", "click", "swipe"}
VALID_EVENT_FAMILIES = {"touch", "pointer", "mouse", "keyboard"}
EVIDENCE_CLAIM_REQUIRED_KEYS = ("claim_id", "claimed_verdict", "command",
                                "exit_code", "log_path", "produced_at",
                                "produced_by")
MODALITY_REQUIRED_KEYS = ("handler_event_family", "dispatched_event_family",
                          "modality_source", "event_reaches_handler_evidence")
# baseline_source values that mean "builder graded its own same-wave homework"
INVALID_BASELINE_SOURCES = {"builder_same_wave", "builder_output", "same_wave_build"}
# claim types that ALWAYS compare actual output to a reference → baseline required by TYPE
BASELINE_CLAIM_TYPES = {"design_fidelity", "route_map", "click_path", "snapshot",
                        "vocabulary_coverage"}


def _read_log(card_dir: Path, log_path: str) -> str | None:
    # Path-safety (EVAL-040 xfam P0): a model-authored log_path that is absolute, '..'-escaping, a
    # symlink, or resolves OUTSIDE card_dir lets a claim point at any always-passing file → a forged
    # proof. Reject before reading; both callers treat None as fail-closed. Mirrors safe_repo_ref
    # (cx_common.py) but rooted at the card/receipt dir.
    p = Path(str(log_path))
    if p.is_absolute() or ".." in p.parts:
        return None
    full = card_dir / p
    if full.is_symlink():
        return None
    resolved = full.resolve()
    if not resolved.is_relative_to(Path(card_dir).resolve()):
        return None
    if not resolved.is_file():
        return None
    return resolved.read_text(encoding="utf-8", errors="replace")


def _check_evidence_claims(card: dict, card_dir: Path, loc: str, findings: list) -> None:
    """B-PROP-004 claim-evidence binding + scoped positive control + modality +
    universal baseline pinning. All rows live on the proof card as
    evidence_claims; cx RE-READS every referenced log."""
    claims = card.get("evidence_claims")
    if claims is None or claims == []:
        # GPT cross-review 2026-06-12: a PROOF card cannot opt out by omission —
        # the proof card's verdicts ARE its evidence_claims.
        if str(card.get("mode", "")) == "PROOF":
            findings.append(("P1", loc,
                "PROOF card with no evidence_claims — every PASS/FAIL verdict in a "
                "proof card carries a typed evidence_claims row; omission is not an "
                "exemption (B-PROP-004)"))
        return
    if not isinstance(claims, list):
        findings.append(("P0", loc, "evidence_claims must be a list of typed rows (B-PROP-004)"))
        return

    for i, row in enumerate(claims):
        tag = f"evidence_claims[{i}]"
        if not isinstance(row, dict):
            findings.append(("P0", loc, f"{tag} is not a mapping"))
            continue
        cid = str(row.get("claim_id") or f"#{i}")
        for key in EVIDENCE_CLAIM_REQUIRED_KEYS:
            if key not in row or row.get(key) in (None, ""):
                findings.append(("P1", loc,
                    f"{tag} ({cid}).{key} missing — a verdict is never a sentence next "
                    "to a log path; the row must be fully typed (B-PROP-004)"))

        # --- claim-evidence binding: re-read the log ---
        log_path = row.get("log_path")
        log = _read_log(card_dir, log_path) if log_path else None
        if log_path and log is None:
            findings.append(("P0", loc,
                f"{tag} ({cid}) log missing: {log_path} — a claim without its log is "
                "unverifiable (B-PROP-004)"))
        verdict = str(row.get("claimed_verdict", "")).upper()
        if log is not None and verdict == "PASS":
            try:
                exit_code = int(row.get("exit_code"))
            except (TypeError, ValueError):
                exit_code = None
            nonzero_ok = str(row.get("nonzero_pass_semantics", "")).lower() in ("yes", "true")
            if exit_code != 0 and not nonzero_ok:
                findings.append(("P0", loc,
                    f"{tag} ({cid}) claims PASS with exit_code {row.get('exit_code')} and "
                    "no declared nonzero_pass_semantics — claimed PASS contradicted by "
                    "its own evidence (B-PROP-004)"))
            for marker in (row.get("expect_contains") or []):
                if str(marker) not in log:
                    findings.append(("P0", loc,
                        f"{tag} ({cid}) claims PASS but expect_contains marker "
                        f"'{marker}' is absent from the log — claim/log mismatch (B-PROP-004)"))
            for fm in (row.get("fail_markers") or []):
                if str(fm) in log:
                    findings.append(("P0", loc,
                        f"{tag} ({cid}) claims PASS but fail_marker '{fm}' appears in "
                        "the log — claim/log mismatch (B-PROP-004)"))

        claim_type = str(row.get("claim_type", "")).lower()

        # --- positive control (CAN-FAIL proof), scoped to acceptance-proof claims ---
        sole_high_risk = str(row.get("sole_proof_of_high_risk_claim", "")).lower() in ("yes", "true")
        if claim_type in POSITIVE_CONTROL_CLAIM_TYPES or sole_high_risk:
            pc = row.get("positive_control")
            if not isinstance(pc, dict):
                findings.append(("P1", loc,
                    f"{tag} ({cid}) claim_type '{claim_type or 'sole high-risk proof'}' "
                    "requires a positive_control red run — a green run with no "
                    "demonstrated red run does not count (green ≠ enforcing, B-PROP-004)"))
            else:
                pc_log_path = pc.get("log_path")
                pc_log = _read_log(card_dir, pc_log_path) if pc_log_path else None
                if pc_log is None:
                    findings.append(("P0", loc,
                        f"{tag} ({cid}) positive_control log missing: {pc_log_path} — "
                        "the red run must be recorded alongside the green run (B-PROP-004)"))
                else:
                    try:
                        pc_exit = int(pc.get("exit_code"))
                    except (TypeError, ValueError):
                        pc_exit = None
                    marker = str(pc.get("expected_failure_marker", "") or "")
                    # GPT cross-review 2026-06-12: a "red" run with exit 0 is not red —
                    # nonzero exit ALWAYS required; the declared marker must also appear.
                    demonstrated = (pc_exit not in (None, 0)
                                    and (not marker or marker in pc_log))
                    if not demonstrated:
                        findings.append(("P1", loc,
                            f"{tag} ({cid}) positive_control does not demonstrate the "
                            "EXPECTED failure (expected_failure_marker absent from the red "
                            "log / exit 0) — a red run for an unrelated reason does not "
                            "qualify (B-PROP-004)"))

        # --- event modality: hard P1 for interaction proof ---
        if claim_type in INTERACTION_CLAIM_TYPES:
            mod = row.get("modality")
            if not isinstance(mod, dict):
                findings.append(("P1", loc,
                    f"{tag} ({cid}) interaction claim without a typed modality block "
                    f"{{{', '.join(MODALITY_REQUIRED_KEYS)}}} — modality cannot stay "
                    "advisory (B-PROP-004)"))
            else:
                for key in MODALITY_REQUIRED_KEYS:
                    if not mod.get(key):
                        findings.append(("P1", loc,
                            f"{tag} ({cid}) modality.{key} missing (B-PROP-004)"))
                handler = str(mod.get("handler_event_family", "")).lower()
                dispatched = str(mod.get("dispatched_event_family", "")).lower()
                for fam_name, fam in (("handler_event_family", handler),
                                      ("dispatched_event_family", dispatched)):
                    if fam and fam not in VALID_EVENT_FAMILIES:
                        findings.append(("P1", loc,
                            f"{tag} ({cid}) modality.{fam_name} '{fam}' not in "
                            f"{sorted(VALID_EVENT_FAMILIES)}"))
                if handler and dispatched and handler != dispatched:
                    findings.append(("P1", loc,
                        f"{tag} ({cid}) dispatched event family '{dispatched}' != handler "
                        f"family '{handler}' — a {dispatched}-event test never touches a "
                        f"{handler} handler (hard P1, B-PROP-004)"))
                # GPT cross-review 2026-06-12: the handler-reach evidence must be a
                # real artifact, not a self-attested sentence.
                ev_ref = str(mod.get("event_reaches_handler_evidence", "") or "")
                if ev_ref and _read_log(card_dir, ev_ref) is None:
                    findings.append(("P2", loc,
                        f"{tag} ({cid}) modality.event_reaches_handler_evidence "
                        f"'{ev_ref}' does not resolve to an existing file — handler-reach "
                        "evidence is an artifact, never an assertion (B-PROP-004)"))

        # --- baseline pinning, universal ---
        # GPT cross-review 2026-06-12: comparison-class claim types pin a baseline
        # by TYPE, never by opt-in flag alone.
        compares = (claim_type in BASELINE_CLAIM_TYPES
                    or str(row.get("compares_to_reference", "")).lower() in ("yes", "true"))
        if compares:
            baseline = row.get("baseline")
            if not isinstance(baseline, dict) or not all(
                    baseline.get(k) for k in ("baseline_ref", "baseline_hash", "baseline_source")):
                findings.append(("P0", loc,
                    f"{tag} ({cid}) compares actual output to a reference but does not "
                    "pin {baseline_ref, baseline_hash, baseline_source} — comparison "
                    "baseline must be the frozen lock/contract hash (B-PROP-004)"))
            elif str(baseline.get("baseline_source", "")).lower() in INVALID_BASELINE_SOURCES:
                findings.append(("P0", loc,
                    f"{tag} ({cid}) baseline_source '{baseline.get('baseline_source')}' is "
                    "builder-produced output from the same implementation wave — INVALID "
                    "as 'expected'; pin the frozen lock/contract hash (B-PROP-004)"))


def cmd_evidence(args) -> int:
    card_path = args.card
    card, err = load_yaml(card_path)
    if err:
        print(f"FIX-FIRST\n  [P0] {card_path} — {err}")
        return 1

    findings = []
    loc = card_path

    # P2-06 / PB-PROP-002 follow-up: resolve evidence paths relative to the card
    # first, then the project root when the card lives in a repo.
    card_dir = Path(card_path).resolve().parent
    repo_root = None
    for candidate in (card_dir, *card_dir.parents):
        if (candidate / ".git").exists() or (candidate / "CODE-X-STATE.yaml").exists():
            repo_root = candidate
            break

    ev_required = card.get("evidence_required") or []
    mode = card.get("mode", "")
    is_fix_card = mode == "FIX"

    # Check each evidence path exists and is non-empty
    for ev_path in ev_required:
        p = Path(str(ev_path))
        if not p.is_absolute():
            card_relative = card_dir / p
            repo_relative = (repo_root / p) if repo_root is not None else None
            if card_relative.exists() or repo_relative is None:
                p = card_relative
            else:
                p = repo_relative
        p = p.resolve()
        if not p.exists():
            findings.append(("P0", loc, f"evidence_required path missing: {ev_path}"))
        elif p.is_file() and p.stat().st_size == 0:
            findings.append(("P1", loc, f"evidence_required path is empty: {ev_path}"))
        elif p.is_file():
            # Scan for faked-pass patterns
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                hits = scan_faked_pass(content)
                for h in hits:
                    findings.append(("P0", loc, f"faked-pass pattern in {ev_path}: {h}"))
            except Exception:
                pass

    # B-PROP-004: proof-card honesty — typed evidence_claims re-read against their logs
    _check_evidence_claims(card, card_dir, loc, findings)

    # P1-05: diff-aware test-edit guard
    # A test file in the diff is ONLY allowed with fix_test_edits.allowed: yes + reason + file listed
    diff_path = getattr(args, 'diff', None)
    touched_in_diff: list[str] = []
    if diff_path:
        parsed = _parse_touched_files(diff_path)
        if parsed:
            touched_in_diff = parsed

    fix_test_edits = card.get("fix_test_edits") or {}
    test_edits_allowed = str(fix_test_edits.get("allowed", "no")).lower() in ("yes", "true")
    test_edits_reason = (fix_test_edits.get("reason") or "").strip()
    touched_test_files_declared = [str(f) for f in (fix_test_edits.get("touched_test_files") or [])]

    if is_fix_card and touched_in_diff:
        for f in touched_in_diff:
            is_test_file = bool(re.search(r'test', f, re.I))
            if is_test_file:
                if not test_edits_allowed:
                    findings.append(("P1", loc,
                        f"diff touches test file '{f}' but fix_test_edits.allowed is not yes — "
                        "test edits require explicit authorisation"))
                elif not test_edits_reason:
                    findings.append(("P1", loc,
                        f"fix_test_edits.allowed=yes but reason is empty — must explain why test is being edited"))
                elif f not in touched_test_files_declared and not any(
                    _file_matches(f, tf) for tf in touched_test_files_declared
                ):
                    findings.append(("P1", loc,
                        f"diff touches test file '{f}' but it is not listed in fix_test_edits.touched_test_files — "
                        "all touched test files must be explicitly declared"))
                else:
                    # Check regression_test_evidence is set for this file
                    ttf_items = fix_test_edits.get("touched_test_files") or []
                    if isinstance(ttf_items, list):
                        matched = False
                        for tf_item in ttf_items:
                            if isinstance(tf_item, dict):
                                if _file_matches(f, str(tf_item.get("file", ""))):
                                    if not tf_item.get("regression_test_evidence"):
                                        findings.append(("P1", loc,
                                            f"fix_test_edits.touched_test_files entry for '{f}' "
                                            "missing regression_test_evidence"))
                                    matched = True
                            elif isinstance(tf_item, str):
                                if _file_matches(f, tf_item):
                                    matched = True
                        # If items are plain strings without regression_test_evidence, that's OK —
                        # the evidence is presumed tracked at card level

    # Fix cards with no --diff: apply the old allowed_files-based check as fallback
    if is_fix_card and not touched_in_diff:
        allowed_files = card.get("allowed_files") or []
        for f in allowed_files:
            if re.search(r'test', str(f), re.I):
                if not test_edits_allowed:
                    findings.append(("P1", loc,
                        f"FIX card lists test file '{f}' in allowed_files but fix_test_edits.allowed is not yes — "
                        "test edits require explicit authorisation"))

    return findings_report(findings)
