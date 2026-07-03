#!/usr/bin/env bash
# Release-cut re-stamp for the Code-X installer (PBF-PROP-017 fix-fold, 2026-07-03).
#
# What this does, in plain English:
#   Every time Code-X cuts a release, the installer's two self-referential
#   pins go stale: the manifest's code-x release_tag/commit_sha (must match
#   the release being cut — "same-release-as-self"), and install.sh's own
#   embedded release tag + manifest checksum (its bootstrap trust root for
#   the pipe-to-bash path). This script updates all four together and prints
#   a plain diff of what changed, so nothing is re-stamped by hand.
#
# Usage:
#   installer/restamp-release.sh <release_tag> <code_x_commit_sha>
#
# Example (run from the port session at the actual release cut):
#   installer/restamp-release.sh v1.22.3 3edca29c1234...(real 40-char sha)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
MANIFEST="$HERE/installer-manifest.yaml"
INSTALL_SH="$HERE/install.sh"

RELEASE_TAG="${1:-}"
COMMIT_SHA="${2:-}"
if [ -z "$RELEASE_TAG" ] || [ -z "$COMMIT_SHA" ]; then
  echo "Usage: $0 <release_tag> <code_x_commit_sha>" >&2
  exit 1
fi

shasum_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

echo "Before:"
grep -n 'release_tag:\|^    commit_sha:' "$MANIFEST" | head -2 | sed 's/^/  manifest: /'
grep -n 'INSTALLER_RELEASE_TAG=\|INSTALLER_MANIFEST_SHA256=' "$INSTALL_SH" | sed 's/^/  install.sh: /'

# 1. Stamp the manifest's code-x pin (release_tag + commit_sha together — never one alone).
python3 - "$MANIFEST" "$RELEASE_TAG" "$COMMIT_SHA" <<'EOF'
import sys, re
path, tag, sha = sys.argv[1:4]
text = open(path).read()
text = re.sub(r'(code-x:.*?release_tag: ")[^"]*(")', r'\g<1>' + tag + r'\g<2>', text, count=1, flags=re.S)
text = re.sub(r'(code-x:.*?commit_sha: ")[0-9a-f]+(")', r'\g<1>' + sha + r'\g<2>', text, count=1, flags=re.S)
open(path, 'w').write(text)
EOF

# 2. Stamp install.sh's embedded bootstrap release tag to match.
sed -i.bak "s/^INSTALLER_RELEASE_TAG=\".*\"/INSTALLER_RELEASE_TAG=\"$RELEASE_TAG\"/" "$INSTALL_SH"

# 3. Recompute the manifest checksum AFTER step 1's edit, then stamp it into
#    install.sh. This must be last: any change to the manifest invalidates it.
MANIFEST_SHA256="$(shasum_file "$MANIFEST")"
sed -i.bak "s/^INSTALLER_MANIFEST_SHA256=\".*\"/INSTALLER_MANIFEST_SHA256=\"$MANIFEST_SHA256\"/" "$INSTALL_SH"
rm -f "$INSTALL_SH.bak"

echo ""
echo "After:"
grep -n 'release_tag:\|^    commit_sha:' "$MANIFEST" | head -2 | sed 's/^/  manifest: /'
grep -n 'INSTALLER_RELEASE_TAG=\|INSTALLER_MANIFEST_SHA256=' "$INSTALL_SH" | sed 's/^/  install.sh: /'
echo ""
echo "Re-stamped for release $RELEASE_TAG. Re-run installer/tests/run-installer-tests.sh before shipping."
