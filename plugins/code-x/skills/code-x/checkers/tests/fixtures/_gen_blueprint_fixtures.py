#!/usr/bin/env python3
"""Generate the cx check blueprint fixture packets + approval/state receipts with CORRECT
recomputed hashes (anchor span hashes, manifest_hash, packet_hash, approved_source_hash).

GOOD packet = blueprint_good_packet/ + blueprint_good_approval.yaml + blueprint_good_state.yaml.
BAD variants reuse the same source files but pin ONE deliberate violation per clause (in the
manifest or the approval/state receipt) so each contract clause bites for exactly its reason.

Run: python3 checkers/tests/fixtures/_gen_blueprint_fixtures.py   (from anywhere)
Deterministic: rebuilds the whole tree from scratch each run.
"""
import copy
import hashlib
import os
import shutil
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent          # checkers/tests/fixtures
CHECKERS = HERE.parent.parent                    # checkers/
sys.path.insert(0, str(CHECKERS))
from cx_deck import _compute_packet_hash         # noqa: E402


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _line_hash(text: str, line: int | None) -> str:
    if line in (None, 0):
        span = text
    else:
        span = text.splitlines()[line - 1]
    return hashlib.sha256(span.encode("utf-8")).hexdigest()


def _module_source_hash(anchors: list[dict]) -> str:
    parts = [f"{a['anchor_id']}:{a['source_hash']}" for a in sorted(anchors, key=lambda x: x["anchor_id"])]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# ── Source files inside the GOOD packet ─────────────────────────────────────────────────────────
REQUIREMENTS_SRC = """# requirements line 1
# requirements line 2
REQ-001: home screen shows balance
REQ-002: add-entry button opens the form
REQ-003: shared money rounding rule
"""

UI_LOCK_SRC = """ui_lock_manifest:
  screen_id: home
  style_locked: yes
  provenance: original
"""

HOME_SCREEN_SRC = """<button data-fn="add_entry">Add entry</button>
<a href="detail">Go to detail</a>
<div id="balance">balance region</div>
"""


