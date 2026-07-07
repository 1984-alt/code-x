# Test queue — bad fixture: status case drift ("applied" not "APPLIED") on a genuinely-applied
# behavioural PROP with ZERO enforcement — a bare `status != "APPLIED"` string compare silently
# read this as "not applied" and skipped the whole APPLIED-only ladder, greening the closure
# safeguard (PBF-PROP-021 group-2 hole #7).

```yaml
- id: PROP-TEST-STATUS-DRIFT
  status: applied
  behavioural: yes
```
