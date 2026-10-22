#!/usr/bin/env bash
# Device-only H3 regression: the first server Initial must not use an old clock.
set -euo pipefail
EMBEDDER=$1
LIBNODE=$2
LIBCXX=$3
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
DEST=/data/local/tmp/nm-quic-smoke
adb shell "mkdir -p $DEST"
adb push "$EMBEDDER" "$DEST/node_smoke" >/dev/null
adb push "$LIBNODE" "$DEST/libnode.so" >/dev/null
adb push "$LIBCXX" "$DEST/libc++_shared.so" >/dev/null
adb push "$SCRIPT_DIR/quic-h3.js" "$DEST/quic-h3.js" >/dev/null
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
  -subj /CN=localhost -addext subjectAltName=DNS:localhost \
  -keyout "$RUNNER_TEMP/quic-key.pem" -out "$RUNNER_TEMP/quic-cert.pem" -days 1
adb push "$RUNNER_TEMP/quic-key.pem" "$DEST/key.pem" >/dev/null
adb push "$RUNNER_TEMP/quic-cert.pem" "$DEST/cert.pem" >/dev/null
adb shell "chmod 755 $DEST/node_smoke"
OUTPUT=$(adb shell "cd $DEST && LD_LIBRARY_PATH=$DEST TMPDIR=$DEST timeout 30 ./node_smoke --experimental-quic quic-h3.js; echo QUIC_EXIT:\$?")
echo "$OUTPUT"
grep -q NODEJS_MOBILE_QUIC_H3_OK <<< "$OUTPUT"
grep -q QUIC_EXIT:0 <<< "$OUTPUT"
