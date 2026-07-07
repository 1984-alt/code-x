# cmd_kaizen: Kaizen-queue closure safeguard (PBF-PROP-012 Part F).
#
#   cx check kaizen <queue-file> [--contracts <path>] [--strict-debt] [--conflict-scan]
#
# Parses the queue's ```yaml fences into PROP blocks, classifies APPLIED,
# and audits each for the 7 KAIZEN-* clauses + the 4 PBF-PROP-014 CONFLICT-SCAN clauses
# + the 5 PBF-PROP-013 STAGE-RENAME clauses (when ids are in the new format).
# Returns findings_report(findings) — exit 0=PASS, 1=FIX-FIRST.
import hashlib
import os
import re
import subprocess
from pathlib import Path

import yaml

from cx_common import PROTOCOL_VERSION, findings_report, load_yaml

_THIS_DIR = Path(__file__).resolve().parent
_DEFAULT_CONTRACTS = _THIS_DIR / "check-contracts.yaml"

# Enforcement kinds allowed for a behavioural APPLIED PROP.
_ALLOWED_KINDS = {"clause", "prompt_marker", "judgment_limit"}
# Banned kind: presence_lint resolves to no clause bite.
_BANNED_KINDS = {"presence_lint"}
# Required sub-fields for judgment_limit enforcement.
_JL_REQUIRED = {"justification", "review_lens", "ceo_decision_ref"}

# G1 (PBF-PROP-014): a yaml fence is a PROP block ONLY if its parsed mapping has an
# `id` key matching this pattern.  Non-PROP fences (example yaml embedded in prose,
# config stanzas, etc.) are silently skipped.
# Permissive on the prefix; strict on the PROP- core — keeps test ids (PROP-TEST-*)
# and the future stage-prefixed ids (<PREFIX>-PROP-NNN) alongside today's PROP-0NN ids.
_PROP_ID_RE = re.compile(
    r"^(?:P|B|F|PB|PF|BF|PBF)?-?PROP-\S+$"
)

# PBF-PROP-013 stage-rename clauses.
# KAIZEN-ID-FORMAT: post-migration ids must match exactly (active PROPs only).
_NEW_ID_RE = re.compile(r"^(P|B|F|PB|PF|BF|PBF)-PROP-\d{3}$")
# Old (pre-migration) PROP id format — the ONLY ids KAIZEN-ID-FORMAT bites on.
# Synthetic test ids (PROP-TEST-*, etc.) match neither pattern → silently exempt.
_OLD_ID_RE = re.compile(r"^PROP-\d{3}$")
# Retired legacy ids are EXEMPT from KAIZEN-ID-FORMAT (MERGED / CLOSED-REJECTED entries).
_RETIRED_STATUSES = {"MERGED-INTO-008", "CLOSED-REJECTED"}
# PBF-PROP-021 group-2 hole #7: the full enum of `status` values the live queue actually uses.
# Any OTHER string (a case/typo drift of APPLIED — "Applied", "APPLED", "applied", etc.) is not
# a legitimate status and must be flagged, never silently treated as "not applied" (that silent
# read is exactly how a genuinely-applied behavioural PROP with zero enforcement skipped every
# APPLIED-only clause and greened the closure safeguard).
_VALID_KAIZEN_STATUSES = {"QUEUED", "APPLIED"} | _RETIRED_STATUSES
# Sub-part ids (PBF-PROP-012-C etc.) are EXEMPT from CROSSWALK-COMPLETE and ID-FORMAT.
_SUBPART_ID_RE = re.compile(r"^(P|B|F|PB|PF|BF|PBF)-PROP-\d+-\w+$")
# Template entry is EXEMPT.
_TEMPLATE_ID = "PROP-NNN"
# Synthetic test/demo id prefixes — EXEMPT from KAIZEN-PROP-ID-PARSEABLE.
_EXEMPT_ID_PREFIXES = ("PROP-TEST-", "PROP-DEMO-")
# Semantic PROP fields — a fence carrying any of these that has a malformed id
# is silently invisible to all KAIZEN-* clauses (KAIZEN-PROP-ID-PARSEABLE target).
_SEMANTIC_PROP_FIELDS = frozenset({"status", "behavioural", "conflict_scan"})
# PBF-PROP-021 group-2 hole #6: the fence-open token was the literal ```yaml + newline —
# a trailing space/tab (```yaml ) or CRLF line ending (```yaml\r\n) never matched, so the
# WHOLE fence vanished from every KAIZEN-* clause with zero finding. Tolerate the trailing
# whitespace + CRLF variant (still requires the "yaml" language tag itself, unlike the
# generic backstop scanner below).
_YAML_FENCE_OPEN_RE = r"```yaml[ \t]*\r?\n(.*?)```"
# Generic backstop: ANY fenced block regardless of language tag (or none/garbled), used only
# to detect a fence the tolerant regex above STILL missed (e.g. ```YAML, ```yml, an attribute
# after the tag) that is nonetheless PROP-shaped — see _check_unrecognized_prop_shaped_fences.
_ANY_FENCE_RE = re.compile(r"```([^\n]*)\r?\n(.*?)```", re.DOTALL)
# A fence the parser didn't recognize as a yaml PROP fence is still flagged loud when its raw
# text looks like it was authoring a PROP entry — `id: ...PROP-NNN` (quoted or not).
_PROP_SHAPED_TEXT_RE = re.compile(r"id:\s*[\"']?[\w-]*PROP-\d+")
# Valid stage values (PBF-PROP-013).
_VALID_STAGES = {"planning", "building", "fixing"}
# Stage letter encoding (canonical order P→B→F).
_STAGE_LETTERS = {"planning": "P", "building": "B", "fixing": "F"}
_STAGE_ORDER = ["planning", "building", "fixing"]

