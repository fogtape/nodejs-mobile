#!/usr/bin/env bash
set -euo pipefail

ORIGINAL="${BASH_SOURCE[0]}.nodejs-mobile-original"

# Only intercept the emulator action's single stable-emulator update. Licenses,
# system images, build tools, NDK and mixed installs are forwarded unchanged.
if [ "$#" -eq 3 ] && [ "$1" = --install ] &&
   [ "$2" = emulator ] && [ "$3" = --channel=0 ]; then
  : "${ANDROID_HOME:?ANDROID_HOME must identify the runner Android SDK}"
  VERSION=$("$ANDROID_HOME/emulator/emulator" -version 2>&1) || {
    echo "::error::The prepared Android Emulator cannot run: $VERSION" >&2
    exit 1
  }
  [[ "$VERSION" == *'Android emulator version '* ]] || {
    echo "::error::The prepared Android Emulator did not report its version" >&2
    exit 1
  }
  echo "::notice::Reusing checksum-verified Android Emulator; skipping redundant update download"
  printf '%s\n' "$VERSION"
  exit 0
fi

exec "$ORIGINAL" "$@"
