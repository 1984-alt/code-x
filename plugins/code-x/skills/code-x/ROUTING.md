# Code-X V1 — ROUTING (model tiers + per-family notes)

> The card names the `model_tier`. If it doesn't, the default is **NOT top model**. **Cost-effective by default** (CEO 2026-06-10): the cheapest model that reliably succeeds FIRST PASS for the task class — a redo is the most expensive token; mini/spark/haiku-class never writes app code. Pay for top only where it earns its keep. On a *subscription* (weekly usage limit), top models burn the limit fastest — so routing IS Goal B. **Exact per-engine seats (model + effort per role, Claude Code AND Codex App): `BUILD-ENGINE-PROFILES.yaml`** — the Card Compiler injects them into every card; no actor guesses.

## Tiers — what runs where
**TOP** (Opus 4.8 xhigh · GPT-5.5 high/xhigh) — only for: product taste · architecture · money/business rules · security/privacy · **card compilation** · **card audit** · cross-family review · final-ready review · ambiguous failures. (Claude: Fable 5 high + GPT: gpt-5.5-pro cloud are the CRITICAL-JUNCTION tier above this — Fable xhigh extraordinary-only, Fable max NEVER, Opus effort max retired; CEO 2026-06-11 — see the seat ladders + `fable_window` sunset in `BUILD-ENGINE-PROFILES.yaml`.)

**STANDARD / CHEAP** (Sonnet · Haiku · gpt-5.4 · gpt-5.3-codex-spark) — for: formatting · grep/catalogue · running tests · simple file updates · evidence indexing · status summaries · small mechanical lint · screenshot inventory · non-risky copy edits · routine module code (STANDARD floor — never mini/spark-class).

**Codex long autonomy** — for **bounded** backend/data/test cards only. NOT subjective UI taste. NOT unbounded fix loops.

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
