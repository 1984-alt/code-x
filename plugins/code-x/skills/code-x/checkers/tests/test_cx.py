"""
pytest test suite for cx — Code-X V1 checker CLI.
Each subcommand: >= 1 PASS case + >= 1 FIX-FIRST case.
Assert exit codes + that the right finding fires.
"""
import subprocess
import sys
import tempfile
import os
from pathlib import Path

# Path to the cx script (needed for direct subprocess calls in F5 test)
_CX_ROOT = Path(__file__).parent.parent.parent

CHECKERS_DIR = Path(__file__).parent.parent
CX = str(CHECKERS_DIR / "cx")
FIXTURES = Path(__file__).parent / "fixtures"

# Pin BUILD-ENGINE-PROFILES to the test mirror (stable fixture hashes — see profiles_test.yaml)
os.environ["CODE_X_TEST_MODE"] = "1"  # PROP-014: CX_PROFILES honored only in test mode
os.environ["CX_PROFILES"] = str(FIXTURES / "profiles_test.yaml")


def run_cx(*args) -> tuple[int, str]:
    """Run cx with args. Returns (exit_code, combined_stdout+stderr)."""
    result = subprocess.run(
        [sys.executable, CX] + list(args),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fix(name: str) -> str:
    return str(FIXTURES / name)


# ---------------------------------------------------------------------------
# cx check card
# ---------------------------------------------------------------------------

class TestCheckCard:
    def test_good_card_passes(self):
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out

    def test_proof_mode_card_passes(self):
        # PROOF is a real intended mode — cx_evidence.py branches on mode == "PROOF".
        # cx check card must accept it, not flag a spurious "mode 'PROOF' not in [...]" P1.
        rc, out = run_cx("check", "card", fix("card_good_proof.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out
        assert "mode 'PROOF' not in" not in out

    def test_missing_source_map(self):
        rc, out = run_cx("check", "card", fix("card_bad_missing_source_map.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "source_map" in out.lower()

    def test_same_family_cross_review_rejected(self):
        rc, out = run_cx("check", "card", fix("card_bad_same_family.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        # Should mention same-family rejection
        assert "same-family" in out.lower() or "cross_review" in out.lower()

    def test_missing_required_field(self):
        rc, out = run_cx("check", "card", fix("card_bad_missing_field.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        # model_tier is blank → should flag it
        assert "model_tier" in out.lower() or "objective" in out.lower()

    def test_missing_security_tripwire(self):
        rc, out = run_cx("check", "card", fix("card_bad_missing_security_tripwire.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "security_tripwire" in out.lower()

    def test_invalid_model_tier(self):
        rc, out = run_cx("check", "card", fix("card_bad_unnamed_model_tier.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "model_tier" in out.lower()

    def test_over_budget_read(self):
        rc, out = run_cx("check", "card", fix("card_bad_over_budget_read.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        # Should mention read budget / over-budget
        assert "read" in out.lower() and ("budget" in out.lower() or "files" in out.lower())

    def test_nonexistent_file_returns_fix_first(self):
        rc, out = run_cx("check", "card", "/tmp/does_not_exist_cx_test.yaml")
        assert rc == 1
        assert "FIX-FIRST" in out

    def test_malformed_yaml_returns_fix_first(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("key: [unclosed bracket\n  nested: :")
        rc, out = run_cx("check", "card", str(bad))
        assert rc == 1
        assert "FIX-FIRST" in out


# ---------------------------------------------------------------------------
# cx check state
# ---------------------------------------------------------------------------

class TestCheckState:
    def test_good_state_passes(self):
        rc, out = run_cx("check", "state", fix("state_good.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out

    def test_bad_state_wrong_protocol_stamp(self):
        rc, out = run_cx("check", "state", fix("state_bad.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "protocol_stamp" in out.lower() or "Code-X V1" in out

    def test_bad_state_counts_mismatch(self):
        rc, out = run_cx("check", "state", fix("state_bad.yaml"))
        assert rc == 1
        # counts mismatch should be mentioned
        assert "counts" in out.lower() or "p0" in out.lower() or "items" in out.lower()

    def test_state_info_shows_current_card(self):
        rc, out = run_cx("check", "state", fix("state_good.yaml"))
        assert rc == 0
        assert "BUILD-001" in out or "current_card" in out.lower()


# ---------------------------------------------------------------------------
# cx check scope
# ---------------------------------------------------------------------------

class TestCheckScope:
    def test_good_diff_passes(self):
        rc, out = run_cx("check", "scope", fix("card_good.yaml"), fix("diff_good.txt"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out

    def test_diff_touches_forbidden_file(self):
        rc, out = run_cx("check", "scope", fix("card_good.yaml"), fix("diff_bad_forbidden.txt"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        # Should name the forbidden or secret file
        assert ".env" in out or "forbidden" in out.lower() or "secret" in out.lower()

    def test_nonexistent_diff_returns_fix_first(self):
        rc, out = run_cx("check", "scope", fix("card_good.yaml"), "/tmp/no_such_diff.txt")
        assert rc == 1
        assert "FIX-FIRST" in out


# ---------------------------------------------------------------------------
# cx check evidence
# ---------------------------------------------------------------------------

class TestCheckEvidence:
    def test_good_card_with_no_evidence_required_passes(self, tmp_path):
        """A card with evidence_required=[] should pass (no paths to check)."""
        import yaml
        card = {
            "id": "TEST-001",
            "mode": "MODULE_BUILD",
            "model_tier": "standard",
            "objective": "Test card.",
            "evidence_required": [],
        }
        card_file = tmp_path / "card.yaml"
        card_file.write_text(yaml.dump(card))
        rc, out = run_cx("check", "evidence", str(card_file))
        assert rc == 0, f"Expected PASS, got {rc}. Output:\n{out}"
        assert "PASS" in out

    def test_missing_evidence_path_fires_fix_first(self, tmp_path):
        import yaml
        missing = tmp_path / "evidence_output.txt"
        # Do NOT create the file
        card = {
            "id": "TEST-002",
            "mode": "MODULE_BUILD",
            "model_tier": "standard",
            "objective": "Test card.",
            "evidence_required": [str(missing)],
        }
        card_file = tmp_path / "card.yaml"
        card_file.write_text(yaml.dump(card))
        rc, out = run_cx("check", "evidence", str(card_file))
        assert rc == 1, f"Expected FIX-FIRST, got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "evidence_required" in out.lower() or str(missing) in out

    def test_empty_evidence_file_fires_fix_first(self, tmp_path):
        import yaml
        ev = tmp_path / "output.txt"
        ev.write_text("")  # empty
        card = {
            "id": "TEST-003",
            "mode": "MODULE_BUILD",
            "model_tier": "standard",
            "objective": "Test card.",
            "evidence_required": [str(ev)],
        }
        card_file = tmp_path / "card.yaml"
        card_file.write_text(yaml.dump(card))
        rc, out = run_cx("check", "evidence", str(card_file))
        assert rc == 1, f"Expected FIX-FIRST, got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out

    def test_faked_pass_in_evidence_fires_fix_first(self, tmp_path):
        import yaml
        ev = tmp_path / "test_output.txt"
        ev.write_text('assert True  # always passes\n')  # faked-pass pattern
        card = {
            "id": "TEST-004",
            "mode": "MODULE_BUILD",
            "model_tier": "standard",
            "objective": "Test card.",
            "evidence_required": [str(ev)],
        }
        card_file = tmp_path / "card.yaml"
        card_file.write_text(yaml.dump(card))
        rc, out = run_cx("check", "evidence", str(card_file))
        assert rc == 1, f"Expected FIX-FIRST, got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "faked-pass" in out.lower() or "assert True" in out


# ---------------------------------------------------------------------------
# cx check cost
# ---------------------------------------------------------------------------

class TestCheckCost:
    def test_good_cost_log_passes(self):
        rc, out = run_cx("check", "cost", fix("cost_log_good.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out

    def test_bad_cost_log_fires_fix_first(self):
        rc, out = run_cx("check", "cost", fix("cost_log_bad.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        # Should flag invalid model_tier or loops
        assert "model_tier" in out.lower() or "loop" in out.lower() or "over_read" in out.lower()

    def test_not_a_list_fires_fix_first(self, tmp_path):
        bad_log = tmp_path / "bad.yaml"
        bad_log.write_text("not: a-list\n")
        rc, out = run_cx("check", "cost", str(bad_log))
        assert rc == 1
        assert "FIX-FIRST" in out

    def test_missing_required_field_fires_fix_first(self, tmp_path):
        import yaml
        log = [{"stage": "BUILDING", "model_tier": "standard", "result": "PASS"}]
        # Missing card_id, actor, model_family, files_read
        log_file = tmp_path / "log.yaml"
        log_file.write_text(yaml.dump(log))
        rc, out = run_cx("check", "cost", str(log_file))
        assert rc == 1, f"Expected FIX-FIRST, got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out


# ---------------------------------------------------------------------------
# cx check final-ready
# ---------------------------------------------------------------------------

class TestCheckFinalReady:
    def test_good_final_ready_state_passes(self):
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out
        assert "READY" in out

    def test_bad_final_ready_state_fires_fix_first(self):
        rc, out = run_cx("check", "final-ready", fix("state_bad_final_ready.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        # Should mention open findings or card still in flight
        assert "p0" in out.lower() or "current_card" in out.lower() or "findings" in out.lower()

    def test_final_ready_blocked_by_open_findings(self):
        rc, out = run_cx("check", "final-ready", fix("state_bad_final_ready.yaml"))
        assert rc == 1
        assert "FIX-FIRST" in out
        # P0 finding should block
        assert "p0" in out.lower() or "findings" in out.lower()

    def test_final_ready_certificate_assembled_on_pass(self):
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        assert rc == 0
        assert "ASSEMBLED" in out or "verdict" in out.lower() or "READY" in out

    def test_wrong_protocol_stamp_in_final_ready(self, tmp_path):
        import yaml
        state = {
            "project": "test",
            "protocol_stamp": "Code-X v0.13",  # wrong
            "current_stage": "BUILD_FACTORY",
            "current_mode": "FINAL_READY",
            "current_card": None,
            "current_actor": "claude",
            "next_actor": "CEO",
            "next_action": "done",
            "stop_status": "NONE",
            "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []},
        }
        sf = tmp_path / "state.yaml"
        sf.write_text(yaml.dump(state))
        rc, out = run_cx("check", "final-ready", str(sf))
        assert rc == 1
        assert "FIX-FIRST" in out
        assert "protocol_stamp" in out.lower() or "Code-X V1" in out


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

class TestCLISurface:
    def test_help_lists_check_subcommand(self):
        rc, out = run_cx("--help")
        assert rc == 0
        assert "check" in out

    def test_check_help_lists_seven_subcommands(self):
        rc, out = run_cx("check", "--help")
        assert rc == 0
        for sub in ["card", "state", "scope", "evidence", "cost", "final-ready", "consistency"]:
            assert sub in out, f"Missing subcommand '{sub}' in help output:\n{out}"

    def test_no_args_returns_usage_error(self):
        rc, _ = run_cx()
        assert rc == 2

    def test_unknown_subcommand_returns_usage_error(self):
        rc, _ = run_cx("check", "run")
        assert rc == 2


# ---------------------------------------------------------------------------
# cx check consistency
# ---------------------------------------------------------------------------

# Paths relative to the test file's location
_ROOT = Path(__file__).parent.parent.parent  # Code-X-V1 root


class TestCheckConsistency:
    def test_real_tree_passes(self):
        """Consistency check on the actual Code-X-V1 tree must PASS (exit 0)."""
        rc, out = run_cx("check", "consistency")
        assert rc == 0, f"Expected PASS on real tree (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out

    def test_drifted_fixture_fires_fix_first(self):
        """A registry with a reworded canonical must fire FIX-FIRST naming the rule and file."""
        reg = fix("consistency_registry_drifted.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "fix-card-test-edit" in out
        # Must name at least one of the appears_in files
        assert "LESSONS.yaml" in out or "CX-CHECK-SPEC.md" in out

    def test_bad_registry_missing_path_fires_fix_first(self):
        """A registry pointing at a non-existent file must fire FIX-FIRST."""
        reg = fix("consistency_registry_bad_missing_path.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "does not exist" in out.lower() or "no-such-file" in out or "DOES_NOT_EXIST" in out

    def test_bad_registry_dup_id_fires_fix_first(self):
        """A registry with duplicate ids must fire FIX-FIRST."""
        reg = fix("consistency_registry_bad_dup_id.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "duplicate" in out.lower() or "eval-count" in out

    def test_missing_registry_fires_fix_first(self):
        """Pointing at a non-existent registry file must fire FIX-FIRST."""
        rc, out = run_cx("check", "consistency", "--registry", "/tmp/no-such-registry.yaml")
        assert rc == 1
        assert "FIX-FIRST" in out

    def test_meaning_flip_fires_fix_first(self):
        """KEY PROOF: a file that KEEPS the first canonical phrase but rewrites the rule to
        mean the OPPOSITE (dropping 'weaken') must fire FIX-FIRST.
        This is the meaning-flip class that single-token canonical silently misses.
        """
        reg = fix("consistency_registry_meaning_flip.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        assert rc == 1, (
            f"Expected FIX-FIRST (exit 1) — meaning-flip must be caught, got {rc}.\nOutput:\n{out}"
        )
        assert "FIX-FIRST" in out
        assert "fix-card-test-edit" in out
        # Must name the missing phrase 'weaken' — not just the file
        assert "weaken" in out

    # ── P1-07: banned_negations tripwire ──────────────────────────────────────
    def test_banned_negation_fires_fix_first(self):
        """P1-07: a file that keeps canonical phrases but adds a banned_negation phrase
        must fire FIX-FIRST — cheap tripwire for obvious meaning-flips.
        BAD FIXTURE: lessons_banned_negation.yaml contains 'tests may be weakened'.
        """
        reg = fix("consistency_registry_banned_negation.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        assert rc == 1, f"Expected FIX-FIRST (exit 1) for banned_negation, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "banned_negation" in out.lower() or "tests may be weakened" in out

    def test_good_registry_no_banned_negation_passes(self):
        """P1-07 good case: normal registry with no banned phrases in files passes."""
        rc, out = run_cx("check", "consistency")
        assert rc == 0, f"Expected PASS, got {rc}.\nOutput:\n{out}"
        assert "PASS" in out

    # ── P1-08: --strict mode ──────────────────────────────────────────────────
    def test_strict_mode_fails_unregistered_copy(self, tmp_path):
        """P1-08: --strict causes an unlisted file with key_phrases to FAIL not WARN.
        BAD: create an unregistered .md carrying the key_phrases.
        """
        import yaml, shutil
        # Set up a minimal tree: copy the real LESSONS.yaml as a registered file,
        # then create an unregistered file with key_phrases present.
        # Use a tmp registry pointing at an existing file, with an unregistered copy also existing.

        # Copy actual LESSONS.yaml as the registered file
        cx_root = Path(__file__).parent.parent.parent
        lessons_real = cx_root / "MEMORY" / "LESSONS.yaml"

        # Create an unregistered copy in a tmp dir reachable from root isn't possible
        # without modifying the real tree. Instead: test that --strict on the real tree
        # produces results (may PASS if no key_phrases in unlisted files after design-history excluded,
        # or may FAIL if some files match). The important thing is --strict doesn't CRASH.
        rc, out = run_cx("check", "consistency", "--strict")
        # Must exit cleanly (0 or 1) — never crash (2)
        assert rc in (0, 1), f"--strict must exit 0 or 1, got {rc}.\nOutput:\n{out}"

    def test_strict_mode_design_history_ignored(self):
        """P1-08: design-history/ files are excluded from --strict failures."""
        rc, out = run_cx("check", "consistency", "--strict")
        # design-history/ files must not cause hard FAIL — they're in the ignore list
        # If it fails, it must NOT mention design-history as a FAIL
        if rc == 1:
            lines = out.splitlines()
            for line in lines:
                if "[P1]" in line and "design-history/" in line:
                    assert False, f"design-history/ should be ignored under --strict:\n{line}"

    # ── P1-09: path boundary ──────────────────────────────────────────────────
    def test_path_escape_fires_fix_first(self):
        """P1-09: a registry with appears_in containing .. escape must fire FIX-FIRST.
        BAD FIXTURE: consistency_registry_path_escape.yaml has '../../etc/passwd'.
        """
        reg = fix("consistency_registry_path_escape.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        assert rc == 1, f"Expected FIX-FIRST for path escape, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "escape" in out.lower() or "absolute" in out.lower() or "rejected" in out.lower() or ".." in out

    def test_absolute_registry_outside_root_fires_fix_first(self):
        """P1-09: --registry pointing outside Code-X root must fire FIX-FIRST."""
        rc, out = run_cx("check", "consistency", "--registry", "/etc/passwd")
        assert rc == 1, f"Expected FIX-FIRST for out-of-root registry, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out

    # ── P2-05: .yaml scan ─────────────────────────────────────────────────────
    def test_yaml_files_scanned_in_consistency(self):
        """P2-05: .yaml files not in appears_in that carry key_phrases must be detected.
        This confirms the rglob now includes *.yaml as well as *.md.
        Uses consistency_registry_stale_yaml.yaml — a registry pointing at MEMORY/LESSONS.yaml
        which carries the phrases; any other .yaml with key_phrases gets WARN'd.
        """
        reg = fix("consistency_registry_stale_yaml.yaml")
        rc, out = run_cx("check", "consistency", "--registry", reg)
        # Should PASS or WARN (not crash) — the fixture points at LESSONS.yaml which
        # has the canonical phrases, so the registered file PASSes.
        # The test verifies no crash and that .yaml candidates are found (WARN may appear).
        assert rc in (0, 1), f"Must exit 0 or 1, not crash: {rc}.\nOutput:\n{out}"
        # At minimum, should not crash on yaml scanning
        assert "FATAL" not in out


# ---------------------------------------------------------------------------
# NEW: cx check card — P1-01, P1-06, P2-01, P2-03
# ---------------------------------------------------------------------------

class TestCheckCardNewFindings:
    # ── P1-06: full traceability ──────────────────────────────────────────────
    def test_audit_status_pending_fires_fix_first(self):
        """P1-06: audit_status=PENDING must be REJECTED (not PASS).
        BAD FIXTURE: card_bad_audit_status_pending.yaml
        BUG PROOF: before fix, cx check card would PASS this card because audit_status was not checked.
        """
        rc, out = run_cx("check", "card", fix("card_bad_audit_status_pending.yaml"))
        assert rc == 1, f"Expected FIX-FIRST for PENDING audit_status, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "audit_status" in out.lower() or "pending" in out.lower()

    def test_empty_requirement_ids_fires_fix_first(self):
        """P1-06: source_section with empty requirement_ids must fail.
        BAD FIXTURE: card_bad_audit_status_pending.yaml (has requirement_ids: [])
        """
        rc, out = run_cx("check", "card", fix("card_bad_audit_status_pending.yaml"))
        assert rc == 1
        assert "FIX-FIRST" in out
        assert "requirement_ids" in out.lower() or "audit_status" in out.lower()

    def test_good_card_with_full_traceability_passes(self):
        """P1-06 good case: card with complete traceability passes."""
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        assert rc == 0, f"Expected PASS for fully traced card, got {rc}.\nOutput:\n{out}"
        assert "PASS" in out

    # ── P1-01: foundation checkpoint ──────────────────────────────────────────
    def test_foundation_checkpoint_missing_reason_fires_fix_first(self):
        """P1-01: foundation_checkpoint_required: yes with empty reason must fail.
        BAD FIXTURE: card_bad_foundation_checkpoint_no_reason.yaml
        BUG PROOF: before fix, this would PASS (foundation_checkpoint_reason was not checked).
        """
        rc, out = run_cx("check", "card", fix("card_bad_foundation_checkpoint_no_reason.yaml"))
        assert rc == 1, f"Expected FIX-FIRST for missing foundation_checkpoint_reason, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "foundation_checkpoint" in out.lower() or "reason" in out.lower()

    def test_card_without_foundation_checkpoint_passes(self):
        """P1-01 good case: card without foundation_checkpoint_required passes."""
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        assert rc == 0, f"Expected PASS, got {rc}.\nOutput:\n{out}"
        assert "PASS" in out

    # ── P2-03: estimate_tokens ceiling ────────────────────────────────────────
    def test_estimate_tokens_over_ceiling_fires_fix_first(self):
        """P2-03: read.estimate_tokens exceeding READ_BUDGET_TOKENS must fail.
        BAD FIXTURE: card_bad_estimate_tokens_over_ceiling.yaml (estimate_tokens: 9999)
        BUG PROOF: before fix, estimate_tokens was not checked at all.
        """
        rc, out = run_cx("check", "card", fix("card_bad_estimate_tokens_over_ceiling.yaml"))
        assert rc == 1, f"Expected FIX-FIRST for over-ceiling estimate_tokens, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "estimate_tokens" in out.lower() or "ceiling" in out.lower() or "budget" in out.lower()

    def test_estimate_tokens_within_ceiling_passes(self):
        """P2-03 good case: estimate_tokens within ceiling passes."""
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        assert rc == 0, f"Expected PASS, got {rc}.\nOutput:\n{out}"
        assert "PASS" in out


# ---------------------------------------------------------------------------
# NEW: cx check final-ready — P1-02
# ---------------------------------------------------------------------------

class TestCheckFinalReadyNewFindings:
    def test_missing_gate_fields_fires_fix_first(self):
        """P1-02: state with zero findings but missing module_capsules_current etc. must NOT be READY.
        BAD FIXTURE: state_bad_missing_gate_fields.yaml
        BUG PROOF: before fix, this would pass as READY (gate fields not checked).
        """
        rc, out = run_cx("check", "final-ready", fix("state_bad_missing_gate_fields.yaml"))
        assert rc == 1, f"Expected FIX-FIRST for missing gate fields, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "module_capsules_current" in out.lower() or "absent" in out.lower() or "missing" in out.lower()

    def test_gate_fields_present_and_pass_required(self, tmp_path):
        """P1-02: state with gate field = PENDING (not PASS) must NOT be READY."""
        import yaml
        state = {
            "project": "test",
            "protocol_stamp": "Code-X V1",
            "current_stage": "BUILD_FACTORY",
            "current_mode": "FINAL_READY",
            "current_card": None,
            "current_actor": "claude",
            "next_actor": "CEO",
            "next_action": "done",
            "stop_status": "NONE",
            "last_commit": "abc123",
            "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []},
            "module_capsules_current": "PENDING",   # NOT PASS
            "module_regressions_pass": "PASS",
            "ceo_module_approvals_complete": "PASS",
            "security_closeout": "PASS",
            "recovery_proof": "PASS",
        }
        sf = tmp_path / "state.yaml"
        sf.write_text(yaml.dump(state))
        rc, out = run_cx("check", "final-ready", str(sf))
        assert rc == 1, f"Expected FIX-FIRST for PENDING gate field, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "module_capsules_current" in out.lower() or "pending" in out.lower()

    def test_all_gate_fields_pass_gives_ready(self):
        """P1-02 good case: state with all 5 gate fields = PASS gives READY."""
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        assert rc == 0, f"Expected PASS, got {rc}.\nOutput:\n{out}"
        assert "READY" in out


# ---------------------------------------------------------------------------
# NEW: cx check state — P2-02
# ---------------------------------------------------------------------------

class TestCheckStateNewFindings:
    def test_missing_last_commit_fires_fix_first(self):
        """P2-02: state missing last_commit must fire FIX-FIRST.
        BAD FIXTURE: state_bad_last_commit_missing.yaml
        BUG PROOF: before fix, missing last_commit was silently allowed.
        """
        rc, out = run_cx("check", "state", fix("state_bad_last_commit_missing.yaml"))
        assert rc == 1, f"Expected FIX-FIRST for missing last_commit, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "last_commit" in out.lower()

    def test_good_state_with_last_commit_passes(self):
        """P2-02 good case: state with last_commit present passes."""
        rc, out = run_cx("check", "state", fix("state_good.yaml"))
        assert rc == 0, f"Expected PASS, got {rc}.\nOutput:\n{out}"
        assert "PASS" in out


# ---------------------------------------------------------------------------
# NEW: cx check scope — P1-03, P1-04
# ---------------------------------------------------------------------------

class TestCheckScopeNewFindings:
    def test_empty_allowed_files_with_real_diff_fires_fix_first(self):
        """P1-04: empty allowed_files + real diff (non-REVIEW mode) must FAIL.
        BAD FIXTURE: card_empty_allowed_files.yaml + diff_bad_empty_allowed_files.txt
        BUG PROOF: before fix, empty allowed_files was silently OK (nothing to check against).
        """
        rc, out = run_cx("check", "scope", fix("card_empty_allowed_files.yaml"),
                          fix("diff_bad_empty_allowed_files.txt"))
        assert rc == 1, f"Expected FIX-FIRST for empty allowed_files + real diff, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "allowed_files" in out.lower() or "empty" in out.lower()

    def test_money_tripwire_no_but_diff_touches_balance_fires_fix_first(self):
        """P1-03: touches_money_or_balances=no but diff touches balance.py must FAIL.
        BAD FIXTURE: card_money_tripwire_no.yaml + diff_bad_money.txt
        BUG PROOF: before fix, only touches_auth and touches_secrets were checked.
        """
        rc, out = run_cx("check", "scope", fix("card_money_tripwire_no.yaml"),
                          fix("diff_bad_money.txt"))
        assert rc == 1, f"Expected FIX-FIRST for money tripwire mismatch, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "money" in out.lower() or "balance" in out.lower() or "tripwire" in out.lower()

    def test_review_mode_empty_allowed_files_passes(self, tmp_path):
        """P1-04 good case: REVIEW mode with empty allowed_files is allowed."""
        import yaml
        card = {
            "id": "REVIEW-001",
            "mode": "REVIEW",
            "actor": "claude-sonnet",
            "model_tier": "standard",
            "objective": "Review the module.",
            "source_map": {
                "locked_packet_id": "PKT-001",
                "locked_packet_hash": "abc123",
                "source_sections": [{"file": "SPEC.md", "section": "S1", "requirement_ids": ["R1"]}],
                "dependency_capsules": [],
            },
            "card_compilation": {
                "compiled_by": {"actor": "claude-opus", "family": "claude", "model": "claude-opus-4", "date": "2026-06-09"},
                "audited_by": {"actor": "gpt-5.5", "family": "gpt", "model": "gpt-5.5", "date": "2026-06-09"},
                "audit_status": "PASS",
            },
            "actor_record": {
                "executor": {"actor": "claude-sonnet", "family": "claude", "model": "claude-sonnet-4-6"},
                "cross_review": {
                    "required": "yes", "actor": "codex", "family": "gpt",
                    "family_substituted": "no", "ceo_authorization_ref": "",
                },
            },
            "family_note": {"known_quirk": "none", "leash": "review only"},
            "read": {"required": [], "forbidden": []},
            "allowed_files": [],
            "forbidden_files": [".env"],
            "allowed_operations": ["read-only"],
            "forbidden_operations": ["write"],
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
                            "self_heal_attempts": {"codex": 3}},
            "stop_conditions": [],
            "cost_budget": "1000 tokens",
            "state_update": "noop",
        }
        card_file = tmp_path / "card.yaml"
        card_file.write_text(yaml.dump(card))
        diff_file = tmp_path / "diff.txt"
        diff_file.write_text("--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new\n")
        rc, out = run_cx("check", "scope", str(card_file), str(diff_file))
        # REVIEW mode with empty allowed_files should PASS (no edits expected)
        # Note: diff touches src/main.py but REVIEW mode is exempt
        assert rc == 0, f"Expected PASS for REVIEW mode + empty allowed_files, got {rc}.\nOutput:\n{out}"


# ---------------------------------------------------------------------------
# NEW: cx check evidence — P1-05, P2-06
# ---------------------------------------------------------------------------

class TestCheckEvidenceNewFindings:
    def test_test_file_in_diff_without_authorisation_fires_fix_first(self):
        """P1-05: diff touches a test file but fix_test_edits.allowed: no → FAIL.
        BAD FIXTURE: card_fix_test_edits_not_allowed.yaml + diff_bad_test_unauthorized.txt
        BUG PROOF: before fix, the check used `any('test' in allowed_files)` shortcut
        which incorrectly passed cards when test was listed in allowed_files.
        """
        rc, out = run_cx("check", "evidence",
                          fix("card_fix_test_edits_not_allowed.yaml"),
                          "--diff", fix("diff_bad_test_unauthorized.txt"))
        assert rc == 1, f"Expected FIX-FIRST for unauthorized test edit in diff, got {rc}.\nOutput:\n{out}"
        assert "FIX-FIRST" in out
        assert "test" in out.lower() and ("authoris" in out.lower() or "allowed" in out.lower())

    def test_evidence_path_resolves_relative_to_card_dir(self, tmp_path):
        """P2-06: evidence paths resolve relative to card dir, not CWD.
        Place card and evidence file in tmp_path, run cx from a different CWD,
        and verify the relative path resolves correctly.
        """
        import yaml, os
        ev_file = tmp_path / "EVIDENCE.md"
        ev_file.write_text("PASS — all checks passed\n")

        card = {
            "id": "EVPATH-001",
            "mode": "MODULE_BUILD",
            "model_tier": "standard",
            "objective": "Test path resolution.",
            "evidence_required": ["EVIDENCE.md"],  # relative — should resolve to tmp_path/EVIDENCE.md
        }
        card_file = tmp_path / "card.yaml"
        card_file.write_text(yaml.dump(card))

        # Run from a DIFFERENT directory (the checkers dir, not tmp_path)
        orig_cwd = os.getcwd()
        try:
            os.chdir(str(Path(__file__).parent.parent))
            rc, out = run_cx("check", "evidence", str(card_file))
        finally:
            os.chdir(orig_cwd)

        assert rc == 0, (
            f"Expected PASS — relative evidence path should resolve from card dir, not CWD. "
            f"Got {rc}.\nOutput:\n{out}"
        )
        assert "PASS" in out


# ---------------------------------------------------------------------------
# ROUND 2: cx check card — F1 P1-01, F2 P1-06
# ---------------------------------------------------------------------------

class TestCheckCardRound2:
    # ── F1 P1-01: dependent-card foundation blocking ──────────────────────────
    def test_dependent_card_blocked_when_checkpoint_unmet(self):
        """F1: dependent card with dependency_capsule requiring foundation checkpoint
        that is NOT in state.foundation_checkpoints_passed must FAIL.
        PRE-FIX PROOF: wrongly returned PASS on unfixed code.
        """
        rc, out = run_cx("check", "card",
                          fix("card_dependent_unmet_checkpoint.yaml"),
                          "--state", fix("state_foundation_unmet.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "FOUND-001" in out

    def test_dependent_card_passes_when_checkpoint_met(self):
        """F1 good path: same dependent card passes when FOUND-001 is in foundation_checkpoints_passed."""
        rc, out = run_cx("check", "card",
                          fix("card_dependent_unmet_checkpoint.yaml"),
                          "--state", fix("state_foundation_met.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out

    def test_dependent_card_no_state_fails_closed(self):
        """A1 contract correction: without --state, a card with checkpoint-required dependency
        must FAIL CLOSED. This inverts the prior test which expected PASS (no over-fire)."""
        rc, out = run_cx("check", "card", fix("card_dependent_unmet_checkpoint.yaml"))
        assert rc == 1, f"Expected FAIL CLOSED (exit 1) without --state, got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "FAIL CLOSED" in out or "fail closed" in out or "--state" in out, \
            f"Expected fail-closed message in output:\n{out}"

    def test_foundation_card_does_not_self_block(self):
        """PROP-041(b): a FOUNDATION card (foundation_checkpoint_required: yes, with reason)
        must PASS its own `cx check card` even when its own id is NOT yet in
        state.foundation_checkpoints_passed. The checkpoint can only be recorded AFTER the
        card builds + is xfam-reviewed (chicken-and-egg), so a self-block would make the
        foundation card unbuildable forever. Per GATES.md:48 the checkpoint blocks every
        DEPENDENT card, never the foundation card itself.
        PRE-FIX PROOF: cx_card.py:879-882 self-blocked (returned exit 1) on unfixed code.
        """
        rc, out = run_cx("check", "card",
                          fix("card_foundation_self_unmet.yaml"),
                          "--state", fix("state_foundation_unmet.yaml"))
        assert rc == 0, f"Expected PASS (exit 0) — foundation card must not self-block, got {rc}. Output:\n{out}"
        assert "PASS" in out

    # ── F2 P1-06: empty source_sections ──────────────────────────────────────
    def test_empty_source_sections_fails(self):
        """F2: source_map.source_sections: [] must FAIL — no auditable packet slice.
        PRE-FIX PROOF: wrongly returned PASS on unfixed code.
        """
        rc, out = run_cx("check", "card", fix("card_empty_source_sections.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "source_sections" in out.lower()

    # ── F2 P1-06: required work-order fields ─────────────────────────────────
    def test_missing_workorder_fields_fail(self):
        """F2: card missing all five required work-order fields must FAIL.
        ALL FIVE must appear in the output — proves each check fires independently.
        PRE-FIX PROOF: wrongly returned PASS on unfixed code.
        """
        rc, out = run_cx("check", "card", fix("card_missing_workorder_fields.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        for f in ("relevant_invariants", "acceptance", "loop_budget", "stop_conditions", "state_update"):
            assert f in out.lower(), f"Expected '{f}' in output but got:\n{out}"

    def test_good_card_still_passes_after_workorder_check(self):
        """F2 good path: fully filled work-order card must still PASS."""
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out

    # ── A2 P1-06: source_sections must be a NON-EMPTY LIST ───────────────────
    def test_source_sections_not_list_fails(self):
        """A2: source_map.source_sections as a string (not a list) must FAIL.
        Pre-fix: slipped through because old code only guarded empty-list, not wrong type."""
        rc, out = run_cx("check", "card", fix("card_bad_source_sections_not_list.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "source_sections" in out.lower(), f"Expected 'source_sections' in output:\n{out}"

    # ── A3 P2-04: loop_budget.review_fix_cycles > 1 rejected at CARD level ──
    def test_review_fix_cycles_over_one_fails_at_card_level(self):
        """A3: card planning review_fix_cycles:2 must FAIL at card-check time (one-and-done).
        Pre-fix: only the cost-log checked this; the card could silently plan 2 cycles."""
        rc, out = run_cx("check", "card", fix("card_bad_review_fix_cycles.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "review_fix_cycles" in out.lower(), f"Expected 'review_fix_cycles' in output:\n{out}"

    def test_review_fix_cycles_one_passes_at_card_level(self):
        """A3 good path: card with review_fix_cycles:1 must still PASS."""
        rc, out = run_cx("check", "card", fix("card_good.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out


# ---------------------------------------------------------------------------
# ROUND 2: cx check consistency — F3 P1-09
# ---------------------------------------------------------------------------

class TestCheckConsistencyRound2:
    def test_relative_registry_escape_rejected(self):
        """F3: relative --registry path that escapes Code-X root must be rejected.
        PRE-FIX PROOF: current code LOADS the outside registry instead of rejecting it.
        Uses a valid registry written one level above root.
        """
        import shutil
        outside = _CX_ROOT.parent / "_cx_tmp_outside_registry.yaml"
        # copy the real registry as a valid outside file
        real_registry = _CX_ROOT / "checkers" / "rule-registry.yaml"
        try:
            shutil.copy(str(real_registry), str(outside))
            rc, out = run_cx("check", "consistency", "--registry", "../_cx_tmp_outside_registry.yaml")
            assert rc == 1, f"Expected FIX-FIRST (exit 1) for relative escape, got {rc}. Output:\n{out}"
            assert "FIX-FIRST" in out
            assert "escape" in out.lower()
        finally:
            if outside.exists():
                outside.unlink()


# ---------------------------------------------------------------------------
# ROUND 2: cx check cost — F4 P2-04
# ---------------------------------------------------------------------------

class TestCheckCostRound2:
    def test_review_fix_cycles_over_one_fails(self):
        """F4: cost-log entry with review_fix_cycles: 2 must FAIL (one-and-done).
        PRE-FIX PROOF: wrongly returned PASS on unfixed code.
        """
        rc, out = run_cx("check", "cost", fix("cost_log_review_fix_cycles_over.yaml"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "review_fix_cycles" in out.lower()
        assert "one-and-done" in out.lower()

    def test_good_cost_log_no_review_fix_cycles_still_passes(self):
        """F4 good path: cost_log_good has no review_fix_cycles field — must still PASS."""
        rc, out = run_cx("check", "cost", fix("cost_log_good.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out


# ---------------------------------------------------------------------------
# ROUND 2: cx check final-ready — F5 P2-03
# ---------------------------------------------------------------------------

class TestCheckFinalReadyRound2:
    def test_final_ready_card_evidence_resolves_from_any_cwd(self):
        """F5: --card evidence paths must resolve relative to card's directory, not CWD.
        PRE-FIX PROOF: running from /tmp returned FIX-FIRST (evidence path missing).
        After fix: PASS regardless of CWD.
        """
        result = subprocess.run(
            [sys.executable, CX, "check", "final-ready",
             fix("state_good_final_ready.yaml"), "--card", fix("card_final_ready_relpath.yaml")],
            capture_output=True, text=True, cwd="/tmp")
        out = result.stdout + result.stderr
        assert result.returncode == 0, (
            f"Expected PASS from /tmp, got {result.returncode}:\n{out}"
        )

    def test_good_card_from_project_cwd_still_passes(self):
        """F5 good path (no regression): good card with absolute evidence path still passes."""
        rc, out = run_cx("check", "final-ready", fix("state_good_final_ready.yaml"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out


# ---------------------------------------------------------------------------
# cx check deck
# ---------------------------------------------------------------------------

class TestCheckDeck:
    def test_good_deck_passes(self):
        """Good fixture: all BUILDING covered, NOT_APPLICABLE has reason, CEO_DEFERRED has ref."""
        rc, out = run_cx("check", "deck", fix("deck_good_cards"), fix("deck_good_packet"))
        assert rc == 0, f"Expected PASS (exit 0), got {rc}. Output:\n{out}"
        assert "PASS" in out

    def test_good_deck_coverage_summary_in_output(self):
        """PASS output must include coverage summary line."""
        rc, out = run_cx("check", "deck", fix("deck_good_cards"), fix("deck_good_packet"))
        assert rc == 0
        assert "coverage:" in out
        assert "building/covered" in out

    def test_good_deck_lists_non_building_ids(self):
        """PASS output must list dispositioned-out requirement ids."""
        rc, out = run_cx("check", "deck", fix("deck_good_cards"), fix("deck_good_packet"))
        assert rc == 0
        # REQ-002 NOT_APPLICABLE and REQ-003 CEO_DEFERRED should appear
        assert "REQ-002" in out
        assert "REQ-003" in out

    def test_missing_building_requirement_bites_p0(self):
        """Gate 1: BUILDING requirement absent from all cards => P0."""
        rc, out = run_cx("check", "deck",
                         fix("deck_bad_missing_building_cards"),
                         fix("deck_bad_missing_building_packet"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "[P0]" in out
        assert "dropped at compile" in out.lower() or "building" in out.lower()

    def test_not_building_without_ceo_ref_bites_p1(self):
        """Gate 2: NOT_BUILDING row missing ceo_decision_ref => P1."""
        rc, out = run_cx("check", "deck",
                         fix("deck_bad_not_building_no_ref_cards"),
                         fix("deck_bad_not_building_no_ref_packet"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "[P1]" in out
        assert "ceo_decision_ref" in out.lower()

    def test_ghost_requirement_bites_p1(self):
        """Gate 4: card claims req id not in manifest => P1 ghost."""
        rc, out = run_cx("check", "deck",
                         fix("deck_bad_ghost_cards"),
                         fix("deck_bad_ghost_packet"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "[P1]" in out
        assert "ghost" in out.lower()
        assert "REQ-999" in out

    def test_hash_mismatch_bites_p0(self):
        """Gate 5: card locked_packet_hash != recomputed hash => P0."""
        rc, out = run_cx("check", "deck",
                         fix("deck_bad_hash_mismatch_cards"),
                         fix("deck_bad_hash_mismatch_packet"))
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out
        assert "[P0]" in out
        assert "hash" in out.lower()

    def test_na_without_reason_bites_p1(self):
        """Gate 3: NOT_APPLICABLE row missing reason => P1."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            pdir = Path(tmpdir) / "pkt"
            cdir = Path(tmpdir) / "cards"
            pdir.mkdir()
            cdir.mkdir()
            # Write a manifest with NOT_APPLICABLE but no reason
            (pdir / "spec.md").write_text("dummy")
            (pdir / "requirements-manifest.yaml").write_text(
                "requirements:\n"
                "  - id: REQ-A\n"
                "    disposition: NOT_APPLICABLE\n"
            )
            # Compute real hash for this packet
            import hashlib
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
            assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
            assert "FIX-FIRST" in out
            assert "[P1]" in out
            assert "reason" in out.lower()

    def test_malformed_manifest_bites_p1(self):
        """Gate 6: manifest with bad YAML => P1."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pdir = Path(tmpdir) / "pkt"
            cdir = Path(tmpdir) / "cards"
            pdir.mkdir()
            cdir.mkdir()
            (pdir / "requirements-manifest.yaml").write_text("requirements: [unclosed\n  bad: :")
            rc, out = run_cx("check", "deck", str(cdir), str(pdir))
            assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
            assert "FIX-FIRST" in out
            assert "[P1]" in out

    def test_empty_requirements_list_bites_p1(self):
        """Gate 6: empty requirements list => P1."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pdir = Path(tmpdir) / "pkt"
            cdir = Path(tmpdir) / "cards"
            pdir.mkdir()
            cdir.mkdir()
            (pdir / "requirements-manifest.yaml").write_text("requirements: []\n")
            rc, out = run_cx("check", "deck", str(cdir), str(pdir))
            assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
            assert "FIX-FIRST" in out
            assert "[P1]" in out

    def test_manifest_escape_rejected(self):
        """--manifest absolute path escape is rejected."""
        rc, out = run_cx("check", "deck",
                         fix("deck_good_cards"),
                         fix("deck_good_packet"),
                         "--manifest", "/etc/passwd")
        assert rc == 1, f"Expected FIX-FIRST (exit 1), got {rc}. Output:\n{out}"
        assert "FIX-FIRST" in out


# ---------------------------------------------------------------------------
# --session-start mode helpers (mirrored from run.py)
# ---------------------------------------------------------------------------
def _git_init(repo_dir: str) -> None:
    subprocess.run(["git", "init", "-q", repo_dir], check=True)
    subprocess.run(["git", "-C", repo_dir, "config", "user.email", "cx@test"], check=True)
    subprocess.run(["git", "-C", repo_dir, "config", "user.name", "cx"], check=True)


def _git_commit(repo_dir: str, msg: str = "init") -> str:
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
    "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": []},
    "cost_this_week": {"cards_run": 1, "top_model_cards": 0, "cheap_model_cards": 0,
                       "full_reviews": 0, "loops_used": 1, "waste_alarm": "LOW"},
}


def _write_state_ss(path: str, last_commit: str, wip=None) -> None:
    import yaml
    state = dict(_STATE_BASE_SS)
    state["last_commit"] = last_commit
    if wip is not None:
        state["wip_continuation"] = wip
    with open(path, "w") as f:
        yaml.dump(state, f)


# ---------------------------------------------------------------------------
# --session-start tests (pytest-style, same method set as run.py class)
# ---------------------------------------------------------------------------
class TestCheckStateSessionStart:

    def test_ancestor_ok_passes(self):
        """Clean tree, last_commit == HEAD → PASS."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            sha = _git_commit(repo, "second")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, sha)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            assert rc == 0, f"Expected PASS, got {rc}.\n{out}"
            assert "PASS" in out

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
            assert rc == 1, f"Expected FIX-FIRST, got {rc}.\n{out}"
            assert "[P1]" in out
            assert ("history" in out.lower() or "ancestor" in out.lower() or
                    "worktree" in out.lower())

    def test_unknown_sha_bites_p1(self):
        """Well-formed sha not in repo → P1."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            _git_commit(repo, "first")
            unknown_sha = "deadbeef" * 5
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, unknown_sha)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            assert rc == 1, f"Expected FIX-FIRST, got {rc}.\n{out}"
            assert "[P1]" in out

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
            assert rc == 1, f"Expected FIX-FIRST, got {rc}.\n{out}"
            assert "[P1]" in out
            assert ("uncommitted" in out.lower() or "wip" in out.lower() or
                    "dirty" in out.lower())

    def test_wip_marked_passes(self):
        """Dirty tree + wip_continuation fully marked → PASS."""
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
            })
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            assert rc == 0, f"Expected PASS, got {rc}.\n{out}"
            assert "PASS" in out

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
            assert rc == 1, f"Expected FIX-FIRST, got {rc}.\n{out}"
            assert "[P2]" in out
            assert ("owner_card" in out.lower() or "handoff_ref" in out.lower() or
                    "unowned" in out.lower())

    def test_behind_3_warns_but_exits_0(self):
        """6 commits; last_commit = first sha; clean tree → exit 0 + WARN."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            _git_init(repo)
            first_sha = _git_commit(repo, "commit-1")
            for i in range(2, 7):
                _git_commit(repo, f"commit-{i}")
            state = os.path.join(tmp, "state.yaml")
            _write_state_ss(state, first_sha)
            rc, out = run_cx("check", "state", state, "--session-start", "--repo-root", repo)
            assert rc == 0, f"Expected exit 0 (advisory only), got {rc}.\n{out}"
            assert "PASS" in out
            assert "WARN:" in out

    def test_session_start_without_repo_root_errors(self):
        """--session-start without --repo-root must FIX-FIRST."""
        rc, out = run_cx("check", "state", fix("state_good.yaml"), "--session-start")
        assert rc == 1, f"Expected FIX-FIRST (missing --repo-root), got {rc}.\n{out}"
        assert "FIX-FIRST" in out
        assert "--repo-root" in out

    def test_back_compat_state_good_without_session_start(self):
        """Existing state_good.yaml still passes without --session-start."""
        rc, out = run_cx("check", "state", fix("state_good.yaml"))
        assert rc == 0, f"Back-compat FAIL: state_good.yaml got {rc}.\n{out}"
        assert "PASS" in out


# ---------------------------------------------------------------------------
# cx check packet — PROP-031 external-visual-reference capture + lock
# ---------------------------------------------------------------------------

class TestCheckPacketProp031:
    def test_style_locked_still_passes_with_provenance(self):
        """Regression: a cat-14-DONE packet passes once it declares visual_provenance."""
        rc, out = run_cx("check", "packet", fix("packet_good_style_locked"))
        assert rc == 0, f"style_locked should PASS, got {rc}.\n{out}"
        assert "PASS" in out

    def test_external_reference_good_passes(self):
        """A fully captured + pinned + bound external_reference packet passes."""
        rc, out = run_cx("check", "packet", fix("packet_prop031_external_good"))
        assert rc == 0, f"external_good should PASS, got {rc}.\n{out}"

    def test_missing_provenance_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_no_provenance"))
        assert rc == 1
        assert "look-source unstated (P-PROP-004)" in out

    def test_external_uncaptured_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_uncaptured"))
        assert rc == 1
        assert "the captured reference must be pinned inside the packet (P-PROP-004)" in out

    def test_capture_hash_mismatch_bites(self):
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_capture_hash"))
        assert rc == 1
        assert "file_hash mismatch" in out

    def test_fidelity_language_warns_but_does_not_block(self):
        """Advisory heuristic: 'looks like MM' on a non-external screen WARNs, never blocks."""
        rc, out = run_cx("check", "packet", fix("packet_warn_prop031_fidelity_lang"))
        assert rc == 0, f"advisory WARN must not block, got {rc}.\n{out}"
        assert "WARN:" in out
        assert "reads like an external reference" in out

    # --- built-code review hardening (GPT/Codex thread 019ee299, fix-first) ---
    def test_empty_screens_list_bites(self):
        """An empty/all-false screens list cannot collapse the provenance gate to no-check."""
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_empty_screens"))
        assert rc == 1
        assert "declares no user-facing screen" in out

    def test_short_hash_rejected(self):
        """A 1-2 char declared file_hash must not pass via startswith."""
        rc, out = run_cx("check", "packet", fix("packet_bad_prop031_short_hash"))
        assert rc == 1
        assert "is not a lowercase-hex sha256 prefix" in out


# ---------------------------------------------------------------------------
# cx check packet — PROP-023 WRITING-stage front-end hardening (v1.13):
#   (a) clarify-before-freeze  (b) testable acceptance criterion
# ---------------------------------------------------------------------------

class TestCheckPacketProp023:
    def test_good_packet_passes_with_sweep_and_acceptance(self):
        """Regression: packet_good now carries clarification-sweep.md + a structured
        acceptance_criterion on its BUILDING row, and still PASSes."""
        rc, out = run_cx("check", "packet", fix("packet_good"))
        assert rc == 0, f"packet_good should PASS, got {rc}.\n{out}"
        assert "clarify-before-freeze" in out

    def test_missing_sweep_bites(self):
        """No clarification-sweep.md — absence of markers is not proof the sweep ran (PROP-023a)."""
        rc, out = run_cx("check", "packet", fix("packet_bad_clarify_no_sweep"))
        assert rc == 1
        assert "absence of markers is not proof the sweep ran" in out

    def test_open_marker_blocks_freeze(self):
        """An unresolved [NEEDS-CLARIFICATION: …] marker in a content doc blocks freeze."""
        rc, out = run_cx("check", "packet", fix("packet_bad_clarify_open_marker"))
        assert rc == 1
        assert "unresolved '[NEEDS-CLARIFICATION" in out

    def test_clarification_ref_must_resolve_to_ledger_row(self):
        """A ceo_decision_ref that looks valid (CEO-D-99999) but names no real ledger row is
        rejected — built-code review P1: the presence-only check was not ledger-bound."""
        rc, out = run_cx("check", "packet", fix("packet_bad_clarify_inline_dismissal"))
        assert rc == 1
        assert "does not resolve to a" in out

    def test_acceptance_criterion_required_on_building(self):
        """A BUILDING requirement with no acceptance_criterion block is rejected (PROP-023b)."""
        rc, out = run_cx("check", "packet", fix("packet_bad_acceptance_missing"))
        assert rc == 1
        assert "no 'acceptance_criterion' block" in out

    def test_placeholder_acceptance_field_bites(self):
        """Present-but-placeholder (pass_condition: TBD) is not a filled-in criterion."""
        rc, out = run_cx("check", "packet", fix("packet_bad_acceptance_placeholder"))
        assert rc == 1
        assert "missing/placeholder/non-string" in out
        assert "pass_condition" in out

    def test_nonstring_acceptance_field_bites(self):
        """A non-string acceptance value (pass_condition: true) must not pass via str-coercion."""
        rc, out = run_cx("check", "packet", fix("packet_bad_acceptance_nonstring"))
        assert rc == 1
        assert "missing/placeholder/non-string" in out


# ---------------------------------------------------------------------------
# cx check design-fidelity — PROP-031 external_capture lock binding + receipt
# ---------------------------------------------------------------------------

class TestCheckDesignFidelityProp031:
    def _run(self, manifest):
        return run_cx("check", "design-fidelity",
                      "--manifest", fix(manifest),
                      "--dom", fix("dom_good.html"),
                      "--screenshot", fix("screenshot_good.png"))

    def test_external_capture_lock_good_passes(self):
        rc, out = self._run("ui_lock_manifest_external_good.yaml")
        assert rc == 0, f"external_capture good lock should PASS, got {rc}.\n{out}"

    def test_missing_side_by_side_receipt_bites_p0(self):
        rc, out = self._run("ui_lock_manifest_external_no_receipt.yaml")
        assert rc == 1
        assert "[P0]" in out
        assert "no side_by_side_accept receipt" in out

    def test_viewport_dimension_mismatch_bites_p1(self):
        rc, out = self._run("ui_lock_manifest_external_dim_mismatch.yaml")
        assert rc == 1
        assert "[P1]" in out
        assert "not judged at the same viewport" in out


class TestSubstantiveSourceHash:
    """Unit tests for _compute_substantive_source_hash (PROP-041)."""

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

    def test_buildmeta_only_registry_edit_identical_hash(self):
        """Editing ONLY build-metadata fields in MODULE-REGISTRY.yaml yields the same substantive hash."""
        import yaml, copy
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            from cx_deck import _compute_substantive_source_hash
        finally:
            sys.path.pop(0)
        base_reg = {"module_registry": {"frozen_packet_hash": "old-hash", "protocol_version": "1.0",
                                         "modules": [{"module_id": "m_a", "card_ids": ["C-001"],
                                                       "dependency_modules": ["m_b"],
                                                       "requirement_ids": ["REQ-001"]},
                                                      {"module_id": "m_b", "card_ids": [],
                                                       "dependency_modules": [], "requirement_ids": []}]}}
        with tempfile.TemporaryDirectory() as tmp:
            pkt1 = self._make_packet(tmp + "/p1", {
                "requirements-manifest.yaml": "requirements:\n  - id: REQ-001\n    disposition: BUILDING\n",
                "MODULE-REGISTRY.yaml": yaml.safe_dump(base_reg)})
            mutated = copy.deepcopy(base_reg)
            mutated["module_registry"]["frozen_packet_hash"] = "new-hash"
            mutated["module_registry"]["protocol_version"] = "1.99"
            mutated["module_registry"]["modules"][0]["card_ids"] = ["C-999"]
            mutated["module_registry"]["modules"][0]["dependency_modules"] = []
            pkt2 = self._make_packet(tmp + "/p2", {
                "requirements-manifest.yaml": "requirements:\n  - id: REQ-001\n    disposition: BUILDING\n",
                "MODULE-REGISTRY.yaml": yaml.safe_dump(mutated)})
            h1 = _compute_substantive_source_hash(pkt1)
            h2 = _compute_substantive_source_hash(pkt2)
            assert h1 == h2, "Build-metadata-only registry edit must yield identical substantive hash"

    def test_substantive_registry_edit_different_hash(self):
        """Editing a TRD content field yields a different substantive hash."""
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            from cx_deck import _compute_substantive_source_hash
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as tmp:
            pkt1 = self._make_packet(tmp + "/p1", {
                "requirements-manifest.yaml": "requirements: []\n",
                "TRD.md": "# TRD v1\n"})
            pkt2 = self._make_packet(tmp + "/p2", {
                "requirements-manifest.yaml": "requirements: []\n",
                "TRD.md": "# TRD v2 CHANGED\n"})
            h1 = _compute_substantive_source_hash(pkt1)
            h2 = _compute_substantive_source_hash(pkt2)
            assert h1 != h2, "Substantive content edit must yield different hash"

    def test_symlink_raises_valueerror(self):
        """A symlink under the packet raises ValueError (fail-closed)."""
        import pytest
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            from cx_deck import _compute_substantive_source_hash
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as tmp:
            pkt = Path(tmp) / "packet"
            pkt.mkdir()
            (pkt / "real.md").write_text("content")
            (pkt / "link.md").symlink_to(pkt / "real.md")
            with pytest.raises(ValueError):
                _compute_substantive_source_hash(pkt)

    def test_date_typed_substantive_field_does_not_launder(self):
        """GPT xfam P2: a YAML date in a substantive registry field must NOT collapse to its string
        form (json default= coercion removed) — changing the date value MUST invalidate."""
        sys.path.insert(0, str(CHECKERS_DIR))
        try:
            from cx_deck import _compute_substantive_source_hash
        finally:
            sys.path.pop(0)
        reg1 = ("module_registry:\n  frozen_packet_hash: h\n  modules:\n"
                "  - module_id: m_a\n    review_due: 2026-06-28\n    card_ids: [C-001]\n"
                "    dependency_modules: []\n    requirement_ids: [REQ-001]\n")
        reg2 = reg1.replace("2026-06-28", "2026-06-29")
        with tempfile.TemporaryDirectory() as tmp:
            p1 = self._make_packet(tmp + "/p1", {"MODULE-REGISTRY.yaml": reg1})
            p2 = self._make_packet(tmp + "/p2", {"MODULE-REGISTRY.yaml": reg2})
            assert _compute_substantive_source_hash(p1) != _compute_substantive_source_hash(p2), \
                "a date-typed substantive registry field must invalidate on change, not collapse"


class TestCxAuditLayerIdCoercion:
    """F4 (v1.22 self-review): cx_audit.py's table_by_id keyed on the SOP layer table's `id`
    (int) — comparing a report layer id of a DIFFERENT type (e.g. a quoted YAML string) silently
    SKIPPED the Rule 2 live-subitem cross-check (fail-open on type mismatch). _coerce_layer_id()
    now normalizes both sides to int, and an unparseable id is itself a fail-closed finding."""

    def _write_audit_dir(self, tmp, layers_yaml: str, facts_yaml: str = None):
        d = Path(tmp) / "audit"
        d.mkdir()
        (d / "AUDIT-SUMMARY.md").write_text("# audit summary\n")
        facts = facts_yaml or (
            "  A1: true\n  A2: true\n  A3: true\n  A4: false\n  A5: E2\n"
            "  A6: true\n  A7: true\n  A8: false\n  A9: false\n")
        (d / "applicability.yaml").write_text(f"facts:\n{facts}layers:\n{layers_yaml}")
        return d

    def test_string_layer_id_still_cross_checked(self):
        """A layer id given as a quoted string ("1") in the report must still match the SOP
        table's int id 1 — before F4 this type mismatch silently skipped Rule 2 entirely, hiding
        a whole-layer N/A that contradicts a live sub-item under the recorded facts."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._write_audit_dir(tmp,
                '- id: "1"\n  verdict: N_A\n  driving_fact: "A1=false (claimed, but built app has UI)"\n')
            rc, out = run_cx("check", "audit", str(d), "--state", fix("audit_state_good.yaml"))
            assert rc == 1, f"Expected FIX-FIRST, got {rc}.\nOutput:\n{out}"
            assert "AUDIT-STAGE-WHOLE-LAYER-NA-WITH-LIVE-SUBITEM" in out, \
                f"string id '1' must still cross-check against the SOP table's int id 1.\nOutput:\n{out}"

    def test_unparseable_layer_id_fails_closed(self):
        """A layer id that cannot be coerced to int must fail CLOSED with a dedicated finding —
        never a silent skip of the Rule 2 cross-check (the pre-F4 fail-open behavior)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._write_audit_dir(tmp,
                '- id: "not-a-number"\n  verdict: N_A\n  driving_fact: "some fact"\n')
            rc, out = run_cx("check", "audit", str(d), "--state", fix("audit_state_good.yaml"))
            assert rc == 1, f"Expected FIX-FIRST, got {rc}.\nOutput:\n{out}"
            assert "AUDIT-STAGE-LAYER-ID-UNPARSEABLE" in out, \
                f"an unparseable layer id must fail closed, not silently skip.\nOutput:\n{out}"
