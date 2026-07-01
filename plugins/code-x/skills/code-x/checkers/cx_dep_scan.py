# cmd_dep_scan: validate a dependency-scan receipt before the first build card (B-PROP-006).
#
#   cx check dep-scan <receipt> --repo-root <dir>
#
# A HARD pre-build supply-chain gate (amends P-PROP-001 PACKET-CONTENTS S1): promotes the
# soft "S1 rides existing reviews — no new gate" line to a mechanical gate. The receipt
# is a typed, auditable scan record (GPT #12) that lives OUTSIDE the frozen packet but is
# hash-bound to each lockfile (GPT #15). 0 high/critical OR a typed CEO waiver (GPT #13);
# every manifest/lockfile pair scanned (GPT #14); a stale/forged lockfile hash is rejected
# (which also catches a lockfile that drifted AFTER the scan when build-turn re-runs this
# against the live tree, GPT #11). CHECK/RECEIPT-ONLY — it never invokes a scanner.
import hashlib
from pathlib import Path

from cx_common import findings_report, load_yaml, field_present

SCAN_REQUIRED_KEYS = ("ecosystem", "command", "scanner_version", "db_timestamp",
                      "manifest", "lockfile", "lockfile_hash", "produced_at",
                      "high_count", "critical_count")
WAIVER_REQUIRED_KEYS = ("ceo_decision_ref", "advisory_ids", "package", "severity",
                        "reason", "mitigation", "expiry", "owner")
# Manifest filenames cx discovers under the repo to prove no package-manager root went
# unscanned (GPT #14). Bounded: known ecosystems only; build/vendor dirs are skipped.
MANIFEST_NAMES = {"package.json", "requirements.txt", "pyproject.toml", "go.mod",
                  "Cargo.toml", "Gemfile", "pom.xml", "composer.json"}
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv", "__pycache__"}
# Lockfiles cx discovers to prove no lockfile in a scanned root went unscanned (GPT review F4).
LOCKFILE_NAMES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock",
                  "Pipfile.lock", "go.sum", "Cargo.lock", "Gemfile.lock", "composer.lock"}


