# cmd_whole_packet_review: validate the whole-packet cross-family INTEGRATION review receipt (P-PROP-006).
#
#   cx check whole-packet-review --state <CODE-X-STATE.yaml> --packet-dir <frozen packet> --repo-root <dir>
#
# The G7 build-authorization integration gate. The G1 card audit checks each CARD against its packet
# SLICE (per-card, traceable); the deterministic checker proves hash/coverage. NEITHER reads the
# non-card packet docs (TRD / PRD / architecture / security-baseline) for CROSS-DOCUMENT coherence —
# exactly where a real project's drift lived (the TRD still named the OLD voice engine after the stack locked
# to the new voice engine; an autonomous builder reading that card→TRD would have built the WRONG voice component).
# P-PROP-006 makes a FULL opposite-family review of the WHOLE frozen packet a mandatory precondition
# before any module build. It COMPLEMENTS (never replaces) the card audit / risk-module / per-module
# reviews — it is the integration/coherence pass none of them provide.
#
# The receipt is a typed, hash-bound record that lives OUTSIDE the frozen packet (the B-PROP-008 · B-PROP-010
# receipts-outside-packet pattern; writing a review never mutates the packet hash), referenced from
# CODE-X-STATE via whole_packet_review_receipt {receipt, receipt_hash}. CHECK/RECEIPT-ONLY — it never
# runs a review. Final-ready-grade binding (mirrors final_cross_family_receipt in cx_final_ready):
#   - receipt ref repo-relative + path-safe (no absolute / '..' / symlink / resolved-escape)
#   - receipt file exists + its sha12 == state.whole_packet_review_receipt.receipt_hash (fabricated/stale)
#   - a typed whole_packet_review mapping carrying every required field + review_kind WHOLE_PACKET_G7
#   - reviewer_family != authoring_family (opposite-family — a same-family review is not cross-family)
#   - verdict present and in {PASS, FIX_FIRST_RESOLVED} (a missing verdict is not a silent pass; a raw
#     FIX_FIRST / REJECTED blocks)
#   - frozen_packet_hash == the recomputed frozen-packet hash. ANY packet-hash change invalidates the
#     receipt — TRD/PRD/security/stack-lock/blueprint can change with every module approved_source_hash
#     unchanged (exactly what a real project's own whole-packet fold did), so currency keys on the WHOLE packet
#     hash, NEVER a module hash (P-PROP-006 Rev 2 #2). Recomputed from source, never the self-declared value.
import hashlib
import os
from pathlib import Path

from cx_common import findings_report, load_yaml, field_present, safe_repo_ref
from cx_deck import _compute_packet_hash, _compute_substantive_source_hash
# Single-source the cross-family taxonomy + three-leg-ask placeholder set from their existing canonical
# homes (cx_blueprint / cx_card) — NOT a second divergent copy (P-PROP-006 xfam continuity). The dispatcher
# imports both before this module, so there is no import cycle.
from cx_blueprint import VALID_FAMILIES, _family_group
from cx_card import TLA_PLACEHOLDERS

# Every field a whole_packet_review receipt must pin (auditable, non-forgeable).
# Note: reviewed_source_set_hash is intentionally absent here — the currency block (PB-PROP-002)
# handles blank/missing with its own specific error id (WHOLE-PACKET-REVIEW-SUBSTANTIVE-HASH-PRESENT).
REQUIRED_KEYS = ("schema_version", "review_kind", "frozen_packet_hash",
                 "authoring_family", "reviewer_family", "three_leg_ask", "verdict", "findings_ref")
VALID_VERDICTS = {"PASS", "FIX_FIRST_RESOLVED"}
REVIEW_KIND = "WHOLE_PACKET_G7"
# The three legs of the PBF-PROP-009 review ask (mirrors cx_card.TLA_LEGS keys).
TLA_LEGS = ("continuity", "problems", "approach_improvement")


