# Shared constants, helpers, YAML loading, findings output, exit-code logic for cx checkers.
import hashlib
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FATAL: PyYAML not installed. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = "1.12"    # Code-X V1 protocol version (V1.12 = Plain Talk + Built-App Audit fold)
READ_BUDGET_TOKENS = 4000   # kernel cap: allowed_files token budget per card
CARD_TOKEN_BUDGET = 1800    # max card size in tokens (per spec)
VALID_MODEL_TIERS = {"cheap", "standard", "top"}
VALID_MODES = {"MODE_A_UI", "MODULE_BUILD", "REVIEW", "FIX", "FINAL_READY", "PROOF"}
VALID_RESULTS = {"PASS", "FIX_FIRST", "STOP"}
VALID_REVIEW_MODES = {"NONE", "SCAN", "DELTA", "SLICE", "FULL"}
VALID_WASTE_FLAGS = {"over_read", "repeated_review", "loop", "wrong_model_tier",
                     "unclear_card", "missing_evidence"}

# --- BUILD-ENGINE-PROFILES enforcement (PROP-013) -------------------------
# Canonical profiles file lives at Code-X-V1 root (one level up from checkers/).
DEFAULT_PROFILES_PATH = Path(__file__).resolve().parent.parent / "BUILD-ENGINE-PROFILES.yaml"

VALID_BUILD_ENGINES = {"CLAUDE_CODE", "CODEX_APP"}
ENGINE_BRANCH_KEYS = {"CLAUDE_CODE": "claude_code", "CODEX_APP": "codex_app"}

# code_writing_floor: mini/spark/haiku-class models NEVER write app code (family-neutral).
MECHANICAL_CLASS_MARKERS = ("haiku", "spark", "mini", "nano")

# Effort ordering for "exceeds the seat" comparisons. standard ~ medium.
EFFORT_RANK = {"low": 1, "medium": 2, "standard": 2, "high": 3, "xhigh": 4, "max": 4}
# efforts that demand a top_allowed_reason when present on a card (per cx clause 6)
TOP_EFFORTS = {"high", "xhigh", "max"}

# Model ladders per family (rank within family; longest alias matched first when parsing).
CLAUDE_MODEL_RANK = {"haiku": 1, "sonnet": 2, "opus": 3, "fable": 4}
GPT_MODEL_RANK = {"gpt-5.3-codex-spark": 1, "gpt-5.4": 2, "gpt-5.5": 3, "gpt-5.5-pro": 4}


def resolve_profiles_path(args) -> tuple[str, str | None]:
    """Profiles file: --profiles flag > CX_PROFILES env (TEST-ONLY) > canonical default.
    CX_PROFILES is honored ONLY when CODE_X_TEST_MODE=1 — production reads live canon.
    A stale env var silently redirecting validation to an old profiles file is the
    green-but-not-enforcing class (PROP-014 fold, GPT P1-02 — fail LOUD, not silent).
    Returns (path, error): error is a P1 finding message when the env is set outside
    test mode; callers must emit it and skip profile checks (the path is untrusted)."""
    flag = getattr(args, "profiles", None)
    if flag:
        return str(flag), None
    env = os.environ.get("CX_PROFILES")
    if env:
        if os.environ.get("CODE_X_TEST_MODE") == "1":
            return env, None
        return env, ("CX_PROFILES is set but CODE_X_TEST_MODE != 1 — refusing to validate "
                     "against a redirected profiles file in production; unset CX_PROFILES "
                     "or pass --profiles explicitly")
    return str(DEFAULT_PROFILES_PATH), None


def profiles_sha12(path: str) -> str | None:
    """sha256-12 stamp of the profiles file (None if unreadable)."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return None


def parse_model_effort(text: str) -> tuple[str | None, str | None]:
    """Parse a free-form 'alias + effort as launched' string (e.g. 'opus max',
    'codex / gpt-5.5 medium'). Returns (model_alias, effort) — either may be None."""
    low = str(text or "").lower()
    model = None
    for alias in sorted(list(CLAUDE_MODEL_RANK) + list(GPT_MODEL_RANK), key=len, reverse=True):
        if alias in low:
            model = alias
            break
    effort = None
    for tok in re.split(r"[\s/,()]+", low):
        if tok in EFFORT_RANK:
            effort = tok
            break
    return model, effort

# Faked-pass patterns (ported from code-x-honesty-check.sh)
FAKED_PASS_PATTERNS = [
    re.compile(r'exit\s+0\s*#\s*(fake|cheat|force)', re.I),
    re.compile(r'echo\s+"PASS"', re.I),
    re.compile(r'# FORCE.*PASS', re.I),
    re.compile(r'return\s+True\s*#\s*(fake|always|force)', re.I),
    re.compile(r'assert\s+True\b'),                   # trivial assertion
    re.compile(r'sys\.exit\(0\)\s*#\s*(skip|bypass|fake)', re.I),
    re.compile(r'pytest\.skip\(', re.I),
    re.compile(r'\|\s*0\s*\|\s*(ignore|skip)', re.I),  # score table suppression
]

# Secret patterns (ported from code-x-secrets-scan.py)
SECRET_PATTERNS = [
    re.compile(r'(?i)(password|passwd|secret|api[_-]?key|token|private[_-]?key)\s*=\s*["\'][^"\']{4,}["\']'),
    re.compile(r'(?i)bearer\s+[A-Za-z0-9\-_]{20,}'),
    re.compile(r'(?i)-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'(?i)(aws_access_key_id|aws_secret)\s*=\s*["\']?[A-Z0-9/+]{16,}'),
    re.compile(r'(?i)AIza[0-9A-Za-z\-_]{35}'),   # Google API key
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def findings_report(findings: list[tuple[str, str, str]]) -> int:
    """Print findings and return exit code. findings = [(sev, loc, msg)]."""
    if not findings:
        print("PASS")
        return 0
    print("FIX-FIRST")
    for sev, loc, msg in findings:
        print(f"  [{sev}] {loc} — {msg}")
    return 1


def load_yaml(path: str) -> tuple[dict | list | None, str | None]:
    """Load YAML. Returns (data, error_string)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data, None
    except FileNotFoundError:
        return None, f"file not found: {path}"
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"


def rough_token_count(text: str) -> int:
    """Rough token count: ~4 chars per token."""
    return max(1, len(text) // 4)


def field_present(d: dict, key: str) -> bool:
    """True if key exists in dict and value is not None/empty string."""
    return key in d and d[key] is not None and d[key] != ""


def nested_get(d: dict, *keys, default=None):
    """Safe nested dict access."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def scan_secrets(content: str) -> list[str]:
    """Return list of secret pattern names found (not their values)."""
    hits = []
    for pat in SECRET_PATTERNS:
        m = pat.search(content)
        if m:
            # Report only the pattern name, not the value
            hits.append(f"secret-pattern:{pat.pattern[:40]}...")
    return hits


def scan_faked_pass(content: str) -> list[str]:
    """Return list of faked-pass pattern descriptions found."""
    hits = []
    for pat in FAKED_PASS_PATTERNS:
        m = pat.search(content)
        if m:
            hits.append(f"faked-pass-pattern:{m.group(0)[:60]}")
    return hits
