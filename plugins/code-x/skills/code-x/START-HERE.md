# Code-X V1 — START HERE (the map)

> This file is the MAP — read it once to learn the layout. What you read EVERY session is just the **KERNEL + state + your one card**.

## What Code-X V1 is (one line)
A lean, file-based system that turns a non-coder CEO's intent into shipped, working software — by handing each AI **one small work-order at a time**, building **module-by-module with CEO approval**, and **reviewing only what changed**. Soul: you direct the engineering system; it directs the AI; you never debug.

## The two stages
- **PLANNING STUDIO** (hands-on with CEO · top models) → product taste · decisions · architecture · security baseline · looks-first design · money-rule sign-off · then the work-order deck (G1 card-compilation gate).
- **BUILD FACTORY** (hands-off except approvals · cost-effective models by default) → Mode A → module (deterministic checks on every card) → demo → **one model review per module** → CEO approve → capsule → next module → P3-zero → final-ready certificate.

## Read order
1. **Every session:** `KERNEL.md` + the project's `CODE-X-STATE.yaml` + your ONE work-order + only the files it names. Nothing else.
2. **When a gate fires:** the matching section of `GATES.md` (+ `SEVERITY.md` for findings).
3. **When routing / escalating:** `ROUTING.md` (your family note is injected into your card, so you don't open this just for that).
4. **When improving the protocol / reviewing cost:** `KAIZEN.md`, `EVALS.md`, `MEMORY/`.

## File map
- `CHARTER.md` — the locked design (decisions + manifest). Reference.
- `KERNEL.md` — house rules, read every session.
- `VOICE.md` — plain-talk standard: how the AI talks to the CEO (plain, scannable, decisions decidable).
- `GATES.md` — G1 card-compilation … G8 final-ready. Load-on-demand.
- `SEVERITY.md` — the P0–P3 ladder.
- `ROUTING.md` — model tiers + per-family notes.
- `BUILD-ENGINE-PROFILES.yaml` — exact model+effort per role for BOTH engines (Claude Code / Codex App); the compiler injects per-card `execution` blocks; switching engines = one state line. Load-on-demand (compiler + session start only).
- `PACKET-CONTENTS.md` — the packet floor: 20 coverage categories · completeness-audit gate · CEO-DECISION-LEDGER (asks+decisions) · readiness triggers · builder standard. Read when WRITING a packet; `cx check packet` enforces the mechanical half.
- `BUILDER-STANDARD.md` — the 12 coding rules + stop-instead-of-guessing. **A build session reads it ONCE at session start** and records the ack in state (`session_start.builder_standard_read`, checked by `cx check state --session-start`); cards carry only the injected `builder-standard` invariant token.
- `KAIZEN.md` — continuous-improvement engine (waste + lessons + evals).
- `EVALS.md` — the protocol self-tests.
- `templates/` — STATE · WORK-ORDER · MODULE-CAPSULE · FINAL-READY-CERTIFICATE · WEEKLY-BURN · WORK-ORDER-COST-LOG · PRODUCT-TASTE-LOCK · DESIGN-GOLDEN-MASTER · BUSINESS-LOGIC-VALIDATION · CEO-PROVISIONING-MANIFEST · STOP-ACTION-CARD · DEAD-ENDS-LEDGER · BUILDER-QUESTIONS-LOG · EVIDENCE-INDEX · GOLDEN-SKELETON-CERTIFICATE · COVERAGE-MAP · CEO-DECISION-LEDGER. *(All load-on-demand — none sit in the every-turn read path.)*
- `MEMORY/` — LESSONS.yaml (seeded) · PROTOCOL-IMPROVEMENT-QUEUE.md · CEO-DECISION-LEDGER.md (protocol-level decisions; project packets carry their own).
- `checkers/` — `cx check` (Level-B mechanical checkers) + ported v0.13 checkers. `CX-CHECK-SPEC.md` describes them.

## One ops rule (continuity)
**One active project per working tree.** A parallel project gets its OWN git worktree — never share a working tree between concurrently-active projects (uncommitted work on a shared tree is one branch-switch from gone). At session start, `cx check state --session-start` verifies the state still belongs to this branch's history.

## What's NOT here (on purpose)
No full orchestration runner. No live token meter. No long autonomous UI build. No "read the whole protocol every turn."
