#!/usr/bin/env bash
# Clone an upstream tag/branch or an immutable PR commit, without inventing tags.
# Usage: scripts/clone-upstream.sh <repository> <ref-or-full-sha> <destination>
set -euo pipefail

REPO=$1
REF=$2
OUT=$3
[ ! -e "$OUT" ] || { echo "error: $OUT already exists" >&2; exit 1; }

if [[ "$REF" =~ ^[0-9a-f]{40}$ ]]; then
  git init -q "$OUT"
  git -C "$OUT" remote add origin "$REPO"
  git -C "$OUT" fetch --depth 1 origin "$REF"
  git -C "$OUT" checkout -q --detach FETCH_HEAD
  GOT=$(git -C "$OUT" rev-parse HEAD)
  [ "$GOT" = "$REF" ] || { echo "error: upstream commit mismatch: $GOT != $REF" >&2; exit 1; }
else
  git clone --depth 1 --branch "$REF" "$REPO" "$OUT"
fi
# Local metadata for the in-tree test audit, including unreleased PR snapshots.
git -C "$OUT" update-ref refs/nodejs-mobile/upstream-base HEAD
