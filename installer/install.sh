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

# ---- embedded trust root (council trust-model rebuild, 2026-07-03; INV-1) --
# This installer has exactly ONE manifest trust root: it ALWAYS fetches
# installer-manifest.yaml fresh from this exact pinned release tag and
# verifies it against this exact pinned checksum BEFORE trusting a single
# byte of it — it never reads a manifest sitting beside the script or in the
# current directory (that would let a manifest planted next to a downloaded
# install.sh, e.g. in ~/Downloads, be trusted silently). Re-stamped together
# by installer/restamp-release.sh at every release cut — never edit by hand.
INSTALLER_RELEASE_TAG="v1.22.8"
INSTALLER_MANIFEST_SHA256="6d3163be7000b25e00a419a133bff49c66c5659c6347e2776b7c5027d38736c1"
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

# ---- manifest resolution: single trust root, ALWAYS fetch (INV-1) ----------
# install.sh never reads a manifest from disk (cwd or beside the script) —
# it always fetches its own copy from the pinned release tag and checksum
# above, then parses that. This collapses what used to be two code paths
# (local-file vs fetch) into one: the same fetch-and-verify logic runs for
# every install, dev or real, so a test can never accidentally exercise a
# different (and weaker) path than a real user does. Tests point
# CODE_X_INSTALLER_REMOTE_BASE at a throwaway file:// tree instead of the
# real network — same code, no shortcuts.
if [ "$INSTALLER_MANIFEST_SHA256" = "__PENDING_RESTAMP__" ]; then
  fail_closed "install.sh's embedded manifest checksum has not been stamped for a release yet" \
    "this is a dev/pre-release copy of install.sh — run installer/restamp-release.sh first"
fi
if ! command -v curl >/dev/null 2>&1; then
  fail_closed "curl is unavailable, and this installer needs it to fetch installer-manifest.yaml" \
    "install curl, then re-run this installer"
fi
TMP_MANIFEST="$(mktemp -t code-x-manifest.XXXXXX 2>/dev/null || mktemp)"
trap 'rm -f "$TMP_MANIFEST"' EXIT
REMOTE_MANIFEST_URL="${REMOTE_BASE}/${INSTALLER_RELEASE_TAG}/installer/installer-manifest.yaml"
if ! curl -fsSL "$REMOTE_MANIFEST_URL" -o "$TMP_MANIFEST" 2>/dev/null; then
  fail_closed "could not fetch installer-manifest.yaml from the pinned release ($REMOTE_MANIFEST_URL)" \
    "check your internet connection and try again"
fi
FETCHED_SHA256="$(shasum_file "$TMP_MANIFEST")"
if [ -z "$FETCHED_SHA256" ] || [ "$FETCHED_SHA256" != "$INSTALLER_MANIFEST_SHA256" ]; then
  fail_closed "fetched installer-manifest.yaml does not match the pinned checksum (expected ${INSTALLER_MANIFEST_SHA256:0:12}\xe2\x80\xa6, got ${FETCHED_SHA256:0:12}\xe2\x80\xa6)" \
    "the release asset may be corrupted or tampered with \xe2\x80\x94 do not proceed; report this"
fi
MANIFEST="$TMP_MANIFEST"
ok "fetched + verified installer-manifest.yaml from pinned release $INSTALLER_RELEASE_TAG"

