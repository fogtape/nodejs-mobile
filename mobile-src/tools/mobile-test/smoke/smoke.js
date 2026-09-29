'use strict';

// Boot smoke, on device (see docs/TESTING.md on the recipe branch): prove
// the cross-compiled mobile libnode boots and runs JavaScript on the device
// runtime, then exits cleanly. The marker string is grepped by the smoke
// workflows — keep in sync.
const assert = require('node:assert/strict');
assert.ok(process.versions.mobile, 'mobile version metadata must be present');
assert.equal(process.versions.mobile.split('-')[0], process.versions.node);
console.log(
  `NODEJS_MOBILE_SMOKE_OK ${process.version} ${process.platform} ${process.arch}`,
);
process.exit(0);
