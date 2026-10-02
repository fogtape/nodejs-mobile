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

const ffiEnabled = Boolean(process.config.variables.node_use_ffi);
assert.equal(ffiEnabled, !lite, 'FFI must be enabled only in full builds');
if (!ffiEnabled) {
  assert.throws(() => require('node:ffi'), { code: 'ERR_UNKNOWN_BUILTIN_MODULE' });
} else {
  console.log('NODEJS_MOBILE_FEATURE_STAGE ffi-load');
  const ffi = require('node:ffi');
  const sizeType = ['arm', 'ia32'].includes(process.arch) ? 'uint32' : 'uint64';
  const sizeValue = (value) => sizeType === 'uint64' ? BigInt(value) : value;
  const { lib, functions } = ffi.dlopen(null, {
    abs: { arguments: ['int32'], return: 'int32' },
    qsort: { arguments: ['pointer', sizeType, sizeType, 'function'], return: 'void' },
  });
  console.log('NODEJS_MOBILE_FEATURE_STAGE ffi-call');
  assert.equal(functions.abs(-42), 42);
  const numbers = Buffer.alloc(12);
  [3, 1, 2].forEach((value, index) => numbers.writeInt32LE(value, index * 4));
  let callbackCalls = 0;
  console.log('NODEJS_MOBILE_FEATURE_STAGE ffi-callback');
  const callback = lib.registerCallback(
    { arguments: ['pointer', 'pointer'], return: 'int32' },
    (left, right) => {
      callbackCalls += 1;
      return ffi.toBuffer(left, 4, true).readInt32LE() -
        ffi.toBuffer(right, 4, true).readInt32LE();
    },
  );
  try {
    functions.qsort(ffi.getRawPointer(numbers), sizeValue(3), sizeValue(4), callback);
    assert.deepEqual([0, 4, 8].map((offset) => numbers.readInt32LE(offset)), [1, 2, 3]);
    assert.ok(callbackCalls > 0, 'native libffi callback did not run');
  } finally {
    lib.unregisterCallback(callback);
    lib.close();
  }
}

console.log('NODEJS_MOBILE_FEATURE_STAGE temporal');
const temporalEnabled = !!process.config.variables.v8_enable_temporal_support;
assert.equal(temporalEnabled, !lite, 'Temporal must be enabled only in full builds');
assert.equal(typeof globalThis.Temporal, temporalEnabled ? 'object' : 'undefined');
if (temporalEnabled) {
  assert.equal(Temporal.PlainDate.from('2024-02-28').add({ days: 1 }).toString(), '2024-02-29');
  console.log('NODEJS_MOBILE_FEATURE_STAGE temporal-timezone');
  const spring = Temporal.ZonedDateTime.from('2026-03-08T01:30-05:00[America/New_York]');
  assert.equal(spring.add({ hours: 1 }).hour, 3, 'Temporal timezone data/DST is unavailable');
}
console.log(`NODEJS_MOBILE_FEATURES_OK flavor=${flavor} icu=full ffi=${Number(ffiEnabled)} temporal=${Number(temporalEnabled)}`);
