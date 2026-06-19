# cmd_build_turn: the every-card aggregate gate (PROP-018 build-session rail).
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

from cx_common import findings_report, load_yaml, field_present
from cx_dep_scan import discover_manifests

THIS_DIR = Path(__file__).resolve().parent
CX = str(THIS_DIR / "cx")


def _run_cx(*cx_args) -> tuple[int, str]:
    result = subprocess.run([sys.executable, CX] + list(cx_args),
                            capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def _sub(label: str, rc: int, out: str, findings: list) -> None:
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

    # 7. CodeRabbit receipt — TYPED + egress-bound, verified when required, never invoked (PROP-026,
    #    GPT built-code review F1). The receipt must be a typed coderabbit_review artifact whose
    #    egress_receipt_ref resolves to a valid scrub/carve-out receipt (scrub-before-egress precedes
    #    CodeRabbit). CodeRabbit is MANDATORY on a code-diff module review once the project declares the
    #    v1.11 review model (state.review_boundary.xfam_capability) — it cannot be silently skipped.
    cr = card.get("coderabbit") or {}
    code_diff_review = card_mode in ("MODULE_BUILD", "MODE_A_UI")
    xfam_declared = bool(str((state.get("review_boundary") or {}).get("xfam_capability", "")).strip())
    if isinstance(cr, dict) and str(cr.get("required", "no")).lower() in ("yes", "true"):
        receipt = cr.get("receipt")
        receipt_path = (root / str(receipt)) if receipt else None
        if not receipt or not receipt_path.is_file():
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
                    "not a review (PROP-026 / GPT #8)"))
            else:
                miss = [k for k in ("commit", "diff_hash", "tool_version", "findings_hash",
                                    "egress_receipt_ref", "produced_at") if not field_present(cblk, k)]
                if miss:
                    findings.append(("P1", "coderabbit-receipt",
                        f"CodeRabbit receipt missing {miss} — a non-deterministic CLI's receipt must pin "
                        "the commit, diff hash, tool version, findings hash, egress receipt, and time "
                        "(PROP-026 / GPT #8)"))
                else:
                    eref = str(cblk.get("egress_receipt_ref"))
                    if Path(eref).is_absolute() or ".." in Path(eref).parts:
                        findings.append(("P1", "coderabbit-receipt",
                            f"CodeRabbit receipt egress_receipt_ref '{eref}' must be a repo-relative path"))
                    else:
                        edoc, _eerr = load_yaml(str(root / eref)) if (root / eref).is_file() else (None, "x")
                        if not (isinstance(edoc, dict) and (isinstance(edoc.get("egress_scrub"), dict)
                                or isinstance(edoc.get("sensitive_code_carveout"), dict))):
                            findings.append(("P1", "coderabbit-receipt",
                                "CodeRabbit receipt egress_receipt_ref does not resolve to a valid "
                                "egress_scrub / sensitive_code_carveout receipt — scrub-before-egress must "
                                "precede CodeRabbit (PROP-026 / GPT #1)"))
                        else:
                            print("  [INFO] PASS coderabbit-receipt (typed + egress-bound)")
    elif code_diff_review and xfam_declared:
        findings.append(("P1", "coderabbit-receipt",
            "card is a code-diff module review and state declares xfam_capability (the v1.11 review "
            "model) but the card requires no CodeRabbit — CodeRabbit is MANDATORY before cross-family on "
            "a code-diff review; it unblocks the build but never satisfies xfam (PROP-026)"))
    else:
        print("  [INFO] NOT_APPLICABLE coderabbit-receipt")

    # 8. dependency scan — supply-chain gate (PROP-027). Validate the declared receipt
    #    (which re-checks each lockfile hash against the LIVE tree, catching a lockfile that
    #    drifted after the G7 scan — GPT #11). If dependency manifests exist under the repo
    #    but no receipt is declared, fail closed — a package-manager root must be scanned.
    dep_ref = str(state.get("dependency_scan_receipt_ref", "") or "").strip()
    if dep_ref:
        if Path(dep_ref).is_absolute() or ".." in Path(dep_ref).parts:
            findings.append(("P1", "dep-scan",
                f"state.dependency_scan_receipt_ref '{dep_ref}' must be a repo-relative path "
                "(no absolute path / .. escape)"))
        else:
            rc, out = _run_cx("check", "dep-scan", str(root / dep_ref), "--repo-root", repo_root)
            _sub("dep-scan", rc, out, findings)
    else:
        found = discover_manifests(root)
        if found:
            findings.append(("P1", "dep-scan",
                f"dependency manifests found under the repo ({found[:3]}) but state declares no "
                "dependency_scan_receipt_ref — a package-manager root must be scanned before build "
                "(fail-closed, PROP-027)"))
        else:
            print("  [INFO] NOT_APPLICABLE dep-scan (no dependency manifests)")

    return findings_report(findings)
