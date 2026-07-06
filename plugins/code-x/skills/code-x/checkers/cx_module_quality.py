# cmd_module_quality: the per-module QUALITY BAR (V1.10 module_acceptance gate family).
#
# Reads a MODULE-ACCEPTANCE receipt + the frozen module_registry and enforces the professional
# quality bar the Andon receipt asserts — depth by the module's risk:
#   - QUALITY CARD (always): the receipt carries a quality_card answering the core four
#     (security · efficient · regression · tests) + a conformance answer — else P1.
#   - MODULE SELF-REVIEW (always): the receipt carries the same-family self_review evidence
#     for the completed module — build-card intent alone is not proof the review ran.
#   - CONFORMANCE-TO-LOCK: a money/login/data module REQUIRES extracted-actuals conformance
#     evidence (conformance_evidence_refs non-empty) vs the locked IMPLEMENTATION-CONTRACT
#     manifest — a free-text answer alone is not proof (P1; the non-visual anti-drift, GAP-1).
#   - REGRESSION-SMOKE: a module touching the shared shell/routes must show a PASS regression-smoke
#     over the already-accepted modules (quality_card.regression == PASS) — else P1.
#
#   cx check module-quality --acceptance <MODULE-ACCEPTANCE.yaml> --registry <MODULE-REGISTRY.yaml> --module-id <id>
#
# READ-ONLY. (design-fidelity BLOCKS the VISUAL half; this blocks the architecture/logic/data half.)
from pathlib import Path

from cx_common import findings_report, load_yaml, nested_get, field_present
from cx_evidence import _read_log
from cx_module_acceptance import validate_live_slice_accept, registry_flag_true, has_blocking

CONFORMANCE_RISK = {"money", "login", "data"}
CORE_FOUR = ("security", "efficient", "regression", "tests")
SELF_REVIEW_PASS = {"PASS", "PASS_AFTER_FIX"}
# EVAL-040: the build_validation N/A escape is for these artifact kinds ONLY (docs/config/protocol).
BUILD_VALIDATION_NA_ARTIFACT_TYPES = {"docs", "config", "protocol"}
SELF_REVIEW_EVIDENCE_KEYS = (
    "review_ref",
    "receipt_ref",
    "report_ref",
    "findings_ref",
    "review_agent",
    "first_review_agent",
    "review_id",
)


def _str_field(d: dict, key: str) -> str:
    """EVAL-040: field_present (cx_common.py:144) accepts [], [None], and maps as "present" — a
    scalar machine field (status/reviewer/builder/...) needs a strict string read instead, mirroring
    the R12 non-string-as-absent hardening (cx_module_acceptance.py:592-596). Non-string -> ABSENT."""
    v = d.get(key) if isinstance(d, dict) else None
    return v.strip() if isinstance(v, str) else ""


