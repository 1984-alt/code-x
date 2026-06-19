# Code-X — MEMORY/PROTOCOL-IMPROVEMENT-QUEUE.md

> This is your protocol-improvement queue. It ships EMPTY: a fresh install starts
> with no queued proposals and you grow the list from your own Kaizen reviews.

## What it is for

The running list of **proposed protocol changes** (referred to as `PROP-###` throughout
the docs) — improvements to the protocol *itself* that have been surfaced but not yet
folded in. A proposal sits here until it has been through cross-family review and
explicit CEO approval (see `KAIZEN.md`); on approval it becomes an active rule and the
protocol version bumps (recorded in `VERSION-HISTORY.md`). Nothing here auto-applies.

## Entry format (one block per proposal)

```
PROP-001  <short title>
  status:   QUEUED | IN-REVIEW | APPLIED | DEFERRED | REJECTED
  problem:  what failure or waste prompted it (one line)
  change:   the proposed protocol change (one line)
  review:   cross-family review verdict + date, once it has one
  decision: CEO ruling + date, once decided
```

## Queue

_(empty — add proposals here as your Kaizen reviews surface them)_
