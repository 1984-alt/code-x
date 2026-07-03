#!/usr/bin/env bash
# Local, offline tests for the Code-X installer (PBF-PROP-017).
# No network required: a fake `claude` CLI stub (tests/fixtures/fake-claude)
# stands in for the real Claude Code CLI, backed by throwaway local git repos
# instead of real GitHub marketplaces.
#
# Follows the pattern of Code-X-V1/checkers/tests/run.py (a single runner that
# reports PASS/FAIL per case) but as shell, since install.sh has no Python
# entry point to import directly — a shell test harness is the smallest thing
# that satisfies "test the shell script" (do-less ladder rung 6).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
INSTALLER_DIR="$(dirname "$HERE")"
INSTALL_SH="$INSTALLER_DIR/install.sh"
FAKE_CLAUDE="$HERE/fixtures/claude"

PASS=0
FAIL=0

run_case() {
  local name="$1"
  shift
  if "$@"; then
    printf 'PASS  %s\n' "$name"
    PASS=$((PASS + 1))
  else
    printf 'FAIL  %s\n' "$name"
    FAIL=$((FAIL + 1))
  fi
}

fresh_sandbox() {
  # Sets up an isolated workdir + fake HOME + an untouched manifest copy.
  local dir="$1"
  mkdir -p "$dir/home" "$dir/state"
  cp "$INSTALL_SH" "$dir/install.sh"
  cp "$INSTALLER_DIR/installer-manifest.yaml" "$dir/installer-manifest.yaml"
}

manifest_field() {
  # $1 = block header (e.g. "code-x"), $2 = field name. Robust to any number
  # of comment lines inside the block: enters at the "  <block>:" line, exits
  # when the next top-level (2-space-indented) key appears, prints the first
  # matching field value. Not position-dependent (the old grep -A<N> broke
  # when a comment shifted a field past the window).
  awk -v blk="  $1:" -v field="$2" '
    $0 == blk { inb=1; next }
    inb && /^  [a-zA-Z]/ { inb=0 }
    inb && $0 ~ "^    "field":" {
      sub("^    "field":[ ]*", ""); gsub(/^"|"$/, ""); print; exit
    }
  ' "$INSTALLER_DIR/installer-manifest.yaml"
}

manifest_release_tag() {
  # $1 = block header, e.g. "code-x" or "superpowers"
  manifest_field "$1" release_tag | grep -oE 'v[0-9.]+'
}

tag_pinned_add_source() {
  # $1 = block header. Reconstructs the exact full-URL#tag string install.sh
  # passes to `claude plugin marketplace add`.
  printf '%s#%s' "$(manifest_field "$1" marketplace_add_url)" "$(manifest_release_tag "$1")"
}

seed_marketplaces_matching_manifest() {
  # $1 = sandbox dir. Pre-adds both marketplaces via fake-claude using the
  # SAME full-URL#<tag> the real install.sh would request, so the fake CLI's
  # self-declared version already matches the shipped manifest (see
  # tests/fixtures/claude: version = the requested ref). Used by tests that
  # need marketplaces already present before running the installer.
  local dir="$1"
  FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace add "$(tag_pinned_add_source code-x)" >/dev/null
  FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace add "$(tag_pinned_add_source superpowers)" >/dev/null
}

run_installer() {
  local dir="$1"
  ( cd "$dir" && \
    HOME="$dir/home" \
    FAKE_CLAUDE_HOME="$dir/state" \
    PATH="$HERE/fixtures:$PATH" \
    bash "$dir/install.sh" ) > "$dir/out.log" 2>&1
  echo $?
}

# ---- case 1: happy path — clean install exits 0 -----------------------------
test_clean_install_exits_zero() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  local status; status="$(run_installer "$dir")"
  [ "$status" -eq 0 ]
  local rc=$?
  rm -rf "$dir"
  return $rc
}

