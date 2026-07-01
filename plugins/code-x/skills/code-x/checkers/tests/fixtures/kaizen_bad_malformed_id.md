# Test queue — bad KAIZEN-PROP-ID-PARSEABLE fixture (malformed id → P1)
# id PROP-12 matches neither ^PROP-\d{3}$ nor ^PREFIX-PROP-\d{3}$ but carries
# semantic fields → silently dropped/invisible; clause must bite.

```yaml
- id: PROP-12
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