def _sha12(path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def cmd_whole_packet_review(args) -> int:
    state_path = getattr(args, "state", None)
    packet_dir_arg = getattr(args, "packet_dir", None)
    repo_root_arg = getattr(args, "repo_root", None)
    findings = []

    if not state_path:
        print("FIX-FIRST\n  [P0] --state required for cx check whole-packet-review")
        return 1
    if not packet_dir_arg:
        print("FIX-FIRST\n  [P0] --packet-dir required (the frozen packet whose hash binds the review)")
        return 1
    if not repo_root_arg:
        print("FIX-FIRST\n  [P0] --repo-root required (the receipt ref resolves under it)")
        return 1

    state, serr = load_yaml(state_path)
    if serr or not isinstance(state, dict):
        print(f"FIX-FIRST\n  [P0] {state_path} — {serr or 'not a YAML mapping'}")
        return 1

    packet_dir = Path(packet_dir_arg)
    if not packet_dir.is_dir():
        print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — packet-dir not found or not a directory")
        return 1
    if packet_dir.is_symlink():
        print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — packet-dir is a symlink (fail-closed, P-PROP-006)")
        return 1

    # --packet-dir must live INSIDE --repo-root, with NO symlink in the path chain (mirrors
    # cx_module_start._symlink_in_path_chain). Otherwise the standalone G7 floor would bind the review
    # to an arbitrary EXTERNAL packet — a receipt for a non-project packet could green-light the build
    # (P-PROP-006 xfam P1). The build-turn rail already resolves packet_dir under repo-root; this hardens
    # the standalone gate to the same bar. The chain is bounded to BELOW repo-root, so a symlink ABOVE
    # the repo (e.g. macOS /tmp -> /private/tmp) is never flagged.
    root_abs = Path(os.path.abspath(repo_root_arg))
    pkt_abs = Path(os.path.abspath(packet_dir_arg))
    try:
        rel_chain = pkt_abs.relative_to(root_abs)
    except ValueError:
        print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — --packet-dir is not under --repo-root "
              f"'{repo_root_arg}'; the frozen packet must live inside the repo (P-PROP-006)")
        return 1
    _cur = root_abs
    for _part in rel_chain.parts:
        _cur = _cur / _part
        if _cur.is_symlink():
            print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — path component '{_cur}' is a symlink; no "
                  "symlink may appear between the repo root and the frozen packet (it would point the "
                  "packet at content OUTSIDE the repo) (P-PROP-006)")
            return 1

    repo = Path(repo_root_arg)

    # The receipt pointer lives in state, OUTSIDE the frozen packet (writing a review never mutates the
    # packet hash — the B-PROP-008 · B-PROP-010 pattern). A module-advancing build with no pointer is fail-closed:
    # the whole-packet integration review is a G7 build-authorization precondition, not optional.
    blk = state.get("whole_packet_review_receipt")
    if not isinstance(blk, dict):
        findings.append(("P0", state_path,
            "whole_packet_review_receipt missing — the whole-packet cross-family INTEGRATION review is a "
            "mandatory G7 build-authorization precondition (the cross-document coherence pass the per-card "
            "audit + the deterministic checker structurally cannot provide). Building without its bound "
            "receipt is forbidden (P-PROP-006)"))
        return findings_report(findings)

    receipt_ref = str(blk.get("receipt", "") or "").strip()
    receipt_hash = str(blk.get("receipt_hash", "") or "").strip()
    if not receipt_ref or not receipt_hash:
        findings.append(("P0", state_path,
            "whole_packet_review_receipt must carry a bound receipt + receipt_hash — missing either field "
            "blocks build (a stale/fabricated review cannot be detected without the hash) (P-PROP-006)"))
        return findings_report(findings)

    # final-ready-grade path-safety on the model/state-authored ref (shared guard, the B-PROP-011 class):
    # absolute / '..' / symlink / resolved-escape — the gate reads only an in-repo receipt.
    safe_receipt, perr = safe_repo_ref(receipt_ref, repo)
    if perr:
        findings.append(("P0", state_path,
            f"whole_packet_review_receipt.receipt '{receipt_ref}' {perr} (P-PROP-006)"))
        return findings_report(findings)
    if not safe_receipt.is_file():
        findings.append(("P0", state_path,
            f"whole_packet_review_receipt.receipt '{receipt_ref}' does not exist under the repo — the "
            "receipt must exist to prove the whole-packet review happened (P-PROP-006)"))
        return findings_report(findings)

    actual = _sha12(str(safe_receipt))
    if actual != receipt_hash:
        findings.append(("P0", state_path,
            f"whole_packet_review_receipt.receipt_hash {receipt_hash} != the receipt file's sha12 "
            f"{actual} — a fabricated/stale receipt blocks build (mirrors the Andon binding) (P-PROP-006)"))
        return findings_report(findings)

    rdoc, rerr = load_yaml(str(safe_receipt))
    review = rdoc.get("whole_packet_review") if isinstance(rdoc, dict) else None
    if not isinstance(review, dict):
        findings.append(("P0", receipt_ref,
            f"receipt is not a typed whole_packet_review mapping ({rerr or 'wrong shape'}) — an arbitrary "
            "bound blob of bytes is not a review (P-PROP-006)"))
        return findings_report(findings)

    missing = [k for k in REQUIRED_KEYS if not field_present(review, k)]
    if missing:
        findings.append(("P0", receipt_ref,
            f"whole_packet_review missing {missing} — the review record must pin schema_version, "
            "review_kind, frozen_packet_hash, reviewed_source_set_hash, authoring + reviewer family, "
            "three_leg_ask, verdict and findings_ref (auditable, non-forgeable) (P-PROP-006)"))
        return findings_report(findings)

    if str(review.get("review_kind")) != REVIEW_KIND:
        findings.append(("P0", receipt_ref,
            f"whole_packet_review.review_kind '{review.get('review_kind')}' != {REVIEW_KIND} — this gate "
            "accepts only a WHOLE-PACKET G7 integration review, not a per-card / per-module review (P-PROP-006)"))

    # opposite-family — BOTH families must be KNOWN and their cross-family GROUPS must DIFFER. A bare
    # string-inequality is NOT enough (P-PROP-006 xfam P0): same-family ALIASES (authoring 'claude' vs
    # reviewer 'anthropic' — both the Anthropic group) and UNKNOWN families ('mistral') are not a
    # cross-family catch. Reuse the single-source taxonomy from cx_blueprint (VALID_FAMILIES +
    # _family_group). The whole point is the OPPOSITE family's blind-spot catch (a real project's TRD-vs-lock
    # drift was caught by GPT reviewing an Anthropic-authored packet).
    auth = str(review.get("authoring_family", "")).strip().lower()
    rev = str(review.get("reviewer_family", "")).strip().lower()
    if auth not in VALID_FAMILIES or rev not in VALID_FAMILIES:
        findings.append(("P0", receipt_ref,
            f"whole_packet_review authoring_family '{auth or '(missing)'}' / reviewer_family "
            f"'{rev or '(missing)'}' — both must be a KNOWN family {sorted(VALID_FAMILIES)}; an unknown "
            "family cannot be proven to be the opposite family (P-PROP-006)"))
    elif _family_group(auth) == _family_group(rev):
        findings.append(("P0", receipt_ref,
            f"whole_packet_review.reviewer_family '{rev}' is the SAME cross-family group as "
            f"authoring_family '{auth}' — a same-family review is not a cross-family review (an alias "
            "like claude/anthropic still fails); the whole-packet review must be by the OPPOSITE family "
            "(P-PROP-006)"))

    # verdict present + accepted — a missing verdict is not a silent pass; a raw FIX_FIRST / REJECTED blocks.
    verdict = str(review.get("verdict", "")).strip()
    if verdict not in VALID_VERDICTS:
        findings.append(("P0", receipt_ref,
            f"whole_packet_review.verdict '{verdict or '(missing)'}' is not PASS or FIX_FIRST_RESOLVED — "
            "build is authorized only when the whole-packet review PASSED, or every FIX_FIRST finding was "
            "folded + re-confirmed (a raw FIX_FIRST / REJECTED, or a missing verdict, blocks) (P-PROP-006)"))

    # three-leg ask (PBF-PROP-009) — must be a STRUCTURED record of all three legs (continuity / problems /
    # approach_improvement), each a non-placeholder string. A bare 'present' scalar is a placeholder —
    # exactly what the card review_dispatch rule rejects (cx_card.TLA_PLACEHOLDERS); the receipt must
    # not over-claim "the three-leg ask was made" on the strength of a placeholder (P-PROP-006 xfam P2).
    tla = review.get("three_leg_ask")
    if not isinstance(tla, dict):
        findings.append(("P0", receipt_ref,
            "whole_packet_review.three_leg_ask must be a mapping recording all three legs "
            "(continuity / problems / approach_improvement) — a bare scalar like 'present' is a "
            "placeholder, not proof the PBF-PROP-009 three-leg ask was made (P-PROP-006)"))
    else:
        for leg in TLA_LEGS:
            val = str(tla.get(leg, "")).strip()
            if not val or val.lower() in TLA_PLACEHOLDERS:
                findings.append(("P0", receipt_ref,
                    f"whole_packet_review.three_leg_ask.{leg} missing or placeholder ('{val}') — each "
                    "leg must record how it was asked/answered; placeholders are rejected (PBF-PROP-009 / "
                    "P-PROP-006)"))

    # currency — keys on SUBSTANTIVE-source hash (PB-PROP-002: build-metadata-only registry edits carry).
    # Recompute from --packet-dir; never trust self-declared values.
    try:
        real_substantive_hash = _compute_substantive_source_hash(packet_dir)
    except Exception as e:
        findings.append(("P0", packet_dir_arg,
            f"could not recompute the substantive-source hash: {e} (PB-PROP-002)"))
        return findings_report(findings)

    rec_sub = str(review.get("reviewed_source_set_hash", "") or "").strip().lower()
    if not rec_sub:
        findings.append(("P0", receipt_ref,
            "whole_packet_review.reviewed_source_set_hash missing — the receipt must record the "
            "substantive-source hash (WHOLE-PACKET-REVIEW-SUBSTANTIVE-HASH-PRESENT, PB-PROP-002)"))
    elif rec_sub != real_substantive_hash:
        findings.append(("P0", receipt_ref,
            f"whole_packet_review.reviewed_source_set_hash {rec_sub[:12] or '(missing)'}… != "
            f"recomputed substantive-source hash {real_substantive_hash[:12]}… — the review is STALE "
            "for a different SUBSTANTIVE packet doc (WHOLE-PACKET-REVIEW-SUBSTANTIVE-CURRENT, PB-PROP-002)"))

    # Defense-in-depth: detect build-metadata-only delta for observability (non-blocking).
    try:
        real_packet_hash = _compute_packet_hash(packet_dir)
        rec_packet = str(review.get("frozen_packet_hash", "") or "").strip().lower()
        if rec_packet and rec_packet != real_packet_hash:
            pass  # Build-metadata only delta — carried. No finding.
    except Exception:
        pass

    return findings_report(findings)
