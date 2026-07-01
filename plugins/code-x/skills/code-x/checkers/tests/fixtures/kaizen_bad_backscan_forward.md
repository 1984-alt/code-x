# Test queue — BAD fixture: forward PROP (B-PROP-099, not in crosswalk) with
# basis.source: backscan-2026-06-30 → KAIZEN-CONFLICT-SCAN-BASIS-CURRENT P1 (P1-002)

```yaml
- id: B-PROP-099
  legacy_id: PROP-099
  stages: [building]
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
