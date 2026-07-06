# cmd_state: validates a Code-X V1 CODE-X-STATE.yaml file.
#
# Optional --session-start mode adds git-continuity checks:
#   --session-start   enable session-start continuity checks
#   --repo-root DIR   path to the git repo root (required when --session-start given)
#
# Additional state schema block (optional; only checked in --session-start mode):
#
#   wip_continuation:
#     marked: yes           # must be present + "yes" to silence dirty-tree P1
#     owner_card: BUILD-007 # required when marked: yes
#     handoff_ref: handoffs/...  # required when marked: yes
#
# The block being absent is fine when the working tree is clean.
import copy
import hashlib
import subprocess
from pathlib import Path

import yaml

from cx_common import (
    findings_report, load_yaml, nested_get, field_present,
    VALID_BUILD_ENGINES, ENGINE_BRANCH_KEYS,
    CLAUDE_MODEL_RANK, GPT_MODEL_RANK, EFFORT_RANK,
    resolve_profiles_path, parse_model_effort, profiles_sha12,
    resolve_risk_tier,
)

# Build modes whose sessions must acknowledge BUILDER-STANDARD.md at session start
# (P-PROP-001: session-level read law — ack proves WHICH version, not internalization).
BUILD_MODES = {"MODE_A_UI", "MODULE_BUILD", "FIX"}

# B-PROP-002: the canonical files cx check boot hashes into the boot receipt.
# Resolved relative to the Code-X-V1 root (one level up from checkers/), like
# DEFAULT_PROFILES_PATH — the canon travels with the cx binary, not the project repo.
CANON_ROOT = Path(__file__).resolve().parent.parent
BOOT_CANON_FILES = ["START-HERE.md", "KERNEL.md", "GATES.md", "BUILDER-STANDARD.md"]

# BF-PROP-002: review_boundary enums (partial prose rejected — required enums only).
VALID_CODERABBIT_BOUNDARY = {"yes", "no", "not_applicable"}
VALID_SELF_REVIEW_BOUNDARY = {"card", "module", "foundation_checkpoint", "final"}
VALID_CROSS_FAMILY_BOUNDARY = {"module", "foundation_checkpoint", "final", "ceo_deferred"}
# BF-PROP-005: the 3-stage cross-family review ladder a project/CEO declares (the protocol
# cannot auto-detect how many model families a user has). stage_1 = 1 CLI (CodeRabbit
# unblocks the build, a true opposite-family pass is required before ship); stage_3 = 2 CLIs.
VALID_XFAM_CAPABILITY = {"stage_1", "stage_2", "stage_3"}
VALID_DEVIATION_BLOCKS = {"next_card", "ship", "final_ready", "none"}
VALID_INCIDENT_STATUS = {"OPEN", "REPAIRED"}

# Stage whose sessions must acknowledge the lessons preload at session start
# (PBF-PROP-010: planning-sessions-only — the build read path is untouched).
PLANNING_STAGE = "PLANNING_STUDIO"


def _check_session_ack(data: dict, repo_root: str, loc: str, findings: list,
                       ack_key: str, what: str, requirement: str) -> None:
    """Shared session_start ack check (P-PROP-001 · PBF-PROP-010): status PASS + file + hash,
    plus best-effort drift detection against the live file under repo_root."""
    ack = nested_get(data, "session_start", ack_key)
    if (not isinstance(ack, dict) or str(ack.get("status", "")) != "PASS"
            or not ack.get("file") or not ack.get("hash")):
        findings.append(("P2", loc,
            f"session_start.{ack_key} missing or not PASS (status+file+hash) — {requirement}"))
        return
    target = Path(repo_root) / str(ack.get("file"))
    if target.is_file():
        live = profiles_sha12(str(target))
        if live and str(ack.get("hash")) != live:
            findings.append(("P2", loc,
                f"{what} drifted since acknowledgment — recorded hash "
                f"'{ack.get('hash')}' != live '{live}' for {ack.get('file')}; "
                "re-read and re-acknowledge"))


def _check_orchestration_mode(data: dict, loc: str, findings: list) -> None:
    """PBF-PROP-012 Part B (R-ORCH): a BUILD/FIXING session must declare it runs as an
    ORCHESTRATOR that dispatches a fresh, specialized subagent per build/review task —
    the lead never builds or self-reviews inline. This is the model-agnostic delivery
    rail for the fresh-subagent review pipeline (the orchestrator is what injects the
    builder prevention preamble + the post-build review legs). A trivial single-card
    project may instead carry a typed inline_waiver + ceo_decision_ref. P2 (mirrors the
    builder-standard / lessons-preload acks). [RULE:orchestration-mode-ack]"""
    om = nested_get(data, "session_start", "orchestration_mode")
    if not isinstance(om, dict):
        findings.append(("P2", loc,
            "session_start.orchestration_mode missing — a BUILD/FIXING session must declare "
            "dispatch_subagents: yes + lead_role: orchestrator (or a typed inline_waiver + ceo_decision_ref)"))
        return
    if om.get("inline_waiver"):
        # P1-003→P2: inline_waiver requires ceo_decision_ref + scope: single_card + card_ref
        # so a multi-card build cannot blanket-waive orchestration dispatch.
        if not om.get("ceo_decision_ref"):
            findings.append(("P2", loc,
                "orchestration_mode.inline_waiver set without ceo_decision_ref — an inline "
                "(no-dispatch) build needs a typed CEO waiver"))
        if str(om.get("scope", "")).strip().lower() != "single_card":
            findings.append(("P2", loc,
                "orchestration_mode.inline_waiver requires scope: single_card — "
                "only a single-card build may waive orchestration dispatch (P1-003)"))
        if not str(om.get("card_ref", "")).strip():
            findings.append(("P2", loc,
                "orchestration_mode.inline_waiver requires card_ref — "
                "name the single card being built inline (P1-003)"))
        return
    if (str(om.get("dispatch_subagents", "")).lower() != "yes"
            or str(om.get("lead_role", "")).lower() != "orchestrator"):
        findings.append(("P2", loc,
            "orchestration_mode must declare dispatch_subagents: yes + lead_role: orchestrator "
            "(or a typed inline_waiver + ceo_decision_ref)"))


def _check_module_demo_mode(data: dict, loc: str, findings: list) -> None:
    """PBF-PROP-012 Part E (SEE-AND-TEST): a BUILD/FIXING session must declare it will DEMO every
    user-facing module on its real surface (web→Chrome, mobile→iPhone 13 Pro sim) and capture a
    real shown-screenshot before offering the CEO live-drive accept. The model-agnostic rail that
    forces the show-step real-project skipped. A project with NO user-facing modules may carry a typed
    no_user_facing_modules waiver + ceo_decision_ref. P2 (mirrors the orchestration-mode ack).
    [RULE:module-demo-mode-ack]"""
    md = nested_get(data, "session_start", "module_demo_mode")
    if not isinstance(md, dict):
        findings.append(("P2", loc,
            "session_start.module_demo_mode missing — a BUILD/FIXING session must declare "
            "demo_every_user_facing_module: yes + surfaces: [web|mobile] (or a typed "
            "no_user_facing_modules waiver + ceo_decision_ref) (PBF-PROP-012 Part E)"))
        return
    if md.get("no_user_facing_modules"):
        if not md.get("ceo_decision_ref"):
            findings.append(("P2", loc,
                "module_demo_mode.no_user_facing_modules set without ceo_decision_ref — a "
                "backend-only build needs a typed CEO waiver (PBF-PROP-012 Part E)"))
        return
    if str(md.get("demo_every_user_facing_module", "")).lower() != "yes":
        findings.append(("P2", loc,
            "module_demo_mode must declare demo_every_user_facing_module: yes "
            "(or a typed no_user_facing_modules waiver + ceo_decision_ref) (PBF-PROP-012 Part E)"))


