> **Status: experimental.** Built by AI, directed by someone who can't read a single line of code — for non-coders and vibe-coders. It's worked far better for me than building without it — but I'm the only user and tester so far, so call it personally proven, not publicly proven. Take what's useful; judge it for yourself.

---

# Code-X

**A way for non-coders to get software they can trust out of AI: you direct, the AI builds, and built-in checks catch the corners it quietly cuts.**

---

## What is this

You hand the AI one small, checkable work-order at a time. A tiny program (`cx`) mechanically catches when the AI claims "done" on work that's broken or half-finished — so a non-coder can't be fooled. A second, *different* AI family then reviews what the first one built, to catch blind spots one family can't see in itself.

The name = **Claude Code + Codex**, the two AI coding harnesses Code-X is built for.

Code-X is a framework — a methodology plus the `cx` checker. It is not a plugin that writes code for you. It is a way of directing AI agents so the output is trustworthy even when you can't read the code yourself.

---

## Why it exists

It came from repeated, painful experience — AI coding assistants (both Claude and Codex) would not build to the author's specs: they drifted, cut corners, skipped requirements, then cheerfully reported "all tests pass" and "looks good" on work that was broken or half-finished. If you can't read code, you can't catch that.

Code-X is an attempt to put guardrails around the AI so a non-coder can trust the output: a planning stage that pins down exactly what to build, a building stage that forces the AI to build *only that* — one small, checkable work-order at a time — deterministic checks that can't be talked around ("green ≠ enforcing"), and cross-family review so one AI's blind spots get caught by another. It was shaped by using it on real projects and folding every failure back into the rules.

---

## The two stages

Code-X has two distinct stages. You never start the second before the first is done and verified.

1. **Planning stage** — decide and lock *exactly* what to build before any code: requirements, decisions, design, and a security baseline — frozen and verified.
2. **Building stage** — the AI builds *only* what the verified plan specifies, one small checkable work-order at a time, gated and reviewed. This stage is strict for a reason: without it, both Claude and Codex drifted from the author's specs; the gates and the `cx` checker make "build to spec" *enforceable* instead of merely hoped-for.

**The rule: never build before the planning stage is done and verified.** Building on an unfrozen plan is the root of the drift Code-X exists to prevent.

**Spend as much time and effort as you can in the planning stage.** Every question you resolve here is friction you *won't* hit while building — the more concrete the plan (requirements, decisions, and especially the UX and UI), the smoother and cheaper the build. It is the highest-leverage time you'll spend on the whole project.

A practical tip: use **`/plan`** — available in both Claude Code and Codex — to work the plan out properly. Take your time, go deep, and make it concrete *before* you freeze it.

---

## Who this is for & how you can help

I'm an Indonesian vibe-coder who can't read a single line of code. I didn't build Code-X — I *directed* it: I told Claude what I wanted, Claude did the actual building, and Codex/GPT cross-reviewed the work and drove improvements along the way. That's the whole idea — I aspire to be an **AI-directed engineer**: someone who directs AI to build software they can trust, without writing the code themselves. If that's you too, this is for you.

**If you're a vibe-coder or non-coder:** here's a way of working you can try today. Install, read `START-HERE.md`, build something. The checker runs on your machine with Python 3.

**If you're a professional engineer:** this was built by AI, directed by someone who can't read code well — *please tear it apart.* Where is it naive, unsafe, or reinventing a wheel? Issues and PRs that challenge the design are the most welcome contribution. The explicit aim is for the community to make it better. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## The three principles

1. **Capability — what it reaches for.** This is one non-coder's attempt at a way of working with AI: you direct an engineering system, it directs the AI, and the hope is software that genuinely works without you debugging it. It's worked well on my own projects — but with a single user and tester (me), so treat it as personally proven, not independently proven: a work-in-progress shared openly, not a finished method.
2. **Efficiency — because the meter is running.** The AI subscriptions that power this are metered and priced in USD, which is genuinely expensive from Indonesia — so the protocol tries hard not to waste reads, reviews, or loops. Less optimization theater; more "make the waste visible and cut the biggest piece first."
3. **Kaizen — it tries to improve itself.** Every mistake — and every review — is meant to become a lesson, and every new kind of failure becomes a check that stops it recurring. Borrowed from the Toyota Way; whether it fully holds up is part of what's being tested.

---

## Prerequisites

Code-X is a plugin you install from a marketplace, and it builds on a few other plugins. The commands differ a little between **Claude Code** (slash commands typed inside a session) and **Codex** (the `codex` CLI plus its in-session `/plugins` picker).

**1. Python 3 + PyYAML** — the `cx` checker needs it (the one Python dependency):

