# Node 26.11 upstream PR preview

This recipe previews official Node.js release proposal
[#66546](https://github.com/nodejs/node/pull/66546), titled
`2026-10-07, Version 26.11.0 (Current)`. At preparation time on 2026-10-06,
it was open and in draft, with no official `v26.11.0` tag.

`upstream-base.txt` pins the proposal's exact commit:
`7f68d75ee7963cd38ddc3783dd529f826bbde614`.
The upstream version header reports `v26.11.0`; the mobile header reports
`26.11.0-0`. These identifiers do not mean the official release or a mobile
release has been published. The immutable commit and expected source-tree
checksum identify this preview even if the proposal branch changes.

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
  It reconstructed tree `a92053298021a6780ac09b4c31653fc210d68ec8`.
- 38 local regression tests passed: immutable SHA/tag/cache cloning (4),
  flavor/ICU contracts (5), Rust/libffi toolchain actions (5), embedded verdict
  isolation (6), real shared-library symbol stripping (1), release control (17).
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

Complete Android/iOS compilation, newly added device tests and final artifact
size measurements remain CI work. The local checks do not establish that new
mobile binaries have passed device testing.

## Move to the official release

After upstream publishes `v26.11.0`, compare its commit against this pin,
review any additional changes, update `upstream-base.txt` to the official tag,
regenerate the recipe and checksum, and rerun the platform/device gates.
The SHA baseline is deliberately rejected by Cut release and manual
prerelease publication. This upgrade does not include a release-ready marker.
Follow [RELEASING.md](RELEASING.md) after the official-tag upgrade is reviewed.