# conflict_scan: required list keys (PBF-PROP-014 §3c / G4).
_CS_LIST_KEYS = {"duplicates", "ambiguities", "conflicts"}
# conflict_scan: required scalar keys.
_CS_SCALAR_KEYS = {"resolution_ref"}
# conflict_scan: basis keys for a forward PROP (commit-anchored shas + counts + anchor).
_CS_BASIS_LIVE = {
    "queue_sha", "ledger_sha", "crosswalk_sha", "prop_count", "decision_count", "scan_commit",
}
# Accepted basis.source value for historical PROPs (§10).
_CS_BACKSCAN_SOURCE = "backscan-2026-06-30"
# scan_commit test-fixture sentinel: a static contract-bite fixture has no bespoke commit to
# anchor to, so it carries this distinctive 40-hex value. It skips ONLY git resolution, and ONLY
# under CODE_X_TEST_MODE=1 — in production it is just a sha that won't be in the object store and
# fails closed as unresolvable (mirrors cx_module_acceptance._FRESH_CLONE_TEST_SENTINEL).
_SCAN_COMMIT_TEST_SENTINEL = "deadbeef" * 5


def _encode_stages(stages: list) -> str:
    """Return the canonical prefix string for a list of stage values (P→B→F order)."""
    return "".join(_STAGE_LETTERS[s] for s in _STAGE_ORDER if s in stages)


def _load_crosswalk(cx_root: Path) -> dict[str, str] | None:
    """Load PROP-CROSSWALK.md and return {new_id: legacy_id}.

    Returns None if the file cannot be read (crosswalk check degrades gracefully).
    """
    cw_path = cx_root / "PROP-CROSSWALK.md"
    if not cw_path.is_file():
        return None
    try:
        text = cw_path.read_text(encoding="utf-8")
    except OSError:
        return None
    mapping: dict[str, str] = {}
    # Parse "| old | new | title |" table rows.
    # Only collect rows where the "new" column matches the stage-prefixed id format
    # (guards against picking up rows from the "Retired" and "Frozen clause-ids" sections
    # which use the same | old | disposition | table shape).
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        # expect at least 4 non-empty parts: ['', old, new, title, '']
        if len(parts) >= 4 and parts[1].startswith("PROP-") and parts[2]:
            new_id = parts[2].strip()
            legacy_id = parts[1].strip()
            if new_id and _NEW_ID_RE.match(new_id):
                mapping[new_id] = legacy_id
    return mapping or None


