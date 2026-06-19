# PRODUCT TASTE LOCK — <project>

> The CEO signs off **how the app should look and feel** BEFORE any build. This is the "taste" half of the visual gate (the CEO verifies taste; the AI verifies the mechanical proof). Required for user-facing apps (G7). Load-on-demand — not in the every-turn read path.

**applicable:** yes | NOT_APPLICABLE (why: ___)   ← set NOT_APPLICABLE for non-user-facing tools

## 1. What this app should FEEL like
- One sentence (e.g. "calm, trustworthy, fast — like a clean banking app, not a busy dashboard").

## 2. Reference vibes (apps/screens the CEO likes)
- <app/screenshot/link> — what specifically to borrow (spacing, color calm, typography…).

## 3. Must-have screens (the core surfaces)
- <screen> — its job in one line.

## 4. Taste do / don't (the leash for the builder)
| DO | DON'T |
|---|---|
| <e.g. generous whitespace> | <e.g. no gradient-soup, no emoji headings> |

## 5. Non-negotiables (break = P1)
- <e.g. amounts always right-aligned; expense in red; never truncate a balance>

## 6. Locked style direction (PROP-016 — REQUIRED for user-facing apps; G7 blocks without it)
> Filled at Style-Select: ONE representative core screen in 3 variants (4–5 with stated reason), variant matrix in `design-golden-master/style-select/index.md`. Every screen after this follows the chosen style; different style = P1 drift.
```yaml
locked_style_direction:
  applicable:            # yes | NOT_APPLICABLE (why: ___)
  chosen_variant_id:     # e.g. STYLE_B
  chosen_variant_path:   # design-golden-master/style-select/<file>
  ceo_notes:             # what to keep / avoid (may borrow details from unchosen variants)
  accepted_by:           # CEO
  accepted_at:           # date
```

## CEO sign-off
- Accepted by: ____  · Date: ____  · Status: **LOCKED** | DRAFT
- Notes: ____

*A change to taste AFTER lock is a CEO decision card, not a builder edit.*
