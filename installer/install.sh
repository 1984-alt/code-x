#!/usr/bin/env bash
# Code-X one-line installer (PBF-PROP-017).
#
# What this does, in plain English:
#   1. Checks your machine has what Code-X needs (Python, git, the Claude CLI).
#   2. Installs the Code-X plugin and the "superpowers" plugin it builds on,
#      pulling BOTH straight from their own official GitHub repos — pinned to
#      exact, checked coordinates in installer-manifest.yaml (never a guess).
#   3. Tells you about CodeRabbit (an optional third-party code-review tool) —
#      it does NOT install it for you; that is your own account, your choice.
#   4. Prints a pass/fail table so you can see exactly what worked.
#
# Safe to re-run: if something is already installed correctly, this script
# leaves it alone. If something is only half-installed, it finishes the job.
#
# If ANY dependency can't be verified against its pinned coordinate, this
# script STOPS (fails closed) rather than silently installing something
# unverified.

# Deliberately NOT `set -u`: macOS ships bash 3.2 (last GPLv2 release), which
# has a known bug where `${#EMPTY_ARRAY[@]}` throws "unbound variable" under
# nounset even though the array is legitimately declared-but-empty. Since
# macOS/bash-3.2 is this installer's primary target, every variable below is
# given an explicit default instead of relying on nounset to catch typos.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# ---- embedded trust root (xfam P1 ONE_LINE_COMMAND_NONFUNCTIONAL, 2026-07-03) --
# `curl .../install.sh | bash` downloads ONLY this file — no adjacent manifest.
# These two values make install.sh self-sufficient: when no local manifest is
# found beside the script, it fetches installer-manifest.yaml from this exact
# pinned release tag and verifies it against this exact pinned checksum before
# trusting a single byte of it. Re-stamped together by
# installer/restamp-release.sh at every release cut — never edit by hand.
INSTALLER_RELEASE_TAG="v1.22.4"
INSTALLER_MANIFEST_SHA256="3f870d0b42e8f0fafddb9e68508993380119bb824dda6b73d8b721fe97a0fb98"
DEFAULT_REMOTE_BASE="https://raw.githubusercontent.com/1984-alt/code-x"
# Test-only override (offline fixtures point this at a file:// tree); never
# set this yourself for a real install.
REMOTE_BASE="${CODE_X_INSTALLER_REMOTE_BASE:-$DEFAULT_REMOTE_BASE}"

# Pinned+hashed PyYAML coordinate for the manual-install hint printed below
# (xfam P0 UNPINNED_PIP_FETCH, 2026-07-03). PyYAML has no transitive deps, so
# a single package+hash pin is sufficient. Sourced from pypi.org/pypi/PyYAML —
# update both together if the pin ever moves.
PYYAML_PIN="pyyaml==6.0.3"
PYYAML_SHA256="d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"

# ---- tiny output helpers (plain English, no jargon dump) -------------------
PASS_ROWS=()
FAIL_ROWS=()
WARN_ROWS=()

note()  { printf '%s\n' "$*"; }
ok()    { PASS_ROWS+=("$1"); printf '  [ok]   %s\n' "$1"; }
bad()   { FAIL_ROWS+=("$1"); printf '  [FAIL] %s\n' "$1"; }
warn()  { WARN_ROWS+=("$1"); printf '  [warn] %s\n' "$1"; }

fail_closed() {
  # $1 = short reason, $2 = plain-English fix hint
  bad "$1"
  printf '\nSTOPPED: %s\n' "$1"
  printf 'Why this matters: this installer only proceeds when it can verify\n'
  printf 'exactly what it is fetching. It would rather stop than install\n'
  printf 'something unverified onto your machine.\n'
  printf 'What to try: %s\n' "$2"
  exit 1
}

shasum_file() {
  # $1 = path. Prefers sha256sum (Linux), falls back to shasum -a 256 (macOS).
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    printf ''
  fi
}