def _check_stage_rename(
    blocks: list[dict], cx_root: Path
) -> list[tuple[str, str, str]]:
    """Run the 5 PBF-PROP-013 stage-rename clauses against all PROP blocks.

    Returns a list of (severity, prop_id, message) findings.
    """
    findings: list[tuple[str, str, str]] = []
    crosswalk = _load_crosswalk(cx_root)

    # Collect active (non-retired, non-template, non-subpart) blocks for series checks.
    active_blocks: list[dict] = []
    seen_legacy: dict[str, str] = {}  # legacy_id -> first prop_id that claimed it

    for block in blocks:
        if block.get("_unparseable"):
            continue
        prop_id = block.get("id", "<unknown>")
        status = _status_value(block).split("#")[0].strip()

        # Exempt: template, sub-parts, retired statuses.
        if prop_id == _TEMPLATE_ID:
            continue
        if _SUBPART_ID_RE.match(prop_id):
            continue
        is_retired = status in _RETIRED_STATUSES

        # KAIZEN-ID-FORMAT (P0): active PROPs that carry the OLD ^PROP-\d{3}$ format must be
        # migrated to the stage-prefixed scheme.  Synthetic test ids (PROP-TEST-*, PROP-DEMO-*,
        # etc.) match neither the old nor the new pattern and are silently exempt — this clause
        # only targets genuine unmigrated PROP entries.
        if not is_retired and not _NEW_ID_RE.match(prop_id):
            if _OLD_ID_RE.match(prop_id):
                findings.append(("P0", prop_id,
                    f"KAIZEN-ID-FORMAT: id {prop_id!r} does not match the stage-prefixed format "
                    f"^(P|B|F|PB|PF|BF|PBF)-PROP-NNN — all active PROPs must use the new format "
                    f"(retired MERGED/CLOSED-REJECTED entries are exempt)"))
            continue  # skip further checks — id is neither old-canon nor new-canon

        if is_retired:
            continue  # retired entries skip the remaining checks

        # KAIZEN-PREFIX-MATCHES-STAGES (P0): stages field must exist, be valid, and encode to the prefix.
        stages_raw = block.get("stages")
        if not stages_raw or not isinstance(stages_raw, list) or len(stages_raw) == 0:
            findings.append(("P0", prop_id,
                f"KAIZEN-PREFIX-MATCHES-STAGES: PROP {prop_id!r} is missing a 'stages' field "
                f"or it is empty — every active PROP must carry a non-empty stages list "
                f"(allowed values: {sorted(_VALID_STAGES)})"))
            active_blocks.append(block)
            continue

        invalid = [s for s in stages_raw if s not in _VALID_STAGES]
        if invalid:
            findings.append(("P0", prop_id,
                f"KAIZEN-PREFIX-MATCHES-STAGES: PROP {prop_id!r} stages contains invalid value(s) "
                f"{invalid!r} — allowed: {sorted(_VALID_STAGES)}"))
            active_blocks.append(block)
            continue

        # Derive the expected prefix from stages (canonical order P→B→F).
        expected_prefix = _encode_stages(stages_raw)
        actual_prefix = prop_id.split("-PROP-")[0]
        if actual_prefix != expected_prefix:
            findings.append(("P0", prop_id,
                f"KAIZEN-PREFIX-MATCHES-STAGES: PROP {prop_id!r} prefix {actual_prefix!r} does not "
                f"match the derived prefix {expected_prefix!r} from stages {stages_raw!r}"))

        active_blocks.append(block)

        # KAIZEN-LEGACY-ID-PRESENT-UNIQUE (P1): every active PROP needs a unique legacy_id.
        legacy_id = block.get("legacy_id")
        if not legacy_id or not isinstance(legacy_id, str) or not legacy_id.strip():
            findings.append(("P1", prop_id,
                f"KAIZEN-LEGACY-ID-PRESENT-UNIQUE: PROP {prop_id!r} is missing the 'legacy_id' field "
                f"— every active PROP must carry its original PROP-NNN id as legacy_id"))
        else:
            lid = legacy_id.strip()
            if lid in seen_legacy:
                findings.append(("P1", prop_id,
                    f"KAIZEN-LEGACY-ID-PRESENT-UNIQUE: legacy_id {lid!r} is already claimed by "
                    f"{seen_legacy[lid]!r} — legacy_ids must be unique across the queue"))
            else:
                seen_legacy[lid] = prop_id

    # KAIZEN-STAGE-SERIES-ORDER-GAPLESS (P1): within each prefix, NNN must be gapless from 001
    # and ascending by numeric legacy_id.
    # Group active blocks by prefix.
    prefix_groups: dict[str, list[dict]] = {}
    for block in active_blocks:
        prop_id = block.get("id", "")
        if not _NEW_ID_RE.match(prop_id):
            continue
        prefix = prop_id.split("-PROP-")[0]
        prefix_groups.setdefault(prefix, []).append(block)

    for prefix, group in sorted(prefix_groups.items()):
        # Extract NNN numbers.
        nnn_list = []
        for block in group:
            prop_id = block.get("id", "")
            nnn_str = prop_id.split("-PROP-")[1]
            try:
                nnn_list.append((int(nnn_str), prop_id, block))
            except ValueError:
                pass

        if not nnn_list:
            continue

        # Sort by NNN (they should already be in order).
        nnn_list.sort(key=lambda x: x[0])

        # Check gapless from 001.
        expected = list(range(1, len(nnn_list) + 1))
        actual = [n for n, _, _ in nnn_list]
        if actual != expected:
            ids_str = ", ".join(pid for _, pid, _ in nnn_list)
            findings.append(("P1", f"{prefix}-PROP-*",
                f"KAIZEN-STAGE-SERIES-ORDER-GAPLESS: prefix {prefix!r} series is not gapless "
                f"from 001 — expected NNN sequence {expected!r}, got {actual!r} "
                f"(ids: {ids_str})"))
            continue

        # Check ascending by numeric legacy_id.
        def _legacy_num(block: dict) -> int:
            lid = block.get("legacy_id", "")
            if isinstance(lid, str):
                m = re.search(r"\d+", lid)
                if m:
                    return int(m.group())
            return 9999

        legacy_nums = [_legacy_num(b) for _, _, b in nnn_list]
        if legacy_nums != sorted(legacy_nums):
            ids_str = ", ".join(f"{pid}(legacy={_legacy_num(b)})" for _, pid, b in nnn_list)
            findings.append(("P1", f"{prefix}-PROP-*",
                f"KAIZEN-STAGE-SERIES-ORDER-GAPLESS: prefix {prefix!r} series NNN numbers are "
                f"not ascending by legacy_id numeric order — {ids_str}"))

    # KAIZEN-CROSSWALK-COMPLETE (P1): queue ↔ crosswalk bijection.
    if crosswalk is not None:
        # Collect queue active ids.
        queue_ids: set[str] = set()
        for block in active_blocks:
            pid = block.get("id", "")
            if _NEW_ID_RE.match(pid):
                queue_ids.add(pid)

        # Queue PROP not in crosswalk.
        for pid in sorted(queue_ids):
            if pid not in crosswalk:
                findings.append(("P1", pid,
                    f"KAIZEN-CROSSWALK-COMPLETE: PROP {pid!r} is not present in PROP-CROSSWALK.md "
                    f"— every active queue PROP must have a crosswalk entry"))

        # Crosswalk new-id with no matching active PROP.
        # Guard: only enforce the reverse direction when the queue actually contains real staged
        # PROPs (queue_ids non-empty).  A fixture-only queue with no new-format ids is silently
        # exempt — this prevents test fixtures from triggering 42 false bijection failures.
        if queue_ids:
            for new_id in sorted(crosswalk.keys()):
                if new_id not in queue_ids:
                    findings.append(("P1", new_id,
                        f"KAIZEN-CROSSWALK-COMPLETE: PROP-CROSSWALK.md maps {new_id!r} but no matching "
                        f"active PROP was found in the queue — bijection broken"))

    return findings


def _load_clause_ids(contracts_path: Path) -> set[str]:
    """Extract all clause-level ids from check-contracts.yaml."""
    data, err = load_yaml(str(contracts_path))
    ids: set[str] = set()
    if err or not isinstance(data, dict):
        return ids
    for entry in data.get("clauses", []):
        if isinstance(entry, dict) and "id" in entry:
            ids.add(entry["id"])
    return ids


