# Code-X — MEMORY/CEO-DECISION-LEDGER.md

> This is your protocol-level decision ledger. It ships EMPTY: a fresh install starts
> with no decisions and you grow the list as you make them.

## What it is for

The append-only record of **decisions about the protocol itself** — the calls the
director (CEO) makes when a Kaizen proposal is approved, a rule is changed, or an
ambiguity is resolved. (Each *project* keeps its own decision ledger inside its packet;
this one is only for protocol-level decisions, not per-project product decisions.)

It exists so that *why* the protocol is the way it is never gets lost: every non-obvious
rule should trace back to a dated decision here.

## Entry format (one row per decision)

```
CEO-D-001 | <date> | <one-line decision> | <one-line rationale> | <PROP-### or doc it touched>
```

## Ledger

_(empty — append decisions here as you make them)_