# ---- case 2: idempotent second run — still exits 0, no duplicate installs --
test_idempotent_second_run() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  run_installer "$dir" >/dev/null
  local status2; status2="$(run_installer "$dir")"
  [ "$status2" -eq 0 ] || return 1
  local installed_count
  installed_count="$(python3 -c "import json; print(len(json.load(open('$dir/state/installed.json'))))")"
  [ "$installed_count" -eq 2 ] || { echo "expected 2 installed plugins after 2 runs, got $installed_count" >&2; return 1; }
  local marketplace_count
  marketplace_count="$(FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace list | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")"
  [ "$marketplace_count" -eq 2 ] || { echo "expected 2 marketplaces after 2 runs (no dupes), got $marketplace_count" >&2; return 1; }
  local rc=0
  rm -rf "$dir"
  return $rc
}

# ---- case 3: a PRE-EXISTING UNPINNED marketplace fails closed (hole A) ------
test_preexisting_unpinned_marketplace_fails_closed() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  # Add marketplaces via fake-claude with NO ref (the unpinned shorthand a
  # user's manual `marketplace add owner/repo` would use) -> no tag is created,
  # so HEAD is not at the pinned tag. install.sh must NOT trust the
  # pre-existing marketplace: exact-tag check fails closed with a "remove and
  # re-run" instruction.
  FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace add "1984-alt/code-x" >/dev/null
  FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace add "obra/superpowers" >/dev/null
  local status; status="$(run_installer "$dir")"
  local rc=1
  if [ "$status" -ne 0 ] && grep -qi "is NOT at the pinned tag" "$dir/out.log" && \
     grep -qi "marketplace remove" "$dir/out.log"; then
    rc=0
  else
    echo "--- installer output ---" >&2
    cat "$dir/out.log" >&2
  fi
  rm -rf "$dir"
  return $rc
}

# ---- case 4: CodeRabbit is offered, never auto-installed --------------------
test_coderabbit_never_autoinstalled() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  run_installer "$dir" >/dev/null
  local rc=1
  if grep -qi "offered, not installed" "$dir/out.log" && \
     ! grep -qi "coderabbit" "$dir/state/installed.json" 2>/dev/null; then
    rc=0
  fi
  # install.sh itself must contain no line that actually installs coderabbit
  if grep -Eq 'plugin install .*coderabbit|cli\.coderabbit\.ai.*\|.*sh' "$INSTALL_SH"; then
    echo "install.sh appears to execute a coderabbit install — that is forbidden" >&2
    rc=1
  fi
  rm -rf "$dir"
  return $rc
}

# ---- case 5: missing manifest + no bootstrap fetch configured fails closed --
test_missing_manifest_fails_closed() {
  local dir; dir="$(mktemp -d)"
  mkdir -p "$dir/home"
  cp "$INSTALL_SH" "$dir/install.sh"
  # deliberately no installer-manifest.yaml copied, and no fixture "remote" to
  # bootstrap-fetch from, so this exercises the "curl can't reach the pinned
  # release" fail-closed path rather than the placeholder-hash path.
  ( cd "$dir" && HOME="$dir/home" PATH="$HERE/fixtures:$PATH" \
      CODE_X_INSTALLER_REMOTE_BASE="file:///nonexistent-fixture-path" \
      bash "$dir/install.sh" ) > "$dir/out.log" 2>&1
  local status=$?
  local rc=1
  [ "$status" -ne 0 ] && grep -qi "could not fetch installer-manifest.yaml" "$dir/out.log" && rc=0
  rm -rf "$dir"
  return $rc
}

# ---- P0-1: README + install.sh never reference the mutable `main` branch ----
test_no_unpinned_main_branch_url() {
  local hits
  hits="$(grep -n 'raw\.githubusercontent\.com/.*/main/' "$INSTALL_SH" \
            "$INSTALLER_DIR/README-INSTALL-SECTION.md" 2>/dev/null)"
  if [ -n "$hits" ]; then
    echo "found a mutable /main/ raw.githubusercontent URL:" >&2
    echo "$hits" >&2
    return 1
  fi
  return 0
}

