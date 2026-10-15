# Android OpenSSL 4.x

Android builds on this line link a prebuilt, statically linked OpenSSL 4.0.3
tree instead of Node's bundled 3.5.x. iOS and the fallback path keep the
bundled line unchanged.

OpenSSL 4 is connected to the client APIs on this branch. Android external-OpenSSL
builds enable experimental QUIC and use Node's vendored ngtcp2 OpenSSL adapter
and nghttp3; no external QUIC library or Go process is needed. iOS and the
bundled fallback still build without ECH.

## Client API (fork extension)

- `require('node:tls').ECH_SUPPORTED` reports compile-time ECH support.
- `tls.connect({ servername, echConfigList, ... })` accepts a binary
  ECHConfigList (`Buffer` or another ArrayBufferView). A supplied config is
  mandatory: certificate verification and TLS 1.3 are enforced inside OpenSSL,
  and an unaccepted ECH handshake cannot become a successful JS connection.
  `socket.echAccepted` and `socket.getECHStatus()` expose the outcome.
- `node:quic.connect(address, { servername, echConfigList, verifyPeer:'strict' })`
  applies the same policy. `await session.opened` includes `echAccepted`.
  ECH disables session-ticket 0-RTT and prevents stream creation until its
  handshake succeeds. Load the module with `--experimental-quic`.
- ECH configuration discovery/TTL, protocol selection and safe retries belong
  to the caller. No automatic plaintext-SNI fallback is implemented.

`test-mobile-ech` covers input validation, unsupported bundled builds, and
rejection without application-data leakage to an ordinary TLS server.
Implementation validation is recorded separately from the earlier build below;
that build predates these APIs and does not validate ECH/H3.

## How it is built

- `tools/android_openssl.sh` downloads the pinned release asset
  (`openssl-4.0.3.tar.gz`), verifies its SHA-256, and configures it with the
  NDK for the target ABI:
  `no-shared no-module no-tests no-docs no-asm -fPIC --libdir=lib`.
  `no-asm` mirrors the bundled builds this replaces (`--openssl-no-asm`).
  The result is a static `libcrypto.a` / `libssl.a` tree under
  `<source tree>/../openssl4-android/prefix/<abi>-<version>` (override with
  `OPENSSL4_ROOT`).
- `tools/android_build.sh` builds that tree per ABI and exports
  `NODEJS_MOBILE_ANDROID_OPENSSL_DIR`.
- `android_configure.py` passes `--shared-openssl --shared-openssl-includes=…`
  (and drops `--openssl-no-asm`, incompatible with `--shared-openssl`) and
  exports the library directory through `GYP_DEFINES`. `configure.py`'s
  `configure_library` is patched so this mode adds only the include
  directory: the normal shared-openssl path would put `-L…`/`-lssl`/`-lcrypto`
  into the global libraries, which gyp applies to host tools and pre-libnode
  targets (`node_js2c`, `nop`). `node.gypi` adds the link flags for the
  node/libnode targets themselves.
- The archives are linked into `libnode.so`; no new runtime `.so` files
  ship with the app.

## Verify

- Every Android flavor/ABI build greps the artifact for the embedded
  version and fails without it:
  `grep -a -o -m1 'OpenSSL 4\.0\.[0-9]*' out_android/<abi>/libnode.so`.
  The Build workflow repeats this after restore, so cache hits are covered.
- On device, `process.versions.openssl` reports `4.0.3`.

## Validation record

[Build run 38581872268](https://github.com/fogtape/nodejs-mobile/actions/runs/38581872268)
(2026-10-14, tree `d41435800d43f8de4c6775704f8b477e371f93ee`) passed all six
Android legs (full/lite × arm/arm64/x86_64) and all four iOS legs, both
Android boot smokes and both Android curated suites. The full device suites
are skipped on manual dispatches, so this is a preview gate, not a release
run. Every Android job re-verified the embedded version string, and a
downloaded `nodejs-mobile-android-lite` artifact carries `OpenSSL 4.0.3` in
all three ABIs. That older run had QUIC disabled and did not contain the
ECH client APIs described above.

## Fall back to the bundled line

```sh
NODEJS_MOBILE_ANDROID_OPENSSL=0 ./tools/android_build.sh <ndk-path> 24 <arch>
```

## Maintenance

- Bump `OPENSSL4_VERSION` and `OPENSSL4_SHA256` together in
  `tools/android_openssl.sh`; the Android libnode cache key includes the
  script's hash, so a stale library cannot be restored after a bump.
- Prefer the latest 4.0.x patch release; ECH API stability matters more
  than new features here.
