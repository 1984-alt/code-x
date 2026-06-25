# Changelog

All notable changes to Code-X will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [1.18.0]

Syncs the public release up to protocol **v1.18**, folding in one upgrade (PROP-039, the Master Blueprint). It was cross-family reviewed twice — once as a proposal, once as built code — and fixed-first before landing.

### Added
- **The Master Blueprint (PROP-039) — the planning stage made reviewable by a non-coder.** Planning used to emit a scatter of separate files no non-coder could read as one thing, so the plan you *thought* you approved could quietly drift from the plan that was actually written — invisible until build or demo. This release makes planning **screen-first** and gives it a single review surface: the **Master Blueprint**, one auto-generated page that projects the whole locked plan in plain language. It is *render-never-re-type* — never hand-typed, always a projection of the real source — and it **embeds the live locked screen designs**, so you see the finished software before any of it is built. It carries an always-on completeness checklist (locked design · a navigation map · a behaviour contract for every control · a done-test for every feature), a glossary for unfamiliar words, source anchors, and an approval cockpit with risk callouts. A module becomes buildable only when `cx check blueprint` **recomputes** it ready straight from source — never from a written flag, a badge, or a manifest boolean — *and* you approve it; the build gate then blocks any module whose blueprint isn't ready. No new gate family — it rides the existing build-order wall. Your approval and any required opposite-family review live in hash-bound receipts kept *outside* the frozen plan, so recording an approval never disturbs the plan's seal.

  Honest limit: the page is a view — the real gated objects are the immutable plan plus the approval/review receipts, and the source is always the ground truth. A receipt proves the plan hasn't changed since you approved it and that the review happened against that exact version; it can't prove the plan is *good* — that stays your judgment and the reviewer's. The plain-language and glossary checks are presence checks, not a grammar grade.

288 tests · 270 gate clauses enforced · consistency strict-clean.

---

## [1.17.0]

Syncs the public release up to protocol **v1.17**, folding in two upgrades (PROP-036, plus a follow-up PROP-037). Each was cross-family reviewed before landing.

### Added
- **The Verify-App Gate (PROP-036) — a screen's behavior is machine-checked before any human drives it.** A previous release made sure the author personally drove each page of a build. But the author was still the *first* thing to actually exercise the screen at runtime — a page could be built, all-green, and offered for review while its behavior had never once been run and checked by a machine. (The visual version of this gap once shipped a 617-pixel-wide screen onto a 390-pixel phone and passed every green check, because no check ever rendered it; the behavior version is a flow the tests never clicked through.) This gate closes the behavior half: before a user-facing page can be accepted, a verify-app agent must drive the running build and confirm its acceptance criteria at runtime, recorded in a typed receipt. It is a precondition to the author's own live-drive — no passing runtime receipt, no acceptance, and the next page can't start. Honest limit: the check proves a machine-stamped receipt recorded a pass for a commit-shaped build id; it does not re-run the app itself, does not verify the id is the live HEAD, and never claims the screen *felt* right — that stays the author's call.

### Fixed
- **Path-safety closed across the whole build step (PROP-037).** The cross-family review of the verify-app gate noticed that one file-reference the build checker reads had just been hardened against a path trick — a symbolic link pointing outside the project, which would make the checker read foreign bytes and trust them — but its sibling references had not been, and one carried no such guard at all. This release factors the check into a single shared helper and applies it to *every* file reference the build step reads, with a meta-test proving each one now rejects the trick. No change for honest inputs; it only closes a way to feed the checker an out-of-project file. The review came back clean.

257 tests · 247 gate clauses enforced · consistency strict-clean.

---

## [1.16.0]

Syncs the public release up to protocol **v1.16**, folding in one protocol upgrade (PROP-035). It was cross-family reviewed twice — once as a proposal, once as built code — and fixed-first before landing.

### Added
- **The Fixing Stage (PROP-035) — a third stage with a "preserve, don't drift" posture.** Until now the protocol had two stages: *Planning* (decide what to build) and *Building* (create it). But most real work after launch is *fixing* — and a fix is exactly where a build quietly drifts: a file gets deleted, a screen gets restyled, an earlier decision gets silently reversed "while we're in here." This release gives fixing its own stage whose default posture is **preserve**: anything that changes beyond the fix is treated as a failure, not a side effect. Two rules from the author shape it — *every fix is a fix* (the posture is on even for a quick mid-build repair), and *same rules, scaled ceremony* (the rules are always on, but the heavy gate only fires when you touch a locked, already-accepted piece). It builds on the previous release's lock-fidelity work (PROP-034) and gives the visual and scope drift guards a proper home. Five guardrails:
  - **Structure lock.** When a surface is accepted, its real file tree is recorded straight from version control — not a list the AI types out — so a later "fix" can't quietly delete or move files without it showing up. Deeper component/route checks ship advisory-only for now.
  - **No decision amnesia.** Questions raised and answered during a fix are written to a typed log file, and the end-of-turn check reconciles against it — so an answer given mid-fix can't silently evaporate by the next handoff.
  - **Per-target cross-lock.** A fix card has to name what kind of thing it's touching (one of a fixed list of seven) and spell out the surfaces involved — you can't opt out of the check by leaving the target vague.
  - **Always-on guardrails.** The preserve rules are present-and-enforced the same way the do-less ladder is, so they can't quietly drift out of the protocol.
  - **Revert on drift.** When a fix does drift, the recovery is a recorded revert — no checker ever runs a destructive reset on its own.

  Honest limit: the structure lock is bound to the real file tree, but the decision log is still checked at the record level — a question that is simply never written down escapes the log (it surfaces as an end-of-turn mismatch, not silently). The stage protects forward from a frozen baseline; it does not retroactively un-drift screens built before it existed.

