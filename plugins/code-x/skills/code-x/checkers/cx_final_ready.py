# cmd_final_ready: auto-assembles and checks the FINAL-READY-CERTIFICATE from existing evidence.
import hashlib
from pathlib import Path

from cx_common import findings_report, load_yaml, field_present, nested_get


def _sha12(path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def cmd_final_ready(args) -> int:
    """Auto-assemble and check the FINAL-READY-CERTIFICATE from existing evidence.
    READ/ASSEMBLE ONLY — never runs builds, routes actors, edits source, or creates missing evidence.
    """
    state_path = args.state
    card_path = args.card if hasattr(args, 'card') and args.card else None

    findings = []

    # Load state
    state, err = load_yaml(state_path)
    if err:
        print(f"FIX-FIRST\n  [P0] {state_path} — {err}")
        return 1

    if not isinstance(state, dict):
        print(f"FIX-FIRST\n  [P0] {state_path} — not a YAML mapping")
        return 1

    loc = state_path

    # --- protocol_stamp ---
    stamp = state.get("protocol_stamp", "")
    if str(stamp).strip() != "Code-X V1":
        findings.append(("P0", loc, f"protocol_stamp must be 'Code-X V1', got '{stamp}'"))

    # --- PROTOCOL_INCIDENT open forbids final-ready (BF-PROP-002) ---
    from cx_state import incident_open
    if incident_open(state) is not None:
        findings.append(("P0", loc,
            "PROTOCOL_INCIDENT open — going final-ready is forbidden until the "
            "current-stage checklist re-runs and the incident records cause + repair"))

    # --- open_findings must be all zero ---
    of = state.get("open_findings", {}) or {}
    counts = of.get("counts", {}) or {}
    items = of.get("items") or []
    if not isinstance(items, list):
        items = []

    for sev in ["p0", "p1", "p2", "p3"]:
        c = counts.get(sev, 0) or 0
        if c > 0:
            findings.append(("P0", loc,
                f"open_findings.counts.{sev}={c} — all findings must be zero for READY verdict"))

    if items:
        findings.append(("P0", loc,
            f"open_findings.items is not empty ({len(items)} items) — all must be closed"))

    # --- CROSS_FAMILY_RECHECK_PENDING blocks ---
    for item in items:
        if isinstance(item, dict):
            if "CROSS_FAMILY_RECHECK_PENDING" in str(item.get("finding", "")):
                if item.get("status", "OPEN") == "OPEN":
                    findings.append(("P0", loc,
                        f"CROSS_FAMILY_RECHECK_PENDING blocks final-ready: {item.get('id', '?')}"))

    # --- current_card must be null (no card in flight) ---
    cc = state.get("current_card")
    if cc is not None:
        findings.append(("P1", loc,
            f"current_card='{cc}' — must be null (no card in flight) before final-ready"))

    # --- stop_status must be NONE ---
    stop = state.get("stop_status", "")
    if str(stop) != "NONE":
        findings.append(("P0", loc,
            f"stop_status='{stop}' — must be NONE before final-ready"))

    # --- P1-02: ALL five gate fields must be explicit PASS (missing = NOT READY) ---
    GATE_FIELDS = [
        "module_capsules_current",
        "module_regressions_pass",
        "ceo_module_approvals_complete",
        "security_closeout",
        "recovery_proof",
    ]
    for gf in GATE_FIELDS:
        val = state.get(gf)
        if val is None:
            findings.append(("P0", loc,
                f"{gf} absent — must be explicit PASS in state for READY verdict (missing = NOT READY)"))
        elif str(val).upper() != "PASS":
            findings.append(("P0", loc,
                f"{gf}='{val}' — must be PASS (never default-pass); current value blocks READY"))

    # --- V1.10: final cross-family ship-gate — "last" can never become "never" ---
    # The final whole-build cross-family review (opposite family of the builder) is the ship
    # gate. Shipping without its bound receipt is forbidden. If the opposite family is out of
    # budget, that must be a typed protocol_deviation/STOP that saves state (BF-PROP-002) — never a
    # silently missing receipt that still ships.
    fcf = state.get("final_cross_family_receipt")
    if not isinstance(fcf, dict):
        findings.append(("P0", loc,
            "final_cross_family_receipt missing — the final whole-build cross-family review is the "
            "ship gate; shipping without it is forbidden ('last' can never become 'never'). A budget "
            "block must be a typed protocol_deviation/STOP that saves state, never a silent skip [V1.10]"))
    else:
        receipt_ref = str(fcf.get("receipt", "") or "").strip()
        receipt_hash = str(fcf.get("receipt_hash", "") or "").strip()
        reviewer = str(fcf.get("reviewer_family", "") or "").strip().lower()
        builder = str(fcf.get("builder_family", "") or "").strip().lower()
        verdict = str(fcf.get("verdict", "") or "").strip().upper()
        if not receipt_ref or not receipt_hash:
            findings.append(("P0", loc,
                "final_cross_family_receipt must carry a bound receipt + receipt_hash (the final "
                "cross-family review artifact) — an unbound claim is not the ship gate [V1.10]"))
        elif Path(receipt_ref).is_absolute() or ".." in Path(receipt_ref).parts:
            findings.append(("P0", loc,
                f"final_cross_family_receipt.receipt '{receipt_ref}' must be a repo-relative path "
                "(no absolute path / .. escape) — the ship gate reads only an in-tree receipt [V1.10]"))
        else:
            # The receipt is the wall: it must be an in-tree file, sha12-bound to receipt_hash, AND a
            # TYPED cross-family review artifact whose decisive fields MATCH the state claim — state
            # alone is not the gate (a bound blob of arbitrary bytes is not a review; GPT R2).
            base = Path(getattr(args, "repo_root", None)) if getattr(args, "repo_root", None) \
                else Path(state_path).resolve().parent
            base_resolved = base.resolve()
            receipt_path = base / receipt_ref
            resolved = receipt_path.resolve()  # follows symlinks; an escaping link resolves outside base
            if receipt_path.is_symlink() or not resolved.is_relative_to(base_resolved):
                findings.append(("P0", loc,
                    f"final_cross_family_receipt.receipt '{receipt_ref}' escapes the repo/state dir "
                    "(symlink or path traversal) — rejected [V1.10]"))
            else:
                actual = _sha12(str(receipt_path))
                if actual is None:
                    findings.append(("P0", loc,
                        f"final_cross_family_receipt.receipt missing/unreadable at '{receipt_path}' — the "
                        "final ship review artifact must exist; an unbound claim is not the ship gate [V1.10]"))
                elif actual != receipt_hash:
                    findings.append(("P0", loc,
                        f"final_cross_family_receipt.receipt_hash {receipt_hash} != the receipt file's sha12 "
                        f"{actual} — the recorded review is not bound to THIS artifact (fabricated/stale hash) [V1.10]"))
                else:
                    rdoc, _derr = load_yaml(str(receipt_path))
                    rblk = nested_get(rdoc, "final_cross_family_review") if isinstance(rdoc, dict) else None
                    if not isinstance(rblk, dict):
                        rblk = rdoc if isinstance(rdoc, dict) else None
                    if not isinstance(rblk, dict):
                        findings.append(("P0", loc,
                            "final_cross_family_receipt.receipt is not a typed cross-family review artifact "
                            "(expected YAML with builder_family/reviewer_family/verdict) — a bound blob of "
                            "arbitrary bytes is not a review [V1.10]"))
                    else:
                        r_rev = str(rblk.get("reviewer_family", "") or "").strip().lower()
                        r_bld = str(rblk.get("builder_family", "") or "").strip().lower()
                        r_ver = str(rblk.get("verdict", "") or "").strip().upper()
                        if (r_rev, r_bld, r_ver) != (reviewer, builder, verdict):
                            findings.append(("P0", loc,
                                f"final_cross_family_receipt fields in state (reviewer={reviewer}, "
                                f"builder={builder}, verdict={verdict}) do not match the receipt file "
                                f"(reviewer={r_rev}, builder={r_bld}, verdict={r_ver}) — the recorded "
                                "review is not the artifact [V1.10]"))
        # State-claim sanity (also the gate when no readable receipt above):
        if not reviewer or not builder:
            findings.append(("P0", loc,
                "final_cross_family_receipt must name reviewer_family + builder_family — the final "
                "ship review must be the OPPOSITE family of the builder (cross-family) [V1.10]"))
        elif reviewer == builder:
            findings.append(("P0", loc,
                f"final_cross_family_receipt reviewer_family '{reviewer}' == builder_family — the "
                "final ship review must be cross-family (opposite of the builder) [V1.10]"))
        # The verdict must be PRESENT and pass — a MISSING verdict is not a silent pass (GPT P0-4).
        if not verdict:
            findings.append(("P0", loc,
                "final_cross_family_receipt has no verdict — the final cross-family review must record "
                "an explicit PASS (or FIX_FIRST_RESOLVED); a missing verdict never ships [V1.10]"))
        elif verdict not in ("PASS", "FIX_FIRST_RESOLVED"):
            findings.append(("P0", loc,
                f"final_cross_family_receipt verdict '{verdict}' — the final cross-family review must "
                "be PASS (or FIX_FIRST_RESOLVED with all findings closed) before ship [V1.10]"))

    # --- Check if a card was supplied for extra evidence checks ---
    if card_path:
        card, cerr = load_yaml(card_path)
        if cerr:
            findings.append(("P1", card_path, f"could not load card for evidence check: {cerr}"))
        elif isinstance(card, dict):
            # Mirror cmd_evidence: resolve paths relative to card's own directory, not CWD
            card_dir = Path(card_path).resolve().parent
            ev_required = card.get("evidence_required") or []
            for ev_path in ev_required:
                p = Path(str(ev_path))
                if not p.is_absolute():
                    p = card_dir / p
                p = p.resolve()
                if not p.exists():
                    findings.append(("P1", card_path, f"evidence_required path missing: {ev_path}"))
                elif p.is_file() and p.stat().st_size == 0:
                    findings.append(("P1", card_path, f"evidence_required path empty: {ev_path}"))

    # --- G8: Built-App Audit required before final-ready (v1.12) ---
    # A whole-app audit (3 angles: requirements coverage / CEO asks / shipped reality) must have
    # run AND every finding must be fixed-or-CEO-deferred before final-ready is granted.
    # Path-safety mirrors acceptance_ref: repo-relative, non-symlink, inside repo.
    audit_blk = state.get("built_app_audit")
    if not isinstance(audit_blk, dict):
        findings.append(("P0", loc,
            "built_app_audit block missing from state — the Built-App Audit (see BUILT-APP-AUDIT.md) "
            "must run and all findings must be fixed-or-CEO-deferred before final-ready (v1.12)"))
    else:
        audit_status = str(audit_blk.get("status", "") or "").strip()
        if audit_status != "run":
            findings.append(("P0", loc,
                f"built_app_audit.status='{audit_status}' — must be 'run' before final-ready; "
                "the Built-App Audit has not completed (BUILT-APP-AUDIT.md, v1.12)"))
        dispositioned = audit_blk.get("findings_dispositioned")
        if dispositioned is not True:
            findings.append(("P0", loc,
                f"built_app_audit.findings_dispositioned='{dispositioned}' — must be true; "
                "every audit finding must be fixed or explicitly CEO-deferred before final-ready (v1.12)"))
        audit_ref = str(audit_blk.get("report_ref", "") or "").strip()
        if not audit_ref:
            findings.append(("P0", loc,
                "built_app_audit.report_ref missing — must be a repo-relative, non-symlink path "
                "to the audit report directory (v1.12)"))
        elif Path(audit_ref).is_absolute() or ".." in Path(audit_ref).parts:
            findings.append(("P0", loc,
                f"built_app_audit.report_ref '{audit_ref}' must be a repo-relative path "
                "(no absolute path / .. escape) — mirrors acceptance_ref path-safety (v1.12)"))
        else:
            # Resolve against repo_root or state dir and reject symlinks / escapes
            base = Path(getattr(args, "repo_root", None)) if getattr(args, "repo_root", None) \
                else Path(state_path).resolve().parent
            base_resolved = base.resolve()
            audit_path = base / audit_ref
            if audit_path.is_symlink() or not audit_path.resolve().is_relative_to(base_resolved):
                findings.append(("P0", loc,
                    f"built_app_audit.report_ref '{audit_ref}' escapes the repo/state dir "
                    "(symlink or path traversal) — rejected (v1.12)"))
            elif not audit_path.exists():
                # The ceremonial-gate hole: a report_ref pointing at a non-existent dir must BLOCK
                # (state alone is not the gate — the audit report must actually exist) [v1.12 FIX].
                findings.append(("P0", loc,
                    f"built_app_audit.report_ref '{audit_ref}' does not exist — the Built-App Audit "
                    "report directory must actually exist before final-ready (v1.12)"))
            elif not audit_path.is_dir():
                findings.append(("P0", loc,
                    f"built_app_audit.report_ref '{audit_ref}' is not a directory — report_ref must "
                    "point at the audit report DIRECTORY (BUILT-APP-AUDIT.md Output) (v1.12)"))
            elif not (audit_path / "AUDIT-SUMMARY.md").is_file():
                # LIGHT only: existence of the bottom-line summary file. No parsing, no traceability
                # engine — just that a real report (with its summary) is present (v1.12 FIX).
                findings.append(("P0", loc,
                    f"built_app_audit.report_ref '{audit_ref}' has no AUDIT-SUMMARY.md — the audit "
                    "report directory must contain the bottom-line summary file (v1.12)"))

    # --- v1.22 Audit stage (A-PROP-001 + PBAF-PROP-001): final-ready must not be reachable
    # while skipping the 4th stage (GATES.md "a build cannot reach final-ready while skipping
    # Audit"). Additive to (not a replacement for) built_app_audit above — that block is the
    # angle-A/B/C engine record; this block is the FINAL Audit-stage receipt (angle D + the SOP
    # hard rules + the review ladder), judged by the SAME collect_audit_findings() the `cx check
    # audit` CLI uses (F1, v1.22 self-review — no divergent second copy of the judgment logic).
    # Path-safety mirrors built_app_audit.report_ref exactly (repo-relative, non-symlink, in-tree).
    audit_stage_blk = state.get("audit_stage_final")
    if not isinstance(audit_stage_blk, dict):
        findings.append(("P1", loc,
            "audit_stage_final block missing from state — a valid FINAL Audit-stage receipt "
            "(cx check audit --final) must exist and pass before final-ready (A-PROP-001; "
            "GATES.md: 'a build cannot reach final-ready while skipping Audit') "
            "[AUDIT-STAGE-FINAL-READY-CHAIN]"))
    else:
        as_ref = str(audit_stage_blk.get("report_ref", "") or "").strip()
        if not as_ref:
            findings.append(("P1", loc,
                "audit_stage_final.report_ref missing — must be a repo-relative, non-symlink path "
                "to the FINAL Audit-stage report directory [AUDIT-STAGE-FINAL-READY-CHAIN]"))
        elif Path(as_ref).is_absolute() or ".." in Path(as_ref).parts:
            findings.append(("P1", loc,
                f"audit_stage_final.report_ref '{as_ref}' must be a repo-relative path "
                "(no absolute path / .. escape) — mirrors built_app_audit.report_ref path-safety "
                "[AUDIT-STAGE-FINAL-READY-CHAIN]"))
        else:
            base = Path(getattr(args, "repo_root", None)) if getattr(args, "repo_root", None) \
                else Path(state_path).resolve().parent
            base_resolved = base.resolve()
            as_path = base / as_ref
            if as_path.is_symlink() or not as_path.resolve().is_relative_to(base_resolved):
                findings.append(("P1", loc,
                    f"audit_stage_final.report_ref '{as_ref}' escapes the repo/state dir "
                    "(symlink or path traversal) — rejected [AUDIT-STAGE-FINAL-READY-CHAIN]"))
            elif not as_path.is_dir():
                findings.append(("P1", loc,
                    f"audit_stage_final.report_ref '{as_ref}' does not exist or is not a directory "
                    "— the FINAL Audit-stage report must actually exist [AUDIT-STAGE-FINAL-READY-CHAIN]"))
            else:
                from cx_audit import collect_audit_findings
                audit_findings = collect_audit_findings(
                    as_path, final=True, state_path=state_path, repo_root=base)
                if audit_findings:
                    worst = next((s for s, _, _ in audit_findings if s == "P1"), audit_findings[0][0])
                    reasons = "; ".join(m for _, _, m in audit_findings[:3])
                    findings.append((worst, str(as_path),
                        f"AUDIT-STAGE-FINAL-READY-CHAIN: the FINAL Audit-stage receipt at "
                        f"'{as_ref}' does not pass ({len(audit_findings)} finding(s)): {reasons}"))

    # --- G8: dependency scan re-runs pre-ship (B-PROP-006 / GPT review F5) ---
    # READ/ASSEMBLE ONLY: final-ready requires the dependency-scan receipt to be PRESENT at ship when
    # the repo has package-manager manifests (the scan itself runs per-card at build-turn); a code
    # project may not ship without a current supply-chain scan receipt.
    repo_root = getattr(args, "repo_root", None)
    if repo_root:
        from cx_dep_scan import discover_manifests
        dep_ref = str(state.get("dependency_scan_receipt_ref", "") or "").strip()
        manifests = discover_manifests(Path(repo_root))
        if manifests and not dep_ref:
            findings.append(("P1", loc,
                f"dependency manifests exist under the repo ({manifests[:3]}) but state declares no "
                "dependency_scan_receipt_ref — G8 re-scans dependencies pre-ship; a code project may not "
                "ship without a current supply-chain scan receipt (B-PROP-006 / GPT review F5)"))
        elif dep_ref:
            if Path(dep_ref).is_absolute() or ".." in Path(dep_ref).parts:
                findings.append(("P1", loc,
                    f"dependency_scan_receipt_ref '{dep_ref}' must be a repo-relative path"))
            elif not (Path(repo_root) / dep_ref).is_file():
                findings.append(("P1", loc,
                    f"dependency_scan_receipt_ref '{dep_ref}' does not exist under the repo — the pre-ship "
                    "dependency scan receipt must be present (B-PROP-006 / GPT review F5)"))

    # --- Assemble certificate summary (if PASS) ---
    if not findings:
        print("PASS")
        cert = {
            "final_ready_certificate": {
                "project": state.get("project", ""),
                "protocol": "Code-X V1",
                "last_commit": state.get("last_commit", ""),
                "open_findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
                "verdict": "READY"
            }
        }
        print("  [ASSEMBLED]")
        for k, v in cert["final_ready_certificate"].items():
            print(f"    {k}: {v}")
        return 0

    return findings_report(findings)
