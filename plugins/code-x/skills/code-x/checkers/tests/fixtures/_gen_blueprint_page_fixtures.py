#!/usr/bin/env python3
"""Generate the cx check blueprint-page fixture HTML pages (P-PROP-007, fold v1.22.2).

Built ON TOP of blueprint_good_packet (from _gen_blueprint_fixtures.py) so the GOOD page's
markers are recomputed from the SAME hashes the packet already carries (self-healing, never a
stale committed constant). Run _gen_blueprint_fixtures.py FIRST (run.py's setUpClass already does).

GOOD page = blueprint_good_page.html — covers ALL THREE modules (home, rounding, detail) with
--all scope: home + detail are kind:screen (frames), home->detail is the only nav edge, home +
rounding each carry one user_journeys lane, home + detail share the same ui_lock_manifest
artefact (embedded once), and every module's expected anchor id is visible.

BAD pages each reuse the GOOD page with exactly ONE deliberate defect, so each contract clause
bites for exactly its reason (mirrors the blueprint packet fixtures' one-violation-per-file rule).

Run: python3 checkers/tests/fixtures/_gen_blueprint_page_fixtures.py
"""
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # checkers/tests/fixtures
CHECKERS = HERE.parent.parent                    # checkers/
sys.path.insert(0, str(CHECKERS))

PKT = HERE / "blueprint_good_packet"
LOCK_PATH = PKT / "ui-locks" / "home.lock.yaml"


def _lock_hash() -> str:
    return hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest()


def _good_html(*, frames=("home", "detail"), edges=("home->detail",),
              lane_home="I tap Add entry, the app opens the form",
              lane_rounding="money rounds the same everywhere",
              proto_hash=None,
              anchor_ids=("req:REQ-001", "req:REQ-002", "control:add_entry",
                          "nav:home->detail", "req:REQ-003"),
              extra_frame="", extra_edge="", extra_lane="", extra_anchor="") -> str:
    if proto_hash is None:
        proto_hash = _lock_hash()
    frame_html = "\n".join(f'<section data-storyboard-frame="{f}">frame {f}</section>' for f in frames)
    edge_html = "\n".join(f'<div data-storyboard-edge="{e}"></div>' for e in edges)
    lane_html = ""
    if lane_home:
        lane_html += f'<p data-journey-lane="1">{lane_home}</p>\n'
    if lane_rounding:
        lane_html += f'<p data-journey-lane="1">{lane_rounding}</p>\n'
    anchor_html = "\n".join(f'<span data-anchor-id="{a}"></span>' for a in anchor_ids)
    return f"""<!DOCTYPE html>
<html><head><title>Master Blueprint</title></head>
<body>
<section id="storyboard">
{frame_html}
{extra_frame}
{edge_html}
{extra_edge}
</section>
<section id="journeys">
{lane_html}
{extra_lane}
</section>
<section id="prototype">
<iframe data-proto-src="ui-locks/home.lock.yaml" data-proto-src-hash="{proto_hash}"></iframe>
</section>
<section id="anchors">
{anchor_html}
{extra_anchor}
</section>
</body></html>
"""


def build():
    lock_hash = _lock_hash()

    # ── GOOD ──
    (HERE / "blueprint_good_page.html").write_text(_good_html(proto_hash=lock_hash), encoding="utf-8")

    # ── BLUEPRINT-STORYBOARD-FRAMES: drop the 'detail' frame ──
    (HERE / "blueprint_bad_page_missing_frame.html").write_text(
        _good_html(frames=("home",), proto_hash=lock_hash), encoding="utf-8")

    # ── BLUEPRINT-STORYBOARD-EDGES: a hand-drawn edge not in the screens-manifest ──
    (HERE / "blueprint_bad_page_handdrawn_edge.html").write_text(
        _good_html(edges=("home->detail", "home->ghostscreen"), proto_hash=lock_hash), encoding="utf-8")

    # ── BLUEPRINT-STORYBOARD-LANES: drop the rounding journey lane ──
    (HERE / "blueprint_bad_page_missing_lane.html").write_text(
        _good_html(lane_rounding="", proto_hash=lock_hash), encoding="utf-8")

    # ── BLUEPRINT-PROTOTYPE-TAB-LOCKED: embed hash diverges from the locked artefact ──
    (HERE / "blueprint_bad_page_proto_hash_mismatch.html").write_text(
        _good_html(proto_hash="f" * 64), encoding="utf-8")

    # ── BLUEPRINT-ANCHOR-ID-VISIBLE: an invented anchor id absent from the manifest ──
    (HERE / "blueprint_bad_page_anchor_invented.html").write_text(
        _good_html(proto_hash=lock_hash,
                  anchor_ids=("req:REQ-001", "req:REQ-002", "control:add_entry",
                              "nav:home->detail", "req:REQ-003", "control:invented_button")),
        encoding="utf-8")

    # ── fail-closed: unparseable/binary "page" (not valid text) ──
    (HERE / "blueprint_bad_page_unreadable.html").write_bytes(b"\xff\xfe\x00\x01\x02\x80\x81not-utf8")

    print("blueprint-page fixtures generated under", HERE)


if __name__ == "__main__":
    build()
