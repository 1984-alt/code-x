# Session Continuity

> How to hand off cleanly between AI sessions — and why it matters.

---

## Why this matters

AI sessions are stateless. When a session ends, the model forgets everything: what was built, what was tried, what failed, and what decision was made five minutes ago. The next session starts with no memory of the previous one.

Without a handoff, the new session must reconstruct context from code and files alone. That reconstruction is slow, error-prone, and expensive. It also misses the invisible context: the decisions that were NOT taken, the dead-ends that were already tried, and the open issues that need a human answer before anything can proceed.

A well-written handoff takes about two minutes to produce. Recovering without one takes fifteen to thirty minutes of re-orientation — often with errors.

---

## The single rule

**Always end a session with a handoff document and a copy-paste resume prompt.**

No exceptions. Even if the session ends cleanly with everything green. Even if you plan to resume in five minutes. A session that ends without a handoff relies on memory — and memory is what you do not have.

---

## How to write a handoff

Use the template: `templates/HANDOFF.template.md`

Fill in every section:

1. **Front matter** — project, date, branch, HEAD commit, next actor.
2. **Status** — one line: where the project sits right now, current Code-X stage/mode/card.
3. **What was done** — bullet list of concrete outcomes (not vague "worked on X").
4. **Files changed** — table of changed files with commit SHAs.
5. **Verification status** — test count, cx check results, runtime smoke status.
6. **Open issues** — anything unresolved; blockers the next actor must address before proceeding.
7. **Paste-ready resume prompt** — the most important section. A fenced block the next session pastes in verbatim. Edit the placeholders before saving.
8. **Evidence paths** — where artifacts live, so future sessions know where to look.

### What makes a good resume prompt

The resume prompt is a **trigger, not a payload.** It is the first message of the next session, and its only job is to point the AI at the source of truth and name the next move — NOT to re-carry the state. The recap, open issues, branch, and evidence already live in the handoff file and `CODE-X-STATE.yaml`; re-pasting them just duplicates those and drifts out of sync.

So a good resume prompt is tiny — one or two lines:

```
Resume Code-X: {PROJECT}. Latest handoff: handoffs/{this-file}.md.
Read that handoff + CODE-X-STATE.yaml, tell me where I am and the ONE next action, then wait for my go.
```

That is enough because the next session will *read* the handoff for the full recap. Naming the handoff filename removes any "which one is latest" doubt. (If you forget to save the prompt and just type `resume {PROJECT}`, a session that follows the resume procedure below will still find the newest handoff — the named filename is belt-and-suspenders, not a requirement.)

What a good resume prompt is NOT: a re-paste of "what was done" and "open issues." That long form re-states the handoff, goes stale against it, and trains the habit of trusting the prompt over the source of truth. Keep the handoff detailed; keep the prompt lean.

---

## How to resume

Because the resume prompt is just a trigger, the resume *procedure* is where the real work happens. At the start of the next session the AI must:

1. Take the project from the resume prompt (even bare `resume {PROJECT}` is enough).
2. Locate the **newest** handoff in that project's `handoffs/` folder (filenames are date-stamped, so newest filename = latest), and read it.
3. Read `CODE-X-STATE.yaml` and the `MODULE-REGISTRY.yaml` (if in BUILD_FACTORY).
4. Confirm state is consistent: `cx check state --session-start`.
5. State back, in one breath: where the project is, the ONE next action, and any stop-first blocker — then **wait for the director's go** before acting.

This is what lets the prompt stay tiny: the AI reconstructs full context from the handoff + state file every time, rather than from whatever happened to be pasted.

If there is no handoff at all, reconstruct state from `CODE-X-STATE.yaml` + the latest commit log before doing anything else. Treat any uncertainty about open issues as a blocker — do not guess.

---

## Where to save the handoff

Keep the handoff file inside your project folder. A common convention:

```
your-project/
  handoffs/
    handoff-YYYY-MM-DD.md
    handoff-YYYY-MM-DD-2.md   ← if you ran two sessions in a day
```

Copy the paste-ready resume prompt to wherever you can reach it at the start of a new session: a notes app, a scratch file, the project README's "next session" section, or your own STATUS file.

---

## A note on automation

Code-X does not ship a `/save` command or any automatic handoff mechanism. This is deliberate: automation varies by setup (Claude Code, API, IDE, custom harness), and a hardcoded hook would break most configurations.

If you want to automate handoff creation for your setup, write a hook or script that calls the AI with instructions to fill in `templates/HANDOFF.template.md` and write it to `handoffs/handoff-{date}.md`. The template is designed to be fillable by the AI at session end — prompt it to do so before the context window closes.

What matters is that the handoff exists. How you produce it is your choice.
