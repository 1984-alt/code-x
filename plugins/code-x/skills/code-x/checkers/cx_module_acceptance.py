# cmd_module_acceptance: the ANDON WALL (V1.10 module_acceptance gate family).
#
# Module N+1 cannot unlock until module N carries a MODULE-ACCEPTANCE receipt that is:
#   1. present and readable (a hand-edited `accepted` in state with no receipt is rejected),
#   1b. identifies its module — non-empty module_id EXACTLY equal to the requested module (a
#       sha-bound but module-LESS receipt would 'accept' ANY module; V1.10 R4, GPT R10),
#   2. verdict == accepted,
#   3. generator-stamped — non-empty generated_by (the receipt names its generator; `cx check accept`
#      is that generator today — enforced as non-empty; a receipt with no generator is bare text),
#   4. binding-fields present — non-empty state_sha_before + quality_card_hash, and
#   5. bound to state by sha — state.accepted_modules[module_id].acceptance_sha12 must equal the
#      receipt file's sha12 (swapping / hand-editing the recorded acceptance is rejected).
#
# SHIPPED (B-PROP-013, design-history/b-prop-013-forge-parity-design-2026-07-06.md — was tracked as
# acceptance-binding debt through V1.10; the debt is CLOSED, not merely presence-asserted anymore):
# the receipt FILE is sha12-bound to state (clause 5) — a swapped or hand-edited recorded acceptance
# is rejected. Clause 4's binding fields are now RECOMPUTED, not just presence-asserted:
# `forge_parity_findings` below (gated on the packet's `b_prop_013_forge_parity` marker, §4) reaches
# behind clause 4 to recompute verify_app/module_demo/live_slice_accept.repo_sha reachability
# against the real commit graph (§2a) and quality_card_hash against the recomputed canonical hash of
# the inline quality_card block (§2b, drift-detection honest limit — see its docstring).
# `state_sha_before` stays a generation-honest ceiling (§2c) — captured once, at stamp time, by
# `cx check accept` (cx_accept.py, the STAMPER); it is not later re-derivable, symmetric with
# `cx check boot`'s own repo_head ceiling. HONEST FRAMING (do not overclaim): the stamper is
# ergonomics + the one honest capture moment, NOT the wall — a hand-authored receipt can still skip
# it entirely. THE WALL is this file's recompute + the state<->file sha12 seal (clause 5).
#
#   cx check module-acceptance --module-id <id> --state <CODE-X-STATE.yaml> \
#       [--acceptance <MODULE-ACCEPTANCE.yaml>] [--repo-root <dir>]
#
# READ-ONLY: never builds, routes actors, edits source, or generates the receipt (that is
# `cx check accept`, cx_accept.py).
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from cx_common import findings_report, load_yaml, nested_get, resolve_risk_tier
from cx_lock_fidelity import resolve_in_repo
# Read-only reuse of the packet-stage manifest filename constant (PB-PROP-003 Unit 2) — never
# imports FROM cx_module_acceptance into cx_packet, so no cycle; cx_packet only ever reads this
# module's exports for tests, never at runtime.
from cx_packet import MANIFEST_FILE as _MANIFEST_FILE

# BF-PROP-006: phantom-completion guard. A module accepted whose build baseline (repo_sha_before)
# is identical to HEAD (zero files changed) shipped NO real code — the receipt is green but the
# wall is not enforcing. Risk-flag intersection escalates the empty-diff finding to P0.
_HEX12_RE = re.compile(r"^[0-9a-fA-F]{12,}$")
# risk-escalation reads risk_flags from the receipt's module_acceptance block (ma.get("risk_flags")).
_HIGH_RISK_FLAGS = {"money", "login", "auth", "data", "security"}
# Fresh-clone / test-fixture sentinel: a static good-path fixture has NO real commit graph to bind
# to (a fresh public-release clone has a different root commit), so it cannot carry a real
# repo_sha_before. This sentinel skips ONLY the git verification leg, and ONLY under
# CODE_X_TEST_MODE=1 — in production it is just a non-hex value and fails closed as malformed.
_FRESH_CLONE_TEST_SENTINEL = "NONE_TEST_FIXTURE"
# Blocking severities. P2/P3 findings from this validator are non-escalating advisories (per the
# locked CX-CHECK-SPEC: a legacy_no_baseline carve-out is a NON-BLOCKING P2 migration-debt advisory).
_BLOCKING = {"P0", "P1"}


def has_blocking(findings) -> bool:
    """True if any finding is a blocking severity (P0/P1). P2/P3 are advisories that do not block
    acceptance — the module is validly accepted WITH migration debt (locked spec)."""
    return any(sev in _BLOCKING for sev, _loc, _msg in findings)


# B-PROP-008 (Live Slice Delivery): a live_slice module (a user-facing PAGE slice, flagged in the
# FROZEN registry) must carry a typed live_slice_accept block proving the CEO DROVE the running
# build live on the Mac — not a Mode A screenshot/shell accept or a module-level batch. Presence +
# shape ONLY: the checker proves the running build existed (live_url) and the CEO recorded driving
# it; whether it FELT right stays the CEO's accept (no over-claiming the experience — the cardinal sin).
_LIVE_SLICE_ACCEPT_STRING_FIELDS = ("live_url", "ceo_turn_ref", "repo_sha")

# PBF-PROP-012 Part E (SEE-AND-TEST gate): the demo collector that generated the shown screenshot must
# be machine-stamped — mirrors _MACHINE_GENERATORS in cx_render_fidelity.py.
_DEMO_GENERATORS = {"cx demo collect", "cx-demo-collect", "verify-app"}
# CEO-locked mobile simulator device (E-A2 — workspace standing rule; a per-project list is a
# trivial future change if a project ever targets another device; note that in §7 of the design).
_DEMO_MOBILE_SIM = "iphone-13-pro"


def registry_flag_true(v) -> bool:
    """A frozen-registry boolean flag (live_slice / walking_skeleton) is True ONLY for a real boolean
    True or an explicit 'true'/'yes' string — NOT a truthy-coerced bool('false')==True (built-code
    review P2: a quoted live_slice: 'false' must not fire the live-drive gate on an honest build)."""
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes"))


