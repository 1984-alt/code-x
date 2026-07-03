# cmd_accepted_surface: the PRESERVE-POSTURE gate (PBF-PROP-018; xfam-fold 2026-07-03).
#
#   cx check accepted-surface <card.yaml> --repo-root <dir>
#       [--manifests-dir <dir>] [--baseline <sha>] [--screen-globs <comma,list>]
#       [--state <CODE-X-STATE.yaml>] [--ledger <CEO-DECISION-LEDGER.md>]
#
# Plain-talk (CEO-facing, PBF-PROP-018 xfam P2-2): before the builder may delete or rewrite a
# screen the CEO already approved, the checker itself lists everything that screen does today, and
# the builder must show where each item went — kept, replaced by the new design the CEO approved, or
# dropped with the CEO's sign-off — and prove the whole app still passes its full test suite.
#
# WHAT THIS GATE RECOGNIZES: a card whose write-set (allowed_files) touches a file belonging to an
# accepted_surface_manifest (a receipt naming a CEO-accepted module's owned/shared files, generated
# at module acceptance OR a one-time legacy freeze-baseline). Such a card MUST carry either:
#   (a) mode: FIX + a resolvable lock_anchor_ref (BF-PROP-007) with deviation_class RESTORE or
#       AMBIGUITY_RESOLVED — pure defect repair, no new scope. A FIX carrying SCOPE_CHANGE (or no
#       deviation_class at all), or new_locked_scope: true, does NOT ride the anchor alone
#       (built-code xfam P2-1: SCOPE_CHANGE is by definition new scope on the surface); or
#   (b) a typed preserve_contract block (extractor-backed inventory + evidence-bound regression
#       receipt).
#
# FAIL-CLOSED clauses (all P1):
#   ACCEPTED-SURFACE-MANIFEST-REQUIRED       — accepted-file write-set with no FIX-repair-anchor /
#                                               preserve_contract (incl. shared-shell full coverage)
#   ACCEPTED-SURFACE-LEGACY-FAILS-CLOSED     — deletes/rewrites a screen-glob file with NO manifest
#   ACCEPTED-SURFACE-INVENTORY-EXTRACTED     — inventory missing/incomplete vs the recomputed
#                                               extraction (union of accepted_commit + wave baseline
#                                               when given — a manifest pinned to an older, thinner
#                                               version of the file cannot shrink the must-keep set,
#                                               built-code xfam P1-4); drop refs must RESOLVE to a
#                                               real CEO-D row in the decision ledger (P1-2) —
#                                               no ledger available = fail closed, never open
#   ACCEPTED-SURFACE-MANIFEST-BINDING        — manifest accepted_commit not bound to a real
#                                               acceptance receipt / typed hash-bound legacy-freeze
#                                               receipt (self-declared commit, P1-4)
#   ACCEPTED-SURFACE-REGRESSION-RECEIPT      — regression receipt missing/malformed/dishonest;
#                                               EVIDENCE-BOUND (P1-3): log files must exist, their
#                                               sha256 recomputed vs declared hashes, and the
#                                               receipt's full_suite_command must equal the
#                                               CONFIGURED full-suite command (card/manifest) — a
#                                               card-scoped pytest path fails
#   ACCEPTED-SURFACE-DIFF-UNDECLARED         — (--baseline given) actual git diff touches a
#                                               manifest file NOT in allowed_files; at build-turn a
#                                               MISSING wave baseline while manifests exist is
#                                               itself fail-closed (P1-5, enforced in cx_build_turn)
#
# Manifest discovery: state-declared state.accepted_surface_manifests [{ref, hash}] rows (each ref
# via safe_repo_ref, sha12-verified) when provided; else directory scan of --manifests-dir
# (default <repo-root>/accepted-surface-manifests). READ-ONLY: never builds, routes actors, edits
# source, or generates manifests/receipts.
import fnmatch
import hashlib
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from cx_common import load_yaml, findings_report, safe_repo_ref

_HEX40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_DESTRUCTIVE_OPS_RE = re.compile(r"(delete|remove|rewrite|re-?parent)", re.I)
_DISPOSITION_KEYS = ("re_homed_to", "superseded_by_lock_ref", "dropped_ceo_decision_ref")
# FIX deviation classes that are genuinely repair-shaped and may ride the lock anchor alone
# (built-code xfam P2-1: SCOPE_CHANGE — or a missing deviation_class — is new scope on the
# surface and requires the preserve_contract like any MODULE_BUILD).
_REPAIR_DEVIATION_CLASSES = {"RESTORE", "AMBIGUITY_RESOLVED"}

# Default screen-glob heuristic (ACCEPTED-SURFACE-LEGACY-FAILS-CLOSED): user-facing template/screen
# files. A project can override via --screen-globs; this is the honest default, not a claim of
# universal coverage.
_DEFAULT_SCREEN_GLOBS = ("*.html", "*_shell.html", "*/templates/*", "*/screens/*")

