# Build Instructions

These instructions describe the Node 26 line (`recipe-v26`). For Node 24,
use the `recipe` branch and its toolchain instructions. See
[VERSION-LINES.md](VERSION-LINES.md) for the maintenance policy and the
Node 26 FFI/Temporal configuration.

nodejs-mobile builds one native library per target, and **each target builds on
one host OS only:**

| Target  | Output                       | Build host           |
|---------|------------------------------|----------------------|
| Android | `libnode.so` (per ABI)       | **Linux only**       |
| iOS     | `NodeMobile.xcframework`     | **macOS only** (Xcode) |

> **Why Android can't be built on macOS.** node's bundled gyp archives static
> libs as GNU thin archives (`ar crsT … @file-list` response files) and links
> the cross-build's *host* build-tools (e.g. `node_js2c`) with the ELF-linker
> option `-Wl,--start-group`. Apple's `/usr/bin/ar` and `ld64` support neither,
> so a macOS host fails — first at the archiver (`ar: @…ar-file-list: No such
> file or directory`), and even with `AR_host` pointed at the NDK's `llvm-ar`,
> then at the host link (`ld: unknown options: --start-group`). `--start-group`
> is ELF-only and no Mach-O linker implements it, so there is no drop-in macOS
> fix. This is a property of node's build system, not the mobile patches, and it
> affects `full` and `lite` identically. Build Android on Linux (CI uses
> `ubuntu-24.04`).

## Python (both targets)

Both build paths run gyp / V8 code generation under Python. Use a **Python 3.13**
(3.12 also works) venv with `setuptools` installed — gyp-next declares
`setuptools` as a build-time dependency and a bare venv does not bundle it. CI
does the same:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
pip install setuptools packaging
```

---

## Rust for Node 26 full builds

Full builds require Rust 1.86.0 for the vendored Temporal crates. Install the
native host toolchain plus the standard libraries for your target:

```sh
# Linux Android build host
rustup toolchain install 1.86.0 --profile minimal \
  --target armv7-linux-androideabi,aarch64-linux-android,x86_64-linux-android
# macOS iOS build host
rustup toolchain install 1.86.0 --profile minimal \
  --target aarch64-apple-ios,aarch64-apple-ios-sim
