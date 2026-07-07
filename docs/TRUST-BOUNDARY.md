# How the trust holds — and where it doesn't

> The full trust-boundary discussion, moved here from the [README](../README.md) (which keeps the condensed core under "What the checker proves — and what it can't"). Nothing below was shortened.

A fair, sharp question: the AI writes the state file and many of the artefacts `cx` reads. So what stops a *drifting* agent from writing a state file that simply passes?

No single layer is forge-proof. The protection is the **stack**, where each layer covers a way the others can be fooled:

- **A deterministic checker** the agent can't argue with — `cx` is mechanical Python, not an AI grading an AI.
- **Hash-bound receipts** that tie every approval and review to a fingerprint of the source.
- **An opposite-family reviewer** — a *different* vendor, not the AI that wrote the code.
- **A fresh reader** who didn't author the artefact, and **a human** who owns the decisions.
- **An append-only decision ledger** — every settled decision is recorded; contradicting one later without a recorded override is itself a blocking finding.

**What `cx` proves:** required artefacts exist, fields are present, hashes match, paths are safe, statuses are typed, approvals are current, and reverse coverage holds — every requirement marked `BUILDING` has a card, so nothing was dropped at compile. Newer check families keep the same shape: screen-render fidelity, blueprint readiness, and session-handoff continuity (boot receipts are machine-generated; a handoff's plan-lock pointer is recomputed from the real files at write and at read, so a resume can't quietly drift).

**What `cx` can't prove:** that the requirement was *right*, that the product judgment is sound, that the security model holds, or that a test is meaningful rather than tautological. Those need the fresh reader, the cross-family review, and the human. *Green ≠ enforcing* applies to `cx` itself — it checks shape and existence, not meaning.

**Test circularity** is the same shape: the same AI can write both the code and its tests, so passing tests can be hollow. Code-X fights that with contract-bite tests (the 456 gate clauses), cross-family review of the tests, and the Audit stage's whole-app check that the app is actually wired and running — *built + green ≠ wired*. Residual risk remains, and it's named here on purpose rather than hidden. One gap that used to sit here — acceptance receipts being presence-checked rather than recomputed — is now closed: `/cx-accept` machine-stamps each acceptance and its identity is recomputed against the exact commit the human signed off on, so a hand-edited receipt can't pass (forge-parity acceptance recompute, shipped in v1.22.5).

**Security runs the same fail-closed shape:** dependencies are scanned before build (zero high/critical findings, or an explicit human waiver on record), every card answers a security tripwire that is checked against the actual diff — not self-attested — and anything that leaves the machine passes a PII/egress scrub first.

**Why four review layers, not one?** Because the director can't fix bugs by hand, so the system catches as much as it can before the human is asked to trust the result:

1. **Mechanical checks** — free, deterministic, run on every card.
2. **CodeRabbit** — external automated code review. Useful, but it never satisfies the cross-family checkpoint.
3. **Self-review** — the builder family reviews its own work, under a capped loop.
4. **Opposite-family review** — a *different* AI family reviews the module before it ships.

The same ladder guards more than the build: the entire frozen plan gets a full opposite-family read before building is ever authorized, and at the final audit the cross-family receipt is mandatory. Shipping itself is certified, not declared — the checker auto-assembles the final-ready certificate, and a passing final audit is a hard precondition of it.

The expensive part was never *having* reviews — it was the **looping** (review → fix → re-review → fix…). Code-X catches mechanical issues first, asks each reviewer for all findings in one pass, fixes the whole class, and pins it with a deterministic test. Keep the coverage, kill the loops. (Nine review passes on a single bank-statement parser — the case documented in [VALIDATION.md](../VALIDATION.md) — is what forced that rule.)
