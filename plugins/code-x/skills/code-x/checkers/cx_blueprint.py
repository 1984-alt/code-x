# cmd_blueprint: the per-module BLUEPRINT-READY gate (P-PROP-005, fold v1.18).
#
#   cx check blueprint <packet-dir> --module <id> --state <state.yaml> --approval <BLUEPRINT-APPROVAL.yaml>
#   cx check blueprint <packet-dir> --all   --state <state.yaml> --approval <BLUEPRINT-APPROVAL.yaml>
#
# The PLANNING-stage build-blocker. A module is BLUEPRINT-READY only when its plan is COMPLETE +
# CEO-approved + source-current + reviewed-where-required. The gate RECOMPUTES every claim from
# canonical sources — it NEVER trusts a written `finalized` flag, an HTML badge, or a manifest boolean.
#
# THE TWO ARTIFACTS (split by mutability — GPT review P1-1/P1-2):
#   - blueprint-manifest.yaml  — IMMUTABLE, INSIDE the frozen packet (the plan; NO approval/review
#     fields; NO self-referential packet-hash). Binding rides the existing frozen-packet content hash.
#   - BLUEPRINT-APPROVAL.yaml   — MUTABLE, OUTSIDE the packet (--approval), state-referenced; per-module
#     approval + review RECEIPTS, each hash-bound to {packet_hash, manifest_hash, approved_source_hash}.
#     Writing an approval NEVER mutates the packet hash (= the verify_app / live_slice_accept pattern).
#
# RECOMPUTE-FROM-SOURCE recipe (fail-closed, no symlinks; mirrors cx_deck / cx_lock_fidelity):
#   - packet_hash       = cx_deck._compute_packet_hash(packet_dir)  (the frozen-packet content hash)
#   - manifest_hash     = sha256 of blueprint-manifest.yaml bytes (the manifest is inside the packet,
#                         so it cannot store the hash of the packet that contains it — P1-2)
#   - anchor source_hash = sha256 over the anchored source SPAN (the named line range of `file`)
#   - approved_source_hash = sha256 over the module's coverage-complete anchor source_hashes (sorted
#                         by anchor_id, joined) — any change to any anchored span recomputes a
#                         different value → the approval auto-invalidates (BLUEPRINT-APPROVAL-CURRENT).
#
# HONEST SCOPE (stated, not hidden): HTML is decorative; source is the ground truth. source_hash proves
# the plan DIDN'T change since approval, not that it is CORRECT (the CEO + review own correctness).
# Anchor coverage is only as complete as its derivation sources. Generator faithfulness is bounded — a
# missing attribute/contract fails closed, it never invents behaviour. No new gate family — the
# build-blocker rides the v1.10 order wall (cx check module-start).
#
# READ-ONLY: never builds, routes actors, edits source, or writes a receipt (CHARTER §4).
import hashlib
from pathlib import Path

from cx_common import findings_report, load_yaml, nested_get, safe_repo_ref, resolve_risk_tier
from cx_deck import _compute_packet_hash

MANIFEST_NAME = "blueprint-manifest.yaml"
REGISTRY_NAME = "MODULE-REGISTRY.yaml"
REQUIREMENTS_NAME = "requirements-manifest.yaml"
CONTRACTS_NAME = "behaviour-contracts.yaml"
SCREENS_NAME = "screens-manifest.yaml"
SWEEP_NAME = "clarification-sweep.yaml"
CLARIFY_MARKER = "[NEEDS-CLARIFICATION"

VALID_KINDS = {"screen", "shared_logic"}
# The four G5 high-risk classes — review-required is DERIVED from the FROZEN registry risk_flags,
# never a manifest boolean (P1-5). A risk_flag in this set on a module makes its review_receipt mandatory.
REVIEW_REQUIRED_FLAGS = {"money", "auth", "login", "secrets", "shared_data", "shared-data-shape",
                         "shared_data_shape"}
# A behaviour contract must carry these four fields, each a non-placeholder string.
CONTRACT_FIELDS = ("tap_outcome", "state_change", "error_empty", "done_test_ref")
# A review receipt must carry these (P1-5); reviewed_source_hash must == approved_source_hash.
REVIEW_RECEIPT_STRING_FIELDS = ("reviewer_family", "three_leg_ask", "verdict", "reviewed_source_hash",
                                "review_ref")
VALID_VERDICTS = {"PASS", "FIX_FIRST", "REWORK"}
# Builder/reviewer family taxonomy. A review must be by the OPPOSITE family of the builder (P1-5 /
# CXBP-003) — a same-family review is a blind-spot, not a cross-family catch.
VALID_FAMILIES = {"anthropic", "claude", "gpt", "codex", "openai"}
_FAMILY_GROUP = {"anthropic": "anthropic", "claude": "anthropic",
                 "gpt": "gpt", "codex": "gpt", "openai": "gpt"}


def _family_group(name) -> str | None:
    """Normalize a family name to its cross-family GROUP (anthropic vs gpt). None if unknown."""
    return _FAMILY_GROUP.get(str(name or "").strip().lower())


# Open severity counters read from --state (the same shape cx check state validates).
_SEV_KEYS = ("p0", "p1", "p2", "p3")


def _is_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _safe_inside(packet_dir: Path, rel) -> Path | None:
    """Resolve rel INSIDE packet_dir; None on non-string / absolute / '..' escape / symlink /
    out-of-packet (fail-closed, mirrors cx_packet._resolve_inside + the no-symlink rule)."""
    if not isinstance(rel, str) or not rel:
        return None
    raw = Path(rel)
    if raw.is_absolute() or ".." in raw.parts:
        return None
    cand = packet_dir / raw
    try:
        if cand.is_symlink() or not cand.resolve().is_relative_to(packet_dir.resolve()):
            return None
    except OSError:
        return None
    return cand


