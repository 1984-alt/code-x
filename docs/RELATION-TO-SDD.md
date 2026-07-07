# Relation to Spec-Driven Development

> How Code-X relates to the plan-first / Spec-Driven Development movement (Spec Kit, Kiro, BMAD). Moved here from the [README](../README.md) to keep it focused; nothing below was shortened.

Code-X was built independently, from hands-on pain with AI coding agents — the author didn't know Spec-Driven Development existed. It later turned out to converge with it (Spec Kit, Kiro, BMAD, and the broader plan-first movement). That's not a precedence claim; SDD has been public since 2025. It's independent convergence — and honestly, that's reassuring: landing on the same shape independently is a decent signal the problem is real.

The shared baseline is plan-first development:

| Code-X | Spec-Driven Development |
|---|---|
| packet (frozen, hashed requirements + decisions + security baseline) | constitution → specify |
| technical plan (TRD, data/API contracts) | plan |
| card deck (each card traces to a frozen packet slice) | tasks |
| build stage, one card at a time | implement |
| `cx check deck` (deterministic reverse coverage) | analyze (often AI-driven) |
| Audit stage (read-only whole-app judgment + 13 ship gates) | — no direct equivalent |

What Code-X adds on top:

- **A deterministic checker.** `cx` is mechanical Python, not an AI checking an AI. For someone who can't read the code, a gate that *can't be talked around* is worth more than another model's opinion. This is the core difference.
- **The Master Blueprint.** The plan becomes one page a non-coder reviews and approves screen-by-screen, with readiness recomputed from source rather than taken on faith.
- **The Audit stage.** A dedicated, read-only 4th stage between Building and Fixing that verifies the finished app is actually wired and running — not just that requirements and tests look right (see the SOP section in the [README](../README.md)).
- **A non-coder framing,** plus an always-on security baseline and mandatory cross-family review (Spec Kit has both as well, in lighter, AI-generated form).

In one line: **a shared plan-first baseline, plus a deterministic checker, a reviewable Master Blueprint, and a non-coder framing — arrived at independently.**
