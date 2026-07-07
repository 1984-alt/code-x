#!/usr/bin/env python3
"""
run_contracts.py — contract-bite harness runner for cx.
Reads checkers/check-contracts.yaml and asserts every gate clause bites.

Usage: python3 checkers/tests/run_contracts.py   (from Code-X-V1 root)
       python3 run_contracts.py                   (from checkers/tests/)

Exit 0 = all clauses bite + all good fixtures pass + coverage OK.
Exit 1 = any failure.

git_fixture support: clauses may include `git_fixture: <recipe>` to build a temp
git repo deterministically. {REPO} and {STATE} tokens in clause args are substituted.
"""
import sys

# Runtime floor: the cx checker uses PEP 604 `X | None` type unions (Python 3.10+).
# Guard before importing/exec'ing cx so an older interpreter gets a clear message,
# not a raw import-time TypeError that reads as a false red. (CXAUD-001)
if sys.version_info < (3, 10):
    sys.stderr.write(
        "run_contracts.py: the cx contract-bite harness requires Python 3.10+ (cx uses PEP 604 `X | None` type unions).\n"
        f"    Active interpreter: Python {sys.version.split()[0]} at {sys.executable}\n"
        "    Re-run with Python 3.10+ — e.g.  /opt/homebrew/bin/python3 Code-X-V1/checkers/tests/run_contracts.py\n"
    )
    raise SystemExit(2)

import subprocess
import tempfile
import os
import hashlib as _hashlib
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("FATAL: PyYAML not available — install it or run in the project venv")

THIS_DIR = Path(__file__).resolve().parent
CHECKERS_DIR = THIS_DIR.parent
CX = str(CHECKERS_DIR / "cx")
CONTRACTS = CHECKERS_DIR / "check-contracts.yaml"

# Pin the BUILD-ENGINE-PROFILES input to the test mirror so fixture hashes stay stable
# when the CEO tunes the live canon (PROP-013: one-file change must never break suites).
# CODE_X_TEST_MODE=1 is REQUIRED for the pin to be honored — production cx refuses a
# CX_PROFILES redirect (PROP-014 fold: env override is test-only, fail-loud).
os.environ["CX_PROFILES"] = str(THIS_DIR / "fixtures" / "profiles_test.yaml")
os.environ["CODE_X_TEST_MODE"] = "1"

REQUIRED_SUBCOMMANDS = {"card", "state", "scope", "evidence", "cost", "final-ready", "consistency", "deck", "packet",
                        "boot", "accept", "build-turn", "close-turn", "evals", "design-fidelity", "module-start", "module-acceptance", "module-quality",
                        "dep-scan", "egress", "class-sweep", "render-fidelity", "drift", "structure", "verify-app", "module-demo",
                        "blueprint", "whole-packet-review", "kaizen", "graduation", "audit", "accepted-surface"}
FIXTURES = THIS_DIR / "fixtures"

# Minimal state template that passes all normal cx check state checks.
# Recipes override last_commit and wip_continuation as needed.
_STATE_BASE = {
    "project": "cx-contract-test",
    "protocol_stamp": "Code-X V1",
    "current_stage": "BUILD_FACTORY",
    "current_mode": "MODULE_BUILD",
    "current_card": "BUILD-001",
    "current_actor": "codex",
    "next_actor": "claude",
    "next_action": "cross-review",
    "stop_status": "NONE",
    "build_authorized": "yes",
    "active_build_engine": "CLAUDE_CODE",
    "orchestrator_model": "opus max",
    "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []},
    "cost_this_week": {
        "cards_run": 1, "top_model_cards": 0, "cheap_model_cards": 0,
        "full_reviews": 0, "loops_used": 1, "waste_alarm": "LOW",
    },
    # PROP-014: build-mode sessions must acknowledge BUILDER-STANDARD.md at session start.
    # PROP-042 Part B: build sessions declare orchestrator dispatch (R-ORCH).
    "session_start": {
        "builder_standard_read": {
            "status": "PASS", "file": "BUILDER-STANDARD.md",
            "hash": "deadbeef0123", "read_by": "cx-contract-test",
            "timestamp": "2026-06-10T00:00:00",
        },
        "orchestration_mode": {"dispatch_subagents": "yes", "lead_role": "orchestrator"},
        # PROP-042 Part E: build sessions declare SEE-AND-TEST demo mode (R-DEMO).
        "module_demo_mode": {"demo_every_user_facing_module": "yes", "surfaces": ["web", "mobile"]},
    },
    # PROP-020: reviewer taxonomy/timing as typed state (required at session-start in build modes).
    "review_boundary": {
        "deterministic_checks_each_card": "yes",
        "coderabbit_before_self_review": "yes",
        "self_review_boundary": "module",
        "cross_family_boundary": "module",
        "xfam_capability": "stage_1",
    },
}


def _finalize_boot(repo: str, state_path: str) -> str:
    """PROP-018: run cx check boot against the written state, then inject the
    machine-generated receipt reference into session_start.protocol_boot_ack.
    Returns the receipt path."""
    import hashlib
    receipt = os.path.join(os.path.dirname(state_path), "protocol-boot-receipt.yaml")
    run_cx("check", "boot", "--state", state_path, "--repo-root", repo, "--out", receipt)
    with open(receipt, "rb") as f:
        sha12 = hashlib.sha256(f.read()).hexdigest()[:12]
    with open(state_path) as f:
        state = yaml.safe_load(f)
    state.setdefault("session_start", {})["protocol_boot_ack"] = {
        "receipt": receipt, "receipt_hash": sha12,
        "acked_by": "cx-contract-test", "timestamp": "2026-06-12T00:00:00"}
    with open(state_path, "w") as f:
        yaml.dump(state, f)
    return receipt


def _git_init(repo_dir: str) -> None:
    """Init a bare-minimum git repo deterministically."""
    subprocess.run(["git", "init", "-q", repo_dir], check=True)
    subprocess.run(["git", "-C", repo_dir, "config", "user.email", "cx@test"], check=True)
    subprocess.run(["git", "-C", repo_dir, "config", "user.name", "cx"], check=True)


def _git_commit(repo_dir: str, msg: str = "init") -> str:
    """Make an empty commit; return its SHA."""
    subprocess.run(
        ["git", "-C", repo_dir, "commit", "-q", "--allow-empty", "-m", msg], check=True
    )
    result = subprocess.run(
        ["git", "-C", repo_dir, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _write_state(path: str, last_commit: str, wip: dict | None = None,
                 include_ack: bool = True, overrides: dict | None = None) -> None:
    state = dict(_STATE_BASE)
    state["last_commit"] = last_commit
    if wip is not None:
        state["wip_continuation"] = wip
    if not include_ack:
        state = {k: v for k, v in state.items() if k != "session_start"}
    if overrides:
        state.update(overrides)
    with open(path, "w") as f:
        yaml.dump(state, f)


# ── Recipe registry ───────────────────────────────────────────────────────────

def _recipe_ancestor_ok(tmp: str) -> tuple[str, str]:
    """Clean tree, last_commit == HEAD → PASS."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha)
    _finalize_boot(repo, state)
    return repo, state


def _recipe_foreign_lineage(tmp: str) -> tuple[str, str]:
    """last_commit is a sha from a different repo (unknown in this repo) → bites P1."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")

    # Build a throwaway second repo to get a foreign sha
    other = os.path.join(tmp, "other")
    _git_init(other)
    foreign_sha = _git_commit(other, "foreign")

    state = os.path.join(tmp, "state.yaml")
    _write_state(state, foreign_sha)
    return repo, state


def _recipe_dirty_unmarked(tmp: str) -> tuple[str, str]:
    """Dirty tree, no wip_continuation → bites P1."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    sha = _git_commit(repo, "first")
    # Add an untracked file to make the tree dirty
    with open(os.path.join(repo, "dirty.txt"), "w") as f:
        f.write("dirty\n")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha)
    return repo, state


def _recipe_wip_marked_ok(tmp: str) -> tuple[str, str]:
    """Dirty tree + wip_continuation marked with owner+handoff → PASS."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    sha = _git_commit(repo, "first")
    with open(os.path.join(repo, "dirty.txt"), "w") as f:
        f.write("dirty\n")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, wip={
        "marked": "yes",
        "owner_card": "BUILD-007",
        "handoff_ref": "handoffs/2026-06-10-wip.md",
    })
    _finalize_boot(repo, state)
    return repo, state


def _recipe_wip_marked_unowned(tmp: str) -> tuple[str, str]:
    """Dirty tree + marked: yes but missing owner_card/handoff_ref → bites P2."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    sha = _git_commit(repo, "first")
    with open(os.path.join(repo, "dirty.txt"), "w") as f:
        f.write("dirty\n")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, wip={"marked": "yes"})  # no owner_card, no handoff_ref
    return repo, state


def _recipe_behind_warn(tmp: str) -> tuple[str, str]:
    """6 commits; last_commit = first sha; clean tree → PASS but WARN."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    first_sha = _git_commit(repo, "commit-1")
    for i in range(2, 7):
        _git_commit(repo, f"commit-{i}")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, first_sha)
    _finalize_boot(repo, state)
    return repo, state


def _recipe_no_builder_std_ack(tmp: str) -> tuple[str, str]:
    """Build-mode state WITHOUT session_start.builder_standard_read → bites P2 (PROP-014)."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, include_ack=False)
    return repo, state


def _recipe_no_orchestration_mode(tmp: str) -> tuple[str, str]:
    """Build-mode state WITH builder_standard_read + boot ack but WITHOUT
    session_start.orchestration_mode → bites P2 (PROP-042 Part B, R-ORCH)."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, overrides={"session_start": {
        "builder_standard_read": {
            "status": "PASS", "file": "BUILDER-STANDARD.md",
            "hash": "deadbeef0123", "read_by": "cx-contract-test",
            "timestamp": "2026-06-10T00:00:00"}}})
    _finalize_boot(repo, state)
    return repo, state


def _recipe_inline_waiver_no_scope(tmp: str) -> tuple[str, str]:
    """Build-mode state with inline_waiver set + ceo_decision_ref present BUT missing
    scope: single_card and card_ref → bites P2 (P1-003 R-ORCH inline_waiver scope guard)."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, overrides={"session_start": {
        "builder_standard_read": {
            "status": "PASS", "file": "BUILDER-STANDARD.md",
            "hash": "deadbeef0123", "read_by": "cx-contract-test",
            "timestamp": "2026-06-10T00:00:00"},
        "orchestration_mode": {
            "inline_waiver": True,
            "ceo_decision_ref": "CEO-D-TEST-001",
            # scope and card_ref intentionally omitted
        },
        "module_demo_mode": {"demo_every_user_facing_module": "yes", "surfaces": ["web"]},
    }})
    _finalize_boot(repo, state)
    return repo, state


def _recipe_inline_waiver_with_scope(tmp: str) -> tuple[str, str]:
    """Build-mode state with inline_waiver set + ceo_decision_ref + scope: single_card + card_ref
    → passes STATE-ORCHESTRATION-INLINE-WAIVER-SCOPE (P1-003 good fixture)."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, overrides={"session_start": {
        "builder_standard_read": {
            "status": "PASS", "file": "BUILDER-STANDARD.md",
            "hash": "deadbeef0123", "read_by": "cx-contract-test",
            "timestamp": "2026-06-10T00:00:00"},
        "orchestration_mode": {
            "inline_waiver": True,
            "ceo_decision_ref": "CEO-D-TEST-001",
            "scope": "single_card",
            "card_ref": "BUILD-001",
        },
        "module_demo_mode": {"demo_every_user_facing_module": "yes", "surfaces": ["web"]},
    }})
    _finalize_boot(repo, state)
    return repo, state


def _recipe_no_module_demo_mode(tmp: str) -> tuple[str, str]:
    """Build-mode state WITH builder_standard_read + orchestration_mode + boot ack but WITHOUT
    session_start.module_demo_mode → bites P2 (PROP-042 Part E, SEE-AND-TEST)."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, overrides={"session_start": {
        "builder_standard_read": {
            "status": "PASS", "file": "BUILDER-STANDARD.md",
            "hash": "deadbeef0123", "read_by": "cx-contract-test",
            "timestamp": "2026-06-10T00:00:00"},
        "orchestration_mode": {"dispatch_subagents": "yes", "lead_role": "orchestrator"}}})
    _finalize_boot(repo, state)
    return repo, state


def _recipe_planning_no_lessons_ack(tmp: str) -> tuple[str, str]:
    """PLANNING_STUDIO state WITHOUT session_start.lessons_preload → bites P2 (PROP-017)."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    # base session_start carries only builder_standard_read — no lessons_preload
    _write_state(state, sha, overrides={
        "current_stage": "PLANNING_STUDIO",
        "current_mode": "REVIEW",
    })
    return repo, state


def _recipe_planning_lessons_ack_ok(tmp: str) -> tuple[str, str]:
    """PLANNING_STUDIO state WITH a PASS lessons_preload ack → PASS."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    session_start = dict(_STATE_BASE["session_start"])
    session_start["lessons_preload"] = {
        "status": "PASS", "file": "Code-X-V1/MEMORY/LESSONS.yaml",
        "hash": "cafef00d4242", "read_by": "cx-contract-test",
        "timestamp": "2026-06-11T00:00:00", "active_lesson_count": 6,
    }
    _write_state(state, sha, overrides={
        "current_stage": "PLANNING_STUDIO",
        "current_mode": "REVIEW",
        "session_start": session_start,
    })
    return repo, state


def _recipe_no_boot_ack(tmp: str) -> tuple[str, str]:
    """BUILD-mode session-start state WITHOUT protocol_boot_ack → bites P1 (PROP-018)."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha)  # no _finalize_boot — that's the point
    return repo, state


def _recipe_boot_ack_stale(tmp: str) -> tuple[str, str]:
    """Boot receipt tampered after acknowledgment → bites P1 (PROP-018 anti-theater)."""
    repo, state = _recipe_ancestor_ok(tmp)
    receipt = os.path.join(tmp, "protocol-boot-receipt.yaml")
    with open(receipt, "a") as f:
        f.write("# tampered after ack\n")
    return repo, state


def _recipe_no_review_boundary(tmp: str) -> tuple[str, str]:
    """Booted BUILD-mode state, review_boundary then REMOVED → bites P1 (PROP-020).
    (Receipt hash is of the receipt file, so the ack stays valid — the bite is
    exactly the missing typed review_boundary block.)"""
    repo, state = _recipe_ancestor_ok(tmp)
    with open(state) as f:
        data = yaml.safe_load(f)
    data.pop("review_boundary", None)
    with open(state, "w") as f:
        yaml.dump(data, f)
    return repo, state


def _packet_hash(packet_dir: str) -> str:
    """sha256 over the packet dir — same recipe as cx_deck._compute_packet_hash (kept inline so the
    harness has no import-path dependency on the checkers package)."""
    import hashlib
    base = Path(packet_dir)
    files = sorted([p for p in base.rglob("*") if p.is_file()],
                   key=lambda p: p.relative_to(base).as_posix())
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(base).as_posix().encode("utf-8"))
        h.update(b"\x00")
        h.update(p.read_bytes())
    return h.hexdigest()


def _substantive_hash(pkt) -> str:
    """sha256 over packet with MODULE-REGISTRY.yaml build-metadata stripped — same recipe as
    cx_deck._compute_substantive_source_hash (kept inline to avoid import-path dependency)."""
    import sys as _sys
    _sys.path.insert(0, str(CHECKERS_DIR))
    try:
        from cx_deck import _compute_substantive_source_hash
        return _compute_substantive_source_hash(Path(pkt))
    finally:
        _sys.path.pop(0)


