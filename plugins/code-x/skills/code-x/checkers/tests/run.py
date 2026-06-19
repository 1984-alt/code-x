#!/usr/bin/env python3
"""
run.py — plain Python test runner for the cx test suite.
Usage: python3 checkers/tests/run.py   (from Code-X-V1 root)
       python3 run.py                  (from checkers/tests/)

Converts pytest-style class+method tests to unittest and runs them.
Exit 0 = all pass, 1 = failures.
"""
import subprocess
import sys
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
        """A banned_negation phrase present in a shipping canon file must fire FIX-FIRST naming rule+file."""
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
class TestProtocolVersionIdentity(unittest.TestCase):
    def test_protocol_version_constant_is_1_12(self):
        """The checker constant must equal the shipping protocol version (v1.12) so cx identity
        can never silently lag the ledger again (VERSION-HISTORY current = v1.12)."""
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            import cx_common
            self.assertEqual(cx_common.PROTOCOL_VERSION, "1.12")
        finally:
            sys.path.pop(0)

    def test_cx_version_reports_1_12(self):
        """`cx --version` surfaces V1.12."""
        rc, out = run_cx("--version")
        self.assertEqual(rc, 0, f"Expected exit 0 from --version, got {rc}.\n{out}")
        self.assertIn("V1.12", out)


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
    "session_start": {"builder_standard_read": {
        "status": "PASS", "file": "BUILDER-STANDARD.md", "hash": "deadbeef0123",
        "read_by": "cx-test", "timestamp": "2026-06-10T00:00:00"}},
    # PROP-020: reviewer taxonomy/timing as typed state (required at session-start in build modes).
    "review_boundary": {
        "deterministic_checks_each_card": "yes",
        "coderabbit_before_self_review": "not_applicable",
        "self_review_boundary": "module",
        "cross_family_boundary": "module",
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
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main(verbosity=2)
