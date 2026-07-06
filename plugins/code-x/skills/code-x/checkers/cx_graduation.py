# cmd_graduation: EVAL-041 Reliability-Bar Graduation Gate.
#
# Reads the append-only graduation ledger (MEMORY/GRADUATION-LEDGER.md) + its per-project
# snapshotted receipts (MEMORY/graduation-receipts/<project_id>/) and RECOMPUTES — never trusts
# a hand-typed flag — whether each finished project was clean (all 7 Part D §3 criteria MET),
# then recomputes the consecutive-clean streak counting backward from the newest entry.
#
#   cx check graduation --ledger <GRADUATION-LEDGER.md> --decision-ledger <CEO-DECISION-LEDGER.md>
#       [--receipts-dir <dir>] [--status | --authorize-decision CEO-D-0NN]
#       [--n 3] [--m 3] [--window-days 14]
#
# TWO MODES (design-history/eval041-... REVISION R1 §R1.1 — R1 GOVERNS over the pre-R1 body):
#   --status (default when neither flag given): informational, exit 0, NEVER blocks. The only
#     mode that may be vacuously green.
#   --authorize-decision CEO-D-0NN: THE GATE. Fail-closed — a missing/unmatched decision row, an
#     insufficient streak, or a pending entry newer than the counted streak are all P0.
#
# Builds NO autonomy switch. It builds the scoreboard + the referee the future autonomy-switch
# PROP will consume as its authorization precondition.
#
# READ/RECOMPUTE-ONLY: never writes the ledger, snapshots receipts, or mutates state.
import contextlib
import io
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from cx_common import VALID_RISK_TIERS, field_present, findings_report, load_yaml, nested_get, safe_repo_ref
from cx_final_ready import cmd_final_ready
from cx_module_acceptance import registry_flag_true, validate_module_demo
from cx_module_quality import cmd_module_quality

# ── CEO-locked constants (2026-07-01) — R1.4: production runs may STRENGTHEN, never WEAKEN these
# outside CODE_X_TEST_MODE=1 (fixtures need small values; production never does). ─────────────
GRADUATION_N = 3            # consecutive clean projects for graduation
GRADUATION_M = 3             # min user-facing among the N counted projects — CEO-locked = ALL N
POSTSHIP_WINDOW_DAYS = 14   # criterion-5 observation window (days)
_MILESTONE_MARKER_RE = re.compile(r"long-autonomous milestone REACHED", re.IGNORECASE)

# R1.2 — the 7 Part D §3 criteria, each recomputed from a snapshotted evidence file (never a
# self-declared flag). Order matters: c1 populates ctx["live_slice_module_ids"] that c2 reads.
_CRITERION_IDS = (
    "c1_demo_gate_never_fired",
    "c2_ceo_first_accept",
    "c3_zero_design_drift",
    "c4_matched_blueprint",
    "c5_zero_postship_p0p1",
    "c6_final_ready_clean_first_pass",
    "c7_full_review_pipeline",
)
_CRIT_LABELS = {
    "c1_demo_gate_never_fired": "demo gate never fired",
    "c2_ceo_first_accept": "CEO accepted on the first demo",
    "c3_zero_design_drift": "zero design/fidelity drift",
    "c4_matched_blueprint": "matched the locked blueprint",
    "c5_zero_postship_p0p1": "zero post-ship P0/P1 in the window",
    "c6_final_ready_clean_first_pass": "final-ready clean on the first pass",
    "c7_full_review_pipeline": "full review pipeline ran",
}

_SHIP_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# CEO-DECISION-LEDGER.md is a markdown TABLE (`| id | date | decision | scope | supersedes |`),
# NOT yaml (R1.1) — a row is matched by its leading `| CEO-D-\d+ |` id cell; R2.3 restricts this
# to the real '## Decisions' table region (never a fenced example / another section like '## CEO
# Asks Register') and the marker is scanned ONLY against the decision-text cell (index 2 after the
# id/date cells), never the whole row.
_DECISION_ID_RE = re.compile(r"^\|\s*(CEO-D-\d+)\s*\|")
_FENCE_RE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)
# R2.4: a ```yaml fence carrying ANY of these ledger-entry-shaped keys but lacking `project_id`
# is a WALL (`_unparseable`), never a silent vanish — see _parse_ledger_entries.
_LEDGER_SHAPE_KEYS = ("ship_commit", "criteria", "ship_date", "ship_timestamp_utc")


def _sha256_full(path: Path) -> str | None:
    try:
        return __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _parse_ts_utc(raw) -> datetime | None:
    """R2.6: parse `raw` as a TIMEZONE-AWARE datetime. A naive result (no tzinfo) is REJECTED —
    never silently assumed UTC — so a naive/aware comparison can never raise a bare TypeError
    during the streak sort; the caller turns a None here into a GRADUATION-ENTRY-SHAPE finding."""
    try:
        tv = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if tv.tzinfo is None:
        return None
    return tv


def _sidecar_bound(ref: str, receipts_dir: Path, manifest_files: dict) -> tuple[Path | None, str]:
    """R2.5: resolve + hash-bind a reader-resolved SIDECAR (a file a criterion's real reader would
    need, beyond the top-level snapshotted receipt) against the per-project evidence manifest.
    Centralized so every criterion's sidecar resolution shares one check. Returns (path, "") when
    `ref` is present, a real file, and listed in `manifest_files` with a matching FULL sha256;
    otherwise (None, reason) — an unlisted or mismatched sidecar is never trusted."""
    ref = (ref or "").strip()
    if not ref:
        return None, "missing/blank sidecar ref"
    path, err = safe_repo_ref(ref, receipts_dir)
    if err or path is None or not path.is_file():
        return None, err or "does not exist"
    declared = manifest_files.get(ref)
    actual = _sha256_full(path)
    if not declared or actual is None or actual != declared:
        return None, ("is absent from (or hash-mismatched in) the evidence manifest — an "
                       "unlisted/mismatched sidecar is never trusted (R2.5)")
    return path, ""


def _is_ledger_shaped(item: dict) -> bool:
    """R2.4 discriminator: does `item` carry ANY ledger-entry key other than `project_id`? Used
    to distinguish a corrupt real entry (missing only project_id — must WALL, never vanish) from
    an unrelated ```yaml mapping that happens to appear in the file."""
    return any(k in item for k in _LEDGER_SHAPE_KEYS)