def _check_malformed_prop_ids(queue_text: str) -> list[tuple[str, str, str]]:
    """KAIZEN-PROP-ID-PARSEABLE (P1): detect yaml fences that carry semantic PROP
    fields (status / behavioural / conflict_scan) but whose `id` matches neither the
    old canonical format (^PROP-\\d{3}$) nor the new stage-prefixed format
    (^(P|B|F|PB|PF|BF|PBF)-PROP-\\d{3}$) — and is not an exempt synthetic/template id
    (PROP-TEST-*, PROP-DEMO-*, PROP-NNN, or a sub-part id).

    Such fences are silently dropped by _is_prop_block / _parse_prop_blocks (or pass
    through but evade KAIZEN-ID-FORMAT), making their constraints invisible to every
    KAIZEN-* clause. A malformed id is almost always a typo that needs fixing.
    """
    findings: list[tuple[str, str, str]] = []
    for fence in re.finditer(_YAML_FENCE_OPEN_RE, queue_text, re.DOTALL):
        fragment = fence.group(1)
        try:
            parsed = yaml.safe_load(fragment)
        except yaml.YAMLError:
            continue  # unparseable fences caught by KAIZEN-APPLIED-ENTRY-PARSEABLE

        candidates: list[dict] = []
        if isinstance(parsed, list):
            candidates = [item for item in parsed if isinstance(item, dict)]
        elif isinstance(parsed, dict):
            candidates = [parsed]

        for item in candidates:
            raw_id = item.get("id")
            if not isinstance(raw_id, str):
                continue
            item_id = raw_id.strip()

            # Skip exempt ids
            if item_id == _TEMPLATE_ID:
                continue
            if any(item_id.startswith(pfx) for pfx in _EXEMPT_ID_PREFIXES):
                continue
            # Skip if it already matches old or new canonical format (other clauses handle)
            if _OLD_ID_RE.match(item_id) or _NEW_ID_RE.match(item_id):
                continue
            # Skip sub-part ids (PBF-PROP-012-C etc.)
            if _SUBPART_ID_RE.match(item_id):
                continue

            # Non-canonical id: only flag when fence carries semantic PROP fields
            # (non-PROP example fences — config, etc. — have no semantic fields)
            present = _SEMANTIC_PROP_FIELDS & item.keys()
            if not present:
                continue

            findings.append(("P1", item_id,
                f"KAIZEN-PROP-ID-PARSEABLE: fence with id={item_id!r} carries "
                f"semantic PROP field(s) ({', '.join(sorted(present))}) but its id "
                f"matches neither old format (^PROP-NNN$) nor new stage-prefixed "
                f"format (^PREFIX-PROP-NNN$) — silently dropped/invisible to all "
                f"KAIZEN-* clauses; fix the id format or remove the semantic fields"))
    return findings


def _check_unrecognized_prop_shaped_fences(queue_text: str) -> list[tuple[str, str, str]]:
    """KAIZEN-FENCE-PROP-SHAPED-UNPARSEABLE (P1, PBF-PROP-021 group-2 hole #6): a fence
    that _YAML_FENCE_OPEN_RE still does not recognize (an exotic language tag like ```YAML /
    ```yml, or any other fence shape the tolerant regex above does not cover) but whose raw
    text looks like it was authoring a PROP entry (`id: ...PROP-NNN`) must be a LOUD finding,
    never a silent vanish — that PROP block's constraints would otherwise be invisible to
    every KAIZEN-* clause with zero trace anywhere.

    Runs over the WHOLE queue text using a generic any-fence scan, then reports only the
    fences NOT already covered by the tolerant yaml-fence regex (recognized fences are handled,
    parsed or sentinel-flagged, by _parse_prop_blocks/_check_malformed_prop_ids already).
    """
    findings: list[tuple[str, str, str]] = []
    recognized_spans = [m.span() for m in re.finditer(_YAML_FENCE_OPEN_RE, queue_text, re.DOTALL)]

    def _covered(span: tuple) -> bool:
        return any(rs[0] <= span[0] and span[1] <= rs[1] for rs in recognized_spans)

    for fence in _ANY_FENCE_RE.finditer(queue_text):
        span = fence.span()
        if _covered(span):
            continue
        content = fence.group(2)
        m = _PROP_SHAPED_TEXT_RE.search(content)
        if not m:
            continue
        preview = content.strip()[:80].replace("\n", " ")
        findings.append(("P1", "<unknown>",
            f"KAIZEN-FENCE-PROP-SHAPED-UNPARSEABLE: a fence not recognized as a yaml PROP fence "
            f"(language tag {fence.group(1)!r}) carries PROP-shaped text ({m.group(0)!r}) — "
            f"{preview!r} — a fence the parser skips must never silently hide a PROP block from "
            f"every KAIZEN-* clause; fix the fence to a real ```yaml block"))
    return findings


def _is_prop_block(mapping: dict) -> bool:
    """G1 (PBF-PROP-014): return True iff the mapping's `id` matches the PROP id pattern.

    Non-PROP example fences embedded in prose are silently ignored.
    """
    raw_id = mapping.get("id")
    if not isinstance(raw_id, str):
        return False
    return bool(_PROP_ID_RE.match(raw_id.strip()))


def _parse_prop_blocks(queue_text: str) -> list[dict]:
    """Extract PROP blocks from ```yaml fences in the queue markdown.

    G1 (PBF-PROP-014): only mappings whose `id` matches _PROP_ID_RE are returned.
    Non-PROP fences (example yaml in prose, etc.) are silently skipped.
    Unparseable fences → sentinel so the caller can flag them.
    """
    blocks: list[dict] = []
    for fence in re.finditer(_YAML_FENCE_OPEN_RE, queue_text, re.DOTALL):
        fragment = fence.group(1)
        try:
            parsed = yaml.safe_load(fragment)
        except yaml.YAMLError:
            # unparseable fence — surface as a sentinel so the caller can flag it
            blocks.append({"_unparseable": True, "_raw": fragment})
            continue
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and _is_prop_block(item):
                    blocks.append(item)
        elif isinstance(parsed, dict):
            if _is_prop_block(parsed):
                blocks.append(parsed)
            # else: non-PROP fence (example yaml) — silently ignored
    return blocks


def _status_value(block: dict) -> str:
    """Return the status string, stripping any inline YAML comment."""
    raw = block.get("status", "")
    if not isinstance(raw, str):
        raw = str(raw)
    return raw.split("#")[0].strip()


def _path_safe(ref: str) -> bool:
    """Return True if the path reference is relative and within the repo."""
    if os.path.isabs(ref):
        return False
    resolved = Path(ref).resolve()
    try:
        resolved.relative_to(Path.cwd().resolve())
        return True
    except ValueError:
        return False


