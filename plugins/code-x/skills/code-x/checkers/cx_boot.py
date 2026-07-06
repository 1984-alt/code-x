# cmd_boot: GENERATES the session boot receipt (B-PROP-002 build-session rail).
#
# The receipt is machine-authored — cx hashes the canonical files itself, runs the
# session-start state check, and records the latest handoff. The actor only
# REFERENCES the generated receipt in state (session_start.protocol_boot_ack);
# the model never authors hashes (kills ack theater — GPT P1-018-01).
#
#   cx check boot --state <CODE-X-STATE.yaml> --repo-root <dir> [--out <receipt>] \
#                 [--handoffs-dir <dir>]
#
# Receipt default: protocol-boot-receipt.yaml next to the state file.
# Exit 0 = state check PASS + receipt written; 1 = state check failed (receipt is
# still written, recording the failure — an ack of a failed receipt is rejected by
# cx check state).
from datetime import datetime, timezone
from pathlib import Path

import yaml

import subprocess

from cx_common import profiles_sha12
from cx_state import (collect_state_findings, state_sha12_without_boot_ack,
                      CANON_ROOT, BOOT_CANON_FILES)


def _latest_handoff(handoffs_dir: Path) -> str:
    """Latest handoff = lexically last *.md (dated filenames sort correctly)."""
    if not handoffs_dir.is_dir():
        return "NONE"
    candidates = sorted(p.name for p in handoffs_dir.glob("*.md"))
    return str(handoffs_dir / candidates[-1]) if candidates else "NONE"


def cmd_boot(args) -> int:
    state_path = args.state
    repo_root = args.repo_root
    out_path = Path(args.out) if getattr(args, "out", None) else (
        Path(state_path).resolve().parent / "protocol-boot-receipt.yaml")
    handoffs_dir = Path(args.handoffs_dir) if getattr(args, "handoffs_dir", None) else (
        Path(repo_root) / "handoffs")

    # 1. Hash the canon — cx authors these, never the model.
    canon = []
    canon_missing = []
    for name in BOOT_CANON_FILES:
        sha = profiles_sha12(str(CANON_ROOT / name))
        if sha is None:
            canon_missing.append(name)
        canon.append({"path": name, "sha12": sha or "UNREADABLE"})

    # 2. Run the session-start state check (minus the boot-ack clause this receipt
    #    is about to make satisfiable — chicken-and-egg).
    data, findings, advisories, fatal = collect_state_findings(
        state_path, args, session_start=True, repo_root=repo_root,
        check_boot_ack=False)
    if fatal:
        # fatal is a typed (severity, loc, msg) finding tuple — render it the
        # same way as the non-fatal findings below (the printer re-adds
        # "<state_path> — "). No string re-parsing, no template coupling
        # (PBF-PROP-015; this branch was dead until the arity fix).
        state_result = "FIX-FIRST"
        _sev, _floc, _fmsg = fatal
        finding_lines = [f"[{_sev}] {_fmsg}"]
    else:
        state_result = "FIX-FIRST" if findings else "PASS"
        finding_lines = [f"[{sev}] {msg}" for sev, _loc, msg in (findings or [])]
    if canon_missing:
        state_result = "FIX-FIRST"
        finding_lines.append(f"[P0] canonical files unreadable: {canon_missing}")

    # Anti-forgery binding: receipt is verifiable against THIS state at THIS point in
    # history — forging one is equivalent to running the command (GPT cross-review fix).
    head = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    latest_handoff = _latest_handoff(handoffs_dir)
    receipt = {"protocol_boot_receipt": {
        "generated_by": "cx check boot",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "canon": canon,
        "state_file": str(state_path),
        "state_sha12": state_sha12_without_boot_ack(str(state_path)) or "UNREADABLE",
        "repo_head": head.stdout.strip() if head.returncode == 0 else "NONE",
        "state_check_result": state_result,
        "state_check_findings": finding_lines,
        "latest_handoff_path": latest_handoff,
        "latest_handoff_sha12": (profiles_sha12(latest_handoff) or "UNREADABLE")
                                if latest_handoff != "NONE" else "NONE",
    }}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(receipt, f, sort_keys=False)
    receipt_hash = profiles_sha12(str(out_path))

    if state_result == "PASS":
        print("PASS")
    else:
        print("FIX-FIRST")
        for line in finding_lines:
            sev = line.split("]")[0].lstrip("[") if line.startswith("[") else "P1"
            print(f"  [{sev}] {state_path} — {line.split('] ', 1)[-1]}")
    print(f"  [INFO] boot receipt written: {out_path}")
    print(f"  [INFO] receipt sha12: {receipt_hash}")
    print("  [INFO] copy into CODE-X-STATE.yaml (values verbatim — cx generated them):")
    print("    session_start:")
    print("      protocol_boot_ack:")
    print(f"        receipt: {out_path}")
    print(f"        receipt_hash: {receipt_hash}")
    print("        acked_by: <model+family>")
    print("        timestamp: <ISO datetime>")
    return 0 if state_result == "PASS" else 1
