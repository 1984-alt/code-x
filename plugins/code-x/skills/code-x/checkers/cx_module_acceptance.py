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

# PROP-028: phantom-completion guard. A module accepted whose build baseline (repo_sha_before)
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


# PROP-032 (Live Slice Delivery): a live_slice module (a user-facing PAGE slice, flagged in the
# FROZEN registry) must carry a typed live_slice_accept block proving the CEO DROVE the running
# build live on the Mac — not a Mode A screenshot/shell accept or a module-level batch. Presence +
# shape ONLY: the checker proves the running build existed (live_url) and the CEO recorded driving
# it; whether it FELT right stays the CEO's accept (no over-claiming the experience — the cardinal sin).
_LIVE_SLICE_ACCEPT_STRING_FIELDS = ("live_url", "ceo_turn_ref", "repo_sha")


def registry_flag_true(v) -> bool:
    """A frozen-registry boolean flag (live_slice / walking_skeleton) is True ONLY for a real boolean
    True or an explicit 'true'/'yes' string — NOT a truthy-coerced bool('false')==True (built-code
    review P2: a quoted live_slice: 'false' must not fire the live-drive gate on an honest build)."""
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes"))


def validate_live_slice_accept(ma, receipt_loc):
    """Validate the live_slice_accept block on a live_slice module's acceptance receipt. Returns a
    list of P0 findings — EMPTY means the CEO live-drive accept is well-formed. Shared by the order
    wall (via validate_accepted_module's require_live_slice path) and cx check module-quality (PROP-032)."""
    lsa = ma.get("live_slice_accept") if isinstance(ma, dict) else None
    if not isinstance(lsa, dict):
        return [("P0", receipt_loc,
            "live_slice module accepted with NO typed live_slice_accept block "
            "{live_url, ceo_drove, ceo_turn_ref, repo_sha} — a Mode A screenshot/shell accept or a "
            "module-level batch is not proof the CEO DROVE the running build live on the Mac (PROP-032)")]
    findings = []

    def _s(key):
        v = lsa.get(key, "")
        return v.strip() if isinstance(v, str) else ""  # a non-string is treated as ABSENT (fail closed)

    missing = [k for k in _LIVE_SLICE_ACCEPT_STRING_FIELDS if not _s(k)]
    if missing:
        findings.append(("P0", receipt_loc,
            f"live_slice_accept missing/blank {missing} — live_url (the running build the CEO opened) "
            "+ ceo_turn_ref + repo_sha must each be a non-empty string (PROP-032)"))
    drove = lsa.get("ceo_drove")
    if drove is not True and str(drove).strip().lower() not in ("true", "yes"):
        findings.append(("P0", receipt_loc,
            "live_slice_accept.ceo_drove is not true — the CEO must record DRIVING the running build "
            "live (not just seeing a screenshot); without it the live-drive gate is goodwill (PROP-032)"))
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

    # ── PROP-028: phantom-completion guard ─────────────────────────────────────────────────────
    # repo_sha_before = repo HEAD at the moment this module's build STARTED. An empty diff vs HEAD
    # means the module was 'accepted' with no real change shipped (green receipt, nothing built).
    # READ-ONLY: this only VALIDATES the recorded baseline; it never writes state or the receipt.
    # repo_root resolves the SAME way the receipt path did above (arg, else the state file's dir).
    repo_for_git = str(repo_root) if repo_root else str(Path(state_loc).resolve().parent)
    r_repo_sha = _sfield("repo_sha_before")
    if r_repo_sha == _FRESH_CLONE_TEST_SENTINEL and os.environ.get("CODE_X_TEST_MODE") == "1":
        # Fresh-clone / test-fixture good-path: no real commit graph to verify against. Skip ONLY
        # the git leg (no finding). This branch is unreachable in production (test-mode gated), so a
        # real receipt carrying the sentinel falls through to the malformed-hex P1 below. (PROP-028)
        pass
    elif r_repo_sha:
        if not _HEX12_RE.match(r_repo_sha):
            findings.append(("P1", receipt_path,
                f"repo_sha_before malformed: '{r_repo_sha}' is not a hex commit of >=12 chars — the "
                "build-baseline binding is unusable, so the phantom-completion guard cannot run "
                "(PROP-028)"))
        elif _git(repo_for_git, "rev-parse", "--git-dir")[0] != 0:
            # Distinct from a bad sha: there is no git repo here (or git is unavailable), so the
            # baseline simply CANNOT be verified — report that exact condition, fail closed. (PROP-028)
            findings.append(("P1", receipt_path,
                f"no git repo / git unavailable at '{repo_for_git}' — cannot verify repo_sha_before "
                f"'{r_repo_sha}' against the commit graph; the phantom-completion guard cannot run "
                "(PROP-028)"))
        else:
            rc_anc, _ = _git(repo_for_git, "merge-base", "--is-ancestor", r_repo_sha, "HEAD")
            if rc_anc != 0:
                findings.append(("P1", receipt_path,
                    f"repo_sha_before is not an ancestor of HEAD (baseline not in history): "
                    f"'{r_repo_sha}' is not a real commit / not reachable from HEAD in '{repo_for_git}' "
                    "— a build baseline must be a commit this branch's history actually contains "
                    "(PROP-028)"))
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
                        "shipped (phantom completion) (PROP-028)"))
    else:
        carveout = _sfield("legacy_no_baseline")
        if carveout:
            findings.append(("P2", receipt_path,
                f"legacy acceptance without repo_sha_before (migration debt): {carveout} (PROP-028)"))
        else:
            findings.append(("P1", receipt_path,
                "module-acceptance receipt missing repo_sha_before — the build-baseline binding "
                "needed to prove a real change shipped is absent (add it, or a typed "
                "legacy_no_baseline carve-out reason) (PROP-028)"))

    # ── PROP-032: live-slice CEO live-drive accept ──────────────────────────────────────────────
    # require_live_slice is set by the order wall (cx check module-start) from the FROZEN registry's
    # live_slice flag — so a live_slice prior with no valid live_slice_accept block is NOT validly
    # accepted → the next slice cannot start (P0). The registry is the trusted source, never the
    # receipt's self-declaration.
    if require_live_slice:
        findings.extend(validate_live_slice_accept(ma, receipt_path))

    # ── PROP-034 Lever B/C: an OPEN lock_deviation row blocks module-acceptance ──────────────────
    # A logged AMBIGUITY/scope deviation surfaced at the Andon wall must be CEO_REVIEWED before the
    # module is accepted — logged ambiguity can never quietly ship. Honest scope: a deviation row
    # carries card_id (not module_id), so EVERY OPEN row blocks the wall (conservative fail-closed);
    # a row already CEO_REVIEWED does not block.
    from cx_drift import open_lock_deviation_blockers
    findings.extend(open_lock_deviation_blockers(state, state_loc, "module-acceptance"))

    # ── PROP-034 xfam F7: module-acceptance fails closed on Layer-1 drift ─────────────────────────
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
                "drift (PROP-034 Lever C / F7)"))
        else:
            packet_dir_rel = str(state.get("packet_dir", "") or "").strip()
            l1, _l2, fatal = compute_layer1_findings(repo_root, packet_dir_rel, state, cdir, state_loc)
            if fatal:
                findings.append(("P1", state_loc,
                    f"module-acceptance cannot prove no Layer-1 drift — {fatal} (PROP-034 Lever C / F7)"))
            else:
                findings.extend(l1)

    # ── PROP-035 Lever A: module-acceptance fails closed on STRUCTURAL drift ──────────────────────
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
                f"module-acceptance cannot prove no structural drift — {sfatal} (PROP-035 Lever A)"))
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

    # PROP-034 F7: the Andon wall re-runs the drift Layer-1 validator over the live deck. An EXPLICIT
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