def cmd_module_quality(args) -> int:
    module_id = str(getattr(args, "module_id", "") or "").strip()
    acceptance_path = getattr(args, "acceptance", None)
    registry_path = getattr(args, "registry", None)
    findings = []

    if not acceptance_path:
        print("FIX-FIRST\n  [P1] --acceptance required for cx check module-quality")
        return 1
    if not registry_path:
        print("FIX-FIRST\n  [P1] --registry required for cx check module-quality — the quality bar's "
              "risk source (money/login/data + shared-shell) MUST be the frozen module_registry, never "
              "the acceptance receipt's own self-declaration; omitting it would let a money module skip "
              "conformance/regression (fail-closed) [V1.10]")
        return 1
    receipt, rerr = load_yaml(acceptance_path)
    if rerr or not isinstance(receipt, dict):
        print(f"FIX-FIRST\n  [P1] {acceptance_path} — {rerr or 'not a mapping'}")
        return 1
    # A `module_acceptance:` block, when present, MUST be a mapping. Falling back to the bare receipt on a
    # non-mapping block (e.g. `module_acceptance: []`) let a list/scalar block + top-level fields slip the
    # typed quality / live_slice_accept / verify_app checks on the LAST-slice path (B-PROP-010 xfam, GPT-5.5;
    # mirrors the cx_module_acceptance R12 fix). Only a receipt with NO module_acceptance key uses the bare
    # mapping. Fail closed here so the verify_app precondition can't be bypassed via a non-mapping block.
    if "module_acceptance" in receipt:
        ma = nested_get(receipt, "module_acceptance")
        if not isinstance(ma, dict):
            print(f"FIX-FIRST\n  [P1] {acceptance_path} — acceptance receipt 'module_acceptance' is not a "
                  "mapping; a list/scalar block cannot carry the typed quality / live_slice_accept / "
                  "verify_app fields (fail-closed) [B-PROP-010 xfam]")
            return 1
    else:
        ma = receipt
    loc = acceptance_path

    if not module_id:
        module_id = str(ma.get("module_id", "") or "").strip()

    # Built-code review (F1): the receipt must be FOR the requested module — a wrong-module receipt
    # (e.g. a live_slice receipt pointed at a non-live module to skip the live-drive check) is rejected.
    # HONEST SCOPE: module-quality trusts its --registry + --acceptance the SAME way it trusts them for
    # risk/conformance (pre-existing). The order wall (module-start) content-binds the registry for every
    # slice WITH a successor; the LAST slice rides this check, so the rail must invoke it for that slice
    # with the frozen registry + its bound receipt. final-ready does not re-check live_slice (residual).
    receipt_mid = str(ma.get("module_id", "") or "").strip()
    if module_id and receipt_mid and receipt_mid != module_id:
        findings.append(("P1", loc,
            f"acceptance receipt module_id '{receipt_mid}' != requested '{module_id}' — the quality "
            "bar must read the receipt FOR the module it checks (a wrong-module receipt cannot satisfy "
            "another module's bar, e.g. skip a live_slice's live-drive check) [B-PROP-008 built-code review]"))

    # Risk context: the frozen registry is the SOURCE OF TRUTH for risk; the receipt's own
    # declaration may only ADD risk (raise the bar), never lower it (fail-closed against under-declaring).
    risk_flags = set()
    touches_shared = False
    registry, gerr = load_yaml(registry_path)
    if gerr:
        print(f"FIX-FIRST\n  [P1] {registry_path} — {gerr}")
        return 1
    mr = nested_get(registry, "module_registry") if isinstance(registry, dict) else None
    modules = mr.get("modules") if isinstance(mr, dict) else None
    mod = next((m for m in (modules or [])
                if isinstance(m, dict) and str(m.get("module_id", "")).strip() == module_id), None)
    if mod is None:
        findings.append(("P1", loc,
            f"module '{module_id}' not found in the registry — cannot resolve its risk flags "
            "to set the quality bar (V1.10)"))
    else:
        risk_flags = {str(r).strip().lower() for r in (mod.get("risk_flags") or [])}
        touches_shared = str(mod.get("touches_shared_shell", "")).strip().lower() in ("yes", "true")
    risk_flags |= {str(r).strip().lower() for r in (ma.get("risk_flags") or [])}
    touches_shared = touches_shared or str(ma.get("touches_shared_shell", "")).strip().lower() in ("yes", "true")

    # --- B-PROP-008: live-slice CEO live-drive accept (P0) ---
    # The frozen registry (not the receipt's self-declaration) decides which modules are live_slices.
    # The order wall (module-start) gates a slice that has a NEXT; this covers the LAST slice too —
    # so every live_slice's acceptance proves the CEO DROVE the running build, never a Mode A shell.
    if mod is not None and registry_flag_true(mod.get("live_slice")):
        # PBF-PROP-012 Part E: pass the receipt's parent directory as base so validate_module_demo
        # can resolve shown_screenshot_path and ceo_turn_ref (screenshot + turn artifact must
        # be in-repo relative to the receipt's location when no explicit repo-root is given).
        # PB-PROP-003 Unit 2 (finding CX-PB003-001 FIX-FIRST): thread --packet-dir (+ module_id,
        # already resolved above) so a FINAL/ONLY live_slice module — one no later module-start
        # order-wall re-validation ever fires for — gets the SAME criteria_refs wiring/reverse-
        # coverage checks a PRIOR module already gets via validate_accepted_module. Omitted (the
        # pre-existing standalone invocation, e.g. no --packet-dir on the CLI), those checks
        # silently do not run — this never widens what a caller-less check enforces, only what a
        # caller WITH packet context can.
        from pathlib import Path as _Path
        packet_dir = getattr(args, "packet_dir", None)
        findings.extend(validate_live_slice_accept(ma, loc, base=str(_Path(loc).parent),
                                                    packet_dir=packet_dir, module_id=module_id))

    # --- QUALITY CARD: core four + conformance answer present ---
    qc = ma.get("quality_card")
    if not isinstance(qc, dict):
        findings.append(("P1", loc,
            "no quality_card on the acceptance receipt — a module is not accepted without the "
            "quality card answering the core four (security · efficient · regression · tests) + "
            "the conformance answer [V1.10]"))
        qc = {}
    else:
        for k in CORE_FOUR:
            if not field_present(qc, k):
                findings.append(("P1", loc,
                    f"quality_card.{k} missing — the core four (security · efficient · regression · "
                    "tests) must all be answered for module acceptance [V1.10]"))
        if not field_present(qc, "conformance"):
            findings.append(("P1", loc,
                "quality_card.conformance missing — every module answers conformance-to-lock "
                "(does the built code implement the locked implementation-contract?) [V1.10]"))

    # --- MODULE SELF-REVIEW: actual evidence, not just card intent ---
    # Build cards already declare actor_record.self_review, but real-project v1.20 showed that declaration
    # alone can drift: two accepted modules had deterministic evidence while the same-family
    # self-review receipt never appeared. The module acceptance rail now requires the review receipt.
    sr = ma.get("self_review")
    if not isinstance(sr, dict) and isinstance(qc, dict):
        sr = qc.get("self_review")
    if not isinstance(sr, dict):
        findings.append(("P1", loc,
            "same-family self_review missing — module acceptance must carry the actual self-review "
            "receipt/evidence; build-card intent is not enough [PROP-042 / v1.21]"))
    else:
        relation = str(sr.get("family_relation", "") or "").strip().lower()
        if relation != "same_family":
            findings.append(("P1", loc,
                "same-family self_review.family_relation must be 'same_family' — a module self-review "
                "cannot be replaced by cross-family/final review debt [PROP-042 / v1.21]"))
        status = str(sr.get("status", "") or "").strip().upper()
        if status not in SELF_REVIEW_PASS:
            findings.append(("P1", loc,
                f"same-family self_review.status is '{status or 'UNSET'}', not PASS/PASS_AFTER_FIX — "
                "module acceptance needs a completed self-review [PROP-042 / v1.21]"))
        if not any(field_present(sr, k) for k in SELF_REVIEW_EVIDENCE_KEYS):
            findings.append(("P1", loc,
                "same-family self_review has no evidence anchor (review_ref/receipt_ref/report_ref/"
                "findings_ref/review_agent/first_review_agent/review_id) — the review must be "
                "re-readable, not only asserted [PROP-042 / v1.21]"))

    # --- BUILD-VALIDATION leg: the build actually passed, PROVEN by re-read logs (EVAL-040) ---
    bv = ma.get("build_validation")
    if not isinstance(bv, dict):
        findings.append(("P1", loc,
            "build_validation leg missing — module acceptance must carry machine-checkable proof "
            "the build actually validated (typecheck/lint/tests/build were run and PASSED), or a "
            "declared applicability: not_applicable for a module with no build [EVAL-040]"))
    elif _str_field(bv, "applicability") == "not_applicable":
        art = _str_field(bv, "acceptance_artifact_type")
        if not _str_field(bv, "na_reason") or not art:
            findings.append(("P1", loc,
                "build_validation applicability: not_applicable requires na_reason + "
                "acceptance_artifact_type — a declared N/A must be reasoned, not protocol "
                "noise [EVAL-040]"))
        elif art not in BUILD_VALIDATION_NA_ARTIFACT_TYPES:
            findings.append(("P1", loc,
                f"build_validation.acceptance_artifact_type '{art}' is not one of "
                f"{sorted(BUILD_VALIDATION_NA_ARTIFACT_TYPES)} — an N/A escape is only for "
                "docs/config/protocol modules [EVAL-040]"))
        # A risk-flagged (money/login/data) module HAS a build and cannot skip build_validation via
        # the N/A escape — the escape is for docs/config/protocol modules only (xfam P0). Registry is
        # the risk source of truth (already merged into risk_flags above; receipt can only ADD risk).
        # (Residual: a genuinely code module with NO risk flags could still declare N/A — a future
        # authoritative registry `module_kind` field would fully close it; the risk-flag cross-check
        # closes the dangerous money/login/data case.)
        if risk_flags & CONFORMANCE_RISK:
            findings.append(("P0", loc,
                f"module '{module_id}' is risk {sorted(risk_flags & CONFORMANCE_RISK)} but declares "
                "build_validation applicability: not_applicable — a money/login/data module has a "
                "build and cannot skip build_validation via the N/A escape [EVAL-040]"))
    else:
        status = _str_field(bv, "status").upper()
        if status not in SELF_REVIEW_PASS:
            findings.append(("P1", loc,
                f"build_validation.status is '{status or 'UNSET'}', not PASS/PASS_AFTER_FIX — an "
                "honest FAIL or missing status means the module is not accepted [EVAL-040]"))
        ran_raw = bv.get("ran")
        ran = ([str(r).strip() for r in ran_raw if isinstance(r, str) and r.strip()]
               if isinstance(ran_raw, list) else [])
        if not ran:
            findings.append(("P1", loc,
                "build_validation.ran is empty/not-a-list — every check the module claims to have "
                "run must be named [EVAL-040]"))
        claims = bv.get("claims") if isinstance(bv.get("claims"), list) else []
        claimed = set()
        for i, row in enumerate(claims):
            if not isinstance(row, dict):
                continue
            tag = f"build_validation.claims[{i}]"
            chk = _str_field(row, "check")
            if _str_field(row, "claimed_verdict").upper() != "PASS":
                continue
            if chk:
                claimed.add(chk)   # a check WITH a PASS claim row (verified or contradicted) is covered
            log_path = row.get("log_path")
            log = _read_log(Path(loc).parent, log_path) if log_path else None
            if log is None:
                findings.append(("P0", loc,
                    f"{tag} claims PASS but its log_path '{log_path}' does not resolve — a claim "
                    "without its log is unverifiable (fabricated PASS) [EVAL-040]"))
                continue
            try:
                exit_code = int(row.get("exit_code"))
            except (TypeError, ValueError):
                exit_code = None
            nonzero_ok = str(row.get("nonzero_pass_semantics", "")).lower() in ("yes", "true")
            fail_hit = next((str(fm) for fm in (row.get("fail_markers") or []) if str(fm) in log), None)
            missing_marker = next((str(m) for m in (row.get("expect_contains") or []) if str(m) not in log), None)
            if (exit_code != 0 and not nonzero_ok) or fail_hit or missing_marker is not None:
                if fail_hit:
                    reason = f"fail_marker '{fail_hit}' present in the log"
                elif missing_marker is not None:
                    reason = f"expect_contains marker '{missing_marker}' absent from the log"
                else:
                    reason = f"exit_code {row.get('exit_code')} with no declared nonzero_pass_semantics"
                findings.append(("P0", loc,
                    f"{tag} claims PASS but the re-read log contradicts it ({reason}) — fabricated "
                    "PASS [EVAL-040]"))
        # Coverage (xfam #7 isolation): a `ran` check with NO PASS claim row at all is the only
        # -MALFORMED here; a check whose claim row is contradicted already fired its own P0 above.
        for chk in ran:
            if chk not in claimed:
                findings.append(("P1", loc,
                    f"build_validation.ran names '{chk}' but no re-readable PASS claims row covers "
                    "it — command coverage requires a matching claim for every named check [EVAL-040]"))
        rv, bd = _str_field(bv, "reviewer"), _str_field(bv, "builder")
        if not rv or not bd:
            findings.append(("P1", loc,
                "build_validation.reviewer/builder identity missing — both must be present as "
                "scalar ids [EVAL-040]"))
        elif rv.casefold() == bd.casefold():
            findings.append(("P1", loc,
                "build_validation.reviewer == builder — the builder cannot grade its own same-wave "
                "build (same-wave self-grading) [EVAL-040]"))

    # --- ANTI-SLOP leg: same-family, fresh non-builder, slop_removal role (EVAL-040) ---
    aslop = ma.get("anti_slop")
    if not isinstance(aslop, dict):
        findings.append(("P1", loc,
            "anti_slop leg missing — module acceptance must carry a same-family slop_removal review "
            "receipt (dead code / over-abstraction / defensive theater / narrative comments / "
            "premature frameworks stripped); always-on, no N/A path [EVAL-040]"))
    else:
        aslop_status = _str_field(aslop, "status").upper()
        role = _str_field(aslop, "role")
        relation = _str_field(aslop, "family_relation")
        rf, bf = _str_field(aslop, "reviewer_family"), _str_field(aslop, "builder_family")
        if aslop_status not in SELF_REVIEW_PASS:
            findings.append(("P1", loc,
                f"anti_slop.status is '{aslop_status or 'UNSET'}', not PASS/PASS_AFTER_FIX [EVAL-040]"))
        if role != "slop_removal":
            findings.append(("P1", loc,
                f"anti_slop.role is '{role or 'UNSET'}', not 'slop_removal' — the review's ROLE, not "
                "just its family, must be proven [EVAL-040]"))
        if relation != "same_family":
            findings.append(("P1", loc,
                "anti_slop.family_relation must be 'same_family' — a module anti-slop pass cannot be "
                "deferred to cross-family/final review debt [EVAL-040]"))
        if not rf or not bf:
            findings.append(("P1", loc,
                "anti_slop.reviewer_family/builder_family missing [EVAL-040]"))
        if not any(_str_field(aslop, k) for k in SELF_REVIEW_EVIDENCE_KEYS):
            findings.append(("P1", loc,
                "anti_slop has no evidence anchor (review_ref/receipt_ref/report_ref/findings_ref/"
                "review_agent/first_review_agent/review_id) — the review must be a NON-EMPTY scalar "
                "ref, re-readable, not only asserted [EVAL-040]"))
        rv, bd = _str_field(aslop, "reviewer"), _str_field(aslop, "builder")
        if not rv or not bd:
            findings.append(("P1", loc,
                "anti_slop.reviewer/builder identity missing — both must be present as scalar ids "
                "[EVAL-040]"))
        elif rv.casefold() == bd.casefold():
            findings.append(("P1", loc,
                "anti_slop.reviewer == builder — same-wave self-grading of the anti-slop pass "
                "[EVAL-040]"))

    # --- CONFORMANCE-TO-LOCK: money/login/data modules need EXTRACTED-actuals proof ---
    if risk_flags & CONFORMANCE_RISK:
        refs = ma.get("conformance_evidence_refs") or []
        if not isinstance(refs, list) or not [r for r in refs if str(r).strip()]:
            findings.append(("P1", loc,
                f"module '{module_id}' is risk {sorted(risk_flags & CONFORMANCE_RISK)} but carries no "
                "conformance_evidence_refs — a money/login/data module requires an EXTRACTED-actuals "
                "diff vs the locked implementation-contract manifest, not a free-text conformance "
                "answer (the non-visual anti-drift, GAP-1) [V1.10]"))

    # --- REGRESSION-SMOKE: shared-shell modules need a PASS smoke over accepted modules ---
    if touches_shared:
        reg = str(qc.get("regression", "") or "").strip().upper()
        if reg != "PASS":
            findings.append(("P1", loc,
                f"module '{module_id}' touches the shared shell/routes but quality_card.regression is "
                f"'{reg or 'UNSET'}', not PASS — a passing regression-smoke over the already-accepted "
                "modules is required before acceptance [V1.10]"))

    if not findings:
        print("PASS")
        print(f"  [INFO] module '{module_id}' quality bar met "
              f"(core four answered; risk {sorted(risk_flags)}; shared_shell={touches_shared})")
        return 0
    # A findings set with ONLY advisories (P2/P3 — e.g. the PB-PROP-003 §R5 legacy_criteria_ref
    # migration-debt advisory, only reachable now that --packet-dir threads through to
    # validate_live_slice_accept) is non-blocking — mirrors cmd_module_acceptance's and
    # cmd_verify_app's identical has_blocking() gate; module-quality must not turn a genuine
    # non-blocking carve-out into a hard FIX-FIRST [PB-PROP-003 CX-PB003-001 FIX-FIRST].
    rc = findings_report(findings)
    return rc if has_blocking(findings) else 0
