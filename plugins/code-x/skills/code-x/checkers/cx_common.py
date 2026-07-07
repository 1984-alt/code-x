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
PROTOCOL_VERSION = "1.22.6"          # v1.22.6 (CEO-D-051) PBF-PROP-021 audit hole-closing + PBF-PROP-022 gate ROI slimming (fold 2026-07-07; lock-onto-main pending CEO "lock"). Prior: v1.22.5 (CEO-D-050) BUNDLE, 5 folds: PBF-PROP-015 (cx_state arity) · PBF-PROP-020 (mockup-first) · PBF-PROP-019 (risk tiers) · PB-PROP-003 (G/W/T wiring) · B-PROP-013 (forge-parity acceptance recompute). Prior: v1.22.4 (CEO-D-042) PBF-PROP-017 one-line installer (patch). Prior: v1.22.3 (CEO-D-041) PBF-PROP-018 accepted-surface preserve posture; v1.22.2 (CEO-D-040) P-PROP-007 blueprint visual parity; v1.22.1 (CEO-D-039) PBF-PROP-016 public CI runs the full eval gate; v1.22 (CEO-D-038) A-PROP-001 Audit Stage + PBAF-PROP-001 SOP asset bind; v1.21.4 (CEO-D-037) canon-hygiene; v1.21.3 (CEO-D-036) EVAL-041; v1.21.2 (CEO-D-035) EVAL-040; v1.21.1 (CEO-D-034) CSFIX; v1.21 (CEO-D-033) PROP-042/043/044.
READ_BUDGET_TOKENS = 4000   # kernel cap: allowed_files token budget per card
CARD_TOKEN_BUDGET = 1800    # max card size in tokens (per spec)
VALID_MODEL_TIERS = {"cheap", "standard", "top"}
VALID_MODES = {"MODE_A_UI", "MODULE_BUILD", "REVIEW", "FIX", "FINAL_READY", "PROOF"}
VALID_RESULTS = {"PASS", "FIX_FIRST", "STOP"}
VALID_REVIEW_MODES = {"NONE", "SCAN", "DELTA", "SLICE", "FULL"}
VALID_WASTE_FLAGS = {"over_read", "repeated_review", "loop", "wrong_model_tier",
                     "unclear_card", "missing_evidence"}

# PBF-PROP-019: per-project risk tier (LITE/STANDARD/STRICT), declared in the frozen
# packet's requirements-manifest.yaml (top-level `risk_tier` field).
VALID_RISK_TIERS = {"LITE", "STANDARD", "STRICT"}
_RISK_TIER_MANIFEST_FILE = "requirements-manifest.yaml"

# --- BUILD-ENGINE-PROFILES enforcement (PBF-PROP-008) -------------------------
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
    green-but-not-enforcing class (P-PROP-001 fold, GPT P1-02 — fail LOUD, not silent).
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


class _DuplicateKeyRejectingLoader(yaml.SafeLoader):
    """yaml.SafeLoader subclass that FAILS on a repeated mapping key instead of the
    stdlib default (silent last-key-wins). X5 (v1.22 xfam fix): safe_load's silent
    overwrite is a data-loss / spoofing risk on money/audit/state inputs — a second
    'disposition:' or 'verdict:' key later in the same mapping would silently replace
    the first with no trace. This is the SHARED loader every checker inherits via
    load_yaml() below, so audit/state/packet/deck/card inputs all get the protection
    from one place (never a per-checker copy)."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            try:
                hashable_key = key
                if hashable_key in seen:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        f"found duplicate key: {key!r}", key_node.start_mark)
                seen.add(hashable_key)
            except TypeError:
                pass  # unhashable key (rare) — let the base class's own error surface
        return super().construct_mapping(node, deep=deep)


def load_yaml(path: str) -> tuple[dict | list | None, str | None]:
    """Load YAML. Returns (data, error_string). Uses the duplicate-key-rejecting
    loader (X5) — a repeated mapping key is a parse ERROR, never silent last-key-wins."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.load(f, Loader=_DuplicateKeyRejectingLoader)
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


def safe_repo_ref(ref: str, root) -> tuple[Path | None, str | None]:
    """Path-safety for a model/state-authored ref a checker reads as `root / ref`.

    The SHARED guard the build-turn rail applies to every artifact ref it reads
    (dep-scan receipt · render bundle · verify_app receipt · CodeRabbit receipt +
    its egress receipt). It mirrors the canonical acceptance_ref guard in
    cx_module_acceptance.validate_accepted_module — the Andon-wall path-safety the
    v1.10 R4/R11 folds landed (B-PROP-011 factors it into one place so every
    build-turn read carries the FULL class, not just the absolute/'..' half).

    Returns (resolved_path, None) for a SAFE ref, or (None, reason) when the ref is
    absolute, contains a '..' segment, is a symlink (final component), or resolves
    OUTSIDE `root` — any of which lets the rail read arbitrary EXTERNAL bytes as an
    in-repo artifact. `reason` is a message suffix the caller appends after its own
    '<field> <ref>' label, so each step keeps its own finding location while sharing
    one security check. Substrings 'repo-relative path' and 'symlink or resolves
    OUTSIDE the repo' are load-bearing (contract clauses assert on them)."""
    p = Path(ref)
    if p.is_absolute() or ".." in p.parts:
        return None, ("must be a repo-relative path (no absolute path / '..' escape) — the rail "
                      "reads only artifacts committed inside the repo")
    rp = Path(root) / ref
    if rp.is_symlink() or not rp.resolve().is_relative_to(Path(root).resolve()):
        return None, ("is a symlink or resolves OUTSIDE the repo — the rail must not read arbitrary "
                      "external bytes as an in-repo artifact (path-safety, mirrors the Andon wall's "
                      "acceptance_ref guard)")
    return rp, None


def resolve_risk_tier(packet_dir) -> str:
    """PBF-PROP-019: fail-closed per-project risk-tier resolution (design v2 §1).

    Reads the frozen packet's `requirements-manifest.yaml` top-level `risk_tier`
    field (mirrors how `cx_packet._style_block_values` extracts `locked_style_direction`
    from the taste lock — same mirror-the-precedent pattern, different file).

    - field ABSENT (missing file, unreadable YAML, or no `risk_tier` key) -> "STRICT"
      (no error; this is the safety default, never a silent LITE).
    - field present and one of LITE/STANDARD/STRICT (case-insensitive) -> that value,
      normalised to uppercase.
    - ANY other/invalid value -> "STRICT" (the loud P0 rejection of a malformed
      declaration is `cx_packet`'s `PACKET-RISK-TIER-WELL-FORMED` validator's job,
      not this resolver's — this helper only ever needs to answer "what ceremony
      applies right now", so it never raises).
    """
    manifest_path = Path(packet_dir) / _RISK_TIER_MANIFEST_FILE
    data, err = load_yaml(str(manifest_path))
    if err or not isinstance(data, dict):
        return "STRICT"
    raw = data.get("risk_tier")
    if raw is None:
        return "STRICT"
    val = str(raw).strip().upper()
    return val if val in VALID_RISK_TIERS else "STRICT"


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
