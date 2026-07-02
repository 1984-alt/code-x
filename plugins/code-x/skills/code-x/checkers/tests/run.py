#!/usr/bin/env python3
"""
run.py — plain Python test runner for the cx test suite.
Usage: python3 checkers/tests/run.py   (from Code-X-V1 root)
       python3 run.py                  (from checkers/tests/)

Converts pytest-style class+method tests to unittest and runs them.
Exit 0 = all pass, 1 = failures.
"""
import sys

# Runtime floor: the cx checker uses PEP 604 `X | None` type unions (Python 3.10+).
# Guard before importing/exec'ing cx so an older interpreter gets a clear message,
# not a raw import-time TypeError that reads as a false test failure. (CXAUD-001)
if sys.version_info < (3, 10):
    sys.stderr.write(
        "run.py: the cx test suite requires Python 3.10+ (cx uses PEP 604 `X | None` type unions).\n"
        f"    Active interpreter: Python {sys.version.split()[0]} at {sys.executable}\n"
        "    Re-run with Python 3.10+ — e.g.  /opt/homebrew/bin/python3 Code-X-V1/checkers/tests/run.py\n"
    )
    raise SystemExit(2)

import subprocess
import tempfile
import os
import unittest
from pathlib import Path

# Resolve paths
THIS_DIR = Path(__file__).parent
CHECKERS_DIR = THIS_DIR.parent
CX = str(CHECKERS_DIR / "cx")
FIXTURES = THIS_DIR / "fixtures"
CX_ROOT = CHECKERS_DIR.parent  # Code-X-V1 root

# Pin BUILD-ENGINE-PROFILES to the test mirror (stable fixture hashes — see profiles_test.yaml)
os.environ["CODE_X_TEST_MODE"] = "1"  # PROP-014: CX_PROFILES honored only in test mode
os.environ["CX_PROFILES"] = str(FIXTURES / "profiles_test.yaml")

# Direct import for in-process hermetic tests (git-resolution path can't be exercised via a
# static fixture — it needs a real commit graph mirroring the nested-worktree layout).
sys.path.insert(0, str(CHECKERS_DIR))
import cx_kaizen  # noqa: E402


def run_cx(*args) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, CX] + list(args),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def fix(name: str) -> str:
    return str(FIXTURES / name)


