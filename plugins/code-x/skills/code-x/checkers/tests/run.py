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
import cx_blueprint  # noqa: E402 — PBF-PROP-019 Phase 3: unit-test _derive_expected_anchor_ids directly
import cx_egress  # noqa: E402 — PBF-PROP-021 P1-3/P2-1: unit-test the normalize/context helpers directly


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


class TestCardHighRiskForcesFoundation(unittest.TestCase):
    """PBF-PROP-019 Phase 2 (design v2 P0-1, CARD-HIGH-RISK-FORCES-FOUNDATION): a
    card_high_risk card mechanically requires foundation_checkpoint_required: yes —
    regardless of self-declaration. This gate is SPINE (never reads risk_tier)."""

    def test_high_risk_card_without_checkpoint_fails(self):
        rc, out = run_cx("check", "card", fix("card_bad_high_risk_no_foundation_checkpoint.yaml"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("CARD-HIGH-RISK-FORCES-FOUNDATION", out, out)

    def test_high_risk_card_with_checkpoint_passes(self):
        rc, out = run_cx("check", "card", fix("card_good_high_risk_with_foundation_checkpoint.yaml"))
        self.assertEqual(rc, 0, out)

    def test_non_high_risk_card_unaffected(self):
        # Positive control: card_good.yaml has no truthy tripwire — unaffected by the new gate.
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("CARD-HIGH-RISK-FORCES-FOUNDATION", out, out)


# ---------------------------------------------------------------------------
# PBF-PROP-019 Phase 3: per-gate ceremony reads (cx_card CodeRabbit + cross-review)
# ---------------------------------------------------------------------------
class TestCardCoderabbitTierGated(unittest.TestCase):
    """design v2.B row 3: LITE drops the CodeRabbit rail requirement; STANDARD/STRICT unchanged."""

    def test_missing_coderabbit_strict_default_fails(self):
        # No --state -> risk_tier defaults STRICT (fail-closed) -> CodeRabbit still mandatory.
        rc, out = run_cx("check", "card", fix("card_good_no_coderabbit.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("CodeRabbit", out)

    def test_missing_coderabbit_strict_state_fails(self):
        rc, out = run_cx("check", "card", fix("card_good_no_coderabbit.yaml"),
                         "--state", fix("state_pbf019_strict.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("CodeRabbit", out)

    def test_missing_coderabbit_lite_state_passes(self):
        rc, out = run_cx("check", "card", fix("card_good_no_coderabbit.yaml"),
                         "--state", fix("state_pbf019_lite.yaml"))
        self.assertEqual(rc, 0, out)


class TestCardCrossReviewLiteSelfReviewOk(unittest.TestCase):
    """design v2.B row 2: LITE relaxes the per-module cross-family review floor to self-review
    only — UNLESS the card is high-risk, in which case Phase-2's mechanical force is NOT relaxed."""

    def test_same_family_default_strict_rejected(self):
        rc, out = run_cx("check", "card", fix("card_good_lite_self_review.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("same-family", out.lower())

    def test_same_family_strict_state_rejected(self):
        rc, out = run_cx("check", "card", fix("card_good_lite_self_review.yaml"),
                         "--state", fix("state_pbf019_strict.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("same-family", out.lower())

    def test_same_family_lite_state_self_review_ok(self):
        rc, out = run_cx("check", "card", fix("card_good_lite_self_review.yaml"),
                         "--state", fix("state_pbf019_lite.yaml"))
        self.assertEqual(rc, 0, out)

    def test_high_risk_same_family_lite_state_still_rejected(self):
        """Invariant (c): the LITE relaxation must NEVER override the Phase-2 high-risk force —
        a money-touching card with same-family cross_review fails in EVERY tier, including LITE."""
        rc, out = run_cx("check", "card", fix("card_bad_high_risk_same_family_lite_not_relaxed.yaml"),
                         "--state", fix("state_pbf019_lite.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("same-family", out.lower())


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
# B-PROP-013 Unit 2 — `cx check accept` (the STAMPER). Mirrors cx_boot.py's generate->write->
# self-hash-seal pattern: recomputes state_sha_before + repo HEAD + quality_card_hash, refuses
# verdict: accepted without a ceo_accept_token embedding the recomputed HEAD prefix.
# HONEST FRAMING (design §3/§10.3): this command is ergonomics + honest capture, NOT a forge
# wall — the wall is `cx check module-acceptance` (Unit 1). These tests pin the STAMPER's own
# mechanical behavior only.
# ---------------------------------------------------------------------------
class TestCheckAccept(unittest.TestCase):

    def _repo_and_state(self, tmp):
        repo = os.path.join(tmp, "repo")
        _git_init(repo)
        head = _git_commit(repo, "first")
        state = os.path.join(tmp, "state.yaml")
        with open(state, "w") as f:
            f.write("project: cx-accept-unit-test\nprotocol_stamp: Code-X V1\n")
        return repo, state, head

    def test_refuses_accepted_verdict_with_no_ceo_accept_token(self):
        """CX-ACCEPT-NO-CEO-TOKEN: verdict: accepted with no token anywhere → refuse (P0), no
        receipt written."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, _head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {"module_id": "m1", "verdict": "accepted"}}, f)
            out_path = os.path.join(repo, "out.yaml")
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo, "--out", out_path)
            self.assertEqual(rc, 1, out)
            self.assertIn("[P0]", out)
            self.assertIn("CX-ACCEPT-NO-CEO-TOKEN", out)
            self.assertFalse(os.path.exists(out_path), "a refusal must write NO receipt file")

    def test_refuses_when_token_does_not_embed_head_prefix(self):
        """A ceo_accept_token that does NOT embed the recomputed HEAD prefix is not valid —
        refuses even though a token is present (proves it isn't just a non-blank check)."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, _head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {
                    "module_id": "m1", "verdict": "accepted",
                    "ceo_accept_token": "ceo-accepts-ffffff"}}, f)
            out_path = os.path.join(repo, "out.yaml")
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo, "--out", out_path)
            self.assertEqual(rc, 1, out)
            self.assertIn("CX-ACCEPT-NO-CEO-TOKEN", out)

    def test_stamps_with_valid_ceo_accept_token(self):
        """A token embedding the real 12-char HEAD prefix PLUS a ceo_turn_ref stamps cleanly:
        PASS, receipt written, generated_by/state_sha_before/repo_sha_before recomputed (never
        trusted from the draft) — the honest full-prefix+turn_ref case (FIX-FIRST B-PROP-013)."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {
                    "module_id": "m1", "verdict": "accepted",
                    "generated_by": "hand-authored-should-be-overwritten",
                    "repo_sha_before": "stale00000000",
                    "ceo_accept_token": f"ceo-accepts-{head[:12]}",
                    "ceo_turn_ref": "turn-2026-07-06-001"}}, f)
            out_path = os.path.join(repo, "out.yaml")
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo, "--out", out_path)
            self.assertEqual(rc, 0, out)
            self.assertTrue(os.path.exists(out_path))
            with open(out_path) as f:
                receipt = yaml.safe_load(f)
            ma = receipt["module_acceptance"]
            self.assertEqual(ma["generated_by"], "cx check accept")
            self.assertEqual(ma["repo_sha_before"], head)
            self.assertTrue(ma.get("state_sha_before"))

    def test_refuses_short_six_char_prefix_token_fix_first(self):
        """FIX-FIRST (B-PROP-013 xfam P1): a token embedding only the OLD 6-char HEAD prefix
        (`auto-<HEAD[:6]>`) with no ceo_turn_ref must now be REFUSED — the forgeable short-prefix
        substring check is closed; 12 hex chars are required."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {
                    "module_id": "m1", "verdict": "accepted",
                    "ceo_accept_token": f"auto-{head[:6]}"}}, f)
            out_path = os.path.join(repo, "out.yaml")
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo, "--out", out_path)
            self.assertEqual(rc, 1, out)
            self.assertIn("CX-ACCEPT-NO-CEO-TOKEN", out)
            self.assertFalse(os.path.exists(out_path))

    def test_refuses_full_prefix_token_with_no_ceo_turn_ref(self):
        """FIX-FIRST (B-PROP-013 xfam P1): a full 12-char HEAD-prefix token with NO ceo_turn_ref
        on the same block must be REFUSED — a token alone (no turn reference) is not proof of a
        real CEO turn."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {
                    "module_id": "m1", "verdict": "accepted",
                    "ceo_accept_token": f"ceo-accepts-{head[:12]}"}}, f)
            out_path = os.path.join(repo, "out.yaml")
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo, "--out", out_path)
            self.assertEqual(rc, 1, out)
            self.assertIn("CX-ACCEPT-NO-CEO-TOKEN", out)
            self.assertIn("ceo_turn_ref", out)
            self.assertFalse(os.path.exists(out_path))

    def test_refuses_token_on_wrong_top_level_block_for_live_slice_module(self):
        """FIX-FIRST (B-PROP-013 xfam P1): a live_slice module's draft carrying live_slice_accept
        (present but with NO ceo_accept_token on it) plus a bare TOP-LEVEL ceo_accept_token/
        ceo_turn_ref must be REFUSED — for a live_slice/module_demo module the token must live ON
        that structured block, not at the top level (closes the block-co-location bypass)."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {
                    "module_id": "m1", "verdict": "accepted",
                    "live_slice_accept": {"passed": True},
                    "ceo_accept_token": f"ceo-accepts-{head[:12]}",
                    "ceo_turn_ref": "turn-2026-07-06-001"}}, f)
            out_path = os.path.join(repo, "out.yaml")
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo, "--out", out_path)
            self.assertEqual(rc, 1, out)
            self.assertIn("CX-ACCEPT-NO-CEO-TOKEN", out)
            self.assertFalse(os.path.exists(out_path))

    def test_stamps_with_token_and_turn_ref_on_live_slice_accept_block(self):
        """The honest live_slice case: token + ceo_turn_ref co-located ON live_slice_accept
        stamps cleanly."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {
                    "module_id": "m1", "verdict": "accepted",
                    "live_slice_accept": {
                        "passed": True,
                        "ceo_accept_token": f"ceo-accepts-{head[:12]}",
                        "ceo_turn_ref": "turn-2026-07-06-001"}}}, f)
            out_path = os.path.join(repo, "out.yaml")
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo, "--out", out_path)
            self.assertEqual(rc, 0, out)
            self.assertTrue(os.path.exists(out_path))

    def test_recomputes_quality_card_hash_never_trusts_draft(self):
        """The draft's quality_card_hash (if any) is IGNORED and recomputed from the inline
        quality_card block — mirrors cx_module_acceptance._canonicalize_quality_card_hash."""
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {
                    "module_id": "m1", "verdict": "accepted",
                    "ceo_accept_token": f"ceo-accepts-{head[:12]}",
                    "ceo_turn_ref": "turn-2026-07-06-001",
                    "quality_card": {"b": 2, "a": 1},
                    "quality_card_hash": "stale-and-wrong"}}, f)
            out_path = os.path.join(repo, "out.yaml")
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo, "--out", out_path)
            self.assertEqual(rc, 0, out)
            with open(out_path) as f:
                receipt = yaml.safe_load(f)
            ma = receipt["module_acceptance"]
            self.assertNotEqual(ma["quality_card_hash"], "stale-and-wrong")
            import hashlib, json
            expected = hashlib.sha256(json.dumps({"a": 1, "b": 2}, sort_keys=True,
                                                  separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
            self.assertEqual(ma["quality_card_hash"], expected)

    def test_missing_module_id_refused(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            repo, state, _head = self._repo_and_state(tmp)
            draft = os.path.join(repo, "draft.yaml")
            with open(draft, "w") as f:
                yaml.dump({"module_acceptance": {"verdict": "accepted"}}, f)
            rc, out = run_cx("check", "accept", "--draft", draft, "--state", state,
                             "--repo-root", repo)
            self.assertEqual(rc, 1, out)
            self.assertIn("module_id", out)


# ---------------------------------------------------------------------------
# PB-PROP-003 Unit 2 — acceptance-stage criteria_refs WIRING (Design Resolution v2).
# 4 clauses: ACCEPTANCE-CRITERIA-REFS-RESOLVE (Layer 1, spine), ACCEPTANCE-BEHAVIORAL-REQ-UNWIRED
# (Layer 2, ceremony/tier-split), ACCEPTANCE-PRESENT-EXAMPLE-COVERED (Layer 2, spine), and the
# ACCEPTANCE-LEGACY-CRITERIA-REF-ADVISORY §R5 migration carve-out (non-blocking).
# ---------------------------------------------------------------------------
class TestPBProp003AcceptanceWiring(unittest.TestCase):
    WIRED_PKT = fix("pb_prop_003_wired_packet")
    LITE_PKT = fix("pb_prop_003_lite_packet")
    LEGACY_PKT = fix("pb_prop_003_legacy_packet")

    def test_wired_good_resolves_and_reverse_covers(self):
        """Layer 1 + Layer 2 clean: criteria_refs covers both m_wired behavioral requirements."""
        rc, out = run_cx("check", "verify-app", "--acceptance", fix("verify_app_wired_good.yaml"),
                         "--packet-dir", self.WIRED_PKT, "--module-id=m_wired")
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)

    def test_dangling_ref_rejected(self):
        """Layer 1: a citation to a requirement id that does not exist ANYWHERE in the frozen
        manifest is a P0, distinct message from the coverage clauses (ACCEPTANCE-CRITERIA-REFS-
        RESOLVE)."""
        rc, out = run_cx("check", "verify-app", "--acceptance",
                         fix("verify_app_wired_dangling_ref.yaml"),
                         "--packet-dir", self.WIRED_PKT, "--module-id=m_wired")
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("ACCEPTANCE-CRITERIA-REFS-RESOLVE", out)
        self.assertIn("REQ-999", out)

    def test_exempt_id_cannot_be_cited(self):
        """Layer 1: a non_behavioral_exemption'd id (REQ-003, exempt in the wired packet) is NOT
        citable even though it exists in the manifest — 'behavioral' is required, not just present."""
        with tempfile.TemporaryDirectory() as td:
            rp = os.path.join(td, "receipt.yaml")
            with open(rp, "w") as f:
                f.write("module_acceptance:\n  module_id: m_wired\n  verify_app:\n"
                        "    passed: true\n    repo_sha: 7d1408c9aa21\n"
                        "    generated_by: verify-app-agent\n    criteria_refs: [REQ-003]\n")
            rc, out = run_cx("check", "verify-app", "--acceptance", rp,
                             "--packet-dir", self.WIRED_PKT, "--module-id=m_wired")
            self.assertEqual(rc, 1)
            self.assertIn("ACCEPTANCE-CRITERIA-REFS-RESOLVE", out)
            self.assertIn("REQ-003", out)

    def test_criteria_refs_grammar_rejects_non_string_and_duplicate(self):
        """§R7 grammar: non-string entries and duplicate ids both P0, before resolution ever runs."""
        with tempfile.TemporaryDirectory() as td:
            bad_type = os.path.join(td, "bad_type.yaml")
            with open(bad_type, "w") as f:
                f.write("module_acceptance:\n  module_id: m_wired\n  verify_app:\n"
                        "    passed: true\n    repo_sha: 7d1408c9aa21\n"
                        "    generated_by: verify-app-agent\n    criteria_refs: [REQ-001, 42]\n")
            rc, out = run_cx("check", "verify-app", "--acceptance", bad_type,
                             "--packet-dir", self.WIRED_PKT)
            self.assertEqual(rc, 1)
            self.assertIn("non-string/blank", out)

            dupe = os.path.join(td, "dupe.yaml")
            with open(dupe, "w") as f:
                f.write("module_acceptance:\n  module_id: m_wired\n  verify_app:\n"
                        "    passed: true\n    repo_sha: 7d1408c9aa21\n"
                        "    generated_by: verify-app-agent\n"
                        "    criteria_refs: [REQ-001, REQ-001]\n")
            rc, out = run_cx("check", "verify-app", "--acceptance", dupe, "--packet-dir", self.WIRED_PKT)
            self.assertEqual(rc, 1)
            self.assertIn("duplicate", out)

    def test_unwired_behavioral_req_blocks_at_standard(self):
        """Layer 2 ceremony: REQ-002 (behavioral, has an example) uncovered at STANDARD tier -> P1
        ACCEPTANCE-BEHAVIORAL-REQ-UNWIRED."""
        rc, out = run_cx("check", "verify-app", "--acceptance", fix("verify_app_wired_unwired.yaml"),
                         "--packet-dir", self.WIRED_PKT, "--module-id=m_wired")
        self.assertEqual(rc, 1)
        self.assertIn("ACCEPTANCE-BEHAVIORAL-REQ-UNWIRED", out)
        self.assertIn("REQ-002", out)

    def test_present_example_uncovered_blocks_regardless(self):
        """Layer 2 spine: the SAME uncovered REQ-002 also trips ACCEPTANCE-PRESENT-EXAMPLE-COVERED
        (a DISTINCT clause from the ceremony one — both fire together here)."""
        rc, out = run_cx("check", "verify-app", "--acceptance", fix("verify_app_wired_unwired.yaml"),
                         "--packet-dir", self.WIRED_PKT, "--module-id=m_wired")
        self.assertEqual(rc, 1)
        self.assertIn("ACCEPTANCE-PRESENT-EXAMPLE-COVERED", out)

    def test_lite_tier_relaxes_ceremony_with_nothing_to_wire(self):
        """Tier-split (§R3): m_lite's only requirement has NO authored example (LITE relaxes
        authoring) -> an empty criteria_refs is valid grammar AND passes reverse coverage clean."""
        rc, out = run_cx("check", "verify-app", "--acceptance", fix("verify_app_wired_lite_ok.yaml"),
                         "--packet-dir", self.LITE_PKT, "--module-id=m_lite")
        self.assertEqual(rc, 0, out)

    def test_same_unwired_shape_fails_at_standard_not_lite(self):
        """Direct tier-boundary contrast: the STANDARD wired packet's unwired fixture fails; an
        LITE-tier module with the identical 'nothing cited' shape does not."""
        rc_standard, _ = run_cx("check", "verify-app", "--acceptance",
                                fix("verify_app_wired_unwired.yaml"),
                                "--packet-dir", self.WIRED_PKT, "--module-id=m_wired")
        rc_lite, _ = run_cx("check", "verify-app", "--acceptance", fix("verify_app_wired_lite_ok.yaml"),
                            "--packet-dir", self.LITE_PKT, "--module-id=m_lite")
        self.assertEqual(rc_standard, 1)
        self.assertEqual(rc_lite, 0)

    def test_legacy_carveout_is_advisory_not_blocking(self):
        """§R5 migration proof: a packet with NO pb_prop_003_wiring marker keeps the OLD scalar
        criteria_ref accepted — a typed P2 advisory, non-blocking (rc stays 0)."""
        rc, out = run_cx("check", "verify-app", "--acceptance", fix("verify_app_legacy_ok.yaml"),
                         "--packet-dir", self.LEGACY_PKT)
        self.assertEqual(rc, 0, out)
        self.assertIn("[P2]", out)
        self.assertIn("ACCEPTANCE-LEGACY-CRITERIA-REF-ADVISORY", out)

    def test_no_packet_dir_preserves_pre_existing_behavior(self):
        """Migration proof #2: the pre-existing standalone invocation (no --packet-dir at all,
        e.g. every EXISTING live_slice acceptance fixture) is untouched — the old free-text
        criteria_ref alone still satisfies the gate, no new findings appear."""
        rc, out = run_cx("check", "verify-app", "--acceptance",
                         fix("module_acceptance_live_slice_good.yaml"))
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)

    def test_module_acceptance_order_wall_still_green_with_legacy_fixture(self):
        """Migration proof #3: the EXISTING module_acceptance_live_slice_good.yaml fixture (no
        pb_prop_003_wiring marker anywhere in its acceptance context) still passes module-quality/
        module-acceptance-shaped checks untouched by this Unit — verified via the pre-existing
        contract clause family (MODULE-QUALITY-LIVE-SLICE-NO-DRIVE) which this test re-confirms
        directly."""
        rc, out = run_cx("check", "module-quality", "--acceptance",
                         fix("module_acceptance_live_slice_good.yaml"),
                         "--registry", fix("module_registry_good.yaml"), "--module-id=m_live")
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# CX-PB003-001 FIX-FIRST (xfam finding 1, P0): the FINAL/ONLY live_slice module of a marked packet
# — the one no later module-start order-wall re-validation ever fires for — must trip the SAME
# criteria_refs wiring/reverse-coverage checks a PRIOR module already gets via the order wall.
# `cx check module-quality` (previously called validate_live_slice_accept with no packet_dir/
# module_id, cx_module_quality.py:130) and the graduation c7 replay (cx_graduation.py's _NS, which
# previously carried no packet_dir at all) are the two production chokepoints fixed.
# ---------------------------------------------------------------------------
class TestCXPB003001ModuleQualityPacketDirWiring(unittest.TestCase):
    WIRED_PKT = fix("pb_prop_003_wired_packet")

    def test_module_quality_with_packet_dir_rejects_unwired_final_module(self):
        """THE FIX: `cx check module-quality --packet-dir` on m_wired (live_slice: true, this
        packet's final/only live_slice module) with an unwired REQ-002 now FAILS."""
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_pb003_wired_live_unwired.yaml"),
                         "--registry", fix("pb_prop_003_wired_packet/MODULE-REGISTRY.yaml"),
                         "--module-id=m_wired", "--packet-dir", self.WIRED_PKT)
        self.assertEqual(rc, 1, out)
        self.assertIn("ACCEPTANCE-BEHAVIORAL-REQ-UNWIRED", out)
        self.assertIn("REQ-002", out)

    def test_module_quality_with_packet_dir_accepts_fully_wired_module(self):
        """Good control: the SAME module fully wired (criteria_refs covers REQ-001 + REQ-002)
        passes clean with --packet-dir."""
        rc, out = run_cx("check", "module-quality",
                         "--acceptance", fix("module_acceptance_pb003_wired_live_good.yaml"),
                         "--registry", fix("pb_prop_003_wired_packet/MODULE-REGISTRY.yaml"),
                         "--module-id=m_wired", "--packet-dir", self.WIRED_PKT)
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)

    def test_legacy_no_packet_dir_still_green_no_new_blocking(self):
        """Migration proof: the PRE-EXISTING legacy fixture (module_acceptance_live_slice_good.yaml
        + module_registry_good.yaml, no pb_prop_003_wiring marker anywhere) stays green with
        --packet-dir omitted (the pre-existing standalone invocation) — untouched by this fix."""
        rc, out = run_cx("check", "module-quality", "--acceptance",
                         fix("module_acceptance_live_slice_good.yaml"),
                         "--registry", fix("module_registry_good.yaml"), "--module-id=m_live")
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)

    def test_legacy_with_packet_dir_advisory_stays_non_blocking(self):
        """A legacy (unmarked) packet's P2 migration-debt advisory — only reachable once
        --packet-dir is supplied — must stay non-blocking (has_blocking gate on module-quality's
        own return, mirroring cmd_module_acceptance/cmd_verify_app's identical pattern)."""
        rc, out = run_cx("check", "module-quality", "--acceptance",
                         fix("module_acceptance_live_slice_good.yaml"),
                         "--registry", fix("module_registry_good.yaml"), "--module-id=m_live",
                         "--packet-dir", fix("."))
        self.assertEqual(rc, 0, out)


