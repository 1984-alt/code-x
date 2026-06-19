# cmd_design_fidelity: deterministic UI-fidelity gate (PROP-019, G3/G6).
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
import re
from pathlib import Path

from cx_common import findings_report, load_yaml

SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _marker_in_dom(dom: str, marker_id: str) -> bool:
    """A region/marker id counts as present via any of the stable attribute forms."""
    return any(f'{attr}="{marker_id}"' in dom
               for attr in ("id", "data-cx", "data-region"))


def _selector_in_dom(dom: str, selector: str) -> bool:
    """Deterministic subset of CSS selector presence: #id, .class, [attr="v"],
    or a literal substring for anything else."""
    sel = selector.strip()
    if sel.startswith("#"):
        return f'id="{sel[1:]}"' in dom
    if sel.startswith(".") and " " not in sel:
        return re.search(r'class="[^"]*\b' + re.escape(sel[1:]) + r'\b[^"]*"', dom) is not None
    if sel.startswith("[") and sel.endswith("]"):
        return sel[1:-1].replace("'", '"') in dom
    return sel in dom


def cmd_design_fidelity(args) -> int:
    manifest_path = args.manifest
    dom_path = args.dom
    screenshot_path = args.screenshot

    raw, err = load_yaml(manifest_path)
    if err:
        print(f"FIX-FIRST\n  [P0] {manifest_path} — {err}")
        return 1
    # PROP-022: ui_marker_manifest extended into ui_lock_manifest (one owner = this
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
                  "Migrate to ui_lock_manifest (PROP-022).")
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
        # PROP-022: planning-authored, opposite-family audited, CEO-accepted, hash-frozen —
        # the builder only CONSUMES it. No PASS = no build.
        if str(manifest.get("audit_status", "")).upper() != "PASS":
            findings.append(("P0", manifest_path,
                "ui_lock_manifest.audit_status is not PASS — the lock manifest must be "
                "opposite-family audited against the frozen lock before any build "
                "consumes it (no PASS = no build, PROP-022)"))
        if not str(manifest.get("ceo_acceptance_ref", "") or "").strip():
            findings.append(("P0", manifest_path,
                "ui_lock_manifest.ceo_acceptance_ref missing — the CEO accepts the lock "
                "manifest before the builder consumes it (PROP-022)"))

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
        dom = Path(dom_path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"FIX-FIRST\n  [P0] {dom_path} — DOM snapshot unreadable: {e}")
        return 1

    def _sev(marker: str) -> str:
        return "P1" if marker in forbidden_missing else "P2"

    for region in regions:
        rid = str(region.get("id", ""))
        if rid and not _marker_in_dom(dom, rid):
            findings.append((_sev(rid), loc,
                f"required region '{rid}' missing from live DOM — the CEO-accepted shell "
                "drifted (G3 fixture-purge semantics: replace data, preserve shell)"))

    for control in controls:
        fn = str(control.get("data_fn", ""))
        if not fn:
            continue
        idx = dom.find(f'data-fn="{fn}"')
        if idx == -1:
            findings.append((_sev(fn), loc,
                f"required control data-fn=\"{fn}\" missing from live DOM — approved "
                "controls must survive the engine wave"))
            continue
        # Marker-stuffing guard (GPT cross-review): the marker must sit on a real,
        # visible control with the locked role + label — a hidden stub on a generic
        # template must not read green.
        tag_start = dom.rfind("<", 0, idx)
        tag_end = dom.find(">", idx)
        tag = dom[tag_start:tag_end + 1] if tag_start != -1 and tag_end != -1 else ""
        if re.search(r"\shidden[\s>=]", tag) or "display:none" in tag.replace(" ", ""):
            findings.append((_sev(fn), loc,
                f"control data-fn=\"{fn}\" is a hidden stub — marker present but the "
                "control is not visible"))
        role = str(control.get("role", "") or "")
        if role and f'role="{role}"' not in tag:
            findings.append((_sev(fn), loc,
                f"control data-fn=\"{fn}\" lacks locked role \"{role}\" in its element"))
        label = str(control.get("label", "") or "")
        if label:
            text_end = dom.find("<", tag_end + 1) if tag_end != -1 else -1
            inner = dom[tag_end + 1:text_end] if tag_end != -1 and text_end != -1 else ""
            if (label not in inner and f'aria-label="{label}"' not in tag
                    and f'value="{label}"' not in tag):
                findings.append((_sev(fn), loc,
                    f"control data-fn=\"{fn}\" lacks locked label \"{label}\" "
                    "(element text, aria-label, or value)"))

    for entry in shell:
        sel = str(entry.get("selector", ""))
        if sel and not _selector_in_dom(dom, sel):
            findings.append((_sev(sel), loc,
                f"required shell selector '{sel}' missing from live DOM"))

    # PROP-022 lock-vocabulary coverage: translation_keys · ui_states · alert_variants.
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
            "build's vocabulary and pass it (PROP-022)"))
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
                        "extends it (PROP-022)"))
                for entry in sorted(locked - built):
                    findings.append(("P2", loc,
                        f"ui_lock_manifest {section} entry '{entry}' missing from the build — "
                        "locked vocabulary drifted (PROP-022)"))

    # Screenshot = supporting evidence; existence + non-trivial size only (no pixel-AI).
    shot = Path(screenshot_path)
    if not shot.is_file() or shot.stat().st_size == 0:
        findings.append(("P1", screenshot_path,
            "screenshot missing or empty — visual support proof (viewport / visible "
            "shell / no blank page) is required alongside the DOM marker check"))
    elif shot.suffix.lower() not in SCREENSHOT_EXTS:
        findings.append(("P2", screenshot_path,
            f"screenshot extension '{shot.suffix}' not in {sorted(SCREENSHOT_EXTS)}"))

    return findings_report(findings)
