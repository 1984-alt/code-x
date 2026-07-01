# Test queue — bad fixture: enforcement clause_id not in check-contracts.yaml

```yaml
- id: PROP-TEST-FAKE-CLAUSE
  status: APPLIED
  behavioural: yes
  enforcement:
    kind: clause
    clause_id: KAIZEN-NO-SUCH-CLAUSE-XYZ
```
