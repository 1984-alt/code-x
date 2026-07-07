# cmd_design_fidelity: deterministic UI-fidelity gate (B-PROP-003, G3/G6).
#
# Compares a live DOM snapshot (saved HTML / accessibility-tree dump) against the
# locked reference's ui_marker_manifest, authored at design-lock time:
#
#   ui_marker_manifest:
#     screen_id:
#     route:
#     required_regions:   [{id: top_tabs}, ...]          # id= / data-cx= / data-region=
#     required_controls:  [{data_fn: add_expense, label:, role:}, ...]
#     required_shell:     [{selector: "#app-shell", purpose:}, ...]
#     forbidden_missing:  [top_tabs, add_expense, ...]   # absence of these = P1 (else P2)
#
#   cx check design-fidelity --manifest <yaml> --dom <html> --screenshot <png>
#
# Marker manifest + DOM = the deterministic gate; the screenshot is supporting
# evidence (viewport / visible shell / no blank page) — pixel-AI is never the
# primary gate. Missing screenshot = P1 (no visual support proof).
from html.parser import HTMLParser
from pathlib import Path

from cx_common import findings_report, load_yaml
from cx_module_acceptance import _sha12

SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# HTML void elements (no end tag, per WHATWG) — mirrors cx_blueprint_page._VOID_ELEMENTS:
# closed immediately on the open tag so an unclosed stack entry never leaks trailing markup
# into an unrelated element's descendant text.
_VOID_ELEMENTS = frozenset({
    "br", "img", "input", "hr", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr",
})

# PBF-PROP-021 P2-2 (GPT-5.5 xhigh built-code review): elements whose text is never RENDERED
# content — a browser never shows script/style/template bodies as visible text. hole #11
# (round 1) already closed the region-MARKER spoof (an id inside a <script> string is text data,
# never a parsed attribute, so _marker_in_dom never sees it). The residual gap was the control
# LABEL check, which matches against el["text"] — and the OLD handle_data below fed a <script>'s
# CDATA text to every currently-open ANCESTOR's text too, so `<button ...><script>var s="Add
# expense"</script></button>` let the script string satisfy the button's locked label. Text
# inside one of these tags must not reach ANY ancestor's text — not just its own.
_NON_VISIBLE_TEXT_TAGS = frozenset({"script", "style", "template"})