class TestCXPB003001GraduationC7PacketDirWiring(unittest.TestCase):
    """Unit-tests cx_graduation._crit_c7 directly (mirrors TestGraduationTierEvidence's in-process
    pattern) — proves the graduation replay's _NS now threads packet_dir = the registry ref's own
    parent directory (the SAME canonical-location convention module-start's --packet-dir already
    trusts: <packet-dir>/MODULE-REGISTRY.yaml), so a marked packet's final/only live_slice module
    with an unwired behavioral requirement makes c7 UNMET at graduation-entry replay time too."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.receipts_dir = Path(self._tmp.name)
        pkt_src = Path(__file__).resolve().parent / "fixtures" / "pb_prop_003_wired_packet"
        pkt_dst = self.receipts_dir / "pkt"
        _shutil.copytree(pkt_src, pkt_dst)
        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        good_src = fixtures_dir / "module_acceptance_pb003_wired_live_good.yaml"
        bad_src = fixtures_dir / "module_acceptance_pb003_wired_live_unwired.yaml"
        for name, src in (("good.yaml", good_src), ("bad.yaml", bad_src)):
            (self.receipts_dir / name).write_bytes(src.read_bytes())
        # The receipts carry module_demo/build_validation refs resolved relative to the receipt's
        # OWN directory (base=str(Path(loc).parent) in cmd_module_quality) — copy those two real
        # sidecars alongside so the demo/log legs (unrelated to the wiring fix under test) pass.
        (self.receipts_dir / "module_demo_shot.png").write_bytes(
            (fixtures_dir / "module_demo_shot.png").read_bytes())
        (self.receipts_dir / "logs").mkdir(exist_ok=True)
        (self.receipts_dir / "logs" / "build_validation_pass.txt").write_bytes(
            (fixtures_dir / "logs" / "build_validation_pass.txt").read_bytes())
        # Reuse the pre-existing, already-valid c7 coderabbit sidecar pair (real typed
        # coderabbit_review + its egress_scrub sidecar) — this test is about the packet_dir
        # threading leg, not re-proving the coderabbit-receipt shape checks.
        (self.receipts_dir / "coderabbit.yaml").write_bytes(
            (fixtures_dir / "graduation_receipts" / "clean" / "coderabbit-receipt.yaml").read_bytes())
        (self.receipts_dir / "egress_scrub_good.yaml").write_bytes(
            (fixtures_dir / "egress_scrub_good.yaml").read_bytes())
        self.manifest_files = {}
        for rel in ("pkt/MODULE-REGISTRY.yaml", "pkt/requirements-manifest.yaml",
                    "good.yaml", "bad.yaml", "coderabbit.yaml", "egress_scrub_good.yaml"):
            self.manifest_files[rel] = _hashlib.sha256((self.receipts_dir / rel).read_bytes()).hexdigest()

    def _doc(self, acceptance_rel):
        return {
            "modules": [{"module_id": "m_wired", "acceptance_receipt": acceptance_rel,
                        "registry": "pkt/MODULE-REGISTRY.yaml"}],
            "coderabbit_receipt": "coderabbit.yaml",
        }

    def test_unwired_final_module_makes_c7_unmet(self):
        findings = cx_graduation._crit_c7(
            self._doc("bad.yaml"), self.receipts_dir / "bad.yaml", "proj-x", "loc",
            self.receipts_dir, {"manifest_files": self.manifest_files})
        self.assertTrue(any("module-quality replay FAILED" in f[2] for f in findings), findings)

    def test_wired_final_module_makes_c7_met(self):
        findings = cx_graduation._crit_c7(
            self._doc("good.yaml"), self.receipts_dir / "good.yaml", "proj-x", "loc",
            self.receipts_dir, {"manifest_files": self.manifest_files})
        self.assertEqual(findings, [])


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


class TestBProp013ForgeParity(unittest.TestCase):
    """B-PROP-013 Unit 1 (the GUARD): a hex-shaped-but-unreachable repo_sha in verify_app /
    module_demo / live_slice_accept must be graded fabrication (P0) when the frozen packet opts
    in via b_prop_013_forge_parity: true — and must NOT fire at all when the marker is absent
    (grandfather carve-out: legacy packets ride the pre-existing presence-only path unchanged)."""

    def _build(self, tmp, *, marker=True, malformed_marker=False, bad_field=None,
              bad_qc_hash=False, no_packet=False, module_registry_ref=None):
        """Real git repo (2 commits) + a packet dir (requirements-manifest.yaml carrying the
        marker) + a sha12-bound receipt/state. bad_field, if set, is one of
        {"verify_app", "module_demo", "live_slice_accept"} and gets a fabricated (unreachable)
        hex repo_sha; the other two get the real HEAD sha."""
        import hashlib
        repo = os.path.join(tmp, "repo")
        _git_init(repo)
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("one\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        _git_commit(repo, "first")
        with open(os.path.join(repo, "b.txt"), "w") as f:
            f.write("two\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        head_sha = _git_commit(repo, "second")
        fabricated = "deadbeefdead"  # hex-shaped, 12 chars, not a real commit in this repo

        if not no_packet:
            os.makedirs(os.path.join(repo, "packet"), exist_ok=True)
            marker_val = '"true"' if malformed_marker else ("true" if marker else None)
            manifest_lines = []
            if marker_val is not None:
                manifest_lines.append(f"b_prop_013_forge_parity: {marker_val}\n")
            with open(os.path.join(repo, "packet", "requirements-manifest.yaml"), "w") as f:
                f.writelines(manifest_lines)
            subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
            _git_commit(repo, "packet")

        def sha_for(field):
            return fabricated if bad_field == field else head_sha

        qc_block = "  quality_card:\n    security: PASS\n    efficient: PASS\n" \
                   "    regression: PASS\n    tests: PASS\n    conformance: PASS\n"
        qc_hash = _canon_qc_hash({"security": "PASS", "efficient": "PASS", "regression": "PASS",
                                  "tests": "PASS", "conformance": "PASS"})
        if bad_qc_hash:
            qc_hash = "wronghash1234"

        body = (
            "module_acceptance:\n  module_id: m1\n  verdict: accepted\n"
            "  generated_by: cx-accept\n  state_sha_before: 9f8e7d6c5b4a\n"
            f"  quality_card_hash: {qc_hash}\n"
            f"  repo_sha_before: {head_sha}\n"
            + qc_block +
            "  verify_app:\n    passed: true\n"
            f"    repo_sha: {sha_for('verify_app')}\n"
            "    generated_by: verify-app\n    criteria_ref: manual\n"
            "  module_demo:\n    surface: web\n    generated_by: verify-app\n"
            f"    repo_sha: {sha_for('module_demo')}\n"
            "  live_slice_accept:\n    live_url: http://localhost:8787\n"
            "    ceo_drove: true\n    ceo_turn_ref: handoffs/x.md\n"
            f"    repo_sha: {sha_for('live_slice_accept')}\n"
        )
        rp = os.path.join(repo, "receipt.yaml")
        with open(rp, "w") as f:
            f.write(body)
        sha = hashlib.sha256(open(rp, "rb").read()).hexdigest()[:12]
        sp = os.path.join(tmp, "state.yaml")
        pkt_line = "" if no_packet else "packet_dir: packet\n"
        reg_line = f"module_registry_ref: {module_registry_ref}\n" if module_registry_ref else ""
        with open(sp, "w") as f:
            f.write("project: x\nprotocol_stamp: Code-X V1\n" + pkt_line + reg_line +
                    "accepted_modules:\n  - module_id: m1\n    acceptance_ref: receipt.yaml\n"
                    f'    acceptance_sha12: "{sha}"\n')
        return repo, sp

    def test_fabricated_verify_app_repo_sha_bites_p0(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, bad_field="verify_app")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, out)
            self.assertIn("[P0]", out)
            self.assertIn("verify_app.repo_sha", out)
            self.assertIn("MODULE-ACCEPTANCE-REPO-SHA-NOT-A-COMMIT", out)

    def test_fabricated_module_demo_repo_sha_bites_p0(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, bad_field="module_demo")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, out)
            self.assertIn("[P0]", out)
            self.assertIn("module_demo.repo_sha", out)

    def test_fabricated_live_slice_accept_repo_sha_bites_p0(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, bad_field="live_slice_accept")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, out)
            self.assertIn("[P0]", out)
            self.assertIn("live_slice_accept.repo_sha", out)

    def test_quality_card_hash_drift_bites_p1(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, bad_qc_hash=True)
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, out)
            self.assertIn("quality_card_hash", out)
            self.assertIn("recomputed canonical hash", out)

    def test_malformed_marker_bites_p1(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, malformed_marker=True)
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 1, out)
            self.assertIn("[P1]", out)
            self.assertIn("b_prop_013_forge_parity", out)
            self.assertIn("botched", out)

    def test_marker_absent_grandfathers_fabricated_sha(self):
        """No marker at all => legacy path, non-blocking on this guard: a fabricated repo_sha in
        verify_app/module_demo/live_slice_accept must NOT be graded by the B-PROP-013 guard (it
        may still fail other unrelated checks, but never this one) — grandfather carve-out."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, marker=False, bad_field="verify_app")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertNotIn("MODULE-ACCEPTANCE-REPO-SHA-NOT-A-COMMIT", out)

    def test_good_fixture_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp)
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_missing_packet_dir_with_registry_ref_fires_p2_advisory(self):
        """FIX-FIRST (B-PROP-013 xfam P1, packet_dir-omission fail-open): a state that carries
        module_registry_ref (cx_build_turn.py's OWN signal that this is a module-advancing,
        packet-bound build) but NO packet_dir is an anomaly, not genuine legacy — the guard must
        surface a NON-BLOCKING P2 advisory (never P0/P1, per the judge's grandfather ruling), and
        acceptance must still PASS (rc=0) since P2 never blocks."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, no_packet=True, module_registry_ref="MODULE-REGISTRY.yaml")
            # A real post-baseline commit so repo_sha_before != HEAD (avoids an UNRELATED
            # BF-PROP-006 phantom-completion P1 from an incidentally-empty diff — not what this
            # test is proving).
            with open(os.path.join(repo, "c.txt"), "w") as f:
                f.write("three\n")
            subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
            _git_commit(repo, "third")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 0, f"P2 is non-blocking, expected PASS. Got {rc}.\n{out}")
            self.assertIn("[P2]", out)
            self.assertIn("MODULE-ACCEPTANCE-FORGE-PARITY-PACKET-CONTEXT-MISSING", out)
            self.assertNotIn("[P0]", out)
            self.assertNotIn("[P1]", out)

    def test_missing_packet_dir_no_registry_ref_stays_fully_silent(self):
        """Genuine legacy carve-out (judge-protected): NO packet_dir AND no module_registry_ref
        signal at all => completely silent on this guard (no P0/P1/P2) — the grandfathered
        no-packet project must never see even an advisory noise."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, sp = self._build(tmp, no_packet=True)
            with open(os.path.join(repo, "c.txt"), "w") as f:
                f.write("three\n")
            subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
            _git_commit(repo, "third")
            rc, out = run_cx("check", "module-acceptance", "--module-id", "m1",
                             "--state", sp, "--repo-root", repo)
            self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
            self.assertNotIn("MODULE-ACCEPTANCE-FORGE-PARITY-PACKET-CONTEXT-MISSING", out)