def _parse_ledger_entries(ledger_text: str) -> list[dict]:
    """Extract graduation-ledger project entries from ```yaml fences.

    OWN function — mirrors the fence-reading IDIOM in cx_kaizen._parse_prop_blocks (:362) but does
    NOT import it: that reader filters to PROP-id blocks only and is the wrong tool here (R1.5).
    A mapping counts as a ledger entry iff it carries a `project_id` key; other ```yaml fences
    (e.g. a schema EXAMPLE in the seed file) are silently skipped PROVIDED they are not tagged
    ```yaml (the seed file's illustrative example deliberately uses a plain ``` fence so it is
    never mistaken for a real entry). Unparseable fences surface as an `_unparseable` sentinel so
    the caller can flag GRADUATION-ENTRY-SHAPE instead of silently vanishing a corrupt entry.

    R2.4: a ```yaml mapping (or list item) that IS ledger-shaped (carries any of
    _LEDGER_SHAPE_KEYS) but is missing `project_id` is ALSO surfaced as `_unparseable` — a
    ledger-shaped entry missing only its id must WALL (a non-clean entry), never silently vanish
    (a vanished newest-dirty entry would let the prior N clean entries authorize unopposed).
    """
    entries: list[dict] = []
    for fence in _FENCE_RE.finditer(ledger_text):
        fragment = fence.group(1)
        try:
            parsed = yaml.safe_load(fragment)
        except yaml.YAMLError:
            entries.append({"_unparseable": True, "_raw": fragment[:200]})
            continue
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                if "project_id" in item:
                    entries.append(item)
                elif _is_ledger_shaped(item):
                    entries.append({"_unparseable": True, "_raw": str(item)[:200]})
        elif isinstance(parsed, dict):
            if "project_id" in parsed:
                entries.append(parsed)
            elif _is_ledger_shaped(parsed):
                entries.append({"_unparseable": True, "_raw": str(parsed)[:200]})
    return entries


def _decisions_table_lines(decision_ledger_text: str) -> list[str]:
    """R2.3: return only the lines inside the real '## Decisions' table region, with any lines
    inside fenced ``` code blocks removed first. A marker-bearing row that only exists inside a
    fenced example, or inside an unrelated section (e.g. '## CEO Asks Register'), must never be
    able to authorize or advisory-flag a milestone decision."""
    unfenced: list[str] = []
    in_fence = False
    for line in decision_ledger_text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        unfenced.append(line)
    out: list[str] = []
    in_decisions = False
    for line in unfenced:
        if line.strip().startswith("## "):
            in_decisions = line.strip().lower() == "## decisions"
            continue
        if in_decisions:
            out.append(line)
    return out


def _decision_text_cell(row_line: str) -> str:
    """The decision-text cell of a `| id | date | decision | scope | supersedes |` row — index 3
    of the pipe-split line (0=pre-leading-pipe empty, 1=id, 2=date, 3=decision). R2.3: the marker
    must be matched ONLY against this cell, never the whole row (scope/supersedes are not expected
    to carry milestone prose, and matching the whole row is how a forged/adjacent cell could fake
    authorization)."""
    cells = row_line.strip().split("|")
    return cells[3] if len(cells) > 3 else ""


def _lookup_decision_row(decision_ledger_text: str, decision_id: str) -> str | None:
    """Return the decision-text cell for `decision_id`'s CEO-DECISION-LEDGER.md row, or None if
    the id has no row in the real Decisions table (R1.1: authorization must resolve to a REAL
    decision — missing = P0, never green). R2.3: fenced/example rows and rows outside the
    Decisions table are never considered."""
    for line in _decisions_table_lines(decision_ledger_text):
        m = _DECISION_ID_RE.match(line.strip())
        if m and m.group(1) == decision_id:
            return _decision_text_cell(line)
    return None


def _milestone_authorized(decision_ledger_text: str) -> bool:
    """True iff ANY CEO-D-* decision row's decision-text cell (in the real Decisions table,
    outside any fence) matches the milestone marker regex.

    Used ONLY for the informational --status readout (a status-mode note that a milestone
    decision already exists) — never the authorization gate itself, which resolves a SPECIFIC
    --authorize-decision id via _lookup_decision_row (R1.1)."""
    for line in _decisions_table_lines(decision_ledger_text):
        m = _DECISION_ID_RE.match(line.strip())
        if m and _MILESTONE_MARKER_RE.search(_decision_text_cell(line)):
            return True
    return False


# ── per-criterion re-derivation (R1.2) ──────────────────────────────────────────────────────────
# Each _crit_cN(doc, receipt_path, project_id, loc, receipts_dir, ctx) re-derives ONE criterion's
# verdict from the snapshotted evidence file's real fields (never a self-declared flag). `ctx`
# carries cross-criterion context (ship_date/window_days/today set by the caller; c1 populates
# live_slice_module_ids + userfacing for c2 to consume). Returns (findings) — the caller sets the
# verdict to UNMET iff findings is non-empty (MET otherwise), except c5 which may signal
# INDETERMINATE via ctx["_c5_indeterminate"].

def _crit_c1(doc, receipt_path, project_id, loc, receipts_dir, ctx):
    """c1_demo_gate_never_fired: every live_slice module's module_demo gate must be well-formed
    (validate_module_demo empty). >=1 live_slice module present => user_facing recomputed true."""
    modules = doc.get("modules")
    if not isinstance(modules, list):
        return [("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c1 evidence has no 'modules' "
            "list — cannot enumerate live_slice modules")]
    findings = []
    live_ids: list[str] = []
    for m in modules:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("module_id", "") or "").strip()
        if not registry_flag_true(m.get("live_slice")):
            continue
        live_ids.append(mid)
        aref = str(m.get("acceptance_receipt", "") or "").strip()
        apath, aerr = safe_repo_ref(aref, receipts_dir)
        if aerr or apath is None or not apath.is_file():
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c1 module '{mid}' "
                f"acceptance_receipt '{aref}' {aerr or 'does not exist'}"))
            continue
        adoc, aderr = load_yaml(str(apath))
        if aderr or not isinstance(adoc, dict):
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c1 module '{mid}' "
                f"acceptance receipt unreadable: {aderr or 'not a mapping'}"))
            continue
        ma = nested_get(adoc, "module_acceptance") if "module_acceptance" in adoc else adoc
        if not isinstance(ma, dict):
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c1 module '{mid}' "
                "module_acceptance block is not a mapping"))
            continue
        demo_findings = validate_module_demo(ma, str(apath), base=str(receipts_dir))
        if demo_findings:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c1 module '{mid}' demo "
                f"gate NOT clean — {demo_findings[0][2][:180]}"))
    ctx["live_slice_module_ids"] = live_ids
    ctx["userfacing"] = len(live_ids) > 0
    return findings


