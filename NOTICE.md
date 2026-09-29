# Recipe provenance and mirror differences

This repository maintains its own recipe, originally imported from
`digidem/nodejs-mobile` at `de44804` (2026-09-03). Materialization downloads
source directly from official `nodejs/node`, applies this branch's patches,
overlays `mobile-src`, and checks the resulting tree against
`expected-tree.txt`. No third-party fork's binary is a build input.

The maintained branches are `recipe` (Node 24) and `recipe-v26` (Node 26).
The selected branch's `upstream-base.txt` is authoritative.

Differences from the imported recipe include:

- BrowserStack workflows were removed because this mirror has no credentials.
  Emulator/simulator boot, addon, curated and full device tests gate releases.
- There are no R2 secrets. Non-release builds persist the local sccache
  directory as an Actions cache archive, including after compilation failure.
- Completed mobile libraries may be restored on release runs with exact
  build-input keys. Shared compiler-object caches remain disabled on the
  release path. See [the cache policy](docs/BUILDING.md#the-ci-compiler-cache).
- Release source tags use parentless, verified full-source snapshot commits;
  importing upstream's complete history is unnecessary.
- Node majors have independent recipes, toolchains and release PRs. Node 26
  publication requires the version marker created by **Cut release**.
- Dependabot and the R2 credential probe from upstream are not installed.

The current patch series and fork-only sources have evolved since the import;
the repository history records those changes. Node.js and the recipe retain
their applicable license notices; see `LICENSE`.
