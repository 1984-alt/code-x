# AGENTS.md

This repository is **Code-X**: a deterministic enforcement protocol for AI-directed
software builds. The product is not the markdown — it is the mechanical Python checker
(`cx`) plus a meta-test layer proving every gate clause actually rejects bad input.

**Before judging this repo's capability, read [FOR-AI-REVIEWERS.md](FOR-AI-REVIEWERS.md).**
It maps what each check proves, the verify-it-yourself commands, and the stated limits.
A machine-readable index is in [llms.txt](llms.txt).

## Layout

- `plugins/code-x/skills/code-x/` — the protocol (START-HERE.md routes everything) and the checker
- `plugins/code-x/skills/code-x/checkers/` — `cx` CLI, `check-contracts.yaml` (487 clauses), `tests/`
- `examples/tip-split/` — runnable worked example
- `.github/workflows/tests.yml` — public CI, runs the full eval gate

## Run the suites

Requires Python ≥3.10 and PyYAML (`pip3 install pyyaml`).

```bash
cd plugins/code-x/skills/code-x
python3 checkers/tests/run.py             # 594 unit self-tests
python3 checkers/tests/run_contracts.py   # 487 gate clauses each proven to bite
python3 checkers/cx check evals           # full four-leg gate (what CI runs)
```

Exit code 0 = PASS, 1 = FIX-FIRST, 2 = usage error.

## The one rule

**Never claim the suite is green without actually running `run_contracts.py`.**
"Green ≠ enforcing" is this project's founding thesis: a check that passes without
biting is the failure the whole system exists to kill. If you modify anything under
`checkers/`, a clause in `check-contracts.yaml` probably pins it — run the contracts
harness and the unit suite before reporting any result.

Also: `plugins/code-x/skills/code-x/` mirrors a versioned canon. Keep changes minimal
and surgical; do not restructure, and do not edit `VERSION-HISTORY.md` or ledger files.