def _crit_c2(doc, receipt_path, project_id, loc, receipts_dir, ctx):
    """c2_ceo_first_accept: for every live_slice module (from c1), the FIRST demo attempt's
    ceo_verdict must be 'accepted' — a needs_fix-then-accepted history is UNMET (R1.0's core
    correction: a current-state receipt cannot prove this, only an append-only attempt history can)."""
    live_ids = ctx.get("live_slice_module_ids", [])
    if not live_ids:
        return []  # no live_slice modules — vacuously MET (backend-only project, §11)
    modules = doc.get("modules")
    history: dict[str, object] = {}
    if isinstance(modules, list):
        for m in modules:
            if isinstance(m, dict) and isinstance(m.get("module_id"), str):
                history[m["module_id"].strip()] = m.get("attempts")
    findings = []
    for mid in live_ids:
        attempts = history.get(mid)
        if not isinstance(attempts, list) or not attempts:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c2 has no demo-attempt-"
                f"history for live_slice module '{mid}' — absent history for a closed criterion "
                "fails closed (R1.0)"))
            continue
        try:
            ordered = sorted(attempts, key=lambda a: int(a.get("attempt", 0)) if isinstance(a, dict) else 0)
        except (TypeError, ValueError):
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c2 module '{mid}' has "
                "non-integer 'attempt' fields"))
            continue
        first = ordered[0] if isinstance(ordered[0], dict) else {}
        verdict = str(first.get("ceo_verdict", "") or "").strip().lower()
        if verdict != "accepted":
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c2 module '{mid}' "
                f"attempt #{first.get('attempt')} ceo_verdict='{verdict or 'MISSING'}' — not "
                "accepted on the FIRST demo"))
    return findings


def _crit_c3(doc, receipt_path, project_id, loc, receipts_dir, ctx):
    """c3_zero_design_drift: design + render + lock fidelity all PASS with zero P0/P1 drift.

    R2.1 (finding #4, P0): a bare hand-typed `{verdict: PASS}` summary with NO real evidence must
    NEVER pass — the fidelity criteria are the UI-drift safety net that justifies autonomy; a
    summary-only pass makes them theater. HONEST-SCOPE (documented per R2.1's own escape hatch):
    literally replaying cmd_design_fidelity/cmd_render_fidelity against this receipt would need
    the live DOM/screenshot bytes + a rendered bundle snapshotted whole (megabytes, not wired into
    any `cx` subcommand today for lock-fidelity) — too heavy for a per-project ledger receipt. The
    fallback is presence + manifest-hash-bind + field re-derivation: each kind-block must name a
    real `sidecar_ref` file (a reader-output-adjacent artifact — e.g. the DOM/screenshot/lock-
    manifest bytes actually used), manifest-hash-bound (R2.5) so it cannot be a forged path: a
    receipt/sidecar absent from the manifest is UNMET.
    """
    findings = []
    manifest_files = ctx.get("manifest_files") or {}
    for kind in ("design_fidelity", "render_fidelity", "lock_fidelity"):
        blk = doc.get(kind)
        if not isinstance(blk, dict):
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c3 missing '{kind}' block"))
            continue
        verdict = str(blk.get("verdict", "") or "").strip().upper()
        p0 = blk.get("drift_p0", 0) or 0
        p1 = blk.get("drift_p1", 0) or 0
        if verdict != "PASS" or p0 != 0 or p1 != 0:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c3 '{kind}' verdict="
                f"'{verdict or 'MISSING'}' drift_p0={p0} drift_p1={p1}"))
            continue
        sidecar_ref = str(blk.get("sidecar_ref", "") or "").strip()
        _, serr = _sidecar_bound(sidecar_ref, receipts_dir, manifest_files)
        if serr:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c3 '{kind}' sidecar_ref "
                f"'{sidecar_ref or '(absent)'}' {serr} — a real reader-output artifact must back "
                "every fidelity block; a bare verdict summary with no sidecar is theater (R2.1)"))
        if kind == "render_fidelity" and not str(blk.get("repo_head", "") or "").strip():
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c3 render_fidelity has no "
                "'repo_head' sidecar field — a render receipt with no authoritative repo-head "
                "binding cannot prove freshness (R1.2/R2.1)"))
    return findings


_C4_REQUIRED_DIRS = ("packet", "approval", "state", "review")


def _crit_c4(doc, receipt_path, project_id, loc, receipts_dir, ctx):
    """c4_matched_blueprint: blueprint verdict green + every unbudgeted addition carries a
    ceo_decision_ref + the packet/approval/state/review anchor refs the reader needs (R1.2) are
    present and manifest-hash-bound (R2.1 finding #4 / R2.5) — any required ref absent is UNMET."""
    findings = []
    manifest_files = ctx.get("manifest_files") or {}
    verdict = str(doc.get("verdict", "") or "").strip().lower()
    if verdict not in ("green", "pass"):
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c4 blueprint verdict="
            f"'{verdict or 'MISSING'}', not green"))
    additions = doc.get("unbudgeted_additions") or []
    if isinstance(additions, list):
        for a in additions:
            ref = str(a.get("ceo_decision_ref", "") or "").strip() if isinstance(a, dict) else ""
            if not ref:
                findings.append(("P1", loc,
                    f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c4 has an unbudgeted "
                    "addition with no ceo_decision_ref"))
    dir_refs = doc.get("dir_refs")
    if not isinstance(dir_refs, dict) or any(name not in dir_refs for name in _C4_REQUIRED_DIRS):
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c4 'dir_refs' is missing one "
            f"of {_C4_REQUIRED_DIRS} — the packet/approval/state/review anchors the reader needs "
            "(R1.2) must all be present"))
        return findings
    for name in _C4_REQUIRED_DIRS:
        ref = str(dir_refs.get(name, "") or "").strip()
        _, derr = _sidecar_bound(ref, receipts_dir, manifest_files)
        if derr:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c4 dir_refs.{name} "
                f"'{ref or '(absent)'}' {derr}"))
    return findings


def _crit_c5(doc, receipt_path, project_id, loc, receipts_dir, ctx):
    """c5_zero_postship_p0p1: window OPEN => INDETERMINATE (pending, not clean, not a reset — §3).
    Window CLOSED => MET iff zero P0/P1 rows for this build_tag dated inside [ship_date, +window]."""
    ship_date_val: date = ctx["ship_date"]
    window_days: int = ctx["window_days"]
    today: date = ctx.get("today") or date.today()
    window_close = ship_date_val + timedelta(days=window_days)
    if today < window_close:
        ctx["_c5_indeterminate"] = True
        return []
    # R2.2: a closed-window incident artifact must carry a non-blank build_tag AND an explicit
    # 'rows' list. An empty list IS a valid "zero incidents" declaration; a missing/blank
    # build_tag or a missing/non-list 'rows' key is MALFORMED (not zero-incidents) -> UNMET.
    build_tag = str(doc.get("build_tag", "") or "").strip()
    if not build_tag:
        return [("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c5 'build_tag' is missing/"
            "blank — a closed-window incident artifact with no build_tag is malformed, not "
            "zero-incidents (R2.2)")]
    rows = doc.get("rows")
    if not isinstance(rows, list):
        return [("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c5 'rows' is missing or not "
            "a list — a closed-window incident artifact must explicitly declare its rows (an "
            "empty list means zero incidents; a missing/malformed key does not, R2.2)")]
    hits = 0
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("severity", "") or "").strip().upper() not in ("P0", "P1"):
                continue
            if str(row.get("build_tag", "") or "").strip() != build_tag:
                continue
            try:
                rdate = date.fromisoformat(str(row.get("date")))
            except (TypeError, ValueError):
                continue
            if ship_date_val <= rdate <= window_close:
                hits += 1
    if hits:
        return [("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c5 recorded {hits} P0/P1 "
            f"incident(s) for build_tag '{build_tag}' within the {window_days}-day post-ship window")]
    return []


