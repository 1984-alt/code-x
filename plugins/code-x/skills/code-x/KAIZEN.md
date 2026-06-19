# Code-X V1 — KAIZEN (the continuous-improvement engine)

> Compact by design. Kaizen makes the *protocol itself* learn and get leaner — across **waste AND mistakes**, not just tokens. Read when running a Kaizen review or proposing a protocol change.

**Principle:** *Every card should leave the system slightly better measured, better scoped, or better standardized.*

## Toyota → Code-X mapping
| Toyota | Code-X equivalent |
|---|---|
| Make waste visible | `WORK-ORDER-COST-LOG` + `WEEKLY-BURN.md` (the **WASTE ALARM**) |
| Stop the line (jidoka) | CEO reject button · STOP card · no next module until accepted |
| Standardized work | work-order template · module capsule · golden skeleton |
| Continuous improvement (kaizen) | `MEMORY/LESSONS.yaml` + `MEMORY/PROTOCOL-IMPROVEMENT-QUEUE.md` |
| Go and see the real thing (gemba) | golden screenshot + click-path demo — NOT AI claims |
| Defect prevention (poka-yoke) | Card Compilation Gate · security tripwire · `EVALS/` |

## Three sensors → one loop
1. **Waste sensor** — the cost log → waste alarm (`over_read / wrong_model_tier / repeated_review / loop / unclear_card / missing_evidence`).
2. **Mistake sensor** — lessons + incidents (`MEMORY/LESSONS.yaml`).
3. **Verification sensor** — evals (`EVALS/`): prove a fixed failure-class can't recur.

**The loop:** signal → lesson → proposed protocol change (+ a new eval if it's a *new* failure-class) → cross-family review → **CEO approval** → active rule + a leaner protocol. **Never auto-mutating** — the CEO approves every change. Every fold bumps the protocol version (v1.01, v1.02, …) and appends ONE dated+timestamped row to `VERSION-HISTORY.md` (history ledger, not read-path).

**Provenance rule (protocol changes):** a change touching KERNEL / GATES / `cx check` / rule-registry / templates / SEVERITY / ROUTING / final-ready behavior gets its cross-family review from the **OPPOSITE family of the change's AUTHORING family** — same-family author + reviewer is never "independent." (Distinct from app waves, which key off the planner/builder.)

**Protocol-change exit gate (PROP-005/012):** every protocol-change session ends with all three green — `checkers/tests/run.py` OK · `tests/run_contracts.py` PASS (every gate clause bites) · `cx check consistency --strict` PASS (the canon-scope drift gate; sweep scope = registry `scan_scope` ∪ `appears_in`).

## The Kaizen review (every 5–10 cards, or weekly)
Read the cost log and ask: Where did tokens go? Which cards over-read? Which reviews should have been DELTA not FULL? Which model was too expensive for the task? Which card caused a loop? Which artifact was too vague and caused rework? **What ONE rule should change so it doesn't repeat?** → log the lesson, queue the change. *Find the largest waste source → remove it → standardize the fix.*

**Catch-rate guard:** the `caught_by` / `should_have_been_caught_by` sensors OBSERVE first — **no gate is pruned on catch-rate data before 2–3 real projects** (or a clear repeated pattern). Loop- and token-reduction must never lower catch-rate.

> Keep this file short. Kaizen is a habit + a log template, not a philosophy binder.