def _span_hash(packet_dir: Path, file_rel, line) -> tuple[str | None, str | None]:
    """sha256 over the anchored source SPAN. The span = the single source LINE named by `line`
    (1-based) of `file`, recomputed from the live bytes. Returns (hex_digest, None) or (None, reason).
    A whole-file anchor (line is None / 0) hashes the whole file. Fail-closed: an unresolvable file,
    an out-of-range line, or a symlink yields a reason (the anchor cannot resolve)."""
    target = _safe_inside(packet_dir, file_rel)
    if target is None:
        return None, (f"anchor file '{file_rel}' does not resolve to a real, in-packet, non-symlink "
                      "source path (fail-closed)")
    if not target.is_file():
        return None, f"anchor file '{file_rel}' is not a file in the packet (fail-closed)"
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return None, f"anchor file '{file_rel}' unreadable: {e}"
    if line in (None, 0, "0"):
        span = text
    else:
        try:
            ln = int(line)
        except (TypeError, ValueError):
            return None, f"anchor line '{line}' is not an integer (fail-closed)"
        lines = text.splitlines()
        if ln < 1 or ln > len(lines):
            return None, (f"anchor line {ln} is out of range for '{file_rel}' "
                          f"({len(lines)} lines) — the span does not resolve (fail-closed)")
        span = lines[ln - 1]
    return hashlib.sha256(span.encode("utf-8")).hexdigest(), None


def _derive_expected_anchor_ids(reg_module: dict, mid: str, screen_id: str, kind: str,
                                contracts: dict, screen_nav: dict, risk_tier: str = "STRICT") -> set:
    """The EXPECTED anchor-id set for a module, DERIVED from sources INDEPENDENT of the manifest field
    being validated (CXBP-001 — the circularity fix). NEVER reads module.controls / module.nav (those
    are exactly what coverage must prove complete):
      - requirements: the FROZEN REGISTRY row (reg_module.requirement_ids) — canonical.
      - controls (screen): every behaviour-contracts.yaml entry SCOPED to this screen/module (each
        contract carries a `control_id` + a `screen`/`module_id` scope). A screen that omits a control
        the contracts source declares now FAILS coverage (so CONTROL-HAS-CONTRACT actually iterates it).
      - nav edges (screen): every nav edge the INDEPENDENT screens-manifest declares for this screen
        (screen_nav[screen_id] = list of to_screen ids). A manifest that omits a declared nav row fails.
    The manifest's declared anchor set must EQUAL this (no missing, no extra). Anchor ids:
    req:<id> / control:<id> / nav:<from>-><to>. Coverage is only as complete as these independent
    sources (honest limit).

    PBF-PROP-019 Phase 3 (design v2.B row 6, blueprint_depth): a LITE-tier project's expected set
    keeps req:/nav: (the "nav-map + done-test" floor) but DROPS control: — the full behaviour-contract
    anchors — since LITE also does not require BLUEPRINT-CONTROL-HAS-CONTRACT (see _validate_module).
    STANDARD/STRICT are unchanged (risk_tier default "STRICT" preserves today's behaviour byte-for-byte
    for any caller that doesn't pass risk_tier)."""
    expected = set()
    # requirements are CANONICAL: derived from the frozen registry row, not the manifest.
    for rid in (reg_module.get("requirement_ids") or []):
        if rid:
            expected.add(f"req:{rid}")
    if kind == "screen":
        scope_ids = {mid}
        if screen_id:
            scope_ids.add(screen_id)
        if risk_tier != "LITE":
            # controls: INDEPENDENT — from the behaviour-contracts source, scoped to this screen/module.
            for ctr in contracts.values():
                if not isinstance(ctr, dict):
                    continue
                scope = str(ctr.get("screen", "") or ctr.get("module_id", "") or "").strip()
                cid = str(ctr.get("control_id", "") or "").strip()
                if cid and scope in scope_ids:
                    expected.add(f"control:{cid}")
        # nav: INDEPENDENT — from the screens-manifest's declared edges for this screen.
        sid = screen_id or mid
        for to in (screen_nav.get(sid) or []):
            to = str(to).strip()
            if to:
                expected.add(f"nav:{sid}->{to}")
    return expected


