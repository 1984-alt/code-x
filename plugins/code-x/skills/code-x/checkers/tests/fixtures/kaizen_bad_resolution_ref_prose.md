# Test queue — BAD fixture: non-empty hits with resolution_ref that is free-form prose
# (no '/', '§', '#', or CEO-D-) → KAIZEN-RESOLUTION-REF-RESOLVABLE P1 (P2-007)

```yaml
- id: PROP-TEST-CS-PROSE-REF
  status: APPLIED
  behavioural: no
  conflict_scan:
    basis:
      source: backscan-2026-06-30
    duplicates: []
    ambiguities: [PBF-PROP-005]
    conflicts: []
    resolution_ref: "resolved by discussion"
    scan_step_marker: present
```