def _canon_qc_hash(qc: dict) -> str:
    """Test-side mirror of cx_module_acceptance._canonicalize_quality_card_hash — kept as an
    independent re-implementation (not an import) so the test proves the ALGORITHM, not just
    that the same function was called on both sides."""
    import hashlib as _h
    import json as _j
    canonical = _j.dumps(qc, sort_keys=True, separators=(",", ":"), default=str)
    return _h.sha256(canonical.encode("utf-8")).hexdigest()[:12]


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

    def test_coverage_incomplete_zero_zero_blocks(self):
        """PBF-PROP-021 P1-1 round 1 repro: required_rows AND render_evidence both empty, ui_card
        omitted — must fail closed (this fixture existed but was never wired to a test)."""
        self._bad("render_bad_empty_no_uicard.yaml", "RENDER-FIT-COVERAGE-INCOMPLETE", "P0")

    def test_coverage_incomplete_vacuous_evidence_blocks(self):
        """PBF-PROP-021 P1-1 round 2 (GPT-5.5 xhigh built-code review): a single THROWAWAY but
        otherwise-VALID evidence row must NOT dodge the P0 when required_rows is empty — evidence
        proves rows, it can never DEFINE what was required."""
        self._bad("render_bad_coverage_vacuous_evidence.yaml", "RENDER-FIT-COVERAGE-INCOMPLETE", "P0")

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
                    "      expiry: '2026-12-01'\n      owner: acme\n") if waiver else "  waivers: []\n"
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
# PBF-PROP-019 Phase 3: cx_build_turn CodeRabbit tier-conditional (design v2.B row 3)
# ---------------------------------------------------------------------------
class TestBuildTurnCoderabbitTierGated(unittest.TestCase):
    """LITE drops the every-card CodeRabbit-mandatory finding; STANDARD/STRICT unchanged.
    Mirrors test_build_turn_xfam_requires_coderabbit's minimal-card shape (many OTHER
    sub-checks also fail on this minimal card/state — only the CodeRabbit line is asserted)."""

    def _run(self, tier_packet_dir=None):
        with tempfile.TemporaryDirectory() as t:
            repo = os.path.join(t, "repo")
            os.makedirs(repo, exist_ok=True)
            card = os.path.join(t, "card.yaml")
            with open(card, "w") as f:
                f.write("id: BUILD-X\nmode: MODULE_BUILD\n")
            state = os.path.join(t, "state.yaml")
            body = "project: t\nprotocol_stamp: Code-X V1\n"
            if tier_packet_dir:
                os.makedirs(os.path.join(repo, tier_packet_dir), exist_ok=True)
                body += f"packet_dir: {tier_packet_dir}\n"
            with open(state, "w") as f:
                f.write(body)
            return run_cx("check", "build-turn", card, "--state", state, "--repo-root", repo)

    def test_no_tier_default_strict_requires_coderabbit(self):
        rc, out = self._run()
        self.assertEqual(rc, 1, out)
        self.assertIn("CodeRabbit is MANDATORY", out)

    def test_lite_tier_drops_coderabbit_requirement(self):
        with tempfile.TemporaryDirectory() as t:
            repo = os.path.join(t, "repo")
            pkt = "pbf019_pkt"
            os.makedirs(os.path.join(repo, pkt), exist_ok=True)
            with open(os.path.join(repo, pkt, "requirements-manifest.yaml"), "w") as f:
                f.write("risk_tier: LITE\nrisk_tier_decision_ref: CEO-D-001\n")
            card = os.path.join(t, "card.yaml")
            with open(card, "w") as f:
                f.write("id: BUILD-X\nmode: MODULE_BUILD\n")
            state = os.path.join(t, "state.yaml")
            with open(state, "w") as f:
                f.write(f"project: t\nprotocol_stamp: Code-X V1\npacket_dir: {pkt}\n")
            rc, out = run_cx("check", "build-turn", card, "--state", state, "--repo-root", repo)
            # other sub-checks on this minimal card still fail closed, but never on CodeRabbit
            self.assertNotIn("CodeRabbit is MANDATORY", out)
            self.assertIn("NOT_APPLICABLE coderabbit-receipt (risk_tier: LITE)", out)


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

    def test_pii_phone_and_bank_account_shapes_are_caught(self):
        """PBF-PROP-021 hole #12: real Indonesian phone numbers (raw/dash/spaced/+62/62 prefixes)
        and a 10-digit bank account number (with account-context nearby) are caught — a scrub
        claiming clean is contradicted. (Fixture existed but was never wired to a test — F17.)"""
        rc, out = run_cx("check", "egress", fix("egress_diff_pii.txt"), "--target", "coderabbit",
                         "--receipt", fix("egress_scrub_for_pii.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("contradicted by the diff content", out)
        self.assertIn("Indonesian phone number (PII)", out)
        self.assertIn("10-digit account number (bank/PII)", out)

    def test_benign_long_digit_runs_stay_quiet(self):
        """Negative control: a dotted version string, a hex build hash, an ISO timestamp, and a
        13-digit epoch-millis value are NOT phone/account-shaped — the tripwire stays quiet and
        the scrub is NOT contradicted. (Fixture existed but was never wired to a test — F17.)"""
        rc, out = run_cx("check", "egress", fix("egress_diff_benign_digits.txt"), "--target", "coderabbit",
                         "--receipt", fix("egress_scrub_for_benign_digits.yaml"))
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)

    def test_separator_format_phone_bypasses_are_caught(self):
        """PBF-PROP-021 P1-3 (GPT-5.5 xhigh built-code review): dotted (0812.3456.7890),
        parenthesized ((0812) 3456 7890), and +62-with-parens (+62 (812) 3456-7890) phone formats
        all slipped the old hand-grown separator class. All three are pinned in ONE diff; the
        normalize-then-match fix catches all three (a scrub claiming clean is contradicted)."""
        rc, out = run_cx("check", "egress", fix("egress_diff_pii_separators.txt"), "--target", "coderabbit",
                         "--receipt", fix("egress_scrub_for_pii_separators.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("contradicted by the diff content", out)
        self.assertIn("Indonesian phone number (PII)", out)

    def test_separator_format_phone_bypasses_block_with_no_receipt(self):
        """Same 3 separator-format dodges, no receipt at all — must BLOCK with the hit named."""
        rc, out = run_cx("check", "egress", fix("egress_diff_pii_separators.txt"), "--target", "coderabbit")
        self.assertEqual(rc, 1, out)
        self.assertIn("NO scrub receipt and NO local-only carve-out", out)
        self.assertIn("Indonesian phone number (PII)", out)

    def test_bare_10digit_negative_controls_stay_quiet(self):
        """PBF-PROP-021 P2-1 (GPT-5.5 xhigh built-code review): an order id ('order 1234567890'),
        a datelike code ('2026070712'), and a numeric-leading hex/alnum chunk
        ('1234567890abcdef') must NOT trip the bank-account tripwire — none carry account/bank context, and
        the hex-leading chunk fails the alnum-boundary check. A scrub claiming clean must NOT be
        contradicted (proves the P2-1 fix without weakening the real bank-account catch above)."""
        rc, out = run_cx("check", "egress", fix("egress_diff_benign_bare_10digit.txt"), "--target", "coderabbit",
                         "--receipt", fix("egress_scrub_for_benign_bare_10digit.yaml"))
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS", out)


class TestEgressTierGated(unittest.TestCase):
    """PBF-PROP-019 Phase 3 (design v2.B row 4): LITE/STANDARD only require the scrub for a
    money/PII-touching card; STRICT requires it for every module. Absent --card/--state (the
    pre-existing call shape, TestEgress above) preserves always-required — proven unchanged."""

    def test_non_money_lite_not_required(self):
        rc, out = run_cx("check", "egress", fix("egress_diff_clean.txt"), "--target", "coderabbit",
                         "--card", fix("egress_card_non_money.yaml"),
                         "--state", fix("state_pbf019_lite.yaml"))
        self.assertEqual(rc, 0, out)
        self.assertIn("NOT_APPLICABLE", out)

    def test_non_money_strict_still_required(self):
        rc, out = run_cx("check", "egress", fix("egress_diff_clean.txt"), "--target", "coderabbit",
                         "--card", fix("egress_card_non_money.yaml"),
                         "--state", fix("state_pbf019_strict.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("NO scrub receipt and NO local-only carve-out", out)

    def test_money_lite_still_required(self):
        """The money/PII trigger is NEVER relaxed by tier, even under LITE."""
        rc, out = run_cx("check", "egress", fix("egress_diff_clean.txt"), "--target", "coderabbit",
                         "--card", fix("egress_card_money.yaml"),
                         "--state", fix("state_pbf019_lite.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("NO scrub receipt and NO local-only carve-out", out)

    def test_sensitive_hit_lite_non_money_still_required(self):
        """A mechanical tripwire hit (a real detected secret) is evidence, not a self-declared
        risk class — it forces the requirement regardless of tier/card declaration."""
        rc, out = run_cx("check", "egress", fix("egress_diff_secret.txt"), "--target", "coderabbit",
                         "--card", fix("egress_card_non_money.yaml"),
                         "--state", fix("state_pbf019_lite.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("NO scrub receipt and NO local-only carve-out", out)


class TestEgressPhoneAndBankAccountPatternsDirect(unittest.TestCase):
    """PBF-PROP-021 P1-3 / P2-1 (GPT-5.5 xhigh built-code review): direct, in-process proof of the
    normalize-then-match phone detector and the context-gated bank-account detector — precise per-shape
    coverage that complements the CLI/fixture-level TestEgress tests above."""

    def test_all_separator_formats_normalize_and_match(self):
        for shape in ("0812-3456-7890", "08123456789", "+62 812-3456-7890",
                      "0812.3456.7890", "(0812) 3456 7890", "+62 (812) 3456-7890"):
            normalized = cx_egress._normalize_digit_runs(shape)
            self.assertTrue(cx_egress._ID_PHONE_RE.search(normalized),
                            f"{shape!r} (normalized {normalized!r}) should match _ID_PHONE_RE")

    def test_bank_account_negative_controls_stay_quiet(self):
        for shape in ("order 1234567890", "2026070712", "1234567890abcdef"):
            normalized = cx_egress._normalize_digit_runs(shape)
            self.assertFalse(cx_egress._bank_account_hit(normalized),
                             f"{shape!r} must NOT trip the bank-account context-gated detector")

    def test_bank_account_with_context_is_caught(self):
        shape = "BANK_ACCOUNT = '1234509876'"
        normalized = cx_egress._normalize_digit_runs(shape)
        self.assertTrue(cx_egress._bank_account_hit(normalized),
                        "a real 10-digit account number with bank context must be caught")


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
# PROP-042-DRAFT / V1.21-candidate — review routing hardening from the real-project planning skip
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


class TestStateReviewBoundaryCoderabbitTierGated(unittest.TestCase):
    """PBF-PROP-019 P2 FIX (integration drift): `cx check state` required
    coderabbit_before_self_review: yes for BUILD_FACTORY MODULE_BUILD/MODE_A_UI work in EVERY
    tier, but cards + build-turn already let LITE skip CodeRabbit (cx_card.py:419,
    cx_build_turn.py:251) — a LITE project was forced to either keep an inaccurate 'yes' or
    fail state check. Now tier-aware: LITE relaxes the requirement; STANDARD/STRICT
    unchanged."""

    def test_lite_state_without_coderabbit_passes(self):
        rc, out = run_cx("check", "state", fix("state_good_review_boundary_coderabbit_na_lite.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_standard_same_shape_without_coderabbit_still_fails(self):
        # Same shape, no packet_dir -> tier defaults STRICT (fail-closed) -> still mandatory.
        rc, out = run_cx("check", "state", fix("state_bad_review_boundary_coderabbit_na.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("CodeRabbit", out)


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
            # PBF-PROP-021 group-1: evidence_required is path-safety-guarded now — an
            # absolute tempdir path is rejected before the faked-pass scan this test
            # exercises. Card-relative keeps the scan reachable.
            card = {"id": "TEST-004", "mode": "MODULE_BUILD", "model_tier": "standard",
                    "objective": "Test.", "evidence_required": [ev.name]}
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
        real-project cards live under cards/ and require evidence/... at the project root; the
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


class TestCheckCostRound3(unittest.TestCase):
    """PBF-PROP-021 group-2 hole #4/#5: type(value) is int (not isinstance) + crash close.

    PRE-FIX PROOF (verified interactively before this fix landed):
      - cost_log_quoted_review_fix_cycles.yaml (review_fix_cycles: "4") returned PASS exit 0 —
        isinstance(rfc, int) silently rejected the quoted str with NO finding at all.
      - cost_log_quoted_loops_used_crashes.yaml (loops_used: "9") returned FATAL exit 2
        (TypeError: unsupported operand type(s) for +: 'int' and 'str') in the roll-up sum.
    """

    def test_quoted_review_fix_cycles_fires_not_a_real_integer(self):
        rc, out = run_cx("check", "cost", fix("cost_log_quoted_review_fix_cycles.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("review_fix_cycles", out)
        self.assertIn("is not a real integer", out)

    def test_quoted_loops_used_no_longer_crashes(self):
        rc, out = run_cx("check", "cost", fix("cost_log_quoted_loops_used_crashes.yaml"))
        self.assertEqual(rc, 1, f"Expected FIX-FIRST (not a FATAL crash), got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("loops_used", out)
        self.assertIn("is not a real integer", out)
        self.assertNotIn("FATAL", out)

    def test_good_cost_log_still_passes(self):
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
    def test_protocol_version_constant_marks_1_22_6_folded(self):
        """The checker reports v1.22.6 (CEO-D-051 fold 2026-07-07; lock-onto-main pending CEO "lock") as the protocol version."""
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            import cx_common
            self.assertEqual(cx_common.PROTOCOL_VERSION, "1.22.6")
        finally:
            sys.path.pop(0)

    def test_cx_version_reports_1_22_6_folded(self):
        """`cx --version` reports the v1.22.6 (CEO-D-051) canonical version (not candidate)."""
        rc, out = run_cx("--version")
        self.assertEqual(rc, 0, f"Expected exit 0 from --version, got {rc}.\n{out}")
        self.assertRegex(out, r"V1\.22\.6(?!\d)")
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


class TestPBFPROP015StateArity(unittest.TestCase):
    """PBF-PROP-015: an unparseable / ill-shaped CODE-X-STATE.yaml must be
    REPORTED as a [P0], never crash the checker on a tuple-unpack. The two
    early-error return sites in collect_state_findings were 3-ary while both
    callers (cmd_state and cx check boot) unpack 4 — so ANY bad state file
    exited 2 ("not enough values to unpack") with the real P0 swallowed. A
    session-start guard that cannot report its own worst input is a gate that
    does not bite. These pin the [P0] line via BOTH callers."""

    def test_duplicate_key_state_reports_p0_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "state.yaml")
            with open(state, "w") as f:
                f.write("protocol_stamp: Code-X V1\nproject: x\nproject: y\n")
            rc, out = run_cx("check", "state", state)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST exit 1 (not crash exit 2), got {rc}.\n{out}")
            self.assertIn("[P0]", out)
            self.assertIn("duplicate key", out.lower())
            self.assertNotIn("not enough values to unpack", out)

    def test_non_mapping_state_reports_p0_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "state.yaml")
            with open(state, "w") as f:
                f.write("- just\n- a list\n")
            rc, out = run_cx("check", "state", state)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST exit 1 (not crash exit 2), got {rc}.\n{out}")
            self.assertIn("[P0]", out)
            self.assertIn("not a YAML mapping", out)
            self.assertNotIn("not enough values to unpack", out)

    def test_boot_on_unparseable_state_reports_p0_not_crash(self):
        """Second caller: cx check boot must surface the [P0], not crash. Its
        fatal branch was dead code until the arity fix (it always crashed on the
        unpack first), so its output shape is pinned here for the first time."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            state = os.path.join(tmp, "state.yaml")
            with open(state, "w") as f:
                f.write("protocol_stamp: Code-X V1\nproject: x\nproject: y\n")
            receipt = os.path.join(tmp, "protocol-boot-receipt.yaml")
            rc, out = run_cx("check", "boot", "--state", state,
                             "--repo-root", repo, "--out", receipt)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST exit 1 (not crash exit 2), got {rc}.\n{out}")
            self.assertIn("[P0]", out)
            self.assertIn("duplicate key", out.lower())
            self.assertNotIn("not enough values to unpack", out)

    def test_boot_on_non_mapping_state_reports_p0_not_crash(self):
        """Second caller against the second early-error branch (non-mapping),
        so cx check boot is pinned on BOTH fatal paths (GPT-5.5 xfam P3)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            state = os.path.join(tmp, "state.yaml")
            with open(state, "w") as f:
                f.write("- just\n- a list\n")
            receipt = os.path.join(tmp, "protocol-boot-receipt.yaml")
            rc, out = run_cx("check", "boot", "--state", state,
                             "--repo-root", repo, "--out", receipt)
            self.assertEqual(rc, 1, f"Expected FIX-FIRST exit 1 (not crash exit 2), got {rc}.\n{out}")
            self.assertIn("[P0]", out)
            self.assertIn("not a YAML mapping", out)
            self.assertNotIn("not enough values to unpack", out)


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
# cx check packet — PB-PROP-003 Unit 1 (packet stage): Given/When/Then examples +
# typed/anchored non_behavioral_exemption.
# ---------------------------------------------------------------------------
class TestCheckPacketPBPROP003GWT(unittest.TestCase):
    def test_good_packet_has_examples_and_passes(self):
        """Positive control: packet_good's behavioral row now carries a well-formed
        Given/When/Then example and still PASSes."""
        rc, out = run_cx("check", "packet", fix("packet_good"))
        self.assertEqual(rc, 0, f"packet_good should PASS, got {rc}.\n{out}")

    def test_examples_required_on_behavioral_row(self):
        """A behavioral BUILDING row (no non_behavioral_exemption) with no examples bites."""
        rc, out = run_cx("check", "packet", fix("packet_bad_gwt_missing"))
        self.assertEqual(rc, 1)
        self.assertIn("PACKET-GWT-EXAMPLE-REQUIRED", out)
        self.assertIn("examples", out)

    def test_malformed_example_bites(self):
        """An example with a placeholder 'then' clause is not a well-formed G/W/T item —
        structure only, never an English-quality judgment."""
        rc, out = run_cx("check", "packet", fix("packet_bad_gwt_malformed"))
        self.assertEqual(rc, 1)
        self.assertIn("PACKET-GWT-EXAMPLE-MALFORMED", out)
        self.assertIn("'then'", out.replace('"', "'"))

    def test_valid_exemption_passes_without_examples(self):
        """A typed + anchored non_behavioral_exemption (reason in the frozen vocabulary,
        artifact_ref resolving to a real in-packet file) exempts the row — no examples needed."""
        rc, out = run_cx("check", "packet", fix("packet_good_gwt_exemption"))
        self.assertEqual(rc, 0, f"valid exemption should PASS, got {rc}.\n{out}")

    def test_untyped_exemption_bites(self):
        """A bare-string non_behavioral_exemption (not a {reason, artifact_ref} mapping) is
        the free-text hatch this clause forbids."""
        rc, out = run_cx("check", "packet", fix("packet_bad_gwt_exemption_untyped"))
        self.assertEqual(rc, 1)
        self.assertIn("PACKET-EXEMPTION-UNTYPED-OR-UNANCHORED", out)

    def test_unresolvable_artifact_ref_bites(self):
        """A well-formed {reason, artifact_ref} whose artifact_ref names neither a real
        packet file nor a real requirement/module/screen id is a bare claim, not an anchor —
        and must not be defeated by a naive full-text substring scan of the manifest that
        declares the ref (self-reference loophole)."""
        rc, out = run_cx("check", "packet", fix("packet_bad_gwt_exemption_unresolved"))
        self.assertEqual(rc, 1)
        self.assertIn("PACKET-EXEMPTION-UNTYPED-OR-UNANCHORED", out)

    def test_self_referential_manifest_artifact_ref_rejected(self):
        """CX-PB003-003 FIX-FIRST (xfam finding 3, P1): artifact_ref: requirements-manifest.yaml
        is a REAL, EXISTING file (it's the manifest declaring the exemption) — the naive
        target.is_file() check used to accept this as a resolved anchor. Must be rejected: an
        anchor cannot be the manifest (or registry) that carries its own declaration."""
        rc, out = run_cx("check", "packet", fix("packet_bad_gwt_exemption_self_ref"))
        self.assertEqual(rc, 1, "a manifest-self-referencing artifact_ref must be rejected")
        self.assertIn("PACKET-EXEMPTION-UNTYPED-OR-UNANCHORED", out)

    def test_lite_relaxes_authoring_standard_enforces(self):
        """Tier-split proof (§R3): the SAME example-less behavioral row PASSES at LITE and
        FAILS at STANDARD — authoring is ceremony, not spine."""
        rc_lite, out_lite = run_cx("check", "packet", fix("packet_good_risk_tier_lite"))
        self.assertEqual(rc_lite, 0, f"LITE should relax authoring, got {rc_lite}.\n{out_lite}")
        rc_std, out_std = run_cx("check", "packet", fix("packet_good_risk_tier_standard"))
        self.assertEqual(rc_std, 1, "STANDARD must enforce authoring on the same row")
        self.assertIn("PACKET-GWT-EXAMPLE-REQUIRED", out_std)

    def test_malformed_manifest_fails_closed(self):
        """A requirements-manifest.yaml whose 'requirements' is not a list must FAIL the
        G/W/T clause (fail-closed), not silently skip it like _check_acceptance_criteria."""
        rc, out = run_cx("check", "packet", fix("packet_bad_gwt_manifest_malformed"))
        self.assertEqual(rc, 1)
        self.assertIn("PACKET-GWT-MANIFEST-MALFORMED-FAILS-CLOSED", out)


class TestCheckPacketForgeParityWaiverRound2(unittest.TestCase):
    """PBF-PROP-021 group-2 hole #9 (round 1): the --legacy-migration frozen_packet_hash waiver
    leg was SHAPE-CHECKED (real sha256 hex digest), not accepted as any non-empty string.

    PRE-FIX PROOF (verified interactively before this fix landed): `cx check packet
    packet_bad_forge_parity_waiver_forged_hash --legacy-migration` returned PASS exit 0 — the
    self-authored 'totally-forged-not-a-hash' string satisfied `if not rerr and fph:` verbatim.

    PBF-PROP-021 P1-2 round 2 (GPT-5.5 xhigh built-code review): the shape-check leg ITSELF was
    then found forgeable — any 64-char hex (e.g. all-zeros) shape-passes trivially. The leg is now
    REMOVED entirely; both a non-hex garbage string AND a validly-shaped all-zeros hex fail
    identically (neither is proof the packet was really frozen — only a resolving
    --migration-ref counts)."""

    def test_self_authored_non_hex_hash_does_not_waive(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_forge_parity_waiver_forged_hash"),
                         "--legacy-migration")
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("PACKET-FORGE-PARITY-MARKER-REQUIRED", out)
        self.assertIn("are NOT a waiver", out)

    def test_self_authored_allzeros_hex_does_not_waive(self):
        """PBF-PROP-021 P1-2 round 2: a VALIDLY-SHAPED 64-char hex (all zeros) — the exact dodge
        the GPT-5.5 xhigh reviewer named — must fail identically to the non-hex garbage string
        above; the registry-hash leg is gone, so shape no longer matters at all."""
        rc, out = run_cx("check", "packet", fix("packet_bad_forge_parity_waiver_allzeros_hash"),
                         "--legacy-migration")
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("PACKET-FORGE-PARITY-MARKER-REQUIRED", out)
        self.assertIn("are NOT a waiver", out)

    def test_migration_ref_resolving_to_ledger_row_waives(self):
        """The one remaining (strong) leg still works: --migration-ref resolving to a real
        MEMORY/CEO-DECISION-LEDGER.md row exempts the marker requirement."""
        rc, out = run_cx("check", "packet", fix("packet_bad_forge_parity_waiver_allzeros_hash"),
                         "--legacy-migration", "--migration-ref", "CEO-D-001")
        self.assertEqual(rc, 0, f"Expected PASS via the resolving migration-ref, got {rc}.\n{out}")

    def test_migration_ref_not_in_ledger_does_not_waive(self):
        """A --migration-ref that merely LOOKS like a ledger id but names no real protocol-ledger
        row must not waive (the fake-ref self-exemption escape hatch)."""
        rc, out = run_cx("check", "packet", fix("packet_bad_forge_parity_waiver_allzeros_hash"),
                         "--legacy-migration", "--migration-ref", "CEO-D-99999-FAKE")
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("PACKET-FORGE-PARITY-MARKER-REQUIRED", out)

    def test_good_packet_still_passes(self):
        rc, out = run_cx("check", "packet", fix("packet_good"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)


# ---------------------------------------------------------------------------
# CX-PB003-002 FIX-FIRST (xfam finding 2, P1): the pb_prop_003_wiring marker must be TRI-STATE, not
# a plain bool that collapses "malformed" (field present but not boolean True, e.g. a quoted
# "true"/"yes" string) into the same False as genuine "absent" — a packet that TRIED to opt in and
# botched it must BLOCK, never silently keep the legacy carve-out only real absence deserves.
# Covers both ends of the marker's lifecycle: freeze-time (cx check packet) and acceptance-time
# (cx check verify-app / _resolve_pb_prop_003_wiring_state).
# ---------------------------------------------------------------------------
class TestCXPB003002MalformedMarkerFailsClosed(unittest.TestCase):
    def test_packet_freeze_rejects_malformed_marker(self):
        """cx check packet: a quoted pb_prop_003_wiring: \"true\" trips
        PACKET-PB-PROP-003-MARKER-WELL-FORMED at freeze time."""
        rc, out = run_cx("check", "packet", fix("pb_prop_003_malformed_marker_packet"))
        self.assertEqual(rc, 1)
        self.assertIn("PACKET-PB-PROP-003-MARKER-WELL-FORMED", out)
        self.assertIn("not a real boolean true", out)

    def test_packet_freeze_absent_marker_has_no_such_finding(self):
        """Control: a packet with NO marker field at all (packet_good) never trips this clause —
        absence is a legitimate non-opt-in, not malformed."""
        rc, out = run_cx("check", "packet", fix("packet_good"))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("PACKET-PB-PROP-003-MARKER-WELL-FORMED", out)

    def test_verify_app_rejects_malformed_marker(self):
        """cx check verify-app: the SAME malformed marker BLOCKS at acceptance time — it must NOT
        silently fall to the non-blocking ACCEPTANCE-LEGACY-CRITERIA-REF-ADVISORY carve-out."""
        rc, out = run_cx("check", "verify-app",
                         "--acceptance", fix("verify_app_malformed_marker.yaml"),
                         "--packet-dir", fix("pb_prop_003_malformed_marker_packet"))
        self.assertEqual(rc, 1, out)
        self.assertIn("[P1]", out)
        self.assertIn("not a real boolean true", out)
        self.assertNotIn("ACCEPTANCE-LEGACY-CRITERIA-REF-ADVISORY", out)

    def test_verify_app_absent_marker_keeps_legacy_advisory_nonblocking(self):
        """Control (unchanged §R5 behavior): genuine absence still gets the non-blocking P2
        legacy advisory, rc stays 0 — malformed and absent are NOT the same outcome anymore."""
        rc, out = run_cx("check", "verify-app",
                         "--acceptance", fix("verify_app_legacy_ok.yaml"),
                         "--packet-dir", fix("pb_prop_003_legacy_packet"))
        self.assertEqual(rc, 0, out)
        self.assertIn("ACCEPTANCE-LEGACY-CRITERIA-REF-ADVISORY", out)

    def test_resolver_tri_state_directly(self):
        """Unit-test _resolve_pb_prop_003_wiring_state directly: absent / enabled / malformed are
        3 DISTINCT outcomes, not a collapsed bool."""
        import cx_module_acceptance
        self.assertEqual(
            cx_module_acceptance._resolve_pb_prop_003_wiring_state(fix("pb_prop_003_legacy_packet")),
            "absent")
        self.assertEqual(
            cx_module_acceptance._resolve_pb_prop_003_wiring_state(fix("pb_prop_003_wired_packet")),
            "enabled")
        self.assertEqual(
            cx_module_acceptance._resolve_pb_prop_003_wiring_state(fix("pb_prop_003_malformed_marker_packet")),
            "malformed")
        self.assertEqual(cx_module_acceptance._resolve_pb_prop_003_wiring_state(None), "absent")


# ---------------------------------------------------------------------------
# CX-PB003-002 residual (fix re-sweep) — build-turn's verify-app sub-check must THREAD
# --packet-dir/--module-id (from state.packet_dir / card.module_id) into `cx check verify-app`,
# not call it bare. Bare-call was the exact gap: a malformed pb_prop_003_wiring marker (or a
# dangling criteria_ref) has NO packet context to resolve against, so cx_module_acceptance's
# _validate_criteria_wiring leg never runs and the receipt PASSES on the build-turn rail even
# though the standalone `cx check verify-app --packet-dir ...` call (TestCXPB003002Malformed-
# MarkerFailsClosed, above) correctly blocks it. This drives cmd_build_turn end-to-end (real
# subprocess via run_cx, not a mock) with a card.verify_app_ref + state.packet_dir, exactly the
# shape the fixed code path reads.
# ---------------------------------------------------------------------------
class TestCXPB003002BuildTurnPacketDirThreading(unittest.TestCase):
    def _repo(self, t, packet_fixture, receipt_fixture, module_id, extra_pkt_files=()):
        repo = os.path.join(t, "repo")
        os.makedirs(os.path.join(repo, "pkt"), exist_ok=True)
        os.makedirs(os.path.join(repo, "acceptance"), exist_ok=True)
        pkt_src = FIXTURES / packet_fixture
        (Path(repo) / "pkt" / "requirements-manifest.yaml").write_text(
            (pkt_src / "requirements-manifest.yaml").read_text())
        for name in extra_pkt_files:
            (Path(repo) / "pkt" / name).write_text((pkt_src / name).read_text())
        (Path(repo) / "acceptance" / "receipt.yaml").write_text(fix_text(receipt_fixture))
        with open(os.path.join(repo, "card.yaml"), "w") as f:
            f.write(f"id: BUILD-X\nmode: FIX\nverify_app_ref: acceptance/receipt.yaml\n"
                    f"module_id: {module_id}\n")
        state = os.path.join(t, "state.yaml")
        with open(state, "w") as f:
            f.write("project: t\nprotocol_stamp: Code-X V1\npacket_dir: pkt\n")
        return repo, os.path.join(repo, "card.yaml"), state

    def test_build_turn_threads_packet_dir_catches_malformed_marker(self):
        """POSITIVE (the bite): a build-turn run on a card whose verify_app_ref receipt sits under
        a packet with a MALFORMED pb_prop_003_wiring marker (string "true", not boolean) must FAIL
        the verify-app sub-check and surface the CX-PB003-002 finding — proving build-turn now
        passes state.packet_dir through, not just the standalone verify-app CLI call. Without the
        fix (bare `cx check verify-app --acceptance <ref>`, no --packet-dir), this sub-check PASSES
        instead (verified by stashing the fix and re-running: output becomes
        '[INFO] PASS verify-app') — that is the exact gap CX-PB003-002 closes."""
        with tempfile.TemporaryDirectory() as t:
            repo, card, state = self._repo(
                t, "pb_prop_003_malformed_marker_packet", "verify_app_malformed_marker.yaml",
                "m_malformed")
            rc, out = run_cx("check", "build-turn", card, "--state", state, "--repo-root", repo)
            self.assertEqual(rc, 1, out)
            self.assertIn("[P1] verify-app", out)
            self.assertIn("not a real boolean true", out)
            self.assertIn("CX-PB003-002", out)

    def test_build_turn_threads_packet_dir_control_wired_receipt_passes(self):
        """CONTROL (no regression / no false-positive): the SAME build-turn shape, but the packet's
        pb_prop_003_wiring marker is a real boolean true and the receipt's criteria_refs correctly
        resolves + reverse-covers module m_wired's behavioral requirements — the verify-app
        sub-check must still PASS through build-turn (threading --packet-dir must not turn a
        genuinely well-wired receipt into a false failure)."""
        with tempfile.TemporaryDirectory() as t:
            repo, card, state = self._repo(
                t, "pb_prop_003_wired_packet", "verify_app_wired_good.yaml", "m_wired",
                extra_pkt_files=("MODULE-REGISTRY.yaml",))
            rc, out = run_cx("check", "build-turn", card, "--state", state, "--repo-root", repo)
            self.assertIn("[INFO] PASS verify-app", out)

    def test_build_turn_threads_packet_dir_control_legacy_packet_passes(self):
        """CONTROL variant: a legacy packet (no pb_prop_003_wiring marker at all — the default
        state of every live packet today) still passes the verify-app sub-check through build-turn
        (non-blocking advisory only), confirming the threading doesn't retroactively break packets
        that never opted in."""
        with tempfile.TemporaryDirectory() as t:
            repo, card, state = self._repo(
                t, "pb_prop_003_legacy_packet", "verify_app_legacy_ok.yaml", "m_legacy")
            rc, out = run_cx("check", "build-turn", card, "--state", state, "--repo-root", repo)
            self.assertIn("[INFO] PASS verify-app", out)


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


class TestBlueprintDepthTierGated(unittest.TestCase):
    """PBF-PROP-019 Phase 3 (design v2.B row 6, blueprint_depth): LITE drops the control: (full
    behaviour-contract) anchors from the expected set — nav-map (nav:) + requirements (req:) stay
    (the "nav-map + done-test" floor; BLUEPRINT-FEATURE-HAS-DONE-TEST is untouched, enforced
    elsewhere in _validate_module regardless of tier). Unit-tests _derive_expected_anchor_ids
    directly (cx_blueprint imported in-process, mirrors the cx_kaizen/cx_common precedent above) —
    the full CLI path is proven unbroken by TestCheckBlueprint's unmodified 465-test pass (no
    risk_tier field in blueprint_good_packet's manifest -> defaults STRICT, byte-for-byte)."""

    _REG_MODULE = {"requirement_ids": ["REQ-1"]}
    _CONTRACTS = {"C1": {"control_id": "ctrl-1", "screen": "home"}}
    _SCREEN_NAV = {"home": ["settings"]}

    def test_lite_drops_control_anchors(self):
        expected = cx_blueprint._derive_expected_anchor_ids(
            self._REG_MODULE, "home", "home", "screen", self._CONTRACTS, self._SCREEN_NAV,
            risk_tier="LITE")
        self.assertEqual(expected, {"req:REQ-1", "nav:home->settings"})

    def test_default_strict_keeps_control_anchors(self):
        # default risk_tier param ("STRICT") preserves today's behaviour byte-for-byte.
        expected = cx_blueprint._derive_expected_anchor_ids(
            self._REG_MODULE, "home", "home", "screen", self._CONTRACTS, self._SCREEN_NAV)
        self.assertEqual(expected, {"req:REQ-1", "control:ctrl-1", "nav:home->settings"})

    def test_standard_keeps_control_anchors(self):
        expected = cx_blueprint._derive_expected_anchor_ids(
            self._REG_MODULE, "home", "home", "screen", self._CONTRACTS, self._SCREEN_NAV,
            risk_tier="STANDARD")
        self.assertEqual(expected, {"req:REQ-1", "control:ctrl-1", "nav:home->settings"})


# ---------------------------------------------------------------------------
# blueprint-page (P-PROP-007 v1.22.2 — the projection-views render-faithfulness gate)
# ---------------------------------------------------------------------------
class TestCheckBlueprintPage(unittest.TestCase):
    """P-PROP-007: cx check blueprint-page recomputes the three projection views (storyboard
    frames/edges/lanes + prototype tab + anchor ids) from canonical source and requires the
    rendered page's markers to be set-equal; cx check blueprint itself stays untouched."""

    GOOD_PACKET = "blueprint_good_packet"
    GOOD_PAGE = "blueprint_good_page.html"

    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(FIXTURES / "_gen_blueprint_fixtures.py")], check=True)
        subprocess.run([sys.executable, str(FIXTURES / "_gen_blueprint_page_fixtures.py")], check=True)

    def _run(self, page, packet=None, all_=True):
        args = [fix(packet or self.GOOD_PACKET), "--page", fix(page)]
        if all_:
            args += ["--all"]
        return run_cx("check", "blueprint-page", *args)

    def test_good_page_all_modules_passes(self):
        rc, out = self._run(self.GOOD_PAGE)
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)

    def test_module_flag_rejected(self):
        # xfam X2 (CEO-D-040): --module was REMOVED — the page is a whole-plan artefact checked
        # whole, always. Passing --module must fail as an unknown argument, not silently scope.
        rc, out = run_cx("check", "blueprint-page", fix(self.GOOD_PACKET),
                         "--page", fix(self.GOOD_PAGE), "--module", "home")
        self.assertNotEqual(rc, 0)
        self.assertIn("unrecognized argument", (out or "").lower())

    def test_missing_frame_fails_p1(self):
        rc, out = self._run("blueprint_bad_page_missing_frame.html")
        self.assertEqual(rc, 1)
        self.assertIn("[P1]", out)
        self.assertIn("BLUEPRINT-STORYBOARD-FRAMES", out)

    def test_handdrawn_edge_fails_p1(self):
        rc, out = self._run("blueprint_bad_page_handdrawn_edge.html")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-STORYBOARD-EDGES", out)

    def test_missing_journey_lane_fails_p1(self):
        rc, out = self._run("blueprint_bad_page_missing_lane.html")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-STORYBOARD-LANES", out)

    def test_prototype_hash_mismatch_fails_p1(self):
        rc, out = self._run("blueprint_bad_page_proto_hash_mismatch.html")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-PROTOTYPE-TAB-LOCKED", out)

    def test_invented_anchor_id_fails_p1(self):
        rc, out = self._run("blueprint_bad_page_anchor_invented.html")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-ANCHOR-ID-VISIBLE", out)

    def test_missing_page_fails_closed_at_frames(self):
        rc, out = run_cx("check", "blueprint-page", fix(self.GOOD_PACKET), "--all")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-STORYBOARD-FRAMES", out)
        self.assertIn("--page", out)

    def test_unreadable_page_fails_closed(self):
        rc, out = self._run("blueprint_bad_page_unreadable.html")
        self.assertEqual(rc, 1)
        self.assertIn("BLUEPRINT-STORYBOARD-FRAMES", out)
        self.assertIn("fail-closed", out)

    def test_pathsafe_proto_src_rejected(self):
        rc, out = self._run(self.GOOD_PAGE)
        self.assertEqual(rc, 0)
        # a proto src escaping the packet must be rejected, not silently trusted
        import tempfile as _tmp
        bad_html = ('<section data-storyboard-frame="home">h</section>'
                   '<section data-storyboard-frame="detail">d</section>'
                   '<div data-storyboard-edge="home->detail"></div>'
                   '<p data-journey-lane="1">I tap Add entry, the app opens the form</p>'
                   '<p data-journey-lane="1">money rounds the same everywhere</p>'
                   '<iframe data-proto-src="../../../etc/passwd" data-proto-src-hash="' + "0" * 64 + '"></iframe>'
                   '<span data-anchor-id="req:REQ-001"></span>'
                   '<span data-anchor-id="req:REQ-002"></span>'
                   '<span data-anchor-id="control:add_entry"></span>'
                   '<span data-anchor-id="nav:home->detail"></span>'
                   '<span data-anchor-id="req:REQ-003"></span>')
        with _tmp.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(bad_html)
            path = f.name
        try:
            rc, out = run_cx("check", "blueprint-page", fix(self.GOOD_PACKET), "--page", path, "--all")
            self.assertEqual(rc, 1)
            self.assertIn("BLUEPRINT-PROTOTYPE-TAB-LOCKED", out)
            self.assertIn("does not resolve to a real, in-packet", out)
        finally:
            os.unlink(path)

    def test_blueprint_semantics_unchanged(self):
        # cx check blueprint (the existing gate) must still PASS exactly as before — zero behavior
        # change from adding the new sibling subcommand.
        rc, out = run_cx("check", "blueprint", fix(self.GOOD_PACKET), "--all",
                         "--state", fix("blueprint_good_state.yaml"),
                         "--approval", fix("blueprint_good_approval.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS for --all, got {rc}.\n{out}")

    # F1 (self-review, fail-closed): a kind:screen module whose ui_lock_manifest ref does NOT
    # resolve to a real, in-packet, non-symlink file must NOT be silently dropped from
    # expected_proto — it must fail closed with a P1 finding instead of letting a page stripped
    # of that module's prototype embed PASS.
    def test_unsafe_lock_ref_fails_closed_p1(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            packet = os.path.join(tmp, "packet")
            shutil.copytree(fix(self.GOOD_PACKET), packet)
            manifest_path = Path(packet) / "blueprint-manifest.yaml"
            text = manifest_path.read_text(encoding="utf-8")
            # 'detail' shares home's lock ref today; break ONLY detail's, leaving home's intact
            # so this pins the fail-closed path in isolation (not a duplicate of the hash-mismatch
            # or missing-embed fixtures).
            lines = text.splitlines()
            out_lines = []
            in_detail = False
            for ln in lines:
                if ln.strip().startswith("- module_id: detail"):
                    in_detail = True
                if in_detail and ln.strip().startswith("ui_lock_manifest:"):
                    indent = ln[:len(ln) - len(ln.lstrip())]
                    out_lines.append(f"{indent}ui_lock_manifest: ui-locks/does-not-exist.lock.yaml")
                    in_detail = False
                    continue
                out_lines.append(ln)
            manifest_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
            rc, out = run_cx("check", "blueprint-page", packet, "--page", fix(self.GOOD_PAGE), "--all")
            self.assertEqual(rc, 1)
            self.assertIn("[P1]", out)
            self.assertIn("BLUEPRINT-PROTOTYPE-TAB-LOCKED", out)
            self.assertIn("does not resolve to a real, in-packet, non-symlink file", out)

    # F6 (self-review): pin the EXTRA-frame rejection path (a hand-drawn frame not derivable from
    # any registered kind:screen module) — only the missing-frame direction had a fixture before.
    def test_extra_frame_hand_drawn_fails_p1(self):
        import hashlib as _hashlib
        lock_hash = _hashlib.sha256(Path(fix("blueprint_good_packet")).joinpath(
            "ui-locks", "home.lock.yaml").read_bytes()).hexdigest()
        bad_html = ('<section data-storyboard-frame="home">h</section>'
                   '<section data-storyboard-frame="detail">d</section>'
                   '<section data-storyboard-frame="ghostscreen">ghost</section>'
                   '<div data-storyboard-edge="home->detail"></div>'
                   '<p data-journey-lane="1">I tap Add entry, the app opens the form</p>'
                   '<p data-journey-lane="1">money rounds the same everywhere</p>'
                   f'<iframe data-proto-src="ui-locks/home.lock.yaml" data-proto-src-hash="{lock_hash}"></iframe>'
                   '<span data-anchor-id="req:REQ-001"></span>'
                   '<span data-anchor-id="req:REQ-002"></span>'
                   '<span data-anchor-id="control:add_entry"></span>'
                   '<span data-anchor-id="nav:home->detail"></span>'
                   '<span data-anchor-id="req:REQ-003"></span>')
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(bad_html)
            path = f.name
        try:
            rc, out = self._run(path)
            self.assertEqual(rc, 1)
            self.assertIn("BLUEPRINT-STORYBOARD-FRAMES", out)
            self.assertIn("not derivable from any registered", out)
            self.assertIn("ghostscreen", out)
        finally:
            os.unlink(path)

    # F6 (self-review): pin the EXTRA-lane rejection path (a re-typed/invented lane text with no
    # verbatim match in the manifest) — only the missing-lane direction had a fixture before.
    def test_extra_lane_invented_text_fails_p1(self):
        import hashlib as _hashlib
        lock_hash = _hashlib.sha256(Path(fix("blueprint_good_packet")).joinpath(
            "ui-locks", "home.lock.yaml").read_bytes()).hexdigest()
        bad_html = ('<section data-storyboard-frame="home">h</section>'
                   '<section data-storyboard-frame="detail">d</section>'
                   '<div data-storyboard-edge="home->detail"></div>'
                   '<p data-journey-lane="1">I tap Add entry, the app opens the form</p>'
                   '<p data-journey-lane="1">money rounds the same everywhere</p>'
                   '<p data-journey-lane="1">this journey was never approved</p>'
                   f'<iframe data-proto-src="ui-locks/home.lock.yaml" data-proto-src-hash="{lock_hash}"></iframe>'
                   '<span data-anchor-id="req:REQ-001"></span>'
                   '<span data-anchor-id="req:REQ-002"></span>'
                   '<span data-anchor-id="control:add_entry"></span>'
                   '<span data-anchor-id="nav:home->detail"></span>'
                   '<span data-anchor-id="req:REQ-003"></span>')
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(bad_html)
            path = f.name
        try:
            rc, out = self._run(path)
            self.assertEqual(rc, 1)
            self.assertIn("BLUEPRINT-STORYBOARD-LANES", out)
            self.assertIn("this journey was never approved", out)
        finally:
            os.unlink(path)

    # F2 (self-review): an HTML void element (e.g. <br>) inside a journey lane must not leak the
    # lane buffer past its real closing tag — the void element is closed immediately, not pushed
    # onto the tag stack unclosed. The manifest's journey text is "I tap Add entry, the app opens
    # the form"; splitting it across a <br> right after the existing space must still concatenate
    # to the exact verbatim string and PASS clean (no false P1 anywhere).
    def test_void_element_inside_lane_parses_verbatim(self):
        import hashlib as _hashlib
        lock_hash = _hashlib.sha256(Path(fix("blueprint_good_packet")).joinpath(
            "ui-locks", "home.lock.yaml").read_bytes()).hexdigest()
        good_html = ('<section data-storyboard-frame="home">h</section>'
                   '<section data-storyboard-frame="detail">d</section>'
                   '<div data-storyboard-edge="home->detail"></div>'
                   '<p data-journey-lane="1">I tap Add entry, <br>the app opens the form</p>'
                   '<p data-journey-lane="1">money rounds the same everywhere</p>'
                   f'<iframe data-proto-src="ui-locks/home.lock.yaml" data-proto-src-hash="{lock_hash}"></iframe>'
                   '<span data-anchor-id="req:REQ-001"></span>'
                   '<span data-anchor-id="req:REQ-002"></span>'
                   '<span data-anchor-id="control:add_entry"></span>'
                   '<span data-anchor-id="nav:home->detail"></span>'
                   '<span data-anchor-id="req:REQ-003"></span>')
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(good_html)
            path = f.name
        try:
            rc, out = self._run(path)
            self.assertEqual(rc, 0, f"Expected PASS (verbatim match across <br>), got:\n{out}")
            self.assertIn("PASS", out)
        finally:
            os.unlink(path)


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


class KaizenChecksRound2(unittest.TestCase):
    """PBF-PROP-021 group-2 hole #6/#7: fence-tolerance + status enum validation.

    PRE-FIX PROOF (verified interactively before this fix landed): all 3 bad fixtures below
    returned PASS exit 0 on the pre-fix code — the trailing-space and exotic-tag fences made
    the whole PROP block vanish with zero finding, and the case-drifted status silently read
    as "not applied" and skipped the enforcement clause.
    """

    _CONTRACTS = str(CHECKERS_DIR / "check-contracts.yaml")

    def test_fence_trailing_space_still_parsed(self):
        """A ```yaml<space> fence is still parsed — the missing-enforcement P0 still fires."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_fence_trailing_space.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT", out)

    def test_fence_exotic_tag_prop_shaped_fires_loud(self):
        """An unrecognized-tag fence with PROP-shaped text fires KAIZEN-FENCE-PROP-SHAPED-UNPARSEABLE."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_fence_exotic_tag_prop_shaped.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-FENCE-PROP-SHAPED-UNPARSEABLE", out)

    def test_status_case_drift_enum_validated_and_still_enforced(self):
        """status: applied (lowercase) fires KAIZEN-STATUS-ENUM-VALID AND is still treated as
        APPLIED — the missing-enforcement P0 must ALSO fire, not be silently skipped."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_bad_status_case_drift.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 1, f"Expected FIX-FIRST, got {rc}.\n{out}")
        self.assertIn("FIX-FIRST", out)
        self.assertIn("KAIZEN-STATUS-ENUM-VALID", out)
        self.assertIn("KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT", out)

    def test_good_queue_unaffected(self):
        """The existing good fixture is untouched by the fence/status hardening."""
        rc, out = run_cx("check", "kaizen", fix("kaizen_good.md"),
                         "--contracts", self._CONTRACTS)
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")
        self.assertIn("PASS", out)


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


class TestCheckAuditTierGated(unittest.TestCase):
    """PBF-PROP-019 Phase 3 (design v2.B row 1): LITE drops the SEPARATE formal Audit-STAGE
    entry requirement; STANDARD/STRICT unchanged. If an audit_dir IS present under LITE, it is
    still judged in full (proven by test_good_audit_passes / test_no_receipt_fails_entry_required
    above, which pass no packet_dir and so default STRICT — unaffected by this class)."""

    def test_no_receipt_strict_state_still_fails_entry_required(self):
        rc, out = run_cx("check", "audit", fix("as_no_audit_receipt"), "--state", fix("audit_state_good.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("AUDIT-STAGE-ENTRY-REQUIRED", out)

    def test_no_receipt_lite_state_drops_entry_required(self):
        rc, out = run_cx("check", "audit", fix("as_no_audit_receipt"), "--state", fix("audit_state_good_lite.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS (LITE drops the entry requirement), got {rc}.\n{out}")

    def test_good_audit_present_still_judged_in_full_under_lite(self):
        """A light audit report DOES exist under LITE — facts/hard-rules are never suppressed,
        it is judged exactly like the STANDARD/STRICT case (as_good already passes both ways)."""
        rc, out = run_cx("check", "audit", fix("audit_good"), "--state", fix("audit_state_good_lite.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_bad_report_present_under_lite_still_fails(self):
        """A present-but-broken audit report under LITE still fails its real findings (N/A
        derivation is never relaxed by tier)."""
        rc, out = run_cx("check", "audit", fix("as_na_no_fact"), "--state", fix("audit_state_good_lite.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("AUDIT-STAGE-APPLICABILITY-DERIVED", out)


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


class TestCheckFinalReadyTierGated(unittest.TestCase):
    """PBF-PROP-019 Phase 3 (design v2.B row 1 + v2.C, CEO ruling 2026-07-05 Option A):
    audit_stage_final and final_cross_family_receipt both relax under a pure-LITE build with
    zero high-risk cards fired; STANDARD/STRICT are unchanged; a high-risk card fired during a
    LITE build still requires the final_cross_family_receipt (invariant c)."""

    def test_pure_lite_no_fcf_no_audit_stage_passes(self):
        # P0-2 FIX: high_risk_card_fired is now recomputed from the build's real cards
        # (fail-closed if unresolvable) rather than a proxy field, so the legitimate
        # pure-LITE fast path must point at a real cards-dir whose cards are all clean.
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready_lite_no_fcf.yaml"),
                         "--cards-dir", fix("final_ready_cards_lite_clean"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_strict_same_omissions_blocks_both(self):
        rc, out = run_cx("check", "final-ready", fix("state_bad_final_ready_strict_no_fcf.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("final_cross_family_receipt missing", out)
        self.assertIn("AUDIT-STAGE-FINAL-READY-CHAIN", out)

    def test_lite_high_risk_fired_still_requires_fcf(self):
        rc, out = run_cx("check", "final-ready", fix("state_bad_final_ready_lite_high_risk_fired_no_fcf.yaml"))
        self.assertEqual(rc, 1, out)
        self.assertIn("final_cross_family_receipt missing", out)

    def test_spine_blocking_never_tier_gated(self):
        """CRITICAL invariant: the open-findings spine block is NEVER tier-conditional — a
        state with an open P0/finding still blocks final-ready regardless of risk_tier."""
        rc, out = run_cx("check", "final-ready", fix("state_bad_final_ready.yaml"))
        self.assertEqual(rc, 1, out)


class TestFinalReadyHighRiskCardRecompute(unittest.TestCase):
    """PBF-PROP-019 P0-2 FIX (GPT-5.5 xhigh codex 019f32cb cross-family finding): the OLD
    high_risk_card_fired = bool(state.foundation_checkpoints_passed) proxy was UNSOUND — a
    TERMINAL high-risk card (no dependents) passes `cx check card` per PB-PROP-002(b)
    (cx_card.py:1072) WITHOUT ever populating foundation_checkpoints_passed (only a DEPENDENT
    card's check reads that field, cx_card.py:1080), so a LITE build containing exactly that
    shape reached final-ready with zero cross-family review. Fixed: cx_final_ready now
    recomputes high_risk_card_fired by enumerating the build's real compiled cards
    (--cards-dir, or the conventional <repo-root>/cards) and calling card_high_risk() on each
    — fail-closed (True) whenever the cards cannot be positively enumerated."""

    STATE = "state_good_final_ready_lite_no_fcf.yaml"  # LITE, no fcf, no foundation_checkpoints_passed

    def test_terminal_high_risk_card_forces_fcf_even_with_no_checkpoint(self):
        """THE reproduction: the SAME LITE state as the positive control below (no
        foundation_checkpoints_passed at all — the exact case the old proxy read as False),
        but the real cards-dir contains one TERMINAL high-risk card. Must now FAIL requiring
        the final cross-family receipt."""
        rc, out = run_cx("check", "final-ready", fix(self.STATE),
                         "--cards-dir", fix("final_ready_cards_terminal_high_risk"))
        self.assertEqual(rc, 1, out)
        self.assertIn("final_cross_family_receipt missing", out)

    def test_positive_control_all_clean_cards_pure_lite_passes(self):
        """Positive control: the SAME LITE state, cards enumerated successfully, all
        non-high-risk — the legitimate pure-LITE self-review-only ship path still works."""
        rc, out = run_cx("check", "final-ready", fix(self.STATE),
                         "--cards-dir", fix("final_ready_cards_lite_clean"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_cards_dir_nonexistent_fails_closed(self):
        """'Can't tell' must never relax the gate: an explicit --cards-dir that does not
        exist cannot be enumerated -> high_risk_card_fired=True -> receipt required."""
        rc, out = run_cx("check", "final-ready", fix(self.STATE),
                         "--cards-dir", fix("final_ready_cards_does_not_exist"))
        self.assertEqual(rc, 1, out)
        self.assertIn("final_cross_family_receipt missing", out)

    def test_cards_dir_empty_fails_closed(self):
        """Zero cards found where cards were expected is itself an anomaly — fail closed,
        never silently treated as 'nothing risky happened'."""
        with tempfile.TemporaryDirectory() as t:
            rc, out = run_cx("check", "final-ready", fix(self.STATE), "--cards-dir", t)
            self.assertEqual(rc, 1, out)
            self.assertIn("final_cross_family_receipt missing", out)

    def test_no_cards_dir_at_all_fails_closed(self):
        """No --cards-dir and no --repo-root -> no conventional cards dir discoverable ->
        fail closed (the P0-2 fix's default posture; mirrors
        test_lite_high_risk_fired_still_requires_fcf's existing coverage)."""
        rc, out = run_cx("check", "final-ready", fix(self.STATE))
        self.assertEqual(rc, 1, out)
        self.assertIn("final_cross_family_receipt missing", out)

    def test_nonshaped_yaml_dir_fails_closed(self):
        """Re-sweep hole (GPT-5.5 codex 019f32f9): a NON-EMPTY --cards-dir of YAML that are
        NOT shaped cards (no security_tripwire mapping — e.g. a packet dir wrongly supplied)
        must fail closed. Before the shape guard, card_high_risk() returned False on every
        tripwire-less file and the whole dir read as 'all clean' (unsafe False)."""
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "not-a-card.yaml").write_text(
                "id: something\nmode: BUILD\nsome_field: value\n", encoding="utf-8")
            rc, out = run_cx("check", "final-ready", fix(self.STATE), "--cards-dir", t)
            self.assertEqual(rc, 1, out)
            self.assertIn("final_cross_family_receipt missing", out)


class TestCheckPacketSopCoverageMap(unittest.TestCase):
    """cx check packet — SOP-BIND-COVERAGE-MAP clause (PBAF-PROP-001 Lever B)."""

    def test_good_packet_passes(self):
        rc, out = run_cx("check", "packet", fix("packet_good"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_missing_sop_coverage_map_fails(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_no_sop_coverage_map"))
        self.assertEqual(rc, 1)
        self.assertIn("SOP-BIND-COVERAGE-MAP", out)


class TestAcceptedSurface(unittest.TestCase):
    """PBF-PROP-018: the preserve-posture gate. In-process unit tests of the pure validators
    (extractor + shape/coverage logic) — the full git-recompute path is exercised by the
    contract-bite fixtures (run_contracts.py, ACCEPTED-SURFACE-* clauses)."""

    def setUp(self):
        import cx_accepted_surface as cas
        self.cas = cas

    def test_extract_capabilities_finds_every_kind(self):
        text = (
            '{% extends "base.html" %}\n'
            '{% include "cowork/_ask_pane.html" %}\n'
            '<script src="app.js"></script>\n'
            '<script>function navSwipe() { return 1; }</script>\n'
            '<link rel="stylesheet" href="trans.css">\n'
            '<div data-fn="submit"></div>\n'
            '<button onclick="doThing()">x</button>\n'
            '<a href="/trans?lang=en">EN</a>\n'
        )
        caps = self.cas.extract_capabilities(text)
        self.assertIn("extends:base.html", caps)
        self.assertIn("include:cowork/_ask_pane.html", caps)
        self.assertIn("script:app.js", caps)
        self.assertIn("script-fn:navSwipe", caps)
        self.assertIn("stylesheet:trans.css", caps)
        self.assertIn("data-fn:submit", caps)
        self.assertIn("handler:onclick", caps)
        self.assertIn("link-query:/trans?lang=en", caps)

    def test_manifest_required_bites_with_no_contract_or_anchor(self):
        card = {"mode": "MODULE_BUILD", "allowed_files": ["a.html"],
                "allowed_operations": ["delete-killed-partials"]}
        manifest = {"module_id": "m1", "owned_files": ["a.html"], "shared_files": []}
        findings = self.cas.validate_manifest_required(card, [(manifest, "m1.yaml")], "card.yaml")
        self.assertTrue(any("ACCEPTED-SURFACE-MANIFEST-REQUIRED" in msg for _, _, msg in findings))

    def test_manifest_required_passes_with_defect_repair_fix_anchor(self):
        # built-code xfam P2-1: the anchor alone is enough ONLY for repair-shaped deviation classes
        card = {"mode": "FIX", "deviation_class": "RESTORE", "allowed_files": ["a.html"],
                "allowed_operations": ["delete-killed-partials"],
                "lock_anchor_ref": {"card_id": "BUILD-001"}}
        manifest = {"module_id": "m1", "owned_files": ["a.html"], "shared_files": []}
        findings = self.cas.validate_manifest_required(card, [(manifest, "m1.yaml")], "card.yaml")
        self.assertEqual(findings, [])

    def test_manifest_required_fix_anchor_insufficient_for_new_locked_scope(self):
        card = {"mode": "FIX", "deviation_class": "RESTORE", "new_locked_scope": True,
                "allowed_files": ["a.html"],
                "allowed_operations": ["delete-killed-partials"],
                "lock_anchor_ref": {"card_id": "BUILD-001"}}
        manifest = {"module_id": "m1", "owned_files": ["a.html"], "shared_files": []}
        findings = self.cas.validate_manifest_required(card, [(manifest, "m1.yaml")], "card.yaml")
        self.assertTrue(any("ACCEPTED-SURFACE-MANIFEST-REQUIRED" in msg for _, _, msg in findings))

    def test_manifest_required_fix_scope_change_needs_contract(self):
        # built-code xfam P2-1: SCOPE_CHANGE (or a missing deviation_class) is new scope on the
        # surface — the anchor alone must NOT satisfy the gate.
        for dc in ("SCOPE_CHANGE", ""):
            card = {"mode": "FIX", "deviation_class": dc, "allowed_files": ["a.html"],
                    "allowed_operations": ["delete-killed-partials"],
                    "lock_anchor_ref": {"card_id": "BUILD-001"}}
            manifest = {"module_id": "m1", "owned_files": ["a.html"], "shared_files": []}
            findings = self.cas.validate_manifest_required(card, [(manifest, "m1.yaml")], "card.yaml")
            self.assertTrue(any("ACCEPTED-SURFACE-MANIFEST-REQUIRED" in msg for _, _, msg in findings),
                            f"deviation_class={dc!r} must not ride the anchor alone")

    def test_legacy_fails_closed_on_unmanifested_screen_file(self):
        card = {"allowed_files": ["orphan_shell.html"],
                "allowed_operations": ["delete-killed-partials"]}
        findings = self.cas.validate_legacy_fails_closed(card, [], "card.yaml")
        self.assertTrue(any("ACCEPTED-SURFACE-LEGACY-FAILS-CLOSED" in msg for _, _, msg in findings))

    def test_regression_receipt_honesty_bound_bites(self):
        card = {"preserve_contract": {"accepted_surface_regression_receipt": {
            "baseline_sha": "a" * 40, "full_suite_command": "pytest", "baseline_log_hash": "x",
            "post_change_log_hash": "x", "diff_summary": "none", "generated_by": "test",
            "declared_regressions": ["something broke"]}}}
        findings = self.cas.validate_regression_receipt(card, [], "card.yaml")
        self.assertTrue(any("contradicts itself" in msg for _, _, msg in findings))

    def test_regression_receipt_narrow_command_bites(self):
        # built-code xfam P1-3: the receipt's command must equal the CONFIGURED full-suite command
        card = {"full_suite_command": "pytest tests/",
                "preserve_contract": {"accepted_surface_regression_receipt": {
                    "baseline_sha": "a" * 40,
                    "full_suite_command": "pytest tests/nav/test_one.py",
                    "baseline_log_hash": "x", "post_change_log_hash": "y",
                    "baseline_log_ref": "logs/b.log", "post_change_log_ref": "logs/p.log",
                    "diff_summary": "none", "generated_by": "test"}}}
        findings = self.cas.validate_regression_receipt(card, [], "card.yaml")
        self.assertTrue(any("does not match the configured full-suite command" in msg
                            for _, _, msg in findings))

    def test_regression_receipt_no_configured_command_fails_closed(self):
        card = {"preserve_contract": {"accepted_surface_regression_receipt": {
            "baseline_sha": "a" * 40, "full_suite_command": "pytest tests/",
            "baseline_log_hash": "x", "post_change_log_hash": "y",
            "baseline_log_ref": "logs/b.log", "post_change_log_ref": "logs/p.log",
            "diff_summary": "none", "generated_by": "test"}}}
        findings = self.cas.validate_regression_receipt(card, [], "card.yaml")
        self.assertTrue(any("no configured full-suite command" in msg for _, _, msg in findings))

    def test_extract_capabilities_variant_forms(self):
        # built-code xfam P1-1: attr order, spaced attributes, class/window dispatchers,
        # addEventListener — all must extract.
        text = (
            '<link href="trans.css" rel="stylesheet">\n'
            '<div data-fn = "submit"></div>\n'
            '<script>\n'
            'class NavSwipe { constructor() {} }\n'
            'window.NavSwipe = new NavSwipe();\n'
            'document.addEventListener("touchstart", h);\n'
            '</script>\n'
        )
        caps = self.cas.extract_capabilities(text)
        self.assertIn("stylesheet:trans.css", caps)
        self.assertIn("data-fn:submit", caps)
        self.assertIn("js-class:NavSwipe", caps)
        self.assertIn("js-global:NavSwipe", caps)
        self.assertIn("js-listener:addEventListener", caps)

    def test_drop_ref_fails_closed_without_ledger(self):
        # built-code xfam P1-2: no readable ledger → a drop ref fails CLOSED, never open
        card = {"allowed_files": [], "preserve_contract": {"inventory": [
            {"capability": "x", "extracted_from": {"commit": "a" * 40, "path": "a.html"},
             "dropped_ceo_decision_ref": "CEO-D-001"}]}}
        findings = self.cas.validate_inventory_extracted(
            card, [], "card.yaml", ledger_ids=None, ledger_available=False)
        self.assertTrue(any("fails CLOSED" in msg for _, _, msg in findings))

    def test_drop_ref_dangling_bites_resolved_passes(self):
        card = {"allowed_files": [], "preserve_contract": {"inventory": [
            {"capability": "x", "extracted_from": {"commit": "a" * 40, "path": "a.html"},
             "dropped_ceo_decision_ref": "CEO-D-999"}]}}
        findings = self.cas.validate_inventory_extracted(
            card, [], "card.yaml", ledger_ids={"CEO-D-001"}, ledger_available=True)
        self.assertTrue(any("not found in the decision ledger" in msg for _, _, msg in findings))
        findings_ok = self.cas.validate_inventory_extracted(
            card, [], "card.yaml", ledger_ids={"CEO-D-999"}, ledger_available=True)
        self.assertEqual(findings_ok, [])

    def test_shared_coverage_bites_when_one_owner_omitted(self):
        card = {"allowed_files": ["shared.html"],
                "preserve_contract": {"accepted_surfaces": ["m1"]}}
        m1 = {"module_id": "m1", "owned_files": [], "shared_files": ["shared.html"]}
        m2 = {"module_id": "m2", "owned_files": [], "shared_files": ["shared.html"]}
        findings = self.cas.validate_shared_surface_coverage(
            card, [(m1, "m1.yaml"), (m2, "m2.yaml")], "card.yaml")
        self.assertTrue(any("SHARED accepted-surface file" in msg for _, _, msg in findings))


# ---------------------------------------------------------------------------
# PBF-PROP-020 — Mockup-First Change Rule (v2, fail-closed-by-default)
# ---------------------------------------------------------------------------
class TestPBFPROP020MockupFirst(unittest.TestCase):
    def test_rule3_lock_acceptance_no_chosen_from_bites(self):
        rc, out = run_cx("check", "design-fidelity",
                         "--manifest", fix("ui_lock_manifest_bad_no_chosen_from.yaml"),
                         "--dom", fix("dom_good.html"),
                         "--screenshot", fix("screenshot_good.png"))
        self.assertEqual(rc, 1)
        self.assertIn("[P1]", out)
        self.assertIn("LOCK-ACCEPTANCE-CITES-RENDERED", out)

    def test_rule3_lock_acceptance_good_passes(self):
        rc, out = run_cx("check", "design-fidelity",
                         "--manifest", fix("ui_lock_manifest_good.yaml"),
                         "--dom", fix("dom_good.html"),
                         "--screenshot", fix("screenshot_good.png"),
                         "--build-vocab", fix("build_vocab_good.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_rule4_module_demo_no_diff_receipt_bites(self):
        rc, out = run_cx("check", "module-demo",
                         "--acceptance", fix("module_demo_no_diff_receipt.yaml"),
                         "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("PRESENTED-VISUAL-HAS-DIFF-RECEIPT", out)

    def test_rule4_module_demo_good_passes(self):
        rc, out = run_cx("check", "module-demo",
                         "--acceptance", fix("module_acceptance_live_slice_good.yaml"),
                         "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_rule4_module_demo_full_omission_bites(self):
        """FOLD RE-SWEEP FIX (WAVE-TRIGGERED): a live_slice acceptance that OMITS the diff receipt
        ENTIRELY (no mockup_ref/mockup_hash/diff_score/tolerance) must fail closed — pre-fix the
        field-triggered check let a full omission pass, the new-work dodge the extra sweep caught."""
        rc, out = run_cx("check", "module-demo",
                         "--acceptance", fix("module_demo_full_omission_no_diff.yaml"),
                         "--repo-root", str(FIXTURES))
        self.assertEqual(rc, 1)
        self.assertIn("PRESENTED-VISUAL-HAS-DIFF-RECEIPT", out)

    def test_rule4_legacy_no_diff_carveout_is_advisory_not_blocking(self):
        """A GENUINE pre-020 live_slice acceptance with NO diff receipt but a typed
        legacy_no_diff_receipt carve-out is DEMOTED from the blocking P1 to a P2 advisory (migration
        debt). P2 is non-blocking at the real acceptance walls (has_blocking = {P0, P1}); the
        standalone module-demo diagnostic still surfaces it, so we assert the SEVERITY demotion."""
        rc, out = run_cx("check", "module-demo",
                         "--acceptance", fix("module_demo_legacy_no_diff_carveout.yaml"),
                         "--repo-root", str(FIXTURES))
        self.assertIn("[P2]", out, out)
        self.assertIn("legacy_no_diff_receipt", out)
        self.assertNotIn("PRESENTED-VISUAL-HAS-DIFF-RECEIPT", out,
                         f"the carve-out demotes to advisory — the blocking P1 clause must not fire.\n{out}")

    def test_rule6a_two_live_locks_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_two_live_locks"))
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("ONE-LIVE-LOCK-PER-SCREEN", out)

    def test_rule6a_one_live_lock_good_passes(self):
        rc, out = run_cx("check", "packet", fix("packet_good_one_live_lock"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_rule5_rule_conflict_no_resolution_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_rule_conflict_no_resolution"))
        self.assertEqual(rc, 1)
        self.assertIn("RULE-CONFLICT-IS-OPEN-CLARIFICATION", out)

    def test_rule5_rule_conflict_resolved_good_passes(self):
        rc, out = run_cx("check", "packet", fix("packet_good_rule_conflict_resolved"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_rule6b_interactive_chrome_no_contract_bites(self):
        rc, out = run_cx("check", "blueprint", fix("blueprint_bad_chrome_no_behavior_contract"),
                         "--module", "home", "--state", fix("blueprint_good_state.yaml"),
                         "--approval", fix("blueprint_bad_chrome_no_behavior_contract_approval.yaml"))
        self.assertEqual(rc, 1)
        self.assertIn("INTERACTIVE-CHROME-HAS-BEHAVIOR-CONTRACT", out)

    def test_rule6b_interactive_chrome_with_contract_good_passes(self):
        rc, out = run_cx("check", "blueprint", fix("blueprint_good_chrome_with_contract"),
                         "--module", "home", "--state", fix("blueprint_good_state.yaml"),
                         "--approval", fix("blueprint_good_chrome_approval.yaml"))
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    _RULE1_STATE = fix("prop020_rule1_repo/state.yaml")

    def test_rule1_prose_only_ui_change_bites(self):
        rc, out = run_cx("check", "card", fix("card_bad_ui_change_prose_only.yaml"),
                         "--state", self._RULE1_STATE)
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("MOCKUP-FIRST-CHANGE-NEEDS-LOCK", out)

    def test_rule1_registry_lock_good_passes(self):
        rc, out = run_cx("check", "card", fix("card_good_ui_change_with_registry_lock.yaml"),
                         "--state", self._RULE1_STATE)
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_rule1_restore_fix_exempt_good_passes(self):
        rc, out = run_cx("check", "card", fix("card_good_restore_fix.yaml"),
                         "--state", self._RULE1_STATE)
        self.assertEqual(rc, 0, f"Expected PASS, got {rc}.\n{out}")

    def test_rule1_ui_change_no_render_bundle_bites(self):
        """FOLD RE-SWEEP FIX (CITE-AND-COMPARE): a UI card with a VALID registry lock_ref but NO
        render_bundle must fail closed — the lock is referenced but never rendered against, the
        fail-open dodge (build-turn marks render-fidelity NOT_APPLICABLE) the extra sweep caught."""
        rc, out = run_cx("check", "card", fix("card_bad_ui_change_no_render_bundle.yaml"),
                         "--state", self._RULE1_STATE)
        self.assertEqual(rc, 1)
        self.assertIn("[P0]", out)
        self.assertIn("no render_bundle", out)
        self.assertIn("MOCKUP-FIRST-CHANGE-NEEDS-LOCK", out)


class TestPBFPROP020GitTouchedScope(unittest.TestCase):
    """PBF-PROP-020 Rules 2 & 7 — the git-touched CEO-visible screen scope. These need a REAL git
    repo (a diff vs repo_sha_before) + a MODULE-REGISTRY screen->files binding + a hash-bound lock
    with pictured_states, so — like the module-acceptance repo_sha_before tests — they are proven
    to BITE here rather than in the static contract-bite harness. Covered: each of the 3 clauses
    bites, plus the scoped-not-global posture (untouched screens stay advisory; no repo flags =
    the rules stay dormant; a fully-covered/pictured touched screen raises no false positive)."""

    def _repo(self, tmp, *, cover_home=True, pictured_state="populated", drift_screen=None,
              omit_repo_sha=False, legacy_carveout=None):
        """Build a temp git repo whose HEAD touches templates/home.html vs its baseline, a packet
        with a registry binding home->that file + a lock carrying pictured_states, and a render
        bundle. Returns (repo, packet_rel, bundle, head_sha). omit_repo_sha drops repo_sha_before
        from the bundle (the fold re-sweep fail-open probe); legacy_carveout adds a typed
        legacy_no_baseline marker (the explicit pre-020 grandfather)."""
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
                "  frozen_packet_hash: p020-r2r7-fixture\n"
                "  modules:\n"
                "    - module_id: m_home\n"
                "      screen_id: home\n"
                "      kind: screen\n"
                "      files: [templates/home.html]\n"
                "      lock_ref: packet/locks/home.lock.yaml\n"
                "      requirement_ids: []\n"
                "      dependency_modules: []\n"
                "      card_ids: [BUILD-1]\n")
        covered_screen = "home" if cover_home else "other"
        lines = []
        if not omit_repo_sha:
            lines.append(f"repo_sha_before: {base[:12]}")
        if legacy_carveout:
            lines.append(f"legacy_no_baseline: {legacy_carveout}")
        lines += [
            "coverage_matrix:",
            "  ui_card: true",
            "  required_rows:",
            f"    - screen_id: {covered_screen}",
            "      viewport_id: phone",
            "      theme: light",
            "      content_state: populated",
        ]
        if drift_screen:
            lines += [
                "golden_drift:",
                f"  - screen_id: {drift_screen}",
                "    viewport_id: phone",
                "    diff_score: 0.9",
                "    tolerance: 0.1",
                "    baseline_ref: baseline-shot",
            ]
        bundle = os.path.join(tmp, "bundle.yaml")
        with open(bundle, "w") as f:
            f.write("\n".join(lines) + "\n")
        return repo, "packet", bundle, head

    def test_render_covers_git_touched_bites(self):
        """home is git-touched but omitted from required_rows => RENDER-COVERS-GIT-TOUCHED P0."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkt, bundle, head = self._repo(tmp, cover_home=False)
            rc, out = run_cx("check", "render-fidelity", bundle,
                             "--repo-root", repo, "--packet-dir", pkt, "--repo-head", head)
            self.assertIn("RENDER-COVERS-GIT-TOUCHED", out, out)
            self.assertNotEqual(rc, 0, f"a touched-but-omitted screen must fail closed.\n{out}")

    def test_unpictured_state_is_gap_bites(self):
        """home touched & covered as 'populated' but the lock pictures only 'empty' =>
        UNPICTURED-STATE-IS-GAP P0."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkt, bundle, head = self._repo(tmp, cover_home=True, pictured_state="empty")
            rc, out = run_cx("check", "render-fidelity", bundle,
                             "--repo-root", repo, "--packet-dir", pkt, "--repo-head", head)
            self.assertIn("UNPICTURED-STATE-IS-GAP", out, out)
            self.assertNotEqual(rc, 0, out)

    def test_golden_drift_blocks_touched_bites(self):
        """a golden_drift over tolerance on the git-touched screen => GOLDEN-DRIFT-BLOCKS-TOUCHED P1."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkt, bundle, head = self._repo(tmp, cover_home=True, drift_screen="home")
            rc, out = run_cx("check", "render-fidelity", bundle,
                             "--repo-root", repo, "--packet-dir", pkt, "--repo-head", head)
            self.assertIn("GOLDEN-DRIFT-BLOCKS-TOUCHED", out, out)
            self.assertNotEqual(rc, 0, out)

    def test_golden_drift_untouched_stays_advisory(self):
        """a golden_drift over tolerance on an UNtouched screen stays advisory WARN — the flip is
        scoped to touched screens, never global (the bloat the CEO refused)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkt, bundle, head = self._repo(tmp, cover_home=True, drift_screen="other")
            rc, out = run_cx("check", "render-fidelity", bundle,
                             "--repo-root", repo, "--packet-dir", pkt, "--repo-head", head)
            self.assertNotIn("GOLDEN-DRIFT-BLOCKS-TOUCHED", out, out)

    def test_rules_2_7_dormant_without_repo_flags(self):
        """without --repo-root/--packet-dir the git-touched scope is unresolved => Rules 2/7 do NOT
        apply (scoped-not-global); none of the 3 clauses fire."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkt, bundle, head = self._repo(tmp, cover_home=False, drift_screen="home")
            rc, out = run_cx("check", "render-fidelity", bundle, "--repo-head", "aaaaaaaaaaaa")
            for clause in ("RENDER-COVERS-GIT-TOUCHED", "UNPICTURED-STATE-IS-GAP",
                           "GOLDEN-DRIFT-BLOCKS-TOUCHED"):
                self.assertNotIn(clause, out, f"{clause} must be dormant without repo flags.\n{out}")

    def test_touched_covered_pictured_no_020_finding(self):
        """home touched, covered, pictured 'populated', drift under tolerance => none of the 3
        Rule 2/7 clauses fire (no false-positive)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkt, bundle, head = self._repo(tmp, cover_home=True, pictured_state="populated")
            rc, out = run_cx("check", "render-fidelity", bundle,
                             "--repo-root", repo, "--packet-dir", pkt, "--repo-head", head)
            for clause in ("RENDER-COVERS-GIT-TOUCHED", "UNPICTURED-STATE-IS-GAP",
                           "GOLDEN-DRIFT-BLOCKS-TOUCHED"):
                self.assertNotIn(clause, out, f"{clause} false-positived.\n{out}")

    def test_missing_repo_sha_before_fails_closed(self):
        """FOLD RE-SWEEP FIX: repo/packet flags SUPPLIED but the bundle OMITS repo_sha_before must
        fail CLOSED — omission can no longer make Rules 2/7 go silently dormant (the fail-open
        new-work dodge the extra xfam sweep caught). Home IS git-touched but omitted from coverage;
        pre-fix this returned None (no finding), so the touched-but-omitted screen shipped green."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkt, bundle, head = self._repo(tmp, cover_home=False, omit_repo_sha=True)
            rc, out = run_cx("check", "render-fidelity", bundle,
                             "--repo-root", repo, "--packet-dir", pkt, "--repo-head", head)
            self.assertIn("no repo_sha_before", out, out)
            self.assertNotEqual(rc, 0, f"a bundle with repo flags but no repo_sha_before must fail "
                                       f"closed, not go dormant.\n{out}")

    def test_legacy_no_baseline_carveout_stays_dormant(self):
        """A GENUINE pre-020 bundle declares the typed legacy_no_baseline carve-out — Rules 2/7 stay
        dormant (advisory WARN, migration debt), never a blocking finding. This is the ONLY way to
        omit repo_sha_before with the flags supplied; an untyped omission is the P0 above."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, pkt, bundle, head = self._repo(tmp, cover_home=False, omit_repo_sha=True,
                                                 legacy_carveout="pre-020-migration-debt")
            rc, out = run_cx("check", "render-fidelity", bundle,
                             "--repo-root", repo, "--packet-dir", pkt, "--repo-head", head)
            self.assertIn("legacy_no_baseline", out, out)
            self.assertNotIn("RENDER-COVERS-GIT-TOUCHED", out,
                             f"a typed pre-020 carve-out must keep Rules 2/7 dormant.\n{out}")


# ---------------------------------------------------------------------------
# PBF-PROP-019 Phase 5: EVAL-052 — LITE can't skip the SPINE
# ---------------------------------------------------------------------------
class TestEval052HighRiskForceAcrossAllTiers(unittest.TestCase):
    """EVAL-052 headline case: CARD-HIGH-RISK-FORCES-FOUNDATION (Phase 2, mechanical, never reads
    risk_tier) must reject the SAME high-risk/no-foundation-checkpoint card identically under all
    three declared tiers — LITE, STANDARD, and STRICT — proving the tier declaration itself has zero
    effect on this gate. STRICT already runs with no --state at all (TestCardHighRiskForcesFoundation
    above); this class adds the explicit LITE/STANDARD/STRICT --state triple."""

    _BAD = "card_bad_high_risk_no_foundation_checkpoint.yaml"

    def test_high_risk_no_checkpoint_fails_under_lite(self):
        rc, out = run_cx("check", "card", fix(self._BAD), "--state", fix("state_pbf019_lite.yaml"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("CARD-HIGH-RISK-FORCES-FOUNDATION", out, out)

    def test_high_risk_no_checkpoint_fails_under_standard(self):
        rc, out = run_cx("check", "card", fix(self._BAD), "--state", fix("state_pbf019_standard.yaml"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("CARD-HIGH-RISK-FORCES-FOUNDATION", out, out)

    def test_high_risk_no_checkpoint_fails_under_strict(self):
        rc, out = run_cx("check", "card", fix(self._BAD), "--state", fix("state_pbf019_strict.yaml"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("CARD-HIGH-RISK-FORCES-FOUNDATION", out, out)


class TestEval052GoodLiteRelaxesCeremonyOnly(unittest.TestCase):
    """EVAL-052 mirror case: a legitimate LITE fixture that drops BOTH ceremony rails Phase 3
    relaxes (CodeRabbit + same-family cross-review) simultaneously, while every SPINE field
    (source_map, module_id, card_compilation, security_tripwire) stays intact, PASSES clean under
    LITE and fails BOTH relaxed gates under the STRICT default — proving LITE relaxes ceremony
    without ever touching the spine."""

    _CARD = "card_good_lite_relaxed_ceremony.yaml"

    def test_strict_default_fails_both_relaxed_gates(self):
        rc, out = run_cx("check", "card", fix(self._CARD))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("CodeRabbit rail missing", out)
        self.assertIn("same-family cross-review REJECTED", out)

    def test_lite_passes_clean(self):
        rc, out = run_cx("check", "card", fix(self._CARD), "--state", fix("state_pbf019_lite.yaml"))
        self.assertEqual(rc, 0, out)


class TestEval052SpineGatesNeverReadRiskTier(unittest.TestCase):
    """EVAL-052: source-level proof that the remaining named spine gates — deck reverse coverage,
    the module-start frozen-packet-hash/order wall, scope/allowed-files, and dependency-scan — carry
    NO risk_tier branch at all, so no declared tier can possibly relax them (structurally, not just
    by absence of a failing test). Complements the concrete fixture-level proofs above (card spine
    fields, final-ready open-findings) with a mechanical guarantee against a future regression that
    silently threads risk_tier into one of these files."""

    _SPINE_MODULES = ["cx_deck.py", "cx_scope.py", "cx_dep_scan.py", "cx_module_start.py"]

    def test_spine_modules_never_reference_risk_tier(self):
        checkers_dir = Path(__file__).resolve().parent.parent
        for name in self._SPINE_MODULES:
            src = (checkers_dir / name).read_text(encoding="utf-8")
            self.assertNotIn("risk_tier", src,
                f"{name} must never read risk_tier — it is SPINE (PBF-PROP-019 EVAL-052)")

    def test_source_map_spine_still_fails_under_lite(self):
        """A concrete companion to the source-grep: the existing CARD-SOURCE-MAP-REQUIRED bad
        fixture still fails identically when a LITE-tier --state is supplied."""
        rc, out = run_cx("check", "card", fix("card_bad_missing_source_map.yaml"),
                         "--state", fix("state_pbf019_lite.yaml"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("missing source_map", out)

    def test_final_ready_open_findings_spine_still_fails_under_explicit_lite(self):
        """The final-ready open_findings block (cx_final_ready.py:64-79) never reads risk_tier_val —
        an explicit risk_tier: LITE packet_dir with an open P0 finding still blocks final-ready,
        identically to the tier-absent state_bad_final_ready.yaml case (EVAL-001)."""
        rc, out = run_cx("check", "final-ready", fix("state_bad_final_ready_lite_open_findings.yaml"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("open_findings.counts.p0=1", out)


# ---------------------------------------------------------------------------
# PBF-PROP-019: risk_tier resolver + packet validator (EVAL-052/053)
# ---------------------------------------------------------------------------
import cx_common  # noqa: E402


class TestRiskTierResolver(unittest.TestCase):
    """EVAL-053 — undeclared/unknown tier resolves STRICT; malformed also FAILS
    PACKET-RISK-TIER-WELL-FORMED at cx check packet. Positive control: explicit
    STRICT behaves identically to the absent case's resolution."""

    def test_absent_risk_tier_resolves_strict(self):
        self.assertEqual(cx_common.resolve_risk_tier(fix("packet_good")), "STRICT")

    def test_bogus_risk_tier_resolves_strict(self):
        # Resolver never raises / never returns anything but STRICT for a bad value —
        # the loud rejection is cx check packet's job (tested below), not the resolver's.
        self.assertEqual(cx_common.resolve_risk_tier(fix("packet_bad_risk_tier_invalid")), "STRICT")

    def test_explicit_strict_resolves_strict(self):
        self.assertEqual(cx_common.resolve_risk_tier(fix("packet_good_risk_tier_strict")), "STRICT")

    def test_declared_lite_resolves_lite(self):
        self.assertEqual(cx_common.resolve_risk_tier(fix("packet_good_risk_tier_lite")), "LITE")

    def test_missing_packet_dir_resolves_strict(self):
        self.assertEqual(cx_common.resolve_risk_tier(fix("no-such-packet-dir")), "STRICT")

    def test_bogus_tier_fails_packet_well_formed(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_risk_tier_invalid"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("PACKET-RISK-TIER-WELL-FORMED", out, out)

    def test_lite_without_ceo_ref_fails_packet_well_formed(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_risk_tier_lite_no_ref"))
        self.assertNotEqual(rc, 0, out)
        self.assertIn("PACKET-RISK-TIER-WELL-FORMED", out, out)

    def test_lite_with_resolving_ceo_ref_passes_packet(self):
        rc, out = run_cx("check", "packet", fix("packet_good_risk_tier_lite"))
        self.assertEqual(rc, 0, out)

    def test_explicit_strict_passes_packet_no_ref_needed(self):
        rc, out = run_cx("check", "packet", fix("packet_good_risk_tier_strict"))
        self.assertEqual(rc, 0, out)

    def test_absent_risk_tier_still_passes_packet(self):
        # Positive control: an undeclared tier is not itself a finding (absence -> STRICT
        # is proven by the resolver test above, not a written flag on the good fixture).
        rc, out = run_cx("check", "packet", fix("packet_good"))
        self.assertEqual(rc, 0, out)


# ---------------------------------------------------------------------------
# PBF-PROP-019 Phase 4: graduation hash-bound tier evidence + LITE streak exclusion
# ---------------------------------------------------------------------------
import hashlib as _hashlib  # noqa: E402
import cx_graduation  # noqa: E402


class TestGraduationTierEvidence(unittest.TestCase):
    """Unit-tests `_validate_tier_evidence` directly (in-process, mirrors the cx_blueprint/
    cx_common precedents above) — the FULL fail-closed direction is the OPPOSITE of
    cx_common.resolve_risk_tier's packet default: missing/unbindable/malformed tier evidence
    here REJECTS the entry (tier_ok=False, verified_tier=None), it is never defaulted to
    STRICT-and-counted. The CLI-level bite (P0 GRADUATION-TIER-EVIDENCE-REQUIRED under
    --authorize-decision) is proven by the check-contracts.yaml GRADUATION-TIER-EVIDENCE-*
    clauses; this class proves the underlying helper's exact return contract."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.receipts_dir = Path(self._tmp.name)
        standard_bytes = b"resolved_risk_tier: STANDARD\n"
        lite_bytes = b"resolved_risk_tier: LITE\n"
        (self.receipts_dir / "tier-standard.yaml").write_bytes(standard_bytes)
        (self.receipts_dir / "tier-lite.yaml").write_bytes(lite_bytes)
        self.standard_sha = _hashlib.sha256(standard_bytes).hexdigest()
        self.lite_sha = _hashlib.sha256(lite_bytes).hexdigest()
        self.manifest_files = {
            "tier-standard.yaml": self.standard_sha,
            "tier-lite.yaml": self.lite_sha,
        }

    def test_missing_risk_tier_field_rejected(self):
        entry = {"tier_evidence": {"receipt": "tier-standard.yaml", "receipt_sha256": self.standard_sha}}
        ok, tier, findings = cx_graduation._validate_tier_evidence(
            entry, True, self.manifest_files, self.receipts_dir, "proj-x", "loc")
        self.assertFalse(ok)
        self.assertIsNone(tier)
        self.assertTrue(any("GRADUATION-TIER-EVIDENCE-REQUIRED" in f[2] for f in findings), findings)

    def test_missing_tier_evidence_block_rejected(self):
        entry = {"risk_tier": "STANDARD"}
        ok, tier, findings = cx_graduation._validate_tier_evidence(
            entry, True, self.manifest_files, self.receipts_dir, "proj-x", "loc")
        self.assertFalse(ok)
        self.assertIsNone(tier)
        self.assertTrue(any("no 'tier_evidence' block" in f[2] for f in findings), findings)

    def test_unbound_receipt_hash_mismatch_rejected(self):
        entry = {"risk_tier": "STANDARD",
                  "tier_evidence": {"receipt": "tier-standard.yaml", "receipt_sha256": "f" * 64}}
        ok, tier, findings = cx_graduation._validate_tier_evidence(
            entry, True, self.manifest_files, self.receipts_dir, "proj-x", "loc")
        self.assertFalse(ok)
        self.assertIsNone(tier)
        self.assertTrue(any("absent from (or hash-mismatched in)" in f[2] for f in findings), findings)

    def test_standard_claim_over_lite_packet_receipt_rejected(self):
        # The LITE->STANDARD migration guard (design v2 P1-5): a declared STANDARD claim whose
        # bound receipt asserts the run was actually built LITE can never retroactively bank it.
        entry = {"risk_tier": "STANDARD",
                  "tier_evidence": {"receipt": "tier-lite.yaml", "receipt_sha256": self.lite_sha}}
        ok, tier, findings = cx_graduation._validate_tier_evidence(
            entry, True, self.manifest_files, self.receipts_dir, "proj-x", "loc")
        self.assertFalse(ok)
        self.assertIsNone(tier)
        self.assertTrue(any("cannot retroactively bank a run built under a lighter tier" in f[2]
                             for f in findings), findings)

    def test_well_formed_standard_verified(self):
        entry = {"risk_tier": "STANDARD",
                  "tier_evidence": {"receipt": "tier-standard.yaml", "receipt_sha256": self.standard_sha}}
        ok, tier, findings = cx_graduation._validate_tier_evidence(
            entry, True, self.manifest_files, self.receipts_dir, "proj-x", "loc")
        self.assertTrue(ok, findings)
        self.assertEqual(tier, "STANDARD")
        self.assertEqual(findings, [])

    def test_well_formed_lite_verified(self):
        entry = {"risk_tier": "LITE",
                  "tier_evidence": {"receipt": "tier-lite.yaml", "receipt_sha256": self.lite_sha}}
        ok, tier, findings = cx_graduation._validate_tier_evidence(
            entry, True, self.manifest_files, self.receipts_dir, "proj-x", "loc")
        self.assertTrue(ok, findings)
        self.assertEqual(tier, "LITE")
        self.assertEqual(findings, [])


class TestGraduationLiteStreakExclusion(unittest.TestCase):
    """Unit-tests `_recompute_streak`'s LITE-population filter directly: a verified-LITE entry
    is SKIPPED (neither counts nor resets), same mechanic as 'pending' (design v2 §5/P1-5)."""

    def _status(self, pid, is_clean, is_lite=False, is_pending=False, is_userfacing=True):
        return {"project_id": pid, "is_clean": is_clean, "is_userfacing": is_userfacing,
                "is_pending": is_pending, "is_lite": is_lite}

    def test_lite_interleaved_is_skipped_standard_streak_still_counts(self):
        # oldest->newest: w(clean) x(LITE, dirty if it were evaluated normally) y(clean) z(clean)
        statuses = [
            self._status("w", is_clean=True),
            self._status("x", is_clean=False, is_lite=True),
            self._status("y", is_clean=True),
            self._status("z", is_clean=True),
        ]
        streak, userfacing, per_project = cx_graduation._recompute_streak(statuses, Path("."), n=3, m=3)
        self.assertEqual(streak, 3, per_project)
        self.assertEqual(userfacing, 3, per_project)
        self.assertEqual(per_project["x"]["project_id"], "x")

    def test_same_shape_without_lite_flag_resets_streak(self):
        # Contrast control: same dirty-newest-minus-one shape, but x is NOT verified-lite ->
        # the old behaviour applies — counting stops at x, streak breaks at 2.
        statuses = [
            self._status("w", is_clean=True),
            self._status("x", is_clean=False, is_lite=False),
            self._status("y", is_clean=True),
            self._status("z", is_clean=True),
        ]
        streak, userfacing, per_project = cx_graduation._recompute_streak(statuses, Path("."), n=3, m=3)
        self.assertEqual(streak, 2, per_project)

    def test_lite_as_newest_neither_counts_nor_resets(self):
        statuses = [
            self._status("w", is_clean=True),
            self._status("y", is_clean=True),
            self._status("z", is_clean=True),
            self._status("newest-lite", is_clean=False, is_lite=True),
        ]
        streak, userfacing, per_project = cx_graduation._recompute_streak(statuses, Path("."), n=3, m=3)
        self.assertEqual(streak, 3, per_project)


if __name__ == "__main__":
    unittest.main()
