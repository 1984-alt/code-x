# cmd_consistency: checks every rule in the registry is present in all its appears_in files.
import os
import re
from pathlib import Path

from cx_common import findings_report, load_yaml

# Default registry location relative to this script's parent directory (checkers/)
_DEFAULT_REGISTRY = Path(__file__).parent / "rule-registry.yaml"
# Root of the Code-X-V1 tree is one level up from checkers/
_CX_ROOT = Path(__file__).parent.parent


def _normalise_ws(text: str) -> str:
    """Collapse all whitespace runs to a single space and strip."""
    return re.sub(r'\s+', ' ', text).strip()


def _canonical_phrases(canonical_raw) -> list[str]:
    """Normalise canonical field: string → 1-element list, list → list of strings.
    All phrases must appear (whitespace-normalised) for a file to PASS.
    Backward-compat: a plain string is treated as a 1-element list.
    """
    if isinstance(canonical_raw, list):
        return [_normalise_ws(str(p)) for p in canonical_raw if str(p).strip()]
    return [_normalise_ws(str(canonical_raw))] if str(canonical_raw).strip() else []


# PROP-005/012: structural sweep exemptions — never swept in ANY mode.
# The registry cannot be an "unregistered copy" of itself (handled separately by
# path), and tests/fixtures are deliberately pinned good/bad copies of rule text.
_NEVER_SWEPT_PREFIXES = ("checkers/tests/",)