257 tests · 237 gate clauses enforced · consistency strict-clean.

---

## [1.15.0]

Syncs the public release up to protocol **v1.15**, folding in one protocol upgrade (PROP-034). It was cross-family reviewed twice — once as a proposal, once as built code — and fixed-first before landing.

### Added
- **Lock-fidelity continuity (PROP-034) — `cx check drift`, fix-card anchoring, and lock-pointing handoffs.** Locked plans tend to rot during corrections and handoffs: the AI starts reasoning from the drifted conversation instead of the frozen plan, and a handoff carries a paraphrase rather than the lock itself. This is the *scope/plan* sibling of the previous release's *visual* drift gate (PROP-033). Three levers, with friction matched to risk:
  - **Re-anchor before you fix.** A fix card must name the exact locked requirement it touches and classify the change as a *restore*, an *ambiguity resolved*, or a *scope change*. A scope change is a hard stop — nothing outside the lock can be built as a "fix" without a recorded decision and a plan amendment.
  - **Handoffs point at the lock, they don't paraphrase it.** A handoff now carries the frozen plan's hash and its open-work list, copied verbatim; both writing and reading the handoff recompute those from the real files and reject a self-declared hash or an empty open-work list that doesn't actually match.
  - **Drift alarm.** A new deterministic check flags a card that references a requirement not in the frozen plan, a planned requirement with no card covering it, or a fix touching files outside its anchored card — wired into the acceptance wall so it blocks before a module is accepted. A semantic "this behavior exceeds the requirement" layer ships advisory-only for now.

  Honest limit: the checker proves the fields are present, the anchor resolves, and a scope change is authorized — it can't mechanically prove a card *labeled* a restore truly is one. That residual is held by a fail-closed default (when in doubt, the stricter class) plus an opposite-family reviewer auditing the label on every fix card. Green never means "this restore is honest."

257 tests · 219 gate clauses enforced · consistency strict-clean.

---

## [1.14.0]

Syncs the public release up to protocol **v1.14**, folding in everything from the v1.13 and v1.14 cycles. Five protocol upgrades (PROP-031, PROP-023, PROP-032, PROP-024, PROP-033), each cross-family reviewed and fixed-first before landing.

