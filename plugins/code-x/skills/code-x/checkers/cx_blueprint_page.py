# cmd_blueprint_page: the blueprint-page render-faithfulness gate (P-PROP-007, fold v1.22.2).
#
#   cx check blueprint-page <packet-dir> --page <html> --all
#
# WHOLE-PAGE ONLY (xfam X2, CEO-D-040): the page is a whole-plan artefact — the projections
# (frames/edges/lanes/anchor ids) are computed page-wide, so a --module <id> scope would
# false-fail on every OTHER module's markers still present on the page. There is no --module
# option; --all is the only supported invocation. Per-module gating already lives in
# `cx check blueprint`.
#
# SIBLING of `cx check blueprint` (which is UNCHANGED — zero diffs to its behavior). The Master
# Blueprint page renders three CEO-facing PROJECTION views on top of the per-module blueprint:
#   1. FLOW STORYBOARD  — a frame per `kind: screen` module + an arrow per declared nav edge +
#      one lane per `user_journeys` entry.
#   2. PROTOTYPE TAB     — the Mode A locked design embedded by path + content hash.
#   3. FEEDBACK ANCHOR IDS — every rendered item shows its existing manifest anchor id.
#
# All three are PURE PROJECTIONS of already-locked source (render-never-re-type). This checker
# never trusts the page — it recomputes each projection's EXPECTED set from canonical sources
# (frozen MODULE-REGISTRY + screens-manifest + blueprint-manifest + ui_lock_manifest) and requires
# the page's machine-readable markers to be SET-EQUAL. A hand-drawn edge, a dropped screen frame,
# a divergent prototype embed, or an invented anchor id fails closed. Same G6 design-fidelity
# pattern as cx_design_fidelity: the page is checked AGAINST source, never a source of truth.
#
# HONEST LIMITS (stated, not hidden — MASTER-BLUEPRINT.md carries the same text):
#   - Journey lanes: `user_journeys` entries carry no screen-sequence field, so a lane is checked
#     as PRESENCE + VERBATIM TEXT only, never a verified click-path (OQ2, CEO-D-040).
#   - Anchor-id visibility is DOM-presence, not a CSS-visibility proof.
#   - The prototype tab proves the locked artefact is embedded byte-identical, not that it "feels"
#     right — the CEO's own drive owns that.
#
# Wiring: a generator-time check, run on every page (re)generation before CEO review. NOT wired
# into module-start / build-turn in this patch (OQ1, CEO-D-040) — the manifest/approval gates
# already guard building; a stale/unfaithful PAGE does not block it.
#
# READ-ONLY: never builds, routes actors, edits source, or writes a receipt (CHARTER §4).
import hashlib
from html.parser import HTMLParser
from pathlib import Path

from cx_common import findings_report, load_yaml, nested_get
from cx_blueprint import (
    MANIFEST_NAME, REGISTRY_NAME,
    _safe_inside, _screen_nav_index, _registry_index, _load_contracts,
    _derive_expected_anchor_ids,
)

# HTML void elements (no end tag, per WHATWG) — never pushed onto the tag stack as an OPEN frame;
# handle_starttag closes them immediately (F2, self-review). Without this, e.g. a <br> inside a
# data-journey-lane pushes an unclosed stack entry that is never popped by a matching endtag, so
# the lane's buffer leaks past its real closing tag and swallows unrelated trailing markup as
# "lane text" -> a false BLUEPRINT-STORYBOARD-LANES P1 on a perfectly legitimate page.
_VOID_ELEMENTS = frozenset({
    "br", "img", "input", "hr", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr",
})

FRAMES_CLAUSE = "BLUEPRINT-STORYBOARD-FRAMES"
EDGES_CLAUSE = "BLUEPRINT-STORYBOARD-EDGES"
LANES_CLAUSE = "BLUEPRINT-STORYBOARD-LANES"
PROTO_CLAUSE = "BLUEPRINT-PROTOTYPE-TAB-LOCKED"
ANCHOR_CLAUSE = "BLUEPRINT-ANCHOR-ID-VISIBLE"