# Jinja template markers stay regex (attr-order is not a concern inside {% %}).
_INCLUDE_RE = re.compile(r'{%\s*include\s+["\']([^"\']+)["\']')
_EXTENDS_RE = re.compile(r'{%\s*extends\s+["\']([^"\']+)["\']')
# JS heuristics over inline <script> contents (built-code xfam P1-1: a dispatcher shipped as a
# class, a window-global assignment, or an addEventListener wire-up is a capability too).
_SCRIPT_FN_RE = re.compile(r'\bfunction\s+(\w+)\s*\(')
_JS_CLASS_RE = re.compile(r'\bclass\s+(\w+)')
_JS_WINDOW_RE = re.compile(r'\bwindow\.(\w+)\s*=')
_JS_LISTENER_RE = re.compile(r'\baddEventListener\s*\(')


class _CapExtractor(HTMLParser):
    """Tag/attr-level capability extraction (built-code xfam P1-1): a real HTML parser is
    attr-ORDER-agnostic (<link href=x rel=stylesheet> == <link rel=stylesheet href=x>) and
    handles spaced attributes (data-fn = "x") the old regexes missed."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.caps: set = set()
        self._in_script = False
        self.script_text: list = []

    def handle_starttag(self, tag, attrs):
        ad = {}
        for k, v in attrs:
            kl = k.lower()
            ad[kl] = (v or "").strip()
            if kl == "data-fn" and ad[kl]:
                self.caps.add(f"data-fn:{ad[kl]}")
            elif kl.startswith("on") and len(kl) > 2:
                self.caps.add(f"handler:{kl}")
        if tag == "link":
            if ad.get("rel", "").lower() == "stylesheet" and ad.get("href"):
                self.caps.add(f"stylesheet:{ad['href']}")
        elif tag == "script":
            if ad.get("src"):
                self.caps.add(f"script:{ad['src']}")
            else:
                self._in_script = True
        href = ad.get("href", "")
        if tag != "link" and "?" in href and "=" in href.split("?", 1)[1]:
            self.caps.add(f"link-query:{href}")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.script_text.append(data)


def extract_capabilities(text: str) -> set:
    """Recompute the extracted-capability set of an old template/screen file's TEXT (Lever C).
    Returns a set of 'kind:value' strings. Deterministic, re-readable — the SAME extraction the
    checker re-runs from `git show <commit>:<path>`, never trusted from the card."""
    parser = _CapExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        pass  # a malformed fragment must not crash extraction; regex passes below still run
    caps = set(parser.caps)
    for m in _INCLUDE_RE.finditer(text):
        caps.add(f"include:{m.group(1)}")
    for m in _EXTENDS_RE.finditer(text):
        caps.add(f"extends:{m.group(1)}")
    js = "\n".join(parser.script_text)
    for m in _SCRIPT_FN_RE.finditer(js):
        caps.add(f"script-fn:{m.group(1)}")
    for m in _JS_CLASS_RE.finditer(js):
        caps.add(f"js-class:{m.group(1)}")
    for m in _JS_WINDOW_RE.finditer(js):
        caps.add(f"js-global:{m.group(1)}")
    if _JS_LISTENER_RE.search(js):
        caps.add("js-listener:addEventListener")
    return caps


def _git(repo_root: str, *git_args) -> tuple:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root)] + list(git_args),
            capture_output=True, text=True,
        )
    except OSError as e:
        return 1, str(e)
    return result.returncode, result.stdout.strip() + result.stderr.strip()


def _git_blob_text_at_commit(commit: str, rel_path: str, repo_root) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{commit}:{rel_path}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


def _is_ancestor(commit: str, ref: str, repo_root) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", commit, ref],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _sha256_file(path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def ledger_decision_ids(ledger_path) -> set | None:
    """All CEO-D-* ids present in the decision ledger. None = ledger unreadable (callers fail
    CLOSED when a drop ref needs resolving — built-code xfam P1-2)."""
    try:
        text = Path(ledger_path).read_text(encoding="utf-8")
    except OSError:
        return None
    return set(re.findall(r"CEO-D-[A-Za-z0-9_-]+", text))


def load_manifests(manifests_dir: str) -> tuple:
    """Directory-scan manifest discovery. Returns (manifests, errors) where manifests =
    [(manifest_dict, path), ...] and errors = [(path, reason), ...]."""
    manifests, errors = [], []
    d = Path(manifests_dir)
    if not d.is_dir():
        return manifests, errors
    for p in sorted(d.glob("*.yaml")):
        data, err = load_yaml(str(p))
        if err or not isinstance(data, dict):
            errors.append((str(p), err or "not a YAML mapping"))
            continue
        m = data.get("accepted_surface_manifest") if "accepted_surface_manifest" in data else data
        if not isinstance(m, dict):
            errors.append((str(p), "accepted_surface_manifest is not a mapping"))
            continue
        manifests.append((m, str(p)))
    return manifests, errors


def load_state_manifests(state: dict, repo_root) -> tuple:
    """State-declared manifest discovery (xfam improvement leg): state.accepted_surface_manifests
    is a list of {ref, hash} rows — each ref path-safe via safe_repo_ref and sha12-verified against
    the real file bytes, so a swapped manifest is rejected. Returns (manifests, errors)."""
    manifests, errors = [], []
    rows = state.get("accepted_surface_manifests") if isinstance(state, dict) else None
    if not isinstance(rows, list):
        return manifests, errors
    for i, row in enumerate(rows):
        loc = f"state.accepted_surface_manifests[{i}]"
        if not isinstance(row, dict):
            errors.append((loc, "row is not a mapping"))
            continue
        ref = str(row.get("ref", "") or "").strip()
        declared = str(row.get("hash", "") or "").strip()
        if not ref or not declared:
            errors.append((loc, "row must carry {ref, hash}"))
            continue
        resolved, reason = safe_repo_ref(ref, repo_root)
        if reason:
            errors.append((loc, f"ref '{ref}' {reason}"))
            continue
        real = _sha256_file(resolved)
        if real is None:
            errors.append((loc, f"ref '{ref}' unreadable"))
            continue
        if real[:12] != declared:
            errors.append((loc, f"ref '{ref}' hash mismatch: declared {declared}, real {real[:12]}"))
            continue
        data, err = load_yaml(str(resolved))
        if err or not isinstance(data, dict):
            errors.append((loc, err or "not a YAML mapping"))
            continue
        m = data.get("accepted_surface_manifest") if "accepted_surface_manifest" in data else data
        if not isinstance(m, dict):
            errors.append((loc, "accepted_surface_manifest is not a mapping"))
            continue
        manifests.append((m, str(resolved)))
    return manifests, errors


def validate_manifest_shape(m: dict, path: str, repo_root=None) -> list:
    """Shape + path-safety + BINDING validation of ONE accepted_surface_manifest receipt.

    Built-code xfam P1-4 (ACCEPTED-SURFACE-MANIFEST-BINDING): accepted_commit is model/state-
    authored — a manifest could point at an older, thinner version of the file. A non-legacy
    manifest must bind to its MODULE-ACCEPTANCE receipt (receipt exists, typed, and AGREES with
    accepted_commit); a legacy_freeze_baseline manifest must reference a typed, HASH-BOUND
    legacy-freeze receipt whose frozen_commit equals accepted_commit."""
    findings = []
    for key in ("module_id", "accepted_commit", "acceptance_ref", "generated_by"):
        if not str(m.get(key, "") or "").strip():
            findings.append(("P1", path, f"accepted_surface_manifest.{key} missing/blank"))
    commit = str(m.get("accepted_commit", "") or "").strip()
    if commit and not _HEX40_RE.match(commit):
        findings.append(("P1", path,
            f"accepted_surface_manifest.accepted_commit '{commit}' is not a 40-hex commit sha"))
        commit = ""
    for key in ("owned_files", "shared_files", "routes_screens"):
        v = m.get(key)
        if v is not None and not isinstance(v, list):
            findings.append(("P1", path, f"accepted_surface_manifest.{key} must be a list"))

    ref = str(m.get("acceptance_ref", "") or "").strip()
    if not ref or not commit:
        return findings  # missing fields already reported above

    if not repo_root:
        findings.append(("P1", path,
            "cannot verify the manifest's accepted_commit binding without --repo-root — a "
            "self-declared accepted_commit fails closed (ACCEPTED-SURFACE-MANIFEST-BINDING)"))
        return findings

    if ref == "legacy_freeze_baseline":
        lref = str(m.get("legacy_freeze_ref", "") or "").strip()
        lhash = str(m.get("legacy_freeze_hash", "") or "").strip()
        if not lref or not lhash:
            findings.append(("P1", path,
                "legacy_freeze_baseline manifest must reference a typed legacy-freeze receipt: "
                "legacy_freeze_ref + legacy_freeze_hash (sha12 of the receipt file) are required — "
                "a bare 'legacy_freeze_baseline' string with no receipt is a self-declared commit "
                "(ACCEPTED-SURFACE-MANIFEST-BINDING)"))
            return findings
        resolved, reason = safe_repo_ref(lref, repo_root)
        if reason:
            findings.append(("P1", path,
                f"accepted_surface_manifest.legacy_freeze_ref '{lref}' {reason} "
                "(ACCEPTED-SURFACE-MANIFEST-BINDING)"))
            return findings
        real = _sha256_file(resolved)
        if real is None:
            findings.append(("P1", path,
                f"legacy-freeze receipt '{lref}' missing/unreadable (ACCEPTED-SURFACE-MANIFEST-BINDING)"))
            return findings
        if real[:12] != lhash:
            findings.append(("P1", path,
                f"legacy-freeze receipt hash mismatch: manifest declares {lhash}, file hashes to "
                f"{real[:12]} — the receipt is not the one the manifest was bound to "
                "(ACCEPTED-SURFACE-MANIFEST-BINDING)"))
            return findings
        data, err = load_yaml(str(resolved))
        block = data.get("legacy_freeze_baseline") if isinstance(data, dict) else None
        if err or not isinstance(block, dict):
            findings.append(("P1", path,
                f"legacy-freeze receipt '{lref}' is not a typed legacy_freeze_baseline mapping "
                "(ACCEPTED-SURFACE-MANIFEST-BINDING)"))
            return findings
        frozen = str(block.get("frozen_commit", "") or "").strip()
        gen = str(block.get("generated_by", "") or "").strip()
        if frozen != commit or not gen:
            findings.append(("P1", path,
                f"legacy-freeze receipt '{lref}' does not agree with the manifest: frozen_commit "
                f"'{frozen}' vs accepted_commit '{commit}' (or generated_by blank) — the manifest's "
                "commit must come FROM the freeze receipt, never self-declared "
                "(ACCEPTED-SURFACE-MANIFEST-BINDING)"))
        return findings

    # Non-legacy: acceptance_ref must resolve to a real receipt agreeing with accepted_commit.
    resolved, reason = safe_repo_ref(ref, repo_root)
    if reason:
        findings.append(("P1", path,
            f"accepted_surface_manifest.acceptance_ref '{ref}' {reason} "
            "(ACCEPTED-SURFACE-MANIFEST-BINDING)"))
        return findings
    data, err = load_yaml(str(resolved))
    if err or not isinstance(data, dict):
        findings.append(("P1", path,
            f"acceptance receipt '{ref}' missing/unreadable — the manifest's accepted_commit "
            f"cannot be verified against a real acceptance receipt: {err or 'not a mapping'} "
            "(ACCEPTED-SURFACE-MANIFEST-BINDING)"))
        return findings
    block = data.get("module_acceptance") if isinstance(data.get("module_acceptance"), dict) else data
    receipt_commits = {str(block.get(k, "") or "").strip()
                       for k in ("accepted_commit", "repo_sha", "repo_sha_before")}
    if commit not in receipt_commits:
        findings.append(("P1", path,
            f"accepted_surface_manifest.accepted_commit '{commit}' does not agree with any commit "
            f"field in the acceptance receipt '{ref}' — a self-declared commit could point at an "
            "older, thinner version of the surface, shrinking the must-keep inventory "
            "(ACCEPTED-SURFACE-MANIFEST-BINDING)"))
    return findings


def _manifest_file_index(manifests: list) -> dict:
    """file path -> manifest dict (first manifest claiming it wins the reference for messages)."""
    idx = {}
    for m, _path in manifests:
        files = set(str(f) for f in (m.get("owned_files") or [])) | \
                set(str(f) for f in (m.get("shared_files") or []))
        for f in files:
            idx.setdefault(f, m)
    return idx


def _manifest_owners_by_file(manifests: list) -> dict:
    """file path -> list of module_ids of EVERY manifest that claims it (owned or shared)."""
    owners: dict = {}
    for m, _path in manifests:
        mid = str(m.get("module_id", "") or "").strip()
        files = set(str(f) for f in (m.get("owned_files") or [])) | \
                set(str(f) for f in (m.get("shared_files") or []))
        for f in files:
            owners.setdefault(f, []).append(mid)
    return owners


def _card_write_set(card: dict) -> set:
    return set(str(f) for f in (card.get("allowed_files") or []))


def _card_is_destructive(card: dict) -> bool:
    ops = card.get("allowed_operations")
    ops_text = " ".join(str(o) for o in ops) if isinstance(ops, list) else str(ops or "")
    return bool(_DESTRUCTIVE_OPS_RE.search(ops_text))


def validate_manifest_required(card: dict, manifests: list, card_loc: str) -> list:
    """ACCEPTED-SURFACE-MANIFEST-REQUIRED (P1)."""
    findings = []
    file_index = _manifest_file_index(manifests)
    write_set = _card_write_set(card)
    touched = sorted(f for f in write_set if f in file_index)
    if not touched:
        return findings

    mode = str(card.get("mode", "") or "")
    new_locked_scope = bool(card.get("new_locked_scope"))
    pc = card.get("preserve_contract")
    has_preserve_contract = isinstance(pc, dict)
    anchor = card.get("lock_anchor_ref")
    has_fix_anchor = (mode == "FIX" and isinstance(anchor, dict)
                      and str(anchor.get("card_id", "") or "").strip())
    # xfam P2-1 (design) + built-code P2-1: the anchor alone covers only genuinely repair-shaped
    # FIX work — deviation_class must be RESTORE/AMBIGUITY_RESOLVED and new_locked_scope unset.
    # SCOPE_CHANGE (or a MISSING deviation_class) is new scope on the surface → preserve_contract.
    deviation_class = str(card.get("deviation_class", "") or "").strip()
    fix_ok = (has_fix_anchor and not new_locked_scope
              and deviation_class in _REPAIR_DEVIATION_CLASSES)

    if not has_preserve_contract and not fix_ok:
        findings.append(("P1", card_loc,
            f"card's allowed_files touch accepted-surface file(s) {touched} but the card carries "
            "neither a resolvable mode: FIX lock_anchor_ref with a repair-shaped deviation_class "
            "(RESTORE/AMBIGUITY_RESOLVED, no new scope) nor a typed preserve_contract block — new "
            "locked scope on an accepted surface (including a FIX with SCOPE_CHANGE or no "
            "deviation_class) requires the preserve_contract; mode: FIX alone does not satisfy it "
            "(ACCEPTED-SURFACE-MANIFEST-REQUIRED)"))
    return findings


def validate_shared_surface_coverage(card: dict, manifests: list, card_loc: str) -> list:
    """(e) a file shared across MULTIPLE accepted modules must have its preserve_contract declare
    ALL owning module_ids in accepted_surfaces (ACCEPTED-SURFACE-MANIFEST-REQUIRED)."""
    findings = []
    pc = card.get("preserve_contract")
    if not isinstance(pc, dict):
        return findings  # absence is MANIFEST-REQUIRED's concern
    owners = _manifest_owners_by_file(manifests)
    write_set = _card_write_set(card)
    declared_surfaces = set(str(s) for s in (pc.get("accepted_surfaces") or []))
    for f in sorted(write_set):
        owning_modules = owners.get(f, [])
        if len(owning_modules) < 2:
            continue
        missing = sorted(set(owning_modules) - declared_surfaces)
        if missing:
            findings.append(("P1", card_loc,
                f"'{f}' is a SHARED accepted-surface file owned by modules {sorted(owning_modules)} "
                f"but preserve_contract.accepted_surfaces omits {missing} — a shared shell touching "
                "multiple accepted modules must cover ALL of them, not just one "
                "(ACCEPTED-SURFACE-MANIFEST-REQUIRED)"))
    return findings


def validate_legacy_fails_closed(card: dict, manifests: list, card_loc: str,
                                 screen_globs=None) -> list:
    """ACCEPTED-SURFACE-LEGACY-FAILS-CLOSED (P1): a destructive card touching a screen-glob file
    that carries NO manifest entry at all fails closed."""
    findings = []
    if not _card_is_destructive(card):
        return findings
    globs = screen_globs or _DEFAULT_SCREEN_GLOBS
    file_index = _manifest_file_index(manifests)
    write_set = _card_write_set(card)
    for f in sorted(write_set):
        if f in file_index:
            continue
        if any(fnmatch.fnmatch(f, g) for g in globs):
            findings.append(("P1", card_loc,
                f"card deletes/re-parents/rewrites '{f}' which matches a declared user-facing "
                "screen glob but carries no accepted-surface manifest — no accepted-surface "
                "manifest — register the surface (legacy freeze-baseline) before deleting/"
                "rewriting it (ACCEPTED-SURFACE-LEGACY-FAILS-CLOSED)"))
    return findings


def validate_inventory_extracted(card: dict, manifests: list, card_loc: str,
                                 repo_root=None, baseline_sha=None,
                                 ledger_ids=None, ledger_available=False) -> list:
    """ACCEPTED-SURFACE-INVENTORY-EXTRACTED (P1): shape + extractor-backed recompute + resolvable
    drop refs.

    Built-code xfam P1-4: extraction runs against the UNION of the manifest's accepted_commit AND
    the wave pre-build baseline (when given) — if the file at the wave baseline carries MORE
    capabilities than at accepted_commit, the richer set governs; a manifest pinned to an older,
    thinner version of the file cannot shrink the must-keep set.
    Built-code xfam P1-2: a dropped_ceo_decision_ref must RESOLVE to a real CEO-D row in the
    decision ledger; ledger unavailable = fail closed, never open."""
    findings = []
    pc = card.get("preserve_contract")
    if not isinstance(pc, dict):
        return findings  # absence itself is MANIFEST-REQUIRED's concern
    inventory = pc.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        findings.append(("P1", card_loc,
            "preserve_contract.inventory missing/empty — a card touching an accepted surface must "
            "carry an extractor-backed inventory of the old file's capabilities "
            "(ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
        return findings

    row_caps = set()
    for i, row in enumerate(inventory):
        if not isinstance(row, dict):
            findings.append(("P1", card_loc,
                f"preserve_contract.inventory[{i}] is not a mapping (ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
            continue
        cap = str(row.get("capability", "") or "").strip()
        if cap:
            row_caps.add(cap)
        else:
            findings.append(("P1", card_loc,
                f"preserve_contract.inventory[{i}] missing 'capability' (ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
        ef = row.get("extracted_from")
        if not isinstance(ef, dict) or not str(ef.get("commit", "") or "").strip() \
                or not str(ef.get("path", "") or "").strip():
            findings.append(("P1", card_loc,
                f"preserve_contract.inventory[{i}] missing extracted_from {{commit, path}} "
                "(ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
        present = [k for k in _DISPOSITION_KEYS if str(row.get(k, "") or "").strip()]
        if len(present) != 1:
            findings.append(("P1", card_loc,
                f"preserve_contract.inventory[{i}] must map to exactly ONE of {list(_DISPOSITION_KEYS)}, "
                f"found {present} (ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
        elif present[0] == "dropped_ceo_decision_ref":
            dref = str(row.get("dropped_ceo_decision_ref", "") or "").strip()
            if not dref.upper().startswith("CEO-D-"):
                findings.append(("P1", card_loc,
                    f"preserve_contract.inventory[{i}].dropped_ceo_decision_ref '{dref}' does not "
                    "look like a resolvable CEO-D ledger id (must start with 'CEO-D-') — a fake/"
                    "free-form drop reason is not a real CEO sign-off (ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
            elif not ledger_available:
                findings.append(("P1", card_loc,
                    f"preserve_contract.inventory[{i}].dropped_ceo_decision_ref '{dref}' cannot be "
                    "resolved: no readable CEO-DECISION-LEDGER available (--ledger or "
                    "<repo-root>/CEO-DECISION-LEDGER.md) — a drop sign-off fails CLOSED, never open "
                    "(ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
            elif dref not in (ledger_ids or set()):
                findings.append(("P1", card_loc,
                    f"preserve_contract.inventory[{i}].dropped_ceo_decision_ref '{dref}' is not "
                    "found in the decision ledger — a format-valid but dangling drop reference is "
                    "not a real CEO sign-off (ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))

    if repo_root:
        file_index = _manifest_file_index(manifests)
        write_set = _card_write_set(card)
        for f in sorted(write_set):
            m = file_index.get(f)
            if m is None:
                continue
            commit = str(m.get("accepted_commit", "") or "").strip()
            extracted: set = set()
            resolved_any = False
            commits = [commit] if commit else []
            if baseline_sha and baseline_sha not in commits:
                commits.append(baseline_sha)
            for c in commits:
                text = _git_blob_text_at_commit(c, f, repo_root)
                if text is not None:
                    resolved_any = True
                    extracted |= extract_capabilities(text)
            if not resolved_any:
                findings.append(("P1", card_loc,
                    f"cannot recompute the extraction for '{f}' at commit(s) {commits} — extractor-"
                    "backed recompute failed (unresolvable git blob); the inventory cannot be "
                    "verified (ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
                continue
            missing = sorted(extracted - row_caps)
            if missing:
                findings.append(("P1", card_loc,
                    f"preserve_contract.inventory for '{f}' is missing extracted capability row(s) "
                    f"{missing} — the inventory is recomputed from the file's real committed contents "
                    "(union of accepted_commit and the wave baseline; the richer set governs), never "
                    "authored freehand (ACCEPTED-SURFACE-INVENTORY-EXTRACTED)"))
    return findings


def _configured_full_suite_commands(card: dict, manifests: list) -> set:
    """The CONFIGURED full-suite command set (built-code xfam P1-3): the card's own
    full_suite_command field plus any manifest-declared full_suite_command."""
    vals = set()
    v = str(card.get("full_suite_command", "") or "").strip()
    if v:
        vals.add(v)
    for m, _p in manifests:
        mv = str(m.get("full_suite_command", "") or "").strip()
        if mv:
            vals.add(mv)
    return vals


def validate_regression_receipt(card: dict, manifests: list, card_loc: str,
                                repo_root=None) -> list:
    """ACCEPTED-SURFACE-REGRESSION-RECEIPT (P1): EVIDENCE-BOUND receipt (built-code xfam P1-3).

    The receipt must carry baseline_log_ref + post_change_log_ref (path-safe, files exist); the
    checker RECOMPUTES sha256 of both logs and compares to the declared hashes; the receipt's
    full_suite_command must equal the CONFIGURED full-suite command (card.full_suite_command or a
    manifest full_suite_command) — a card-scoped pytest path fails; no configured command at all
    fails closed. baseline_sha must be 40-hex AND an ancestor of HEAD."""
    findings = []
    pc = card.get("preserve_contract")
    if not isinstance(pc, dict):
        return findings
    rr = pc.get("accepted_surface_regression_receipt")
    if not isinstance(rr, dict):
        findings.append(("P1", card_loc,
            "preserve_contract.accepted_surface_regression_receipt missing — a card touching an "
            "accepted surface must prove a full-suite regression diff vs the pre-build baseline "
            "(ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))
        return findings

    required = ("baseline_sha", "full_suite_command", "baseline_log_hash",
                "post_change_log_hash", "diff_summary", "generated_by",
                "baseline_log_ref", "post_change_log_ref")
    missing = [k for k in required if not str(rr.get(k, "") or "").strip()]
    if missing:
        findings.append(("P1", card_loc,
            f"accepted_surface_regression_receipt missing/blank {missing} (ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))

    baseline = str(rr.get("baseline_sha", "") or "").strip()
    if baseline:
        if not _HEX40_RE.match(baseline):
            findings.append(("P1", card_loc,
                f"accepted_surface_regression_receipt.baseline_sha '{baseline}' is not a 40-hex "
                "commit sha (ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))
        elif repo_root and not _is_ancestor(baseline, "HEAD", repo_root):
            findings.append(("P1", card_loc,
                f"accepted_surface_regression_receipt.baseline_sha '{baseline}' is not an ancestor "
                "of HEAD — the baseline must be a real commit this branch's history contains "
                "(ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))

    # P1-3a: full_suite_command must equal the CONFIGURED full-suite command.
    declared_cmd = str(rr.get("full_suite_command", "") or "").strip()
    configured = _configured_full_suite_commands(card, manifests)
    if declared_cmd:
        if not configured:
            findings.append(("P1", card_loc,
                "no configured full-suite command found (card.full_suite_command or a manifest "
                "full_suite_command) — the receipt's command cannot be proven to be the FULL suite; "
                "fails closed (ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))
        elif declared_cmd not in configured:
            findings.append(("P1", card_loc,
                f"accepted_surface_regression_receipt.full_suite_command '{declared_cmd}' does not "
                f"match the configured full-suite command {sorted(configured)} — a card-scoped test "
                "path is the masking class this receipt exists to close "
                "(ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))

    # P1-3b: EVIDENCE-BOUND log hashes — recompute sha256 of the real log files.
    for ref_key, hash_key in (("baseline_log_ref", "baseline_log_hash"),
                              ("post_change_log_ref", "post_change_log_hash")):
        ref = str(rr.get(ref_key, "") or "").strip()
        declared = str(rr.get(hash_key, "") or "").strip()
        if not ref:
            continue  # absence already reported in `missing` above
        if not repo_root:
            findings.append(("P1", card_loc,
                f"accepted_surface_regression_receipt.{ref_key} '{ref}' cannot be verified without "
                "--repo-root — evidence-bound log hashes fail closed (ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))
            continue
        resolved, reason = safe_repo_ref(ref, repo_root)
        if reason:
            findings.append(("P1", card_loc,
                f"accepted_surface_regression_receipt.{ref_key} '{ref}' {reason} "
                "(ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))
            continue
        real = _sha256_file(resolved)
        if real is None:
            findings.append(("P1", card_loc,
                f"accepted_surface_regression_receipt.{ref_key} '{ref}' does not exist — the "
                "regression log must be a real re-readable file; a declared hash with no log bytes "
                "is model-authored text (ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))
            continue
        if declared and declared not in (real, real[:12]):
            findings.append(("P1", card_loc,
                f"accepted_surface_regression_receipt.{hash_key} '{declared}' does not match the "
                f"recomputed sha256 of '{ref}' ({real[:12]}…) — the declared hash is not bound to "
                "the real log bytes (ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))

    # Semantic honesty bound: identical baseline/post log hashes cannot coexist with a non-empty
    # declared regressions list.
    declared_regs = rr.get("declared_regressions")
    b_hash = str(rr.get("baseline_log_hash", "") or "").strip()
    p_hash = str(rr.get("post_change_log_hash", "") or "").strip()
    if b_hash and p_hash and b_hash == p_hash and isinstance(declared_regs, list) and declared_regs:
        findings.append(("P1", card_loc,
            "accepted_surface_regression_receipt.post_change_log_hash == baseline_log_hash but "
            "declared_regressions is non-empty — an unchanged log hash claims nothing changed while "
            "regressions are declared; the receipt contradicts itself (ACCEPTED-SURFACE-REGRESSION-RECEIPT)"))
    return findings


def validate_actual_diff(card: dict, manifests: list, card_loc: str,
                         repo_root: str, baseline_sha: str) -> list:
    """ACCEPTED-SURFACE-DIFF-UNDECLARED (P1, build-turn only): the ACTUAL git diff vs baseline
    touches an accepted-surface file the card never declared in allowed_files."""
    findings = []
    if not repo_root or not baseline_sha:
        return findings
    rc, out = _git(repo_root, "diff", "--name-only", baseline_sha, "HEAD")
    if rc != 0:
        findings.append(("P1", card_loc,
            f"cannot compute the actual diff {baseline_sha}..HEAD to check for undeclared "
            f"accepted-surface writes — {out} (ACCEPTED-SURFACE-DIFF-UNDECLARED)"))
        return findings
    changed = set(line.strip() for line in out.splitlines() if line.strip())
    file_index = _manifest_file_index(manifests)
    declared = _card_write_set(card)
    undeclared = sorted((changed & set(file_index)) - declared)
    if undeclared:
        findings.append(("P1", card_loc,
            f"the ACTUAL git diff {baseline_sha}..HEAD touches accepted-surface file(s) {undeclared} "
            "that are NOT in the card's allowed_files — a broad-glob write touched accepted files "
            "without declaring them (ACCEPTED-SURFACE-DIFF-UNDECLARED)"))
    return findings


def validate_accepted_surface_card(card: dict, manifests: list, card_loc: str,
                                   repo_root=None, baseline_sha=None,
                                   screen_globs=None, ledger_ids=None,
                                   ledger_available=False) -> list:
    """Single entry point: runs every ACCEPTED-SURFACE-* card clause over one card. Returns a list
    of (severity, loc, message) findings — EMPTY means the card is clear on the preserve-posture
    gate. Manifest shape/binding validation is the caller's job (run_accepted_surface_checks)."""
    findings = []
    findings.extend(validate_manifest_required(card, manifests, card_loc))
    findings.extend(validate_shared_surface_coverage(card, manifests, card_loc))
    findings.extend(validate_legacy_fails_closed(card, manifests, card_loc, screen_globs))
    findings.extend(validate_inventory_extracted(
        card, manifests, card_loc, repo_root, baseline_sha,
        ledger_ids=ledger_ids, ledger_available=ledger_available))
    findings.extend(validate_regression_receipt(card, manifests, card_loc, repo_root))
    if baseline_sha:
        findings.extend(validate_actual_diff(card, manifests, card_loc, repo_root, baseline_sha))
    return findings


