# SOP Applicability Model — v0.2 (rulings LOCKED 2026-07-01)

> Derived verbatim from the locked draft `code-x-sop-applicability-model-2026-07-01.html`
> (v0.2, resolves Decision §8-6). Bound into Code-X v1.22 by PBAF-PROP-001. Feeds two
> mechanisms: (a) Planning's SOP coverage map — app-level facts → layers the plan must
> address; (b) the Audit stage's per-module + final scope — module-level facts → layers
> that module is audited against. Facts are auditor-verifiable → N/A cannot be gamed.

The SOP applies to **every** build. What's N/A is **derived** — per sub-item, never
whole-layer by reflex.

## Rule 1 — zero-ambiguity (derived, not argued)

A part of the SOP is N/A **only** when a named build-fact is false. The plan records the
9 facts; applicability is a lookup, not a debate. The **Audit stage independently
re-derives** the same facts — so nothing can be dodged by mislabeling. Lying about a fact
is a checkable defect, not a valid N/A.

## Rule 2 — per sub-item, not per layer (CEO ruling)

Applicability is decided **sub-item by sub-item**. A whole layer is N/A **only when every
one of its sub-items is N/A**. If even one sub-item lives — e.g. a live-production money app still needs
static-asset caching out of layer 10 — the layer is **PARTIAL** and that surviving
sub-item is **mandatory**. Never drop a whole layer just because most of it doesn't apply.

## 1. The 9 build-facts (the axes)

Every one is a yes/no (A5 is a tier) and **observable** — the auditor confirms each by
looking at the built app.

| Fact | Question — answer from the build itself |
|---|---|
| A1 · UI | Does it render a user-facing interface (screens, HTML/CSS, a PWA)? |
| A2 · Request surface | Does it expose callable endpoints / receive requests (HTTP API, server actions, webhooks)? |
| A3 · Persistence | Does it store durable data (a database, file store, or long-lived state)? |
| A4 · Multi-identity | More than one user or role — any access boundary *between* people? |
| A5 · Exposure | **Tier:** E0 one-shot local script · E1 local service (localhost only) · E2 private network / your own devices (LAN, your phone) · E3 public internet. |
| A6 · Sensitive data | Private / financial / personal data, or any secret/credential? |
| A7 · Async compute | Any background / scheduled / retryable work (cron, queue, launchd, serverless)? |
| A8 · Metered calls | Any paid / metered / rate-limited external API where volume = cost or throttle? |
| A9 · Scale-out | Does it (or will it) run more than one instance / need to scale for concurrent load? |

## 2. The 13 layers, derived from the facts

Legend: **APPLIES** every sub-item in play · **PARTIAL** some sub-items live & mandatory,
some N/A · **N/A** whole layer off — every sub-item N/A.

| # | Layer | Applies when… | Sub-items that fold to N/A when… |
|--|--|--|--|
| 1 | Frontend | `A1` true | headless (no UI) → whole layer off |
| 2 | Backend / API | any server-side logic (nearly always) | pure static site w/ no logic → off · HTTP sub-items (status codes, CORS) off when `A2` false · cross-user access sub-item off when `A4` false |
| 3 | Database & Storage | `A3` true | stateless → off · per-user scoping / second-lock sub-items off when `A4` false |
| 4 | Auth & Permissions | `A4`, or `A5≥E2` with a login | roles/scope/RLS sub-items off when `A4` false · whole layer off only at E0/E1 single-user non-sensitive |
| 5 | Hosting & Deploy | `A5≥E1` (deployed / long-running) | E0 one-shot → off · DNS / CDN / staging off below E3 · **HTTPS/padlock now MANDATORY at E2+** |
| 6 | Cloud & Compute | `A7` or `A8` | synchronous local only → off · cost/pooler sub-items off when `A8`+`A9` false · async retry-safety stays whenever `A7` |
| 7 | CI/CD & Version Ctrl | **version control = ALWAYS** | CI-pipeline sub-items optional for solo manual deploy (ruling: optional) |
| 8 | Security & RLS | `A6`, or `A2`, or `A5≥E2` | RLS/multi-tenant off when `A4` false · CORS/public-CSP off below E3 · **HTTPS mandatory at E2+** · secrets-hygiene + input-safety + dependency-scan stay on almost everything |
| 9 | Rate Limiting | public-abuse: `A2`&`A5≥E2`&`A4` · runaway-guard: `A7` or `A8` | public/login-abuse off for a trusted single user — **but runaway-loop + retry-backoff stays** whenever there's a background caller |
| 10 | Caching & CDN | **static-asset caching: any UI with assets (`A1`)** · CDN: `A5=E3` · data caching: expensive recompute | CDN, cross-user cache-scoping, stampede off when single-user/local — **static-asset caching stays** |
| 11 | Load Balancing & Scaling | `A9` true | single instance → whole layer off |
| 12 | Error Tracking & Logs | `A5≥E1`, or `A7`, or `A6` (runs unattended / matters) | trivial one-shot you watch → minimal; external tooling scales with stakes |
| 13 | Availability & Recovery | backups: `A3` & hard-to-recreate data · uptime: `A5≥E2` | no persistence / nothing depends on it → off · **backups+restore mandatory whenever `A6`** |

