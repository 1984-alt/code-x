# Test queue — bad fixture: forward PROP with a malformed scan_commit (not 40-hex).
# SHAPE validation must reject it before any git call is attempted.

```yaml
- id: P-PROP-046-A
  status: QUEUED
  behavioural: no
  conflict_scan:
    basis:
      scan_commit: "deadbeefcafe"
      queue_sha: "cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd"
      ledger_sha: "efefefefefefefefefefefefefefefefefefefef"
      crosswalk_sha: "1212121212121212121212121212121212121212"
      prop_count: 42
      decision_count: 12
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "n/a — no conflicts found"
    scan_step_marker: present
```
