# Changelog

All notable changes to Code-X will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

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
