# Node 26.11 upstream PR preview

This recipe previews official Node.js release proposal
[#66546](https://github.com/nodejs/node/pull/66546), titled
`2026-10-07, Version 26.11.0 (Current)`. At preparation time on 2026-10-06,
it was open and ready for review, with no official `v26.11.0` tag.

`upstream-base.txt` pins the proposal's exact commit:
`49072a0be4c7410982557aebf5b5c924fe7db597`.
The upstream version header reports `v26.11.0`; the mobile header reports
`26.11.0-0`. These identifiers do not mean the official release or a mobile
release has been published. The immutable commit and expected source-tree
checksum identify this preview even if the proposal branch changes.

The refreshed pin includes HdrHistogram 0.12.0, NSS 3.129 certificate source
data, WebCrypto WPT and test426 fixture updates, plus the Alpine support
documentation added after the initial `7f68d75ee7` preview. The certificate
source update does not change `src/node_root_certs.h`. V8, ICU, Temporal,
FFI and the existing mobile/lite configuration are unchanged by this refresh.

## Build and inspect

Use `upgrade/node26.11-mobile-lite` for this preview. The Node 24 `recipe`
line and maintained Node 26.10 release assets remain independent.

```sh
git clone -b upgrade/node26.11-mobile-lite https://github.com/fogtape/nodejs-mobile.git
cd nodejs-mobile
scripts/prepare.sh
```

For platform builds, follow [BUILDING.md](BUILDING.md). Reconstruction,
the CI source cache and per-patch configure checks all accept the full SHA;
no local release tag is fabricated. The test audit uses a local Git ref
recording the upstream commit, outside the source tree.

## Flavor contract

Upstream upgrade PRs build and boot-smoke both iOS flavors, and preview
package names use the recorded mobile version. SHA baselines are verified
against the official repository without requiring a release ancestry branch.

Full retains complete ICU data, Temporal and FFI, with the existing mobile
Rust/libffi integration. The 26.11 rebase also preserves upstream's new
Temporal zoneinfo source generator and the iOS platform guards.

Lite carries forward the reviewed [danmu contract](DANMU-LITE.md): the ICU
API with all Node web encoding converters, selected English/Chinese/Cantonese/
Japanese/Korean locale families, Unicode normalization/IDNA, time zones and
segmentation. Temporal, FFI, Amaro, Inspector, SQLite/Web Storage, SEA and
native object-print helpers remain disabled. Android retains JIT/native
WebAssembly and pointer compression on 64-bit targets. iOS retains jitless
V8 and polywasm without pointer compression. Android lite strips non-runtime
symbols only after confirming the dynamic exports remain unchanged.

The actual 26.11 ICU profile generation retained its required resources and
passed package dependency validation: **33,107,952 → 11,026,480 bytes**.
The 22,081,472-byte reduction measures ICU data, not a compiled libnode or ZIP.

## Validation

- A fresh shallow fetch from `nodejs/node` applied all 22 regenerated patches
  directly; regeneration from that fresh tree preserved every recipe byte.
  The current recipe reconstructs tree
  `366de32e0018c646ea07608448b694716229b35b` after the upstream refresh and Android test correction
  described below.
- 39 local regression tests passed: immutable SHA/tag/cache/CI baseline checks (5),
  flavor/ICU contracts (5), Rust/libffi toolchain actions (5), embedded verdict
  isolation (6), real shared-library symbol stripping (1), release control (17).
- Six additional Android shard regressions passed, including exact coverage
  of all 4,125 runnable cases in 16 shards of 257–258 tests, and a failing
  test process retaining its nonzero exit status through logging and cleanup.
  The actual Node status parser verifies watch-mode CLI exclusions on both
  mobile platforms while retaining in-process debugger/filesystem tests and
  leaving the two CLI tests runnable on desktop Linux.
  HdrHistogram 0.12.0 compiled on Termux arm64 and passed recording,
  percentile, bounds, extreme-value and four-thread atomic-recording probes.
- Recipe ownership, YAML/shell/JavaScript syntax, all 219 curated test entries,
  zero upstream workflows and the test-edit audit passed.
- All ten full GYP graphs generated successfully: Android arm/arm64/x64 and
  iOS arm64 device/simulator, each in full/lite. Config assertions confirmed
  full ICU, the Temporal/FFI split and Android-only 64-bit lite pointer
  compression. This is graph validation using Termux Clang and Rust version
  stubs; it does not compile with the Linux NDK or Xcode toolchains.
- Eleven new in-process Buffer, HTTP, crypto, stream and compression tests
  were added to the curated device gate. The new subprocess exclusions
  (11 parallel tests and one sequential test per platform) are inferred from
  their code; the full device suite must confirm them. The renamed VFS load
  exclusion was updated. Existing bench/negative-zero tests retain their
  in-process assertions and skip only the child startup checks.

[Build run 37410879823](https://github.com/fogtape/nodejs-mobile/actions/runs/37410879823)
completed all ten Android/iOS full/lite compilations, both platforms' full/lite
boot smokes, Android full/lite curated tests and iOS full curated tests
successfully. Recipe reconstruction and per-patch configure checks also passed.

The Android full-suite attempt was incomplete: shards 0, 1 and 2 received
`The runner has received a shutdown signal` before completing or uploading
their summaries. Shards 1 and 2 also exposed missing debugger CLI exclusions:
`test-debugger-backtrace`, `test-debugger-exec` and
`test-debugger-restart-message` launch `process.execPath` through
`test/common/debugger.js`. In an Android app this starts `app_process`, whose
child aborted with `Error changing dalvik-cache ownership : Permission denied`.
The recipe now excludes those three tests and the same subprocess-dependent
`test-debugger-low-level` and `test-debugger-repeat-last` on Android. The
in-process `test-debugger-run-restart-init` and `test-debugger-wait-for-debugger`
remain runnable. Node's actual status-file parser verified that distinction.

These exclusions correct test applicability; they do not explain the runner
shutdowns. The next [Build run 37441663775](https://github.com/fogtape/nodejs-mobile/actions/runs/37441663775)
again passed all ten builds, boot smokes and curated gates. Android shards
1, 2 and 3 then lost their runners with 514, 559 and 470 passed tests and
zero failed tests; QEMU reported unresponsive threads in two of those logs.
All four iOS full-suite shards passed. No new test exclusion is justified by
the Android failures.

The Android full suite now uses 16 deterministic shards, with four jobs at
most running concurrently, to limit the number of app relaunches per emulator.
APK assembly uses Gradle's `--no-daemon --max-workers=2`, so its JVM exits
before the sweep. The AVD has explicit 2048 MB RAM / 256 MB Java heap settings.
The shard wrapper records host/guest memory, disk and process statistics at
startup, every minute and exit, in both the live job output and an artifact.
Its pipefail exit status retains actual test failures. The integrity gate
checks the workflow denominator and uses Node's actual test selector to verify
that every runnable parallel/sequential test appears exactly once.

The runner logs do not prove an out-of-memory cause. These changes reduce
session length and resource contention and provide evidence for a future
failure. A complete device-suite rerun is still required before merge.
Final artifact size measurements are separate from the ICU data measurement.

The [refreshed Build run 37473151347](https://github.com/fogtape/nodejs-mobile/actions/runs/37473151347)
passed all ten builds, boot smokes and curated gates. All 16 Android shards
finished without a runner shutdown; 14 passed, while shards 8 and 9 exposed
two further CLI tests, `test-watch-mode-inspect` and `test-watch-mode`. Their
independent child Node attempts failed with dalvik-cache permission errors
and SIGABRT. Android now excludes those two specific tests. iOS already
excluded `test-watch-mode`; `test-watch-mode-inspect` now has the same
child-process exclusion because `NodeInstance` uses a separate executable.
The simulator permitted that spawn, which a shipped iOS app cannot use.

All four iOS shards passed their test sweeps. Shard 0's 1,015 passing tests
were followed by `Failed to CreateArtifact: Unable to make request: ENOTFOUND`
from the diagnostic log upload, causing the job and full-suite gate to fail.
The log action now retries once after 15 seconds, using a distinct retry name
to avoid a partial-upload collision. If both attempts fail, it emits a warning
and a job-summary note; the live test log and preceding summary remain
available. Only diagnostic log uploads are best effort: test execution and
binary-artifact uploads remain required. These corrections require another
complete device-suite run.

## Move to the official release

After upstream publishes `v26.11.0`, compare its commit against this pin,
review any additional changes, update `upstream-base.txt` to the official tag,
regenerate the recipe and checksum, and rerun the platform/device gates.
The SHA baseline is deliberately rejected by Cut release and manual
prerelease publication. This upgrade does not include a release-ready marker.
Follow [RELEASING.md](RELEASING.md) after the official-tag upgrade is reviewed.
