# Test queue — bad KAIZEN-LEGACY-ID-PRESENT-UNIQUE fixture (duplicate legacy_id → P1)

```yaml
- id: PBF-PROP-001
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

```yaml
- id: PBF-PROP-002
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
