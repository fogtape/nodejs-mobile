#!/bin/bash

set -e

ROOT=${PWD}

if [ $# -lt 2 ]; then
  echo "Requires a path to the Android NDK and an SDK version number (optionally: target arch)"
  echo "Usage: android_build.sh <ndk_path> <sdk_version> [target_arch]"
  exit 1
fi

ANDROID_SDK_VERSION="$2"

SCRIPT_DIR="$(dirname "$BASH_SOURCE")"
cd "$SCRIPT_DIR"
SCRIPT_DIR=${PWD}

cd "$ROOT"
cd "$1"
ANDROID_NDK_PATH=${PWD}
cd "$SCRIPT_DIR"
cd ../

# Keep RELRO padding and load segments compatible with 16 KB devices, including
# local builds that do not inherit the CI job's linker flags.
export LDFLAGS="${LDFLAGS:-} -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384"

BUILD_ARCH() {
  # Clean previous compilation
  make clean
  rm -rf android-toolchain/

  # Android links a prebuilt static OpenSSL 4.x tree (see docs/OPENSSL-4.md
  # on the recipe branch). NODEJS_MOBILE_ANDROID_OPENSSL=0 keeps the bundled
  # 3.5.x path for comparison builds.
  if [ "${NODEJS_MOBILE_ANDROID_OPENSSL:-1}" != "0" ]; then
    NODEJS_MOBILE_ANDROID_OPENSSL_DIR=$(bash "$SCRIPT_DIR/android_openssl.sh" "$ANDROID_NDK_PATH" "$ANDROID_SDK_VERSION" "$TARGET_ARCH")
    export NODEJS_MOBILE_ANDROID_OPENSSL_DIR
  fi

  # Compile
  eval '"./android-configure" "$ANDROID_NDK_PATH" $ANDROID_SDK_VERSION $TARGET_ARCH'
  make -j $(getconf _NPROCESSORS_ONLN)

  # Move binaries
  TARGET_ARCH_FOLDER="$TARGET_ARCH"
  if [ "$TARGET_ARCH_FOLDER" == "arm" ]; then
    # Use the Android NDK ABI name.
    TARGET_ARCH_FOLDER="armeabi-v7a"
  elif [ "$TARGET_ARCH_FOLDER" == "arm64" ]; then
    # Use the Android NDK ABI name.
    TARGET_ARCH_FOLDER="arm64-v8a"
  fi
  mkdir -p "out_android/$TARGET_ARCH_FOLDER/"
  OUTPUT1="out/Release/lib.target/libnode.so"
  OUTPUT2="out/Release/obj.target/libnode.so"
  if [ -f "$OUTPUT1" ]; then
    cp "$OUTPUT1" "out_android/$TARGET_ARCH_FOLDER/libnode.so"
  elif [ -f "$OUTPUT2" ]; then
    cp "$OUTPUT2" "out_android/$TARGET_ARCH_FOLDER/libnode.so"
  else
    echo "Could not find libnode.so file after compilation"
    exit 1
  fi
  if [ "${NODEJS_MOBILE_ANDROID_OPENSSL:-1}" != "0" ]; then
    # Prove the artifact really carries the external OpenSSL line.
    grep -a -o -m1 'OpenSSL 4\.0\.[0-9]*' "out_android/$TARGET_ARCH_FOLDER/libnode.so" \
      || { echo "libnode.so does not embed the external OpenSSL 4.x build" >&2; exit 1; }
  fi
  # Keep the linked build output for debugging; only trim the copied lite SDK.
  if [ "${NODEJS_MOBILE_FLAVOR:-full}" = "lite" ]; then
    python3 tools/strip-android-runtime.py --ndk "$ANDROID_NDK_PATH" \
      "out_android/$TARGET_ARCH_FOLDER/libnode.so"
  fi
  python3 tools/check-android-elf.py "out_android/$TARGET_ARCH_FOLDER/libnode.so"
}

if [ $# -eq 2 ]; then
  TARGET_ARCH="arm"
  BUILD_ARCH
  # TARGET_ARCH="x86"
  # BUILD_ARCH
  TARGET_ARCH="arm64"
  BUILD_ARCH
  TARGET_ARCH="x86_64"
  BUILD_ARCH
else
  TARGET_ARCH=$3
  BUILD_ARCH
fi

source $SCRIPT_DIR/copy_libnode_headers.sh android

cd "$ROOT"
