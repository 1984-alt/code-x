#!/usr/bin/env bash
# tip-split — reproduce the Code-X worked example end to end.
#
# What you'll see:
#   1. A complete card deck PASSES `cx check deck` (every requirement covered).
#   2. Drop ONE requirement's card, and `cx` catches it — a P0 finding: the
#      exact failure Code-X exists to prevent, a requirement silently dropped
#      when the plan was compiled into work-orders.
#
# Requires: Python 3 + PyYAML (see the repo README "Prerequisites").
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CX="$HERE/../../plugins/code-x/skills/code-x/checkers/cx"

echo "== 1. Full deck — every BUILDING requirement is covered =="
python3 "$CX" check deck "$HERE/cards" "$HERE/packet"

echo
echo "== 2. Drop REQ-004's card — cx catches the dropped requirement =="
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "$HERE/cards/card-w1-001.yaml" \
   "$HERE/cards/card-w1-002.yaml" \
   "$HERE/cards/card-w1-003.yaml" "$TMP/"
# REQ-004's card is intentionally absent from $TMP → expect a [P0].
python3 "$CX" check deck "$TMP" "$HERE/packet" || true