```bash
pip3 install pyyaml
```

**2. superpowers** ([obra/superpowers](https://github.com/obra/superpowers)) — the planning, TDD, and debugging skills Code-X builds on. In both official marketplaces:

- **Claude Code:** `/plugin install superpowers@claude-plugins-official`
- **Codex:** open a `codex` session, run `/plugins`, find **Superpowers**, and Install

**3. CodeRabbit** — the cross-family code review that Code-X's mandatory review gate depends on. In both official marketplaces (and also available as the `coderabbit` CLI):

- **Claude Code:** `/plugin install coderabbit@claude-plugins-official`
- **Codex:** open a `codex` session, run `/plugins`, find **CodeRabbit**, and Install

**4. frontend-design** — the design skill Code-X uses for its looks-first build stage:

- **Claude Code:** `/plugin install frontend-design@claude-plugins-official`

(frontend-design is a Claude Code design skill and isn't in the Codex marketplace.)

---

## Install Code-X

Code-X ships as a plugin in its own single-plugin marketplace (this repository). Install it after the prerequisites above.

**Claude Code** (type these as slash commands inside a session):

```
/plugin marketplace add 1984-alt/code-x
/plugin install code-x@code-x
```

**Codex** (both commands in your terminal):

```bash
codex plugin marketplace add 1984-alt/code-x
codex plugin add code-x@code-x
```

> Prefer clicking? Inside a `codex` session run `/plugins`, find **Code-X**, and Install — or add the repository through the Codex app's **Plugins** panel (the **+** button). The two terminal commands above are the route confirmed working.

That's it — no setup to remember. Code-X turns itself on: a SessionStart hook (on by default) loads the Code-X entrypoint at the start of every session, so the AI plans-then-builds without you having to invoke anything. It also checks for an existing handoff and resumes where you left off.

> **Codex (one-time approval):** Codex gates every plugin's hooks behind a trust prompt. The first time, Codex asks you to approve Code-X's session-start hook — approve it once. The auto-load then activates **from your next session onward** (the approval lands after the current session already started). This is standard Codex behavior, the same for any plugin hook. On Claude Code it's on immediately, no prompt.

After install, open a new session and start with:

> "Let's start a new project with Code-X."

The AI will guide you through the planning stage first.

---

## Running the checker

The `cx` checker is a small Python program that ships inside the plugin's skill folder. From a clone of this repo, change into that folder first, then run it:

```bash
cd plugins/code-x/skills/code-x

# Run the self-tests (verify the checker works on your machine)
python3 checkers/tests/run.py

# Run a specific check
python3 checkers/cx check state <state>
python3 checkers/cx check packet
python3 checkers/cx check deck
```

The checker requires Python 3 and PyYAML (see Prerequisites). No other setup.

---

## Roadmap / Help wanted

Code-X welcomes contributions. The headline open item is an **Autonomous Build/Session Loop** — a policy layer that drives the build stage hands-off and stops only when human input is genuinely required (a real gate or a decision the locked plan didn't pre-decide). See [HELP-WANTED.md](HELP-WANTED.md) for the full spec, guardrails, and why it's a good contribution to pick up.

---

## Acknowledgments

**Thanks & influences — people and ideas the author learned from:**

- **@mattmurphyai** (Instagram) — a genuine thank-you. His reels and ideas about working with AI were genuinely helpful; the author learned about observability, dependencies, and security from his content, and it shaped Code-X's thinking. An indirect but real influence.
- **The Toyota Way / Kaizen** — the continuous-improvement philosophy behind the protocol's self-improvement loop.

**Built with — the AI that did the actual work:**

- **Anthropic's Claude** — Code-X was built almost entirely by Claude: the Opus models did ~99% of the hands-on building, with a brief assist from Fable. I directed; Claude built. Sincere thanks to Anthropic for the tools that let someone who can't code get this built at all.
- **OpenAI's Codex / GPT** — the cross-family reviewer. Codex/GPT caught blind spots Claude couldn't see in its own work, and drove many of the fixes and improvements folded into the protocol over time. Code-X's whole cross-family-review idea — one AI family checking the other — depends on having both. (It's also half the name: **C**laude Code + Code**x**.)

**Built on — technical prerequisites Code-X depends on:**

- **obra / superpowers** — the plugin template and methodology (including the TDD skill).
- **frontend-design** — the design skill Code-X relies on as a prerequisite.

---

## Contact

Questions, feedback, or just want to say this helped (or didn't)? **[Open a GitHub issue](https://github.com/1984-alt/code-x/issues)** — that's the best way to reach me. (GitHub is free to join.)

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
