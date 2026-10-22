// Flags: --experimental-vm-modules
'use strict';

// https://github.com/nodejs/node/issues/3020
// Promises used to allow code to escape the timeout
// set for runInContext, runInNewContext, and runInThisContext.

const common = require('../common');
const assert = require('assert');
const vm = require('vm');

const NS_PER_MS = 1000000n;
// nodejs-mobile patch: leave the 10ms VM deadline unchanged, but allow the
// watchdog thread to be scheduled on a busy iOS simulator before the test's
// escape guard fires. Other VM timeout tests already use a 2-second guard.
const escapeGuardMs = common.isIOS ? 2000n : 100n;

const hrtime = process.hrtime.bigint;

function loop() {
  const start = hrtime();
  while (1) {
    const current = hrtime();
    const span = (current - start) / NS_PER_MS;
    if (span >= escapeGuardMs) {
      throw new Error(
        `escaped timeout at ${span} milliseconds!`);
    }
  }
}

assert.rejects(async () => {
  const module = new vm.SourceTextModule(
    'Promise.resolve().then(() => loop());',
    {
      context: vm.createContext({
        hrtime,
        loop,
      }, { microtaskMode: 'afterEvaluate' }),
    });
  await module.link(common.mustNotCall());
  await module.evaluate({ timeout: 10 });
}, {
  code: 'ERR_SCRIPT_EXECUTION_TIMEOUT',
  message: 'Script execution timed out after 10ms',
}).then(common.mustCall());
