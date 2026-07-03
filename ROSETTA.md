# Code-X Rosetta — the jargon, translated

> **What this is.** Code-X has its own words. Most of them are ordinary software ideas
> wearing a Code-X name. This page is the bridge: **Code-X word → plain meaning → what a
> normal developer or GitHub user would call the same thing.** Read it once; keep it open
> the first few sessions.
>
> Two anchors that explain most of the naming:
> - **The house analogy.** Building software is building a house. You (the director) plus
>   the architect lock ONE plan. That plan produces two things: the **construction
>   documents** the builder works from, and the **Master Blueprint** — the render *you*
>   review before anything is built.
> - **The name is the method.** Code-X = **C**laude Code **+** Code**x** — the two AI tools
>   it runs on, and the two AI families that check each other's work.

---

## 1. The four stages (the shape of a whole project)

Code-X has **four** stages. You never start one until the stage before it is done and
verified.

| Code-X term | Plain meaning | Familiar equivalent |
|---|---|---|
| **1. Planning** | Decide and lock *exactly* what to build before any code — requirements, decisions, screen designs, business rules, architecture, security baseline. | The design/spec phase — but locked and signed off, not a living doc. |
| **2. Building** | The AI builds *only* what the locked plan says, one small work-order at a time, with a demo and your approval at each module boundary. | Implementation — but scoped ticket-by-ticket, no free-styling. |
| **3. Audit** | After building, a read-only pass judges the finished app against the plan and a ship-readiness standard. Judges only; never edits code. | A final QA / release-readiness review + acceptance testing. |
| **4. Fixing** | Repairing something already built, with the posture flipped from *create* to *preserve*: change only the defect, nothing else. | Bug-fix / hotfix work — but with a hard "touch nothing else" rule. |

**"Writing" is a sub-phase of Planning, not a fifth stage.** You'll hear the AI talk about
*writing the packet* — that's the hands-on part of Planning where it drafts the requirements
documents and you push them until they're concrete and truly yours (the equivalent of
writing the PRD + technical spec + ADRs). It happens inside Planning, before the plan is
frozen.

---

## 2. Gates (the automated stop-checks)

A **gate** is a checkpoint that must pass before work continues — like a required CI check
that blocks a merge. Code-X numbers its main ones G1–G8. You rarely touch these; the AI
runs them and the `cx` checker enforces them.

| Code-X term | Plain meaning | Familiar equivalent |
|---|---|---|
| **gate** | A pass/fail checkpoint that blocks progress until it's satisfied. | A required status check / branch-protection rule. |
| **G1 · Card Compilation Gate** | Proves the task list actually covers the locked plan — nothing was dropped when the plan became tasks. | "Every requirement maps to a ticket" traceability check. |
| **G2 · Security tripwire** | One security baseline for the project, plus a small security check on every task. | A pre-commit / CI security scan on each change. |
| **G3 · Anti-staleness + real-engine** | A finished module's summary and sample data are refreshed/replaced with the real thing — no leftover fakes. | "No stub data / no dead mocks left in the merge." |
| **G4 · Review modes** | Right-sizes how deep a review goes (quick scan vs full read); full reviews are rare and reserved for big moments. | Choosing lightweight vs deep code review by risk. |
| **G5 · One-and-done review** | Review happens once per *module* (not per tiny task), and the fix-loop is capped so reviews can't spiral. | Per-feature PR review with a hard "no endless re-review" cap. |
| **G6 · Mode A UI Foundation** | For user-facing apps: pick the look first (a few style variants), then build in that locked style. | Design-first / build the UI shell before the engine. |
| **G7 · Build-authorization** | The plan is frozen, security + dependencies are clean, and the whole plan gets one full opposite-vendor read *before any building starts*. | "Design approved + green light to code" sign-off. |
| **Audit Gate** | The read-only whole-app audit must run and its findings be handled before shipping. | A mandatory release-readiness audit. |
| **G8 · Final-ready** | The ship gate: zero open defects, all approvals current, a final opposite-vendor review, certificate auto-assembled. Nothing ships until every line reads PASS. | The release checklist / go-live gate. |