# ---- P0-2: install.sh never runs an unpinned/unhashed pip install -----------
test_no_unpinned_pip_install() {
  # PYYAML_PIN carries the "package==version" pin; the actual invocation
  # references it by variable rather than inline, so a line is safe if it
  # references PYYAML_PIN (already asserted pinned below) AND --hash.
  grep -q '^PYYAML_PIN="[^"]*==[^"]*"' "$INSTALL_SH" || { echo "PYYAML_PIN is not a pinned ==version string" >&2; return 1; }
  local rc=0
  local line
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    case "$line" in
      *'#'*'pip install'*) continue ;;  # comment/prose mentioning "pip install", not an invocation
    esac
    if [[ "$line" == *'--hash'* ]] && { [[ "$line" == *'PYYAML_PIN'* ]] || [[ "$line" == *'=='* ]]; }; then
      continue  # pinned (inline == or via the pinned PYYAML_PIN variable) + hashed, allowed
    fi
    echo "unpinned/unhashed pip install line: $line" >&2; rc=1
  done <<< "$(grep -n 'pip install' "$INSTALL_SH" || true)"
  return $rc
}

# ---- P0-2: missing-PyYAML path prints the pinned+hashed command and fails ---
test_missing_pyyaml_hints_pinned_hashed_command() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  # Shadow python3 with a stub that has no yaml module and is not the real
  # PY_FALLBACK, so the PyYAML-missing branch is guaranteed to trigger.
  mkdir -p "$dir/fakebin"
  local real_python3; real_python3="$(command -v python3)"
  cat > "$dir/fakebin/python3" <<EOF
#!/usr/bin/env bash
if [[ "\$*" == *"import sys"* ]]; then echo "3.11"; exit 0; fi
if [[ "\$*" == *"import yaml"* ]]; then exit 1; fi
exec "$real_python3" "\$@"
EOF
  chmod +x "$dir/fakebin/python3"
  ( cd "$dir" && HOME="$dir/home" FAKE_CLAUDE_HOME="$dir/state" \
      PATH="$dir/fakebin:$HERE/fixtures:$PATH" \
      bash "$dir/install.sh" ) > "$dir/out.log" 2>&1
  local status=$?
  local rc=1
  if grep -qi "PyYAML missing" "$dir/out.log" && \
     grep -q -- "--hash=sha256:" "$dir/out.log" && \
     grep -q "pyyaml==" "$dir/out.log"; then
    rc=0
  fi
  # overall run must still fail closed (nonzero exit) because of the FAIL row
  [ "$status" -eq 0 ] && rc=1
  rm -rf "$dir"
  return $rc
}

# ---- P0-3: matching version with a DIRTY working tree must still FAIL ------
test_dirty_tree_fails_even_with_matching_head() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  seed_marketplaces_matching_manifest "$dir"
  # Dirty the already-pinned code-x checkout after the pin was aligned to it.
  echo "unexpected local edit" >> "$dir/state/marketplaces/code-x/README.md"
  local status; status="$(run_installer "$dir")"
  local rc=1
  if [ "$status" -ne 0 ] && grep -qi "working tree is not clean" "$dir/out.log"; then
    rc=0
  else
    echo "--- installer output ---" >&2
    cat "$dir/out.log" >&2
  fi
  rm -rf "$dir"
  return $rc
}

# ---- P1: a newly-added marketplace is ROLLED BACK on pin-verification fail --
test_rollback_removes_newly_added_marketplace_on_mismatch() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  # Neither marketplace exists yet, and FAKE_CLAUDE_FORCE_VERSION simulates
  # upstream drift: the tag's real content, once cloned, self-declares a
  # DIFFERENT version than installer-manifest.yaml expects. install.sh must
  # add the marketplace itself (newly_added=1), discover the mismatch on the
  # SAME run, and remove it again — never leave it sitting unverified.
  local status
  status="$(FAKE_CLAUDE_FORCE_VERSION=9.9.9 run_installer "$dir")"
  local rc=1
  if [ "$status" -ne 0 ] && grep -qi "does not match the pinned release" "$dir/out.log"; then
    local mp_count
    mp_count="$(FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace list | \
      python3 -c "import json,sys; print(len(json.load(sys.stdin)))")"
    [ "$mp_count" -eq 0 ] && rc=0 || echo "expected marketplace rolled back (0 left), got $mp_count" >&2
  else
    echo "--- installer output ---" >&2
    cat "$dir/out.log" >&2
  fi
  rm -rf "$dir"
  return $rc
}