def _build_turn_repo(tmp: str, with_test_cmd: bool, test_cmd: str = "git --version",
                     module_id: str = "m1", risk_tier_manifest_extra: str = "") -> tuple[str, str]:
    """Shared build-turn recipe: repo with a shape-valid card, existing allowed
    files, real evidence, committed clean. The named test command is the
    deterministic command the card itself names (never guessed).

    V1.10 R4: the frozen MODULE-REGISTRY is committed INSIDE a frozen packet dir (packet/) together
    with the requirements manifest; state.packet_dir + state.module_registry_ref point at them and the
    card's locked_packet_hash is the content hash of that packet dir. build-turn's order-wall sub-check
    (module-start) re-hashes the packet (content-deep binding) then enforces order. module_id='m1' is
    the first module (no priors) → order wall PASSES; module_id='m2' needs m1 accepted → BLOCKS."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    with open(FIXTURES / "card_good.yaml") as f:
        card = yaml.safe_load(f)
    os.makedirs(os.path.join(repo, "src"), exist_ok=True)
    with open(os.path.join(repo, "src", "app.py"), "w") as f:
        f.write("# build-turn fixture module\n")
    with open(os.path.join(repo, "evidence.txt"), "w") as f:
        f.write("build-turn fixture evidence: src/app.py exists and is committed\n")
    # Commit the frozen packet (manifest + registry the order wall reads) INSIDE packet/.
    packet = os.path.join(repo, "packet")
    os.makedirs(packet, exist_ok=True)
    with open(FIXTURES / "module_start_good_packet" / "requirements-manifest.yaml") as f:
        manifest_body = f.read()
    if risk_tier_manifest_extra:
        # PBF-PROP-019 Phase 5 (EVAL-052): inject a risk_tier declaration into the frozen packet
        # BEFORE the packet content hash is computed below, so the tier-gated build-turn recipes
        # stay content-bound like every other _build_turn_repo caller.
        manifest_body += risk_tier_manifest_extra
    with open(os.path.join(packet, "requirements-manifest.yaml"), "w") as f:
        f.write(manifest_body)
    with open(FIXTURES / "module_registry_good.yaml") as f:
        registry_body = f.read()
    with open(os.path.join(packet, "MODULE-REGISTRY.yaml"), "w") as f:
        f.write(registry_body)
    # The card's locked_packet_hash = content hash of the frozen packet (deck semantics).
    pkt_hash = _packet_hash(packet)
    card.setdefault("source_map", {})["locked_packet_hash"] = pkt_hash
    card["allowed_files"] = ["src/app.py"]
    card["evidence_required"] = ["evidence.txt"]
    card["module_id"] = module_id
    if with_test_cmd:
        card["test_command"] = test_cmd
    # PROP-040: bake a VALID whole-packet integration review receipt into the shared passing base so
    # the new step-12 gate (which fires on every MODULE_BUILD / MODE_A_UI card) PASSES on it; every
    # build-turn fixture inherits a current opposite-family review, and the bad-case recipes strip it.
    # The receipt lives OUTSIDE the frozen packet (reviews/), bound to the packet content hash; it is
    # committed so the tree stays clean (an untracked receipt would show in the derived scope list).
    os.makedirs(os.path.join(repo, "reviews"), exist_ok=True)
    _wpr = {"whole_packet_review": {
        "schema_version": 1, "review_kind": "WHOLE_PACKET_G7", "frozen_packet_hash": pkt_hash,
        "reviewed_source_set_hash": _substantive_hash(packet),
        "authoring_family": "anthropic", "reviewer_family": "gpt",
        "three_leg_ask": {"continuity": "prior decisions re-checked", "problems": "no P0; drift swept",
                          "approach_improvement": "no simpler structure found"},
        "verdict": "PASS", "findings_ref": "reviews/whole-packet-review.md"}}
    _wpr_path = os.path.join(repo, "reviews", "whole-packet-review.yaml")
    with open(_wpr_path, "w") as f:
        yaml.safe_dump(_wpr, f)
    _wpr_hash = _hashlib.sha256(open(_wpr_path, "rb").read()).hexdigest()[:12]
    _egress_path = os.path.join(repo, "reviews", "coderabbit-egress.yaml")
    with open(_egress_path, "w") as f:
        yaml.safe_dump({"egress_scrub": {"target": "coderabbit", "diff_hash": "fixture"}}, f)
    _cr = {"coderabbit_review": {
        "commit": "abcdef012345",
        "diff_hash": "fixture-diff",
        "tool_version": "fixture",
        "findings_hash": "fixture-findings",
        "egress_receipt_ref": "reviews/coderabbit-egress.yaml",
        "produced_at": "2026-06-29T00:00:00Z",
    }}
    _cr_path = os.path.join(repo, "reviews", "coderabbit-review.yaml")
    with open(_cr_path, "w") as f:
        yaml.safe_dump(_cr, f)
    card["coderabbit"] = {"required": "yes", "receipt": "reviews/coderabbit-review.yaml"}
    card_path = os.path.join(repo, "card.yaml")
    with open(card_path, "w") as f:
        yaml.dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    sha = _git_commit(repo, "build-turn fixture")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, overrides={"packet_dir": "packet",
                                        "module_registry_ref": "packet/MODULE-REGISTRY.yaml",
                                        "whole_packet_review_receipt": {
                                            "receipt": "reviews/whole-packet-review.yaml",
                                            "receipt_hash": _wpr_hash}})
    return repo, state


def _recipe_build_turn_ok(tmp: str) -> tuple[str, str]:
    """Card names its test command; all sub-checks PASS (m1 = first module, order wall clear)."""
    return _build_turn_repo(tmp, with_test_cmd=True)


def _recipe_build_turn_no_test(tmp: str) -> tuple[str, str]:
    """No test command named by card or state → 'card incomplete' P1, never a guess."""
    return _build_turn_repo(tmp, with_test_cmd=False)


def _recipe_build_turn_test_fails(tmp: str) -> tuple[str, str]:
    """Named test command exits nonzero → P1."""
    return _build_turn_repo(tmp, with_test_cmd=True, test_cmd="git rev-parse --verify deadbeef")


def _recipe_build_turn_module_start_blocks(tmp: str) -> tuple[str, str]:
    """V1.10: a module-advancing card for m2 while m1 is NOT accepted — build-turn must run the
    order wall (module-start) and BLOCK. Proves the rail invokes module-start (GPT P0-2)."""
    return _build_turn_repo(tmp, with_test_cmd=True, module_id="m2")


def _build_turn_verify_app_repo(tmp: str, passed: bool) -> tuple[str, str]:
    """PROP-036: build-turn over a card declaring `verify_app_ref` pointing at a verify_app receipt
    (passed True/False). The verify-app sub-check fires INSIDE build-turn = the rail is wired. The card
    passes its own card/scope/evidence/tests sub-checks (built on the build_turn fixture, m1 = first
    module so the order wall is clear), so verify-app is the sole variable: a failing receipt is the
    only thing that blocks the turn (proves the step fires, not silently NOT_APPLICABLE-passes)."""
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    os.makedirs(os.path.join(repo, "acc"), exist_ok=True)
    receipt = ("module_acceptance:\n  module_id: m1\n"
               f"  verify_app:\n    passed: {'true' if passed else 'false'}\n"
               "    repo_sha: abcdef012345\n    generated_by: verify-app-agent\n"
               "    criteria_ref: cards/m1-card.yaml#acceptance_criteria\n")
    with open(os.path.join(repo, "acc", "verify.yaml"), "w") as f:
        f.write(receipt)
    cpath = os.path.join(repo, "card.yaml")
    with open(cpath) as f:
        card = yaml.safe_load(f)
    card["verify_app_ref"] = "acc/verify.yaml"
    with open(cpath, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                    "verify-app rail fixture\n\nCode-X-Provenance: cx-test"], check=True)
    return repo, state


def _recipe_build_turn_verify_app_rail(tmp: str) -> tuple[str, str]:
    return _build_turn_verify_app_repo(tmp, passed=False)


def _recipe_build_turn_verify_app_rail_ok(tmp: str) -> tuple[str, str]:
    return _build_turn_verify_app_repo(tmp, passed=True)


def _recipe_build_turn_verify_app_symlink(tmp: str) -> tuple[str, str]:
    """PROP-036 xfam (GPT-5.5): card.verify_app_ref is a SYMLINK to a passing receipt OUTSIDE the repo.
    Without the symlink/resolved-escape guard the rail would read arbitrary external bytes as an in-repo
    receipt; build-turn must P1 the ref (path-safety), not read through it. Proves the F3 guard bites."""
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    # external passing receipt OUTSIDE the repo (in tmp, the repo's parent)
    ext = os.path.join(tmp, "external_passing.yaml")
    with open(ext, "w") as f:
        f.write("module_acceptance:\n  module_id: m1\n  verify_app:\n    passed: true\n"
                "    repo_sha: abcdef012345\n    generated_by: verify-app-agent\n    criteria_ref: c\n")
    os.makedirs(os.path.join(repo, "acc"), exist_ok=True)
    os.symlink(ext, os.path.join(repo, "acc", "verify.yaml"))  # in-repo symlink -> external bytes
    cpath = os.path.join(repo, "card.yaml")
    with open(cpath) as f:
        card = yaml.safe_load(f)
    card["verify_app_ref"] = "acc/verify.yaml"
    with open(cpath, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                    "verify-app symlink fixture\n\nCode-X-Provenance: cx-test"], check=True)
    return repo, state


def _build_turn_ref_symlink_repo(tmp: str, field: str) -> tuple[str, str]:
    """PROP-037: a build-turn root/ref read whose ref is an in-repo SYMLINK to bytes OUTSIDE the repo.
    field ∈ {'render_bundle', 'dep_scan', 'coderabbit'}. Built on the passing build_turn base (m1 = first
    module so the order wall is clear, tests pass) so the symlink ref is the SOLE failure — proves the
    shared safe_repo_ref guard bites at that step (mirror of the verify_app symlink fixture). Without the
    guard the rail would read arbitrary external bytes as an in-repo artifact. The safe-ref (non-symlink)
    pass path is field-agnostic and already proven by build_turn_verify_app_rail_ok."""
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    ext = os.path.join(tmp, "external_artifact.yaml")  # OUTSIDE the repo (repo's parent)
    with open(ext, "w") as f:
        f.write("external: bytes pretending to be an in-repo artifact\n")
    os.makedirs(os.path.join(repo, "acc"), exist_ok=True)
    os.symlink(ext, os.path.join(repo, "acc", "ref.yaml"))  # in-repo symlink -> external bytes
    ref = "acc/ref.yaml"
    cpath = os.path.join(repo, "card.yaml")
    with open(cpath) as f:
        card = yaml.safe_load(f)
    if field == "render_bundle":
        card["render_bundle"] = ref
    elif field == "coderabbit":
        card["coderabbit"] = {"required": "yes", "receipt": ref}
    elif field == "dep_scan":
        with open(state) as f:
            sdoc = yaml.safe_load(f)
        sdoc["dependency_scan_receipt_ref"] = ref
        with open(state, "w") as f:
            yaml.safe_dump(sdoc, f)
    else:
        raise ValueError(f"unknown field {field}")
    with open(cpath, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                    f"prop037 {field} symlink fixture\n\nCode-X-Provenance: cx-test"], check=True)
    return repo, state


def _recipe_build_turn_render_bundle_symlink(tmp: str) -> tuple[str, str]:
    return _build_turn_ref_symlink_repo(tmp, "render_bundle")


def _recipe_build_turn_dep_scan_symlink(tmp: str) -> tuple[str, str]:
    return _build_turn_ref_symlink_repo(tmp, "dep_scan")


def _recipe_build_turn_coderabbit_receipt_symlink(tmp: str) -> tuple[str, str]:
    return _build_turn_ref_symlink_repo(tmp, "coderabbit")


def _build_turn_ref_real_repo(tmp: str, field: str) -> tuple[str, str]:
    """PROP-038 item 1: per-field good fixtures for DEP-SCAN / RENDER-BUNDLE / CODERABBIT-RECEIPT
    symlink-escape clauses. The base _build_turn_repo already includes a passing coderabbit receipt
    and all other required fields. For dep_scan and render_bundle we add the specific ref as a REAL
    in-repo non-symlink file + commit it, then point the state/card at it — proving the safe-ref
    pass path is exercised through the WHOLE build-turn for that specific field, not just
    field-agnostically via build_turn_verify_app_rail_ok (PROP-037 note).

    render_bundle uses a two-phase commit: first commit to get HEAD (the render evidence must bind
    to the authoritative --repo-head which is the live git HEAD at check time), then write the bundle
    with that HEAD baked in, then commit again — so the bundle's repo_head matches the live HEAD."""
    import hashlib as _hl
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    cpath = os.path.join(repo, "card.yaml")
    with open(cpath) as f:
        card = yaml.safe_load(f)
    with open(state) as f:
        sdoc = yaml.safe_load(f)

    if field == "dep_scan":
        # Write a real in-repo dep-scan receipt (non-symlink) and set state to point at it.
        os.makedirs(os.path.join(repo, "scans"), exist_ok=True)
        lock_body = b"lockfile-contents-v1\n"
        lock_hash = _hl.sha256(lock_body).hexdigest()[:12]
        with open(os.path.join(repo, "package.json"), "w") as f:
            f.write('{"name":"x","dependencies":{"a":"1.0.0"}}\n')
        with open(os.path.join(repo, "package-lock.json"), "wb") as f:
            f.write(lock_body)
        receipt = {"dependency_scan": {"scans": [{
            "ecosystem": "npm", "command": "npm audit --json",
            "scanner_version": "npm/10.8.0", "db_timestamp": "2026-06-18T00:00:00Z",
            "manifest": "package.json", "lockfile": "package-lock.json",
            "lockfile_hash": lock_hash, "produced_at": "2026-06-18T09:00:00Z",
            "high_count": 0, "critical_count": 0}], "waivers": []}}
        rpath = os.path.join(repo, "scans", "dep-scan.yaml")
        with open(rpath, "w") as f:
            yaml.safe_dump(receipt, f)
        sdoc["dependency_scan_receipt_ref"] = "scans/dep-scan.yaml"
        with open(cpath, "w") as f:
            yaml.safe_dump(card, f)
        with open(state, "w") as f:
            yaml.safe_dump(sdoc, f)
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                        "prop038 dep_scan real-ref good fixture\n\nCode-X-Provenance: cx-test"],
                       check=True)
        sha = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"],
                                      text=True).strip()
        sdoc["last_commit"] = sha
        with open(state, "w") as f:
            yaml.safe_dump(sdoc, f)
        return repo, state

    elif field == "render_bundle":
        # Render-fidelity requires render_evidence[].repo_head == live HEAD at build-turn call time.
        # Technique: (1) commit card with render_bundle ref, (2) get HEAD SHA, (3) write bundle
        # on disk (no additional commit) with that HEAD baked in. build-turn reads FS not git objects,
        # so it sees the updated bundle; `git rev-parse HEAD` returns the commit SHA that matches.
        # Screenshot is also written to disk (not committed); the render-fidelity checker only
        # needs the file to exist on the FS (it reads real bytes for hash verification).
        os.makedirs(os.path.join(repo, "render"), exist_ok=True)
        profile_hash = "c7c416dfa9b0"  # matches render_good.yaml pinned hash

        # Step 1: commit card with render_bundle ref + screenshot (both in allowed_files) using a
        # placeholder bundle. The screenshot bytes are final here (hash is stable for step 2).
        shot_body = b"fake-screenshot-bytes\n"
        shot_hash = _hl.sha256(shot_body).hexdigest()[:12]
        with open(os.path.join(repo, "render", "home-390.png"), "wb") as f:
            f.write(shot_body)
        with open(os.path.join(repo, "render", "bundle.yaml"), "w") as f:
            f.write("placeholder: true\n")
        with open(cpath) as f:
            card2 = yaml.safe_load(f)
        card2["render_bundle"] = "render/bundle.yaml"
        card2["allowed_files"] = card2.get("allowed_files", ["src/app.py"]) + [
            "render/bundle.yaml", "render/home-390.png"]
        with open(cpath, "w") as f:
            yaml.safe_dump(card2, f)
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                        "prop038 render_bundle card+screenshot commit\n\nCode-X-Provenance: cx-test"],
                       check=True)
        commit_sha = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"],
                                             text=True).strip()

        # Step 2: write the REAL render bundle on disk (dirty tree) with commit_sha baked in.
        # build-turn reads the FS; `git rev-parse HEAD` returns commit_sha; render-fidelity
        # sees repo_head == HEAD. The dirty bundle.yaml IS in card.allowed_files so scope passes.
        # The screenshot (home-390.png) is already at the right bytes and already committed —
        # if it stays unchanged the scope check won't flag it as modified.
        bundle = {
            "current_repo_head": commit_sha,
            # PBF-PROP-020 fold re-sweep: a render bundle checked with --repo-root/--packet-dir
            # (build-turn wires them when state.packet_dir is set) MUST declare repo_sha_before or
            # fail closed. baseline == HEAD here => empty git-touched set => Rules 2/7 resolve with
            # no CEO-visible screen touched (this fixture proves the safe-ref pass path, not coverage).
            "repo_sha_before": commit_sha,
            "render_profile": {
                "chromium_revision": "1234.5", "device_pixel_ratio": 2,
                "viewport": "390x844",
                "viewports": [{"viewport_id": "phone", "width": 390}],
                "color_schemes": ["light", "dark"], "reduced_motion": True,
                "locale": "en-US", "timezone": "UTC", "fonts": "bundled",
                "animations": "disabled", "network": "blocked",
                "fixture": "DESIGN_FIXTURE", "profile_hash": profile_hash},
            "coverage_matrix": {
                "ui_card": True,
                "required_rows": [{"screen_id": "home", "viewport_id": "phone",
                                   "theme": "light", "content_state": "populated"}]},
            "render_evidence": [{
                "card_id": "BUILD-001", "screen_id": "home",
                "viewport_id": "phone", "theme": "light",
                "content_state": "populated", "route": "/home",
                "repo_head": commit_sha, "state_sha12": "state00aabbcc",
                "locked_packet_hash": "pktfixture0011",
                "render_profile_hash": profile_hash,
                "tool_version": "cx-render/1.0.0",
                "command": "cx render collect --screen home",
                "generated_by": "cx render collect",
                "screenshot_path": "home-390.png",  # relative to bundle parent dir (render/)
                "screenshot_hash": shot_hash,
                "measured_metrics": {
                    "viewport_width": 390, "content_width": 390,
                    "has_horizontal_overflow": False,
                    "max_visible_right": 389.4, "nonblank": True,
                    "app_ready": True,
                    "controls_in_frame": [{"id": "add_expense", "in_frame": True}]},
                "produced_at": "2026-06-30T00:00:00Z"}],
            "golden_drift": [{"screen_id": "home", "viewport_id": "phone",
                               "baseline_ref": "render/golden-home.png",
                               "baseline_hash": "goldenhash0011",
                               "diff_score": 0.4, "tolerance": 2.0}]}
        with open(os.path.join(repo, "render", "bundle.yaml"), "w") as f:
            yaml.safe_dump(bundle, f)

        sdoc["last_commit"] = commit_sha
        with open(state, "w") as f:
            yaml.safe_dump(sdoc, f)
        return repo, state

    elif field == "coderabbit":
        # The base _build_turn_repo already writes a real non-symlink coderabbit receipt at
        # reviews/coderabbit-review.yaml and sets card.coderabbit.receipt to it — the field
        # is already proven to pass the whole build-turn by the base fixture. Return as-is.
        return repo, state

    else:
        raise ValueError(f"unknown field {field}")


def _recipe_build_turn_dep_scan_ref_ok(tmp: str) -> tuple[str, str]:
    """PROP-038 item 1: dep_scan per-field good — real in-repo dep-scan receipt, passes whole build-turn."""
    return _build_turn_ref_real_repo(tmp, "dep_scan")


def _recipe_build_turn_render_bundle_ref_ok(tmp: str) -> tuple[str, str]:
    """PROP-038 item 1: render_bundle per-field good — real in-repo render bundle, passes whole build-turn."""
    return _build_turn_ref_real_repo(tmp, "render_bundle")


def _recipe_build_turn_coderabbit_receipt_ref_ok(tmp: str) -> tuple[str, str]:
    """PROP-038 item 1: coderabbit per-field good — real in-repo receipt, passes whole build-turn."""
    return _build_turn_ref_real_repo(tmp, "coderabbit")


def _relocate_state_to_repo_root(repo: str, state: str) -> str:
    """cx_card.py's resolve_card_risk_tier (and every other packet_dir-relative resolver in
    cx_card.py — lock_fidelity, the packet-ledger loader) resolves repo_root as
    Path(state_path).resolve().parent — the documented, universal convention that CODE-X-STATE.yaml
    lives AT the repo root. _build_turn_repo's shared state.yaml lives in tmp/ (the repo's parent),
    which every OTHER existing git_fixture recipe tolerates because none of them exercise a
    packet_dir-relative resolver through the nested `cx check card` sub-check build-turn dispatches.
    The risk_tier read is the first one that does, so the state file must actually sit at the repo
    root for the nested card sub-check to resolve the SAME packet_dir the outer build-turn command
    resolves via its own --repo-root."""
    real_state = os.path.join(repo, "CODE-X-STATE.yaml")
    with open(state) as f:
        body = f.read()
    with open(real_state, "w") as f:
        f.write(body)
    return real_state


def _recipe_build_turn_coderabbit_lite_strict(tmp: str) -> tuple[str, str]:
    """PBF-PROP-019 Phase 5 (EVAL-052): bad — the frozen packet declares NO risk_tier (defaults
    STRICT) and the card's coderabbit block is stripped -> build-turn's CodeRabbit rail must still
    fire MANDATORY. Closes the Phase-3 contract gap: cx_build_turn's tier-conditional CodeRabbit
    read (design v2.B row 3) previously had a run.py integration test but no check-contracts.yaml
    git_fixture bite."""
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    state = _relocate_state_to_repo_root(repo, state)
    cpath = os.path.join(repo, "card.yaml")
    with open(cpath) as f:
        card = yaml.safe_load(f)
    del card["coderabbit"]
    with open(cpath, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                    "pbf019 phase5 strip coderabbit, strict tier\n\nCode-X-Provenance: cx-test"],
                   check=True)
    return repo, state


def _recipe_build_turn_coderabbit_lite_relaxed(tmp: str) -> tuple[str, str]:
    """PBF-PROP-019 Phase 5 (EVAL-052): good — the frozen packet declares risk_tier: LITE (with a
    resolving risk_tier_decision_ref) and the SAME coderabbit-stripped card now PASSES the
    CodeRabbit sub-check (NOT_APPLICABLE, tier-relaxed) — proving the tier read actually reaches
    build-turn's git-backed rail, not just cx_card's static fixture path."""
    repo, state = _build_turn_repo(
        tmp, with_test_cmd=True,
        risk_tier_manifest_extra="risk_tier: LITE\nrisk_tier_decision_ref: CEO-D-001\n")
    state = _relocate_state_to_repo_root(repo, state)
    cpath = os.path.join(repo, "card.yaml")
    with open(cpath) as f:
        card = yaml.safe_load(f)
    del card["coderabbit"]
    with open(cpath, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                    "pbf019 phase5 strip coderabbit, lite tier\n\nCode-X-Provenance: cx-test"],
                   check=True)
    return repo, state


def _recipe_module_start_registry_alias_symlink(tmp: str) -> tuple[str, str]:
    """PROP-038 item 2: --registry is a SYMLINK-ALIAS to the canonical in-packet registry.
    The alias resolves to the canonical file (same bytes), but it is a symlink — rejected for
    consistency with the safe_repo_ref helper pattern (hygiene, P1)."""
    return _module_start_symlink_repo(tmp, where="alias")


_MS_MANIFEST = ("requirements:\n  - id: REQ-001\n    disposition: BUILDING\n"
                "  - id: REQ-003\n    disposition: BUILDING\n")
_MS_FULL_REGISTRY = (
    "module_registry:\n  frozen_packet_hash: g1-frozen\n  modules:\n"
    "    - module_id: m1\n      dependency_modules: []\n      card_ids: [BUILD-001]\n"
    "    - module_id: m2\n      dependency_modules: [m1]\n      card_ids: [BUILD-002]\n")
_MS_TRIMMED_REGISTRY = (
    "module_registry:\n  frozen_packet_hash: g1-frozen\n  modules:\n"
    "    - module_id: m2\n      dependency_modules: []\n      card_ids: [BUILD-002]\n")


