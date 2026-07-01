# Code-X V1 — MASTER-BLUEPRINT.md (the planning-stage artefact)

> Added by P-PROP-005 (fold v1.18). Code-X's PLANNING stage produced ~10 scattered yaml/md/html files a
> non-coder cannot review as ONE thing — so the plan the CEO *thought* he approved drifted from the plan
> that was *written*, invisibly, until build/demo. The **Master Blueprint** is the fix: ONE auto-generated
> page that is the CEO's single surface to review and drive the whole plan — every screen, what each
> control does, how screens connect, and a written "done" test per feature. A module is **buildable only
> after the CEO approves it on the blueprint**, and the gate **recomputes readiness from source** — never
> from a written flag. Planning sibling of `FIXING-STAGE.md`; rides existing machinery (frozen packet hash
> + requirements-manifest + `cx check deck` + Mode A + the v1.10 order wall + `cx_lock_fidelity`), no new
> gate family for the build-blocker. [RULE:master-blueprint-gate]

## The artefact + the iron rule

The **Master Blueprint** is ONE auto-generated HTML page projecting the whole locked plan for the CEO.
🔒 **RENDER, NEVER RE-TYPE** [RULE:render-never-retype]: the page is a *projection* of the locked
source-of-truth files; no human types content into it; change the plan → regenerate. A hand-written
blueprint would become a 4th drifting truth — forbidden. The same rule extends to EDITS (see "The edit
flow"): the page is never edited directly.

**🔒 VISUAL LOCK — the CEO SEES the finished software (the single most important thing the blueprint does for a non-coder).** The blueprint **EMBEDS the actual locked screen designs** (rendered, device-framed) — so the CEO sees what the WHOLE finished software will look like, screen by screen, **before a single line of it is built**. It is not a written description of the app; it is the app's finished face, shown and approved up front. The design is **locked in PLANNING** (Mode A moves into planning, per module — the CEO approves each screen's look before any engine), and the build then has to MATCH that locked visual. The CEO approves the finished picture, not a guess from text. Enforcement: `BLUEPRINT-SCREEN-DESIGN-LOCKED` (every screen module carries a hash-bound `ui_lock_manifest`, which the generator embeds live) + the CEO approval receipt recorded against the rendered blueprint.

## The two artifacts — split by mutability (the load-bearing design)

Behind the page sit TWO machine-readable artifacts. **Mutable state must never live inside a frozen-hash
artifact** — so:

| Artifact | Mutability | Home | Holds |
|---|---|---|---|
| `blueprint-manifest.yaml` | **immutable** | **inside the frozen packet** (packet-hash-bound) | the plan: modules · anchors · controls→`contract_id` · nav · journeys · risk callouts. **No approval/review fields. No self-referential packet-hash.** |
| `BLUEPRINT-APPROVAL.yaml` | **mutable** | **outside the packet**, state-referenced | per-module **approval receipts** + **review receipts**, each hash-bound to `{module_id, packet_hash, manifest_hash, approved_source_hash}` |

This is the `verify_app` / `live_slice_accept` receipt pattern (B-PROP-008 · B-PROP-010): writing an approval can
never mutate the packet hash and break G1. **The HTML is decorative; the two artifacts are what the gate
reads; the packet source is the ground truth — `cx check blueprint` recomputes every claim.**

## Screen / module-first planning

The unit of planning is the **module**; for a user-facing app **module = screen** (each screen its own
module: locked design + its features + what each control does). Engine rules with no screen group into
per-area **`shared_logic`** modules.

**Per-kind required fields — NO buildable kind bypasses readiness:**
- `kind: screen` → locked design + nav + controls/behaviour-contracts + done-tests + approval + risk-review (where required) + anchor-coverage.
- `kind: shared_logic` → design + nav **N/A** (explicit reason, never a silent skip); STILL requires done-tests + approval + risk-review (where required) + source-anchor-coverage.