# ---- P1: marketplace-add uses the DOCUMENTED full-URL#<release_tag> form ----
test_marketplace_add_uses_tag_pinned_source() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  run_installer "$dir" >/dev/null
  local cx_expected sp_expected
  cx_expected="$(tag_pinned_add_source code-x)"
  sp_expected="$(tag_pinned_add_source superpowers)"
  local rc=1
  # Must be the documented full-git-URL + "#<tag>" form (not a bare
  # owner/repo@tag shorthand, which is undocumented for marketplace add).
  if [ -n "$cx_expected" ] && [ -n "$sp_expected" ] && \
     [ "$cx_expected" = "https://github.com/1984-alt/code-x.git#$(manifest_release_tag code-x)" ] && \
     grep -qx "$cx_expected" "$dir/state/marketplace_add_log" && \
     grep -qx "$sp_expected" "$dir/state/marketplace_add_log" && \
     ! grep -Eq '(code-x|superpowers)@v' "$dir/state/marketplace_add_log"; then
    rc=0
  else
    echo "--- marketplace_add_log ---" >&2
    cat "$dir/state/marketplace_add_log" >&2 2>/dev/null
  fi
  rm -rf "$dir"
  return $rc
}

# ---- P1: a WRONG plugin version at the SAME tag fails closed (belt) ---------
test_wrong_installed_version_fails_closed() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  seed_marketplaces_matching_manifest "$dir"
  # Botched/mispinned release: the tag exists and HEAD is ON it, but the tagged
  # content's marketplace.json declares a DIFFERENT version. Force-move the tag
  # onto the amended commit so the exact-tag check passes and this isolates the
  # belt-and-suspenders version-parity check.
  local cx_dir="$dir/state/marketplaces/code-x"
  local cx_tag; cx_tag="$(manifest_release_tag code-x)"
  printf '{"name": "code-x", "plugins": [{"name": "code-x", "version": "9.9.9"}]}\n' > "$cx_dir/.claude-plugin/marketplace.json"
  git -C "$cx_dir" -c user.email=test@test -c user.name=test commit -q -am "botched release: wrong version at tag"
  git -C "$cx_dir" tag -f "$cx_tag" >/dev/null 2>&1
  local status; status="$(run_installer "$dir")"
  local rc=1
  if [ "$status" -ne 0 ] && grep -qi "does not match the pinned release" "$dir/out.log"; then
    rc=0
  else
    echo "--- installer output ---" >&2
    cat "$dir/out.log" >&2
  fi
  rm -rf "$dir"
  return $rc
}

# ---- BLOCKING: clean, RIGHT-version, but HEAD NOT at the tag -> fail closed --
# This is the class the pre-fix verify missed: a main-branch checkout with the
# same declared version and a clean tree would print "verified". Only the exact
# tag assertion catches it.
test_right_version_wrong_branch_fails_closed() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  seed_marketplaces_matching_manifest "$dir"
  # Add a commit on top of the tag that KEEPS the correct version (so
  # version-parity would happily pass) but leaves HEAD off the tag — exactly
  # what an unpinned main-branch checkout looks like.
  local cx_dir="$dir/state/marketplaces/code-x"
  echo "extra main-branch commit" > "$cx_dir/EXTRA.md"
  git -C "$cx_dir" add -A
  git -C "$cx_dir" -c user.email=test@test -c user.name=test commit -q -m "main-branch drift, version unchanged"
  local status; status="$(run_installer "$dir")"
  local rc=1
  # Must fail closed on the TAG check (not version-parity: version still matches).
  if [ "$status" -ne 0 ] && grep -qi "is NOT at the pinned tag" "$dir/out.log" && \
     ! grep -qi "does not match the pinned release" "$dir/out.log"; then
    rc=0
  else
    echo "--- installer output ---" >&2
    cat "$dir/out.log" >&2
  fi
  rm -rf "$dir"
  return $rc
}