def _module_start_symlink_repo(tmp: str, where: str) -> tuple[str, str]:
    """V1.10 R4 — a frozen packet must be self-contained (no symlinks). Variants:
      where='child' (GPT R5): the canonical <packet>/MODULE-REGISTRY.yaml is a SYMLINK to an external
        trimmed registry → packet hash rejects it → P0.
      where='root' (GPT R6): the packet dir itself is a SYMLINK to an external dir holding a trimmed
        registry → packet hash + module-start reject the symlinked root → P0.
      where='none': a real, symlink-free packet with the canonical registry, card module_id=m1 (no
        priors) → PASS.
      where='alias' (PROP-038 item 2): canonical registry is REAL (packet hash OK, m1 passes), but
        the --registry arg used by the build-turn rail is a SYMLINK-ALIAS (reg-alias.yaml → canonical).
        Rejected P1 for hygiene (consistent with safe_repo_ref helper; no external-byte hole)."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    packet = os.path.join(repo, "packet")
    if where == "alias":
        # PROP-038 item 2: canonical registry is REAL (packet hash OK), but --registry arg is a symlink.
        os.makedirs(packet, exist_ok=True)
        with open(os.path.join(packet, "requirements-manifest.yaml"), "w") as f:
            f.write(_MS_MANIFEST)
        with open(os.path.join(packet, "MODULE-REGISTRY.yaml"), "w") as f:
            f.write(_MS_FULL_REGISTRY)
        # Create a SYMLINK-ALIAS to the canonical registry (same target, different entry path)
        os.symlink(os.path.join(packet, "MODULE-REGISTRY.yaml"),
                   os.path.join(repo, "reg-alias.yaml"))
        module_id, locked = "m1", _packet_hash(packet)  # hash is correct (canonical is real)
    elif where == "ancestor":
        # repo/link -> external dir; repo/link/packet is a REAL dir (final component not a symlink),
        # but the ancestor 'link' is — so the packet resolves OUTSIDE the repo (GPT R7).
        ext_packet = os.path.join(repo, "external_real", "packet")
        os.makedirs(ext_packet, exist_ok=True)
        with open(os.path.join(ext_packet, "requirements-manifest.yaml"), "w") as f:
            f.write(_MS_MANIFEST)
        with open(os.path.join(ext_packet, "MODULE-REGISTRY.yaml"), "w") as f:
            f.write(_MS_TRIMMED_REGISTRY)
        os.symlink(os.path.join(repo, "external_real"), os.path.join(repo, "link"))
        module_id, locked = "m2", "deadbeef"
    elif where == "root":
        external = os.path.join(repo, "external_packet")
        os.makedirs(external, exist_ok=True)
        with open(os.path.join(external, "requirements-manifest.yaml"), "w") as f:
            f.write(_MS_MANIFEST)
        with open(os.path.join(external, "MODULE-REGISTRY.yaml"), "w") as f:
            f.write(_MS_TRIMMED_REGISTRY)
        os.symlink(external, packet)  # packet ROOT is a symlink
        module_id, locked = "m2", "deadbeef"
    else:
        os.makedirs(packet, exist_ok=True)
        with open(os.path.join(packet, "requirements-manifest.yaml"), "w") as f:
            f.write(_MS_MANIFEST)
        if where == "child":
            external = os.path.join(repo, "EXTERNAL-TRIMMED.yaml")
            with open(external, "w") as f:
                f.write(_MS_TRIMMED_REGISTRY)
            os.symlink(external, os.path.join(packet, "MODULE-REGISTRY.yaml"))
            module_id, locked = "m2", "deadbeef"  # hash raises on the symlink before any compare
        else:  # none = good
            with open(os.path.join(packet, "MODULE-REGISTRY.yaml"), "w") as f:
                f.write(_MS_FULL_REGISTRY)
            module_id, locked = "m1", _packet_hash(packet)  # m1 = first module → PASS
    with open(os.path.join(repo, "card.yaml"), "w") as f:
        yaml.dump({"id": "BUILD-X", "mode": "MODULE_BUILD", "module_id": module_id,
                   "source_map": {"locked_packet_hash": locked}}, f)
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "cx-ms-symlink-test", "protocol_stamp": "Code-X V1",
                   "accepted_modules": []}, f)
    return repo, state


def _recipe_module_start_symlink_registry(tmp: str) -> tuple[str, str]:
    return _module_start_symlink_repo(tmp, where="child")


def _recipe_module_start_symlink_root(tmp: str) -> tuple[str, str]:
    return _module_start_symlink_repo(tmp, where="root")


def _recipe_module_start_symlink_ancestor(tmp: str) -> tuple[str, str]:
    return _module_start_symlink_repo(tmp, where="ancestor")


def _recipe_module_start_symlink_ok(tmp: str) -> tuple[str, str]:
    return _module_start_symlink_repo(tmp, where="none")


def _ma_receipt_body(repo_sha_before: str) -> str:
    """A shape-valid acceptance receipt carrying a real PROP-028 build baseline (repo_sha_before)."""
    return ("module_acceptance:\n  module_id: m1\n  verdict: accepted\n  generated_by: cx-accept\n"
            "  state_sha_before: abc123\n  quality_card_hash: qc0011223344\n"
            f"  repo_sha_before: {repo_sha_before}\n")


def _module_acceptance_ref_repo(tmp: str, external: bool) -> tuple[str, str]:
    """V1.10 R4 (GPT R11): the recorded acceptance_ref is model-authored. An ABSOLUTE / outside-repo
    ref would let the Andon wall read arbitrary external bytes as the receipt → reject. Good variant:
    a repo-relative in-repo receipt → PASS. The repo is a real git repo with two real-content commits
    so the PROP-028 phantom-completion guard finds a non-empty base..HEAD diff (no false-positive)."""
    import hashlib
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    # two real-content commits → base..HEAD has a non-empty diff (PROP-028 baseline)
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("one\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    base_sha = _git_commit(repo, "first")
    with open(os.path.join(repo, "b.txt"), "w") as f:
        f.write("two\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    _git_commit(repo, "second")
    if external:
        receipt = os.path.join(tmp, "outside-receipt.yaml")  # OUTSIDE the repo
        ref = receipt  # absolute path
    else:
        os.makedirs(os.path.join(repo, "acc"), exist_ok=True)
        receipt = os.path.join(repo, "acc", "receipt.yaml")
        ref = "acc/receipt.yaml"  # repo-relative
    with open(receipt, "w") as f:
        f.write(_ma_receipt_body(base_sha))
    sha = hashlib.sha256(open(receipt, "rb").read()).hexdigest()[:12]
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "cx-ma-ref-test", "protocol_stamp": "Code-X V1",
                   "accepted_modules": [{"module_id": "m1", "acceptance_ref": ref,
                                         "acceptance_sha12": sha}]}, f)
    return repo, state


def _recipe_module_acceptance_external_ref(tmp: str) -> tuple[str, str]:
    return _module_acceptance_ref_repo(tmp, external=True)


def _recipe_module_acceptance_inrepo_ref(tmp: str) -> tuple[str, str]:
    return _module_acceptance_ref_repo(tmp, external=False)


# ── B-PROP-013 Unit 1 forge-parity bite harness (design-history/b-prop-013-forge-parity-design-
# 2026-07-06.md §7) — formalizes the GUARD's new clauses into check-contracts.yaml so a prior
# builder's run.py-only unit tests count as ENFORCING risk, not just green (run_contracts.py is
# the wall that proves a clause bites via the CLI, same as every other gate in this file).

def _forge_parity_qc_hash(qc: dict) -> str:
    """Same canonicalization as cx_module_acceptance._canonicalize_quality_card_hash — kept inline
    so the harness has no import-path dependency on the checkers package (mirrors _packet_hash)."""
    import json
    canonical = json.dumps(qc, sort_keys=True, separators=(",", ":"), default=str)
    return _hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _forge_parity_repo(tmp: str) -> tuple[str, str]:
    """A real 2-commit repo (non-empty repo_sha_before diff, PROP-028 baseline) — returns
    (repo, base_sha) so callers can bind forge-parity repo_sha fields to a REAL reachable commit
    (base_sha) or a fabricated one, and still pass the pre-existing phantom-completion guard."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("one\n")
    _git_init(repo)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    base_sha = _git_commit(repo, "first")
    with open(os.path.join(repo, "b.txt"), "w") as f:
        f.write("two\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    _git_commit(repo, "second")
    return repo, base_sha


def _forge_parity_write(tmp: str, repo: str, base_sha: str, *, marker_value=True,
                        verify_sha=None, demo_sha=None, lsa_sha=None,
                        quality_card=None, qc_hash=None) -> tuple[str, str]:
    """Writes the packet (declaring the b_prop_013_forge_parity marker), a module-acceptance
    receipt (verify_app/module_demo/live_slice_accept carry ONLY repo_sha — forge_parity_findings
    reads these unconditionally; the full block-shape checks only fire when the order wall passes
    require_live_slice=True, which these standalone `cx check module-acceptance` calls never do),
    and a state.yaml binding the receipt + pointing packet_dir at the packet."""
    packet = os.path.join(repo, "packet")
    os.makedirs(packet, exist_ok=True)
    with open(os.path.join(packet, "requirements-manifest.yaml"), "w") as f:
        yaml.dump({"b_prop_013_forge_parity": marker_value, "requirements": []}, f)

    ma = {
        "module_id": "m1", "verdict": "accepted", "generated_by": "cx-accept",
        "state_sha_before": "abc123", "quality_card_hash": qc_hash or "qc0011223344",
        "repo_sha_before": base_sha,
    }
    if verify_sha is not None:
        ma["verify_app"] = {"repo_sha": verify_sha}
    if demo_sha is not None:
        ma["module_demo"] = {"repo_sha": demo_sha}
    if lsa_sha is not None:
        ma["live_slice_accept"] = {"repo_sha": lsa_sha}
    if quality_card is not None:
        ma["quality_card"] = quality_card

    os.makedirs(os.path.join(repo, "acc"), exist_ok=True)
    receipt = os.path.join(repo, "acc", "receipt.yaml")
    with open(receipt, "w") as f:
        yaml.dump({"module_acceptance": ma}, f)
    with open(receipt, "rb") as fh:
        sha = _hashlib.sha256(fh.read()).hexdigest()[:12]

    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "cx-fp-test", "protocol_stamp": "Code-X V1", "packet_dir": "packet",
                   "accepted_modules": [{"module_id": "m1", "acceptance_ref": "acc/receipt.yaml",
                                         "acceptance_sha12": sha}]}, f)
    return repo, state


def _recipe_forge_parity_good(tmp: str) -> tuple[str, str]:
    """Marker enabled + all three repo_sha fields reachable + a matching quality_card_hash — the
    honest /cx-accept-shaped receipt that must pass the FULL forge-parity wall clean."""
    repo, base_sha = _forge_parity_repo(tmp)
    qc = {"core_four_answered": True, "conformance": "n/a"}
    qc_hash = _forge_parity_qc_hash(qc)
    return _forge_parity_write(tmp, repo, base_sha, marker_value=True,
                               verify_sha=base_sha, demo_sha=base_sha, lsa_sha=base_sha,
                               quality_card=qc, qc_hash=qc_hash)


