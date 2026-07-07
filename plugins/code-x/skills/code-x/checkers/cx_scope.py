# cmd_scope: checks a diff against a card's allowed/forbidden files and security_tripwire.
import re
import fnmatch
from pathlib import Path

from cx_common import findings_report, load_yaml, scan_secrets


def cmd_scope(args) -> int:
    """Check a diff or file-list against a card's allowed/forbidden files + security_tripwire."""
    card_path = args.card
    diff_path = args.diff

    # Load card
    card, err = load_yaml(card_path)
    if err:
        print(f"FIX-FIRST\n  [P0] {card_path} — {err}")
        return 1

    findings = []

    allowed_files = card.get("allowed_files") or []
    forbidden_files = card.get("forbidden_files") or []
    st = card.get("security_tripwire", {}) or {}

    # Parse touched files from diff or file list
    touched = _parse_touched_files(diff_path)
    if touched is None:
        print(f"FIX-FIRST\n  [P0] {diff_path} — could not read diff/file-list")
        return 1

    loc = diff_path

    # Check forbidden files
    for f in touched:
        for fb in forbidden_files:
            if _file_matches(f, fb):
                findings.append(("P0", loc, f"diff touches forbidden_file: {f}"))

    # Check allowed files: empty allowed_files + real diff = FAIL unless REVIEW mode (P1-04)
    card_mode = card.get("mode", "")
    if not allowed_files and touched and card_mode != "REVIEW":
        findings.append(("P1", loc,
            "allowed_files is empty but diff has real changes — "
            "empty allowed_files with a non-empty diff FAILS (mode is not REVIEW)"))
    elif allowed_files:
        for f in touched:
            if not any(_file_matches(f, af) for af in allowed_files):
                findings.append(("P1", loc,
                    f"diff touches '{f}' which is not in allowed_files — out of card scope"))

    # Security tripwire: ALL 7 fields verified against diff (P1-03)
    # field_name → (list of regex patterns for file paths that trigger it)
    TRIPWIRE_CHECKS = [
        ("touches_auth",
         [r'auth', r'login', r'session', r'jwt', r'token', r'rls', r'permit']),
        ("touches_secrets",
         [r'\.env', r'secret', r'credential', r'keychain', r'\.pem', r'\.key']),
        ("touches_money_or_balances",
         [r'payment', r'balance', r'invoice', r'charge', r'bill', r'cost_log', r'wallet', r'ledger']),
        ("touches_bank_or_pii",
         [r'pii', r'personal', r'bank', r'iban', r'routing', r'ssn', r'passport', r'nric']),
        ("touches_upload_restore_import",
         [r'upload', r'restore', r'import', r'ingest', r'seed', r'migration', r'fixture']),
        ("touches_network_or_public_surface",
         [r'api', r'http', r'webhook', r'endpoint', r'route', r'url', r'socket', r'cors', r'nginx']),
        ("touches_logs_or_error_output",
         [r'log', r'logger', r'logging', r'error_handler', r'sentry', r'traceback', r'stacktrace']),
    ]

    def any_match(files, patterns):
        for f in files:
            for p in patterns:
                if re.search(p, f, re.I):
                    return True
        return False

    TRIPWIRE_SEVERITY = {
        "touches_secrets": "P0",
    }
    def tripwire_is_no(val) -> bool:
        """True if the tripwire field value means 'no' — handles bool False or string 'no'."""
        if val is None:
            return True  # absent = default no
        if isinstance(val, bool):
            return not val
        return str(val).lower() in ("no", "false", "0", "")

    for field_name, patterns in TRIPWIRE_CHECKS:
        if tripwire_is_no(st.get(field_name)) and any_match(touched, patterns):
            sev = TRIPWIRE_SEVERITY.get(field_name, "P1")
            findings.append((sev, loc,
                f"security_tripwire.{field_name}=no but diff touches matching files — verify tripwire"))

    # Scan diff content for actual secret values
    try:
        diff_content = Path(diff_path).read_text(encoding="utf-8", errors="replace")
        hits = scan_secrets(diff_content)
        for h in hits:
            findings.append(("P0", loc, f"diff contains secret pattern — refer by name only: {h}"))
    except Exception:
        pass

    return findings_report(findings)


def _parse_touched_files(path: str) -> list[str] | None:
    """Parse a unified diff or plain file list. Returns list of file paths."""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None

    files = set()
    # Unified diff: look for +++ and --- lines
    for line in content.splitlines():
        m = re.match(r'^(?:\+\+\+|---)\s+(?:a/|b/)?(.+?)(?:\s+\d{4}-\d{2}-\d{2}.*)?$', line)
        if m:
            f = m.group(1).strip()
            if f and f != "/dev/null":
                files.add(f)
            continue
        # git rename/copy headers: 'rename from <path>' / 'rename to <path>' (also 'copy
        # from'/'copy to'). A pure rename/copy (similarity 100%, no content hunk) emits ONLY
        # these header lines — no +++/--- pair — so a forbidden file that was MOVED (not
        # edited) was previously invisible to this parser even in a diff that also carries a
        # real +++/--- hunk elsewhere. Both the old and new path are recorded: the old path
        # lets forbidden_files catch a forbidden file renamed away; the new path lets
        # allowed_files catch it landing somewhere out of scope.
        m2 = re.match(r'^(?:rename|copy) (?:from|to) (.+)$', line)
        if m2:
            f = m2.group(1).strip()
            if f:
                files.add(f)
    if files:
        return sorted(files)

    # Plain file list (one path per line)
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith("#")]
    if lines:
        return lines

    return []


def _file_matches(filepath: str, pattern: str) -> bool:
    """Glob-style match using fnmatch. Treats trailing /** as directory-prefix recursion.
    P1-04: NOT substring — real glob semantics.
    """
    if filepath == pattern:
        return True
    # Directory prefix: 'dir/**' matches any file under dir/
    if pattern.endswith("/**"):
        prefix = pattern[:-3]  # strip /**
        if filepath.startswith(prefix + "/") or filepath == prefix:
            return True
    # Directory without /** trailing: treat 'dir/' as 'dir/**'
    if pattern.endswith("/"):
        prefix = pattern[:-1]
        if filepath.startswith(prefix + "/") or filepath == prefix:
            return True
    # Standard fnmatch
    if fnmatch.fnmatch(filepath, pattern):
        return True
    # fnmatch on basename for simple *.ext patterns
    basename = filepath.rsplit("/", 1)[-1]
    if fnmatch.fnmatch(basename, pattern):
        return True
    return False