class _MarkerParser(HTMLParser):
    """Extracts the page's machine-readable projection markers with stdlib html.parser only (no
    new dependency — mirrors how the rest of cx parses HTML/text with the standard library).

    - data-storyboard-frame="<screen_id>"           -> frames
    - data-storyboard-edge="<from>-><to>"           -> edges
    - data-journey-lane (+ its VERBATIM text content) -> lanes
    - data-proto-src="<path>" data-proto-src-hash="<sha256>" -> prototype embeds
    - data-anchor-id="<anchor_id>"                  -> anchor ids

    Journey-lane text is captured as the element's full textContent (all descendant text nodes
    concatenated), matching how a browser would read it — a nested <span> inside the lane still
    counts toward the verbatim text.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ok = True
        self.frames = set()
        self.edges = set()
        self.anchor_ids = set()
        self.proto = []  # list of (src, hash) raw attribute pairs, in document order
        self.lane_texts = []
        self._stack = []  # list of [tag, buffer-or-None] — buffer set only for data-journey-lane origins

    def _open(self, tag, attrs):
        ad = {k: v for k, v in attrs}
        buf = [] if "data-journey-lane" in ad else None
        self._stack.append([tag, buf])
        if "data-storyboard-frame" in ad and ad["data-storyboard-frame"]:
            self.frames.add(ad["data-storyboard-frame"].strip())
        if "data-storyboard-edge" in ad and ad["data-storyboard-edge"]:
            self.edges.add(ad["data-storyboard-edge"].strip())
        if "data-anchor-id" in ad and ad["data-anchor-id"]:
            self.anchor_ids.add(ad["data-anchor-id"].strip())
        if "data-proto-src" in ad:
            self.proto.append((ad.get("data-proto-src") or "", ad.get("data-proto-src-hash") or ""))

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs)
        if tag in _VOID_ELEMENTS:
            self._close()

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs)
        self._close()

    def _close(self):
        if not self._stack:
            return
        _tag, buf = self._stack.pop()
        if buf is not None:
            self.lane_texts.append("".join(buf).strip())

    def handle_endtag(self, tag):
        self._close()

    def handle_data(self, data):
        for _tag, buf in self._stack:
            if buf is not None:
                buf.append(data)


def _parse_page(page_path: str) -> tuple["_MarkerParser | None", str | None]:
    """Read + parse the page. Returns (parser, error). error is set on a missing/unreadable/
    unparseable page — the umbrella fail-closed case (no 6th clause; it surfaces at
    BLUEPRINT-STORYBOARD-FRAMES per the design spec)."""
    if not page_path:
        return None, "--page <html> required — the projection views are checked against a rendered page"
    p = Path(page_path)
    if not p.is_file():
        return None, f"{page_path} — page not found (fail-closed)"
    if p.is_symlink():
        return None, f"{page_path} — page is a symlink (fail-closed)"
    try:
        text = p.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError) as e:
        return None, f"{page_path} — page unreadable/undecodable: {e} (fail-closed)"
    parser = _MarkerParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:  # html.parser is lenient; this is a belt-and-suspenders fail-closed path
        return None, f"{page_path} — page did not parse as HTML: {e} (fail-closed)"
    return parser, None


def _select_modules(bp_modules: list, do_all) -> tuple[list, str | None]:
    if not do_all:
        return [], "--all required for cx check blueprint-page (whole-page only, xfam X2/CEO-D-040)"
    if not bp_modules:
        return [], ("blueprint-manifest has an EMPTY modules list — --all cannot certify zero module "
                     "projections as rendered; an emptied/truncated manifest fails CLOSED, it is never "
                     "a vacuous PASS (BLUEPRINT-MODULES-NONEMPTY, P-PROP-007)")
    return bp_modules, None


def cmd_blueprint_page(args) -> int:
    packet_dir_arg = getattr(args, "packet_dir", None)
    if not packet_dir_arg:
        print(f"FIX-FIRST\n  [P0] packet-dir required for cx check blueprint-page ({FRAMES_CLAUSE})")
        return 1
    packet_dir = Path(packet_dir_arg)
    if not packet_dir.is_dir():
        print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — packet-dir not found or not a directory ({FRAMES_CLAUSE})")
        return 1
    if packet_dir.is_symlink():
        print(f"FIX-FIRST\n  [P0] {packet_dir_arg} — packet-dir is a symlink (fail-closed, {FRAMES_CLAUSE})")
        return 1

    do_all = getattr(args, "all", False)

    # ── umbrella fail-closed: page must exist/parse BEFORE anything else (no 6th clause) ─────────
    parser, perr = _parse_page(getattr(args, "page", None))
    if perr:
        print(f"FIX-FIRST\n  [P1] {perr} ({FRAMES_CLAUSE})")
        return 1

    findings: list[tuple[str, str, str]] = []

    manifest_path = packet_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        print(f"FIX-FIRST\n  [P0] {manifest_path} — the immutable blueprint-manifest.yaml is missing "
              f"from the frozen packet ({FRAMES_CLAUSE})")
        return 1
    mdata, merr = load_yaml(str(manifest_path))
    bp = nested_get(mdata, "blueprint_manifest") if isinstance(mdata, dict) else None
    if merr or not isinstance(bp, dict) or not isinstance(bp.get("modules"), list):
        print(f"FIX-FIRST\n  [P0] {manifest_path} — not a typed blueprint_manifest with a 'modules' "
              f"list ({merr or 'wrong shape'}) ({FRAMES_CLAUSE})")
        return 1

    all_modules = [m for m in bp.get("modules") if isinstance(m, dict)]
    targets, serr = _select_modules(all_modules, do_all)
    if serr:
        tag = "" if "(BLUEPRINT-" in serr else f" ({FRAMES_CLAUSE})"
        print(f"FIX-FIRST\n  [P0] {serr}{tag}")
        return 1

    reg_index = _registry_index(packet_dir, findings)
    screen_nav = _screen_nav_index(packet_dir)
    contracts = _load_contracts(packet_dir)

    expected_frames = set()
    expected_edges = set()
    expected_lanes = set()
    expected_proto = {}   # path -> hash
    expected_anchor_ids = set()

    for m in targets:
        mid = str(m.get("module_id", "") or "").strip()
        kind = str(m.get("kind", "") or "").strip()
        screen_id = str(m.get("screen_id", "") or "").strip()
        sid = screen_id or mid
        reg_module = reg_index.get(mid)
        if reg_module is None:
            findings.append(("P0", f"{manifest_path}#module:{mid or '?'}",
                f"manifest module '{mid}' is not in the frozen {REGISTRY_NAME} — the projection "
                f"views cannot be recomputed without the canonical registry ({FRAMES_CLAUSE})"))
            continue

        if kind == "screen":
            expected_frames.add(sid)
            for to in (screen_nav.get(sid) or []):
                to = str(to).strip()
                if to:
                    expected_edges.add(f"{sid}->{to}")
            lock_ref = m.get("ui_lock_manifest")
            if lock_ref:
                lock_target = _safe_inside(packet_dir, lock_ref)
                if lock_target is not None and lock_target.is_file():
                    expected_proto[str(lock_ref)] = hashlib.sha256(lock_target.read_bytes()).hexdigest()
                else:
                    # F1 (self-review, fail-closed): a kind:screen module's ui_lock_manifest ref
                    # that doesn't resolve to a real, in-packet, non-symlink file must NOT be
                    # silently dropped from expected_proto — that would let a page stripped of its
                    # prototype embed PASS. Surface it as a P1 finding instead.
                    findings.append(("P1", f"{manifest_path}#module:{mid}",
                        f"module '{mid}' declares ui_lock_manifest '{lock_ref}' which does not "
                        f"resolve to a real, in-packet, non-symlink file — the locked design cannot "
                        f"be verified as embedded ({PROTO_CLAUSE})"))

        for uj in (m.get("user_journeys") or []):
            if isinstance(uj, dict):
                text = str(uj.get("journey", "") or "").strip()
                if text:
                    expected_lanes.add(text)

        expected_anchor_ids |= _derive_expected_anchor_ids(
            reg_module, mid, screen_id, kind, contracts, screen_nav)

    # ── BLUEPRINT-STORYBOARD-FRAMES: page frame set == registered screen-module set (in scope) ──
    missing_frames = sorted(expected_frames - parser.frames)
    extra_frames = sorted(parser.frames - expected_frames)
    if missing_frames:
        findings.append(("P1", str(manifest_path),
            f"page is missing storyboard frame(s) {missing_frames} — every locked kind:screen module "
            f"must render as a frame ({FRAMES_CLAUSE})"))
    if extra_frames:
        findings.append(("P1", str(manifest_path),
            f"page renders storyboard frame(s) {extra_frames} not derivable from any registered "
            f"kind:screen module in scope — a hand-drawn/invented frame ({FRAMES_CLAUSE})"))

    # ── BLUEPRINT-STORYBOARD-EDGES: page edge set == screens-manifest declared nav edges (in scope) ──
    missing_edges = sorted(expected_edges - parser.edges)
    extra_edges = sorted(parser.edges - expected_edges)
    if missing_edges:
        findings.append(("P1", str(manifest_path),
            f"page is missing storyboard edge(s) {missing_edges} — an omitted locked nav edge "
            f"({EDGES_CLAUSE})"))
    if extra_edges:
        findings.append(("P1", str(manifest_path),
            f"page draws storyboard edge(s) {extra_edges} not declared in the INDEPENDENT "
            f"screens-manifest — a hand-drawn arrow ({EDGES_CLAUSE})"))

    # ── BLUEPRINT-STORYBOARD-LANES: page lane text set == manifest user_journeys text (verbatim) ──
    actual_lanes = {t for t in parser.lane_texts if t}
    missing_lanes = sorted(expected_lanes - actual_lanes)
    extra_lanes = sorted(actual_lanes - expected_lanes)
    if missing_lanes:
        findings.append(("P1", str(manifest_path),
            f"page is missing journey lane(s) for {missing_lanes} — a dropped journey "
            f"({LANES_CLAUSE}; HONEST LIMIT: presence + verbatim text only, no verified screen path)"))
    if extra_lanes:
        findings.append(("P1", str(manifest_path),
            f"page renders journey lane text {extra_lanes} that does not verbatim-match any manifest "
            f"user_journeys entry in scope — a re-typed/invented lane ({LANES_CLAUSE})"))

    # ── BLUEPRINT-PROTOTYPE-TAB-LOCKED: page embed set == {ui_lock_manifest path: sha256} (in scope) ──
    actual_proto_paths = set()
    for raw_src, raw_hash in parser.proto:
        safe = _safe_inside(packet_dir, raw_src) if raw_src else None
        if safe is None or not safe.is_file():
            findings.append(("P1", str(manifest_path),
                f"prototype embed data-proto-src '{raw_src}' does not resolve to a real, in-packet, "
                f"non-symlink file — the embed must reference a locked artefact by a safe path "
                f"({PROTO_CLAUSE})"))
            continue
        actual_proto_paths.add(raw_src)
        expected_hash = expected_proto.get(raw_src)
        if expected_hash is None:
            findings.append(("P1", str(manifest_path),
                f"prototype embed data-proto-src '{raw_src}' is not any in-scope screen module's "
                f"ui_lock_manifest — a divergent/invented embed ({PROTO_CLAUSE})"))
            continue
        if raw_hash.strip().lower() != expected_hash:
            findings.append(("P1", str(manifest_path),
                f"prototype embed '{raw_src}' data-proto-src-hash {raw_hash[:12] or '(missing)'}… != "
                f"recomputed lock-artefact hash {expected_hash[:12]}… — the embedded copy has diverged "
                f"from the locked design ({PROTO_CLAUSE})"))
    missing_proto = sorted(set(expected_proto) - actual_proto_paths)
    if missing_proto:
        findings.append(("P1", str(manifest_path),
            f"page has no prototype-tab embed for locked design(s) {missing_proto} — every in-scope "
            f"screen module's Mode A artefact must be embedded ({PROTO_CLAUSE})"))

    # ── BLUEPRINT-ANCHOR-ID-VISIBLE: page anchor-id set == manifest anchor set (already "
    #    coverage-complete via BLUEPRINT-ANCHOR-COVERAGE) ──
    missing_anchor_ids = sorted(expected_anchor_ids - parser.anchor_ids)
    extra_anchor_ids = sorted(parser.anchor_ids - expected_anchor_ids)
    if missing_anchor_ids:
        findings.append(("P1", str(manifest_path),
            f"page does not show a visible anchor id for {missing_anchor_ids} — every manifest anchor "
            f"must be visible so CEO feedback maps to it ({ANCHOR_CLAUSE})"))
    if extra_anchor_ids:
        findings.append(("P1", str(manifest_path),
            f"page shows anchor id(s) {extra_anchor_ids} not in the manifest anchor set — an invented id "
            f"({ANCHOR_CLAUSE})"))

    if not findings:
        print("PASS")
        print(f"  [INFO] all {len(targets)} module(s) page projections (storyboard frames/edges/lanes + "
              "prototype tab + anchor ids) all derive from locked source (set-equal, P-PROP-007)")
        return 0
    return findings_report(findings)
