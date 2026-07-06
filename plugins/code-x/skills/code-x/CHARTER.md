# Code-X V1 — Locked Direction Charter

**Status:** 🔒 DESIGN LOCKED — 2026-06-09 (4-pass cross-family review complete: 13→4→2→0, GPT 5.5 Pro **PASS**; CEO locked). Next: build `cx check` → then V1 canonical + v0.13 archived.
**Signed off by:** Opus 4.8 Max + GPT 5.5 Pro Extended (3-way council, fully converged — "zero open direction seams")
**Locked by:** the user (CEO / decider)
**Credits (CEO directive 2026-06-11):** the user (CEO) · Claude Opus 4.8 · GPT 5.5 Pro · **Claude Fable 5** — involved from the moment it launched: round-4 fresh-eyes review → lock synthesis → PBF-PROP-008 · P-PROP-001 · PBF-PROP-009 + subsequent protocol sessions. Code-X is the work of all four, not a fixed pair.
**This file is:** the single source of truth for *what was decided and where it lives*. The mechanics live in the actual V1 files; this charter is the decision record + file manifest + build/review plan. Don't restate mechanics here — point to the file.

---

## 1. Why V1 exists (the two problems it must kill)

1. **Too expensive** — Code-X v0.13 burned the weekly limit of *both* $200 subscriptions (Claude Max + Codex) in ~2.5 days.
2. **Didn't work** — the last big build (a live-production build) shipped broken-looking, because visual quality was a *requirement* but not an *executable gate*; reviews checked code, not the running app. *"Codex built the wrong thing successfully."*

## 2. The mission (unchanged soul)

- **Goal A — ships working software** a non-coder can show users/devs *proudly*.
- **Goal B — token-efficient** enough that the subscriptions last the *whole week*.
- **Soul:** a non-coder → professional-team-quality full-stack apps, working from the get-go, **never debugging, never reading stack traces, never accepting "known issues."**
- **The CEO is an AI build director:** *directs the engineering system that directs the AI* — not the code.
**The soul in three lines (canonical phrasing — CEO intent, wording refined + approved 2026-06-11; raw CEO words preserved in ledger A-002):**
1. **Capability** — Code-X turns a non-coder into an **AI build director**: the CEO directs the engineering system, the system directs the AI, and the output is real, working software to the standard of a professional dev team — shipped proudly, never debugged by the CEO, zero "known issues."
2. **Efficiency** — token and work efficiency is an **obsession, not a preference**: every read, review, and loop must earn its cost; waste is made visible and the largest source removed first; the subscriptions last the whole week.
3. **Kaizen** — the protocol **improves itself continuously**: every mistake — *and every review* — becomes a lesson, every new failure-class becomes a mistake-proofing eval, every change leaves the system leaner — the system learns from *how it works*, not only from *what it builds*. *(reviews added at PBF-PROP-010 fold 2026-06-11: learning is review-triggered, not only mistake-triggered)*

- **Core value (CEO): the Toyota Way / Kaizen — applied to the WHOLE protocol, not just tokens.** Continuous improvement on three fronts: eliminate waste (tokens), **learn from every pipeline/protocol mistake**, and **streamline the protocol over time**. Make problems *visible* (cost log + incidents + evals), fix the root cause, then lock the fix in as a lesson AND a mistake-proofing eval so it can never recur. (Engine: §4 "The Kaizen engine.") *"I am the system, and the system is part of me — it must learn and evolve from every mistake."*

### 2.1 The house analogy + the four stages (P-PROP-005)

Building software is building a house. **Planning** = the client (CEO) + the architect: ONE plan yields TWO outputs — (a) **full construction docs**, what the AI *builder* reads and builds from (the Code-X packet + cards); and (b) the **Master Blueprint**, the architect's render the *client* reviews to see the finished thing before any building (= `MASTER-BLUEPRINT.md`; a render-never-re-type projection of the docs, the CEO's single review-and-drive surface). **Building** = the contractor builds faithfully from the construction docs; the gates stop slop + drift; a module is buildable only after the CEO approves it on the blueprint. **Audit** = the building inspector: walks the finished build against the plans and the code standard, read-only — judges, never repairs. **Fixing** = repair, posture flipped to preserve.

