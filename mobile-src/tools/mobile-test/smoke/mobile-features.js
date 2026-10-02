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
assert.equal(process.config.variables.icu_small, false, 'full ICU data is required');
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

console.log(`NODEJS_MOBILE_FEATURES_OK flavor=${flavor} icu=full`);
