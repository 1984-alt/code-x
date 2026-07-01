# Test queue — good fixture (2 APPLIED PROPs, both pass all clauses)

```yaml
- id: PROP-TEST-001
  status: APPLIED
  behavioural: no
  conflict_scan:
    basis:
      source: backscan-2026-06-30
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "n/a — no conflicts found"
    scan_step_marker: present

- id: PROP-TEST-002
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
