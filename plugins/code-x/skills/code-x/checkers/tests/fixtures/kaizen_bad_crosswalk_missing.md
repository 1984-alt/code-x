# Test queue — bad KAIZEN-CROSSWALK-COMPLETE fixture (queue PROP not in crosswalk → P1)
# P-PROP-999 is a valid format id but not in PROP-CROSSWALK.md

```yaml
- id: P-PROP-999
  status: APPLIED
  legacy_id: PROP-999
  stages: [planning]
  behavioural: no
  conflict_scan:
    basis:
      source: backscan-2026-06-30
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "design-history/prop-backscan-findings-2026-06-30.md"
    scan_step_marker: present
```
