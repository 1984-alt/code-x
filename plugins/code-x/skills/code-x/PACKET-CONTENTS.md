# Code-X V1 — PACKET-CONTENTS (the packet floor) ✅ CANON

> Folded 2026-06-10 (PROP-014). Cross-family review: GPT 5.5 Pro cloud FIX-FIRST →
> PROP-006 synthesis (adopt 4/5, reject 1 stale) → CEO approved → folded WITH enforcement
> built same session (`cx check packet` + 10 biting clauses). Source: v0.13 gold pieces
> (tag `code-x-v0.13-final`), re-based onto V1's packet → card-deck architecture.
> [RULE:packet-contents-floor]

## The gap this closes (why)

V1 proves the DECK covers the PACKET (`cx check deck`, reverse coverage) and every card
traces back to a frozen packet slice (`source_map`). But before this floor, **nothing
defined what the packet itself must CONTAIN.** A thin packet passed every gate:
requirements-manifest with 3 shallow requirements → deck covers them → all green — while
data contracts, security baseline, CEO decisions, readiness triggers, and the builder's
coding standard were never written down. v0.13 had five proven pieces for exactly this;
this file is their V1-native port — **packet floor, deterministic where possible,
fresh-eyes where it must be.**

## Piece 1 — Coverage map (20 categories, V1-rebased)

A `coverage-map.yaml` lives **INSIDE the frozen packet dir** (same inside-the-hash pattern
as `requirements-manifest.yaml` — editing it after the deck is cut breaks the deck).
Schema per row: `id` (1–20) · `name` · `status: DONE | N/A` · `file:` (DONE — path inside
the packet, existing + non-trivial ≥200 bytes) · `na_because:` (N/A — written reason).
**Categories, not files** — package into fewer files as long as every category is present
and findable (PRD and TRD stay separate).

| # | Category | Typical packet home | When |
|--|--|--|--|
| 1 | product vision / problem / users | product-vision | always |
| 2 | functional requirements | PRD | always |
| 3 | non-functional requirements | PRD or TRD | always |
| 4 | technical architecture | TRD | always |
| 5 | data model / schema | DATA-API-CONTRACTS | backend/data |
| 6 | internal API / function contracts | DATA-API-CONTRACTS | backend/data |
| 7 | external integration contracts | DATA-API-CONTRACTS | external integration |
| 8 | validation / errors / permissions / side-effects | DATA-API-CONTRACTS | backend/data |
| 9 | pagination / retries / timeouts / caching / idempotency | DATA-API-CONTRACTS | backend/data |
| 10 | authn / authz / tenant isolation / RLS | SECURITY-BASELINE | always |
| 11 | secrets / privacy / PII / logging redaction | SECURITY-BASELINE | always |
| 12 | input validation / uploads / rate-limit / CSRF / CORS / XSS / injection / prompt-injection | SECURITY-BASELINE | always |
| 13 | retention / deletion / audit logs / admin access | SECURITY-BASELINE | always |
| 14 | UI / workflow locked designs | locked-designs + PRODUCT-TASTE-LOCK / DESIGN-GOLDEN-MASTER | UI/workflow |
| 15 | CEO decision ledger (asks + decisions) | CEO-DECISION-LEDGER.md (Piece 3) | always |
| 16 | requirements manifest + dispositions | requirements-manifest.yaml (PROP-007) | always |
| 17 | business-logic validation worked examples | BUSINESS-LOGIC-VALIDATION (G7 line) | money/business rule |
| 18 | CEO provisioning manifest | CEO-PROVISIONING-MANIFEST (G7 line) | external provisioning |
| 19 | production-readiness triggers answered (Piece 4) | production-readiness section/file | always |
| 20 | builder coding standard named (Piece 5) | pointer to BUILDER-STANDARD.md + project deltas | always |

**"always" categories (1–4, 10–13, 15, 16, 19, 20) may never be N/A** — the checker
rejects it (a thin packet must not pass green). Conditional categories N/A with a written
`na_because`. **V1 re-base deltas from v0.13's 23:** v0.13 cats 17/18 (wave plan, wave
build contract) are **dissolved into the card deck**; 21–23 became rows 19/16/20 — the
build-runbook half of v0.13 cat-23 is V1-owned by KERNEL/GATES/ROUTING and is NOT packet
content. Net: **20 categories.** The number is not sacred; the AUDIT is: every category
accounted for.

