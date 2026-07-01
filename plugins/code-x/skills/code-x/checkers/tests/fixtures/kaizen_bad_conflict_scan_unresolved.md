# Test queue — bad fixture: conflict_scan lists hits but resolution_ref is blank (KAIZEN-CONFLICT-SCAN-RESOLVED)

```yaml
- id: PROP-TEST-CS-UNRESOLVED
  status: APPLIED
  behavioural: no
  conflict_scan:
    basis:
      source: backscan-2026-06-30
    duplicates: [PROP-023]
    ambiguities: []
    conflicts: []
    resolution_ref: ""
    scan_step_marker: present
```
