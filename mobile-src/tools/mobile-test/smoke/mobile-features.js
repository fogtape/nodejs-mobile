'use strict';

// Exercise the compiled feature set on the mobile runtime, including the
// native callback path (a successful require alone cannot test libffi).
const assert = require('node:assert/strict');
if (process.platform === 'android' || process.platform === 'ios') {
  assert.ok(process.versions.mobile, 'mobile version metadata must be present');
  assert.equal(process.versions.mobile.split('-')[0], process.versions.node);
}

const ffi = require('node:ffi');
const sizeType = ['arm', 'ia32'].includes(process.arch) ? 'uint32' : 'uint64';
const sizeValue = (value) => sizeType === 'uint64' ? BigInt(value) : value;
const { lib, functions } = ffi.dlopen(null, {
  abs: { arguments: ['int32'], return: 'int32' },
  qsort: { arguments: ['pointer', sizeType, sizeType, 'function'], return: 'void' },
});
assert.equal(functions.abs(-42), 42);
const numbers = Buffer.alloc(12);
[3, 1, 2].forEach((value, index) => numbers.writeInt32LE(value, index * 4));
let callbackCalls = 0;
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

const temporalEnabled = !!process.config.variables.v8_enable_temporal_support;
assert.equal(typeof globalThis.Temporal, temporalEnabled ? 'object' : 'undefined');
if (temporalEnabled) {
  assert.equal(Temporal.PlainDate.from('2024-02-28').add({ days: 1 }).toString(), '2024-02-29');
  const spring = Temporal.ZonedDateTime.from('2026-03-08T01:30-05:00[America/New_York]');
  assert.equal(spring.add({ hours: 1 }).hour, 3, 'Temporal timezone data/DST is unavailable');
}
console.log(`NODEJS_MOBILE_FEATURES_OK ffi=1 temporal=${Number(temporalEnabled)}`);
