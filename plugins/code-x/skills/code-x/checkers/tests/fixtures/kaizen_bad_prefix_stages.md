# Test queue — bad KAIZEN-PREFIX-MATCHES-STAGES fixture (stages mismatch prefix → P0)
# PBF-PROP-001 prefix=PBF but stages=[planning] encodes to P — mismatch

```yaml
- id: PBF-PROP-001
  status: APPLIED
  legacy_id: PROP-001
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
