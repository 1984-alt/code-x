# PROP-CROSSWALK.md — canonical PROP id crosswalk (old ↔ new)

> The permanent bridge between pre-v1.21 `PROP-NNN` ids (still in VERSION-HISTORY, the CEO
> ledger, git history, design-history, handoffs, and the public mirror) and the
> stage-categorized ids introduced by PROP-043 (= PBF-PROP-013). This file is itself FROZEN
> (it must hold the old ids); never swept.

## Active renames (42)

| old | new | title |
|---|---|---|
| PROP-001 | PBF-PROP-001 | Consistency lint |
| PROP-002 | PBF-PROP-002 | SSOT + checks-first |
| PROP-003 | B-PROP-001 | Review per module |
| PROP-004 | PBF-PROP-003 | Contract-bite harness |
| PROP-005 | PBF-PROP-004 | Scope strict consistency sweep |
| PROP-006 | PBF-PROP-005 | Review methodology (3-leg) |
| PROP-007 | PB-PROP-001 | Round-4 lock bundle (reverse coverage) |
| PROP-008 | BF-PROP-001 | Evidence-integrity (merged 008+009) |
| PROP-011 | PBF-PROP-006 | Sorted set output |
| PROP-012 | PBF-PROP-007 | Consistency WARN tuning |
| PROP-013 | PBF-PROP-008 | Build-engine profiles |
| PROP-014 | P-PROP-001 | Packet-contents floor |
| PROP-015 | PBF-PROP-009 | Three-leg ask every review |
| PROP-016 | P-PROP-002 | Style-Select gate |
| PROP-017 | PBF-PROP-010 | Review-lessons loop |
| PROP-018 | B-PROP-002 | Build-session command rail |
| PROP-019 | B-PROP-003 | UI-contract + design-fidelity |
| PROP-020 | BF-PROP-002 | Typed deviations + incidents |
| PROP-021 | BF-PROP-003 | Fix-escalation ladder |
| PROP-022 | B-PROP-004 | Proof-card honesty |
| PROP-023 | P-PROP-003 | WRITING-stage front-end |
| PROP-024 | B-PROP-005 | Prevention-first do-less ladder |
| PROP-025 | BF-PROP-004 | Engine-epoch fix-cycle fix |
| PROP-026 | BF-PROP-005 | xfam ladder + egress scrub |
| PROP-027 | B-PROP-006 | Dependency pre-build scan |
| PROP-028 | BF-PROP-006 | Phantom-completion guard |
| PROP-029 | PBF-PROP-011 | Plain Talk / VOICE |
| PROP-030 | B-PROP-007 | Built-App Audit |
| PROP-031 | P-PROP-004 | External-visual-reference lock |
| PROP-032 | B-PROP-008 | Live Slice Delivery |
| PROP-033 | B-PROP-009 | In-loop rendered-fidelity gate |
| PROP-034 | BF-PROP-007 | Lock-fidelity continuity |
| PROP-035 | F-PROP-001 | The Fixing Stage |
| PROP-036 | B-PROP-010 | Verify-App Gate |
| PROP-037 | B-PROP-011 | Build-turn path-safety |
| PROP-038 | B-PROP-012 | Path-safety hygiene tail |
| PROP-039 | P-PROP-005 | Master Blueprint |
| PROP-040 | P-PROP-006 | Whole-packet integration review |
| PROP-041 | PB-PROP-002 | Registry build-shape floor |
| PROP-042 | PBF-PROP-012 | Review-routing + orchestration |
| PROP-043 | PBF-PROP-013 | Stage-rename + crosswalk |
| PROP-044 | PBF-PROP-014 | No-ambiguity rule |
| PROP-045 | PBF-PROP-015 | cx_state arity crash fix (parse-P0 masking) |
| PROP-046 | PBF-PROP-016 | Public CI runs the full eval gate (run.py-only scar) |
| PROP-047 | P-PROP-007 | Blueprint visual parity (storyboard + prototype tab + anchor ids) |
| PROP-048 | PBF-PROP-017 | One-line installer, dependencies pulled from official sources |
| PROP-049 | PBF-PROP-018 | Stage routing recognized + preserve posture on accepted surfaces |
| PROP-050 | B-PROP-013 | /cx-accept forge-parity acceptance recompute (CHARTER §4 promotion) |
| PROP-051 | PB-PROP-003 | Given/When/Then executable acceptance examples |
| PROP-052 | PBF-PROP-019 | Tiered strictness — per-project risk tiers (LITE/STANDARD/STRICT) |
| PROP-053 | PBF-PROP-020 | Mockup-first change rule — no unrendered visuals anywhere in the loop |

