# Built-App Audit — Procedure

A final, read-only, whole-app audit run before certifying an app final-ready (at or before G8).
**Read-only: the audit looks, never touches code.** It fills the gap the per-card gates cannot see:
a feature can be built + tested + green and still never wired to run in production.

---

## When

Run once per project, after all modules are accepted and before the `FINAL-READY-CERTIFICATE` is assembled.
Must complete — with every finding **fixed**, or narrowly **CEO-deferred as a scope/requirements decision**
(see "The gate" below) — before `cx check final-ready` passes. **Zero means zero (KERNEL.md): a real
shipped defect or an accepted-known-risk stays OPEN and blocks final-ready — it is never "deferred".**
See `GATES.md` G8 for the machine-enforced pre-condition.

---

## The 3 angles (run in parallel, read-only)

### A — Requirements coverage
Every formal requirement (from `requirements-manifest.yaml`) is traced to:
1. A compiled card in the deck (`cx check deck` passes this mechanically — the audit confirms it held at ship)
2. Shipped code that implements it
3. Evidence the feature was accepted

Flag:
- **Ghosts** — required by the manifest but unbuilt or untraceable to real code
- **Orphans** — code that was built but has no formal requirement tracing it (scope creep / undocumented feature)

### B — Original CEO asks
Each plain-English ask from day 1 (pre-spec conversations, brainstorm notes, CEO-DECISION-LEDGER) is traced to:
1. A card or stated reason for deferral
2. Real code + tests that implement it
3. Accepted evidence (CEO-approved outcome)

Flag:
- **Silently dropped** — an ask that never became a card and was never explicitly deferred/decided
- **Half-delivered** — a card exists and passed but only partially implements what was asked

### C — Shipped reality
Planned waves vs actually-shipped code:
1. Every wave/module in the registry is verified to have shipped real, non-empty code
2. The full test suite is **run firsthand** by the auditor (not read — run)
3. Orphans (shipped code with no card, no requirement) are flagged
4. Gaps (planned cards not shipped, modules not accepted) are flagged

**The killer check (mandatory inside angle C):**
> Built + tested + green ≠ wired and running.

For **every shippable feature or CEO ask**, confirm a **real production caller or trigger** exists:
a route, schedule, cron, tick, entrypoint, or lifecycle hook that **actually invokes the feature code**
in a running app — not just tests.

Flag any feature with **zero non-test callers** or no production trigger.
This is the failure mode per-card gates cannot see: a feature passes all tests and all reviews
yet is never reached by any user-facing path.

---

## Method

**Default method:** three parallel read-only subagents — one per angle (A, B, C). Each works
independently, blind to the other two (independent perspectives, no shared draft). They read existing
artifacts: manifest, deck, cards, state, capsules, code, tests. (A tiny, low-risk app may collapse this
to a single-pass combined audit — see the scaled-effort default below.)

The orchestrator **firsthand-verifies every actionable finding** before it enters the synthesis:
no second-hand claims, no "probably broken" without a concrete evidence trace.

Synthesis: reconcile the 3 angle outputs → severity-ranked findings (P0–P3, per `SEVERITY.md`) →
recommended CEO dispositions (fix + card / explicit defer / accept-known-risk).

Effort scales to project size and risk:
- **Tiny app (single developer, <5 modules, low-risk):** single-pass combined audit (one agent, 3 angles sequentially)
- **Real project (>5 modules or medium-risk):** full 3-angle parallel audit
- **HIGH-risk** (money / login / auth / data): always the full 3-angle parallel audit, regardless of size

---

## Output

A single audit report directory (path recorded in state as `built_app_audit.report_ref`):

| File | Purpose |
|---|---|
| `AUDIT-SUMMARY.md` | Bottom line · severity-ranked findings · recommended dispositions |
| `A-requirements-coverage.md` | Angle A full output |
| `B-ceo-original-asks.md` | Angle B full output |
| `C-shipped-reality.md` | Angle C full output (includes killer-check evidence) |

Use `templates/BUILT-APP-AUDIT.template.md` for `AUDIT-SUMMARY.md`.

---

## The gate (pre-final-xfam and pre-G8)

An app **cannot** be routed to final xfam or certified final-ready until:
1. The Built-App Audit has run (state carries `built_app_audit.status: run`)
2. Every finding is **dispositioned** — one of exactly two ways:
   - **Fixed** — via a normal Code-X card (see the fix path below), never a hot patch; OR
   - **CEO-deferred as a scope/requirements decision** — the CEO has changed scope so the finding
     is no longer a ship defect (it describes behaviour the product is no longer required to have).
     The decision is recorded in `CODE-X-STATE.yaml` with a ref.

   **What "CEO-deferred" is NOT (zero-means-zero, KERNEL.md):** an *accepted-known-risk* or a *real
   shipped defect* is a **known issue** — it stays **OPEN in `open_findings` and BLOCKS final-ready**.
   Deferral is a scope decision, never a way to park a known bug.
3. `built_app_audit.findings_dispositioned: true` is set in state
4. `built_app_audit.report_ref` points to the audit report directory — repo-relative, non-symlink,
   inside repo, **existing**, and containing `AUDIT-SUMMARY.md`

`cx check state` rejects a BUILD_FACTORY state that routes accepted modules straight to final
xfam without this milestone. `cx check final-ready` enforces this mechanically at ship (P0
block when missing or incomplete).
This gate **complements** — does not replace — the existing G8 / `FINAL-READY-CERTIFICATE`.

**Fix path for real build holes (one-shot — no re-review loop, GATES.md):** an audit finding that is a
real build hole becomes a **normal Code-X card** that runs the **standard single build + review cycle**
(self-review + the one cross-family pass + deterministic verification / class-sweep) — *not* a fresh
model re-review of the already-audited module. The audit is a finder, not a review loop; the only later
model review is the normal ship gate (the final cross-family review), which comes after this audit
for a `CODEX_APP` build.

---

## Relationship to existing gates

The audit is a synthesis layer, not a substitute:
- `cx check deck` (G7): packet coverage → deck coverage (still runs at final-ready)
- Module-acceptance Andon receipts: per-module CEO sign-off (still required)
- `cx check final-ready` (G8): machine-assembled certificate (still required)
- **Built-App Audit**: whole-app reconciliation across all three angles — catches the gaps the per-card gates are blind to (especially the killer check)
