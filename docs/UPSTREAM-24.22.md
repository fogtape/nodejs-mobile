# Node 24.22 LTS upstream PR preview

This recipe previews the official Node.js release proposal
[#66667](https://github.com/nodejs/node/pull/66667), titled
`2026-10-14, Version 24.22.0 'Krypton' (LTS)`. On 2026-10-13 it is still a
draft PR, with no official `v24.22.0` tag.

The reviewed baseline is pinned in `upstream-base.txt`:
`a5d0eb95dd03b90986ad1a7c0cd3f2de1a0f383c`.
The upstream header identifies Node 24.22.0 and the mobile header identifies
24.22.0-0. Those version strings identify the proposed source; they do not
mean that the upstream release has been published. The immutable commit and
`expected-tree.txt` identify the build if the proposal branch changes.

## Lite configuration

The upgrade retains the latest [danmu runtime contract](DANMU-LITE.md),
introduced on this line by PR #6. Both flavors use the full ICU API.
Lite uses the reviewed `danmu-lite.json` data profile with all Node web
encoding converters, selected English/Chinese/Cantonese/Japanese/Korean
locale families, Unicode normalization/IDNA, time zones and segmentation.
The profile and ICU source data are unchanged by this upstream upgrade.

Lite still omits Amaro, Inspector, SQLite/Web Storage, SEA and native V8
object-print helpers. Android keeps JIT/native WebAssembly and pointer
compression on 64-bit targets. Its SDK copy is stripped only after confirming
the dynamic exports remain identical. iOS keeps jitless V8 and polywasm,
without pointer compression. Node 26 feature choices and toolchains are
maintained separately.

## Compatibility and build gates

Upstream now defines `V8_ENABLE_WEBASSEMBLY` for Node targets and guards the
JSPI flag itself. The equivalent mobile-only guard is retired. Existing
mobile patches are rebased onto the proposal, and two new upstream workflow
files are removed from the generated product tree.

Twenty-six new in-process crypto, histogram, filesystem, HTTP/TLS, utility,
SQLite and compression regressions enter the curated gate. The new
benchmark, WPT-helper and provider-snapshot tests launch a separate Node
process and are skipped on both mobile platforms. The new permission test
cannot write the harness verdict and is also skipped. The new glob test keeps
its in-process assertions and guards only the separate permission-model
child on mobile. These decisions follow the test code; the device suites
must confirm them.

Existing Android debugger CLI tests and sequential watch CLI tests use the
same unsupported child-process path. Their exclusions carry forward the
corrections already validated on the Node 26 line. The emulator suite also
uses that line's 16 deterministic shards, four concurrent jobs, bounded
Gradle/emulator memory settings and failure-preserving log wrapper. These
changes preserve complete runnable-test coverage.

The upgrade PR compiles all ten targets: Android arm/arm64/x86_64 and iOS
arm64 device/simulator, each in full/lite. Boot smokes verify the danmu ICU
contract. Curated and full device suites run on emulators/simulators.
Successful builds produce four `*-24.22.0-0-preview.zip` packages with
`BUILD-INFO.json` and `SHA256SUMS` in the Actions artifacts. This is a CI
preview and does not create a release tag or GitHub release.

Local verification passed 34 regression tests: immutable clones/cache/CI
baseline checks (5), flavor/ICU/preview metadata (5), native symbol stripping
(1), manual release controls (17), and Android shard coverage/failure
propagation (6). The actual upstream test selector covered all 3,771 runnable
Android cases exactly once in 16 shards of 235–236 tests. All 236 curated
entries exist, patch ownership is consistent, the generated tree has no
upstream workflows, and the test-edit audit passed.

A fresh shallow fetch applied all 20 regenerated patches and reconstructed
`b1927713596da90cceebd71afada3a6af42764eb`; regeneration from that fresh tree
preserved every patch and mobile source byte. Native cross-compilation and
device execution are verified separately by CI.

All six Android GYP graphs also generated successfully (arm/arm64/x64,
full/lite), with assertions for the ICU API, WebAssembly, feature omissions
and Android-only 64-bit lite pointer compression. This configure-only check
uses Termux Clang and does not substitute for an NDK cross-compile.

## First complete device sweep and corrections

[Build run 38280763394](https://github.com/fogtape/nodejs-mobile/actions/runs/38280763394)
passed all ten platform/flavor builds, host checks, full/lite boot smokes and
Android full/lite plus iOS full curated tests. The full suites finished with
three failing Android tests and two failing iOS tests, representing four
unique cases. Every failing shard completed; there were no hung, crashed or
missing-verdict tests in those shard summaries.

- Android `test-intl` spawned `process.execPath`, which is `app_process64`
  in the embedder, and the child aborted with dalvik-cache permission errors.
  Both mobile platforms now skip only its two child startup probes. All
  in-process assertions remain; iOS's previous whole-test exclusion is removed.
- Android `test-sqlite-backup` gained a child-process subtest upstream. Only
  that subtest is skipped on both mobile platforms; the other backup and
  source-lifetime/GC regressions still run. The iOS simulator happened to allow
  the spawn, but an iOS app cannot rely on it.
- Both platforms' `test-fs-rmSync-special-char-additional-error` returned
  `ENOTEMPTY` rather than `EACCES` when removing a read-only directory. The
  mobile branch now expects the observed error while retaining every path,
  syscall, message and cleanup assertion. The unmodified failure and corrected
  pass were reproduced on Termux's Android filesystem too.
- iOS `test-internal-webidl-buffer-source` failed before executing JS because
  `--experimental-wasm-rab-integration` is compiled out of its jitless V8.
  It is now listed in the existing iOS native-WebAssembly exclusion section;
  Android and desktop still run it.

Intl, SQLite backup and the filesystem error test also enter the curated gate,
which now contains 239 cases. An Intl execution regression verifies that both
mobile branches retain all 19 in-process assertions and launch no child Node,
while the desktop branch retains both locale-startup probes. The real status
parser verifies only the iOS WASM case is excluded and the other three tests
remain runnable on every platform. No runtime/build/ICU input changed, so
compiled-library cache keys remain identical to the completed build.

The corrected source tree is
`3264ab4c31529014c7b4c5de198fdada43978027`. The next complete CI run verifies
these corrections on devices before the preview packages can be produced.

## Emulator workflow preparation

[Build run 38321165710](https://github.com/fogtape/nodejs-mobile/actions/runs/38321165710)
passed all ten builds, host checks, platform/flavor boot smokes, every curated
suite, all four iOS full-suite shards and 15 of the 16 Android shards. The
previous device-test failures were eliminated. Android shard 8 failed before
running any test: SDK Manager could not unpack its Emulator update
(`Error on ZipFile unknown archive`). Retrying that job reproduced the same
package-install failure, so the remaining red gates were infrastructure failures.

All three Android emulator entry points now use
`.github/actions/prepare-android-emulator`. It installs the exact successful
Emulator 37.2.12 build 16428233 archive from Google's repository. The reviewed
archive size (349,654,171 bytes) and SHA-1 were verified against Google's
`repository2-3.xml`; SHA-256 is pinned alongside the build ID. Cached and newly
downloaded archives must match the size/digest and pass ZIP validation before
installation. Transfer/verification retries are bounded. The extracted binary
must report the pinned version/build before the test action can start.

A narrowly scoped SDK Manager wrapper bypasses only the emulator action's
redundant `--install emulator --channel=0` call. Licenses, system images,
build/platform tools, NDK and other install requests are forwarded unchanged,
including their failure exit codes. The fixed archive is cached by its build
and digest, and a corrupt cache is rejected. Real test failures are not retried
or ignored.

Seven local regressions cover a verified cache, corrupt downloads, exhausted
retries, unchanged SDK arguments/failures, repeated preparation, broken emulator
binaries and all three workflow entry points. This is a CI-only change: the
reviewed product tree, compiled-library keys and danmu lite recipe are unchanged.

The preparation action explicitly installs `libpulse0` before validating the
emulator binary. Hosted runner images differ in their installed libraries;
the first CI validation found `libpulse.so.0` missing even though the pinned
archive's size, digest, ZIP contents and package metadata were correct.

## iOS smoke launch transport

[Build run 38334766961](https://github.com/fogtape/nodejs-mobile/actions/runs/38334766961)
passed all sixteen Android full-suite shards, both Android boot smokes and
curated flavors with the verified emulator preparation. The remaining iOS full
smoke wrote no output or verdict on three attempts using `simctl --console`;
iOS lite smoke and the same full framework's curated device suite passed.
The full iOS sweep was skipped because its smoke prerequisite failed.

The smoke launcher now follows the already validated curated proxy: launch
without a console FIFO, read the app PID, poll the per-token verdict and read
stdout from the app's sandbox file. A real `FAIL` still fails immediately;
a missing verdict never passes and retries remain bounded. Four host regressions
exercise PASS, immediate FAIL, recovery after no verdict and exhausted retries.
No Node runtime, ICU or compilation input changed. The test harness update is
included in source tree `7dd2d6b6eaf7937b6a050e715754920dcbe4c8c3`.

## Android per-test launch acknowledgement

[Build run 38337972601](https://github.com/fogtape/nodejs-mobile/actions/runs/38337972601)
passed all ten builds, both platforms' full/lite boot smokes and curated gates,
all four iOS full-suite shards and fifteen Android shards. Android shard 15
reported 234 passes and one timeout in `test-https-simple`. Its output contained
messages from an earlier TLS renegotiation test and an `am start` failure,
without a verdict from the requested test. The previous proxy ignored errors
when force-stopping the old activity, clearing logs and launching its replacement,
and discarded the launch command's diagnostic output.

The proxy now bounds each ADB call, requires the old process to be stopped and
logs to be cleared before launch, and retains failed-launch diagnostics.
MainActivity writes a per-token startup acknowledgement before starting Node.
A launch may be retried only when a successful force-stop, process query and
sandbox query prove that Node never started. Missing/failed queries cannot
authorize a retry. An acknowledged JS failure, hang or native crash is never
retried; PASS still requires the authoritative per-token verdict file.

Ten regressions exercise device targeting/output, failed force-stop, stale
activities, failed log clearing, recovery before Node starts, a lost launch
reply after Node starts, real FAIL/hang/crash, exhausted attempts and an unknown
or late startup acknowledgement. The full runnable suite and all its tests are
retained. The runtime, ICU profile and full/lite build configuration are unchanged.
The updated harness is included in source tree
`786da7b5d33a6cabb31668f3089731b3c0a62713`.

## Move to the official release

After upstream publishes `v24.22.0`, compare its commit with this baseline,
review any differences, update `upstream-base.txt`, regenerate the recipe and
checksum, and rerun platform/device validation. Follow
[RELEASING.md](RELEASING.md) for reviewed version selection and explicit
publication. A source upgrade or ordinary build does not publish by itself.
