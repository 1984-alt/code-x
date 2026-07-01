# Code-X V1 — BUILDER-STANDARD.md (the coding standard)

> Ported from v0.13 `CODE-X-BUILDER-STANDARD.md` at the P-PROP-001 fold (2026-06-10).
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

## Build-session command rail (B-PROP-002, folded 2026-06-12)

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
correction: stop, re-run the current-stage rail, record a PROTOCOL_INCIDENT (GATES, BF-PROP-002)
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

## The do-less ladder (B-PROP-005 — prevention, not review) [RULE:builder-prevention-preamble]

> **Orchestrator injection (PBF-PROP-012 Part C):** this ladder is the canonical builder prevention preamble — the orchestrator MUST inject it as the prevention preamble into the builder subagent's prompt before every builder dispatch on every engine. The Card Compiler records the injection in `execution.prevention_preamble`; `cx check card` bites if absent.

Before writing code for a card, **decide what NOT to build first.** Walk these rungs in order;
take the highest one that honestly satisfies the card, then stop climbing. This is a PREVENTION
gate walked before the first edit — not the post-build anti-slop cure.

1. **Need-to-exist.** Does this need to exist at all? If the card's goal is met without it,
   build nothing (YAGNI on the feature, not just the abstraction).
2. **Built-in toolkit.** Does the language / framework standard library already do it? Use it
   rather than hand-roll it.
3. **Native platform feature.** Does a native platform capability cover it — `<input
   type="date">` over a picker library, CSS over JS, a database constraint over app code? Prefer it.
4. **Installed dependency.** Does a dependency already in the project cover it? Reuse it; never
   add a new one to dodge this rung (Rule 10 still governs every install).
5. **Readable one-expression.** Can it be one readable expression instead of a new function,
   class, or module? Write the small thing.
6. **Minimum.** Build the smallest faithful slice that satisfies the card — nothing it did not
   ask for, no scaffolding for a future that has not arrived.

**The ladder NEVER cuts** these, even when a leaner rung would "save code": input validation at
trust boundaries, error handling that protects against data loss, security, accessibility, the
card's required tests, anything the card explicitly requested, and any **CEO-locked design / UI
contract** (a native-feature rung must bow to a locked golden master — G3/G6 design-fidelity).
If a leaner rung would break any of these, do not take it.

Honest overlap: rung 1 ≈ Rule 1, rung 4 ≈ Rule 10, rung 6 ≈ Rule 6 — the NEW value is the
ORDERED front gate (rungs 2/3/5) and the timing (decide-less *before* code). Two ideas are
explicitly **NOT** imported from the source it came from: "minimal prose / code-first" (it
fights plain-English for a non-coder CEO — `VOICE.md`) and "YAGNI applies to tests too" (it
fights the verification spine — green ≠ enforcing). Prose and tests are never what you cut.

## Fixing-stage rules (F-PROP-001 — preserve, don't improve)

When the card's job is to REPAIR an existing surface (`mode: FIX`, any fix — even a mid-build
self-heal), the posture flips from CREATE to **PRESERVE: change only the defect.** These rules apply to
EVERY fix; only the *heavy ceremony* (structural re-freeze + CEO re-accept) scales up when the fix
touches an already-accepted / locked artifact (CEO-D-FIX-B). [RULE:fixing-stage-preserve-posture]

- **Always-read hard rule:** **never create, rename, move, delete, or refactor "for improvement"; if a
  fix seems to need a structural change, STOP and ask.** Look and structure must not wander. A fix is
  scoped to its declared `fix_targets`; everything else is frozen (`cx check structure` proves the file
  tree did not move outside `allowed_files`).
- **Never mix fix + improve:** a fix is *"fix the bug only, preserve everything else"* OR *"redesign
  only, no logic changes"* — never both in one card. **Forbidden during a fix unless the card names it:**
  layout · spacing · colours · typography · copy · component names.
- **SCREEN_CONTRACT per locked screen** (Purpose / Must-preserve / Forbidden): for a fix on an accepted
  screen, state what the screen is for, what must survive untouched, and what is off-limits — then
  **plan-then-wait scoped to risk:** show the plan and wait for CEO OK before editing a locked artifact
  or any product / UX / business / security / cross-target change. A compile/test self-heal iteration
  does NOT wait (that would grind the build) — but the preserve-rules above still bind it.
- **Anti-amnesia:** before re-asking the CEO a decision, **search the CEO-DECISION-LEDGER first.** A
  FIX-stage question must be file-backed (a `FIX-QUESTIONS-LOG` row or a STOP card) carrying
  `ledger_searched` + the related decision refs; an answer that CHANGES a locked rule needs a resolved
  `ceo_override_ref`, never a silent second decision. `cx check close-turn` reconciles it.
- **Revert-on-drift, never fix-forward:** if a structure/lock check fails, you do not patch over it —
  you produce a `revert_receipt` (bad_head → restored_head, clean post-revert diff) and re-approach
  tighter. No tool runs `git reset` for you; surfacing the drift and reverting is your job.

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
  **never infer the visual contract** (B-PROP-003; the Sample W4 scar: approved shells deleted,
  generic templates built, all checks green).

## Builder self-check (written into the card's evidence before claiming done)

```text
Builder standard self-check:
Card ID:
Standard file: Code-X-V1/BUILDER-STANDARD.md (hash: <sha256-12>)
Do-less ladder walked, built only what survived: PASS | FIX-FIRST | STOP
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
CodeRabbit receipt present for code-diff build cards: PASS | NOT_APPLICABLE | FIX-FIRST
Module self-review evidence recorded for module-quality: PASS | NOT_APPLICABLE | FIX-FIRST
Unresolved stop decisions:
Verdict: PASS | FIX-FIRST | STOP
Evidence paths:
Actor + timestamp:
```

A module cannot clear its review checkpoint unless this verdict is `PASS`, the required
CodeRabbit rail has a receipt, and module-quality carries same-family self-review evidence,
or the CEO explicitly accepts a documented exception. Project-specific deltas to this standard
live in the packet (coverage-map category 20), never as silent local conventions.

**Plain-talk lens (`VOICE.md`) — judgment, NOT a deterministic check:** model reviews ALSO
check that CEO-facing text (status updates, questions, stop cards, summaries) obeys `VOICE.md`
— flag undefined jargon, walls of prose, or un-decidable questions as a finding (rides the
existing one-pass fix rule).
