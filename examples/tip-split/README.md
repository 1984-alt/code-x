# Worked example: tip-split

A tiny, runnable example that shows Code-X's deterministic checker catching a
real mistake — in under a minute, no setup beyond Python 3 + PyYAML.

## The "app"

A bill-splitter for a group of friends at a restaurant: add up what each
person ordered, apply a shared tip, split by order, and round each share
fairly. Four requirements, all in the frozen packet:

- **REQ-001** — subtotal per person
- **REQ-002** — apply the tip
- **REQ-003** — split by what each person ordered
- **REQ-004** — round each share and reconcile the leftover

## Run it

```bash
bash run.sh
```

## What you'll see

**Step 1 — the full deck passes.** Every requirement is covered by a card, so
`cx check deck` returns:

```
PASS
  coverage: 4 building/covered, 0 not_building, 0 not_applicable, 0 ceo_deferred
```

**Step 2 — drop a requirement, and `cx` catches it.** The script removes
REQ-004's card (the rounding one — the easy one to forget) and re-checks.
`cx` refuses to pass:

```
FIX-FIRST
  [P0] .../requirements-manifest.yaml — requirement 'REQ-004' disposition=BUILDING but appears in NO card's requirement_ids — dropped at compile
```

That `[P0]` is the whole point. A requirement was agreed and frozen, then
silently fell out when the plan was compiled into work-orders — the exact
drift a non-coder can't see by reading the code. The checker sees it
mechanically, every time. (See the repo's *"What `cx` can and can't verify"*
section for what this does and doesn't prove.)

## What's in here

- `packet/` — the frozen plan: `requirements-manifest.yaml` (the four
  requirements), `spec-summary.md`, and a `CEO-DECISION-LEDGER.md`.
- `cards/` — one work-order card per requirement. Each card is bound to the
  packet by a content hash (`locked_packet_hash`), so editing the packet after
  the deck is cut is itself caught.
- `receipts/` — the captured output of both runs above, so you can see the
  result without running anything.
- `run.sh` — reproduces both steps.