def _crit_c6(doc, receipt_path, project_id, loc, receipts_dir, ctx):
    """c6_final_ready_clean_first_pass: the ATTEMPT-1 final-ready snapshot must itself re-derive
    READY (open_findings zero, gate fields PASS, xfam receipt bound) — a CURRENT-state receipt
    cannot prove 'clean on first pass' (R1.0); the snapshot IS the first attempt's output.

    R2.7 (finding #3, cheap hardening): the snapshot must also self-declare `attempt_n: 1` — a
    first-attempt marker. Absent/wrong -> UNMET. Full "is it really attempt-1" parity (re-deriving
    attempt number from history rather than trusting the field) remains honest-scope until
    `/cx-graduate` (R1.4's trust boundary)."""
    if doc.get("attempt_n") != 1:
        return [("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c6 snapshot has no "
            f"'attempt_n: 1' first-attempt marker (attempt_n={doc.get('attempt_n')!r}) — a "
            "snapshot must declare itself the FIRST final-ready attempt (R2.7)")]

    class _NS:
        state = str(receipt_path)
        card = None
        repo_root = None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_final_ready(_NS())
    if rc != 0:
        tail = buf.getvalue().strip().splitlines()
        reason = tail[1] if len(tail) > 1 else (tail[0] if tail else "no output")
        return [("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c6 attempt-1 final-ready "
            f"snapshot does NOT re-derive READY — {reason[:180]}")]
    return []


def _crit_c7(doc, receipt_path, project_id, loc, receipts_dir, ctx):
    """c7_full_review_pipeline: replay `cx check module-quality` per module (self_review +
    build_validation + anti_slop, EVAL-040) AND the CodeRabbit/build-turn receipt is a typed,
    field-complete, egress-bound artifact.

    R2.1 (finding #4, P0): `modules` must be a NON-EMPTY list — an empty/missing modules list is
    UNMET, never a vacuous pass (a coderabbit receipt alone proves nothing about module review).
    R2.5: the per-module `registry` ref and the coderabbit receipt's `egress_receipt_ref` sidecar
    are manifest-hash-bound, same as every other reader-resolved sidecar."""
    findings = []
    manifest_files = ctx.get("manifest_files") or {}
    modules = doc.get("modules")
    if not isinstance(modules, list) or not modules:
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 has an empty/missing "
            "'modules' list — zero modules under review can never be a vacuous pass (R2.1)"))
        modules = []
    for m in modules:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("module_id", "") or "").strip()
        aref = str(m.get("acceptance_receipt", "") or "").strip()
        rref = str(m.get("registry", "") or "").strip()
        apath, aerr = safe_repo_ref(aref, receipts_dir)
        rpath, rerr = safe_repo_ref(rref, receipts_dir)
        if aerr or rerr or apath is None or rpath is None or not apath.is_file() or not rpath.is_file():
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 module '{mid}' "
                f"acceptance/registry unreachable ({aerr or rerr or 'missing file'})"))
            continue
        _, rsc_err = _sidecar_bound(rref, receipts_dir, manifest_files)
        if rsc_err:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 module '{mid}' "
                f"registry '{rref}' {rsc_err}"))
            continue

        # PB-PROP-003 Unit 2 (finding CX-PB003-001 FIX-FIRST): resolve the frozen packet dir the
        # SAME way module-start's order wall does — the canonical registry lives at the TOP of
        # the frozen packet (<packet-dir>/MODULE-REGISTRY.yaml, cx_module_start.py's
        # CANONICAL_REGISTRY_NAME convention), so the registry ref's own parent directory IS the
        # packet dir. No new resolution path: this recovers the same directory module-start's
        # --packet-dir already names, from the same ref this replay already reads. A registry
        # fixture with no sibling requirements-manifest.yaml (every pre-existing, non-PB-PROP-003
        # replay fixture) safely resolves the wiring marker to absent -> no new findings (fail-
        # closed OMISSION, not fail-open widening).
        class _NS:
            acceptance = str(apath)
            registry = str(rpath)
            module_id = mid
            packet_dir = str(rpath.parent)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_module_quality(_NS())
        if rc != 0:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 module '{mid}' "
                "module-quality replay FAILED (self_review/build_validation/anti_slop leg unmet)"))

    cr_ref = str(doc.get("coderabbit_receipt", "") or "").strip()
    if not cr_ref:
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 has no coderabbit_receipt"))
        return findings
    cr_path, crerr = safe_repo_ref(cr_ref, receipts_dir)
    if crerr or cr_path is None or not cr_path.is_file():
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 coderabbit_receipt "
            f"'{cr_ref}' {crerr or 'does not exist'}"))
        return findings
    crdoc, crderr = load_yaml(str(cr_path))
    cblk = crdoc.get("coderabbit_review") if isinstance(crdoc, dict) else None
    if not isinstance(cblk, dict):
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 coderabbit receipt is not "
            "a typed coderabbit_review artifact"))
        return findings
    required = ("commit", "diff_hash", "tool_version", "findings_hash", "egress_receipt_ref", "produced_at")
    miss = [k for k in required if not field_present(cblk, k)]
    if miss:
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 coderabbit receipt "
            f"missing {miss}"))
        return findings
    eref = str(cblk.get("egress_receipt_ref"))
    epath, eerr = safe_repo_ref(eref, receipts_dir)
    if eerr or epath is None or not epath.is_file():
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 coderabbit "
            f"egress_receipt_ref '{eref}' {eerr or 'does not exist'}"))
        return findings
    _, esc_err = _sidecar_bound(eref, receipts_dir, manifest_files)
    if esc_err:
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' c7 coderabbit "
            f"egress_receipt_ref '{eref}' {esc_err}"))
    return findings


