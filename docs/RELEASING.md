# Release instructions

Each maintained Node major has its own release line: `recipe` for Node 24
and `recipe-v26` for Node 26. Select the intended branch in every workflow
and open its release PR against that same branch. Node 26 releases never
replace Node 24's branch, tags or assets.

## Manual version selection

The two manual workflows have separate responsibilities. **Cut release**
prepares a reviewed source/version change. **Build** explicitly requests a
prerelease or a rehearsal after that review. Ordinary pushes and PR builds
never create tags or releases, including the merge of a release PR.

### 1. Choose and review the version

Run **Cut release** (the workflow-definition branch may be `recipe` or
`recipe-v26`) with:

| Input | Example | Meaning |
|---|---|---|
| `release_line` | `recipe-v26` | Node 26; `recipe` selects Node 24. This explicitly chooses the recipe source and PR target, independently of the Run workflow branch menu. |
| `version` | `26.10.0-0` | Exact mobile version. `26.10.0` or `auto` selects the next unused revision for the line's pinned upstream. |
| `operation` | `plan` | Validate and show the plan without changing source or creating a PR. |
| `operation` | `prepare-pr` | Prepare the version header, CHANGELOG, release marker, verified source hash, and open a review PR. |

The selected upstream version must match `upstream-base.txt` on the target
line. Merge an upstream upgrade into that line first; a version input cannot
turn Node 26.1 binaries into Node 26.10. Current/legacy release tags and
existing `release/vX.Y.Z-R` branches reserve revisions. Exact taken versions
fail; no source branch or published release is overwritten.

An existing CHANGELOG section for the selected version is preserved and
dated instead of replaced with an empty TODO. New revisions receive a review
stub. Review the English notes and diff, then merge the PR. Its
`release-ready.txt` must match the version header, but the merge does not
publish anything by itself.

### 2. Run the chosen prerelease

Run **Build** on the maintained version-line branch with:

| Input | Example | Meaning |
|---|---|---|
| Branch | `recipe-v26` | Node 26; use `recipe` for Node 24. Development branches and tags cannot publish. |
| `operation` | `build` | Default: build/test only. Leave `version` empty. |
| `operation` | `prerelease-dryrun` | Run the full prerelease gates and packaging without pushing a tag or creating a GitHub release. |
| `operation` | `prerelease` | Run the same gates, then publish a GitHub prerelease. |
| `version` | `26.10.0-0` | Required for either prerelease operation; must exactly match the reviewed header, upstream and release marker. |

A cheap preflight rejects version/branch/marker/tag/notes problems before
starting compiler jobs. Publication requires both flavors on every platform,
boot and native-addon smokes, host checks, curated device tests and full device
suites from **this same run**. The publish job additionally requires
`ci-required` and the release-notes gate. A failed gate prevents publication.

The publish job uses the `release` Environment. It materializes the verified
source, packages this run's artifacts, and publishes `vX.Y.Z-R` as a GitHub
**prerelease**, with `latest=false`. Titles show the Node major line and full
mobile version, for example `Node.js 26 Current · nodejs-mobile v26.10.0-0（预发布）`.
Existing release tags retain their names so download URLs remain valid.

```sh
# Plan only. Cut release loads the selected recipe-v26 source.
gh workflow run cut-release.yml --ref recipe \
  -f release_line=recipe-v26 -f version=26.10.0-0 -f operation=plan

# After the reviewed release PR is merged into recipe-v26:
gh workflow run build.yml --ref recipe-v26 \
  -f operation=prerelease-dryrun -f version=26.10.0-0
# Change operation to prerelease only when ready to publish.
```

GitHub's web form uses workflow definitions on the default branch; shared
manual controls must be reviewed into `recipe` as well as the Node 26 line.
This does not require merging Node 26 source changes into Node 24.

The four archives are
`nodejs-mobile-{android,ios}{,-lite}-X.Y.Z-R.zip`, accompanied by
`SHA256SUMS`. Android includes arm64-v8a, armeabi-v7a and x86_64. iOS includes
arm64 device and simulator slices. Verify the checksum after downloading.

Node 26 full builds enable Temporal and `node:ffi`; the new lite recipe
omits both and retains full ICU. Already published 26.10.0-0 lite assets
have FFI and no ICU; the older 26.1 release disables both features.
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

A manual `prerelease-dryrun` rehearses the same gates without tagging or
publishing. It requires the same reviewed version, release marker and notes;
placeholder notes are not accepted even for a rehearsal. After a failed run,
fix the selected line and dispatch the same still-untagged version again.
For an interrupted publish that already created its tag, inspect and rerun
the publish job from that original release run rather than creating or
overwriting another release.