def _git_blob_sha_at_commit(commit: str, rel_path: str, cx_root: Path) -> str | None:
    """Return the git blob sha for `rel_path` as of `commit`, or None if unresolvable.

    The `./` prefix makes git resolve the object path relative to cwd (cx_root), not the
    repo root — cx_root is a SUBDIR of the git root in a nested worktree.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{commit}:./{rel_path}"],
            capture_output=True, text=True, timeout=10, cwd=cx_root,
        )
        sha = result.stdout.strip()
        if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
            return sha
    except Exception:
        pass
    return None


def _git_blob_text_at_commit(commit: str, rel_path: str, cx_root: Path) -> str | None:
    """Return the text content of `rel_path` as of `commit`, or None if unresolvable.

    The `./` prefix resolves the object path relative to cwd (cx_root), not the repo root.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{commit}:./{rel_path}"],
            capture_output=True, text=True, timeout=10, cwd=cx_root,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


def _is_ancestor(commit: str, ref: str, cx_root: Path) -> bool:
    """Return True iff `commit` is an ancestor of (or equal to) `ref`."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, ref],
            capture_output=True, text=True, timeout=10, cwd=cx_root,
        )
        return result.returncode == 0
    except Exception:
        return False


def _git_blame_line_sha(path: Path, line_no: int, cx_root: Path) -> str | None:
    """Return the commit sha that last touched `path`'s `line_no` (1-based)."""
    try:
        result = subprocess.run(
            ["git", "blame", "-L", f"{line_no},{line_no}", "--porcelain", str(path)],
            capture_output=True, text=True, timeout=10, cwd=cx_root,
        )
        token = result.stdout.split()[0] if result.stdout.strip() else ""
        if len(token) >= 7 and all(c in "0123456789abcdef" for c in token):
            return token
    except Exception:
        pass
    return None


def _lock_commit_for_version(version: str, cx_root: Path) -> str | None:
    """Return the commit sha that locked protocol `version`, per VERSION-HISTORY.md.

    Prefers a backtick-quoted sha in the row's commits column; falls back to blaming
    the row line itself (covers rows like v1.21's "this lock commit" self-reference,
    since VERSION-HISTORY.md's own edit IS the lock commit).
    """
    vh_path = cx_root / "VERSION-HISTORY.md"
    if not vh_path.is_file():
        return None
    try:
        lines = vh_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    prefix = f"| v{version} |"
    for idx, line in enumerate(lines):
        if line.startswith(prefix):
            m = re.search(r"`([0-9a-f]{7,40})`", line)
            if m:
                return m.group(1)
            return _git_blame_line_sha(vh_path, idx + 1, cx_root)
    return None


def _cx_root(this_dir: Path) -> Path:
    """Return the Code-X-V1 root (parent of checkers/)."""
    return this_dir.parent


