'use strict';

// Keep danmu_api's decoding, normalization and Chinese sorting available in
// both flavors. The boot harness supplies the expected artifact flavor.
const assert = require('node:assert/strict');
if (process.platform === 'android' || process.platform === 'ios') {
  assert.ok(process.versions.mobile, 'mobile version metadata must be present');
  assert.equal(process.versions.mobile.split('-')[0], process.versions.node);
}
const flavor = globalThis.NODEJS_MOBILE_EXPECT_FLAVOR ||
  process.env.NODEJS_MOBILE_EXPECT_FLAVOR ||
  (process.config.variables.node_use_sqlite ? 'full' : 'lite');
assert.ok(['full', 'lite'].includes(flavor), 'invalid expected build flavor');
const lite = flavor === 'lite';
assert.equal(Boolean(process.config.variables.node_use_sqlite), !lite);
assert.equal(Boolean(process.config.variables.node_use_amaro), !lite);
assert.equal(Boolean(process.config.variables.v8_enable_inspector), !lite);
if (lite) {
  assert.throws(() => require('node:sqlite'), { code: 'ERR_UNKNOWN_BUILTIN_MODULE' });
  assert.throws(() => require('node:inspector'), { code: 'ERR_INSPECTOR_NOT_AVAILABLE' });
}

console.log('NODEJS_MOBILE_FEATURE_STAGE icu');
assert.ok(process.versions.icu, 'ICU must be compiled into both flavors');
assert.equal(process.config.variables.icu_small, false, 'ICU must retain the complete API mode');
assert.equal('１２Ａ'.normalize('NFKC'), '12A');
assert.ok(new Intl.Collator('zh-CN').resolvedOptions().locale.startsWith('zh'));
assert.deepEqual(['张', '阿', '李'].sort((a, b) => a.localeCompare(b, 'zh-CN')),
  ['阿', '李', '张']);
for (const [encoding, bytes] of [
  ['gbk', [0xd6, 0xd0, 0xce, 0xc4]],
  ['gb2312', [0xd6, 0xd0, 0xce, 0xc4]],
  ['big5', [0xa4, 0xa4, 0xa4, 0xe5]],
]) {
  assert.equal(new TextDecoder(encoding, { fatal: true }).decode(Uint8Array.from(bytes)), '中文');
}

