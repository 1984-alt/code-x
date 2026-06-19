# Help Wanted — Autonomous Build/Session Loop for Code-X

## The gap

Code-X has a tight **build → fix → review loop *inside* a single session**. It does **not** have a **session-level loop**.

Today an operator has to babysit the run: watch how full the conversation is, save a handoff, and re-enter in a fresh session to continue. But once planning is locked, **most of the build stage needs no human input** — so that monitoring is largely wasted effort.

## The goal

A loop that drives Code-X's build stage **hands-off** and **stops only when human input is genuinely required**.

## The only valid stops (loop halts and asks the human)

- A business decision the locked plan did not pre-decide.
- Ambiguity or a conflict the frozen packet doesn't resolve.
- The 4-failure cross-family escalation fires (auto-fix exhausted).
- Built-App Audit findings need disposition.
- Version lock / publish.

Anything else in the build stage → keep going, card by card.

## Build on existing primitives (don't reinvent)

The host tools already ship most of the machinery — a contributor should wire these, not rebuild them:

- Self-paced loop running (e.g. Claude Code `/loop` with no interval).
- Scheduled agents (run a wave overnight) and background agents (kick off, get notified).
- Automatic cross-session context summarization (the manual save → copy → paste-into-fresh-session step is largely obsolete already).

**The actual contribution = the Code-X policy layer:** a machine-readable stop-condition list + an auto re-entry that reads `CODE-X-STATE.yaml` / the handoff and resumes the build, wired so the loop respects every gate.

## Guardrails (non-negotiable)

Autonomous ≠ safe to leave fully unwatched. A loop can run *confidently in the wrong direction* and burn time and money. Any implementation MUST include:

- A spend / iteration cap.
- The existing G-gates as hard stops.
- The Built-App Audit as the "built + green ≠ wired and running" catch.

## Out of scope

- Replacing or weakening the gates.
- Removing human sign-off at lock / publish.

## Why this is a good first or intermediate contribution

It's additive (a policy + re-entry layer over existing host primitives), it has a crisp done-definition (the stop-condition list above), and it has built-in safety rails the protocol already defines. A capable contributor can land it without touching the core gate logic.

---

# Help Wanted — Trust-Boundary Hardening / Forge-Parity

## The gap

`cx` is deterministic, but it reads artefacts the AI itself authored (the state file, cards, receipts). The protection today is the *stack* — deterministic check + opposite-family review + a fresh cold-reader + the human — not a hard wall inside the checker. Two concrete pieces are open:

- **Forge-parity recompute (`/cx-accept`).** A few acceptance-receipt fields (`state_sha_before`, `quality_card_hash`) are currently presence-asserted, not recomputed from source. A runner that recomputes them end-to-end would make the acceptance wall machine-forged rather than partly ceremonial.
- **Boundary probing.** An explicit map of which artefacts the agent can author vs which the checker independently controls — plus adversarial tests that *try* to forge a green, to find where the stack actually holds and where it doesn't.

## Why this is a good contribution

It targets the deepest, most-cited critique of the whole design. It's additive (a recompute runner + tests; no change to existing gate logic), and a passing/failing adversarial test is a crisp done-definition.
