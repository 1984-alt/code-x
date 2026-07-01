# Test queue — GOOD fixture: historical PROP (PBF-PROP-001, IS in crosswalk) with
# basis.source: backscan-2026-06-30 → passes KAIZEN-CONFLICT-SCAN-BASIS-CURRENT (P1-002)

```yaml
- id: PBF-PROP-001
  legacy_id: PROP-001
  stages: [planning, building, fixing]
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
```