def fix_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# card
# ---------------------------------------------------------------------------
class TestCheckCard(unittest.TestCase):
    def test_good_card_passes(self):
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS (exit 0), got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_proof_mode_card_passes(self):
        # PROOF is a real intended mode — cx_evidence.py branches on mode == "PROOF".
        # cx check card must accept it, not flag a spurious "mode 'PROOF' not in [...]" P1.
        rc, out = run_cx("check", "card", fix("card_good_proof.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS (exit 0), got {rc}.\n{out}")
        self.assertIn("PASS", out)
        self.assertNotIn("mode 'PROOF' not in", out)

    def test_missing_source_map(self):
        rc, out = run_cx("check", "card", fix("card_bad_missing_source_map.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("source_map", out.lower())

    def test_same_family_cross_review_rejected(self):
        rc, out = run_cx("check", "card", fix("card_bad_same_family.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("same-family" in out.lower() or "cross_review" in out.lower())

    def test_missing_required_field(self):
        rc, out = run_cx("check", "card", fix("card_bad_missing_field.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("model_tier" in out.lower() or "objective" in out.lower())

    def test_missing_security_tripwire(self):
        rc, out = run_cx("check", "card", fix("card_bad_missing_security_tripwire.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("security_tripwire", out.lower())

    def test_invalid_model_tier(self):
        rc, out = run_cx("check", "card", fix("card_bad_unnamed_model_tier.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("model_tier", out.lower())

    def test_over_budget_read(self):
        rc, out = run_cx("check", "card", fix("card_bad_over_budget_read.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("read" in out.lower() and ("budget" in out.lower() or "files" in out.lower()))

    def test_nonexistent_file_returns_fix_first(self):
        rc, out = run_cx("check", "card", "/tmp/does_not_exist_cx_test.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)

    def test_malformed_yaml_returns_fix_first(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("key: [unclosed bracket\n  nested: :")
            tmpname = f.name
        try:
            rc, out = run_cx("check", "card", tmpname)
            self.assertEqual(rc, 1)
            self.assertIn("FIX-FIRST", out)
        finally:
            os.unlink(tmpname)

    def test_module_build_missing_module_id_fails(self):
        """V1.10: a MODULE_BUILD card without module_id can't be gated by the order wall → P0."""
        rc, out = run_cx("check", "card", fix("card_no_module_id.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("module_id", out)

    def test_module_build_missing_coderabbit_fails(self):
        """PROP-042-DRAFT / V1.21-candidate: a code-diff module build card must plan CodeRabbit."""
        rc, out = run_cx("check", "card", fix("card_bad_missing_coderabbit.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("CodeRabbit", out)

    def test_module_build_missing_prevention_preamble_fails(self):
        """BUILD-PREVENTION-PREAMBLE-MISSING (PROP-042 Part C): a MODULE_BUILD card without
        execution.prevention_preamble must be rejected P1."""
        rc, out = run_cx("check", "card", fix("card_bad_no_prevention_preamble.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("prevention_preamble", out)

    def test_module_build_prevention_preamble_ref_unsafe_fails(self):
        """BUILD-PREVENTION-PREAMBLE-REF-UNSAFE (PROP-042 Part C): a MODULE_BUILD card with
        execution.prevention_preamble.standard_ref containing path traversal must be rejected P1."""
        rc, out = run_cx("check", "card", fix("card_bad_prevention_preamble_ref_unsafe.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("standard_ref", out)

    def test_module_build_good_prevention_preamble_passes(self):
        """BUILD-PREVENTION-PREAMBLE-MISSING: card_good.yaml (with valid prevention_preamble) passes."""
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS for card_good.yaml with prevention_preamble, got rc={rc}.\n{out}")


# ---------------------------------------------------------------------------
# self-review escalation cap (V1.10 — the one non-additive clause change)
# ---------------------------------------------------------------------------
class TestSelfReviewFixCycles(unittest.TestCase):
    """V1.10: a SELF_REVIEW card may run review_fix_cycles up to 3 (bounded
    builder→stronger→strongest escalation); every other card stays one-and-done (<= 1)."""

    def test_self_review_rfc3_passes(self):
        rc, out = run_cx("check", "card", fix("card_self_review_good_rfc3.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS (exit 0), got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_self_review_rfc4_fails(self):
        rc, out = run_cx("check", "card", fix("card_self_review_bad_rfc4.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("SELF_REVIEW", out)
        self.assertIn("review_fix_cycles", out.lower())

    def test_non_self_review_rfc2_still_fails(self):
        """The cap is 1 for non-SELF_REVIEW cards — the existing one-and-done bite is unbroken."""
        rc, out = run_cx("check", "card", fix("card_bad_review_fix_cycles.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("review_fix_cycles", out.lower())

    def test_self_review_label_unbacked_fails(self):
        """V1.10 (GPT P1-2): review_kind SELF_REVIEW + rfc 3 but self_review.family != executor.family
        — a mislabeled cross-family dispatch cannot buy the cap-3 escalation budget."""
        rc, out = run_cx("check", "card", fix("card_self_review_mislabel_rfc3.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("SELF_REVIEW", out)
        self.assertIn("same-family self review", out)


# ---------------------------------------------------------------------------
# module-start — the order wall (V1.10)
# ---------------------------------------------------------------------------
class TestCheckModuleStart(unittest.TestCase):
    """V1.10: a module-advancing card may start only when its module_id is in the frozen
    registry AND every prior required module is accepted."""

    # V1.10 R4: the order wall content-binds the card to the frozen packet — the registry lives
    # INSIDE module_start_good_packet/ and the cards' locked_packet_hash = the packet's content hash.
    _PKT = "module_start_good_packet"
    _REG = "module_start_good_packet/MODULE-REGISTRY.yaml"

    def test_in_order_card_passes(self):
        rc, out = run_cx("check", "module-start", fix("card_module2_start.yaml"),
                         "--packet-dir", fix(self._PKT), "--registry", fix(self._REG),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_out_of_order_fails(self):
        rc, out = run_cx("check", "module-start", fix("card_module3_start.yaml"),
                         "--packet-dir", fix(self._PKT), "--registry", fix(self._REG),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("prior required module", out)

    def test_unknown_module_id_fails(self):
        rc, out = run_cx("check", "module-start", fix("card_module_unknown.yaml"),
                         "--packet-dir", fix(self._PKT), "--registry", fix(self._REG),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("out-of-registry", out.lower())

    def test_non_build_card_is_na(self):
        """A REVIEW card is not a module-advancing event — order wall N/A, PASS (returns at the
        mode gate, before the packet-content binding, so no --packet-dir is needed)."""
        rc, out = run_cx("check", "module-start", fix("card_review_good.yaml"),
                         "--state", fix("state_modules_m1_accepted.yaml"),
                         "--registry", fix(self._REG))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_prior_module_no_receipt_blocks(self):
        """V1.10 (GPT P0-1): the order wall RE-VALIDATES each prior module's receipt — a prior
        marked accepted with no bound receipt does NOT unlock the next module (no trusting the id set)."""
        rc, out = run_cx("check", "module-start", fix("card_module2_start.yaml"),
                         "--packet-dir", fix(self._PKT), "--registry", fix(self._REG),
                         "--state", fix("state_module_accepted_no_receipt.yaml"),
                         "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("prior required module", out)

    # ── V1.10 R4 content-deep binding (closes the R3 open P0) ──────────────────────────────
    def test_packet_content_mismatch_rejected(self):
        """Headline R4 bite: a trimmed registry (m1 deleted) that keeps the SAME frozen_packet_hash
        STRING is rejected — re-hashing the packet (which CONTAINS the registry) no longer equals the
        card's frozen locked_packet_hash. String-deep would PASS this; content-deep does not."""
        rc, out = run_cx("check", "module-start", fix("card_module2_start.yaml"),
                         "--packet-dir", fix("module_start_trimmed_packet"),
                         "--registry", fix("module_start_trimmed_packet/module-registry.yaml"),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("packet content mismatch", out)

    def test_registry_outside_packet_rejected(self):
        """The registry must be the canonical <packet>/MODULE-REGISTRY.yaml — an external registry
        (even a pristine-looking one) is rejected, so order can't be read from an out-of-packet copy."""
        rc, out = run_cx("check", "module-start", fix("card_module2_start.yaml"),
                         "--packet-dir", fix(self._PKT),
                         "--registry", fix("module_registry_good.yaml"),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("canonical", out)

    def test_alternate_in_packet_registry_rejected(self):
        """GPT R4 P0: a packet may contain other registry-shaped files; the order wall reads ONLY the
        canonical MODULE-REGISTRY.yaml. Selecting an alternate trimmed registry that is itself INSIDE
        the content-verified packet (content hash still matches) must be rejected — registry IDENTITY,
        not just 'inside the packet'."""
        rc, out = run_cx("check", "module-start", fix("card_module2_two_registry.yaml"),
                         "--packet-dir", fix("module_start_two_registry_packet"),
                         "--registry", fix("module_start_two_registry_packet/TRIMMED-REGISTRY.yaml"),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("canonical", out)

    def test_two_registry_canonical_passes(self):
        """Counterpart to the identity bite: selecting the canonical registry in the same two-registry
        packet (m1 accepted) PASSES — proves the bite is the IDENTITY check, not the content check."""
        rc, out = run_cx("check", "module-start", fix("card_module2_two_registry.yaml"),
                         "--packet-dir", fix("module_start_two_registry_packet"),
                         "--registry", fix("module_start_two_registry_packet/MODULE-REGISTRY.yaml"),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_missing_packet_dir_rejected(self):
        """--packet-dir is required for a module-advancing card (fail-closed) — without it the order
        wall cannot content-bind the card to the frozen packet."""
        rc, out = run_cx("check", "module-start", fix("card_module2_start.yaml"),
                         "--registry", fix(self._REG),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("--packet-dir required", out)

    def test_symlink_canonical_registry_rejected(self):
        """GPT R5 P0: the canonical <packet>/MODULE-REGISTRY.yaml is a SYMLINK to an external trimmed
        registry. Following it would hash the target's bytes (content still 'matches') and read the
        order from OUTSIDE the packet. A frozen packet must be self-contained → P0, no symlinks."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            pkt = base / "packet"
            pkt.mkdir()
            (pkt / "requirements-manifest.yaml").write_text(
                "requirements:\n  - id: REQ-001\n    disposition: BUILDING\n")
            (base / "EXTERNAL-TRIMMED.yaml").write_text(
                "module_registry:\n  frozen_packet_hash: g1-frozen\n  modules:\n"
                "    - module_id: m2\n      dependency_modules: []\n      card_ids: [BUILD-002]\n")
            os.symlink(base / "EXTERNAL-TRIMMED.yaml", pkt / "MODULE-REGISTRY.yaml")
            (base / "card.yaml").write_text(
                "id: BUILD-002\nmode: MODULE_BUILD\nmodule_id: m2\n"
                "source_map:\n  locked_packet_hash: deadbeef\n")
            (base / "state.yaml").write_text(
                "project: x\nprotocol_stamp: Code-X V1\naccepted_modules: []\n")
            rc, out = run_cx("check", "module-start", str(base / "card.yaml"),
                             "--packet-dir", str(pkt), "--registry", str(pkt / "MODULE-REGISTRY.yaml"),
                             "--state", str(base / "state.yaml"), "--repo-root", str(base))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("symlink", out)

    def test_symlink_packet_root_rejected(self):
        """GPT R6 P0: the packet ROOT itself is a symlink to an external dir holding a trimmed
        registry. is_dir()/os.walk would follow it and hash bytes OUTSIDE the intended packet. A
        frozen packet must be a real, self-contained directory → P0."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ext = base / "external_packet"
            ext.mkdir()
            (ext / "requirements-manifest.yaml").write_text(
                "requirements:\n  - id: REQ-001\n    disposition: BUILDING\n")
            (ext / "MODULE-REGISTRY.yaml").write_text(
                "module_registry:\n  frozen_packet_hash: g1-frozen\n  modules:\n"
                "    - module_id: m2\n      dependency_modules: []\n      card_ids: [BUILD-002]\n")
            os.symlink(ext, base / "packet")  # packet root is a symlink
            (base / "card.yaml").write_text(
                "id: BUILD-002\nmode: MODULE_BUILD\nmodule_id: m2\n"
                "source_map:\n  locked_packet_hash: deadbeef\n")
            (base / "state.yaml").write_text(
                "project: x\nprotocol_stamp: Code-X V1\naccepted_modules: []\n")
            rc, out = run_cx("check", "module-start", str(base / "card.yaml"),
                             "--packet-dir", str(base / "packet"),
                             "--registry", str(base / "packet" / "MODULE-REGISTRY.yaml"),
                             "--state", str(base / "state.yaml"), "--repo-root", str(base))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("symlink", out)

    def test_duplicate_module_id_rejected(self):
        """GPT R7 P0: a registry with a DUPLICATE module_id (m2,m1,m2) lets ordered_ids.index('m2')
        pick the first occurrence → m2 sees no priors → m1 skipped. Module order must be unambiguous."""
        rc, out = run_cx("check", "module-start", fix("card_module2_dup.yaml"),
                         "--packet-dir", fix("module_start_dup_module_packet"),
                         "--registry", fix("module_start_dup_module_packet/MODULE-REGISTRY.yaml"),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("duplicate module_id", out)

    def test_symlinked_ancestor_rejected(self):
        """GPT R7 P0: a symlinked ANCESTOR of --packet-dir (repo/link/packet, 'link' a symlink) points
        the packet OUTSIDE the repo even though the packet dir + subtree are clean. With --repo-root
        given, no symlink may appear in the chain from repo root down to the packet → P0."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            extp = base / "external_real" / "packet"
            extp.mkdir(parents=True)
            (extp / "requirements-manifest.yaml").write_text(
                "requirements:\n  - id: REQ-001\n    disposition: BUILDING\n")
            (extp / "MODULE-REGISTRY.yaml").write_text(
                "module_registry:\n  frozen_packet_hash: g1-frozen\n  modules:\n"
                "    - module_id: m2\n      dependency_modules: []\n      card_ids: [B]\n")
            os.symlink(base / "external_real", base / "link")  # ancestor symlink
            (base / "card.yaml").write_text(
                "id: B\nmode: MODULE_BUILD\nmodule_id: m2\n"
                "source_map:\n  locked_packet_hash: deadbeef\n")
            (base / "state.yaml").write_text(
                "project: x\nprotocol_stamp: Code-X V1\naccepted_modules: []\n")
            rc, out = run_cx("check", "module-start", str(base / "card.yaml"),
                             "--packet-dir", str(base / "link" / "packet"),
                             "--registry", str(base / "link" / "packet" / "MODULE-REGISTRY.yaml"),
                             "--state", str(base / "state.yaml"), "--repo-root", str(base))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("symlink", out)

    def test_missing_repo_root_rejected(self):
        """GPT R8 P0: --repo-root is required for a module-advancing card — without it the order wall
        cannot bound the symlinked-ancestor check to the repo (standalone opt-out). Fail-closed."""
        rc, out = run_cx("check", "module-start", fix("card_module2_start.yaml"),
                         "--packet-dir", fix(self._PKT), "--registry", fix(self._REG),
                         "--state", fix("state_modules_m1_accepted.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("repo-root required", out)

    def test_packet_dir_dotdot_rejected(self):
        """GPT R9 P0: a '..' in --packet-dir is rejected before any fs access — os.path.abspath would
        lexically collapse 'link/..' and hide a symlinked ancestor from the chain check while the fs
        follows it outside the repo."""
        rc, out = run_cx("check", "module-start", fix("card_module2_start.yaml"),
                         "--packet-dir", fix("module_start_good_packet") + "/../module_start_good_packet",
                         "--registry", fix(self._REG),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("'..' component", out)

    def test_malformed_registry_row_rejected(self):
        """GPT R8 P0: a registry row with no module_id (or non-mapping / bad deps) must fail closed —
        silently skipping it would drop a real prior module from the order."""
        rc, out = run_cx("check", "module-start", fix("card_module2_malformed.yaml"),
                         "--packet-dir", fix("module_start_malformed_packet"),
                         "--registry", fix("module_start_malformed_packet/MODULE-REGISTRY.yaml"),
                         "--state", fix("state_modules_m1_accepted.yaml"), "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("module_id", out)

    def test_good_packet_hash_matches_card_fixture(self):
        """Drift guard: the baked locked_packet_hash in card_module2_start.yaml must equal the live
        recompute of module_start_good_packet/. If a packet fixture file is edited, refresh the
        module-start cards' locked_packet_hash to the value this test prints."""
        sys.path.insert(0, str(CHECKERS_DIR))
        from cx_deck import _compute_packet_hash
        import yaml as _yaml
        live = _compute_packet_hash(Path(fix(self._PKT)))
        with open(fix("card_module2_start.yaml")) as f:
            card = _yaml.safe_load(f)
        baked = str(card["source_map"]["locked_packet_hash"])
        self.assertEqual(live, baked,
            f"module_start_good_packet hashes to {live} but card_module2_start.yaml has {baked} — "
            "refresh the module-start cards' locked_packet_hash to the live value")


# ---------------------------------------------------------------------------
# module-acceptance — the Andon receipt wall (V1.10)
# ---------------------------------------------------------------------------
class TestCheckModuleAcceptance(unittest.TestCase):
    """V1.10: a module unlocks the next only with a bound, machine-generated MODULE-ACCEPTANCE
    receipt — verdict accepted, forge-bound, and bound to state by sha."""

    def test_bound_receipt_passes(self):
        rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                         "--state", fix("state_module_accepted_good.yaml"),
                         "--acceptance", fix("module_acceptance_good.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_no_module_id_receipt_fails(self):
        """GPT R10 P0 (enforced-path): a sha-bound receipt that OMITS module_id would 'accept' ANY
        module — the validator must require module_id present + matching, not just non-mismatching."""
        rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                         "--state", fix("state_module_accepted_no_module_id.yaml"),
                         "--acceptance", fix("module_acceptance_no_module_id.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("no module_id", out)

    def test_malformed_receipt_fields_fail(self):
        """GPT R12 P0 (enforced-path): receipt fields that are non-scalars (list/mapping) used to pass
        via str(x or '') coercion. They must be treated as absent → presence checks fail closed."""
        rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                         "--state", fix("state_module_accepted_malformed.yaml"),
                         "--acceptance", fix("module_acceptance_malformed_fields.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("generated_by", out)

    def test_non_mapping_acceptance_block_fails(self):
        """GPT R12 P0: a `module_acceptance:` block that is a list/scalar must be rejected, not fall
        back to the bare receipt (which let a non-mapping block + valid top-level fields slip)."""
        import tempfile as _tf, hashlib as _hl
        with _tf.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rcpt = base / "r.yaml"
            rcpt.write_text(
                "module_acceptance: []\nmodule_id: m1\nverdict: accepted\ngenerated_by: cx-accept\n"
                "state_sha_before: abc\nquality_card_hash: qc\n")
            sha = _hl.sha256(rcpt.read_bytes()).hexdigest()[:12]
            (base / "state.yaml").write_text(
                "project: x\nprotocol_stamp: Code-X V1\naccepted_modules:\n"
                f"  - module_id: m1\n    acceptance_ref: r.yaml\n    acceptance_sha12: \"{sha}\"\n")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", str(base / "state.yaml"), "--repo-root", str(base))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("not a mapping", out)

    def test_external_acceptance_ref_fails(self):
        """GPT R11 P0 (enforced-path): a model-authored acceptance_ref that is absolute / outside the
        repo lets the Andon wall read arbitrary external bytes as the receipt. Must be repo-relative."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "outside-receipt.yaml").write_text(
                "module_acceptance:\n  module_id: m1\n  verdict: accepted\n  generated_by: cx-accept\n"
                "  state_sha_before: abc\n  quality_card_hash: qc\n")
            import hashlib
            sha = hashlib.sha256((base / "outside-receipt.yaml").read_bytes()).hexdigest()[:12]
            repo = base / "repo"
            repo.mkdir()
            (repo / "state.yaml").write_text(
                "project: x\nprotocol_stamp: Code-X V1\naccepted_modules:\n"
                f"  - module_id: m1\n    acceptance_ref: {base}/outside-receipt.yaml\n"
                f'    acceptance_sha12: "{sha}"\n')
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", str(repo / "state.yaml"), "--repo-root", str(repo))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("repo-relative", out)

    def test_accepted_in_state_no_receipt_fails(self):
        rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                         "--state", fix("state_module_accepted_no_receipt.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("receipt", out.lower())

    def test_hash_mismatch_fails(self):
        rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                         "--state", fix("state_module_accepted_hash_mismatch.yaml"),
                         "--acceptance", fix("module_acceptance_good.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("hash mismatch", out)

    def test_verdict_not_accepted_fails(self):
        rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                         "--state", fix("state_module_accepted_pending.yaml"),
                         "--acceptance", fix("module_acceptance_bad_verdict_pending.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("not 'accepted'", out)

    def test_empty_binding_fields_fail(self):
        """A receipt missing state_sha_before / quality_card_hash is not forge-bound → P0."""
        import tempfile, os, hashlib
        body = ("module_acceptance:\n  module_id: m1\n  verdict: accepted\n"
                "  generated_by: cx-accept\n"
                "  state_sha_before: ''\n  quality_card_hash: ''\n")
        with tempfile.TemporaryDirectory() as td:
            rp = os.path.join(td, "receipt.yaml")
            with open(rp, "w") as f:
                f.write(body)
            sha = hashlib.sha256(open(rp, "rb").read()).hexdigest()[:12]
            sp = os.path.join(td, "state.yaml")
            with open(sp, "w") as f:
                f.write("protocol_stamp: Code-X V1\naccepted_modules:\n  - module_id: m1\n"
                        f"    acceptance_ref: receipt.yaml\n    acceptance_sha12: {sha}\n")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--acceptance", rp)
            self.assertEqual(rc, 1)
            self.assertTrue("state_sha_before" in out or "quality_card_hash" in out)

    def test_missing_generated_by_fails(self):
        """V1.10 (GPT P0-3): a receipt with no generated_by is model-authored text, not a machine wall → P0."""
        import tempfile, os, hashlib
        body = ("module_acceptance:\n  module_id: m1\n  verdict: accepted\n"
                "  state_sha_before: 9f8e7d6c5b4a\n  quality_card_hash: qc0011223344\n")
        with tempfile.TemporaryDirectory() as td:
            rp = os.path.join(td, "receipt.yaml")
            with open(rp, "w") as f:
                f.write(body)
            sha = hashlib.sha256(open(rp, "rb").read()).hexdigest()[:12]
            sp = os.path.join(td, "state.yaml")
            with open(sp, "w") as f:
                f.write("protocol_stamp: Code-X V1\naccepted_modules:\n  - module_id: m1\n"
                        f"    acceptance_ref: receipt.yaml\n    acceptance_sha12: {sha}\n")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--acceptance", rp)
            self.assertEqual(rc, 1)
            self.assertIn("generated_by", out)


# ---------------------------------------------------------------------------
# PROP-028 — phantom-completion guard at the module-acceptance Andon wall.
# The git-dependent core (empty-diff + ancestor) cannot be a static fixture, so each test
# builds a TEMP git repo with real commits and binds the receipt to state by sha12.
# ---------------------------------------------------------------------------
class TestProp028PhantomCompletion(unittest.TestCase):
    """A module accepted whose build baseline (repo_sha_before) is identical to HEAD shipped NO
    real change — a green receipt for nothing built. The guard must BITE on that empty diff and
    must NOT false-positive when real files changed between the baseline and HEAD."""

    def _build(self, tmp, repo_sha_before, extra=""):
        """Create a temp git repo with two real-content commits and a sha12-bound receipt+state.
        Returns (repo, state_path). repo_sha_before is the literal value written into the receipt
        (None omits the field)."""
        import hashlib
        repo = os.path.join(tmp, "repo")
        _git_init(repo)
        # commit 1: a real file (the build baseline candidate)
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("one\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        base_sha = _git_commit(repo, "first")
        # commit 2 (HEAD): a real second change so base..HEAD has a non-empty diff
        with open(os.path.join(repo, "b.txt"), "w") as f:
            f.write("two\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        head_sha = _git_commit(repo, "second")
        rsb = head_sha if repo_sha_before == "HEAD" else (
            base_sha if repo_sha_before == "BASE" else repo_sha_before)
        rsb_line = f"  repo_sha_before: {rsb}\n" if rsb is not None else ""
        body = ("module_acceptance:\n  module_id: m1\n  verdict: accepted\n"
                "  generated_by: cx-accept\n  state_sha_before: 9f8e7d6c5b4a\n"
                "  quality_card_hash: qc0011223344\n" + rsb_line + extra)
        rp = os.path.join(repo, "receipt.yaml")
        with open(rp, "w") as f:
            f.write(body)
        sha = hashlib.sha256(open(rp, "rb").read()).hexdigest()[:12]
        sp = os.path.join(tmp, "state.yaml")
        with open(sp, "w") as f:
            f.write("project: x\nprotocol_stamp: Code-X V1\naccepted_modules:\n"
                    f"  - module_id: m1\n    acceptance_ref: receipt.yaml\n"
                    f'    acceptance_sha12: "{sha}"\n')
        return repo, sp

    def test_empty_diff_phantom_bites(self):
        """repo_sha_before == HEAD => empty diff => the guard BITES (phantom completion)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, "HEAD")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST (phantom), got {rc}.\n{out}")
            self.assertIn("phantom completion", out)
            self.assertIn("empty diff", out)

    def test_empty_diff_phantom_escalates_to_p0_on_risk(self):
        """A money/login/data module with an empty diff escalates the phantom finding to P0."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, "HEAD", extra="  risk_flags: [money]\n")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("[P0]", out)
            self.assertIn("phantom completion", out)

    def test_real_change_passes(self):
        """repo_sha_before == an earlier commit with real changes before HEAD => no false-positive."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, "BASE")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
            self.assertIn("PASS", out)

    def test_not_ancestor_bites(self):
        """repo_sha_before is well-formed hex but not a commit in history => P1 (baseline not in history)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("not an ancestor of HEAD", out)

    def test_missing_repo_sha_bites(self):
        """No repo_sha_before and no carve-out => P1 (missing build baseline)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, None)
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("missing repo_sha_before", out)

    def test_legacy_carveout_is_non_blocking(self):
        """A typed legacy_no_baseline carve-out yields only the advisory P2 migration-debt finding —
        no P0/P1 phantom/missing finding fires (non-blocking heuristic)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, None,
                                   extra="  legacy_no_baseline: pre-PROP-028 module, no baseline recorded\n")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 0, f"legacy carve-out must be NON-BLOCKING (rc=0), got {rc}.\n{out}")
            self.assertIn("migration debt", out)
            self.assertIn("[P2]", out)
            self.assertNotIn("[P0]", out)
            self.assertNotIn("[P1]", out)


# ---------------------------------------------------------------------------
# cross-family ship gate (V1.10) — final is valid; a deferral may not permit ship
# ---------------------------------------------------------------------------
class TestCrossFamilyShipGate(unittest.TestCase):
    def test_cross_family_final_passes(self):
        rc, out = run_cx("check", "state", fix("state_good_cross_family_final.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_ceo_deferred_permitting_ship_fails(self):
        rc, out = run_cx("check", "state", fix("state_bad_ceo_deferred_permits_ship.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("may not permit ship", out)

    def test_ceo_deferred_blocking_ship_passes(self):
        """The existing deferral that DOES block ship/final_ready stays valid."""
        rc, out = run_cx("check", "state", fix("state_good_ceo_deferred.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")


# ---------------------------------------------------------------------------
# design-fidelity BLOCKS (V1.10) — legacy marker-manifest is no longer an escape
# ---------------------------------------------------------------------------
class TestDesignFidelityBlocks(unittest.TestCase):
    def test_legacy_new_build_blocks(self):
        rc, out = run_cx("check", "design-fidelity",
                         "--manifest", fix("ui_marker_manifest_good.yaml"),
                         "--dom", fix("dom_good.html"),
                         "--screenshot", fix("screenshot_good.png"))
        self.assertEqual(rc, 1)
        self.assertIn("design-fidelity BLOCKS", out)

    def test_legacy_migration_flag_warns_and_passes(self):
        rc, out = run_cx("check", "design-fidelity",
                         "--manifest", fix("ui_marker_manifest_good.yaml"),
                         "--dom", fix("dom_good.html"),
                         "--screenshot", fix("screenshot_good.png"),
                         "--legacy-migration")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("WARN", out)


# ---------------------------------------------------------------------------
# render-fidelity (PROP-033, fold v1.14) — in-loop RENDERED-fidelity gate
# Layer 1 = deterministic + BLOCKING; Layer 2 = golden-drift ADVISORY (WARN only).
# ---------------------------------------------------------------------------
class TestRenderFidelity(unittest.TestCase):
    # PROP-033 xfam fold: the authoritative repo head is supplied by the rail via --repo-head
    # (FIX 1), never read from the bundle. The good fixture's evidence repo_head == this sha.
    _HEAD = "aaaaaaaaaaaa"
    # The full set of Layer-1 clause ids — used to PROVE isolation (only the target clause fires).
    _ALL_CLAUSES = [
        "RENDER-FIT-PROFILE-UNPINNED", "RENDER-FIT-EVIDENCE-MISSING-OR-STALE",
        "RENDER-FIT-RECEIPT-FORGED", "RENDER-FIT-COVERAGE-INCOMPLETE", "RENDER-FIT-OVERFLOW",
        "RENDER-FIT-CONTROL-OFFSCREEN", "RENDER-FIT-BLANK-OR-ROUTE-FAIL", "RENDER-FIT-CANNOT-VERIFY",
    ]

    def test_good_bundle_passes(self):
        rc, out = run_cx("check", "render-fidelity", fix("render_good.yaml"), "--repo-head", self._HEAD)
        self.assertEqual(rc, 0, f"Expected PASS (exit 0), got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_missing_repo_head_arg_is_rejected(self):
        # FIX 1: --repo-head is REQUIRED — argparse must reject the invocation without it (rc=2),
        # so freshness can never be proven against an empty/absent authoritative head.
        rc, out = run_cx("check", "render-fidelity", fix("render_good.yaml"))
        self.assertEqual(rc, 2, f"Expected argparse usage error (exit 2), got {rc}.\n{out}")

    def _bad(self, fixture, clause, sev):
        rc, out = run_cx("check", "render-fidelity", fix(fixture), "--repo-head", self._HEAD)
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn(clause, out)
        self.assertIn(f"[{sev}]", out)
        # REAL isolation (the contract harness only substring-matches): assert that NO non-target
        # RENDER-FIT-* clause rode along on this fixture.
        for other in self._ALL_CLAUSES:
            if other != clause:
                self.assertNotIn(other, out,
                    f"{fixture}: non-target clause {other} rode along — fixture not isolated.\n{out}")

    def test_profile_unpinned_blocks(self):
        self._bad("render_bad_profile_unpinned.yaml", "RENDER-FIT-PROFILE-UNPINNED", "P0")

    def test_profile_unbound_blocks(self):
        # FIX 2: profile_hash present but != the recomputed fingerprint of the profile body.
        self._bad("render_bad_profile_unbound.yaml", "RENDER-FIT-PROFILE-UNPINNED", "P0")

    def test_evidence_stale_blocks(self):
        self._bad("render_bad_evidence_stale.yaml", "RENDER-FIT-EVIDENCE-MISSING-OR-STALE", "P0")

    def test_receipt_forged_blocks(self):
        self._bad("render_bad_receipt_forged.yaml", "RENDER-FIT-RECEIPT-FORGED", "P0")

    def test_missing_row_hash_is_forged(self):
        # FIX 2: an evidence row with NO render_profile_hash can no longer dodge the profile pin.
        self._bad("render_bad_missing_row_hash.yaml", "RENDER-FIT-RECEIPT-FORGED", "P0")

    def test_wrong_viewport_is_forged(self):
        # FIX 3: viewport_width that does not match the pinned profile width is P0 forgery.
        self._bad("render_bad_wrong_viewport.yaml", "RENDER-FIT-RECEIPT-FORGED", "P0")

    def test_coverage_incomplete_blocks(self):
        self._bad("render_bad_coverage_incomplete.yaml", "RENDER-FIT-COVERAGE-INCOMPLETE", "P0")

    def test_overflow_blocks(self):
        self._bad("render_bad_overflow.yaml", "RENDER-FIT-OVERFLOW", "P1")

    def test_control_offscreen_blocks(self):
        self._bad("render_bad_control_offscreen.yaml", "RENDER-FIT-CONTROL-OFFSCREEN", "P1")

    def test_blank_route_fail_blocks(self):
        self._bad("render_bad_blank_route_fail.yaml", "RENDER-FIT-BLANK-OR-ROUTE-FAIL", "P1")

    def test_cannot_verify_blocks(self):
        self._bad("render_bad_cannot_verify.yaml", "RENDER-FIT-CANNOT-VERIFY", "P1")

    def test_stale_head_mismatch_with_live_head(self):
        # FIX 1 end-to-end: even a bundle whose OWN current_repo_head matches its evidence is STALE
        # when the rail supplies a DIFFERENT authoritative --repo-head. The receipt cannot vouch for
        # its own freshness — the live head is the only truth.
        rc, out = run_cx("check", "render-fidelity", fix("render_good.yaml"), "--repo-head", "ffffffffffff")
        self.assertEqual(rc, 1, f"A live-head mismatch must block, got {rc}.\n{out}")
        self.assertIn("RENDER-FIT-EVIDENCE-MISSING-OR-STALE", out)

    def test_same_commit_double_run_is_deterministic(self):
        # The proposal demanded same-commit repeatability: render_good run twice → identical output.
        rc1, out1 = run_cx("check", "render-fidelity", fix("render_good.yaml"), "--repo-head", self._HEAD)
        rc2, out2 = run_cx("check", "render-fidelity", fix("render_good.yaml"), "--repo-head", self._HEAD)
        self.assertEqual(rc1, rc2, "double-run exit codes differ")
        self.assertEqual(out1, out2, "double-run output is not byte-identical (non-deterministic gate)")

    def test_layer2_golden_drift_warns_but_does_not_block(self):
        # Layer 2 ADVISORY: diff_score > tolerance prints a WARN line but the exit code stays 0.
        with tempfile.TemporaryDirectory() as tmp:
            body = fix_text("render_good.yaml").replace("diff_score: 0.4", "diff_score: 9.9")
            bundle = Path(tmp) / "render_drift.yaml"
            bundle.write_text(body, encoding="utf-8")
            # screenshot_path is bundle-relative, so the shot must sit beside the bundle.
            (Path(tmp) / "render_shot.txt").write_bytes(
                (FIXTURES / "render_shot.txt").read_bytes())
            rc, out = run_cx("check", "render-fidelity", str(bundle), "--repo-head", self._HEAD)
        self.assertEqual(rc, 0, f"Layer-2 drift must NOT change the exit code, got {rc}.\n{out}")
        self.assertIn("WARN: golden-drift", out)
        self.assertIn("ADVISORY only", out)


# ---------------------------------------------------------------------------
# module-quality (V1.10) — the per-module professional bar
# ---------------------------------------------------------------------------
class TestModuleQualityBar(unittest.TestCase):
    def test_full_quality_bar_passes(self):
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_full_good.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m1")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_money_module_no_conformance_fails(self):
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_no_conformance.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m1")
        self.assertEqual(rc, 1)
        self.assertIn("EXTRACTED-actuals", out)

    def test_missing_quality_card_fails(self):
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_no_quality_card.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m3")
        self.assertEqual(rc, 1)
        self.assertIn("quality_card", out)

    def test_missing_self_review_fails(self):
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_no_self_review.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m1")
        self.assertEqual(rc, 1)
        self.assertIn("same-family self_review", out)

    def test_shared_shell_regression_fail(self):
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_regression_fail.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m1")
        self.assertEqual(rc, 1)
        self.assertIn("regression-smoke", out)

    def test_missing_registry_fails_closed(self):
        """V1.10 (GPT P1-1): without --registry the quality bar would take risk from the receipt's
        own self-declaration → a money module could skip conformance. Now fail-closed."""
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_full_good.yaml"),
                         "--module-id", "m1")
        self.assertEqual(rc, 1)
        self.assertIn("--registry required", out)

    # --- PROP-032: Live Slice Delivery (live-drive accept) ---
    def test_live_slice_good_passes(self):
        """A live_slice accepted WITH a valid live_slice_accept block passes the quality bar."""
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_live_slice_good.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m_live")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_live_slice_no_drive_block_fails(self):
        """A live_slice (frozen registry) with NO live_slice_accept block is P0 — a Mode A
        screenshot/shell accept is not proof the CEO drove the running build (PROP-032)."""
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_live_slice_missing.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m_live")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("NO typed live_slice_accept block", out)

    def test_live_slice_ceo_drove_false_fails(self):
        """live_slice_accept present but ceo_drove false → P0 (the CEO must record DRIVING it)."""
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_live_slice_not_driven.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m_live")
        self.assertEqual(rc, 1)
        self.assertIn("ceo_drove is not true", out)

    def test_wrong_module_receipt_rejected(self):
        """Built-code review F1: a live_slice receipt for m_live pointed at --module-id m3 must NOT
        pass — the quality bar reads the receipt FOR the module it checks (closes the mis-point bypass)."""
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_live_slice_missing.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m3")
        self.assertEqual(rc, 1)
        self.assertIn("!= requested", out)

    def test_quoted_false_live_slice_not_fired(self):
        """Built-code review P2: a registry live_slice: 'false' (quoted string) must NOT be
        truthy-coerced into firing the live-drive gate on an honest non-live build."""
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_quoted_false.yaml"),
                         "--registry", fix("module_registry_good.yaml"),
                         "--module-id", "m_qfalse")
        self.assertEqual(rc, 0, f"quoted live_slice:'false' must not fire the live-drive gate.\n{out}")


# ---------------------------------------------------------------------------
# EVAL-040 (PBF-PROP-012-EVAL040) — build_validation + anti_slop evidence-bound legs
# ---------------------------------------------------------------------------
class TestEval040BuildValidationAntiSlop(unittest.TestCase):
    def _mq(self, fixture, module_id="m1"):
        return run_cx("check", "module-quality",
                      "--acceptance", fix(fixture),
                      "--registry", fix("module_registry_good.yaml"),
                      "--module-id", module_id)

    # --- shared good paths ---
    def test_build_antislop_good_passes(self):
        """PROP-037 per-clause hygiene: PASS_AFTER_FIX enum branch + distinct identities."""
        rc, out = self._mq("module_acceptance_build_antislop_good.yaml")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_build_validation_na_good_passes(self):
        """A declared, reasoned applicability: not_applicable is a PASS for a no-build module."""
        rc, out = self._mq("module_acceptance_build_validation_na_good.yaml", module_id="m3")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    # --- BUILD-VALIDATION-REQUIRED ---
    def test_no_build_validation_fails(self):
        rc, out = self._mq("module_acceptance_no_build_validation.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("build_validation leg missing", out)

    # --- BUILD-VALIDATION-MALFORMED (all sub-classes) ---
    def test_build_validation_bad_status_fails(self):
        rc, out = self._mq("module_acceptance_build_validation_bad_status.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("not PASS/PASS_AFTER_FIX", out)

    def test_build_validation_ran_empty_fails(self):
        rc, out = self._mq("module_acceptance_build_validation_ran_empty.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("ran is empty/not-a-list", out)

    def test_build_validation_missing_coverage_fails(self):
        rc, out = self._mq("module_acceptance_build_validation_missing_coverage.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("no re-readable PASS claims row covers it", out)

    def test_build_validation_nonscalar_reviewer_fails(self):
        """field_present would accept reviewer: [null] as 'present' — _str_field must not."""
        rc, out = self._mq("module_acceptance_build_validation_nonscalar_reviewer.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("identity missing", out)

    def test_build_validation_na_no_reason_fails(self):
        # non-risk module m3 so ONLY the na-branch MALFORMED fires (isolation, xfam #7)
        rc, out = self._mq("module_acceptance_build_validation_na_no_reason.yaml", module_id="m3")
        self.assertEqual(rc, 1)
        self.assertIn("not_applicable requires na_reason", out)

    # --- BUILD-VALIDATION-MALFORMED na-branch: artifact-type enum (xfam P0#1 part 2) ---
    def test_build_validation_na_bad_artifact_type_fails(self):
        rc, out = self._mq("module_acceptance_build_validation_na_bad_type.yaml", module_id="m3")
        self.assertEqual(rc, 1)
        self.assertIn("acceptance_artifact_type 'banana' is not one of", out)

    # --- BUILD-VALIDATION-NA-INVALID (P0) — a risk module cannot escape via N/A (xfam P0#1) ---
    def test_build_validation_na_on_risk_module_is_p0(self):
        """A money/data risk-flagged module declaring applicability: not_applicable with otherwise
        valid N/A fields is a P0 — the registry cross-check closes the dangerous escape. Live probe
        the reviewer confirmed: risk module + N/A + acceptance_artifact_type: banana previously PASSED."""
        rc, out = self._mq("module_acceptance_build_validation_na_on_risk_module.yaml", module_id="m1")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("cannot skip build_validation via the N/A escape", out)

    # --- BUILD-VALIDATION-CONTRADICTED (P0) — the re-read must actually OPEN the log ---
    def test_build_validation_expect_contains_absent_is_p0(self):
        """xfam P0#3: expect_contains was ignored (grep found zero refs in cx_module_quality). A PASS
        claim over a real passing log with an expect_contains marker ABSENT from that log must P0 —
        proves the marker is now checked, mirroring cx_evidence.py:90-93."""
        rc, out = self._mq("module_acceptance_build_validation_expect_contains_absent.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("expect_contains marker 'MARKER-THAT-IS-NOT-IN-THE-LOG' absent from the log", out)

    def test_build_validation_absolute_log_path_is_p0(self):
        """xfam P0#2: _read_log used an absolute log_path as-is → a claim could point at any
        always-passing file OUTSIDE the receipt dir. The hardened _read_log rejects absolute paths →
        None → P0 (does not resolve), fail-closed."""
        rc, out = self._mq("module_acceptance_build_validation_abs_log_path.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("does not resolve", out)

    def test_read_log_rejects_absolute_and_dotdot(self):
        """Direct unit on the hardened shared helper: an absolute path, a '..'-escape, and a path
        resolving outside the card dir all return None (fail-closed); a real relative log reads."""
        import cx_evidence
        d = FIXTURES / "logs"
        self.assertIsNone(cx_evidence._read_log(d, "/etc/hostname"))
        self.assertIsNone(cx_evidence._read_log(d, "../../../../etc/hostname"))
        self.assertIsNone(cx_evidence._read_log(d, "../module_registry_good.yaml"))
        self.assertIsNotNone(cx_evidence._read_log(d, "build_validation_pass.txt"))

    # --- BUILD-VALIDATION-CONTRADICTED (P0) — the re-read must actually OPEN the log ---
    def test_build_validation_contradicted_exit_is_p0_from_real_reread(self):
        """The log file EXISTS and resolves; the claim's own declared exit_code (1) is what
        contradicts it — proves the P0 fires from the exit-code re-read, not from a missing log."""
        rc, out = self._mq("module_acceptance_build_validation_contradicted_exit.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("exit_code 1 with no declared nonzero_pass_semantics", out)
        self.assertIn("fabricated PASS", out)

    def test_build_validation_contradicted_marker_is_p0_from_real_reread(self):
        """The log file logs/build_validation_fail_marker.txt EXISTS on disk and genuinely CONTAINS
        'ERROR' — the P0 fires because module-quality actually opened and scanned it, not because
        the log was absent (that is a distinct -REQUIRED/-CONTRADICTED unresolvable-log path)."""
        log = FIXTURES / "logs" / "build_validation_fail_marker.txt"
        self.assertTrue(log.is_file(), "fixture log must exist on disk for the re-read to be real")
        self.assertIn("ERROR", log.read_text(), "fixture log must genuinely contain the declared marker")
        rc, out = self._mq("module_acceptance_build_validation_contradicted_marker.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("fail_marker 'ERROR' present in the log", out)

    def test_build_validation_unresolvable_log_is_p0(self):
        """A claims row that claims PASS but whose log_path does not resolve on disk is a fabricated
        PASS (P0), fail-closed — never a silent skip."""
        with tempfile.TemporaryDirectory() as tmp:
            body = fix_text("module_acceptance_full_good.yaml").replace(
                "log_path: logs/build_validation_pass.txt",
                "log_path: logs/does-not-exist.txt")
            bundle = Path(tmp) / "module_acceptance_unresolvable_log.yaml"
            bundle.write_text(body, encoding="utf-8")
            rc, out = run_cx("check", "module-quality",
                             "--acceptance", str(bundle),
                             "--registry", fix("module_registry_good.yaml"),
                             "--module-id", "m1")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("does not resolve", out)

    def test_build_validation_real_pass_log_reread_passes(self):
        """Mirror good case: the log EXISTS and genuinely shows a PASS (exit 0, no fail markers) —
        the leg passes on true re-read evidence, not on an unread assertion."""
        log = FIXTURES / "logs" / "build_validation_pass.txt"
        self.assertTrue(log.is_file())
        self.assertNotIn("ERROR", log.read_text())
        rc, out = self._mq("module_acceptance_full_good.yaml")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    # --- BUILD-VALIDATION-SELF-GRADED ---
    def test_build_validation_self_graded_fails(self):
        rc, out = self._mq("module_acceptance_build_validation_self_graded.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("same-wave self-grading", out)

    # --- ANTI-SLOP-REQUIRED ---
    def test_no_anti_slop_fails(self):
        rc, out = self._mq("module_acceptance_no_anti_slop.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("anti_slop leg missing", out)

    # --- ANTI-SLOP-MALFORMED (all sub-classes) ---
    def test_anti_slop_bad_status_fails(self):
        rc, out = self._mq("module_acceptance_anti_slop_bad_status.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("anti_slop.status is 'PENDING'", out)

    def test_anti_slop_wrong_family_fails(self):
        rc, out = self._mq("module_acceptance_anti_slop_wrong_family.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("family_relation must be 'same_family'", out)

    def test_anti_slop_wrong_role_fails(self):
        rc, out = self._mq("module_acceptance_anti_slop_wrong_role.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("not 'slop_removal'", out)

    def test_anti_slop_missing_families_fails(self):
        rc, out = self._mq("module_acceptance_anti_slop_missing_families.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("reviewer_family/builder_family missing", out)

    def test_anti_slop_no_anchor_fails(self):
        rc, out = self._mq("module_acceptance_anti_slop_no_anchor.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("no evidence anchor", out)

    def test_anti_slop_empty_anchor_fails(self):
        """xfam P1#5: the anchor used field_present, so review_ref: [] passed with no real anchor.
        _str_field now requires a NON-EMPTY scalar ref."""
        rc, out = self._mq("module_acceptance_anti_slop_empty_anchor.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("no evidence anchor", out)

    # --- ANTI-SLOP-MALFORMED: identity required (xfam P1#4) ---
    def test_anti_slop_missing_identity_fails(self):
        """xfam P1#4: anti_slop.reviewer/builder were not required (unlike build_validation), so
        omitting builder silently bypassed the self-grading check. Both are now REQUIRED scalars."""
        rc, out = self._mq("module_acceptance_anti_slop_missing_identity.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("anti_slop.reviewer/builder identity missing", out)

    # --- ANTI-SLOP-SELF-GRADED ---
    def test_anti_slop_self_graded_fails(self):
        rc, out = self._mq("module_acceptance_anti_slop_self_graded.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("self-grading of the anti-slop pass", out)

    # --- #6: self-grading equality is case/space-insensitive (both legs) ---
    def test_self_grading_casefold_build_validation(self):
        """xfam #6: ' Sonnet ' vs 'sonnet' must still be caught as self-grading (casefold + strip)."""
        with tempfile.TemporaryDirectory() as tmp:
            body = fix_text("module_acceptance_full_good.yaml").replace(
                "reviewer: build-validator-agent\n    builder: cx-sonnet-builder",
                "reviewer: ' Sonnet '\n    builder: sonnet")
            bundle = Path(tmp) / "ma_casefold_bv.yaml"
            bundle.write_text(body, encoding="utf-8")
            rc, out = run_cx("check", "module-quality",
                             "--acceptance", str(bundle),
                             "--registry", fix("module_registry_good.yaml"),
                             "--module-id", "m1")
        self.assertEqual(rc, 1)
        self.assertIn("reviewer == builder", out)

    def test_self_grading_casefold_anti_slop(self):
        """xfam #6: anti_slop self-grading also casefold/strip-insensitive."""
        with tempfile.TemporaryDirectory() as tmp:
            body = fix_text("module_acceptance_full_good.yaml").replace(
                "reviewer: sonnet-anti-slop-reviewer\n    builder: cx-sonnet-builder",
                "reviewer: ' Slopper '\n    builder: slopper")
            bundle = Path(tmp) / "ma_casefold_as.yaml"
            bundle.write_text(body, encoding="utf-8")
            rc, out = run_cx("check", "module-quality",
                             "--acceptance", str(bundle),
                             "--registry", fix("module_registry_good.yaml"),
                             "--module-id", "m1")
        self.assertEqual(rc, 1)
        self.assertIn("anti_slop.reviewer == builder", out)


# ---------------------------------------------------------------------------
# defect ledger (V1.10) — post-ship CEO-found defects reuse open_findings
# ---------------------------------------------------------------------------
class TestDefectLedger(unittest.TestCase):
    def test_post_ship_defect_with_found_by_passes(self):
        rc, out = run_cx("check", "state", fix("state_good_post_ship_defect.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_post_ship_defect_without_found_by_fails(self):
        rc, out = run_cx("check", "state", fix("state_bad_post_ship_no_found_by.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("found_by", out)

    def test_open_post_ship_defect_blocks_final_ready(self):
        rc, out = run_cx("check", "final-ready", fix("state_good_post_ship_defect.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------
class TestCheckState(unittest.TestCase):
    def test_good_state_passes(self):
        rc, out = run_cx("check", "state", fix("state_good.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_bad_state_wrong_protocol_stamp(self):
        rc, out = run_cx("check", "state", fix("state_bad.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("protocol_stamp" in out.lower() or "Code-X V1" in out)

    def test_bad_state_counts_mismatch(self):
        rc, out = run_cx("check", "state", fix("state_bad.yaml"))
        self.assertEqual(rc, 1)
        self.assertTrue("counts" in out.lower() or "p0" in out.lower() or "items" in out.lower())

    def test_state_info_shows_current_card(self):
        rc, out = run_cx("check", "state", fix("state_good.yaml"))
        self.assertEqual(rc, 0)
        self.assertTrue("BUILD-001" in out or "current_card" in out.lower())


# ---------------------------------------------------------------------------
# PROP-025 — engine-epoch fix_cycles (EVAL-018)
# ---------------------------------------------------------------------------
class TestFixCyclesEngineEpoch(unittest.TestCase):
    """PROP-025: fix_cycles are validated against the engine epoch ACTIVE AT THE
    ATTEMPT (engine_switch_log), never the current engine."""

    def test_prior_epoch_seats_pass_after_switch_back(self):
        # Sample 2026-06-18 regression: GPT seats fixed under the CODEX epoch must PASS
        # even though active_build_engine has since switched back to CLAUDE_CODE.
        rc, out = run_cx("check", "state", fix("state_good_fix_cycles_epoch.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_single_epoch_wrong_family_still_fails(self):
        # bite (ii): a no-switch project recording GPT seats under a CLAUDE engine still fails.
        rc, out = run_cx("check", "state", fix("state_bad_fix_cycle_wrong_engine.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("epoch ran", out)

    def test_unresolvable_epoch_fails_closed(self):
        rc, out = run_cx("check", "state", fix("state_bad_fix_cycle_epoch_unresolvable.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("cannot resolve which engine epoch", out)

    def test_engine_family_cache_mismatch_fails(self):
        rc, out = run_cx("check", "state", fix("state_bad_fix_cycle_epoch_cache_mismatch.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("engine_family is a cache", out)

    def test_cross_epoch_reset_without_deviation_fails(self):
        rc, out = run_cx("check", "state", fix("state_bad_fix_cycle_cross_epoch_reset.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("across an engine switch", out)

    def test_malformed_switch_log_fails_closed(self):
        rc, out = run_cx("check", "state", fix("state_bad_engine_switch_log_malformed.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("switch row must record", out)

    def test_declared_family_with_legacy_ref_resolves(self):
        # GPT review F2 back-compat: a historical row with engine_family + engine_epoch_legacy_ref resolves.
        rc, out = run_cx("check", "state", fix("state_good_fix_cycles_epoch_legacy.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_declared_family_without_legacy_ref_fails_closed(self):
        # GPT review F2 bypass: a bare self-declared engine_family must NOT resolve the row.
        rc, out = run_cx("check", "state", fix("state_bad_fix_cycle_epoch_declared_no_legacy.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("cannot resolve which engine epoch", out)


# ---------------------------------------------------------------------------
# PROP-027 — pre-build dependency-scan gate (EVAL-019)
# ---------------------------------------------------------------------------
import hashlib as _hashlib
import tempfile as _tempfile


def _write_dep_repo(tmp, high=0, crit=0, lock_hash=None, write_lock=True,
                    waiver=False, extra_manifest=None, advisories=None):
    """Build a tiny repo (package.json + package-lock.json) and a dependency_scan receipt."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)
    with open(os.path.join(repo, "package.json"), "w") as f:
        f.write('{"name":"x","dependencies":{"a":"1.0.0"}}\n')
    if write_lock:
        labs = os.path.join(repo, "package-lock.json")
        with open(labs, "w") as f:
            f.write("lockfile-contents-v1\n")
        real = _hashlib.sha256(open(labs, "rb").read()).hexdigest()[:12]
    else:
        real = "deadbeef0000"
    if extra_manifest:
        with open(os.path.join(repo, extra_manifest), "w") as f:
            f.write("extra\n")
    h = lock_hash or real
    adv_block = (f"      high_critical_advisories: [{', '.join(advisories)}]\n") if advisories else ""
    cover = "[" + ", ".join(advisories) + "]" if advisories else "[GHSA-aaaa]"
    waiver_block = ("  waivers:\n"
                    "    - ceo_decision_ref: CEO-D-X\n"
                    f"      advisory_ids: {cover}\n"
                    "      package: a\n      severity: high\n"
                    "      reason: not reachable\n      mitigation: pinned\n"
                    "      expiry: '2026-12-01'\n      owner: dev\n") if waiver else "  waivers: []\n"
    receipt = ("dependency_scan:\n  scans:\n"
               "    - ecosystem: npm\n      command: npm audit\n"
               "      scanner_version: npm/10.8.0\n      db_timestamp: '2026-06-18T00:00:00Z'\n"
               "      manifest: package.json\n      lockfile: package-lock.json\n      package: a\n"
               f"      lockfile_hash: '{h}'\n      produced_at: '2026-06-18T09:00:00Z'\n"
               f"      high_count: {high}\n      critical_count: {crit}\n{adv_block}{waiver_block}")
    rpath = os.path.join(tmp, "receipt.yaml")
    with open(rpath, "w") as f:
        f.write(receipt)
    return repo, rpath


class TestDepScan(unittest.TestCase):
    """PROP-027: the pre-build supply-chain gate (cx check dep-scan + build-turn wiring)."""

    def test_clean_scan_passes(self):
        with _tempfile.TemporaryDirectory() as t:
            repo, r = _write_dep_repo(t)
            rc, out = run_cx("check", "dep-scan", r, "--repo-root", repo)
            self.assertEqual(rc, 0)
            self.assertIn("PASS", out)

    def test_high_critical_unenumerated_fails(self):
        with _tempfile.TemporaryDirectory() as t:
            repo, r = _write_dep_repo(t, high=2, crit=1)   # no high_critical_advisories listed
            rc, out = run_cx("check", "dep-scan", r, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("does not name exactly", out)

    def test_high_critical_waived_passes(self):
        with _tempfile.TemporaryDirectory() as t:
            repo, r = _write_dep_repo(t, high=1, crit=0, advisories=["GHSA-aaaa"], waiver=True)
            rc, out = run_cx("check", "dep-scan", r, "--repo-root", repo)
            self.assertEqual(rc, 0)
            self.assertIn("PASS", out)

    def test_high_critical_uncovered_advisory_fails(self):
        with _tempfile.TemporaryDirectory() as t:
            # advisory enumerated but the only waiver covers a different package/advisory
            repo, r = _write_dep_repo(t, high=1, crit=0, advisories=["GHSA-aaaa"])
            rc, out = run_cx("check", "dep-scan", r, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("need a typed CEO waiver", out)

    def test_stale_lockfile_hash_fails(self):
        with _tempfile.TemporaryDirectory() as t:
            repo, r = _write_dep_repo(t, lock_hash="deadbeef0000")
            rc, out = run_cx("check", "dep-scan", r, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("stale / forged", out)

    def test_uncovered_manifest_fails(self):
        with _tempfile.TemporaryDirectory() as t:
            repo, r = _write_dep_repo(t, extra_manifest="requirements.txt")
            rc, out = run_cx("check", "dep-scan", r, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("not covered by any dependency_scan", out)

    def test_build_turn_manifest_without_receipt_ref_fails(self):
        # build-turn branch (b): manifests under the repo but no dependency_scan_receipt_ref → fail closed.
        with _tempfile.TemporaryDirectory() as t:
            repo = os.path.join(t, "repo")
            os.makedirs(repo, exist_ok=True)
            with open(os.path.join(repo, "package.json"), "w") as f:
                f.write('{"name":"x"}\n')
            card = os.path.join(t, "card.yaml")
            with open(card, "w") as f:
                f.write("id: BUILD-X\nmode: FIX\n")
            state = os.path.join(t, "state.yaml")
            with open(state, "w") as f:
                f.write("project: t\nprotocol_stamp: Code-X V1\n")
            rc, out = run_cx("check", "build-turn", card, "--state", state, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("package-manager root must be scanned", out)

    def test_final_ready_manifest_requires_dep_receipt(self):
        # GPT review F5: a repo with a manifest may not ship without a dependency_scan_receipt_ref.
        with _tempfile.TemporaryDirectory() as t:
            repo = os.path.join(t, "repo")
            os.makedirs(repo, exist_ok=True)
            with open(os.path.join(repo, "package.json"), "w") as f:
                f.write('{"name":"x"}\n')
            state = os.path.join(t, "state.yaml")
            with open(state, "w") as f:
                f.write("protocol_stamp: Code-X V1\n")
            rc, out = run_cx("check", "final-ready", state, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("G8 re-scans dependencies", out)

    def test_build_turn_xfam_requires_coderabbit(self):
        # GPT review F1: a code-diff card + state declares xfam_capability + no CodeRabbit → mandatory.
        with _tempfile.TemporaryDirectory() as t:
            repo = os.path.join(t, "repo")
            os.makedirs(repo, exist_ok=True)
            card = os.path.join(t, "card.yaml")
            with open(card, "w") as f:
                f.write("id: BUILD-X\nmode: MODULE_BUILD\n")
            state = os.path.join(t, "state.yaml")
            with open(state, "w") as f:
                f.write("project: t\nprotocol_stamp: Code-X V1\nreview_boundary:\n  xfam_capability: stage_1\n")
            rc, out = run_cx("check", "build-turn", card, "--state", state, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("CodeRabbit is MANDATORY", out)

    def test_build_turn_untyped_coderabbit_receipt_fails(self):
        # GPT review F1: an arbitrary CodeRabbit receipt file is not a typed coderabbit_review artifact.
        with _tempfile.TemporaryDirectory() as t:
            repo = os.path.join(t, "repo")
            os.makedirs(repo, exist_ok=True)
            with open(os.path.join(repo, "cr.yaml"), "w") as f:
                f.write("some: junk\n")
            card = os.path.join(t, "card.yaml")
            with open(card, "w") as f:
                f.write("id: BUILD-X\nmode: FIX\ncoderabbit:\n  required: yes\n  receipt: cr.yaml\n")
            state = os.path.join(t, "state.yaml")
            with open(state, "w") as f:
                f.write("project: t\nprotocol_stamp: Code-X V1\n")
            rc, out = run_cx("check", "build-turn", card, "--state", state, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("not a typed coderabbit_review artifact", out)


# ---------------------------------------------------------------------------
# PROP-026 — scrub-before-egress gate (EVAL-020)
# ---------------------------------------------------------------------------
class TestEgress(unittest.TestCase):
    """PROP-026 / GPT #1: a raw diff to a mandatory external reviewer needs a bound
    egress_scrub receipt (positive control nonzero) or a typed local-only carve-out."""

    def test_no_receipt_blocks(self):
        rc, out = run_cx("check", "egress", fix("egress_diff_secret.txt"), "--target", "coderabbit")
        self.assertEqual(rc, 1)
        self.assertIn("NO scrub receipt and NO local-only carve-out", out)

    def test_good_scrub_passes(self):
        rc, out = run_cx("check", "egress", fix("egress_diff_clean.txt"), "--target", "coderabbit",
                         "--receipt", fix("egress_scrub_good.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_local_only_carveout_passes(self):
        rc, out = run_cx("check", "egress", fix("egress_diff_clean.txt"), "--target", "coderabbit",
                         "--receipt", fix("egress_carveout_good.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_unbound_scrub_blocks(self):
        rc, out = run_cx("check", "egress", fix("egress_diff_clean.txt"), "--target", "coderabbit",
                         "--receipt", fix("egress_scrub_wrong_hash.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("not bound to THIS diff", out)

    def test_scrub_contradicted_by_content_blocks(self):
        rc, out = run_cx("check", "egress", fix("egress_diff_secret.txt"), "--target", "coderabbit",
                         "--receipt", fix("egress_scrub_for_secret.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("contradicted by the diff content", out)


# ---------------------------------------------------------------------------
# PROP-026 — the 3-stage cross-family review ladder (xfam_capability, EVAL-021)
# ---------------------------------------------------------------------------
class TestXfamCapability(unittest.TestCase):
    """PROP-026 / GPT #4: xfam_capability is a fixed ladder, evidence-backed (stage_3
    needs real opposite-family evidence), append-only (a downgrade needs a CEO ref)."""

    def test_stage3_with_evidence_passes(self):
        rc, out = run_cx("check", "state", fix("state_good_xfam_capability.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_bad_enum_fails(self):
        rc, out = run_cx("check", "state", fix("state_bad_xfam_capability_enum.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("fixed ladder", out)

    def test_stage3_without_evidence_fails(self):
        rc, out = run_cx("check", "state", fix("state_bad_xfam_capability_stage3_no_evidence.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("without xfam_capability_evidence", out)

    def test_downgrade_without_ref_fails(self):
        rc, out = run_cx("check", "state", fix("state_bad_xfam_capability_downgrade_no_ref.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("needs a CEO decision ref", out)

    def test_evidence_unsafe_path_fails(self):
        # GPT review F6: stage_3 evidence ref escaping the repo (absolute) must not satisfy stage_3.
        rc, out = run_cx("check", "state", fix("state_bad_xfam_capability_evidence_unsafe.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("must be a repo-relative path", out)


# ---------------------------------------------------------------------------
# PROP-042-DRAFT / V1.21-candidate — review routing hardening from the a real project planning skip
# ---------------------------------------------------------------------------
class TestReviewRoutingHardening(unittest.TestCase):
    def test_build_state_rejects_coderabbit_not_applicable(self):
        rc, out = run_cx("check", "state", fix("state_bad_review_boundary_coderabbit_na.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("CodeRabbit", out)
        self.assertIn("MODULE_BUILD", out)

    def test_build_state_rejects_final_only_self_review_boundary(self):
        rc, out = run_cx("check", "state", fix("state_bad_review_boundary_self_final.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("self_review_boundary", out)
        self.assertIn("module", out)

    def test_codex_app_rejects_module_xfam_boundary(self):
        rc, out = run_cx("check", "state", fix("state_bad_codex_module_xfam_boundary.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("CODEX_APP", out)
        self.assertIn("whole-app", out)

    def test_final_xfam_route_requires_built_app_audit(self):
        rc, out = run_cx("check", "state", fix("state_bad_final_xfam_without_built_app_audit.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("Built-App Audit", out)
        self.assertIn("final xfam", out)

    def test_final_xfam_route_with_built_app_audit_passes(self):
        rc, out = run_cx("check", "state", fix("state_good_final_xfam_with_built_app_audit.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# PROP-026 — class-sweep self-audit (anti-whack-a-mole, EVAL-023)
# ---------------------------------------------------------------------------
class TestClassSweep(unittest.TestCase):
    """PROP-026 / GPT #6: a deterministic finding's fix ships a class-sweep receipt so one
    review resolves the whole class without re-review (trust = the test)."""

    def test_complete_sweep_passes(self):
        rc, out = run_cx("check", "class-sweep", fix("class_sweep_good.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_missing_fields_fails(self):
        rc, out = run_cx("check", "class-sweep", fix("class_sweep_bad_missing_fields.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("the sweep must name the class", out)

    def test_empty_hits_fails(self):
        rc, out = run_cx("check", "class-sweep", fix("class_sweep_bad_empty_hits.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("whack-a-mole is fixing one instance", out)

    def test_no_positive_control_fails(self):
        rc, out = run_cx("check", "class-sweep", fix("class_sweep_bad_no_positive_control.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("planted_instance_detected: yes", out)

    def test_no_regression_test_fails(self):
        rc, out = run_cx("check", "class-sweep", fix("class_sweep_bad_no_regression_test.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("TRUST is the test", out)

    def test_unsafe_regression_test_ref_fails(self):
        # GPT review F7: regression_test_ref escaping the repo (absolute) is rejected.
        rc, out = run_cx("check", "class-sweep", fix("class_sweep_bad_unsafe_test_ref.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("must be a repo-relative path", out)


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------
class TestCheckScope(unittest.TestCase):
    def test_good_diff_passes(self):
        rc, out = run_cx("check", "scope", fix("card_good.yaml"), fix("diff_good.txt"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_diff_touches_forbidden_file(self):
        rc, out = run_cx("check", "scope", fix("card_good.yaml"), fix("diff_bad_forbidden.txt"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue(".env" in out or "forbidden" in out.lower() or "secret" in out.lower())

    def test_nonexistent_diff_returns_fix_first(self):
        rc, out = run_cx("check", "scope", fix("card_good.yaml"), "/tmp/no_such_diff.txt")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------
class TestCheckEvidence(unittest.TestCase):
    def _write_card(self, tmp_dir, card_dict):
        import yaml
        p = Path(tmp_dir) / "card.yaml"
        p.write_text(yaml.dump(card_dict))
        return str(p)

    def test_good_card_no_evidence_required_passes(self):
        import yaml, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            card = {"id": "TEST-001", "mode": "MODULE_BUILD", "model_tier": "standard",
                    "objective": "Test.", "evidence_required": []}
            card_file = self._write_card(tmp, card)
            rc, out = run_cx("check", "evidence", card_file)
            self.assertEqual(rc, 0)
            self.assertIn("PASS", out)

    def test_missing_evidence_path_fires_fix_first(self):
        import yaml, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "evidence_output.txt")
            card = {"id": "TEST-002", "mode": "MODULE_BUILD", "model_tier": "standard",
                    "objective": "Test.", "evidence_required": [missing]}
            card_file = self._write_card(tmp, card)
            rc, out = run_cx("check", "evidence", card_file)
            self.assertEqual(rc, 1)
            self.assertIn("FIX-FIRST", out)

    def test_empty_evidence_file_fires_fix_first(self):
        import yaml, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "output.txt"
            ev.write_text("")
            card = {"id": "TEST-003", "mode": "MODULE_BUILD", "model_tier": "standard",
                    "objective": "Test.", "evidence_required": [str(ev)]}
            card_file = self._write_card(tmp, card)
            rc, out = run_cx("check", "evidence", card_file)
            self.assertEqual(rc, 1)
            self.assertIn("FIX-FIRST", out)

    def test_faked_pass_in_evidence_fires_fix_first(self):
        import yaml, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "test_output.txt"
            ev.write_text("assert True  # always passes\n")
            card = {"id": "TEST-004", "mode": "MODULE_BUILD", "model_tier": "standard",
                    "objective": "Test.", "evidence_required": [str(ev)]}
            card_file = self._write_card(tmp, card)
            rc, out = run_cx("check", "evidence", card_file)
            self.assertEqual(rc, 1)
            self.assertIn("FIX-FIRST", out)
            self.assertTrue("faked-pass" in out.lower() or "assert True" in out)


# ---------------------------------------------------------------------------
# cost
# ---------------------------------------------------------------------------
class TestCheckCost(unittest.TestCase):
    def test_good_cost_log_passes(self):
        rc, out = run_cx("check", "cost", fix("cost_log_good.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)

    def test_bad_cost_log_fires_fix_first(self):
        rc, out = run_cx("check", "cost", fix("cost_log_bad.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("model_tier" in out.lower() or "loop" in out.lower() or "over_read" in out.lower())

    def test_not_a_list_fires_fix_first(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("not: a-list\n")
            fname = f.name
        try:
            rc, out = run_cx("check", "cost", fname)
            self.assertEqual(rc, 1)
            self.assertIn("FIX-FIRST", out)
        finally:
            import os; os.unlink(fname)

    def test_missing_required_field_fires_fix_first(self):
        import yaml, tempfile, os
        log = [{"stage": "BUILDING", "model_tier": "standard", "result": "PASS"}]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(log, f)
            fname = f.name
        try:
            rc, out = run_cx("check", "cost", fname)
            self.assertEqual(rc, 1)
            self.assertIn("FIX-FIRST", out)
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# final-ready
# ---------------------------------------------------------------------------
class TestCheckFinalReady(unittest.TestCase):
    def test_good_final_ready_state_passes(self):
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)
        self.assertIn("READY", out)

    def test_bad_final_ready_state_fires_fix_first(self):
        rc, out = run_cx("check", "final-ready", fix("state_bad_final_ready.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("p0" in out.lower() or "current_card" in out.lower() or "findings" in out.lower())

    def test_final_ready_blocked_by_open_findings(self):
        rc, out = run_cx("check", "final-ready", fix("state_bad_final_ready.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("p0" in out.lower() or "findings" in out.lower())

    def test_final_ready_certificate_assembled_on_pass(self):
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        self.assertEqual(rc, 0)
        self.assertTrue("ASSEMBLED" in out or "verdict" in out.lower() or "READY" in out)

    def test_final_ready_requires_cross_family_receipt(self):
        """V1.10: shipping without the final cross-family receipt is forbidden (P0)."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_no_cross_family.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("cross-family", out)

    def test_final_ready_missing_verdict_blocks(self):
        """V1.10 (GPT P0-4): a final cross-family receipt with NO verdict must not silently ship."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_verdict_missing.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("no verdict", out)

    def test_final_ready_receipt_hash_mismatch_blocks(self):
        """V1.10 (GPT P0-4): final-ready opens + rehashes the receipt; a fabricated/stale hash blocks ship."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_receipt_hash.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("not bound to THIS artifact", out)

    def test_final_ready_receipt_content_mismatch_blocks(self):
        """V1.10 (GPT R2): receipt must be a TYPED artifact matching the state claim — state PASS over
        a receipt that says REJECTED is blocked (a bound blob is not a review)."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_receipt_content_mismatch.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("not the artifact", out)

    def test_final_ready_receipt_path_escape_blocks(self):
        """V1.10 (GPT R2): an absolute / traversal / symlink receipt path is rejected before any read."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_receipt_escape.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("repo-relative", out)

    def test_wrong_protocol_stamp_in_final_ready(self):
        import yaml, tempfile, os
        state = {
            "project": "test", "protocol_stamp": "Code-X v0.13",
            "current_stage": "BUILD_FACTORY", "current_mode": "FINAL_READY",
            "current_card": None, "current_actor": "claude",
            "next_actor": "CEO", "next_action": "done", "stop_status": "NONE",
            "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []},
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(state, f)
            fname = f.name
        try:
            rc, out = run_cx("check", "final-ready", fname)
            self.assertEqual(rc, 1)
            self.assertIn("FIX-FIRST", out)
            self.assertTrue("protocol_stamp" in out.lower() or "Code-X V1" in out)
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# consistency
# ---------------------------------------------------------------------------
class TestCheckConsistency(unittest.TestCase):
    def test_real_tree_passes(self):
        """Consistency check on the actual Code-X-V1 tree must PASS (exit 0)."""
        rc, out = run_cx("check", "consistency")
        self.assertEqual(rc, 0, f"Expected PASS on real tree (exit 0), got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_drifted_fixture_fires_fix_first(self):
        """A registry with a reworded canonical must fire FIX-FIRST naming rule+file."""
        reg = fix("consistency_registry_drifted.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("fix-card-test-edit", out)
        self.assertTrue("LESSONS.yaml" in out or "CX-CHECK-SPEC.md" in out)

    def test_bad_registry_missing_path_fires_fix_first(self):
        """A registry pointing at a non-existent file must fire FIX-FIRST."""
        reg = fix("consistency_registry_bad_missing_path.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("does not exist" in out.lower() or "no-such-file" in out or "DOES_NOT_EXIST" in out)

    def test_bad_registry_dup_id_fires_fix_first(self):
        """A registry with duplicate ids must fire FIX-FIRST."""
        reg = fix("consistency_registry_bad_dup_id.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("duplicate" in out.lower() or "eval-count" in out)

    def test_missing_registry_fires_fix_first(self):
        """Pointing at a non-existent registry file must fire FIX-FIRST."""
        rc, out = run_cx("check", "consistency", "--registry", "/tmp/no-such-registry.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)

    def test_meaning_flip_fires_fix_first(self):
        """KEY PROOF: a file that KEEPS the first canonical phrase but rewrites the rule to
        mean the OPPOSITE (dropping 'weaken') must fire FIX-FIRST.
        This is the meaning-flip class that single-token canonical silently misses.
        """
        reg = fix("consistency_registry_meaning_flip.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        self.assertEqual(rc, 1, (
            f"Expected FIX-FIRST (exit 1) — meaning-flip must be caught, got {rc}.\nOutput:\n{out}"
        ))
        self.assertIn("FIX-FIRST", out)
        self.assertIn("fix-card-test-edit", out)
        # Must name the missing phrase 'weaken' — not just the file
        self.assertIn("weaken", out)

    # P1-07
    def test_banned_negation_fires_fix_first(self):
        """P1-07: banned_negation phrase in appears_in file fires FIX-FIRST.
        BAD FIXTURE: lessons_banned_negation.yaml contains 'tests may be weakened'.
        BUG PROOF: before fix, banned_negations were not checked at all.
        """
        reg = fix("consistency_registry_banned_negation.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for banned_negation, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("banned_negation" in out.lower() or "tests may be weakened" in out)

    # P1-08
    def test_strict_mode_does_not_crash(self):
        """P1-08: --strict mode runs without crashing (exit 0 or 1, never 2)."""
        rc, out = run_cx("check", "consistency", "--strict")
        self.assertIn(rc, (0, 1),
            f"--strict must exit 0 or 1, got {rc}.\nOutput:\n{out}")


# ---------------------------------------------------------------------------
# EVAL-029 — prevention-first do-less ladder presence (PROP-024)
# ---------------------------------------------------------------------------
class TestDoLessLadderPresence(unittest.TestCase):
    """The ordered pre-write do-less ladder must stay present in BUILDER-STANDARD.md, pinned by the
    `prevention-first-ladder` rule-registry entry. Presence + anti-drift ONLY — never a mechanical
    'did the builder build less' gate (that would over-claim; module reviews judge the actual call).
    The registry canonical phrases are guarded against removal by TestCheckConsistency.test_real_tree_passes
    (drop one from the standard → cx check consistency goes red — BUILDER-STANDARD.md carries NO [RULE:]
    pointer, so the canonical phrases are genuinely required; built-code xfam P1-01); these tests
    additionally pin the self-check row + the rejected-idea text, which the registry canonical does not cover."""

    def test_ladder_and_selfcheck_present_in_builder_standard(self):
        std = (CX_ROOT / "BUILDER-STANDARD.md").read_text(encoding="utf-8")
        for anchor in (
            "do-less ladder",                          # the gate's name
            "decide what NOT to build first",          # the ordered-front-gate framing
            "The ladder NEVER cuts",                   # the binding list intro
            "CEO-locked design / UI",                  # the G3/G6 binding (synthesis hardening)
            "Do-less ladder walked, built only what survived: PASS | FIX-FIRST | STOP",  # self-check row
        ):
            self.assertIn(anchor, std,
                          f"BUILDER-STANDARD.md lost a do-less-ladder anchor: {anchor!r}")
        # built-code xfam P1-01: no [RULE:] pointer may sneak back — a pointer would short-circuit
        # the cx check consistency canonical check (full-pass), making EVAL-029's bite a no-op.
        self.assertNotIn("[RULE:prevention-first-ladder]", std,
                         "a [RULE:] pointer would defeat the consistency bite — keep the canonical phrases required")

    def test_rejected_source_ideas_stay_rejected(self):
        """The two ponytail ideas explicitly NOT imported must remain named as rejected — a future
        edit that quietly adopts 'code-first/minimal-prose' or 'YAGNI-on-tests' would break the
        verification spine + plain-English rule. (built-code xfam P2-01: assert BOTH explicit phrases,
        not only the conclusion sentence.)"""
        std = (CX_ROOT / "BUILDER-STANDARD.md").read_text(encoding="utf-8")
        self.assertIn("minimal prose / code-first", std)
        self.assertIn("YAGNI applies to tests too", std)
        self.assertIn("Prose and tests are never what you cut", std)

    def test_registry_entry_pins_the_ladder(self):
        reg = (CX_ROOT / "checkers" / "rule-registry.yaml").read_text(encoding="utf-8")
        self.assertIn("id: prevention-first-ladder", reg)
        std = (CX_ROOT / "BUILDER-STANDARD.md").read_text(encoding="utf-8")
        # every phrase the registry pins as canonical must really live in the standard
        for canonical in ("do-less ladder", "decide what NOT to build first", "The ladder NEVER cuts"):
            self.assertIn(canonical, std,
                          f"registry pins {canonical!r} but BUILDER-STANDARD.md lacks it")

    def test_strict_mode_design_history_ignored(self):
        """P1-08: design-history/ files are excluded from --strict FAIL."""
        rc, out = run_cx("check", "consistency", "--strict")
        if rc == 1:
            lines = out.splitlines()
            for line in lines:
                if "[P1]" in line and "design-history/" in line:
                    self.fail(f"design-history/ should be ignored under --strict:\n{line}")

    # P1-09
    def test_path_escape_fires_fix_first(self):
        """P1-09: appears_in path with .. escape must fire FIX-FIRST.
        BAD FIXTURE: consistency_registry_path_escape.yaml has '../../etc/passwd'.
        BUG PROOF: before fix, paths were not validated (could point outside Code-X root).
        """
        reg = fix("consistency_registry_path_escape.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for path escape, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue(
            "escape" in out.lower() or "absolute" in out.lower() or
            "rejected" in out.lower() or ".." in out
        )

    def test_absolute_registry_outside_root_fires_fix_first(self):
        """P1-09: --registry path outside Code-X root fires FIX-FIRST."""
        rc, out = run_cx("check", "consistency", "--registry", "/etc/passwd")
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for out-of-root registry, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)

    # P2-05
    def test_yaml_scan_no_crash(self):
        """P2-05: consistency scan covers .yaml files without crashing."""
        reg = fix("consistency_registry_stale_yaml.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        self.assertIn(rc, (0, 1), f"Must exit 0 or 1, not crash: {rc}.\nOutput:\n{out}")
        self.assertNotIn("FATAL", out)


# ---------------------------------------------------------------------------
# NEW: cx check card — P1-01, P1-06, P2-03
# ---------------------------------------------------------------------------
class TestCheckCardNewFindings(unittest.TestCase):
    # P1-06
    def test_audit_status_pending_fires_fix_first(self):
        """P1-06: audit_status=PENDING must be REJECTED.
        BAD FIXTURE: card_bad_audit_status_pending.yaml
        BUG PROOF: before fix, audit_status was not validated.
        """
        rc, out = run_cx("check", "card", fix("card_bad_audit_status_pending.yaml"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for PENDING audit_status, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("audit_status" in out.lower() or "pending" in out.lower())

    def test_empty_requirement_ids_fires_fix_first(self):
        """P1-06: source_section with empty requirement_ids must fail."""
        rc, out = run_cx("check", "card", fix("card_bad_audit_status_pending.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("requirement_ids" in out.lower() or "audit_status" in out.lower())

    # P1-01
    def test_foundation_checkpoint_missing_reason_fires_fix_first(self):
        """P1-01: foundation_checkpoint_required: yes with empty reason must fail.
        BAD FIXTURE: card_bad_foundation_checkpoint_no_reason.yaml
        BUG PROOF: before fix, foundation_checkpoint_reason was not checked.
        """
        rc, out = run_cx("check", "card", fix("card_bad_foundation_checkpoint_no_reason.yaml"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for missing foundation_checkpoint_reason, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("foundation_checkpoint" in out.lower() or "reason" in out.lower())

    # P2-03
    def test_estimate_tokens_over_ceiling_fires_fix_first(self):
        """P2-03: read.estimate_tokens > READ_BUDGET_TOKENS must fail.
        BAD FIXTURE: card_bad_estimate_tokens_over_ceiling.yaml (estimate_tokens: 9999)
        BUG PROOF: before fix, estimate_tokens was not checked.
        """
        rc, out = run_cx("check", "card", fix("card_bad_estimate_tokens_over_ceiling.yaml"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for over-ceiling estimate_tokens, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue(
            "estimate_tokens" in out.lower() or "ceiling" in out.lower() or "budget" in out.lower()
        )

    # P2-01
    def test_substitution_state_missing_pending_fires_fix_first(self):
        """P2-01: family_substituted:yes + state given but no CROSS_FAMILY_RECHECK_PENDING item → FAIL.
        BUG PROOF: before fix, --state was not accepted by cx check card at all.
        """
        import yaml, tempfile, os
        # Create a state file with NO CROSS_FAMILY_RECHECK_PENDING item
        state = {
            "project": "test", "protocol_stamp": "Code-X V1",
            "current_stage": "BUILD_FACTORY", "current_mode": "MODULE_BUILD",
            "current_card": "SUBST-001", "current_actor": "codex",
            "next_actor": "claude", "next_action": "build", "stop_status": "NONE",
            "last_commit": "abc123",
            "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []},
        }
        # Create a card with family_substituted: yes + ceo_authorization_ref
        card = {
            "id": "SUBST-001", "mode": "MODULE_BUILD", "actor": "codex",
            "model_tier": "standard",
            "objective": "Test substitution state check.",
            "source_map": {
                "locked_packet_id": "PKT-001", "locked_packet_hash": "abc123",
                "source_sections": [{"file": "SPEC.md", "section": "S1", "requirement_ids": ["R1"]}],
                "dependency_capsules": [],
            },
            "card_compilation": {
                "compiled_by": {"actor": "claude-opus", "family": "claude", "model": "claude-opus-4", "date": "2026-06-09"},
                "audited_by": {"actor": "gpt-5.5", "family": "gpt", "model": "gpt-5.5", "date": "2026-06-09"},
                "audit_status": "PASS",
            },
            "actor_record": {
                "executor": {"actor": "codex", "family": "gpt", "model": "gpt-5.3-codex"},
                "self_review": {"required": "yes", "actor": "codex", "family": "gpt"},
                "cross_review": {
                    "required": "yes", "actor": "codex", "family": "gpt",  # same family!
                    "family_substituted": "yes", "ceo_authorization_ref": "CEO-2026-06-09",
                    "recheck_when_opposite_family_available": "yes",
                },
                "fixer": {"actor": "codex", "family": "gpt"},
                "final_reviewer": {"required": "yes", "actor": "claude-opus", "family": "claude"},
            },
            "family_note": {"known_quirk": "gpt verbose", "leash": "lean"},
            "read": {"required": ["SPEC.md"], "forbidden": []},
            "allowed_files": ["src/main.py"], "forbidden_files": [".env"],
            "allowed_operations": ["write-python"], "forbidden_operations": ["broad-refactor"],
            "relevant_invariants": ["real-data-only"], "acceptance": ["tests pass"],
            "evidence_required": [],
            "security_tripwire": {
                "touches_auth": "no", "touches_secrets": "no",
                "touches_money_or_balances": "no", "touches_bank_or_pii": "no",
                "touches_upload_restore_import": "no",
                "touches_network_or_public_surface": "no",
                "touches_logs_or_error_output": "no",
            },
            "loop_budget": {"review_fix_cycles": 1, "verification_passes": 1,
                            "third_review_loop_allowed": False,
                            "self_heal_attempts": {"codex": 3, "claude_cross_family": "4 + final synthesis"}},
            "stop_conditions": [], "cost_budget": "5000 tokens",
            "state_update": "set current_card=null after PASS",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as sf:
            yaml.dump(state, sf); state_path = sf.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as cf:
            yaml.dump(card, cf); card_path = cf.name
        try:
            rc, out = run_cx("check", "card", card_path, "--state", state_path)
            self.assertEqual(rc, 1,
                f"Expected FIX-FIRST: substituted card + state missing CROSS_FAMILY_RECHECK_PENDING, "
                f"got {rc}.\nOutput:\n{out}")
            self.assertIn("FIX-FIRST", out)
            self.assertTrue("recheck" in out.lower() or "pending" in out.lower() or "cross_family" in out.lower())
        finally:
            os.unlink(state_path)
            os.unlink(card_path)


# ---------------------------------------------------------------------------
# NEW: cx check final-ready — P1-02
# ---------------------------------------------------------------------------
class TestCheckFinalReadyNewFindings(unittest.TestCase):
    def test_missing_gate_fields_fires_fix_first(self):
        """P1-02: zero findings but missing module_capsules_current etc. → NOT READY.
        BAD FIXTURE: state_bad_missing_gate_fields.yaml
        BUG PROOF: before fix, missing gate fields were silently treated as PASS.
        """
        rc, out = run_cx("check", "final-ready", fix("state_bad_missing_gate_fields.yaml"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for missing gate fields, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue(
            "module_capsules_current" in out.lower() or
            "absent" in out.lower() or
            "missing" in out.lower()
        )

    def test_gate_field_not_pass_fires_fix_first(self):
        """P1-02: gate field = PENDING (not PASS) must block READY."""
        import yaml, tempfile, os
        state = {
            "project": "test", "protocol_stamp": "Code-X V1",
            "current_stage": "BUILD_FACTORY", "current_mode": "FINAL_READY",
            "current_card": None, "current_actor": "claude",
            "next_actor": "CEO", "next_action": "done", "stop_status": "NONE",
            "last_commit": "abc123",
            "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []},
            "module_capsules_current": "PENDING",   # NOT PASS
            "module_regressions_pass": "PASS",
            "ceo_module_approvals_complete": "PASS",
            "security_closeout": "PASS",
            "recovery_proof": "PASS",
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(state, f)
            fname = f.name
        try:
            rc, out = run_cx("check", "final-ready", fname)
            self.assertEqual(rc, 1,
                f"Expected FIX-FIRST for PENDING gate field, got {rc}.\nOutput:\n{out}")
            self.assertIn("FIX-FIRST", out)
            self.assertTrue("module_capsules_current" in out.lower() or "pending" in out.lower())
        finally:
            os.unlink(fname)

    def test_all_gate_fields_pass_gives_ready(self):
        """P1-02 good case: all 5 gate fields PASS → READY."""
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("READY", out)


# ---------------------------------------------------------------------------
# NEW: cx check state — P2-02
# ---------------------------------------------------------------------------
class TestCheckStateNewFindings(unittest.TestCase):
    def test_missing_last_commit_fires_fix_first(self):
        """P2-02: state missing last_commit must fire FIX-FIRST.
        BAD FIXTURE: state_bad_last_commit_missing.yaml
        BUG PROOF: before fix, missing last_commit was silently ignored.
        """
        rc, out = run_cx("check", "state", fix("state_bad_last_commit_missing.yaml"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for missing last_commit, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("last_commit", out.lower())

    def test_good_state_with_last_commit_passes(self):
        """P2-02 good case: state with last_commit present passes."""
        rc, out = run_cx("check", "state", fix("state_good.yaml"))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# NEW: cx check scope — P1-03, P1-04
# ---------------------------------------------------------------------------
class TestCheckScopeNewFindings(unittest.TestCase):
    def test_empty_allowed_files_with_real_diff_fires_fix_first(self):
        """P1-04: empty allowed_files + non-REVIEW diff must FAIL.
        BAD FIXTURE: card_empty_allowed_files.yaml + diff_bad_empty_allowed_files.txt
        BUG PROOF: before fix, empty allowed_files skipped all checks (nothing to match against).
        """
        rc, out = run_cx("check", "scope", fix("card_empty_allowed_files.yaml"),
                          fix("diff_bad_empty_allowed_files.txt"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for empty allowed_files + real diff, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("allowed_files" in out.lower() or "empty" in out.lower())

    def test_money_tripwire_no_but_diff_touches_balance_fires_fix_first(self):
        """P1-03: touches_money_or_balances=no but diff touches balance.py must FAIL.
        BAD FIXTURE: card_money_tripwire_no.yaml + diff_bad_money.txt
        BUG PROOF: before fix, only 2 of 7 tripwire fields were checked.
        """
        rc, out = run_cx("check", "scope", fix("card_money_tripwire_no.yaml"),
                          fix("diff_bad_money.txt"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for money tripwire mismatch, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue(
            "money" in out.lower() or "balance" in out.lower() or "tripwire" in out.lower()
        )


# ---------------------------------------------------------------------------
# NEW: cx check evidence — P1-05, P2-06
# ---------------------------------------------------------------------------
class TestCheckEvidenceNewFindings(unittest.TestCase):
    def test_test_file_in_diff_without_authorisation_fires_fix_first(self):
        """P1-05: diff touches test file but fix_test_edits.allowed: no → FAIL.
        BAD FIXTURE: card_fix_test_edits_not_allowed.yaml + diff_bad_test_unauthorized.txt
        BUG PROOF: before fix, the broken 'any("test" in allowed_files)' shortcut was used.
        """
        rc, out = run_cx("check", "evidence",
                          fix("card_fix_test_edits_not_allowed.yaml"),
                          "--diff", fix("diff_bad_test_unauthorized.txt"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST for unauthorized test edit in diff, got {rc}.\nOutput:\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue(
            "test" in out.lower() and ("authoris" in out.lower() or "allowed" in out.lower())
        )

    def test_module_build_can_create_declared_test_outputs(self):
        """P1-05 is a FIX-card guard, not a module-build ban on writing tests."""
        import yaml, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            card = {
                "id": "MODTEST-001",
                "mode": "MODULE_BUILD",
                "model_tier": "standard",
                "objective": "Build module code and tests.",
                "allowed_operations": ["write-python", "write-test"],
                "allowed_files": ["app/module.py", "tests/test_module.py"],
                "new_outputs": ["app/module.py", "tests/test_module.py"],
                "evidence_required": [],
            }
            card_file = Path(tmp) / "card.yaml"
            card_file.write_text(yaml.dump(card))
            diff_file = Path(tmp) / "diff.txt"
            diff_file.write_text("app/module.py\ntests/test_module.py\n")

            rc, out = run_cx("check", "evidence", str(card_file), "--diff", str(diff_file))
            self.assertEqual(rc, 0,
                f"Expected PASS — MODULE_BUILD cards may create declared tests.\n"
                f"Got {rc}.\nOutput:\n{out}")
            self.assertIn("PASS", out)

    def test_evidence_path_resolves_relative_to_card_dir(self):
        """P2-06: evidence paths resolve from card dir not CWD.
        BUG PROOF: before fix, paths were resolved from CWD — running cx from a different
        directory would cause false 'path missing' failures.
        """
        import yaml, tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            # Create evidence file inside tmp
            ev_file = Path(tmp) / "EVIDENCE.md"
            ev_file.write_text("PASS — all checks passed\n")

            card = {
                "id": "EVPATH-001",
                "mode": "MODULE_BUILD",
                "model_tier": "standard",
                "objective": "Test path resolution.",
                "evidence_required": ["EVIDENCE.md"],  # relative to card dir
            }
            card_file = Path(tmp) / "card.yaml"
            card_file.write_text(yaml.dump(card))

            # Run from a DIFFERENT directory (checkers/)
            orig_cwd = os.getcwd()
            try:
                os.chdir(str(Path(__file__).parent.parent))
                rc, out = run_cx("check", "evidence", str(card_file))
            finally:
                os.chdir(orig_cwd)

            self.assertEqual(rc, 0,
                f"Expected PASS — relative evidence path should resolve from card dir, not CWD.\n"
                f"Got {rc}.\nOutput:\n{out}")
            self.assertIn("PASS", out)

    def test_evidence_path_resolves_relative_to_project_root_for_cards_dir(self):
        """PROP-041 follow-up: cards may declare repo-root evidence paths.
        a real project cards live under cards/ and require evidence/... at the project root; the
        checker must not turn that into cards/evidence/... and block a real build.
        """
        import yaml, tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir()
            cards = repo / "cards"
            cards.mkdir()
            ev_dir = repo / "evidence"
            ev_dir.mkdir()
            (ev_dir / "output.txt").write_text("PASS — real evidence\n")

            card = {
                "id": "EVPATH-002",
                "mode": "MODULE_BUILD",
                "model_tier": "standard",
                "objective": "Test project-root evidence path.",
                "evidence_required": ["evidence/output.txt"],
            }
            card_file = cards / "card.yaml"
            card_file.write_text(yaml.dump(card))

            orig_cwd = os.getcwd()
            try:
                os.chdir(str(Path(__file__).parent.parent))
                rc, out = run_cx("check", "evidence", str(card_file))
            finally:
                os.chdir(orig_cwd)

            self.assertEqual(rc, 0,
                f"Expected PASS — repo-root evidence path should resolve from project root.\n"
                f"Got {rc}.\nOutput:\n{out}")
            self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# ROUND 2: cx check card — F1 P1-01, F2 P1-06
# ---------------------------------------------------------------------------
class TestCheckCardRound2(unittest.TestCase):
    # F1 P1-01: dependent-card foundation blocking
    def test_dependent_card_blocked_when_checkpoint_unmet(self):
        """F1: dependent card blocked when dependency_capsule's checkpoint not in state."""
        rc, out = run_cx("check", "card",
                          fix("card_dependent_unmet_checkpoint.yaml"),
                          "--state", fix("state_foundation_unmet.yaml"))
        self.assertEqual(rc, 1,
            f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("FOUND-001", out)

    def test_dependent_card_passes_when_checkpoint_met(self):
        """F1 good path: checkpoint in state → PASS."""
        rc, out = run_cx("check", "card",
                          fix("card_dependent_unmet_checkpoint.yaml"),
                          "--state", fix("state_foundation_met.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_dependent_card_no_state_fails_closed(self):
        """A1 contract correction: without --state, a card with checkpoint-required dependency
        must FAIL CLOSED (not skip silently). This inverts the prior test which expected PASS."""
        rc, out = run_cx("check", "card", fix("card_dependent_unmet_checkpoint.yaml"))
        self.assertEqual(rc, 1, f"Expected FAIL CLOSED (exit 1) without --state, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertTrue("FAIL CLOSED" in out or "fail closed" in out or "--state" in out,
                        f"Expected fail-closed message in output:\n{out}")

    def test_foundation_card_does_not_self_block(self):
        """PROP-041(b): a FOUNDATION card (foundation_checkpoint_required: yes, with reason)
        must PASS its own `cx check card` even when its id is NOT yet in
        state.foundation_checkpoints_passed. The checkpoint can only be recorded AFTER the
        card builds + is xfam-reviewed (chicken-and-egg), so a self-block would make the
        foundation card unbuildable forever. Per GATES.md:48 the checkpoint blocks every
        DEPENDENT card, never the foundation card itself.
        PRE-FIX PROOF: cx_card.py self-blocked (returned exit 1) on unfixed code."""
        rc, out = run_cx("check", "card",
                          fix("card_foundation_self_unmet.yaml"),
                          "--state", fix("state_foundation_unmet.yaml"))
        self.assertEqual(rc, 0,
            f"Expected PASS (exit 0) — foundation card must not self-block, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    # F2 P1-06: empty source_sections
    def test_empty_source_sections_fails(self):
        """F2: source_map.source_sections: [] must FAIL."""
        rc, out = run_cx("check", "card", fix("card_empty_source_sections.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("source_sections", out.lower())

    # F2 P1-06: required work-order fields
    def test_missing_workorder_fields_fail(self):
        """F2: all 5 required work-order fields must appear in output when missing."""
        rc, out = run_cx("check", "card", fix("card_missing_workorder_fields.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        for f_name in ("relevant_invariants", "acceptance", "loop_budget",
                       "stop_conditions", "state_update"):
            self.assertIn(f_name, out.lower(),
                f"Expected '{f_name}' in output but missing.\n{out}")

    def test_good_card_still_passes_after_workorder_check(self):
        """F2 good path: fully filled work-order card still PASSes."""
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    # A2 P1-06: source_sections must be a non-empty LIST (string/mapping rejected)
    def test_source_sections_not_list_fails(self):
        """A2: source_sections as a string must FAIL (not just empty-list guard)."""
        rc, out = run_cx("check", "card", fix("card_bad_source_sections_not_list.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("source_sections", out.lower())

    # A3 P2-04: loop_budget.review_fix_cycles > 1 must FAIL at CARD level
    def test_review_fix_cycles_over_one_fails_at_card_level(self):
        """A3: card with loop_budget.review_fix_cycles: 2 must FAIL at card-check time."""
        rc, out = run_cx("check", "card", fix("card_bad_review_fix_cycles.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("review_fix_cycles", out.lower())

    def test_review_fix_cycles_one_passes_at_card_level(self):
        """A3 good path: card with loop_budget.review_fix_cycles: 1 must still PASS."""
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# ROUND 2: cx check consistency — F3 P1-09
# ---------------------------------------------------------------------------
class TestCheckConsistencyRound2(unittest.TestCase):
    def test_relative_registry_escape_rejected(self):
        """F3: relative --registry that escapes root must be rejected.
        PRE-FIX PROOF: current code loads the outside registry instead of rejecting.
        """
        import shutil
        outside = CX_ROOT.parent / "_cx_tmp_outside_registry.yaml"
        real_registry = CX_ROOT / "checkers" / "rule-registry.yaml"
        try:
            shutil.copy(str(real_registry), str(outside))
            rc, out = run_cx("check", "consistency", "--registry", "../_cx_tmp_outside_registry.yaml")
            self.assertEqual(rc, 1,
                f"Expected FIX-FIRST for relative escape, got {rc}.\n{out}")
            self.assertIn("FIX-FIRST", out)
            self.assertIn("escape", out.lower())
        finally:
            if outside.exists():
                outside.unlink()


# ---------------------------------------------------------------------------
# ROUND 2: cx check cost — F4 P2-04
# ---------------------------------------------------------------------------
class TestCheckCostRound2(unittest.TestCase):
    def test_review_fix_cycles_over_one_fails(self):
        """F4: review_fix_cycles: 2 must FAIL (one-and-done).
        PRE-FIX PROOF: wrongly returned PASS on unfixed code.
        """
        rc, out = run_cx("check", "cost", fix("cost_log_review_fix_cycles_over.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("review_fix_cycles", out.lower())
        self.assertIn("one-and-done", out.lower())

    def test_good_cost_log_no_review_fix_cycles_still_passes(self):
        """F4 good path: cost_log_good has no review_fix_cycles field → PASS."""
        rc, out = run_cx("check", "cost", fix("cost_log_good.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# ROUND 2: cx check final-ready — F5 P2-03
# ---------------------------------------------------------------------------
class TestCheckFinalReadyRound2(unittest.TestCase):
    def test_final_ready_card_evidence_resolves_from_any_cwd(self):
        """F5: --card evidence paths resolve relative to card dir, not CWD.
        PRE-FIX PROOF: running from /tmp returned FIX-FIRST (evidence path missing).
        """
        result = subprocess.run(
            [sys.executable, CX, "check", "final-ready",
             fix("state_good_final_ready.yaml"), "--card", fix("card_final_ready_relpath.yaml")],
            capture_output=True, text=True, cwd="/tmp")
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0,
            f"Expected PASS from /tmp, got {result.returncode}:\n{out}")

    def test_good_card_from_project_cwd_still_passes(self):
        """F5 good path (regression guard): good state still PASSes."""
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# ROUND 3: cx check final-ready — Built-App Audit precondition (v1.12)
# ---------------------------------------------------------------------------
class TestCheckFinalReadyBuiltAppAudit(unittest.TestCase):
    """B4: built_app_audit block required before final-ready (P0).

    State schema:
      built_app_audit:
        status: run
        report_ref: <repo-relative, non-symlink path inside repo>
        findings_dispositioned: true
    """

    def test_missing_built_app_audit_block_blocks_final_ready(self):
        """TDD Step 1: absent built_app_audit => P0 block."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_audit_missing.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST when built_app_audit absent, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("built_app_audit", out)

    def test_built_app_audit_status_not_run_blocks(self):
        """status != run => P0 block."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_audit_status.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("built_app_audit", out)

    def test_built_app_audit_findings_not_dispositioned_blocks(self):
        """findings_dispositioned != true => P0 block."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_audit_not_dispositioned.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("built_app_audit", out)

    def test_built_app_audit_bad_report_ref_absolute_blocks(self):
        """Absolute report_ref => P0 block (path-safety mirrors acceptance_ref)."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_audit_ref_absolute.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("built_app_audit", out)

    def test_built_app_audit_good_state_still_passes(self):
        """Good built_app_audit block => PASS (regression guard — state_good_final_ready must add the block)."""
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready_with_audit.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    # --- v1.12 FIX-1 / FIX-5: report_ref must point at a REAL existing audit report dir ---
    def test_built_app_audit_good_final_ready_still_passes(self):
        """FIX-1 regression: the canonical good state still PASSES — its report_ref now resolves to a
        real fixture audit dir (audit_reports/sample-2026-06-19/AUDIT-SUMMARY.md)."""
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_built_app_audit_nonexistent_report_ref_blocks(self):
        """FIX-1: a shape-valid + path-safe report_ref pointing at a NON-EXISTENT dir must BLOCK
        (the ceremonial-gate hole — existence is now enforced)."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_audit_ref_nonexistent.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST for nonexistent report_ref, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("does not exist", out)

    def test_built_app_audit_dotdot_report_ref_blocks(self):
        """FIX-5: a report_ref with a .. traversal segment must BLOCK before any read."""
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_audit_ref_dotdot.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST for .. report_ref, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("built_app_audit", out)

    def test_built_app_audit_symlink_report_ref_blocks(self):
        """FIX-5: a report_ref that is a symlink escaping the repo must BLOCK (constructed in a tmp dir,
        mirroring how the receipt symlink-escape is tested)."""
        import tempfile, os, shutil
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            # An external (out-of-tree) real dir the symlink points at
            external = base / "external_real"
            (external / "audit_reports").mkdir(parents=True)
            (external / "audit_reports" / "AUDIT-SUMMARY.md").write_text("x", encoding="utf-8")
            # The state lives in repo/; report_ref is a symlink inside repo/ that escapes to external
            repo = base / "repo"
            (repo / "audit_reports").mkdir(parents=True)
            os.symlink(external / "audit_reports", repo / "audit_reports" / "escaped")
            # A valid in-tree cross-family receipt so the ONLY finding is the audit symlink
            shutil.copy(fix("final_cross_family_receipt_good.yaml"),
                        repo / "final_cross_family_receipt_good.yaml")
            state_text = (
                fix_text("state_good_final_ready.yaml")
                .replace("report_ref: audit_reports/sample-2026-06-19",
                         "report_ref: audit_reports/escaped")
            )
            state_file = repo / "state.yaml"
            state_file.write_text(state_text, encoding="utf-8")
            rc, out = run_cx("check", "final-ready", str(state_file))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST for symlink report_ref, got {rc}.\n{out}")
            self.assertIn("FIX-FIRST", out)
            self.assertIn("built_app_audit", out)


# ---------------------------------------------------------------------------
# v1.12 FIX-3: checker version identity must match the shipping protocol version
# ---------------------------------------------------------------------------
class TestWholePacketReview(unittest.TestCase):
    """PROP-040 — the whole-packet integration gate. The contract clauses cover the receipt-content
    bites; these unit tests cover the --packet-dir path-safety the harness can't express via the fixed
    {REPO}/packet arg (an absolute EXTERNAL packet dir / a SYMLINK path component) — the xfam P1 fix."""

    @staticmethod
    def _mk(repo, packet_dir, *, hashval=None):
        """Write a valid receipt + state into <repo>. packet_dir binds the review's frozen_packet_hash
        (use hashval to skip the recompute when the check fails before currency). Returns the state path."""
        import hashlib
        h = hashval
        if h is None:
            sys.path.insert(0, str(CHECKERS_DIR))
            try:
                from cx_deck import _compute_packet_hash
                h = _compute_packet_hash(Path(packet_dir))
            finally:
                sys.path.pop(0)
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            from cx_deck import _compute_substantive_source_hash
            sub_h = _compute_substantive_source_hash(Path(packet_dir))
        finally:
            sys.path.pop(0)
        reviews = Path(repo) / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        receipt = reviews / "whole-packet-review.yaml"
        receipt.write_text(
            "whole_packet_review:\n  schema_version: 1\n  review_kind: WHOLE_PACKET_G7\n"
            f"  frozen_packet_hash: {h}\n  reviewed_source_set_hash: {sub_h}\n"
            "  authoring_family: anthropic\n  reviewer_family: gpt\n"
            "  three_leg_ask:\n    continuity: prior decisions re-checked\n    problems: no P0\n"
            "    approach_improvement: no simpler structure\n"
            "  verdict: PASS\n  findings_ref: reviews/whole-packet-review.md\n")
        rh = hashlib.sha256(receipt.read_bytes()).hexdigest()[:12]
        state = Path(repo) / "state.yaml"
        state.write_text(
            "project: x\npacket_dir: packet\nwhole_packet_review_receipt:\n"
            "  receipt: reviews/whole-packet-review.yaml\n"
            f'  receipt_hash: "{rh}"\n')
        return str(state)

    def test_good_passes(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"; repo.mkdir()
            packet = repo / "packet"
            shutil.copytree(FIXTURES / "module_start_good_packet", packet)
            state = self._mk(repo, packet)
            rc, out = run_cx("check", "whole-packet-review", "--state", state,
                             "--packet-dir", str(packet), "--repo-root", str(repo))
            self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
            self.assertIn("PASS", out)

    def test_packet_dir_outside_repo_root_rejected(self):
        """xfam P1: --packet-dir pointing at an EXTERNAL dir (outside --repo-root) must be rejected —
        else the G7 floor could bind the review to a non-project packet."""
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"; repo.mkdir()
            ext_packet = Path(tmp) / "external_packet"
            shutil.copytree(FIXTURES / "module_start_good_packet", ext_packet)
            state = self._mk(repo, ext_packet, hashval="0" * 64)
            rc, out = run_cx("check", "whole-packet-review", "--state", state,
                             "--packet-dir", str(ext_packet), "--repo-root", str(repo))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("not under --repo-root", out)

    def test_packet_dir_symlink_ancestor_rejected(self):
        """xfam P1: a SYMLINK between repo-root and the frozen packet must be rejected (it would point
        the packet at content OUTSIDE the repo)."""
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"; repo.mkdir()
            ext = Path(tmp) / "ext"; ext.mkdir()
            shutil.copytree(FIXTURES / "module_start_good_packet", ext / "packet")
            os.symlink(ext, repo / "link")             # repo/link -> external dir
            packet_via_link = repo / "link" / "packet"  # repo/link/packet
            state = self._mk(repo, packet_via_link, hashval="0" * 64)
            rc, out = run_cx("check", "whole-packet-review", "--state", state,
                             "--packet-dir", str(packet_via_link), "--repo-root", str(repo))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("is a symlink", out)

    def test_buildmeta_only_delta_carries(self):
        """Build-metadata-only registry edit (card_ids/dependency_modules/frozen_packet_hash/protocol_version)
        must NOT invalidate the WPR — the review carries (PROP-041)."""
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"; repo.mkdir()
            packet = repo / "packet"
            shutil.copytree(FIXTURES / "module_start_good_packet", packet)
            state = self._mk(repo, packet)
            # Now mutate ONLY build-metadata fields in MODULE-REGISTRY.yaml
            reg = packet / "MODULE-REGISTRY.yaml"
            txt = reg.read_text()
            reg.write_text(txt.replace("module_registry:\n", "module_registry:\n  protocol_version: \"1.99-test\"\n"))
            rc, out = run_cx("check", "whole-packet-review", "--state", state,
                             "--packet-dir", str(packet), "--repo-root", str(repo))
            self.assertEqual(rc, 0, f"Build-metadata-only delta should carry. rc={rc}\n{out}")

    def test_substantive_doc_change_invalidates(self):
        """Appending to requirements-manifest.yaml (substantive) invalidates the WPR (PROP-041)."""
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"; repo.mkdir()
            packet = repo / "packet"
            shutil.copytree(FIXTURES / "module_start_good_packet", packet)
            state = self._mk(repo, packet)
            mf = packet / "requirements-manifest.yaml"
            with open(mf, "ab") as f:
                f.write(b"\n# substantive-stale-marker\n")
            rc, out = run_cx("check", "whole-packet-review", "--state", state,
                             "--packet-dir", str(packet), "--repo-root", str(repo))
            self.assertEqual(rc, 1, f"Substantive change should invalidate. rc={rc}\n{out}")
            self.assertIn("SUBSTANTIVE packet doc", out)

    def test_registry_order_change_invalidates(self):
        """ANTI-LAUNDERING: a SUBSTANTIVE registry edit (a module title/set/order — NOT one of the
        four stripped build-metadata fields) MUST still invalidate the WPR. Proves the partial-strip
        of MODULE-REGISTRY.yaml cannot smuggle a real change past the carry (PROP-041)."""
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"; repo.mkdir()
            packet = repo / "packet"
            shutil.copytree(FIXTURES / "module_start_good_packet", packet)
            state = self._mk(repo, packet)
            reg = packet / "MODULE-REGISTRY.yaml"
            reg.write_text(reg.read_text().replace(
                "Expense category editor", "Expense category editor RENAMED"))
            rc, out = run_cx("check", "whole-packet-review", "--state", state,
                             "--packet-dir", str(packet), "--repo-root", str(repo))
            self.assertEqual(rc, 1, f"Substantive registry edit should invalidate. rc={rc}\n{out}")
            self.assertIn("SUBSTANTIVE packet doc", out)

    def test_missing_reviewed_source_set_hash_blocks(self):
        """A receipt with reviewed_source_set_hash absent is rejected (PROP-041)."""
        import shutil, hashlib
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"; repo.mkdir()
            packet = repo / "packet"
            shutil.copytree(FIXTURES / "module_start_good_packet", packet)
            sys.path.insert(0, str(CHECKERS_DIR))
            try:
                from cx_deck import _compute_packet_hash
                h = _compute_packet_hash(packet)
            finally:
                sys.path.pop(0)
            reviews = repo / "reviews"; reviews.mkdir()
            receipt = reviews / "whole-packet-review.yaml"
            receipt.write_text(
                "whole_packet_review:\n  schema_version: 1\n  review_kind: WHOLE_PACKET_G7\n"
                f"  frozen_packet_hash: {h}\n  reviewed_source_set_hash: \"\"\n"
                "  authoring_family: anthropic\n  reviewer_family: gpt\n"
                "  three_leg_ask:\n    continuity: prior decisions re-checked\n    problems: no P0\n"
                "    approach_improvement: no simpler structure\n"
                "  verdict: PASS\n  findings_ref: reviews/whole-packet-review.md\n")
            rh = hashlib.sha256(receipt.read_bytes()).hexdigest()[:12]
            state = repo / "state.yaml"
            state.write_text(
                "project: x\npacket_dir: packet\nwhole_packet_review_receipt:\n"
                "  receipt: reviews/whole-packet-review.yaml\n"
                f'  receipt_hash: "{rh}"\n')
            rc, out = run_cx("check", "whole-packet-review", "--state", str(state),
                             "--packet-dir", str(packet), "--repo-root", str(repo))
            self.assertEqual(rc, 1)
            self.assertIn("WHOLE-PACKET-REVIEW-SUBSTANTIVE-HASH-PRESENT", out)


class TestSubstantiveSourceHash(unittest.TestCase):
    """Unit tests for cx_deck._compute_substantive_source_hash — the anti-laundering hash
    that carve-out (c) keys WPR currency on (PROP-041). Gated copy of the test_cx.py mirror."""

    @staticmethod
    def _make_packet(base, files: dict):
        pkt = Path(base) / "packet"
        pkt.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            p = pkt / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(content)
        return pkt

    @staticmethod
    def _sub_hash(pkt):
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            from cx_deck import _compute_substantive_source_hash
            return _compute_substantive_source_hash(pkt)
        finally:
            sys.path.pop(0)

    def test_buildmeta_only_registry_edit_identical_hash(self):
        """Editing ONLY the four build-metadata fields yields the SAME substantive hash (carry)."""
        import yaml, copy
        base_reg = {"module_registry": {"frozen_packet_hash": "old-hash", "protocol_version": "1.0",
                                         "modules": [{"module_id": "m_a", "card_ids": ["C-001"],
                                                       "dependency_modules": ["m_b"],
                                                       "requirement_ids": ["REQ-001"]},
                                                      {"module_id": "m_b", "card_ids": [],
                                                       "dependency_modules": [], "requirement_ids": []}]}}
        manifest = "requirements:\n  - id: REQ-001\n    disposition: BUILDING\n"
        with tempfile.TemporaryDirectory() as tmp:
            pkt1 = self._make_packet(tmp + "/p1", {
                "requirements-manifest.yaml": manifest, "MODULE-REGISTRY.yaml": yaml.safe_dump(base_reg)})
            mutated = copy.deepcopy(base_reg)
            mutated["module_registry"]["frozen_packet_hash"] = "new-hash"
            mutated["module_registry"]["protocol_version"] = "1.99"
            mutated["module_registry"]["modules"][0]["card_ids"] = ["C-999"]
            mutated["module_registry"]["modules"][0]["dependency_modules"] = []
            pkt2 = self._make_packet(tmp + "/p2", {
                "requirements-manifest.yaml": manifest, "MODULE-REGISTRY.yaml": yaml.safe_dump(mutated)})
            self.assertEqual(self._sub_hash(pkt1), self._sub_hash(pkt2),
                             "build-metadata-only registry edit must yield identical substantive hash")

    def test_substantive_registry_edit_different_hash(self):
        """Editing a substantive registry field (a module title) yields a DIFFERENT hash (no laundering)."""
        import yaml, copy
        base_reg = {"module_registry": {"frozen_packet_hash": "h", "protocol_version": "1.0",
                                         "modules": [{"module_id": "m_a", "title": "Importer",
                                                       "card_ids": ["C-001"], "dependency_modules": [],
                                                       "requirement_ids": ["REQ-001"]}]}}
        with tempfile.TemporaryDirectory() as tmp:
            pkt1 = self._make_packet(tmp + "/p1", {"MODULE-REGISTRY.yaml": yaml.safe_dump(base_reg)})
            mutated = copy.deepcopy(base_reg)
            mutated["module_registry"]["modules"][0]["title"] = "Importer RENAMED"
            pkt2 = self._make_packet(tmp + "/p2", {"MODULE-REGISTRY.yaml": yaml.safe_dump(mutated)})
            self.assertNotEqual(self._sub_hash(pkt1), self._sub_hash(pkt2),
                                "substantive registry field edit must yield a different hash")

    def test_substantive_doc_edit_different_hash(self):
        """Editing a non-registry packet doc (TRD) yields a DIFFERENT hash."""
        with tempfile.TemporaryDirectory() as tmp:
            pkt1 = self._make_packet(tmp + "/p1", {"requirements-manifest.yaml": "requirements: []\n",
                                                    "TRD.md": "# TRD v1\n"})
            pkt2 = self._make_packet(tmp + "/p2", {"requirements-manifest.yaml": "requirements: []\n",
                                                    "TRD.md": "# TRD v2 CHANGED\n"})
            self.assertNotEqual(self._sub_hash(pkt1), self._sub_hash(pkt2),
                                "substantive doc edit must yield a different hash")

    def test_symlink_under_packet_raises_valueerror(self):
        """A symlink under the packet fails closed (ValueError) — same guard as _compute_packet_hash."""
        with tempfile.TemporaryDirectory() as tmp:
            pkt = self._make_packet(tmp + "/p", {"a.md": "x\n"})
            ext = Path(tmp) / "ext.md"; ext.write_text("y\n")
            os.symlink(ext, pkt / "link.md")
            self.assertRaises(ValueError, self._sub_hash, pkt)

    def test_date_typed_substantive_field_does_not_launder(self):
        """GPT xfam P2: a YAML date in a substantive registry field must NOT collapse to its string
        form (json default= coercion removed) — changing the date value MUST invalidate, never carry.
        Without the fix, json.dumps(default=str) hashed a date and its string form identically."""
        reg1 = ("module_registry:\n  frozen_packet_hash: h\n  modules:\n"
                "  - module_id: m_a\n    review_due: 2026-06-28\n    card_ids: [C-001]\n"
                "    dependency_modules: []\n    requirement_ids: [REQ-001]\n")
        reg2 = reg1.replace("2026-06-28", "2026-06-29")
        with tempfile.TemporaryDirectory() as tmp:
            pkt1 = self._make_packet(tmp + "/p1", {"MODULE-REGISTRY.yaml": reg1})
            pkt2 = self._make_packet(tmp + "/p2", {"MODULE-REGISTRY.yaml": reg2})
            self.assertNotEqual(self._sub_hash(pkt1), self._sub_hash(pkt2),
                "a date-typed substantive registry field must invalidate on change, not collapse")


class TestProtocolVersionIdentity(unittest.TestCase):
    def test_protocol_version_constant_marks_1_22_locked(self):
        """The checker reports v1.22 as the locked canonical protocol version (CEO-D-038, Audit Stage + SOP bind)."""
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            import cx_common
            self.assertEqual(cx_common.PROTOCOL_VERSION, "1.22.1")
        finally:
            sys.path.pop(0)

    def test_cx_version_reports_1_22_locked(self):
        """`cx --version` reports the locked v1.22 canonical version (not candidate)."""
        rc, out = run_cx("--version")
        self.assertEqual(rc, 0, f"Expected exit 0 from --version, got {rc}.\n{out}")
        self.assertRegex(out, r"V1\.22\.1(?!\d)")
        self.assertNotIn("candidate", out)

    def test_entrypoints_guard_old_python(self):
        """CXAUD-001: every checker entrypoint (cx, run.py, run_contracts.py) fail-fasts on
        Python <3.10 with a clear message — the modules use PEP 604 `X | None` unions, so an
        older interpreter must not reach a raw import-time TypeError (a false red)."""
        for name in ("cx", "tests/run.py", "tests/run_contracts.py"):
            src = (CHECKERS_DIR / name).read_text()
            self.assertIn("sys.version_info < (3, 10)", src,
                          f"{name} lost its Python-version guard (CXAUD-001 regression)")
            self.assertIn("3.10+", src,
                          f"{name} guard must name the Python 3.10+ requirement (CXAUD-001)")


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# deck
# ---------------------------------------------------------------------------
class TestCheckDeck(unittest.TestCase):
    def test_good_deck_passes(self):
        rc, out = run_cx("check", "deck", fix("deck_good_cards"), fix("deck_good_packet"))
        self.assertEqual(rc, 0, f"Expected PASS (exit 0), got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_good_deck_coverage_summary_in_output(self):
        rc, out = run_cx("check", "deck", fix("deck_good_cards"), fix("deck_good_packet"))
        self.assertEqual(rc, 0)
        self.assertIn("coverage:", out)
        self.assertIn("building/covered", out)

    def test_good_deck_lists_non_building_ids(self):
        rc, out = run_cx("check", "deck", fix("deck_good_cards"), fix("deck_good_packet"))
        self.assertEqual(rc, 0)
        self.assertIn("REQ-002", out)
        self.assertIn("REQ-003", out)

    def test_missing_building_requirement_bites_p0(self):
        rc, out = run_cx("check", "deck",
                         fix("deck_bad_missing_building_cards"),
                         fix("deck_bad_missing_building_packet"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("[P0]", out)

    def test_not_building_without_ceo_ref_bites_p1(self):
        rc, out = run_cx("check", "deck",
                         fix("deck_bad_not_building_no_ref_cards"),
                         fix("deck_bad_not_building_no_ref_packet"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("[P1]", out)
        self.assertIn("ceo_decision_ref", out.lower())

    def test_ghost_requirement_bites_p1(self):
        rc, out = run_cx("check", "deck",
                         fix("deck_bad_ghost_cards"),
                         fix("deck_bad_ghost_packet"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("[P1]", out)
        self.assertIn("ghost", out.lower())
        self.assertIn("REQ-999", out)

    def test_hash_mismatch_bites_p0(self):
        rc, out = run_cx("check", "deck",
                         fix("deck_bad_hash_mismatch_cards"),
                         fix("deck_bad_hash_mismatch_packet"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (exit 1), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("[P0]", out)
        self.assertIn("hash", out.lower())

    def test_na_without_reason_bites_p1(self):
        import tempfile, hashlib
        with tempfile.TemporaryDirectory() as tmpdir:
            pdir = Path(tmpdir) / "pkt"
            cdir = Path(tmpdir) / "cards"
            pdir.mkdir()
            cdir.mkdir()
            (pdir / "spec.md").write_text("dummy")
            (pdir / "requirements-manifest.yaml").write_text(
                "requirements:\n"
                "  - id: REQ-A\n"
                "    disposition: NOT_APPLICABLE\n"
            )
            files = sorted([p for p in pdir.rglob("*") if p.is_file()],
                           key=lambda p: p.relative_to(pdir).as_posix())
            h = hashlib.sha256()
            for p in files:
                rel = p.relative_to(pdir).as_posix().encode()
                h.update(rel); h.update(b"\x00"); h.update(p.read_bytes())
            real_hash = h.hexdigest()
            (cdir / "card.yaml").write_text(
                f"id: BUILD-X\nmode: MODULE_BUILD\nactor: codex\n"
                f"source_map:\n"
                f"  locked_packet_id: P\n"
                f"  locked_packet_hash: {real_hash}\n"
                f"  source_sections:\n"
                f"    - file: spec.md\n"
                f"      section: S\n"
                f"      requirement_ids: []\n"
            )
            rc, out = run_cx("check", "deck", str(cdir), str(pdir))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("FIX-FIRST", out)
            self.assertIn("[P1]", out)
            self.assertIn("reason", out.lower())

    def test_empty_requirements_list_bites_p1(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pdir = Path(tmpdir) / "pkt"
            cdir = Path(tmpdir) / "cards"
            pdir.mkdir()
            cdir.mkdir()
            (pdir / "requirements-manifest.yaml").write_text("requirements: []\n")
            rc, out = run_cx("check", "deck", str(cdir), str(pdir))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("FIX-FIRST", out)
            self.assertIn("[P1]", out)

    def test_manifest_absolute_escape_rejected(self):
        rc, out = run_cx("check", "deck",
                         fix("deck_good_cards"),
                         fix("deck_good_packet"),
                         "--manifest", "/etc/passwd")
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)

    def test_malformed_manifest_bites_p1(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pdir = Path(tmpdir) / "pkt"
            cdir = Path(tmpdir) / "cards"
            pdir.mkdir()
            cdir.mkdir()
            (pdir / "requirements-manifest.yaml").write_text("requirements: [unclosed\n  bad: :")
            rc, out = run_cx("check", "deck", str(cdir), str(pdir))
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("FIX-FIRST", out)
            self.assertIn("[P1]", out)


# ---------------------------------------------------------------------------
# --session-start mode
# ---------------------------------------------------------------------------
def _git_init(repo_dir):
    subprocess.run(["git", "init", "-q", repo_dir], check=True)
    subprocess.run(["git", "-C", repo_dir, "config", "user.email", "cx@test"], check=True)
    subprocess.run(["git", "-C", repo_dir, "config", "user.name", "cx"], check=True)


def _git_commit(repo_dir, msg="init"):
    subprocess.run(["git", "-C", repo_dir, "commit", "-q", "--allow-empty", "-m", msg], check=True)
    return subprocess.run(
        ["git", "-C", repo_dir, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


_STATE_BASE_SS = {
    "project": "cx-test", "protocol_stamp": "Code-X V1",
    "current_stage": "BUILD_FACTORY", "current_mode": "MODULE_BUILD",
    "current_card": "BUILD-001", "current_actor": "codex",
    "next_actor": "claude", "next_action": "cross-review", "stop_status": "NONE",
    "build_authorized": "yes",
    "active_build_engine": "CLAUDE_CODE",
    "orchestrator_model": "opus max",
    "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []},
    "cost_this_week": {"cards_run": 1, "top_model_cards": 0, "cheap_model_cards": 0,
                       "full_reviews": 0, "loops_used": 1, "waste_alarm": "LOW"},
    # PROP-014: build-mode sessions must acknowledge BUILDER-STANDARD.md at session start.
    # PROP-042 Part B: a build session declares it runs as an orchestrator dispatching subagents.
    "session_start": {
        "builder_standard_read": {
            "status": "PASS", "file": "BUILDER-STANDARD.md", "hash": "deadbeef0123",
            "read_by": "cx-test", "timestamp": "2026-06-10T00:00:00"},
        "orchestration_mode": {"dispatch_subagents": "yes", "lead_role": "orchestrator"},
        # PROP-042 Part E: build sessions declare SEE-AND-TEST demo mode (R-DEMO).
        "module_demo_mode": {"demo_every_user_facing_module": "yes", "surfaces": ["web", "mobile"]}},
    # PROP-020: reviewer taxonomy/timing as typed state (required at session-start in build modes).
    "review_boundary": {
        "deterministic_checks_each_card": "yes",
        "coderabbit_before_self_review": "yes",
        "self_review_boundary": "module",
        "cross_family_boundary": "module",
        "xfam_capability": "stage_1",
    },
}


def _write_state_ss(path, last_commit, wip=None, boot=False):
    import yaml
    state = dict(_STATE_BASE_SS)
    state["last_commit"] = last_commit
    if wip is not None:
        state["wip_continuation"] = wip
    with open(path, "w") as f:
        yaml.dump(state, f)
    if boot:
        # PROP-018: a PASS-expecting build-mode state needs the machine-generated
        # boot receipt acknowledged — run cx check boot and reference its output.
        import hashlib
        repo = None
        # boot needs the repo root; recipes keep state next to the repo dir
        candidate = os.path.join(os.path.dirname(path), "repo")
        repo = candidate if os.path.isdir(candidate) else os.path.dirname(path)
        receipt = os.path.join(os.path.dirname(path), "protocol-boot-receipt.yaml")
        run_cx("check", "boot", "--state", path, "--repo-root", repo, "--out", receipt)
        with open(receipt, "rb") as f:
            sha12 = hashlib.sha256(f.read()).hexdigest()[:12]
        state["session_start"] = dict(state["session_start"])
        state["session_start"]["protocol_boot_ack"] = {
            "receipt": receipt, "receipt_hash": sha12,
            "acked_by": "cx-test", "timestamp": "2026-06-12T00:00:00"}
        with open(path, "w") as f:
            yaml.dump(state, f)


class TestCheckStateSessionStart(unittest.TestCase):

    def test_ancestor_ok_passes(self):
        """Clean tree, last_commit == HEAD → PASS."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            sha = _git_commit(repo, "second")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, sha, boot=True)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
            self.assertIn("PASS", out)

    def test_foreign_lineage_bites_p1(self):
        """last_commit is sha from a different repo → P1."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            other = os.path.join(tmp, "other")
            _git_init(other)
            foreign_sha = _git_commit(other, "foreign")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, foreign_sha)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("[P1]", out)
            self.assertTrue("history" in out.lower() or "ancestor" in out.lower() or
                            "worktree" in out.lower())

    def test_unknown_sha_bites_p1(self):
        """Well-formed sha not present in repo → P1."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            unknown_sha = "deadbeef" * 5  # 40 hex chars not in this repo
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, unknown_sha)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("[P1]", out)

    def test_dirty_unmarked_bites_p1(self):
        """Dirty tree, no wip_continuation → P1."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            sha = _git_commit(repo, "first")
            with open(os.path.join(repo, "dirty.txt"), "w") as f:
                f.write("dirty\n")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, sha)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("[P1]", out)
            self.assertTrue("uncommitted" in out.lower() or "wip" in out.lower() or
                            "dirty" in out.lower())

    def test_wip_marked_passes(self):
        """Dirty tree + wip_continuation marked with owner+handoff → PASS."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            sha = _git_commit(repo, "first")
            with open(os.path.join(repo, "dirty.txt"), "w") as f:
                f.write("dirty\n")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, sha, wip={
                "marked": "yes", "owner_card": "BUILD-007",
                "handoff_ref": "handoffs/2026-06-10-wip.md",
            }, boot=True)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
            self.assertIn("PASS", out)

    def test_wip_unowned_bites_p2(self):
        """wip_continuation marked: yes but missing owner_card/handoff_ref → P2."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            sha = _git_commit(repo, "first")
            with open(os.path.join(repo, "dirty.txt"), "w") as f:
                f.write("dirty\n")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, sha, wip={"marked": "yes"})
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
            self.assertIn("[P2]", out)
            self.assertTrue("owner_card" in out.lower() or "handoff_ref" in out.lower() or
                            "unowned" in out.lower())

    def test_behind_3_warns_but_exits_0(self):
        """6 commits; last_commit = first sha; clean tree → exit 0 + WARN in stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            first_sha = _git_commit(repo, "commit-1")
            for i in range(2, 7):
                _git_commit(repo, f"commit-{i}")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, first_sha, boot=True)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertEqual(rc, 0, f"Expected exit 0 (advisory only), got {rc}.\n{out}")
            self.assertIn("PASS", out)
            self.assertIn("WARN:", out)

    def test_session_start_without_repo_root_errors(self):
        """--session-start without --repo-root must FIX-FIRST."""
        rc, out = run_cx("check", "state", fix("state_good.yaml"), "--session-start")
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (missing --repo-root), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("--repo-root", out)

    def test_back_compat_state_good_without_session_start(self):
        """Existing state_good.yaml still passes without --session-start."""
        rc, out = run_cx("check", "state", fix("state_good.yaml"))
        self.assertEqual(rc, 0, f"Back-compat FAIL: state_good.yaml got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_orchestration_mode_missing_bites(self):
        """PROP-042 Part B: a build-mode session-start state without
        session_start.orchestration_mode bites (R-ORCH)."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            sha = _git_commit(repo, "second")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, sha)
            with open(state) as f:
                data = yaml.safe_load(f)
            data["session_start"].pop("orchestration_mode", None)
            with open(state, "w") as f:
                yaml.dump(data, f)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertNotEqual(rc, 0, f"missing orchestration_mode must bite.\n{out}")
            self.assertIn("orchestration_mode", out)

    def test_orchestration_mode_inline_waiver_needs_ceo_ref(self):
        """PROP-042 Part B: inline_waiver without ceo_decision_ref bites."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            sha = _git_commit(repo, "second")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, sha)
            with open(state) as f:
                data = yaml.safe_load(f)
            data["session_start"]["orchestration_mode"] = {"inline_waiver": "yes"}
            with open(state, "w") as f:
                yaml.dump(data, f)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            self.assertNotEqual(rc, 0, f"inline_waiver without ceo_decision_ref must bite.\n{out}")
            self.assertIn("ceo_decision_ref", out)


class TestCLISurface(unittest.TestCase):
    def test_help_lists_check_subcommand(self):
        rc, out = run_cx("--help")
        self.assertEqual(rc, 0)
        self.assertIn("check", out)

    def test_check_help_lists_eight_subcommands(self):
        rc, out = run_cx("check", "--help")
        self.assertEqual(rc, 0)
        for sub in ["card", "state", "scope", "evidence", "cost", "final-ready", "consistency", "deck"]:
            self.assertIn(sub, out, f"Missing subcommand '{sub}' in help output:\n{out}")

    def test_no_args_returns_usage_error(self):
        rc, _ = run_cx()
        self.assertEqual(rc, 2)

    def test_unknown_subcommand_returns_usage_error(self):
        rc, _ = run_cx("check", "run")
        self.assertEqual(rc, 2)


# ---------------------------------------------------------------------------
# PROP-005/012: consistency sweep scope
# ---------------------------------------------------------------------------
class TestConsistencyScanScope(unittest.TestCase):
    def test_real_tree_zero_warns(self):
        """ACCEPTANCE: with scan_scope declared, the canonical tree sweeps clean —
        zero WARN lines. A future WARN here is a true positive demanding action."""
        rc, out = run_cx("check", "consistency")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        warns = [l for l in out.splitlines() if l.startswith("WARN")]
        self.assertEqual(warns, [], f"Expected 0 WARNs on canonical tree:\n" + "\n".join(warns))

    def test_strict_real_tree_passes(self):
        """ACCEPTANCE: --strict on the canonical tree is now the protocol-change
        gate — must PASS (was 56 false P1s before PROP-005/012)."""
        rc, out = run_cx("check", "consistency", "--strict")
        self.assertEqual(rc, 0, f"--strict must PASS on canonical tree, got {rc}.\n{out}")

    def test_scoped_sweep_warns_in_scope_with_d4_message(self):
        """KERNEL.md in scan_scope, full canonical present, not in appears_in →
        WARN with the D4 'register it in appears_in' duplication message."""
        rc, out = run_cx("check", "consistency", "--registry", fix("consistency_registry_scoped.yaml"))
        self.assertEqual(rc, 0, f"Normal mode stays PASS (WARN only), got {rc}.\n{out}")
        self.assertIn("KERNEL.md", out)
        self.assertIn("register it in appears_in", out)

    def test_scoped_sweep_strict_bites_in_scope(self):
        """Same fixture under --strict → P1 FAIL (scope shrink must never un-bite)."""
        rc, out = run_cx("check", "consistency", "--registry",
                         fix("consistency_registry_scoped.yaml"), "--strict")
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("[P1]", out)
        self.assertIn("KERNEL.md", out)

    def test_scoped_sweep_out_of_scope_silent(self):
        """STATUS.md / handoffs/ / design-history/ are out of the fixture's scope —
        no WARN or P1 may name them, in either mode."""
        for extra in ([], ["--strict"]):
            rc, out = run_cx("check", "consistency", "--registry",
                             fix("consistency_registry_scoped.yaml"), *extra)
            for needle in ("STATUS.md", "handoffs/", "design-history/"):
                for line in out.splitlines():
                    if (line.startswith("WARN") or "[P1]" in line) and needle in line:
                        self.fail(f"out-of-scope {needle} surfaced ({extra}):\n{line}")

    def test_registry_and_fixtures_never_swept(self):
        """Structural exemptions: the registry itself and checkers/tests/ never
        produce sweep output on the canonical tree."""
        rc, out = run_cx("check", "consistency")
        for line in out.splitlines():
            if line.startswith("WARN"):
                self.assertNotIn("rule-registry.yaml", line)
                self.assertNotIn("checkers/tests/", line)


# ---------------------------------------------------------------------------
# cx check packet — PROP-031 external-visual-reference capture + lock (v1.13)
# ---------------------------------------------------------------------------
class TestCheckPacketProp031(unittest.TestCase):
    def test_style_locked_still_passes_with_provenance(self):
        """Regression: a cat-14-DONE packet passes once it declares visual_provenance."""
        rc, out = run_cx("check", "packet", fix("packet_good_style_locked"))
        self.assertEqual(rc, 0, f"style_locked should PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_external_reference_good_passes(self):
        rc, out = run_cx("check", "packet", fix("packet_prop031_external_good"))
        self.assertEqual(rc, 0, f"external_good should PASS, got {rc}.\n{out}")

    def test_missing_provenance_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_no_provenance"))
        self.assertEqual(rc, 1)
        self.assertIn("look-source unstated (P-PROP-004)", out)

    def test_external_uncaptured_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_uncaptured"))
        self.assertEqual(rc, 1)
        self.assertIn("the captured reference must be pinned inside the packet (P-PROP-004)", out)

    def test_capture_hash_mismatch_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_capture_hash"))
        self.assertEqual(rc, 1)
        self.assertIn("file_hash mismatch", out)

    def test_fidelity_language_warns_but_does_not_block(self):
        rc, out = run_cx("check", "packet", fix("packet_warn_prop031_fidelity_lang"))
        self.assertEqual(rc, 0, f"advisory WARN must not block, got {rc}.\n{out}")
        self.assertIn("WARN:", out)
        self.assertIn("reads like an external reference", out)

    # built-code review hardening (GPT/Codex thread 019ee299, fix-first)
    def test_empty_screens_list_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_empty_screens"))
        self.assertEqual(rc, 1)
        self.assertIn("declares no user-facing screen", out)

    def test_short_hash_rejected(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_short_hash"))
        self.assertEqual(rc, 1)
        self.assertIn("is not a lowercase-hex sha256 prefix", out)


# ---------------------------------------------------------------------------
# cx check packet — PROP-023 WRITING-stage front-end hardening (v1.13):
#   (a) clarify-before-freeze  (b) testable acceptance criterion
# ---------------------------------------------------------------------------
class TestCheckPacketProp023(unittest.TestCase):
    def test_good_packet_passes_with_sweep_and_acceptance(self):
        """Regression: packet_good now carries clarification-sweep.md + a structured
        acceptance_criterion on its BUILDING row, and still PASSes."""
        rc, out = run_cx("check", "packet", fix("packet_good"))
        self.assertEqual(rc, 0, f"packet_good should PASS, got {rc}.\n{out}")
        self.assertIn("clarify-before-freeze", out)

    def test_missing_sweep_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_clarify_no_sweep"))
        self.assertEqual(rc, 1)
        self.assertIn("absence of markers is not proof the sweep ran", out)

    def test_open_marker_blocks_freeze(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_clarify_open_marker"))
        self.assertEqual(rc, 1)
        self.assertIn("unresolved '[NEEDS-CLARIFICATION", out)

    def test_clarification_ref_must_resolve_to_ledger_row(self):
        """A ceo_decision_ref that LOOKS valid (CEO-D-99999) but names no real ledger row
        is rejected — built-code review P1: the presence-only check was not ledger-bound."""
        rc, out = run_cx("check", "packet", fix("packet_bad_clarify_inline_dismissal"))
        self.assertEqual(rc, 1)
        self.assertIn("does not resolve to a", out)

    def test_acceptance_criterion_required_on_building(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_acceptance_missing"))
        self.assertEqual(rc, 1)
        self.assertIn("no 'acceptance_criterion' block", out)

    def test_placeholder_acceptance_field_bites(self):
        """Present-but-placeholder (pass_condition: TBD) is not a filled-in criterion."""
        rc, out = run_cx("check", "packet", fix("packet_bad_acceptance_placeholder"))
        self.assertEqual(rc, 1)
        self.assertIn("missing/placeholder/non-string", out)
        self.assertIn("pass_condition", out)

    def test_nonstring_acceptance_field_bites(self):
        """A non-string acceptance value (pass_condition: true) must not pass via
        str-coercion — built-code review P1."""
        rc, out = run_cx("check", "packet", fix("packet_bad_acceptance_nonstring"))
        self.assertEqual(rc, 1)
        self.assertIn("missing/placeholder/non-string", out)


# ---------------------------------------------------------------------------
# cx check design-fidelity — PROP-031 external_capture lock binding + receipt
# ---------------------------------------------------------------------------
class TestCheckDesignFidelityProp031(unittest.TestCase):
    def _run(self, manifest):
        return run_cx("check", "design-fidelity",
                      "--manifest", fix(manifest),
                      "--dom", fix("dom_good.html"),
                      "--screenshot", fix("screenshot_good.png"))

    def test_external_capture_lock_good_passes(self):
        rc, out = self._run("ui_lock_manifest_external_good.yaml")
        self.assertEqual(rc, 0, f"external_capture good lock should PASS, got {rc}.\n{out}")

    def test_missing_side_by_side_receipt_bites_p0(self):
        rc, out = self._run("ui_lock_manifest_external_no_receipt.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("no side_by_side_accept receipt", out)

    def test_viewport_dimension_mismatch_bites_p1(self):
        rc, out = self._run("ui_lock_manifest_external_dim_mismatch.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P1]", out)
        self.assertIn("not judged at the same viewport", out)


# ---------------------------------------------------------------------------
# PROP-034 — lock-fidelity continuity (anti-drift across corrections + handoffs)
# ---------------------------------------------------------------------------
import shutil as _shutil
import yaml as _yaml

_LF_PKT = FIXTURES / "module_start_good_packet"


def _lf_packet(repo):
    _shutil.copytree(_LF_PKT, os.path.join(repo, "packet"))


def _lf_write_card(cards, fname, cid, module_id, reqs, allowed=None, mode="MODULE_BUILD",
                   anchor=None, dev=None):
    c = {"id": cid, "mode": mode, "module_id": module_id,
         "source_map": {"source_sections": [{"file": "x", "section": "y", "requirement_ids": reqs}]}}
    if allowed is not None:
        c["allowed_files"] = allowed
    if anchor is not None:
        c["lock_anchor_ref"] = anchor
    if dev is not None:
        c["deviation_class"] = dev
    with open(os.path.join(cards, fname), "w") as f:
        _yaml.dump(c, f)


class TestLockFidelityDrift(unittest.TestCase):
    """Lever C — cx check drift. Layer 1 deterministic BLOCKS at --at-acceptance, advisory (rc 0)
    at session-start; an authorized SCOPE_CHANGE's off-lock req is logged scope, not silent drift."""

    def _setup(self, tmp, ghost):
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        _lf_packet(repo)
        cards = os.path.join(repo, "cards")
        os.makedirs(cards)
        b1 = ["REQ-001", "REQ-002"] + (["REQ-999"] if ghost else [])
        _lf_write_card(cards, "b1.yaml", "BUILD-001", "m1", b1)
        _lf_write_card(cards, "b2.yaml", "BUILD-002", "m2", ["REQ-003"])
        _lf_write_card(cards, "b3.yaml", "BUILD-003", "m3", ["REQ-004"])
        state = os.path.join(tmp, "state.yaml")
        with open(state, "w") as f:
            _yaml.dump({"project": "lf", "protocol_stamp": "Code-X V1", "packet_dir": "packet",
                        "accepted_modules": [], "current_card": "BUILD-001"}, f)
        return repo, state, cards

    def test_session_start_is_advisory_even_with_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, cards = self._setup(tmp, ghost=True)
            rc, out = run_cx("check", "drift", "--state", state, "--repo-root", repo, "--cards-dir", cards)
            self.assertEqual(rc, 0, f"session-start drift must NEVER block a boot.\n{out}")
            self.assertIn("REQ-999", out, "the divergence is still surfaced as advisory")

    def test_at_acceptance_blocks_on_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, cards = self._setup(tmp, ghost=True)
            rc, out = run_cx("check", "drift", "--state", state, "--repo-root", repo,
                             "--cards-dir", cards, "--at-acceptance")
            self.assertEqual(rc, 1)
            self.assertIn("LOCK-FIDELITY-DRIFT-UNLOGGED", out)

    def test_at_acceptance_clean_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, cards = self._setup(tmp, ghost=False)
            rc, out = run_cx("check", "drift", "--state", state, "--repo-root", repo,
                             "--cards-dir", cards, "--at-acceptance")
            self.assertEqual(rc, 0, f"a clean deck must PASS at acceptance.\n{out}")

    def test_authorized_scope_change_is_not_unlogged_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            os.makedirs(repo)
            _lf_packet(repo)
            cards = os.path.join(repo, "cards")
            os.makedirs(cards)
            _lf_write_card(cards, "b1.yaml", "BUILD-001", "m1", ["REQ-001", "REQ-002"])
            _lf_write_card(cards, "b2.yaml", "BUILD-002", "m2", ["REQ-003"])
            _lf_write_card(cards, "b3.yaml", "BUILD-003", "m3", ["REQ-004"])
            c = {"id": "FIX-SC", "mode": "FIX", "module_id": "m1",
                 "deviation_class": "SCOPE_CHANGE", "ceo_decision_ref": "CEO-D-X",
                 "packet_amendment_ref": "packet/AM-1.md",
                 "lock_anchor_ref": {"card_id": "BUILD-001", "requirement_id": "REQ-001"},
                 "allowed_files": [],
                 "source_map": {"source_sections": [
                     {"file": "x", "section": "y", "requirement_ids": ["REQ-NEW-1"]}]}}
            with open(os.path.join(cards, "fix.yaml"), "w") as f:
                _yaml.dump(c, f)
            state = os.path.join(tmp, "state.yaml")
            with open(state, "w") as f:
                _yaml.dump({"project": "lf", "protocol_stamp": "Code-X V1", "packet_dir": "packet",
                            "accepted_modules": [], "current_card": "FIX-SC"}, f)
            rc, out = run_cx("check", "drift", "--state", state, "--repo-root", repo,
                             "--cards-dir", cards, "--at-acceptance")
            self.assertEqual(rc, 0, f"an authorized SCOPE_CHANGE's off-lock req is not drift.\n{out}")


class TestLockFidelityOpenCardDerivation(unittest.TestCase):
    """Lever B — the open-card set = cards of frozen-registry modules NOT receipt-VERIFIED-accepted."""

    def _accept_repo_with_receipt(self, tmp):
        """A git repo + frozen packet + a state recording m1 accepted with a REAL bound, sha-verified,
        in-repo acceptance receipt (the only kind validate_accepted_module() passes). Returns
        (repo, base_sha, receipt_sha12)."""
        import hashlib
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        _lf_packet(repo)
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "first"], check=True)
        base = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        with open(os.path.join(repo, "b.txt"), "w") as f:
            f.write("two\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "second"], check=True)
        os.makedirs(os.path.join(repo, "acc"))
        receipt = os.path.join(repo, "acc", "m1.yaml")
        with open(receipt, "w") as f:
            f.write("module_acceptance:\n  module_id: m1\n  verdict: accepted\n  generated_by: cx\n"
                    "  state_sha_before: abc123\n  quality_card_hash: qc001122334455\n"
                    f"  repo_sha_before: {base}\n")
        with open(receipt, "rb") as rf:
            sha = hashlib.sha256(rf.read()).hexdigest()[:12]
        return repo, base, sha

    def test_accepting_a_module_with_a_bound_receipt_shrinks_the_open_set(self):
        sys.path.insert(0, str(CHECKERS_DIR))
        from cx_lock_fidelity import recompute_open_cards
        with tempfile.TemporaryDirectory() as tmp:
            repo, _base, sha = self._accept_repo_with_receipt(tmp)
            none_accepted = recompute_open_cards(repo, "packet", {"accepted_modules": []})[0]
            self.assertEqual(none_accepted, ["BUILD-001", "BUILD-002", "BUILD-003"])
            # A REAL bound, sha-verified, in-repo receipt for m1 — its card drops out of the open set.
            m1_accepted = recompute_open_cards(repo, "packet",
                {"accepted_modules": [{"module_id": "m1", "acceptance_ref": "acc/m1.yaml",
                                       "acceptance_sha12": sha}]})[0]
            self.assertEqual(m1_accepted, ["BUILD-002", "BUILD-003"],
                             "a receipt-VERIFIED m1 must drop BUILD-001 from the open set")

    def test_raw_accepted_id_with_no_receipt_does_not_shrink_the_open_set(self):
        """F4 fail-closed: a hand-authored accepted_modules row with NO bound acceptance receipt is
        NOT proof of acceptance — its cards STAY OPEN. This closes the forgery where any row with a
        module_id made open_cards: [] verify (PROP-034 xfam F4)."""
        sys.path.insert(0, str(CHECKERS_DIR))
        from cx_lock_fidelity import recompute_open_cards
        with tempfile.TemporaryDirectory() as tmp:
            repo, _base, _sha = self._accept_repo_with_receipt(tmp)
            forged = recompute_open_cards(repo, "packet",
                {"accepted_modules": [{"module_id": "m1"}]})[0]
            self.assertEqual(forged, ["BUILD-001", "BUILD-002", "BUILD-003"],
                             "a raw module_id with no bound receipt must NOT close BUILD-001 — "
                             "its card stays OPEN (F4 fail-closed)")


class TestLockFidelityFrozenRegistryIntegrity(unittest.TestCase):
    """F5 — _frozen_registry fails closed on the same integrity faults the v1.10 order wall rejects;
    open-card derivation NEVER silently drops a malformed/duplicate row (which would hide cards)."""

    def _packet_with_registry(self, tmp, registry_yaml: str) -> str:
        """A packet dir with the given MODULE-REGISTRY.yaml body + a valid manifest. Returns repo root."""
        repo = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(repo, "packet"))
        with open(os.path.join(repo, "packet", "requirements-manifest.yaml"), "w") as f:
            f.write("requirements:\n  - id: REQ-001\n    disposition: BUILDING\n")
        with open(os.path.join(repo, "packet", "MODULE-REGISTRY.yaml"), "w") as f:
            f.write(registry_yaml)
        return repo

    def test_duplicate_module_id_fails_closed(self):
        sys.path.insert(0, str(CHECKERS_DIR))
        from cx_lock_fidelity import recompute_open_cards
        reg = ("module_registry:\n  frozen_packet_hash: g1\n  modules:\n"
               "    - module_id: m1\n      card_ids: [BUILD-001]\n      dependency_modules: []\n"
               "    - module_id: m1\n      card_ids: [BUILD-099]\n      dependency_modules: []\n")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._packet_with_registry(tmp, reg)
            cards, err = recompute_open_cards(repo, "packet", {"accepted_modules": []})
            self.assertIsNone(cards, "a duplicate module_id must NOT yield a (possibly card-hiding) set")
            self.assertIsNotNone(err)
            self.assertIn("duplicate module_id", err)

    def test_malformed_row_fails_closed(self):
        sys.path.insert(0, str(CHECKERS_DIR))
        from cx_lock_fidelity import recompute_open_cards
        reg = ("module_registry:\n  frozen_packet_hash: g1\n  modules:\n"
               "    - module_id: m1\n      card_ids: [BUILD-001]\n      dependency_modules: []\n"
               "    - just-a-string-not-a-mapping\n")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._packet_with_registry(tmp, reg)
            cards, err = recompute_open_cards(repo, "packet", {"accepted_modules": []})
            self.assertIsNone(cards, "a malformed row must fail closed, not be silently dropped")
            self.assertIsNotNone(err)
            self.assertIn("not a mapping", err)

    def test_unknown_dependency_fails_closed(self):
        sys.path.insert(0, str(CHECKERS_DIR))
        from cx_lock_fidelity import recompute_open_cards
        reg = ("module_registry:\n  frozen_packet_hash: g1\n  modules:\n"
               "    - module_id: m1\n      card_ids: [BUILD-001]\n      dependency_modules: [m_ghost]\n")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._packet_with_registry(tmp, reg)
            cards, err = recompute_open_cards(repo, "packet", {"accepted_modules": []})
            self.assertIsNone(cards)
            self.assertIsNotNone(err)
            self.assertIn("unregistered module_id", err)

    def test_well_formed_registry_still_derives(self):
        sys.path.insert(0, str(CHECKERS_DIR))
        from cx_lock_fidelity import recompute_open_cards
        reg = ("module_registry:\n  frozen_packet_hash: g1\n  modules:\n"
               "    - module_id: m1\n      card_ids: [BUILD-001]\n      dependency_modules: []\n"
               "    - module_id: m2\n      card_ids: [BUILD-002]\n      dependency_modules: [m1]\n")
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._packet_with_registry(tmp, reg)
            cards, err = recompute_open_cards(repo, "packet", {"accepted_modules": []})
            self.assertIsNone(err, f"a clean registry must still derive: {err}")
            self.assertEqual(cards, ["BUILD-001", "BUILD-002"])


class TestLockFidelityDeviationBlocksAcceptance(unittest.TestCase):
    """An OPEN lock_deviation row blocks module-acceptance (logged ambiguity can never quietly ship)."""

    def _accept_repo(self, tmp, deviations):
        import hashlib
        repo = os.path.join(tmp, "repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("one\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "first"], check=True)
        base = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        with open(os.path.join(repo, "b.txt"), "w") as f:
            f.write("two\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "second"], check=True)
        os.makedirs(os.path.join(repo, "acc"))
        receipt = os.path.join(repo, "acc", "m1.yaml")
        with open(receipt, "w") as f:
            f.write("module_acceptance:\n  module_id: m1\n  verdict: accepted\n  generated_by: cx\n"
                    "  state_sha_before: abc123\n  quality_card_hash: qc001122334455\n"
                    f"  repo_sha_before: {base}\n")
        with open(receipt, "rb") as rf:
            sha = hashlib.sha256(rf.read()).hexdigest()[:12]
        state = os.path.join(tmp, "state.yaml")
        st = {"project": "lf", "protocol_stamp": "Code-X V1",
              "accepted_modules": [{"module_id": "m1", "acceptance_ref": "acc/m1.yaml",
                                    "acceptance_sha12": sha}]}
        if deviations is not None:
            st["lock_deviations"] = deviations
        with open(state, "w") as f:
            _yaml.dump(st, f)
        return repo, state

    def test_open_deviation_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._accept_repo(tmp, [{
                "deviation_id": "LD-1", "card_id": "FIX-1",
                "lock_anchor_ref": "BUILD-001/REQ-001", "deviation_class": "AMBIGUITY_RESOLVED",
                "reason": "picked reading X", "status": "OPEN",
                "surfaced_at_gate": "module-acceptance"}])
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", state, "--repo-root", repo)
            self.assertEqual(rc, 1)
            self.assertIn("is OPEN at the module-acceptance gate", out)

    def test_ceo_reviewed_deviation_does_not_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._accept_repo(tmp, [{
                "deviation_id": "LD-1", "card_id": "FIX-1",
                "lock_anchor_ref": "BUILD-001/REQ-001", "deviation_class": "AMBIGUITY_RESOLVED",
                "reason": "picked reading X", "status": "CEO_REVIEWED",
                "surfaced_at_gate": "module-acceptance"}])
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", state, "--repo-root", repo)
            self.assertEqual(rc, 0, f"a CEO_REVIEWED deviation must not block.\n{out}")

    def test_no_deviations_key_does_not_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, state = self._accept_repo(tmp, None)
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", state, "--repo-root", repo)
            self.assertEqual(rc, 0, f"absent lock_deviations must not block (back-compat).\n{out}")


# ---------------------------------------------------------------------------
# blueprint (PROP-039 v1.18 — the per-module BLUEPRINT-READY gate)
# ---------------------------------------------------------------------------
class TestCheckBlueprint(unittest.TestCase):
    """PROP-039: cx check blueprint recomputes module readiness from canonical sources — a complete +
    CEO-approved + source-current + reviewed-where-required module is BLUEPRINT-READY; every soft spot
    (stale receipt, missing anchor, omitted control, unreviewed high-risk, hidden finding) bites."""

    GOOD = "blueprint_good_packet"
    STATE = "blueprint_good_state.yaml"
    APPROVAL = "blueprint_good_approval.yaml"

    @classmethod
    def setUpClass(cls):
        # Regenerate the fixture tree deterministically (correct recomputed hashes) so the tests
        # are self-healing and never depend on stale committed fixtures.
        subprocess.run([sys.executable, str(FIXTURES / "_gen_blueprint_fixtures.py")], check=True)

    def _run(self, packet, module, state=None, approval=None):
        return run_cx("check", "blueprint", fix(packet), "--module", module,
                      "--state", fix(state or self.STATE), "--approval", fix(approval or self.APPROVAL))

    def test_good_screen_module_ready(self):
        rc, out = self._run(self.GOOD, "home")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)
        self.assertIn("BLUEPRINT-READY", out)

    def test_good_shared_logic_module_ready(self):
        rc, out = self._run(self.GOOD, "rounding")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_all_modules_ready(self):
        rc, out = run_cx("check", "blueprint", fix(self.GOOD), "--all",
                         "--state", fix(self.STATE), "--approval", fix(self.APPROVAL))
        self.assertEqual(rc, 0, f"Expected PASS for --all, got {rc}.\n{out}")

    def test_missing_manifest_fails(self):
        rc, out = run_cx("check", "blueprint", fix("blueprint_bad_no_manifest_packet"),
                         "--module", "home", "--state", fix(self.STATE), "--approval", fix(self.APPROVAL))
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("manifest", out.lower())

    def test_stale_approval_fails_p0(self):
        rc, out = self._run(self.GOOD, "home", approval="blueprint_bad_stale_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("BLUEPRINT-APPROVAL-CURRENT", out)
        self.assertIn("STALE", out)

    def test_missing_ceo_approval_fails_p0(self):
        rc, out = self._run(self.GOOD, "home", approval="blueprint_bad_no_ceo_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("no CEO approval", out)

    def test_wrong_manifest_hash_fails_p0(self):
        rc, out = self._run(self.GOOD, "home", approval="blueprint_bad_manifest_hash_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("BLUEPRINT-MANIFEST-HASH-BOUND", out)

    def test_anchor_coverage_fails_p0(self):
        rc, out = self._run("blueprint_bad_anchor_coverage_packet", "home",
                            approval="blueprint_bad_anchor_coverage_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("BLUEPRINT-ANCHOR-COVERAGE", out)
        self.assertIn("INCOMPLETE", out)

    def test_anchor_resolves_fails(self):
        rc, out = self._run("blueprint_bad_anchor_resolves_packet", "home",
                            approval="blueprint_bad_anchor_resolves_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-ANCHOR-RESOLVES", out)

    def test_design_lock_mismatch_fails(self):
        rc, out = self._run("blueprint_bad_design_lock_packet", "home",
                            approval="blueprint_bad_design_lock_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-SCREEN-DESIGN-LOCKED", out)

    def test_dangling_nav_fails(self):
        rc, out = self._run("blueprint_bad_nav_packet", "home",
                            approval="blueprint_bad_nav_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-NAV-COMPLETE", out)

    def test_control_without_contract_fails(self):
        rc, out = self._run("blueprint_bad_control_contract_packet", "home",
                            approval="blueprint_bad_control_contract_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-CONTROL-HAS-CONTRACT", out)

    def test_feature_without_done_test_fails(self):
        rc, out = self._run("blueprint_bad_done_test_packet", "home",
                            approval="blueprint_bad_done_test_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-FEATURE-HAS-DONE-TEST", out)

    def test_open_clarification_fails(self):
        rc, out = self._run("blueprint_bad_clarification_packet", "home",
                            approval="blueprint_bad_clarification_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-NO-OPEN-CLARIFICATION", out)

    def test_high_risk_without_review_receipt_fails(self):
        rc, out = self._run(self.GOOD, "home", approval="blueprint_bad_no_review_receipt.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-REVIEW-RECEIPT", out)

    def test_hidden_severity_fails(self):
        rc, out = self._run(self.GOOD, "home", state="blueprint_bad_hidden_severity_state.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-NO-HIDDEN-SEVERITY", out)

    def test_per_kind_fields_fails(self):
        rc, out = self._run("blueprint_bad_per_kind_packet", "rounding",
                            approval="blueprint_bad_per_kind_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-PER-KIND-FIELDS", out)

    def test_missing_module_flag_fails(self):
        rc, out = run_cx("check", "blueprint", fix(self.GOOD),
                         "--state", fix(self.STATE), "--approval", fix(self.APPROVAL))
        self.assertEqual(rc, 1)
        self.assertIn("--module", out)

    def test_unknown_module_fails(self):
        rc, out = self._run(self.GOOD, "does_not_exist")
        self.assertEqual(rc, 1)
        self.assertIn("not in the blueprint-manifest", out)

    # ── built-code xfam fold (CXBP-001/003/004) ──
    def test_omitted_control_fails_coverage(self):
        rc, out = self._run("blueprint_bad_omit_control_packet", "home",
                            approval="blueprint_bad_omit_control_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-ANCHOR-COVERAGE", out)
        self.assertIn("control:add_entry", out)

    def test_omitted_nav_fails_coverage(self):
        rc, out = self._run("blueprint_bad_omit_nav_packet", "home",
                            approval="blueprint_bad_omit_nav_packet_approval.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-ANCHOR-COVERAGE", out)
        self.assertIn("nav:home->detail", out)

    def test_review_ref_missing_file_fails(self):
        rc, out = self._run(self.GOOD, "home", approval="blueprint_bad_review_ref_missing.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("no real review file", out)

    def test_same_family_reviewer_fails(self):
        rc, out = self._run(self.GOOD, "home", approval="blueprint_bad_review_same_family.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("SAME cross-family group", out)

    def test_hidden_severity_fail_closed_no_open_findings(self):
        rc, out = self._run(self.GOOD, "home", state="blueprint_bad_state_no_open_findings.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("open_findings is missing or not a mapping", out)

    def test_hidden_severity_fail_closed_malformed_items(self):
        rc, out = self._run(self.GOOD, "home", state="blueprint_bad_state_items_malformed.yaml")
        self.assertEqual(rc, 1)
        self.assertIn("items is missing or not a list", out)


# ---------------------------------------------------------------------------
# packet-floor: registry coverage (PROP-039 P1-7)
# ---------------------------------------------------------------------------
class TestPacketRegistryCoverage(unittest.TestCase):
    """PROP-039: for a screen/module-first packet (a planning MODULE-REGISTRY present), the registry
    must cover every screen + every BUILDING requirement before freeze; a legacy packet (no registry)
    keeps these clauses silent."""

    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(FIXTURES / "_gen_blueprint_fixtures.py")], check=True)

    def test_legacy_packet_no_registry_silent(self):
        rc, out = run_cx("check", "packet", fix("packet_good"))
        self.assertEqual(rc, 0, f"packet_good (no registry) must still PASS.\n{out}")

    def test_uncovered_screen_fails(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_registry_missing_screen"))
        self.assertEqual(rc, 1)
        self.assertIn("PACKET-MODULE-REGISTRY-COVERS-SCREENS", out)

    def test_uncovered_requirement_fails(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_registry_missing_requirement"))
        self.assertEqual(rc, 1)
        self.assertIn("PACKET-MODULE-REGISTRY-COVERS-REQUIREMENTS", out)


# ---------------------------------------------------------------------------
# contract-harness robustness (CXBP-007): resolve_args spares ONLY known non-path flag values;
# a genuinely-missing path-valued flag value is still resolved (so MISSING FIXTURE still catches it).
# ---------------------------------------------------------------------------
class TestContractHarnessResolveArgs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_contracts", str(THIS_DIR / "run_contracts.py"))
        cls.rc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.rc)

    def test_module_value_is_spared(self):
        out = self.rc.resolve_args(["--module", "home"])
        self.assertEqual(out, ["--module", "home"],
                         "a bare --module value must be left unresolved, not mangled to a path")

    def test_path_flag_value_is_resolved(self):
        # --state takes a PATH; a relative value must be resolved to absolute so a missing path is
        # still detectable (NOT spared like an identifier flag).
        out = self.rc.resolve_args(["--state", "tests/fixtures/nope_missing.yaml"])
        self.assertTrue(out[1].endswith("tests/fixtures/nope_missing.yaml"))
        self.assertTrue(os.path.isabs(out[1]),
                        "a --state path value must be resolved absolute, never spared as an identifier")

    def test_missing_path_flag_value_would_be_reported(self):
        # Simulate the MISSING-FIXTURE coverage check: a genuinely-missing path-valued flag value is
        # still flagged (the CXBP-007 regression guard — the heuristic must not hide a real typo).
        bad_args = self.rc.resolve_args(["--state", "tests/fixtures/definitely_absent.yaml"])
        flagged = []
        for idx, a in enumerate(bad_args):
            if a.startswith("-"):
                continue
            prev = bad_args[idx - 1] if idx > 0 else ""
            if not os.path.isabs(a) and prev in self.rc._NON_PATH_VALUE_FLAGS:
                continue
            if not os.path.exists(a):
                flagged.append(a)
        self.assertEqual(len(flagged), 1,
                         "a missing path-valued flag value must still be reported MISSING FIXTURE")


# ---------------------------------------------------------------------------
# KaizenChecks (PROP-042 Part F)
# ---------------------------------------------------------------------------
class KaizenChecks(unittest.TestCase):
    """cx check kaizen — KAIZEN-* clause suite (PROP-042 Part F)."""

    _CONTRACTS = str(CHECKERS_DIR / "check-contracts.yaml")

    def test_good_queue_passes(self):
        rc, out = run_cx("check", "kaizen", fix("kaizen_good.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_behavioural_applied_no_enforcement_fails(self):
        """KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT: PROP-024 class."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_no_enforcement.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT", out)

    def test_fake_clause_ref_fails(self):
        """KAIZEN-ENFORCEMENT-CLAUSE-EXISTS: clause_id not in check-contracts."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_fake_clause.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("not found in check-contracts", out)

    def test_presence_only_rejected(self):
        """KAIZEN-ENFORCEMENT-NOT-PRESENCE-ONLY: presence_lint kind is banned."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_presence_only.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("presence-lint", out)

    def test_behavioural_field_missing_is_p1(self):
        """KAIZEN-BEHAVIOURAL-FIELD-PRESENT: APPLIED PROP missing behavioural field."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_no_behavioural_field.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-BEHAVIOURAL-FIELD-PRESENT", out)

    def test_prompt_ref_unsafe_rejected(self):
        """KAIZEN-PROMPT-REF-SHAPE: absolute prompt_ref is rejected."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_promptref_unsafe.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("prompt_ref", out)

    def test_unparseable_applied_is_debt_not_hardfail(self):
        """KAIZEN-APPLIED-ENTRY-PARSEABLE: malformed yaml is P2 (non-blocking) by default."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_unparseable_applied.md"),
                         "--contracts", self._CONTRACTS)
        # P2 = debt, not blocking — gate stays green
        self.assertEqual(rc, 0, f"Expected PASS (P2 debt non-blocking), got {rc}.\n{out}")

    def test_strict_debt_promotes_to_p1(self):
        """--strict-debt promotes unparseable P2 to P1 (gate fails)."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_unparseable_applied.md"),
                         "--contracts", self._CONTRACTS, "--strict-debt")
        self.assertEqual(rc, 1, f"Expected FIX-FIRST under --strict-debt, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)

    def test_judgment_limit_complete_passes(self):
        """judgment_limit with all 3 required fields passes."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_good_judgment_limit.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_judgment_limit_incomplete_fails(self):
        """KAIZEN-JUDGMENT-LIMIT-SHAPE: missing ceo_decision_ref → P1."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_judgment_limit_incomplete.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-JUDGMENT-LIMIT-SHAPE", out)

    def test_prop024_dogfood_fixture_trips_p0(self):
        """PROP-024 dogfood: kaizen_bad_prop024_real trips KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_prop024_real.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1)
        self.assertIn("KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT", out)


# ---------------------------------------------------------------------------
# ConflictScanChecks (PROP-044 — no-ambiguity / conflict_scan clauses)
# ---------------------------------------------------------------------------
class ConflictScanChecks(unittest.TestCase):
    """cx check kaizen — KAIZEN-CONFLICT-SCAN-* + BUILD-CONFLICT-SCAN-STEP-MISSING suite (PROP-044)."""

    _CONTRACTS = str(CHECKERS_DIR / "check-contracts.yaml")

    def test_good_conflict_scan_passes(self):
        """Good fixture with complete conflict_scan passes all clauses."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_good_conflict_scan.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_conflict_scan_missing_fails(self):
        """KAIZEN-CONFLICT-SCAN-PRESENT: PROP without conflict_scan block is rejected P1."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_conflict_scan_missing.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-CONFLICT-SCAN-PRESENT", out)

    def test_conflict_scan_unresolved_fails(self):
        """KAIZEN-CONFLICT-SCAN-RESOLVED: hits listed but resolution_ref blank → P0."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_conflict_scan_unresolved.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-CONFLICT-SCAN-RESOLVED", out)

    def test_conflict_scan_shape_fails(self):
        """KAIZEN-CONFLICT-SCAN-SHAPE: missing required keys → P1."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_conflict_scan_shape.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-CONFLICT-SCAN-SHAPE", out)

    def test_conflict_scan_stale_basis_fails(self):
        """KAIZEN-CONFLICT-SCAN-BASIS-CURRENT: forward PROP with zeroed shas → P1."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_conflict_scan_stale_basis.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-CONFLICT-SCAN-BASIS-CURRENT", out)

    def test_conflict_scan_step_missing_fails(self):
        """BUILD-CONFLICT-SCAN-STEP-MISSING: conflict_scan present but scan_step_marker absent → P1."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_conflict_scan_step_missing.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("BUILD-CONFLICT-SCAN-STEP-MISSING", out)

    def test_conflict_scan_live_basis_passes(self):
        """PBF-PROP-014-CSFIX: real-format forward PROP carrying the scan_commit test sentinel
        passes under CODE_X_TEST_MODE=1 (SHAPE-only carve-out) — the first-ever GOOD live-basis
        case, impossible before the commit anchor. Production fail-closed is proven separately by
        the bad-commit fixture + the hermetic resolution test."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_good_conflict_scan_live_basis.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_conflict_scan_bad_commit_fails(self):
        """PBF-PROP-014-CSFIX: malformed (non-40-hex) scan_commit is rejected on SHAPE
        alone, before any git call — a fabricated anchor cannot be rubber-stamped."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_conflict_scan_bad_commit.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-CONFLICT-SCAN-BASIS-CURRENT", out)
        self.assertIn("scan_commit", out)

    def test_example_fence_in_prose_passes(self):
        """G1: non-PROP yaml fences embedded in prose are ignored — PROP passes."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_example_fence_in_prose.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 0, f"Expected PASS (example fence ignored), got {rc}.\n{out}")
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# ConflictScanResolution (PBF-PROP-014-CSFIX — the git-resolution/recompute/floor path)
# ---------------------------------------------------------------------------
class ConflictScanResolution(unittest.TestCase):
    """Exercise the commit-anchored GIT-RESOLUTION path against a real temp git repo that
    mirrors the nested-worktree layout (git root -> Code-X-V1/ subdir). Static fixtures can
    only reach SHAPE; this proves the recompute, the ancestor/version-floor, and the `./`
    cwd-relative object resolution (P0-1) actually bite."""

    def _git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def _blob_sha(self, commit, rel):
        # cwd = the subdir; `./` resolves relative to it (the production code path).
        return subprocess.run(["git", "rev-parse", f"{commit}:./{rel}"],
                              capture_output=True, text=True, cwd=self.subdir,
                              check=True).stdout.strip()

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="cx-csfix-resolve-")
        self.root = Path(self._tmp)
        self.subdir = self.root / "Code-X-V1"
        (self.subdir / "MEMORY").mkdir(parents=True)
        self._orig_this_dir = cx_kaizen._THIS_DIR
        cx_kaizen._THIS_DIR = self.subdir / "checkers"  # cx_root -> self.subdir

        self.queue_rel = "MEMORY/PROTOCOL-IMPROVEMENT-QUEUE.md"
        self.ledger_rel = "MEMORY/CEO-DECISION-LEDGER.md"
        self.cw_rel = "PROP-CROSSWALK.md"
        self.vh = self.subdir / "VERSION-HISTORY.md"
        self.version = cx_kaizen.PROTOCOL_VERSION

        self._git("init", "-q")
        self._git("config", "user.email", "cx@test")
        self._git("config", "user.name", "cx")

        # commit1 (sha1): initial scanned state; VERSION-HISTORY has a placeholder row.
        (self.subdir / self.queue_rel).write_text(
            "# queue\n\n```yaml\n- id: PBF-PROP-001\n  status: APPLIED\n```\n", encoding="utf-8")
        (self.subdir / self.ledger_rel).write_text(
            "- id: CEO-D-001\n- id: CEO-D-002\n", encoding="utf-8")
        (self.subdir / self.cw_rel).write_text("| PROP-001 | P-PROP-001 | seed |\n", encoding="utf-8")
        self.vh.write_text(f"| v{self.version} | 2026-07-01 | test | `pending` | CEO-D-x |\n",
                           encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "c1")
        self.sha1 = self._git("rev-parse", "HEAD")

        # commit2 (sha2): the scanned state a forward PROP anchors to (queue grows by one block).
        (self.subdir / self.queue_rel).write_text(
            "# queue\n\n```yaml\n- id: PBF-PROP-001\n  status: APPLIED\n```\n"
            "\n```yaml\n- id: PBF-PROP-002\n  status: APPLIED\n```\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "c2")
        self.sha2 = self._git("rev-parse", "HEAD")

        # commit3 (HEAD): the version-lock row now points at sha2 -> lock_commit resolves to sha2.
        self.vh.write_text(f"| v{self.version} | 2026-07-01 | test | `{self.sha2}` | CEO-D-x |\n",
                           encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "c3")

    def tearDown(self):
        cx_kaizen._THIS_DIR = self._orig_this_dir

    def _block(self, scan_commit, **overrides):
        basis = {
            "scan_commit": scan_commit,
            "queue_sha": self._blob_sha(scan_commit, self.queue_rel),
            "ledger_sha": self._blob_sha(scan_commit, self.ledger_rel),
            "crosswalk_sha": self._blob_sha(scan_commit, self.cw_rel),
            "prop_count": overrides.pop("prop_count", None),
            "decision_count": 2,
        }
        # prop_count depends on which commit: sha1 has 1 block, sha2 has 2.
        if basis["prop_count"] is None:
            basis["prop_count"] = 2 if scan_commit == self.sha2 else 1
        basis.update(overrides)
        return {"id": "P-PROP-099-A", "status": "QUEUED", "behavioural": False,
                "conflict_scan": {"basis": basis, "duplicates": [], "ambiguities": [],
                                  "conflicts": [], "resolution_ref": "n/a — none",
                                  "scan_step_marker": "present"}}

    def _run(self, block):
        return cx_kaizen._check_conflict_scan(
            block["id"], block, self.subdir / self.queue_rel)

    def test_resolution_correct_basis_passes(self):
        """(a) Correct commit-anchored shas/counts at a real scan_commit -> no BASIS-CURRENT finding."""
        findings = self._run(self._block(self.sha2))
        basis_hits = [f for f in findings if "BASIS-CURRENT" in f[2]]
        self.assertEqual(basis_hits, [], f"Expected clean recompute, got: {basis_hits}")

    def test_resolution_wrong_sha_bites(self):
        """(b) One wrong declared sha -> recompute BITES P1."""
        findings = self._run(self._block(self.sha2, queue_sha="a" * 40))
        msgs = [f[2] for f in findings if "BASIS-CURRENT" in f[2]]
        self.assertTrue(msgs, "Expected a BASIS-CURRENT P1")
        self.assertIn("queue_sha stale", msgs[0])

    def test_resolution_below_version_floor_bites(self):
        """(c) scan_commit before the version-lock commit -> tighter floor BITES P1."""
        findings = self._run(self._block(self.sha1))
        msgs = [f[2] for f in findings if "BASIS-CURRENT" in f[2]]
        self.assertTrue(msgs, "Expected a BASIS-CURRENT P1")
        self.assertIn("predates", msgs[0])

    def test_resolution_unresolvable_commit_fails_closed(self):
        """P0-2: a well-formed but non-existent scan_commit fails CLOSED, not SHAPE-only."""
        block = self._block(self.sha2)
        block["conflict_scan"]["basis"]["scan_commit"] = "b" * 40
        findings = self._run(block)
        msgs = [f[2] for f in findings if "BASIS-CURRENT" in f[2]]
        self.assertTrue(msgs, "Expected a fail-closed P1")
        self.assertIn("does not resolve to a committed blob", msgs[0])


# StageRenameChecks (PBF-PROP-013 — stage-prefix id format + crosswalk clauses)
# ---------------------------------------------------------------------------
class StageRenameChecks(unittest.TestCase):
    """cx check kaizen --conflict-scan — KAIZEN-ID-FORMAT + KAIZEN-PREFIX-MATCHES-STAGES +
    KAIZEN-STAGE-SERIES-ORDER-GAPLESS + KAIZEN-LEGACY-ID-PRESENT-UNIQUE + KAIZEN-CROSSWALK-COMPLETE
    suite (PBF-PROP-013)."""

    _CONTRACTS = str(CHECKERS_DIR / "check-contracts.yaml")

    def test_good_stage_rename_passes(self):
        """Good fixture with PROP-TEST-* ids passes all stage-rename clauses (exempt by id format)."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_good_stage_rename.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_id_format_bad_fails(self):
        """KAIZEN-ID-FORMAT: old-format PROP-001 id in active PROP is rejected P0."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_id_format.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-ID-FORMAT", out)

    def test_prefix_stages_mismatch_fails(self):
        """KAIZEN-PREFIX-MATCHES-STAGES: PBF prefix with stages:[planning] only is rejected P0."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_prefix_stages.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-PREFIX-MATCHES-STAGES", out)

    def test_series_gap_fails(self):
        """KAIZEN-STAGE-SERIES-ORDER-GAPLESS: B-PROP-001 + B-PROP-003 without B-PROP-002 is rejected P1."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_series_gap.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-STAGE-SERIES-ORDER-GAPLESS", out)

    def test_legacy_id_duplicate_fails(self):
        """KAIZEN-LEGACY-ID-PRESENT-UNIQUE: two PROPs sharing the same legacy_id is rejected P1."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_legacy_dup.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-LEGACY-ID-PRESENT-UNIQUE", out)

    def test_crosswalk_missing_fails(self):
        """KAIZEN-CROSSWALK-COMPLETE: P-PROP-999 not in PROP-CROSSWALK.md is rejected P1."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_crosswalk_missing.md"),
                         "--contracts", self._CONTRACTS, "--conflict-scan")
        self.assertEqual(rc, 1)
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-CROSSWALK-COMPLETE", out)


# ---------------------------------------------------------------------------
# TestCheckAudit (A-PROP-001 + PBAF-PROP-001 — the Audit stage)
# ---------------------------------------------------------------------------
class TestCheckAudit(unittest.TestCase):
    """cx check audit — AUDIT-STAGE-* clause suite."""

    _STATE = fix("audit_state_good.yaml")

    def test_good_audit_passes(self):
        rc, out = run_cx("check", "audit", fix("audit_good"), "--state", self._STATE)
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_final_good_passes(self):
        rc, out = run_cx("check", "audit", fix("as_final_good"), "--state", self._STATE, "--final")
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_no_receipt_fails_entry_required(self):
        rc, out = run_cx("check", "audit", fix("as_no_audit_receipt"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-ENTRY-REQUIRED", out)

    def test_na_without_fact_fails_derived(self):
        rc, out = run_cx("check", "audit", fix("as_na_no_fact"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-APPLICABILITY-DERIVED", out)

    def test_whole_layer_na_with_live_subitem_fails(self):
        rc, out = run_cx("check", "audit", fix("as_layer_na_live_subitem"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-WHOLE-LAYER-NA-WITH-LIVE-SUBITEM", out)

    def test_undispositioned_item_fails(self):
        rc, out = run_cx("check", "audit", fix("as_undispositioned_item"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-SHIPGATE-DISPOSITION", out)

    def test_samefamily_receipt_fails_xfam(self):
        rc, out = run_cx("check", "audit", fix("as_samefamily_receipt"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-XFAM-RECEIPT", out)

    def test_ladder_skip_fails(self):
        rc, out = run_cx("check", "audit", fix("as_ladder_skip"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-REVIEW-LADDER", out)

    def test_final_unresolved_fails_closed(self):
        rc, out = run_cx("check", "audit", fix("as_final_unresolved"), "--state", self._STATE, "--final")
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-FAILCLOSED-FINAL", out)

    def test_e2_no_https_fails(self):
        rc, out = run_cx("check", "audit", fix("as_e2_no_https"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-HTTPS-E2", out)

    # ── F2 (v1.22 self-review): hard_rules driven generically from sop_applicability.yaml —
    # an OMITTED ship-gate sub-item bites at the same severity as an explicit N/A. ──

    def test_version_control_omitted_fails(self):
        rc, out = run_cx("check", "audit", fix("as_version_control_omitted"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-VERSION-CONTROL-ALWAYS", out)

    def test_backups_omitted_fails(self):
        rc, out = run_cx("check", "audit", fix("as_backups_omitted"), "--state", self._STATE)
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-BACKUPS-WHEN-SENSITIVE", out)

    # ── F7 (v1.22 self-review, CEO ruling 2026-07-02): a --final audit with ZERO cross_family
    # receipts fails closed unless a typed escape mirrors the BF-PROP-005 stage_1 discipline —
    # xfam_capability_evidence (manual scrubbed cross-family paste) or ceo_decision_ref waiver. ──

    def test_final_no_xfam_no_escape_fails(self):
        rc, out = run_cx("check", "audit", fix("as_final_no_xfam"), "--state", self._STATE, "--final")
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-FINAL-XFAM-REQUIRED", out)

    def test_final_no_xfam_with_ceo_waiver_passes(self):
        rc, out = run_cx("check", "audit", fix("as_final_xfam_waiver"), "--state", self._STATE, "--final",
                         "--decision-ledger", fix("as_final_xfam_waiver/CEO-DECISION-LEDGER.md"))
        self.assertEqual(rc, 0, f"Expected PASS with typed ceo_decision_ref waiver, got {rc}.\n{out}")

    def test_nonfinal_no_xfam_not_gated(self):
        """The F7 gate is FINAL-only — a per-module (light) audit without a cross_family receipt
        must not fire AUDIT-STAGE-FINAL-XFAM-REQUIRED (the xfam pass is per-module optional)."""
        rc, out = run_cx("check", "audit", fix("as_final_no_xfam"), "--state", self._STATE)
        self.assertNotIn("AUDIT-STAGE-FINAL-XFAM-REQUIRED", out)

    # ── F4 (v1.22 self-review): table_by_id compared report layer ids (possibly a quoted YAML
    # string) against the SOP table's int ids WITHOUT coercion — a type mismatch silently
    # SKIPPED the Rule 2 live-subitem cross-check (fail-open). _coerce_layer_id() normalizes
    # both sides to int; an unparseable id is itself a fail-closed finding. ──

    def _write_audit_dir(self, tmp, layer_line: str) -> str:
        d = os.path.join(tmp, "audit")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "AUDIT-SUMMARY.md"), "w") as f:
            f.write("# audit summary\n")
        with open(os.path.join(d, "applicability.yaml"), "w") as f:
            f.write(
                "facts:\n  A1: true\n  A2: true\n  A3: true\n  A4: false\n  A5: E2\n"
                "  A6: true\n  A7: true\n  A8: false\n  A9: false\n"
                f"layers:\n{layer_line}")
        return d

    def test_string_layer_id_still_cross_checked(self):
        """A layer id given as a quoted string ('1') in the report must still match the SOP
        table's int id 1 — before F4 this type mismatch silently skipped Rule 2 entirely."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._write_audit_dir(
                tmp, '- id: "1"\n  verdict: N_A\n  driving_fact: "A1=false (claimed, but built app has UI)"\n')
            rc, out = run_cx("check", "audit", d, "--state", self._STATE)
            self.assertEqual(rc, 1, out)
            self.assertIn("AUDIT-STAGE-WHOLE-LAYER-NA-WITH-LIVE-SUBITEM", out)

    def test_unparseable_layer_id_fails_closed(self):
        """A layer id that cannot be coerced to int must fail CLOSED with a dedicated finding —
        never a silent skip of the Rule 2 cross-check (the pre-F4 fail-open behavior)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._write_audit_dir(
                tmp, '- id: "not-a-number"\n  verdict: N_A\n  driving_fact: "some fact"\n')
            rc, out = run_cx("check", "audit", d, "--state", self._STATE)
            self.assertEqual(rc, 1, out)
            self.assertIn("AUDIT-STAGE-LAYER-ID-UNPARSEABLE", out)


class TestCheckFinalReadyAuditStageChain(unittest.TestCase):
    """F1 (v1.22 self-review): AUDIT-STAGE-FINAL-READY-CHAIN — final-ready must not be reachable
    while skipping the Audit stage; wires cx_audit.collect_audit_findings into cx_final_ready."""

    def test_good_state_with_audit_stage_final_passes(self):
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_missing_audit_stage_final_blocks(self):
        rc, out = run_cx("check", "final-ready", fix("state_final_ready_bad_no_audit_stage.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("AUDIT-STAGE-FINAL-READY-CHAIN", out)


class TestCheckPacketSopCoverageMap(unittest.TestCase):
    """cx check packet — SOP-BIND-COVERAGE-MAP clause (PBAF-PROP-001 Lever B)."""

    def test_good_packet_passes(self):
        rc, out = run_cx("check", "packet", fix("packet_good"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_missing_sop_coverage_map_fails(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_no_sop_coverage_map"))
        self.assertEqual(rc, 1)
        self.assertIn("SOP-BIND-COVERAGE-MAP", out)


if __name__ == "__main__":
    unittest.main()