# ---- tiny YAML field reader (no PyYAML dependency for the shell layer) -----
# The manifest is a flat, hand-authored YAML file. We only need scalar leaf
# values under known keys, so a narrow indented-block reader is enough —
# pulling in a YAML parser just for this would violate the do-less ladder.
yaml_get() {
  # $1 = block header (e.g. "  superpowers:"), $2 = field name (e.g. "release_tag")
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

CX_RELEASE_TAG="$(yaml_get "  code-x:" release_tag)"
CX_MARKETPLACE_URL="$(yaml_get "  code-x:" marketplace_add_url)"
CX_MP_NAME="$(yaml_get "  code-x:" marketplace_name)"
CX_PLUGIN_ID="$(yaml_get "  code-x:" plugin_id)"
SP_RELEASE_TAG="$(yaml_get "  superpowers:" release_tag)"
SP_MARKETPLACE_URL="$(yaml_get "  superpowers:" marketplace_add_url)"
SP_MP_NAME="$(yaml_get "  superpowers:" marketplace_name)"
SP_PLUGIN_ID="$(yaml_get "  superpowers:" plugin_id)"
# INV-3: enforced when present (superpowers has it; code-x has none — see
# ensure_marketplace_and_plugin below for why code-x auto-skips this check).
SP_COMMIT_SHA="$(yaml_get "  superpowers:" commit_sha)"
CR_INSTALL_URL="$(yaml_get "  coderabbit:" install_url)"
PY_MIN_VERSION="$(yaml_get "  python3:" min_version)"
PY_FALLBACK="$(yaml_get "  python3:" macos_fallback_path)"

for pair in "code-x-release:$CX_RELEASE_TAG" "code-x-marketplace-url:$CX_MARKETPLACE_URL" \
            "code-x-marketplace-name:$CX_MP_NAME" "code-x-plugin-id:$CX_PLUGIN_ID" \
            "superpowers-release:$SP_RELEASE_TAG" "superpowers-marketplace-url:$SP_MARKETPLACE_URL" \
            "superpowers-marketplace-name:$SP_MP_NAME" "superpowers-plugin-id:$SP_PLUGIN_ID"; do
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

# xfam FIX-FIRST P3 (2026-07-03): HARD-STOP before any marketplace/plugin
# mutation if ANY required prerequisite is missing. Previously only a missing
# `claude` CLI stopped here — a missing PyYAML (with Python present) fell
# through and installed the plugins anyway, leaving the user with plugins on
# disk but a non-functional `cx` (which needs PyYAML). Every [FAIL] row above
# is a required prerequisite, so stop closed here and change nothing.
if [ "${#FAIL_ROWS[@]}" -gt 0 ]; then
  fail_closed "a required prerequisite is missing (see the [FAIL] line(s) above)" \
    "install the missing prerequisite(s) listed above, then re-run this installer — it is safe to re-run, and nothing has been installed or changed yet"
fi

# ---- helpers to drive the claude CLI plugin machinery ----------------------
marketplace_exists() {
  # $1 = marketplace name. Structured JSON read (INV-5), not a substring
  # grep — a grep for `"name": "$mp_name"` can also match that same string
  # appearing as another marketplace's unrelated field value, or miss on a
  # harmless whitespace difference the CLI is free to emit.
  local name="$1"
  claude plugin marketplace list --json 2>/dev/null | "$PYTHON_BIN" -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if any(m.get('name') == '$name' for m in data) else 1)
"
}

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

installed_plugin_version() {
  # $1 = marketplace checkout location, $2 = plugin name as listed inside that
  # marketplace's own marketplace.json (e.g. "code-x", "superpowers"). Reads
  # the version straight out of the cloned marketplace.json — the release's
  # own self-declared version, not a live network/CLI call — so this works
  # immediately after marketplace add, before `claude plugin install` runs.
  local loc="$1" name="$2"
  "$PYTHON_BIN" -c "
import json, sys
try:
    with open('$loc/.claude-plugin/marketplace.json') as f:
        data = json.load(f)
except Exception:
    sys.exit(0)
for p in data.get('plugins', []):
    if p.get('name') == '$name':
        print(p.get('version', ''))
        break
"
}

plugin_installed() {
  # $1 = plugin id ("name@marketplace"). Structured JSON read — see
  # marketplace_exists above for why this replaced a substring grep.
  local id="$1"
  claude plugin list --json 2>/dev/null | "$PYTHON_BIN" -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if any(p.get('id') == '$id' for p in data) else 1)
"
}

normalize_git_origin() {
  # $1 = a git remote URL. Prints "host/owner/repo" (host lowercased) so
  # equivalent forms of the SAME repo compare equal — https with or without
  # a trailing "/" or ".git", with or without legit "user@"/"user:pass@"
  # credentials or a ":port" — WITHOUT accepting a lookalike host or a
  # different owner/repo. (INV-2's highest-attention item: accept every legit
  # form, never a lookalike.)
  #
  # CRITICAL: split the AUTHORITY (host[:port], optional userinfo) from the
  # PATH *first*, then strip userinfo/port from the authority ONLY. A naive
  # `${url#*@}` over the whole string treats a path-embedded "@" as userinfo,
  # so a URL like `https://evil.com/@github.com/1984-alt/code-x.git` would
  # normalize to `github.com/1984-alt/code-x` and MATCH the official repo — a
  # trust-root bypass. Because code-x carries no commit_sha pin (self-sha is
  # circular), that bypass would let an attacker-controlled repo be accepted
  # as the official trust root. Never do "@"-surgery on the path.
  #
  # ssh shorthand (git@host:owner/repo) is deliberately NOT handled: the real
  # origin is always the https URL (runtime-probed 2026-07-03), and a legit-
  # but-odd form failing closed is the safe direction — adding ssh parsing
  # risks re-opening exactly the hole above.
  local url="$1"
  url="${url%/}"          # one trailing slash
  url="${url%.git}"       # .git suffix
  url="${url#*://}"       # scheme (https://, git://, ssh://), if present
  local authority path
  case "$url" in
    */*) authority="${url%%/*}"; path="${url#*/}" ;;
    *)   authority="$url"; path="" ;;
  esac
  authority="${authority#*@}"    # strip user@ / user:pass@ — AUTHORITY ONLY
  authority="${authority%%:*}"   # strip :port — AUTHORITY ONLY
  printf '%s/%s' "$(printf '%s' "$authority" | tr '[:upper:]' '[:lower:]')" "$path"
}

