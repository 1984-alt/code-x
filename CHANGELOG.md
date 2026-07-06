# Changelog

All notable changes to Code-X will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [1.22.5]

Syncs the public release up to protocol **v1.22.5** — a bundle of 5 folds (patch class, no version-scheme change). 566 self-tests, 456 gate clauses, 33 `cx check` subcommands.

### Added
- **Checker-crash-masks-finding fix.** `cx check state` and `cx check boot` used to crash outright (instead of reporting a clean `[P0]`) on a malformed session-state file — the exact case a session-start safety check exists to catch. Fixed so a broken state file is now reported, never silently swallowed by a crash.
- **Mockup-first change rule.** A card that changes a CEO-visible screen must now cite the current locked design AND compare its build against a real render of that design — never a prose-only description of a visual change. Closes the gap where a screen could quietly drift from its approved design between one release and the next.
- **Per-project risk tiers (LITE / STANDARD / STRICT).** Small/throwaway projects can now run a lighter review ceremony (less mandatory cross-review, lighter audit) while the non-negotiable safety floor — coverage, frozen-plan hash, scope limits, dependency scanning, and the forced review of any money/auth/secrets-touching work — stays identical at every tier. Undeclared or invalid tier always defaults to the strictest setting.
- **Given/When/Then acceptance examples, wired into runtime proof.** Every behavioral requirement must now carry at least one concrete "Given/When/Then" example (or a typed, reasoned exemption), and the runtime verification step must actually cite and resolve those examples — not just claim the feature was checked. Existing projects keep working under a non-blocking legacy path until they opt in.
- **`/cx-accept` forge-parity acceptance recompute.** Module-acceptance receipts (the record that a feature was built, run, and approved) now have their key fields — the commit reference and the quality-card hash — independently recomputed and checked against reality, rather than trusted at face value. A new `cx check accept` command generates these receipts correctly by construction.
- **Installer re-stamped to v1.22.5** via `installer/restamp-release.sh`; installer test suite: 26/26 passing.

### Fixed
- `EVALS.md` reconciled to the full set of 55 named self-tests (was 48); `PROP-CROSSWALK.md` gained the 4 proposal-numbering rows this bundle introduced.

---

## [1.22.4]

Syncs the public release up to protocol **v1.22.4** — a patch fold, adoption-surface class (no new private-checker gate/clause/subcommand beyond the installer itself).

### Added
- **One-line installer** (PBF-PROP-017): a pinned trust-root shell installer (`installer/install.sh` + `installer/installer-manifest.yaml`) that pulls every dependency straight from its official GitHub source and pins it to an exact release **tag** via the documented full-git-URL `#<tag>` marketplace-add form — never a mutable-ref fetch, never a vendored copy. After the marketplace clones, install.sh proves the checkout actually *is* the pinned tag (`git describe --exact-match --tags HEAD`), the working tree is clean, and the tagged content's own self-declared plugin version matches the pin — fails closed on any mismatch, an unpinned-but-clean main-branch checkout, a dirty tree, or a non-git checkout. The pipe-to-bash path bootstraps its own manifest from the pinned release and checksum-verifies it before trusting a byte. A newly-added marketplace that fails any check is rolled back, never left behind. PyYAML is installed pinned + hashed (never a bare `pip install`), and CodeRabbit stays offer-and-explain, never auto-installed. Release-cut self-pins (manifest `release_tag`, install.sh's embedded bootstrap tag + manifest checksum) are re-stamped together by `installer/restamp-release.sh`; a pinned parity test enforces manifest pin == `checkers/cx --version`, and a version-parity gate asserts `marketplace.json` + `plugin.json` both declare the release tag. ~18 pinned installer tests (offline, fake-`claude`-CLI stub). New `.github/workflows/installer-smoke.yml` — clean-HOME macOS+Linux matrix, run-twice idempotency, negative nonexistent-tag/missing-python/declined-CodeRabbit cases. EVAL-048 registered.
- **README "Install Code-X" section rewritten** around the new installer: recommended download-verify-run path, a convenience one-liner, and the previous manual/prerequisites steps preserved as a collapsible fallback for Codex users or anyone who wants to see each step.

