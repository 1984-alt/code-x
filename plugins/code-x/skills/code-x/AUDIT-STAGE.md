# A-PROP-001 — The Audit Stage (4th stage) + SOP ship-gate conformance

> The stage between Building and Fixing. Posture = **verify** (read-only). Absorbs B-PROP-007 (Built-App Audit) as its engine and adds SOP ship-gate conformance (angle D, via PBAF-PROP-001). Companion doc to `FIXING-STAGE.md`.

## The four stages

1. **Planning** — decide and lock *exactly* what to build before any code.
2. **Building** — the AI builds *only* what the verified plan specifies.
3. **Audit** — *verify the built app against the standard*, read-only, before it is allowed to ship or be fixed.
4. **Fixing** — repair a defect, posture flipped to *preserve*.

Audit sits **after** Building and **before** Fixing: you first prove what's wrong (Audit), then repair only that, preserving the rest (Fixing).

## The organizing principle — verify, don't change (read-only posture)

The Audit stage may **read, run, probe, and judge** the built app. It may **not edit code.** Every finding is a disposition, not an edit. This keeps the auditor honest (an auditor who fixes as they go hides the defect rate) and keeps the two postures clean: Building *creates*, Audit *judges*, Fixing *preserves*.

## The engine — absorbed Built-App Audit (A/B/C) + SOP conformance (D)

Four angles, run in parallel, all read-only:

- **A — Requirements coverage.** Plain-English ask → code → evidence trace.
- **B — Original CEO asks.** Day-1 asks vs delivered / deferred.
- **C — Shipped reality.** Planned waves vs actual code; is there a real production caller/trigger for every feature (not just a passing test)?
- **D — SOP ship-gate conformance.** The shipped app tested against the SOP's 13 ship gates, scoped by the applicability model.

### The applicability scope (9 facts → per-module layers)

Angle D does not run all 13 gates on everything. The auditor re-derives the **9 build-facts** (A1–A9) from the built app and computes, **per sub-item**, which gates apply (APPLIES / PARTIAL / N/A). Rules: N/A only when a named fact is false (Rule 1); a whole layer is N/A only when *every* sub-item is N/A (Rule 2). Per-module audit tests only the layers that module touches; the final audit tests the whole app. Full derivation: `SOP/APPLICABILITY-MODEL.md`.

## The five levers

- **A — Stage entry.** Audit opens only after Building's exit gate closes; final-ready is unreachable if Audit was skipped.
- **B — Applicability re-derivation.** Auditor re-derives A1–A9; every layer marked with the fact driving any N/A; whole-layer N/A hiding a live sub-item = defect.
- **C — Ship-gate disposition.** Every applicable sub-item dispositioned (pass / fix / CEO-waive); undispositioned applicable item = P1.
- **D — Review ladder (CodeRabbit → self-review → cross-family).** CodeRabbit (automated AI review) → same-family self-review → cross-family audit (CEO 2026-06-28); each cross-family receipt is invalid unless preceded, in order, by a CodeRabbit receipt and a self-review receipt. Final receipt = opposite family from the builder. At the **final** audit the cross-family receipt is REQUIRED, not just ordered — zero cross-family receipts fails closed unless a typed escape mirrors the BF-PROP-005 stage_1 discipline: `xfam_capability_evidence` (manual scrubbed cross-family paste) or an explicit `ceo_decision_ref` risk waiver (`AUDIT-STAGE-FINAL-XFAM-REQUIRED`; CEO ruling 2026-07-02).
- **E — Fail-closed at final.** Any unresolved applicable ship-gate item at the final audit blocks final-ready.

## Granularity — per-module + final

- **Per-module (light):** as each module closes Building, audit it against the layers *it* touches. Cheap, early, catches drift close to the source.
- **Final (full):** one whole-app audit before final-ready — catches cross-module emergent gaps the per-module passes cannot see. Mandatory.

## Entry / exit

- **Entry:** Building exit gate green; Planning's recorded 9 build-facts + SOP coverage map available.
- **Exit:** all four angles complete; every applicable ship-gate sub-item dispositioned; **review-ladder receipts present in order — CodeRabbit → self-review → cross-family** (at the final audit the cross-family receipt is mandatory, or a typed stage_1 escape — see Lever D; CEO ruling 2026-07-02); zero undispositioned applicable items. → Fixing (for any `fix` dispositions) or final-ready.

## Honest limits (fail-closed, stated up front)

- Proves conformance to the SOP **as written at its pinned version** — not correctness beyond the standard. A gap the SOP doesn't cover is not caught here → raise a SOP upgrade.
- Per-module audits see only touched layers; the mandatory final audit is the only catch for cross-module gaps.
- `CEO-waive` is an explicit recorded human decision (Constitution 9), never the auditor self-skipping.

## Enforcement (so green = enforcing)

`AUDIT-STAGE-*` biting clauses in `checkers/check-contracts.yaml` + `cx check audit`. The stage is enforced mechanically, not just documented. See `checkers/check-contracts.yaml` (X6, v1.22 xfam fix: the clauses live in check-contracts.yaml, not a separate audit-stage-clauses.yaml).