**Sequence preserved:** the screen-first **MODULE-REGISTRY** is drafted in planning → packet-floor proves
it covers every screen/shared module + every requirement ID → **packet freezes (hash)** → **G1 compiles
cards against the frozen hash** (G1 order + the card `locked_packet_hash` binding UNCHANGED). The registry
moves earlier; the freeze→compile contract does not.

## The always-on completeness checklist (4 items — never hidden)

Every module's blueprint shows these with ✅/⚠️/❌, and `cx check blueprint` recomputes each:

1. **Every screen has a locked design, embedded live** — a hash-bound `ui_lock_manifest` (style locked
   P-PROP-002 · provenance satisfied P-PROP-004); the blueprint EMBEDS the rendered locked design so the CEO
   sees the finished look (the visual lock above). N/A for `shared_logic`.
2. **Screen-to-screen nav map is complete** — every nav `to_screen` resolves to a registered screen (no
   dangling). N/A for `shared_logic`.
3. **What each control does** — a **behaviour contract** per control (NOT just a label).
4. **Every feature has a written "done" test** — a P-PROP-003 `acceptance_criterion {pass_condition,
   evidence_type, verification_ref}` (reused, not reinvented).

The gaps view (⚠️/❌ items) is **vital and must never be hidden** (CEO).

## Behaviour contracts

Each control carries a **behaviour contract** with a canonical SOURCE inside the packet
(`behaviour-contracts.yaml`): `contract_id → {tap_outcome, state_change, error_empty, done_test_ref}`.
Controls carry a `contract_id`; the generator RESOLVES it. The locked screens' `data-fn` / `data-fn-type`
attributes + nav `href`s only **identify** controls/links/nav edges — they never *synthesize* a contract.
A control with no resolving contract blocks the module's approval.

## Source anchors + approval bound to source-hash

Every visible blueprint item carries a stable **source anchor** `{anchor_id, file, section, line,
requirement_id, source_hash}` (source_hash = sha256 over the anchored span). Edits map from the selected
anchor id, never fuzzy text. **Anchor coverage is a biting clause** (`BLUEPRINT-ANCHOR-COVERAGE`): the
expected anchor set is DERIVED from MODULE-REGISTRY + requirements-manifest + screens/ui-lock +
behaviour-contracts + clarification-sweep; a missing OR duplicate anchor fails — an incomplete manifest
cannot hash cleanly and slip through.

**Approval is bound to a recomputed module source-hash, in a receipt OUTSIDE the packet.** The receipt
records `approved_source_hash` = hash over the module's coverage-complete anchor source_hashes. Any later
change to any anchored span recomputes a different hash → the approval is **automatically invalidated**
(`BLUEPRINT-APPROVAL-CURRENT` fails) and the module returns to "Changed-since-approval" until re-approved.
Rides the `cx_lock_fidelity` recompute pattern (fail-closed, no symlinks).

## The computed gate — `cx check blueprint` (the per-module build-blocker)

`cx check blueprint <packet-dir> --module <id> --state <state.yaml> --approval <BLUEPRINT-APPROVAL.yaml>`
(or `--all`). It **recomputes module readiness from canonical sources** — never a written `finalized`
flag, an HTML badge, or a manifest boolean. A module is **BLUEPRINT-READY** only when ALL hold:

- every screen has a locked design + the anchor set is coverage-complete + every anchor resolves;
- nav map complete (screen kind);
- every control resolves to a behaviour contract in the packet source;
- every BUILDING requirement in the module has a done-test;
- no open `[NEEDS-CLARIFICATION]` marker (P-PROP-003) in the module's scope;
- CEO approval receipt present AND `approved_source_hash` == the recomputed current source-hash (stale approval = not ready);
- opposite-family review RECEIPT present where required — review-required DERIVED from the frozen registry `risk_flags` (the four G5 classes: money/auth/shared-data-shape/secrets), NOT a manifest boolean; receipt typed + path-safe + hash-bound;
- no open P0–P3 mapped to the module (read from `--state`; fail-closed to global findings when attribution is absent).

