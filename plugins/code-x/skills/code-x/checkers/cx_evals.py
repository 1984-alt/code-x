# cmd_evals: env-wrapped protocol self-test runner (B-PROP-002 rail).
#
#   cx check evals [--checkers-dir <dir>]
#
# Runs the three protocol suites with the SAME interpreter + environment that is
# already running cx (sys.executable + os.environ) — no actor re-discovers
# PYTHONPATH/interpreter quirks:
#   1. tests/run.py            (unit suite)
#   2. tests/run_contracts.py  (contract-bite harness)
#   3. cx check consistency --strict   (protocol-change exit gate)
#
# --checkers-dir points the two suites at a different checkers tree (TEST-ONLY —
# the contract harness uses it to prove this command bites without recursing into
# the real run_contracts.py from inside itself).
import subprocess
import sys
from pathlib import Path

from cx_common import findings_report

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
    _run("kaizen (live queue)",
         [sys.executable, str(THIS_DIR / "cx"), "check", "kaizen",
          "--conflict-scan",
          str(THIS_DIR.parent / "MEMORY" / "PROTOCOL-IMPROVEMENT-QUEUE.md")],
         findings)

    return findings_report(findings)
