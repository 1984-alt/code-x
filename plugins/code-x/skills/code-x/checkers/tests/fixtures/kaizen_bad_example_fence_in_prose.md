# Test queue — G1 fixture: PROP whose prose body contains a non-PROP yaml example
# The example fence must be IGNORED (not counted as a malformed PROP) → PASS

```yaml
- id: PROP-TEST-CS-G1
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

Here is an example of what a config block looks like (NOT a PROP):

```yaml
name: example-config
kind: configuration
value: 42
```

Another non-PROP fence:

```yaml
host: localhost
port: 5432
```
