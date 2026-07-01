# Test queue — bad fixture: forward PROP with stale basis shas (KAIZEN-CONFLICT-SCAN-BASIS-CURRENT)

```yaml
- id: PROP-TEST-CS-STALE
  status: APPLIED
  behavioural: no
  conflict_scan:
    basis:
      queue_sha: "0000000000000000000000000000000000000000"
      ledger_sha: "0000000000000000000000000000000000000000"
      crosswalk_sha: "0000000000000000000000000000000000000000"
      prop_count: 0
      decision_count: 0
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "n/a — no conflicts found"
    scan_step_marker: present
```
