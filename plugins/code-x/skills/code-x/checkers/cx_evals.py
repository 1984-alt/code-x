# cmd_evals: env-wrapped protocol self-test runner (B-PROP-002 rail).
#
#   cx check evals [--checkers-dir <dir>]
#
# Runs the four protocol suites (unit + contracts + strict consistency + live kaizen)
# with the SAME interpreter + environment that is
# already running cx (sys.executable + os.environ) — no actor re-discovers
# PYTHONPATH/interpreter quirks:
#   1. tests/run.py            (unit suite)
#   2. tests/run_contracts.py  (contract-bite harness)
#   3. cx check consistency --strict   (protocol-change exit gate)
#
# --checkers-dir points the two suites at a different checkers tree (TEST-ONLY —
# the contract harness uses it to prove this command bites without recursing into
# the real run_contracts.py from inside itself).
#
# CX_KAIZEN_QUEUE (F-PROP-002, TEST-ONLY, honored only under CODE_X_TEST_MODE=1) points the
# 4th leg (live kaizen queue) at a fixture queue file instead of the real live
# MEMORY/PROTOCOL-IMPROVEMENT-QUEUE.md — this is what lets the contract harness prove the
# kaizen leg itself bites, in isolation from the other 3 legs. Production always audits the
# real live queue (see cx_common.resolve_kaizen_queue_path).
import subprocess
import sys
from pathlib import Path

from cx_common import findings_report, resolve_kaizen_queue_path

THIS_DIR = Path(__file__).resolve().parent


def _run(label: str, cmd: list[str], findings: list) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  [INFO] PASS {label}")
    else:
        tail = (result.stdout + result.stderr).strip().splitlines()[-3:]
        findings.append(("P1", label,
            f"suite failed (rc={result.returncode}): {' | '.join(tail) or 'no output'}"))


def cmd_evals(args) -> int:
    checkers_dir = Path(args.checkers_dir) if getattr(args, "checkers_dir", None) else THIS_DIR

    findings = []
    for label, script in (("tests/run.py", checkers_dir / "tests" / "run.py"),
                          ("tests/run_contracts.py", checkers_dir / "tests" / "run_contracts.py")):
        if not script.is_file():
            findings.append(("P1", label, f"suite not found at {script}"))
            continue
        _run(label, [sys.executable, str(script)], findings)

    # consistency --strict always runs against the REAL canon (the registry the
    # cx binary belongs to) — a redirected checkers tree never weakens the exit gate.
    _run("consistency --strict",
         [sys.executable, str(THIS_DIR / "cx"), "check", "consistency", "--strict"],
         findings)

    # live kaizen-queue closure — every APPLIED behavioural PROP must carry real enforcement
    # (PBF-PROP-012 Part C wires the A2-deferred line; the real queue must be closure-clean).
    # F-PROP-002: queue_path resolves CX_KAIZEN_QUEUE (TEST-ONLY, gated on CODE_X_TEST_MODE=1)
    # so a real bad fixture can exercise this leg in isolation; queue_err (env set outside test
    # mode) is a P1 finding on its own and the real live queue still runs, untouched.
    default_queue = THIS_DIR.parent / "MEMORY" / "PROTOCOL-IMPROVEMENT-QUEUE.md"
    queue_path, queue_err = resolve_kaizen_queue_path(default_queue)
    if queue_err:
        findings.append(("P1", "kaizen (live queue)", queue_err))
    _run("kaizen (live queue)",
         [sys.executable, str(THIS_DIR / "cx"), "check", "kaizen",
          "--conflict-scan", str(queue_path)],
         findings)

    return findings_report(findings)