---

## [1.22.3]

Syncs the public release up to protocol **v1.22.3** — a patch fold, new gate family (`cx check accepted-surface`).

### Added
- **Accepted-surface preserve posture** (PBF-PROP-018): build-vs-fix becomes a checker-recomputed property of the touched surface instead of model judgment. New `cx check accepted-surface` (`cx_accepted_surface.py`, stdlib-only), wired into `cx check card` and `cx check build-turn`: a card whose write-set touches a file named in a CEO-accepted-surface manifest must carry either an anchored `mode: FIX` (defect repair, no new scope) or a typed `preserve_contract` — an extractor-backed inventory (includes · scripts · stylesheets · `data-fn` · JS class/global/listener · locale links) mapping every capability to `re_homed_to` / `superseded_by_lock_ref` / `dropped_ceo_decision_ref`, receipt-bound to the accepted commit, backed by a full-suite regression receipt. `build-turn` also diffs the actual `git diff` against every manifest so an undeclared broad-glob write is caught even when the card's own `allowed_files` looked clean. 12 new gate clauses (`ACCEPTED-SURFACE-*`, 404 gate clauses now bite; 424 self-tests). New `templates/ACCEPTED-SURFACE-MANIFEST.template.yaml`. EVAL-047 registered.

---

## [1.22.2]

Syncs the public release up to protocol **v1.22.2** — a patch fold, no gate-logic change to existing checks.

### Added
- **Master Blueprint visual parity** (P-PROP-007): the plan page now renders three CEO-facing projection views on top of the per-module blueprint, all pure projections of already-locked source — a flow storyboard (frames + nav-edge arrows + one lane per journey), a prototype tab (the clickable Mode A screens embedded beside the static locked designs), and visible feedback anchor ids on every screen/control. New sibling checker `cx check blueprint-page` recomputes each view from canonical source and requires the rendered page's machine-readable markers to be set-equal — a hand-drawn edge, a dropped journey lane, a divergent prototype embed, or an invented anchor id fails closed. `cx check blueprint` itself is unchanged. 5 new gate clauses (`BLUEPRINT-STORYBOARD-FRAMES`/`-EDGES`/`-LANES`, `BLUEPRINT-PROTOTYPE-TAB-LOCKED`, `BLUEPRINT-ANCHOR-ID-VISIBLE`), each proven against a pinned bad fixture (392 gate clauses now bite; 411 self-tests).

---

## [1.22.1]

Syncs the public release up to protocol **v1.22.1** — a patch fold, no gate-logic change.

### Changed
- **CI now runs the full eval gate, not just the unit suite.** `.github/workflows/tests.yml` ran only `checkers/tests/run.py`; an external GPT-5.5 Pro review flagged that public-CI-green therefore proved unit tests only, never that the gate clauses actually bite. CI now runs `cx check evals` (unit tests + the contract-bite harness + `consistency --strict` + the live kaizen-queue check), so a red gate clause fails the build, not just a red unit test.
- **New "Who Code-X is for" README section**, stating plainly who the protocol is built for and who it is *not* for (fast MVPs and throwaway prototypes should use an AI builder directly). Added from an external Grok review.
- **Backfilled tags** for releases that shipped without one at the time: `v1.12.1`, `v1.14.0`, `v1.17.0`, `v1.19.0`.

---

## [1.22.0]

Syncs the public release up to protocol **v1.22**. It adds a 4th stage — Audit — inserted between Building and Fixing, plus a formal SOP (Standard of Practice) ship-readiness asset that the Audit stage checks the built app against.