## Retired (no new id)

| old | disposition |
|---|---|
| PROP-009 | MERGED-INTO BF-PROP-001 (evidence-integrity) |
| PROP-010 | CLOSED-REJECTED (action-time hook rejected by xfam) |

## Frozen clause-ids (never renamed)

| clause-id | reason |
|---|---|
| PROP-028-NO-REPO-SHA | immutable contract identifier — rename would break harness |
| PROP-028-MALFORMED-REPO-SHA | immutable contract identifier — rename would break harness |

## Reverse lookup (new → old)

| new | old |
|---|---|
| B-PROP-001 | PROP-003 |
| B-PROP-002 | PROP-018 |
| B-PROP-003 | PROP-019 |
| B-PROP-004 | PROP-022 |
| B-PROP-005 | PROP-024 |
| B-PROP-006 | PROP-027 |
| B-PROP-007 | PROP-030 |
| B-PROP-008 | PROP-032 |
| B-PROP-009 | PROP-033 |
| B-PROP-010 | PROP-036 |
| B-PROP-011 | PROP-037 |
| B-PROP-012 | PROP-038 |
| BF-PROP-001 | PROP-008 |
| BF-PROP-002 | PROP-020 |
| BF-PROP-003 | PROP-021 |
| BF-PROP-004 | PROP-025 |
| BF-PROP-005 | PROP-026 |
| BF-PROP-006 | PROP-028 |
| BF-PROP-007 | PROP-034 |
| F-PROP-001 | PROP-035 |
| P-PROP-001 | PROP-014 |
| P-PROP-002 | PROP-016 |
| P-PROP-003 | PROP-023 |
| P-PROP-004 | PROP-031 |
| P-PROP-005 | PROP-039 |
| P-PROP-006 | PROP-040 |
| PB-PROP-001 | PROP-007 |
| PB-PROP-002 | PROP-041 |
| PBF-PROP-001 | PROP-001 |
| PBF-PROP-002 | PROP-002 |
| PBF-PROP-003 | PROP-004 |
| PBF-PROP-004 | PROP-005 |
| PBF-PROP-005 | PROP-006 |
| PBF-PROP-006 | PROP-011 |
| PBF-PROP-007 | PROP-012 |
| PBF-PROP-008 | PROP-013 |
| PBF-PROP-009 | PROP-015 |
| PBF-PROP-010 | PROP-017 |
| PBF-PROP-011 | PROP-029 |
| PBF-PROP-012 | PROP-042 |
| PBF-PROP-013 | PROP-043 |
| PBF-PROP-014 | PROP-044 |

## New PROPs — no old id (post-v1.21, native stage-categorized ids)

| new | title |
|---|---|
| A-PROP-001 | The Audit Stage (absorbs B-PROP-007) |
| PBAF-PROP-001 | SOP asset bind + applicability model |

Note: `B-PROP-007` (Built-App Audit, `PROP-030`) is **superseded/absorbed by `A-PROP-001`** —
its angles A/B/C become the Audit stage's engine verbatim; `B-PROP-007`/`PROP-030` stays in
the renames table above as historical record, not deleted.