ensure_marketplace_and_plugin() {
  # $1 = human label, $2 = marketplace add URL (full https .git URL),
  # $3 = marketplace name (as the marketplace declares itself, NOT the repo
  # name), $4 = plugin id (plugin@marketplace), $5 = pinned release tag,
  # $6 = pinned commit sha (INV-3; empty string when the dep has none — e.g.
  # code-x, whose own release commit cannot contain its own sha).
  #
  # The tag pin uses the DOCUMENTED full-URL + `#<ref>` form
  # ("<url>.git#<tag>"). The bare `owner/repo@tag` shorthand is undocumented
  # for `marketplace add` and can silently clone unpinned on some CLI
  # versions — this form is the one Anthropic's docs guarantee.
  local label="$1" add_url="$2" mp_name="$3" plugin_id="$4" release_tag="$5" commit_sha="${6:-}"
  local newly_added=0
  local add_source="${add_url}#${release_tag}"

  if ! marketplace_exists "$mp_name"; then
    note "Adding the $label marketplace ($add_url, pinned to $release_tag)..."
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

  # xfam FIX-FIRST P2 (2026-07-03): git status on a NON-git or corrupted loc
  # exits nonzero with EMPTY stdout, which the old `[ -n "$dirty" ]` test
  # silently read as "clean". Check the exit status explicitly first.
  local dirty status_rc
  dirty="$(git -C "$loc" status --porcelain 2>/dev/null)"; status_rc=$?
  if [ "$status_rc" -ne 0 ]; then
    rollback_if_newly_added
    fail_closed "$label: $loc is not a readable git checkout (git status failed)" \
      "remove the marketplace and re-run so it is re-cloned fresh: claude plugin marketplace remove $mp_name"
  fi

  # INV-2 (council trust-model rebuild, 2026-07-03): identity = this
  # checkout's OWN git origin, not its name. A marketplace called "code-x"
  # could be ANY repo — `claude plugin marketplace list --json`'s own
  # url/source field reflects settings, not what actually got cloned, so we
  # read the on-disk clone's real remote instead. Highest-attention item:
  # accept every legit form of the official URL, never a lookalike origin.
  local origin_url
  origin_url="$(git -C "$loc" remote get-url origin 2>/dev/null)"
  if [ -z "$origin_url" ]; then
    rollback_if_newly_added
    fail_closed "$label: could not read the checkout's own git origin at $loc" \
      "remove the marketplace and re-run so it is re-cloned fresh: claude plugin marketplace remove $mp_name"
  fi
  if [ "$(normalize_git_origin "$origin_url")" != "$(normalize_git_origin "$add_url")" ]; then
    rollback_if_newly_added
    fail_closed "$label: the '$mp_name' marketplace points at a different repo ($origin_url) than the official source ($add_url)" \
      "a marketplace named '$mp_name' already exists but is not the real one — remove it and re-run so the official one is added: claude plugin marketplace remove $mp_name"
  fi

  # xfam FIX-FIRST BLOCKING (2026-07-03), rebuilt for INV-4 (council
  # trust-model, 2026-07-03): prove HEAD is EXACTLY the commit the pinned tag
  # points at. A tag-pinned `marketplace add ...#<tag>` SHOULD land HEAD on
  # the tag, but we must not TRUST that it did: a marketplace added UNPINNED
  # earlier (hole A — e.g. someone ran the manual `marketplace add
  # owner/repo`), or an older CLI that ignored the `#<tag>` suffix (hole B),
  # can sit at a clean, same-version main-branch HEAD that is NOT the tag —
  # and the version-parity check alone would wave it through. Comparing
  # commits (via `rev-parse refs/tags/<tag>^{commit}`, not tag NAMES via
  # `git describe --exact-match`) also means two tags sharing one commit
  # never produce a false fail.
  local tag_commit head_commit
  tag_commit="$(git -C "$loc" rev-parse "refs/tags/${release_tag}^{commit}" 2>/dev/null)"
  head_commit="$(git -C "$loc" rev-parse HEAD 2>/dev/null)"
  if [ -z "$tag_commit" ] || [ "$tag_commit" != "$head_commit" ]; then
    rollback_if_newly_added
    if [ "$newly_added" -eq 1 ]; then
      fail_closed "$label: the marketplace was added but HEAD is not the pinned tag $release_tag (HEAD's commit does not match the tag's commit)" \
        "your Claude CLI may be too old to honor a #<tag> pin — update Claude Code, then re-run this installer (it is safe to re-run)"
    else
      fail_closed "$label: an existing '$mp_name' marketplace is NOT at the pinned tag $release_tag (HEAD's commit does not match the tag's commit)" \
        "it was likely added unpinned earlier — remove it and re-run so it is re-added pinned: claude plugin marketplace remove $mp_name"
    fi
  fi

  # A dirty tree can diverge from the tagged content even when HEAD is the tag.
  if [ -n "$dirty" ]; then
    rollback_if_newly_added
    fail_closed "$label: installed checkout has local changes (working tree is not clean at $loc)" \
      "delete the marketplace checkout and re-run this installer so it is re-cloned fresh — a pinned tag with local edits is not trustworthy content"
  fi

  # Belt-and-suspenders (fold v1.22.4): the tagged content's OWN self-declared
  # plugin version must equal the pinned release tag — catches a mispinned or
  # botched release where the tag exists but its marketplace.json declares a
  # different version. (For code-x, this is the strongest content check
  # available: a marketplace source can only be pinned to a branch/tag ref,
  # never a raw commit sha, and a code-x release commit cannot contain its
  # own sha — the tag IS the pin. superpowers gets an additional, stronger
  # check right after this one — see INV-3 below.)
  local plugin_name installed_version expected_version
  plugin_name="${plugin_id%%@*}"
  installed_version="$(installed_plugin_version "$loc" "$plugin_name")"
  expected_version="${release_tag#v}"
  if [ -z "$installed_version" ]; then
    rollback_if_newly_added
    bad "$label: could not read the installed plugin's declared version at $loc"
    note "  Fix: run 'claude plugin marketplace update $mp_name' and re-run this installer"
    return 1
  fi
  if [ "$installed_version" != "$expected_version" ]; then
    rollback_if_newly_added
    fail_closed "$label: installed plugin version ($installed_version) does not match the pinned release ($expected_version)" \
      "the upstream tag may have moved, or the checkout is stale — do not proceed on an unverified version; tell the maintainer to re-pin installer-manifest.yaml"
  fi
  # INV-3 (council trust-model rebuild, 2026-07-03): enforced when the
  # manifest carries a commit_sha for this dependency (external deps like
  # superpowers, pinned from outside their own release process). code-x has
  # none — a release commit cannot contain its own sha, so this auto-skips
  # code-x. Runs AFTER version-parity above (a stronger check on top of it):
  # catches an upstream tag moved/re-cut to different content while keeping
  # the same self-declared version, which version-parity alone cannot see.
  if [ -n "$commit_sha" ] && [ "$head_commit" != "$commit_sha" ]; then
    rollback_if_newly_added
    fail_closed "$label: the checkout's commit (${head_commit:-unknown}) does not match the pinned commit ($commit_sha)" \
      "the upstream tag may have moved to different content since it was pinned — do not proceed; report this so installer-manifest.yaml can be re-verified and re-pinned"
  fi

  ok "$label: marketplace verified at pinned tag $release_tag (HEAD on tag, clean tree, version $installed_version)"

  if plugin_installed "$plugin_id"; then
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
  note "Step 2/4: Code-X plugin (pinned to release $CX_RELEASE_TAG)"
  # INV-5 (council trust-model rebuild, 2026-07-03): chain-halt. A code-x
  # step that only "soft-failed" (returned 1 without already calling
  # fail_closed — e.g. the marketplace add itself failed) must STOP here,
  # before superpowers ever runs. Installing superpowers on top of a broken
  # Code-X would leave the user with a half-working setup and no clear
  # signal why.
  if ! ensure_marketplace_and_plugin "Code-X" "$CX_MARKETPLACE_URL" "$CX_MP_NAME" "$CX_PLUGIN_ID" "$CX_RELEASE_TAG" ""; then
    fail_closed "Code-X plugin setup did not complete — see the FAIL line(s) above" \
      "fix the Code-X issue above, then re-run this installer — it will not move on to superpowers until Code-X itself is verified"
  fi

  note ""
  note "Step 3/4: superpowers plugin (pinned to release $SP_RELEASE_TAG)"
  if ! ensure_marketplace_and_plugin "superpowers" "$SP_MARKETPLACE_URL" "$SP_MP_NAME" "$SP_PLUGIN_ID" "$SP_RELEASE_TAG" "$SP_COMMIT_SHA"; then
    fail_closed "superpowers plugin setup did not complete — see the FAIL line(s) above" \
      "fix the superpowers issue above, then re-run this installer"
  fi
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
