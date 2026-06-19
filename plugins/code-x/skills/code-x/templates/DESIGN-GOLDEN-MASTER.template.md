# DESIGN GOLDEN MASTER — <project>  (folder spec)

> The **approved looks-first screens** the whole build must match. This is a FOLDER, not one file. It is the reference the Mode A golden-screenshot gate (G6) checks against. Required for user-facing apps (G7). Load-on-demand.

**applicable:** yes | NOT_APPLICABLE (why: ___)

## What lives in this folder
```
design-golden-master/
  style-select/       # PROP-016 FIRST step: the style variants of ONE representative screen + index.md (matrix below)
  screens/            # the approved screen for each core surface (HTML mock OR locked screenshot)
  index.md            # the list below — one row per screen
  click-path.md       # the Click-Path Contract (below)
  viewport.md         # the fixed device + size every screenshot is taken at (e.g. iPhone 13 Pro, 390×844)
```

## style-select/index.md — the variant matrix (PROP-016)
Default **3 variants** (4–5 only with a stated reason). Same representative screen, same `DESIGN_FIXTURE` rows, different visual language. **Every PAIR of variants must differ on ≥2 of the 4 axes.**
```yaml
style_variants:
  - id: STYLE_A
    path:                  # style-select/<file>
    density:               # compact | balanced | airy
    typography:            # system | editorial | numeric-ledger | soft-rounded
    color_mood:            # calm | high-contrast | warm | monochrome | playful
    layout_character:      # list-first | card-first | dashboard-first | ledger-first
    distinguishing_notes:
chosen:                    # must match PRODUCT-TASTE-LOCK locked_style_direction.chosen_variant_id
```

## index.md — one row per screen
| Screen id | File | Approved? | CEO note |
|---|---|---|---|
| HOME | screens/home.html | ✅ / ⏳ | |

## click-path.md — the Click-Path Contract (per screen)
| Screen | Primary controls (each must be clickable once) | 30-sec demo path | Empty/error state shown? |
|---|---|---|---|
| HOME | <button A, button B, tab C> | <route → action → result> | yes/no |

## Rules
- **Style-Select comes FIRST** (PROP-016): no other golden-master screen is produced before the CEO picks a style variant; every screen after it follows the locked style direction — a screen in a different style = **P1**. [RULE:locked-style-direction]
- Every core screen here is **CEO-accepted** before the build factory opens (G7).
- `DESIGN_FIXTURE` sample data is allowed in these mocks for layout proof only — never real/money data.
- A built screen that drifts from its golden master = **P1** (see SEVERITY).
- Changing a golden screen after lock = a CEO decision card.