### Added
- **The Audit stage (A-PROP-001) — a 4th stage, Planning → Building → Audit → Fixing.** Posture = *verify*, read-only: after a module (or the whole app) is built, the Audit stage judges it against the plan and against a standard before anything is repaired or shipped. It never edits code — findings hand off to the Fixing stage. It absorbs the former Built-App Audit as its first three angles — (A) requirements coverage, (B) original asks vs delivered, (C) shipped reality: is there a real production caller for every feature, not just a passing test — and adds a fourth: (D) SOP ship-gate conformance, tested against the applicability model below. Final-ready is now chained behind a completed Audit stage, and cross-family review is required at the final audit (with a typed escape hatch mirroring the existing stage-1 discipline).
- **The SOP (Standard of Practice) — a 13-layer ship-readiness standard, sha-pinned.** A dedicated asset (`SOP/`) spelling out 13 ship gates a shipped app should meet, hashed so drift is detectable, with a companion applicability model.
- **Applicability model — 9 observable build-facts, machine-enforced N/A rules.** Not every gate applies to every app; the model derives 9 build-facts from what was actually built and mechanically decides which of the 13 gates apply, so a gate can only be marked "not applicable" for a stated, checkable reason — never a silent skip.
- **Counts: 396 self-tests (up from 375), 387 gate clauses proven to bite (up from 366).**

---

## [1.21.0]

Syncs the public release up to protocol **v1.21** (and its v1.21.1–v1.21.4 patch line). It folds in a review-routing + see-and-test upgrade (PROP-042), a no-ambiguity rule (PROP-044), a protocol-wide rename of the improvement proposals (PROP-043), and four follow-up patches. Each change was cross-family reviewed — several as both proposal and built code — and fixed-first before landing.

### Added
- **See-and-test gate (PROP-042) — every user-facing module gets demoed on its real screen before it's accepted.** A module could be built, all-green, and even live-driven while the *show* step — actually running it on its own screen and confirming the behaviour — was quietly skipped. This forces that show-step: a user-facing module can't pass acceptance without a recorded demo of the real screen. It closes the exact gap a real project slipped through — everything green, yet a step never actually shown.
- **Review-routing + orchestration mandate (PROP-042).** Makes sure the *right* review actually fires and can't be skipped: a build that changes code can't quietly bypass its independent-review step, and the rules for which review is required at which point are made explicit rather than left to habit.
- **Model-agnostic anti-slop preamble (PROP-042).** Every build work-order now carries a short, model-independent instruction block steering the builder away from bloat and corner-cutting — injected mechanically and checked for presence, so it can't be dropped.
- **No-Ambiguity rule (PROP-044).** A conflict-scan that catches two protocol rules contradicting each other *before* they cause a silent wrong call, rather than after.
- **Long-autonomous milestone — defined, and shipped OFF.** Fully hands-off autonomous building is named as a future milestone with a reliability bar it must clear first. No autonomy switch ships in this release; it stays a goal the protocol gates toward, not a mode you can flip on.
- **Proposal rename + crosswalk (PROP-043).** The improvement proposals were renamed into stage-categorized ids, with a crosswalk mapping every old id to its new one. Purely organizational — no behaviour change.
- **Kaizen checker (`cx_kaizen.py`) + fixtures.** A new deterministic checker (with its own test fixtures) for continuous-improvement proposal handling ships in this release.

### Patches (v1.21.1–v1.21.4)
- **v1.21.1** — hardens the no-ambiguity conflict-scan's freshness basis, pinning it to an immutable commit instead of a self-referential recompute that could never settle.
- **v1.21.2** — module acceptance now *proves* the build actually passed by re-reading each build log (a claimed pass contradicted by a real failure marker is rejected), and confirms an anti-slop cleanup pass genuinely ran.
- **v1.21.3** — adds an auditable, fail-closed reliability bar for the long-autonomous milestone: a graduation ledger recomputes each finished project's "clean" verdict from hash-locked receipts (never a self-declared flag) and blocks the milestone until a streak of clean ships. It builds *no* autonomy switch — that stays a future proposal the bar unlocks.
- **v1.21.4** — housekeeping only: a Python 3.10+ guard on the checker entrypoints (a clear message instead of a crash on older Python) plus documentation reconciliation. No gate-logic change.

375 tests · 366 gate clauses enforced · consistency strict-clean.

---

## [1.20.0]

(published bundled with v1.21.0 — no separate tag)

