# Changelog

All notable changes to Code-X will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

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