def build():
    PKT = HERE / "blueprint_good_packet"
    if PKT.exists():
        shutil.rmtree(PKT)
    PKT.mkdir(parents=True)

    # source docs
    _write(PKT / "requirements-source.md", REQUIREMENTS_SRC)
    _write(PKT / "screens/home.html", HOME_SCREEN_SRC)
    ui_lock_path = PKT / "ui-locks/home.lock.yaml"
    _write(ui_lock_path, UI_LOCK_SRC)

    # requirements-manifest (BUILDING + acceptance_criterion done-tests)
    requirements = {
        "requirements": [
            {"id": "REQ-001", "disposition": "BUILDING",
             "acceptance_criterion": {"pass_condition": "balance renders on home",
                                      "evidence_type": "screenshot",
                                      "verification_ref": "cards/home#ac1"}},
            {"id": "REQ-002", "disposition": "BUILDING",
             "acceptance_criterion": {"pass_condition": "add-entry form opens on tap",
                                      "evidence_type": "playwright",
                                      "verification_ref": "cards/home#ac2"}},
            {"id": "REQ-003", "disposition": "BUILDING",
             "acceptance_criterion": {"pass_condition": "rounding matches spec table",
                                      "evidence_type": "unit_test",
                                      "verification_ref": "cards/shared#ac3"}},
        ]
    }
    _dump(PKT / "requirements-manifest.yaml", requirements)

    # frozen MODULE-REGISTRY (canonical source of kind/risk/requirements)
    registry = {
        "module_registry": {
            "frozen_packet_hash": "bp-frozen",
            "modules": [
                {"module_id": "home", "screen_id": "home", "kind": "screen",
                 "title": "Home screen", "requirement_ids": ["REQ-001", "REQ-002"],
                 "risk_flags": ["money"], "dependency_modules": []},
                {"module_id": "rounding", "kind": "shared_logic",
                 "title": "Shared rounding rule", "requirement_ids": ["REQ-003"],
                 "risk_flags": ["money"], "dependency_modules": ["home"]},
            ]
        }
    }
    _dump(PKT / "MODULE-REGISTRY.yaml", registry)

    # behaviour-contracts: the INDEPENDENT control source (CXBP-001). Each contract carries control_id
    # + a `screen` scope so cx derives expected controls from HERE, not from the manifest being checked.
    contracts = {
        "behaviour_contracts": {
            "contracts": [
                {"contract_id": "c_add_entry", "control_id": "add_entry", "screen": "home",
                 "tap_outcome": "opens the new-entry form",
                 "state_change": "creates a draft entry",
                 "error_empty": "shows 'name required' when blank",
                 "done_test_ref": "REQ-002"},
            ]
        }
    }
    _dump(PKT / "behaviour-contracts.yaml", contracts)

    # screens-manifest: the INDEPENDENT nav source (CXBP-001) + packet-floor COVERS-SCREENS. The home
    # screen declares its nav edge here; cx derives the expected nav anchor from THIS, not the manifest.
    _dump(PKT / "screens-manifest.yaml",
          {"screens": [{"id": "home", "user_facing": True, "nav": [{"to": "detail"}]}]})

    # clarification-sweep (no open markers)
    _dump(PKT / "clarification-sweep.yaml",
          {"clarification_sweep": {"clarifications": []}})

    # ── home (screen) anchors: req:REQ-001, req:REQ-002, control:add_entry, nav:home->detail ──
    req_text = (PKT / "requirements-source.md").read_text()
    home_text = (PKT / "screens/home.html").read_text()
    home_anchors = [
        {"anchor_id": "req:REQ-001", "file": "requirements-source.md", "section": "REQ-001",
         "line": 3, "requirement_id": "REQ-001", "source_hash": _line_hash(req_text, 3)},
        {"anchor_id": "req:REQ-002", "file": "requirements-source.md", "section": "REQ-002",
         "line": 4, "requirement_id": "REQ-002", "source_hash": _line_hash(req_text, 4)},
        {"anchor_id": "control:add_entry", "file": "screens/home.html", "section": "add button",
         "line": 1, "requirement_id": "REQ-002", "source_hash": _line_hash(home_text, 1)},
        {"anchor_id": "nav:home->detail", "file": "screens/home.html", "section": "detail link",
         "line": 2, "requirement_id": None, "source_hash": _line_hash(home_text, 2)},
    ]
    home_module = {
        "module_id": "home", "screen_id": "home", "kind": "screen", "title": "Home screen",
        "anchors": home_anchors,
        "ui_lock_manifest": "ui-locks/home.lock.yaml",
        "ui_lock_hash": hashlib.sha256(ui_lock_path.read_bytes()).hexdigest(),
        "controls": [{"control_id": "add_entry", "anchor_id": "control:add_entry",
                      "label": "Add entry", "contract_id": "c_add_entry"}],
        "nav": [{"from_screen": "home", "to_screen": "detail", "trigger_control_id": "add_entry"}],
        "user_journeys": [{"journey": "I tap Add entry, the app opens the form",
                           "done_test_ref": "REQ-002"}],
        "risk_callouts": [{"kind": "money", "note": "balance is money", "proof_ref": "REQ-001"}],
    }

    # ── rounding (shared_logic) anchors: req:REQ-003 ──
    rounding_anchors = [
        {"anchor_id": "req:REQ-003", "file": "requirements-source.md", "section": "REQ-003",
         "line": 5, "requirement_id": "REQ-003", "source_hash": _line_hash(req_text, 5)},
    ]
    rounding_module = {
        "module_id": "rounding", "screen_id": None, "kind": "shared_logic",
        "title": "Shared rounding rule",
        "design_nav_na_reason": "shared_logic has no screen — design+nav are N/A",
        "anchors": rounding_anchors,
        "user_journeys": [{"journey": "money rounds the same everywhere", "done_test_ref": "REQ-003"}],
        "risk_callouts": [{"kind": "money", "note": "rounding affects totals", "proof_ref": "REQ-003"}],
    }

    manifest = {"blueprint_manifest": {"generator_version": "0.1.0",
                                       "modules": [home_module, rounding_module]}}
    # detail must be a registered screen so nav:home->detail resolves. Add a minimal detail screen
    # module that needs no anchors checked here? No — it would itself need coverage. Instead, register
    # 'detail' as a nav target by making the home module nav resolve to a registered screen. The
    # checker treats screen_id OR module_id of ANY manifest module as registered, so add a detail
    # screen module with its own (single-req) coverage. Simpler: point nav at an existing module.
    # Keep nav -> 'home' is trivial; instead register a detail module mirroring home minimally.
    # To keep the GOOD case clean we register 'detail' as a screen module with REQ-mapped anchor.
    # --- simplest correct: make 'detail' a registered screen_id via a 3rd registry+manifest module.
    manifest_path = PKT / "blueprint-manifest.yaml"
    _dump(manifest_path, manifest)

    # Register 'detail' so nav resolves: add to registry + manifest + a requirement.
    # Re-open and extend to keep one source of truth.
    registry["module_registry"]["modules"].append(
        {"module_id": "detail", "screen_id": "detail", "kind": "screen",
         "title": "Detail screen", "requirement_ids": [], "risk_flags": [],
         "dependency_modules": ["home"]})
    _dump(PKT / "MODULE-REGISTRY.yaml", registry)
    _dump(PKT / "screens-manifest.yaml",
          {"screens": [{"id": "home", "user_facing": True, "nav": [{"to": "detail"}]},
                       {"id": "detail", "user_facing": True}]})
    detail_module = {
        "module_id": "detail", "screen_id": "detail", "kind": "screen", "title": "Detail screen",
        "anchors": [],  # no requirements/controls/nav -> expected set empty -> coverage OK
        "ui_lock_manifest": "ui-locks/home.lock.yaml",
        "ui_lock_hash": hashlib.sha256(ui_lock_path.read_bytes()).hexdigest(),
        "controls": [], "nav": [],
        "user_journeys": [], "risk_callouts": [],
    }
    manifest["blueprint_manifest"]["modules"].append(detail_module)
    _dump(manifest_path, manifest)

    # recompute manifest_hash + packet_hash AFTER the manifest is final + all files written
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    packet_hash = _compute_packet_hash(PKT)

    # ── approval receipt (OUTSIDE the packet) ──
    # builder_family = anthropic → the opposite-family review must be GPT/codex (CXBP-003). The review
    # files are REAL files next to the approval (review_ref resolves under approval_root = HERE).
    _write(HERE / "reviews/home-review.md", "# home module cross-family review\nverdict: PASS\n")
    _write(HERE / "reviews/rounding-review.md", "# rounding module cross-family review\nverdict: PASS\n")
    home_src_hash = _module_source_hash(home_anchors)
    rounding_src_hash = _module_source_hash(rounding_anchors)
    detail_src_hash = _module_source_hash([])
    approval = {
        "blueprint_approval": {
            "packet_hash": packet_hash,
            "manifest_hash": manifest_hash,
            "builder_family": "anthropic",
            "modules": [
                {"module_id": "home", "approved_source_hash": home_src_hash,
                 "ceo_approval": {"approved_by": "CEO", "approved_at": "2026-06-25"},
                 "review_receipt": {"reviewer_family": "GPT", "three_leg_ask": "CONTINUITY+PROBLEMS+APPROACH",
                                    "verdict": "PASS", "reviewed_source_hash": home_src_hash,
                                    "review_ref": "reviews/home-review.md"}},
                {"module_id": "rounding", "approved_source_hash": rounding_src_hash,
                 "ceo_approval": {"approved_by": "CEO", "approved_at": "2026-06-25"},
                 "review_receipt": {"reviewer_family": "GPT", "three_leg_ask": "CONTINUITY+PROBLEMS+APPROACH",
                                    "verdict": "PASS", "reviewed_source_hash": rounding_src_hash,
                                    "review_ref": "reviews/rounding-review.md"}},
                {"module_id": "detail", "approved_source_hash": detail_src_hash,
                 "ceo_approval": {"approved_by": "CEO", "approved_at": "2026-06-25"}},
            ]
        }
    }
    _dump(HERE / "blueprint_good_approval.yaml", approval)

    # ── clean state (no open findings) ──
    state = {"project": "blueprint-test", "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
                                                            "items": []}}
    _dump(HERE / "blueprint_good_state.yaml", state)

    # ── BAD approval variants (reuse GOOD packet; pin one violation each) ──
    def _bad_approval(name, mutate):
        a = copy.deepcopy(approval)
        mutate(a["blueprint_approval"])
        _dump(HERE / name, a)

    # MANIFEST-HASH-BOUND: wrong manifest_hash
    _bad_approval("blueprint_bad_manifest_hash_approval.yaml",
                  lambda b: b.update({"manifest_hash": "0" * 64}))
    # APPROVAL-CURRENT: stale approved_source_hash for home
    def _stale(b):
        b["modules"][0]["approved_source_hash"] = "deadbeef" * 8
    _bad_approval("blueprint_bad_stale_approval.yaml", _stale)
    # APPROVAL-CURRENT: missing ceo_approval for home
    def _noapproval(b):
        b["modules"][0].pop("ceo_approval")
    _bad_approval("blueprint_bad_no_ceo_approval.yaml", _noapproval)
    # REVIEW-RECEIPT: home risk-flagged but no review_receipt
    def _noreview(b):
        b["modules"][0].pop("review_receipt")
    _bad_approval("blueprint_bad_no_review_receipt.yaml", _noreview)
    # REVIEW-RECEIPT (CXBP-003): review_ref points at a non-existent review file
    def _ghostref(b):
        b["modules"][0]["review_receipt"]["review_ref"] = "reviews/does-not-exist.md"
    _bad_approval("blueprint_bad_review_ref_missing.yaml", _ghostref)
    # REVIEW-RECEIPT (CXBP-003): same-family reviewer (builder anthropic, reviewer claude = same group)
    def _samefam(b):
        b["modules"][0]["review_receipt"]["reviewer_family"] = "claude"
    _bad_approval("blueprint_bad_review_same_family.yaml", _samefam)

    # ── BAD states (CXBP-004 fail-CLOSED on malformed open_findings) ──
    # an open P1 with no module attribution (the classic hidden severity)
    _dump(HERE / "blueprint_bad_hidden_severity_state.yaml",
          {"project": "blueprint-test",
           "open_findings": {"counts": {"p0": 0, "p1": 1, "p2": 0, "p3": 0},
                             "items": [{"severity": "P1", "finding": "something open, no module"}]}})
    # open_findings entirely missing → fail-CLOSED
    _dump(HERE / "blueprint_bad_state_no_open_findings.yaml", {"project": "blueprint-test"})
    # open_findings.items not a list → fail-CLOSED
    _dump(HERE / "blueprint_bad_state_items_malformed.yaml",
          {"project": "blueprint-test",
           "open_findings": {"counts": {"p0": 0, "p1": 0, "p2": 0, "p3": 0}, "items": "oops-not-a-list"}})
    # counts claim an open p1 but items is empty → counts/items mismatch fail-CLOSED
    _dump(HERE / "blueprint_bad_state_counts_mismatch.yaml",
          {"project": "blueprint-test",
           "open_findings": {"counts": {"p0": 0, "p1": 1, "p2": 0, "p3": 0}, "items": []}})

    # ── BAD packet variants (separate dirs, each one violation) ──────────────────────────────────
    def _bad_packet(name, mutate_manifest, mutate_files=None):
        d = HERE / name
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(PKT, d)
        mpath = d / "blueprint-manifest.yaml"
        m = yaml.safe_load(mpath.read_text())
        mutate_manifest(m["blueprint_manifest"])
        if mutate_files:
            mutate_files(d)
        _dump(mpath, m)
        # write a matching approval whose hashes bind to THIS packet (so the ONLY failure is the
        # pinned one, not a manifest/packet-hash mismatch). For coverage/per-kind violations the
        # approved_source_hash may legitimately differ — recompute per module from the mutated anchors.
        new_manifest_hash = hashlib.sha256(mpath.read_bytes()).hexdigest()
        new_packet_hash = _compute_packet_hash(d)
        a = copy.deepcopy(approval)
        a["blueprint_approval"]["manifest_hash"] = new_manifest_hash
        a["blueprint_approval"]["packet_hash"] = new_packet_hash
        # recompute each module's approved_source_hash from the mutated manifest anchors
        by_id = {mm["module_id"]: mm for mm in m["blueprint_manifest"]["modules"]}
        for rec in a["blueprint_approval"]["modules"]:
            mm = by_id.get(rec["module_id"])
            if mm and isinstance(mm.get("anchors"), list):
                h = _module_source_hash([x for x in mm["anchors"] if isinstance(x, dict) and "anchor_id" in x])
                rec["approved_source_hash"] = h
                if "review_receipt" in rec:
                    rec["review_receipt"]["reviewed_source_hash"] = h
        _dump(d.parent / (name + "_approval.yaml"), a)

    # MISSING-MANIFEST packet
    nomani = HERE / "blueprint_bad_no_manifest_packet"
    if nomani.exists():
        shutil.rmtree(nomani)
    shutil.copytree(PKT, nomani)
    (nomani / "blueprint-manifest.yaml").unlink()

    # ANCHOR-RESOLVES: corrupt home's first anchor source_hash
    def _bad_anchor(b):
        b["modules"][0]["anchors"][0]["source_hash"] = "f" * 64
    _bad_packet("blueprint_bad_anchor_resolves_packet", _bad_anchor)

    # ANCHOR-COVERAGE: drop a required anchor (req:REQ-002) from home
    def _drop_anchor(b):
        b["modules"][0]["anchors"] = [a for a in b["modules"][0]["anchors"]
                                      if a["anchor_id"] != "req:REQ-002"]
    _bad_packet("blueprint_bad_anchor_coverage_packet", _drop_anchor)

    # SCREEN-DESIGN-LOCKED: wrong ui_lock_hash on home
    def _bad_lock(b):
        b["modules"][0]["ui_lock_hash"] = "a" * 64
    _bad_packet("blueprint_bad_design_lock_packet", _bad_lock)

    # NAV-COMPLETE (CXBP-002): a nav edge to 'ghostscreen' that is in the INDEPENDENT screens-manifest
    # (so COVERAGE matches) but is NOT a registered registry/screen module → NAV-COMPLETE bites via the
    # frozen-registry-resolved set (a manifest-only row can no longer satisfy a dangling target).
    def _dangling_nav_screens(d):
        sp = d / "screens-manifest.yaml"
        s = yaml.safe_load(sp.read_text())
        for row in s["screens"]:
            if row["id"] == "home":
                row["nav"] = [{"to": "ghostscreen"}]   # ghostscreen NOT in MODULE-REGISTRY
        # ghostscreen has no screens-manifest ENTRY of its own → not in the registered set either.
        _dump(sp, s)
    def _dangling_nav(b):
        b["modules"][0]["nav"] = [{"from_screen": "home", "to_screen": "ghostscreen",
                                   "trigger_control_id": "add_entry"}]
        for a in b["modules"][0]["anchors"]:
            if a["anchor_id"].startswith("nav:"):
                a["anchor_id"] = "nav:home->ghostscreen"
    _bad_packet("blueprint_bad_nav_packet", _dangling_nav, mutate_files=_dangling_nav_screens)

    # CONTROL-HAS-CONTRACT: control points at an unknown contract_id
    def _bad_contract(b):
        b["modules"][0]["controls"][0]["contract_id"] = "c_does_not_exist"
    _bad_packet("blueprint_bad_control_contract_packet", _bad_contract)

    # ── CXBP-001 (coverage circularity closed): the INDEPENDENT source declares a control / a nav
    #    edge that the MANIFEST OMITS → ANCHOR-COVERAGE bites (P0). Previously the manifest could omit
    #    a control/nav and pass because expected came from the manifest itself. ──
    # control omitted: behaviour-contracts declares control 'add_entry' for home; the manifest drops
    # its control anchor + the controls row → coverage now MISSING control:add_entry.
    def _omit_control(b):
        b["modules"][0]["anchors"] = [a for a in b["modules"][0]["anchors"]
                                      if a["anchor_id"] != "control:add_entry"]
        b["modules"][0]["controls"] = []
    _bad_packet("blueprint_bad_omit_control_packet", _omit_control)
    # nav omitted: screens-manifest declares home->detail; the manifest drops its nav anchor + nav row
    # → coverage now MISSING nav:home->detail.
    def _omit_nav(b):
        b["modules"][0]["anchors"] = [a for a in b["modules"][0]["anchors"]
                                      if not a["anchor_id"].startswith("nav:")]
        b["modules"][0]["nav"] = []
    _bad_packet("blueprint_bad_omit_nav_packet", _omit_nav)

    # FEATURE-HAS-DONE-TEST: strip REQ-001's acceptance_criterion in requirements-manifest
    def _strip_ac(d):
        rp = d / "requirements-manifest.yaml"
        r = yaml.safe_load(rp.read_text())
        for row in r["requirements"]:
            if row["id"] == "REQ-001":
                row.pop("acceptance_criterion", None)
        _dump(rp, r)
    _bad_packet("blueprint_bad_done_test_packet", lambda b: None, mutate_files=_strip_ac)

    # NO-OPEN-CLARIFICATION: inject a NEEDS-CLARIFICATION marker into an anchored source
    def _inject_marker(d):
        sp = d / "requirements-source.md"
        sp.write_text(sp.read_text() + "[NEEDS-CLARIFICATION: which currency?]\n", encoding="utf-8")
    # the anchor hashes stay valid (we only append a new line); coverage unaffected.
    _bad_packet("blueprint_bad_clarification_packet", lambda b: None, mutate_files=_inject_marker)

    # PER-KIND-FIELDS: shared_logic module missing design_nav_na_reason
    def _bad_perkind(b):
        b["modules"][1].pop("design_nav_na_reason", None)
    _bad_packet("blueprint_bad_per_kind_packet", _bad_perkind)

    # ── packet-floor BAD fixtures: copy packet_good + a planning MODULE-REGISTRY with a coverage gap ──
    _build_packet_floor_fixtures()

    print("blueprint fixtures generated under", HERE)


