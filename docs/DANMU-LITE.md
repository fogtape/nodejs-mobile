# danmu_api runtime contract

Full builds embed complete ICU data. Lite keeps the complete ICU API mode
(`--with-intl=full-icu`, `icu_small=false`) but embeds a reviewed data profile
from `tools/icu/danmu-lite.json`. Do not substitute Node's default small-ICU
filter: it removes legacy encoding converters and does not satisfy the core.

## ICU data retained by lite

- Every web encoding exposed by Node's TextDecoder, including GBK/GB2312,
  GB18030, Big5, Shift-JIS, EUC-JP, ISO-2022-JP, EUC-KR, European/Windows
  encodings and their label aliases. Converter dependency tables are kept too.
- English, simplified/traditional Chinese, Cantonese, Japanese and Korean
  locale families and their regional variants/parent fallbacks. Keep their
  collation, calendar/date, number/currency/unit, relative-time, plural, list,
  display-name and segmentation resources.
- Unicode normalization/property data for all scripts, including NFC/NFD and
  NFKC/NFKD; IDNA/UTS46 domain handling; all time zones; break rules and
  dictionaries for segmentation. A foreign-language text does not require
  that language's locale-formatting resources to be decoded or normalized.

Lite removes unrelated locale families, non-web converter tables,
transliteration and rule-based spellout data. Other explicit Intl locales
may fall back to a retained locale. Adding a source that requires a new
locale's formatting/collation must extend the profile; future feature use
cannot be inferred from today's imports.

`prepare-mobile-icu.py` uses the host ICU tools, checks required resources
before/after trimming and lets icupkg validate package dependencies. A unique
intermediate package name prevents an installed host's full ICU from hiding
missing resources. The final conventional data entry point is preserved.
With the Node 26.11 proposal’s bundled ICU data, the production helper
reduces 33,107,952 to 11,026,480 bytes (22,081,472 bytes removed). This
measures data only, not a complete newly compiled libnode or compressed ZIP.

## Other lite subtractions

Lite removes Amaro, Inspector, SQLite/Web Storage, SEA executable packaging
and V8 native-debugger object-print support. Node 26 lite also removes Temporal
and FFI. Core JS/MJS/CJS modules and the pure `@dan-uni/dan-any` UniDB do not
require these features. OpenCC remains a JavaScript dependency.

Keep HTTP/HTTPS/TLS/crypto, DNS, fetch/Undici, WebAssembly, compression including
Brotli/zstd, filesystem/module loading, streams, AsyncLocalStorage and the
existing Worker/child-process APIs. WASI/HTTP2 are not separately trimmed in
this change; Undici itself references node:http2.

Android retains JIT/native WASM. Lite uses pointer compression only on 64-bit
Android; it primarily reduces heap memory and changes the direct V8-addon ABI.
iOS retains its existing jitless/polywasm setup without pointer compression.

## Android symbol stripping

Android lite SDK copies are stripped with the NDK's `llvm-strip
--strip-unneeded`. The linked build output remains available locally for
debugging. CI also trims restored lite cache entries before upload. The
helper compares every dynamic symbol before/after and refuses a changed ABI;
node::Start and exported N-API functions remain available. Non-runtime debug
sections and the ordinary symbol/string tables are removed. Full SDK copies
retain their previous symbol policy.

The apps may already strip their packaged libraries: producer-side stripping
reduces SDK downloads, but repeated stripping does not reduce an already
stripped APK a second time. Header declarations are needed to compile the
embedders and do not become a separate runtime payload.

## Validation

After materialization, run from the recipe directory:

```sh
python3 scripts/test-mobile-flavors.py out
```

This invokes Android's configure wrapper for full/lite on arm, arm64 and
x86_64 using a configure recorder, evaluates the real iOS flavor/archive and
ICU profile selection, and runs shipped ICU regressions on host Node.

Both platform boot smokes check all 39 canonical TextDecoder encodings,
streaming/multibyte examples, retained locale APIs, normalization, IDNA and
time zones. Lite additionally verifies that unselected locale data was
actually removed. Node 26 full still exercises native FFI calls/callbacks and
Temporal timezone behavior; lite asserts those features are absent.

Before publishing, complete cross-compilation and device gates and measure
actual new artifacts. Previously published archives and either app's pinned
URL/checksum remain unchanged. Future core/dependency updates must be checked
against this contract.