**Category 14 — visual provenance + external references (PROP-031, 2026-06-20).** When category 14
is DONE (user-facing app), beyond the PRODUCT-TASTE-LOCK `locked_style_direction` (PROP-016) the
packet carries `screens-manifest.yaml` — every user-facing screen with a `visual_provenance`
(`original | external_reference | derived_from_locked_style`); a screen with its look-source unstated
FAILS `cx check packet` ("like a reference app" can no longer be a silent prose aside). Any `external_reference`
screen additionally requires `external-visual-references.yaml` INSIDE the frozen packet hash: the
named app's real screens CAPTURED + pinned read-only (per-capture `file_hash` + a set `manifest_hash`
+ repo-relative path-safe `file_path`), bound to the screen by `ref_id` with `{target_viewports,
borrowed_axes, excluded_axes}` and a capture at every target viewport. A verbal "confirmed the UX" is
never a capture. (The lock-side binding + the side-by-side CEO ACCEPT receipt live in GATES G6 /
`cx check design-fidelity`.) Category 14 N/A = not user-facing = clause silent.

## Piece 2 — Completeness-audit gate (fresh cold reader)

**When:** after all packet docs are drafted, **BEFORE** CEO business-logic validation and
BEFORE the packet freezes / the Card Compiler cuts the deck. Origin scar: a prior project —
completeness gaps surfaced only during CEO validation; "looks done but isn't" wasted the
CEO's time.

- **Mechanical half (`cx check packet <packet-dir>`, BUILT):** coverage map present +
  all 20 rows valid (existing non-trivial files / written N/A; always-on never N/A);
  `requirements-manifest.yaml` + `CEO-DECISION-LEDGER.md` (both sections) +
  `completeness-audit.md` inside the packet dir (inside the hash); no MISSING/PARTIAL
  left open in ledger or audit.
