# cmd_structure: the STRUCTURE LOCK (F-PROP-001 Lever A, fold v1.16).
#
#   cx check structure <card> --repo-root <dir>
#
# THE GAP IT CLOSES: `allowed_files` is a per-card allowed-EDIT list; nothing froze the whole-app
# file tree and failed a fix that RESTRUCTURED it (created / renamed / moved / deleted files outside
# the fix's declared scope). The CEO symptom — "the whole structure wanders over time during fixes"
# — had no in-loop deterministic gate. This is it.
#
# LAYER CUT (honest, stated up front — CX-CHECK-SPEC forbids green over-claim):
#   LAYER 1 — deterministic, BITES.  FILE-TREE / PATH changes only: a mode: FIX card whose live tree
#     (within the lock's roots) differs from the frozen structure_lock at a path NOT covered by the
#     card's allowed_files = structural drift (P1). Fully deterministic, forge-proof.
#   LAYER 2 — advisory only (NOT here yet).  Same-file restructuring — component splits, route-table
#     edits, prop-wiring, CSS restructuring — changes structure WITHOUT changing paths, so Layer-1
#     cannot see it. It graduates to blocking via a follow-up PROP once machine-extraction +
#     same-commit repeatability are proven (the B-PROP-009 staging). Meanwhile mitigated by the visual
#     lock (render-fidelity catches CSS/layout drift) + allowed_files (a same-file edit is still
#     scope-bound).
#
# THE structure_lock RECEIPT (machine-generated, forge-proof — never self-declared, xfam P1-1/P1-5):
#   structure_lock:
#     generator: cx check structure --emit      # the machine marker; a hand-authored receipt is forged
#     accepted_at_commit: <40-hex sha>          # the commit the lock was emitted at — MUST be a real
#                                               #   commit object in this repo (sha-BOUND, not invented)
#     roots: ["src"]                            # the subtree(s) the lock covers (default ["."] = repo)
#     paths: [<ordered repo-relative file paths within roots, at accepted_at_commit>]
#     manifest_sha: <sha256-12 of accepted_at_commit + "\n".join(sorted(paths))>
#   The checker RECOMPUTES manifest_sha and verifies accepted_at_commit exists — a self-declared hash
#   or an invented commit is rejected closed. The lock is bound to its commit, so a forged receipt that
#   copies a paths list but not the commit binding cannot pass.
#
# READ-ONLY: never builds, routes, edits source, runs git reset, or writes state. On a Layer-1 drift it
# SURFACES + BLOCKS; reverting is the fixer's job (Lever E revert_receipt), never the checker's.

import fnmatch
import hashlib
import subprocess
from pathlib import Path

from cx_common import findings_report, load_yaml
from cx_lock_fidelity import path_is_unsafe, resolve_in_repo

# The machine marker a real `cx check structure --emit` would stamp. A receipt that omits/wrongs it is
# a hand-authored forgery (the same authority pattern cx_boot uses for its machine-generated receipt).
GENERATOR_MARKER = "cx check structure --emit"


def recompute_manifest_sha(accepted_at_commit: str, paths: list) -> str:
    """The ONE recompute recipe (must match the emitter + the fixtures): sha256-12 of the accepting
    commit + the sorted path list. Binding the commit makes the hash commit-specific — a receipt that
    copies another lock's paths but names a different commit recomputes to a different hash."""
    body = str(accepted_at_commit) + "\n" + "\n".join(sorted(str(p) for p in paths))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def _within_roots(rel: str, roots: list) -> bool:
    """True if the repo-relative path rel falls under one of the lock's roots. root '.' = whole repo."""
    for r in roots:
        r = str(r).strip().rstrip("/")
        if r in ("", "."):
            return True
        if rel == r or rel.startswith(r + "/"):
            return True
    return False


