# Validation so far

Code-X has been used by the author across **two real personal projects** before public release — a personal-finance tracker and a small-business operations dashboard. (Both are private; they're described here by category only.)

**Scope note:** Code-X's rules were shaped across *many* attempted builds over time — including failed and abandoned ones, which is where its weaknesses surfaced. The validation below is narrower and more honest: the **current public version** was tested on fresh rebuilds of these two projects before release — not on every project that shaped it.

## What it helped catch

- **spec drift** — the build quietly wandering from what was agreed
- **skipped evidence** — a "done" with nothing actually proving it
- **premature "done"** — features reported finished while still half-wired
- **review-loop waste** — re-reviewing the same thing without converging
- **stale handoff / resume-state** — losing the thread between sessions

These are the exact failure modes Code-X's gates, evidence requirements, and handoff discipline exist to stop. They showed up, and the protocol caught them — which is most of why it exists at all.

## A concrete case: cutting a review loop

One real example of "review-loop waste," from the personal-finance tracker. A bank-statement parser — the most safety-critical module, since it handles real money — went through **nine review passes** before it was signed off. Some of that was the reviews doing their job: an early sign-off was *correctly* thrown out when a real bug surfaced on live data. But part of it was the same module being re-reviewed round after round without converging — exactly the waste the protocol now targets.

A rule was then added (folded 2026-06-18): each review runs **once per module**, and a fix is proven by a deterministic check plus a pinned test — never by another round of AI review. Modules built since then have closed in a **single review pass**.

Honest caveats, on purpose:

- This is **one case, not a benchmark**. The nine-pass module was the highest-risk one (real money); later single-pass modules were lower-risk (mostly UI) — so it is *not* an apples-to-apples comparison.
- Some of those nine passes were **genuine bug-catching, not pure waste** (see the voided sign-off above).
- The **token cost was never logged**, so there are **no before/after token numbers to publish** — only the review-pass counts above.

Take it as an illustration of the loop the gates are built to prevent, not as proof of a savings figure.

## How protocol changes were reviewed

Major protocol changes were **cross-reviewed by both Anthropic and OpenAI model families**; review findings were folded into the checker and the protocol where possible. That's deliberately worded as a process, not a seal of approval — it is *not* "reviewed and approved by two AIs." See [`reviews/`](reviews/) for a summarised, inspectable trail.

## The honest limit

This is still **single-operator validation** — one person, two projects. No independent user has completed a public end-to-end build yet. So treat Code-X as **personally proven, not publicly proven**. Closing that gap — getting real reproduction by other people — is exactly what this public release is for.
