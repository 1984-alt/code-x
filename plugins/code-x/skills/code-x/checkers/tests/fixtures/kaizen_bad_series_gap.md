# Test queue — bad KAIZEN-STAGE-SERIES-ORDER-GAPLESS fixture (gap in series → P1)
# B-PROP-001 and B-PROP-003 without B-PROP-002 → gap

```yaml
- id: B-PROP-001
  status: APPLIED
  legacy_id: PROP-003
  stages: [building]
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

```yaml
- id: B-PROP-003
  status: APPLIED
  legacy_id: PROP-019
  stages: [building]
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
