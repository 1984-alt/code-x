#!/usr/bin/env bash
# Release-cut re-stamp for the Code-X installer (PBF-PROP-017 fix-fold, 2026-07-03;
# verification-model fix folded into v1.22.4, 2026-07-03, CEO-D-042).
#
# What this does, in plain English:
#   Every time Code-X cuts a release, the installer's self-referential pins go
#   stale: the manifest's code-x release_tag (must match the release being cut
#   — "same-release-as-self"), and install.sh's own embedded release tag +
#   manifest checksum (its bootstrap trust root for the pipe-to-bash path).
#   This script updates all three together and prints a plain diff of what
#   changed, so nothing is re-stamped by hand.
#
#   No commit sha is stamped here (fold v1.22.4): a release commit cannot
#   contain its own sha, so code-x has no commit_sha field to stamp — the
#   release TAG is the pin, verified by install.sh via marketplace-add's
#   ref-pin syntax + a post-clone version-parity check, not a commit match.
#
# Usage:
#   installer/restamp-release.sh <release_tag>
#
# Example (run from the port session at the actual release cut):
#   installer/restamp-release.sh v1.22.5
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
MANIFEST="$HERE/installer-manifest.yaml"
INSTALL_SH="$HERE/install.sh"

RELEASE_TAG="${1:-}"
if [ -z "$RELEASE_TAG" ]; then
  echo "Usage: $0 <release_tag>" >&2
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
grep -n 'release_tag:' "$MANIFEST" | head -1 | sed 's/^/  manifest: /'
grep -n 'INSTALLER_RELEASE_TAG=\|INSTALLER_MANIFEST_SHA256=' "$INSTALL_SH" | sed 's/^/  install.sh: /'

# 1. Stamp the manifest's code-x pin (release_tag — the only self-referential
#    field left; see header note on why there is no commit_sha to stamp).
python3 - "$MANIFEST" "$RELEASE_TAG" <<'EOF'
import sys, re
path, tag = sys.argv[1:3]
text = open(path).read()
text = re.sub(r'(code-x:.*?release_tag: ")[^"]*(")', r'\g<1>' + tag + r'\g<2>', text, count=1, flags=re.S)
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
grep -n 'release_tag:' "$MANIFEST" | head -1 | sed 's/^/  manifest: /'
grep -n 'INSTALLER_RELEASE_TAG=\|INSTALLER_MANIFEST_SHA256=' "$INSTALL_SH" | sed 's/^/  install.sh: /'
echo ""
echo "Re-stamped for release $RELEASE_TAG. Re-run installer/tests/run-installer-tests.sh before shipping."