**🔒 The four-stage narrative below is COPIED WORD-FOR-WORD from the public GitHub README (`1984-alt/code-x`, README §"How it works: four stages") — the same-as-github rule (CEO 2026-06-25): canon and the public face tell ONE story; copy it, never paraphrase. The Fixing stage especially must read the same as GitHub.** [RULE:same-as-github-three-stage]

1. **Planning** — decide and lock *exactly* what to build before any code: requirements, decisions, screen designs, business rules, architecture, and a security baseline. You review it all through the Master Blueprint.
2. **Building** — the AI builds *only* what the locked plan specifies, one small work-order at a time. Mechanical checks run on every card; human approval and model review happen at module boundaries, not in endless loops.
3. **Audit** — before anything is repaired or shipped, the built app is judged against the plan and against a standard, read-only: the Audit stage doesn't touch code, it only judges. It checks three things — does the shipped code actually match what was asked for (not just what the plan turned into), does "built and green" really mean wired and running (not just a test passing with no real caller behind it), and does a whole-app read catch the gaps no single module review could see on its own. On top of that, it runs the app through a 13-gate ship-readiness standard — but only the gates that genuinely apply to what was built, so a marked "N/A" is a deliberate decision, not a shortcut. Every finding hands off to the Fixing stage; the Audit stage never edits code itself.
4. **Fixing** — repairing something already built flips the posture from *create* to *preserve*: change only the defect, nothing else. It exists because drift sneaks in during repairs — a file moved "while we're here," a screen restyled, a settled decision reversed from memory. Code-X counts that as a failure: it freezes the file tree so nothing moves unseen, and won't let a settled decision be re-argued.

**The one rule above all: never build before the plan is locked and verified.**

(Stage canon: PLANNING → `MASTER-BLUEPRINT.md` · BUILDING → `KERNEL.md`/`GATES.md` · AUDIT → `AUDIT-STAGE.md` · FIXING → `FIXING-STAGE.md`.)

