# tip-split — spec summary (frozen packet)

A tiny worked example for Code-X. The "app" splits a restaurant bill —
including tip — fairly among a group of friends.

Locked by CEO 2026-06-19. Wave: W1.

## Wave W1 — the four requirements

- **REQ-001 — Subtotal.** Sum each person's ordered items into a per-person subtotal.
- **REQ-002 — Tip.** Apply a single shared tip percentage to the bill.
- **REQ-003 — Split.** Divide the total by what each person actually ordered — not evenly (see CEO-D-001).
- **REQ-004 — Rounding & remainder.** Round each person's share to the nearest whole currency unit, and reconcile the leftover so the parts still add up to the whole.

REQ-004 is the easy one to forget — and the one this example deliberately
"drops" to show `cx check deck` catching a requirement that fell out at compile time.