_CRIT_DISPATCH = {
    "c1_demo_gate_never_fired": _crit_c1,
    "c2_ceo_first_accept": _crit_c2,
    "c3_zero_design_drift": _crit_c3,
    "c4_matched_blueprint": _crit_c4,
    "c5_zero_postship_p0p1": _crit_c5,
    "c6_final_ready_clean_first_pass": _crit_c6,
    "c7_full_review_pipeline": _crit_c7,
}


def _recompute_criterion(cid: str, receipt_ref: str, receipt_sha256: str, receipts_dir: Path,
                          project_id: str, loc: str, ctx: dict) -> tuple[str, list]:
    """Step 1: reach + hash-bind the snapshotted receipt (full sha256, R1.4). Step 2: re-derive the
    verdict from the receipt's REAL fields (never a self-declared flag). Returns
    (verdict in {"MET","UNMET","INDETERMINATE"}, findings)."""
    findings: list[tuple[str, str, str]] = []
    receipt_path, rerr = safe_repo_ref(receipt_ref, receipts_dir)
    if rerr or receipt_path is None or not receipt_path.is_file():
        return "UNMET", [("P0", loc,
            f"GRADUATION-ENTRY-RECEIPT-UNBOUND: entry '{project_id}' criteria.{cid} receipt "
            f"'{receipt_ref}' {rerr or 'does not exist'} — an unreachable receipt makes the "
            "criterion UNMET (fail-closed anti-forge)")]
    actual = _sha256_full(receipt_path)
    if actual is None or actual != receipt_sha256:
        return "UNMET", [("P0", loc,
            f"GRADUATION-ENTRY-RECEIPT-UNBOUND: entry '{project_id}' criteria.{cid} receipt "
            f"'{receipt_ref}' sha256={actual or 'UNREADABLE'} != declared {receipt_sha256} — "
            "hash mismatch (forged/swapped/hand-edited receipt)")]
    doc, derr = load_yaml(str(receipt_path))
    if derr or not isinstance(doc, dict):
        return "UNMET", [("P1", loc,
            f"GRADUATION-ENTRY-CRITERION-UNMET: entry '{project_id}' criteria.{cid} receipt is "
            f"not a readable YAML mapping — {derr or 'not a mapping'}")]
    fn = _CRIT_DISPATCH[cid]
    crit_findings = fn(doc, receipt_path, project_id, loc, receipts_dir, ctx)
    findings.extend(crit_findings)
    if cid == "c5_zero_postship_p0p1" and ctx.pop("_c5_indeterminate", False):
        return "INDETERMINATE", findings
    return ("UNMET" if findings else "MET"), findings


def _validate_tier_evidence(entry: dict, manifest_ok: bool, manifest_files: dict, receipts_dir: Path,
                             project_id: str, loc: str) -> tuple[bool, str | None, list[tuple[str, str, str]]]:
    """PBF-PROP-019 Phase 4 (design v2 P1-5): every graduation entry must POSITIVELY declare a
    hash-bound `risk_tier` — an entry may NEVER be silent on tier. FAIL-CLOSED DIRECTION IS THE
    OPPOSITE of the packet resolver (`cx_common.resolve_risk_tier`, which defaults absence to
    STRICT): here, missing/unbindable/malformed tier evidence is a P0
    `GRADUATION-TIER-EVIDENCE-REQUIRED` that keeps the entry OUT of the streak population — it is
    never defaulted to STRICT-and-counted. That P0 only bites under `--authorize-decision`
    (cmd_graduation's existing dormant-by-default posture), so it blocks the autonomy
    authorization until the ledger is complete — that is the intended teeth.

    Mirrors the criteria-receipt pattern (`_recompute_criterion`, ~L581-609 / L694-706): a
    `receipt` + full 64-hex `receipt_sha256` cross-checked against the entry's own evidence
    manifest, then the real file re-hashed. The receipt's content must assert a
    `resolved_risk_tier` that MATCHES the entry's declared `risk_tier` — a declared
    STANDARD/STRICT claim over a receipt asserting the run was actually built LITE is REJECTED
    (the LITE->STANDARD migration guard: a later tier flip cannot retroactively bank a
    LITE-built run as STANDARD).

    Returns (tier_ok, verified_tier, findings). `verified_tier` is the declared tier (normalised
    uppercase) ONLY when tier_ok is True; otherwise None — a caller must never treat an unverified
    tier value as meaningful."""
    findings: list[tuple[str, str, str]] = []
    raw_tier = entry.get("risk_tier")
    declared_tier = str(raw_tier).strip().upper() if isinstance(raw_tier, str) and raw_tier.strip() else None
    if declared_tier not in VALID_RISK_TIERS:
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' 'risk_tier' is missing/blank "
            f"or not one of {sorted(VALID_RISK_TIERS)} — a graduation entry may never be silent on "
            "tier (fail-closed: rejected from the streak population, never defaulted to "
            "STRICT-and-counted)"))
        return False, None, findings

    tier_evidence = entry.get("tier_evidence")
    if not isinstance(tier_evidence, dict):
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' declares risk_tier="
            f"'{declared_tier}' but has no 'tier_evidence' block — the tier must be hash-bound to a "
            "snapshotted receipt, never a bare self-declared field"))
        return False, None, findings

    receipt_ref = str(tier_evidence.get("receipt", "") or "").strip()
    receipt_sha256 = str(tier_evidence.get("receipt_sha256", "") or "").strip().lower()
    if not receipt_ref or not _SHA256_RE.match(receipt_sha256):
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' tier_evidence is missing "
            "'receipt' or a full 64-hex 'receipt_sha256' (mirrors R1.4: full sha256, not a "
            "12-hex prefix)"))
        return False, None, findings

    if manifest_ok and manifest_files.get(receipt_ref) != receipt_sha256:
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' tier_evidence receipt "
            f"'{receipt_ref}' is absent from (or hash-mismatched in) its own evidence manifest — "
            "an unindexed/unbound tier receipt is never trusted"))
        return False, None, findings

    receipt_path, rerr = safe_repo_ref(receipt_ref, receipts_dir)
    if rerr or receipt_path is None or not receipt_path.is_file():
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' tier_evidence receipt "
            f"'{receipt_ref}' {rerr or 'does not exist'}"))
        return False, None, findings

    actual = _sha256_full(receipt_path)
    if actual is None or actual != receipt_sha256:
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' tier_evidence receipt "
            f"'{receipt_ref}' sha256={actual or 'UNREADABLE'} != declared {receipt_sha256} — hash "
            "mismatch (forged/swapped/hand-edited tier receipt)"))
        return False, None, findings

    tdoc, tderr = load_yaml(str(receipt_path))
    if tderr or not isinstance(tdoc, dict):
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' tier_evidence receipt is not "
            f"a readable YAML mapping — {tderr or 'not a mapping'}"))
        return False, None, findings

    raw_receipt_tier = tdoc.get("resolved_risk_tier")
    receipt_tier = (str(raw_receipt_tier).strip().upper()
                    if isinstance(raw_receipt_tier, str) and raw_receipt_tier.strip() else None)
    if receipt_tier not in VALID_RISK_TIERS:
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' tier_evidence receipt "
            f"'resolved_risk_tier' is missing/blank or not one of {sorted(VALID_RISK_TIERS)}"))
        return False, None, findings

    if receipt_tier != declared_tier:
        findings.append(("P0", loc,
            f"GRADUATION-TIER-EVIDENCE-REQUIRED: entry '{project_id}' declares risk_tier="
            f"'{declared_tier}' but its bound tier receipt asserts the frozen packet actually "
            f"resolved to '{receipt_tier}' — a later tier claim cannot retroactively bank a run "
            "built under a lighter tier (LITE->STANDARD migration guard)"))
        return False, None, findings

    return True, declared_tier, findings


