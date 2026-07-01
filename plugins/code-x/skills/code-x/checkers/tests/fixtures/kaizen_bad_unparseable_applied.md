# Test queue — bad fixture: malformed yaml fence (unparseable yaml block)

```yaml
- id: PROP-TEST-MALFORMED
  status: APPLIED
  behavioural: yes
    enforcement: [invalid: yaml: structure: here
      bad indentation and brackets
```
