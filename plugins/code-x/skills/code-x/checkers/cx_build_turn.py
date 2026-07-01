# cmd_build_turn: the every-card aggregate gate (B-PROP-002 build-session rail).
#
#   cx check build-turn <card> --state <CODE-X-STATE.yaml> --repo-root <dir> [--diff <path>]
#
# One PASS line per sub-check; ANY fail blocks the turn:
#   card · scope · stale-allowed-files · evidence · consistency --strict ·
#   project tests · CodeRabbit receipt (where the card requires it)
#
# CHECK/RECEIPT-ONLY, never a runner (GPT P1-018-02, the no-Level-C-runner decision):
# it verifies receipts exist or runs ONLY deterministic commands explicitly named by
# card/state — it never decides tests, routes actors, calls model review, creates
# evidence, or edits source. A missing project test command = FAIL "card incomplete",
# never a guess. Without --diff, the touched-file list is derived deterministically
# from `git diff --name-only HEAD` + untracked files under --repo-root.
import glob as globmod
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from cx_common import findings_report, load_yaml, field_present, safe_repo_ref
from cx_dep_scan import discover_manifests

THIS_DIR = Path(__file__).resolve().parent
CX = str(THIS_DIR / "cx")


def _run_cx(*cx_args) -> tuple[int, str]:
    result = subprocess.run([sys.executable, CX] + list(cx_args),
                            capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def _sub(label: str, rc: int, out: str, findings: list) -> None:
    # FIX 4 (build-turn mis-tier — SHARED aggregator, NOT render-local): EVERY sub-check that fails
    # surfaces as ("P1", ...) at the build-turn layer regardless of the child's true max severity, so
    # a render-fidelity P0 (forged/stale/unpinned receipt) is LABELLED P1 here. This is a pre-existing
    # protocol-wide pattern affecting all sub-checks (card, scope, evidence, dep-scan, ...), not unique
    # to render — per the fold instruction it is NOT refactored in this xfam fold (a shared-path change
    # is a protocol-wide call, out of scope). It does NOT let a P0 slip: any failed sub-check (rc!=0)
    # adds a finding, so findings_report returns non-zero and the turn HARD-BLOCKS — the defect is the
    # severity LABEL, not a silent pass. The render check itself still emits the true [P0] in its own
    # output (preserved in `tail`).
    if rc == 0:
        print(f"  [INFO] PASS {label}")
    else:
        tail = " | ".join(out.strip().splitlines()[1:4]) or out.strip()[:200]
        findings.append(("P1", label, f"sub-check failed: {tail}"))


def _derived_file_list(repo_root: str) -> tuple[list[str] | None, str]:
    """Deterministic touched-file list: tracked changes vs HEAD + untracked files."""
    files = []
    for cmd in (["git", "-C", repo_root, "diff", "--name-only", "HEAD"],
                ["git", "-C", repo_root, "ls-files", "--others", "--exclude-standard"]):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return None, result.stderr.strip()
        files.extend(line for line in result.stdout.splitlines() if line.strip())
    return files, ""


def cmd_build_turn(args) -> int:
    card_path = args.card
    state_path = args.state
    repo_root = args.repo_root

    card, err = load_yaml(card_path)
    if err:
        print(f"FIX-FIRST\n  [P0] {card_path} — {err}")
        return 1
    state, serr = load_yaml(state_path)
    if serr or not isinstance(state, dict):
        print(f"FIX-FIRST\n  [P0] {state_path} — {serr or 'not a YAML mapping'}")
        return 1

    findings = []

    # 1. card (incident gating included via --state)
    rc, out = _run_cx("check", "card", card_path, "--state", state_path)
    _sub("card", rc, out, findings)

    # 1b. module-start — the V1.10 ORDER WALL, wired into the every-card rail so the module
    # gate family bites on the normal build path (not opt-in / out-of-band; GPT P0-2). A
    # module-advancing card needs the frozen module_registry (ref'd in state) and every prior
    # required module validly accepted. No registry ref on a module build = fail-closed.
    card_mode = str(card.get("mode", "") or "").strip()
    if card_mode in ("MODULE_BUILD", "MODE_A_UI"):
        reg_ref = str(state.get("module_registry_ref", "") or "").strip()
        pkt_ref = str(state.get("packet_dir", "") or "").strip()
        if not reg_ref:
            findings.append(("P1", "module-start",
                f"card is a module-advancing build (mode {card_mode}) but state has no "
                "module_registry_ref — the order wall cannot run; a module build needs the frozen "
                "registry ref in state (fail-closed) [V1.10]"))
        elif not pkt_ref:
            # V1.10 R4: the order wall content-binds the card to the frozen packet (re-hash) — it
            # cannot run without the packet dir, so a missing packet_dir is fail-closed, not skipped.
            findings.append(("P1", "module-start",
                f"card is a module-advancing build (mode {card_mode}) but state has no packet_dir — the "
                "order wall content-binds the card to the frozen packet (re-hashes it) and cannot run "
                "without it; a module build needs the frozen packet_dir in state (fail-closed) [V1.10]"))
        elif (Path(reg_ref).is_absolute() or ".." in Path(reg_ref).parts
              or Path(pkt_ref).is_absolute() or ".." in Path(pkt_ref).parts):
            findings.append(("P1", "module-start",
                f"state.module_registry_ref '{reg_ref}' / packet_dir '{pkt_ref}' must be repo-relative "
                "paths (no absolute path / .. escape) — the order wall reads only frozen artifacts "
                "committed in the repo [V1.10]"))
        else:
            reg_path = str(Path(repo_root) / reg_ref)
            pkt_path = str(Path(repo_root) / pkt_ref)
            rc, out = _run_cx("check", "module-start", card_path, "--packet-dir", pkt_path,
                              "--state", state_path, "--registry", reg_path, "--repo-root", repo_root)
            _sub("module-start", rc, out, findings)
    else:
        print("  [INFO] NOT_APPLICABLE module-start (non-module-advancing card)")

    # 2. scope — explicit --diff, else the derived deterministic file list
    diff_path = getattr(args, "diff", None)
    tmp = None
    if not diff_path:
        files, derr = _derived_file_list(repo_root)
        if files is None:
            findings.append(("P1", "scope", f"cannot derive touched files: {derr}"))
        else:
            tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
            tmp.write("\n".join(files) + ("\n" if files else ""))
            tmp.close()
            diff_path = tmp.name
    if diff_path:
        rc, out = _run_cx("check", "scope", card_path, diff_path)
        _sub("scope", rc, out, findings)

    # 3. stale-allowed-files: every allowed path exists under repo-root, matches as a
    #    glob, or is declared in the card's new_outputs list (a file the card creates).
    new_outputs = {str(x) for x in (card.get("new_outputs") or [])}
    root = Path(repo_root)
    stale = []
    for entry in (card.get("allowed_files") or []):
        entry = str(entry)
        if entry in new_outputs:
            continue
        p = root / entry
        if p.exists():
            continue
        if globmod.glob(str(root / entry)):
            continue
        stale.append(entry)
    if stale:
        findings.append(("P1", "stale-allowed-files",
            f"allowed_files entries neither exist under {repo_root} nor are declared "
            f"in new_outputs: {stale} — stale scope is how a card edits ghosts"))
    else:
        print("  [INFO] PASS stale-allowed-files")

    # 4. evidence
    ev_args = ["check", "evidence", card_path]
    if getattr(args, "diff", None):
        ev_args += ["--diff", args.diff]
    rc, out = _run_cx(*ev_args)
    _sub("evidence", rc, out, findings)

    # 5. consistency --strict (protocol canon must hold at every turn)
    rc, out = _run_cx("check", "consistency", "--strict")
    _sub("consistency --strict", rc, out, findings)

    # 6. project tests — the deterministic command EXPLICITLY named by card/state.
    test_cmd = card.get("test_command") or state.get("project_test_command")
    if not test_cmd:
        findings.append(("P1", "project-tests",
            "card incomplete — no project test command named (card.test_command or "
            "state.project_test_command); build-turn never guesses a test command"))
    else:
        # ONE plain argv command, parsed without a shell (no pipes/&&/redirects —
        # shell metacharacters in a frozen card are a smell, not a feature).
        result = subprocess.run(shlex.split(str(test_cmd)), cwd=repo_root,
                                capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  [INFO] PASS project-tests ({test_cmd})")
        else:
            tail = " | ".join((result.stdout + result.stderr).strip().splitlines()[-3:])
            findings.append(("P1", "project-tests",
                f"named test command failed (rc={result.returncode}): {tail[:300]}"))

    # 7. CodeRabbit receipt — TYPED + egress-bound, verified when required, never invoked (BF-PROP-005,
    #    GPT built-code review F1). The receipt must be a typed coderabbit_review artifact whose
    #    egress_receipt_ref resolves to a valid scrub/carve-out receipt (scrub-before-egress precedes
    #    CodeRabbit). PROP-042 / v1.21 hardens the planning-stage gap:
    #    CodeRabbit is MANDATORY on every MODULE_BUILD / MODE_A_UI code-diff card, even if state
    #    forgot to declare xfam_capability.
    cr = card.get("coderabbit") or {}
    code_diff_review = card_mode in ("MODULE_BUILD", "MODE_A_UI")
    if isinstance(cr, dict) and str(cr.get("required", "no")).lower() in ("yes", "true"):
        receipt = cr.get("receipt")
        # B-PROP-011: the receipt ref is card-authored — path-safety it (absolute / '..' / symlink /
        # resolved-escape) BEFORE the .is_file() read, or a symlink/escaping ref reads arbitrary
        # external bytes as a "review" (this read previously carried NO guard at all — the worst
        # of the build-turn root/ref reads). Shared helper, mirrors the Andon wall acceptance_ref.
        safe_receipt, crerr = safe_repo_ref(str(receipt), root) if receipt else (None, None)
        receipt_path = safe_receipt
        if crerr:
            findings.append(("P1", "coderabbit-receipt",
                f"card coderabbit.receipt '{receipt}' {crerr}"))
        elif not receipt or not receipt_path.is_file():
            findings.append(("P1", "coderabbit-receipt",
                f"card requires a CodeRabbit review but receipt '{receipt}' is missing — "
                "build-turn verifies receipts, it never invokes the review"))
        else:
            rdoc, _rerr = load_yaml(str(receipt_path))
            cblk = rdoc.get("coderabbit_review") if isinstance(rdoc, dict) else None
            if not isinstance(cblk, dict):
                findings.append(("P1", "coderabbit-receipt",
                    "CodeRabbit receipt is not a typed coderabbit_review artifact {commit, diff_hash, "
                    "tool_version, findings_hash, egress_receipt_ref, produced_at} — an arbitrary file is "
                    "not a review (BF-PROP-005 / GPT #8)"))
            else:
                miss = [k for k in ("commit", "diff_hash", "tool_version", "findings_hash",
                                    "egress_receipt_ref", "produced_at") if not field_present(cblk, k)]
                if miss:
                    findings.append(("P1", "coderabbit-receipt",
                        f"CodeRabbit receipt missing {miss} — a non-deterministic CLI's receipt must pin "
                        "the commit, diff hash, tool version, findings hash, egress receipt, and time "
                        "(BF-PROP-005 / GPT #8)"))
                else:
                    eref = str(cblk.get("egress_receipt_ref"))
                    safe_eref, eerr = safe_repo_ref(eref, root)
                    if eerr:
                        findings.append(("P1", "coderabbit-receipt",
                            f"CodeRabbit receipt egress_receipt_ref '{eref}' {eerr}"))
                    else:
                        edoc, _eerr = load_yaml(str(safe_eref)) if safe_eref.is_file() else (None, "x")
                        if not (isinstance(edoc, dict) and (isinstance(edoc.get("egress_scrub"), dict)
                                or isinstance(edoc.get("sensitive_code_carveout"), dict))):
                            findings.append(("P1", "coderabbit-receipt",
                                "CodeRabbit receipt egress_receipt_ref does not resolve to a valid "
                                "egress_scrub / sensitive_code_carveout receipt — scrub-before-egress must "
                                "precede CodeRabbit (BF-PROP-005 / GPT #1)"))
                        else:
                            print("  [INFO] PASS coderabbit-receipt (typed + egress-bound)")
    elif code_diff_review:
        findings.append(("P1", "coderabbit-receipt",
            "card is a code-diff module review but the card requires no CodeRabbit — CodeRabbit is "
            "MANDATORY before self/cross review on every MODULE_BUILD / MODE_A_UI code diff; it "
            "unblocks the build but never satisfies xfam (PROP-042 / v1.21)"))
    else:
        print("  [INFO] NOT_APPLICABLE coderabbit-receipt")

    # 8. dependency scan — supply-chain gate (B-PROP-006). Validate the declared receipt
    #    (which re-checks each lockfile hash against the LIVE tree, catching a lockfile that
    #    drifted after the G7 scan — GPT #11). If dependency manifests exist under the repo
    #    but no receipt is declared, fail closed — a package-manager root must be scanned.
    dep_ref = str(state.get("dependency_scan_receipt_ref", "") or "").strip()
    if dep_ref:
        # B-PROP-011: shared path-safety — absolute/'..' WAS guarded here, but a symlink / resolved-escape
        # dep_ref slipped through and let the rail scan an external receipt as in-repo. Full class now.
        safe_dep, derr = safe_repo_ref(dep_ref, root)
        if derr:
            findings.append(("P1", "dep-scan",
                f"state.dependency_scan_receipt_ref '{dep_ref}' {derr}"))
        else:
            rc, out = _run_cx("check", "dep-scan", str(safe_dep), "--repo-root", repo_root)
            _sub("dep-scan", rc, out, findings)
    else:
        found = discover_manifests(root)
        if found:
            findings.append(("P1", "dep-scan",
                f"dependency manifests found under the repo ({found[:3]}) but state declares no "
                "dependency_scan_receipt_ref — a package-manager root must be scanned before build "
                "(fail-closed, B-PROP-006)"))
        else:
            print("  [INFO] NOT_APPLICABLE dep-scan (no dependency manifests)")

    # 9. render-fidelity — the in-loop RENDERED-fidelity gate (B-PROP-009). A UI build card that
    #    declares a render bundle (card.render_bundle) must pass cx check render-fidelity BEFORE
    #    the turn passes / before self-review (Layer 1 P0 blocks the card; P1 = the layout defect).
    #    A card with no render_bundle is NOT_APPLICABLE (non-UI cards / functions-only modules).
    rb_ref = str(card.get("render_bundle", "") or "").strip()
    if rb_ref:
        # B-PROP-011: shared path-safety — absolute/'..' WAS guarded here, but a symlink / resolved-escape
        # render_bundle slipped through. Full class now (the rail reads only an in-repo bundle).
        safe_rb, rberr = safe_repo_ref(rb_ref, root)
        if rberr:
            findings.append(("P1", "render-fidelity",
                f"card.render_bundle '{rb_ref}' {rberr}"))
        else:
            # FIX 1 (stale render): supply the AUTHORITATIVE live repo HEAD from --repo-root (the
            # same git rev-parse HEAD source cx check boot binds) — the render check no longer trusts
            # the bundle's own current_repo_head. Same head source the rail already uses elsewhere.
            head = subprocess.run(["git", "-C", repo_root, "rev-parse", "HEAD"],
                                  capture_output=True, text=True)
            if head.returncode != 0:
                findings.append(("P1", "render-fidelity",
                    f"cannot read live repo HEAD for render-fidelity freshness: {head.stderr.strip()}"))
            else:
                rc, out = _run_cx("check", "render-fidelity", str(safe_rb),
                                  "--repo-head", head.stdout.strip())
                _sub("render-fidelity", rc, out, findings)
    else:
        print("  [INFO] NOT_APPLICABLE render-fidelity (card declares no render_bundle)")

    # 10. structure — the STRUCTURE LOCK (F-PROP-001 Lever A). Every mode: FIX card must not restructure
    #     the file tree outside its allowed_files vs the frozen structure_lock. Rail-wired here (not
    #     opt-in, xfam P1-1) so the preserve-the-architecture gate bites on the normal fix path; a
    #     mode: FIX card with no structure_lock_ref fails closed inside cx check structure. The RAIL
    #     being wired is itself a contract clause (FIX-STAGE-STRUCT-RAIL) — a bad structure_lock here
    #     surfaces as a build-turn sub-check failure. Non-FIX cards = NOT_APPLICABLE.
    if card_mode == "FIX":
        rc, out = _run_cx("check", "structure", card_path, "--repo-root", repo_root)
        _sub("structure", rc, out, findings)
    else:
        print("  [INFO] NOT_APPLICABLE structure (non-FIX card)")

    # 11. verify-app — the runtime-behavior gate (B-PROP-010). The MECHANICAL guarantee ("every live_slice,
    #     once, before the CEO live-drive") is the module-acceptance PRECONDITION (validate_verify_app
    #     inside validate_live_slice_accept) — NOT this step. This build-turn step is an OPT-IN EARLY-CATCH:
    #     a card declaring `verify_app_ref` (mirror of render_bundle) has its verify_app receipt validated
    #     HERE so a malformed/forged/failing receipt is caught at slice completion, before the screen is
    #     surfaced, not only later at the wall. HONEST SCOPE (B-PROP-010 xfam, GPT-5.5): a slice-completion
    #     card that OMITS verify_app_ref is NOT_APPLICABLE here — the wall still catches it, so this step
    #     does not (and is not claimed to) mechanically force the check; it is the convenience early-catch.
    va_ref = str(card.get("verify_app_ref", "") or "").strip()
    if va_ref:
        # B-PROP-010 xfam landed the absolute/'..'/symlink/resolved-escape guard inline here; B-PROP-011
        # moves it onto the shared safe_repo_ref helper so all build-turn root/ref reads carry the
        # identical class (mirrors the Andon wall acceptance_ref path-safety).
        safe_va, vaerr = safe_repo_ref(va_ref, root)
        if vaerr:
            findings.append(("P1", "verify-app",
                f"card.verify_app_ref '{va_ref}' {vaerr}"))
        else:
            rc, out = _run_cx("check", "verify-app", "--acceptance", str(safe_va))
            _sub("verify-app", rc, out, findings)
    else:
        print("  [INFO] NOT_APPLICABLE verify-app (card declares no verify_app_ref)")

    # 12. whole-packet cross-family review — the G7 build-authorization INTEGRATION gate (P-PROP-006).
    #     A module-advancing card means building is underway, so the WHOLE frozen packet must already
    #     have passed a CURRENT, PASS, OPPOSITE-family integration review (the cross-document coherence
    #     pass the per-card audit + the deterministic checker structurally cannot provide — the real-project
    #     TRD-vs-stack-lock drift class). Fail-closed: a module build with no current receipt blocks the
    #     entire build (mirrors module-start's fail-closed on a missing registry). The standalone check
    #     does the path-safety + sha + opposite-family + verdict + packet-hash-currency validation; the
    #     packet dir is the same frozen packet_dir the order wall (step 1b) re-hashes.
    if card_mode in ("MODULE_BUILD", "MODE_A_UI"):
        pkt_ref = str(state.get("packet_dir", "") or "").strip()
        if not pkt_ref:
            findings.append(("P1", "whole-packet-review",
                "module-advancing build but state has no packet_dir — the whole-packet integration review "
                "(P-PROP-006) cannot recompute the frozen-packet hash to prove the review is current; "
                "fail-closed"))
        elif Path(pkt_ref).is_absolute() or ".." in Path(pkt_ref).parts:
            findings.append(("P1", "whole-packet-review",
                f"state.packet_dir '{pkt_ref}' must be a repo-relative path (no absolute / .. escape) — "
                "the whole-packet integration gate reads only the frozen packet committed in the repo "
                "(P-PROP-006)"))
        else:
            pkt_path = str(Path(repo_root) / pkt_ref)
            rc, out = _run_cx("check", "whole-packet-review", "--state", state_path,
                              "--packet-dir", pkt_path, "--repo-root", repo_root)
            _sub("whole-packet-review", rc, out, findings)
    else:
        print("  [INFO] NOT_APPLICABLE whole-packet-review (non-module-advancing card)")

    return findings_report(findings)
