# Code-X V1 — FIXING-STAGE.md (the 3rd stage)

> Added by F-PROP-001 (fold v1.16). Code-X had two stages — **Planning** → **Building**. Fixing is
> the third. It exists because **fixing the app drifts the app**: agents treat "fix X" as licence
> to "improve X" (over-edit), and the AI forgets a decision the CEO already made and re-asks it
> (decision-amnesia). Building CREATES; Fixing **PRESERVES — change only the defect.**
> Siblings: P-PROP-004 (visual reference) · B-PROP-009 (render-fidelity) · BF-PROP-007 (lock-fidelity
> continuity). Fixing is the STAGE those locks live in; it EXTENDS BF-PROP-007's `mode: FIX`, it does
> not parallel it. [RULE:fixing-stage-preserve-posture]

## The three stages

| Stage | Posture | Drift |
|---|---|---|
| 1 · Planning *(unchanged)* | decide + freeze | n/a |
| 2 · Building *(unchanged)* | **CREATE** | some drift normal |
| 3 · **Fixing** | **PRESERVE** — change only the defect | **drift = failure** |

Two CEO design decisions (locked 2026-06-23):
- **CEO-D-FIX-A — "every fix is Fixing."** The preserve-posture turns on for ANY fix, even mid-build
  self-heal — over-edit fires during self-heal too, not only when re-touching an approved screen.
- **CEO-D-FIX-B — "same rules, scaled ceremony."** The fix-RULES (minimal diff · no restructuring ·
  don't touch locked surfaces · revert-on-drift) apply to EVERY fix. The HEAVY gate (structural
  re-freeze + CEO re-accept) fires only when touching an already-accepted / locked artifact. In-build
  self-heal obeys the rules inline — so a normal build does not grind.

## The organizing principle — lock everything you are NOT fixing (the cross-lock)

You do not choose "frontend" or "whole app" up front. **Each fix names ONE target; everything else
freezes.** The two layers cross-lock:

| Target of the fix | LOCKED (drift = fail) | OPEN |
|---|---|---|
| a **frontend** thing (button / screen / style) | every *other* screen · the rest of *this* screen's look · the whole file/component/route tree · **all business rules + data + backend** | the one component/style the fix names |
| a **business rule** (money / logic) | the **entire frontend** (look + structure) · all *other* rules + invariants · the data schema/contracts · the decision ledger | the one rule's logic in its engine file(s) |

Cross-layer bugs are **not** blocked — a genuine both-layers bug becomes **two fix cards**, or one card
that explicitly declares both targets (`fix_targets: [frontend, business_rule]`). The CEO is forced to
say "I'm crossing layers" out loud; the drift can't happen silently.

### `fix_targets` — the typed taxonomy (cross-lock, Lever C)

A `mode: FIX` card declares `fix_targets` from this CLOSED set; everything outside the declared
targets' surfaces is a **frozen assertion** (any change there fails):

`frontend` · `business_rule` · `data_schema_migration` · `api_contract` · `auth_security` ·
`infra_config` · `content_copy`

A multi-target fix carries **one `lock_anchor_ref` + reason per target** — no blanket "declare
everything to open everything." Crossing into a non-declared surface = **P1**; **P0 only** when the
crossed surface is a danger class (money · auth · secrets · shared-data-shape · migration · destructive).

## The five levers

- **Lever A — `cx check structure` (Layer-1 deterministic, BITES).** At screen/module acceptance (or
  step-0 freeze-baseline) Code-X emits a **`structure_lock` receipt**: a machine-generated, ordered,
  hashed list of in-scope file PATHS — repo-root bounded, no symlink / `..`, `sha`-bound to the
  accepting commit, **never self-declared**. `cx check structure` RECOMPUTES it from the real tree and
  compares. A `mode: FIX` card that creates / renames / moves / deletes a file outside its declared
  `allowed_files` vs the frozen lock → **FAIL (P1) → surface + require revert** (Lever E). Rail-wired
  into `cx check build-turn` for every `mode: FIX` and into the v1.10 module-acceptance Andon wall; a
  `mode: FIX` card with no `structure_lock_ref` fails closed. **Honest Layer cut:** Layer-1 (blocking) =
  **file-tree / PATH changes only** — fully deterministic. Component/route/CSS restructuring that
  changes *structure without changing paths* is **Layer-2 ADVISORY WARN** in v1.16 (graduates to
  blocking via a follow-up PROP once machine-extraction + same-commit repeatability is proven — the
  B-PROP-009 staging). The CEO's stated symptom (file/folder structure wandering) is fully covered at
  Layer-1; same-file restructuring is meanwhile mitigated by the visual lock + `allowed_files`.