def _path_safe(root: Path, rel_path: str, registry_path: str, findings: list) -> Path | None:
    """Resolve rel_path under root. Reject absolute paths and .. escapes. P1-09."""
    if os.path.isabs(rel_path):
        findings.append(("P0", registry_path,
            f"appears_in path '{rel_path}' is absolute — paths must be relative to Code-X root"))
        return None
    resolved = (root / rel_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        findings.append(("P0", registry_path,
            f"appears_in path '{rel_path}' escapes the Code-X root via '..' — rejected"))
        return None
    return resolved


def cmd_consistency(args) -> int:
    """Check that every rule in the registry is present in all its appears_in files.

    canonical field supports:
      - string: single required substring (whitespace-normalised) — backward-compat
      - list:   ALL substrings must appear (whitespace-normalised) in the file
    A [RULE:<id>] pointer in the file is always a full PASS regardless of canonical.

    --strict: unlisted files carrying key_phrases FAIL instead of WARN (except design-history/).
    --registry: supply a custom registry path (must be within Code-X root).
    """
    strict = getattr(args, 'strict', False)
    registry_path_raw = getattr(args, 'registry', None) or str(_DEFAULT_REGISTRY)

    # P1-09: bound user-supplied --registry path to root
    # Resolve BOTH absolute AND relative paths against root — (root / abs_path) == abs_path
    # so this single form covers both cases without special-casing.
    root = _CX_ROOT.resolve()
    if getattr(args, 'registry', None):
        try:
            registry_resolved = (root / registry_path_raw).resolve()
            registry_resolved.relative_to(root)
            registry_path = str(registry_resolved)
        except ValueError:
            print(f"FIX-FIRST\n  [P0] {registry_path_raw} — --registry path escapes Code-X root")
            return 1
    else:
        registry_path = registry_path_raw

    reg, err = load_yaml(registry_path)
    if err:
        print(f"FIX-FIRST\n  [P1] {registry_path} — registry load error: {err}")
        return 1
    if not isinstance(reg, dict) or not isinstance(reg.get("rules"), list):
        print(f"FIX-FIRST\n  [P1] {registry_path} — registry must be a mapping with a 'rules' list")
        return 1

    rules = reg["rules"]
    findings = []
    warnings = []

    # --- Validate registry itself: no dup ids, all appears_in paths exist + path safety (P1-09) ---
    seen_ids: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            findings.append(("P1", registry_path, "registry entry is not a mapping"))
            continue
        rid = rule.get("id", "")
        if not rid:
            findings.append(("P1", registry_path, "registry entry missing 'id'"))
            continue
        if rid in seen_ids:
            findings.append(("P1", registry_path, f"duplicate id '{rid}' in registry"))
        seen_ids.add(rid)

        for rel_path in (rule.get("appears_in") or []):
            safe = _path_safe(root, rel_path, registry_path, findings)
            if safe is None:
                continue  # already appended a finding
            if not safe.exists():
                findings.append(("P1", registry_path,
                    f"rule '{rid}': appears_in path does not exist: {rel_path}"))

    # --- PROP-005/012: declared sweep scope (scan_scope.rule_bearing) ---
    # Effective sweep scope = rule_bearing ∪ all appears_in paths. A registry
    # WITHOUT scan_scope keeps the legacy full-tree sweep (backward-compat for
    # external/test registries); the canonical registry declares it.
    scope_block = reg.get("scan_scope") or {}
    rule_bearing = scope_block.get("rule_bearing") or []
    scope_declared = bool(rule_bearing)
    scope_files: set[str] = set()
    scope_prefixes: list[str] = []
    for entry in rule_bearing:
        rel = str(entry)
        safe = _path_safe(root, rel, registry_path, findings)
        if safe is None:
            continue
        if not safe.exists():
            findings.append(("P1", registry_path,
                f"scan_scope.rule_bearing path does not exist: {rel} — a stale scope "
                "entry silently shrinks the sweep"))
            continue
        if rel.endswith("/") or safe.is_dir():
            scope_prefixes.append(rel.rstrip("/") + "/")
        else:
            scope_files.add(rel)

    if findings:
        # Registry invalid — report and stop
        return findings_report(findings)

    # --- Check each rule against each appears_in file ---
    all_file_contents: dict[str, str] = {}

    for rule in rules:
        rid = rule["id"]
        phrases = _canonical_phrases(rule.get("canonical", ""))
        pointer = f"[RULE:{rid}]"
        banned_negations = [str(bn) for bn in (rule.get("banned_negations") or [])]
        appears_in = rule.get("appears_in") or []

        for rel_path in appears_in:
            safe = _path_safe(root, rel_path, registry_path, findings)
            if safe is None:
                continue
            full = safe
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                findings.append(("P1", str(rel_path), f"rule '{rid}': could not read file: {exc}"))
                continue

            all_file_contents[rel_path] = content
            norm_content = _normalise_ws(content)

            if pointer in content:
                pass  # [RULE:id] pointer = full PASS regardless of canonical
            else:
                # ALL phrases must appear
                missing = [p for p in phrases if p not in norm_content]
                if missing:
                    missing_quoted = ", ".join(f"'{p}'" for p in missing)
                    findings.append(("P1", str(rel_path),
                        f"rule '{rid}' drifted/missing — required phrase(s) absent: {missing_quoted}"
                        f" (and no [RULE:{rid}] pointer)"))

            # P1-07: banned_negations tripwire — any match = likely meaning-flip → FAIL
            for bn in banned_negations:
                if bn.lower() in content.lower():
                    findings.append(("P1", str(rel_path),
                        f"rule '{rid}' — banned_negation phrase detected: '{bn}' — "
                        "likely meaning-flip in this appears_in file"))

    # --- Soft WARN / --strict FAIL: unlisted files with ≥2 key_phrases ---
    # P2-05: scan BOTH .md and .yaml (P1-08: strict mode)
    # PROP-005/012: the sweep covers RULE-BEARING CANON ONLY (scan_scope ∪
    # appears_in). Out-of-scope narrative/history is silent in BOTH modes —
    # narrative cites rules, canon defines them. Sweep silence never exempts an
    # active dispatch artifact: the current card/deck/state are checked by their
    # own cx commands (G1/G7 path), which is where operational drift bites.
    all_appears_in: set[str] = set()
    for rule in rules:
        for rel in (rule.get("appears_in") or []):
            all_appears_in.add(str(rel))

    try:
        registry_rel = str(Path(registry_path).resolve().relative_to(root))
    except ValueError:
        registry_rel = None

    def _in_sweep(rel: str) -> bool:
        if rel == registry_rel:
            return False  # the registry is the canonical source, never a copy of itself
        if any(rel.startswith(pfx) for pfx in _NEVER_SWEPT_PREFIXES):
            return False  # pinned test fixtures, by design
        if not scope_declared:
            return True   # legacy registry without scan_scope: full-tree sweep
        return (rel in scope_files
                or any(rel.startswith(pfx) for pfx in scope_prefixes))

    candidates = list(root.rglob("*.md")) + list(root.rglob("*.yaml"))
    for candidate in candidates:
        try:
            rel = str(candidate.relative_to(root))
        except ValueError:
            continue
        if rel in all_appears_in:
            continue
        if not _in_sweep(rel):
            continue
        # Load content
        if rel not in all_file_contents:
            try:
                all_file_contents[rel] = candidate.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
        content = all_file_contents[rel]
        for rule in rules:
            rid = rule["id"]
            pointer = f"[RULE:{rid}]"
            key_phrases = [str(kp) for kp in (rule.get("key_phrases") or [])]
            phrases = _canonical_phrases(rule.get("canonical", ""))
            norm_content = _normalise_ws(content)
            hits = sum(1 for kp in key_phrases if kp in content)
            if hits >= 2 and pointer not in content:
                # D4: a full canonical copy is duplication (register it); a partial
                # match is possible paraphrase drift. Severity unchanged either way.
                all_phrases_present = phrases and all(p in norm_content for p in phrases)
                detail = ("carries the full canonical rule — register it in appears_in"
                          if all_phrases_present else
                          "canonical/pointer missing (possible unregistered/paraphrased copy)")
                if strict:
                    findings.append(("P1", rel,
                        f"rule '{rid}': {hits} key_phrases present in unlisted file — "
                        f"{detail} (--strict mode: FAIL not WARN)"))
                else:
                    warnings.append(f"WARN  {rel} — rule '{rid}': {hits} key_phrases present — {detail}")

    # Print warnings (soft — do not affect exit code)
    for w in warnings:
        print(w)

    return findings_report(findings)