def _build_packet_floor_fixtures():
    """Two packet-floor BAD fixtures (cx check packet): a screen/module-first packet whose planning
    MODULE-REGISTRY does NOT cover a screen (COVERS-SCREENS) / a BUILDING requirement (COVERS-REQUIREMENTS).
    Built from packet_good (a full 20-category passing packet) so the ONLY failure is the coverage gap."""
    src = HERE / "packet_good"

    # COVERS-SCREENS bad: screens-manifest lists a screen the registry omits.
    d1 = HERE / "packet_bad_registry_missing_screen"
    if d1.exists():
        shutil.rmtree(d1)
    shutil.copytree(src, d1)
    _dump(d1 / "screens-manifest.yaml", {"screens": [{"id": "home", "user_facing": True},
                                                     {"id": "settings", "user_facing": True}]})
    _dump(d1 / "MODULE-REGISTRY.yaml", {"module_registry": {"frozen_packet_hash": "pf1", "modules": [
        {"module_id": "home", "screen_id": "home", "kind": "screen", "requirement_ids": ["REQ-001"],
         "risk_flags": [], "dependency_modules": []},
        # 'settings' screen is NOT covered by any registry module -> COVERS-SCREENS bites.
    ]}})

    # COVERS-REQUIREMENTS bad: a BUILDING requirement no registry module claims.
    d2 = HERE / "packet_bad_registry_missing_requirement"
    if d2.exists():
        shutil.rmtree(d2)
    shutil.copytree(src, d2)
    # read packet_good's BUILDING requirement ids
    rdata = yaml.safe_load((d2 / "requirements-manifest.yaml").read_text())
    building = [r["id"] for r in rdata["requirements"]
               if isinstance(r, dict) and str(r.get("disposition", "")).strip() == "BUILDING"]
    # registry covers all screens but OMITS the last BUILDING requirement.
    covered = building[:-1] if len(building) > 1 else []
    _dump(d2 / "screens-manifest.yaml", {"screens": [{"id": "home", "user_facing": True}]})
    _dump(d2 / "MODULE-REGISTRY.yaml", {"module_registry": {"frozen_packet_hash": "pf2", "modules": [
        {"module_id": "home", "screen_id": "home", "kind": "screen", "requirement_ids": covered,
         "risk_flags": [], "dependency_modules": []},
    ]}})


if __name__ == "__main__":
    build()