**HTTPS note:** mandatory the instant the app is reachable over a network — `A5≥E2` (your
phone counts). N/A at E0 (no server). At E1 (strictly localhost) traffic never leaves the
machine, so not required there — but the moment it's exposed, it becomes mandatory.

## 3. Worked proof — a live-production money app (money app)

```
A1 UI = YES · A2 request = YES · A3 persist = YES · A4 multi-identity = NO · A5 exposure = E2 (iPhone)
A6 sensitive = YES (money) · A7 async = YES (fetchers) · A8 metered = NO (free IMAP) · A9 scale = NO (one instance)
```

| Layer | Verdict | Why (from the facts) |
|--|--|--|
| 1 Frontend | APPLIES | A1 — real UI on a phone |
| 2 Backend/API | APPLIES | A2; cross-user access sub-item off (A4=NO) |
| 3 Database | APPLIES | A3 — money correctness/constraints; per-user scoping off (A4=NO) |
| 4 Auth | PARTIAL | login + session hardening on (E2 + login); roles/scope/RLS off (A4=NO) |
| 5 Hosting/Deploy | PARTIAL | env-separation, secrets, reproducible build, rollback, HTTPS/padlock (mandatory, E2) on; DNS/staging/CDN off |
| 6 Cloud/Compute | PARTIAL | async retry-safety, idempotency, dead-letter on (A7); serverless-cost/pooler off (A8+A9=NO) |
| 7 CI/CD + VC | APPLIES | version control always; CI pipeline optional (solo) |
| 8 Security/RLS | PARTIAL | secrets, input safety, dependency scan, HTTPS on (A6); RLS/multi-tenant off (A4); CORS/public-CSP off |
| 9 Rate Limiting | PARTIAL | runaway-loop + retry-backoff guard on (A7 fetchers); public/login-abuse off (single trusted user, A8=NO) |
| 10 Caching/CDN | PARTIAL | static-asset caching ON — hashed, long-cached CSS/JS/images so the PWA opens fast; CDN, cross-user scoping, stampede off (local single-user) |
| 11 Load Balancing | N/A | one instance (A9=NO) — the one layer with no surviving sub-item |
| 12 Error Tracking/Logs | APPLIES | unattended money pipeline (A7+A6) — logs + alert you; external Sentry optional |
| 13 Availability/Recovery | PARTIAL | backups + tested restore mandatory (A6 money); external uptime/RTO-RPO scaled down (E2, single user) |

**a live-production money app result (under Rule 2):** 5 APPLIES · 7 PARTIAL · only 1 N/A (Load Balancing — the
single layer that truly needs more than one machine). Everything else engages at least in
part.

## 4. The range (brackets)

| Build archetype | Roughly… |
|--|--|
| Headless one-shot script (E0, no UI, no persist, no secret) | Only #7 version control + light #12 logs. Everything else N/A. The agreed floor. |
| Local single-user app — a live-production money app | 5 apply · 7 partial · 1 N/A |
| Public multi-user SaaS (all facts true, E3) | All 13 apply, full. Nothing folds. |

## 5. Rulings — all locked (Decision §8 + two follow-ups)

1. PROP letters — `A-PROP-001` (Audit stage) + `PBAF-PROP-001` (SOP bind). ✓
2. Audit stage absorbs the old `BUILT-APP-AUDIT` gate. ✓
3. Granularity — light per-module (against the layers that module touches) + one full final audit. ✓
4. Home — `Code-X-V1/SOP/`. ✓
5. Planning coverage — address all 13, cross-checked against the app's actual facts. ✓
6. Applies to every build; N/A derived from the 9 facts, per sub-item (Rule 2). ✓
7. HTTPS/padlock — MANDATORY at E2+ (reachable over any network, incl. your phone). ✓
8. Version control — always mandatory, every build. ✓
9. Backups + tested restore — mandatory whenever data is sensitive (A6), even local single-user. ✓
10. CI pipeline — optional for solo/manual builds (version control still mandatory). ✓
11. Headless-script floor — a true E0 no-data no-secret script = version control + basic logging only. Not a loophole (auditor re-checks facts). ✓

---
v0.2 · SOP Applicability Model · all rulings locked · 2026-07-01. No canonical file touched
in the source draft; this file is the v1.22 canonical port (PBAF-PROP-001).