// Every Node TextDecoder web encoding stays available, including encodings
// not requested by today's sources. Check streaming against a one-shot decode.
const encodingHashes = {
  "ibm866": "3c8cc5cb485f93d2bb20ea06c4d6808fcae1d924105a0ec4ee2b280457c14e14",
  "windows-1252": "cc916e51644a12e8de4ad160910c171a58621ee5dc3a6da6f8b00f8684085f33",
  "iso-8859-6": "beba4e6cf97dce8317ea76b14b77dbe4d2b3d8920b6b0a3fa9235ab532629f82",
  "big5": "7a7e1f2dbbff786abf55250e204d6db2433cd6ee699cc27374b1d6ecd28865ea",
  "gbk": "9cc45cb5d63e234da6349daddb9b38cc6d3a677a6c1e0bc2877d10bbf673c0b2",
  "windows-1250": "03772ed2e875bd125544fe7f243ea9a1dd163a057030970b26d8b6dd4c79a6e5",
  "windows-1251": "b16600cf4e6d1a2d4659b6a2cc96caa5ddc3e103ecfb07c5154d05fd54b174b3",
  "windows-1253": "e4570135cbc6e3d53eae99c2be1af17c86f4a744bd55757470d2143ece00da0b",
  "windows-1254": "4a8e99647c3e28e6a5234ac8b124e5614a3f99dc68ec948fb67da163e210e4f3",
  "windows-1255": "870c5c5e687fabcddc1209bc1263f6d6e9d6f594baed8ab280dcdeeb5607207d",
  "windows-1256": "6f6e8626197b1b6b280a079d1d842daa09600a39fdb3d1e99596e943c61cc98b",
  "windows-1257": "d19a4e888879e36a450470073fc0344cffdfffa40ad82fb433de9f9b40b5c048",
  "windows-1258": "e79b48db126bc71dfcf1723e9f6350af101d1eb494e29d736ecf9530113cd361",
  "euc-kr": "f82d4597ae2fd7b4cc85f13509cacd40a11d0355de01a146fe6beb3d3ed8d060",
  "euc-jp": "9d9e4b1cf9bad807e677e7af6b49f34b58e8767669fce9f2d85fc57c3fc32c39",
  "iso-2022-jp": "0a53580eb9bb28a3585042beac7a16697ba21b4abf179771423705eacba3ad4d",
  "iso-8859-8": "b43535e7aaeb7bcf8bd8465326ef9ace96e351494306f963fa24cf312e5aaf18",
  "iso-8859-8-i": "b43535e7aaeb7bcf8bd8465326ef9ace96e351494306f963fa24cf312e5aaf18",
  "iso-8859-2": "a5871b0f978b840b9fad23483563caf9edf42c1828bff529f7594779ebaf5210",
  "iso-8859-3": "e83895f2b7d7b82b9356298e197f7ddef190d53209cdf3b46e9eca4d4a582847",
  "iso-8859-4": "449076e20ebf45ebbf44f24e39e98684dd2a6e07467ba3b8ba4192eb9405e2e3",
  "iso-8859-10": "282514fbd01219c48fc84a8e45654368f161e1c5ab33fc028748688b9acb217f",
  "iso-8859-15": "9b58b26dbd8fbff2917ab21d989323703946ba491a1eb15cdb2af7ecf9581e97",
  "iso-8859-5": "9f31ddc0f7444afa24ddc2241f303bcd712296d7f2ca1e6bc9f5d1e9163df86f",
  "iso-8859-7": "71069977a6798ab799df960847c927edfc3f787ac238f73702d7f37ef8cc1a1c",
  "koi8-r": "fb0243455e64ef7026d46b057cfaeb41fef148d7d29a78fde21feda264ac02ee",
  "macintosh": "54112bce885d7b1abc9ba5e06e21900b89ea0f7e5da25e393c0bdf72d0ea4a30",
  "shift_jis": "63214e041f92daeea69d4ff39caf1cdd9dc39551b2a313e1fa0f9a22163b26f8",
  "utf-16le": "c46bd82c3031aaac9e602e1dba920942cefe5427897a162ab7e2a8f5139e2304",
  "windows-874": "6a2c7940c3d682164044abd7db7706dfff0307c39092937230f7554ce9846756",
  "gb18030": "9cc45cb5d63e234da6349daddb9b38cc6d3a677a6c1e0bc2877d10bbf673c0b2",
  "iso-8859-13": "4426f6d2f1b025cdf6d2b46080e2840b0ce85666d424ec909ccab226b34ebcc8",
  "iso-8859-14": "f03afb7e01e66cac3cd7ed1a084173244f55b7c2e7fce44969aeade1077d8560",
  "iso-8859-16": "2de1faef4dc524c9b94fd90885997e4fe6c2be7c672a1c03a10dcb0edd69487e",
  "koi8-u": "896c218aaf12ca1b0489a01d8d2780b0e9de4253e24f0117d5486dfd87acf593",
  "utf-8": "0f1a0d9c96b61c6dd842f73714f9e10c01c40383217f0a095c08145ef36b081b",
  "utf-16be": "d82384cdf8ccf910d979149596e6eac1305878422cf44cbf028a97d6844a9e88",
  "x-mac-cyrillic": "784db55e1c90195e69a4f96d755548fe48a4a6c327d1138cc731af07afec272c",
  "x-user-defined": "fb4341fe90799717efc22f5de56d20a92c13e3711e94c9d4433fa4aabaf57c57"
};
for (const [encoding, expected] of Object.entries(encodingHashes)) {
  const bytes = Uint8Array.from({ length: 256 }, (_, index) => index);
  const decoded = new TextDecoder(encoding).decode(bytes);
  assert.equal(require('node:crypto').createHash('sha256').update(decoded).digest('hex'),
    expected, `${encoding}: data differs from complete ICU`);
  const streaming = new TextDecoder(encoding);
  let chunks = '';
  for (let index = 0; index < bytes.length; index += 7) {
    chunks += streaming.decode(bytes.slice(index, index + 7), { stream: true });
  }
  chunks += streaming.decode();
  assert.equal(chunks, decoded, `${encoding}: streaming decode differs`);
}
for (const [encoding, bytes, expected] of [
  ['shift_jis', [0x93, 0xfa, 0x96, 0x7b], '日本'],
  ['euc-jp', [0xc6, 0xfc, 0xcb, 0xdc], '日本'],
  ['iso-2022-jp', [0x1b, 0x24, 0x42, 0x46, 0x7c, 0x4b, 0x5c, 0x1b, 0x28, 0x42], '日本'],
  ['euc-kr', [0xc7, 0xd1, 0xb1, 0xdb], '한글'],
]) {
  assert.equal(new TextDecoder(encoding, { fatal: true }).decode(Uint8Array.from(bytes)), expected);
}
for (const locale of ['zh-CN', 'zh-TW', 'zh-HK', 'zh-SG', 'zh-MO',
  'en-US', 'en-GB', 'en-AU', 'ja-JP', 'ko-KR']) {
  for (const name of ['Collator', 'DateTimeFormat', 'NumberFormat', 'RelativeTimeFormat',
    'PluralRules', 'ListFormat', 'DisplayNames', 'Segmenter']) {
    assert.equal(Intl[name].supportedLocalesOf([locale]).length, 1, `${name}: ${locale}`);
  }
  assert.ok(new Intl.DateTimeFormat(locale, { timeZone: 'Asia/Shanghai' }).format(0));
  assert.ok(new Intl.NumberFormat(locale, { style: 'currency', currency: 'CNY' }).format(1234.5));
  assert.ok(new Intl.NumberFormat(locale, { style: 'unit', unit: 'kilometer-per-hour' }).format(60));
  assert.ok(new Intl.DisplayNames(locale, { type: 'language' }).of('fr'));
  assert.ok(new Intl.DisplayNames(locale, { type: 'region' }).of('US'));
  assert.ok([...new Intl.Segmenter(locale, { granularity: 'word' }).segment('中文日本어 test')].length);
}
for (const timeZone of ['UTC', 'Asia/Taipei', 'Asia/Hong_Kong', 'Asia/Tokyo',
  'Asia/Seoul', 'America/New_York', 'Europe/London', 'Australia/Sydney']) {
  assert.ok(new Intl.DateTimeFormat('en-US', { timeZone }).format(0));
}
assert.equal(require('node:url').domainToASCII('中文.cn'), 'xn--fiq228c.cn');
assert.equal(require('node:url').domainToASCII('faß.de'), 'xn--fa-hia.de');
assert.equal('①ﬀ'.normalize('NFKC'), '1ff');
if (lite) {
  assert.deepEqual(Intl.DateTimeFormat.supportedLocalesOf(['de-DE']), [],
    'lite must embed the selected ICU locale profile, not complete locale data');
}

console.log(`NODEJS_MOBILE_FEATURES_OK flavor=${flavor} icu=${lite ? 'danmu' : 'full'}`);
