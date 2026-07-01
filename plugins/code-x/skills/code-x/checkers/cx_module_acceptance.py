# cmd_module_acceptance: the ANDON WALL (V1.10 module_acceptance gate family).
#
# Module N+1 cannot unlock until module N carries a MODULE-ACCEPTANCE receipt that is:
#   1. present and readable (a hand-edited `accepted` in state with no receipt is rejected),
#   1b. identifies its module — non-empty module_id EXACTLY equal to the requested module (a
#       sha-bound but module-LESS receipt would 'accept' ANY module; V1.10 R4, GPT R10),
#   2. verdict == accepted,
#   3. generator-stamped — non-empty generated_by (the receipt names its generator; /cx-accept once
#      that runner exists — enforced as non-empty TODAY; a receipt with no generator is bare text),
#   4. binding-fields present — non-empty state_sha_before + quality_card_hash, and
#   5. bound to state by sha — state.accepted_modules[module_id].acceptance_sha12 must equal the
#      receipt file's sha12 (swapping / hand-editing the recorded acceptance is rejected).
#
# HONEST SCOPE (V1.10, deferred-runner era): the receipt FILE is genuinely sha12-bound to state
# (clause 5) — a swapped or hand-edited recorded acceptance is rejected. The receipt's INTERNAL
# claims (state_sha_before, quality_card_hash) are PRESENCE-asserted today (clause 4) + the receipt
# must name its generator (clause 3). Full forge-parity with `cx check boot` (RECOMPUTING the prior
# state sha + hashing the quality-card artifact + binding repo head) lands when `/cx-accept` is built
# (CHARTER §4 forbids a full runner until V1 proves on 2-3 projects). Tracked as acceptance-binding debt.
#
#   cx check module-acceptance --module-id <id> --state <CODE-X-STATE.yaml> \
#       [--acceptance <MODULE-ACCEPTANCE.yaml>] [--repo-root <dir>]
#
# READ-ONLY: never builds, routes actors, edits source, or generates the receipt (that is /cx-accept).
import hashlib
import os
import re
import subprocess
from pathlib import Path

from cx_common import findings_report, load_yaml, nested_get

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
# build live on the local machine — not a Mode A screenshot/shell accept or a module-level batch. Presence +
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


def validate_live_slice_accept(ma, receipt_loc, base=None):
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
    screenshot path-safety resolution."""
    va_findings = validate_verify_app(ma, receipt_loc)
    demo_findings = validate_module_demo(ma, receipt_loc, base)   # PBF-PROP-012 Part E precondition
    lsa = ma.get("live_slice_accept") if isinstance(ma, dict) else None
    if not isinstance(lsa, dict):
        return va_findings + demo_findings + [("P0", receipt_loc,
            "live_slice module accepted with NO typed live_slice_accept block "
            "{live_url, ceo_drove, ceo_turn_ref, repo_sha} — a Mode A screenshot/shell accept or a "
            "module-level batch is not proof the CEO DROVE the running build live on the local machine (B-PROP-008)")]
    findings = list(va_findings) + list(demo_findings)

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
_VERIFY_APP_STRING_FIELDS = ("repo_sha", "generated_by", "criteria_ref")


def validate_verify_app(ma, receipt_loc):
    """Validate the verify_app block on a live_slice module's acceptance receipt (B-PROP-010). Returns a
    list of findings — EMPTY means the verify-app runtime gate passed. Called from
    validate_live_slice_accept so the order wall AND cx check module-quality enforce it at the SAME
    chokepoint as the CEO live-drive accept, making a passing verify_app a precondition to acceptance."""
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
            "in a hex-shaped field) + generated_by (the verify-app runner, machine-stamped) + criteria_ref "
            "(where the checked acceptance criteria came from) must each be a non-empty string; a verify_app "
            "block with no recorded binding is model-authored text, not a runtime gate (B-PROP-010)"))
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
    # EARLIER — that makes registry order a valid build order (closes a real project's "authorized-yet-
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

    # ── B-PROP-008: live-slice CEO live-drive accept ──────────────────────────────────────────────
    # require_live_slice is set by the order wall (cx check module-start) from the FROZEN registry's
    # live_slice flag — so a live_slice prior with no valid live_slice_accept block is NOT validly
    # accepted → the next slice cannot start (P0). The registry is the trusted source, never the
    # receipt's self-declaration.
    if require_live_slice:
        # PBF-PROP-012 Part E: pass repo_root as base so validate_module_demo can resolve
        # shown_screenshot_path and ceo_turn_ref (screenshot + turn artifact must be in-repo).
        base_for_demo = repo_root if repo_root else str(Path(receipt_path).resolve().parent)
        findings.extend(validate_live_slice_accept(ma, receipt_path, base=base_for_demo))

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
    precondition enforced inside validate_live_slice_accept). READ-ONLY: never runs the app itself."""
    acceptance_path = getattr(args, "acceptance", None)
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
    findings = validate_verify_app(ma, acceptance_path)
    if not findings:
        print("PASS")
        print("  [INFO] verify_app receipt present, generator-stamped, repo_sha hex-shaped (recorded, "
              "not freshness-verified), passed:true — the verify-app agent drove the running build and "
              "its acceptance-criteria check passed")
        return 0
    return findings_report(findings)


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