def run_accepted_surface_checks(card: dict, card_loc: str, repo_root=None,
                                manifests_dir=None, baseline_sha=None,
                                screen_globs=None, ledger_path=None,
                                state=None) -> list:
    """Full assembly shared by cmd_accepted_surface AND the cx check card compile-time bite:
    discover manifests (state-declared {ref, hash} rows first, else directory scan), validate
    their shape+binding, resolve the decision ledger, then run every card clause."""
    findings = []

    manifests, merrs = [], []
    if isinstance(state, dict) and isinstance(state.get("accepted_surface_manifests"), list) and repo_root:
        manifests, merrs = load_state_manifests(state, repo_root)
    else:
        if not manifests_dir and repo_root:
            manifests_dir = str(Path(repo_root) / "accepted-surface-manifests")
        if manifests_dir:
            manifests, merrs = load_manifests(manifests_dir)

    findings.extend(("P1", loc, f"unreadable accepted_surface_manifest: {reason}")
                    for loc, reason in merrs)
    for m, mpath in manifests:
        findings.extend(validate_manifest_shape(m, mpath, repo_root))

    ledger_ids, ledger_available = None, False
    lp = ledger_path
    if not lp and repo_root:
        candidate = Path(repo_root) / "CEO-DECISION-LEDGER.md"
        if candidate.is_file():
            lp = str(candidate)
    if lp:
        ledger_ids = ledger_decision_ids(lp)
        ledger_available = ledger_ids is not None

    findings.extend(validate_accepted_surface_card(
        card, manifests, card_loc, repo_root=repo_root, baseline_sha=baseline_sha,
        screen_globs=screen_globs, ledger_ids=ledger_ids, ledger_available=ledger_available))
    return findings