def _validate_entry(entry: dict, receipts_dir: Path, window_days: int = POSTSHIP_WINDOW_DAYS,
                     today: date | None = None) -> tuple[bool, bool, bool, bool, list[tuple[str, str, str]]]:
    """Validate + recompute ONE ledger entry against its snapshotted receipts.

    Returns (is_clean, is_userfacing, is_pending, is_lite, findings). is_pending is True iff every
    criterion is MET except c5 (INDETERMINATE, post-ship window still open) — such an entry is
    NOT clean, does NOT reset the streak, and is EXCLUDED from the streak count (§3 'pending').
    is_lite is True iff the entry's `risk_tier` is hash-bound-VERIFIED (never a bare claim, see
    `_validate_tier_evidence`) as LITE — a verified-LITE entry is likewise EXCLUDED from the streak
    count (PBF-PROP-019 Phase 4 design v2 §5/P1-5): it neither counts nor resets, same mechanic as
    'pending'. A missing/unbindable/malformed tier declaration is NEVER treated as is_lite=True —
    it instead surfaces a P0 GRADUATION-TIER-EVIDENCE-REQUIRED finding and makes the entry NOT
    clean (fail-closed: rejected from the streak, never defaulted to STRICT-and-counted).
    """
    project_id = entry.get("project_id") if isinstance(entry.get("project_id"), str) else None
    loc = f"graduation-ledger:{project_id or '<unknown>'}"

    if entry.get("_unparseable"):
        return False, False, False, False, [("P1", "graduation-ledger",
            f"GRADUATION-ENTRY-SHAPE: a ```yaml fence could not be parsed as a ledger entry — "
            f"{entry.get('_raw', '')!r}")]

    shape_errors = []
    if not project_id or not project_id.strip():
        shape_errors.append("project_id missing/blank")
    ship_commit = entry.get("ship_commit")
    if not isinstance(ship_commit, str) or not _SHIP_COMMIT_RE.match(ship_commit.strip().lower()):
        shape_errors.append("ship_commit must be a 40-hex commit sha")
    ship_date_val = None
    try:
        ship_date_val = date.fromisoformat(str(entry.get("ship_date")))
    except (TypeError, ValueError):
        shape_errors.append("ship_date must be an ISO date (YYYY-MM-DD)")
    # R2.6: ship_timestamp_utc must be TIMEZONE-AWARE — a naive datetime is rejected here rather
    # than silently assumed UTC (the old behavior), since a mix of naive-assumed and genuinely
    # aware timestamps is exactly what raises the ordering TypeError this revision closes.
    if _parse_ts_utc(entry.get("ship_timestamp_utc")) is None:
        shape_errors.append("ship_timestamp_utc must be a timezone-aware ISO-8601 datetime "
                             "(naive/unparseable rejected, R2.6)")
    criteria = entry.get("criteria")
    if not isinstance(criteria, dict) or set(criteria.keys()) != set(_CRITERION_IDS):
        shape_errors.append(f"criteria must carry exactly the 7 keys {sorted(_CRITERION_IDS)}")
        criteria = {}
    evidence_manifest_ref = entry.get("evidence_manifest")
    if not isinstance(evidence_manifest_ref, str) or not evidence_manifest_ref.strip():
        shape_errors.append("evidence_manifest missing/blank")
        evidence_manifest_ref = None

    if shape_errors:
        return False, False, False, False, [("P1", loc,
            f"GRADUATION-ENTRY-SHAPE: entry '{project_id or '<unknown>'}' is malformed — "
            f"{'; '.join(shape_errors)}")]

    findings: list[tuple[str, str, str]] = []
    manifest_ok = True
    manifest_files: dict[str, str] = {}
    manifest_path, mrerr = safe_repo_ref(evidence_manifest_ref, receipts_dir)
    if mrerr or manifest_path is None or not manifest_path.is_file():
        findings.append(("P1", loc,
            f"GRADUATION-ENTRY-SHAPE: entry '{project_id}' evidence_manifest "
            f"'{evidence_manifest_ref}' {mrerr or 'does not exist'} — every entry must carry a "
            "per-project evidence manifest (R1.2)"))
        manifest_ok = False
    else:
        mdoc, _mderr = load_yaml(str(manifest_path))
        gm = nested_get(mdoc, "graduation_evidence_manifest") if isinstance(mdoc, dict) else None
        files = gm.get("files") if isinstance(gm, dict) else None
        if not isinstance(files, list) or not files:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-SHAPE: entry '{project_id}' evidence manifest has no non-empty "
                "'files' list"))
            manifest_ok = False
        else:
            for row in files:
                if isinstance(row, dict) and isinstance(row.get("path"), str):
                    manifest_files[row["path"].strip()] = str(row.get("sha256", "")).strip().lower()

    # PBF-PROP-019 Phase 4: hash-bound tier evidence — independent of the 7-criteria recompute
    # (never touches criterion dispatch/verdicts), gates is_clean + supplies is_lite for the
    # streak-population filter below.
    tier_ok, verified_tier, tier_findings = _validate_tier_evidence(
        entry, manifest_ok, manifest_files, receipts_dir, project_id, loc)
    findings.extend(tier_findings)

    ctx: dict = {"ship_date": ship_date_val, "window_days": window_days, "today": today or date.today(),
                 "live_slice_module_ids": [], "userfacing": False,
                 "manifest_files": manifest_files, "manifest_ok": manifest_ok}
    criterion_verdicts: dict[str, str] = {}
    for cid in _CRITERION_IDS:
        block = criteria.get(cid)
        if not isinstance(block, dict):
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-SHAPE: entry '{project_id}' criteria.{cid} is not a mapping"))
            criterion_verdicts[cid] = "UNMET"
            continue
        receipt_ref = str(block.get("receipt", "") or "").strip()
        receipt_sha256 = str(block.get("receipt_sha256", "") or "").strip().lower()
        if not receipt_ref or not _SHA256_RE.match(receipt_sha256):
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-SHAPE: entry '{project_id}' criteria.{cid} missing 'receipt' or "
                "a full 64-hex 'receipt_sha256' (R1.4: full sha256, not a 12-hex prefix)"))
            criterion_verdicts[cid] = "UNMET"
            continue
        if manifest_ok and manifest_files.get(receipt_ref) != receipt_sha256:
            findings.append(("P1", loc,
                f"GRADUATION-ENTRY-SHAPE: entry '{project_id}' criteria.{cid} receipt "
                f"'{receipt_ref}' is absent from (or hash-mismatched in) its own evidence manifest"))
            manifest_ok = False
        verdict, crit_findings = _recompute_criterion(
            cid, receipt_ref, receipt_sha256, receipts_dir, project_id, loc, ctx)
        criterion_verdicts[cid] = verdict
        findings.extend(crit_findings)

    is_pending = (criterion_verdicts.get("c5_zero_postship_p0p1") == "INDETERMINATE"
                  and all(v == "MET" for cid, v in criterion_verdicts.items() if cid != "c5_zero_postship_p0p1"))
    is_clean = tier_ok and manifest_ok and all(v == "MET" for v in criterion_verdicts.values())
    is_userfacing = bool(ctx.get("userfacing"))
    is_lite = tier_ok and verified_tier == "LITE"
    return is_clean, is_userfacing, is_pending, is_lite, findings