# ---- P2: a NON-git / corrupted checkout must fail closed, not read "clean" ---
test_non_git_checkout_fails_closed() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  seed_marketplaces_matching_manifest "$dir"
  # Destroy the git metadata so `git status` exits nonzero with empty stdout —
  # the case the old `[ -n "$dirty" ]` test silently treated as clean.
  rm -rf "$dir/state/marketplaces/code-x/.git"
  local status; status="$(run_installer "$dir")"
  local rc=1
  if [ "$status" -ne 0 ] && grep -qi "not a readable git checkout" "$dir/out.log"; then
    rc=0
  else
    echo "--- installer output ---" >&2
    cat "$dir/out.log" >&2
  fi
  rm -rf "$dir"
  return $rc
}

# ---- P1: install.sh is self-sufficient — bootstrap-fetches its own manifest -
test_bootstrap_fetch_correct_hash_proceeds() {
  local dir; dir="$(mktemp -d)"
  mkdir -p "$dir/home"
  cp "$INSTALL_SH" "$dir/install.sh"
  local tag
  tag="$(grep '^INSTALLER_RELEASE_TAG=' "$INSTALL_SH" | sed -E 's/.*="(.*)"/\1/')"
  local remote="$dir/remote/$tag/installer"
  mkdir -p "$remote"
  # Byte-identical copy of the real manifest -> hash matches the embedded pin.
  cp "$INSTALLER_DIR/installer-manifest.yaml" "$remote/installer-manifest.yaml"
  ( cd "$dir" && HOME="$dir/home" FAKE_CLAUDE_HOME="$dir/state" \
      PATH="$HERE/fixtures:$PATH" \
      CODE_X_INSTALLER_REMOTE_BASE="file://$dir/remote" \
      bash "$dir/install.sh" ) > "$dir/out.log" 2>&1
  local rc=1
  grep -qi "fetched + verified installer-manifest.yaml from pinned release" "$dir/out.log" && rc=0
  rm -rf "$dir"
  return $rc
}

test_bootstrap_fetch_wrong_hash_fails_closed() {
  local dir; dir="$(mktemp -d)"
  mkdir -p "$dir/home"
  cp "$INSTALL_SH" "$dir/install.sh"
  local tag
  tag="$(grep '^INSTALLER_RELEASE_TAG=' "$INSTALL_SH" | sed -E 's/.*="(.*)"/\1/')"
  local remote="$dir/remote/$tag/installer"
  mkdir -p "$remote"
  cp "$INSTALLER_DIR/installer-manifest.yaml" "$remote/installer-manifest.yaml"
  printf '\n# tampered\n' >> "$remote/installer-manifest.yaml"
  ( cd "$dir" && HOME="$dir/home" FAKE_CLAUDE_HOME="$dir/state" \
      PATH="$HERE/fixtures:$PATH" \
      CODE_X_INSTALLER_REMOTE_BASE="file://$dir/remote" \
      bash "$dir/install.sh" ) > "$dir/out.log" 2>&1
  local status=$?
  local rc=1
  [ "$status" -ne 0 ] && grep -qi "does not match the pinned checksum" "$dir/out.log" && rc=0
  rm -rf "$dir"
  return $rc
}

# ---- P1: manifest's code-x pin version must match the shipping canon version -
test_version_parity_with_cx() {
  # Public repo layout: installer/ sits at repo root, checkers/ is nested under
  # plugins/code-x/skills/code-x/ (unlike private canon's flat Code-X-V1/ layout).
  local cx_bin="$INSTALLER_DIR/../plugins/code-x/skills/code-x/checkers/cx"
  [ -x "$cx_bin" ] || cx_bin="python3 $INSTALLER_DIR/../plugins/code-x/skills/code-x/checkers/cx"
  local cx_version manifest_tag
  cx_version="$($cx_bin --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
  manifest_tag="$(manifest_release_tag code-x | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
  [ -n "$cx_version" ] && [ -n "$manifest_tag" ] && [ "$cx_version" = "$manifest_tag" ]
}

