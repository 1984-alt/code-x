# CEO Decision Ledger — <project>

> Lives INSIDE the frozen packet dir (inside the hash). Append-only. Canon:
> `PACKET-CONTENTS.md` Piece 3. `cx check packet` requires BOTH sections below;
> `cx check deck` requires every `ceo_decision_ref` to resolve to a Decisions row id.
> No MISSING/PARTIAL ask may be frozen over.

## CEO Asks Register

Everything the CEO requested, in the CEO's words — recorded BEFORE it becomes a
requirement (or quietly dies). The completeness audit traces FROM this register.

| id | date | ask_in_ceo_words | status | satisfied_in | superseded_by |
|---|---|---|---|---|---|
| A-001 | YYYY-MM-DD | "..." | DONE | <doc#section> | - |

status: DONE | PARTIAL | MISSING | SUPERSEDED | NOT_APPLICABLE

## Decisions

Chosen decisions, rows `CEO-D-NNN` (legacy/pre-V1: `CEO-D-LEGACY-NNN`, name the source).

| id | date | decision (CEO's words) | scope | supersedes |
|---|---|---|---|---|
| CEO-D-001 | YYYY-MM-DD | "..." | <module/wave/project> | - |
