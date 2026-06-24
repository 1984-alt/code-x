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
import subprocess
import sys
import tempfile
import os
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
                        "boot", "build-turn", "close-turn", "evals", "design-fidelity", "module-start", "module-acceptance", "module-quality",
                        "dep-scan", "egress", "class-sweep", "render-fidelity", "drift", "structure", "verify-app"}
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
    "session_start": {
        "builder_standard_read": {
            "status": "PASS", "file": "BUILDER-STANDARD.md",
            "hash": "deadbeef0123", "read_by": "cx-contract-test",
            "timestamp": "2026-06-10T00:00:00",
        },
    },
    # PROP-020: reviewer taxonomy/timing as typed state (required at session-start in build modes).
    "review_boundary": {
        "deterministic_checks_each_card": "yes",
        "coderabbit_before_self_review": "not_applicable",
        "self_review_boundary": "module",
        "cross_family_boundary": "module",
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


def _build_turn_repo(tmp: str, with_test_cmd: bool, test_cmd: str = "git --version",
                     module_id: str = "m1") -> tuple[str, str]:
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
    with open(os.path.join(packet, "requirements-manifest.yaml"), "w") as f:
        f.write(manifest_body)
    with open(FIXTURES / "module_registry_good.yaml") as f:
        registry_body = f.read()
    with open(os.path.join(packet, "MODULE-REGISTRY.yaml"), "w") as f:
        f.write(registry_body)
    # The card's locked_packet_hash = content hash of the frozen packet (deck semantics).
    card.setdefault("source_map", {})["locked_packet_hash"] = _packet_hash(packet)
    card["allowed_files"] = ["src/app.py"]
    card["evidence_required"] = ["evidence.txt"]
    card["module_id"] = module_id
    if with_test_cmd:
        card["test_command"] = test_cmd
    card_path = os.path.join(repo, "card.yaml")
    with open(card_path, "w") as f:
        yaml.dump(card, f)
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    sha = _git_commit(repo, "build-turn fixture")
    state = os.path.join(tmp, "state.yaml")
    _write_state(state, sha, overrides={"packet_dir": "packet",
                                        "module_registry_ref": "packet/MODULE-REGISTRY.yaml"})
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
        priors) → PASS."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    packet = os.path.join(repo, "packet")
    if where == "ancestor":
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


def _module_start_live_slice_repo(tmp: str, with_drive: bool) -> tuple[str, str]:
    """m1 = a live_slice; m2 depends on m1. m1's acceptance receipt carries (with_drive) or omits a
    live_slice_accept block. cx check module-start for m2 BLOCKS when m1 has no live-drive accept
    (P0 — the next slice cannot start until the CEO drove the prior), PASSES when it does (PROP-032).
    repo_sha_before uses the test-mode fresh-clone sentinel so the PROP-028 git leg is skipped."""
    import hashlib
    repo = os.path.join(tmp, "repo")
    _git_init(repo)
    packet = os.path.join(repo, "packet")
    os.makedirs(packet, exist_ok=True)
    with open(os.path.join(packet, "requirements-manifest.yaml"), "w") as f:
        f.write(_MS_MANIFEST)
    with open(os.path.join(packet, "MODULE-REGISTRY.yaml"), "w") as f:
        f.write(_MS_LIVE_REGISTRY)
    os.makedirs(os.path.join(repo, "acc"), exist_ok=True)
    body = ("module_acceptance:\n  module_id: m1\n  verdict: accepted\n  generated_by: cx-accept\n"
            "  state_sha_before: abc123\n  quality_card_hash: qc0011223344\n"
            "  repo_sha_before: NONE_TEST_FIXTURE\n")
    if with_drive:
        body += _LIVE_SLICE_ACCEPT_BLOCK + _VERIFY_APP_BLOCK
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
           "severity": "high", "reason": "r", "mitigation": "m", "expiry": "2026-12-01", "owner": "dev"}

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


_RECIPES = {
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
    "foreign_lineage": _recipe_foreign_lineage,
    "dirty_unmarked": _recipe_dirty_unmarked,
    "wip_marked_ok": _recipe_wip_marked_ok,
    "wip_marked_unowned": _recipe_wip_marked_unowned,
    "behind_warn": _recipe_behind_warn,
    "no_builder_std_ack": _recipe_no_builder_std_ack,
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
    "module_start_symlink_registry": _recipe_module_start_symlink_registry,
    "module_start_symlink_root": _recipe_module_start_symlink_root,
    "module_start_symlink_ancestor": _recipe_module_start_symlink_ancestor,
    "module_start_symlink_ok": _recipe_module_start_symlink_ok,
    "module_acceptance_external_ref": _recipe_module_acceptance_external_ref,
    "module_acceptance_inrepo_ref": _recipe_module_acceptance_inrepo_ref,
    "module_start_live_slice_blocks": _recipe_module_start_live_slice_blocks,
    "module_start_live_slice_ok": _recipe_module_start_live_slice_ok,
    "boot_receipt_forged": _recipe_boot_receipt_forged,
    "close_turn_row_untyped": _recipe_close_turn_row_untyped,
    "close_turn_ok": _recipe_close_turn_ok,
    "close_turn_no_delta": _recipe_close_turn_no_delta,
    "close_turn_delta_mismatch": _recipe_close_turn_delta_mismatch,
    "close_turn_vault_skip_no_reason": _recipe_close_turn_vault_skip_no_reason,
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

def resolve_args(args_list):
    """Resolve relative fixture paths to absolute (relative to CHECKERS_DIR)."""
    resolved = []
    for a in args_list:
        p = Path(a)
        if not p.is_absolute() and not a.startswith("--"):
            p = (CHECKERS_DIR / a).resolve()
            resolved.append(str(p))
        else:
            resolved.append(a)
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

    # Coverage check: every bad fixture file must exist (skip git_fixture clauses)
    for clause in clauses:
        if clause.get("git_fixture"):
            continue
        bad_args = resolve_args(clause["bad"]["args"])
        for a in bad_args:
            if not a.startswith("-"):
                p = Path(a)
                if not p.exists():
                    failures.append(f"MISSING FIXTURE [{clause['id']}]: {a}")

    for clause in clauses:
        cid = clause["id"]
        check = clause["check"]
        kind = clause.get("kind", "gate")
        expect_sev = clause["bad"].get("expect_severity")
        git_recipe = clause.get("git_fixture")

        subcommands_covered.add(check)
        if kind == "gate":
            gate_count += 1
        else:
            heuristic_count += 1

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
