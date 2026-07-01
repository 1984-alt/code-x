# Code-X V1 — ROUTING (model tiers + per-family notes)

> The card names the `model_tier`. If it doesn't, the default is **NOT top model**. **Cost-effective by default** (CEO 2026-06-10): the cheapest model that reliably succeeds FIRST PASS for the task class — a redo is the most expensive token; mini/spark/haiku-class never writes app code. Pay for top only where it earns its keep. On a *subscription* (weekly usage limit), top models burn the limit fastest — so routing IS Goal B. **Exact per-engine seats (model + effort per role, Claude Code AND Codex App): `BUILD-ENGINE-PROFILES.yaml`** — the Card Compiler injects them into every card; no actor guesses.

## Tiers — what runs where
**TOP** (Opus 4.8 xhigh · GPT-5.5 high/xhigh) — only for: product taste · architecture · money/business rules · security/privacy · **card compilation** · **card audit** · cross-family review · final-ready review · ambiguous failures. (Claude: Fable 5 high + GPT: gpt-5.5-pro cloud are the CRITICAL-JUNCTION tier above this — Fable xhigh extraordinary-only, Fable max NEVER, Opus effort max retired; CEO 2026-06-11 — see the seat ladders + `fable_window` sunset in `BUILD-ENGINE-PROFILES.yaml`.)

**STANDARD / CHEAP** (Sonnet · Haiku · gpt-5.4 · gpt-5.3-codex-spark) — for: formatting · grep/catalogue · running tests · simple file updates · evidence indexing · status summaries · small mechanical lint · screenshot inventory · non-risky copy edits · routine module code (STANDARD floor — never mini/spark-class).

**Codex long autonomy** — TODAY, for **bounded** backend/data/test cards only. NOT subjective UI taste. NOT unbounded fix loops. **Long-autonomous FULL build (incl. UI to completion) is a stated long-term GOAL, switched OFF until the reliability bar is proven** (CHARTER §"Long-autonomous milestone"); until then the per-module see-and-test gate (PBF-PROP-012 Part E, `MODULE-DEMO-MISSING`) structurally forbids hands-off UI — see KERNEL R-ORCH + Part E. This is "not yet", not "never".

**FIXING STAGE (F-PROP-001)** — a fix card runs at the same tier its `fix_target` would (a `frontend` fix = UI-taste tier; a `business_rule` fix = money/business-rule TOP tier). The reviewer is the **opposite family** of the fixer, as always; a fix that touches money / a danger class is a **mandatory cross-family money review** (G5 high-risk foundation rule) — a preserve-posture fix is still a real diff. The `fixing_stage` seat profile in `BUILD-ENGINE-PROFILES.yaml` caps the orchestrator; `cx check state` bites if `current_stage: FIXING_STAGE` has no seat profile.

**Default + escalation:** no `model_tier` on a card → not top model. Cheap worker fails once → may retry once; fails again → escalate a tier or raise a STOP card.

## Per-family notes (ONE protocol, tuned leashes — NOT two protocols)
**Codex (GPT family)**
- Reach: same-family only (cannot call Anthropic). Self-heal ladder = 3 bounded attempts → raise `STOP_CARD: CODEX_TO_CLAUDE_HANDOFF` → hand to Claude Code (carry the dead-ends ledger).
- Known quirk: **tends to loop** (re-reviews its own changes). The one-and-done `loop_budget` cap (GATES G5) binds you hardest — obey it; do NOT re-review after the batch fix.
- Strength: bounded "implement these locked invariants + run tests" cards.

**Claude (Anthropic family)**
- Reach: both families (native + Codex via MCP/CLI). Self-heal ladder runs the full cross-family alternation, ending in a synthesizing final attempt before any CEO escalation.
- Known quirk: can over-explain / over-read — obey the kernel's anti-bloat read law; read only what the card names.
- Strength: taste / architecture / ambiguous-failure cards; leading a continuation after a Codex hand-off.

Same rules for both; only the leash is tuned where each model actually slips.

> **Cross-family availability (operational):** the card-audit / cross-review MUST be the opposite family. If that family is at its weekly/session limit, options are (a) wait, or (b) CEO authorises a fresh cold-start *same-family* reviewer as a temporary stand-in — recorded as `cross_review.family_substituted: yes` **with a `ceo_authorization_ref`**, which **opens a `CROSS_FAMILY_RECHECK_PENDING` finding that blocks final-ready** until the opposite family re-reviews. A same-family stand-in is a provisional IOU, **never** a satisfied cross-family checkpoint. Never silently skip the cross-family check because a family is busy.

## BUILD-stage per-module demo loop (PBF-PROP-012 Part E, SEE-AND-TEST)

For every `live_slice` module, the per-module loop is:

1. **Builder finishes** the module (verify-app agent drives → passing `verify_app` receipt).
2. **Orchestrator demos on the correct surface** — web: open `live_url` in Chrome; mobile: open in iPhone 13 Pro simulator. Capture a real screenshot (machine-stamped; hash-bound into `module_demo.shown_screenshot_hash`).
3. **CEO drives + types accept token** — the CEO opens the running build, drives it, and types a distinct accept token embedding the build's `repo_sha` prefix (e.g. `ACCEPT-m_live-7d1408`). The orchestrator records the token in `module_demo.ceo_accept_token` + `live_slice_accept.ceo_accept_token`, and resolves `module_demo.ceo_turn_ref` to the CEO's actual message artifact (handoff / transcript line). If `ceo_verdict: needs_fix`, the module is NOT accepted — fix and re-demo.
4. **Next module unblocks** — once `module_demo.ceo_verdict: accepted` + all preconditions (verify_app + module_demo) pass, `validate_live_slice_accept` clears and the Andon wall releases the next slice.

The `module_demo` block is a P0 **precondition** inside `validate_live_slice_accept` — enforced by both the order wall (`cx check module-start`) and `cx check module-quality`. Neither accepts the module without it. Standalone early-catch: `cx check module-demo --acceptance <receipt> [--repo-root <r>]` (mirrors `cx check verify-app`). Session declares intent at session-start: `session_start.module_demo_mode: {demo_every_user_facing_module: yes}` (P2 ack, `cx check state --session-start`). Backend-only builds carry `no_user_facing_modules: yes + ceo_decision_ref` waiver instead.