def _recompute_streak(ordered_statuses: list[dict], receipts_dir: Path, n: int, m: int) -> tuple[int, int, dict]:
    """`ordered_statuses`: chronological OLDEST->NEWEST (each carries project_id/is_clean/
    is_userfacing/is_pending/is_lite). Streak = count of consecutive CLEAN projects counting
    backward from the newest, SKIPPING pending entries (they neither count nor reset) AND
    SKIPPING verified-LITE entries (PBF-PROP-019 Phase 4, design v2 §5/P1-5 — same exclusion
    mechanic: a LITE project builds normally but never contributes a "clean project" to the
    reliability record, whether it appears newest, oldest, or interleaved between STANDARD/STRICT
    entries), stopping at the first non-clean/non-pending/non-lite entry (§3). Returns (streak,
    userfacing_in_streak, per_project) — per_project also carries the
    '_pending_newer_than_streak' flag (R1.1.3)."""
    per_project: dict = {}
    streak = 0
    userfacing_in_streak = 0
    pending_newer_than_streak = False
    seen_pending_prefix = False
    counting = True
    for st in reversed(ordered_statuses):
        pid = st["project_id"]
        if counting and st.get("is_lite"):
            per_project[pid] = st
            continue
        if counting and st.get("is_pending"):
            seen_pending_prefix = True
            per_project[pid] = st
            continue
        if counting and st.get("is_clean"):
            streak += 1
            if st.get("is_userfacing"):
                userfacing_in_streak += 1
            if seen_pending_prefix:
                pending_newer_than_streak = True
            per_project[pid] = st
            continue
        counting = False
        per_project[pid] = st
    per_project["_pending_newer_than_streak"] = pending_newer_than_streak
    return streak, userfacing_in_streak, per_project


def _print_status_readout(ordered_statuses, streak, userfacing_in_streak, n, m, pending_newer, marker_note=""):
    print(f"Long-autonomous milestone: {streak} of {n} clean projects "
          f"(need {n} consecutive; ALL user-facing).{marker_note}")
    counting = True
    lines = []
    for st in reversed(ordered_statuses):
        pid = st["project_id"]
        ship_date_disp = st.get("ship_date") or "?"
        if counting and st.get("is_lite"):
            marker, label = "○", "excluded   LITE tier — outside the reliability record (GRADUATION-LITE-EXCLUDED)"
        elif counting and st["is_pending"]:
            marker, label = "⚠️", "pending    post-ship window still open"
        elif counting and st["is_clean"]:
            uf = "user-facing" if st["is_userfacing"] else "not user-facing"
            marker, label = "✅", f"clean      ({uf})"
        else:
            marker, label = "❌", "NOT clean"
            counting = False
        lines.append(f"  {marker} {pid:<14} {label} shipped {ship_date_disp}")
    for line in reversed(lines):
        print(line)
    if not counting:
        print("Streak resets at the ❌ project above. Milestone NOT reached. Autonomy stays OFF.")
    elif streak >= n and userfacing_in_streak >= m and not pending_newer:
        print("Milestone criteria satisfied — a future autonomy-switch PROP may cite this gate "
              "as its authorization precondition (autonomy itself stays a future decision).")
    else:
        print("Milestone NOT reached yet. Autonomy stays OFF.")


