# Release instructions

Each maintained Node major has its own release line: `recipe` for Node 24
and `recipe-v26` for Node 26. Select the intended branch in every workflow
and open its release PR against that same branch. Node 26 releases never
replace Node 24's branch, tags or assets.

## Cut, review and publish

1. Run **Cut release** on the selected branch. The workflow derives the
   upstream version from `upstream-base.txt`, selects the next unused mobile
   revision, updates the version header, creates a CHANGELOG review stub,
   reconstructs the source checksum and opens a release PR.
2. Fill in the English CHANGELOG entry, review the PR and merge with squash
   or rebase. The PR also writes `release-ready.txt` with the version to
   publish. On Node 26, this marker must match the version header before any
   push may publish; normal port updates do not arm a release.
3. The merge push runs both flavors for every platform, boot and native-addon
   smokes, host tests, curated device tests and full device suites. A failed
   gate prevents publication. Fix the selected branch; the next push retries
   the still-unreleased version.
4. The publish job runs in the `release` Environment, materializes the exact
   verified source tree, packages the current run's artifacts and publishes
   `vX.Y.Z-R` as a GitHub **prerelease**, with `latest=false`.

The four archives are
`nodejs-mobile-{android,ios}{,-lite}-X.Y.Z-R.zip`, accompanied by
`SHA256SUMS`. Android includes arm64-v8a, armeabi-v7a and x86_64. iOS includes
arm64 device and simulator slices. Verify the checksum after downloading.

The initial Node 26 port disables `node:ffi` and Temporal in both flavors;
iOS uses jitless V8 and the bundled WebAssembly polyfill. See
[VERSION-LINES.md](VERSION-LINES.md) for compatibility limits.

## Source tags and provenance

Tags point at full-source snapshot commits whose tree matches
`expected-tree.txt`. These mirror-local commits have no parents, avoiding a
shallow-history push that depends on importing all upstream Node history.
The source snapshot records its upstream version and recipe commit. The
annotated tag also carries `Recipe-Commit` and `Source-Tree` trailers, and
the release body links the recipe commit.

Do not push release tags or upload assets manually. The pipeline is the
publisher and its prerequisite jobs enforce validation. Draft-first asset
upload keeps an incomplete release from being published. This mirror has no
BrowserStack credentials: device builds are compiled, while runtime tests
run on Android emulators and iOS simulators. Do not claim physical-device
validation in release notes.

## Build time and cache policy

This mirror reuses completed mobile libraries only when their exact build
input keys match. A test-only fix can therefore rerun the device gates
without recompiling Node. The release path does not use shared compiler
objects or R2 credentials; a mobile-library cache miss builds cold. Host
verification also builds cold because it has no completed-binary cache.
See [BUILDING.md](BUILDING.md#the-ci-compiler-cache).

`release-dryrun:` rehearsals on an armed release line run the same gates
without tagging or publishing. An untagged version is retried after a fix;
for an interrupted publish that already created its tag, inspect and rerun
the publish job from that release run instead of creating a second version.
