# BUSINESS-LOGIC VALIDATION — <project>  (ported from v0.13)

> The CEO signs every **money / business rule** with a WORKED EXAMPLE before build — because a rule can be internally consistent, pass every code gate, and still encode the WRONG intent (the absensi payroll "clamp-both" scar, LESSON-MONEY-001). VALIDATION = does the rule match the CEO's intent (this file). VERIFICATION = does the build match the spec (later). Required for money/business waves (G7). Load-on-demand.

**applicable:** yes | NOT_APPLICABLE (why: no money/business rule in this project)

## One block PER rule
### Rule: <name, e.g. "mid-month resignee pay">
- **Plain-English intent (CEO's words):** ____
- **Worked example table** (the CEO checks each row by hand — INCLUDE edge / partial / zero rows):

| # | Real-ish inputs | Expected output | Why |
|---|---|---|---|
| 1 | <normal case> | <number> | |
| 2 | <edge: partial month> | <number> | |
| 3 | <edge: zero / negative / overlap> | <number> | |

- **CEO sign-off:** Accepted by ____ · Date ____ · Status **SIGNED** | DRAFT

*No money/business build card runs until its rule here is SIGNED. The builder's job is to match this table exactly.*