def _sha12(path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def _safe_in_repo(ref: str, repo: Path):
    """Path-safety mirroring cx_final_ready: repo-relative, no abs / .. , no symlink,
    resolves inside the repo. Returns (path|None, reason|None)."""
    if not ref:
        return None, "is empty"
    p = Path(ref)
    if p.is_absolute() or ".." in p.parts:
        return None, "must be a repo-relative path (no absolute path / .. escape)"
    full = repo / ref
    if full.is_symlink() or not full.resolve().is_relative_to(repo.resolve()):
        return None, "escapes the repo (symlink or path traversal)"
    return full, None


def _discover(repo: Path, names: set) -> list[str]:
    """Repo-relative paths of every file whose name is in `names`, skipping vendored /
    build dirs. Symlinks are ignored (self-contained scan)."""
    out = []
    for p in repo.rglob("*"):
        rel = p.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_symlink() or not p.is_file():
            continue
        if p.name in names:
            out.append(str(rel))
    return sorted(out)


def discover_manifests(repo: Path) -> list[str]:
    return _discover(repo, MANIFEST_NAMES)


def cmd_dep_scan(args) -> int:
    receipt_path = args.receipt
    repo = Path(args.repo_root)
    loc = receipt_path
    findings = []

    doc, err = load_yaml(receipt_path)
    if err or not isinstance(doc, dict):
        print(f"FIX-FIRST\n  [P0] {receipt_path} — {err or 'not a YAML mapping'}")
        return 1

    blk = doc.get("dependency_scan")
    if not isinstance(blk, dict):
        findings.append(("P0", loc,
            "dependency_scan block missing — the pre-build supply-chain gate needs a typed "
            "scan receipt {scans: [...], waivers: [...]} (B-PROP-006)"))
        return findings_report(findings)

    scans = blk.get("scans")
    if not isinstance(scans, list) or not scans:
        findings.append(("P0", loc,
            "dependency_scan.scans must be a non-empty list — at least one ecosystem must be "
            "scanned before build authorization; an empty scan set is not a clean scan (B-PROP-006)"))
        scans = []

    # typed waivers (GPT #13)
    waivers = blk.get("waivers") or []
    if not isinstance(waivers, list):
        findings.append(("P2", loc, "dependency_scan.waivers must be a list (may be empty)"))
        waivers = []
    waiver_pkgs, waiver_advs = set(), set()   # for per-advisory coverage (GPT review F3)
    for i, w in enumerate(waivers):
        if not isinstance(w, dict):
            findings.append(("P2", loc, f"dependency_scan.waivers[{i}] is not a mapping"))
            continue
        missing = [k for k in WAIVER_REQUIRED_KEYS if not field_present(w, k)]
        if missing:
            findings.append(("P2", loc,
                f"dependency_scan.waivers[{i}] missing {missing} — a supply-chain waiver must record "
                "the CEO decision ref, advisory ids, package, severity, reason, mitigation, expiry "
                "and owner (auditable + time-boxed) (B-PROP-006)"))
        waiver_pkgs.add(str(w.get("package", "")))
        for a in (w.get("advisory_ids") or []):
            waiver_advs.add(str(a))

    declared_manifests, scanned_lockfiles = set(), set()
    for i, s in enumerate(scans):
        if not isinstance(s, dict):
            findings.append(("P1", loc, f"dependency_scan.scans[{i}] is not a mapping"))
            continue
        missing = [k for k in SCAN_REQUIRED_KEYS if not field_present(s, k)]
        if missing:
            findings.append(("P1", loc,
                f"dependency_scan.scans[{i}] missing {missing} — a scan record must pin ecosystem, "
                "command, scanner version, advisory-db timestamp, manifest + lockfile, lockfile hash, "
                "produced_at and high/critical counts (auditable, non-forgeable) (B-PROP-006)"))
            continue
        if field_present(s, "manifest"):
            declared_manifests.add(str(Path(str(s.get("manifest")))))
        try:
            high = int(s.get("high_count"))
            crit = int(s.get("critical_count"))
        except (TypeError, ValueError):
            findings.append(("P1", loc,
                f"dependency_scan.scans[{i}] high_count / critical_count must be integers"))
            continue

        # lockfile path-safety + freshness (also catches a post-G7 lockfile drift, GPT #11)
        lf_ref = str(s.get("lockfile"))
        lf_path, reason = _safe_in_repo(lf_ref, repo)
        if lf_path is None:
            findings.append(("P0", loc,
                f"dependency_scan.scans[{i}].lockfile '{lf_ref}' {reason} (B-PROP-006)"))
        elif not lf_path.is_file():
            findings.append(("P0", loc,
                f"dependency_scan.scans[{i}] lockfile '{lf_ref}' does not exist under the repo — a "
                "scanned ecosystem must have a pinned lockfile committed (B-PROP-006 / GPT #14)"))
        else:
            scanned_lockfiles.add(str(Path(lf_ref)))
            actual = _sha12(str(lf_path))
            if actual != str(s.get("lockfile_hash")):
                findings.append(("P0", loc,
                    f"dependency_scan.scans[{i}].lockfile_hash {s.get('lockfile_hash')} != the "
                    f"lockfile's sha12 {actual} — the scan is not bound to THIS lockfile (stale / "
                    "forged, or the lockfile changed after the scan) (B-PROP-006 / GPT #11,#12)"))

        # 0 high/critical is the bar; anything above must ENUMERATE each advisory and cover EACH with a
        # typed CEO waiver — a single blanket waiver may NOT hide an unrelated advisory (GPT review F3).
        if high + crit > 0:
            advs = s.get("high_critical_advisories")
            if not isinstance(advs, list) or len(advs) != high + crit:
                findings.append(("P1", loc,
                    f"dependency_scan.scans[{i}] reports {high} high / {crit} critical advisories but "
                    "high_critical_advisories does not name exactly that many — each high/critical "
                    "advisory must be named to be matched to a typed CEO waiver (0 high/critical is the "
                    "bar) (B-PROP-006 / GPT F3)"))
            else:
                uncovered = [a for a in advs if str(a) not in waiver_advs
                             and str(s.get("package", "")) not in waiver_pkgs]
                if uncovered:
                    findings.append(("P1", loc,
                        f"dependency_scan.scans[{i}] advisories {uncovered} need a typed CEO waiver — a "
                        "blanket waiver may not hide an unrelated advisory; each high/critical must be "
                        "individually covered (CEO-DECISION-LEDGER ref) (B-PROP-006 / GPT F3)"))

    # scan-all-pairs (GPT #14 + F4): every manifest AND every lockfile discovered under the repo must
    # be covered by a scan entry — a second lockfile in a scanned root cannot go unscanned.
    for mf in discover_manifests(repo):
        if mf not in declared_manifests:
            findings.append(("P1", loc,
                f"manifest '{mf}' found under the repo is not covered by any dependency_scan.scans "
                "entry — every package-manager root must be scanned before build (B-PROP-006 / GPT #14)"))
    for lf in _discover(repo, LOCKFILE_NAMES):
        if lf not in scanned_lockfiles:
            findings.append(("P1", loc,
                f"lockfile '{lf}' found under the repo is not covered by any dependency_scan.scans "
                "entry — every lockfile must be scanned (a 2nd lockfile cannot go unscanned) "
                "(B-PROP-006 / GPT F4)"))

    return findings_report(findings)
