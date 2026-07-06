# cmd_render_fidelity: the in-loop RENDERED-FIDELITY gate (B-PROP-009, fold v1.14).
#
#   cx check render-fidelity <bundle.yaml>
#
# VALIDATES a render bundle — it does NOT drive a browser. `cx render collect` (or
# verify-app) GENERATES the evidence; this check only VALIDATES it (collect != check,
# the same machine-receipt pattern as cx check boot / module-acceptance). A green
# render-fit check must mean a FRESH, pinned-profile render actually happened —
# never a hand-authored or stale screenshot.
#
# LAYER 1 (deterministic, BLOCKING):
#   RENDER-FIT-PROFILE-UNPINNED          (P0) — no pinned render_profile / empty profile_hash
#   RENDER-FIT-EVIDENCE-MISSING-OR-STALE (P0) — repo_head drift / missing screenshot file /
#                                               a required matrix row with no otherwise-valid evidence
#   RENDER-FIT-RECEIPT-FORGED            (P0) — non-machine generated_by / screenshot_hash mismatch /
#                                               render_profile_hash mismatch / unsafe screenshot_path
#   RENDER-FIT-COVERAGE-INCOMPLETE       (P0) — a required matrix row uncovered, or a ui_card with
#                                               an empty matrix and no non_user_facing_decision_ref
#   RENDER-FIT-OVERFLOW                  (P1) — horizontal overflow / max_visible_right or
#                                               content_width past the viewport (the layout defect)
#   RENDER-FIT-CONTROL-OFFSCREEN         (P1) — a locked primary control not in frame
#   RENDER-FIT-BLANK-OR-ROUTE-FAIL       (P1) — blank render / app never reached app-ready
#   RENDER-FIT-CANNOT-VERIFY             (P1) — a cannot_verify row with no preflight_pass_ref
#
# LAYER 2 (advisory WARN ONLY — never P0-P3, never changes the exit code): golden_drift
# diff_score > tolerance prints a WARN line. It graduates to a hard P1 only via a follow-up
# PROP once same-commit repeatability is proven (a perceptual diff as a hard gate today =
# the flaky-gate scar in a new hat).
#
# Severity doctrine (SEVERITY.md, review reframe): the missing / stale / forged / unpinned
# GATE is P0; the layout DEFECT (overflow / offscreen / blank) is P1 — still hard-blocks the
# turn, but it is a product defect, not a protocol failure.
#
# READ-ONLY: never builds, renders, routes actors, edits source, or generates the receipt.
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

from cx_common import findings_report, load_yaml
from cx_module_acceptance import _sha12

_HEX12_RE = re.compile(r"^[0-9a-fA-F]{12,}$")

# A small, capped epsilon so deterministic sub-pixel rounding never false-fires overflow.
_OVERFLOW_EPS = 0.5
# generated_by must name a MACHINE collector, not a human / free text — mirrors the
# boot-receipt + module-acceptance generated_by markers (collect != check).
_MACHINE_GENERATORS = {"cx render collect", "cx-render-collect", "verify-app", "cx render-collect"}


def _str(d, key) -> str:
    v = d.get(key, "") if isinstance(d, dict) else ""
    return v.strip() if isinstance(v, str) else ""


def _path_safe(rel: str, base: Path) -> bool:
    """A repo-relative, non-symlink path that resolves inside <base> (mirrors the
    module-acceptance / design-fidelity path-safety helper): an absolute path, a '..'
    escape, a symlink, or a path resolving outside the base is rejected."""
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        return False
    full = base / p
    try:
        if full.is_symlink() or not full.resolve().is_relative_to(base.resolve()):
            return False
    except OSError:
        return False
    return True


def _row_key(d) -> tuple:
    """The matrix coordinate that identifies a screen render."""
    return (_str(d, "screen_id"), _str(d, "viewport_id"),
            _str(d, "theme"), _str(d, "content_state"))