def _check_conflict_scan(prop_id: str, block: dict, queue_path: Path) -> list[tuple[str, str, str]]:
    """Run the 4 PBF-PROP-014 conflict_scan clauses against one PROP block.

    Returns a list of (severity, prop_id, message) findings.
    """
    findings: list[tuple[str, str, str]] = []
    cs = block.get("conflict_scan")

    # KAIZEN-CONFLICT-SCAN-PRESENT (P1, universal per §10)
    if cs is None:
        findings.append(("P1", prop_id,
            f"KAIZEN-CONFLICT-SCAN-PRESENT: PROP {prop_id!r} has no conflict_scan block — "
            f"every PROP must carry a conflict_scan (universal per CEO §10 ratification)"))
        return findings  # no point checking sub-shape if absent

    if not isinstance(cs, dict):
        findings.append(("P1", prop_id,
            f"KAIZEN-CONFLICT-SCAN-SHAPE: conflict_scan must be a mapping, got {type(cs).__name__}"))
        return findings

    # KAIZEN-CONFLICT-SCAN-SHAPE (P1): required list keys + scalar keys + basis mapping
    shape_errors: list[str] = []
    for key in sorted(_CS_LIST_KEYS):
        val = cs.get(key)
        if val is None:
            shape_errors.append(f"{key!r} is missing")
        elif not isinstance(val, list):
            shape_errors.append(f"{key!r} must be a list, got {type(val).__name__}")
    for key in sorted(_CS_SCALAR_KEYS):
        if key not in cs:
            shape_errors.append(f"{key!r} is missing")
    basis = cs.get("basis")
    if basis is None:
        shape_errors.append("'basis' mapping is missing")
    elif not isinstance(basis, dict):
        shape_errors.append(f"'basis' must be a mapping, got {type(basis).__name__}")
    if shape_errors:
        findings.append(("P1", prop_id,
            f"KAIZEN-CONFLICT-SCAN-SHAPE: conflict_scan has shape errors: {'; '.join(shape_errors)}"))
        return findings  # basis checks need a valid basis

    # KAIZEN-CONFLICT-SCAN-RESOLVED (P0): any listed entry + blank/placeholder resolution_ref
    has_hits = any(
        isinstance(cs.get(k), list) and len(cs[k]) > 0
        for k in _CS_LIST_KEYS
    )
    resolution = cs.get("resolution_ref", "")
    # P3-009: exact normalized-token matching replaces first-3-char prefix matching.
    # "plans/foo.md" is NOT a placeholder; "placeholder" exactly IS.
    _PLACEHOLDER_EXACT = {"tbd", "todo", "placeholder", "n/a"}
    resolution_blank = (
        not isinstance(resolution, str)
        or resolution.strip() == ""
        or resolution.strip().lower() in _PLACEHOLDER_EXACT
        or resolution.strip().startswith("<")
    )
    if has_hits and resolution_blank:
        findings.append(("P0", prop_id,
            f"KAIZEN-CONFLICT-SCAN-RESOLVED: conflict_scan lists ≥1 entry in "
            f"duplicates/ambiguities/conflicts but resolution_ref is blank/placeholder — "
            f"every listed hit must be resolved"))

    # KAIZEN-RESOLUTION-REF-RESOLVABLE (P1, P2-007): when hits exist and resolution_ref is
    # non-blank, it must look like a real in-repo file path (contains '/'), a section ref
    # (contains '§' or '#'), or a CEO-D id — not free-form prose.
    if has_hits and not resolution_blank:
        ref_str = resolution.strip()
        ref_valid = (
            "/" in ref_str
            or "§" in ref_str
            or "#" in ref_str
            or ref_str.upper().startswith("CEO-D-")
        )
        if not ref_valid:
            findings.append(("P1", prop_id,
                f"KAIZEN-RESOLUTION-REF-RESOLVABLE: resolution_ref {ref_str!r} must be a real "
                "in-repo file path (with '/'), section ref (with '§' or '#'), or CEO-D id — "
                "free-form prose is not a resolvable reference (P2-007)"))

    # KAIZEN-CONFLICT-SCAN-BASIS-CURRENT (P1, §9-G4 + §10)
    # Historical PROPs carry basis.source = backscan-2026-06-30 — accepted in lieu of live shas.
    # Forward PROPs carry live shas/counts that the checker recomputes.
    if isinstance(basis, dict):
        source = basis.get("source", "")
        if source == _CS_BACKSCAN_SOURCE:
            # P1-002: backscan source is ONLY for the pre-v1.21 historical PROP set
            # (ids present in PROP-CROSSWALK.md). Sub-parts and test/demo ids are exempt.
            # A forward PROP declaring backscan to skip live recompute → P1.
            _is_subpart = bool(_SUBPART_ID_RE.match(prop_id))
            _is_test = any(prop_id.startswith(pfx) for pfx in _EXEMPT_ID_PREFIXES)
            if (not _is_subpart and not _is_test
                    and (_NEW_ID_RE.match(prop_id) or _OLD_ID_RE.match(prop_id))):
                _cx_r = _cx_root(_THIS_DIR)
                _cw_path = _cx_r / "PROP-CROSSWALK.md"
                if _cw_path.is_file():
                    # Build a comprehensive "known" set: new-format ids + all old PROP-NNN
                    # ids from ANY crosswalk row (including retired entries whose "new" column
                    # is a disposition string, not a stage-prefixed id).
                    _cw = _load_crosswalk(_cx_r)
                    _all_known: set[str] = set()
                    if _cw is not None:
                        _all_known = set(_cw.keys()) | set(_cw.values())
                    # Also scan raw text for old-format PROP-NNN in any table row.
                    _cw_text = _cw_path.read_text(encoding="utf-8")
                    for _line in _cw_text.splitlines():
                        _cols = [c.strip() for c in _line.split("|")]
                        if len(_cols) >= 3 and _OLD_ID_RE.match(_cols[1]):
                            _all_known.add(_cols[1])
                    if prop_id not in _all_known:
                        findings.append(("P1", prop_id,
                            f"KAIZEN-CONFLICT-SCAN-BASIS-CURRENT: forward PROP must carry a live "
                            f"recomputable basis — basis.source: {_CS_BACKSCAN_SOURCE!r} is reserved "
                            f"for the pre-v1.21 historical PROP set (ids in PROP-CROSSWALK.md); "
                            f"{prop_id!r} is not in the crosswalk"))
        else:
            # Forward PROP: commit-anchored basis (PBF-PROP-014-CSFIX). scan_commit pins
            # every sha/count to an immutable commit — no self-reference, no ripple.
            cx_root = _cx_root(_THIS_DIR)
            ledger_rel = "MEMORY/CEO-DECISION-LEDGER.md"
            crosswalk_rel = "PROP-CROSSWALK.md"
            queue_rel = Path(os.path.relpath(queue_path.resolve(), cx_root.resolve())).as_posix()

            scan_commit = basis.get("scan_commit", "")
            declared_pc = basis.get("prop_count")
            declared_dc = basis.get("decision_count")

            basis_errors: list[str] = []
            for bkey in sorted(_CS_BASIS_LIVE):
                if bkey not in basis:
                    basis_errors.append(f"basis.{bkey!r} missing")

            if not basis_errors:
                # SHAPE: statically fixturable — always runs.
                if not (isinstance(scan_commit, str) and len(scan_commit) == 40
                        and all(c in "0123456789abcdef" for c in scan_commit)):
                    basis_errors.append(
                        f"basis.scan_commit must be a 40-hex commit sha, got {scan_commit!r}")

                if not isinstance(declared_pc, int):
                    basis_errors.append(
                        f"basis.prop_count must be an integer, got {type(declared_pc).__name__} "
                        f"{declared_pc!r} — P2-008 shape error")
                if not isinstance(declared_dc, int):
                    basis_errors.append(
                        f"basis.decision_count must be an integer, got {type(declared_dc).__name__} "
                        f"{declared_dc!r} — P2-008 shape error")

            # Test-fixture carve-out: a static contract-bite fixture carries the sentinel and
            # skips git resolution ONLY under CODE_X_TEST_MODE=1. In production the sentinel is
            # just a sha absent from the object store and fails closed below.
            _shape_only = (scan_commit == _SCAN_COMMIT_TEST_SENTINEL
                           and os.environ.get("CODE_X_TEST_MODE") == "1")

            if not basis_errors and not _shape_only:
                # GIT-RESOLUTION (fail-closed): a forward PROP MUST anchor to real committed
                # state — an unresolvable scan_commit is a P1, never a SHAPE-only pass.
                declared_q_sha = basis.get("queue_sha", "")
                declared_l_sha = basis.get("ledger_sha", "")
                declared_x_sha = basis.get("crosswalk_sha", "")

                live_q_sha = _git_blob_sha_at_commit(scan_commit, queue_rel, cx_root)
                if live_q_sha is None:
                    basis_errors.append(
                        f"basis.scan_commit {scan_commit!r} does not resolve to a committed blob — "
                        f"a forward PROP must anchor to real committed state")
                else:
                    if not _is_ancestor(scan_commit, "HEAD", cx_root):
                        basis_errors.append(
                            f"basis.scan_commit {scan_commit!r} is not an ancestor of HEAD")

                    lock_commit = _lock_commit_for_version(PROTOCOL_VERSION, cx_root)
                    if lock_commit is None:
                        basis_errors.append(
                            f"cannot resolve the v{PROTOCOL_VERSION} lock commit from "
                            f"VERSION-HISTORY.md — version floor unverifiable")
                    elif not _is_ancestor(lock_commit, scan_commit, cx_root):
                        basis_errors.append(
                            f"basis.scan_commit {scan_commit!r} predates the v{PROTOCOL_VERSION} "
                            f"lock commit {lock_commit!r} — scanned against pre-lock history")

                    if declared_q_sha != live_q_sha:
                        basis_errors.append(
                            f"basis.queue_sha stale: declared {declared_q_sha!r} != "
                            f"at-commit {live_q_sha!r}")

                    live_l_sha = _git_blob_sha_at_commit(scan_commit, ledger_rel, cx_root)
                    if live_l_sha and declared_l_sha != live_l_sha:
                        basis_errors.append(
                            f"basis.ledger_sha stale: declared {declared_l_sha!r} != "
                            f"at-commit {live_l_sha!r}")

                    ledger_text = _git_blob_text_at_commit(scan_commit, ledger_rel, cx_root)
                    if ledger_text is not None:
                        live_dc = sum(1 for line in ledger_text.splitlines()
                                      if line.strip().startswith("- id:"))
                        if declared_dc != live_dc:
                            basis_errors.append(
                                f"basis.decision_count stale: declared {declared_dc} != "
                                f"at-commit {live_dc}")

                    # crosswalk may not exist yet at scan_commit (pre-PROP-043) — degrade safely
                    live_x_sha = _git_blob_sha_at_commit(scan_commit, crosswalk_rel, cx_root)
                    if live_x_sha and declared_x_sha != live_x_sha:
                        basis_errors.append(
                            f"basis.crosswalk_sha stale: declared {declared_x_sha!r} != "
                            f"at-commit {live_x_sha!r}")

                    queue_text = _git_blob_text_at_commit(scan_commit, queue_rel, cx_root)
                    if queue_text is not None:
                        live_pc = len(_parse_prop_blocks(queue_text))
                        if declared_pc != live_pc:
                            basis_errors.append(
                                f"basis.prop_count stale: declared {declared_pc} != "
                                f"at-commit {live_pc}")

            if basis_errors:
                findings.append(("P1", prop_id,
                    f"KAIZEN-CONFLICT-SCAN-BASIS-CURRENT: conflict_scan basis is stale or missing "
                    f"fields — {'; '.join(basis_errors)}"))

    return findings