- **Lever B — the anti-amnesia gate (file-backed questions).** Every FIX-stage CEO question must be
  **FILE-BACKED at the time it is asked** — appended to a typed `FIX-QUESTIONS-LOG` (or a STOP card)
  before / as it goes to the CEO. `cx check close-turn` then **reconciles every open question** in the
  handoff/evidence to a log row, and each row must carry one of: `ledger_searched: true` +
  `related_ceo_d_refs` (must resolve to real ledger rows — ghost refs fail), a `new_ledger_row_ref` for
  a genuinely new decision, or `contradicts_ceo_d` + a resolved path-safe `ceo_override_ref` for an
  answer that CHANGES a locked rule. P1 default; **P0 only** when the contradicted rule is a danger
  class. **Honest limit:** a truly off-the-books chat question can still be omitted — but omission now
  produces a `close-turn` mismatch against the handoff STOP markers, so it is *detectable*, not silent.

- **Lever C — per-target cross-lock.** The `fix_targets` taxonomy above. Each target has declared
  allowed surfaces; everything else is a frozen assertion.

- **Lever D — always-on guardrails (presence + anti-drift, like B-PROP-005).** Cheap rules enforced by
  PRESENCE in canon (not mechanical detection):
  - **Always-read hard rule:** *never create, rename, move, delete, or refactor "for improvement"; if a
    fix seems to need a structural change, STOP and ask.* [RULE:fixing-stage-preserve-posture]
  - **Never mix fix + improve:** a fix dispatch says *"fix bug only, preserve everything else"* OR
    *"redesign only, no logic changes"*, never both. Forbidden-during-a-fix list (unless the fix names
    it): layout · spacing · colours · typography · copy · component names.
  - **SCREEN_CONTRACT per locked screen** (Purpose / Must-preserve / Forbidden) + **plan-then-wait
    scoped to risk:** the fixer shows its plan and waits for CEO OK before editing a locked artifact, or
    any product / UX / business / security / cross-target change — NOT every compile/test self-heal
    iteration (that would grind builds — CEO-D-FIX-B). The preserve-rules still apply to every fix; only
    the *wait* is risk-scoped.

- **Lever E — revert-on-drift + scaled ceremony.** No checker ever runs `git reset` (checkers are
  read-only validators — auto-reset risks destroying legitimate WIP). On any Layer-1 lock fail the wall
  surfaces FAIL and blocks, and the fixer produces a typed **`revert_receipt`** — `bad_head`,
  `restored_head`, a clean post-revert diff on the locked surfaces, explicit WIP handling — before
  re-approaching tighter (not fix-forward). Scaled ceremony: rules always on; the heavy gate
  (structural re-freeze + CEO re-accept) only when touching a locked artifact.

## Entry / exit

- **Enter Fixing** when the work is to repair an existing, already-built (and usually already-accepted)
  surface — not to build new locked scope. State carries `current_stage: FIXING_STAGE`; the seat cap is
  read from the `fixing_stage` profile in `BUILD-ENGINE-PROFILES.yaml`.
- **Step 0 — freeze-baseline (forward-scope).** A lock can only be protected if it exists. For an
  already-drifted app (live-production, Sample) the stage opens with a one-time freeze-baseline: accept current-good,
  capture the `structure_lock` manifest, confirm the ledger. F-PROP-001 does **not** retroactively
  un-drift already-built screens — it freezes current-good and protects forward (exactly like its
  siblings).
- **Exit** a fix when its card passes `cx check build-turn` (structure + scope + evidence) and — for a
  locked artifact — the module-acceptance Andon wall (Layer-1 structure + drift) plus CEO re-accept.

## Honest limits (fail-closed, stated up front)

- Anti-amnesia is **receipt-deep, not mind-reading** — it proves a `ledger_searched` receipt + ref
  resolution; it cannot prove the AI actually USED the answer. A contradiction without a resolved
  override is a hard finding (P0 on a danger class).
- Structural **Layer-1 = file tree only (blocking)**; same-file restructuring is Layer-2 advisory.
- `deviation_class: SCOPE_CHANGE` honesty (inherited from BF-PROP-007) — a builder could mislabel a
  scope-change as a restore; the opposite-family reviewer audits the classification.
- Freeze-baseline is forward-scope.

## Enforcement (so green = enforcing)

16 biting clauses in `checkers/check-contracts.yaml` (`FIX-STAGE-*`), each with a pinned BAD fixture
that fails-closed at the stated severity, proved by `tests/run_contracts.py`. Checkers: new
`cx_structure.py` (the `structure` subcommand); anti-amnesia + revert-receipt folded into `cx check
card` + `cx check close-turn`; structure rail-wired into `cx check build-turn` + the module-acceptance
wall. See `GATES.md` (the Andon-wall wiring), `MEMORY/PROTOCOL-IMPROVEMENT-QUEUE.md` (F-PROP-001), and
`design-history/prop035-fixing-stage-2026-06-23.md` (the spec).
