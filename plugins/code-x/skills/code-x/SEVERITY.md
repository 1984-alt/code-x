# Code-X V1 — SEVERITY ladder

> Plain-English: what counts as a blocking problem. Final-ready requires ALL zero.

| Sev | Meaning | Examples | Blocks |
|---|---|---|---|
| **P0** | Danger — destruction, secret/privacy leak, data loss, public exposure, unsafe/illegal action | secret leaked · app writes data into a forbidden destination · destructive restore with no backup | **STOP NOW** |
| **P1** | Core app can't be trusted or used; major product / security / money / UX failure | wrong account balance · unclickable primary button · **visual slop on a core screen** · wrong money rule | Module cannot clear |
| **P2** | Important defect / missing proof that could cause wrong behavior later | missing regression proof · vague import contract · incomplete security tripwire | Module cannot clear **unless** converted into its own tracked fix card |
| **P3** | Minor polish/doc — doesn't affect safety, trust, money, usability, or acceptance | typo · slight wording · minor non-core spacing | May queue during build; **must be zero before final-ready** |

**User-facing apps (special):** unclickable primary control = **P1** · broken mobile layout = **P1** · AI-slop core screen = **P1** · material mismatch from the approved design = **P1/P2** · tiny non-blocking polish = **P3**.

**Verify-app gate (PROP-036) — a live_slice's behavior is machine-verified before the CEO live-drive:** a `live_slice` module accepted with a missing / forged / unbound (non-hex `repo_sha`) `verify_app receipt` = **P0** (the live-drive accept would be offered on behavior that was never machine-exercised — the same danger class as a green screen that no gate ever rendered). An honest `verify_app.passed != true` — the verify-app agent drove the running build and its runtime acceptance-criteria check FAILED — = **P1** (the slice cannot clear and the live-drive is not offered until the behavior passes). The verify-app gate is blocking, never advisory; it never claims the behavior was perfect (the CEO live-drive still judges the experience).

**Final-ready:** `P0=0 · P1=0 · P2=0 · P3=0 · known_issues = NONE`. **Zero means zero** — nothing dirty is left behind. **(V1.10)** plus a bound `final_cross_family_receipt` (the final cross-family review is the ship gate; missing receipt = P0 — "last" can never become "never").
