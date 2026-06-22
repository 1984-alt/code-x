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
                        "dep-scan", "egress", "class-sweep", "render-fidelity"}
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
        body += _LIVE_SLICE_ACCEPT_BLOCK
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


_RECIPES = {
    "ancestor_ok": _recipe_ancestor_ok,
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