def _forge_parity_repo_with_side_branch(tmp: str) -> tuple[str, str, str]:
    """FIX-FIRST (B-PROP-013 xfam P1): same 2-commit main history as _forge_parity_repo, PLUS a
    commit made on a side branch that is NEVER merged back — a REAL commit object that genuinely
    exists in the repo (git cat-file -e would find it) but is NOT an ancestor of HEAD. Proves the
    guard checks ANCESTRY, not mere object existence: before the fix, this side-branch sha wrongly
    PASSED (cat-file -e only checks the object is present); merge-base --is-ancestor correctly
    rejects it. Returns (repo, base_sha, side_sha)."""
    repo, base_sha = _forge_parity_repo(tmp)
    orig_branch = subprocess.run(
        ["git", "-C", repo, "symbolic-ref", "--short", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "-C", repo, "checkout", "-b", "side-branch", base_sha],
                   check=True, capture_output=True)
    with open(os.path.join(repo, "side.txt"), "w") as f:
        f.write("side-only\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    side_sha = _git_commit(repo, "side-only-commit-never-merged")
    subprocess.run(["git", "-C", repo, "checkout", orig_branch], check=True, capture_output=True)
    return repo, base_sha, side_sha


def _recipe_forge_parity_bad_verify_app(tmp: str) -> tuple[str, str]:
    repo, base_sha = _forge_parity_repo(tmp)
    return _forge_parity_write(tmp, repo, base_sha, marker_value=True, verify_sha="deadbeef0000")


def _recipe_forge_parity_bad_verify_app_not_ancestor(tmp: str) -> tuple[str, str]:
    """FIX-FIRST: a real, existing commit that is on a side branch — NOT an ancestor of HEAD."""
    repo, base_sha, side_sha = _forge_parity_repo_with_side_branch(tmp)
    return _forge_parity_write(tmp, repo, base_sha, marker_value=True, verify_sha=side_sha)


def _recipe_forge_parity_bad_module_demo(tmp: str) -> tuple[str, str]:
    repo, base_sha = _forge_parity_repo(tmp)
    return _forge_parity_write(tmp, repo, base_sha, marker_value=True, demo_sha="deadbeef0000")


def _recipe_forge_parity_bad_live_slice(tmp: str) -> tuple[str, str]:
    repo, base_sha = _forge_parity_repo(tmp)
    return _forge_parity_write(tmp, repo, base_sha, marker_value=True, lsa_sha="deadbeef0000")


def _recipe_forge_parity_bad_qc_drift(tmp: str) -> tuple[str, str]:
    repo, base_sha = _forge_parity_repo(tmp)
    qc = {"core_four_answered": True, "conformance": "n/a"}
    return _forge_parity_write(tmp, repo, base_sha, marker_value=True, quality_card=qc,
                               qc_hash="wronghash1234")


def _recipe_forge_parity_bad_marker_malformed(tmp: str) -> tuple[str, str]:
    repo, base_sha = _forge_parity_repo(tmp)
    return _forge_parity_write(tmp, repo, base_sha, marker_value="true")  # quoted string, not real bool


# ── B-PROP-013 Unit 2 (`cx check accept`, the STAMPER) — CX-ACCEPT-NO-CEO-TOKEN fixtures ─────────

def _cx_accept_repo(tmp: str) -> tuple[str, str]:
    """A minimal one-commit repo (HEAD == that commit) + a minimal state.yaml — cx-accept only
    needs a resolvable HEAD and a readable state file to recompute state_sha_before."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    head = _git_commit(repo, "first")
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "cx-accept-test", "protocol_stamp": "Code-X V1"}, f)
    return repo, state, head


def _recipe_cx_accept_no_token(tmp: str) -> tuple[str, str]:
    """A draft requesting verdict: accepted with NO ceo_accept_token anywhere — cx-accept must
    refuse to stamp it (CX-ACCEPT-NO-CEO-TOKEN)."""
    repo, state, _head = _cx_accept_repo(tmp)
    draft = {"module_acceptance": {"module_id": "m1", "verdict": "accepted"}}
    with open(os.path.join(repo, "draft.yaml"), "w") as f:
        yaml.dump(draft, f)
    return repo, state


def _recipe_cx_accept_good_token(tmp: str) -> tuple[str, str]:
    """A draft whose ceo_accept_token embeds the recomputed HEAD's FULL 12-char prefix PLUS a
    ceo_turn_ref on the same (top-level, no live_slice/module_demo block) location — cx-accept
    stamps it (PASS), proving the refusal below is not a blanket block. FIX-FIRST: was head[:6]
    with no turn_ref before the P1 close."""
    repo, state, head = _cx_accept_repo(tmp)
    draft = {"module_acceptance": {
        "module_id": "m1", "verdict": "accepted",
        "ceo_accept_token": f"ceo-accepts-{head[:12]}",
        "ceo_turn_ref": "turn-2026-07-06-001",
    }}
    with open(os.path.join(repo, "draft.yaml"), "w") as f:
        yaml.dump(draft, f)
    return repo, state


def _recipe_cx_accept_short_prefix_token(tmp: str) -> tuple[str, str]:
    """FIX-FIRST (B-PROP-013 xfam P1): a token embedding only the OLD forgeable 6-char HEAD
    prefix (`auto-<HEAD[:6]>` shape) must be REFUSED — 12 hex chars are required now."""
    repo, state, head = _cx_accept_repo(tmp)
    draft = {"module_acceptance": {
        "module_id": "m1", "verdict": "accepted",
        "ceo_accept_token": f"auto-{head[:6]}",
    }}
    with open(os.path.join(repo, "draft.yaml"), "w") as f:
        yaml.dump(draft, f)
    return repo, state


def _recipe_cx_accept_token_no_turn_ref(tmp: str) -> tuple[str, str]:
    """FIX-FIRST (B-PROP-013 xfam P1): a full 12-char HEAD-prefix token with NO ceo_turn_ref on
    the same block must be REFUSED — a token alone is not proof of a real CEO turn."""
    repo, state, head = _cx_accept_repo(tmp)
    draft = {"module_acceptance": {
        "module_id": "m1", "verdict": "accepted",
        "ceo_accept_token": f"ceo-accepts-{head[:12]}",
    }}
    with open(os.path.join(repo, "draft.yaml"), "w") as f:
        yaml.dump(draft, f)
    return repo, state


def _recipe_cx_accept_token_wrong_block(tmp: str) -> tuple[str, str]:
    """FIX-FIRST (B-PROP-013 xfam P1): a live_slice module (live_slice_accept block present, but
    carrying NO ceo_accept_token) with a bare TOP-LEVEL token+turn_ref must be REFUSED — for a
    live_slice/module_demo module the token must live ON that structured block, not top-level."""
    repo, state, head = _cx_accept_repo(tmp)
    draft = {"module_acceptance": {
        "module_id": "m1", "verdict": "accepted",
        "live_slice_accept": {"passed": True},
        "ceo_accept_token": f"ceo-accepts-{head[:12]}",
        "ceo_turn_ref": "turn-2026-07-06-001",
    }}
    with open(os.path.join(repo, "draft.yaml"), "w") as f:
        yaml.dump(draft, f)
    return repo, state


def _lf_acceptance_repo(tmp: str, *, deviations=None, drift_card=False,
                        accept_module="m3") -> tuple[str, str]:
    """An lf-packet git repo with a REAL bound receipt for accept_module + a state that sets packet_dir
    (so the F7 Layer-1 gate runs) and optional lock_deviations. drift_card=True adds a working-set card
    referencing an off-manifest requirement_id (Layer-1 (a) drift) into <repo>/cards so module-acceptance
    must fail closed (F7). deviations seeds state.lock_deviations (F8). The packet's m1/m2 are receipt-
    verified-accepted so the open set = m3's cards (the working set the drift card joins)."""
    import hashlib
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    _lf_copy_packet(repo)
    _git_init(repo)
    # a real prior commit so repo_sha_before..HEAD has a non-empty diff (PROP-028 baseline)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    base = _git_commit(repo, "first")
    with open(os.path.join(repo, "b.txt"), "w") as f:
        f.write("two\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    _git_commit(repo, "second")
    # the live deck (cards dir) — full BUILDING coverage so Layer-1 (b) does NOT fire on the clean case
    cards = os.path.join(repo, "cards")
    os.makedirs(cards, exist_ok=True)
    _wcard(cards, "b1.yaml", "BUILD-001", "m1", ["REQ-001", "REQ-002"])
    _wcard(cards, "b2.yaml", "BUILD-002", "m2", ["REQ-003"])
    _wcard(cards, "b3.yaml", "BUILD-003", "m3", ["REQ-004"])
    if drift_card:
        # a working-set card (m3 not accepted → BUILD-003 open) referencing an OFF-manifest req
        _wcard(cards, "b3.yaml", "BUILD-003", "m3", ["REQ-004", "REQ-OFF-LOCK-999"])
    # bound, sha-verified, in-repo receipts for the accepted modules
    os.makedirs(os.path.join(repo, "acc"), exist_ok=True)
    accepted = []
    verified_priors = ["m1", "m2"] if accept_module == "m3" else ["m1"]
    for mid in set(verified_priors + [accept_module]):
        rp = os.path.join(repo, "acc", f"{mid}.yaml")
        with open(rp, "w") as f:
            f.write(f"module_acceptance:\n  module_id: {mid}\n  verdict: accepted\n"
                    "  generated_by: cx-accept\n  state_sha_before: abc123\n"
                    f"  quality_card_hash: qc0011223344\n  repo_sha_before: {base}\n")
        sha = hashlib.sha256(open(rp, "rb").read()).hexdigest()[:12]
        accepted.append({"module_id": mid, "acceptance_ref": f"acc/{mid}.yaml",
                         "acceptance_sha12": sha})
    st = {"project": "lf", "protocol_stamp": "Code-X V1", "packet_dir": "packet",
          "accepted_modules": accepted}
    if deviations is not None:
        st["lock_deviations"] = deviations
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump(st, f)
    return repo, state


def _recipe_lf_accept_status_invalid(tmp: str) -> tuple[str, str]:
    # F8: a lock_deviation with a non-enum status (CLOSED) must fail closed, not slip through.
    return _lf_acceptance_repo(tmp, deviations=[{
        "deviation_id": "LD-9", "card_id": "FIX-9", "lock_anchor_ref": "BUILD-001/REQ-001",
        "deviation_class": "AMBIGUITY_RESOLVED", "reason": "x", "status": "CLOSED",
        "surfaced_at_gate": "module-acceptance"}])


def _recipe_lf_accept_status_ok(tmp: str) -> tuple[str, str]:
    # F8 good: CEO_REVIEWED is the only nonblocking status.
    return _lf_acceptance_repo(tmp, deviations=[{
        "deviation_id": "LD-9", "card_id": "FIX-9", "lock_anchor_ref": "BUILD-001/REQ-001",
        "deviation_class": "AMBIGUITY_RESOLVED", "reason": "x", "status": "CEO_REVIEWED",
        "surfaced_at_gate": "module-acceptance"}])


def _recipe_lf_accept_layer1_drift(tmp: str) -> tuple[str, str]:
    # F7: accept m2 (m1 the only verified prior) so m3's BUILD-003 stays OPEN; the off-manifest req on
    # that open working-set card is Layer-1 drift that must block this module-acceptance.
    return _lf_acceptance_repo(tmp, drift_card=True, accept_module="m2")


def _recipe_lf_accept_layer1_clean(tmp: str) -> tuple[str, str]:
    # F7 good: a clean deck (no Layer-1 drift) accepts m2.
    return _lf_acceptance_repo(tmp, drift_card=False, accept_module="m2")


def _lf_session_start_repo(tmp: str, *, with_lock_pointer: bool) -> tuple[str, str]:
    """F6: a frozen project (state.packet_dir set) at session-start. Built on _STATE_BASE so all the
    unrelated state checks pass; the ONLY variable under test is the handoff's lock_pointer.
    with_lock_pointer=False writes a handoff carrying a close_turn block but NO lock_pointer → must
    fail closed. with_lock_pointer=True copies the real recomputed hash + open set → must pass."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    real = _lf_copy_packet(repo)
    _git_init(repo)
    os.makedirs(os.path.join(repo, "handoffs"), exist_ok=True)
    handoff = os.path.join(repo, "handoffs", "2026-06-22-turn.md")
    if with_lock_pointer:
        body = _LF_HANDOFF.format(hash=real, open="[BUILD-001, BUILD-002, BUILD-003]", assert_hash=real)
    else:
        body = ("# Handoff — no lock pointer\n\n```yaml\nclose_turn:\n  findings_delta: []\n"
                "  evidence_paths: [evidence.txt]\n  next_prompt: |\n    Continue.\n"
                "  vault_sync:\n    status: NOT_APPLICABLE\n    reason: t\n    where_saved: repo\n```\n")
    with open(handoff, "w") as f:
        f.write(body)
    with open(os.path.join(repo, "evidence.txt"), "w") as f:
        f.write("evidence\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    head = _git_commit(repo, "turn")
    state = os.path.join(tmp, "state.yaml")
    # _STATE_BASE is a build-mode session that already satisfies builder-standard / boot-ack /
    # review-boundary; add packet_dir so the F6 lock-pointer requirement applies, and the open-card
    # set is m1/m2/m3's cards (no accepted_modules) so the good lock_pointer's open_cards matches.
    _write_state(state, head, overrides={"packet_dir": "packet"})
    _finalize_boot(repo, state)
    return repo, state


def _recipe_lf_session_no_lock_pointer(tmp: str) -> tuple[str, str]:
    return _lf_session_start_repo(tmp, with_lock_pointer=False)


def _recipe_lf_session_lock_pointer_ok(tmp: str) -> tuple[str, str]:
    return _lf_session_start_repo(tmp, with_lock_pointer=True)


# PROP-032: m1 is a live_slice in the FROZEN registry; m2 depends on m1. The order wall must read
# live_slice from the registry and require m1's receipt to carry a live_slice_accept block before m2
# can start — proving "no next slice until the CEO drove the prior" (P0).
_MS_LIVE_REGISTRY = (
    "module_registry:\n  frozen_packet_hash: g1-frozen\n  modules:\n"
    "    - module_id: m1\n      live_slice: true\n      dependency_modules: []\n      card_ids: [BUILD-001]\n"
    "    - module_id: m2\n      dependency_modules: [m1]\n      card_ids: [BUILD-002]\n")
_LIVE_SLICE_ACCEPT_BLOCK = (
    "  live_slice_accept:\n"
    "    live_url: http://localhost:8000/home\n"
    "    ceo_drove: true\n"
    "    ceo_turn_ref: handoffs/2026-06-20-slice-home.md\n"
    "    repo_sha: NONE_TEST_FIXTURE\n"
    "    ceo_accept_token: \"ACCEPT-m1-abcdef\"\n"
    "    viewport: 390x844\n")
# PROP-036: a valid live_slice acceptance also needs a passing verify_app block (precondition to the
# CEO live-drive). verify_app.repo_sha is presence+hex-shape only (honest scope, like live_slice_accept),
# so a real hex value is used here — not the NONE_TEST_FIXTURE git-leg sentinel.
_VERIFY_APP_BLOCK = (
    "  verify_app:\n"
    "    passed: true\n"
    "    repo_sha: abcdef012345\n"
    "    generated_by: verify-app-agent\n"
    "    criteria_ref: cards/m1-card.yaml#acceptance_criteria\n")
# PROP-042 Part E: a valid live_slice acceptance also needs a module_demo block (precondition to the
# CEO live-drive accept, SEE-AND-TEST gate). The shown_screenshot_path must be a real in-repo file;
# the test recipe writes a dummy turn artifact to the repo so ceo_turn_ref resolves.
# Screenshot hash: dummy value (the file is generated in the recipe as binary content matching this hash).
# repo_sha abcdef012345 → prefix abcdef; token "ACCEPT-m1-abcdef" embeds it.
_MODULE_DEMO_BLOCK_TEMPLATE = (
    "  module_demo:\n"
    "    surface: web\n"
    "    generated_by: cx demo collect\n"
    "    repo_sha: abcdef012345\n"
    "    shown_screenshot_path: {shot_path}\n"
    "    shown_screenshot_hash: {shot_hash}\n"
    "    live_url: http://localhost:8000/home\n"
    "    ceo_accept_token: \"ACCEPT-m1-abcdef\"\n"
    "    ceo_turn_ref: {turn_path}\n"
    "    ceo_verdict: accepted\n"
    "    viewport: 390x844\n"
    "    mockup_ref: {shot_path}\n"
    "    mockup_hash: {shot_hash}\n"
    "    diff_score: 0.0\n"
    "    tolerance: 0.05\n")


def _module_start_live_slice_repo(tmp: str, with_drive: bool) -> tuple[str, str]:
    """m1 = a live_slice; m2 depends on m1. m1's acceptance receipt carries (with_drive) or omits a
    live_slice_accept block. cx check module-start for m2 BLOCKS when m1 has no live-drive accept
    (P0 — the next slice cannot start until the CEO drove the prior), PASSES when it does (PROP-032).
    repo_sha_before uses the test-mode fresh-clone sentinel so the PROP-028 git leg is skipped.
    PROP-042 Part E: when with_drive=True the receipt also carries a well-formed module_demo block
    (surface: web, machine-stamped, real screenshot bytes committed, ceo_verdict: accepted,
    ceo_accept_token embedding repo_sha prefix abcdef)."""
    import hashlib, struct, zlib
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    packet = os.path.join(repo, "packet")
    os.makedirs(packet, exist_ok=True)
    with open(os.path.join(packet, "requirements-manifest.yaml"), "w") as f:
        f.write(_MS_MANIFEST)
    with open(os.path.join(packet, "MODULE-REGISTRY.yaml"), "w") as f:
        f.write(_MS_LIVE_REGISTRY)
    os.makedirs(os.path.join(repo, "acc"), exist_ok=True)

    # PROP-042 Part E: write a real tiny PNG (1x1 red pixel) and a turn artifact into the repo
    # so the module_demo.shown_screenshot_path and ceo_turn_ref resolve when with_drive=True.
    def _tiny_png():
        def chunk(name, data):
            c = struct.pack('>I', len(data)) + name + data
            c += struct.pack('>I', zlib.crc32(name + data) & 0xffffffff)
            return c
        header = b'\x89PNG\r\n\x1a\n'
        ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        idat = chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00'))
        iend = chunk(b'IEND', b'')
        return header + ihdr + idat + iend

    shot_rel = "acc/m1-demo-shot.png"
    turn_rel = "acc/m1-turn.md"
    if with_drive:
        png_bytes = _tiny_png()
        with open(os.path.join(repo, shot_rel), "wb") as f:
            f.write(png_bytes)
        shot_hash = hashlib.sha256(png_bytes).hexdigest()[:12]
        with open(os.path.join(repo, turn_rel), "w") as f:
            f.write("# CEO turn — m1 accept\n\nCEO typed: ACCEPT-m1-abcdef\n")
        demo_block = _MODULE_DEMO_BLOCK_TEMPLATE.format(
            shot_path=shot_rel, shot_hash=shot_hash, turn_path=turn_rel)
    else:
        demo_block = ""
        shot_hash = ""

    body = ("module_acceptance:\n  module_id: m1\n  verdict: accepted\n  generated_by: cx-accept\n"
            "  state_sha_before: abc123\n  quality_card_hash: qc0011223344\n"
            "  repo_sha_before: NONE_TEST_FIXTURE\n")
    if with_drive:
        body += demo_block + _LIVE_SLICE_ACCEPT_BLOCK + _VERIFY_APP_BLOCK
    receipt = os.path.join(repo, "acc", "m1.yaml")
    with open(receipt, "w") as f:
        f.write(body)
    sha = hashlib.sha256(open(receipt, "rb").read()).hexdigest()[:12]
    with open(os.path.join(repo, "card.yaml"), "w") as f:
        yaml.dump({"id": "BUILD-002", "mode": "MODULE_BUILD", "module_id": "m2",
                   "source_map": {"locked_packet_hash": _packet_hash(packet)}}, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    _git_commit(repo, "live-slice fixture")
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "cx-live-slice-test", "protocol_stamp": "Code-X V1",
                   "accepted_modules": [{"module_id": "m1", "acceptance_ref": "acc/m1.yaml",
                                         "acceptance_sha12": sha}]}, f)
    return repo, state


def _recipe_module_start_live_slice_blocks(tmp: str) -> tuple[str, str]:
    return _module_start_live_slice_repo(tmp, with_drive=False)


def _recipe_module_start_live_slice_ok(tmp: str) -> tuple[str, str]:
    return _module_start_live_slice_repo(tmp, with_drive=True)


_CLOSE_TURN_BLOCK_OK = """## Close-turn block

```yaml
close_turn:
  findings_delta:
    - id: F-001
      severity: P1
      status: OPEN
      finding: test coverage for scope subcommand is thin
      state_item_ref: F-001
  evidence_paths:
    - evidence.txt
  next_prompt: |
    Continue with BUILD-002 per the deck; boot first (cx check boot).
  vault_sync:
    status: NOT_APPLICABLE
    reason: contract-test environment has no vault
    where_saved: committed in the fixture repo itself
```
"""


def _close_turn_repo(tmp: str, handoff_body: str, state_overrides: dict | None = None) -> tuple[str, str]:
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    with open(os.path.join(repo, "evidence.txt"), "w") as f:
        f.write("close-turn fixture evidence\n")
    handoff = os.path.join(repo, "handoff.md")
    with open(handoff, "w") as f:
        f.write("# Handoff — contract fixture\n\n" + handoff_body)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                    "fixture turn\n\nCode-X-Provenance: cx-contract-test"], check=True)
    sha = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    state = os.path.join(tmp, "state.yaml")
    overrides = {"open_findings": {"counts": {"p0": 0, "p1": 1, "p2": 0, "p3": 0},
                                   "items": [{"id": "F-001", "severity": "P1",
                                              "finding": "test coverage for scope subcommand is thin",
                                              "owner_card": "BUILD-002", "status": "OPEN"}]}}
    overrides.update(state_overrides or {})
    _write_state(state, sha, overrides=overrides)
    return repo, state


def _recipe_close_turn_ok(tmp: str) -> tuple[str, str]:
    return _close_turn_repo(tmp, _CLOSE_TURN_BLOCK_OK)


def _recipe_close_turn_no_delta(tmp: str) -> tuple[str, str]:
    """Handoff has no typed close_turn block → P1 (free text cannot be reconciled)."""
    return _close_turn_repo(tmp, "All findings handled, vault synced, see you next turn.\n")


def _recipe_close_turn_delta_mismatch(tmp: str) -> tuple[str, str]:
    """Handoff reports an OPEN finding state does not carry → P1 (the W4 scar)."""
    body = _CLOSE_TURN_BLOCK_OK.replace("id: F-001", "id: F-999").replace(
        "state_item_ref: F-001", "state_item_ref: F-999")
    return _close_turn_repo(tmp, body)


def _recipe_boot_receipt_forged(tmp: str) -> tuple[str, str]:
    """Hand-authored receipt with CORRECT canon hashes + PASS — but never generated by
    cx check boot, so it lacks the state/HEAD binding → bites P1 (forging a green boot
    must be equivalent to running the command — GPT cross-review fix)."""
    import hashlib
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    _git_commit(repo, "first")
    sha = _git_commit(repo, "second")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha)
    canon_root = CHECKERS_DIR.parent
    canon = []
    for name in ("START-HERE.md", "KERNEL.md", "GATES.md", "BUILDER-STANDARD.md"):
        digest = hashlib.sha256((canon_root / name).read_bytes()).hexdigest()[:12]
        canon.append({"path": name, "sha12": digest})
    receipt_path = os.path.join(tmp, "protocol-boot-receipt.yaml")
    with open(receipt_path, "w") as f:
        yaml.dump({"protocol_boot_receipt": {
            "generated_by": "cx check boot", "generated_at": "2026-06-12T00:00:00+00:00",
            "canon": canon, "state_file": state, "state_check_result": "PASS",
            "state_check_findings": [], "latest_handoff_path": "NONE",
        }}, f)
    with open(receipt_path, "rb") as f:
        receipt_sha = hashlib.sha256(f.read()).hexdigest()[:12]
    with open(state) as f:
        data = yaml.safe_load(f)
    data.setdefault("session_start", {})["protocol_boot_ack"] = {
        "receipt": receipt_path, "receipt_hash": receipt_sha,
        "acked_by": "forger", "timestamp": "2026-06-12T00:00:00"}
    with open(state, "w") as f:
        yaml.dump(data, f)
    return repo, state


def _recipe_close_turn_row_untyped(tmp: str) -> tuple[str, str]:
    """findings_delta row missing finding + state_item_ref → P1 (typed schema, all five fields)."""
    body = _CLOSE_TURN_BLOCK_OK.replace(
        "      finding: test coverage for scope subcommand is thin\n", "").replace(
        "      state_item_ref: F-001\n", "")
    return _close_turn_repo(tmp, body)


def _recipe_close_turn_evidence_path_escape(tmp: str) -> tuple[str, str]:
    """PBF-PROP-021 group-1 hole #5: `(Path(repo_root) / str(ev)).exists()` silently drops the
    left operand when `ev` is ABSOLUTE (pathlib join semantics) — `/etc/hosts` resolved OUTSIDE
    the repo and counted as durable in-repo evidence, masking a turn that committed nothing."""
    body = _CLOSE_TURN_BLOCK_OK.replace("    - evidence.txt\n", "    - /etc/hosts\n")
    return _close_turn_repo(tmp, body)


def _recipe_close_turn_vault_skip_no_reason(tmp: str) -> tuple[str, str]:
    """vault_sync SKIPPED_WITH_REASON without reason/where_saved → P1."""
    body = _CLOSE_TURN_BLOCK_OK.replace(
        "    status: NOT_APPLICABLE\n    reason: contract-test environment has no vault\n"
        "    where_saved: committed in the fixture repo itself",
        "    status: SKIPPED_WITH_REASON")
    return _close_turn_repo(tmp, body)


def _mk_dep_repo(tmp, scan_override=None, waivers=None, write_lockfile=True,
                 extra_manifests=None, extra_lockfiles=None):
    """PROP-027: a tiny repo with package.json (+ package-lock.json) and a
    dependency_scan receipt. scan_override patches the single npm scan entry
    (a None value deletes that key, for the missing-field recipe)."""
    import hashlib
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    with open(os.path.join(repo, "package.json"), "w") as f:
        f.write('{"name":"x","dependencies":{"a":"1.0.0"}}\n')
    lock_rel, lock_hash = "package-lock.json", "deadbeef0000"
    if write_lockfile:
        lock_abs = os.path.join(repo, lock_rel)
        with open(lock_abs, "w") as f:
            f.write("lockfile-contents-v1\n")
        lock_hash = hashlib.sha256(open(lock_abs, "rb").read()).hexdigest()[:12]
    for mf in (extra_manifests or []):
        with open(os.path.join(repo, mf), "w") as f:
            f.write("extra-manifest\n")
    for lf in (extra_lockfiles or []):
        with open(os.path.join(repo, lf), "w") as f:
            f.write("extra-lock\n")
    scan = {"ecosystem": "npm", "command": "npm audit --json",
            "scanner_version": "npm/10.8.0", "db_timestamp": "2026-06-18T00:00:00Z",
            "manifest": "package.json", "lockfile": lock_rel,
            "lockfile_hash": lock_hash, "produced_at": "2026-06-18T09:00:00Z",
            "high_count": 0, "critical_count": 0}
    if scan_override:
        scan.update(scan_override)
        scan = {k: v for k, v in scan.items() if v is not None}
    receipt = {"dependency_scan": {"scans": [scan], "waivers": waivers or []}}
    rpath = os.path.join(tmp, "dep-scan-receipt.yaml")
    with open(rpath, "w") as f:
        yaml.dump(receipt, f)
    return repo, rpath


def _recipe_dep_scan_ok(tmp):
    return _mk_dep_repo(tmp)

def _recipe_dep_scan_stale_hash(tmp):
    return _mk_dep_repo(tmp, scan_override={"lockfile_hash": "deadbeef0000"})

def _recipe_dep_scan_high_unwaived(tmp):
    return _mk_dep_repo(tmp, scan_override={"high_count": 2, "critical_count": 1})

_WAIVER = {"ceo_decision_ref": "CEO-D-X", "advisory_ids": ["GHSA-aaaa"], "package": "a",
           "severity": "high", "reason": "r", "mitigation": "m", "expiry": "2026-12-01", "owner": "acme"}

def _recipe_dep_scan_high_uncovered(tmp):
    # advisories named, but the only waiver covers a DIFFERENT advisory + package -> uncovered.
    return _mk_dep_repo(tmp,
        scan_override={"high_count": 1, "critical_count": 0, "high_critical_advisories": ["GHSA-aaaa"],
                       "package": "a"},
        waivers=[{**_WAIVER, "advisory_ids": ["GHSA-zzzz"], "package": "other"}])

def _recipe_dep_scan_high_waived(tmp):   # GOOD — advisory named AND covered by a waiver
    return _mk_dep_repo(tmp,
        scan_override={"high_count": 1, "critical_count": 0, "high_critical_advisories": ["GHSA-aaaa"],
                       "package": "a"},
        waivers=[_WAIVER])

def _recipe_dep_scan_extra_lockfile(tmp):
    return _mk_dep_repo(tmp, extra_lockfiles=["yarn.lock"])

def _recipe_dep_scan_path_unsafe(tmp):
    return _mk_dep_repo(tmp, scan_override={"lockfile": "../../etc/passwd"})

def _recipe_dep_scan_missing_lockfile(tmp):
    return _mk_dep_repo(tmp, write_lockfile=False)

def _recipe_dep_scan_missing_field(tmp):
    return _mk_dep_repo(tmp, scan_override={"scanner_version": None})

def _recipe_dep_scan_uncovered_manifest(tmp):
    return _mk_dep_repo(tmp, extra_manifests=["requirements.txt"])


# ── PROP-040 whole-packet-review recipes ────────────────────────────────────────
# A self-contained repo: a frozen packet copied under <repo>/packet, a typed whole_packet_review
# receipt under <repo>/reviews/ (OUTSIDE the packet), and a state pointing at it via
# whole_packet_review_receipt {receipt, receipt_hash}. The standalone check needs no git; the returned
# (repo, state) fill {REPO} and {STATE}; --packet-dir is {REPO}/packet. The good receipt's
# frozen_packet_hash + the state's receipt_hash are computed LIVE (never baked constants that drift).
def _mk_wpr_repo(tmp, review_override=None, drop_receipt_block=False, receipt_ref_override=None,
                 state_hash_override=None, not_typed=False):
    import shutil
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "reviews"), exist_ok=True)
    pkt = os.path.join(repo, "packet")
    shutil.copytree(FIXTURES / "module_start_good_packet", pkt)
    pkt_hash = _packet_hash(pkt)
    review = {"schema_version": 1, "review_kind": "WHOLE_PACKET_G7", "frozen_packet_hash": pkt_hash,
              "reviewed_source_set_hash": _substantive_hash(pkt),
              "authoring_family": "anthropic", "reviewer_family": "gpt",
              "three_leg_ask": {"continuity": "prior packet decisions re-checked vs the frozen registry",
                                "problems": "no P0; cross-document drift swept (TRD vs stack-lock)",
                                "approach_improvement": "no simpler structure found; coverage adequate"},
              "verdict": "PASS", "findings_ref": "reviews/whole-packet-review.md"}
    if review_override:
        review.update(review_override)
        review = {k: v for k, v in review.items() if v is not None}   # None deletes a key
    rpath = os.path.join(repo, "reviews", "whole-packet-review.yaml")
    with open(rpath, "w") as f:
        if not_typed:
            f.write("not_a_review: true\n")   # a mapping with NO whole_packet_review key
        else:
            yaml.safe_dump({"whole_packet_review": review}, f)
    rhash = _hashlib.sha256(open(rpath, "rb").read()).hexdigest()[:12]
    state_doc = {"project": "wpr-contract-test", "packet_dir": "packet"}
    if not drop_receipt_block:
        state_doc["whole_packet_review_receipt"] = {
            "receipt": receipt_ref_override or "reviews/whole-packet-review.yaml",
            "receipt_hash": state_hash_override or rhash}
    spath = os.path.join(tmp, "state.yaml")
    with open(spath, "w") as f:
        yaml.safe_dump(state_doc, f)
    return repo, spath


def _recipe_wpr_ok(tmp):
    return _mk_wpr_repo(tmp)

def _recipe_wpr_missing_receipt(tmp):
    return _mk_wpr_repo(tmp, drop_receipt_block=True)

def _recipe_wpr_hash_mismatch(tmp):
    return _mk_wpr_repo(tmp, state_hash_override="deadbeef0000")

def _recipe_wpr_path_unsafe(tmp):
    return _mk_wpr_repo(tmp, receipt_ref_override="../outside.yaml")

def _recipe_wpr_not_typed(tmp):
    return _mk_wpr_repo(tmp, not_typed=True)

def _recipe_wpr_same_family(tmp):
    # ALIAS same-group: authoring 'claude' + reviewer 'anthropic' are BOTH the Anthropic group — a bare
    # string-inequality would pass; the cross-family GROUP check must reject it (PROP-040 xfam P0).
    return _mk_wpr_repo(tmp, review_override={"authoring_family": "claude", "reviewer_family": "anthropic"})

def _recipe_wpr_unknown_family(tmp):
    return _mk_wpr_repo(tmp, review_override={"reviewer_family": "mistral"})   # not a KNOWN family

def _recipe_wpr_wrong_kind(tmp):
    return _mk_wpr_repo(tmp, review_override={"review_kind": "PER_MODULE"})

def _recipe_wpr_missing_field(tmp):
    return _mk_wpr_repo(tmp, review_override={"findings_ref": None})   # None deletes a required key

def _recipe_wpr_three_leg_placeholder(tmp):
    return _mk_wpr_repo(tmp, review_override={"three_leg_ask": "present"})   # a bare scalar placeholder

def _recipe_wpr_bad_verdict(tmp):
    return _mk_wpr_repo(tmp, review_override={"verdict": "FIX_FIRST"})

def _recipe_wpr_stale_packet(tmp):
    # Write a valid receipt with the CURRENT substantive hash, then append a byte to a
    # SUBSTANTIVE file (requirements-manifest.yaml) — making the recomputed substantive
    # hash differ from the receipt's recorded value (WHOLE-PACKET-REVIEW-SUBSTANTIVE-CURRENT).
    import shutil
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "reviews"), exist_ok=True)
    pkt = os.path.join(repo, "packet")
    shutil.copytree(FIXTURES / "module_start_good_packet", pkt)
    # Compute substantive hash BEFORE the edit
    sub_hash = _substantive_hash(pkt)
    pkt_hash = _packet_hash(pkt)
    review = {"schema_version": 1, "review_kind": "WHOLE_PACKET_G7", "frozen_packet_hash": pkt_hash,
              "reviewed_source_set_hash": sub_hash,
              "authoring_family": "anthropic", "reviewer_family": "gpt",
              "three_leg_ask": {"continuity": "prior packet decisions re-checked vs the frozen registry",
                                "problems": "no P0; cross-document drift swept (TRD vs stack-lock)",
                                "approach_improvement": "no simpler structure found; coverage adequate"},
              "verdict": "PASS", "findings_ref": "reviews/whole-packet-review.md"}
    rpath = os.path.join(repo, "reviews", "whole-packet-review.yaml")
    with open(rpath, "w") as f:
        yaml.safe_dump({"whole_packet_review": review}, f)
    rhash = _hashlib.sha256(open(rpath, "rb").read()).hexdigest()[:12]
    # NOW append a byte to requirements-manifest.yaml (substantive change) AFTER writing receipt
    mf = os.path.join(pkt, "requirements-manifest.yaml")
    with open(mf, "ab") as f:
        f.write(b"\n# stale-marker\n")
    state_doc = {"project": "wpr-contract-test", "packet_dir": "packet",
                 "whole_packet_review_receipt": {
                     "receipt": "reviews/whole-packet-review.yaml",
                     "receipt_hash": rhash}}
    spath = os.path.join(tmp, "state.yaml")
    with open(spath, "w") as f:
        yaml.safe_dump(state_doc, f)
    return repo, spath


def _recipe_wpr_missing_sub_hash(tmp):
    return _mk_wpr_repo(tmp, review_override={"reviewed_source_set_hash": ""})


def _recipe_wpr_buildmeta_delta(tmp):
    # Build-metadata-only registry edit: add protocol_version to registry AFTER receipt
    import shutil
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "reviews"), exist_ok=True)
    pkt = os.path.join(repo, "packet")
    shutil.copytree(FIXTURES / "module_start_good_packet", pkt)
    # Write receipt with CURRENT substantive hash
    sub_hash_before = _substantive_hash(pkt)
    pkt_hash_before = _packet_hash(pkt)
    review = {"schema_version": 1, "review_kind": "WHOLE_PACKET_G7",
              "frozen_packet_hash": pkt_hash_before,
              "reviewed_source_set_hash": sub_hash_before,
              "authoring_family": "anthropic", "reviewer_family": "gpt",
              "three_leg_ask": {"continuity": "prior packet decisions re-checked vs the frozen registry",
                                "problems": "no P0; cross-document drift swept (TRD vs stack-lock)",
                                "approach_improvement": "no simpler structure found; coverage adequate"},
              "verdict": "PASS", "findings_ref": "reviews/whole-packet-review.md"}
    rpath = os.path.join(repo, "reviews", "whole-packet-review.yaml")
    with open(rpath, "w") as f:
        yaml.safe_dump({"whole_packet_review": review}, f)
    rhash = _hashlib.sha256(open(rpath, "rb").read()).hexdigest()[:12]
    # NOW mutate ONLY build-metadata fields in MODULE-REGISTRY.yaml
    reg_path = os.path.join(pkt, "MODULE-REGISTRY.yaml")
    with open(reg_path, "r") as f:
        content = f.read()
    # Add protocol_version under module_registry (build-metadata only)
    content = content.replace("module_registry:\n", "module_registry:\n  protocol_version: \"1.99-test\"\n")
    with open(reg_path, "w") as f:
        f.write(content)
    state_doc = {"project": "wpr-contract-test", "packet_dir": "packet",
                 "whole_packet_review_receipt": {
                     "receipt": "reviews/whole-packet-review.yaml",
                     "receipt_hash": rhash}}
    spath = os.path.join(tmp, "state.yaml")
    with open(spath, "w") as f:
        yaml.safe_dump(state_doc, f)
    return repo, spath


def _recipe_wpr_receipt_symlink(tmp):
    # the in-repo receipt ref is a SYMLINK to bytes OUTSIDE the repo — safe_repo_ref must reject it
    # before reading (the PROP-037 path-safety class).
    repo, state = _mk_wpr_repo(tmp)
    ext = os.path.join(tmp, "external_review.yaml")
    with open(ext, "w") as f:
        f.write("whole_packet_review: {verdict: PASS}\n")
    link = os.path.join(repo, "reviews", "whole-packet-review.yaml")
    os.remove(link)
    os.symlink(ext, link)   # in-repo symlink -> external bytes
    return repo, state


def _recipe_build_turn_wpr_missing(tmp):
    """PROP-040: a module-advancing build-turn whose state has NO whole_packet_review_receipt — the
    step-12 integration gate fails closed (no module builds without a current whole-packet review).
    Built on the passing build_turn base (which now bakes a valid receipt) so the stripped receipt is
    the SOLE failure — proves the rail wiring bites."""
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    with open(state) as f:
        sdoc = yaml.safe_load(f)
    sdoc.pop("whole_packet_review_receipt", None)
    with open(state, "w") as f:
        yaml.safe_dump(sdoc, f)
    return repo, state


# ── PROP-034 lock-fidelity recipes ──────────────────────────────────────────────
# All reuse the frozen module_start_good_packet (REQ-001..004 BUILDING; m1->BUILD-001,
# m2->BUILD-002, m3->BUILD-003) committed under <repo>/packet, with state.packet_dir=packet.

import shutil as _shutil

_LF_PACKET_SRC = FIXTURES / "module_start_good_packet"


def _lf_copy_packet(repo: str) -> str:
    """Copy the frozen packet into <repo>/packet; return its content hash (= deck/order-wall hash)."""
    dst = os.path.join(repo, "packet")
    _shutil.copytree(_LF_PACKET_SRC, dst)
    return _packet_hash(dst)


def _lf_card_repo(tmp: str, card_fixture: str, bind_packet_hash: bool = False,
                  seed_packet=None) -> tuple[str, str]:
    """A repo with the frozen packet + a state pointing packet_dir=packet, and the named card fixture
    copied to <repo>/card.yaml. The card check resolves the packet relative to the state file's dir
    (== repo), so lock_anchor_ref REQ ids resolve. The clause references {REPO}/card.yaml.

    seed_packet(repo): optional callback run AFTER the packet is copied, BEFORE the hash is bound —
    used to add F3 authorization files (ledger row + amendment) into the hashed packet body.
    bind_packet_hash=True (GOOD fixtures only, F2): recompute the copied packet's hash and inject it as
    the card's source_map.locked_packet_hash so the anchor-binds-to-packet check passes for the honest
    case. BAD fixtures leave the fixture's static hash so the F2 mismatch is NOT what they trip on."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    _lf_copy_packet(repo)
    if seed_packet is not None:
        seed_packet(repo)
    card_dst = os.path.join(repo, "card.yaml")
    _shutil.copyfile(FIXTURES / card_fixture, card_dst)
    if bind_packet_hash:
        sys.path.insert(0, str(CHECKERS_DIR))
        from cx_deck import _compute_packet_hash
        real_hash = _compute_packet_hash(Path(os.path.join(repo, "packet")))
        with open(card_dst) as f:
            card = yaml.safe_load(f)
        card.setdefault("source_map", {})["locked_packet_hash"] = real_hash
        with open(card_dst, "w") as f:
            yaml.dump(card, f)
    state = os.path.join(repo, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "lf", "protocol_stamp": "Code-X V1", "packet_dir": "packet"}, f)
    return repo, state


def _lf_drift_repo(tmp: str, ghost: bool) -> tuple[str, str]:
    """Drift repo: cards-dir covering all four BUILDING reqs (no Layer-1(b) drop). ghost=True adds a
    requirement_id NOT in the manifest to an OPEN working-set card → LOCK-FIDELITY-DRIFT-UNLOGGED."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    _lf_copy_packet(repo)
    cards = os.path.join(repo, "cards")
    os.makedirs(cards)
    # cover all four BUILDING reqs across the three module cards (no silent drop)
    b1_reqs = ["REQ-001", "REQ-002"] + (["REQ-999"] if ghost else [])
    _wcard(cards, "b1.yaml", "BUILD-001", "m1", b1_reqs)
    _wcard(cards, "b2.yaml", "BUILD-002", "m2", ["REQ-003"])
    _wcard(cards, "b3.yaml", "BUILD-003", "m3", ["REQ-004"])
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "lf", "protocol_stamp": "Code-X V1", "packet_dir": "packet",
                   "accepted_modules": [], "current_card": "BUILD-001"}, f)
    return repo, state


def _wcard(cards_dir: str, fname: str, cid: str, module_id: str, req_ids: list,
           allowed_files=None, mode="MODULE_BUILD", anchor=None, dev_class=None) -> None:
    card = {"id": cid, "mode": mode, "module_id": module_id,
            "source_map": {"source_sections": [
                {"file": "x", "section": "y", "requirement_ids": req_ids}]}}
    if allowed_files is not None:
        card["allowed_files"] = allowed_files
    if anchor is not None:
        card["lock_anchor_ref"] = anchor
    if dev_class is not None:
        card["deviation_class"] = dev_class
    with open(os.path.join(cards_dir, fname), "w") as f:
        yaml.dump(card, f)


def _lf_mutated_card_repo(tmp: str, mutate, bind_packet_hash: bool = False,
                          seed_packet=None) -> tuple[str, str]:
    """Build an lf card repo from card_fix_good_restore.yaml, then apply mutate(card) to the loaded
    card dict and re-write it. Used to forge a single F2/F3 violation off an otherwise-valid card so
    the clause bites for the RIGHT reason (only the mutated field is wrong)."""
    repo, state = _lf_card_repo(tmp, "card_fix_good_restore.yaml",
                                bind_packet_hash=bind_packet_hash, seed_packet=seed_packet)
    card_dst = os.path.join(repo, "card.yaml")
    with open(card_dst) as f:
        card = yaml.safe_load(f)
    mutate(card)
    with open(card_dst, "w") as f:
        yaml.dump(card, f)
    return repo, state


def _recipe_lf_card_packet_hash_mismatch(tmp: str) -> tuple[str, str]:
    # F2: a valid RESTORE anchor but the card's locked_packet_hash points at a DIFFERENT packet.
    def m(card):
        card.setdefault("source_map", {})["locked_packet_hash"] = "deadbeefdeadbeefdeadbeef"
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=False)


def _recipe_lf_card_anchor_card_not_in_registry(tmp: str) -> tuple[str, str]:
    # F2: valid hash binding, but lock_anchor_ref.card_id names a card NOT in the frozen registry.
    def m(card):
        card.setdefault("lock_anchor_ref", {})["card_id"] = "BUILD-DOES-NOT-EXIST"
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=True)


def _recipe_lf_card_scope_ceo_ref_dangling(tmp: str) -> tuple[str, str]:
    # F3: SCOPE_CHANGE whose ceo_decision_ref does NOT resolve to a packet ledger row (amendment ok).
    def m(card):
        card["deviation_class"] = "SCOPE_CHANGE"
        card["ceo_decision_ref"] = "CEO-D-NOT-IN-LEDGER-999"
        card["packet_amendment_ref"] = "packet/AMENDMENT-001.md"
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=True, seed_packet=_lf_seed_scope_authorization)


def _recipe_lf_card_scope_amend_unsafe(tmp: str) -> tuple[str, str]:
    # F3: SCOPE_CHANGE with a resolving ceo_decision_ref but a path-unsafe packet_amendment_ref.
    def m(card):
        card["deviation_class"] = "SCOPE_CHANGE"
        card["ceo_decision_ref"] = "CEO-D-LOCKFID-001"
        card["packet_amendment_ref"] = "../../etc/passwd"
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=True, seed_packet=_lf_seed_scope_authorization)


def _recipe_lf_card_scope_destructive_p0(tmp: str) -> tuple[str, str]:
    # F3: an UNAUTHORIZED SCOPE_CHANGE on a DESTRUCTIVE surface (touches_upload_restore_import) must
    # escalate to P0 — the class the OLD card_high_risk() missed.
    def m(card):
        card["deviation_class"] = "SCOPE_CHANGE"
        card.pop("ceo_decision_ref", None)
        card.pop("packet_amendment_ref", None)
        card.setdefault("security_tripwire", {})["touches_upload_restore_import"] = True
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=True)


def _recipe_lf_card_no_anchor(tmp: str) -> tuple[str, str]:
    return _lf_card_repo(tmp, "card_fix_no_anchor.yaml")


def _recipe_lf_card_no_devclass(tmp: str) -> tuple[str, str]:
    return _lf_card_repo(tmp, "card_fix_no_devclass.yaml")


def _recipe_lf_card_scope_unauth(tmp: str) -> tuple[str, str]:
    return _lf_card_repo(tmp, "card_fix_scope_change_unauthorized.yaml")


def _recipe_lf_card_good_restore(tmp: str) -> tuple[str, str]:
    return _lf_card_repo(tmp, "card_fix_good_restore.yaml", bind_packet_hash=True)


def _lf_seed_scope_authorization(repo: str) -> None:
    """F3: seed the packet so a GOOD SCOPE_CHANGE's refs resolve — the ledger row CEO-D-LOCKFID-001 in
    the packet's CEO-DECISION-LEDGER.md, and the in-repo packet_amendment_ref packet/AMENDMENT-001.md.
    Called BEFORE bind_packet_hash so these files are part of the hashed packet body."""
    packet = os.path.join(repo, "packet")
    with open(os.path.join(packet, "CEO-DECISION-LEDGER.md"), "w") as f:
        f.write("# CEO Decision Ledger (packet fixture)\n\n"
                "- CEO-D-LOCKFID-001 — authorize the scope expansion this fix builds.\n")
    with open(os.path.join(packet, "AMENDMENT-001.md"), "w") as f:
        f.write("# Packet amendment AMENDMENT-001\nScope expansion authorized by CEO-D-LOCKFID-001.\n")


def _recipe_lf_card_good_scope(tmp: str) -> tuple[str, str]:
    # F3: a GOOD SCOPE_CHANGE must resolve its ceo_decision_ref to the packet ledger AND carry a real
    # in-repo packet_amendment_ref. Seed both into the packet BEFORE the hash is bound so the honest
    # case passes the tightened authorization without breaking the F2 packet-hash binding.
    return _lf_card_repo(tmp, "card_fix_good_scope_change.yaml", bind_packet_hash=True,
                         seed_packet=_lf_seed_scope_authorization)


def _recipe_lf_drift_unlogged(tmp: str) -> tuple[str, str]:
    return _lf_drift_repo(tmp, ghost=True)


def _recipe_lf_drift_ok(tmp: str) -> tuple[str, str]:
    return _lf_drift_repo(tmp, ghost=False)


def _lf_overreach_repo(tmp: str, overreach: bool) -> tuple[str, str]:
    """A fix card anchored to BUILD-001 (allowed src/a.py). overreach=True gives the fix an
    allowed_files entry OUTSIDE BUILD-001's set → LOCK-FIDELITY-RESTORE-OVERREACH."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    _lf_copy_packet(repo)
    cards = os.path.join(repo, "cards")
    os.makedirs(cards)
    _wcard(cards, "b1.yaml", "BUILD-001", "m1", ["REQ-001", "REQ-002"], allowed_files=["src/a.py"])
    _wcard(cards, "b2.yaml", "BUILD-002", "m2", ["REQ-003"])
    _wcard(cards, "b3.yaml", "BUILD-003", "m3", ["REQ-004"])
    fix_files = ["src/a.py"] + (["src/OTHER.py"] if overreach else [])
    _wcard(cards, "fix.yaml", "FIX-OVR", "m1", ["REQ-001"], allowed_files=fix_files, mode="FIX",
           anchor={"card_id": "BUILD-001", "requirement_id": "REQ-001"}, dev_class="RESTORE")
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "lf", "protocol_stamp": "Code-X V1", "packet_dir": "packet",
                   "accepted_modules": [], "current_card": "FIX-OVR"}, f)
    return repo, state