def _recompute_profile_fp(profile: dict) -> str:
    """The deterministic fingerprint of the render_profile body EXCLUDING its own
    profile_hash field. The hash must bind the profile bytes — a self-declared
    profile_hash that does not equal this is unpinned (FIX 2: profile not actually
    pinned). Canonical JSON (sorted keys, compact separators) so the bytes are stable."""
    body = {k: v for k, v in profile.items() if k != "profile_hash"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]


def _pinned_viewport_widths(profile: dict) -> dict:
    """The canonical {viewport_id: width} map the render_profile pins. A render must
    declare the widths it is allowed to render at; the receipt's measured viewport_width
    is then checked AGAINST this map (FIX 3: the receipt must not lie about its width)."""
    out = {}
    vps = profile.get("viewports") if isinstance(profile, dict) else None
    if isinstance(vps, list):
        for vp in vps:
            if isinstance(vp, dict):
                vid = _str(vp, "viewport_id")
                w = vp.get("width")
                if vid and isinstance(w, (int, float)) and not isinstance(w, bool):
                    out[vid] = w
    return out


def _evidence_is_valid(ev, current_head, profile_fp, pinned_widths, base, findings, loc) -> bool:
    """Validate ONE evidence row (freshness + receipt forgery + profile-pin + viewport-pin +
    path-safety). Appends P0 findings for any failure and returns False — a row is 'otherwise
    valid' (usable to cover a matrix row) only when this returns True. Layout P1 defects are
    checked separately (a valid-but-defective render still covers the matrix row).

    The three authoritative anchors here all come from OUTSIDE the receipt, so a
    self-consistent forged receipt cannot pass: current_head is the rail's live HEAD,
    profile_fp is recomputed from the profile bytes, pinned_widths come from the profile."""
    ok = True

    # Freshness: the evidence must be of the AUTHORITATIVE repo head (the live HEAD the rail
    # supplies via --repo-head, NOT a head the bundle declares about itself), and its screenshot
    # file must exist. The head must be PRESENT and EQUAL; a missing OR drifted head is the
    # 'green = stale screenshot' P0. An empty evidence repo_head now FAILS (it cannot prove the
    # render is of this commit), it does not skip.
    repo_head = _str(ev, "repo_head")
    if not repo_head or repo_head != current_head:
        findings.append(("P0", loc, "RENDER-FIT-EVIDENCE-MISSING-OR-STALE — evidence "
            f"repo_head '{repo_head or '(absent)'}' is missing or != the authoritative repo head "
            f"'{current_head}' (the live HEAD supplied by the rail, not declared by the bundle); the "
            "render is stale or unbound (a green render-fit check must mean a render of THIS commit, "
            "not a leftover screenshot)"))
        ok = False

    shot_rel = _str(ev, "screenshot_path")
    shot_safe = bool(shot_rel) and _path_safe(shot_rel, base)
    if not shot_safe:
        # An unsafe screenshot path is forgery-class (it lets the receipt point at arbitrary
        # bytes); also fail freshness since the file cannot be trusted to exist in-repo.
        findings.append(("P0", loc, "RENDER-FIT-RECEIPT-FORGED — screenshot_path "
            f"'{shot_rel}' is absent, absolute, a '..' escape, or a symlink/outside-repo path; the "
            "receipt must point at a real repo-relative screenshot, not arbitrary external bytes"))
        ok = False
    else:
        shot_full = base / shot_rel
        if not shot_full.is_file():
            findings.append(("P0", loc, "RENDER-FIT-EVIDENCE-MISSING-OR-STALE — screenshot "
                f"'{shot_rel}' does not exist; the render evidence is missing (collect never ran or "
                "the artifact was not committed)"))
            ok = False

    # Receipt forgery: machine-generated, screenshot-hash-bound, profile-bound. A hand-authored
    # receipt (no machine generator) or a hash that does not match the real bytes is rejected.
    gen = _str(ev, "generated_by")
    if gen not in _MACHINE_GENERATORS:
        findings.append(("P0", loc, "RENDER-FIT-RECEIPT-FORGED — generated_by "
            f"'{gen or '(absent)'}' is not a machine collector marker {sorted(_MACHINE_GENERATORS)}; "
            "the evidence must be GENERATED by the collector, not hand-authored (collect != check)"))
        ok = False

    declared_shot_hash = _str(ev, "screenshot_hash")
    if shot_safe:
        real_shot_hash = _sha12(base / shot_rel)
        if real_shot_hash is not None and declared_shot_hash != real_shot_hash:
            findings.append(("P0", loc, "RENDER-FIT-RECEIPT-FORGED — screenshot_hash "
                f"'{declared_shot_hash or '(absent)'}' != sha12 of the screenshot bytes "
                f"'{real_shot_hash}'; the receipt's screenshot hash does not bind the real file "
                "(a forged or swapped screenshot)"))
            ok = False

    # FIX 2 (profile not pinned): render_profile_hash is MANDATORY on EVERY row and must equal
    # the RECOMPUTED fingerprint of the profile bytes — never the row's own self-declared string.
    # A missing/empty hash or one that does not bind the recomputed fp is a forged receipt (the
    # render did not provably use the pinned profile). The old `if profile_hash and row_hash`
    # skip is removed: an absent row hash can no longer dodge the pin.
    row_profile_hash = _str(ev, "render_profile_hash")
    if not row_profile_hash or (profile_fp and row_profile_hash != profile_fp):
        findings.append(("P0", loc, "RENDER-FIT-RECEIPT-FORGED — render_profile_hash "
            f"'{row_profile_hash or '(absent)'}' is missing or != the profile fingerprint "
            f"recomputed from the profile bytes '{profile_fp or '(unpinned)'}'; the render did not "
            "provably use the pinned profile (a self-declared profile_hash cannot vouch for itself)"))
        ok = False

    # FIX 3 (wrong viewport — the receipt lies about its width). The measured viewport_width must
    # equal the canonical width the profile pins for this row's viewport_id. Lying about a pinned
    # render parameter to dodge the overflow check is the SAME forgery class as a forged hash, so
    # this is rated P0 (deliberately NOT the reviewer's loose P1): a receipt that claims it rendered
    # at 1440 when its viewport is the 390px phone gates the overflow math out of existence.
    m = ev.get("measured_metrics") if isinstance(ev.get("measured_metrics"), dict) else {}
    measured_vw = m.get("viewport_width")
    vid = _str(ev, "viewport_id")
    if pinned_widths:
        if vid not in pinned_widths:
            findings.append(("P0", loc, "RENDER-FIT-RECEIPT-FORGED — viewport_id "
                f"'{vid or '(absent)'}' is not a pinned profile viewport {sorted(pinned_widths)}; "
                "the receipt rendered at an unpinned viewport the profile never declared"))
            ok = False
        elif not isinstance(measured_vw, (int, float)) or isinstance(measured_vw, bool) \
                or measured_vw != pinned_widths[vid]:
            findings.append(("P0", loc, "RENDER-FIT-RECEIPT-FORGED — viewport_width "
                f"{measured_vw} != pinned profile width {pinned_widths[vid]} for viewport_id "
                f"'{vid}' — the receipt lies about the viewport it rendered at, gaming the overflow "
                "check"))
            ok = False

    return ok