def validate_module_demo(ma, receipt_loc, base=None):
    """PBF-PROP-012 Part E (SEE-AND-TEST gate): validate the module_demo block on a live_slice module's
    acceptance receipt. Returns a list of findings — EMPTY means the demo evidence is well-formed.
    Called from validate_live_slice_accept as a precondition (so both the order wall and
    cx check module-quality enforce the demo before the CEO live-drive accept, in both return paths).

    Checks (all fail-closed, P0 per clause table §4):
    1. module_demo block exists and is a mapping.
    2. surface ∈ {web, mobile}.
    3. generated_by ∈ _DEMO_GENERATORS (machine-stamped, not hand-authored).
    4. repo_sha is hex >=12 (shape only, honest scope — same as verify_app).
    5. shown_screenshot_path exists, is path-safe, file is present.
    6. shown_screenshot_hash == _sha12(real bytes) — anti-forgery anchor (B-PROP-009 pattern).
    7. Surface-appropriate evidence: web → live_url present, simulator ABSENT; mobile → simulator ==
       iphone-13-pro, live_url ABSENT (cross-field surface guard).
    8. ceo_accept_token non-blank AND equal to live_slice_accept.ceo_accept_token (binding check).
    9. ceo_accept_token embeds module_demo.repo_sha[:6] prefix (E-A1 — unique-per-slice token).
    10. ceo_turn_ref: path-safe AND the file exists (resolves to a real in-repo turn artifact).
    11. ceo_verdict ∈ {accepted, needs_fix}; accept requires ceo_verdict == accepted (E-A3).

    RESIDUAL HONEST LIMIT: E proves a real build was rendered on the correct surface, the exact
    screenshot bytes shown are bound into the receipt, and a CEO-typed accept token resolves to a
    real turn artifact — but it cannot prove the CEO's eyes were on the screen or that the token
    was typed by the CEO rather than transcribed by the orchestrator; that the human saw it and
    drove it remains human-attested, and E does not claim otherwise (over-claiming is the cardinal sin).
    """
    md = ma.get("module_demo") if isinstance(ma, dict) else None
    if not isinstance(md, dict):
        return [("P0", receipt_loc,
            "live_slice module accepted with NO typed module_demo block — the SEE-AND-TEST "
            "show-step was skipped: the demo block must record the surface (web/mobile), a "
            "machine-captured shown screenshot (hash-bound), and the CEO's typed accept token "
            "before the module can be accepted; without it ceo_drove is a bare self-ticked "
            "boolean (the real-project failure PBF-PROP-012 Part E fixes)")]

    findings = []

    def _s(key):
        v = md.get(key, "")
        return v.strip() if isinstance(v, str) else ""

    # 2. surface enum
    surface = _s("surface")
    if surface not in ("web", "mobile"):
        findings.append(("P0", receipt_loc,
            f"module_demo.surface '{surface or 'MISSING'}' is not in {{web, mobile}} — the demo "
            "block must declare which screen the build ran on (PBF-PROP-012 Part E)"))
        surface = ""  # suppress downstream surface-conditional checks

    # 3. generated_by must be machine-stamped
    gen = _s("generated_by")
    if gen not in _DEMO_GENERATORS:
        findings.append(("P0", receipt_loc,
            f"module_demo.generated_by '{gen or 'MISSING'}' is not a machine demo collector "
            f"(must be one of {sorted(_DEMO_GENERATORS)}) — a hand-authored marker is not "
            "proof the CEO was shown a real running build (PBF-PROP-012 Part E)"))

    # 4. repo_sha hex >=12 (shape only, honest scope — mirrors verify_app.repo_sha)
    repo_sha = _s("repo_sha")
    if not _HEX12_RE.match(repo_sha):
        findings.append(("P0", receipt_loc,
            f"module_demo.repo_sha '{repo_sha or 'MISSING'}' is not a hex commit id of >=12 "
            "chars — the receipt does not record which build was demoed in a commit-shaped "
            "field (hex shape only; the checker does not verify it is HEAD — honest scope, "
            "mirrors verify_app.repo_sha) (PBF-PROP-012 Part E)"))

    # 5–6. shown_screenshot_path: path-safe, file exists, hash matches real bytes
    shot_path = _s("shown_screenshot_path")
    shot_hash = _s("shown_screenshot_hash")
    base_dir = Path(base) if base else Path(receipt_loc).resolve().parent
    if not shot_path:
        findings.append(("P0", receipt_loc,
            "module_demo.shown_screenshot_path missing/blank — a path to the real screenshot "
            "the CEO was shown is required (PBF-PROP-012 Part E)"))
    else:
        p = Path(shot_path)
        if p.is_absolute() or ".." in p.parts:
            findings.append(("P0", receipt_loc,
                f"module_demo.shown_screenshot_path '{shot_path}' is an absolute path or "
                "contains '..' — only repo-relative paths are accepted (PBF-PROP-012 Part E)"))
        else:
            full = base_dir / p
            try:
                if full.is_symlink() or not full.resolve().is_relative_to(base_dir.resolve()):
                    findings.append(("P0", receipt_loc,
                        f"module_demo.shown_screenshot_path '{shot_path}' is a symlink or "
                        "resolves outside the repo — the screenshot must be a real in-repo "
                        "file (PBF-PROP-012 Part E)"))
                elif not full.is_file():
                    findings.append(("P0", receipt_loc,
                        f"module_demo.shown_screenshot_path '{shot_path}' does not exist — "
                        "the screenshot the CEO was shown must be a committed in-repo file "
                        "(PBF-PROP-012 Part E)"))
                else:
                    real_hash = _sha12(str(full))
                    if real_hash is None:
                        findings.append(("P0", receipt_loc,
                            f"module_demo shown_screenshot_path '{shot_path}' unreadable for hashing"))
                    elif shot_hash != real_hash:
                        findings.append(("P0", receipt_loc,
                            f"module_demo.shown_screenshot_hash '{shot_hash}' != recomputed "
                            f"'{real_hash}' — the declared screenshot hash does not match the "
                            "real file bytes (screenshot was swapped or hand-edited; "
                            "PBF-PROP-012 Part E / B-PROP-009 anti-forgery pattern)"))
            except OSError:
                findings.append(("P0", receipt_loc,
                    f"module_demo.shown_screenshot_path '{shot_path}' cannot be resolved"))

    # PRESENTED-VISUAL-HAS-DIFF-RECEIPT (P1, PBF-PROP-020 Rule 4) — FORWARD-SCOPE (CEO-D-046
    # grandfather, 2026-07-05): enforced only when the demo DECLARES any 020 diff field
    # (mockup_ref / diff_score / tolerance). A pre-020 receipt that carries none is grandfathered
    # (untouched — never retro-broken). When ANY is present the FULL receipt is required (no
    # half-filled dodge): a HASH-BOUND mockup (mockup_ref + mockup_hash == sha12 of real bytes) +
    # a passing diff (diff_score <= tolerance). The mechanical proof the comparison was RUN — never
    # a free-text 'confirmed', nor a mockup_ref pointed at any image (own-eyes stays honest-scope).
    mockup_ref = _s("mockup_ref")
    _diff_declared = bool(mockup_ref) or ("diff_score" in md) or ("tolerance" in md)
    if not _diff_declared:
        # FOLD RE-SWEEP FIX (WAVE-TRIGGERED, not field-triggered): validate_module_demo runs ONLY
        # on live_slice / CEO-visible acceptances — all three callers (validate_live_slice_accept,
        # graduation _crit_c1, module-quality) guard on the FROZEN registry live_slice flag — so the
        # rendered-vs-mockup diff receipt is REQUIRED here, not merely validated-if-declared. Omitting
        # all three fields was the fail-open dodge the extra xfam sweep caught (EVAL-051 already claims
        # 'every CEO-visible acceptance'). A GENUINE pre-020 receipt declares a typed
        # legacy_no_diff_receipt carve-out (advisory, migration debt); a bare omission fails closed.
        _carveout = _s("legacy_no_diff_receipt")
        if _carveout:
            findings.append(("P2", receipt_loc,
                f"module_demo has no rendered-vs-mockup diff receipt (legacy_no_diff_receipt: "
                f"{_carveout}) — pre-020 grandfather, migration debt (PBF-PROP-020 Rule 4)"))
        else:
            findings.append(("P1", receipt_loc,
                "module_demo on a CEO-visible/live_slice acceptance has NO rendered-vs-mockup diff "
                "receipt — a live-drive acceptance must carry a hash-bound mockup + passing diff "
                "(mockup_ref + mockup_hash + diff_score <= tolerance), or a typed legacy_no_diff_receipt "
                "carve-out for a genuine pre-020 receipt; a free-text 'confirmed' / omission no longer "
                "satisfies acceptance (PRESENTED-VISUAL-HAS-DIFF-RECEIPT, PBF-PROP-020 Rule 4)"))
    if _diff_declared:
        if not mockup_ref:
            findings.append(("P1", receipt_loc,
                "module_demo declares a diff field but mockup_ref is missing/blank — a 020-era "
                "diff receipt must be complete: a hash-bound mockup the screenshot was diffed "
                "against (PRESENTED-VISUAL-HAS-DIFF-RECEIPT, PBF-PROP-020 Rule 4)"))
        else:
            mr = Path(mockup_ref)
            if mr.is_absolute() or ".." in mr.parts:
                findings.append(("P1", receipt_loc,
                    f"module_demo.mockup_ref '{mockup_ref}' is an absolute path or contains '..' — "
                    "only repo-relative paths are accepted (PBF-PROP-020 Rule 4)"))
            else:
                full_mr = base_dir / mr
                try:
                    if full_mr.is_symlink() or not full_mr.resolve().is_relative_to(base_dir.resolve()):
                        findings.append(("P1", receipt_loc,
                            f"module_demo.mockup_ref '{mockup_ref}' is a symlink or resolves outside "
                            "the repo (PBF-PROP-020 Rule 4)"))
                    elif not full_mr.is_file():
                        findings.append(("P1", receipt_loc,
                            f"module_demo.mockup_ref '{mockup_ref}' does not exist — the mockup the "
                            "shown screenshot was diffed against must be a committed in-repo file "
                            "(PRESENTED-VISUAL-HAS-DIFF-RECEIPT, PBF-PROP-020 Rule 4)"))
                    else:
                        # HASH-BINDING (built-code xfam P1): the mockup bytes must match a declared
                        # mockup_hash — a receipt that can point mockup_ref at ANY image is not a
                        # real comparison. Same _sha12 anti-forgery anchor as shown_screenshot_hash.
                        declared_mh = _s("mockup_hash")
                        real_mh = _sha12(str(full_mr))
                        if not declared_mh:
                            findings.append(("P1", receipt_loc,
                                "module_demo.mockup_hash missing — the diffed mockup must be hash-bound "
                                "(mockup_hash == sha12 of the mockup bytes), else mockup_ref could point "
                                "at any image (PRESENTED-VISUAL-HAS-DIFF-RECEIPT, PBF-PROP-020 Rule 4)"))
                        elif real_mh is not None and declared_mh != real_mh:
                            findings.append(("P1", receipt_loc,
                                f"module_demo.mockup_hash '{declared_mh}' != recomputed sha12 '{real_mh}' "
                                "of the mockup bytes — the diff receipt is not bound to the shown mockup "
                                "(PRESENTED-VISUAL-HAS-DIFF-RECEIPT, PBF-PROP-020 Rule 4)"))
                except OSError:
                    findings.append(("P1", receipt_loc,
                        f"module_demo.mockup_ref '{mockup_ref}' cannot be resolved"))
        diff_score = md.get("diff_score")
        tolerance = md.get("tolerance")
        if not isinstance(diff_score, (int, float)) or isinstance(diff_score, bool) \
                or not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool):
            findings.append(("P1", receipt_loc,
                "module_demo.diff_score/tolerance missing or not numeric — the rendered-vs-mockup "
                "comparison must be a recorded MACHINE result, not implied "
                "(PRESENTED-VISUAL-HAS-DIFF-RECEIPT, PBF-PROP-020 Rule 4)"))
        elif diff_score > tolerance:
            findings.append(("P1", receipt_loc,
                f"module_demo.diff_score {diff_score} > tolerance {tolerance} — the shown screen does "
                "not match its mockup within tolerance; a CEO-visible acceptance cannot ship on a "
                "failing rendered-vs-mockup diff (PRESENTED-VISUAL-HAS-DIFF-RECEIPT, PBF-PROP-020 Rule 4)"))

    # 7. Cross-field surface guard (surface-appropriate evidence)
    if surface == "web":
        if not _s("live_url"):
            findings.append(("P0", receipt_loc,
                "module_demo surface: web but live_url is missing/blank — a web demo must "
                "record the running URL the CEO opened in Chrome (PBF-PROP-012 Part E)"))
        sim = _s("simulator")
        if sim:
            findings.append(("P0", receipt_loc,
                f"module_demo surface: web but simulator '{sim}' is present — a web demo "
                "must not carry a simulator field (surface mismatch; PBF-PROP-012 Part E)"))
    elif surface == "mobile":
        sim = _s("simulator")
        if sim != _DEMO_MOBILE_SIM:
            findings.append(("P0", receipt_loc,
                f"module_demo surface: mobile but simulator is '{sim or 'MISSING'}' — must "
                f"be '{_DEMO_MOBILE_SIM}' (CEO-locked device; E-A2 PBF-PROP-012 Part E). "
                "A per-project allowed-device list is the trivial upgrade path if another "
                "device is ever needed."))
        if _s("live_url"):
            findings.append(("P0", receipt_loc,
                "module_demo surface: mobile but live_url is present — a mobile demo must "
                "not carry a live_url (surface mismatch; PBF-PROP-012 Part E)"))

    # 8. ceo_accept_token: non-blank + must equal live_slice_accept.ceo_accept_token
    demo_token = _s("ceo_accept_token")
    lsa = ma.get("live_slice_accept") if isinstance(ma, dict) else None
    lsa_token = ""
    if isinstance(lsa, dict):
        v = lsa.get("ceo_accept_token", "")
        lsa_token = v.strip() if isinstance(v, str) else ""
    if not demo_token:
        findings.append(("P0", receipt_loc,
            "module_demo.ceo_accept_token missing/blank — the CEO's distinct typed accept "
            "token must be recorded in the demo block (PBF-PROP-012 Part E)"))
    elif not lsa_token:
        pass  # live_slice_accept.ceo_accept_token absence is caught by validate_live_slice_accept
    elif demo_token != lsa_token:
        findings.append(("P0", receipt_loc,
            f"module_demo.ceo_accept_token '{demo_token}' != live_slice_accept.ceo_accept_token "
            f"'{lsa_token}' — the human accept is not bound to the shown demo "
            "(PBF-PROP-012 Part E)"))

    # 9. E-A1: token must embed repo_sha prefix (first 6 hex chars) — unique per slice
    if demo_token and _HEX12_RE.match(repo_sha):
        sha_prefix = repo_sha[:6].lower()
        if sha_prefix not in demo_token.lower():
            findings.append(("P0", receipt_loc,
                f"module_demo.ceo_accept_token '{demo_token}' does not embed the repo_sha "
                f"prefix '{sha_prefix}' — the token must include the first 6 chars of "
                "module_demo.repo_sha so it is unique per slice and cannot be reused across "
                "builds (E-A1 PBF-PROP-012 Part E)"))

    # 10. ceo_turn_ref: path-safe + file exists
    turn_ref = _s("ceo_turn_ref")
    if not turn_ref:
        findings.append(("P0", receipt_loc,
            "module_demo.ceo_turn_ref missing/blank — must resolve to a real in-repo CEO "
            "turn artifact (handoff or transcript line carrying the typed accept); without "
            "it the CEO accept token cannot be traced to a real CEO message (PBF-PROP-012 Part E)"))
    else:
        tr = Path(turn_ref)
        if tr.is_absolute() or ".." in tr.parts:
            findings.append(("P0", receipt_loc,
                f"module_demo.ceo_turn_ref '{turn_ref}' is an absolute path or contains '..' "
                "— only repo-relative paths are accepted (PBF-PROP-012 Part E)"))
        else:
            full_tr = base_dir / tr
            try:
                if full_tr.is_symlink() or not full_tr.resolve().is_relative_to(base_dir.resolve()):
                    findings.append(("P0", receipt_loc,
                        f"module_demo.ceo_turn_ref '{turn_ref}' is a symlink or resolves "
                        "outside the repo (PBF-PROP-012 Part E)"))
                elif not full_tr.is_file():
                    findings.append(("P0", receipt_loc,
                        f"module_demo.ceo_turn_ref '{turn_ref}' does not exist — the CEO "
                        "turn artifact (handoff/transcript carrying the typed accept) must "
                        "be a committed in-repo file (PBF-PROP-012 Part E)"))
            except OSError:
                findings.append(("P0", receipt_loc,
                    f"module_demo.ceo_turn_ref '{turn_ref}' cannot be resolved"))

    # 11. E-A3: ceo_verdict ∈ {accepted, needs_fix}; accept requires accepted
    verdict = _s("ceo_verdict")
    if verdict not in ("accepted", "needs_fix"):
        findings.append(("P0", receipt_loc,
            f"module_demo.ceo_verdict '{verdict or 'MISSING'}' must be 'accepted' or "
            "'needs_fix' — a missing or unknown verdict means the CEO's demo decision is "
            "not recorded (PBF-PROP-012 Part E E-A3)"))
    elif verdict == "needs_fix":
        findings.append(("P0", receipt_loc,
            "module_demo.ceo_verdict is 'needs_fix' — the CEO drove the demo and requested "
            "fixes; the module is NOT accepted and the next slice is blocked until a fresh "
            "demo shows 'accepted' (PBF-PROP-012 Part E E-A3)"))

    return findings