**Build-blocker is PER-MODULE, riding the order wall:** `cx check module-start` gains the precondition
"target module is BLUEPRINT-READY", proven THROUGH `cx check build-turn` (a MODULE/MODE_A card reaching
build-turn with stale/missing blueprint approval fails via module-start). A BLUEPRINT-READY module is
buildable; a non-ready module is hard-blocked. The project-level **G7** floor stays once-per-project
(packet floor, security, provisioning); the blueprint gate is the per-module layer. **No new gate family.**

## The edit flow (the blueprint is the user's ONLY surface)

The CEO reads + drives everything from the blueprint; the construction docs are builder-only. To change
something: the CEO files a request **on a blueprint element** (by anchor id) in plain language → the AI
maps it to the right SOURCE location → proposes the exact source edits + the affected modules → the CEO
approves the EDIT INTENT → the AI edits only those anchors → re-render shows before/after → only the
changed modules lose approval (via the source-hash invalidation above). The **enforceable** part is the
source-hash currency; the "edits only those anchors / before-after preview" mechanics are honest PROCESS
guidance (a typed change-request receipt is a future-Kaizen rider, not a v1.18 claim).

## The cockpit + risk callouts + plain language

The page renders ONE **approval cockpit** — each module shows one computed status: **Ready ·
Needs-decision · Changed-since-approval · Blocked · Builder-only** (decorative; truth is `cx check
blueprint`). **Risk callouts** flag money / data / privacy items tied to their proof. Surfaced text is
**plain language** with an **auto-glossary** for any surviving jargon (the "dedupe" lesson); builder/
technical detail is collapsed at the bottom. Dependencies are blockers-only context, not a big surface.

## Honest limits (fail-closed, stated up front)

- HTML decorative; the manifest (immutable, in-packet) + the approval/review receipts (mutable,
  out-of-packet) are the gated objects; **source is the ground truth** — cx recomputes, never trusts a
  flag/badge/boolean; mutable state never lives inside the frozen packet.
- **Generator faithfulness is bounded** — it derives behaviour/nav from locked-screen attributes +
  packet contract source; a missing attribute/contract fails closed, it never invents behaviour.
- **Anchor coverage is only as complete as its derivation sources** (registry/requirements/contracts);
  a requirement absent from ALL canonical sources can't be demanded — the deck reverse-coverage +
  registry-covers-requirements clauses bound this.
- `source_hash` proves the plan **didn't change** since approval, not that it is **correct** (the CEO +
  review own correctness). Mirrors `live_slice_accept` / `verify_app` honest scope.
- Plain-language / glossary is **presence + generation, not an English-quality gate** (P-PROP-003 pattern).
- Legacy build-wave-first packets keep heuristic screen↔module matching until re-planned screen-first.
- Portable `cx check` (no Claude-only hook dependency).

## Enforcement (so green = enforcing)

Biting clauses in `checkers/check-contracts.yaml` (`BLUEPRINT-*` + the packet-floor
`PACKET-MODULE-REGISTRY-*` + the order-wall `MODULE-START-BLUEPRINT-READY`), each with a pinned BAD
fixture that fails-closed at the stated severity, proved by `tests/run_contracts.py`. Checker: new
`cx_blueprint.py` (the `blueprint` subcommand); the BLUEPRINT-READY precondition rail-wired into `cx check
module-start` + `cx check build-turn`; packet-floor registry coverage in `cx check packet`. See `GATES.md`
(the order-wall wiring + G6/G7 lines), `PACKET-CONTENTS.md` (the screen-first planning ladder),
`MEMORY/PROTOCOL-IMPROVEMENT-QUEUE.md` (P-PROP-005), and
`design-history/prop-039-gpt-review-synthesis-2026-06-25.md` (the review synthesis).