**v1.22 — the Audit stage (A-PROP-001, CEO-D-038 2026-07-01)** inserted the 4th stage between Building and Fixing. Posture = *verify* (read-only): the Audit stage judges the built app against the standard (absorbed `BUILT-APP-AUDIT` angles A/B/C + the SOP's 13 ship gates as angle D, scoped by the applicability model), it never edits code — findings hand off to Fixing. Stage canon: `AUDIT-STAGE.md`. The four-stage block above stays word-for-word locked to the public GitHub README (`[RULE:same-as-github-three-stage]`); the companion GitHub README update (README §"How it works: four stages") shipped 2026-07-02.

## 3. The architecture

```
PLANNING STUDIO  (hands-on with CEO — top models)
  product taste lock → decisions closed → architecture → ONE security baseline
  → design golden master (looks-first screens CEO approves) → business-logic validation
  → work-order deck compiled  ──►  CARD COMPILATION GATE (compiler + opposite-family auditor + shape checker)

BUILD FACTORY  (hands-off from CEO except approvals — cheap models unless the card says otherwise)
  Mode A UI Foundation → CEO approves the look
  → module build → 30-sec golden screenshot + click-path → CEO approves → write module capsule
  → (repeat; module N reads kernel + state + its card + dependency capsules only)
  → one-and-done capped review loop + per-module security tripwire
  → P0–P3 all zero → final-ready certificate + full security/privacy closeout

MEMORY  (lightweight files — never auto-mutating)
  lessons (seeded from v0.13 scars) · incidents · cost log (Kaizen) · skeleton improvements
```

## 4. Locked decisions register (the signed-off design)

**Structure & cost**
- Clean reset (not v0.14 patching v0.13). Name: **Code-X V1**.
- **Tiny kernel + one work-order at a time + module capsules.** Per-turn read = kernel + state + one card + named slices. Nothing else.
- **Anti-bloat ceiling:** the per-turn read path has a hard size cap; any change that busts it must cut something else first. Fail-closed on size.
- **Enforcement = Level A (plain files) + Level B (tiny checkers). NO Level C (full orchestrator/runner) now.** Revisit only after V1 proves itself on 2–3 projects. *(Clarified B-PROP-013 2026-07-06: a Level-B **receipt-stamper** — `cx check boot`, `cx check accept` — is NOT the deferred Level-C auto-orchestrator; it generates one machine-authored receipt per command invocation and never routes actors, builds, or self-mutates. Forge-parity hardening of the acceptance checkpoint (`cx check module-acceptance` recompute legs + `cx check accept`) is therefore permitted NOW and is orthogonal to the reliability-bar / long-autonomous axis below (L80–84) — it hardens the wall the bar depends on, it does not move the bar.)*
- **`cx check` = ONE command surface** with subcommands (`card`, `state`, `scope`, `evidence`, `cost`, `final-ready`). Never a sprawl of scripts; never `cx run`/`orchestrate`/`auto-route`/`self-mutate`.

## Long-autonomous milestone

**GOAL:** long-autonomous full build (every module built to completion without a per-module CEO turn) is a long-term objective of Code-X V1 — not a permanent "never."

**Status: OFF until proven.** Hands-off long-autonomous UI build is switched OFF today. It is kept OFF mechanically, not by policy alone, by PBF-PROP-012-E `MODULE-DEMO-MISSING` (P0 precondition inside `validate_live_slice_accept`): every `live_slice` module requires a per-module CEO demo + typed-accept turn before the next module may start; the order wall (`MODULE-START-LIVE-SLICE-NO-DRIVE`) then blocks the whole build if that turn is missing. These two gates make hands-off UI build structurally impossible until a future PROP removes them.

**Reliability bar: LOCKED + auditable (EVAL-041, CEO-locked 2026-07-01).** The bar is canon now — not deferred: **N = 3 consecutive clean real projects, ALL user-facing** (`GRADUATION_N`/`GRADUATION_M` = 3/3), each observed for a **14-day post-ship window** (`POSTSHIP_WINDOW_DAYS` = 14). "Clean" means a whole project shipped with all 7 criteria BINDING (not illustrative) — RECOMPUTED from real receipts, never a self-declared flag: (1) every user-facing module passed the see-and-test gate on first acceptance (`MODULE-DEMO-MISSING` never fired); (2) CEO accepted on the FIRST demo of each user-facing module — zero rebuilds; (3) zero design drift (`cx check design-fidelity` + `cx check render-fidelity` + lock-fidelity levers all green); (4) build matched the locked Blueprint (`cx check blueprint` green, no unbudgeted behaviour lacking a `ceo_decision_ref`); (5) zero P0/P1 defects in the 14-day post-ship window; (6) final-ready certificate clean on the FIRST pass; (7) full review pipeline (module-quality legs + CodeRabbit/build-turn receipt) present and green on every module. The append-only **graduation ledger** (`MEMORY/GRADUATION-LEDGER.md` + `MEMORY/graduation-receipts/`) records each finished project; `cx check graduation` re-derives clean/not-clean from the ledger's snapshotted receipts and recomputes the consecutive-clean streak — it never trusts a hand-typed verdict.

**Enforcement pointer:** `MODULE-DEMO-MISSING` (PBF-PROP-012-E) + `MODULE-START-LIVE-SLICE-NO-DRIVE` (B-PROP-008) keep build OFF today. `cx check graduation --authorize-decision` (EVAL-041) is the GATE on top of the bar: fail-closed, it blocks any future long-autonomous authorization until the recomputed streak proves N-of-N clean, all user-facing, with no pending (post-ship-window-open) entry newer than the counted streak. `cx check graduation --status` gives a plain informational readout and never blocks.

**Upgrade path:** once the bar is proven (the streak recomputes clean), the CEO records a typed `ceo_decision_ref` (e.g. `CEO-D-0NN: long-autonomous milestone REACHED`) in `MEMORY/CEO-DECISION-LEDGER.md`. `cx check graduation --authorize-decision <that id>` is the precondition a future autonomy-switch PROP must pass before it may build the switch itself — this gate authorizes that future PROP; it does not build the switch. Until both the decision ref exists AND the gate passes, build stays OFF.

**Work orders & cards**
- **Card compiler = a top-model AI planning task** (reads the locked packet once → emits the full work-order deck).
- **Card auditor = opposite-family top model** — and this audit **IS** the main pre-build cross-family checkpoint *per card* (do *not* stack a second per-CARD cross-family review on top). It checks each card against its packet slice; it does **not** review the non-card packet docs (TRD/PRD/architecture/security baseline) for cross-document coherence — that is the separate **whole-packet integration review** at G7 (P-PROP-006), a distinct surface. *(Opus sharpening #2; whole-packet carve-out added v1.19.)*
- **Card Compilation Gate is mandatory:** compiler compiles, opposite-AI audits, tiny checker validates shape/scope/budget. A bad card is more dangerous than a long packet.
- Work-order fields: id, mode, actor, model_tier, objective, **source_map, card_compilation, actor_record, family_note,** read(required/forbidden), allowed/forbidden files, allowed/forbidden ops, relevant_invariants, acceptance, evidence_required, security_tripwire, loop_budget (review_fix_cycles + self_heal_attempts), stop_conditions, cost_budget, state_update.

**Build factory**
- **Per-module build + CEO approval before the next module.** Long autonomous / program-seal build is **retired** (it caused the a live-production build end-surprise). Modules sized so approval takes **minutes, not hours**.
- **Mode A UI Foundation mandatory for user-facing apps** — looks first, engine after.
- **Mode A fixture exception:** Mode A may use clearly-labelled `DESIGN_FIXTURE` sample data for visual proof only — never real/money/test/"done" data, and removed/replaced once the module's real engine is built (G3-enforced). *(Cross-family pass-1 fix P1-03.)*
- **Visual gate = Golden Screenshot + Click-Path Contract:** AI verifies mechanical proof (screen exists, viewport correct, no overflow, controls clickable, route map complete, matches approved screen card); **CEO verifies taste.**
- **Module capsules** required after approval; module N reads only dependency capsules, not full prior docs.
- **Capsule anti-staleness:** touch a module → refresh its capsule *same wave* + its regression commands must pass, or the wave can't clear. *(Opus sharpening #3.)*
- **One-and-done review loop:** review once → fix one batch → verify once → stop/handoff. `loop_budget` is a hard cap.

**Reviews & security**
- **Right-sized reviews:** SCAN / DELTA / SLICE / FULL. FULL only at lock, ship, major security/architecture/privacy change, or explicit CEO request.
- **Security: one project baseline once + a tiny tripwire every module.** If the tripwire fires → security delta. **Tripwire answers are compiler/diff/checker-derived where possible, not builder self-attestation only.** *(Opus sharpening #4.)*

**Models & memory**
- **Cheap-model routing mandatory.** If a card names no tier, default is **NOT top model**. Cheap worker fails once → may retry once; fails again → escalate or STOP.
- **Lightweight MEMORY**, never auto-mutating. Improvement loop: lesson → proposal → eval update → cross-family review → **CEO approval** → active rule.
- **Seed MEMORY/LESSONS from v0.13's scars** on day one (don't lose hard-won fixes). *(Opus sharpening #5.)*
- **Golden skeleton** (reusable app starter) allowed **only with a certificate** (version, included/excluded, known limits, security baseline, visual-shell quality, backup/restore proof, final-ready cert).

**Safety floor (kept)**
- Severity ladder P0/P1/P2/P3 (see `SEVERITY.md`); **final-ready = all four zero + zero known issues.**
- **Self-heal loop** (technical errors auto-fix, bounded) + **4-failure cross-family debug rule** preserved. **STOP never = CEO debugs.**
- Business-logic validation (CEO signs money rules), CEO provisioning manifest, real-data-only, secrets-by-name — all kept.

**The Kaizen engine — continuous improvement of the *protocol itself* (not just tokens)**
Kaizen is the soul of V1's self-improvement: one loop that makes the pipeline learn from every mistake and get leaner over time. **Three sensors** feed it:
- **Waste sensor — the cost log → the WASTE ALARM.** Each card logs to `WORK-ORDER-COST-LOG` its model tier, review mode, files read/changed, loops, and **waste_flags** (over_read / wrong_model_tier / repeated_review / loop / unclear_card / missing_evidence). It is a *waste* alarm, not a *cost* meter — the action is *find the largest waste source → remove it → standardize the fix*, never "spend less" generically. (A live provider-limit meter is impossible → glanceable `WEEKLY-BURN.md` = manual provider status + Code-X proxy counts.) *(GPT reply-3 #6 + Opus #1 / CEO Toyota reframe.)*
- **Mistake sensor — lessons + incidents.** Every pipeline/protocol failure becomes a `MEMORY/LESSONS` entry (seeded day-one from v0.13's scars). Lightweight files; only the Card Compiler pulls the relevant ones into a card.
- **Verification sensor — evals (mistake-proofing / poka-yoke).** Tiny protocol self-tests that prove the protocol still enforces its rules and that a fixed failure-class cannot recur. Start small (5 seeded, 9 at V1 lock); the set grows SLOWLY (one eval per *new* failure-class, not per lesson), each tiny, run rarely (protocol change / V1 creation / before a first build / before calling V1 stable) — never per module. The anti-bloat ceiling applies to evals too: if they grow heavy, consolidate. See `EVALS.md`.
- **The loop:** sensor signal → lesson → proposed protocol change (+ a new eval if it's a new failure-class) → cross-family review → **CEO approval** → active rule + a leaner protocol. **Never auto-mutating** — the CEO approves every protocol change.

## 5. Transition & retirement policy (CEO override — 2026-06-09)

- **Full retirement:** once V1 is locked, **v0.13 is retired.** (Overrides GPT's "in-flight finish on v0.13.")
- **Redo halfway projects under V1** (a live-production build, an attendance app) rather than limping on v0.13 — **but PORT their existing planning/decisions** (requirements, money rules, locked decisions); they re-run through V1's *build factory*, they are NOT re-planned from zero. *(Opus practicality add — makes the bold call cheap.)*
- Every project carries a `protocol_stamp` (Code-X V1 | v0.13) during the switch so old and new rules never mix in one build.
- **First proof build = `CEO_DEFERRED`** (recorded 2026-06-09; candidates: Sample, or a redone a live-production build). CEO decides after V1 is locked.

**Machine-readable (GPT reply-3):**
```yaml
legacy_protocol_policy:
  v0_13_live_status: RETIRED_ON_V1_APPROVAL
  v0_13_role: ARCHIVE_AND_LESSON_SOURCE_ONLY   # archived as history + memory, NOT deleted as knowledge
  in_flight_projects: REPLAN_OR_RECARD_UNDER_V1
  mixed_protocols_for_one_project: FORBIDDEN

first_proof_project: CEO_DEFERRED   # CEO sets after V1 lock (Sample | live-production_V2_REDO | CEO_DEFERRED)
```

## 6. File manifest (what V1 contains)

| File | Role | Status |
|---|---|---|
| `CHARTER.md` | this — locked decisions + map | ✅ written |
| `KERNEL.md` | one-page house-rules, read every session | ✅ written |
| `templates/STATE.template.yaml` | "you are here" state file | ✅ written |
| `templates/WORK-ORDER.template.yaml` | the one-card-at-a-time work order | ✅ written |
| `templates/MODULE-CAPSULE.template.yaml` | post-approval module summary | ✅ written |
| `templates/FINAL-READY-CERTIFICATE.template.yaml` | ship certificate (auto-assembled) | ✅ written |
| `templates/WEEKLY-BURN.template.md` | Kaizen cost log | ✅ written |
| `GATES.md` | card-compilation gate, security tripwire, capsule anti-staleness, review modes, one-and-done loop, Mode A | ✅ written |
| `SEVERITY.md` | P0–P3 ladder + final-ready rule | ✅ written |
| `ROUTING.md` | model routing + per-family "personality notes" | ✅ written |
| `EVALS.md` | 9 tiny protocol self-tests at V1 lock (grows slowly) | ✅ written |
| `MEMORY/LESSONS.yaml` | seeded from v0.13 scars | ✅ written |
| `START-HERE.md` | router/index | ✅ written |
| `templates/PRODUCT-TASTE-LOCK.template.md` | CEO signs the look/feel/taste before build (G7) | ✅ written |
| `templates/DESIGN-GOLDEN-MASTER.template.md` | folder spec: approved looks-first screens + click-path contract | ✅ written |
| `templates/BUSINESS-LOGIC-VALIDATION.template.md` | CEO signs money/business rules by worked example (ported v0.13) | ✅ written |
| `templates/CEO-PROVISIONING-MANIFEST.template.yaml` | external accounts/secrets/human setup closed before build (ported v0.13) | ✅ written |
| `templates/STOP-ACTION-CARD.template.yaml` | the typed STOP output (handoff/decision/safety/escalation) | ✅ written |
| `templates/DEAD-ENDS-LEDGER.template.md` | what was tried & failed, carried across handoffs (ported v0.13) | ✅ written |
| `templates/BUILDER-QUESTIONS-LOG.template.md` | builder's open questions → CEO/planner answers (ported v0.13) | ✅ written |
| `templates/EVIDENCE-INDEX.template.md` | light index of evidence paths per card/module | ✅ written |
| `templates/GOLDEN-SKELETON-CERTIFICATE.template.yaml` | the starter-kit certificate Charter §4 requires | ✅ written |
| `checkers/cx-check` | the ONE checker surface (Level B) | ⏳ to build (code) |
| ported checkers | packet-lint, honesty-check, preflight, sync-check, secrets-scan, BRG | ⏳ to port |

**Folded (NOT separate files — anti-bloat):** the *P3-closure queue* lives in `CODE-X-STATE.yaml → open_findings` + the SEVERITY workflow (no separate file). The *actor ledger* (who-did-what) is **never hand-kept** — it lives in each card's `actor_record`; a derived roll-up by `cx check state` is a Kaizen/future item, NOT enforced today. All template homes above are **load-on-demand** (none sit in the every-turn read path), so giving the "kept" artifacts proper homes does **not** re-bloat the read budget. *(Cross-family review pass 1, lean implementation.)*

## 7. Build & review plan for V1 itself

1. **Charter + Kernel** (this batch) → CEO confirms the charter is the right spec.
2. **Core templates + gates** (state, work-order, capsule, GATES, SEVERITY) — the structural skeleton.
3. **Supporting files** (ROUTING, EVALS, LESSONS seed, certificate, weekly-burn, START-HERE, migration note).
4. **`cx check` + porting** the proven v0.13 checkers (code step).
5. **GPT 5.5 Pro batch-reviews** the V1 files (≤20 per batch), adversarially.
6. **CEO locks V1** → v0.13 retired → first proof build (project TBD).

---

*Council provenance: brief → GPT reply 1 (conceded runner, +4 additions) → Opus R2 (+5 refinements) → R3 closure → GPT reply 2 (full sign-off) → Opus take + CEO lock. Both frontier models agree on this exact direction.*

*Cross-family review pass 1 (GPT 5.5 Pro Extended, 2026-06-09): verdict FIX-FIRST · 16 items passed clean · 13 findings (3×P1, 7×P2, 3×P3) — **all adopted**, implemented lean per the anti-bloat ceiling (actor-ledger derived, P3-queue folded). New homes: 9 load-on-demand templates. New memory: LESSON-CARD/PRIVACY/PROVISIONING-001 + EVAL-006/007. Opus value-adds on top of GPT: fixture exit-rule, frozen+cloud-safe packet hashing, enforce-don't-document (cx check rejects un-traced/same-family cards). → Awaiting GPT confirming pass → CEO lock.*

*Cross-family review pass 2 (GPT 5.5 Pro Extended, 2026-06-09): all 13 pass-1 findings CONFIRMED resolved; 4 NEW consistency holes found — all introduced by the pass-1 fixes themselves: **P2-N1** same-family-substitution rule conflicted across 5 files (allowed in WORK-ORDER/ROUTING, hard-rejected in CX-CHECK/EVALS/GATES) · **P2-N2** folded P3-queue needed item-level fields in STATE, not just counts · **P2-N3** stale `LESSON-HONESTY-001` ("no test edits") vs the new fix-card test rule · **P3-N4** Charter EVAL count (5→7) + work-order field-list drift. **All 4 fixed**, plus Opus extended P2-N1 with a provisional `CROSS_FAMILY_RECHECK_PENDING` finding that blocks final-ready (a substitution is an IOU, never a satisfied checkpoint). Trajectory 13→4 = healthy convergence. → Awaiting GPT confirming pass 3 → CEO lock.*

*Cross-family review pass 3 (GPT 5.5 Pro Extended, 2026-06-09): all 4 pass-2 findings CONFIRMED resolved; 2 small stragglers of the same stale-reference class — **P2** `LESSON-CARD-001` still carried the old hard-reject wording (memory is load-bearing → re-injection risk) · **P3** `recheck_when_opposite_family_available` default `yes` was misleading. **Both fixed.** Opus also ran a full tree-sweep (grep) and fixed a 3rd straggler GPT didn't flag (the `forbidden_files` test-file example) + added `owner_card` to `CROSS_FAMILY_RECHECK_PENDING` (GPT §3 nuance), and logged the recurring drift-class to the Kaizen queue as **PBF-PROP-001** (a `cx check` consistency-lint). Trajectory 13→4→2 = converging. → Awaiting GPT confirming pass 4 (expect PASS) → CEO lock.*

*Cross-family review pass 4 (GPT 5.5 Pro Extended, 2026-06-09): **PASS.** All pass-3 fixes confirmed; no remaining protocol-document blocker; same-family-substitution rule consistent across all surfaces; folded P3-queue sound; `CROSS_FAMILY_RECHECK_PENDING` extension endorsed; PBF-PROP-001 endorsed as the right systemic fix. Trajectory 13→4→2→**0**. **Both frontier models sign off. V1 ready to lock; the only remaining work is building the `cx check` script (first task under V1).** → Awaiting CEO lock.*

*ROUND-4-LOCK-BUNDLE addendum (2026-06-10, CEO-approved): after `cx check` passed 3 GPT rounds + the contract-bite harness was built, a fresh-eyes same-family review (Claude Fable 5) + 3 GPT 5.5 Pro reply rounds converged on a frozen final pre-lock bundle — `cx` round-4 split (behaviour-preserving) · `cx check deck` reverse-coverage gate + `requirements-manifest.yaml` inside the frozen packet hash (PB-PROP-001; closes the packet→deck direction G1 lacked) · `cx check state --session-start` git/worktree continuity guard (ancestor-of-HEAD; the branch-loss scar) · drift cleanup scoped to rule-bearing files · inert catch-rate + CEO-attention sensor fields (observe first; no gate pruned before 2–3 real projects) · protocol-change provenance one-liner (KAIZEN) · BF-PROP-001 · PROP-009 · PROP-010 (retired) queued (evidence freshness · capsule extraction · Claude-hook experiment — never canonical). Scope frozen in `checkers/BUILD-CARD-round4-lock-bundle.md`; nothing else enters pre-lock. → one confirming GPT review → CEO locks V1.*

*🔒 **V1 LOCKED CANONICAL (2026-06-10, CEO).** GPT 5.5 Pro round-4 confirming review = **PASS** ("safe to lock V1 canonical"; all §4 implementation calls A–J CONFIRMED) + orchestrator (Fable 5) tree-verified synthesis per PBF-PROP-005 — every claim checked against the tree, evidence suite re-run fresh at `b96c3aa` (93 tests OK · 41 gate clauses bite + 2 heuristics · consistency PASS · no rejected concept present). One delta surfaced honestly (consistency soft-WARN count 38 vs reported 5 — advisory-only, mechanical) → PBF-PROP-007. At lock: PBF-PROP-001 · PBF-PROP-002 · B-PROP-001 · PBF-PROP-003 · PBF-PROP-005 · PB-PROP-001 → Applied; PBF-PROP-005 folded into GATES "Review methodology"; **PBF-PROP-004 DEFERRED by CEO (bundled with PBF-PROP-007, first post-lock housekeeping)**; first proof project remains **CEO_DEFERRED (Sample | live-production_V2_REDO — never assumed)**. v0.13 archived: tag `code-x-v0.13-final` on `refs/heads/Code-X`; its `PROTOCOL-VERSION.md` pointer flipped to V1. Synthesis record: `design-history/code-x-v1-round4-confirming-review-synthesis-2026-06-10.md`.*

*First-proof decision (2026-06-10, later same day, CEO): **first proof = Sample**, on its OWN branch (`Sample`, not main; main queued for a cleanup session), fresh session, staggered — **a live-production build migrates to V1 second**, at the clean boundary after its in-flight audit/fix session lands (rebuild per module under V1, not patch). Seats: Orchestrator + Planner & Architect = Fable 5 max effort · cross-family = GPT 5.5 xhigh. The GPT-only Sample plan = draft input, no approvals carry over. Record: `handoffs/handoff-2026-06-10-first-proof-sample.md`.*