---

## 3. Artifacts (the things Code-X produces and reads)

| Code-X term | Plain meaning | Familiar equivalent |
|---|---|---|
| **packet** | The frozen bundle of requirements + decisions + security baseline the whole build reads from. Once frozen, it can't be quietly edited. | A locked, versioned spec / requirements repo (pinned like a release tag). |
| **requirements-manifest** | The checklist of every requirement and its disposition (building it / not building / not applicable / deferred). | A requirements traceability matrix. |
| **card** (work-order) | One small build task with everything scoped: what to touch, what not to, which model, how it's checked, what proves it's done. | A single well-specified ticket / issue. |
| **deck** | The full set of cards for a project. | The backlog / task list for the build. |
| **Master Blueprint** | ONE generated page you review — it embeds the real locked screen designs so you *see* the finished app before it's built. Rendered from the plan, never hand-typed. | An interactive design prototype + spec you approve screen-by-screen. |
| **module capsule** | A short summary written after a module is approved; later modules read the capsule, not the full history. | A module README / interface summary. |
| **coverage map** | Proof the plan addresses all 20 required planning categories (security, backups, error handling, money rules, …). | A "definition of ready" completeness checklist. |
| **SOP (13-layer standard)** | The written standard for what production software actually needs, scaled to the app; the Audit stage runs its ship gates. | A production-readiness / "definition of done" standard. |
| **live slice** | A single user-facing page, built to actually run, that you open and click through yourself before it's accepted. | A vertical slice / runnable thin end-to-end feature. |
| **golden screenshot + click-path** | A saved screenshot and a checked list of clickable paths proving a screen exists, fits, and works. | Visual snapshot test + smoke test of the happy path. |
| **final-ready certificate** | The auto-assembled proof that every ship condition passed. Shipping is *certified*, not declared. | A signed release manifest / release notes gate. |
| **receipt** | A machine-generated record that ties an approval or review to a fingerprint of the exact source it approved. | A build attestation / provenance record (think signed commit / SLSA-style). |

---

## 4. Who does what (roles — human and AI)

| Code-X term | Plain meaning | Familiar equivalent |
|---|---|---|
| **AI build director** | You. You direct the engineering system that directs the AI — you own product judgment, not the code. | Like a film director who owns the final cut without operating the camera. |
| **orchestrator** | The lead AI session that hands out tasks and *verifies* the results — it delegates the actual building, it doesn't build. | A tech lead / build coordinator. |
| **builder** | The AI (often a cheaper model) that writes the code for one card. | The implementer / coding agent. |
| **seat & engine profile** | Which model + reasoning effort is assigned to each role, and which tool (Claude Code or Codex) is running the build. | The CI runner + model matrix config. |
| **self-review** | The building AI family reviews its own work first, under a capped loop. | Author self-review of their own PR. |
| **cross-family review / xfam** | A *different* AI vendor reviews the work — the core second-opinion check. | Code review by an independent reviewer from another team. |
| **opposite family** | The other AI vendor. If Claude built it, GPT/Codex reviews it, and vice-versa. | A different vendor / independent second opinion. |
| **CodeRabbit** | An external automated code-review service used as one *early* layer — it never counts as the real cross-family review. | An automated PR-review bot (a first pass, not the sign-off). |
| **verify-app** | An agent that drives the running app and checks it behaves correctly at runtime, before you ever touch it. | An automated E2E / smoke test that exercises the live app. |

---

## 5. Severity & failure words