def validate_live_slice_accept(ma, receipt_loc, base=None, packet_dir=None, module_id=None):
    """Validate the live_slice_accept block on a live_slice module's acceptance receipt. Returns a
    list of findings — EMPTY means the CEO live-drive accept is well-formed. Shared by the order
    wall (via validate_accepted_module's require_live_slice path) and cx check module-quality (B-PROP-008).

    B-PROP-010: a passing verify_app receipt is a PRECONDITION — validate_verify_app runs alongside the
    live_slice_accept checks (in BOTH return paths) so a live_slice module cannot be validly accepted
    unless the verify-app agent already drove the running build and passed its acceptance-criteria check
    at slice completion, BEFORE the CEO live-drive.

    PBF-PROP-012 Part E: a well-formed module_demo block is also a PRECONDITION — validate_module_demo
    runs in BOTH return paths so a live_slice module cannot be accepted without the SEE-AND-TEST
    show-step evidence (surface-aware, screenshot-bound, CEO-token-bound). base = repo root for
    screenshot path-safety resolution.

    PB-PROP-003 Unit 2 (acceptance-stage wiring, Design Resolution v2): packet_dir + module_id (both
    optional, caller-supplied) enable the criteria_refs wiring/reverse-coverage checks — see
    validate_verify_app (Layer 1 resolution) and _reverse_coverage_findings (Layer 2, registry-
    enumerated). Either omitted -> those checks silently do not run (the caller had no packet context
    to prove them against); this never widens what is REQUIRED, it only widens what CAN be checked."""
    va_findings = validate_verify_app(ma, receipt_loc, packet_dir=packet_dir)
    demo_findings = validate_module_demo(ma, receipt_loc, base)   # PBF-PROP-012 Part E precondition
    lsa = ma.get("live_slice_accept") if isinstance(ma, dict) else None
    if not isinstance(lsa, dict):
        return va_findings + demo_findings + [("P0", receipt_loc,
            "live_slice module accepted with NO typed live_slice_accept block "
            "{live_url, ceo_drove, ceo_turn_ref, repo_sha} — a Mode A screenshot/shell accept or a "
            "module-level batch is not proof the CEO DROVE the running build live on the Mac (B-PROP-008)")]
    findings = list(va_findings) + list(demo_findings)
    if module_id:
        findings.extend(_reverse_coverage_findings(ma, receipt_loc, packet_dir, module_id))

    def _s(key):
        v = lsa.get(key, "")
        return v.strip() if isinstance(v, str) else ""  # a non-string is treated as ABSENT (fail closed)

    missing = [k for k in _LIVE_SLICE_ACCEPT_STRING_FIELDS if not _s(k)]
    if missing:
        findings.append(("P0", receipt_loc,
            f"live_slice_accept missing/blank {missing} — live_url (the running build the CEO opened) "
            "+ ceo_turn_ref + repo_sha must each be a non-empty string (B-PROP-008)"))
    drove = lsa.get("ceo_drove")
    if drove is not True and str(drove).strip().lower() not in ("true", "yes"):
        findings.append(("P0", receipt_loc,
            "live_slice_accept.ceo_drove is not true — the CEO must record DRIVING the running build "
            "live (not just seeing a screenshot); without it the live-drive gate is goodwill (B-PROP-008)"))

    # PBF-PROP-012 Part E: ceo_accept_token must be present and non-blank in live_slice_accept.
    # The binding between demo token and accept token is enforced in validate_module_demo above;
    # here we only enforce the live_slice_accept side is non-blank (absence is the simpler P0).
    token = _s("ceo_accept_token")
    if not token:
        findings.append(("P0", receipt_loc,
            "live_slice_accept.ceo_accept_token missing/blank — ceo_drove is no longer "
            "believed without the CEO's distinct typed accept token; the token binds the "
            "human accept to the shown demo (PBF-PROP-012 Part E)"))
    return findings


# B-PROP-010 (Verify-App Gate): runtime behavior is machine-verified once per completed slice. A
# live_slice module must carry a verify_app receipt proving the verify-app agent DROVE the running
# build and checked its acceptance criteria at runtime — a PRECONDITION run before the CEO live-drive,
# so the CEO never drives (or accepts) a build whose behavior was never machine-exercised. Presence +
# shape-binding + verdict ONLY: the checker proves a generator-stamped verify_app block carrying a
# hex-SHAPED repo_sha recorded passed == True; it does NOT re-run the app (the agent's job), does NOT
# verify repo_sha is HEAD / a real commit (no commit-graph check, mirroring live_slice_accept.repo_sha),
# and never claims the behavior was perfect (the CEO live-drive still judges the experience — no
# over-claiming, the cardinal sin per B-PROP-008).
# criteria_ref(s) grammar/resolution is validated SEPARATELY (_validate_criteria_wiring, PB-PROP-003
# Unit 2) — its required shape depends on the packet's pb_prop_003_wiring marker (§R5), unlike these
# two which are unconditionally required on every verify_app block.
_VERIFY_APP_STRING_FIELDS = ("repo_sha", "generated_by")
# PB-PROP-003 Unit 2 (§R5): the frozen packet declares this top-level requirements-manifest.yaml
# field to opt IN to the new resolving criteria_refs wiring/reverse-coverage. A packet's ABSENCE of
# this marker (the default — every pre-existing packet) keeps the OLD free-text criteria_ref accepted
# under a non-blocking legacy advisory, so already-shipped apps and any other in-flight project never
# retroactively breaks at the order wall.
_PB_PROP_003_MARKER_FIELD = "pb_prop_003_wiring"
_REGISTRY_FILE = "MODULE-REGISTRY.yaml"

# B-PROP-013 (forge-parity acceptance recompute, design-history/b-prop-013-forge-parity-design-
# 2026-07-06.md): a NEW capability marker in the frozen requirements-manifest.yaml. Tri-state
# resolver mirrors _resolve_pb_prop_003_wiring_state exactly (§4 activation): "absent" (no
# packet_dir / unreadable manifest / field genuinely missing) -> legacy presence-only path,
# non-blocking (grandfathers in-flight already-shipped apps); "enabled" (real boolean True) -> the §2
# recompute legs below run; "malformed" (present but not real bool True) -> P1 fail-closed (a
# packet that TRIED to opt in and botched it must not silently fall to the legacy carve-out).
FORGE_PARITY_MARKER_FIELD = "b_prop_013_forge_parity"


def _resolve_forge_parity_marker_state(packet_dir) -> str:
    """B-PROP-013 §4 — tri-state marker resolver, same read pattern + vocabulary as
    _resolve_pb_prop_003_wiring_state (kept as a separate function, not a generic helper: the two
    markers gate unrelated capabilities and must be free to diverge later)."""
    if not packet_dir:
        return "absent"
    data, err = load_yaml(str(Path(packet_dir) / _MANIFEST_FILE))
    if err or not isinstance(data, dict):
        return "absent"
    if FORGE_PARITY_MARKER_FIELD not in data:
        return "absent"
    return "enabled" if data.get(FORGE_PARITY_MARKER_FIELD) is True else "malformed"


