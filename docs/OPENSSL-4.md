# Android OpenSSL 4.x

Android builds on this line link a prebuilt, statically linked OpenSSL 4.0.3
tree instead of Node's bundled 3.5.x. iOS and the fallback path keep the
bundled line unchanged.

Why: OpenSSL 4.0 is the first release with Encrypted Client Hello (ECH,
RFC 9849). Upstream Node still bundles 3.5.x and exposes no ECH API yet
([nodejs/node#64280](https://github.com/nodejs/node/issues/64280) is an open
tracking issue), so this change buys the *library* capability only —
node:tls / node:quic wiring is a separate, later step. `node:quic` stays
disabled exactly as before this change (`--experimental-quic` is not
passed); enabling it against a shared OpenSSL additionally needs the
ngtcp2/nghttp3 side to be provided and is not part of this change.

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