Syncs the public release up to protocol **v1.20**, folding in PROP-041 and its follow-up fixes.

### Fixed
- **Registry build-shape is checked before build authorization.** Frozen module registries now fail early when they are not hash-marked, contain dependency cycles, point at unknown or later modules, name missing cards, or include blank card ids.
- **Foundation cards no longer block themselves.** Dependent cards still wait for the required checkpoint, but the foundation work-order itself can now run.
- **Whole-packet review receipts carry across build-metadata-only registry edits.** The review stays current when only registry build metadata changes, while substantive packet edits still invalidate it.
- **Evidence test-output handling is scoped correctly.** Module-build cards may create declared test outputs; the stricter test-edit guard remains for fix cards.

303 tests · 291 gate clauses enforced · consistency strict-clean.

---

## [1.19.0]

Syncs the public release up to protocol **v1.19**, folding in one upgrade (PROP-040, the whole-packet integration review). It was cross-family reviewed twice — once as a proposal, once as built code — and fixed-first before landing.

### Added
- **Whole-packet integration review (PROP-040) — one cross-family read of the *entire* plan before any building starts.** Until now, opposite-family review only ever looked at *slices*: each work-order card on its own, a risky module here and there, one finished module at a time. Nothing read the whole locked plan as a single coherent document — so a contradiction *between* documents (the technical spec says one thing, a later locked decision says another) could slip past every check and reach the builder. This release adds one mandatory, whole-plan, opposite-family review as a build-authorization precondition: before the first module is built, a different AI family reads the complete frozen plan end to end — requirements, every module spec, the architecture and technical docs, the data and behaviour contracts, the locked screens, the Master Blueprint — looking for the cross-document contradictions the per-card checks structurally cannot see. It is recorded as a hash-bound receipt kept *outside* the frozen plan and tied to that exact plan version; change the plan and the review is automatically invalidated and must be redone. The build-order wall then blocks every module until a current, passing review exists — *no module builds without it*.

  Why it matters: on a real project, the plan passed every automated check, every slice-level review, and a visual approval — yet a stale technical doc still named an old component the stack had already been re-locked away from. An autonomous builder reading that doc would have built the wrong thing. This is the integration pass none of the slice reviews could provide.

  Honest limit: it is a judgment review. The receipt proves the whole-plan review *happened* against the current plan and records its verdict — it cannot prove the review was perfect (that is bounded by the reviewer's thoroughness). It complements, never replaces, the per-card and per-module reviews.

291 tests · 283 gate clauses enforced · consistency strict-clean.

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

(pre-dates the public repository — no tag)

### Added
- **Plain Talk (Communication Standard)** — `VOICE.md` governs how the AI communicates with the non-coder user: no-jargon/define-don't-delete, scannable/minimal, decisions presented as decidable options; exactly 3 status markers (✅ / ⚠️ / ❌); enforced by a plain-language review lens (not a machine check).
- **Built-App Audit** — a final read-only whole-app audit before final-ready (gate G8): 3 angles (requirements ↔ original asks ↔ shipped reality) plus the "built + tested + green ≠ wired and running" killer check; includes a new `BUILT-APP-AUDIT.md`, a report template, and a light `cx check final-ready` precondition (a `built_app_audit` state block with a real audit report must exist).
- **Phantom-completion guard (PROP-028)** — module-acceptance now rejects empty or phantom diffs so "done" cannot be claimed without real changes.

---

## [1.11.0] — Initial public release

(pre-dates the public repository — no tag)

### Added
- Two-stage planning → building methodology with enforced gate progression
- `cx` checker: deterministic Python program that verifies gate conditions and proves checks are enforcing (not just green)
- Cross-family review gates: mandatory review by a second AI family (Claude reviews Codex-built code and vice versa)
- Kaizen self-improvement loop: failures and reviews feed back into the rules and checks
- Session-continuity system: handoff template and guide for resuming across sessions without losing state
- Plugin packaging for both Claude Code and Codex (a `.claude-plugin/` marketplace catalog plus the plugin under `plugins/code-x/`)
- Apache 2.0 license
