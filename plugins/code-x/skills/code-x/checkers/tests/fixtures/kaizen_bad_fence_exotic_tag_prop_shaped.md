# Test queue — bad fixture: an exotic fence tag (uppercase YAML, not lowercase yaml) is never
# recognized as a yaml PROP fence by even the trailing-space-tolerant regex — but its raw text
# is unmistakably PROP-shaped (id: PROP-999). Must be a LOUD finding
# (KAIZEN-FENCE-PROP-SHAPED-UNPARSEABLE), never a silent vanish (PBF-PROP-021 group-2 hole #6,
# backstop leg).

```YAML
id: PROP-999
status: APPLIED
behavioural: yes
```