### Added
- **In-loop rendered-fidelity gate (PROP-033) — `cx check render-fidelity`.** A UI build card could produce a screen that *renders wrong* (wrong width, horizontal overflow, a desktop-shaped layout on a phone target) and still pass every green check — because no gate actually rendered the screen and measured it; the first real look-check was a human eye, after the build. The new gate runs right after a UI screen is built and before it's shown for review, so objective layout drift is caught early. Layer 1 is deterministic and blocking (a missing/stale/forged render receipt is a hard fail; measured overflow or an off-screen control hard-blocks the build turn); Layer 2 (drift vs your own locked reference shot) is advisory only for now. The checker validates a render bundle — it never claims the screen "looks right," which stays your call.
- **External-visual-reference capture + lock (PROP-031).** When a screen is meant to look like another app, that app must be pulled into the plan as a pinned screenshot, captured and bound at each target viewport — a verbal "I confirmed its UX" is no longer enough. At accept time the captured reference is forced on-screen side-by-side, so a "make it like that app" screen can never ship from memory. Green means the real reference was captured, pinned, and shown to you — not that the look was achieved (that's still your accept).
- **Live Slice Delivery (PROP-032).** Re-scopes a build to a per-page vertical slice that you open and *drive live* in the running app before the next page can start ("no accept, no next"). The first slice is a walking skeleton — the shell and navigation with every page present but empty — so the whole app is tappable from day one. Adds no new gate; it rides the existing acceptance wall.
- **Prevention-first do-less ladder (PROP-024).** A short ordered checklist the builder walks *before* writing code — decide what NOT to build first (does it need to exist · is it in the standard library · is there a native platform feature · is a dependency already present · can it be one readable line · build the minimum). It never cuts input validation, security, accessibility, required tests, or anything you explicitly asked for or locked.

### Changed
- **WRITING-stage front-end hardening (PROP-023).** Two mechanical checks now bite before a plan is frozen: (a) clarify-before-freeze — every open/ambiguous point is raised and resolved to a real decision-ledger row, recorded in a structured sweep file, with no unresolved "needs clarification" markers left hiding in any file; (b) every requirement being built carries a structured, testable acceptance criterion (pass condition · evidence type · verification reference). Both are presence-and-structure gates, not English-quality judges.

### Notes
- Protocol self-tests grow to **244** green; **204** gate clauses bite. The render-fidelity browser collector ships as a documented interface — the gate validates render evidence; generating that evidence (driving a browser) is opt-in at real-project use.

---

## [1.12.2]

### Added
- **Worked example — `examples/tip-split/`.** A tiny, runnable project: `bash examples/tip-split/run.sh` shows `cx check deck` PASS, then catches a dropped requirement as a `[P0]` ("requirement … BUILDING but appears in NO card — dropped at compile"). Committed receipts let you see the result without running anything.
- **`VALIDATION.md`** — honest single-operator validation: what Code-X has caught on real projects, and the limit (personally proven, not publicly proven).
- **`reviews/`** — a summarised, inspectable cross-family review trail (real reviews, verdicts, what was folded).
- **README — "Relation to Spec-Driven Development"** — independent-invention framing plus the verified delta vs current Spec Kit (deterministic checker · Built-App Audit · non-coder framing; security baseline + cross-family review as enforced/mandatory).
- **README — "What `cx` can and can't verify" + "Trust boundary & test circularity"** — honest-limits sections, plus a HELP-WANTED "Trust-Boundary / Forge-Parity" open problem.
- **CI + badges** — `.github/workflows/tests.yml` runs the checker self-tests on push/PR; README badges for tests, license, and protocol version.

### Changed
- **Role renamed "AI-Directed Engineer" → "AI build director"** across the README and CHARTER — "engineer" wrongly implied code-literacy.
- **README "What is this" rewritten** in plain language, centered on keeping what you build faithful to your original vision (planning as the heart, not just the build-time checks).

### Fixed
- **`cx check card` no longer rejects valid PROOF cards.** `PROOF` is a first-class card mode — `cx check evidence` has dedicated PROOF logic (a PROOF card must carry evidence_claims) and GATES.md treats it as built and biting — but it was missing from the checker's `VALID_MODES` set, so `cx check card` flagged every PROOF card with a spurious `[P1] mode 'PROOF' not in [...]`. Added `PROOF` to `VALID_MODES` (`checkers/cx_common.py`) and a regression test (`test_proof_mode_card_passes`) that runs a good PROOF card through `cx check card` — the test gap was that PROOF fixtures only ran through `cx check evidence`, never `cx check card`. Author-facing mode hints in the WORK-ORDER and STATE templates now list PROOF too. Protocol unchanged (still 1.12) — a checker bugfix only. Found by an external GPT cloud review; fixed via the Code-X process (TDD + cross-family review).

---

## [1.12.1]

### Added
- **Auto-load on install (SessionStart hook)** — once the plugin is installed, Code-X loads itself at the start of every session automatically; no command to remember. The hook injects a compact (~250-token) spine: the two iron laws, the session-start resume rule, a non-negotiable routing directive, and the read-order to enter the protocol — full protocol detail is read on demand from the skill folder. On by default for both Claude Code and Codex. Protocol unchanged (still 1.12) — a packaging/usability improvement only.

### Changed
- **Leaner resume prompts (trigger, not payload)** — `SESSION-CONTINUITY.md` and `templates/HANDOFF.template.md` now treat the paste-ready resume prompt as a 1–2 line *trigger* that points at the latest handoff + `CODE-X-STATE.yaml`, instead of re-pasting the recap and open-issues (which duplicated the handoff and drifted out of sync). The resume *procedure* does the reconstruction: locate the newest handoff, read it + the state file, report position + next action, and wait for go. Handoff files stay detailed; only the paste-block shrank.

---

## [1.12.0]

### Added
- **Plain Talk (Communication Standard)** — `VOICE.md` governs how the AI communicates with the non-coder user: no-jargon/define-don't-delete, scannable/minimal, decisions presented as decidable options; exactly 3 status markers (✅ / ⚠️ / ❌); enforced by a plain-language review lens (not a machine check).
- **Built-App Audit** — a final read-only whole-app audit before final-ready (gate G8): 3 angles (requirements ↔ original asks ↔ shipped reality) plus the "built + tested + green ≠ wired and running" killer check; includes a new `BUILT-APP-AUDIT.md`, a report template, and a light `cx check final-ready` precondition (a `built_app_audit` state block with a real audit report must exist).
- **Phantom-completion guard (PROP-028)** — module-acceptance now rejects empty or phantom diffs so "done" cannot be claimed without real changes.

---

## [1.11.0] — Initial public release

### Added
- Two-stage planning → building methodology with enforced gate progression
- `cx` checker: deterministic Python program that verifies gate conditions and proves checks are enforcing (not just green)
- Cross-family review gates: mandatory review by a second AI family (Claude reviews Codex-built code and vice versa)
- Kaizen self-improvement loop: failures and reviews feed back into the rules and checks
- Session-continuity system: handoff template and guide for resuming across sessions without losing state
- Plugin packaging for both Claude Code and Codex (a `.claude-plugin/` marketplace catalog plus the plugin under `plugins/code-x/`)
- Apache 2.0 license
