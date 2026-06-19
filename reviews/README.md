# Cross-review trail (summaries)

Code-X's claim that protocol changes are "cross-reviewed by both AI families,"
made inspectable.

**How the discipline works.** When one family (say, Claude) builds or changes
the protocol, the *opposite* family (GPT/Codex) reviews it — a different
vendor, not the builder grading itself. Findings are folded back in, and where
a finding describes a new failure mode, it becomes a mechanical check so it
can't recur (Kaizen). Verdicts you'll see below: **SHIP-CLEAN / Approved**
(no blocking issues), **FIX-FIRST** (fix the findings before proceeding),
**NOT READY** (real problems found — exactly what a review is for).

**Why summaries, not raw write-ups.** The raw review artefacts reference
private project detail from the author's own apps. So this trail publishes
only the inspectable facts — date, what was reviewed, which family, the
verdict, and what got folded — not the full text. (Internal proposal IDs and
commit hashes are omitted for the same reason.)

| Date | What was reviewed | Family | Verdict | What was folded |
|---|---|---|---|---|
| 2026-06-19 | PROOF-mode checker fix (a mode the checker recognised in one place but rejected in another) | OpenAI (cross-family) | SHIP-CLEAN | one template-hint nit (P3) |
| 2026-06-19 | Plain-language pass across the protocol docs | Anthropic | Approved | a real gap — the plain-talk requirement was missing from one core doc — closed |
| 2026-06-19 | The new Built-App Audit gate ("built + green ≠ wired and running") | Anthropic | Approved | 3 named risks verified clean firsthand; 3 minor cosmetic notes left for final review |
| 2026-06-19 | Version-record change + the audit gate's enforcement | OpenAI (cross-family, high-effort) | FIX-FIRST — 3 P1, 4 P2, 2 P3, no P0 | all folded in one sweep; the big one: a gate that checked a field *existed* but not that the audit report itself really existed (ceremony → enforcement) |
| 2026-06-18 | Whole-tree readiness for public release | Anthropic (read-only) | NOT READY | 4 issues confirmed firsthand and fixed before anything shipped |

These are a representative sample, not the complete history. The point isn't
the count — it's that the reviews *bit*: they caught real gaps (a missing
requirement in a core doc, a ceremonial gate that didn't actually enforce, a
not-ready release), and the fixes went back through the checker.
