# Test queue — bad fixture: yaml fence with a TRAILING SPACE after the language tag
# (```yaml<space>\n) previously never matched the exact ```yaml\n literal — the whole
# behavioural APPLIED PROP block (with zero enforcement) vanished from every KAIZEN-*
# clause, including KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT (PBF-PROP-021 group-2
# hole #6).

```yaml 
id: PROP-TEST-FENCE-SPACE
status: APPLIED
behavioural: yes
```
