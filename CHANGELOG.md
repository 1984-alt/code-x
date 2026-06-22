# Changelog

All notable changes to Code-X will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

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
