---
name: code-x
description: Structured AI development methodology — plan then build. Load this skill at the start of any Code-X project or session. It routes you into the protocol, the checker, and the session-continuity rules.
---

# Code-X

## What This Is

Code-X is a methodology that forces AI agents to plan before they build and catch the corners they quietly cut. It is designed for non-coders directing AI: you hold the business logic; the system enforces the process.

Three stages — and you never skip to BUILD without the WRITING stage passing the checker. The third is the FIXING stage: when you repair something already built, change only the defect — never anything else.

---

## SESSION-START RULE (do this every time)

**Before any work:** read the project's handoff file and paste the resume prompt it contains. If there is no handoff yet, say so and ask the director to confirm you are starting fresh.

Handoff template: `templates/HANDOFF.template.md`
Continuity guide: `SESSION-CONTINUITY.md`

> Every session must end with a completed handoff and a paste-ready resume prompt. No exceptions. A session that ends without one loses state across restarts.

---

## Step 1: Read the protocol (in this order)

All docs are flat siblings of this SKILL.md file:

1. `START-HERE.md` — orientation and routing (read this first, always)
2. `KERNEL.md` — core concepts: stages, gates, actors, engines
3. `GATES.md` — the eight gates (G1–G8) that govern stage transitions
4. `ROUTING.md` — how to route work to the right actor
5. `SEVERITY.md` — finding severity levels (P0–P3) and what each demands

**Packet floor** (read when entering the WRITING stage):
- `PACKET-CONTENTS.md` — the 20-category coverage map every packet must satisfy
- `BUILDER-STANDARD.md` — what a buildable card looks like

**Engine profiles:**
- `BUILD-ENGINE-PROFILES.yaml` — sits beside this SKILL.md; defines which AI model fills which seat at which stage

---

## Step 2: Run the checker

The checker lives in `checkers/`. Two commands you will use:

```bash
# Run the full test suite (303 tests — all must be green before any build):
python3 checkers/tests/run.py

# Run a specific check subcommand:
python3 checkers/cx check <subcommand>
```

Common subcommands: `packet`, `deck`, `card`, `state`, `egress`, `dep-scan`, `class-sweep`.

Run `python3 checkers/cx --help` for the full list.

The checker enforces the process mechanically. If it fails, fix the issue — do not argue with the gate.

---

## Step 3: Platform tool mapping

**Claude Code (this environment):**
- Load this skill via the Skill tool.
- Run `cx` via Bash: `python3 checkers/cx check <subcommand>`.
- Use the Agent tool for subagent dispatches; use worktree isolation for large inputs.

**Codex:**
- This plugin loads natively on install.
- Run `cx` from the terminal panel: `python3 checkers/cx check <subcommand>`.
- Skills declared in `skills/` are available as native skill invocations.

---

## Step 4: WRITING stage checklist

Do not proceed to BUILD until all of these pass:

- [ ] `requirements-manifest.yaml` written and complete
- [ ] Packet docs cover all 20 categories (`PACKET-CONTENTS.md`)
- [ ] CEO-DECISION-LEDGER entries recorded for every business-logic decision
- [ ] `python3 checkers/cx check packet` → PASS
- [ ] Director validates business logic (not the AI — the human)
- [ ] Packet frozen (no edits after freeze)

---

## Step 5: BUILD stage rules

- Compile cards from the frozen packet; each card maps to packet requirements
- `python3 checkers/cx check deck` → PASS before first build card executes
- Gate G7 (build-authorization) must be GREEN before any code is written
- Cross-family review is mandatory per module (builder family A → reviewer family B)
- `python3 checkers/tests/run.py` must be all-green after each card

---

## The Iron Laws

```
NEVER BUILD BEFORE THE WRITING STAGE PASSES THE CHECKER.
NEVER END A SESSION WITHOUT A HANDOFF AND A PASTE-READY RESUME PROMPT.
```

Violating these is not a shortcut — it is the failure mode Code-X exists to prevent.

---

## Quick reference

| What you need | Where |
|---|---|
| Session resume / handoff | `templates/HANDOFF.template.md` + `SESSION-CONTINUITY.md` |
| Protocol read order | START-HERE → KERNEL → GATES → ROUTING → SEVERITY |
| Packet requirements | `PACKET-CONTENTS.md` + `BUILDER-STANDARD.md` |
| Engine/model seats | `BUILD-ENGINE-PROFILES.yaml` |
| Checker entry | `checkers/cx` |
| Checker tests | `checkers/tests/run.py` |
| Change log | `CHANGELOG.md` |
| Lessons learned | `MEMORY/LESSONS.yaml` |