def _live_paths(repo_root: str, roots: list) -> tuple[set | None, str | None]:
    """The live in-scope file set: tracked (git ls-files) + untracked-non-ignored
    (git ls-files --others --exclude-standard), filtered to roots, that ACTUALLY EXIST on disk now.
    Existence-filtering catches a tracked file deleted/moved in the working tree (still in ls-files,
    gone on disk) as a removal vs the frozen lock. Recomputed from the real repo — never trusted from
    a copy. Returns (set, error)."""
    def _lines(git_args):
        r = subprocess.run(["git", "-C", repo_root] + git_args, capture_output=True, text=True)
        if r.returncode != 0:
            return None, r.stderr.strip()
        return [ln for ln in r.stdout.splitlines() if ln.strip()], None
    tracked, terr = _lines(["ls-files"])
    if terr is not None:
        return None, f"git ls-files failed: {terr}"
    untracked, uerr = _lines(["ls-files", "--others", "--exclude-standard"])
    if uerr is not None:
        return None, f"git ls-files --others failed: {uerr}"
    base = Path(repo_root)
    out = set()
    for p in set(tracked) | set(untracked):
        if _within_roots(p, roots) and (base / p).is_file():
            out.add(p)
    return out, None


def _commit_exists(repo_root: str, sha: str) -> bool:
    """True if sha resolves to a real commit object in this repo (sha-binding is genuine, not invented)."""
    r = subprocess.run(["git", "-C", repo_root, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
                       capture_output=True, text=True)
    return r.returncode == 0 and bool(r.stdout.strip())


def _tree_paths_at_commit(repo_root: str, commit: str, roots: list) -> tuple[set | None, str | None]:
    """The AUTHORITATIVE frozen file set = `git ls-tree -r <commit>`, filtered to roots. This is what
    makes the lock forge-proof (xfam built-code review #1): a self-declared `paths` list can OMIT a file
    a fixer deleted, making the live-vs-declared diff empty — so we NEVER trust the declared list; we
    recompute the frozen side from the real tree at the accepting commit and require the lock's `paths`
    to MATCH it. Rejects symlink (mode 120000) / submodule (160000) entries within roots (xfam #2 — the
    v1.10 path-class: a frozen architecture is real in-tree regular files, not pointers). Returns
    (path_set, error)."""
    r = subprocess.run(["git", "-C", repo_root, "ls-tree", "-r", commit], capture_output=True, text=True)
    if r.returncode != 0:
        return None, f"git ls-tree at '{commit}' failed: {r.stderr.strip()}"
    out = set()
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        meta, _, path = line.partition("\t")  # "<mode> <type> <sha>\t<path>"
        if not path or not _within_roots(path, roots):
            continue
        parts = meta.split()
        mode = parts[0] if parts else ""
        if mode in ("120000", "160000"):
            return None, (f"frozen tree contains a symlink/submodule entry '{path}' (mode {mode}) within "
                          "roots — a structure lock must freeze real in-tree regular files, not pointers "
                          "(v1.10 path-class)")
        out.add(path)
    return out, None


def _is_allowed(rel: str, allowed: set, allowed_globs: list) -> bool:
    """A changed path is in-scope ONLY if it is a declared allowed_file (exact or glob). new_outputs is
    NOT a separate allow-list (xfam #3): a created file must be in allowed_files, and a rename =
    delete+add where BOTH sides must be allowed — otherwise a fix could create files outside its scope by
    listing them only in new_outputs."""
    if rel in allowed:
        return True
    return any(fnmatch.fnmatch(rel, pat) for pat in allowed_globs)


def validate_structure_lock(card: dict, repo_root: str, loc: str) -> list:
    """Validate ONE mode: FIX card's structure_lock. Returns a list of (severity, loc, msg) findings —
    EMPTY means no Layer-1 structural drift and a well-formed forge-proof lock. Shared by cmd_structure
    (the CLI / build-turn rail) AND cx_module_acceptance (the Andon wall) so both ends compute identically.
    A non-FIX card has no structure obligation → returns []. Fails CLOSED: a missing ref / unreadable
    lock / unsafe path is a finding, never a silent pass."""
    findings = []
    if str(card.get("mode", "")) != "FIX":
        return findings  # only fixes carry a preserve-the-structure obligation

    # FIX-STAGE-STRUCT-LOCK-REF — fail closed if a fix names no frozen architecture to preserve.
    ref = str(card.get("structure_lock_ref", "") or "").strip()
    if not ref:
        findings.append(("P1", loc,
            "mode: FIX card without structure_lock_ref — a fix must bind to the frozen architecture it "
            "preserves; nothing freezes the file tree otherwise (F-PROP-001 Lever A / FIX-STAGE-STRUCT-LOCK-REF)"))
        return findings

    # FIX-STAGE-STRUCT-PATHSAFE — the ref must be a real in-tree path (no absolute / '..' / symlink /
    # outside-repo); reuses the v1.10 path-safety shape so a fix cannot point the lock at arbitrary bytes.
    resolved, perr = resolve_in_repo(repo_root, ref)
    if perr is not None:
        findings.append(("P1", loc,
            f"structure_lock_ref {perr} (F-PROP-001 Lever A / FIX-STAGE-STRUCT-PATHSAFE)"))
        return findings
    if resolved is None or not resolved.is_file():
        findings.append(("P1", loc,
            f"structure_lock_ref '{ref}' does not resolve to a real in-repo file — a missing lock is not "
            "a preserved architecture (F-PROP-001 Lever A / FIX-STAGE-STRUCT-LOCK-REF)"))
        return findings

    doc, derr = load_yaml(str(resolved))
    lock = doc.get("structure_lock") if isinstance(doc, dict) else None
    if derr or not isinstance(lock, dict):
        findings.append(("P1", loc,
            f"structure_lock_ref '{ref}' is not a typed structure_lock mapping {{generator, "
            "accepted_at_commit, roots, paths, manifest_sha}} — an arbitrary file is not a lock "
            "(F-PROP-001 Lever A / FIX-STAGE-STRUCT-FORGED)"))
        return findings

    generator = str(lock.get("generator", "") or "").strip()
    commit = str(lock.get("accepted_at_commit", "") or "").strip()
    declared_sha = str(lock.get("manifest_sha", "") or "").strip()
    paths = lock.get("paths")
    roots = lock.get("roots") or ["."]
    if not isinstance(roots, list) or not roots:
        roots = ["."]

    # FIX-STAGE-STRUCT-FORGED — machine-generated + sha-BOUND to a real commit. A hand-authored receipt
    # (wrong/blank generator marker), a missing/invalid commit, or a commit that is not real in this repo
    # is a forgery: it cannot prove it was emitted at a real acceptance.
    if generator != GENERATOR_MARKER:
        findings.append(("P1", loc,
            f"structure_lock.generator '{generator}' is not the machine marker '{GENERATOR_MARKER}' — a "
            "hand-authored lock is forged; only an emitted receipt is trusted (F-PROP-001 Lever A / "
            "FIX-STAGE-STRUCT-FORGED)"))
        return findings
    if not isinstance(paths, list):
        findings.append(("P1", loc,
            "structure_lock.paths is missing or not a list — a lock with no frozen path list cannot be "
            "compared (F-PROP-001 Lever A / FIX-STAGE-STRUCT-FORGED)"))
        return findings
    if len(commit) < 7 or not all(c in "0123456789abcdef" for c in commit.lower()):
        findings.append(("P1", loc,
            f"structure_lock.accepted_at_commit '{commit}' is not a commit sha — the lock must be "
            "sha-bound to the commit it was accepted at (F-PROP-001 Lever A / FIX-STAGE-STRUCT-FORGED)"))
        return findings
    if not _commit_exists(repo_root, commit):
        findings.append(("P1", loc,
            f"structure_lock.accepted_at_commit '{commit}' is not a real commit in this repo — an "
            "invented commit is not a binding (F-PROP-001 Lever A / FIX-STAGE-STRUCT-FORGED)"))
        return findings
    # any path-unsafe entry in the frozen list (or roots) is a forged/unsafe manifest
    for entry in list(paths) + list(roots):
        if path_is_unsafe(str(entry)):
            findings.append(("P1", loc,
                f"structure_lock contains an unsafe path '{entry}' (absolute / '..') — every frozen path "
                "must be repo-relative in-tree (F-PROP-001 Lever A / FIX-STAGE-STRUCT-PATHSAFE)"))
            return findings
    # each root must resolve INSIDE the repo and not be a symlink (xfam built-code review #2): path_is_unsafe
    # above catches absolute / '..' but NOT a symlinked root that escapes the repo. resolve_in_repo rejects
    # symlink / abs / '..' / outside-repo, reusing the v1.10 path-class for the lock's root subtree(s).
    for r in roots:
        _rres, rerr = resolve_in_repo(repo_root, str(r))
        if rerr is not None:
            findings.append(("P1", loc,
                f"structure_lock root {rerr} — a frozen root must be a real in-repo directory, never a "
                "symlink/escape (F-PROP-001 Lever A / FIX-STAGE-STRUCT-PATHSAFE)"))
            return findings

    # FIX-STAGE-STRUCT-HASH-RECOMPUTE — never trust the declared hash; recompute from the receipt's own
    # commit + paths. A self-declared / edited manifest_sha that does not bind the real list+commit fails.
    real_sha = recompute_manifest_sha(commit, paths)
    if not declared_sha:
        findings.append(("P1", loc,
            "structure_lock.manifest_sha missing — the lock must carry the recomputable hash binding its "
            "paths to its commit (F-PROP-001 Lever A / FIX-STAGE-STRUCT-HASH-RECOMPUTE)"))
        return findings
    if declared_sha != real_sha:
        findings.append(("P1", loc,
            f"structure_lock.manifest_sha '{declared_sha}' != the RECOMPUTED hash '{real_sha}' of its "
            "commit + paths — a self-declared structure hash is never trusted (F-PROP-001 Lever A / "
            "FIX-STAGE-STRUCT-HASH-RECOMPUTE)"))
        return findings

    # FIX-STAGE-STRUCT-TREE-BOUND — the frozen side is the REAL tree at the commit, NEVER the self-declared
    # paths list (xfam built-code review #1, the #1 defect). Recompute the authoritative file set from
    # `git ls-tree` at accepted_at_commit (within roots) and require the lock's paths to MATCH it. Without
    # this, a fixer who deletes a tracked file and OMITS it from paths (recomputing a self-consistent hash —
    # so HASH-RECOMPUTE above still passes) would empty the live-vs-frozen diff; binding to ls-tree closes it.
    frozen_tree, terr = _tree_paths_at_commit(repo_root, commit, roots)
    if terr or frozen_tree is None:
        findings.append(("P1", loc,
            f"cannot recompute the frozen tree from git ls-tree at '{commit}' to bind the structure_lock — "
            f"{terr} (fail closed) (F-PROP-001 Lever A / FIX-STAGE-STRUCT-TREE-BOUND)"))
        return findings
    declared_paths = {str(p) for p in paths}
    if declared_paths != frozen_tree:
        missing = sorted(frozen_tree - declared_paths)  # in the real tree, omitted from the lock
        extra = sorted(declared_paths - frozen_tree)    # in the lock, not in the real tree
        findings.append(("P1", loc,
            f"structure_lock.paths do not match git ls-tree at {commit[:12]} (omitted-from-lock: {missing}; "
            f"not-in-tree: {extra}) — the frozen architecture is bound to the REAL tree, never a self-declared "
            "paths list; omitting a deleted/renamed file to empty the live diff is the forgery this closes "
            "(F-PROP-001 Lever A / FIX-STAGE-STRUCT-TREE-BOUND)"))
        return findings

    # FIX-STAGE-STRUCT-MANIFEST — the actual Layer-1 drift: the live in-scope tree vs the frozen path
    # set, minus the fix's declared allowed scope. Any created/renamed/moved/deleted path OUTSIDE
    # allowed_files is structural drift. The frozen side is the VERIFIED ls-tree set (== declared_paths,
    # proven equal just above), never trusted from the lock's own list.
    live, lerr = _live_paths(repo_root, roots)
    if lerr or live is None:
        findings.append(("P1", loc,
            f"cannot recompute the live file tree to compare against the structure_lock — {lerr} "
            "(fail closed) (F-PROP-001 Lever A / FIX-STAGE-STRUCT-MANIFEST)"))
        return findings
    frozen = frozen_tree
    changed = (live - frozen) | (frozen - live)  # created/untracked + deleted/moved
    allowed_raw = [str(f) for f in (card.get("allowed_files") or [])]
    allowed = {f for f in allowed_raw if not any(ch in f for ch in "*?[")}
    allowed_globs = [f for f in allowed_raw if any(ch in f for ch in "*?[")]
    drift = sorted(p for p in changed if not _is_allowed(p, allowed, allowed_globs))
    if drift:
        findings.append(("P1", loc,
            f"mode: FIX card restructured the file tree OUTSIDE its allowed_files {sorted(allowed_raw)}: "
            f"{drift} — a fix preserves the architecture; create/rename/move/delete outside the declared "
            "scope is drift. SURFACE + revert (Lever E revert_receipt), do not fix-forward (F-PROP-001 "
            "Lever A / FIX-STAGE-STRUCT-MANIFEST)"))
    return findings


def _load_fix_cards(cards_dir: Path) -> list:
    """Every mode: FIX card in cards_dir (non-recursive *.yaml), as (data, path). Used by the wall."""
    out = []
    for card_path in sorted(cards_dir.glob("*.yaml")):
        data, err = load_yaml(str(card_path))
        if err or not isinstance(data, dict):
            continue
        if str(data.get("mode", "")) == "FIX":
            out.append((data, card_path))
    return out


def compute_structure_findings(repo_root: str, cards_dir: Path) -> tuple[list, str | None]:
    """Aggregate Layer-1 structural-drift findings across every mode: FIX card in the live deck. Reused
    by cx_module_acceptance so a module cannot be accepted while a fix card's structure lock is drifted
    or forged (mirrors how the Andon wall already re-runs the BF-PROP-007 drift Layer-1 validator). Returns
    (findings, fatal_error); a fatal_error means the cards-dir could not be read — fail closed."""
    if not cards_dir.is_dir():
        return [], f"structure cards-dir '{cards_dir}' is not a directory"
    findings = []
    # An unreadable/malformed card is SURFACED (P2), never silently skipped (xfam built-code review #8):
    # _load_fix_cards drops a YAML-error / non-mapping card, which could hide a mode: FIX structure
    # obligation from the aggregate. Cheap belt-and-suspenders to the per-card `cx check card` (which also
    # rejects it). P2 = advisory but visible; the per-card build-turn rail remains the hard gate.
    for card_path in sorted(cards_dir.glob("*.yaml")):
        data, derr = load_yaml(str(card_path))
        if derr or not isinstance(data, dict):
            findings.append(("P2", f"structure cards-dir card '{card_path.name}'",
                f"could not parse as a YAML mapping ({derr or 'not a mapping'}) — a malformed card cannot "
                "be checked for a structure obligation; fix or remove it (fail closed, F-PROP-001 Lever A)"))
    for card, path in _load_fix_cards(cards_dir):
        findings.extend(validate_structure_lock(card, repo_root, f"fix card '{card.get('id', path.name)}'"))
    return findings, None


def cmd_structure(args) -> int:
    card_path = getattr(args, "card", None)
    repo_root = getattr(args, "repo_root", None)
    if not card_path or not repo_root:
        print("FIX-FIRST\n  [P0] cx check structure requires <card> and --repo-root")
        return 1

    card, err = load_yaml(card_path)
    if err or not isinstance(card, dict):
        print(f"FIX-FIRST\n  [P0] {card_path} — {err or 'not a YAML mapping'}")
        return 1

    if str(card.get("mode", "")) != "FIX":
        print("PASS")
        print("  [INFO] NOT_APPLICABLE structure (non-FIX card has no preserve-the-structure obligation)")
        return 0

    findings = validate_structure_lock(card, repo_root, card_path)
    return findings_report(findings)