- **Semantic half (fresh cold reader, NOT the packet's writer):** every ask in the CEO
  Asks Register traced to the exact doc location that satisfies it → `DONE | MISSING |
  PARTIAL`. Any MISSING or PARTIAL → return to writing; cannot advance. The mechanical
  check NEVER claims to replace this — it only proves the artifacts exist and no open
  item was frozen over.
- **Output:** `completeness-audit.md` appended to the packet (inside the hash).

**Planning-studio ladder (strict order, ports v0.13's writing_stage_complete_ladder):**
1. all packet docs written → 2. completeness audit clean → 3. CEO business-logic
validation signed (or N/A) → 4. self review (full audit + security) → 5. cross-family
review LAST → packet freezes → deck compiles (G1). No build talk before G7.

**Review-backflow rule (GPT P2-02, adopted at fold):** if self review or cross-family
review changes product intent, money/business logic, a security/privacy tradeoff, packet
requirements, or CEO decisions, the packet must **return to the affected CEO validation**
/ decision step before freeze. Not a new review loop — a correctness backflow. (Semantic
rule — enforced by process + review methodology, not by a checker; honest scope.)

**WRITING-stage front-end hardening (PROP-023, 2026-06-20 — part of v1.13).** Two HARD
mechanical clauses ride the mechanical half, both firing at the WRITING→freeze boundary
(GitHub Spec Kit's two enforcement-neutral front-end ideas rendered as Code-X clauses that
actually bite — never the prose, self-exemptible gates Code-X exists to kill):
- **(a) clarify-before-freeze.** Packet authoring runs a templated ambiguity-elicitation
  pass; every open / under-specified point is tagged inline with the ONE canonical marker
  `[NEEDS-CLARIFICATION: <question>]`, raised to the CEO, and resolved to a
  CEO-DECISION-LEDGER row before its inline marker is removed. Resolutions are recorded in a
  STRUCTURED `clarification-sweep.yaml` (a `clarification_sweep.clarifications` list; empty =
  swept, nothing raised). `cx check packet`: requires that artifact (absence of markers is
  NOT proof the sweep ran); FAILS while ANY `[NEEDS-CLARIFICATION]` marker survives in a
  content doc (EVERY non-binary file is scanned — only the root sweep is excluded — so a
  marker hidden in a `.json` or extensionless file cannot dodge); and requires every listed
  clarification's `ceo_decision_ref` to **RESOLVE to a real `CEO-D-NNN` ledger row** — a ref
  that merely looks valid but names no row (or an inline free-text dismissal) is the
  self-exemption escape hatch this floor rejects. (Built-code GPT/Codex review hardened the
  artifact from free-text to structured so the fake-ref / case-variant / false-positive
  bypasses cannot exist.)
- **(b) testable acceptance criterion.** Every BUILDING row in `requirements-manifest.yaml`
  carries a structured `acceptance_criterion: {pass_condition, evidence_type,
  verification_ref}`, present + non-placeholder **string** (a bool / list / dict does not
  pass via str-coercion). Scoped to BUILDING (dispositioned-out rows already carry ref/reason
  semantics via `cx check deck`). **This is a PRESENCE + structure gate, NOT an
  English-quality gate** — the cold-reader completeness audit (the semantic half above)
  judges whether the criterion is actually *testable*; a literal "is this measurable" checker
  would over-claim, the cardinal sin. A requirement with no testable acceptance criterion is
  exactly what drifts undetected to acceptance (the live-production drift class). GREEN = the
  structured fields are present + filled, NOT that the requirement is unambiguous.

## Piece 3 — CEO-DECISION-LEDGER (asks + decisions, one home)

`CEO-DECISION-LEDGER.md` inside the packet, **append-only**, with **two REQUIRED
sections** (GPT P1-01, adopted as Option B — one file, two registers):

1. **`## CEO Asks Register`** — everything the CEO requested, in the CEO's words,
   BEFORE it becomes a requirement or dies silently. Fields per row:
   `id | date | ask_in_ceo_words | status | satisfied_in | superseded_by` with
   `status: DONE | PARTIAL | MISSING | SUPERSEDED | NOT_APPLICABLE`. The completeness
   audit traces FROM this register; `cx check packet` fails any ledger still carrying
   MISSING/PARTIAL. Origin scar: a CEO directive said many times was lost from docs
   (a copy-verbatim requirement, 2026-06-09).
2. **`## Decisions`** — chosen decisions, rows `CEO-D-NNN`:
   `id | date | decision (CEO's words) | scope | supersedes`. Legacy/pre-V1 decisions
   migrate as `CEO-D-LEGACY-NNN` rows (source: v0.13 / chat / old handoff) — "decision
   lives in a chat transcript" is exactly the hole this closes.

Every `ceo_decision_ref` (requirements-manifest NOT_BUILDING/CEO_DEFERRED rows, state
items, queue entries) points to a row id — **`cx check deck` verifies every ref resolves
to a ledger row (BUILT, P1)**. Protocol-level decisions have their own ledger:
`MEMORY/CEO-DECISION-LEDGER.md`.

## Piece 4 — Production-readiness triggers (R1–R6 + S1–S4)

Ported intact from v0.13 (CEO-approved 2026-06-02, freemium tool stack included).
**Trigger checklist answered at planning; recorded in the packet (coverage-map row 19):**
money/charges? (business-logic validation already covers) · paid/external service? → R6
cost guardrails · many concurrent users? → R5 load sanity · sensitive/biometric data? → S4.

- **Always-on per client-facing ship (wired into G8 final-ready):** R1 resilience/
  failure-mode (timeouts, clear error states, no duplicate-on-retry) · R2 real-environment
  proof (fresh install, empty states, env-completeness) · R3 observability wired BEFORE
  ship (crash + uptime + usage; first-hour watch) · R4 recovery runbook (plain "if X
  breaks do Y" + 1-command rollback a non-coder can run).
- **Risk-gated:** R5 load (k6/Artillery) · R6 cost caps (budget caps + rate limit).
- **S1 dependency / supply-chain scan — HARD pre-build GATE (PROP-027, amends this piece):**
  `cx check dep-scan` requires a typed `dependency_scan` receipt — 0 high/critical (or a typed
  CEO waiver → CEO-DECISION-LEDGER) · every manifest/lockfile pair scanned · each lockfile
  hash-bound (stale/forged or post-gate drift = fail) · re-scan pre-ship (G8). The receipt
  lives OUTSIDE the frozen packet (`templates/DEPENDENCY-SCAN-RECEIPT`). A G7
  build-authorization line; for a public vibe-coder audience pulling arbitrary packages,
  unscanned supply-chain is the #1 real-world risk (npm-worm class).
- **Security sharpenings (ride EXISTING reviews — G2 baseline + security delta — no new
  gate):** S2 auth-boundary TEST (actually attempt cross-user access) · S3 PII
  baseline (inventory → encrypt → least-access → retention → consent) · S4 sensitive/
  biometric escalation (consent + encryption + retention + breach plan; UU PDP frame).
- Skips are written: `NOT APPLICABLE because no trigger fired`. Dormant by default:
  multi-region, read replicas, geo-routing, Redis caching.

## Piece 5 — BUILDER-STANDARD.md (the coding standard)

`Code-X-V1/BUILDER-STANDARD.md` (BUILT at fold) — the 12 rules + stop-instead-of-guessing
+ builder self-check. **Session-level read law:** the build engine reads it ONCE at
session start, NOT per card; cards carry the compiler-injected token
`relevant_invariants: [builder-standard]`. **Session acknowledgment (GPT P2-01, adopted):**
the session records `session_start.builder_standard_read` (status PASS + file + hash
sha256-12 + read_by + timestamp) in CODE-X-STATE.yaml — `cx check state --session-start`
rejects a build-mode session without it (P2) and flags a hash that no longer matches the
live standard (drift). Honest scope: proves WHICH version was acknowledged, not that it
was internalized. Packet coverage-map row 20 names the standard + any project deltas.
[RULE:builder-standard-session-read]

## Enforcement (BUILT 2026-06-10 — binds BY CHECKER)

`cx check packet <packet-dir>` + 10 contract clauses, each with a pinned biting bad
fixture (PROP-004 discipline): PACKET-COVERAGE-MAP-REQUIRED · PACKET-COVERAGE-ALL-CATEGORIES ·
PACKET-COVERAGE-FILE-EXISTS · PACKET-ALWAYS-CATEGORY-NA · PACKET-LEDGER-ASKS-REGISTER ·
PACKET-OPEN-ASKS-BLOCK-FREEZE · PACKET-COMPLETENESS-AUDIT-REQUIRED (all P1) ·
DECK-CEO-REF-RESOLVES (P1, deck-side) · STATE-BUILDER-STANDARD-ACK (P2, state-side) ·
CARD-PROFILES-ENV-TEST-ONLY (P1 — `CX_PROFILES` honored only with `CODE_X_TEST_MODE=1`;
production reads live canon, fail-loud, GPT P1-02). G7 carries the packet-floor line;
G8 carries the R1–R4 always-on lines.

Later v1.13 folds added more `cx check packet` clauses, each with a pinned biting fixture:
PROP-031 (external-visual-reference) the `PACKET-PROP031-*` provenance/capture clauses;
**PROP-023 (WRITING-stage front-end hardening) five clauses — PACKET-CLARIFY-SWEEP-REQUIRED ·
PACKET-CLARIFY-NO-OPEN-MARKERS · PACKET-CLARIFY-RESOLUTION-LEDGER-BOUND ·
PACKET-ACCEPTANCE-CRITERION-REQUIRED · PACKET-ACCEPTANCE-CRITERION-FILLED** (all P1, see EVAL-027).

## What this floor does NOT do (anti-bloat)

No new review actors (fresh-cold-reader slot exists in G-flow; cross-family unchanged).
No per-card reading growth (session-level standard; card carries one invariant token).
No v0.13 lane/ledger machinery revival (Continuity Ledger stays archived; the asks
register is one section in one packet file). No new user-facing scripts (`packet` rides
the one `cx` surface, anti-bloat ceiling respected).
