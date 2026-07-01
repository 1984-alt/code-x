# Test queue — good stage-rename fixture (properly formatted PROP passes all stage-rename clauses)
# Uses PROP-TEST-* ids which are exempt from crosswalk/series checks (not in _NEW_ID_RE scope)
# so this queue passes all 5 PBF-PROP-013 clauses.

```yaml
- id: PROP-TEST-STAGE-GOOD
  status: APPLIED
  behavioural: yes
  enforcement:
    kind: clause
    clause_id: STATE-ORCHESTRATION-MODE-MISSING
  conflict_scan:
    basis:
      source: backscan-2026-06-30
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "design-history/prop-backscan-findings-2026-06-30.md"
    scan_step_marker: present
```
