# Code-X V1 — Locked Direction Charter

**Status:** 🔒 DESIGN LOCKED — 2026-06-09 (4-pass cross-family review complete: 13→4→2→0, GPT 5.5 Pro **PASS**; CEO locked). Next: build `cx check` → then V1 canonical + v0.13 archived.
**Signed off by:** Opus 4.8 Max + GPT 5.5 Pro Extended (3-way council, fully converged — "zero open direction seams")
**Locked by:** the user (CEO / decider)
**Credits (CEO directive 2026-06-11):** the user (CEO) · Claude Opus 4.8 · GPT 5.5 Pro · **Claude Fable 5** — involved from the moment it launched: round-4 fresh-eyes review → lock synthesis → PROP-013/014/015 + subsequent protocol sessions. Code-X is the work of all four, not a fixed pair.
**This file is:** the single source of truth for *what was decided and where it lives*. The mechanics live in the actual V1 files; this charter is the decision record + file manifest + build/review plan. Don't restate mechanics here — point to the file.

---

## 1. Why V1 exists (the two problems it must kill)

1. **Too expensive** — Code-X v0.13 burned the weekly limit of *both* $200 subscriptions (Claude Max + Codex) in ~2.5 days.
2. **Didn't work** — the last big build (a restaurant-ops app v2) shipped broken-looking, because visual quality was a *requirement* but not an *executable gate*; reviews checked code, not the running app. *"Codex built the wrong thing successfully."*

## 2. The mission (unchanged soul)

- **Goal A — ships working software** a non-coder can show users/devs *proudly*.
- **Goal B — token-efficient** enough that the subscriptions last the *whole week*.
- **Soul:** a non-coder → professional-team-quality full-stack apps, working from the get-go, **never debugging, never reading stack traces, never accepting "known issues."**
- **The CEO is an AI build director:** *directs the engineering system that directs the AI* — not the code.
**The soul in three lines (canonical phrasing — CEO intent, wording refined + approved 2026-06-11; raw CEO words preserved in ledger A-002):**
1. **Capability** — Code-X turns a non-coder into an **AI build director**: the CEO directs the engineering system, the system directs the AI, and the output is real, working software to the standard of a professional dev team — shipped proudly, never debugged by the CEO, zero "known issues."
2. **Efficiency** — token and work efficiency is an **obsession, not a preference**: every read, review, and loop must earn its cost; waste is made visible and the largest source removed first; the subscriptions last the whole week.
3. **Kaizen** — the protocol **improves itself continuously**: every mistake — *and every review* — becomes a lesson, every new failure-class becomes a mistake-proofing eval, every change leaves the system leaner — the system learns from *how it works*, not only from *what it builds*. *(reviews added at PROP-017 fold 2026-06-11: learning is review-triggered, not only mistake-triggered)*

- **Core value (CEO): the Toyota Way / Kaizen — applied to the WHOLE protocol, not just tokens.** Continuous improvement on three fronts: eliminate waste (tokens), **learn from every pipeline/protocol mistake**, and **streamline the protocol over time**. Make problems *visible* (cost log + incidents + evals), fix the root cause, then lock the fix in as a lesson AND a mistake-proofing eval so it can never recur. (Engine: §4 "The Kaizen engine.") *"I am the system, and the system is part of me — it must learn and evolve from every mistake."*

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
- **Enforcement = Level A (plain files) + Level B (tiny checkers). NO Level C (full orchestrator/runner) now.** Revisit only after V1 proves itself on 2–3 projects.
- **`cx check` = ONE command surface** with subcommands (`card`, `state`, `scope`, `evidence`, `cost`, `final-ready`). Never a sprawl of scripts; never `cx run`/`orchestrate`/`auto-route`/`self-mutate`.

