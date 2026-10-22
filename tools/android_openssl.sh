#!/usr/bin/env bash
# Build a static OpenSSL 4.x tree for one Android ABI and print its prefix.
#
# The Android nodejs-mobile build links libnode.so against this tree through
# --shared-openssl (android_configure.py reads NODEJS_MOBILE_ANDROID_OPENSSL_DIR).
# Upstream Node bundles the OpenSSL 3.5.x line; 4.x is the prerequisite for
# ECH-capable runtimes (docs/OPENSSL-4.md on the recipe branch).
#
# Usage: tools/android_openssl.sh <ndk_path> <api_level> <arm|arm64|x86_64>
#
# Environment overrides:
#   OPENSSL4_VERSION  OpenSSL version to build (default 4.0.3)
#   OPENSSL4_SHA256   Expected tarball checksum (default: 4.0.3 release asset)
#   OPENSSL4_ROOT     Build root (default: <source tree>/../openssl4-android)
set -euo pipefail

OPENSSL4_VERSION=${OPENSSL4_VERSION:-4.0.3}
OPENSSL4_SHA256=${OPENSSL4_SHA256:-325b5c806167c13b40b1ffeadfe0248197c00eccc4cf123ec1e28d2d2fd216d9}

NDK=${1:?usage: android_openssl.sh <ndk_path> <api_level> <arm|arm64|x86_64>}
API=${2:?usage: android_openssl.sh <ndk_path> <api_level> <arm|arm64|x86_64>}
ARCH=${3:?usage: android_openssl.sh <ndk_path> <api_level> <arm|arm64|x86_64>}

case "$ARCH" in
  arm)    TARGET=android-arm ;;
  arm64)  TARGET=android-arm64 ;;
  x86_64) TARGET=android-x86_64 ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

ROOT=${OPENSSL4_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)/../openssl4-android}
SRC="$ROOT/src/$ARCH/openssl-$OPENSSL4_VERSION"
PREFIX="$ROOT/prefix/$ARCH-$OPENSSL4_VERSION"
STAMP="$PREFIX/.openssl-$OPENSSL4_VERSION.built"

if [ -f "$PREFIX/lib/libssl.a" ] && [ -f "$STAMP" ]; then
  echo "$PREFIX"
  exit 0
fi

TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/linux-x86_64"
[ -d "$TOOLCHAIN" ] || TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/darwin-x86_64"
[ -d "$TOOLCHAIN" ] || { echo "no NDK LLVM toolchain under $NDK" >&2; exit 1; }

mkdir -p "$ROOT/src/$ARCH"
if [ ! -d "$SRC" ]; then
  TARBALL="$ROOT/openssl-$OPENSSL4_VERSION.tar.gz"
  if [ ! -f "$TARBALL" ]; then
    echo "Fetching OpenSSL $OPENSSL4_VERSION..." >&2
    curl -fsSL --retry 3 --retry-delay 2 -o "$TARBALL.download" \
      "https://github.com/openssl/openssl/releases/download/openssl-$OPENSSL4_VERSION/openssl-$OPENSSL4_VERSION.tar.gz"
    mv "$TARBALL.download" "$TARBALL"
  fi
  echo "$OPENSSL4_SHA256  $TARBALL" | sha256sum -c - >&2
  tar -xzf "$TARBALL" -C "$ROOT/src/$ARCH"
fi

cd "$SRC"
export ANDROID_NDK_ROOT="$NDK"
export PATH="$TOOLCHAIN/bin:$PATH"

# no-asm mirrors the bundled builds this replaces; -fPIC because the static
# archives are linked into libnode.so; no-module/no-tests/no-docs keep the
# tree minimal. --libdir=lib: OpenSSL would otherwise install into lib64 on
# some hosts.
./Configure "$TARGET" -D__ANDROID_API__="$API" \
  no-shared no-module no-tests no-docs no-asm \
  -fPIC --libdir=lib --prefix="$PREFIX" --openssldir="$PREFIX/ssl" >&2
make -j"$(getconf _NPROCESSORS_ONLN)" >&2
make install_sw >&2
touch "$STAMP"
echo "$PREFIX"