# ---- manifest resolution: local file first, pinned-release fetch as fallback -
# This is the single trust root install.sh relies on. Local-file mode (manifest
# copied beside the script) is what dev/tests use. The pipe-to-bash path with no
# local manifest falls back to fetching it from the pinned release tag and
# checking it against the embedded checksum above before using it.
MANIFEST="${SCRIPT_DIR}/installer-manifest.yaml"
if [ ! -f "$MANIFEST" ]; then
  if [ "$INSTALLER_MANIFEST_SHA256" = "__PENDING_RESTAMP__" ]; then
    fail_closed "install.sh's embedded manifest checksum has not been stamped for a release yet" \
      "this is a dev/pre-release copy of install.sh — download the whole installer/ folder instead of just install.sh, or run installer/restamp-release.sh first"
  fi
  if ! command -v curl >/dev/null 2>&1; then
    fail_closed "installer-manifest.yaml not found next to install.sh, and curl is unavailable to fetch it" \
      "download the whole installer/ folder instead of just install.sh"
  fi
  TMP_MANIFEST="$(mktemp -t code-x-manifest.XXXXXX 2>/dev/null || mktemp)"
  trap 'rm -f "$TMP_MANIFEST"' EXIT
  REMOTE_MANIFEST_URL="${REMOTE_BASE}/${INSTALLER_RELEASE_TAG}/installer/installer-manifest.yaml"
  if ! curl -fsSL "$REMOTE_MANIFEST_URL" -o "$TMP_MANIFEST" 2>/dev/null; then
    fail_closed "could not fetch installer-manifest.yaml from the pinned release ($REMOTE_MANIFEST_URL)" \
      "check your internet connection, or download the whole installer/ folder instead of just install.sh"
  fi
  FETCHED_SHA256="$(shasum_file "$TMP_MANIFEST")"
  if [ -z "$FETCHED_SHA256" ] || [ "$FETCHED_SHA256" != "$INSTALLER_MANIFEST_SHA256" ]; then
    fail_closed "fetched installer-manifest.yaml does not match the pinned checksum (expected ${INSTALLER_MANIFEST_SHA256:0:12}\xe2\x80\xa6, got ${FETCHED_SHA256:0:12}\xe2\x80\xa6)" \
      "the release asset may be corrupted or tampered with \xe2\x80\x94 do not proceed; report this"
  fi
  MANIFEST="$TMP_MANIFEST"
  ok "fetched + verified installer-manifest.yaml from pinned release $INSTALLER_RELEASE_TAG"
fi

# ---- tiny YAML field reader (no PyYAML dependency for the shell layer) -----
# The manifest is a flat, hand-authored YAML file. We only need scalar leaf
# values under known keys, so a narrow indented-block reader is enough —
# pulling in a YAML parser just for this would violate the do-less ladder.
yaml_get() {
  # $1 = block header (e.g. "  superpowers:"), $2 = field name (e.g. "commit_sha")
  awk -v block="$1" -v field="$2" '
    $0 == block { inblock=1; next }
    inblock && /^  [a-zA-Z]/ && $0 != block { inblock=0 }
    inblock && $0 ~ "^    "field":" {
      sub("^    "field":[ ]*", "");
      gsub(/^"|"$/, "");
      print; exit
    }
  ' "$MANIFEST"
}

CX_COMMIT="$(yaml_get "  code-x:" commit_sha)"
CX_RELEASE_TAG="$(yaml_get "  code-x:" release_tag)"
CX_MARKETPLACE="$(yaml_get "  code-x:" marketplace_add_source)"
SP_COMMIT="$(yaml_get "  superpowers:" commit_sha)"
SP_MARKETPLACE="$(yaml_get "  superpowers:" marketplace_add_source)"
CR_INSTALL_URL="$(yaml_get "  coderabbit:" install_url)"
PY_MIN_VERSION="$(yaml_get "  python3:" min_version)"
PY_FALLBACK="$(yaml_get "  python3:" macos_fallback_path)"

for pair in "code-x:$CX_COMMIT" "code-x-marketplace:$CX_MARKETPLACE" \
            "superpowers:$SP_COMMIT" "superpowers-marketplace:$SP_MARKETPLACE"; do
  key="${pair%%:*}"; val="${pair#*:}"
  if [ -z "$val" ]; then
    fail_closed "manifest is missing a pinned value for $key" \
      "the manifest is corrupted or edited — re-download installer-manifest.yaml"
  fi
  case "$val" in
    PIN-ME-AT-RELEASE*)
      fail_closed "manifest pin for $key is a placeholder (PIN-ME-AT-RELEASE), not a real coordinate" \
        "the maintainer needs to fill in the real release/commit before this installer can run"
      ;;
  esac
done

note "Code-X installer — checking your machine first"
note "======================================================"

# ---- Step 1: preflight -------------------------------------------------
PYTHON_BIN=""
for candidate in python3 "$PY_FALLBACK"; do
  [ -z "$candidate" ] && continue
  if command -v "$candidate" >/dev/null 2>&1; then
    ver="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
    if [ -n "$ver" ]; then
      major="${ver%%.*}"; minor="${ver##*.}"
      req_major="${PY_MIN_VERSION%%.*}"; req_minor="${PY_MIN_VERSION##*.}"
      if [ "$major" -gt "$req_major" ] || { [ "$major" -eq "$req_major" ] && [ "$minor" -ge "$req_minor" ]; }; then
        PYTHON_BIN="$candidate"; break
      fi
    fi
  fi
