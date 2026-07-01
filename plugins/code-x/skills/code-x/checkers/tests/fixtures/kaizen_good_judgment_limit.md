# Test queue — good judgment_limit fixture (complete enforcement block → PASS)

```yaml
- id: PROP-TEST-TONE
  status: APPLIED
  behavioural: yes
  enforcement:
    kind: judgment_limit
    justification: Tone is an AI-output quality that has no machine test; a mechanical gate would over-claim (cardinal sin).
    review_lens: anti-slop
    ceo_decision_ref: CEO-D-029
  conflict_scan:
    basis:
      source: backscan-2026-06-30
    duplicates: []
    ambiguities: []
    conflicts: []
    resolution_ref: "n/a — no conflicts found"
    scan_step_marker: present
```
