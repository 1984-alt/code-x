# Handoff — {PROJECT} · {DATE}

<!--
  PURPOSE: End every session with one of these. Fill it out, then copy the
  paste-ready resume prompt at the bottom and save it somewhere you can reach
  it from the next session (a notes app, a scratch file, your project STATUS).
  A handoff takes ~2 minutes. Re-orienting without one takes ~20 minutes.
-->

---

## Front matter

| Field       | Value                                   |
|:------------|:----------------------------------------|
| Project     | {PROJECT}                               |
| Date        | {YYYY-MM-DD}                            |
| Session end | {HH:MM} (approx)                        |
| Next actor  | {Claude / Codex / User}                 |
| Branch      | {branch-name}                           |
| HEAD commit | {sha}                                   |

---

## Status

> One line: where the project sits right now.

{e.g. "G6 green, module 3 accepted, module 4 card compiled — not yet started."}

**Current Code-X stage:** {PLANNING_STUDIO | BUILD_FACTORY}
**Current mode:** {MODE_A_UI | MODULE_BUILD | REVIEW | FIX | FINAL_READY}
**Current card:** {card-id or null}
**Open findings:** P0: {n} · P1: {n} · P2: {n} · P3: {n}

---

## What was done this session

> Bullet list. One bullet = one meaningful outcome. No vague "worked on X."

- {e.g. Compiled card deck (8 cards, CARD-I1..I7 + P1). cx check deck PASS.}
- {e.g. Built CARD-I1 (ingest route). 87 tests green. Self-review: 0 P0/P1.}
- {e.g. GPT-5.5 cross-family review folded: 1 P1 fixed (commit abc1234).}
- {e.g. CARD-I2 started — see open issues below.}

---

## Files changed

> List only files changed this session. Include the commit SHA if committed.

| File | What changed | Commit |
|:-----|:-------------|:-------|
| {path/to/file.py} | {one-line description} | {sha} |
| {path/to/other.yaml} | {one-line description} | {sha} |

**Uncommitted work:** {none | yes — see open issues}

---

## Verification status

> Evidence that the session's work actually runs and passes.

| Check | Result |
|:------|:-------|
| Test suite | {N green / M failed} |
| cx check state | {PASS / FAIL — detail} |
| cx check card | {PASS / N/A} |
| Runtime smoke | {PASS / N/A / not run} |
| Cross-family review | {PASS / PENDING / N/A} |

---

## Open issues

> Anything unresolved that the NEXT actor must handle before proceeding.

- [ ] {e.g. CARD-I2 mid-build: ingest route wired but reconcile check not yet added. Next: add reconcile + tests.}
- [ ] {e.g. CEO decision needed: field X — accept NULL or require default? (CEO-DECISION-CARD candidate)}
- [ ] {e.g. Parser edge case P2 SKIP-001 not yet patched. Deferred by decision CEO-D-007.}

**Blockers (must resolve before next card):** {none | describe}

---

## Paste-ready resume prompt

> The resume prompt is a TRIGGER, not a recap. Everything the next session needs
> already lives in THIS handoff and in `CODE-X-STATE.yaml` — so keep this file
> detailed, but keep the paste-block tiny. Copy the block below; edit {PROJECT}
> and the handoff filename.

```
Resume Code-X: {PROJECT}. Latest handoff: handoffs/{this-file}.md.
Read that handoff + CODE-X-STATE.yaml, tell me where I am and the ONE next
action, then wait for my go.
```

> Why so short: a resume prompt that re-pastes the recap and open-issues just
> duplicates this handoff and drifts out of sync with it. Point to the source of
> truth; don't copy it. (If same-day reruns make "latest" ambiguous, the named
> filename above removes the doubt.)

---

## Evidence paths

> Paths to artifacts that prove this session's work. Future sessions use these
> to verify — not to re-read in full, but to know WHERE evidence lives.

| Artifact | Path |
|:---------|:-----|
| State file | CODE-X-STATE.yaml |
| Packet dir | {packet-dir/} |
| Module registry | {packet-dir/MODULE-REGISTRY.yaml} |
| Last acceptance receipt | {path/to/MODULE-ACCEPTANCE-{id}.yaml} |
| Test output | {path/to/test-run-{date}.txt or "re-run: pytest -q"} |
| Cross-family review pkg | {path/or N/A} |
| Cost log | WORK-ORDER-COST-LOG.yaml |