def _validate_module(packet_dir: Path, manifest: dict, module: dict, mloc: str,
                     reg_module: dict, approval_block, state, findings: list,
                     reg_index: dict, screen_nav: dict, builder_family: str,
                     approval_root: Path, risk_tier: str = "STRICT") -> None:
    """Recompute + validate ONE module against canonical sources. Appends findings.

    risk_tier (PBF-PROP-019 Phase 3, design v2.B row 6): default "STRICT" preserves today's
    behaviour byte-for-byte for any caller that doesn't pass it."""
    mid = str(module.get("module_id", "") or "").strip()
    kind = str(module.get("kind", "") or "").strip()
    screen_id = str(module.get("screen_id", "") or "").strip()
    # behaviour-contracts (independent control source — loaded once, used by coverage + CONTROL clause).
    contracts = _load_contracts(packet_dir)

    # BLUEPRINT-PER-KIND-FIELDS (P1): kind must be valid; per-kind required field set enforced; a
    # screen-only field N/A on shared_logic must carry an explicit reason, never a silent skip.
    if kind not in VALID_KINDS:
        findings.append(("P1", mloc,
            f"module '{mid}' kind '{kind or '(missing)'}' is not one of {sorted(VALID_KINDS)} — "
            "every buildable module declares its kind so the gate enforces the per-kind field set "
            "(BLUEPRINT-PER-KIND-FIELDS, P-PROP-005)"))
        return
    if kind == "screen":
        for fld in ("controls", "nav"):
            if module.get(fld) is None:
                findings.append(("P1", mloc,
                    f"screen module '{mid}' omits required '{fld}' — a screen kind requires "
                    "design+nav+controls; a missing field set is a silent skip "
                    "(BLUEPRINT-PER-KIND-FIELDS, P-PROP-005)"))
    else:  # shared_logic — design+nav are N/A, but the skip must be written, never silent.
        na = module.get("design_nav_na_reason")
        if not _is_str(na):
            findings.append(("P1", mloc,
                f"shared_logic module '{mid}' omits 'design_nav_na_reason' — design+nav are N/A for a "
                "shared_logic kind but the skip must carry an explicit reason, never be silent "
                "(BLUEPRINT-PER-KIND-FIELDS, P-PROP-005)"))

    # ── anchors: recompute every span hash + coverage ──────────────────────────────────────────
    anchors = module.get("anchors")
    declared_ids = []
    anchor_by_id = {}
    if not isinstance(anchors, list):
        findings.append(("P1", mloc,
            f"module '{mid}' has no 'anchors' list — every visible blueprint item must carry a stable "
            "source anchor (BLUEPRINT-ANCHOR-RESOLVES, P-PROP-005)"))
        anchors = []
    for j, a in enumerate(anchors):
        aloc = f"{mloc}#anchors[{j}]"
        if not isinstance(a, dict):
            findings.append(("P1", aloc, "anchor row is not a mapping (P-PROP-005)"))
            continue
        aid = str(a.get("anchor_id", "") or "").strip()
        if not aid:
            findings.append(("P1", aloc, "anchor row has no anchor_id (P-PROP-005)"))
            continue
        declared_ids.append(aid)
        anchor_by_id[aid] = a
        # BLUEPRINT-ANCHOR-RESOLVES (P1): recompute the span hash; it must equal the declared source_hash.
        recomputed, rerr = _span_hash(packet_dir, a.get("file"), a.get("line"))
        if rerr:
            findings.append(("P1", aloc,
                f"anchor '{aid}' does not resolve: {rerr} (BLUEPRINT-ANCHOR-RESOLVES, P-PROP-005)"))
            continue
        declared = str(a.get("source_hash", "") or "").strip().lower()
        if declared != recomputed:
            findings.append(("P1", aloc,
                f"anchor '{aid}' source_hash mismatch: declared {declared[:12] or '(missing)'}…, "
                f"recomputed {recomputed[:12]}… — the anchored source span changed since the manifest "
                "was generated (BLUEPRINT-ANCHOR-RESOLVES, P-PROP-005)"))

    # BLUEPRINT-ANCHOR-COVERAGE (P0): declared anchor set must EQUAL the expected set derived from
    # canonical sources — a missing OR a duplicate anchor fails.
    dupes = sorted({x for x in declared_ids if declared_ids.count(x) > 1})
    if dupes:
        findings.append(("P0", mloc,
            f"module '{mid}' has duplicate anchor_id(s) {dupes} — a duplicate lets an incomplete "
            "manifest still hash cleanly (BLUEPRINT-ANCHOR-COVERAGE, P-PROP-005)"))
    expected = _derive_expected_anchor_ids(reg_module, mid, screen_id, kind, contracts, screen_nav, risk_tier)
    declared_set = set(declared_ids)
    missing_anchors = sorted(expected - declared_set)
    if missing_anchors:
        findings.append(("P0", mloc,
            f"module '{mid}' anchor set is INCOMPLETE — missing {missing_anchors} expected from "
            "MODULE-REGISTRY + requirements + controls + nav; an omitted requirement/control that "
            "still hashes clean is exactly the hole this clause closes "
            "(BLUEPRINT-ANCHOR-COVERAGE, P-PROP-005)"))
    # extra anchors not derivable from any canonical source = the manifest fabricated an item.
    extra_anchors = sorted(declared_set - expected)
    if extra_anchors:
        findings.append(("P0", mloc,
            f"module '{mid}' declares anchor(s) {extra_anchors} not derivable from any canonical "
            "source (registry/requirements/controls/nav) — the anchor set must EQUAL the expected set "
            "(BLUEPRINT-ANCHOR-COVERAGE, P-PROP-005)"))

    # ── BLUEPRINT-SCREEN-DESIGN-LOCKED (P1): each screen module has a hash-bound ui_lock_manifest ──
    if kind == "screen":
        lock_ref = module.get("ui_lock_manifest")
        lock_target = _safe_inside(packet_dir, lock_ref) if lock_ref else None
        if not lock_ref or lock_target is None or not lock_target.is_file():
            findings.append(("P1", mloc,
                f"screen module '{mid}' has no hash-bound, in-packet ui_lock_manifest — a screen's "
                "design must be locked (style+provenance) before it is buildable "
                "(BLUEPRINT-SCREEN-DESIGN-LOCKED, P-PROP-005)"))
        else:
            declared_lock = str(module.get("ui_lock_hash", "") or "").strip().lower()
            actual_lock = hashlib.sha256(lock_target.read_bytes()).hexdigest()
            if declared_lock != actual_lock:
                findings.append(("P1", mloc,
                    f"screen module '{mid}' ui_lock_hash mismatch: declared {declared_lock[:12] or '(missing)'}…, "
                    f"actual {actual_lock[:12]}… — the locked design is not hash-bound to the manifest "
                    "(BLUEPRINT-SCREEN-DESIGN-LOCKED, P-PROP-005)"))
            else:
                # INTERACTIVE-CHROME-HAS-BEHAVIOR-CONTRACT (P1, PBF-PROP-020 Rule 6b): a lock
                # flagged interactive_chrome: yes (nav shells, scroll strips, sticky bars) must
                # carry a behavior_contract {fixed, scrolls, bounces} — "feel never written down"
                # is the a live-production app's nav-shell drift cause this closes.
                lock_raw, _lock_err = load_yaml(str(lock_target))
                lock_body = (lock_raw.get("ui_lock_manifest") if isinstance(lock_raw, dict)
                            and isinstance(lock_raw.get("ui_lock_manifest"), dict) else lock_raw)
                interactive = isinstance(lock_body, dict) and str(
                    lock_body.get("interactive_chrome", "") or "").strip().lower() in ("yes", "true")
                if interactive:
                    bc = lock_body.get("behavior_contract")
                    if not isinstance(bc, dict) or not all(
                            _is_str(bc.get(k)) for k in ("fixed", "scrolls", "bounces")):
                        findings.append(("P1", mloc,
                            f"screen module '{mid}' lock '{lock_ref}' is flagged interactive_chrome: "
                            "yes but carries no complete behavior_contract {fixed, scrolls, bounces} "
                            "— the feel of a nav shell/scroll strip/sticky bar must be written down, "
                            "not left to builder judgment "
                            "(INTERACTIVE-CHROME-HAS-BEHAVIOR-CONTRACT, PBF-PROP-020 Rule 6b)"))

    # ── BLUEPRINT-NAV-COMPLETE (P1): every nav to_screen resolves to a screen REGISTERED IN THE FROZEN
    #    REGISTRY (or the independent screens-manifest) — NEVER a manifest-only row (CXBP-002). A fake
    #    manifest-only `ghostscreen` can no longer satisfy a dangling target. ──
    if kind == "screen":
        registered = set()
        for m in reg_index.values():
            if isinstance(m, dict):
                if m.get("module_id"):
                    registered.add(str(m.get("module_id")).strip())
                if m.get("screen_id"):
                    registered.add(str(m.get("screen_id")).strip())
        registered |= set(screen_nav.keys())  # screens declared in the independent screens-manifest
        for n in (module.get("nav") or []):
            if not isinstance(n, dict):
                continue
            to = str(n.get("to_screen", "") or "").strip()
            if to and to not in registered:
                findings.append(("P1", mloc,
                    f"screen module '{mid}' nav target '{to}' is a dangling screen — it resolves to no "
                    "screen registered in the frozen MODULE-REGISTRY or screens-manifest (a manifest-only "
                    "row never satisfies it) (BLUEPRINT-NAV-COMPLETE, P-PROP-005)"))

    # ── BLUEPRINT-CONTROL-HAS-CONTRACT (P1): every control_id resolves to a full behaviour contract ──
    # PBF-PROP-019 Phase 3 (design v2.B row 6, blueprint_depth): LITE drops the full behaviour-
    # contract requirement (nav-map + done-test is the LITE floor, enforced separately below by
    # BLUEPRINT-NAV-COMPLETE + BLUEPRINT-FEATURE-HAS-DONE-TEST, which this tier read does NOT touch).
    # STANDARD/STRICT are unchanged.
    if kind == "screen" and risk_tier != "LITE":
        for c in (module.get("controls") or []):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("control_id", "") or "").strip()
            ctr_id = str(c.get("contract_id", "") or "").strip()
            if not ctr_id:
                findings.append(("P1", mloc,
                    f"control '{cid or '(unnamed)'}' on module '{mid}' carries no contract_id — a "
                    "control needs a behaviour contract, not just a label "
                    "(BLUEPRINT-CONTROL-HAS-CONTRACT, P-PROP-005)"))
                continue
            ctr = contracts.get(ctr_id)
            if not isinstance(ctr, dict):
                findings.append(("P1", mloc,
                    f"control '{cid}' contract_id '{ctr_id}' does not resolve in {CONTRACTS_NAME} — "
                    "the generator never synthesizes a contract from a data-fn attribute "
                    "(BLUEPRINT-CONTROL-HAS-CONTRACT, P-PROP-005)"))
                continue
            miss = [f for f in CONTRACT_FIELDS if not _is_str(ctr.get(f))]
            if miss:
                findings.append(("P1", mloc,
                    f"control '{cid}' contract '{ctr_id}' missing/placeholder {miss} — a behaviour "
                    "contract needs tap_outcome+state_change+error_empty+done_test_ref "
                    "(BLUEPRINT-CONTROL-HAS-CONTRACT, P-PROP-005)"))
                continue
            # the done_test_ref must resolve to an acceptance_criterion (done-test).
            if not _done_test_resolves(packet_dir, ctr.get("done_test_ref")):
                findings.append(("P1", mloc,
                    f"control '{cid}' contract '{ctr_id}' done_test_ref '{ctr.get('done_test_ref')}' "
                    "does not resolve to a BUILDING requirement's acceptance_criterion "
                    "(BLUEPRINT-CONTROL-HAS-CONTRACT, P-PROP-005)"))

    # ── BLUEPRINT-FEATURE-HAS-DONE-TEST (P1): every BUILDING req in the module has a done-test ──
    building_reqs = _building_reqs_for_module(packet_dir, reg_module)
    ac_ids = _reqs_with_acceptance(packet_dir)
    for rid in sorted(building_reqs):
        if rid not in ac_ids:
            findings.append(("P1", mloc,
                f"module '{mid}' BUILDING requirement '{rid}' has no acceptance_criterion done-test in "
                f"{REQUIREMENTS_NAME} — every feature needs a written 'done' test "
                "(BLUEPRINT-FEATURE-HAS-DONE-TEST, P-PROP-005)"))

    # ── BLUEPRINT-NO-OPEN-CLARIFICATION (P1): no surviving marker in the module scope ──
    for a in anchors:
        if not isinstance(a, dict):
            continue
        tgt = _safe_inside(packet_dir, a.get("file"))
        if tgt is None or not tgt.is_file():
            continue
        if CLARIFY_MARKER in tgt.read_text(encoding="utf-8", errors="replace"):
            findings.append(("P1", mloc,
                f"module '{mid}' anchored source '{a.get('file')}' carries an unresolved "
                f"'{CLARIFY_MARKER}: …]' marker — an open question blocks readiness "
                "(BLUEPRINT-NO-OPEN-CLARIFICATION, P-PROP-005)"))
            break

    # ── recompute the module's approved_source_hash from its coverage-complete anchor source_hashes ──
    # (sorted by anchor_id, joined). This is what the approval receipt must equal.
    recomputed_module_hash = _module_source_hash(anchor_by_id)

    # ── approval + review receipts (read from --approval, OUTSIDE the packet) ──────────────────
    receipt = None
    if isinstance(approval_block, dict):
        for r in (approval_block.get("modules") or []):
            if isinstance(r, dict) and str(r.get("module_id", "")).strip() == mid:
                receipt = r
                break

    # BLUEPRINT-APPROVAL-CURRENT (P0): a ceo_approval present AND approved_source_hash == recomputed.
    if receipt is None or not isinstance(receipt.get("ceo_approval"), dict):
        findings.append(("P0", mloc,
            f"module '{mid}' has no CEO approval receipt in the --approval file — a module is not "
            "BLUEPRINT-READY without a present, source-current CEO approval "
            "(BLUEPRINT-APPROVAL-CURRENT, P-PROP-005)"))
    else:
        approved_hash = str(receipt.get("approved_source_hash", "") or "").strip().lower()
        if approved_hash != recomputed_module_hash:
            findings.append(("P0", mloc,
                f"module '{mid}' approval is STALE: approved_source_hash {approved_hash[:12] or '(missing)'}…"
                f" != recomputed current source-hash {recomputed_module_hash[:12]}… — a plan edit after "
                "approval auto-invalidates it; the CEO must re-approve "
                "(BLUEPRINT-APPROVAL-CURRENT, P-PROP-005)"))

    # BLUEPRINT-REVIEW-RECEIPT (P1): review-required DERIVED from the FROZEN registry risk_flags.
    reg_flags = {str(f).strip().lower() for f in (reg_module.get("risk_flags") or [])}
    if reg_flags & REVIEW_REQUIRED_FLAGS:
        rr = receipt.get("review_receipt") if isinstance(receipt, dict) else None
        if not isinstance(rr, dict):
            findings.append(("P1", mloc,
                f"module '{mid}' is registry-risk-flagged ({sorted(reg_flags & REVIEW_REQUIRED_FLAGS)}) "
                "but carries no typed review_receipt — a manifest boolean never satisfies it; an "
                "opposite-family review receipt is mandatory (BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
        else:
            miss = [f for f in REVIEW_RECEIPT_STRING_FIELDS if not _is_str(rr.get(f))]
            if miss:
                findings.append(("P1", mloc,
                    f"module '{mid}' review_receipt missing/blank {miss} — needs reviewer_family + "
                    "three_leg_ask + verdict + reviewed_source_hash + review_ref "
                    "(BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
            else:
                verdict = str(rr.get("verdict", "")).strip().upper()
                if verdict not in VALID_VERDICTS:
                    findings.append(("P1", mloc,
                        f"module '{mid}' review_receipt verdict '{verdict}' is not one of "
                        f"{sorted(VALID_VERDICTS)} (BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
                elif verdict != "PASS":
                    findings.append(("P1", mloc,
                        f"module '{mid}' review_receipt verdict is '{verdict}' (not PASS) — an "
                        "unresolved review does not authorize the build (BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
                rsh = str(rr.get("reviewed_source_hash", "")).strip().lower()
                if rsh != recomputed_module_hash:
                    findings.append(("P1", mloc,
                        f"module '{mid}' review_receipt reviewed_source_hash {rsh[:12] or '(missing)'}… "
                        f"!= recomputed current source-hash {recomputed_module_hash[:12]}… — the review "
                        "was of an older plan; re-review the current source "
                        "(BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
                # CXBP-003: review_ref must be path-safe (no symlink/escape) AND the review file must
                # EXIST — a non-existent or escaping review_ref is not a review.
                review_ref = str(rr.get("review_ref", "")).strip()
                safe_ref, ref_err = safe_repo_ref(review_ref, approval_root)
                if ref_err:
                    findings.append(("P1", mloc,
                        f"module '{mid}' review_receipt review_ref '{review_ref}' {ref_err} "
                        "(BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
                elif not safe_ref.is_file():
                    findings.append(("P1", mloc,
                        f"module '{mid}' review_receipt review_ref '{review_ref}' resolves to no real "
                        "review file next to the approval — a missing review file is not a review "
                        "(BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
                # CXBP-003: reviewer_family must be the OPPOSITE cross-family group of the builder —
                # a same-family review is a blind-spot, not a cross-family catch (P1-5).
                rev_group = _family_group(rr.get("reviewer_family"))
                bld_group = _family_group(builder_family)
                if rev_group is None:
                    findings.append(("P1", mloc,
                        f"module '{mid}' review_receipt reviewer_family '{rr.get('reviewer_family')}' is "
                        f"not a known family {sorted(VALID_FAMILIES)} (BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
                elif bld_group is None:
                    findings.append(("P1", mloc,
                        f"module '{mid}': the builder_family '{builder_family or '(missing)'}' on the "
                        "approval is unknown/absent — the gate cannot prove the review is opposite-family "
                        "(fail-closed, BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))
                elif rev_group == bld_group:
                    findings.append(("P1", mloc,
                        f"module '{mid}' review_receipt reviewer_family '{rr.get('reviewer_family')}' is "
                        f"the SAME cross-family group as the builder '{builder_family}' — a review must be "
                        "by the OPPOSITE family (a same-family review is a blind-spot) "
                        "(BLUEPRINT-REVIEW-RECEIPT, P-PROP-005)"))

    # BLUEPRINT-NO-HIDDEN-SEVERITY (P1): no open P0–P3 mapped to the module (fail-closed to global).
    _check_hidden_severity(state, mid, mloc, findings)


def _module_source_hash(anchor_by_id: dict) -> str:
    """The module's approved_source_hash = sha256 over its coverage-complete anchor source_hashes,
    sorted by anchor_id and joined. Recomputed here so a stale/forged approved_source_hash is caught."""
    parts = []
    for aid in sorted(anchor_by_id):
        a = anchor_by_id[aid]
        parts.append(f"{aid}:{str(a.get('source_hash', '') or '').strip().lower()}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _load_contracts(packet_dir: Path) -> dict:
    """contract_id -> contract dict, from the packet-source behaviour-contracts.yaml."""
    data, err = load_yaml(str(packet_dir / CONTRACTS_NAME))
    block = nested_get(data, "behaviour_contracts") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        # also accept a top-level mapping of contract_id -> contract
        block = data if isinstance(data, dict) else {}
    out = {}
    rows = block.get("contracts") if isinstance(block, dict) and isinstance(block.get("contracts"), list) else None
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and r.get("contract_id"):
                out[str(r.get("contract_id"))] = r
    elif isinstance(block, dict):
        for k, v in block.items():
            if isinstance(v, dict):
                out[str(k)] = v
    return out


def _requirements_index(packet_dir: Path) -> dict:
    """requirement_id -> row, from requirements-manifest.yaml."""
    data, err = load_yaml(str(packet_dir / REQUIREMENTS_NAME))
    rows = data.get("requirements") if isinstance(data, dict) else None
    out = {}
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and r.get("id"):
                out[str(r.get("id"))] = r
    return out


def _building_reqs_for_module(packet_dir: Path, reg_module: dict) -> set:
    """The BUILDING requirement ids the registry maps to this module."""
    idx = _requirements_index(packet_dir)
    out = set()
    for rid in (reg_module.get("requirement_ids") or []):
        rid = str(rid)
        row = idx.get(rid)
        if isinstance(row, dict) and str(row.get("disposition", "")).strip() == "BUILDING":
            out.add(rid)
    return out


def _reqs_with_acceptance(packet_dir: Path) -> set:
    """requirement ids that carry a non-placeholder acceptance_criterion (done-test)."""
    idx = _requirements_index(packet_dir)
    out = set()
    for rid, row in idx.items():
        ac = row.get("acceptance_criterion")
        if isinstance(ac, dict) and _is_str(ac.get("pass_condition")) and _is_str(ac.get("evidence_type")):
            out.add(rid)
    return out


def _done_test_resolves(packet_dir: Path, ref) -> bool:
    """A contract's done_test_ref must name a requirement with an acceptance_criterion."""
    if not _is_str(ref):
        return False
    return str(ref).strip() in _reqs_with_acceptance(packet_dir)


def _check_hidden_severity(state, mid: str, mloc: str, findings: list) -> None:
    """BLUEPRINT-NO-HIDDEN-SEVERITY (P1): no open P0–P3 finding mapped to this module. A finding with
    NO module attribution fails CLOSED to global (blocks every module). Read from --state.

    CXBP-004 (fail-CLOSED on malformed state): the check REQUIRES a well-formed `open_findings`
    mapping — `counts` a mapping with integer p0..p3 + `items` a list. A missing/malformed
    open_findings, a non-integer count, or a non-list items DOES NOT silently become an empty,
    passing state — it is a P1 (the gate cannot prove there is no hidden open severity)."""
    if not isinstance(state, dict):
        findings.append(("P1", mloc,
            f"module '{mid}': --state did not load as a mapping — the hidden-severity check requires "
            "--state to read open findings (fail-closed, BLUEPRINT-NO-HIDDEN-SEVERITY, P-PROP-005)"))
        return
    of = state.get("open_findings")
    if not isinstance(of, dict):
        findings.append(("P1", mloc,
            f"module '{mid}': state.open_findings is missing or not a mapping — the gate cannot prove "
            "there is no open severity mapped to this module (fail-closed, BLUEPRINT-NO-HIDDEN-SEVERITY, "
            "P-PROP-005)"))
        return
    counts = of.get("counts")
    if not isinstance(counts, dict):
        findings.append(("P1", mloc,
            f"module '{mid}': state.open_findings.counts is missing or not a mapping {{p0..p3}} — a "
            "severity tally that cannot be read fails CLOSED (BLUEPRINT-NO-HIDDEN-SEVERITY, P-PROP-005)"))
        return
    items = of.get("items")
    if not isinstance(items, list):
        findings.append(("P1", mloc,
            f"module '{mid}': state.open_findings.items is missing or not a list — without an itemized "
            "list a non-zero count has no attribution to disprove (fail-closed, "
            "BLUEPRINT-NO-HIDDEN-SEVERITY, P-PROP-005)"))
        return
    open_total = 0
    bad_count = False
    for k in _SEV_KEYS:
        v = counts.get(k, 0)
        if isinstance(v, bool) or not isinstance(v, int):
            bad_count = True
            continue
        open_total += v
    if bad_count:
        findings.append(("P1", mloc,
            f"module '{mid}': state.open_findings.counts has a non-integer p0..p3 value — an "
            "unparseable severity tally fails CLOSED (BLUEPRINT-NO-HIDDEN-SEVERITY, P-PROP-005)"))
        return
    for it in items:
        if not isinstance(it, dict):
            continue
        sev = str(it.get("severity", "") or "").strip().upper()
        if sev not in ("P0", "P1", "P2", "P3"):
            continue
        item_mod = str(it.get("module_id", "") or it.get("module", "") or "").strip()
        if not item_mod:
            findings.append(("P1", mloc,
                f"module '{mid}': an open {sev} finding has NO module attribution — it fails CLOSED to "
                "global and blocks every module until attributed/resolved "
                "(BLUEPRINT-NO-HIDDEN-SEVERITY, P-PROP-005)"))
        elif item_mod == mid:
            findings.append(("P1", mloc,
                f"module '{mid}' has an open {sev} finding mapped to it — a module with an open finding "
                "is not BLUEPRINT-READY (BLUEPRINT-NO-HIDDEN-SEVERITY, P-PROP-005)"))
    # counts > itemized findings => a hidden severity with no attribution (fail-closed).
    if open_total > len([i for i in items if isinstance(i, dict)
                         and str(i.get("severity", "")).strip().upper() in ("P0", "P1", "P2", "P3")]):
        findings.append(("P1", mloc,
            f"module '{mid}': open_findings.counts report {open_total} open finding(s) but fewer are "
            "itemized — an un-itemized open severity has no module attribution and fails CLOSED "
            "(BLUEPRINT-NO-HIDDEN-SEVERITY, P-PROP-005)"))


def cmd_blueprint(args) -> int:
    packet_dir_arg = getattr(args, "packet_dir", None)
    if not packet_dir_arg:
        print("FIX-FIRST\n  [P0] packet-dir required for cx check blueprint")
        return 1
    packet_dir = Path(packet_dir_arg)
    if not packet_dir.is_dir():
        print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — packet-dir not found or not a directory")
        return 1
    if packet_dir.is_symlink():
        print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — packet-dir is a symlink (fail-closed, P-PROP-005)")
        return 1

    # PBF-PROP-019 Phase 3 (design v2.B row 6, blueprint_depth): resolve the project risk_tier
    # directly from the same packet_dir the whole gate already reads (no new CLI wiring needed).
    risk_tier_val = resolve_risk_tier(packet_dir)

    module_arg = getattr(args, "module", None)
    do_all = getattr(args, "all", False)
    if not module_arg and not do_all:
        print("FIX-FIRST\n  [P0] --module <id> or --all required for cx check blueprint")
        return 1

    findings: list[tuple[str, str, str]] = []

    # ── load the immutable in-packet manifest ──────────────────────────────────────────────────
    manifest_path = packet_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        print(f"FIX-FIRST\n  [P0] {manifest_path} — the immutable blueprint-manifest.yaml is missing "
              "from the frozen packet (P-PROP-005)")
        return 1
    mdata, merr = load_yaml(str(manifest_path))
    bp = nested_get(mdata, "blueprint_manifest") if isinstance(mdata, dict) else None
    if merr or not isinstance(bp, dict) or not isinstance(bp.get("modules"), list):
        print(f"FIX-FIRST\n  [P0] {manifest_path} — not a typed blueprint_manifest with a 'modules' "
              f"list ({merr or 'wrong shape'}) (P-PROP-005)")
        return 1
    # the manifest must NOT store its own packet-hash (self-referential under _compute_packet_hash, P1-2).
    if bp.get("generated_from_packet_hash") is not None:
        findings.append(("P1", str(manifest_path),
            "blueprint-manifest carries a self-referential 'generated_from_packet_hash' — a file "
            "INSIDE the frozen packet cannot store the hash of the packet that contains it; binding "
            "rides the frozen-packet content hash + the external receipt (BLUEPRINT-MANIFEST-HASH-BOUND, "
            "P-PROP-005)"))

    # ── BLUEPRINT-MANIFEST-HASH-BOUND (P0): the --approval receipt's manifest_hash + packet_hash must
    #    equal the recomputed manifest + frozen-packet hashes ──────────────────────────────────────
    try:
        real_packet_hash = _compute_packet_hash(packet_dir)
    except Exception as e:
        print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — could not recompute frozen-packet hash: {e} (P-PROP-005)")
        return 1
    real_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    approval_path = getattr(args, "approval", None)
    approval_block = None
    approval_root = packet_dir.parent  # default; reset to the approval file's dir when present
    builder_family = ""
    if not approval_path:
        findings.append(("P0", "--approval",
            "--approval <BLUEPRINT-APPROVAL.yaml> required — the mutable approval/review receipts live "
            "OUTSIDE the frozen packet; without them readiness cannot be proven "
            "(BLUEPRINT-MANIFEST-HASH-BOUND, P-PROP-005)"))
    else:
        approval_root = Path(approval_path).resolve().parent
        adata, aerr = load_yaml(approval_path)
        approval_block = nested_get(adata, "blueprint_approval") if isinstance(adata, dict) else None
        if aerr or not isinstance(approval_block, dict):
            findings.append(("P0", approval_path,
                f"--approval is not a typed blueprint_approval mapping ({aerr or 'wrong shape'}) "
                "(BLUEPRINT-MANIFEST-HASH-BOUND, P-PROP-005)"))
            approval_block = None
        else:
            builder_family = str(approval_block.get("builder_family", "") or "").strip()
            rec_packet = str(approval_block.get("packet_hash", "") or "").strip().lower()
            rec_manifest = str(approval_block.get("manifest_hash", "") or "").strip().lower()
            if rec_packet != real_packet_hash:
                findings.append(("P0", approval_path,
                    f"approval packet_hash {rec_packet[:12] or '(missing)'}… != recomputed frozen-packet "
                    f"hash {real_packet_hash[:12]}… — a STALE receipt for a different packet "
                    "(BLUEPRINT-MANIFEST-HASH-BOUND, P-PROP-005)"))
            if rec_manifest != real_manifest_hash:
                findings.append(("P0", approval_path,
                    f"approval manifest_hash {rec_manifest[:12] or '(missing)'}… != recomputed manifest "
                    f"hash {real_manifest_hash[:12]}… — the receipt is bound to an older manifest "
                    "(BLUEPRINT-MANIFEST-HASH-BOUND, P-PROP-005)"))

    # ── load --state (required for BLUEPRINT-NO-HIDDEN-SEVERITY) ────────────────────────────────
    state_path = getattr(args, "state", None)
    state = None
    if not state_path:
        findings.append(("P1", "--state",
            "--state required — the gate reads open P0–P3 findings mapped to the module from state "
            "(BLUEPRINT-NO-HIDDEN-SEVERITY, P-PROP-005)"))
    else:
        sdata, serr = load_yaml(state_path)
        if serr or not isinstance(sdata, dict):
            findings.append(("P1", state_path, f"--state did not load: {serr or 'not a mapping'} (P-PROP-005)"))
        else:
            state = sdata

    # ── frozen registry (canonical) + screens-manifest nav (independent control/nav source) ────
    reg_index = _registry_index(packet_dir, findings)
    screen_nav = _screen_nav_index(packet_dir)

    # ── select module(s) ───────────────────────────────────────────────────────────────────────
    modules = [m for m in bp.get("modules") if isinstance(m, dict)]
    if module_arg:
        targets = [m for m in modules if str(m.get("module_id", "")).strip() == module_arg]
        if not targets:
            findings.append(("P0", str(manifest_path),
                f"module '{module_arg}' is not in the blueprint-manifest — cannot check readiness "
                "(P-PROP-005)"))
    else:
        targets = modules

    for m in targets:
        mid = str(m.get("module_id", "") or "").strip()
        mloc = f"{manifest_path}#module:{mid or '?'}"
        reg_module = reg_index.get(mid)
        if reg_module is None:
            findings.append(("P0", mloc,
                f"manifest module '{mid}' is not in the frozen {REGISTRY_NAME} — kind/risk/requirements "
                "are derived from the canonical registry, never the manifest alone (P-PROP-005)"))
            continue
        _validate_module(packet_dir, bp, m, mloc, reg_module, approval_block, state, findings,
                         reg_index, screen_nav, builder_family, approval_root, risk_tier_val)

    if not findings:
        print("PASS")
        scope = f"module '{module_arg}'" if module_arg else f"all {len(targets)} module(s)"
        print(f"  [INFO] {scope} BLUEPRINT-READY — plan complete + CEO-approved + source-current + "
              "reviewed-where-required (recomputed from source, P-PROP-005)")
        return 0
    return findings_report(findings)


def _screen_nav_index(packet_dir: Path) -> dict:
    """screen_id -> [to_screen, ...], from the INDEPENDENT screens-manifest.yaml (CXBP-001 nav source).
    Each screen row may declare `nav: [{to: <id>}, ...]` (or `nav: [<id>, ...]`). Every declared screen
    id is a key (so the registered-screen set for NAV-COMPLETE includes screens-manifest entries)."""
    data, err = load_yaml(str(packet_dir / SCREENS_NAME))
    screens = data.get("screens") if isinstance(data, dict) else None
    out = {}
    if isinstance(screens, list):
        for s in screens:
            if not isinstance(s, dict) or not s.get("id"):
                continue
            sid = str(s.get("id")).strip()
            edges = []
            for n in (s.get("nav") or []):
                if isinstance(n, dict) and n.get("to"):
                    edges.append(str(n.get("to")).strip())
                elif isinstance(n, str) and n.strip():
                    edges.append(n.strip())
            out[sid] = edges
    return out


def _registry_index(packet_dir: Path, findings: list) -> dict:
    """module_id -> frozen registry row (the canonical source of kind/risk/requirements)."""
    reg_path = packet_dir / REGISTRY_NAME
    data, err = load_yaml(str(reg_path))
    mr = nested_get(data, "module_registry") if isinstance(data, dict) else None
    rows = mr.get("modules") if isinstance(mr, dict) else (
        data.get("modules") if isinstance(data, dict) else None)
    out = {}
    if not isinstance(rows, list):
        findings.append(("P0", str(reg_path),
            f"frozen {REGISTRY_NAME} has no module_registry.modules list — the gate derives kind/risk/"
            "requirements from the canonical registry (P-PROP-005)"))
        return out
    for m in rows:
        if isinstance(m, dict) and m.get("module_id"):
            out[str(m.get("module_id"))] = m
    return out
