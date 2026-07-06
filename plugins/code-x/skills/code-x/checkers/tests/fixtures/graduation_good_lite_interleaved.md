# Test fixture — PBF-PROP-019 Phase 4 (design v2 §5/P1-5): 4 entries oldest->newest =
# proj-w (STANDARD, clean) / proj-x (LITE, hash-bound tier evidence VERIFIED, but its c2
# criterion is deliberately UNMET — reuses the needs_fix-then-accepted receipt from
# graduation_bad_criterion.md) / proj-y (STANDARD, clean) / proj-z (STANDARD, clean, newest).
# Counting backward from newest: z clean(1) -> y clean(2) -> x is_lite=SKIP (neither counts nor
# resets, same mechanic as 'pending') -> w clean(3). Streak=3 satisfies N=3/M=3 and authorization
# PASSES — proving a verified-LITE entry INTERLEAVED between STANDARD entries is excluded from
# the streak population while the STANDARD entries either side still count. Without the
# exclusion, proj-x's UNMET c2 would reset the streak to 0 and authorization would FAIL.

```yaml
- project_id: proj-w
  ship_commit: 6875306e5e4632433d955d86601457dbd5d6e768
  ship_date: 2026-01-01
  ship_timestamp_utc: "2026-01-01T10:00:00Z"
  entered_by: hand-append
  evidence_manifest: graduation_receipts/clean/graduation-evidence-manifest.yaml
  risk_tier: STANDARD
  tier_evidence: {receipt: graduation_receipts/clean/tier-standard.yaml, receipt_sha256: e750d7cd467245edee8660a769076cc046090068d3a87e79661324af943675a0}
  criteria:
    c1_demo_gate_never_fired: {receipt: graduation_receipts/clean/c1-index.yaml, receipt_sha256: 2015b253a72f442a2921eb1a528673b2219f82487a6745cc3a5829de4cdd856a}
    c2_ceo_first_accept: {receipt: graduation_receipts/clean/c2-history.yaml, receipt_sha256: 7198be08655e7b5d048b66ef394713e881cfbdb9d281bdae75e2f415a899c31b}
    c3_zero_design_drift: {receipt: graduation_receipts/clean/c3-fidelity.yaml, receipt_sha256: c54b72753049ba9de65e0ffd7dd9c95fef9cd3bab4b6a16ce8a4b17a19441dbc}
    c4_matched_blueprint: {receipt: graduation_receipts/clean/c4-blueprint.yaml, receipt_sha256: 8a6ef04e9d038a169642d35596847fcbf394c5c2f90981de0df08a3acb8ff358}
    c5_zero_postship_p0p1: {receipt: graduation_receipts/clean/c5-incidents.yaml, receipt_sha256: 7694895533f95511f60a185cfd7c4be0a03432016cc0beacf2778ada97fb7ddb}
    c6_final_ready_clean_first_pass: {receipt: state_good_final_ready_attempt1.yaml, receipt_sha256: 4223fdf5f2c02f7d104b8fd545dbda98744b860c29558e87f810802c480c1644}
    c7_full_review_pipeline: {receipt: graduation_receipts/clean/c7-review-index.yaml, receipt_sha256: a93658d2dcb2e0c1c3ee40d5c674dcb9f10a06de8c0567f7c2dfaa17e2786c02}
- project_id: proj-x
  ship_commit: 9a9a9a9a9a9a9a9a9a9a9a9a9a9a9a9a9a9a9a9a
  ship_date: 2026-02-01
  ship_timestamp_utc: "2026-02-01T10:00:00Z"
  entered_by: hand-append
  evidence_manifest: graduation_receipts/bad/manifest-crit2.yaml
  risk_tier: LITE
  tier_evidence: {receipt: graduation_receipts/clean/tier-lite.yaml, receipt_sha256: ed2a223e150d5e08ab633892cbef60b5fc11a105db4f7cb12d97c13ca85a2ac0}
  criteria:
    c1_demo_gate_never_fired: {receipt: graduation_receipts/clean/c1-index.yaml, receipt_sha256: 2015b253a72f442a2921eb1a528673b2219f82487a6745cc3a5829de4cdd856a}
    c2_ceo_first_accept: {receipt: graduation_receipts/bad/c2-history-needsfix.yaml, receipt_sha256: f45110418e57dfa0b8fda03afb46bd513e33c48507a89d5ef84a9264f63f7620}
    c3_zero_design_drift: {receipt: graduation_receipts/clean/c3-fidelity.yaml, receipt_sha256: c54b72753049ba9de65e0ffd7dd9c95fef9cd3bab4b6a16ce8a4b17a19441dbc}
    c4_matched_blueprint: {receipt: graduation_receipts/clean/c4-blueprint.yaml, receipt_sha256: 8a6ef04e9d038a169642d35596847fcbf394c5c2f90981de0df08a3acb8ff358}
    c5_zero_postship_p0p1: {receipt: graduation_receipts/clean/c5-incidents.yaml, receipt_sha256: 7694895533f95511f60a185cfd7c4be0a03432016cc0beacf2778ada97fb7ddb}
    c6_final_ready_clean_first_pass: {receipt: state_good_final_ready_attempt1.yaml, receipt_sha256: 4223fdf5f2c02f7d104b8fd545dbda98744b860c29558e87f810802c480c1644}
    c7_full_review_pipeline: {receipt: graduation_receipts/clean/c7-review-index.yaml, receipt_sha256: a93658d2dcb2e0c1c3ee40d5c674dcb9f10a06de8c0567f7c2dfaa17e2786c02}
- project_id: proj-y
  ship_commit: 123f52f7a728c0d611be39782218e4b953566d5a
  ship_date: 2026-03-01
  ship_timestamp_utc: "2026-03-01T10:00:00Z"
  entered_by: hand-append
  evidence_manifest: graduation_receipts/clean/graduation-evidence-manifest.yaml
  risk_tier: STANDARD
  tier_evidence: {receipt: graduation_receipts/clean/tier-standard.yaml, receipt_sha256: e750d7cd467245edee8660a769076cc046090068d3a87e79661324af943675a0}
  criteria:
    c1_demo_gate_never_fired: {receipt: graduation_receipts/clean/c1-index.yaml, receipt_sha256: 2015b253a72f442a2921eb1a528673b2219f82487a6745cc3a5829de4cdd856a}
    c2_ceo_first_accept: {receipt: graduation_receipts/clean/c2-history.yaml, receipt_sha256: 7198be08655e7b5d048b66ef394713e881cfbdb9d281bdae75e2f415a899c31b}
    c3_zero_design_drift: {receipt: graduation_receipts/clean/c3-fidelity.yaml, receipt_sha256: c54b72753049ba9de65e0ffd7dd9c95fef9cd3bab4b6a16ce8a4b17a19441dbc}
    c4_matched_blueprint: {receipt: graduation_receipts/clean/c4-blueprint.yaml, receipt_sha256: 8a6ef04e9d038a169642d35596847fcbf394c5c2f90981de0df08a3acb8ff358}
    c5_zero_postship_p0p1: {receipt: graduation_receipts/clean/c5-incidents.yaml, receipt_sha256: 7694895533f95511f60a185cfd7c4be0a03432016cc0beacf2778ada97fb7ddb}
    c6_final_ready_clean_first_pass: {receipt: state_good_final_ready_attempt1.yaml, receipt_sha256: 4223fdf5f2c02f7d104b8fd545dbda98744b860c29558e87f810802c480c1644}
    c7_full_review_pipeline: {receipt: graduation_receipts/clean/c7-review-index.yaml, receipt_sha256: a93658d2dcb2e0c1c3ee40d5c674dcb9f10a06de8c0567f7c2dfaa17e2786c02}
- project_id: proj-z
  ship_commit: 7e8015386e894745107ad5c803c4d088f64b1c73
  ship_date: 2026-04-01
  ship_timestamp_utc: "2026-04-01T10:00:00Z"
  entered_by: hand-append
  evidence_manifest: graduation_receipts/clean/graduation-evidence-manifest.yaml
  risk_tier: STANDARD
  tier_evidence: {receipt: graduation_receipts/clean/tier-standard.yaml, receipt_sha256: e750d7cd467245edee8660a769076cc046090068d3a87e79661324af943675a0}
  criteria:
    c1_demo_gate_never_fired: {receipt: graduation_receipts/clean/c1-index.yaml, receipt_sha256: 2015b253a72f442a2921eb1a528673b2219f82487a6745cc3a5829de4cdd856a}
    c2_ceo_first_accept: {receipt: graduation_receipts/clean/c2-history.yaml, receipt_sha256: 7198be08655e7b5d048b66ef394713e881cfbdb9d281bdae75e2f415a899c31b}
    c3_zero_design_drift: {receipt: graduation_receipts/clean/c3-fidelity.yaml, receipt_sha256: c54b72753049ba9de65e0ffd7dd9c95fef9cd3bab4b6a16ce8a4b17a19441dbc}
    c4_matched_blueprint: {receipt: graduation_receipts/clean/c4-blueprint.yaml, receipt_sha256: 8a6ef04e9d038a169642d35596847fcbf394c5c2f90981de0df08a3acb8ff358}
    c5_zero_postship_p0p1: {receipt: graduation_receipts/clean/c5-incidents.yaml, receipt_sha256: 7694895533f95511f60a185cfd7c4be0a03432016cc0beacf2778ada97fb7ddb}
    c6_final_ready_clean_first_pass: {receipt: state_good_final_ready_attempt1.yaml, receipt_sha256: 4223fdf5f2c02f7d104b8fd545dbda98744b860c29558e87f810802c480c1644}
    c7_full_review_pipeline: {receipt: graduation_receipts/clean/c7-review-index.yaml, receipt_sha256: a93658d2dcb2e0c1c3ee40d5c674dcb9f10a06de8c0567f7c2dfaa17e2786c02}
```
