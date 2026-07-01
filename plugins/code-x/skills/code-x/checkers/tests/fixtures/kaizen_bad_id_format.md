# Test queue — bad KAIZEN-ID-FORMAT fixture (active PROP with old-format id → P0)

```yaml
- id: PROP-001
  status: APPLIED
  legacy_id: PROP-001
  stages: [planning, building, fixing]
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
