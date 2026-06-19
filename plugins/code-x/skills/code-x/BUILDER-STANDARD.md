# Code-X V1 — BUILDER-STANDARD.md (the coding standard)

> Ported from v0.13 `CODE-X-BUILDER-STANDARD.md` at the PROP-014 fold (2026-06-10).
> v0.13's embedded Build-Runbook section is NOT ported — KERNEL/GATES/ROUTING own runbook
> duties in V1. [RULE:builder-standard-session-read]

## Read law (session-level — cards stay tiny)

The build engine reads this file **ONCE at session start**, NOT per card. Cards carry only
the compiler-injected invariant token `relevant_invariants: [builder-standard]`. The session
records the acknowledgment in state — `session_start.builder_standard_read` with `status:
PASS`, `file`, `hash` (sha256-12 of this file), `read_by`, `timestamp` — checked by
`cx check state --session-start` (P2 when missing in a build mode; hash mismatch = the
standard drifted since acknowledgment → re-read + re-acknowledge). Honest scope: the ack
proves WHICH version the session started from; it cannot prove the standard was internalized
— that is what module reviews are for.

## Build-session command rail (PROP-018, folded 2026-06-12)

A build session's protocol obligations are COMMANDS, not remembered prose (engine-agnostic —
Codex app and Claude alike). The paste-ready session prompt carries this rail VERBATIM:

```text
session start  -> cx check boot --state <state> --repo-root .     (then state the project /
                  current card / next actor, and wait or proceed only if state says proceed)
every card     -> cx check build-turn <card> --state <state> --repo-root .
turn end       -> cx check close-turn --state <state> --handoff <path>
protocol evals -> cx check evals          (protocol-change sessions; build sessions on demand)
```

No file edits, reviews, or builds before the boot check passes. After ANY CEO protocol
correction: stop, re-run the current-stage rail, record a PROTOCOL_INCIDENT (GATES, PROP-020)
— never patch only the named symptom and continue.
*✅ The four subcommands are BUILT + biting (2026-06-12) — run the rail verbatim; falling back
to constituent checks is no longer an allowed substitute.*

## Before the first code edit

Read the frozen packet slice your card names, this standard, then check the target codebase
for existing style, boundaries, helpers, tests, and naming conventions. On a self-heal
continuation or builder handover, also read the wave's DEAD-ENDS-LEDGER first — never repeat
a proven-failed approach; append each attempt's result so the ledger travels with the next
handover. If you cannot tell how to implement the card without guessing, write the question
or blocker and STOP — never invent product, data, UX, security, privacy, money, legal,
release, or architecture decisions.

## The 12 rules

1. **Build the smallest faithful implementation.** Do exactly the card's scope. No product
   expansion, no redesigning unrelated flows, no "improving" nearby code the card didn't allow.
2. **Follow the existing project style.** Match language, framework, folder layout, naming,
   formatting, state patterns, test style, error style, helper APIs. Style conflicts with a
   clear safety rule → stop and ask.
3. **Respect architecture boundaries.** UI, domain logic, API/client, persistence, config,
   tests stay in their existing layers; moving responsibility needs an explicit instruction.
4. **Use readable names.** Names say what a thing means in the domain language. No `data`,
   `thing`, `stuff`, `handleIt`, `temp2`.
5. **Keep functions and components simple.** Small units, one clear job. If a reader cannot
   quickly follow the control flow, split or simplify — no clever one-liners hiding complexity.
6. **No speculative abstractions.** No new framework, service layer, generic engine, base
   class, hook family, or "future-proof" API unless the current scope needs it and the
   codebase pattern supports it.
7. **Never create fake production paths.** No mock-only production code, fake success
   fallback, placeholder records, faker/random production data, lorem ipsum, demo-only auth,
   silent bypass, dummy integration.
8. **Handle errors honestly.** Fail visibly enough for the caller/user/operator to understand
   the state without leaking sensitive detail. No empty catches, swallowed failures, or
   success UI after failed work.
9. **Security and privacy by default.** Validate untrusted input at the trusted boundary;
   authorize on the trusted side; never log secrets, tokens, cookies, PII, raw private
   payloads; config and secrets stay out of source.
10. **Be restrained with dependencies.** Existing dependencies and platform APIs first. No
    install/upgrade/new dependency unless the card explicitly allows it or you stop for approval.
11. **Map tests and evidence to acceptance criteria.** Every behavior change carries proof
    that traces to the card's acceptance criteria: unit/domain for logic, integration for
    contracts, UI/runtime evidence for user-facing behavior.
12. **Leave the code easier to review.** No unrelated formatting, renames, moves, or
    refactors in a build change; a needed refactor happens in small behavior-preserving
    steps backed by tests.

## Stop instead of guessing

Technical failures (compile/type/lint/test errors, missing harness) are **self-heal-zone** —
fix them via the self-heal ladder, never stop for the CEO. Return `FIX-FIRST`/`STOP` only
for **decisions you must not invent**:

- the frozen packet slice is missing, stale, unclear, or the packet floor never passed
  (`cx check packet`);
- the needed file is outside `allowed_files`, or the work would break an architecture boundary;
- a required product, UX, data, security, privacy, legal, money, release, or architecture
  decision is missing;
- production behavior would need mock, fake, placeholder, or invented data;
- a new dependency or package upgrade appears necessary but is not approved;
- a security/privacy concern cannot be resolved inside the card;
- the card touches CEO-accepted UI screens (templates/static/HTML routes, or purges Mode A
  fixtures) but does NOT carry the `ui_contract` locked visual artifacts in its read set —
  **never infer the visual contract** (PROP-019; a real scar from an engine build wave: approved shells deleted,
  generic templates built, all checks green).

## Builder self-check (written into the card's evidence before claiming done)

```text
Builder standard self-check:
Card ID:
Standard file: Code-X-V1/BUILDER-STANDARD.md (hash: <sha256-12>)
Smallest faithful implementation: PASS | FIX-FIRST | STOP
Existing style followed: PASS | FIX-FIRST | STOP
Architecture boundaries respected: PASS | FIX-FIRST | STOP
Readable names: PASS | FIX-FIRST | STOP
Simple functions/components: PASS | FIX-FIRST | STOP
No speculative abstractions: PASS | FIX-FIRST | STOP
No fake/mock/placeholder production paths: PASS | FIX-FIRST | STOP
Error handling honest and visible: PASS | FIX-FIRST | STOP
Security/privacy defaults preserved: PASS | FIX-FIRST | STOP
Dependencies unchanged or approved: PASS | FIX-FIRST | STOP
Tests/evidence mapped to acceptance criteria: PASS | FIX-FIRST | STOP
Code easier to review than before: PASS | FIX-FIRST | STOP
Unresolved stop decisions:
Verdict: PASS | FIX-FIRST | STOP
Evidence paths:
Actor + timestamp:
```

A module cannot clear its review checkpoint unless this verdict is `PASS`, or the CEO
explicitly accepts a documented exception. Project-specific deltas to this standard live in
the packet (coverage-map category 20), never as silent local conventions.

**Plain-talk lens (`VOICE.md`) — judgment, NOT a deterministic check:** model reviews ALSO
check that CEO-facing text (status updates, questions, stop cards, summaries) obeys `VOICE.md`
— flag undefined jargon, walls of prose, or un-decidable questions as a finding (rides the
existing one-pass fix rule).
