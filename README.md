# Code-X

[![tests](https://github.com/1984-alt/code-x/actions/workflows/tests.yml/badge.svg)](https://github.com/1984-alt/code-x/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![protocol](https://img.shields.io/badge/protocol-v1.22-orange.svg)

**Code-X is a build protocol for non-coders directing AI to build software — faithfully, without writing the code.** It's one Indonesian vibe-coder's answer to a specific, maddening problem.

AI coding tools that won't build what you actually meant. They drift, cut corners, and skip requirements, then report "all tests pass" on work that's broken — and if you can't read code, you can't catch any of it.

The method, in one breath: you lock the plan first and review it as a visual **Master Blueprint**; the AI then builds one small work-order at a time; a deterministic Python checker — not another AI — blocks dropped requirements, stale approvals, fake-done work, unsafe file paths, and many forms of drift from the locked plan; then, at each review checkpoint, a *different* AI family reviews the result. The name is the method — **C**laude Code **+** Code**x**, the two tools it runs on and the two AIs that check each other's work.

The point isn't to make AI coding magical. It's to make it hard for the AI to quietly cut corners while the person directing it can't see the code.

It's early days — but the proof is real and runnable: **396 self-tests** green in CI, **387 gate clauses** each proven to reject bad input, and a genuine bug caught in real-money code before it shipped.

---

## What backs this up

- **387 gate clauses, every one proven to bite.** A green check that doesn't actually enforce anything is the failure this is built to kill — *green ≠ enforcing*. So a meta-test layer feeds every gate a deliberately broken input and confirms the gate *rejects* it.
- **396 self-tests, green in CI.** The checker is mechanical Python with a single dependency — clone the repo and run it yourself in a minute.
- **A real bug, caught in real-money code.** On a bank-statement parser handling live financial data, an early "looks good" sign-off was *thrown out* when cross-family review found a genuine bug on real data — before it shipped. (Anonymized write-up in [VALIDATION.md](VALIDATION.md).)
- **No single layer is forge-proof.** The protection is the whole *stack* — a checker the AI can't argue with, an opposite-family reviewer, and a human who owns every call — not any one gate. (How it holds, and where it doesn't, is spelled out below.)

> **The honest limit.** Code-X is experimental and single-operator: proven on the author's own projects, not yet independently reproduced by anyone else. If that missing proof bothers you, that's fair — inspect the repo and judge it directly. The full account of what is and isn't proven is in [VALIDATION.md](VALIDATION.md); the review trail is in [reviews/](reviews/).

---

## What it catches

Drift — the AI wandering from what you pictured — is the famous failure. It is not the only one. Code-X is built around the whole family a non-coder can't see until it has already bitten:

| Failure | What it looks like |
|---|---|
| **Drift** | the AI quietly wandering from what you pictured |
| **Ambiguity** | a vague plan filled in the AI's way, not yours |
| **AI-slop** | bloated, over-engineered, corner-cutting code |
| **Dropped requirements** | something you asked for, silently gone when the plan becomes build tasks |
| **Fake-done** | "all tests pass / looks good" — on work that's still broken |
| **Looks-done-but-isn't** | built and green, but never actually wired up and running |
| **Decision-amnesia** | a settled decision quietly re-asked, reversed, or forgotten |
| **Wrong-looking results** | a screen that renders broken — wrong size, overflow — yet passes every check |
| **Runaway cost** | review loops repeating until the bill explodes |

Every new failure that shows up gets folded into a new rule, receipt, or deterministic check, so it's harder to repeat. That's the engine: the protocol is shaped by real mistakes, not designed up front.

---

## How it works: four stages

You never start the next stage until the previous one is done and verified.

1. **Planning** — decide and lock *exactly* what to build before any code: requirements, decisions, screen designs, business rules, architecture, and a security baseline. You review it all through the Master Blueprint.
2. **Building** — the AI builds *only* what the locked plan specifies, one small work-order at a time. Mechanical checks run on every card; human approval and model review happen at module boundaries, not in endless loops.
3. **Audit** — before anything is repaired or shipped, the built app is judged against the plan and against a standard, read-only: the Audit stage doesn't touch code, it only judges. It checks three things — does the shipped code actually match what was asked for (not just what the plan turned into), does "built and green" really mean wired and running (not just a test passing with no real caller behind it), and does a whole-app read catch the gaps no single module review could see on its own. On top of that, it runs the app through a 13-gate ship-readiness standard — but only the gates that genuinely apply to what was built, so a marked "N/A" is a deliberate decision, not a shortcut. Every finding hands off to the Fixing stage; the Audit stage never edits code itself.
4. **Fixing** — repairing something already built flips the posture from *create* to *preserve*: change only the defect, nothing else. It exists because drift sneaks in during repairs — a file moved "while we're here," a screen restyled, a settled decision reversed from memory. Code-X counts that as a failure: it freezes the file tree so nothing moves unseen, and won't let a settled decision be re-argued.

**The one rule above all: never build before the plan is locked and verified.**

Building on an unfrozen plan is the root of the drift Code-X exists to prevent — so spend the effort in planning. Every question you resolve there is friction you won't hit while building; the more concrete the plan, especially the UX and UI, the smoother and cheaper the build. Use **`/plan`** (in both Claude Code and Codex) to make it real before you freeze it. It's the highest-leverage time you'll spend on the whole project.

---

## The Master Blueprint

The Master Blueprint is the planning stage made reviewable by a non-coder. From one locked plan, Code-X generates two things: the **construction documents** the AI builds from, and the **Master Blueprint** — the single page *you* review. The wedge, in five points:

- **One generated page from the locked plan** — never hand-typed or hand-edited (🔒 *render, never re-type*). You request changes in plain language *on* the page; the source plan changes; the page regenerates.
- **It embeds the real, locked screen designs** — so you actually *see* what the finished software will look like, screen by screen, before any of it is built.
- **You approve what you can see** — each screen's look, what every control does, how the screens connect, and a plain "done" test for every feature.
- **`cx check blueprint` recomputes readiness from the source** — a module can't be built until its blueprint is complete and approved. A pretty page can't hide a gap.
- **Change the plan and your approval is void** — sign-off is pinned to a fingerprint of the plan; edit it later and that module un-approves itself until you re-approve.

That's the wedge versus a plain written spec: a spec is text a non-coder can't really judge, checked only at build time; the Blueprint is something you genuinely understood *before* the build began. Like building a house — the architect's render is for the client, while the construction documents go to the builder.

---

## Get started

### Prerequisites

Code-X is a plugin you install from a marketplace, and it builds on a few others. Commands differ slightly between **Claude Code** (slash commands inside a session) and **Codex** (the `codex` CLI plus its in-session `/plugins` picker).

**1. Python 3 + PyYAML** — the one dependency the `cx` checker needs:

```bash
pip3 install pyyaml
```

**2. superpowers** ([obra/superpowers](https://github.com/obra/superpowers)) — the planning, TDD, and debugging skills Code-X builds on.

- **Claude Code:** `/plugin install superpowers@claude-plugins-official`
- **Codex:** open a `codex` session, run `/plugins`, find **Superpowers**, Install

**3. CodeRabbit** — external automated code review, used as one layer *before* the true cross-family review (also available as the `coderabbit` CLI).

- **Claude Code:** `/plugin install coderabbit@claude-plugins-official`
- **Codex:** open a `codex` session, run `/plugins`, find **CodeRabbit**, Install

**4. frontend-design** — the design skill Code-X uses for its looks-first build stage. (Claude Code only; not in the Codex marketplace.)

- **Claude Code:** `/plugin install frontend-design@claude-plugins-official`

### Install Code-X

Code-X ships as a plugin in its own single-plugin marketplace (this repository). Install it after the prerequisites.

**Claude Code** (slash commands inside a session):

```
/plugin marketplace add 1984-alt/code-x
/plugin install code-x@code-x
```

**Codex** (in your terminal):

```bash
codex plugin marketplace add 1984-alt/code-x
codex plugin add code-x@code-x
```

> Prefer clicking? Inside a `codex` session run `/plugins`, find **Code-X**, Install — or add the repository through the Codex app's **Plugins** panel (the **+** button). The two terminal commands above are the route confirmed working.

That's it — no setup to remember. A SessionStart hook (on by default) loads the Code-X entrypoint at the start of every session, so the AI starts each session inside the Code-X plan-then-build workflow, and resumes from an existing handoff if there is one. This auto-loads the protocol *guidance*; it is not yet a fully hands-off autonomous build loop across sessions (that's on the roadmap).

> **Codex, one-time approval:** Codex gates every plugin's hooks behind a trust prompt. The first time, it asks you to approve Code-X's session-start hook — approve it once, and auto-load activates from your next session on. Standard Codex behavior for any plugin hook. On Claude Code it's on immediately, no prompt.

Then open a new session and start with:

> "Let's start a new project with Code-X."

> **How I actually drive it day-to-day** — which engine for planning vs building, my context-window habits, and clean session handoffs — is in [OPERATING-MODES.md](OPERATING-MODES.md). Code-X is model-agnostic; that doc is one operator's preferences, not requirements.

### Run the checker

The `cx` checker is a small Python program inside the plugin's skill folder. From a clone of this repo:

```bash
cd plugins/code-x/skills/code-x

python3 checkers/tests/run.py        # self-tests — verify the checker works on your machine
python3 checkers/cx check state <state>
python3 checkers/cx check packet
python3 checkers/cx check deck
```

### Worked example

[`examples/tip-split/`](examples/tip-split/) is a tiny project you can run in under a minute. A clean card deck passes `cx check deck`; drop one requirement's card and `cx` catches it as a `[P0]` — the exact failure Code-X exists to prevent (a requirement silently dropped at compile).

```bash
bash examples/tip-split/run.sh
```

The captured output of both runs is in [`examples/tip-split/receipts/`](examples/tip-split/receipts/), so you can see the result without running anything.

---

## How the trust holds — and where it doesn't

A fair, sharp question: the AI writes the state file and many of the artefacts `cx` reads. So what stops a *drifting* agent from writing a state file that simply passes?

No single layer is forge-proof. The protection is the **stack**, where each layer covers a way the others can be fooled:

- **A deterministic checker** the agent can't argue with — `cx` is mechanical Python, not an AI grading an AI.
- **Hash-bound receipts** that tie every approval and review to a fingerprint of the source.
- **An opposite-family reviewer** — a *different* vendor, not the AI that wrote the code.
- **A fresh reader** who didn't author the artefact, and **a human** who owns the decisions.

**What `cx` proves:** required artefacts exist, fields are present, hashes match, paths are safe, statuses are typed, approvals are current, and reverse coverage holds — every requirement marked `BUILDING` has a card, so nothing was dropped at compile.

**What `cx` can't prove:** that the requirement was *right*, that the product judgment is sound, that the security model holds, or that a test is meaningful rather than tautological. Those need the fresh reader, the cross-family review, and the human. *Green ≠ enforcing* applies to `cx` itself — it checks shape and existence, not meaning.

**Test circularity** is the same shape: the same AI can write both the code and its tests, so passing tests can be hollow. Code-X fights that with contract-bite tests (the 387 gate clauses), cross-family review of the tests, and the Audit stage's whole-app check that the app is actually wired and running — *built + green ≠ wired*. Residual risk remains, and it's named here on purpose rather than hidden. One known-open gap: a couple of acceptance-receipt fields are presence-checked, not yet recomputed end-to-end (a future `/cx-accept` runner closes this — see [HELP-WANTED.md](HELP-WANTED.md)).

**Why four review layers, not one?** Because the director can't fix bugs by hand, so the system catches as much as it can before the human is asked to trust the result:

1. **Mechanical checks** — free, deterministic, run on every card.
2. **CodeRabbit** — external automated code review. Useful, but it never satisfies the cross-family checkpoint.
3. **Self-review** — the builder family reviews its own work, under a capped loop.
4. **Opposite-family review** — a *different* AI family reviews the module before it ships.

The expensive part was never *having* reviews — it was the **looping** (review → fix → re-review → fix…). Code-X catches mechanical issues first, asks each reviewer for all findings in one pass, fixes the whole class, and pins it with a deterministic test. Keep the coverage, kill the loops.

---

## Three principles

1. **Capability — what it reaches for.** One non-coder directing an engineering system that in turn directs the AI, aiming at software that genuinely works without you debugging it by hand. Code-X is the culmination of long, often painful experience building this way — every mistake folded back into a system so the next project comes out better. It's a work-in-progress shaped by that experience, not a finished method.
2. **Efficiency — because the meter is running.** The AI subscriptions behind this are metered and priced in USD, which is genuinely expensive from Indonesia. So the protocol works hard not to waste reads, reviews, or loops — less optimization theater, more "make the waste visible and cut the biggest piece first."
3. **Kaizen — it improves itself.** Every mistake and every review is meant to become a lesson, and every new failure becomes a check that stops it recurring. Borrowed from the Toyota Way; whether it fully holds up is part of what's being tested.

---

## Relation to Spec-Driven Development

Code-X was built independently, from hands-on pain with AI coding agents — the author didn't know Spec-Driven Development existed. It later turned out to converge with it (Spec Kit, Kiro, BMAD, and the broader plan-first movement). That's not a precedence claim; SDD has been public since 2025. It's independent convergence — and honestly, that's reassuring: landing on the same shape independently is a decent signal the problem is real.

The shared baseline is plan-first development:

| Code-X | Spec-Driven Development |
|---|---|
| packet (frozen, hashed requirements + decisions + security baseline) | constitution → specify |
| technical plan (TRD, data/API contracts) | plan |
| card deck (each card traces to a frozen packet slice) | tasks |
| build stage, one card at a time | implement |
| `cx check deck` (deterministic reverse coverage) | analyze (often AI-driven) |

What Code-X adds on top:

- **A deterministic checker.** `cx` is mechanical Python, not an AI checking an AI. For someone who can't read the code, a gate that *can't be talked around* is worth more than another model's opinion. This is the core difference.
- **The Master Blueprint.** The plan becomes one page a non-coder reviews and approves screen-by-screen, with readiness recomputed from source rather than taken on faith.
- **The Audit stage.** A dedicated, read-only 4th stage between Building and Fixing that verifies the finished app is actually wired and running (not just that requirements and tests look right) against both the plan and a 13-gate ship-readiness standard.
- **A non-coder framing,** plus an always-on security baseline and mandatory cross-family review (Spec Kit has both as well, in lighter, AI-generated form).

In one line: **a shared plan-first baseline, plus a deterministic checker, a reviewable Master Blueprint, and a non-coder framing — arrived at independently.**

---

## Who this is for

I'm an Indonesian vibe-coder. I can't read a single line of code — I didn't build Code-X, I *directed* it. I said what I wanted; Claude did the hands-on building; Codex and GPT cross-reviewed the work and drove many of the improvements. That's the experiment: can someone who doesn't write code still direct AI rigorously enough that the software comes out faithful to their intent? I think of the role as an **AI build director** — like a film director who owns the final cut without operating the camera.

- **If you're a vibe-coder or non-coder:** this is a way of working you can try today. Install it, read `START-HERE.md`, build something — then see [OPERATING-MODES.md](OPERATING-MODES.md) for how I actually drive it.
- **If you're a professional engineer:** please tear it apart. Where is it naive, unsafe, over-built, or reinventing a wheel? Issues and PRs that challenge the design are the most welcome contribution — the explicit aim is for people who know more than I do to make it better. See [CONTRIBUTING.md](CONTRIBUTING.md). This isn't a formal proof; it's an open method shaped by real use and real mistakes, shared so those mistakes are harder to repeat.

---

## Roadmap & help wanted

The headline open item is an **Autonomous Build/Session Loop** — a policy layer that drives the build stage hands-off and stops only when human input is genuinely required (a real gate failure, or a decision the locked plan didn't pre-decide). Other valuable work: independent reproductions, stronger example projects, the future `/cx-accept` runner, and hard reviews of the trust boundary. See [HELP-WANTED.md](HELP-WANTED.md).

---

## Acknowledgments

**Influences:**

- **@mattmurphyai** (Instagram) — his reels and ideas about working with AI shaped the author's thinking on observability, dependencies, and security. An indirect but real influence.
- **[ponytail](https://github.com/DietrichGebert/ponytail) by DietrichGebert** — evaluating this plugin shaped Code-X's prevention-first ladder: decide what *not* to build before writing any code. Its idea — *"the best code is the code you never wrote"* — became the ladder's first rung.
- **The Toyota Way / Kaizen** — the continuous-improvement philosophy behind the protocol's self-improvement loop.

**Built with:**

- **Anthropic's Claude** — Code-X was built almost entirely by Claude (the Opus models did ~99% of the hands-on building, with a brief assist from Fable). I directed; Claude built.
- **OpenAI's Codex / GPT** — the opposite-family reviewer that caught blind spots Claude couldn't see in its own work and drove many of the fixes folded in over time. It's also half the name: **C**laude Code + Code**x**.

**Built on:** obra/superpowers (plugin template + TDD skill), frontend-design (design skill), CodeRabbit (one layer before the true opposite-family review).

---

## Contact & license

Questions, feedback, or just want to say this helped (or didn't)? **[Open a GitHub issue](https://github.com/1984-alt/code-x/issues)** — the best way to reach me. (GitHub is free to join.)

Licensed under **Apache 2.0** — see [LICENSE](LICENSE).
