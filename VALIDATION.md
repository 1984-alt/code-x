# Validation so far

Code-X has been used by the author across **two real personal projects** before public release — a personal-finance tracker and a small-business operations dashboard. (Both are private; they're described here by category only.)

## What it helped catch

- **spec drift** — the build quietly wandering from what was agreed
- **skipped evidence** — a "done" with nothing actually proving it
- **premature "done"** — features reported finished while still half-wired
- **review-loop waste** — re-reviewing the same thing without converging
- **stale handoff / resume-state** — losing the thread between sessions

These are the exact failure modes Code-X's gates, evidence requirements, and handoff discipline exist to stop. They showed up, and the protocol caught them — which is most of why it exists at all.

## How protocol changes were reviewed

Major protocol changes were **cross-reviewed by both Anthropic and OpenAI model families**; review findings were folded into the checker and the protocol where possible. That's deliberately worded as a process, not a seal of approval — it is *not* "reviewed and approved by two AIs." See [`reviews/`](reviews/) for a summarised, inspectable trail.

## The honest limit

This is still **single-operator validation** — one person, two projects. No independent user has completed a public end-to-end build yet. So treat Code-X as **personally proven, not publicly proven**. Closing that gap — getting real reproduction by other people — is exactly what this public release is for.