def cmd_graduation(args) -> int:
    ledger_arg = getattr(args, "ledger", None)
    if not ledger_arg:
        print("FIX-FIRST\n  [P0] --ledger required for cx check graduation")
        return 1
    ledger_path = Path(ledger_arg)
    if not ledger_path.is_file():
        print(f"FIX-FIRST\n  [P0] {ledger_path} — ledger file not found")
        return 1

    receipts_dir_arg = getattr(args, "receipts_dir", None)
    receipts_dir = Path(receipts_dir_arg) if receipts_dir_arg else ledger_path.resolve().parent

    decision_ledger_arg = getattr(args, "decision_ledger", None)
    decision_ledger_path = Path(decision_ledger_arg) if decision_ledger_arg else None

    authorize_id = getattr(args, "authorize_decision", None)

    test_mode = os.environ.get("CODE_X_TEST_MODE") == "1"
    n = int(getattr(args, "n", None) or GRADUATION_N)
    m = int(getattr(args, "m", None) or GRADUATION_M)
    window_days = int(getattr(args, "window_days", None) or POSTSHIP_WINDOW_DAYS)

    # R1.4: reject locked-constant WEAKENING outside CODE_X_TEST_MODE=1 — applies REGARDLESS of
    # mode (a weakened constant would misreport --status too, not only --authorize-decision).
    weaken = []
    if n < GRADUATION_N and not test_mode:
        weaken.append(("P0", "graduation-cli",
            f"GRADUATION-STREAK-UNPROVEN: --n {n} weakens the locked GRADUATION_N={GRADUATION_N} "
            "outside CODE_X_TEST_MODE — locked constants cannot be weakened in production (R1.4)"))
    if m < GRADUATION_M and not test_mode:
        weaken.append(("P0", "graduation-cli",
            f"GRADUATION-STREAK-UNPROVEN: --m {m} weakens the locked GRADUATION_M={GRADUATION_M} "
            "outside CODE_X_TEST_MODE — locked constants cannot be weakened in production (R1.4)"))
    if window_days < POSTSHIP_WINDOW_DAYS and not test_mode:
        weaken.append(("P0", "graduation-cli",
            f"GRADUATION-STREAK-UNPROVEN: --window-days {window_days} weakens the locked "
            f"POSTSHIP_WINDOW_DAYS={POSTSHIP_WINDOW_DAYS} outside CODE_X_TEST_MODE — locked "
            "constants cannot be weakened in production (R1.4)"))
    if weaken:
        return findings_report(weaken)

    ledger_text = ledger_path.read_text(encoding="utf-8")
    raw_entries = _parse_ledger_entries(ledger_text)
    today = date.today()

    statuses = []
    for entry in raw_entries:
        is_clean, is_userfacing, is_pending, is_lite, findings = _validate_entry(
            entry, receipts_dir, window_days=window_days, today=today)
        pid = entry.get("project_id") if isinstance(entry, dict) else None
        statuses.append({
            "project_id": pid or "<unknown>",
            "is_clean": is_clean, "is_userfacing": is_userfacing, "is_pending": is_pending,
            "is_lite": is_lite,
            "findings": findings,
            "ts_raw": entry.get("ship_timestamp_utc") if isinstance(entry, dict) else None,
            "ship_date": entry.get("ship_date") if isinstance(entry, dict) else None,
        })

    # R1.3 ordering: sort by ship_timestamp_utc ascending. Equal/unparseable timestamps BLOCK
    # (GRADUATION-ENTRY-SHAPE P1) rather than falling back to hand order — a same-day tie must
    # not be able to hide a later non-clean project. Cross-project git-ancestry tie-break is NOT
    # used (unreliable across repos, R1.3).
    order_findings = []
    ts_seen: dict = {}
    orderable = []
    for st in statuses:
        # R2.6: naive (timezone-unaware) timestamps are rejected here too — never silently
        # assumed UTC — so a naive/aware mix can never reach the sort key comparison below.
        tv = _parse_ts_utc(st["ts_raw"])
        if tv is None:
            order_findings.append(("P1", f"graduation-ledger:{st['project_id']}",
                f"GRADUATION-ENTRY-SHAPE: entry '{st['project_id']}' ship_timestamp_utc is not a "
                "timezone-aware ISO-8601 datetime — naive/unparseable timestamps cannot order the "
                "streak, never silently assumed UTC (R1.3/R2.6)"))
            st["is_clean"] = False
            st["is_pending"] = False
            st["is_lite"] = False
            orderable.append((None, st))
            continue
        if tv in ts_seen:
            order_findings.append(("P1", f"graduation-ledger:{st['project_id']}",
                f"GRADUATION-ENTRY-SHAPE: entry '{st['project_id']}' ship_timestamp_utc collides "
                f"with '{ts_seen[tv]}' — equal/unorderable timestamps are rejected, never hand-"
                "ordered (R1.3)"))
            st["is_clean"] = False
            st["is_pending"] = False
            st["is_lite"] = False
        else:
            ts_seen[tv] = st["project_id"]
        orderable.append((tv, st))
    # R2.6: wrap the sort itself — any ordering failure (never expected once every tv here is
    # tz-aware, but defense-in-depth per R2.6's "never crash") becomes a SHAPE finding that
    # dirties every entry, never an uncaught TypeError.
    try:
        orderable.sort(key=lambda pair: (pair[0] is None,
                                          pair[0] or datetime.min.replace(tzinfo=timezone.utc)))
    except TypeError:
        order_findings.append(("P1", "graduation-ledger",
            "GRADUATION-ENTRY-SHAPE: the streak could not be ordered (timestamp comparison "
            "failure) — an unorderable streak is never trusted; every entry is treated as "
            "unorderable/dirty rather than crashing (R2.6)"))
        for _, st in orderable:
            st["is_clean"] = False
            st["is_pending"] = False
            st["is_lite"] = False
    ordered_statuses = [st for _, st in orderable]

    streak, userfacing_in_streak, per_project = _recompute_streak(ordered_statuses, receipts_dir, n, m)
    pending_newer = per_project.get("_pending_newer_than_streak", False)
    entry_findings = order_findings + [f for st in statuses for f in st["findings"]]

    if authorize_id:
        auth_findings = list(entry_findings)
        if decision_ledger_path is None:
            auth_findings.append(("P0", "graduation-authorize",
                "GRADUATION-STREAK-UNPROVEN: --decision-ledger is required with "
                "--authorize-decision — authorization is fail-closed, never vacuous (R1.1)"))
        elif not decision_ledger_path.is_file():
            auth_findings.append(("P0", "graduation-authorize",
                f"GRADUATION-STREAK-UNPROVEN: decision ledger '{decision_ledger_path}' not found "
                "— authorization is fail-closed (R1.1)"))
        else:
            row_text = _lookup_decision_row(decision_ledger_path.read_text(encoding="utf-8"), authorize_id)
            if row_text is None:
                auth_findings.append(("P0", "graduation-authorize",
                    f"GRADUATION-STREAK-UNPROVEN: decision id '{authorize_id}' has no row in the "
                    "decision ledger — authorization must resolve to a REAL decision; missing = P0 "
                    "(R1.1.1)"))
            elif not _MILESTONE_MARKER_RE.search(row_text):
                auth_findings.append(("P0", "graduation-authorize",
                    f"GRADUATION-STREAK-UNPROVEN: decision '{authorize_id}' text does not match the "
                    f"milestone marker /{_MILESTONE_MARKER_RE.pattern}/ — a non-matching decision "
                    "row cannot authorize (R1.1.1)"))
        if streak < n or userfacing_in_streak < m:
            auth_findings.append(("P0", "graduation-authorize",
                f"GRADUATION-STREAK-UNPROVEN: recomputed streak={streak}, user_facing_in_streak="
                f"{userfacing_in_streak}; need >= {n} consecutive clean with >= {m} user-facing — "
                "authorization BLOCKED (R1.1.2)"))
        if pending_newer:
            auth_findings.append(("P0", "graduation-authorize",
                "GRADUATION-STREAK-UNPROVEN: a pending entry (post-ship window still open) is "
                "newer than the counted streak — authorizing while the most recent work is "
                "unproven is the premature-authorization risk (R1.1.3)"))
        return findings_report(auth_findings)

    # STATUS MODE (default when --authorize-decision is not given) — informational, exit 0,
    # never blocks. The only mode that may be vacuously green (R1.1).
    marker_note = ""
    if decision_ledger_path and decision_ledger_path.is_file():
        if _milestone_authorized(decision_ledger_path.read_text(encoding="utf-8")):
            marker_note = (" A milestone-authorization decision already exists in the decision "
                            "ledger — run --authorize-decision to gate it.")
    _print_status_readout(ordered_statuses, streak, userfacing_in_streak, n, m, pending_newer, marker_note)
    return 0