def _canonicalize_quality_card_hash(qc: dict) -> str:
    """B-PROP-013 §2b: deterministic canonicalization of the INLINE quality_card block (stable key
    order + normalized scalars via json's sort_keys) hashed with the same sha12 convention as the
    rest of this file (first 12 hex chars of a sha256). HONEST LIMIT (must travel with every caller
    of this function): the block and its hash both live in the same receipt, so this recompute is
    drift/typo detection, not forge resistance — a forger who edits the block just re-hashes it
    (design §2b/§10.1). It exists to catch accidental drift, not to be sold as an anti-forge wall."""
    canonical = json.dumps(qc, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _repo_sha_reachability_finding(repo_root, sha: str, field_label: str, receipt_loc) -> tuple | None:
    """B-PROP-013 §2a: a hex-shaped repo_sha that is not a real ANCESTOR commit of HEAD is
    fabrication (P0) — consistent with the existing non-hex=P0 / empty=P0 grades on these same
    fields. Reuses the ACTUAL BF-PROP-006 git leg verbatim: `merge-base --is-ancestor <sha> HEAD`
    (cx_module_acceptance.py's own repo_sha_before check, ~L1151) — NOT `cat-file -e <sha>^{commit}`,
    which only proves the object exists in the repo's object database (a real commit authored on an
    unrelated side branch, or any dangling object, satisfies cat-file -e while never having been on
    this history at all — FIX-FIRST closed this exact gap, B-PROP-013 xfam P1). Returns None when
    the field is blank / non-hex (already graded by the caller's shape check), or when reachability
    genuinely cannot be determined (no repo_root, no git repo) — this function never widens what is
    REQUIRED, only what CAN be checked, mirroring the rest of this file.
    HONEST LIMIT (§10.4): ancestry proves the commit is really on THIS branch's history, not that it
    was the exact HEAD the human drove — the ceo_accept_token<->HEAD tie enforced by /cx-accept (§3)
    is what binds identity to the precise commit; this guard's job is only to reject non-real /
    off-history (fabricated) commits."""
    if not sha or not _HEX12_RE.match(sha):
        return None
    if sha == _FRESH_CLONE_TEST_SENTINEL and os.environ.get("CODE_X_TEST_MODE") == "1":
        return None  # fresh-clone test fixture — no real commit graph to bind to (mirrors BF-PROP-006)
    if not repo_root:
        return None
    if _git(str(repo_root), "rev-parse", "--git-dir")[0] != 0:
        return ("P1", receipt_loc,
            f"no git repo / git unavailable at '{repo_root}' — cannot verify {field_label}.repo_sha "
            f"'{sha}' is a real ancestor commit of HEAD; the B-PROP-013 forge-parity guard cannot run "
            "(MODULE-ACCEPTANCE-REPO-SHA-NOT-A-COMMIT, B-PROP-013 §2a)")
    if _git(str(repo_root), "merge-base", "--is-ancestor", sha, "HEAD")[0] != 0:
        return ("P0", receipt_loc,
            f"{field_label}.repo_sha '{sha}' is hex-shaped but is NOT a real commit that is an "
            f"ancestor of HEAD in '{repo_root}' — fabrication (a forged or off-history/side-branch "
            "commit id must not grade lighter than an empty field; mere object EXISTENCE is not "
            "enough — a real commit from an unrelated branch must still be rejected); ancestry "
            "proves the commit is really on this history, not that it was HEAD when driven — the "
            "ceo_accept_token<->HEAD tie in /cx-accept is what binds identity to the exact commit "
            "(MODULE-ACCEPTANCE-REPO-SHA-NOT-A-COMMIT, B-PROP-013 §2a/§5)")
    return None


def forge_parity_findings(ma: dict, receipt_loc, packet_dir, repo_root,
                          state_has_module_registry_ref: bool = False) -> list:
    """B-PROP-013 Unit 1 — the GUARD (the real forge-parity wall). Called once from
    validate_accepted_module for EVERY module (live_slice or not), gated by the §4 activation
    marker so a legacy packet (marker absent) rides the pre-existing presence-only path unchanged
    (grandfather carve-out — in-flight already-shipped apps never break).

    Checks, ONLY when the marker resolves "enabled":
      - §2a: verify_app.repo_sha / module_demo.repo_sha / live_slice_accept.repo_sha each must be a
        real reachable commit (per-field P0 fabrication finding; blocks that are simply absent on a
        non-live_slice module are silently skipped — nothing to check).
      - §2b: quality_card_hash must equal the recomputed canonical hash of the inline quality_card
        block (P1 drift; skipped if quality_card itself is missing — cx_module_quality already
        grades that absence separately, this is not the place to duplicate it).
    A "malformed" marker state fires its own P1 regardless of the rest (fail-closed marker
    vocabulary, §4/§7 MODULE-ACCEPTANCE-FORGE-PARITY-MARKER-MALFORMED).

    FIX-FIRST (B-PROP-013 xfam P1, packet_dir-omission fail-open): a packet_dir that is simply
    MISSING from state resolves "absent" here exactly like a genuinely legacy no-packet project —
    that leniency is REQUIRED (judge ruling: failing closed on absent packet_dir would break
    grandfathered already-shipped apps). But when state ALSO carries module_registry_ref — the same
    field cx_build_turn.py's order wall uses to REQUIRE a frozen packet_dir for a module-advancing
    build (cx_build_turn.py ~L100-113) — a state with a registry ref but no packet_dir is an
    anomaly, not genuine legacy: something clearly bound this project to the packet system, yet
    THIS acceptance check has no packet context to resolve the marker against. That is a real,
    named risk, so it fires a NON-BLOCKING P2 ADVISORY (never P0/P1 — the carve-out stays lenient
    exactly as ruled). Mitigation for the residual risk: Fix 3's required-true WRITING-floor
    marker (a NEW packet cannot freeze without declaring the marker) + the pre-existing frozen-
    manifest hash binding (module-start content-binds the card to the frozen packet)."""
    state = _resolve_forge_parity_marker_state(packet_dir)
    if state == "malformed":
        return [("P1", receipt_loc,
            f"the frozen packet's requirements-manifest.yaml declares '{FORGE_PARITY_MARKER_FIELD}' "
            "but its value is not a real boolean true — a marker that TRIED to opt into the "
            "B-PROP-013 forge-parity guard and botched it must NOT silently fall to the legacy "
            "carve-out (that carve-out is for packets that never declared the marker at all); fix "
            "the manifest to a real `true`, or remove the field entirely (fail-closed marker "
            "vocabulary, MODULE-ACCEPTANCE-FORGE-PARITY-MARKER-MALFORMED, B-PROP-013 §4/§7)")]
    if state != "enabled":
        if not packet_dir and state_has_module_registry_ref:
            return [("P2", receipt_loc,
                "state carries module_registry_ref (the SAME signal cx_build_turn.py's order wall "
                "uses to REQUIRE a frozen packet_dir for a module-advancing build) but this "
                "acceptance check received no packet_dir — the B-PROP-013 forge-parity marker "
                "cannot be resolved without packet context, so the guard silently rides the "
                "legacy carve-out; this is an ADVISORY, non-blocking (P0/P1 would break the "
                "CEO-locked grandfather carve-out for genuinely packet-less legacy projects) — "
                "mitigated by Fix 3's required-true WRITING-floor marker + the frozen-manifest "
                "hash binding (MODULE-ACCEPTANCE-FORGE-PARITY-PACKET-CONTEXT-MISSING, "
                "B-PROP-013 §4 FIX-FIRST)")]
        return []

    findings = []
    for block_key, field_label in (("verify_app", "verify_app"),
                                    ("module_demo", "module_demo"),
                                    ("live_slice_accept", "live_slice_accept")):
        block = ma.get(block_key) if isinstance(ma, dict) else None
        sha = block.get("repo_sha", "") if isinstance(block, dict) else ""
        sha = sha.strip() if isinstance(sha, str) else ""
        finding = _repo_sha_reachability_finding(repo_root, sha, field_label, receipt_loc)
        if finding:
            findings.append(finding)

    qc = ma.get("quality_card") if isinstance(ma, dict) else None
    recorded_hash = ma.get("quality_card_hash", "") if isinstance(ma, dict) else ""
    recorded_hash = recorded_hash.strip() if isinstance(recorded_hash, str) else ""
    if isinstance(qc, dict) and qc and recorded_hash:
        recomputed = _canonicalize_quality_card_hash(qc)
        if recorded_hash != recomputed:
            findings.append(("P1", receipt_loc,
                f"quality_card_hash '{recorded_hash}' != recomputed canonical hash '{recomputed}' of "
                "the inline quality_card block — drift between the recorded hash and the block's "
                "real content (HONEST LIMIT: this is drift/typo detection, not forge resistance — "
                "the block and its hash live in the same receipt, so a forger who edits the block "
                "just re-hashes it; the real cover for the whole receipt is the state<->file sha12 "
                "seal) (MODULE-ACCEPTANCE-QUALITY-CARD-HASH-DRIFT, B-PROP-013 §2b/§10.1)"))
    return findings


def _resolve_pb_prop_003_wiring_state(packet_dir) -> str:
    """CX-PB003-002 FIX-FIRST (xfam finding 2, P1): TRI-STATE marker resolver — mirrors
    cx_common.resolve_risk_tier's read pattern (frozen packet's requirements-manifest.yaml
    top-level field), but distinguishes 3 states instead of collapsing to a bool (§R5 fail-closed):
      - "absent"    — no packet_dir, unreadable/malformed manifest, or the field genuinely missing
                      -> the legacy carve-out is legitimate (this packet never tried to opt in).
      - "enabled"   — the field IS present and is a real boolean True -> full wiring ON.
      - "malformed" — the field IS present but is anything else (a string 'true'/'yes', 1, etc.)
                      -> the packet TRIED to opt in but botched it; this must NOT silently resolve
                      to the same legacy carve-out as genuine absence (the bug this fixes: a plain
                      bool collapsed 'malformed' and 'absent' to the same False)."""
    if not packet_dir:
        return "absent"
    data, err = load_yaml(str(Path(packet_dir) / _MANIFEST_FILE))
    if err or not isinstance(data, dict):
        return "absent"
    if _PB_PROP_003_MARKER_FIELD not in data:
        return "absent"
    return "enabled" if data.get(_PB_PROP_003_MARKER_FIELD) is True else "malformed"


def _resolve_pb_prop_003_wiring(packet_dir) -> bool:
    """PB-PROP-003 §R5 capability-gate resolver — back-compat bool view of
    _resolve_pb_prop_003_wiring_state: True only for the "enabled" state. A "malformed" marker is
    NOT "enabled" here (callers that only check this bool still safely skip the full wiring gate),
    but _validate_criteria_wiring separately reads the tri-state to block "malformed" instead of
    silently granting it the "absent" legacy carve-out."""
    return _resolve_pb_prop_003_wiring_state(packet_dir) == "enabled"


def _manifest_requirement_index(manifest_path) -> tuple:
    """PB-PROP-003 Unit 2: load requirements-manifest.yaml and return (index, err).
    index = {requirement_id: {"behavioral": bool, "has_examples": bool}} for every BUILDING row —
    'behavioral' = no non_behavioral_exemption declared (mirrors cx_packet's default-behavioral
    crux); 'has_examples' = acceptance_criterion.examples is a non-empty list. Fails CLOSED
    (None, err) on a malformed/unreadable manifest — mirrors PACKET-GWT-MANIFEST-MALFORMED-FAILS-
    CLOSED (§R8): a malformed manifest must never let a citation silently resolve or a coverage
    check silently skip."""
    data, err = load_yaml(str(manifest_path))
    if err or not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
        return None, err or "no requirements list"
    index = {}
    for row in data["requirements"]:
        if not isinstance(row, dict) or str(row.get("disposition", "")).strip() != "BUILDING":
            continue
        rid = str(row.get("id", "")).strip()
        if not rid:
            continue
        behavioral = row.get("non_behavioral_exemption") is None
        ac = row.get("acceptance_criterion")
        examples = ac.get("examples") if isinstance(ac, dict) else None
        index[rid] = {"behavioral": behavioral,
                      "has_examples": isinstance(examples, list) and len(examples) > 0}
    return index, None


def _registry_module_requirement_ids(registry_path, module_id) -> tuple:
    """PB-PROP-003 Unit 2 §R1: load the FROZEN MODULE-REGISTRY.yaml at registry_path and return
    (requirement_ids, err) for module_id's row — the authority for 'which requirements belong to
    this module' (cx_packet.py PACKET-MODULE-REGISTRY-COVERS-REQUIREMENTS, NOT card source_map)."""
    registry, gerr = load_yaml(str(registry_path))
    if gerr or not isinstance(registry, dict):
        return None, gerr or "registry not a mapping"
    mr = nested_get(registry, "module_registry")
    modules = mr.get("modules") if isinstance(mr, dict) else None
    if not isinstance(modules, list):
        return None, "module_registry.modules missing/not a list"
    mod = next((m for m in modules if isinstance(m, dict)
                and str(m.get("module_id", "")).strip() == module_id), None)
    if mod is None:
        return None, f"module '{module_id}' not found in the frozen registry"
    ids = mod.get("requirement_ids") or []
    if not isinstance(ids, list):
        return None, f"module '{module_id}' requirement_ids is not a list"
    return {str(r).strip() for r in ids if str(r).strip()}, None


def _validate_criteria_wiring(va, receipt_loc, packet_dir):
    """PB-PROP-003 Unit 2 (Design Resolution v2 §R3/§R5/§R7) — Layer 1: criteria_refs GRAMMAR +
    RESOLUTION. Returns a list of findings; EMPTY means either (a) a well-formed new-grammar
    citation set (every id resolves to a real behavioral requirement carrying >=1 example), or
    (b) a legitimate legacy fall-through (no marker declared -> old free-text criteria_ref accepted
    under a typed, non-blocking migration-debt advisory).

    HONESTY (§R6): resolution proves the reference chain is shape-checked + receipt-bound — NOT a
    freshness/forge proof; it does not re-run the app (unchanged B-PROP-010 scope).

    CX-PB003-002 FIX-FIRST (xfam finding 2, P1): a MALFORMED marker (the field is present but not
    a real boolean True — e.g. a quoted `pb_prop_003_wiring: "true"`) is REJECTED here, not
    silently granted the "absent" legacy carve-out (§R5's fail-closed vocabulary: only genuine
    absence is a legitimate non-opt-in)."""
    refs = va.get("criteria_refs")
    legacy_ref = va.get("criteria_ref")
    wiring_state = _resolve_pb_prop_003_wiring_state(packet_dir)

    if wiring_state == "malformed":
        return [("P1", receipt_loc,
            f"the frozen packet's requirements-manifest.yaml declares "
            f"'{_PB_PROP_003_MARKER_FIELD}' but its value is not a real boolean true — a marker "
            "that TRIED to opt into the PB-PROP-003 wiring gate and botched it must NOT silently "
            "fall to the legacy carve-out (that carve-out is for packets that never declared the "
            "marker at all); fix the manifest to a real `true`, or remove the field entirely "
            "(fail-closed marker vocabulary, PB-PROP-003 §R5, xfam finding CX-PB003-002)")]

    if wiring_state != "enabled":
        # §R5 legacy carve-out: a packet that never declared the marker keeps the OLD free-text
        # field, recorded as migration debt (P2, non-blocking) rather than a hard requirement to
        # rewrite every in-flight project's receipts overnight.
        legacy_val = legacy_ref.strip() if isinstance(legacy_ref, str) and legacy_ref.strip() else ""
        has_refs_anyway = isinstance(refs, list) and bool(refs)
        if not legacy_val and not has_refs_anyway:
            return [("P0", receipt_loc,
                "verify_app has neither criteria_ref nor criteria_refs — 'where the checked "
                "acceptance criteria came from' must be recorded as a non-empty string (B-PROP-010)")]
        return [("P2", receipt_loc,
            f"verify_app uses the pre-PB-PROP-003 free-text criteria_ref "
            f"('{legacy_val or refs}') — this packet has not declared the '{_PB_PROP_003_MARKER_FIELD}' "
            "capability marker, so the resolving criteria_refs wiring + reverse-coverage gate is not "
            "enforced here; recorded as migration debt, non-blocking "
            "(ACCEPTANCE-LEGACY-CRITERIA-REF-ADVISORY, PB-PROP-003 §R5)")]

    # Wiring ON (§R7 grammar, spine — every tier): criteria_refs must be PRESENT as a list (an EMPTY
    # list is valid — a LITE module with zero present-example behavioral requirements legitimately
    # cites nothing; reverse coverage, not this grammar check, is what proves nothing was left
    # unwired). Every entry must be a unique, non-blank string resolving to a BEHAVIORAL BUILDING
    # requirement carrying >=1 example.
    if refs is None:
        return [("P0", receipt_loc,
            "verify_app.criteria_refs missing — this packet declares "
            f"'{_PB_PROP_003_MARKER_FIELD}', so the OLD free-text criteria_ref no longer satisfies "
            "the gate; criteria_refs must be declared as a list (empty if this module cites no "
            "requirement) of the requirement id(s) the verify-app agent exercised "
            "(ACCEPTANCE-CRITERIA-REFS-RESOLVE, PB-PROP-003 §R7)")]
    if not isinstance(refs, list):
        return [("P0", receipt_loc,
            f"verify_app.criteria_refs is not a list (got {type(refs).__name__}) "
            "(ACCEPTANCE-CRITERIA-REFS-RESOLVE, PB-PROP-003 §R7)")]
    bad_shape = [r for r in refs if not isinstance(r, str) or not r.strip()]
    if bad_shape:
        return [("P0", receipt_loc,
            f"verify_app.criteria_refs contains non-string/blank entries {bad_shape!r} — every entry "
            "must be a non-empty requirement id string (ACCEPTANCE-CRITERIA-REFS-RESOLVE, "
            "PB-PROP-003 §R7)")]
    clean = [r.strip() for r in refs]
    dupes = sorted({r for r in clean if clean.count(r) > 1})
    if dupes:
        return [("P0", receipt_loc,
            f"verify_app.criteria_refs contains duplicate id(s) {dupes} — each cited requirement "
            "id must be listed once (ACCEPTANCE-CRITERIA-REFS-RESOLVE, PB-PROP-003 §R7)")]
    if not clean:
        return []  # empty-but-present list is valid grammar; reverse coverage judges sufficiency

    index, ierr = _manifest_requirement_index(Path(packet_dir) / _MANIFEST_FILE)
    if ierr:
        return [("P0", receipt_loc,
            f"verify_app.criteria_refs cannot be resolved — the frozen requirements-manifest at "
            f"'{packet_dir}' is unreadable/malformed ({ierr}); the gate fails CLOSED rather than "
            "silently passing an unresolvable citation (ACCEPTANCE-CRITERIA-REFS-RESOLVE, "
            "PB-PROP-003 §R7/§R8)")]
    bad_refs = sorted(r for r in clean
                       if not (index.get(r, {}).get("behavioral") and index.get(r, {}).get("has_examples")))
    if bad_refs:
        return [("P0", receipt_loc,
            f"verify_app.criteria_refs cites {bad_refs} — each id must resolve to a BEHAVIORAL "
            "BUILDING requirement carrying >=1 Given/When/Then example in the frozen requirements-"
            "manifest; a dangling, non-behavioral/exempt, or example-less id cannot be cited as "
            "behavior the verify-app agent exercised (ACCEPTANCE-CRITERIA-REFS-RESOLVE, "
            "PB-PROP-003 §R3/§R7)")]
    return []


def _reverse_coverage_findings(ma, receipt_loc, packet_dir, module_id):
    """PB-PROP-003 Unit 2 (Design Resolution v2 §R1/§R2/§R3) — Layer 2: REVERSE coverage. Enumerates
    the module's behavioral BUILDING requirements from the FROZEN MODULE-REGISTRY row's
    requirement_ids (the authority — cx_packet.py:822-841 PACKET-MODULE-REGISTRY-COVERS-
    REQUIREMENTS — never card source_map), intersected with the manifest's behavioral rows, and
    checks verify_app.criteria_refs covers them. Two teeth, split by tier (§R3):
      - ACCEPTANCE-PRESENT-EXAMPLE-COVERED (P1, SPINE — every tier): any requirement that HAS an
        authored example must be covered by some citation.
      - ACCEPTANCE-BEHAVIORAL-REQ-UNWIRED (P1, CEREMONY — relaxed under LITE): every behavioral
        requirement of the module (whether or not it carries examples) must be covered.
    Gated on the pb_prop_003_wiring marker (§R5) — a legacy packet gets NO reverse-coverage
    findings here (its own advisory already fires from _validate_criteria_wiring)."""
    if not _resolve_pb_prop_003_wiring(packet_dir):
        return []
    reg_ids, rerr = _registry_module_requirement_ids(Path(packet_dir) / _REGISTRY_FILE, module_id)
    if rerr:
        return [("P1", receipt_loc,
            f"cannot compute PB-PROP-003 reverse coverage for module '{module_id}' — {rerr}; the "
            "frozen registry is the requirement-coverage authority and must be readable "
            "(ACCEPTANCE-BEHAVIORAL-REQ-UNWIRED, PB-PROP-003 §R1)")]
    index, ierr = _manifest_requirement_index(Path(packet_dir) / _MANIFEST_FILE)
    if ierr:
        return [("P1", receipt_loc,
            f"cannot compute PB-PROP-003 reverse coverage — the frozen requirements-manifest is "
            f"unreadable/malformed ({ierr}) (ACCEPTANCE-BEHAVIORAL-REQ-UNWIRED, PB-PROP-003 §R1)")]

    va = ma.get("verify_app") if isinstance(ma, dict) else None
    raw_refs = va.get("criteria_refs") if isinstance(va, dict) else None
    covered = ({r.strip() for r in raw_refs if isinstance(r, str) and r.strip()}
               if isinstance(raw_refs, list) else set())

    behavioral_ids = {rid for rid in reg_ids if index.get(rid, {}).get("behavioral")}
    present_example_ids = {rid for rid in behavioral_ids if index[rid]["has_examples"]}

    findings = []
    uncovered_present = sorted(present_example_ids - covered)
    if uncovered_present:
        findings.append(("P1", receipt_loc,
            f"module '{module_id}' has an AUTHORED Given/When/Then example on requirement(s) "
            f"{uncovered_present} that NO verify_app.criteria_refs entry covers — an authored "
            "example must never go unexercised, at ANY risk tier (ACCEPTANCE-PRESENT-EXAMPLE-"
            "COVERED, PB-PROP-003 §R3)"))

    tier = resolve_risk_tier(packet_dir)
    if tier != "LITE":
        uncovered_behavioral = sorted(behavioral_ids - covered)
        if uncovered_behavioral:
            findings.append(("P1", receipt_loc,
                f"module '{module_id}' behavioral BUILDING requirement(s) {uncovered_behavioral} "
                "(from the frozen MODULE-REGISTRY.requirement_ids, PACKET-MODULE-REGISTRY-COVERS-"
                "REQUIREMENTS authority) are covered by NO verify_app.criteria_refs entry — authored"
                "-but-never-wired at module acceptance (ACCEPTANCE-BEHAVIORAL-REQ-UNWIRED, "
                f"PB-PROP-003 §R1/§R3; ceremony — relaxed at LITE tier, current tier '{tier}')"))
    return findings


def validate_verify_app(ma, receipt_loc, packet_dir=None):
    """Validate the verify_app block on a live_slice module's acceptance receipt (B-PROP-010). Returns a
    list of findings — EMPTY means the verify-app runtime gate passed. Called from
    validate_live_slice_accept so the order wall AND cx check module-quality enforce it at the SAME
    chokepoint as the CEO live-drive accept, making a passing verify_app a precondition to acceptance.

    PB-PROP-003 Unit 2: packet_dir (optional) enables the criteria_refs wiring/resolution check
    (_validate_criteria_wiring) — omitted (e.g. a bare `cx check verify-app --acceptance` with no
    --packet-dir), the OLD free-text criteria_ref is accepted with no grammar/resolution check at
    all (there is no packet to resolve against; the legacy-vs-wired distinction needs one)."""
    va = ma.get("verify_app") if isinstance(ma, dict) else None
    if not isinstance(va, dict):
        return [("P0", receipt_loc,
            "live_slice module accepted with NO typed verify_app block "
            "{passed, repo_sha, generated_by, criteria_ref} — the verify-app agent must DRIVE the "
            "running build and check its acceptance criteria at runtime BEFORE the CEO live-drive; "
            "without it the live-drive accept is offered on behavior that was never machine-exercised "
            "(B-PROP-010)")]
    findings = []

    def _s(key):
        v = va.get(key, "")
        return v.strip() if isinstance(v, str) else ""  # a non-string is treated as ABSENT (fail closed)

    missing = [k for k in _VERIFY_APP_STRING_FIELDS if not _s(k)]
    if missing:
        findings.append(("P0", receipt_loc,
            f"verify_app missing/blank {missing} — repo_sha (the build commit the agent drove, recorded "
            "in a hex-shaped field) + generated_by (the verify-app runner, machine-stamped) must each be "
            "a non-empty string; a verify_app block with no recorded binding is model-authored text, "
            "not a runtime gate (B-PROP-010)"))
    elif not _HEX12_RE.match(_s("repo_sha")):
        # HONEST SCOPE (B-PROP-010 xfam, GPT-5.5): presence + hex SHAPE only — the checker does NOT verify
        # repo_sha is HEAD or a real commit (no commit-graph/ancestry check), mirroring
        # live_slice_accept.repo_sha. A valid-hex but stale/forged repo_sha WILL pass shape; the field
        # records WHICH build the agent claims it drove, it is not a freshness proof. So the message must
        # not over-claim "bound to the built code" (the cardinal sin).
        findings.append(("P0", receipt_loc,
            f"verify_app.repo_sha '{_s('repo_sha')}' is not a hex commit id of >=12 chars — the receipt "
            "does not even RECORD which build the agent drove in a commit-shaped field (hex shape only; "
            "the checker does not verify it is HEAD or a real commit) (B-PROP-010)"))

    # PB-PROP-003 Unit 2: criteria_ref(s) grammar + resolution, gated on packet_dir being supplied at
    # all (a bare standalone call with no packet context cannot distinguish legacy-vs-wired, so it
    # skips this leg entirely rather than guessing — unchanged pre-existing behavior for that case).
    if packet_dir:
        findings.extend(_validate_criteria_wiring(va, receipt_loc, packet_dir))
    elif not (isinstance(va.get("criteria_refs"), list) and va.get("criteria_refs")) \
            and not (isinstance(va.get("criteria_ref"), str) and va.get("criteria_ref").strip()):
        findings.append(("P0", receipt_loc,
            "verify_app has neither criteria_ref nor criteria_refs — 'where the checked acceptance "
            "criteria came from' must be recorded as a non-empty string (B-PROP-010)"))

    # verify_app.passed is a MACHINE verdict (the receipt is generated_by a verify-app runner) — NOT a
    # human attestation like live_slice_accept.ceo_drove, so it must be a real boolean True, not a
    # "true"/"yes" STRING. A quoted passed: "yes" on a machine receipt is malformed/suspect → fails closed
    # (B-PROP-010 xfam, GPT-5.5: closes the truthy-coercion class on the gate's core verdict).
    if va.get("passed") is not True:
        findings.append(("P1", receipt_loc,
            "verify_app.passed is not true — the verify-app agent drove the running build and its "
            "runtime acceptance-criteria check did NOT pass (or passed was not recorded as a real boolean "
            "true); the slice cannot be accepted and the CEO live-drive is not offered until the behavior "
            "passes (B-PROP-010)"))
    return findings


def _sha12(path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def _git(repo_root: str, *git_args) -> tuple[int, str]:
    """Run a git command under repo_root (mirror of cx_state._git). Returns (returncode, output)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root)] + list(git_args),
            capture_output=True, text=True,
        )
    except OSError as e:
        return 1, str(e)
    return result.returncode, result.stdout.strip() + result.stderr.strip()


def validate_registry_build_shape(modules: list, loc: str, require_frozen_hash: bool = False, frozen_hash_value: str = "") -> tuple:
    """Single-source registry build-shape validator. Returns (parsed, findings).
    parsed = {"ordered_ids":[...], "deps":{mid:[...]}, "live_slice":{mid:bool}} or None on fatal-parse.

    Validates: row shape, module_id present, dependency_modules list, duplicates, unknown deps, cycles.
    Called from cx_module_start (order wall) and cx_packet (build-auth floor, PB-PROP-002).
    """
    findings = []
    ordered_ids = []
    deps: dict = {}
    live_slice_flags: dict = {}

    for i, m in enumerate(modules):
        if not isinstance(m, dict):
            findings.append(("P0", loc,
                f"module_registry.modules[{i}] is not a mapping — a malformed registry row would be "
                "silently dropped, vanishing a prior module from the order (V1.10 R4)"))
            return None, findings
        raw_mid = m.get("module_id", None)
        if not isinstance(raw_mid, str) or not raw_mid.strip():
            findings.append(("P0", loc,
                f"module_registry.modules[{i}] has a missing/blank/non-string module_id — every "
                "registry row must name its module so the order wall can gate it (a dropped row "
                "vanishes a prior) (V1.10 R4)"))
            return None, findings
        raw_deps = m.get("dependency_modules", []) or []
        if not isinstance(raw_deps, list):
            findings.append(("P0", loc,
                f"module_registry.modules[{i}] ('{raw_mid.strip()}') dependency_modules is not a list "
                "— malformed dependencies cannot be gated (V1.10 R4)"))
            return None, findings
        mid = raw_mid.strip()
        ordered_ids.append(mid)
        deps[mid] = [str(d).strip() for d in raw_deps]
        live_slice_flags[mid] = registry_flag_true(m.get("live_slice"))

    # Duplicate check — a duplicate lets the order wall pick the first occurrence and skip a real prior.
    dupes = sorted({x for x in ordered_ids if ordered_ids.count(x) > 1})
    if dupes:
        findings.append(("P0", loc,
            f"duplicate module_id(s) in the registry: {dupes} — a duplicate lets the order wall pick "
            "the first occurrence and skip a real prior module; module order must be unambiguous "
            "(V1.10 R4)"))
        return None, findings

    # Unknown deps — a dependency that names a module not in the registry cannot be gated.
    ordered_set = set(ordered_ids)
    unknown_deps = sorted({d for ds in deps.values() for d in ds if d and d not in ordered_set})
    if unknown_deps:
        findings.append(("P0", loc,
            f"dependency_modules reference module_id(s) not in the registry: {unknown_deps} — every "
            "dependency must be a registered module the order wall can gate (V1.10 R4)"))
        return {"ordered_ids": ordered_ids, "deps": deps, "live_slice": live_slice_flags}, findings

    # Cycle detection (Kahn's algorithm) — a cycle makes the order wall unresolvable.
    in_degree: dict = {mid: len(deps[mid]) for mid in ordered_ids}
    successors: dict = {mid: [] for mid in ordered_ids}
    for mid, dep_list in deps.items():
        for d in dep_list:
            if d in successors:
                successors[d].append(mid)
    queue = [mid for mid in ordered_ids if in_degree[mid] == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for succ in successors[node]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)
    if visited != len(ordered_ids):
        offenders = sorted(mid for mid in ordered_ids if in_degree[mid] > 0)
        findings.append(("P0", loc,
            f"dependency_modules form a cycle: {offenders} — deps must form a DAG; "
            "a cycle makes the order wall unresolvable (PB-PROP-002)"))
        return None, findings

    # Order-consistency (PB-PROP-002 P0, GPT xfam): the order wall builds in REGISTRY ORDER and treats
    # every earlier row as a required prior (cx_module_start: required_prior = deps ∪ ordered_ids[:idx]),
    # so a dependency on a SAME-or-LATER module is a guaranteed module-start deadlock even though the
    # dependency graph is itself a valid DAG. Every dependency must reference a module ordered strictly
    # EARLIER — that makes registry order a valid build order (closes the real-project "authorized-yet-
    # faceplants-at-module-start" class that Kahn alone does not catch).
    index_of = {mid: i for i, mid in enumerate(ordered_ids)}
    forward = [(mid, d) for mid in ordered_ids for d in deps[mid]
               if d in index_of and index_of[d] >= index_of[mid]]
    if forward:
        pretty = ", ".join(f"'{m}'->'{d}'" for m, d in forward)
        findings.append(("P0", loc,
            f"dependency_modules must reference a module ordered EARLIER (registry order IS the build "
            f"order): {pretty} depends on a same-or-later module — a forward/out-of-order dependency the "
            "order wall can never satisfy (PB-PROP-002)"))
        return None, findings

    return {"ordered_ids": ordered_ids, "deps": deps, "live_slice": live_slice_flags}, findings


def validate_accepted_module(module_id, state, state_loc, repo_root=None, acceptance_override=None,
                             require_live_slice=False, cards_dir=None):
    """The SINGLE source of truth for 'is module <module_id> validly accepted in <state>'.

    Returns a list of (severity, loc, message) findings — EMPTY means validly accepted.
    Used by `cx check module-acceptance` (verify ONE module) AND by `cx check module-start`'s
    order wall (verify EVERY prior required module) — the order wall NEVER trusts the
    accepted-module id set; it calls this per prior module so a hand-authored `accepted` with
    no bound receipt cannot unlock the next module (closes the model-authored-acceptance bypass).
    """
    findings = []

    entry = None
    for m in ((state.get("accepted_modules") or []) if isinstance(state, dict) else []):
        if isinstance(m, dict) and str(m.get("module_id", "")).strip() == module_id:
            entry = m
            break

    if entry is None:
        findings.append(("P0", state_loc,
            f"module '{module_id}' is not in state.accepted_modules — it has no acceptance "
            "receipt, so the next module cannot unlock (Andon wall, V1.10)"))
        return findings

    recorded_ref = str(entry.get("acceptance_ref", "") or "").strip()
    recorded_sha = str(entry.get("acceptance_sha12", "") or "").strip()

    # Resolve the receipt path: --acceptance overrides; else the recorded ref (relative to
    # repo_root if given, else the state file's own directory — mirrors cx_boot resolution).
    # The recorded acceptance_ref is MODEL-AUTHORED state, so it is path-safety checked the same way
    # cx_final_ready checks receipt refs (GPT R11 P0): an absolute path, a '..' escape, a symlink, or
    # a path resolving OUTSIDE the base would let the wall read arbitrary external bytes as a receipt.
    if acceptance_override:
        receipt_path = acceptance_override
    elif recorded_ref:
        if Path(recorded_ref).is_absolute() or ".." in Path(recorded_ref).parts:
            findings.append(("P0", state_loc,
                f"module '{module_id}' acceptance_ref '{recorded_ref}' must be a repo-relative path "
                "(no absolute path / '..' escape) — the Andon wall reads only receipts committed "
                "inside the repo (V1.10 R4)"))
            return findings
        base = Path(repo_root) if repo_root else Path(state_loc).resolve().parent
        rp = base / recorded_ref
        if rp.is_symlink() or not rp.resolve().is_relative_to(base.resolve()):
            findings.append(("P0", state_loc,
                f"module '{module_id}' acceptance_ref '{recorded_ref}' is a symlink or resolves "
                "OUTSIDE the repo — the receipt must be a real file committed inside the repo, not a "
                "pointer to arbitrary external bytes (V1.10 R4)"))
            return findings
        receipt_path = str(rp)
    else:
        receipt_path = None

    if receipt_path is None:
        findings.append(("P0", state_loc,
            f"module '{module_id}' is marked accepted in state but carries NO acceptance_ref — "
            "the acceptance receipt is the wall, not model-authored state text (Andon wall, V1.10)"))
        return findings

    receipt, rerr = load_yaml(receipt_path)
    if rerr or not isinstance(receipt, dict):
        findings.append(("P0", state_loc,
            f"module '{module_id}' acceptance receipt unreadable/missing at '{receipt_path}' — "
            f"accepted in state with no usable receipt (Andon wall, V1.10): {rerr or 'not a mapping'}"))
        return findings

    # A `module_acceptance:` block, when present, MUST be a mapping — a list/scalar block can't carry
    # the typed fields, and falling back to the bare receipt let a non-mapping block + valid top-level
    # fields slip through (GPT R12). Only a receipt with NO module_acceptance key uses the bare mapping.
    if "module_acceptance" in receipt:
        ma = nested_get(receipt, "module_acceptance")
        if not isinstance(ma, dict):
            findings.append(("P0", receipt_path,
                "acceptance receipt 'module_acceptance' is not a mapping — a list/scalar block cannot "
                "carry the typed acceptance fields (Andon wall, V1.10 R4)"))
            return findings
    else:
        ma = receipt  # allow a bare top-level mapping

    # Each field must be a STRING. str(x or "")-coercion turned [None]/dicts into non-empty strings,
    # so malformed non-scalar values satisfied the presence checks (GPT R12) — a non-string is treated
    # as ABSENT here so the non-empty checks below fail closed.
    def _sfield(key: str) -> str:
        v = ma.get(key, "")
        return v.strip() if isinstance(v, str) else ""

    r_module = _sfield("module_id")
    r_verdict = _sfield("verdict").lower()
    r_generated_by = _sfield("generated_by")
    r_state_sha = _sfield("state_sha_before")
    r_qc_hash = _sfield("quality_card_hash")

    if not r_module:
        findings.append(("P0", receipt_path,
            f"acceptance receipt has no module_id — it does not identify the module it accepts, so a "
            f"sha-bound but module-LESS receipt would 'accept' ANY module; it cannot prove module "
            f"'{module_id}' was accepted (Andon wall, V1.10 R4)"))
    elif r_module != module_id:
        findings.append(("P0", receipt_path,
            f"receipt module_id '{r_module}' != requested '{module_id}' — wrong receipt bound"))
    if r_verdict != "accepted":
        findings.append(("P0", receipt_path,
            f"acceptance receipt verdict is '{r_verdict or 'UNSET'}', not 'accepted' — the module "
            "is not CEO-accepted; the next module stays locked (Andon wall, V1.10)"))
    if not r_generated_by:
        findings.append(("P0", receipt_path,
            "acceptance receipt has empty generated_by — a MODULE-ACCEPTANCE receipt must name its "
            "machine generator (/cx-accept); a receipt with no generator is model-authored text, "
            "not a machine wall [V1.10]"))
    if not r_state_sha:
        findings.append(("P0", receipt_path,
            "acceptance receipt has empty state_sha_before — the forge-proof binding is missing "
            "(a receipt not bound to a real prior state is goodwill, not a wall) [V1.10]"))
    if not r_qc_hash:
        findings.append(("P0", receipt_path,
            "acceptance receipt has empty quality_card_hash — the forge-proof binding is missing "
            "(no quality card bound = unproven acceptance) [V1.10]"))

    # State ↔ receipt FILE hash binding (the real anti-forge clause: a swapped or hand-edited
    # recorded acceptance is rejected because the recorded sha12 will no longer match the file).
    actual_sha = _sha12(receipt_path)
    if actual_sha is None:
        findings.append(("P0", receipt_path, "acceptance receipt file unreadable for hashing"))
    elif not recorded_sha:
        findings.append(("P0", state_loc,
            f"state.accepted_modules['{module_id}'] has no acceptance_sha12 — the receipt is not "
            "bound to state; a hand-edited 'accepted' with no bound receipt is rejected (Andon wall, V1.10)"))
    elif recorded_sha != actual_sha:
        findings.append(("P0", state_loc,
            f"acceptance receipt hash mismatch: state records {recorded_sha} but the receipt file "
            f"hashes to {actual_sha} — the recorded acceptance is not bound to THIS receipt "
            "(hand-edited acceptance / swapped receipt) [V1.10]"))

    # ── BF-PROP-006: phantom-completion guard ─────────────────────────────────────────────────────
    # repo_sha_before = repo HEAD at the moment this module's build STARTED. An empty diff vs HEAD
    # means the module was 'accepted' with no real change shipped (green receipt, nothing built).
    # READ-ONLY: this only VALIDATES the recorded baseline; it never writes state or the receipt.
    # repo_root resolves the SAME way the receipt path did above (arg, else the state file's dir).
    repo_for_git = str(repo_root) if repo_root else str(Path(state_loc).resolve().parent)
    r_repo_sha = _sfield("repo_sha_before")
    if r_repo_sha == _FRESH_CLONE_TEST_SENTINEL and os.environ.get("CODE_X_TEST_MODE") == "1":
        # Fresh-clone / test-fixture good-path: no real commit graph to verify against. Skip ONLY
        # the git leg (no finding). This branch is unreachable in production (test-mode gated), so a
        # real receipt carrying the sentinel falls through to the malformed-hex P1 below. (BF-PROP-006)
        pass
    elif r_repo_sha:
        if not _HEX12_RE.match(r_repo_sha):
            findings.append(("P1", receipt_path,
                f"repo_sha_before malformed: '{r_repo_sha}' is not a hex commit of >=12 chars — the "
                "build-baseline binding is unusable, so the phantom-completion guard cannot run "
                "(BF-PROP-006)"))
        elif _git(repo_for_git, "rev-parse", "--git-dir")[0] != 0:
            # Distinct from a bad sha: there is no git repo here (or git is unavailable), so the
            # baseline simply CANNOT be verified — report that exact condition, fail closed. (BF-PROP-006)
            findings.append(("P1", receipt_path,
                f"no git repo / git unavailable at '{repo_for_git}' — cannot verify repo_sha_before "
                f"'{r_repo_sha}' against the commit graph; the phantom-completion guard cannot run "
                "(BF-PROP-006)"))
        else:
            rc_anc, _ = _git(repo_for_git, "merge-base", "--is-ancestor", r_repo_sha, "HEAD")
            if rc_anc != 0:
                findings.append(("P1", receipt_path,
                    f"repo_sha_before is not an ancestor of HEAD (baseline not in history): "
                    f"'{r_repo_sha}' is not a real commit / not reachable from HEAD in '{repo_for_git}' "
                    "— a build baseline must be a commit this branch's history actually contains "
                    "(BF-PROP-006)"))
            else:
                rc_diff, diff_out = _git(repo_for_git, "diff", "--name-only", r_repo_sha, "HEAD")
                if rc_diff == 0 and diff_out.strip() == "":
                    # risk-escalation: read risk_flags from the receipt's module_acceptance block; a
                    # money/login/auth/data/security module shipping nothing is a P0.
                    raw_flags = ma.get("risk_flags")
                    flags = {str(f).strip().lower() for f in raw_flags} if isinstance(raw_flags, list) else set()
                    sev = "P0" if flags & _HIGH_RISK_FLAGS else "P1"
                    findings.append((sev, receipt_path,
                        "module accepted with an empty diff vs repo_sha_before — no real change "
                        "shipped (phantom completion) (BF-PROP-006)"))
    else:
        carveout = _sfield("legacy_no_baseline")
        if carveout:
            findings.append(("P2", receipt_path,
                f"legacy acceptance without repo_sha_before (migration debt): {carveout} (BF-PROP-006)"))
        else:
            findings.append(("P1", receipt_path,
                "module-acceptance receipt missing repo_sha_before — the build-baseline binding "
                "needed to prove a real change shipped is absent (add it, or a typed "
                "legacy_no_baseline carve-out reason) (BF-PROP-006)"))

    # Resolve the frozen packet dir from state.packet_dir ONCE — used both by the B-PROP-008
    # live-slice block below (PB-PROP-003 Unit 2 wiring) and by the B-PROP-013 forge-parity guard
    # (every module, live_slice or not). Path-safety mirrors every other model-authored ref this
    # wall reads (resolve_in_repo — absolute/'..'/symlink/outside-repo rejected).
    packet_dir_full = None
    pkt_rel = str((state.get("packet_dir") if isinstance(state, dict) else "") or "").strip()
    if pkt_rel:
        base_for_pkt = repo_root if repo_root else str(Path(state_loc).resolve().parent)
        resolved_pkt, perr = resolve_in_repo(base_for_pkt, pkt_rel)
        if perr:
            findings.append(("P1", state_loc,
                f"state.packet_dir {perr} — cannot resolve the frozen packet for the PB-PROP-003 "
                "acceptance-stage wiring checks (fails closed rather than skipping them silently)"))
        else:
            packet_dir_full = str(resolved_pkt)

    # ── B-PROP-008: live-slice CEO live-drive accept ──────────────────────────────────────────────
    # require_live_slice is set by the order wall (cx check module-start) from the FROZEN registry's
    # live_slice flag — so a live_slice prior with no valid live_slice_accept block is NOT validly
    # accepted → the next slice cannot start (P0). The registry is the trusted source, never the
    # receipt's self-declaration.
    if require_live_slice:
        # PBF-PROP-012 Part E: pass repo_root as base so validate_module_demo can resolve
        # shown_screenshot_path and ceo_turn_ref (screenshot + turn artifact must be in-repo).
        base_for_demo = repo_root if repo_root else str(Path(receipt_path).resolve().parent)
        findings.extend(validate_live_slice_accept(ma, receipt_path, base=base_for_demo,
                                                    packet_dir=packet_dir_full, module_id=module_id))

    # ── B-PROP-013: forge-parity acceptance recompute (Unit 1 GUARD) ────────────────────────────────
    # Runs for EVERY module (live_slice or not) — gated internally on the §4 activation marker so a
    # legacy packet (marker absent) is unaffected. repo_for_git is the SAME resolved repo root the
    # BF-PROP-006 phantom-completion guard above already uses. FIX-FIRST: thread whether state
    # carries module_registry_ref (cx_build_turn.py's own "this is a module-advancing/packet-bound
    # build" signal) so forge_parity_findings can tell a genuinely packet-less legacy state apart
    # from an anomalous one that should have had packet_dir but doesn't (P2 advisory, never P0/P1).
    _reg_ref = str((state.get("module_registry_ref") if isinstance(state, dict) else "") or "").strip()
    findings.extend(forge_parity_findings(ma, receipt_path, packet_dir_full, repo_for_git,
                                          state_has_module_registry_ref=bool(_reg_ref)))

    # ── BF-PROP-007 Lever B/C: an OPEN lock_deviation row blocks module-acceptance ──────────────────
    # A logged AMBIGUITY/scope deviation surfaced at the Andon wall must be CEO_REVIEWED before the
    # module is accepted — logged ambiguity can never quietly ship. Honest scope: a deviation row
    # carries card_id (not module_id), so EVERY OPEN row blocks the wall (conservative fail-closed);
    # a row already CEO_REVIEWED does not block.
    from cx_drift import open_lock_deviation_blockers
    findings.extend(open_lock_deviation_blockers(state, state_loc, "module-acceptance"))

    # ── BF-PROP-007 xfam F7: module-acceptance fails closed on Layer-1 drift ─────────────────────────
    # An OPEN lock_deviation is not the only way scope can drift; a working-set card can reference a
    # requirement_id NOT in the frozen manifest, a BUILDING requirement can be silently dropped, or a
    # fix card can over-reach its anchored allowed_files — all DETERMINISTIC Layer-1 divergences. The
    # Andon wall must re-run the drift Layer-1 validator (the SAME logic cx check drift uses) so a
    # module cannot be accepted while Layer-1 drift exists. Gated on cards_dir so it runs ONLY in the
    # direct command path (cmd_module_acceptance) — the order wall's per-prior calls and the F4 open-card
    # recompute pass NO cards_dir, which both avoids an infinite recompute recursion and keeps the wall's
    # prior-module checks about acceptance receipts, not deck drift.
    if cards_dir is not None and repo_root:
        from cx_drift import compute_layer1_findings
        cdir = Path(cards_dir)
        if not cdir.is_dir():
            findings.append(("P1", state_loc,
                f"module-acceptance cannot prove no Layer-1 drift: cards-dir '{cards_dir}' is not a "
                "directory — the Andon wall fails closed when the live deck cannot be read to re-run "
                "drift (BF-PROP-007 Lever C / F7)"))
        else:
            packet_dir_rel = str(state.get("packet_dir", "") or "").strip()
            l1, _l2, fatal = compute_layer1_findings(repo_root, packet_dir_rel, state, cdir, state_loc)
            if fatal:
                findings.append(("P1", state_loc,
                    f"module-acceptance cannot prove no Layer-1 drift — {fatal} (BF-PROP-007 Lever C / F7)"))
            else:
                findings.extend(l1)

    # ── F-PROP-001 Lever A: module-acceptance fails closed on STRUCTURAL drift ──────────────────────
    # The Andon wall also re-runs the structure Layer-1 validator over every mode: FIX card in the live
    # deck (the SAME logic cx check structure uses), so a module cannot be accepted while a fix has
    # restructured the file tree outside its allowed_files, or carries a forged / self-declared /
    # path-unsafe structure_lock. Same cards_dir gating as the drift block above (direct command path
    # only — avoids recursion on the order wall's per-prior calls).
    if cards_dir is not None and repo_root:
        from cx_structure import compute_structure_findings
        sfindings, sfatal = compute_structure_findings(repo_root, Path(cards_dir))
        if sfatal:
            findings.append(("P1", state_loc,
                f"module-acceptance cannot prove no structural drift — {sfatal} (F-PROP-001 Lever A)"))
        else:
            findings.extend(sfindings)

    return findings


def cmd_module_acceptance(args) -> int:
    module_id = str(getattr(args, "module_id", "") or "").strip()
    state_path = getattr(args, "state", None)
    acceptance_path = getattr(args, "acceptance", None)
    repo_root = getattr(args, "repo_root", None)

    if not module_id:
        print("FIX-FIRST\n  [P0] --module-id required for cx check module-acceptance")
        return 1
    if not state_path:
        print("FIX-FIRST\n  [P0] --state required for cx check module-acceptance")
        return 1

    state, serr = load_yaml(state_path)
    if serr:
        print(f"FIX-FIRST\n  [P0] {state_path} — {serr}")
        return 1

    # BF-PROP-007 F7: the Andon wall re-runs the drift Layer-1 validator over the live deck. An EXPLICIT
    # --cards-dir always runs the gate (fail-closed if that dir is unreadable). With no --cards-dir we
    # auto-discover <repo-root>/cards and run the gate ONLY when that conventional deck dir actually
    # exists — so a project without an in-repo deck (or a receipt-only check) is not forced to fail
    # closed on a dir that was never part of its layout, while a project WITH a deck cannot accept a
    # module that has Layer-1 drift.
    cards_dir = getattr(args, "cards_dir", None)
    if cards_dir is None and repo_root:
        conventional = Path(repo_root) / "cards"
        if conventional.is_dir():
            cards_dir = str(conventional)

    findings = validate_accepted_module(
        module_id, state, state_path, repo_root=repo_root, acceptance_override=acceptance_path,
        cards_dir=cards_dir)

    if not findings:
        print("PASS")
        print(f"  [INFO] module '{module_id}' accepted — receipt bound to state by sha12, "
              "verdict accepted, generator stamped")
        return 0
    # Print every finding, but a findings set with ONLY advisories (P2/P3) is non-blocking:
    # the module is validly accepted WITH migration debt (locked spec — legacy_no_baseline carve-out).
    rc = findings_report(findings)
    return rc if has_blocking(findings) else 0


def cmd_verify_app(args) -> int:
    """B-PROP-010: validate a verify_app receipt block standalone. The build-turn runs this when a
    live_slice slice completes — after the verify-app agent drives the running build, before the CEO
    live-drive — so a malformed/forged/failing verify_app receipt is caught at slice completion, not
    only later at the Andon wall. Reuses validate_verify_app (single source of truth with the
    precondition enforced inside validate_live_slice_accept). READ-ONLY: never runs the app itself.

    PB-PROP-003 Unit 2: --packet-dir (optional) enables the criteria_refs wiring/resolution check;
    --module-id (optional, needs --packet-dir too) additionally enables the registry-enumerated
    reverse-coverage check. Both omitted preserves the pre-existing standalone behavior exactly."""
    acceptance_path = getattr(args, "acceptance", None)
    packet_dir = getattr(args, "packet_dir", None)
    module_id = str(getattr(args, "module_id", "") or "").strip()
    if not acceptance_path:
        print("FIX-FIRST\n  [P0] --acceptance required for cx check verify-app")
        return 1
    receipt, rerr = load_yaml(acceptance_path)
    if rerr or not isinstance(receipt, dict):
        print(f"FIX-FIRST\n  [P0] {acceptance_path} — {rerr or 'not a mapping'}")
        return 1
    if "module_acceptance" in receipt:
        ma = nested_get(receipt, "module_acceptance")
        if not isinstance(ma, dict):
            print("FIX-FIRST\n  [P0] acceptance receipt 'module_acceptance' is not a mapping — it "
                  "cannot carry the typed verify_app block (B-PROP-010)")
            return 1
    else:
        ma = receipt
    findings = validate_verify_app(ma, acceptance_path, packet_dir=packet_dir)
    if module_id and packet_dir:
        findings.extend(_reverse_coverage_findings(ma, acceptance_path, packet_dir, module_id))
    if not findings:
        print("PASS")
        print("  [INFO] verify_app receipt present, generator-stamped, repo_sha hex-shaped (recorded, "
              "not freshness-verified), passed:true — the verify-app agent drove the running build and "
              "its acceptance-criteria check passed")
        return 0
    # PB-PROP-003 §R5: a findings set with ONLY advisories (P2/P3 — e.g. legacy_criteria_ref
    # migration debt) is non-blocking, mirroring cmd_module_acceptance's has_blocking() gate — the
    # standalone command must not turn a genuine non-blocking carve-out into a hard FIX-FIRST.
    rc = findings_report(findings)
    return rc if has_blocking(findings) else 0


def cmd_module_demo(args) -> int:
    """PBF-PROP-012 Part E: validate a module_demo receipt block standalone. The build-turn runs this
    when a live_slice slice completes — after the demo collector captures the shown screenshot and
    the CEO types their accept token — so a malformed/forged/unbound demo block is caught at slice
    completion, not only later at the Andon wall. Reuses validate_module_demo (single source of
    truth with the precondition enforced inside validate_live_slice_accept). READ-ONLY: never runs
    the app or opens Chrome/simulator itself.

    HONEST LIMIT: E proves a real build was rendered on the correct surface, the exact screenshot
    bytes are hash-bound, and the CEO-typed token resolves to a real turn artifact — it cannot
    prove the CEO's eyes were on the screen or that the token was typed by the CEO rather than
    transcribed by the orchestrator; that the human saw it and drove it remains human-attested."""
    acceptance_path = getattr(args, "acceptance", None)
    repo_root = getattr(args, "repo_root", None)
    if not acceptance_path:
        print("FIX-FIRST\n  [P0] --acceptance required for cx check module-demo")
        return 1
    receipt, rerr = load_yaml(acceptance_path)
    if rerr or not isinstance(receipt, dict):
        print(f"FIX-FIRST\n  [P0] {acceptance_path} — {rerr or 'not a mapping'}")
        return 1
    if "module_acceptance" in receipt:
        ma = nested_get(receipt, "module_acceptance")
        if not isinstance(ma, dict):
            print("FIX-FIRST\n  [P0] acceptance receipt 'module_acceptance' is not a mapping — it "
                  "cannot carry the typed module_demo block (PBF-PROP-012 Part E)")
            return 1
    else:
        ma = receipt
    base = repo_root if repo_root else str(Path(acceptance_path).resolve().parent)
    findings = validate_module_demo(ma, acceptance_path, base)
    if not findings:
        print("PASS")
        print("  [INFO] module_demo block present, generator-stamped, surface-appropriate evidence, "
              "screenshot bytes hash-bound (shown == real file), CEO-typed accept token resolves to "
              "a real turn artifact, ceo_verdict: accepted — the SEE-AND-TEST show-step is "
              "well-formed (PBF-PROP-012 Part E)")
        return 0
    return findings_report(findings)