export RUSTUP_TOOLCHAIN=1.86.0
```

Cargo consumes the checked-in lockfile and vendor directory with `--frozen`.
The build action selects a native host triple for snapshot tools and a separate
mobile triple for the library. Android target archives use the supplied NDK
and SDK level; iOS target archives use the device/simulator SDK and iOS 14
minimum deployment target. Lite builds omit Temporal with ICU and need no Rust.
Both flavors include `node:ffi`.

## Android — build on Linux

### Prerequisites

```sh
sudo apt-get install -y build-essential git gcc-multilib g++-multilib clang-19
export CC_host=clang-19 CXX_host=clang++-19
```

Install Android NDK **r29** (`29.0.14206865`) via the SDK Manager (the
CI installs this exact NDK version):

```sh
sdkmanager "ndk;29.0.14206865"
```

### 1) Get a source tree

This repository holds the recipe, not the source. Generate a tree from it:

```sh
git clone -b recipe-v26 https://github.com/fogtape/nodejs-mobile
cd nodejs-mobile && scripts/prepare.sh && cd out
```

All the build commands below run from that `out/` directory. A release tag
(`vX.Y.Z-R`) already *is* a materialized tree, so checking one out works too.

### 2) Build with the helper script

```sh
./tools/android_build.sh <ndk-path> <sdk-version> [arch]
```

- `<ndk-path>` — the installed NDK, e.g. `~/Android/Sdk/ndk/29.0.14206865`
- `<sdk-version>` — minimum Android SDK version as a number, e.g. `24`
- `[arch]` — `arm`, `arm64`, or `x86_64`; omit to build all three.

```sh
./tools/android_build.sh ~/Android/Sdk/ndk/29.0.14206865 24
```

Output: `out_android/<abi>/libnode.so` for each ABI (`armeabi-v7a`, `arm64-v8a`,
`x86_64`).

To configure and build a single architecture manually instead:

```sh
./android-configure <ndk-path> <sdk-version> <arch>
make
# -> out/Release/lib.target/libnode.so
```

---

## iOS — build on macOS

### Prerequisites

Xcode with the Command Line Tools (`xcode-select --install`, which also installs
`git`).

### 1) Get a source tree

As above — `scripts/prepare.sh`, or a release tag. Commands run from `out/`.

### 2) Build with the helper script

```sh
./tools/ios_framework_prepare.sh [arm64|arm64-simulator]
```

With no argument it builds **both** arm64 slices — device (`iphoneos`) and
simulator (`iphonesimulator`) — and combines them. The script configures gyp to
build Node.js and its dependencies as static libraries with V8 set to run
jitless (Apple's no-JIT rule), staging the libs through
`tools/ios-framework/bin/` into the `tools/ios-framework/NodeMobile.xcodeproj`
project. Because iOS can never JIT, the compiled optimizer tiers are removed
outright in **both** flavors: `v8_enable_turbofan=0` swaps V8's compiler for
upstream's `turbofan-disabled.cc` stub (mksnapshot keeps the real backend to
generate builtins), `--v8-disable-maglev` drops the mid-tier, and the
snapshot-generator (`libv8_initializers`) and gtest libraries — dead weight the
`-all_load` framework link used to force in — are excluded from the link. Pass `arm64` or `arm64-simulator` to build only one slice during
development. (x86_64 / Intel-simulator support was dropped for v24: Intel Macs
are EOL and Apple Silicon runs the arm64 simulator natively.)

Node 26's static `libnode` normally leaves `GetEmbeddedSnapshotData()` for
the executable to provide. The iOS recipe includes upstream's no-snapshot
stub in the archive because the framework links that archive directly.
Dependent executables exclude their own copy to avoid duplicate symbols.
This applies to both flavors with `--without-node-snapshot`.

Output: **`out_ios/NodeMobile.xcframework`** (device + simulator arm64 slices).

---

## The lite variant

To build it instead of the default, set `NODEJS_MOBILE_FLAVOR=lite` on either
target's build command.

The build ships in two flavors (selected by `NODEJS_MOBILE_FLAVOR`, default
`full`). **`full`** is the general-purpose binary all consumers get. **`lite`**
is a smaller binary for consumers that don't need the full feature set, built by
layering feature-drops — and on Android one V8 configuration change, [pointer
compression](#pointer-compression-android-lite-only) — on top of the full
configure, so the full binary and its test gate are unchanged.

What `lite` drops (all already-available upstream `configure` flags, so no extra
patch-stack surface):

| Cut | Why it can be dropped |
|---|---|
| `--without-amaro` (TS type-stripping) | for consumers shipping plain `.js` |
| `--without-inspector` | not used in production |
| `--without-sqlite` | for consumers using the `better-sqlite3` addon, not `node:sqlite` |
| `--with-intl=none` (no ICU) | for consumers that use no `Intl.*` — verify against your own dependency tree (a dependency may reference `Intl` from a code path you never call) |
| **iOS only:** `--v8-lite-mode` | drops the compiled JIT + V8 WASM engine, both **dead on iOS** (it runs jitless; WebAssembly is served by the bundled polywasm polyfill — see [FAQ](./FAQ.md#does-fetch-work-what-about-webassembly)). This is the big lever. |

Dead-code stripping (`--gc-sections`) applies to **both** Android flavors: the
linker only discards unreferenced sections, so it costs no functionality.

Historical Node 24 shipping sizes (arm64, after symbol strip; these are
not measurements of the Node 26 port):

- **iOS:** the dead-code removal above cut the lite device slice
  **54.5 → 33.8 MB** (−38%); full shrinks by the same ~20 MB since every cut
  is flavor-neutral (its size is measured by the release CI).
- **Android:** **61.5 MB (full)** / **45.6 MB (lite)** with gc-sections on
  both flavors; no
  `--v8-lite-mode` (Android keeps the JIT and V8's native WASM for undici).

Those figures were measured before pointer compression was turned on for
Android; it aims at the heap rather than at the binary, and the release CI
re-measures the shipping artifacts on every release.

`build-id` (`-Wl,--build-id=sha1`) is emitted on the Android `libnode.so` in
**both** flavors so crash reporters (e.g. Sentry) can symbolicate native
crashes. The safeguard for `intl=none` is running your own application's test
suite against the lite binary — it catches `Intl` breakage from future
dependency changes.

### Pointer compression (Android lite only)

Android `lite` also configures V8 with
`--experimental-enable-pointer-compression`. V8 then stores tagged pointers as
32-bit offsets from a per-isolate 4 GB *cage* base instead of as full 64-bit
addresses, so every object field, array element and map slot on the JS heap
halves. The lever here is **runtime memory, not file size**: V8's own
measurements put the saving at roughly 40% of the JS heap
([v8.dev/blog/pointer-compression](https://v8.dev/blog/pointer-compression)),
which on a phone is the margin between staying resident and being reaped by the
low-memory killer.

**iOS does not get it** — the cage reservation cannot succeed there at all; see
[iOS cannot reserve the cage](#ios-cannot-reserve-the-cage) below.

Why it is `lite`-only on Android, when the flag is available to both flavors:

- **It changes the V8 ABI.** A native addon that includes V8's headers directly
  (`v8.h`, NAN, node-addon-api's V8 escape hatches) has to be compiled with the
  same defines as the library it loads into — `V8_COMPRESS_POINTERS` and
  `V8_31BIT_SMIS_ON_64BIT_ARCH`, the two the public V8 headers branch on.
  Mismatched, it reads object fields at the wrong offsets and corrupts the
  heap. The artifact ships headers without a `config.gypi`, so those
  defines have to be passed by hand; see the
  [FAQ](./FAQ.md#are-nodejs-native-modules-supported). **N-API
  addons are unaffected**: that ABI hides V8's object layout, it is what
  `libnode.so` exports, and it is what the addon gate (`crc-native`, see
  [TESTING.md](./TESTING.md#the-napi-addon-gate)) builds and loads. `full` is
  the binary every consumer gets by default, so it keeps the upstream-standard
  ABI; `lite` is opt-in, and its consumers are the ones trading compatibility
  for footprint.
- **It caps the JS heap at 4 GB** and is still flagged `--experimental-` upstream
  — neither costs anything on a device whose whole budget is a fraction of that,
  but both are reasons not to impose it on the default binary.

**64-bit slices only.** Upstream's `common.gypi` force-disables pointer
compression for `target_arch in "arm ia32 mips mipsel"`, so the Android
`armeabi-v7a` slice cannot have it, and passing the flag there would build the
same uncompressed library either way. `android_configure.py` gates it on
`arm64`/`x64` anyway, because that upstream guard zeroes the gyp variable but
not the copy `configure` already wrote into `config.gypi`: ungated, a 32-bit
lite build would ship a `process.config` claiming compression it doesn't have —
`tools/test.py` derives its `$pointer_compression` status variable from exactly
that, and `test-max-old-space-size-percentage` and
`test-experimental-shared-value-conveyor` branch on it.

Each isolate (the main one, plus one per `Worker`) reserves its own cage, so
the cost is 4 GB of *address space* per isolate. Node's shared-cage mode
(`--experimental-pointer-compression-shared-cage`) is deliberately left off,
matching upstream's default.

#### iOS cannot reserve the cage

The address space that costs nothing on Android is exactly what iOS will not
hand out, so the flag is **not** passed in `tools/ios_framework_prepare.sh`.

V8 does not ask for 4 GB. The cage has to be 4 GB-*aligned* as well as
4 GB long, and V8 gets that alignment by over-reserving and trimming —
`OS::Allocate` in `deps/v8/src/base/platform/platform-posix.cc` requests
`size + (alignment - page_size)`, so one `mmap` of just under **8 GB**,
`PROT_NONE`, before it unmaps the misaligned head and tail.

An iOS process does not have 8 GB of address space to give. Without the
[`com.apple.developer.kernel.extended-virtual-addressing`](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.kernel.extended-virtual-addressing)
entitlement the kernel caps a process at `ARM64_MIN_MAX_ADDRESS`-derived
limits — **7.375 GB** usable on devices with more than 3 GB of RAM, and less
below that, after the 4 GB `PAGE_ZERO` and the 4 GB shared region are taken out
([the arithmetic, with the kernel
constants](https://alwaysprocessing.blog/2022/02/20/size-matters)). The
reservation is therefore larger than the entire address space of the process
and fails on every device, not marginally and not only on small ones.
`VirtualMemoryCage::InitReservation` returns false and
`IsolateGroup::Initialize` calls `V8::FatalProcessOutOfMemory(... "Failed to
reserve virtual memory for process-wide V8 pointer compression cage")`, which
aborts the process during `Isolate` init — i.e. the app crashes a second into
launch, before any embedder JS runs.

The entitlement would lift the cap ("jumbo mode", full 64-bit address space),
but it is not something a runtime library can require: it is a restricted
capability that every consuming app would have to add to its own provisioning
profile, and it would still spend 4 GB of address space per isolate. Shipping
iOS `lite` uncompressed is the cheaper trade.

This is invisible to the iOS **simulator**, which is a macOS process and has no
such cap — the simulator legs of `curated-tests-ios` pass on a build that
cannot start on any physical device. Treat iOS simulator green as no evidence
at all about address-space behaviour.


---

## The CI compiler cache

There are two distinct caches in `build.yml`:

1. **Completed libraries:** Android `out_android` and each iOS framework slice
   use exact keys covering the source/dependency trees, build scripts and
   target settings. A hit skips compilation. Test-only and documentation-only
   changes retain these keys; changes to `node.gyp`, compiler settings or
   runtime sources invalidate them. Never add a broad restore prefix to a
   completed-library cache: that could restore an obsolete binary.
2. **Compiler objects:** non-release jobs use sccache. This mirror has no R2
   credentials, so its backend is a local directory. The
   `restore-compiler-cache` action restores that directory from an Actions
   cache archive before compilation; `Save compiler objects` persists it even
   if a later compilation or link fails. Previously the directory existed
   only on the disposable runner, causing essentially cold rebuilds.

Object archives are separated by Node major, runner OS/CPU, platform,
architecture, flavor and toolchain fingerprint. Each run attempt writes an
immutable key, and subsequent attempts restore the newest matching prefix.
Sccache still checks each compiler invocation and source contents; an object
cache hit is not a reason to skip compilation of changed input. The local
cache is capped at 2 GB per job. Actions storage quotas and eviction can
reduce reuse, so a cache is an optimization, never a build prerequisite.
One archive upload per job also avoids the per-object request volume of
sccache's direct GitHub Actions backend.

The optional R2 configuration remains supported. If R2 credentials are
installed, use separate read and write tokens and restrict the write
Environment to trusted maintenance branches. The local archive fallback
needs no cloud secrets.

### Releases and provenance

As documented in this mirror's `NOTICE.md`, completed mobile libraries may
be reused on release runs when their exact input key matches. The library
matrix still uploads the restored files into the current run, and that run
must pass its boot, addon, curated and full device gates before publication.

Release and `release-dryrun:` jobs do not restore compiler-object archives,
use sccache, or expose R2 credentials. A missing completed-library key
therefore causes a cold compile. The host verification binary currently has
no completed-binary cache and is rebuilt on the release path. The first
release can still take hours even with mobile-library hits; full device
suites also take time independent of compilation.

This policy reuses exact mobile build outputs, not arbitrary compiler
objects on the publish path. The release notes must accurately identify the
recipe commit, tests performed and missing physical-device coverage.

### Diagnosing a slow run

- Check `Restore built libnode` first. A hit should skip `Build`.
- On a normal build miss, inspect `Restore compiler objects` and
  `sccache stats`: the cache location, hit count and miss count show whether
  the persisted backend was actually reused.
- `Save compiler objects` runs after a failed build too, provided the runner
  was not cancelled. Cancelled jobs may lose newly compiled objects.
- Changing source/build inputs, changing the runner toolchain, storage
  eviction and the first run of a new version all cause legitimate misses.
- A green compile does not mean a green release. Emulator/simulator tests
  consume the compiled artifacts and retain their own runtime cost.