class _DomIndex(HTMLParser):
    """Parses the live DOM snapshot into real elements (tag + attrs + full descendant text),
    using stdlib html.parser only (no new dependency — mirrors cx_blueprint_page._MarkerParser).
    Every marker/selector/control check below matches against this PARSED element list, never a
    raw substring over the HTML source: a marker id sitting inside an HTML comment
    (handle_comment is a no-op here — the content is dropped, not indexed) or inside a <script>
    string literal (script/style bodies are stdlib CDATA text delivered to handle_data, never
    parsed into tags/attributes) is NOT a live DOM element and must not satisfy the gate
    (PBF-PROP-021 hole #11 — the substring/naive-regex false-PASS). Text inside script/style/
    template is likewise excluded from every ancestor's accumulated text, so it cannot spoof a
    required control LABEL either (PBF-PROP-021 P2-2)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: list[dict] = []   # each: {"tag": str, "attrs": {lower_name: value}, "text": [str, ...]}
        self._stack: list[dict] = []      # currently open elements, innermost last

    def _open(self, tag, attrs):
        ad = {}
        for k, v in attrs:
            if k is None:
                continue
            ad[k.lower()] = v if v is not None else ""
        el = {"tag": tag.lower(), "attrs": ad, "text": []}
        self.elements.append(el)
        self._stack.append(el)
        return el

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs)
        if tag.lower() in _VOID_ELEMENTS:
            self._close()

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs)
        self._close()

    def _close(self):
        if self._stack:
            self._stack.pop()

    def handle_endtag(self, tag):
        self._close()

    def handle_data(self, data):
        # every currently-open ancestor accumulates the text (full descendant textContent,
        # matching how a browser reads it — a nested <span> inside a control still counts) —
        # UNLESS the innermost open element is script/style/template, whose body is never
        # rendered text and must not reach ANY ancestor (PBF-PROP-021 P2-2).
        if self._stack and self._stack[-1]["tag"] in _NON_VISIBLE_TEXT_TAGS:
            return
        for el in self._stack:
            el["text"].append(data)


def parse_dom(dom_text: str) -> list[dict]:
    """Parse a DOM snapshot into its element list. html.parser is lenient (never raises on
    malformed markup); a belt-and-suspenders try/except keeps this fail-closed-safe like the
    blueprint-page parser — on a genuine parse exception, the caller sees an EMPTY element list
    (every marker/selector/control then correctly reads as missing, never as present)."""
    idx = _DomIndex()
    try:
        idx.feed(dom_text)
        idx.close()
    except Exception:
        return []
    return idx.elements


def _marker_in_dom(elements: list[dict], marker_id: str) -> bool:
    """A region/marker id counts as present only on a REAL parsed element via any of the
    stable attribute forms — never a raw substring over the HTML text."""
    return any(el["attrs"].get(attr) == marker_id
               for el in elements for attr in ("id", "data-cx", "data-region"))


def _selector_in_dom(elements: list[dict], selector: str) -> bool:
    """Deterministic subset of CSS selector presence, matched against PARSED elements:
    #id, .class, [attr="v"] / [attr] (presence-only), or an attribute-name fallback for
    anything else unsupported — never a raw substring over the HTML source."""
    sel = selector.strip()
    if sel.startswith("#"):
        target = sel[1:]
        return any(el["attrs"].get("id") == target for el in elements)
    if sel.startswith(".") and " " not in sel:
        cls = sel[1:]
        return any(cls in (el["attrs"].get("class") or "").split() for el in elements)
    if sel.startswith("[") and sel.endswith("]"):
        inner = sel[1:-1].replace("'", '"')
        if "=" in inner:
            k, v = inner.split("=", 1)
            return any(el["attrs"].get(k.strip().lower()) == v.strip().strip('"') for el in elements)
        return any(inner.strip().lower() in el["attrs"] for el in elements)
    # any other selector shape is not a supported deterministic form — fail closed (absent),
    # never a substring guess over raw markup.
    return False


def _find_by_attr(elements: list[dict], attr: str, value: str) -> dict | None:
    for el in elements:
        if el["attrs"].get(attr) == value:
            return el
    return None


def cmd_design_fidelity(args) -> int:
    manifest_path = args.manifest
    dom_path = args.dom
    screenshot_path = args.screenshot

    raw, err = load_yaml(manifest_path)
    if err:
        print(f"FIX-FIRST\n  [P0] {manifest_path} — {err}")
        return 1
    # B-PROP-004: ui_marker_manifest extended into ui_lock_manifest (one owner = this
    # check, never a parallel gate). Legacy ui_marker_manifest still accepted.
    is_lock_manifest = isinstance(raw, dict) and isinstance(raw.get("ui_lock_manifest"), dict)
    manifest = (raw.get("ui_lock_manifest") if is_lock_manifest
                else raw.get("ui_marker_manifest")) if isinstance(raw, dict) else None
    if not isinstance(manifest, dict):
        print(f"FIX-FIRST\n  [P0] {manifest_path} — no ui_lock_manifest / ui_marker_manifest "
              "mapping (authored at design-lock time; without it there is nothing mechanical to compare)")
        return 1

    findings = []
    loc = dom_path

    if not is_lock_manifest:
        if getattr(args, "legacy_migration", False):
            # In-flight project on a legacy marker-manifest: advisory migration-debt path
            # until the next clean module boundary (the marker checks below still bite).
            print(f"WARN: {manifest_path} is a legacy ui_marker_manifest — no audit_status/"
                  "ceo_acceptance_ref enforced; migration-debt path (--legacy-migration). "
                  "Migrate to ui_lock_manifest (B-PROP-004).")
        else:
            # V1.10: NEW builds get NO advisory escape — design-fidelity BLOCKS. A UI module
            # needs an audited + CEO-accepted ui_lock_manifest (audit_status PASS +
            # ceo_acceptance_ref); a bare legacy marker-manifest cannot ship a new build.
            findings.append(("P0", manifest_path,
                "legacy ui_marker_manifest on a NEW build — design-fidelity BLOCKS (V1.10): a UI "
                "module needs an audited + CEO-accepted ui_lock_manifest; the advisory-WARN escape "
                "is removed for new builds (pass --legacy-migration ONLY for an in-flight project's "
                "documented migration debt)"))
    if is_lock_manifest:
        # B-PROP-004: planning-authored, opposite-family audited, CEO-accepted, hash-frozen —
        # the builder only CONSUMES it. No PASS = no build.
        if str(manifest.get("audit_status", "")).upper() != "PASS":
            findings.append(("P0", manifest_path,
                "ui_lock_manifest.audit_status is not PASS — the lock manifest must be "
                "opposite-family audited against the frozen lock before any build "
                "consumes it (no PASS = no build, B-PROP-004)"))
        if not str(manifest.get("ceo_acceptance_ref", "") or "").strip():
            findings.append(("P0", manifest_path,
                "ui_lock_manifest.ceo_acceptance_ref missing — the CEO accepts the lock "
                "manifest before the builder consumes it (B-PROP-004)"))

        # LOCK-ACCEPTANCE-CITES-RENDERED (P1, PBF-PROP-020 Rule 3): a lock acceptance that DECLARES
        # chosen_from must cite >=2 hash-matched RENDERED artifacts the CEO chose FROM — never a
        # worded/numbered option list. FORWARD-SCOPE (CEO-D-046 grandfather, 2026-07-05): a pre-020
        # accepted lock that OMITS chosen_from is grandfathered (untouched — never retro-broken).
        # WHY OMISSION STAYS GRANDFATHERED HERE (and is NOT forced like repo_sha_before/render_bundle):
        # chosen_from lives on a lock manifest that is FROZEN inside the packet hash — forcing it
        # would retro-break every live project's already-frozen pre-020 lock (already-shipped apps), the exact
        # thing CEO-D-046 protects. The residual (a lock accepted on a word-only pick) is BACKSTOPPED
        # by the now-fail-closed primary gates: Rule 1 (card must cite the live lock) + Rule 2 (the
        # card must declare a render_bundle AND the bundle must declare repo_sha_before, both made
        # fail-closed in the fold re-sweep) block any real look-change regardless of chosen_from. A
        # NEW lock that DOES declare chosen_from is fully enforced (>=2 hash-matched rendered picks).
        chosen_from = manifest.get("chosen_from")
        if chosen_from is not None:
            base_dir = Path(manifest_path).resolve().parent
            valid_rendered = 0
            if isinstance(chosen_from, list):
                for row in chosen_from:
                    if not isinstance(row, dict):
                        continue
                    rpath = str(row.get("path", "") or "").strip()
                    rhash = str(row.get("hash", "") or "").strip()
                    if not rpath or not rhash:
                        continue
                    rp = Path(rpath)
                    if rp.is_absolute() or ".." in rp.parts:
                        continue
                    full = base_dir / rp
                    try:
                        if full.is_symlink() or not full.resolve().is_relative_to(base_dir.resolve()):
                            continue
                    except OSError:
                        continue
                    if not full.is_file():
                        continue
                    if _sha12(full) == rhash:
                        valid_rendered += 1
            if valid_rendered < 2:
                findings.append(("P1", manifest_path,
                    f"ui_lock_manifest.chosen_from has only {valid_rendered} hash-matched, in-repo "
                    "rendered artifact(s) — a lock acceptance needs >=2 RENDERED options the CEO chose "
                    "FROM (path+hash, file exists, hash matches real bytes); a worded/numbered option "
                    "list is not a rendered pick (LOCK-ACCEPTANCE-CITES-RENDERED, PBF-PROP-020 Rule 3)"))

    # ui_lock_manifest section names (dom_markers · controls · shell_regions) with
    # legacy ui_marker_manifest aliases.
    regions = [r for r in (manifest.get("dom_markers") or manifest.get("required_regions") or [])
               if isinstance(r, dict)]
    controls = [c for c in (manifest.get("controls") or manifest.get("required_controls") or [])
                if isinstance(c, dict)]
    shell = [s for s in (manifest.get("shell_regions") or manifest.get("required_shell") or [])
             if isinstance(s, dict)]
    forbidden_missing = {str(x) for x in (manifest.get("forbidden_missing") or [])}

    if not regions and not controls:
        findings.append(("P1", manifest_path,
            "ui_marker_manifest has no required_regions and no required_controls — "
            "nothing deterministic to compare; re-author the manifest at the locked reference"))

    try:
        dom_text = Path(dom_path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"FIX-FIRST\n  [P0] {dom_path} — DOM snapshot unreadable: {e}")
        return 1
    elements = parse_dom(dom_text)

    def _sev(marker: str) -> str:
        return "P1" if marker in forbidden_missing else "P2"

    for region in regions:
        rid = str(region.get("id", ""))
        if rid and not _marker_in_dom(elements, rid):
            findings.append((_sev(rid), loc,
                f"required region '{rid}' missing from live DOM — the CEO-accepted shell "
                "drifted (G3 fixture-purge semantics: replace data, preserve shell)"))

    for control in controls:
        fn = str(control.get("data_fn", ""))
        if not fn:
            continue
        el = _find_by_attr(elements, "data-fn", fn)
        if el is None:
            findings.append((_sev(fn), loc,
                f"required control data-fn=\"{fn}\" missing from live DOM — approved "
                "controls must survive the engine wave"))
            continue
        # Marker-stuffing guard (GPT cross-review): the marker must sit on a real,
        # visible control with the locked role + label — a hidden stub on a generic
        # template must not read green. Matched against the PARSED element's own
        # attrs/text — a marker inside a comment/JS string is not a real element and
        # never reaches this point (PBF-PROP-021 hole #11).
        attrs = el["attrs"]
        style = (attrs.get("style") or "").replace(" ", "")
        if "hidden" in attrs or "display:none" in style:
            findings.append((_sev(fn), loc,
                f"control data-fn=\"{fn}\" is a hidden stub — marker present but the "
                "control is not visible"))
        role = str(control.get("role", "") or "")
        if role and attrs.get("role") != role:
            findings.append((_sev(fn), loc,
                f"control data-fn=\"{fn}\" lacks locked role \"{role}\" in its element"))
        label = str(control.get("label", "") or "")
        if label:
            inner = "".join(el["text"])
            if (label not in inner and attrs.get("aria-label") != label
                    and attrs.get("value") != label):
                findings.append((_sev(fn), loc,
                    f"control data-fn=\"{fn}\" lacks locked label \"{label}\" "
                    "(element text, aria-label, or value)"))

    for entry in shell:
        sel = str(entry.get("selector", ""))
        if sel and not _selector_in_dom(elements, sel):
            findings.append((_sev(sel), loc,
                f"required shell selector '{sel}' missing from live DOM"))

    # B-PROP-004 lock-vocabulary coverage: translation_keys · ui_states · alert_variants.
    # --build-vocab = the vocabulary actually used by the build (extracted mechanically).
    # Build vocabulary absent from the manifest = INVENTED vocabulary (P1); manifest
    # vocabulary absent from the build = drift (P2).
    build_vocab_path = getattr(args, "build_vocab", None)
    locked_vocab_sections = [s for s in ("translation_keys", "ui_states", "alert_variants")
                             if manifest.get(s)]
    if locked_vocab_sections and not build_vocab_path:
        # GPT cross-review 2026-06-12: when the lock carries vocabulary, the check
        # is not optional — omitting --build-vocab leaves coverage unverified.
        findings.append(("P1", manifest_path,
            f"ui_lock_manifest locks vocabulary ({', '.join(locked_vocab_sections)}) but "
            "no --build-vocab was supplied — vocabulary coverage UNVERIFIED; extract the "
            "build's vocabulary and pass it (B-PROP-004)"))
    if build_vocab_path:
        bv_raw, bv_err = load_yaml(build_vocab_path)
        if bv_err or not isinstance(bv_raw, dict):
            findings.append(("P0", build_vocab_path,
                f"build vocabulary file unreadable: {bv_err or 'not a mapping'}"))
        else:
            bv = bv_raw.get("build_vocabulary") if isinstance(bv_raw.get("build_vocabulary"), dict) else bv_raw
            for section in ("translation_keys", "ui_states", "alert_variants"):
                locked = {str(x) for x in (manifest.get(section) or [])}
                built = {str(x) for x in (bv.get(section) or [])}
                for entry in sorted(built - locked):
                    findings.append(("P1", build_vocab_path,
                        f"build {section} entry '{entry}' absent from the ui_lock_manifest — "
                        "invented vocabulary; the builder consumes the lock, it never "
                        "extends it (B-PROP-004)"))
                for entry in sorted(locked - built):
                    findings.append(("P2", loc,
                        f"ui_lock_manifest {section} entry '{entry}' missing from the build — "
                        "locked vocabulary drifted (B-PROP-004)"))

    # Screenshot = supporting evidence; existence + non-trivial size only (no pixel-AI).
    shot = Path(screenshot_path)
    if not shot.is_file() or shot.stat().st_size == 0:
        findings.append(("P1", screenshot_path,
            "screenshot missing or empty — visual support proof (viewport / visible "
            "shell / no blank page) is required alongside the DOM marker check"))
    elif shot.suffix.lower() not in SCREENSHOT_EXTS:
        findings.append(("P2", screenshot_path,
            f"screenshot extension '{shot.suffix}' not in {sorted(SCREENSHOT_EXTS)}"))

    # P-PROP-004: external-visual-reference lock binding + side-by-side ACCEPT receipt.
    # When the lock's baseline is an external app capture (not team-produced output), the
    # lock must trace to the captured reference and the CEO must have ACCEPTED the produced
    # screen side-by-side with that reference at the target viewport. cx check packet owns
    # the cross-file capture hashes; this owns the lock-side binding + receipt shape.
    if is_lock_manifest and str(manifest.get("baseline_source", "")).strip() == "external_capture":
        for f in ("external_reference_ref", "capture_ids", "capture_manifest_hash", "viewport_ids"):
            if not manifest.get(f):
                findings.append(("P1", manifest_path,
                    f"ui_lock_manifest.baseline_source is external_capture but '{f}' is missing — "
                    "the lock baseline must trace to the captured external reference, not to "
                    "team-produced output (P-PROP-004)"))
        receipt = manifest.get("side_by_side_accept")
        if not isinstance(receipt, dict):
            findings.append(("P0", manifest_path,
                "external_capture lock has no side_by_side_accept receipt — the CEO must ACCEPT the "
                "produced screen side-by-side with the captured reference at the target viewport "
                "before G7 (the gap that let 'like MM' ship from memory, P-PROP-004)"))
        else:
            req = ("produced_screen_hash", "reference_capture_hash", "viewport_id",
                   "produced_dimensions", "reference_dimensions", "composite_path",
                   "ceo_acceptance_ref")
            miss = [k for k in req if not str(receipt.get(k, "") or "").strip()]
            if miss:
                findings.append(("P0", manifest_path,
                    f"side_by_side_accept receipt missing {miss} — an ACCEPT with no reference "
                    "in-frame is not a valid taste gate (P-PROP-004)"))
            pd = str(receipt.get("produced_dimensions", "") or "").strip()
            rd = str(receipt.get("reference_dimensions", "") or "").strip()
            if pd and rd and pd != rd:
                findings.append(("P1", manifest_path,
                    f"side_by_side_accept produced_dimensions ({pd}) != reference_dimensions ({rd}) "
                    "— not judged at the same viewport (P-PROP-004)"))
            comp = str(receipt.get("composite_path", "") or "").strip()
            if comp:
                cp = Path(comp)
                if cp.is_absolute() or ".." in cp.parts:
                    findings.append(("P1", manifest_path,
                        f"side_by_side_accept composite_path '{comp}' must be lock-relative, no "
                        "'..'/absolute (P-PROP-004)"))
                else:
                    base = Path(manifest_path).resolve().parent
                    full = base / cp
                    try:
                        escapes = full.is_symlink() or not full.resolve().is_relative_to(base)
                    except OSError:
                        escapes = True
                    if escapes:
                        findings.append(("P1", manifest_path,
                            f"side_by_side_accept composite_path '{comp}' is a symlink or resolves "
                            "outside the lock directory — no symlink-ancestor escape (P-PROP-004)"))
                    elif not full.is_file():
                        findings.append(("P1", manifest_path,
                            f"side_by_side_accept composite_path '{comp}' is not a real file beside "
                            "the lock — the side-by-side image must exist (P-PROP-004)"))

    return findings_report(findings)
