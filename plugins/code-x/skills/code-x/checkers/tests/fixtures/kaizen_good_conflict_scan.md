# Test queue — good conflict_scan fixture (PROP with complete conflict_scan → PASS)

```yaml
- id: PROP-TEST-CS-GOOD
  status: APPLIED
  behavioural: yes
  enforcement:
    kind: clause
    clause_id: STATE-ORCHESTRATION-MODE-MISSING
  conflict_scan:
    basis:
      source: backscan-2026-06-30
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "n/a — no conflicts found"
    scan_step_marker: present
```