def state_sha12_without_boot_ack(path: str) -> str | None:
    """Canonical sha12 of the state file with session_start.protocol_boot_ack removed —
    the binding that makes a boot receipt verifiable against the CURRENT state (the
    ack itself is excluded so acknowledging the receipt doesn't invalidate it).
    Shared by cx check boot (writer) and _check_boot_ack (verifier)."""
    data, err = load_yaml(path)
    if err or not isinstance(data, dict):
        return None
    data = copy.deepcopy(data)
    ss = data.get("session_start")
    if isinstance(ss, dict):
        ss.pop("protocol_boot_ack", None)
    canonical = yaml.safe_dump(data, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _check_boot_ack(data: dict, repo_root: str, loc: str, findings: list) -> None:
    """B-PROP-002: a BUILD-mode session references the MACHINE-GENERATED boot receipt
    (cx check boot) in session_start.protocol_boot_ack — the model never authors
    hashes. Stale receipt (canon drifted, tampered file, failed state check) = P1."""
    ack = nested_get(data, "session_start", "protocol_boot_ack")
    if (not isinstance(ack, dict) or not ack.get("receipt")
            or not ack.get("receipt_hash")):
        findings.append(("P1", loc,
            "session_start.protocol_boot_ack missing receipt+receipt_hash — a BUILD-mode "
            "session must run `cx check boot` and reference the generated receipt "
            "(no file edits, reviews, or builds before the boot check passes)"))
        return
    receipt_path = Path(repo_root) / str(ack.get("receipt"))
    if not receipt_path.is_file():
        findings.append(("P1", loc,
            f"protocol_boot_ack.receipt not found: {ack.get('receipt')} — re-run cx check boot"))
        return
    live_hash = profiles_sha12(str(receipt_path))
    if live_hash != str(ack.get("receipt_hash")):
        findings.append(("P1", loc,
            f"protocol_boot_ack.receipt_hash '{ack.get('receipt_hash')}' != live receipt "
            f"hash '{live_hash}' — receipt changed after acknowledgment; re-run cx check boot"))
        return
    receipt, rerr = load_yaml(str(receipt_path))
    receipt = (receipt or {}).get("protocol_boot_receipt") if isinstance(receipt, dict) else None
    if rerr or not isinstance(receipt, dict):
        findings.append(("P1", loc,
            f"boot receipt unreadable or not a protocol_boot_receipt mapping: {ack.get('receipt')}"))
        return
    if str(receipt.get("state_check_result", "")) != "PASS":
        findings.append(("P1", loc,
            "boot receipt records a FAILED state check — fix the state and re-run cx check boot"))
    # Anti-forgery binding (GPT cross-review 2026-06-12): a receipt must be equivalent
    # to having RUN cx check boot against THIS state at THIS point in history —
    # generated_by + bounded path + state-minus-ack sha + HEAD binding all verified.
    if str(receipt.get("generated_by", "")) != "cx check boot":
        findings.append(("P1", loc,
            "boot receipt generated_by is not 'cx check boot' — receipts are machine-"
            "generated only, never model-authored"))
    receipt_resolved = receipt_path.resolve()
    state_dir = Path(loc).resolve().parent
    repo_resolved = Path(repo_root).resolve()
    if not (str(receipt_resolved).startswith(str(state_dir) + "/")
            or str(receipt_resolved).startswith(str(repo_resolved) + "/")):
        findings.append(("P1", loc,
            f"boot receipt lives outside the state dir and repo root: {receipt_resolved}"))
    live_state_sha = state_sha12_without_boot_ack(loc)
    if live_state_sha and str(receipt.get("state_sha12", "")) != live_state_sha:
        findings.append(("P1", loc,
            "state changed since boot — receipt state_sha12 "
            f"'{receipt.get('state_sha12')}' != live '{live_state_sha}' (state minus the "
            "ack block); re-run cx check boot"))
    rc_head, head_out = _git(repo_root, "rev-parse", "HEAD")
    live_head = head_out if rc_head == 0 else "NONE"
    if str(receipt.get("repo_head", "")) != live_head:
        findings.append(("P1", loc,
            "repo HEAD moved since boot — receipt repo_head "
            f"'{receipt.get('repo_head')}' != live '{live_head}'; re-run cx check boot "
            "at session start"))
    hashed = {str(e.get("path")): str(e.get("sha12"))
              for e in (receipt.get("canon") or []) if isinstance(e, dict)}
    for name in BOOT_CANON_FILES:
        if name not in hashed:
            findings.append(("P1", loc,
                f"boot receipt does not hash canonical file {name} — not a cx-generated receipt"))
            continue
        live = profiles_sha12(str(CANON_ROOT / name))
        if live and hashed[name] != live:
            findings.append(("P1", loc,
                f"canon drifted since boot — receipt sha12 '{hashed[name]}' != live "
                f"'{live}' for {name}; re-read the canon and re-run cx check boot"))


def _check_review_boundary(data: dict, loc: str, findings: list,
                           require_block: bool = False, risk_tier_val: str = "STRICT") -> None:
    """BF-PROP-002: reviewer taxonomy/timing is STATE, not prose — required enums,
    partial prose rejected. Block presence enforced at session-start in BUILD modes.

    PBF-PROP-019 P2 FIX: `coderabbit_before_self_review: yes` is now tier-aware — LITE
    projects legitimately skip CodeRabbit (cx_card.py:419, cx_build_turn.py:251 already relax
    this), so forcing the flag here on every LITE project was integration drift: a LITE
    project was forced to either carry an inaccurate 'yes' or fail state check for a rail it
    correctly never runs. STANDARD/STRICT are unchanged (default STRICT, fail-closed)."""
    rb = data.get("review_boundary")
    if not isinstance(rb, dict):
        if require_block:
            findings.append(("P1", loc,
                "review_boundary block missing — a build session must declare reviewer "
                "taxonomy/timing as typed state (BF-PROP-002), never as prose"))
        return
    det = str(rb.get("deterministic_checks_each_card", "")).lower()
    if det not in ("yes", "true"):
        findings.append(("P1", loc,
            "review_boundary.deterministic_checks_each_card must be yes — deterministic "
            "checks run on every card (G5), no opt-out"))
    cr = str(rb.get("coderabbit_before_self_review", "")).lower()
    if cr not in VALID_CODERABBIT_BOUNDARY:
        findings.append(("P1", loc,
            f"review_boundary.coderabbit_before_self_review '{rb.get('coderabbit_before_self_review')}' "
            f"not in {sorted(VALID_CODERABBIT_BOUNDARY)}"))
    code_diff_build_state = (
        str(data.get("current_stage", "")) == "BUILD_FACTORY"
        and str(data.get("current_mode", "")) in ("MODULE_BUILD", "MODE_A_UI")
    )
    if code_diff_build_state and cr != "yes" and risk_tier_val != "LITE":
        findings.append(("P1", loc,
            "review_boundary.coderabbit_before_self_review must be yes for BUILD_FACTORY "
            f"{data.get('current_mode')} code-diff work — CodeRabbit is mandatory before "
            "self-review/cross-family on build modules; not_applicable/no is a planning-stage "
            "skip (PROP-042 / v1.21)"))
    # else: risk_tier LITE drops the CodeRabbit-mandatory requirement (self-review only,
    # PBF-PROP-019 P2 fix) — mirrors cx_card.py's _check_coderabbit_required_for_code_diff.
    srb = str(rb.get("self_review_boundary", ""))
    if srb not in VALID_SELF_REVIEW_BOUNDARY:
        findings.append(("P1", loc,
            f"review_boundary.self_review_boundary '{srb}' not in {sorted(VALID_SELF_REVIEW_BOUNDARY)}"))
    elif code_diff_build_state and srb != "module":
        findings.append(("P1", loc,
            "review_boundary.self_review_boundary must be module for BUILD_FACTORY "
            f"{data.get('current_mode')} code-diff work — same-family self-review is mandatory "
            "at the module acceptance gate; the final Built-App Audit / whole-app self-audit is "
            "additional, not a replacement (PROP-042 / v1.21)"))
    cfb = str(rb.get("cross_family_boundary", ""))
    if cfb not in VALID_CROSS_FAMILY_BOUNDARY:
        findings.append(("P1", loc,
            f"review_boundary.cross_family_boundary '{cfb}' not in {sorted(VALID_CROSS_FAMILY_BOUNDARY)}"))
    elif cfb == "ceo_deferred":
        if not field_present(rb, "ceo_decision_ref") or not rb.get("deferred_review_blocks"):
            findings.append(("P1", loc,
                "cross_family_boundary: ceo_deferred REQUIRES ceo_decision_ref + "
                "deferred_review_blocks — an unrecorded deferral is protocol drift (BF-PROP-002)"))
        else:
            # V1.10: cross-family is the LAST review = the ship gate; a deferral may NOT permit
            # ship/advance ("last" can never become "never"). The deferral must block ship/final_ready.
            blocks = [str(b).strip().lower() for b in (rb.get("deferred_review_blocks") or [])]
            if "ship" not in blocks and "final_ready" not in blocks:
                findings.append(("P1", loc,
                    "cross_family_boundary: ceo_deferred but deferred_review_blocks does not include "
                    "'ship' or 'final_ready' — a cross-family deferral may not permit ship (the final "
                    "cross-family pass is the ship gate; 'last' can never become 'never') [V1.10]"))
    if (code_diff_build_state
            and str(data.get("active_build_engine", "")) == "CODEX_APP"
            and cfb in ("module", "foundation_checkpoint")):
        findings.append(("P1", loc,
            "CODEX_APP build state may not route cross-family review at "
            f"'{cfb}' — Codex-built projects route xfam to the whole-app final pass after the "
            "Built-App Audit / whole-app self-audit; Claude Code may use per-module xfam after "
            "module self-review (PROP-042 / v1.21)"))

    # BF-PROP-005: the 3-stage cross-family review ladder (xfam_capability). Append-only +
    # evidence-backed (GPT #4): stage_3 must be backed by REAL opposite-family evidence
    # (auto-promotion), never self-asserted; a DOWNGRADE to a weaker tier needs a CEO ref.
    cap = rb.get("xfam_capability")
    if code_diff_build_state and cap is None:
        findings.append(("P1", loc,
            "review_boundary.xfam_capability missing for BUILD_FACTORY MODULE_BUILD/MODE_A_UI — "
            "the review tier must be explicit before build cards route to self/cross review "
            "(PROP-042 / v1.21)"))
    if cap is not None:
        if str(cap) not in VALID_XFAM_CAPABILITY:
            findings.append(("P1", loc,
                f"review_boundary.xfam_capability '{cap}' not in {sorted(VALID_XFAM_CAPABILITY)} — "
                "the cross-family capability is a fixed ladder (BF-PROP-005)"))
        elif str(cap) == "stage_3" and not field_present(rb, "xfam_capability_evidence"):
            findings.append(("P1", loc,
                "review_boundary.xfam_capability stage_3 without xfam_capability_evidence (a ref to real "
                "opposite-family review evidence) — capability is evidence-backed / auto-promoted, never "
                "self-asserted to dodge the second family (BF-PROP-005 / GPT #4)"))
        ev = str(rb.get("xfam_capability_evidence", "") or "").strip()
        if ev and (Path(ev).is_absolute() or ".." in Path(ev).parts):
            findings.append(("P1", loc,
                f"review_boundary.xfam_capability_evidence '{ev}' must be a repo-relative path (no "
                "absolute path / .. escape) — the evidence is an in-tree opposite-family review artifact, "
                "not an arbitrary external file (BF-PROP-005 / GPT review F6)"))
        if (field_present(rb, "xfam_capability_downgraded_from")
                and not field_present(rb, "xfam_capability_downgrade_ref")):
            findings.append(("P1", loc,
                "review_boundary.xfam_capability_downgraded_from without xfam_capability_downgrade_ref — a "
                "capability DOWNGRADE to a weaker review tier needs a CEO decision ref (append-only; you "
                "cannot quietly drop the second family) (BF-PROP-005 / GPT #4)"))


def _boolish_true(value) -> bool:
    return value is True or str(value).strip().lower() in ("true", "yes")


def _check_built_app_audit_before_final_xfam(data: dict, loc: str, findings: list) -> None:
    """PROP-042 / v1.21: state may not route from accepted modules straight to final xfam.
    The Built-App Audit / whole-app self-audit is the explicit post-build milestone
    before the final opposite-family review. This is a route guard; final-ready
    still owns the heavier path/existence checks."""
    if str(data.get("current_stage", "")) != "BUILD_FACTORY":
        return
    if data.get("current_card") not in (None, ""):
        return
    accepted = data.get("accepted_modules")
    if not isinstance(accepted, list) or not accepted:
        return
    route = " ".join(str(data.get(k, "") or "") for k in ("next_actor", "next_action", "stop_status")).lower()
    if "final" not in route:
        return
    if not any(marker in route for marker in ("xfam", "cross-family", "opposite-family")):
        return

    audit = data.get("built_app_audit")
    if not isinstance(audit, dict):
        findings.append(("P1", loc,
            "state routes accepted modules to final xfam before the Built-App Audit / whole-app "
            "self-audit milestone is recorded — run BUILT-APP-AUDIT.md and disposition findings "
            "before final xfam (PROP-042 / v1.21)"))
        return
    status = str(audit.get("status", "") or "").strip().lower()
    if status != "run" or not _boolish_true(audit.get("findings_dispositioned")) or not field_present(audit, "report_ref"):
        findings.append(("P1", loc,
            "state routes accepted modules to final xfam but built_app_audit is incomplete — "
            "requires status: run, findings_dispositioned: true, and report_ref before final xfam "
            "(PROP-042 / v1.21)"))


def _check_protocol_deviations(data: dict, loc: str, findings: list) -> None:
    """BF-PROP-002: a CEO-authorized departure from canonical timing is a TYPED block —
    never blended into state as if normal; review debt stays visible until repaid."""
    devs = data.get("protocol_deviations")
    if devs is None:
        return
    if not isinstance(devs, list):
        findings.append(("P1", loc, "protocol_deviations must be a list of typed rows"))
        return
    for i, row in enumerate(devs):
        if not isinstance(row, dict):
            findings.append(("P1", loc, f"protocol_deviations[{i}] is not a mapping"))
            continue
        for key in ("id", "ceo_decision_ref", "canonical_rule", "temporary_rule"):
            if not field_present(row, key):
                findings.append(("P1", loc,
                    f"protocol_deviations[{i}].{key} missing — a deviation without it is "
                    "an unrecorded deviation (PROTOCOL_INCIDENT class)"))
        if str(row.get("ceo_authorized", "")).lower() not in ("yes", "true"):
            findings.append(("P1", loc,
                f"protocol_deviations[{i}].ceo_authorized must be yes — only the CEO "
                "authorizes a departure from canonical timing"))
        blocks = str(row.get("blocks", ""))
        if blocks not in VALID_DEVIATION_BLOCKS:
            findings.append(("P1", loc,
                f"protocol_deviations[{i}].blocks '{blocks}' not in {sorted(VALID_DEVIATION_BLOCKS)}"))
        if not isinstance(row.get("review_debt_items"), list):
            findings.append(("P1", loc,
                f"protocol_deviations[{i}].review_debt_items must be a list (may be empty) — "
                "review debt stays visible until repaid"))


def incident_open(data: dict) -> dict | None:
    """Returns the open PROTOCOL_INCIDENT row, or None. Used by cx_card to block
    new build cards / cross-family requests while an incident is open."""
    if not isinstance(data, dict):
        return None
    inc = data.get("protocol_incident")
    inc = inc if isinstance(inc, dict) else {}
    is_open = (str(data.get("stop_status", "")) == "PROTOCOL_INCIDENT"
               or str(inc.get("status", "")).upper() == "OPEN")
    return (inc or {}) if is_open else None


def _check_protocol_incident(data: dict, loc: str, findings: list) -> None:
    """BF-PROP-002: a missed gate / skipped check / false state sets PROTOCOL_INCIDENT —
    the incident row must record cause + repair before new build cards run.
    Scope: PROTOCOL corrections only (a CEO product rejection is a product finding)."""
    inc = data.get("protocol_incident")
    flagged = str(data.get("stop_status", "")) == "PROTOCOL_INCIDENT"
    if not flagged and inc is None:
        return
    if not isinstance(inc, dict):
        findings.append(("P1", loc,
            "stop_status PROTOCOL_INCIDENT without a protocol_incident block — the "
            "incident row must record id + cause + repair (BF-PROP-002)"))
        return
    for key in ("id", "cause", "repair"):
        if not field_present(inc, key):
            findings.append(("P1", loc,
                f"protocol_incident.{key} missing — new build cards stay BLOCKED until "
                "the incident records cause + repair"))
    status = str(inc.get("status", "OPEN")).upper()
    if status not in VALID_INCIDENT_STATUS:
        findings.append(("P1", loc,
            f"protocol_incident.status '{inc.get('status')}' not in {sorted(VALID_INCIDENT_STATUS)}"))


# BF-PROP-003: fix-escalation ladder. fix_cycles rows are STATE-owned; required keys
# per GATES G5 [RULE:fix-escalation-ladder].
FIX_CYCLE_REQUIRED_KEYS = ("finding_id", "source_review_ref", "attempt_n",
                           "seat_ref", "result", "review_ref")
MAX_FIX_ATTEMPTS = 3  # fix-3 failure feeds the 4-failure cross-family debug rule

# BF-PROP-004: a fix_cycles row is validated against the engine epoch ACTIVE AT ITS
# ATTEMPT (not the current engine). engine_switch_log reconstructs the epochs so a
# legitimate prior-epoch seat does not false-fire the BF-PROP-003 seat-family check.
ENGINE_TO_FAMILY = {"CLAUDE_CODE": "ANTHROPIC", "CODEX_APP": "CODEX"}
ENGINE_SWITCH_REQUIRED_KEYS = ("engine_epoch_id", "from_engine", "to_engine", "effective_at")


def _seat_rank(seat_ref: str) -> tuple[int, int, str] | None:
    """Parse a seat_ref into (model_rank, effort_rank, family). None = unparseable."""
    model, effort = parse_model_effort(str(seat_ref))
    if model is None:
        return None
    if model in CLAUDE_MODEL_RANK:
        return CLAUDE_MODEL_RANK[model], EFFORT_RANK.get(effort or "", 0), "ANTHROPIC"
    return GPT_MODEL_RANK[model], EFFORT_RANK.get(effort or "", 0), "CODEX"


def _build_engine_epochs(data: dict, loc: str, findings: list):
    """BF-PROP-004: reconstruct engine epochs from engine_switch_log so a fix_cycles row
    is validated against the engine active AT ITS ATTEMPT, not the current engine.

    Returns (epochs, by_id, switched, ok):
      epochs   ordered [{epoch_id, family, start, end}] (effective_at boundaries;
               first.start=None, last.end=None). [] when no switch log.
      by_id    {engine_epoch_id: family}
      switched True when an engine_switch_log is present (multi-epoch project).
      ok       False when the log is malformed — callers fail closed (GPT #18).
    """
    log = data.get("engine_switch_log")
    if log is None:
        return [], {}, False, True
    if not isinstance(log, list) or not log:
        findings.append(("P1", loc,
            "engine_switch_log must be a non-empty list of typed switch rows "
            "{engine_epoch_id, from_engine, to_engine, effective_at} (BF-PROP-004)"))
        return [], {}, True, False
    rows, ok = [], True
    for i, sw in enumerate(log):
        if not isinstance(sw, dict):
            findings.append(("P1", loc, f"engine_switch_log[{i}] is not a mapping"))
            ok = False
            continue
        missing = [k for k in ENGINE_SWITCH_REQUIRED_KEYS if not field_present(sw, k)]
        if missing:
            findings.append(("P1", loc,
                f"engine_switch_log[{i}] missing {missing} — a switch row must record the "
                "epoch id, both engines, and when it took effect (fail closed, BF-PROP-004)"))
            ok = False
            continue
        if (str(sw.get("from_engine")) not in VALID_BUILD_ENGINES
                or str(sw.get("to_engine")) not in VALID_BUILD_ENGINES):
            findings.append(("P1", loc,
                f"engine_switch_log[{i}] from/to engine not in {sorted(VALID_BUILD_ENGINES)}"))
            ok = False
            continue
        rows.append(sw)
    if not ok or not rows:
        return [], {}, True, False
    rows.sort(key=lambda s: str(s.get("effective_at")))
    init_engine = str(rows[0].get("from_engine"))
    epochs = [{"epoch_id": f"_pre_{rows[0].get('engine_epoch_id')}",
               "family": ENGINE_TO_FAMILY.get(init_engine),
               "start": None, "end": str(rows[0].get("effective_at"))}]
    prev_to = init_engine
    for j, sw in enumerate(rows):
        if str(sw.get("from_engine")) != prev_to:
            findings.append(("P1", loc,
                f"engine_switch_log: a switch to '{sw.get('to_engine')}' records from_engine "
                f"'{sw.get('from_engine')}' but the prior epoch ran '{prev_to}' — the chain "
                "must be continuous (fail closed, BF-PROP-004)"))
            ok = False
        end = str(rows[j + 1].get("effective_at")) if j + 1 < len(rows) else None
        epochs.append({"epoch_id": str(sw.get("engine_epoch_id")),
                       "family": ENGINE_TO_FAMILY.get(str(sw.get("to_engine"))),
                       "start": str(sw.get("effective_at")), "end": end})
        prev_to = str(sw.get("to_engine"))
    cur = str(data.get("active_build_engine", ""))
    if prev_to != cur:
        findings.append(("P1", loc,
            f"engine_switch_log ends at '{prev_to}' but active_build_engine is '{cur}' — the "
            "switch chain must end at the current engine (fail closed, BF-PROP-004)"))
        ok = False
    return epochs, {e["epoch_id"]: e["family"] for e in epochs}, True, ok


def _row_epoch_family(row: dict, epochs, by_id, switched, current_family):
    """BF-PROP-004 (+ GPT #16): the engine family for a fix_cycles row's OWN epoch.
    Returns (family|None, resolvable, cache_mismatch). The recomputed epoch
    (engine_epoch_id / effective_at) is authoritative; an explicit engine_family is a
    CACHE that must agree (GPT #16: never trust a self-declared epoch over the log). A
    switched-project row with neither a placeable anchor nor an engine_family is
    unresolvable — the caller fails closed (never assume the current engine)."""
    declared = str(row.get("engine_family", "")).strip().upper() or None
    if not switched:
        # single-epoch project: the only epoch is the current engine.
        mismatch = bool(declared and current_family and declared != current_family)
        return current_family, current_family is not None, mismatch
    derived = None
    eid = str(row.get("engine_epoch_id", "")).strip()
    if eid and eid in by_id:
        derived = by_id[eid]
    elif field_present(row, "effective_at"):
        at = str(row.get("effective_at"))
        for e in epochs:
            if ((e["start"] is None or at >= e["start"])
                    and (e["end"] is None or at < e["end"])):
                derived = e["family"]
                break
    if derived is not None:
        return derived, True, bool(declared and declared != derived)
    # not placeable by the log: a declared engine_family is accepted ONLY with an explicit legacy
    # annotation (engine_epoch_legacy_ref) — this closes the self-declared-epoch BYPASS (GPT review
    # F2: a current-epoch wrong-family row could omit the anchor and self-declare a family). Without
    # the legacy ref the row is unresolvable and the caller fails closed (never trust a bare epoch).
    if declared and field_present(row, "engine_epoch_legacy_ref"):
        return declared, True, False
    return None, False, False


def _check_fix_cycles(data: dict, loc: str, findings: list) -> None:
    """BF-PROP-003 (epoch-aware BF-PROP-004): a failed fix on the same finding_id MUST
    escalate the seat per BUILD-ENGINE-PROFILES.fix_escalation — re-dispatching the
    same (or lower) seat tier = protocol drift; escalation never resets loop_budget.
    The seat-family + ladder validation keys off the engine epoch ACTIVE AT EACH
    ATTEMPT (engine_switch_log), never the current engine."""
    rows = data.get("fix_cycles")
    if rows is None:
        return
    current_family = ENGINE_TO_FAMILY.get(str(data.get("active_build_engine", "")))
    epochs, by_id, switched, _epochs_ok = _build_engine_epochs(data, loc, findings)
    if not isinstance(rows, list):
        findings.append(("P1", loc,
            "fix_cycles must be a list of typed rows "
            "{finding_id, source_review_ref, attempt_n, seat_ref, result, review_ref} (BF-PROP-003)"))
        return

    by_finding: dict[str, list[tuple[int, dict]]] = {}
    row_epoch: dict[int, tuple] = {}  # id(row) -> (family|None, resolvable)
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            findings.append(("P1", loc, f"fix_cycles[{i}] is not a mapping"))
            continue
        for key in FIX_CYCLE_REQUIRED_KEYS:
            if not field_present(row, key):
                findings.append(("P1", loc,
                    f"fix_cycles[{i}].{key} missing — attempt history is STATE-owned and "
                    "typed; a fix attempt without it is untracked (BF-PROP-003)"))
        if str(row.get("loop_budget_reset", "")).lower() in ("yes", "true", "1"):
            findings.append(("P1", loc,
                f"fix_cycles[{i}] records a loop_budget reset — escalation only changes "
                "the seat for the next bounded fix attempt, it is NEVER permission for a "
                "new review cycle (BF-PROP-003)"))
        fam, resolvable, cache_mismatch = _row_epoch_family(
            row, epochs, by_id, switched, current_family)
        row_epoch[id(row)] = (fam, resolvable)
        if cache_mismatch:
            findings.append(("P1", loc,
                f"fix_cycles[{i}].engine_family '{row.get('engine_family')}' contradicts the "
                "engine epoch recomputed from engine_switch_log — engine_family is a cache, the "
                "epoch is authoritative (fail closed, BF-PROP-004)"))
        try:
            attempt_n = int(row.get("attempt_n"))
        except (TypeError, ValueError):
            findings.append(("P1", loc,
                f"fix_cycles[{i}].attempt_n must be an integer >= 1"))
            continue
        if attempt_n < 1:
            findings.append(("P1", loc,
                f"fix_cycles[{i}].attempt_n must be an integer >= 1"))
            continue
        if attempt_n > MAX_FIX_ATTEMPTS:
            findings.append(("P1", loc,
                f"fix_cycles[{i}].attempt_n={attempt_n} — fix-3 failure feeds the "
                "4-failure cross-family debug rule, never a fix-4 row (BF-PROP-003)"))
            continue
        fid = str(row.get("finding_id", ""))
        if fid:
            by_finding.setdefault(fid, []).append((attempt_n, row))

    for fid, attempts in by_finding.items():
        attempts.sort(key=lambda t: t[0])
        seen_n = set()
        prev: dict[int, dict] = {}
        for attempt_n, row in attempts:
            if attempt_n in seen_n:
                findings.append(("P1", loc,
                    f"fix_cycles: duplicate attempt_n={attempt_n} for finding {fid} — "
                    "one row per bounded attempt"))
                continue
            seen_n.add(attempt_n)
            prev[attempt_n] = row
            if attempt_n < 2:
                continue
            cur_rank = _seat_rank(str(row.get("seat_ref", "")))
            if cur_rank is None:
                findings.append(("P1", loc,
                    f"fix_cycles: attempt {attempt_n} for finding {fid} has unparseable "
                    f"seat_ref '{row.get('seat_ref')}' — an escalated attempt must name a "
                    "model + effort verifiable against the ladder (fail closed, BF-PROP-003)"))
                continue
            fam, resolvable = row_epoch.get(id(row), (None, False))
            if not resolvable:
                findings.append(("P1", loc,
                    f"fix_cycles: attempt {attempt_n} for finding {fid} — cannot resolve which "
                    "engine epoch it belongs to (no engine_epoch_id / effective_at / engine_family, "
                    "and engine_switch_log does not place it). Record the epoch; the ladder is "
                    "validated per the engine active AT THE ATTEMPT, never the current engine "
                    "(fail closed, BF-PROP-004)"))
                continue
            if fam and cur_rank[2] != fam:
                findings.append(("P1", loc,
                    f"fix_cycles: attempt {attempt_n} for finding {fid} seat "
                    f"'{row.get('seat_ref')}' is {cur_rank[2]}-family but its engine epoch ran "
                    f"{fam} — the escalation ladder is per the epoch's engine "
                    "(BF-PROP-003, epoch-aware BF-PROP-004)"))
                continue
            prior_row = prev.get(attempt_n - 1)
            if prior_row is None:
                findings.append(("P1", loc,
                    f"fix_cycles: attempt {attempt_n} for finding {fid} has no recorded "
                    f"attempt {attempt_n - 1} — the ladder is sequential, attempts are "
                    "never skipped or untracked (BF-PROP-003)"))
                continue
            prior_rank = _seat_rank(str(prior_row.get("seat_ref", "")))
            if prior_rank is None:
                continue  # fix_1 may be the symbolic original_builder_seat — nothing to compare
            prior_fam, _pf = row_epoch.get(id(prior_row), (None, False))
            if fam and prior_fam and fam != prior_fam:
                # the same finding's ladder spans an engine switch (legitimate cross-epoch).
                dev = row.get("cross_epoch_deviation")
                if not (isinstance(dev, dict) and field_present(dev, "ceo_decision_ref")):
                    findings.append(("P1", loc,
                        f"fix_cycles: attempt {attempt_n} for finding {fid} continues the "
                        f"ladder across an engine switch ({prior_fam} -> {fam}) without a typed "
                        "cross_epoch_deviation {ceo_decision_ref, reason} — the fix level must be "
                        "preserved across a switch, never silently reset (BF-PROP-004)"))
                continue  # cross-epoch tier is compared within family only (per epoch)
            if cur_rank[2] != prior_rank[2]:
                findings.append(("P1", loc,
                    f"fix_cycles: attempt {attempt_n} for finding {fid} switches family "
                    f"({prior_rank[2]} -> {cur_rank[2]}) — the fix ladder stays within the "
                    "epoch's engine; family alternation belongs to the 4-failure "
                    "cross-family debug rule (BF-PROP-003)"))
                continue
            escalated = (cur_rank[0] > prior_rank[0]
                         or (cur_rank[0] == prior_rank[0] and cur_rank[1] > prior_rank[1]))
            if not escalated:
                findings.append(("P1", loc,
                    f"fix_cycles: attempt {attempt_n} for finding {fid} seat "
                    f"'{row.get('seat_ref')}' is not above attempt {attempt_n - 1} seat "
                    f"'{prior_row.get('seat_ref')}' — re-dispatching the same seat tier on "
                    "the same finding = protocol drift; escalate per "
                    "BUILD-ENGINE-PROFILES.fix_escalation (BF-PROP-003)"))


_STAGE_TO_PROFILES_KEY = {"PLANNING_STUDIO": "planning_studio", "BUILD_FACTORY": "build_factory",
                          "FIXING_STAGE": "fixing_stage", "AUDIT_STAGE": "audit_stage"}


def _engine_profile_checks(data: dict, args, loc: str, findings: list) -> None:
    """PBF-PROP-008 BUILD-ENGINE-PROFILES enforcement — state-side clauses."""
    # clause: active_build_engine present + in enum
    engine = data.get("active_build_engine")
    if not engine or str(engine) not in VALID_BUILD_ENGINES:
        findings.append(("P1", loc,
            f"active_build_engine '{engine}' missing or not in {sorted(VALID_BUILD_ENGINES)} — "
            "the session must declare which build engine it is driving"))
        return  # cannot resolve a seat without a valid engine

    # FIX-STAGE-SEAT-PROFILE (F-PROP-001): a FIXING_STAGE session MUST have a fixing_stage orchestrator
    # seat in BUILD-ENGINE-PROFILES, else the seat cap is invisible — an over-tier orchestrator in a
    # fixing session would pass unchecked. This presence check runs INDEPENDENT of orchestrator_model
    # (which the exceeds-check below skips when absent), so a fixing session can never silently lack a
    # seat cap. Fail closed: a stage whose seat is unreadable/absent is a real gap, not a free pass.
    if str(data.get("current_stage", "")) == "FIXING_STAGE":
        profiles_path, env_err = resolve_profiles_path(args)
        if env_err:
            findings.append(("P1", loc, env_err))
            return
        profiles, perr = load_yaml(profiles_path)
        if perr or not isinstance(profiles, dict):
            findings.append(("P1", loc,
                f"current_stage: FIXING_STAGE but BUILD-ENGINE-PROFILES is unreadable at {profiles_path} — "
                "cannot verify the fixing_stage seat cap (fail closed) (F-PROP-001 / FIX-STAGE-SEAT-PROFILE)"))
            return
        branch_key = ENGINE_BRANCH_KEYS[str(engine)]
        fix_seat = nested_get(profiles, "orchestrator", "fixing_stage", branch_key)
        if not isinstance(fix_seat, dict) or not fix_seat.get("model"):
            findings.append(("P1", loc,
                f"current_stage: FIXING_STAGE but BUILD-ENGINE-PROFILES has no orchestrator.fixing_stage."
                f"{branch_key} seat — the Fixing-stage seat cap is invisible (an over-tier orchestrator "
                "would pass unchecked); add a fixing_stage seat for this engine (F-PROP-001 / "
                "FIX-STAGE-SEAT-PROFILE)"))
            return

    # AUDIT-STAGE-SEAT-PROFILE (X4, v1.22 xfam fix): mirrors FIX-STAGE-SEAT-PROFILE exactly — an
    # AUDIT_STAGE session MUST have an audit_stage orchestrator seat in BUILD-ENGINE-PROFILES, else
    # the seat cap is invisible. Audit posture = verify / review-tier (never a builder seat) —
    # same conductor-tier discipline as fixing_stage, just for the Audit stage's read-only judgment.
    if str(data.get("current_stage", "")) == "AUDIT_STAGE":
        profiles_path, env_err = resolve_profiles_path(args)
        if env_err:
            findings.append(("P1", loc, env_err))
            return
        profiles, perr = load_yaml(profiles_path)
        if perr or not isinstance(profiles, dict):
            findings.append(("P1", loc,
                f"current_stage: AUDIT_STAGE but BUILD-ENGINE-PROFILES is unreadable at {profiles_path} — "
                "cannot verify the audit_stage seat cap (fail closed) (A-PROP-001 / AUDIT-STAGE-SEAT-PROFILE)"))
            return
        branch_key = ENGINE_BRANCH_KEYS[str(engine)]
        audit_seat = nested_get(profiles, "orchestrator", "audit_stage", branch_key)
        if not isinstance(audit_seat, dict) or not audit_seat.get("model"):
            findings.append(("P1", loc,
                f"current_stage: AUDIT_STAGE but BUILD-ENGINE-PROFILES has no orchestrator.audit_stage."
                f"{branch_key} seat — the Audit-stage seat cap is invisible (an over-tier orchestrator "
                "would pass unchecked); add an audit_stage seat for this engine (A-PROP-001 / "
                "AUDIT-STAGE-SEAT-PROFILE)"))
            return

    # clause: orchestrator_model must not exceed the profiles seat for engine + stage
    launched = data.get("orchestrator_model")
    stage_key = _STAGE_TO_PROFILES_KEY.get(str(data.get("current_stage", "")))
    if not launched or not stage_key:
        return  # nothing to compare (orchestrator_model optional pre-PROP-013; stage enum checked elsewhere)

    profiles_path, env_err = resolve_profiles_path(args)
    if env_err:
        findings.append(("P1", loc, env_err))
        return
    profiles, perr = load_yaml(profiles_path)
    if perr or not isinstance(profiles, dict):
        findings.append(("P1", loc,
            f"cannot verify orchestrator seat — BUILD-ENGINE-PROFILES unreadable at {profiles_path} (fail closed)"))
        return

    branch_key = ENGINE_BRANCH_KEYS[str(engine)]
    seat = nested_get(profiles, "orchestrator", stage_key, branch_key)
    if not isinstance(seat, dict) or not seat.get("model"):
        return  # profiles file has no seat for this stage/engine — nothing to enforce

    seat_model = str(seat.get("model", "")).lower()
    rank = CLAUDE_MODEL_RANK if seat_model in CLAUDE_MODEL_RANK else GPT_MODEL_RANK
    launched_model, launched_effort = parse_model_effort(str(launched))

    if launched_model is None or launched_model not in rank:
        findings.append(("P1", loc,
            f"orchestrator_model '{launched}' unrecognized for engine {engine} — "
            "cannot verify against the BUILD-ENGINE-PROFILES seat (fail closed)"))
        return

    seat_rank = rank.get(seat_model, 0)
    seat_effort_rank = EFFORT_RANK.get(str(seat.get("effort", "")).lower(), 0)
    launched_rank = rank[launched_model]
    launched_effort_rank = EFFORT_RANK.get(launched_effort or "", 0)

    exceeds = (launched_rank > seat_rank or
               (launched_rank == seat_rank and seat_effort_rank and launched_effort_rank > seat_effort_rank))
    if exceeds and not field_present(data, "top_allowed_reason"):
        findings.append(("P1", loc,
            f"orchestrator_model '{launched}' exceeds the BUILD-ENGINE-PROFILES seat "
            f"'{seat.get('model')} {seat.get('effort', '')}' for {stage_key}/{branch_key} "
            "without a top_allowed_reason"))


def _git(repo_root: str, *git_args) -> tuple[int, str]:
    """Run a git command under repo_root. Returns (returncode, stdout+stderr)."""
    result = subprocess.run(
        ["git", "-C", repo_root] + list(git_args),
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout.strip() + result.stderr.strip()


def _latest_handoff_path(repo_root: str) -> str | None:
    """Latest handoff = lexically last *.md in <repo-root>/handoffs (mirrors cx_boot._latest_handoff)."""
    hd = Path(repo_root) / "handoffs"
    if not hd.is_dir():
        return None
    candidates = sorted(p.name for p in hd.glob("*.md"))
    return str(hd / candidates[-1]) if candidates else None


def _lock_pointer_migration_exempt(data: dict) -> bool:
    """F6: an explicit typed migration/deviation row in state.lock_deviations can exempt a session
    from the REQUIRED lock-pointer (a project genuinely mid-migration before the sub-block existed).
    The exemption must be EXPLICIT and typed — a row whose deviation_class is the recognized migration
    marker — never the mere ABSENCE of the block (which is the forgery F6 closes)."""
    rows = data.get("lock_deviations")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        dc = str(row.get("deviation_class", "") or "").strip().upper()
        reason = str(row.get("reason", "") or "")
        if dc == "MIGRATION" or "lock_pointer_migration" in reason.lower():
            return True
    return False


def _check_handoff_lock_pointer(data: dict, repo_root: str, loc: str, findings: list) -> None:
    """BF-PROP-007 Lever B (read side): when state.packet_dir is set, the latest handoff in
    <repo-root>/handoffs MUST carry a typed close_turn.lock_pointer that points at the RECOMPUTED
    frozen hash + open-card set, so the next session NEVER boots on a drifted handoff.

    F6 hardening: a frozen project (state.packet_dir set) that has a handoff but NO lock_pointer block,
    or a handoff whose block was removed, now FAILS CLOSED — the silent-return was the hole (a
    REVIEW/FINAL_READY handoff, or a stripped block, booted without recomputing the lock). The ONLY
    exemption is an EXPLICIT typed migration/deviation row (_lock_pointer_migration_exempt). When
    packet_dir is unset there is no frozen lock to point at, so nothing is required."""
    packet_dir_rel = str(data.get("packet_dir", "") or "").strip()
    if not packet_dir_rel:
        return  # no frozen packet → no lock to point at; nothing to verify

    handoff = _latest_handoff_path(repo_root)
    if not handoff:
        return  # no handoff yet (e.g. the very first session) — nothing to read

    try:
        text = Path(handoff).read_text(encoding="utf-8")
    except OSError:
        findings.append(("P1", loc,
            f"latest handoff '{handoff}' is unreadable — cannot verify the lock pointer at "
            "session-start; fail closed (BF-PROP-007 Lever B / F6)"))
        return
    import re as _re
    import yaml as _yaml
    block = None
    for m in _re.finditer(r"```ya?ml\s*\n(.*?)```", text, _re.S):
        try:
            d = _yaml.safe_load(m.group(1))
        except _yaml.YAMLError:
            continue
        if isinstance(d, dict) and isinstance(d.get("close_turn"), dict):
            block = d["close_turn"]
            break
    if not isinstance(block, dict) or "lock_pointer" not in block:
        if _lock_pointer_migration_exempt(data):
            return  # explicit typed migration row exempts this session
        findings.append(("P1", loc,
            f"state.packet_dir is set but the latest handoff '{handoff}' carries NO "
            "close_turn.lock_pointer — a frozen project must POINT AT the lock every turn so the next "
            "session cannot boot on a drifted/stripped handoff; only an explicit typed migration "
            "deviation row exempts this (BF-PROP-007 Lever B / F6)"))
        return
    from cx_close_turn import verify_lock_pointer
    findings.extend(verify_lock_pointer(block.get("lock_pointer"), data, repo_root,
                                        f"{handoff} (lock-pointer)"))


def _session_start_checks(data: dict, repo_root: str, loc: str, findings: list,
                          check_boot_ack: bool = True) -> list[str]:
    """Run --session-start continuity checks. Returns list of advisory WARN lines (not findings).
    check_boot_ack=False is used ONLY by cx check boot itself (the receipt it is about
    to generate cannot already be acknowledged — chicken-and-egg)."""
    advisories = []

    last_commit = data.get("last_commit", "")
    if not last_commit:
        # already caught by normal check; skip git checks to avoid confusing errors
        return advisories

    # P1-1: last_commit must be an ancestor of HEAD
    rc_anc, _ = _git(repo_root, "merge-base", "--is-ancestor", str(last_commit), "HEAD")
    if rc_anc != 0:
        findings.append(("P1", loc,
            "state points outside this branch's history — wrong worktree/branch or stale state"))
    else:
        # ADVISORY: more than 3 commits behind HEAD
        rc_cnt, cnt_out = _git(repo_root, "rev-list", "--count", f"{last_commit}..HEAD")
        if rc_cnt == 0:
            try:
                behind = int(cnt_out)
                if behind > 3:
                    advisories.append(
                        f"WARN: state.last_commit is {behind} commits behind HEAD — confirm state was refreshed"
                    )
            except ValueError:
                pass

    # P1-2: dirty working tree without WIP_CONTINUATION marker
    rc_st, st_out = _git(repo_root, "status", "--porcelain")
    is_dirty = (rc_st == 0 and st_out.strip() != "")

    wip = data.get("wip_continuation") or {}
    wip_marked = str(wip.get("marked", "")).lower() == "yes"

    if is_dirty and not wip_marked:
        findings.append(("P1", loc,
            "uncommitted work without WIP_CONTINUATION marker"))

    # P2: wip_continuation.marked: yes but missing owner_card or handoff_ref
    if wip_marked:
        if not wip.get("owner_card") or not wip.get("handoff_ref"):
            findings.append(("P2", loc,
                "WIP marked but unowned — add owner_card + handoff_ref"))

    # P2: builder-standard session acknowledgment (P-PROP-001, session-level read law).
    # A build-mode session records WHICH BUILDER-STANDARD.md it started from (file + hash).
    if str(data.get("current_mode", "")) in BUILD_MODES:
        _check_session_ack(data, repo_root, loc, findings,
            "builder_standard_read", "builder standard",
            "a build session must acknowledge BUILDER-STANDARD.md at session start")
        # P2: orchestration mode declared (PBF-PROP-012 Part B, R-ORCH) — the lead dispatches
        # fresh subagents per task; it never builds/self-reviews inline.
        _check_orchestration_mode(data, loc, findings)
        # P2: SEE-AND-TEST demo mode declared (PBF-PROP-012 Part E) — the session commits to
        # demoing every user-facing module on its real surface before accepting it.
        _check_module_demo_mode(data, loc, findings)
        # P1: machine-generated boot receipt referenced + fresh (B-PROP-002 rail).
        if check_boot_ack:
            _check_boot_ack(data, repo_root, loc, findings)
        # P1: reviewer taxonomy/timing declared as typed state (BF-PROP-002). PBF-PROP-019
        # P2 fix: resolve risk_tier the same way collect_state_findings does (repo_root is
        # always given at session-start) so the tier-aware CodeRabbit read is consistent
        # whether or not this session-start block ran.
        _rb_risk_tier = "STRICT"
        _rb_pkt_rel = str(data.get("packet_dir", "") or "").strip()
        if _rb_pkt_rel and not (Path(_rb_pkt_rel).is_absolute() or ".." in Path(_rb_pkt_rel).parts):
            _rb_risk_tier = resolve_risk_tier(Path(repo_root) / _rb_pkt_rel)
        _check_review_boundary(data, loc, findings, require_block=True, risk_tier_val=_rb_risk_tier)

    # P1: BF-PROP-007 Lever B (F6) — when state.packet_dir is set, the latest handoff's lock-pointer
    # must match the RECOMPUTED frozen hash + open-card set, so the next session cannot boot on a
    # drifted handoff. This runs across ALL handoff-bearing modes (REVIEW / FINAL_READY / build),
    # not just BUILD_MODES — a stripped or absent lock_pointer on a frozen project fails closed.
    _check_handoff_lock_pointer(data, repo_root, loc, findings)

    # P2: lessons-preload acknowledgment (PBF-PROP-010, planning-session read law).
    # A planning session records WHICH MEMORY/LESSONS.yaml it preloaded the
    # ACTIVE stage-planning lessons from (file + hash).
    if str(data.get("current_stage", "")) == PLANNING_STAGE:
        _check_session_ack(data, repo_root, loc, findings,
            "lessons_preload", "lessons file",
            "a planning session must acknowledge the ACTIVE stage-planning lessons "
            "(MEMORY/LESSONS.yaml) at session start")

    return advisories


def collect_state_findings(path: str, args, session_start: bool, repo_root: str | None,
                           check_boot_ack: bool = True):
    """Full state validation as (data, findings, advisories, fatal). Shared by
    cmd_state and cx check boot (which runs the same checks pre-receipt,
    minus the boot-ack clause it is about to make satisfiable). Every return
    site is 4-ary. `fatal` is None on the happy path; on an early parse/shape
    error it is a TYPED (severity, loc, msg) finding tuple (not a pre-rendered
    string) so each caller renders it itself — a bad state file is REPORTED,
    never crashes the unpack, and no caller re-parses a display string
    (PBF-PROP-015; typed shape per GPT-5.5 xfam)."""
    data, err = load_yaml(path)
    if err:
        return None, None, None, ("P0", path, " ".join(str(err).split()))
    if not isinstance(data, dict):
        return None, None, None, ("P0", path, "not a YAML mapping")

    findings = []
    loc = path

    # --- protocol_stamp ---
    stamp = data.get("protocol_stamp", "")
    if str(stamp).strip() != "Code-X V1":
        findings.append(("P0", loc,
            f"protocol_stamp must be 'Code-X V1', got '{stamp}'"))

    # --- required fields ---
    required = ["project", "current_stage", "current_mode", "current_card",
                "current_actor", "next_actor", "next_action", "stop_status"]
    for f in required:
        if f not in data:
            findings.append(("P0", loc, f"missing required field: {f}"))

    # --- last_commit present & non-empty (anti-chat-only-drift anchor, P2-02) ---
    if "last_commit" not in data or not data.get("last_commit"):
        findings.append(("P1", loc, "last_commit missing or empty — required as anti-chat-only-drift anchor"))

    # --- PBF-PROP-008: active_build_engine + orchestrator seat vs BUILD-ENGINE-PROFILES ---
    _engine_profile_checks(data, args, loc, findings)

    # PBF-PROP-019 P2 FIX: resolve the project risk_tier once, reused by
    # _check_review_boundary's CodeRabbit ceremony read below. Fail-closed: absent/unsafe
    # packet_dir resolves STRICT. Mirrors cx_final_ready.py / cx_build_turn.py's identical
    # packet_dir->resolve_risk_tier pattern; falls back to the state file's own dir when no
    # --repo-root is given (cx check state does not require --repo-root outside session-start).
    risk_tier_val = "STRICT"
    _pkt_rel_tier = str(data.get("packet_dir", "") or "").strip()
    if _pkt_rel_tier and not (Path(_pkt_rel_tier).is_absolute() or ".." in Path(_pkt_rel_tier).parts):
        _base_tier = Path(repo_root) if repo_root else Path(path).resolve().parent
        risk_tier_val = resolve_risk_tier(_base_tier / _pkt_rel_tier)

    # --- BF-PROP-002: typed deviations + review_boundary enums + PROTOCOL_INCIDENT ---
    # (review_boundary validated whenever present; presence required at session-start
    # in build modes — see _session_start_checks)
    _check_review_boundary(data, loc, findings, require_block=False, risk_tier_val=risk_tier_val)
    _check_protocol_deviations(data, loc, findings)
    _check_protocol_incident(data, loc, findings)
    _check_built_app_audit_before_final_xfam(data, loc, findings)

    # --- BF-PROP-003: fix-escalation ladder (STATE-owned fix_cycles) ---
    _check_fix_cycles(data, loc, findings)

    # --- exactly one current_card (null is allowed, but must be present) ---
    if "current_card" in data:
        cc = data["current_card"]
        if cc is None:
            pass  # null = no card in play, that's allowed
        elif not isinstance(cc, str):
            findings.append(("P1", loc, "current_card must be a string id or null"))

    # --- open_findings: counts match items ---
    of = data.get("open_findings", {}) or {}
    counts = of.get("counts", {}) or {}
    items = of.get("items") or []
    if not isinstance(items, list):
        items = []

    # Count actual severities in items
    actual_counts = {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
    for item in items:
        if isinstance(item, dict):
            sev = str(item.get("severity", "")).lower()
            if sev in actual_counts:
                actual_counts[sev] += 1

    # Compare declared vs actual
    for sev in ["p0", "p1", "p2", "p3"]:
        declared = counts.get(sev, 0) or 0
        actual = actual_counts[sev]
        if declared != actual:
            findings.append(("P1", loc,
                f"open_findings.counts.{sev}={declared} but items list has {actual} {sev.upper()} findings — counts must match items"))

    # --- CROSS_FAMILY_RECHECK_PENDING blocks final-ready ---
    for item in items:
        if isinstance(item, dict):
            finding_text = str(item.get("finding", ""))
            if "CROSS_FAMILY_RECHECK_PENDING" in finding_text:
                status = item.get("status", "OPEN")
                if status == "OPEN":
                    findings.append(("P2", loc,
                        f"CROSS_FAMILY_RECHECK_PENDING open finding blocks final-ready: {item.get('id', '?')}"))

    # --- V1.10 defect ledger: post-ship CEO-found defects reuse open_findings ---
    # The Q2 "record the bugs I find" path: a defect the CEO finds after ship is recorded as an
    # open finding flagged found_post_ship + found_by — NOT a parallel ledger file. An OPEN
    # post-ship P0-P2 is then not shippable (final-ready already enforces all-zero, so recording
    # it here keeps it visible + blocking until a fix module closes it).
    for item in items:
        if isinstance(item, dict) and str(item.get("found_post_ship", "")).strip().lower() in ("true", "yes", "1"):
            if not field_present(item, "found_by"):
                findings.append(("P2", loc,
                    f"open_findings item {item.get('id', '?')} is found_post_ship but names no "
                    "found_by — a post-ship defect-ledger row must record who found it (e.g. ceo) [V1.10]"))

    # --- --session-start continuity checks ---
    advisories = []
    if session_start:
        advisories = _session_start_checks(data, repo_root, loc, findings,
                                           check_boot_ack=check_boot_ack)

    return data, findings, advisories, None


def cmd_state(args) -> int:
    path = args.file
    session_start = getattr(args, "session_start", False)
    repo_root = getattr(args, "repo_root", None)

    # --repo-root is required when --session-start is given
    if session_start and not repo_root:
        print("FIX-FIRST\n  [P0] --repo-root is required when --session-start is given",
              flush=True)
        return 1

    data, findings, advisories, fatal = collect_state_findings(
        path, args, session_start, repo_root)
    if fatal:
        _sev, _loc, _msg = fatal
        print(f"FIX-FIRST\n  [{_sev}] {_loc} — {_msg}")
        return 1
    loc = path
    counts = nested_get(data, "open_findings", "counts", default={}) or {}

    # --- Derived who-did-what view ---
    # (printed as info, not a failure)
    # Collect executor + cross_review actor info from any referenced card files
    # Since we only have the state file here, we note this is a read-only derived view
    if not findings:
        # Print derived actor view summary
        print("PASS")
        print(f"  [INFO] protocol_stamp: Code-X V1")
        print(f"  [INFO] current_card: {data.get('current_card', 'null')}")
        of_summary = []
        for s in ["p0","p1","p2","p3"]:
            c = counts.get(s, 0) or 0
            if c:
                of_summary.append(f"{s.upper()}={c}")
        if of_summary:
            print(f"  [INFO] open_findings: {', '.join(of_summary)}")
        else:
            print("  [INFO] open_findings: all zero")
        for warn in advisories:
            print(f"  {warn}")
        return 0

    return findings_report(findings)
