# cmd_module_quality: the per-module QUALITY BAR (V1.10 module_acceptance gate family).
#
# Reads a MODULE-ACCEPTANCE receipt + the frozen module_registry and enforces the professional
# quality bar the Andon receipt asserts — depth by the module's risk:
#   - QUALITY CARD (always): the receipt carries a quality_card answering the core four
#     (security · efficient · regression · tests) + a conformance answer — else P1.
#   - CONFORMANCE-TO-LOCK: a money/login/data module REQUIRES extracted-actuals conformance
#     evidence (conformance_evidence_refs non-empty) vs the locked IMPLEMENTATION-CONTRACT
#     manifest — a free-text answer alone is not proof (P1; the non-visual anti-drift, GAP-1).
#   - REGRESSION-SMOKE: a module touching the shared shell/routes must show a PASS regression-smoke
#     over the already-accepted modules (quality_card.regression == PASS) — else P1.
#
#   cx check module-quality --acceptance <MODULE-ACCEPTANCE.yaml> --registry <MODULE-REGISTRY.yaml> --module-id <id>
#
# READ-ONLY. (design-fidelity BLOCKS the VISUAL half; this blocks the architecture/logic/data half.)
from cx_common import findings_report, load_yaml, nested_get, field_present

CONFORMANCE_RISK = {"money", "login", "data"}
CORE_FOUR = ("security", "efficient", "regression", "tests")


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
    ma = nested_get(receipt, "module_acceptance")
    if not isinstance(ma, dict):
        ma = receipt
    loc = acceptance_path

    if not module_id:
        module_id = str(ma.get("module_id", "") or "").strip()

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
    return findings_report(findings)