def repo_has_manifests(repo_root, state=None) -> bool:
    """True when ANY accepted_surface_manifest is discoverable (state rows or the conventional
    directory) — the build-turn uses this to fail CLOSED on a missing wave baseline (P1-5)."""
    if isinstance(state, dict):
        rows = state.get("accepted_surface_manifests")
        if isinstance(rows, list) and rows:
            return True
    d = Path(repo_root) / "accepted-surface-manifests"
    return d.is_dir() and any(d.glob("*.yaml"))


def cmd_accepted_surface(args) -> int:
    card_path = getattr(args, "card", None)
    repo_root = getattr(args, "repo_root", None)
    baseline_sha = getattr(args, "baseline", None)
    manifests_dir = getattr(args, "manifests_dir", None)
    ledger_path = getattr(args, "ledger", None)
    state_path = getattr(args, "state", None)
    screen_globs_raw = getattr(args, "screen_globs", None)
    screen_globs = [g.strip() for g in screen_globs_raw.split(",") if g.strip()] if screen_globs_raw else None

    if not card_path:
        print("FIX-FIRST\n  [P0] card path required for cx check accepted-surface")
        return 1
    card, cerr = load_yaml(card_path)
    if cerr or not isinstance(card, dict):
        print(f"FIX-FIRST\n  [P0] {card_path} — {cerr or 'not a YAML mapping'}")
        return 1

    state = None
    if state_path:
        state, serr = load_yaml(state_path)
        if serr or not isinstance(state, dict):
            print(f"FIX-FIRST\n  [P0] {state_path} — {serr or 'not a YAML mapping'}")
            return 1

    findings = run_accepted_surface_checks(
        card, card_path, repo_root=repo_root, manifests_dir=manifests_dir,
        baseline_sha=baseline_sha, screen_globs=screen_globs, ledger_path=ledger_path,
        state=state)

    if not findings:
        print("PASS")
        print("  [INFO] no accepted-surface exposure, or exposure fully covered by an anchored FIX / "
              "typed preserve_contract with extractor-backed inventory + evidence-bound regression receipt")
        return 0
    return findings_report(findings)
