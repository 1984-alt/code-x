# Test queue — bad fixture: prompt_marker kind with unsafe prompt_ref path

```yaml
- id: PROP-TEST-UNSAFE-PROMPTREF
  status: APPLIED
  behavioural: yes
  enforcement:
    kind: prompt_marker
    prompt_ref: /etc/passwd
```
