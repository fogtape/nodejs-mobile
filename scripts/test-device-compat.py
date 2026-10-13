#!/usr/bin/env python3
"""Verify Intl keeps its in-process assertions without spawning on mobile."""
from pathlib import Path
import json
import subprocess
import sys
import unittest

SOURCE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'out'


class DeviceCompatibility(unittest.TestCase):
    def test_intl_retains_assertions_and_desktop_locale_startup_checks(self):
        script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert');
const source = fs.readFileSync(process.argv[2], 'utf8');
const platform = process.argv[3];
let assertions = 0;
const assertionAPI = new Proxy(assert, {
  get(target, key) {
    if (key !== 'strictEqual') return Reflect.get(target, key);
    return (...args) => { assertions++; return assert.strictEqual(...args); };
  },
});
const children = [];
const common = {
  hasIntl: true,
  isAndroid: platform === 'android',
  isIOS: platform === 'ios',
  mustSucceed: () => (error) => assert.ifError(error),
};
vm.runInNewContext(`(function() {\n${source}\n})();`, {
  process: { execPath: process.execPath, env: {}, config: { variables: {
    v8_enable_i18n_support: 1, icu_locales: '',
  } } },
  console,
  require(name) {
    if (name === '../common') return common;
    if (name === 'assert') return assertionAPI;
    if (name === 'child_process') return { execFile(...args) {
      assert.strictEqual(platform, 'linux', 'mobile attempted to spawn a child Node');
      children.push(args[2].env.LC_ALL);
      args[3](null);
    } };
    throw new Error(`Unexpected import ${name}`);
  },
}, { filename: process.argv[2] });
console.log(JSON.stringify({ assertions, children }));
'''
        counts = []
        for platform in ('android', 'ios', 'linux'):
            with self.subTest(platform=platform):
                result = subprocess.run(
                    ['node', '-', str(SOURCE / 'test/parallel/test-intl.js'), platform],
                    input=script, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertGreaterEqual(report['assertions'], 15)
                counts.append(report['assertions'])
                self.assertEqual(report['children'], ['ja', 'fr@EURO'] if platform == 'linux' else [])
        self.assertEqual(len(set(counts)), 1, 'mobile must retain every in-process assertion')


if __name__ == '__main__':
    unittest.main()
