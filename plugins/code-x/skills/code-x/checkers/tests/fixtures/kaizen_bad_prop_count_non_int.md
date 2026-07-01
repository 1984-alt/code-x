# Test queue — BAD fixture: forward PROP with prop_count as a string (not int)
# → KAIZEN-CONFLICT-SCAN-BASIS-CURRENT P1 shape error (P2-008)

```yaml
- id: PROP-TEST-CS-COUNT-TYPE
  status: APPLIED
  behavioural: no
  conflict_scan:
    basis:
      queue_sha: "0000000000000000000000000000000000000000"
      ledger_sha: "0000000000000000000000000000000000000000"
      crosswalk_sha: "0000000000000000000000000000000000000000"
      prop_count: "44"
      decision_count: 0
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "n/a — no conflicts found"
    scan_step_marker: present
```