done
if [ -n "$PYTHON_BIN" ]; then
  ok "python3 >= ${PY_MIN_VERSION} found ($PYTHON_BIN)"
else
  bad "python3 >= ${PY_MIN_VERSION} not found"
  note "  Fix: install Python 3.10 or newer from https://www.python.org/downloads/"
  note "       (on a Mac with Homebrew: brew install python3)"
fi

if [ -n "$PYTHON_BIN" ]; then
  if "$PYTHON_BIN" -c 'import yaml' >/dev/null 2>&1; then
    ok "PyYAML installed"
  else
    # xfam P0 UNPINNED_PIP_FETCH (2026-07-03): this installer NEVER auto-runs a
    # bare, unpinned `pip install`. It fails closed and hands you the exact
    # pinned+hashed command to run yourself, then re-run this installer
    # (idempotent — safe to re-run as many times as you need).
    bad "PyYAML missing"
    note "  Fix: this installer will not auto-fetch third-party packages without a pin+hash."
    note "       Run this exact command yourself, then re-run this installer:"
    note "         $PYTHON_BIN -m pip install --no-binary :all: --require-hashes -r <(printf '%s --hash=sha256:%s\n' \"$PYYAML_PIN\" \"$PYYAML_SHA256\")"
  fi
fi

if command -v git >/dev/null 2>&1; then
  ok "git found"
else
  bad "git not found"
  note "  Fix: install git — https://git-scm.com/downloads"
fi

if command -v claude >/dev/null 2>&1; then
  ok "claude CLI found"
  CLAUDE_OK=1
else
  bad "claude CLI not found"
  note "  Fix: install Claude Code first — https://claude.com/claude-code"
  CLAUDE_OK=0
fi

if [ "${#FAIL_ROWS[@]}" -gt 0 ] && [ "$CLAUDE_OK" -eq 0 ]; then
  fail_closed "the claude CLI is required for every remaining step" \
    "install Claude Code, then re-run this script — it is safe to re-run"
fi

# ---- helpers to drive the claude CLI plugin machinery ----------------------
marketplace_installed_location() {
  # $1 = marketplace name as configured (e.g. "code-x")
  local name="$1"
  claude plugin marketplace list --json 2>/dev/null | \
    "$PYTHON_BIN" -c "
import json,sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for m in data:
    if m.get('name') == '$name':
        print(m.get('installLocation',''))
        break
"
}

