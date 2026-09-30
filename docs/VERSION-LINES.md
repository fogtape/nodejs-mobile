# Maintained version lines

Each Node.js major has its own recipe branch. The upstream tag, mobile
patches, additional sources, source-tree checksum and build toolchain are
versioned together on that branch.

| Branch | Upstream base | Purpose | Outputs |
| --- | --- | --- | --- |
| `recipe` | Node.js 24.21.0 | Stable Node 24 maintenance and releases | Android and iOS, full and lite |
| `recipe-v26` | Node.js 26.10.0 | Independent Node 26 maintenance and prereleases | Android and iOS, full and lite |

The authoritative base is always `upstream-base.txt` on the selected branch.
Updating Node 26 does not change the Node 24 recipe or replace its published
release assets. The release ancestry refs are also independent:
`upstream-base` for Node 24 and `upstream-base-v26` for Node 26 (only needed
when preparing that line for publication). Shared fixes can be cherry-picked
between the branches after testing against each branch's upstream base. Do not merge an entire Node 26
upgrade into the Node 24 branch.

## Build a selected line

```sh
git clone --branch recipe-v26 https://github.com/fogtape/nodejs-mobile.git
cd nodejs-mobile
scripts/prepare.sh
cd out
./tools/android_build.sh "$ANDROID_NDK_HOME" 24 arm64
```

Use `--branch recipe` for Node 24. Build Android on Linux and iOS on
macOS/Xcode; see [BUILDING.md](BUILDING.md). Use a separate checkout for
each line because the materialized source and compiler outputs belong to
one upstream base.

In GitHub Actions, select **Build**, then choose the desired branch in
**Run workflow**. Pushes to either maintained branch also run its build.
The **Verify recipe branch** workflow checks the selected branch's patch
partition and expected source-tree checksum.

## Node 26 configuration

The Node 26 line uses Android NDK r29 (`29.0.14206865`) and Clang 19 for
Linux host tools. Node 24 keeps its existing NDK r27d configuration.

Node 26.10 full builds enable V8 Temporal and the experimental `node:ffi`
module on Android and iOS. The build requires Rust **1.86.0** and its standard
libraries for the chosen mobile targets. Cargo builds the locked, vendored
Temporal crates separately for native host tools and the mobile runtime;
Android archives use the matching NDK compiler driver and position-independent
code. iOS frameworks link only the target Rust archive, alongside `libffi`,
`libnode_base`, and `libncrypto_engine`.

Lite builds enable `node:ffi` but retain `--with-intl=none` and explicitly
disable Temporal, which currently requires bundled ICU. They do not need Rust.
iOS libffi uses its precompiled executable trampoline table for native-to-JS
callbacks rather than generating executable callback code at runtime. Boot
smokes exercise C calls, native callbacks, and Temporal date/timezone behavior;
physical-device validation is still a separate consumer responsibility.

iOS keeps its jitless V8 configuration and WebAssembly polyfill. The Node 26
patches also guard a Wasm-only V8 postmortem metadata offset so the generated
debug support compiles with native WebAssembly disabled. Native
addons using V8 or the Node C++ API must be rebuilt for Node 26. Test
Node-API addons against the chosen platform and flavor as well.

## Download and identify a build

Published Node 24 assets and Node 26 prereleases use separate versioned
entries on the repository's
[Releases page](https://github.com/fogtape/nodejs-mobile/releases).
Each release includes four platform/flavor archives and a SHA256SUMS file.

For Node 26 previews, open a successful **Build** run on `recipe-v26` and
download its artifacts. Versioned preview packaging requires the build,
boot smokes, curated tests and full device suites to succeed. The combined
artifacts are:

- `nodejs-mobile-android`
- `nodejs-mobile-android-lite`
- `nodejs-mobile-ios`
- `nodejs-mobile-ios-lite`

Artifact names are scoped to a workflow run. Keep the branch, commit and
run URL with the downloaded files; do not mix platform slices or flavors
from different runs. Versioned preview packages additionally contain
`BUILD-INFO.json` and are accompanied by `SHA256SUMS`.

`process.version` reports `v26.10.0`; `process.versions.mobile` identifies
the mobile build revision. A CI preview is not a published release. **Cut release** also supports
`recipe-v26`; its reviewed PR arms a specific version for publication after
the complete gate chain succeeds. See [RELEASING.md](RELEASING.md).

## Upgrade one line

Start from the corresponding recipe branch, update its upstream base,
resolve patches in a materialized tree, regenerate the recipe, update
`expected-tree.txt`, and run that line's builds and device tests. See
[UPGRADING.md](UPGRADING.md). Open maintenance PRs against the same line.

Keep release tags and filenames versioned (`vX.Y.Z-R` and
`nodejs-mobile-<platform>[-lite]-X.Y.Z-R.zip`). Never reuse a Node 24 tag or
asset name for Node 26.
