# Code-X V1 — KAIZEN (the continuous-improvement engine)

> Compact by design. Kaizen makes the *protocol itself* learn and get leaner — across **waste AND mistakes**, not just tokens. Read when running a Kaizen review or proposing a protocol change.

**Principle:** *Every card should leave the system slightly better measured, better scoped, or better standardized.*

## Toyota → Code-X mapping
| Toyota | Code-X equivalent |
|---|---|
| Make waste visible | `WORK-ORDER-COST-LOG` (the **WASTE ALARM** — `cx check cost`) |
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

**Protocol-change exit gate (PBF-PROP-004 · PBF-PROP-007):** every protocol-change session ends with all three green — `checkers/tests/run.py` OK · `tests/run_contracts.py` PASS (every gate clause bites) · `cx check consistency --strict` PASS (the canon-scope drift gate; sweep scope = registry `scan_scope` ∪ `appears_in`).

**Closure rule (behavioural PROPs — PBF-PROP-012 Part F):** a queue proposal tagged `behavioural: yes` — a rule about what the AI must DO (prevention, delegation, tone, showing the CEO; NOT mechanically provable from output alone) — may NOT be marked `status: APPLIED` unless it carries an `enforcement:` that is EITHER **(a)** a biting fail-closed checker `clause_id` that exists in `checkers/check-contracts.yaml` and fails on a pinned bad fixture, OR **(b)** a `prompt_marker`: the rule is wired into an operating prompt the AI runs (an agent definition under `~/.claude/agents/` OR a canon dispatch stanza) AND a `marker_clause_id` whose ack/marker bites, OR **(c)** a `judgment_limit`: the behaviour cannot be mechanically proven, accepted by the CEO with a `ceo_decision_ref`, and the nearest review lens is named. **Presence-lint-only — "the canonical phrase exists in a canon doc" as the SOLE enforcement — is BANNED for a behavioural APPLIED PROP.** The checker is `cx check kaizen MEMORY/PROTOCOL-IMPROVEMENT-QUEUE.md`; its clauses run inside the protocol-change exit gate via `run.py`/`run_contracts.py`, and the live-queue closure check joins that exit gate in Part C. Honest limit: F proves the behaviour is WIRED to something that bites — not that the AI then obeyed it at runtime (the module review + the clause's own bite judge that). Plain-English: a "the AI must do X" rule cannot be called done until something real forces X; a sentence in a doc is not real.

**No-ambiguity rule (PBF-PROP-014):** every PROP — at authoring time — must scan all existing PROPs and the CEO-DECISION-LEDGER for (a) duplicates, (b) ambiguities (same problem two ways), and (c) conflicts (contradictory rules). The scan step is injected into the PROP-authoring dispatch; findings are declared and resolved, not silently dropped. The result is recorded in a `conflict_scan` block on the queue entry. The biting clause is `KAIZEN-CONFLICT-SCAN-RESOLVED` (P0): a `conflict_scan` that lists ≥1 hit but carries a blank or placeholder `resolution_ref` fails closed. Every PROP must carry a `conflict_scan` block (`KAIZEN-CONFLICT-SCAN-PRESENT` P1). **Honest limit (judgment_limit residual):** the scan proves the step RAN and findings were declared + resolved; it cannot prove that zero ambiguity exists in the universe. GREEN = "the author scanned and resolved what they found," NOT "this PROP is provably unambiguous."

## The Kaizen review (every 5–10 cards, or weekly)
Read the cost log and ask: Where did tokens go? Which cards over-read? Which reviews should have been DELTA not FULL? Which model was too expensive for the task? Which card caused a loop? Which artifact was too vague and caused rework? **What ONE rule should change so it doesn't repeat?** → log the lesson, queue the change. *Find the largest waste source → remove it → standardize the fix.*

**Catch-rate guard:** the `caught_by` / `should_have_been_caught_by` sensors OBSERVE first — **no gate is pruned on catch-rate data before 2–3 real projects** (or a clear repeated pattern). Loop- and token-reduction must never lower catch-rate.

**Hardening moratorium (PBF-PROP-022-E, 2026-07-07):** the mirror image of the catch-rate guard —
no NEW hardening round on any gate that has ZERO in-anger fires on a real project, until it either
fires for real or earns a pinned real-world eval. Applies to the whole UNTESTED-22 set from the
2026-07-07 gate-ROI audit (`design-history/cx-audit-2026-07-07-findings-summary.md`), named
examples: module-start forge-proofing, fix-escalation/engine-epoch, lock-fidelity. Standing walls
stay FROZEN as-is — not removed, not extended — until they earn a reason to change. A round of
extra edge-case coverage on an already-zero-fire gate is ceremony, not safety; the CEO's eye and
cross-family review are the sensors that have actually caught real defects (see EARNING list,
same audit) — spend effort there, not on hardening walls nothing has hit yet.

> Keep this file short. Kaizen is a habit + a log template, not a philosophy binder.