ensure_marketplace_and_plugin() {
  # $1 = human label, $2 = marketplace add source (owner/repo), $3 = marketplace name,
  # $4 = plugin id (plugin@marketplace), $5 = pinned commit sha
  local label="$1" add_source="$2" mp_name="$3" plugin_id="$4" pinned_commit="$5"
  local newly_added=0

  if ! claude plugin marketplace list --json 2>/dev/null | grep -q "\"name\": \"$mp_name\""; then
    note "Adding the $label marketplace ($add_source)..."
    if ! claude plugin marketplace add "$add_source" >/dev/null 2>&1; then
      bad "$label: could not add marketplace $add_source"
      note "  Fix: check your internet connection, or add it manually:"
      note "       claude plugin marketplace add $add_source"
      return 1
    fi
    newly_added=1
  fi

  # xfam P1 PARTIAL_UNTRUSTED_STATE_LEFT_BEHIND (2026-07-03): if we added the
  # marketplace this run and it fails ANY verification step below, remove it
  # again before failing closed — never leave a just-added, unverified
  # marketplace sitting under a trusted-looking name.
  rollback_if_newly_added() {
    [ "$newly_added" -eq 1 ] && claude plugin marketplace remove "$mp_name" >/dev/null 2>&1
  }

  local loc
  loc="$(marketplace_installed_location "$mp_name")"
  if [ -z "$loc" ]; then
    bad "$label: could not read the installed marketplace's location"
    rollback_if_newly_added
    note "  Fix: run 'claude plugin marketplace update $mp_name' and re-run this installer"
    return 1
  fi

  local resolved
  resolved="$(git -C "$loc" rev-parse HEAD 2>/dev/null)"
  if [ -z "$resolved" ]; then
    bad "$label: could not read the installed marketplace's commit"
    rollback_if_newly_added
    note "  Fix: run 'claude plugin marketplace update $mp_name' and re-run this installer"
    return 1
  fi
  if [ "$resolved" != "$pinned_commit" ]; then
    rollback_if_newly_added
    fail_closed "$label: installed commit ($resolved) does not match the pinned coordinate ($pinned_commit)" \
      "the upstream source has moved since this installer was pinned — do not proceed on an unverified checkout; tell the maintainer to re-pin installer-manifest.yaml"
  fi

  # xfam P0 COMMIT_MATCH_NOT_CONTENT_BINDING (2026-07-03): a matching HEAD is
  # spoofable — a dirty working tree can keep the pinned commit while the
  # actual files `claude plugin install` reads have changed. Clean tree +
  # matching HEAD together = content is provably the pinned commit's content.
  local dirty
  dirty="$(git -C "$loc" status --porcelain 2>/dev/null)"
  if [ -n "$dirty" ]; then
    rollback_if_newly_added
    fail_closed "$label: installed checkout has local changes (working tree is not clean at $loc)" \
      "delete the marketplace checkout and re-run this installer so it is re-cloned fresh — a pinned commit with local edits is not trustworthy content"
  fi
  ok "$label: marketplace verified at pinned commit ${pinned_commit:0:12} (clean tree)"

  if claude plugin list --json 2>/dev/null | grep -q "\"id\": \"$plugin_id\""; then
    ok "$label: plugin already installed ($plugin_id)"
  else
    note "Installing $label ($plugin_id)..."
    if claude plugin install "$plugin_id" >/dev/null 2>&1; then
      ok "$label: plugin installed ($plugin_id)"
    else
      bad "$label: plugin install failed for $plugin_id"
      note "  Fix: run manually — claude plugin install $plugin_id"
      return 1
    fi
  fi
  return 0
}

if [ "$CLAUDE_OK" -eq 1 ] && [ -n "$PYTHON_BIN" ]; then
  note ""
  note "Step 2/4: Code-X plugin (pinned to ${CX_COMMIT:0:12})"
  ensure_marketplace_and_plugin "Code-X" "$CX_MARKETPLACE" "code-x" "code-x@code-x" "$CX_COMMIT"

  note ""
  note "Step 3/4: superpowers plugin (pinned to ${SP_COMMIT:0:12})"
  ensure_marketplace_and_plugin "superpowers" "$SP_MARKETPLACE" "superpowers" "superpowers@superpowers" "$SP_COMMIT"
else
  warn "skipping plugin installs — fix the preflight failures above first"
fi

# ---- Step 4: CodeRabbit — offer only, never auto-install --------------------
note ""
note "Step 4/4: CodeRabbit (optional, third-party — works with Code-X, not included)"
note "  CodeRabbit is a separate, proprietary code-review service that needs its"
note "  own account. This installer will NOT install or configure it for you."
note "  If you want it: ${CR_INSTALL_URL}"
warn "CodeRabbit: offered, not installed (by design — your own account/choice)"

# ---- Verification table -----------------------------------------------------
note ""
note "======================================================"
note "Install summary"
note "======================================================"

if [ "$CLAUDE_OK" -eq 1 ]; then
  cx_version="$(claude plugin details code-x@code-x 2>/dev/null | grep -i version | head -1)"
  [ -n "$cx_version" ] && note "Code-X plugin: $cx_version"
fi

printf 'PASS (%d):\n' "${#PASS_ROWS[@]}"
for row in "${PASS_ROWS[@]}"; do printf '  - %s\n' "$row"; done
printf 'WARN (%d):\n' "${#WARN_ROWS[@]}"
for row in "${WARN_ROWS[@]}"; do printf '  - %s\n' "$row"; done
printf 'FAIL (%d):\n' "${#FAIL_ROWS[@]}"
for row in "${FAIL_ROWS[@]}"; do printf '  - %s\n' "$row"; done

note ""
note "Hooks: Code-X's session-start hook loads automatically in Claude Code."
note "       If you use Codex, approve the hook once when prompted (one-time"
note "       trust step — after that it loads every session)."
note "Skills: superpowers' planning/TDD/debugging skills are discoverable once"
note "        the plugin above shows PASS — no extra step needed."

if [ "${#FAIL_ROWS[@]}" -gt 0 ]; then
  note ""
  note "Some steps did not complete — see FAIL rows above for plain-English fixes."
  exit 1
fi

note ""
note "All set. Open a new Claude Code session and say:"
note "  \"Let's start a new project with Code-X.\""
exit 0