def _recipe_lf_overreach(tmp: str) -> tuple[str, str]:
    return _lf_overreach_repo(tmp, overreach=True)


def _recipe_lf_overreach_ok(tmp: str) -> tuple[str, str]:
    return _lf_overreach_repo(tmp, overreach=False)


_LF_HANDOFF = """# Handoff — lock-fidelity fixture

```yaml
close_turn:
  findings_delta: []
  evidence_paths: [evidence.txt]
  next_prompt: |
    Continue per the deck.
  lock_pointer:
    frozen_packet_hash: {hash}
    open_cards: {open}
    lock_restatement_assertion: "no requirement added/dropped since {assert_hash}"
  vault_sync:
    status: NOT_APPLICABLE
    reason: contract-test
    where_saved: committed in the fixture repo
```
"""


def _lf_close_turn_repo(tmp: str, hash_val, open_val, assert_val) -> tuple[str, str]:
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    real = _lf_copy_packet(repo)
    _git_init(repo)
    with open(os.path.join(repo, "evidence.txt"), "w") as f:
        f.write("evidence\n")
    handoff = os.path.join(repo, "handoff.md")
    with open(handoff, "w") as f:
        f.write(_LF_HANDOFF.format(
            hash=(real if hash_val == "REAL" else hash_val),
            open=open_val,
            assert_hash=(real if assert_val == "REAL" else assert_val)))
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                    "lf fixture\n\nCode-X-Provenance: cx-contract-test"], check=True)
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.dump({"project": "lf", "protocol_stamp": "Code-X V1", "packet_dir": "packet",
                   "accepted_modules": [],
                   "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []}}, f)
    return repo, state


def _recipe_lf_handoff_hash_mismatch(tmp: str) -> tuple[str, str]:
    # correct open cards, WRONG hash → HANDOFF-HASH-MISMATCH
    return _lf_close_turn_repo(tmp, "deadbeefw0ng", "[BUILD-001, BUILD-002, BUILD-003]", "REAL")


def _recipe_lf_handoff_opencards_mismatch(tmp: str) -> tuple[str, str]:
    # correct hash, VACUOUS open_cards: [] (the forgery) → HANDOFF-OPENCARDS-MISMATCH
    return _lf_close_turn_repo(tmp, "REAL", "[]", "REAL")


def _recipe_lf_handoff_ok(tmp: str) -> tuple[str, str]:
    return _lf_close_turn_repo(tmp, "REAL", "[BUILD-001, BUILD-002, BUILD-003]", "REAL")


# ── PROP-035 fixing-stage recipes ───────────────────────────────────────────────
_FS_LOCK_SRC_FILES = ("src/a.py", "src/b.py")


def _fs_emit_lock(repo: str, *, generator="cx check structure --emit", bad_hash=False, roots=("src",),
                  paths_override=None) -> None:
    """Emit a structure_lock receipt at meta/sl.yaml bound to the repo's current HEAD (the same recipe
    cx check structure recomputes). bad_hash forges the manifest_sha; a non-default generator forges the
    machine marker; paths_override forges the paths LIST (omitting a real tracked file) while still
    recomputing a self-consistent hash over the forged list — so only TREE-BOUND (ls-tree at commit) catches
    the omission, not HASH-RECOMPUTE."""
    sys.path.insert(0, str(CHECKERS_DIR))
    from cx_structure import recompute_manifest_sha
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    paths = list(paths_override) if paths_override is not None else list(_FS_LOCK_SRC_FILES)
    sha = "deadbeef0000" if bad_hash else recompute_manifest_sha(head, paths)
    os.makedirs(os.path.join(repo, "meta"), exist_ok=True)
    lock = {"structure_lock": {"generator": generator, "accepted_at_commit": head,
                               "roots": list(roots), "paths": paths, "manifest_sha": sha}}
    with open(os.path.join(repo, "meta", "sl.yaml"), "w") as f:
        yaml.safe_dump(lock, f)


def _fs_struct_repo(tmp, *, ref="meta/sl.yaml", generator="cx check structure --emit", bad_hash=False,
                    drift=False, forge_paths=None) -> tuple[str, str]:
    """A git repo with src/{a,b}.py committed + a structure_lock + a mode: FIX card at cards/fix.yaml.
    The structure clause references {REPO}/cards/fix.yaml + --repo-root {REPO} (state slot unused).
    forge_paths: emit the lock with this paths list (omitting a real tracked file) to exercise TREE-BOUND."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "src"))
    os.makedirs(os.path.join(repo, "cards"))
    for f in _FS_LOCK_SRC_FILES:
        with open(os.path.join(repo, f), "w") as fh:
            fh.write("x = 1\n")
    _git_init(repo)
    subprocess.run(["git", "-C", repo, "add", "src"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "init"], check=True)
    _fs_emit_lock(repo, generator=generator, bad_hash=bad_hash, paths_override=forge_paths)
    card = {"id": "FIX-OVR", "mode": "FIX", "allowed_files": ["src/a.py"],
            "fix_targets": [{"target": "business_rule"}]}
    if ref is not None:
        card["structure_lock_ref"] = ref
    with open(os.path.join(repo, "cards", "fix.yaml"), "w") as f:
        yaml.safe_dump(card, f)
    if drift:  # an untracked file outside allowed_files → structural drift vs the frozen lock
        with open(os.path.join(repo, "src", "sneaky.py"), "w") as f:
            f.write("y = 2\n")
    return repo, repo


def _recipe_fs_struct_good(tmp): return _fs_struct_repo(tmp)
def _recipe_fs_struct_nolockref(tmp): return _fs_struct_repo(tmp, ref=None)
def _recipe_fs_struct_pathsafe(tmp): return _fs_struct_repo(tmp, ref="../../etc/passwd")
def _recipe_fs_struct_forged(tmp): return _fs_struct_repo(tmp, generator="hand-authored")
def _recipe_fs_struct_badhash(tmp): return _fs_struct_repo(tmp, bad_hash=True)
def _recipe_fs_struct_manifest(tmp): return _fs_struct_repo(tmp, drift=True)
# TREE-BOUND: the lock's paths OMIT src/b.py (a file still tracked at the commit) but recompute a
# self-consistent hash over the forged list — HASH-RECOMPUTE passes; only the ls-tree binding catches it.
def _recipe_fs_struct_paths_forged(tmp): return _fs_struct_repo(tmp, forge_paths=["src/a.py"])


def _recipe_fs_struct_rail(tmp) -> tuple[str, str]:
    """build-turn over a mode: FIX card whose structure_lock is FORGED → the structure sub-check fires
    INSIDE build-turn = the rail is wired (FIX-STAGE-STRUCT-RAIL). The card passes its own card/scope/
    evidence/tests sub-checks (built on the build_turn fixture), so structure is the sole failure."""
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    _fs_emit_lock(repo, generator="hand-authored")  # forged generator → structure bites before tree compare
    cpath = os.path.join(repo, "card.yaml")
    with open(cpath) as f:
        card = yaml.safe_load(f)
    card["mode"] = "FIX"
    card["lock_anchor_ref"] = {"card_id": "BUILD-001", "requirement_id": "REQ-001"}
    card["deviation_class"] = "RESTORE"
    card["fix_targets"] = [{"target": "business_rule", "reason": "restore the locked module"}]
    card["structure_lock_ref"] = "meta/sl.yaml"
    with open(cpath, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "fix card\n\nCode-X-Provenance: cx-test"], check=True)
    return repo, state


def _recipe_fs_struct_rail_ok(tmp) -> tuple[str, str]:
    """GOOD (built-code review #9): a VALID mode: FIX card with a REAL structure_lock passes the full
    build-turn rail (card · scope · structure · tests all green) — proves the rail's green path, not just
    that a forgery bites. The lock is emitted bound to the PRIOR (build-turn) commit over the real src tree
    {src/app.py}; the fix commits cleanly so the live tree matches the frozen lock (empty diff)."""
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    # The FIX card's lock-fidelity anchor resolves the packet from the STATE file's dir (Path(state).parent).
    # _build_turn_repo parks state at tmp/ (the repo's PARENT), so packet_dir 'packet' would resolve to
    # tmp/packet (missing). Re-home the state INSIDE the repo so 'packet' -> repo/packet resolves.
    in_repo_state = os.path.join(repo, "state.yaml")
    _shutil.copyfile(state, in_repo_state)
    state = in_repo_state
    # bind the lock to the build-turn commit (current HEAD) over the REAL src tree, not the default a/b.py
    _fs_emit_lock(repo, roots=("src",), paths_override=["src/app.py"])
    cpath = os.path.join(repo, "card.yaml")
    with open(cpath) as f:
        card = yaml.safe_load(f)
    card["mode"] = "FIX"
    card["lock_anchor_ref"] = {"card_id": "BUILD-001", "requirement_id": "REQ-001"}  # resolves in the packet
    card["deviation_class"] = "RESTORE"
    card["fix_targets"] = [{"target": "business_rule", "reason": "restore the locked module",
                            "surfaces": ["src/*"]}]  # covers allowed_files src/app.py
    card["structure_lock_ref"] = "meta/sl.yaml"
    with open(cpath, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "fix card\n\nCode-X-Provenance: cx-test"], check=True)
    return repo, state


_FS_QLOG_HANDOFF = """# Handoff — fixing-stage fixture

```yaml
close_turn:
  findings_delta: []
  evidence_paths: [evidence.txt]
  next_prompt: |
    Continue per the deck.
  lock_pointer:
    frozen_packet_hash: {hash}
    open_cards: {open}
    lock_restatement_assertion: "no requirement added/dropped since {hash}"
  fix_questions:
    log_ref: FIX-QUESTIONS-LOG.yaml
    open_questions:
      - id: Q1
        log_row: {log_row}
  vault_sync:
    status: NOT_APPLICABLE
    reason: contract-test
    where_saved: committed in the fixture repo
```
"""


def _fs_qlog_repo(tmp, row_in_log: bool) -> tuple[str, str]:
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    real = _lf_copy_packet(repo)
    _git_init(repo)
    with open(os.path.join(repo, "evidence.txt"), "w") as f:
        f.write("evidence\n")
    with open(os.path.join(repo, "FIX-QUESTIONS-LOG.yaml"), "w") as f:  # typed log (built-code review #6)
        yaml.safe_dump({"fix_questions": [
            {"id": "Q-IN-LOG", "question": "should the date format stay dd/mm?"}]}, f)
    log_row = "Q-IN-LOG" if row_in_log else "Q-NOT-IN-LOG"
    with open(os.path.join(repo, "handoff.md"), "w") as f:
        f.write(_FS_QLOG_HANDOFF.format(hash=real, open="[BUILD-001, BUILD-002, BUILD-003]", log_row=log_row))
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "fs qlog\n\nCode-X-Provenance: cx-test"], check=True)
    state = os.path.join(tmp, "state.yaml")
    with open(state, "w") as f:
        yaml.safe_dump({"project": "fs", "protocol_stamp": "Code-X V1", "packet_dir": "packet",
                        "accepted_modules": [],
                        "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []}}, f)
    return repo, state


def _recipe_fs_qlog_unreconciled(tmp): return _fs_qlog_repo(tmp, row_in_log=False)
def _recipe_fs_qlog_ok(tmp): return _fs_qlog_repo(tmp, row_in_log=True)


# Card-level fix clauses — mutate the PROP-034 good restore card so ONLY the PROP-035 field is wrong.
def _recipe_fs_posture_no_targets(tmp):
    def m(c): c.pop("fix_targets", None)
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=True)


def _recipe_fs_multi_anchor(tmp):
    def m(c):
        # both targets declare surfaces (required, built-code review #4) so ONLY MULTI-ANCHOR fires
        c["fix_targets"] = [
            {"target": "frontend", "lock_anchor_ref": {"card_id": "BUILD-001", "requirement_id": "REQ-001"},
             "reason": "the button label", "surfaces": ["checkers/*"]},
            {"target": "business_rule", "surfaces": ["checkers/*"]}]  # 2nd target lacks its own anchor + reason
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=True)


def _recipe_fs_xlock_surface(tmp):
    def m(c):
        c["fix_targets"] = [{"target": "frontend", "surfaces": ["checkers/cx"]}]
        c["allowed_files"] = ["checkers/cx", "checkers/tests/test_cx.py"]  # test_cx.py outside the surface
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=True)


def _recipe_fs_revert_missing(tmp):
    def m(c): c["drift_recovery_required"] = True  # no revert_receipt
    return _lf_mutated_card_repo(tmp, m, bind_packet_hash=True)


def _fs_amnesia_repo(tmp, cp, *, log_ids=("Q1",), write_log=True) -> tuple[str, str]:
    """Build an lf card repo (card_fix_good_restore + the CEO-D-LOCKFID-001 packet ledger seed) with
    clarification_provenance=cp and a typed FIX-QUESTIONS-LOG.yaml carrying log_ids (built-code review #5:
    the file-backing is REAL now — a card receipt is not enough). write_log=False omits the log so the
    LOG-BACKED bite fires. cp should set fix_questions_log: FIX-QUESTIONS-LOG.yaml to point at it."""
    def m(c):
        c["clarification_provenance"] = cp
    repo, state = _lf_mutated_card_repo(tmp, m, bind_packet_hash=True,
                                        seed_packet=_lf_seed_scope_authorization)
    if write_log:
        with open(os.path.join(repo, "FIX-QUESTIONS-LOG.yaml"), "w") as f:
            yaml.safe_dump({"fix_questions": [{"id": rid, "question": f"q {rid}"} for rid in log_ids]}, f)
    return repo, state


_FS_AMNESIA_LOG = "FIX-QUESTIONS-LOG.yaml"


def _recipe_fs_amnesia_ghost(tmp):
    return _fs_amnesia_repo(tmp, {"fix_questions_log": _FS_AMNESIA_LOG, "questions": [
        {"id": "Q1", "ledger_searched": True, "related_ceo_d_refs": ["CEO-D-GHOST-999"]}]})


def _recipe_fs_amnesia_contradiction(tmp):
    return _fs_amnesia_repo(tmp, {"fix_questions_log": _FS_AMNESIA_LOG, "questions": [
        {"id": "Q1", "contradicts_ceo_d": "CEO-D-LOCKFID-001"}]})  # no ceo_override_ref


def _recipe_fs_amnesia_override_unsafe(tmp):
    return _fs_amnesia_repo(tmp, {"fix_questions_log": _FS_AMNESIA_LOG, "questions": [
        {"id": "Q1", "contradicts_ceo_d": "CEO-D-LOCKFID-001", "ceo_override_ref": "../../etc/passwd"}]})


def _recipe_fs_amnesia_unlogged(tmp):
    # LOG-BACKED (built-code review #5): the question's id is NOT a row in the file-backed log (resolution
    # is otherwise valid) → only FIX-STAGE-AMNESIA-LOG-BACKED fires.
    return _fs_amnesia_repo(tmp, {"fix_questions_log": _FS_AMNESIA_LOG, "questions": [
        {"id": "Q1", "ledger_searched": True, "related_ceo_d_refs": ["CEO-D-LOCKFID-001"]}]},
        log_ids=("Q-OTHER",))


def _recipe_fs_card_good_amnesia(tmp):
    return _fs_amnesia_repo(tmp, {"fix_questions_log": _FS_AMNESIA_LOG, "questions": [
        {"id": "Q1", "ledger_searched": True, "related_ceo_d_refs": ["CEO-D-LOCKFID-001"]}]})


def _build_turn_blueprint_repo(tmp: str, *, blueprint_ready: bool) -> tuple[str, str]:
    """PROP-039: a build-turn over a module-advancing card whose target module 'm1' is the first
    module (no priors, so the v1.10 order wall is clear) — the SOLE variable is BLUEPRINT-READY. The
    frozen packet carries a blueprint-manifest (screen/module-first project) so cx check module-start
    runs the MODULE-START-BLUEPRINT-READY precondition (= cx check blueprint). blueprint_ready=False
    pins a STALE approved_source_hash → the precondition fails → build-turn surfaces it via the
    module-start sub-check (proves the rider fires THROUGH build-turn, P2-1). blueprint_ready=True =
    correct hashes → PASS."""
    import hashlib
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    with open(FIXTURES / "card_good.yaml") as f:
        card = yaml.safe_load(f)
    os.makedirs(os.path.join(repo, "src"), exist_ok=True)
    with open(os.path.join(repo, "src", "app.py"), "w") as f:
        f.write("# build-turn blueprint fixture module\n")
    with open(os.path.join(repo, "evidence.txt"), "w") as f:
        f.write("build-turn blueprint fixture evidence: src/app.py exists\n")

    # ── frozen packet: requirements + registry + blueprint-manifest (single shared_logic module m1) ──
    packet = os.path.join(repo, "packet")
    os.makedirs(packet, exist_ok=True)
    req_src = "REQ-001: m1 does the thing\n"
    with open(os.path.join(packet, "req-source.md"), "w") as f:
        f.write(req_src)
    with open(os.path.join(packet, "requirements-manifest.yaml"), "w") as f:
        yaml.safe_dump({"requirements": [
            {"id": "REQ-001", "disposition": "BUILDING",
             "acceptance_criterion": {"pass_condition": "m1 renders", "evidence_type": "screenshot",
                                      "verification_ref": "cards/m1#ac"}}]}, f, sort_keys=False)
    with open(os.path.join(packet, "MODULE-REGISTRY.yaml"), "w") as f:
        yaml.safe_dump({"module_registry": {"frozen_packet_hash": "bp", "modules": [
            {"module_id": "m1", "kind": "shared_logic", "requirement_ids": ["REQ-001"],
             "risk_flags": [], "dependency_modules": []}]}}, f, sort_keys=False)
    line1_hash = hashlib.sha256(req_src.splitlines()[0].encode()).hexdigest()
    anchors = [{"anchor_id": "req:REQ-001", "file": "req-source.md", "section": "REQ-001",
                "line": 1, "requirement_id": "REQ-001", "source_hash": line1_hash}]
    with open(os.path.join(packet, "blueprint-manifest.yaml"), "w") as f:
        yaml.safe_dump({"blueprint_manifest": {"generator_version": "0.1.0", "modules": [
            {"module_id": "m1", "screen_id": None, "kind": "shared_logic", "title": "m1",
             "design_nav_na_reason": "shared_logic — no screen", "anchors": anchors,
             "user_journeys": [], "risk_callouts": []}]}}, f, sort_keys=False)

    card.setdefault("source_map", {})["locked_packet_hash"] = _packet_hash(packet)
    card["allowed_files"] = ["src/app.py"]
    card["evidence_required"] = ["evidence.txt"]
    card["module_id"] = "m1"
    card["test_command"] = "git --version"
    card["coderabbit"] = {"required": "yes", "receipt": "reviews/coderabbit-review.yaml"}
    with open(os.path.join(repo, "card.yaml"), "w") as f:
        yaml.safe_dump(card, f)

    # ── approval receipt OUTSIDE the packet (committed in repo, repo-relative ref) ──
    manifest_hash = hashlib.sha256(
        Path(os.path.join(packet, "blueprint-manifest.yaml")).read_bytes()).hexdigest()
    packet_hash = _packet_hash(packet)
    src_hash = hashlib.sha256(f"req:REQ-001:{line1_hash}".encode()).hexdigest()
    approved = src_hash if blueprint_ready else ("deadbeef" * 8)
    os.makedirs(os.path.join(repo, "approvals"), exist_ok=True)
    with open(os.path.join(repo, "approvals", "BLUEPRINT-APPROVAL.yaml"), "w") as f:
        yaml.safe_dump({"blueprint_approval": {
            "packet_hash": packet_hash, "manifest_hash": manifest_hash,
            "modules": [{"module_id": "m1", "approved_source_hash": approved,
                         "ceo_approval": {"approved_by": "CEO", "approved_at": "2026-06-25"}}]}},
            f, sort_keys=False)

    # PROP-040: a valid whole-packet integration review receipt so the new step-12 gate PASSES on this
    # module-advancing build (the SOLE variable here is BLUEPRINT-READY, not the whole-packet review).
    os.makedirs(os.path.join(repo, "reviews"), exist_ok=True)
    _wpr = {"whole_packet_review": {
        "schema_version": 1, "review_kind": "WHOLE_PACKET_G7", "frozen_packet_hash": packet_hash,
        "reviewed_source_set_hash": _substantive_hash(packet),
        "authoring_family": "anthropic", "reviewer_family": "gpt",
        "three_leg_ask": {"continuity": "prior decisions re-checked", "problems": "no P0; drift swept",
                          "approach_improvement": "no simpler structure found"},
        "verdict": "PASS", "findings_ref": "reviews/whole-packet-review.md"}}
    _wpr_path = os.path.join(repo, "reviews", "whole-packet-review.yaml")
    with open(_wpr_path, "w") as f:
        yaml.safe_dump(_wpr, f)
    _wpr_hash = hashlib.sha256(open(_wpr_path, "rb").read()).hexdigest()[:12]
    _egress_path = os.path.join(repo, "reviews", "coderabbit-egress.yaml")
    with open(_egress_path, "w") as f:
        yaml.safe_dump({"egress_scrub": {"target": "coderabbit", "diff_hash": "fixture"}}, f)
    _cr = {"coderabbit_review": {
        "commit": "abcdef012345",
        "diff_hash": "fixture-diff",
        "tool_version": "fixture",
        "findings_hash": "fixture-findings",
        "egress_receipt_ref": "reviews/coderabbit-egress.yaml",
        "produced_at": "2026-06-29T00:00:00Z",
    }}
    with open(os.path.join(repo, "reviews", "coderabbit-review.yaml"), "w") as f:
        yaml.safe_dump(_cr, f)

    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    sha = _git_commit(repo, "build-turn blueprint fixture")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, overrides={"packet_dir": "packet",
                                        "module_registry_ref": "packet/MODULE-REGISTRY.yaml",
                                        "blueprint_approval_ref": "approvals/BLUEPRINT-APPROVAL.yaml",
                                        "whole_packet_review_receipt": {
                                            "receipt": "reviews/whole-packet-review.yaml",
                                            "receipt_hash": _wpr_hash}})
    return repo, state


def _recipe_build_turn_blueprint_not_ready(tmp: str) -> tuple[str, str]:
    return _build_turn_blueprint_repo(tmp, blueprint_ready=False)


def _recipe_build_turn_blueprint_ready(tmp: str) -> tuple[str, str]:
    return _build_turn_blueprint_repo(tmp, blueprint_ready=True)


def _recipe_build_turn_blueprint_approval_symlink(tmp: str) -> tuple[str, str]:
    """CXBP-005: a BLUEPRINT-READY repo where state.blueprint_approval_ref points at a SYMLINK whose
    target is OUTSIDE the repo — the rider's safe_repo_ref must reject it (the PROP-037 class, not just
    absolute/'..'). The plan itself is ready, so the symlink ref is the SOLE failure."""
    repo, state = _build_turn_blueprint_repo(tmp, blueprint_ready=True)
    # an external file the symlink will point at (outside the repo)
    external = os.path.join(tmp, "outside-approval.yaml")
    with open(external, "w") as f:
        f.write("blueprint_approval: {}\n")
    # replace the in-repo approval with a symlink to the external file
    link = os.path.join(repo, "approvals", "BLUEPRINT-APPROVAL.yaml")
    os.remove(link)
    os.symlink(external, link)
    # state.blueprint_approval_ref already = approvals/BLUEPRINT-APPROVAL.yaml (now a symlink)
    return repo, state


# ── PBF-PROP-018 accepted-surface recipes (xfam-fold 2026-07-03: binding, ledger, evidence) ─────
_AS_MODULE_ID = "trans-shell"
_AS_SHARED_MODULE_ID = "cowork-pane"
_AS_FILE = "templates/trans/_shell.html"
_AS_SHARED_FILE = "templates/trans/other_accepted.html"
_AS_FULL_SUITE_CMD = "pytest tests/"
_AS_SHELL_CONTENT = (
    '{% extends "base.html" %}\n'
    '{% include "cowork/_ask_pane.html" %}\n'
    '<script src="app.js"></script>\n'
    '<script>function navSwipe() { return 1; }</script>\n'
    '<link rel="stylesheet" href="trans.css">\n'
    '<div data-fn="submit"></div>\n'
    '<button onclick="doThing()">x</button>\n'
    '<a href="/trans?lang=en">EN</a>\n'
)
# Built-code xfam P1-1: valid HTML/JS variants the old regexes missed — attr order swapped on
# <link>, spaces around = on data-fn, a class-based dispatcher, a window-global assignment,
# and an addEventListener wire-up.
_AS_VARIANT_CONTENT = (
    '{% include "cowork/_ask_pane.html" %}\n'
    '<link href="trans.css" rel="stylesheet">\n'
    '<div data-fn = "submit"></div>\n'
    '<script>\n'
    'class NavSwipe { constructor() {} }\n'
    'window.NavSwipe = new NavSwipe();\n'
    'document.addEventListener("touchstart", h);\n'
    '</script>\n'
)


def _as_full_inventory(accepted_commit: str, dangling_ceo_ref=False, drop_last=False) -> list:
    def row(cap, **disp):
        r = {"capability": cap, "extracted_from": {"commit": accepted_commit, "path": _AS_FILE}}
        r.update(disp or {"re_homed_to": "templates/trans/new_shell.html"})
        return r
    rows = [
        row("extends:base.html", re_homed_to="templates/trans/new_shell.html"),
        row("include:cowork/_ask_pane.html", re_homed_to="templates/trans/new_shell.html"),
        row("script:app.js", re_homed_to="templates/trans/new_shell.html"),
        row("script-fn:navSwipe", re_homed_to="static/swipe.js"),
        row("stylesheet:trans.css", re_homed_to="templates/trans/new_shell.html"),
        row("data-fn:submit", re_homed_to="templates/trans/new_shell.html"),
        row("handler:onclick", re_homed_to="templates/trans/new_shell.html"),
        row("link-query:/trans?lang=en",
            dropped_ceo_decision_ref="CEO-D-999" if dangling_ceo_ref else "CEO-D-099"),
    ]
    if drop_last:
        rows = rows[:-1]
    return rows


def _as_write_manifest(repo: str, name: str, module_id: str, accepted_commit: str,
                       owned: list, shared: list, bad_binding: bool = False) -> None:
    """Write one legacy manifest + its typed, HASH-BOUND legacy-freeze receipt (P1-4 binding).

    bad_binding=True (PBF-PROP-021 F17 systemic scar — ACCEPTED-SURFACE-MANIFEST-BINDING had NO
    pinned bad fixture anywhere): the freeze receipt's frozen_commit DISAGREES with the manifest's
    accepted_commit — the manifest's commit must come FROM the freeze receipt, never a self-declared
    value the receipt doesn't actually back."""
    os.makedirs(os.path.join(repo, "receipts"), exist_ok=True)
    freeze_rel = f"receipts/{name}-freeze.yaml"
    freeze_path = os.path.join(repo, freeze_rel)
    frozen_commit = accepted_commit
    if bad_binding:
        frozen_commit = ("0" if accepted_commit[0] != "0" else "1") + accepted_commit[1:]
    with open(freeze_path, "w") as f:
        yaml.safe_dump({"legacy_freeze_baseline": {
            "frozen_commit": frozen_commit, "generated_by": "cx-test-legacy-freeze"}}, f)
    freeze_hash = _hashlib.sha256(open(freeze_path, "rb").read()).hexdigest()[:12]
    manifest = {"accepted_surface_manifest": {
        "module_id": module_id, "accepted_commit": accepted_commit,
        "acceptance_ref": "legacy_freeze_baseline",
        "legacy_freeze_ref": freeze_rel, "legacy_freeze_hash": freeze_hash,
        "owned_files": owned, "shared_files": shared,
        "routes_screens": ["/trans"], "full_suite_command": _AS_FULL_SUITE_CMD,
        "generated_by": "cx-test-legacy-freeze"}}
    with open(os.path.join(repo, "accepted-surface-manifests", f"{name}.yaml"), "w") as f:
        yaml.safe_dump(manifest, f)


def _as_regression_receipt(repo: str, baseline_sha: str, *, narrow=False) -> dict:
    """Evidence-bound regression receipt (P1-3): real log files, recomputed sha256, configured
    full-suite command. narrow=True forges the bad case (card-scoped command, arbitrary hashes,
    NO log files on disk)."""
    if narrow:
        return {"baseline_sha": baseline_sha,
                "full_suite_command": "pytest tests/nav/test_trans_shell.py",
                "baseline_log_hash": "aaa111", "post_change_log_hash": "bbb222",
                "baseline_log_ref": "logs/baseline.log", "post_change_log_ref": "logs/post.log",
                "diff_summary": "no regressions", "generated_by": "cx-test-regression-runner"}
    os.makedirs(os.path.join(repo, "logs"), exist_ok=True)
    b_path = os.path.join(repo, "logs", "baseline.log")
    p_path = os.path.join(repo, "logs", "post.log")
    with open(b_path, "w") as f:
        f.write("== full suite @ baseline: 120 passed ==\n")
    with open(p_path, "w") as f:
        f.write("== full suite @ post-change: 120 passed ==\n")
    return {"baseline_sha": baseline_sha, "full_suite_command": _AS_FULL_SUITE_CMD,
            "baseline_log_hash": _hashlib.sha256(open(b_path, "rb").read()).hexdigest(),
            "post_change_log_hash": _hashlib.sha256(open(p_path, "rb").read()).hexdigest(),
            "baseline_log_ref": "logs/baseline.log", "post_change_log_ref": "logs/post.log",
            "diff_summary": "no regressions", "generated_by": "cx-test-regression-runner"}


def _as_repo(tmp, *, with_manifest=True, incomplete_inventory=False, dangling_ceo_ref=False,
            missing_regression=False, narrow_regression=False, missing_shared_coverage=False,
            add_shared_manifest=False, diff_undeclared=False, keep_narrow=False,
            fix_scope_change=False, no_contract=False, shell_content=_AS_SHELL_CONTENT,
            with_ledger=True, bad_binding=False) -> tuple:
    """Base recipe for every PBF-PROP-018 accepted-surface clause. Returns (repo, extra) where
    extra is either the repo again (unused-state convention) or, for diff_undeclared, the
    pre-build baseline sha (substituted via the harness's {STATE} token — the ONLY value that
    token carries here, not a state-file path)."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "templates", "trans"))
    os.makedirs(os.path.join(repo, "accepted-surface-manifests"))
    with open(os.path.join(repo, _AS_FILE), "w") as f:
        f.write(shell_content)
    with open(os.path.join(repo, _AS_SHARED_FILE), "w") as f:
        f.write("<p>shared partial</p>\n")
    _git_init(repo)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "accept trans-shell"], check=True)
    accepted_commit = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                                     capture_output=True, text=True).stdout.strip()

    # Decision ledger (P1-2): drop refs resolve against real CEO-D rows, fail closed without it.
    if with_ledger:
        with open(os.path.join(repo, "CEO-DECISION-LEDGER.md"), "w") as f:
            f.write("# CEO Decision Ledger (fixture)\n\n"
                    "- id: CEO-D-099 — drop the ?lang= switcher from the killed shell\n")

    if with_manifest:
        _as_write_manifest(repo, "trans-shell", _AS_MODULE_ID, accepted_commit,
                           owned=[_AS_FILE],
                           shared=[_AS_SHARED_FILE] if add_shared_manifest else [],
                           bad_binding=bad_binding)
    if add_shared_manifest:
        _as_write_manifest(repo, "cowork-pane", _AS_SHARED_MODULE_ID, accepted_commit,
                           owned=[], shared=[_AS_SHARED_FILE])

    pc = {
        "accepted_surfaces": [_AS_MODULE_ID],
        "inventory": _as_full_inventory(accepted_commit, dangling_ceo_ref=dangling_ceo_ref,
                                        drop_last=incomplete_inventory),
        "accepted_surface_regression_receipt": _as_regression_receipt(
            repo, accepted_commit, narrow=narrow_regression),
    }
    if missing_regression:
        pc.pop("accepted_surface_regression_receipt")

    allowed_files = [_AS_FILE]
    if add_shared_manifest and not keep_narrow:
        # card also touches the shared file — accepted_surfaces must cover BOTH owning modules
        # unless missing_shared_coverage deliberately omits the second (the bad-fixture case).
        allowed_files = [_AS_FILE, _AS_SHARED_FILE]
        if not missing_shared_coverage:
            pc["accepted_surfaces"] = [_AS_MODULE_ID, _AS_SHARED_MODULE_ID]

    if fix_scope_change:
        # Built-code xfam P2-1: a FIX card with SCOPE_CHANGE touching an accepted file may NOT
        # ride the lock anchor alone — new scope needs the preserve_contract.
        card = {"id": "CARD-NS-TRANS", "mode": "FIX", "deviation_class": "SCOPE_CHANGE",
                "lock_anchor_ref": {"card_id": "BUILD-001", "requirement_id": "REQ-001"},
                "allowed_files": allowed_files,
                "allowed_operations": ["delete-killed-partials"]}
    elif no_contract:
        # Built-code xfam P2-2: the direct MANIFEST-REQUIRED bad case — a MODULE_BUILD card
        # touching an owned accepted file with no FIX anchor and no preserve_contract.
        card = {"id": "CARD-NS-TRANS", "mode": "MODULE_BUILD", "new_locked_scope": True,
                "allowed_files": allowed_files,
                "allowed_operations": ["delete-killed-partials"]}
    else:
        card = {"id": "CARD-NS-TRANS", "mode": "MODULE_BUILD", "new_locked_scope": True,
                "allowed_files": allowed_files, "allowed_operations": ["delete-killed-partials"],
                "preserve_contract": pc}
    with open(os.path.join(repo, "card.yaml"), "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "wave card"], check=True)

    if diff_undeclared:
        baseline_sha = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                                      capture_output=True, text=True).stdout.strip()
        # the ACTUAL build touches the shared file too, without declaring it in allowed_files
        with open(os.path.join(repo, _AS_SHARED_FILE), "a") as f:
            f.write("<p>silently rewritten</p>\n")
        subprocess.run(["git", "-C", repo, "commit", "-aq", "-m", "undeclared touch"], check=True)
        return repo, baseline_sha

    return repo, repo


def _recipe_as_legacy_no_manifest(tmp):
    return _as_repo(tmp, with_manifest=False)


def _recipe_as_incomplete_inventory(tmp):
    return _as_repo(tmp, incomplete_inventory=True)


def _recipe_as_fake_ceo_ref(tmp):
    # P1-2: CEO-D-999 is format-valid but has no matching ledger row → dangling, must FAIL.
    return _as_repo(tmp, dangling_ceo_ref=True)


def _recipe_as_missing_regression(tmp):
    return _as_repo(tmp, missing_regression=True)


def _recipe_as_narrow_regression(tmp):
    # P1-3: card-scoped command + arbitrary hashes + no log files on disk → must FAIL.
    return _as_repo(tmp, narrow_regression=True)


def _recipe_as_missing_shared_coverage(tmp):
    return _as_repo(tmp, add_shared_manifest=True, missing_shared_coverage=True)


def _recipe_as_diff_undeclared(tmp):
    return _as_repo(tmp, add_shared_manifest=True, keep_narrow=True, diff_undeclared=True)


def _recipe_as_fix_scope_change(tmp):
    return _as_repo(tmp, fix_scope_change=True)


def _recipe_as_no_contract(tmp):
    return _as_repo(tmp, no_contract=True)


def _recipe_as_bad_binding(tmp):
    # PBF-PROP-021 F17 systemic scar: ACCEPTED-SURFACE-MANIFEST-BINDING had NO pinned bad fixture
    # anywhere in the harness. The legacy-freeze receipt's frozen_commit disagrees with the
    # manifest's accepted_commit — a self-declared commit the receipt does not actually back.
    return _as_repo(tmp, bad_binding=True)


def _recipe_as_extractor_variants(tmp):
    # P1-1: baseline file uses valid HTML/JS variants (attr order, spaced data-fn, class/window
    # dispatcher, addEventListener); the inventory covers only the include row → the recomputed
    # extraction must surface the omitted variants as missing rows.
    repo, extra = _as_repo(tmp, shell_content=_AS_VARIANT_CONTENT)
    accepted_commit = None
    # rewrite the card's inventory down to the single include row (the forgeable-thin inventory)
    card_path = os.path.join(repo, "card.yaml")
    with open(card_path) as f:
        card = yaml.safe_load(f)
    full = card["preserve_contract"]["inventory"]
    accepted_commit = full[0]["extracted_from"]["commit"]
    card["preserve_contract"]["inventory"] = [
        {"capability": "include:cowork/_ask_pane.html",
         "extracted_from": {"commit": accepted_commit, "path": _AS_FILE},
         "re_homed_to": "templates/trans/new_shell.html"}]
    with open(card_path, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "commit", "-aq", "-m", "thin inventory"], check=True)
    return repo, extra


def _recipe_as_stale_accepted_commit(tmp):
    # P1-4: the manifest (and its freeze receipt) bind to an OLDER commit where the file was
    # THIN; the wave baseline (HEAD) carries the rich file. Extraction must run against the
    # union — the richer set governs — so an inventory covering only the thin version FAILS.
    # Returns (repo, baseline_sha): the harness's {STATE} token carries the baseline sha.
    repo, _ = _as_repo(tmp, shell_content="<p>thin placeholder</p>\n")
    # enrich the file AFTER the freeze; that commit is the wave baseline
    with open(os.path.join(repo, _AS_FILE), "w") as f:
        f.write(_AS_SHELL_CONTENT)
    subprocess.run(["git", "-C", repo, "commit", "-aq", "-m", "screen grew after freeze"], check=True)
    # thin the inventory to what the OLD commit justified (nothing but a placeholder row shape)
    card_path = os.path.join(repo, "card.yaml")
    with open(card_path) as f:
        card = yaml.safe_load(f)
    old_commit = card["preserve_contract"]["inventory"][0]["extracted_from"]["commit"]
    card["preserve_contract"]["inventory"] = [
        {"capability": "placeholder:none",
         "extracted_from": {"commit": old_commit, "path": _AS_FILE},
         "re_homed_to": "templates/trans/new_shell.html"}]
    with open(card_path, "w") as f:
        yaml.safe_dump(card, f)
    subprocess.run(["git", "-C", repo, "commit", "-aq", "-m", "thin inventory"], check=True)
    baseline_sha = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD~1"],
                                  capture_output=True, text=True).stdout.strip()
    return repo, baseline_sha


def _recipe_build_turn_as_no_baseline(tmp):
    # P1-5: manifests exist in the repo but state carries NO wave_pre_build_baseline_sha →
    # build-turn's accepted-surface step must FAIL CLOSED (the actual-diff bite can never run).
    repo, state = _build_turn_repo(tmp, with_test_cmd=True)
    os.makedirs(os.path.join(repo, "accepted-surface-manifests"), exist_ok=True)
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    _as_write_manifest(repo, "legacy-home", "legacy-home", head,
                       owned=["templates/home.html"], shared=[])
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                    "register legacy surface\n\nCode-X-Provenance: cx-test"], check=True)
    # refresh state.last_commit to the new HEAD so the boot/lineage legs stay green
    with open(state) as f:
        sdata = yaml.safe_load(f)
    sdata["last_commit"] = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                                          capture_output=True, text=True).stdout.strip()
    with open(state, "w") as f:
        yaml.dump(sdata, f)
    return repo, state


def _recipe_as_good(tmp):
    return _as_repo(tmp)


def _recipe_as_good_shared(tmp):
    return _as_repo(tmp, add_shared_manifest=True)


def _recipe_evidence_abs_path(tmp: str) -> tuple[str, str]:
    """PBF-PROP-021 group-1 hole #3: evidence_required with an ABSOLUTE path escapes the card/repo
    entirely — /etc/hosts (any always-present external file) previously satisfied the gate verbatim,
    then the faked-pass scan read the external file as if it were committed proof. No git repo needed:
    the card lives alone in tmp with no .git / CODE-X-STATE.yaml ancestor, so repo_root resolves None
    and the absolute ref is checked as-is (safe_repo_ref rejects it on the is_absolute() branch)."""
    card_dir = os.path.join(tmp, "card")
    os.makedirs(card_dir, exist_ok=True)
    cpath = os.path.join(card_dir, "card.yaml")
    with open(cpath, "w") as f:
        f.write("id: EV-ABS\nmode: MODULE_BUILD\nevidence_required:\n  - /etc/hosts\n")
    return cpath, cpath


def _recipe_evidence_symlink_escape(tmp: str) -> tuple[str, str]:
    """PBF-PROP-021 group-1 hole #3: evidence_required is a relative path that is actually an
    in-card-dir SYMLINK pointing OUTSIDE the card dir — without the safe_repo_ref guard the honesty
    scan would read arbitrary external bytes as an in-repo evidence file."""
    card_dir = os.path.join(tmp, "card")
    os.makedirs(card_dir, exist_ok=True)
    ext = os.path.join(tmp, "external_evidence.log")   # OUTSIDE card_dir (tmp is card_dir's parent)
    with open(ext, "w") as f:
        f.write("not a real evidence file\n")
    os.symlink(ext, os.path.join(card_dir, "sneaky.log"))
    cpath = os.path.join(card_dir, "card.yaml")
    with open(cpath, "w") as f:
        f.write("id: EV-SYM\nmode: MODULE_BUILD\nevidence_required:\n  - sneaky.log\n")
    return cpath, cpath


def _recipe_evidence_unreadable(tmp: str) -> tuple[str, str]:
    """PBF-PROP-021 group-1 hole #4: an unreadable evidence file (chmod 000) previously swallowed
    the read error in a bare `except Exception: pass` and skipped the faked-pass honesty scan with
    NO finding — a faked-pass file made unreadable defeated the `echo "PASS"` anti-cheat scan
    entirely. The file's own content WOULD trip scan_faked_pass if it could be read."""
    card_dir = os.path.join(tmp, "card")
    os.makedirs(card_dir, exist_ok=True)
    fake = os.path.join(card_dir, "fake.log")
    with open(fake, "w") as f:
        f.write('echo "PASS"\n')
    os.chmod(fake, 0o000)
    cpath = os.path.join(card_dir, "card.yaml")
    with open(cpath, "w") as f:
        f.write("id: EV-UNREAD\nmode: MODULE_BUILD\nevidence_required:\n  - fake.log\n")
    return cpath, cpath


def _rft_repo(tmp, *, cover_home=True, pictured_state="populated", drift_screen=None):
    """PBF-PROP-021 F17 systemic scar: RENDER-COVERS-GIT-TOUCHED / UNPICTURED-STATE-IS-GAP /
    GOLDEN-DRIFT-BLOCKS-TOUCHED (PBF-PROP-020 Rules 2/7) were proven to bite only in tests/run.py's
    TestPBFPROP020GitTouchedScope, never in the static contract-bite harness. Mirrors that suite's
    _repo() helper: a real git repo whose HEAD touches templates/home.html vs its baseline, a packet
    with a MODULE-REGISTRY screen->file binding + a hash-bound lock carrying pictured_states, and a
    render bundle. Returns (repo, head_sha) — head_sha rides the harness's {STATE} token."""
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    os.makedirs(os.path.join(repo, "templates"))
    with open(os.path.join(repo, "templates", "home.html"), "w") as f:
        f.write("<h1>one</h1>\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    base = _git_commit(repo, "baseline")
    with open(os.path.join(repo, "templates", "home.html"), "w") as f:
        f.write("<h1>two — the look changed</h1>\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    head = _git_commit(repo, "change home look")
    pkt = os.path.join(repo, "packet")
    os.makedirs(os.path.join(pkt, "locks"))
    with open(os.path.join(pkt, "locks", "home.lock.yaml"), "w") as f:
        f.write(
            "ui_lock_manifest:\n"
            "  audit_status: PASS\n"
            "  ceo_acceptance_ref: CEO-D-FIXTURE\n"
            "  pictured_states:\n"
            f"    - {{screen_id: home, content_state: {pictured_state}}}\n")
    with open(os.path.join(pkt, "MODULE-REGISTRY.yaml"), "w") as f:
        f.write(
            "module_registry:\n"
            "  frozen_packet_hash: p021-f17-rft-fixture\n"
            "  modules:\n"
            "    - module_id: m_home\n"
            "      screen_id: home\n"
            "      kind: screen\n"
            "      files: [templates/home.html]\n"
            "      lock_ref: packet/locks/home.lock.yaml\n"
            "      requirement_ids: []\n"
            "      dependency_modules: []\n"
            "      card_ids: [BUILD-1]\n")
    # Otherwise-VALID render_profile + render_evidence (mirrors tests/fixtures/render_good.yaml)
    # for whichever screen coverage_matrix.required_rows declares — so the only clause that can
    # fire is the ONE this recipe targets, never a coincidental RENDER-FIT-PROFILE-UNPINNED /
    # RENDER-FIT-COVERAGE-INCOMPLETE noise (and so the "good" recipe reaches a clean rc=0).
    with open(os.path.join(repo, "render_shot.txt"), "w") as f:
        f.write("render-fixture-screenshot-bytes-v1\n")
    covered_screen = "home" if cover_home else "other"
    lines = [
        f"repo_sha_before: {base[:12]}",
        "render_profile:",
        "  chromium_revision: \"1234.5\"", "  device_pixel_ratio: 2", "  viewport: \"390x844\"",
        "  viewports:", "    - viewport_id: phone", "      width: 390",
        "  color_schemes: [light, dark]", "  reduced_motion: true", "  locale: en-US",
        "  timezone: UTC", "  fonts: bundled", "  animations: disabled", "  network: blocked",
        "  fixture: DESIGN_FIXTURE", "  profile_hash: c7c416dfa9b0",
        "coverage_matrix:", "  ui_card: true", "  required_rows:",
        f"    - screen_id: {covered_screen}",
        "      viewport_id: phone", "      theme: light", "      content_state: populated",
        "render_evidence:",
        "  - card_id: BUILD-RF-021-F17", f"    screen_id: {covered_screen}",
        "    viewport_id: phone", "    theme: light", "    content_state: populated",
        "    route: /home", f"    repo_head: {head}", "    state_sha12: state00aabbcc",
        "    locked_packet_hash: pkt00112233aa", "    render_profile_hash: c7c416dfa9b0",
        "    tool_version: \"cx-render/1.0.0\"", "    command: \"cx render collect --screen home\"",
        "    generated_by: cx render collect", "    screenshot_path: render_shot.txt",
        "    screenshot_hash: 3e4f45cb0a7d", "    measured_metrics:",
        "      viewport_width: 390", "      content_width: 390",
        "      has_horizontal_overflow: false", "      max_visible_right: 389.4",
        "      nonblank: true", "      app_ready: true", "      controls_in_frame: []",
        "    produced_at: \"2026-06-22T09:00:00Z\"",
    ]
    if drift_screen:
        lines += ["golden_drift:", f"  - screen_id: {drift_screen}", "    viewport_id: phone",
                  "    diff_score: 0.9", "    tolerance: 0.1", "    baseline_ref: baseline-shot"]
    with open(os.path.join(repo, "bundle.yaml"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return repo, head


def _recipe_rft_bad_covers(tmp):
    return _rft_repo(tmp, cover_home=False)


def _recipe_rft_bad_unpictured(tmp):
    return _rft_repo(tmp, cover_home=True, pictured_state="empty")


def _recipe_rft_bad_drift(tmp):
    return _rft_repo(tmp, cover_home=True, drift_screen="home")


def _recipe_rft_good(tmp):
    return _rft_repo(tmp, cover_home=True, pictured_state="populated")


def _recipe_packet_no_risk_tier(tmp: str) -> tuple[str, str]:
    """PBF-PROP-022-C: a fully valid frozen packet that declares NO risk_tier. cx check packet
    PASSES (rc 0 — the fail-closed STRICT resolver default is safe) but prints the non-blocking
    PACKET-RISK-TIER-UNDECLARED WARN nudge. Returns the read-only static fixture path (cx check
    packet never mutates it); tmp is unused."""
    d = str(FIXTURES / "packet_good")
    return d, d


def _recipe_packet_risk_tier_declared(tmp: str) -> tuple[str, str]:
    """PBF-PROP-022-C good/quiet: a valid frozen packet that DOES declare risk_tier (STRICT, needs
    no decision ref). cx check packet PASSES and the undeclared-tier advisory stays SILENT."""
    d = str(FIXTURES / "packet_good_risk_tier_strict")
    return d, d


_RECIPES = {
    "packet_no_risk_tier": _recipe_packet_no_risk_tier,
    "packet_risk_tier_declared": _recipe_packet_risk_tier_declared,
    "build_turn_blueprint_not_ready": _recipe_build_turn_blueprint_not_ready,
    "build_turn_blueprint_ready": _recipe_build_turn_blueprint_ready,
    "build_turn_blueprint_approval_symlink": _recipe_build_turn_blueprint_approval_symlink,
    "ancestor_ok": _recipe_ancestor_ok,
    "fs_struct_good": _recipe_fs_struct_good,
    "fs_struct_nolockref": _recipe_fs_struct_nolockref,
    "fs_struct_pathsafe": _recipe_fs_struct_pathsafe,
    "fs_struct_forged": _recipe_fs_struct_forged,
    "fs_struct_badhash": _recipe_fs_struct_badhash,
    "fs_struct_manifest": _recipe_fs_struct_manifest,
    "fs_struct_paths_forged": _recipe_fs_struct_paths_forged,
    "fs_struct_rail": _recipe_fs_struct_rail,
    "fs_struct_rail_ok": _recipe_fs_struct_rail_ok,
    "fs_qlog_unreconciled": _recipe_fs_qlog_unreconciled,
    "fs_qlog_ok": _recipe_fs_qlog_ok,
    "fs_posture_no_targets": _recipe_fs_posture_no_targets,
    "fs_multi_anchor": _recipe_fs_multi_anchor,
    "fs_xlock_surface": _recipe_fs_xlock_surface,
    "fs_revert_missing": _recipe_fs_revert_missing,
    "fs_amnesia_ghost": _recipe_fs_amnesia_ghost,
    "fs_amnesia_contradiction": _recipe_fs_amnesia_contradiction,
    "fs_amnesia_override_unsafe": _recipe_fs_amnesia_override_unsafe,
    "fs_amnesia_unlogged": _recipe_fs_amnesia_unlogged,
    "fs_card_good_amnesia": _recipe_fs_card_good_amnesia,
    "lf_card_no_anchor": _recipe_lf_card_no_anchor,
    "lf_card_no_devclass": _recipe_lf_card_no_devclass,
    "lf_card_scope_unauth": _recipe_lf_card_scope_unauth,
    "lf_card_good_restore": _recipe_lf_card_good_restore,
    "lf_card_good_scope": _recipe_lf_card_good_scope,
    "lf_card_packet_hash_mismatch": _recipe_lf_card_packet_hash_mismatch,
    "lf_card_anchor_card_not_in_registry": _recipe_lf_card_anchor_card_not_in_registry,
    "lf_card_scope_ceo_ref_dangling": _recipe_lf_card_scope_ceo_ref_dangling,
    "lf_card_scope_amend_unsafe": _recipe_lf_card_scope_amend_unsafe,
    "lf_card_scope_destructive_p0": _recipe_lf_card_scope_destructive_p0,
    "lf_accept_status_invalid": _recipe_lf_accept_status_invalid,
    "lf_accept_status_ok": _recipe_lf_accept_status_ok,
    "lf_accept_layer1_drift": _recipe_lf_accept_layer1_drift,
    "lf_accept_layer1_clean": _recipe_lf_accept_layer1_clean,
    "lf_session_no_lock_pointer": _recipe_lf_session_no_lock_pointer,
    "lf_session_lock_pointer_ok": _recipe_lf_session_lock_pointer_ok,
    "lf_drift_unlogged": _recipe_lf_drift_unlogged,
    "lf_drift_ok": _recipe_lf_drift_ok,
    "lf_overreach": _recipe_lf_overreach,
    "lf_overreach_ok": _recipe_lf_overreach_ok,
    "lf_handoff_hash_mismatch": _recipe_lf_handoff_hash_mismatch,
    "lf_handoff_opencards_mismatch": _recipe_lf_handoff_opencards_mismatch,
    "lf_handoff_ok": _recipe_lf_handoff_ok,
    "dep_scan_ok": _recipe_dep_scan_ok,
    "dep_scan_stale_hash": _recipe_dep_scan_stale_hash,
    "dep_scan_high_unwaived": _recipe_dep_scan_high_unwaived,
    "dep_scan_high_uncovered": _recipe_dep_scan_high_uncovered,
    "dep_scan_high_waived": _recipe_dep_scan_high_waived,
    "dep_scan_extra_lockfile": _recipe_dep_scan_extra_lockfile,
    "dep_scan_path_unsafe": _recipe_dep_scan_path_unsafe,
    "dep_scan_missing_lockfile": _recipe_dep_scan_missing_lockfile,
    "dep_scan_missing_field": _recipe_dep_scan_missing_field,
    "dep_scan_uncovered_manifest": _recipe_dep_scan_uncovered_manifest,
    "wpr_ok": _recipe_wpr_ok,
    "wpr_missing_receipt": _recipe_wpr_missing_receipt,
    "wpr_hash_mismatch": _recipe_wpr_hash_mismatch,
    "wpr_path_unsafe": _recipe_wpr_path_unsafe,
    "wpr_receipt_symlink": _recipe_wpr_receipt_symlink,
    "wpr_not_typed": _recipe_wpr_not_typed,
    "wpr_missing_field": _recipe_wpr_missing_field,
    "wpr_wrong_kind": _recipe_wpr_wrong_kind,
    "wpr_same_family": _recipe_wpr_same_family,
    "wpr_unknown_family": _recipe_wpr_unknown_family,
    "wpr_three_leg_placeholder": _recipe_wpr_three_leg_placeholder,
    "wpr_bad_verdict": _recipe_wpr_bad_verdict,
    "wpr_stale_packet": _recipe_wpr_stale_packet,
    "wpr_missing_sub_hash": _recipe_wpr_missing_sub_hash,
    "wpr_buildmeta_delta": _recipe_wpr_buildmeta_delta,
    "build_turn_wpr_missing": _recipe_build_turn_wpr_missing,
    "foreign_lineage": _recipe_foreign_lineage,
    "dirty_unmarked": _recipe_dirty_unmarked,
    "wip_marked_ok": _recipe_wip_marked_ok,
    "wip_marked_unowned": _recipe_wip_marked_unowned,
    "behind_warn": _recipe_behind_warn,
    "no_builder_std_ack": _recipe_no_builder_std_ack,
    "no_orchestration_mode": _recipe_no_orchestration_mode,
    "inline_waiver_no_scope": _recipe_inline_waiver_no_scope,
    "inline_waiver_with_scope": _recipe_inline_waiver_with_scope,
    "planning_no_lessons_ack": _recipe_planning_no_lessons_ack,
    "planning_lessons_ack_ok": _recipe_planning_lessons_ack_ok,
    "no_boot_ack": _recipe_no_boot_ack,
    "boot_ack_stale": _recipe_boot_ack_stale,
    "no_review_boundary": _recipe_no_review_boundary,
    "build_turn_ok": _recipe_build_turn_ok,
    "build_turn_no_test": _recipe_build_turn_no_test,
    "build_turn_test_fails": _recipe_build_turn_test_fails,
    "build_turn_module_start_blocks": _recipe_build_turn_module_start_blocks,
    "build_turn_verify_app_rail": _recipe_build_turn_verify_app_rail,
    "build_turn_verify_app_rail_ok": _recipe_build_turn_verify_app_rail_ok,
    "build_turn_verify_app_symlink": _recipe_build_turn_verify_app_symlink,
    "build_turn_render_bundle_symlink": _recipe_build_turn_render_bundle_symlink,
    "build_turn_dep_scan_symlink": _recipe_build_turn_dep_scan_symlink,
    "build_turn_coderabbit_receipt_symlink": _recipe_build_turn_coderabbit_receipt_symlink,
    "build_turn_coderabbit_lite_strict": _recipe_build_turn_coderabbit_lite_strict,
    "build_turn_coderabbit_lite_relaxed": _recipe_build_turn_coderabbit_lite_relaxed,
    "build_turn_dep_scan_ref_ok": _recipe_build_turn_dep_scan_ref_ok,
    "build_turn_render_bundle_ref_ok": _recipe_build_turn_render_bundle_ref_ok,
    "build_turn_coderabbit_receipt_ref_ok": _recipe_build_turn_coderabbit_receipt_ref_ok,
    "module_start_symlink_registry": _recipe_module_start_symlink_registry,
    "module_start_symlink_root": _recipe_module_start_symlink_root,
    "module_start_symlink_ancestor": _recipe_module_start_symlink_ancestor,
    "module_start_symlink_ok": _recipe_module_start_symlink_ok,
    "module_start_registry_alias_symlink": _recipe_module_start_registry_alias_symlink,
    "module_acceptance_external_ref": _recipe_module_acceptance_external_ref,
    "module_acceptance_inrepo_ref": _recipe_module_acceptance_inrepo_ref,
    "forge_parity_good": _recipe_forge_parity_good,
    "forge_parity_bad_verify_app": _recipe_forge_parity_bad_verify_app,
    "forge_parity_bad_verify_app_not_ancestor": _recipe_forge_parity_bad_verify_app_not_ancestor,
    "forge_parity_bad_module_demo": _recipe_forge_parity_bad_module_demo,
    "forge_parity_bad_live_slice": _recipe_forge_parity_bad_live_slice,
    "forge_parity_bad_qc_drift": _recipe_forge_parity_bad_qc_drift,
    "forge_parity_bad_marker_malformed": _recipe_forge_parity_bad_marker_malformed,
    "cx_accept_no_token": _recipe_cx_accept_no_token,
    "cx_accept_good_token": _recipe_cx_accept_good_token,
    "cx_accept_short_prefix_token": _recipe_cx_accept_short_prefix_token,
    "cx_accept_token_no_turn_ref": _recipe_cx_accept_token_no_turn_ref,
    "cx_accept_token_wrong_block": _recipe_cx_accept_token_wrong_block,
    "module_start_live_slice_blocks": _recipe_module_start_live_slice_blocks,
    "module_start_live_slice_ok": _recipe_module_start_live_slice_ok,
    "no_module_demo_mode": _recipe_no_module_demo_mode,
    "boot_receipt_forged": _recipe_boot_receipt_forged,
    "close_turn_row_untyped": _recipe_close_turn_row_untyped,
    "close_turn_ok": _recipe_close_turn_ok,
    "close_turn_no_delta": _recipe_close_turn_no_delta,
    "close_turn_delta_mismatch": _recipe_close_turn_delta_mismatch,
    "close_turn_vault_skip_no_reason": _recipe_close_turn_vault_skip_no_reason,
    "close_turn_evidence_path_escape": _recipe_close_turn_evidence_path_escape,
    "as_legacy_no_manifest": _recipe_as_legacy_no_manifest,
    "as_incomplete_inventory": _recipe_as_incomplete_inventory,
    "as_fake_ceo_ref": _recipe_as_fake_ceo_ref,
    "as_missing_regression": _recipe_as_missing_regression,
    "as_narrow_regression": _recipe_as_narrow_regression,
    "as_missing_shared_coverage": _recipe_as_missing_shared_coverage,
    "as_diff_undeclared": _recipe_as_diff_undeclared,
    "as_fix_scope_change": _recipe_as_fix_scope_change,
    "as_no_contract": _recipe_as_no_contract,
    "as_bad_binding": _recipe_as_bad_binding,
    "as_extractor_variants": _recipe_as_extractor_variants,
    "as_stale_accepted_commit": _recipe_as_stale_accepted_commit,
    "build_turn_as_no_baseline": _recipe_build_turn_as_no_baseline,
    "as_good": _recipe_as_good,
    "as_good_shared": _recipe_as_good_shared,
    "evidence_abs_path": _recipe_evidence_abs_path,
    "evidence_symlink_escape": _recipe_evidence_symlink_escape,
    "evidence_unreadable": _recipe_evidence_unreadable,
    "rft_bad_covers": _recipe_rft_bad_covers,
    "rft_bad_unpictured": _recipe_rft_bad_unpictured,
    "rft_bad_drift": _recipe_rft_bad_drift,
    "rft_good": _recipe_rft_good,
}


def run_cx(*args, env_overrides: dict | None = None):
    """env_overrides: {VAR: value} applied over os.environ; value None = unset VAR
    (lets a clause test production env behavior, e.g. CX_PROFILES without test mode)."""
    env = None
    if env_overrides:
        env = dict(os.environ)
        for k, v in env_overrides.items():
            if v is None:
                env = {ek: ev for ek, ev in env.items() if ek != k}
            else:
                env[k] = str(v)
    result = subprocess.run(
        [sys.executable, CX] + list(args),
        capture_output=True, text=True, env=env,
    )
    return result.returncode, result.stdout + result.stderr


# CXBP-007: the ONLY flags in any clause that take a non-path (identifier) value. A bare value
# following one of these is left unresolved; EVERY other token (positional or value of a path-flag
# like --state/--approval/--repo-root/--registry/--packet-dir) is still resolved to an absolute
# fixture path — so a genuinely-missing path-valued flag value is still reported MISSING FIXTURE.
_NON_PATH_VALUE_FLAGS = {"--module", "--module-id", "--target", "--repo-head",
                         "--authorize-decision", "--n", "--m", "--window-days",
                         "--migration-ref"}


def resolve_args(args_list):
    """Resolve relative fixture PATHS to absolute (relative to CHECKERS_DIR). A bare VALUE that follows
    one of the KNOWN non-path-value flags (_NON_PATH_VALUE_FLAGS, e.g. `--module home`) is left
    UNCHANGED, so an identifier flag value is never mangled into a phantom fixture path. Every other
    token resolves as before — a path-flag's value (--state/--approval/...) still resolves, so a typo'd
    missing path is still caught."""
    resolved = []
    prev = ""
    for a in args_list:
        p = Path(a)
        is_non_path_flag_value = prev in _NON_PATH_VALUE_FLAGS and not a.startswith("-")
        if not p.is_absolute() and not a.startswith("--") and not is_non_path_flag_value:
            p = (CHECKERS_DIR / a).resolve()
            resolved.append(str(p))
        else:
            resolved.append(a)
        prev = a
    return resolved

def substitute_tokens(args_list: list[str], repo: str, state: str) -> list[str]:
    """Replace {REPO} and {STATE} placeholder tokens in args."""
    return [a.replace("{REPO}", repo).replace("{STATE}", state) for a in args_list]

def main():
    with open(CONTRACTS) as f:
        manifest = yaml.safe_load(f)

    clauses = manifest.get("clauses", [])
    failures = []
    gate_count = 0
    heuristic_count = 0
    subcommands_covered = set()

    # Coverage check: every bad fixture file must exist (skip git_fixture clauses). resolve_args
    # leaves bare flag VALUES (e.g. `--module home`) unresolved/relative — they are not fixture
    # paths, so a still-relative token after a `--flag` is a flag value, not a missing fixture.
    for clause in clauses:
        if clause.get("git_fixture"):
            continue
        if "bad" not in clause:
            continue
        raw = clause["bad"]["args"]
        bad_args = resolve_args(raw)
        for idx, a in enumerate(bad_args):
            if a.startswith("-"):
                continue
            prev = bad_args[idx - 1] if idx > 0 else ""
            if not Path(a).is_absolute() and prev in _NON_PATH_VALUE_FLAGS:
                continue  # identifier flag value (e.g. --module home) — not a fixture path
            p = Path(a)
            if not p.exists():
                failures.append(f"MISSING FIXTURE [{clause['id']}]: {a}")

    for clause in clauses:
        cid = clause["id"]
        check = clause["check"]
        kind = clause.get("kind", "gate")
        git_recipe = clause.get("git_fixture")

        subcommands_covered.add(check)
        if kind == "gate":
            gate_count += 1
        else:
            heuristic_count += 1

        # ── good-only clause (no bad: key) ──────────────────────────────────
        if "bad" not in clause:
            # root git_fixture (or good.git_fixture) provides the repo for the good case
            good_recipe = clause.get("good", {}).get("git_fixture") or clause.get("git_fixture")
            if good_recipe:
                good_fn = _RECIPES.get(good_recipe)
                if good_fn is None:
                    failures.append(f"UNKNOWN-GOOD-RECIPE [{cid}]: {good_recipe}")
                    continue
                with tempfile.TemporaryDirectory() as tmp_g:
                    try:
                        repo_g, state_g = good_fn(tmp_g)
                    except Exception as e:
                        failures.append(f"RECIPE-ERROR-GOOD [{cid}]: {e}")
                        continue
                    good_args_g = substitute_tokens(clause["good"]["args"], repo_g, state_g)
                    rc_g, out_g = run_cx("check", check, *good_args_g)
                    if rc_g != 0:
                        failures.append(
                            f"GOOD-FAILS [{cid}]: expected rc=0, got {rc_g}\n  output: {out_g[:200]}")
                    else:
                        print(f"  PASS  [{cid}] good-only fixture OK")
            else:
                good_args_g = resolve_args(clause.get("good", {}).get("args", []))
                if good_args_g:
                    rc_g, out_g = run_cx("check", check, *good_args_g)
                    if rc_g != 0:
                        failures.append(
                            f"GOOD-FAILS [{cid}]: expected rc=0, got {rc_g}\n  output: {out_g[:200]}")
                    else:
                        print(f"  PASS  [{cid}] good-only fixture OK")
            continue

        expect_sev = clause["bad"].get("expect_severity")

        if git_recipe:
            # Build temp git repo from recipe, substitute {REPO}/{STATE} tokens
            recipe_fn = _RECIPES.get(git_recipe)
            if recipe_fn is None:
                failures.append(f"UNKNOWN-RECIPE [{cid}]: {git_recipe}")
                continue

            with tempfile.TemporaryDirectory() as tmp:
                try:
                    repo, state_path = recipe_fn(tmp)
                except Exception as e:
                    failures.append(f"RECIPE-ERROR [{cid}]: {e}")
                    continue

                bad_args_raw = clause["bad"]["args"]
                bad_args = substitute_tokens(bad_args_raw, repo, state_path)
                rc, out = run_cx("check", check, *bad_args)

                if kind == "heuristic":
                    # heuristic: must exit 0 AND contain expected text
                    warn_text = clause["bad"].get("expect_warn_text", "WARN:")
                    if rc != 0:
                        failures.append(
                            f"HEURISTIC-NONZERO [{cid}]: expected rc=0, got {rc}\n  output: {out[:300]}"
                        )
                    elif warn_text not in out:
                        failures.append(
                            f"HEURISTIC-NO-WARN [{cid}]: expected '{warn_text}' in output\n  output: {out[:300]}"
                        )
                    else:
                        print(f"  WARN  [{cid}] ({kind}): '{warn_text}' found")
                else:
                    sev_token = f"[{expect_sev}]"
                    contains = clause["bad"].get("expect_contains")
                    if rc != 1:
                        failures.append(f"BAD-NO-BITE [{cid}]: expected rc=1, got {rc}\n  output: {out[:200]}")
                    elif sev_token not in out:
                        failures.append(
                            f"BAD-WRONG-SEVERITY [{cid}]: expected '{sev_token}' in output\n  output: {out[:300]}"
                        )
                    elif contains and contains not in out:
                        failures.append(
                            f"BAD-WRONG-REASON [{cid}]: expected '{contains}' in output — "
                            f"bit for a different reason than the clause claims\n  output: {out[:300]}"
                        )
                    else:
                        print(f"  BITE  [{cid}] ({kind}): {sev_token} found")

                # good fixture
                good_recipe = clause.get("good", {}).get("git_fixture")
                if good_recipe:
                    good_fn = _RECIPES.get(good_recipe)
                    if good_fn is None:
                        failures.append(f"UNKNOWN-GOOD-RECIPE [{cid}]: {good_recipe}")
                        continue
                    with tempfile.TemporaryDirectory() as tmp2:
                        try:
                            repo2, state2 = good_fn(tmp2)
                        except Exception as e:
                            failures.append(f"RECIPE-ERROR-GOOD [{cid}]: {e}")
                            continue
                        good_args = substitute_tokens(clause["good"]["args"], repo2, state2)
                        rc2, out2 = run_cx("check", check, *good_args)
                        if rc2 != 0:
                            failures.append(
                                f"GOOD-FAILS [{cid}]: expected rc=0, got {rc2}\n  output: {out2[:200]}"
                            )
                        else:
                            print(f"  PASS  [{cid}] good fixture OK")
        else:
            # ── standard file-based clause ────────────────────────────────
            bad_args = resolve_args(clause["bad"]["args"])
            good_args = resolve_args(clause.get("good", {}).get("args", []))

            # ── bad fixture must bite ──────────────────────────────
            rc, out = run_cx("check", check, *bad_args,
                             env_overrides=clause["bad"].get("env"))
            sev_token = f"[{expect_sev}]"
            contains = clause["bad"].get("expect_contains")
            if rc != 1:
                failures.append(f"BAD-NO-BITE [{cid}]: expected rc=1, got {rc}\n  output: {out[:200]}")
            elif sev_token not in out:
                failures.append(
                    f"BAD-WRONG-SEVERITY [{cid}]: expected '{sev_token}' in output\n  output: {out[:300]}"
                )
            elif contains and contains not in out:
                failures.append(
                    f"BAD-WRONG-REASON [{cid}]: expected '{contains}' in output — "
                    f"bit for a different reason than the clause claims\n  output: {out[:300]}"
                )
            else:
                print(f"  BITE  [{cid}] ({kind}): {sev_token} found")

            # ── good fixture must pass ─────────────────────────────
            if good_args:
                rc2, out2 = run_cx("check", check, *good_args,
                                   env_overrides=clause.get("good", {}).get("env"))
                if rc2 != 0:
                    failures.append(
                        f"GOOD-FAILS [{cid}]: expected rc=0 for good fixture, got {rc2}\n  output: {out2[:200]}"
                    )
                else:
                    print(f"  PASS  [{cid}] good fixture OK")

    # ── coverage: every required subcommand has >=1 gate clause ──
    missing_sub = REQUIRED_SUBCOMMANDS - subcommands_covered
    if missing_sub:
        failures.append(f"COVERAGE-GAP: no clause for subcommands: {missing_sub}")

    # ── summary ───────────────────────────────────────────────────
    print()
    total = gate_count + heuristic_count
    print(f"Clauses checked: {total} total ({gate_count} gate, {heuristic_count} heuristic)")
    print(f"Subcommands covered: {sorted(subcommands_covered)}")
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  FAIL: {f}")
        print("\nrun_contracts.py: FAIL")
        sys.exit(1)
    else:
        all_gate = gate_count
        print(f"\nAll {all_gate} gate clauses bite. All good fixtures pass. Coverage OK.")
        print("run_contracts.py: PASS")
        sys.exit(0)

if __name__ == "__main__":
    main()