def _git_diff_touched(repo_root: str, base_sha: str, head_sha: str) -> tuple[list | None, str | None]:
    """PBF-PROP-020: the authoritative, non-self-declared touched-file set — `git diff --name-only
    base_sha..head_sha`. Returns (files, error). Fail closed on a bad repo/sha rather than treating
    an error as 'nothing touched' (which would silently exempt every screen)."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, "diff", "--name-only", base_sha, head_sha],
            capture_output=True, text=True,
        )
    except OSError as e:
        return None, str(e)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or "git diff failed").strip()
    return [ln for ln in result.stdout.splitlines() if ln.strip()], None


def _touched_screens(registry_rows: list, touched_files: list) -> set:
    """The touched CEO-visible screen-set: a registry 'screen' row whose declared `files` (the
    screen->file binding authored on the row) intersects the git-touched file set."""
    touched = set(touched_files)
    out = set()
    for m in registry_rows:
        if not isinstance(m, dict) or str(m.get("kind", "")).strip() != "screen":
            continue
        sid = str(m.get("screen_id", "") or "").strip()
        files = m.get("files") or []
        if sid and isinstance(files, list) and any(str(f) in touched for f in files):
            out.add(sid)
    return out


def _resolve_git_touched_scope(raw: dict, args, base: Path, findings: list, loc: str) -> set | None:
    """PBF-PROP-020 Rules 2 + 7: resolve the git-touched CEO-visible screen-set from --repo-root +
    --packet-dir + bundle.repo_sha_before. Returns None (Rules 2/7 do not apply — e.g. a legacy
    bundle/project with no registry wired) UNLESS the caller supplied enough to attempt resolution,
    in which case a resolution failure is a P0 finding (fail-closed) and this still returns None so
    the caller does not also double-report on an unusable touched-set."""
    repo_root = getattr(args, "repo_root", None)
    packet_dir_rel = getattr(args, "packet_dir", None)
    if not repo_root or not packet_dir_rel:
        return None
    repo_sha_before = str(raw.get("repo_sha_before", "") or "").strip()
    if not repo_sha_before:
        # PBF-PROP-020 fold re-sweep fix (CEO-D-046 grandfather made MECHANICAL): a render bundle
        # with the repo/packet flags supplied but NO repo_sha_before can no longer go DORMANT by
        # bare omission — that was a fail-OPEN dodge (new work drops the field and Rules 2/7 vanish,
        # the exact self-declared-opt-in hole the v2 rework was built to kill). The pre-020 legacy
        # carve-out is now an EXPLICIT typed marker, mirroring BF-PROP-006's legacy_no_baseline —
        # never a silent absence. A genuine pre-020 bundle DECLARES `legacy_no_baseline: <reason>`
        # (dormant, advisory WARN — migration debt); a 020-era bundle DECLARES repo_sha_before; a
        # bare omission fails closed. (Return None after the P0 so the caller does not also
        # double-report on an unusable touched-set — same posture as the malformed-hex branch below.)
        carveout = str(raw.get("legacy_no_baseline", "") or "").strip()
        if carveout:
            print(f"WARN: render bundle has no repo_sha_before (legacy_no_baseline: {carveout}) — "
                  "PBF-PROP-020 Rules 2/7 dormant for this pre-020 bundle (migration debt)")
            return None
        findings.append(("P0", loc,
            "--repo-root/--packet-dir supplied but the render bundle has no repo_sha_before — the "
            "git-touched CEO-visible scope cannot be derived, so RENDER-COVERS-GIT-TOUCHED / "
            "UNPICTURED-STATE-IS-GAP would silently not run; a 020-era bundle MUST declare "
            "repo_sha_before (or a typed legacy_no_baseline carve-out for a genuine pre-020 bundle) "
            "— omission is no longer a free dormant pass (PBF-PROP-020 Rule 2/7, fail-closed)"))
        return None
    if not _HEX12_RE.match(repo_sha_before):
        findings.append(("P0", loc,
            f"--repo-root/--packet-dir supplied but bundle.repo_sha_before "
            f"'{repo_sha_before}' is not a hex commit id of >=12 chars — the "
            "git-touched scope cannot be derived without a real baseline (PBF-PROP-020 Rule 2/7)"))
        return None
    current_head = str(getattr(args, "repo_head", "") or "").strip()
    touched_files, derr = _git_diff_touched(repo_root, repo_sha_before, current_head)
    if derr is not None:
        findings.append(("P0", loc,
            f"cannot compute the git-touched file set ({repo_sha_before}..{current_head} in "
            f"'{repo_root}'): {derr} — the git-touched scope cannot be derived (PBF-PROP-020 Rule 2/7)"))
        return None
    from cx_lock_fidelity import frozen_registry_rows
    rows, rerr = frozen_registry_rows(repo_root, packet_dir_rel)
    if rerr:
        findings.append(("P0", loc,
            f"cannot resolve MODULE-REGISTRY.yaml for the git-touched scope — {rerr} "
            "(PBF-PROP-020 Rule 2/7)"))
        return None
    return _touched_screens(rows, touched_files)


def cmd_render_fidelity(args) -> int:
    bundle_path = args.bundle

    raw, err = load_yaml(bundle_path)
    if err:
        print(f"FIX-FIRST\n  [P0] {bundle_path} — {err}")
        return 1
    if not isinstance(raw, dict):
        print(f"FIX-FIRST\n  [P0] {bundle_path} — render bundle is not a YAML mapping")
        return 1

    findings = []
    loc = bundle_path
    base = Path(bundle_path).resolve().parent
    # FIX 1 (stale render): the AUTHORITATIVE head is the live HEAD the rail supplies via
    # --repo-head — NOT the bundle's own current_repo_head (a self-comparison the receipt could
    # satisfy by declaring an old head on both sides). The bundle no longer gets to vouch for its
    # own freshness.
    current_head = str(getattr(args, "repo_head", "") or "").strip()
    if not current_head:
        # Defensive: the subparser makes --repo-head REQUIRED, so this should be unreachable from
        # the CLI; fail closed rather than silently compare against an empty head.
        print("FIX-FIRST\n  [P0] render-fidelity invoked without an authoritative --repo-head; the "
              "rail must supply the live repo HEAD (freshness cannot be proven against an empty head)")
        return 1

    # 4.1 Pinned render profile (the determinism P0). FIX 2: the profile_hash must BIND the profile
    # bytes — recompute the fingerprint and require the self-declared profile_hash to equal it.
    profile = raw.get("render_profile")
    profile_hash = _str(profile, "profile_hash") if isinstance(profile, dict) else ""
    profile_fp = ""
    pinned_widths = {}
    if not isinstance(profile, dict) or not profile_hash:
        findings.append(("P0", loc, "RENDER-FIT-PROFILE-UNPINNED — render_profile is missing or its "
            "profile_hash is empty; without a hashed pinned profile (Chromium revision, viewport, "
            "fonts, color-scheme, network-blocked, fixture data) a render is non-deterministic and a "
            "green check proves nothing"))
    else:
        profile_fp = _recompute_profile_fp(profile)
        pinned_widths = _pinned_viewport_widths(profile)
        if profile_hash != profile_fp:
            findings.append(("P0", loc, "RENDER-FIT-PROFILE-UNPINNED — profile_hash "
                f"'{profile_hash}' does not bind the profile body (recomputed fingerprint "
                f"'{profile_fp}'); a self-declared profile_hash that does not equal the hash of the "
                "profile bytes pins nothing — any string would satisfy it"))

    # The evidence rows, keyed by their matrix coordinate (the FIRST otherwise-valid row wins).
    evidence = raw.get("render_evidence") if isinstance(raw.get("render_evidence"), list) else []
    valid_by_key = {}      # coordinate -> the first valid evidence row
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        ev_loc = f"{bundle_path} (evidence {_str(ev, 'card_id') or '?'} / {_str(ev, 'screen_id') or '?'})"

        # FIX 2/FIX 3: profile-hash recompute and viewport-pin are enforced INSIDE _evidence_is_valid
        # (mandatory per-row, recomputed/pinned from outside the receipt — no row may dodge the pin).
        is_valid = _evidence_is_valid(ev, current_head, profile_fp, pinned_widths, base, findings, ev_loc)

        # 4.8 cannot-verify: a cannot_verify row must be backed by a preflight pass — env-absence
        # is a typed protocol deviation, never a blanket per-card waiver.
        if ev.get("cannot_verify") is True or str(ev.get("cannot_verify", "")).strip().lower() in ("true", "yes"):
            if not _str(ev, "preflight_pass_ref"):
                findings.append(("P1", ev_loc, "RENDER-FIT-CANNOT-VERIFY — evidence row carries "
                    "cannot_verify: true with no preflight_pass_ref; env-absence must be backed by a "
                    "render-capability preflight pass, never a blanket per-card waiver"))

        # 4.4 the objective layout defects (a VALID render can still be DEFECTIVE — a defective
        # render still 'covers' the matrix row; the defect is the product P1).
        m = ev.get("measured_metrics") if isinstance(ev.get("measured_metrics"), dict) else {}
        vw = m.get("viewport_width")
        cw = m.get("content_width")
        mvr = m.get("max_visible_right")
        overflow = m.get("has_horizontal_overflow") is True
        if not overflow and isinstance(mvr, (int, float)) and isinstance(vw, (int, float)):
            overflow = math.ceil(mvr) > vw
        if not overflow and isinstance(cw, (int, float)) and isinstance(vw, (int, float)):
            overflow = cw > vw + _OVERFLOW_EPS
        if overflow:
            findings.append(("P1", ev_loc, "RENDER-FIT-OVERFLOW — the rendered screen overflows its "
                f"viewport (viewport_width={vw}, content_width={cw}, max_visible_right={mvr}, "
                "has_horizontal_overflow flagged); a phone-target screen rendering wider than its "
                "viewport is the layout-drift defect this gate exists to catch"))

        for ctrl in (m.get("controls_in_frame") or []):
            if isinstance(ctrl, dict) and ctrl.get("in_frame") is False:
                findings.append(("P1", ev_loc, "RENDER-FIT-CONTROL-OFFSCREEN — locked primary control "
                    f"'{_str(ctrl, 'id') or '?'}' is not in frame; an off-screen primary control fails "
                    "the screen even when the page does not horizontally overflow"))

        if m.get("nonblank") is False or m.get("app_ready") is False:
            findings.append(("P1", ev_loc, "RENDER-FIT-BLANK-OR-ROUTE-FAIL — the render is blank or the "
                f"app never reached app-ready (nonblank={m.get('nonblank')}, app_ready={m.get('app_ready')}); "
                "a blank error page has no overflow and would otherwise pass the width checks"))

        if is_valid:
            valid_by_key.setdefault(_row_key(ev), ev)

    # 4.3 frozen coverage matrix: every required row must have an otherwise-valid evidence row.
    cm = raw.get("coverage_matrix") if isinstance(raw.get("coverage_matrix"), dict) else {}
    required_rows = cm.get("required_rows") if isinstance(cm.get("required_rows"), list) else []
    ui_card = cm.get("ui_card") is True or str(cm.get("ui_card", "")).strip().lower() in ("true", "yes")
    non_user_facing = _str(cm, "non_user_facing_decision_ref")

    if ui_card and not required_rows and not non_user_facing:
        findings.append(("P0", loc, "RENDER-FIT-COVERAGE-INCOMPLETE — coverage_matrix.ui_card is true but "
            "required_rows is empty and there is no non_user_facing_decision_ref; a card touching "
            "templates/routes/static UI fails closed unless a typed CEO decision marks it non-user-facing"))

    for row in required_rows:
        if not isinstance(row, dict):
            continue
        key = _row_key(row)
        if key not in valid_by_key:
            findings.append(("P0", loc, "RENDER-FIT-COVERAGE-INCOMPLETE — required matrix row "
                f"screen_id={key[0]!r} viewport_id={key[1]!r} theme={key[2]!r} content_state={key[3]!r} "
                "has no otherwise-valid render evidence; every required render row must carry fresh, "
                "non-forged evidence (no row may silently ship unrendered)"))

    # PBF-PROP-020 Rules 2 + 7: the git-touched CEO-visible screen-set (None when --repo-root /
    # --packet-dir were not supplied — Rules 2/7 then do not apply, matching the design's scoped-not-
    # global posture; a resolution FAILURE when the flags WERE supplied is a P0 above, not a skip).
    touched_screens = _resolve_git_touched_scope(raw, args, base, findings, loc)

    if touched_screens is not None:
        required_screen_ids = {_row_key(r)[0] for r in required_rows if isinstance(r, dict)}
        # RENDER-COVERS-GIT-TOUCHED (P0): every git-touched CEO-visible screen must appear in
        # coverage_matrix.required_rows — the bundle can no longer hide a touched screen by omission.
        for sid in sorted(touched_screens - required_screen_ids):
            findings.append(("P0", loc,
                f"RENDER-COVERS-GIT-TOUCHED — screen_id={sid!r} was touched by this build "
                f"(git diff vs repo_sha_before) but has NO row in coverage_matrix.required_rows; a "
                "touched CEO-visible screen cannot be omitted from the bundle's own required set "
                "(PBF-PROP-020 Rule 2)"))

        # UNPICTURED-STATE-IS-GAP (P0): resolve pictured_states from the HASH-BOUND lock manifest via
        # the registry lock_ref (never a bundle-local copy) — a touched (screen_id, content_state) not
        # in the lock's pictured_states is a coverage GAP the builder must stop on.
        from cx_lock_fidelity import frozen_registry_rows, registry_screen_lock, resolve_in_repo
        repo_root = getattr(args, "repo_root", None)
        packet_dir_rel = getattr(args, "packet_dir", None)
        reg_rows, _rerr = frozen_registry_rows(repo_root, packet_dir_rel) if repo_root and packet_dir_rel else (None, None)
        pictured_by_screen: dict = {}
        if reg_rows is not None:
            for sid in touched_screens:
                live_lock, lerr = registry_screen_lock(reg_rows, sid)
                if lerr or not live_lock:
                    continue
                lock_target, lp_err = resolve_in_repo(repo_root, live_lock)
                if lp_err or lock_target is None or not lock_target.is_file():
                    continue
                lock_raw, _le = load_yaml(str(lock_target))
                lock_body = (lock_raw.get("ui_lock_manifest") if isinstance(lock_raw, dict)
                            and isinstance(lock_raw.get("ui_lock_manifest"), dict) else lock_raw)
                ps = lock_body.get("pictured_states") if isinstance(lock_body, dict) else None
                pictured_by_screen[sid] = {
                    (str(p.get("screen_id", "") or "").strip(), str(p.get("content_state", "") or "").strip())
                    for p in ps if isinstance(p, dict)
                } if isinstance(ps, list) else set()

        for row in required_rows:
            if not isinstance(row, dict):
                continue
            sid, _vid, _theme, cstate = _row_key(row)
            if sid not in touched_screens or sid not in pictured_by_screen:
                continue
            if (sid, cstate) not in pictured_by_screen[sid]:
                findings.append(("P0", loc,
                    f"UNPICTURED-STATE-IS-GAP — touched screen_id={sid!r} content_state={cstate!r} "
                    "is absent from the lock's pictured_states — an unpictured state is a coverage "
                    "GAP, not an improvised builder judgment call (PBF-PROP-020 Rule 7)"))

    # LAYER 2 — golden-drift. Untouched screens stay ADVISORY WARN ONLY (never a finding, never
    # changes the exit code). A git-touched screen's drift is PBF-PROP-020 Rule 2's
    # GOLDEN-DRIFT-BLOCKS-TOUCHED (P1) — flipped from WARN to a blocking finding.
    golden = raw.get("golden_drift") if isinstance(raw.get("golden_drift"), list) else []
    for g in golden:
        if not isinstance(g, dict):
            continue
        diff_score = g.get("diff_score")
        tolerance = g.get("tolerance")
        if isinstance(diff_score, (int, float)) and isinstance(tolerance, (int, float)) and diff_score > tolerance:
            g_sid = _str(g, "screen_id")
            if touched_screens is not None and g_sid in touched_screens:
                findings.append(("P1", loc,
                    f"GOLDEN-DRIFT-BLOCKS-TOUCHED — screen_id={g_sid!r} "
                    f"viewport_id={_str(g, 'viewport_id') or '?'} diff_score={diff_score} > "
                    f"tolerance={tolerance} vs baseline {_str(g, 'baseline_ref') or '?'} on a "
                    "GIT-TOUCHED CEO-visible screen — blocking (PBF-PROP-020 Rule 2), not advisory"))
            else:
                print(f"WARN: golden-drift screen_id={g_sid or '?'} "
                      f"viewport_id={_str(g, 'viewport_id') or '?'} diff_score={diff_score} > "
                      f"tolerance={tolerance} vs baseline {_str(g, 'baseline_ref') or '?'} — ADVISORY only "
                      "(untouched screen; Layer 2 graduates to a blocking P1 via a follow-up PROP once "
                      "same-commit repeatability is proven for the general case)")

    return findings_report(findings)
