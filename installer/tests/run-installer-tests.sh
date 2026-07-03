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
  # Sets up an isolated workdir + fake HOME + a manifest copy whose pinned
  # code-x commit is rewritten to match the fake marketplace's real HEAD.
  local dir="$1"
  mkdir -p "$dir/home" "$dir/state"
  cp "$INSTALL_SH" "$dir/install.sh"
  cp "$INSTALLER_DIR/installer-manifest.yaml" "$dir/installer-manifest.yaml"
}

pin_matches_fake_repo() {
  # $1 = sandbox dir. Adds the marketplace via fake-claude first so we can
  # read its real commit, then rewrites the manifest's pinned commit to match
  # (so the "happy path" tests aren't tautologically doomed by using a
  # fabricated real GitHub sha against a fabricated local repo).
  local dir="$1"
  FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace add "1984-alt/code-x" >/dev/null
  FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace add "obra/superpowers" >/dev/null
  local cx_sha sp_sha
  cx_sha="$(git -C "$dir/state/marketplaces/code-x" rev-parse HEAD)"
  sp_sha="$(git -C "$dir/state/marketplaces/superpowers" rev-parse HEAD)"
  python3 - "$dir/installer-manifest.yaml" "$cx_sha" "$sp_sha" <<'EOF'
import sys
path, cx_sha, sp_sha = sys.argv[1:4]
text = open(path).read()
import re
text = re.sub(r'(code-x:.*?commit_sha: ")[0-9a-f]+(")', r'\g<1>' + cx_sha + r'\g<2>', text, count=1, flags=re.S)
text = re.sub(r'(superpowers:.*?commit_sha: ")[0-9a-f]+(")', r'\g<1>' + sp_sha + r'\g<2>', text, count=1, flags=re.S)
open(path, 'w').write(text)
EOF
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
  pin_matches_fake_repo "$dir"
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
  pin_matches_fake_repo "$dir"
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

# ---- case 3: fail-closed on a commit-sha mismatch ---------------------------
test_fail_closed_on_mismatch() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  # Add marketplaces via fake-claude but DO NOT sync the pin -> manifest keeps
  # its shipped (real GitHub) commit shas, which will not match the throwaway
  # local repos' commits.
  FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace add "1984-alt/code-x" >/dev/null
  FAKE_CLAUDE_HOME="$dir/state" "$FAKE_CLAUDE" plugin marketplace add "obra/superpowers" >/dev/null
  local status; status="$(run_installer "$dir")"
  local rc=1
  if [ "$status" -ne 0 ] && grep -qi "does not match the pinned coordinate" "$dir/out.log"; then
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
  pin_matches_fake_repo "$dir"
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
  pin_matches_fake_repo "$dir"
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

# ---- P0-3: matching HEAD with a DIRTY working tree must still FAIL ----------
test_dirty_tree_fails_even_with_matching_head() {
  local dir; dir="$(mktemp -d)"
  fresh_sandbox "$dir"
  pin_matches_fake_repo "$dir"
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
  # Deliberately do NOT sync the pin: the shipped manifest's real commit_sha
  # will not match the freshly-created fake local repo's commit, so install.sh
  # must add the marketplace, discover the mismatch, and remove it again.
  local status; status="$(run_installer "$dir")"
  local rc=1
  if [ "$status" -ne 0 ] && grep -qi "does not match the pinned coordinate" "$dir/out.log"; then
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
  manifest_tag="$(grep -A15 '^  code-x:' "$INSTALLER_DIR/installer-manifest.yaml" | \
    grep 'release_tag:' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
  [ -n "$cx_version" ] && [ -n "$manifest_tag" ] && [ "$cx_version" = "$manifest_tag" ]
}

run_case "clean install exits 0" test_clean_install_exits_zero
run_case "second run is idempotent (no duplicate marketplaces/plugins)" test_idempotent_second_run
run_case "fail-closed on commit-sha mismatch" test_fail_closed_on_mismatch
run_case "CodeRabbit offered, never auto-installed" test_coderabbit_never_autoinstalled
run_case "missing manifest + unreachable bootstrap fails closed" test_missing_manifest_fails_closed
run_case "P0-1: no unpinned /main/ raw.githubusercontent URL" test_no_unpinned_main_branch_url
run_case "P0-2: no unpinned/unhashed pip install in install.sh" test_no_unpinned_pip_install
run_case "P0-2: missing PyYAML hints pinned+hashed command and fails closed" test_missing_pyyaml_hints_pinned_hashed_command
run_case "P0-3: matching HEAD but dirty tree still fails closed" test_dirty_tree_fails_even_with_matching_head
run_case "P1: newly-added marketplace rolled back on pin mismatch" test_rollback_removes_newly_added_marketplace_on_mismatch
run_case "P1: bootstrap manifest fetch — correct hash proceeds" test_bootstrap_fetch_correct_hash_proceeds
run_case "P1: bootstrap manifest fetch — wrong hash fails closed" test_bootstrap_fetch_wrong_hash_fails_closed
run_case "P1: manifest code-x pin version matches checkers/cx --version" test_version_parity_with_cx

echo ""
echo "installer tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