| Code-X term | Plain meaning | Familiar equivalent |
|---|---|---|
| **P0 / P1 / P2 / P3** | Defect severity, worst to least. P0 = blocker. | Bug priority (P0 = Sev-1 / blocker). |
| **FIX-FIRST** | A check said "not yet" — fix the finding before moving on. | A failing required check / "changes requested." |
| **final-ready = all four zero** | Nothing ships while any P0–P3 is open. "Zero known issues" is literal. | "No open bugs, no known issues before release." |
| **drift** | The AI quietly wandering from what you pictured — a moved file, a restyled screen, a reversed decision. | Scope creep / spec drift. |
| **fake-done** | "All tests pass / looks good" reported on work that's still broken. | A green build that isn't actually working. |
| **phantom completion** | A task marked "done" when nothing in the code actually changed. | An empty PR reported as shipped. |
| **decision-amnesia** | A settled decision quietly re-asked or reversed later. | Losing track of prior ADRs and re-litigating them. |

---

## 6. Mechanics & safety words

| Code-X term | Plain meaning | Familiar equivalent |
|---|---|---|
| **cx / `cx check`** | The one deterministic Python checker (not an AI) that runs the gates. It can't be argued with. | A linter / CI validator / pre-commit hook. |
| **hash / fingerprint** | A short code computed from a file's exact contents; change one byte and it changes. | A checksum / content hash / git SHA. |
| **hash-bound receipt** | An approval pinned to the fingerprint of what was approved — edit the source later and the approval auto-voids. | Content-addressed sign-off / signed provenance. |
| **frozen / freeze** | Locked so it can't be edited in place without breaking its fingerprint. | Pinning a version / tagging a release. |
| **Andon wall / order wall** | A gate that halts the "production line" — the next module can't start until the previous one is validly accepted. (Andon = the Toyota factory stop-cord.) | A hard blocking gate in the pipeline. |
| **module-acceptance** | The signed proof a module is truly done and approved before the next one starts. | "Definition of done" met + merge approved. |
| **security tripwire** | A per-task security question, checked against the *actual* code change — not self-attested. | An automated diff-aware security check. |
| **fixture / DESIGN_FIXTURE** | Clearly-labelled fake sample data used only for a visual preview, removed before the real engine ships. | Mock / stub data. |
| **Mode A UI Foundation** | The looks-first build step: get the screens approved before wiring the engine. | UI scaffolding / front-end-first build. |
| **provisioning manifest** | The list of outside accounts, secrets, and human setup that must be ready before building. | Environment / secrets prerequisites checklist. |

---

## 7. The improvement engine (Kaizen)

| Code-X term | Plain meaning | Familiar equivalent |
|---|---|---|
| **Kaizen** | The protocol improves itself: every mistake and every review becomes a lesson, and every new failure becomes a check that stops it recurring. (From the Toyota Way.) | Continuous improvement / blameless postmortems folded into process. |
| **PROP** | A proposal to change the protocol itself; it goes through review + your approval before becoming a rule. Never auto-applied. | An RFC / change proposal. |
| **EVAL** | A tiny self-test that proves a gate still bites — it feeds a deliberately broken input and confirms the gate *rejects* it. | A regression / meta-test ("green ≠ enforcing"). |
| **lesson / incident** | A recorded failure the AI can pull into future work so the same scar doesn't repeat. | A postmortem entry / known-issues log. |
| **waste alarm / cost log** | A running note of wasted reads, wrong model choices, and repeated reviews — so the biggest waste gets cut first. | Build-cost / efficiency tracking. |

---

## Two phrases you'll see a lot

- **"green ≠ enforcing"** — a check that passes but doesn't actually block bad input is the
  exact failure Code-X is built to kill. Every gate is tested to prove it *rejects* a bad
  input, not just that it runs.
- **"built + green ≠ wired"** — code that exists and passes tests still isn't real until
  something actually calls it and it runs. The Audit stage checks for that.

---

*Draft for CEO review. Flags: (1) Gate one-line summaries are compressed from GATES.md; G3,
G6, and G7 each bundle several sub-rules — check the compressions read fairly. (2)
Familiar-dev equivalents are approximate bridges, not exact matches (e.g. "receipt ≈ SLSA
provenance" is a loose analogy) — confirm the analogies help rather than mislead.*
