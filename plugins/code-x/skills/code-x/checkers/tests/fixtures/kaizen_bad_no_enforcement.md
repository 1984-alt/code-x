# Test queue — bad fixture: behavioural=yes, APPLIED, NO enforcement block
# (F-PROP-002: carries a complete conflict_scan so the ONLY finding is the
# no-enforcement one — a single-cause fixture, not a multi-finding smear)

```yaml
- id: PROP-TEST-NO-ENFORCEMENT
  status: APPLIED
  behavioural: yes
  conflict_scan:
    basis:
      source: backscan-2026-06-30
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "n/a — no conflicts found"
    scan_step_marker: present
```