# ---- P1: marketplace.json + plugin.json version == the release tag (gate) --
# xfam v1.22.4 public-port fold: install.sh's version-parity check (belt-and-
# suspenders inside ensure_marketplace_and_plugin) only fires AFTER a real
# `claude plugin marketplace add` clone — it cannot run offline in this local
# suite. This test is the offline substitute: it reads the REAL, shipped
# marketplace.json + plugin.json straight off disk and asserts their declared
# version equals installer-manifest.yaml's code-x release_tag. If a release is
# cut without bumping one of the three, real users hit install.sh's fail-closed
# version-parity check for real — this test catches the mismatch before ship.
test_marketplace_and_plugin_json_version_parity() {
  local repo_root="$INSTALLER_DIR/.."
  local marketplace_json="$repo_root/.claude-plugin/marketplace.json"
  local plugin_json="$repo_root/plugins/code-x/.claude-plugin/plugin.json"
  [ -f "$marketplace_json" ] || { echo "missing $marketplace_json" >&2; return 1; }
  [ -f "$plugin_json" ] || { echo "missing $plugin_json" >&2; return 1; }
  local manifest_tag mp_version plugin_version
  manifest_tag="$(manifest_release_tag code-x | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
  mp_version="$(python3 -c "
import json
data = json.load(open('$marketplace_json'))
plugins = [p for p in data.get('plugins', []) if p.get('name') == 'code-x']
print(plugins[0].get('version', '') if plugins else '')
" 2>/dev/null)"
  plugin_version="$(python3 -c "
import json
print(json.load(open('$plugin_json')).get('version', ''))
" 2>/dev/null)"
  local rc=0
  if [ -z "$manifest_tag" ]; then echo "could not read installer-manifest.yaml code-x release_tag" >&2; rc=1; fi
  if [ -z "$mp_version" ]; then echo "could not read $marketplace_json plugins[code-x].version" >&2; rc=1; fi
  if [ -z "$plugin_version" ]; then echo "could not read $plugin_json version" >&2; rc=1; fi
  [ "$rc" -eq 0 ] || return 1
  if [ "$mp_version" != "$manifest_tag" ]; then
    echo "marketplace.json version ($mp_version) != installer-manifest.yaml release_tag ($manifest_tag)" >&2
    rc=1
  fi
  if [ "$plugin_version" != "$manifest_tag" ]; then
    echo "plugin.json version ($plugin_version) != installer-manifest.yaml release_tag ($manifest_tag)" >&2
    rc=1
  fi
  return $rc
}

run_case "clean install exits 0" test_clean_install_exits_zero
run_case "second run is idempotent (no duplicate marketplaces/plugins)" test_idempotent_second_run
run_case "pre-existing UNPINNED marketplace fails closed (hole A)" test_preexisting_unpinned_marketplace_fails_closed
run_case "CodeRabbit offered, never auto-installed" test_coderabbit_never_autoinstalled
run_case "missing manifest + unreachable bootstrap fails closed" test_missing_manifest_fails_closed
run_case "P0-1: no unpinned /main/ raw.githubusercontent URL" test_no_unpinned_main_branch_url
run_case "P0-2: no unpinned/unhashed pip install in install.sh" test_no_unpinned_pip_install
run_case "P0-2: missing PyYAML hints pinned+hashed command and fails closed" test_missing_pyyaml_hints_pinned_hashed_command
run_case "P0-3: matching version but dirty tree still fails closed" test_dirty_tree_fails_even_with_matching_head
run_case "P1: newly-added marketplace rolled back on version mismatch" test_rollback_removes_newly_added_marketplace_on_mismatch
run_case "P1: bootstrap manifest fetch — correct hash proceeds" test_bootstrap_fetch_correct_hash_proceeds
run_case "P1: bootstrap manifest fetch — wrong hash fails closed" test_bootstrap_fetch_wrong_hash_fails_closed
run_case "P1: manifest code-x pin version matches checkers/cx --version" test_version_parity_with_cx
run_case "GATE: marketplace.json + plugin.json version == release tag" test_marketplace_and_plugin_json_version_parity
run_case "P1: marketplace-add uses the documented full-URL#<release_tag> form" test_marketplace_add_uses_tag_pinned_source
run_case "P1: wrong plugin version at the same tag fails closed (belt)" test_wrong_installed_version_fails_closed
run_case "BLOCKING: clean+right-version but HEAD not at tag fails closed" test_right_version_wrong_branch_fails_closed
run_case "P2: non-git/corrupted checkout fails closed (not read as clean)" test_non_git_checkout_fails_closed

echo ""
echo "installer tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