**Work orders & cards**
- **Card compiler = a top-model AI planning task** (reads the locked packet once → emits the full work-order deck).
- **Card auditor = opposite-family top model** — and this audit **IS** the main pre-build cross-family checkpoint (do *not* stack a second full cross-family review on top). *(Opus sharpening #2.)*
- **Card Compilation Gate is mandatory:** compiler compiles, opposite-AI audits, tiny checker validates shape/scope/budget. A bad card is more dangerous than a long packet.
- Work-order fields: id, mode, actor, model_tier, objective, **source_map, card_compilation, actor_record, family_note,** read(required/forbidden), allowed/forbidden files, allowed/forbidden ops, relevant_invariants, acceptance, evidence_required, security_tripwire, loop_budget (review_fix_cycles + self_heal_attempts), stop_conditions, cost_budget, state_update.

**Build factory**
- **Per-module build + CEO approval before the next module.** Long autonomous / program-seal build is **retired** (it caused a real end-surprise on a prior project). Modules sized so approval takes **minutes, not hours**.
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
- **Redo halfway projects under V1** (e.g. Project A v2, Project C) rather than limping on v0.13 — **but PORT their existing planning/decisions** (requirements, money rules, locked decisions); they re-run through V1's *build factory*, they are NOT re-planned from zero. *(Opus practicality add — makes the bold call cheap.)*
- Every project carries a `protocol_stamp` (Code-X V1 | v0.13) during the switch so old and new rules never mix in one build.
- **First proof build = `CEO_DEFERRED`** (recorded 2026-06-09; candidates: any in-flight project). CEO decides after V1 is locked.

**Machine-readable (GPT reply-3):**
```yaml
legacy_protocol_policy:
  v0_13_live_status: RETIRED_ON_V1_APPROVAL
  v0_13_role: ARCHIVE_AND_LESSON_SOURCE_ONLY   # archived as history + memory, NOT deleted as knowledge
  in_flight_projects: REPLAN_OR_RECARD_UNDER_V1
  mixed_protocols_for_one_project: FORBIDDEN

first_proof_project: CEO_DEFERRED   # CEO sets after V1 lock (PROJECT_A_REDO | PROJECT_B | CEO_DEFERRED)
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

*Cross-family review pass 3 (GPT 5.5 Pro Extended, 2026-06-09): all 4 pass-2 findings CONFIRMED resolved; 2 small stragglers of the same stale-reference class — **P2** `LESSON-CARD-001` still carried the old hard-reject wording (memory is load-bearing → re-injection risk) · **P3** `recheck_when_opposite_family_available` default `yes` was misleading. **Both fixed.** Opus also ran a full tree-sweep (grep) and fixed a 3rd straggler GPT didn't flag (the `forbidden_files` test-file example) + added `owner_card` to `CROSS_FAMILY_RECHECK_PENDING` (GPT §3 nuance), and logged the recurring drift-class to the Kaizen queue as **PROP-001** (a `cx check` consistency-lint). Trajectory 13→4→2 = converging. → Awaiting GPT confirming pass 4 (expect PASS) → CEO lock.*

*Cross-family review pass 4 (GPT 5.5 Pro Extended, 2026-06-09): **PASS.** All pass-3 fixes confirmed; no remaining protocol-document blocker; same-family-substitution rule consistent across all surfaces; folded P3-queue sound; `CROSS_FAMILY_RECHECK_PENDING` extension endorsed; PROP-001 endorsed as the right systemic fix. Trajectory 13→4→2→**0**. **Both frontier models sign off. V1 ready to lock; the only remaining work is building the `cx check` script (first task under V1).** → Awaiting CEO lock.*

*ROUND-4-LOCK-BUNDLE addendum (2026-06-10, CEO-approved): after `cx check` passed 3 GPT rounds + the contract-bite harness was built, a fresh-eyes same-family review (Claude Fable 5) + 3 GPT 5.5 Pro reply rounds converged on a frozen final pre-lock bundle — `cx` round-4 split (behaviour-preserving) · `cx check deck` reverse-coverage gate + `requirements-manifest.yaml` inside the frozen packet hash (PROP-007; closes the packet→deck direction G1 lacked) · `cx check state --session-start` git/worktree continuity guard (ancestor-of-HEAD; the branch-loss scar) · drift cleanup scoped to rule-bearing files · inert catch-rate + CEO-attention sensor fields (observe first; no gate pruned before 2–3 real projects) · protocol-change provenance one-liner (KAIZEN) · PROP-008/009/010 queued (evidence freshness · capsule extraction · Claude-hook experiment — never canonical). Scope frozen in `checkers/BUILD-CARD-round4-lock-bundle.md`; nothing else enters pre-lock. → one confirming GPT review → CEO locks V1.*

*🔒 **V1 LOCKED CANONICAL (2026-06-10, CEO).** GPT 5.5 Pro round-4 confirming review = **PASS** ("safe to lock V1 canonical"; all §4 implementation calls A–J CONFIRMED) + orchestrator (Fable 5) tree-verified synthesis per PROP-006 — every claim checked against the tree, evidence suite re-run fresh at `b96c3aa` (93 tests OK · 41 gate clauses bite + 2 heuristics · consistency PASS · no rejected concept present). One delta surfaced honestly (consistency soft-WARN count 38 vs reported 5 — advisory-only, mechanical) → PROP-012. At lock: PROP-001/002/003/004/006/007 → Applied; PROP-006 folded into GATES "Review methodology"; **PROP-005 DEFERRED by CEO (bundled with PROP-012, first post-lock housekeeping)**; first proof project remains **CEO_DEFERRED (PROJECT_B | PROJECT_A_REDO — never assumed)**. v0.13 archived (tag `code-x-v0.13-final`); its `PROTOCOL-VERSION.md` pointer flipped to V1.*

*First-proof decision (2026-06-10, later same day, CEO): **first proof = Project B** (a personal-finance app), on its OWN branch, fresh session, staggered — **Project A v2 (a restaurant-ops app) migrates to V1 second**, at the clean boundary after its in-flight audit/fix session lands (rebuild per module under V1, not patch). Seats: Orchestrator + Planner & Architect = Fable 5 max effort · cross-family = GPT 5.5 xhigh. Any prior GPT-only draft plan = draft input, no approvals carry over.*
