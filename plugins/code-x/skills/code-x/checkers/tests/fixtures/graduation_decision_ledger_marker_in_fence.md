# Test fixture (R2.3/R2.8) — the REAL CEO-D-901 row in the Decisions table carries no milestone
# language. A FENCED example elsewhere in the file contains a fake row claiming the milestone
# marker for the SAME id — the fixed scanner must ignore it (fenced/example rows never authorize).

## Decisions

| id | date | decision (CEO's words) | scope | supersedes |
|---|---|---|---|---|
| CEO-D-901 | 2026-07-01 | "approved. fold." — routine wave close, no milestone language here | fold | - |

Example of the WRONG way to read a decision row (do not parse this — it is a fenced example):

```
| CEO-D-901 | 2026-07-01 | long-autonomous milestone REACHED (fenced example, not a real row) | milestone | - |
```