def cmd_kaizen(args) -> int:
    """Audit the KAIZEN protocol-improvement queue for closure hygiene.

    cx check kaizen <queue_file> [--contracts <path>] [--strict-debt]

    Parses ```yaml fences (G1: PROP-id discriminated), classifies APPLIED PROPs,
    runs the 7 KAIZEN-* clauses (Part F) + the 4 PBF-PROP-014 CONFLICT-SCAN clauses +
    the BUILD-CONFLICT-SCAN-STEP-MISSING marker clause, and returns
    findings_report(findings).
    """
    queue_path = Path(args.queue_file)
    if not queue_path.is_file():
        print(f"  [ERROR] queue file not found: {queue_path}", flush=True)
        return 1

    contracts_path = Path(args.contracts) if getattr(args, "contracts", None) else _DEFAULT_CONTRACTS
    # Path safety: contracts must be within the repo root (two levels up from checkers/).
    cx_root = _THIS_DIR.parent
    try:
        contracts_path.resolve().relative_to(cx_root.resolve())
    except ValueError:
        print(f"  [ERROR] --contracts path escapes Code-X root: {contracts_path}", flush=True)
        return 1

    # --strict-debt default is ON (PBF-PROP-013 §2e: all 44 PROPs are now in yaml fences,
    # so the unparseable-debt class is zero and the stricter default is earned).
    strict_debt: bool = getattr(args, "strict_debt", True)
    # --conflict-scan activates the PBF-PROP-014 conflict_scan clauses.
    # Also activates the PBF-PROP-013 stage-rename clauses (ID-FORMAT / PREFIX-MATCHES-STAGES /
    # SERIES-ORDER-GAPLESS / LEGACY-ID-PRESENT-UNIQUE / CROSSWALK-COMPLETE).
    conflict_scan_active: bool = getattr(args, "conflict_scan", False)

    clause_ids = _load_clause_ids(contracts_path)
    queue_text = queue_path.read_text(encoding="utf-8")
    blocks = _parse_prop_blocks(queue_text)

    findings: list[tuple[str, str, str]] = []

    # KAIZEN-PROP-ID-PARSEABLE: detect semantic fences with malformed ids (always active).
    findings.extend(_check_malformed_prop_ids(queue_text))

    # KAIZEN-FENCE-PROP-SHAPED-UNPARSEABLE: a fence variant the tolerant regex still misses,
    # but which is PROP-shaped text, must be a loud finding (always active).
    findings.extend(_check_unrecognized_prop_shaped_fences(queue_text))

    # PBF-PROP-013 stage-rename clauses — run once over all blocks when --conflict-scan active.
    if conflict_scan_active:
        findings.extend(_check_stage_rename(blocks, cx_root))

    for block in blocks:
        prop_id = block.get("id", "<unknown>")

        # KAIZEN-APPLIED-ENTRY-PARSEABLE — unparseable sentinel
        if block.get("_unparseable"):  # type: ignore[truthy-function]
            raw_preview = block.get("_raw", "")[:80].replace("\n", " ")
            sev = "P1" if strict_debt else "P2"
            findings.append((sev, prop_id,
                f"KAIZEN-APPLIED-ENTRY-PARSEABLE: yaml fence could not be parsed — {raw_preview!r}"))
            continue

        # PBF-PROP-014 conflict_scan clauses — run on EVERY PROP block when --conflict-scan is active.
        # Without the flag the clauses are defined + fixture-proven but not wired to the live queue
        # yet (historical backfill happens in PBF-PROP-013; scope note in PBF-PROP-014 spec §scope).
        if conflict_scan_active:
            cs_findings = _check_conflict_scan(prop_id, block, queue_path)
            findings.extend(cs_findings)
            # BUILD-CONFLICT-SCAN-STEP-MISSING (P1): conflict_scan must contain a
            # scan_step_marker that proves the orchestrator injected the scan step.
            cs = block.get("conflict_scan")
            if isinstance(cs, dict):
                if not cs.get("scan_step_marker"):
                    findings.append(("P1", prop_id,
                        f"BUILD-CONFLICT-SCAN-STEP-MISSING: conflict_scan.scan_step_marker is absent "
                        f"for PROP {prop_id!r} — the PROP-authoring dispatch must inject the "
                        f"conflict-scan step and record its marker here"))

        status = _status_value(block)
        # KAIZEN-STATUS-ENUM-VALID (P1, PBF-PROP-021 group-2 hole #7): `status` was previously
        # compared with a bare `!= "APPLIED"` — any case/typo drift ("applied", "APPLED", ...)
        # silently read as "not applied" and skipped every APPLIED-only clause below, exempting a
        # genuinely-applied behavioural PROP from its own enforcement requirement. Enum-validate
        # first; an unrecognized value is flagged AND, fail-closed, still treated as APPLIED for
        # the checks below — it might BE a typo'd APPLIED, and treating it as "not applied" is
        # exactly the hole this closes.
        if status and status not in _VALID_KAIZEN_STATUSES:
            findings.append(("P1", prop_id,
                f"KAIZEN-STATUS-ENUM-VALID: status={status!r} is not a valid enum value "
                f"{sorted(_VALID_KAIZEN_STATUSES)} — a case/typo drift of APPLIED must not "
                f"silently exempt this PROP from the APPLIED-only clauses; treating it as "
                f"APPLIED (fail closed) until the status is corrected"))
            is_applied = True
        else:
            is_applied = (status == "APPLIED")
        if not is_applied:
            continue

        # KAIZEN-BEHAVIOURAL-FIELD-PRESENT — every APPLIED PROP must have a behavioural field
        if "behavioural" not in block:
            findings.append(("P1", prop_id,
                "KAIZEN-BEHAVIOURAL-FIELD-PRESENT: APPLIED PROP is missing the 'behavioural' field"))
            continue

        behavioural = block["behavioural"]
        if not behavioural:
            # behavioural: no — no enforcement required
            continue

        # behavioural: yes — must have enforcement
        enf = block.get("enforcement")

        # KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT
        if not enf or not isinstance(enf, dict):
            findings.append(("P0", prop_id,
                "KAIZEN-BEHAVIOURAL-APPLIED-NEEDS-ENFORCEMENT: behavioural APPLIED PROP has no enforcement block"))
            continue

        kind = enf.get("kind", "")

        # KAIZEN-ENFORCEMENT-NOT-PRESENCE-ONLY — banned kinds
        if kind in _BANNED_KINDS:
            findings.append(("P0", prop_id,
                f"KAIZEN-ENFORCEMENT-NOT-PRESENCE-ONLY: enforcement.kind={kind!r}; presence-lint is "
                f"BANNED for a behavioural APPLIED PROP — use clause/prompt_marker/judgment_limit"))
            continue

        # KAIZEN-ENFORCEMENT-NOT-PRESENCE-ONLY — unknown kind
        if kind not in _ALLOWED_KINDS:
            findings.append(("P0", prop_id,
                f"KAIZEN-ENFORCEMENT-NOT-PRESENCE-ONLY: enforcement.kind={kind!r} is not a recognised "
                f"allowed kind ({', '.join(sorted(_ALLOWED_KINDS))})"))
            continue

        # Kind-specific checks
        if kind == "clause":
            clause_id = enf.get("clause_id", "")
            # KAIZEN-ENFORCEMENT-CLAUSE-EXISTS
            if clause_id not in clause_ids:
                findings.append(("P0", prop_id,
                    f"KAIZEN-ENFORCEMENT-CLAUSE-EXISTS: enforcement.clause_id={clause_id!r} not found "
                    f"in check-contracts.yaml — every clause reference must resolve to a real biting clause"))

        elif kind == "prompt_marker":
            ref = enf.get("prompt_ref", "")
            # KAIZEN-PROMPT-REF-SHAPE
            if ref and not _path_safe(str(ref)):
                findings.append(("P1", prop_id,
                    f"KAIZEN-PROMPT-REF-SHAPE: enforcement.prompt_ref={ref!r} is absolute or escapes "
                    f"the repo — prompt_ref must be a relative in-repo path"))

        elif kind == "judgment_limit":
            # KAIZEN-JUDGMENT-LIMIT-SHAPE
            missing = sorted(_JL_REQUIRED - set(enf.keys()))
            if missing:
                findings.append(("P1", prop_id,
                    f"KAIZEN-JUDGMENT-LIMIT-SHAPE: enforcement.kind=judgment_limit is missing required "
                    f"fields: {missing} — all of justification/review_lens/ceo_decision_ref are required"))

    # P2 findings are DEBT — printed but non-blocking (gate stays green).
    # Only P0/P1 block (findings_report returns 1 for any finding in the list).
    p2_findings = [(sev, loc, msg) for sev, loc, msg in findings if sev == "P2"]
    blocking = [(sev, loc, msg) for sev, loc, msg in findings if sev != "P2"]

    if p2_findings:
        print("  [INFO] DEBT findings (non-blocking):")
        for sev, loc, msg in p2_findings:
            print(f"  [{sev}] {loc} — {msg}")

    return findings_report(blocking)
