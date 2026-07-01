# Test queue — good conflict_scan fixture (commit-anchored live basis, PBF-PROP-014-CSFIX).
# Real staged-format id (sub-part shape, not a PROP-TEST-* demo id) with source omitted
# (live branch). scan_commit is the test sentinel (deadbeef*5) → under CODE_X_TEST_MODE=1
# git resolution is skipped and SHAPE validation alone must PASS. In production the sentinel
# would fail closed (unresolvable), so this pass is test-only, not a forgeable production path.

```yaml
- id: P-PROP-045-A
  status: QUEUED
  behavioural: no
  conflict_scan:
    basis:
      scan_commit: "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
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
