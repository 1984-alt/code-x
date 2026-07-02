# Test fixture — proj-gamma shipped 2026-01-01 (window CLOSED by 'today'), but its post-ship
# incident ledger records one P1 dated 2026-01-05, inside the 14-day window. UNMET, not
# INDETERMINATE (closed window with a real hit). GRADUATION-ENTRY-CRITERION-UNMET P1.

```yaml
- project_id: proj-alpha
  ship_commit: 6875306e5e4632433d955d86601457dbd5d6e768
  ship_date: 2026-01-01
  ship_timestamp_utc: "2026-01-01T10:00:00Z"
  entered_by: hand-append
  evidence_manifest: graduation_receipts/clean/graduation-evidence-manifest.yaml
  criteria:
    c1_demo_gate_never_fired: {receipt: graduation_receipts/clean/c1-index.yaml, receipt_sha256: 2015b253a72f442a2921eb1a528673b2219f82487a6745cc3a5829de4cdd856a}
    c2_ceo_first_accept: {receipt: graduation_receipts/clean/c2-history.yaml, receipt_sha256: 7198be08655e7b5d048b66ef394713e881cfbdb9d281bdae75e2f415a899c31b}
    c3_zero_design_drift: {receipt: graduation_receipts/clean/c3-fidelity.yaml, receipt_sha256: c54b72753049ba9de65e0ffd7dd9c95fef9cd3bab4b6a16ce8a4b17a19441dbc}
    c4_matched_blueprint: {receipt: graduation_receipts/clean/c4-blueprint.yaml, receipt_sha256: 8a6ef04e9d038a169642d35596847fcbf394c5c2f90981de0df08a3acb8ff358}
    c5_zero_postship_p0p1: {receipt: graduation_receipts/clean/c5-incidents.yaml, receipt_sha256: 7694895533f95511f60a185cfd7c4be0a03432016cc0beacf2778ada97fb7ddb}
    c6_final_ready_clean_first_pass: {receipt: state_good_final_ready_attempt1.yaml, receipt_sha256: 4223fdf5f2c02f7d104b8fd545dbda98744b860c29558e87f810802c480c1644}
    c7_full_review_pipeline: {receipt: graduation_receipts/clean/c7-review-index.yaml, receipt_sha256: a93658d2dcb2e0c1c3ee40d5c674dcb9f10a06de8c0567f7c2dfaa17e2786c02}
- project_id: proj-beta
  ship_commit: 123f52f7a728c0d611be39782218e4b953566d5a
  ship_date: 2026-02-01
  ship_timestamp_utc: "2026-02-01T10:00:00Z"
  entered_by: hand-append
  evidence_manifest: graduation_receipts/clean/graduation-evidence-manifest.yaml
  criteria:
    c1_demo_gate_never_fired: {receipt: graduation_receipts/clean/c1-index.yaml, receipt_sha256: 2015b253a72f442a2921eb1a528673b2219f82487a6745cc3a5829de4cdd856a}
    c2_ceo_first_accept: {receipt: graduation_receipts/clean/c2-history.yaml, receipt_sha256: 7198be08655e7b5d048b66ef394713e881cfbdb9d281bdae75e2f415a899c31b}
    c3_zero_design_drift: {receipt: graduation_receipts/clean/c3-fidelity.yaml, receipt_sha256: c54b72753049ba9de65e0ffd7dd9c95fef9cd3bab4b6a16ce8a4b17a19441dbc}
    c4_matched_blueprint: {receipt: graduation_receipts/clean/c4-blueprint.yaml, receipt_sha256: 8a6ef04e9d038a169642d35596847fcbf394c5c2f90981de0df08a3acb8ff358}
    c5_zero_postship_p0p1: {receipt: graduation_receipts/clean/c5-incidents.yaml, receipt_sha256: 7694895533f95511f60a185cfd7c4be0a03432016cc0beacf2778ada97fb7ddb}
    c6_final_ready_clean_first_pass: {receipt: state_good_final_ready_attempt1.yaml, receipt_sha256: 4223fdf5f2c02f7d104b8fd545dbda98744b860c29558e87f810802c480c1644}
    c7_full_review_pipeline: {receipt: graduation_receipts/clean/c7-review-index.yaml, receipt_sha256: a93658d2dcb2e0c1c3ee40d5c674dcb9f10a06de8c0567f7c2dfaa17e2786c02}
- project_id: proj-gamma
  ship_commit: 7e8015386e894745107ad5c803c4d088f64b1c73
  ship_date: 2026-01-01
  ship_timestamp_utc: "2026-01-01T10:05:00Z"
  entered_by: hand-append
  evidence_manifest: graduation_receipts/bad/manifest-crit5.yaml
  criteria:
    c1_demo_gate_never_fired: {receipt: graduation_receipts/clean/c1-index.yaml, receipt_sha256: 2015b253a72f442a2921eb1a528673b2219f82487a6745cc3a5829de4cdd856a}
    c2_ceo_first_accept: {receipt: graduation_receipts/clean/c2-history.yaml, receipt_sha256: 7198be08655e7b5d048b66ef394713e881cfbdb9d281bdae75e2f415a899c31b}
    c3_zero_design_drift: {receipt: graduation_receipts/clean/c3-fidelity.yaml, receipt_sha256: c54b72753049ba9de65e0ffd7dd9c95fef9cd3bab4b6a16ce8a4b17a19441dbc}
    c4_matched_blueprint: {receipt: graduation_receipts/clean/c4-blueprint.yaml, receipt_sha256: 8a6ef04e9d038a169642d35596847fcbf394c5c2f90981de0df08a3acb8ff358}
    c5_zero_postship_p0p1: {receipt: graduation_receipts/bad/c5-incidents-p1hit.yaml, receipt_sha256: 29b24c6b7427df091fcee3c66a11b2eede4b927e96f0b1ee49bd22a59fc0f1c0}
    c6_final_ready_clean_first_pass: {receipt: state_good_final_ready_attempt1.yaml, receipt_sha256: 4223fdf5f2c02f7d104b8fd545dbda98744b860c29558e87f810802c480c1644}
    c7_full_review_pipeline: {receipt: graduation_receipts/clean/c7-review-index.yaml, receipt_sha256: a93658d2dcb2e0c1c3ee40d5c674dcb9f10a06de8c0567f7c2dfaa17e2786c02}
```
