# Code-X SOP — asset folder

The **Code-X SOP (Full-Stack Software Protocol)** is a standalone, versioned reference asset. Code-X **points to it**; it is not part of the protocol's own version line.

## Contents
- `code-x-sop-v1.0.html` — the SOP itself: 9-principle Constitution + 13 layers, each with a ship gate. Frozen #1–#13 numbering.
- `SOP-MANIFEST.yaml` — current version + the pointer the protocol reads.
- `APPLICABILITY-MODEL.md` — the 9 build-facts → per-sub-item applicability engine (Rule 1 + Rule 2). What decides which of the 13 layers apply to a given build/module.

## How the four stages use it (bound by PBAF-PROP-001)
- **Planning** — requirement source; the packet carries an SOP coverage map (all 13 layers × APPLIES/PARTIAL/N/A + driving fact).
- **Building** — build guidance; each card cites the layers it must satisfy.
- **Audit** — the checklist; the 13 ship gates are angle D of the Audit stage (A-PROP-001).
- **Fixing** — disposition target; audit `fix` findings become preserve-posture fix cards.

## Versioning
The SOP upgrades on its own clock. New version → new file *beside* the old one, bump `SOP-MANIFEST.yaml`. A SOP upgrade does **not** force a protocol version bump — only the manifest pin moves. See the manifest for the upgrade steps.
