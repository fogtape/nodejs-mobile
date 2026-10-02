# danmu_api runtime contract

Current recipes build full ICU into full and lite on Android and iOS. This is
required by the core's `TextDecoder('gbk')` source requests,
`localeCompare(..., 'zh-CN')` resource sorting and `normalize('NFKC')` title keys.
Default small-ICU data does not provide the required legacy decoders or Chinese
collation; an ICU data-file override cannot fix a runtime built without ICU.

Lite removes Amaro, Inspector, SQLite/Web Storage, SEA executable packaging
and V8 native-debugger object-print support. Node 26 lite also removes Temporal
and FFI. Core JS/MJS/CJS modules and the pure `@dan-uni/dan-any` UniDB do not
require these features. OpenCC remains a JavaScript dependency.

Keep HTTP/HTTPS/TLS/crypto, DNS, fetch/Undici, WebAssembly, compression including
Brotli/zstd, filesystem/module loading, streams, AsyncLocalStorage and the
existing Worker/child-process APIs. The core and Android/Flutter hosts use
these capabilities. WASI/HTTP2 are not separately trimmed in this change.

Android retains JIT/native WASM. Lite uses pointer compression only on 64-bit
Android; it primarily reduces heap memory and changes the direct V8-addon ABI.
iOS retains its existing jitless/polywasm setup without pointer compression.

## Validation

After materialization, run from the recipe directory:

```sh
python3 scripts/test-mobile-flavors.py out
```

This invokes Android's configure wrapper for full/lite on arm, arm64 and
x86_64 using a configure recorder, evaluates the real iOS flavor/archive
selection, and runs the shipped ICU regression assertions on host Node.
It checks configuration and archive consistency, not a cross-compilation.

The Android and iOS boot smokes run the same ICU assertions on freshly built
artifacts and verify the expected optional feature set. Node 26 full still
exercises native FFI calls/callbacks and Temporal date/timezone behavior;
lite asserts those features are absent. Existing fetch and curated device
tests continue to cover networking and the WASM implementation.

Previously published archives remain unchanged. Compile, run device tests and
measure new artifacts before releasing or updating either App's pinned URL and
checksum. Future core/dependency updates must be checked against this contract.
