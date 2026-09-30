#!/usr/bin/env python3
"""Exercise embedded verdict hooks and iOS final-verdict polling on the host."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

SOURCE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else Path('out').resolve()
NODE = shutil.which('node')
HOOKS = (
    'tools/mobile-test/ios/testnode/testnode/NodeRunner.mm',
    'tools/mobile-test/android/testnode/app/src/main/cpp/native-lib.cpp',
)


class MobileVerdicts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='node-mobile-verdict-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_owner(self, native_file, body, *, owner=True):
        self.assertIsNotNone(NODE, 'node is required for verdict regressions')
        source = (SOURCE / native_file).read_text()
        hook = re.search(r'R"JS\((.*?)\)JS";', source, re.S)
        self.assertIsNotNone(hook, native_file)
        hook_path = self.root / 'exit-verdict-hook.cjs'
        hook_path.write_text(hook[1])
        result = self.root / 'result.txt'
        result.unlink(missing_ok=True)
        parent = self.root / 'parent.cjs'
        parent.write_text('''const fs = require('node:fs');
const assert = require('node:assert/strict');
const cp = require('node:child_process');
const { Worker } = require('node:worker_threads');
const verdict = process.argv[2];
const hook = process.argv[3];
process.env.NODEJS_MOBILE_TEST_VERDICT_FILE = verdict;
process.env.NODEJS_MOBILE_TEST_VERDICT_PID = String(process.pid + ''' +
                          ('0' if owner else '1') + ''');
process.env.NODE_OPTIONS = '--require=' + hook;
const loaded = JSON.stringify(process.moduleLoadList);
require(hook);
assert.equal(JSON.stringify(process.moduleLoadList), loaded, 'hook loaded modules before exit');
''' + body)
        process = subprocess.run([NODE, str(parent), str(result), str(hook_path)],
                                 capture_output=True, text=True, timeout=20)
        return process, result.read_text() if result.exists() else None

    def test_owner_records_its_exit_code(self):
        for native_file in HOOKS:
            for code in (0, 3):
                with self.subTest(hook=native_file, exit=code):
                    process, verdict = self.run_owner(native_file, f'process.exit({code});')
                    self.assertEqual(process.returncode, code, process.stderr)
                    self.assertEqual(verdict, 'PASS\n' if code == 0 else 'FAIL\n')

    def test_child_cannot_write_parent_verdict(self):
        for native_file in HOOKS:
            for child_code, owner_code in ((1, 0), (0, 3)):
                with self.subTest(hook=native_file, child=child_code):
                    body = f'''
const child = cp.spawnSync(process.execPath, ['-e', 'process.exit({child_code})']);
assert.equal(child.status, {child_code}, child.stderr.toString());
assert.equal(fs.existsSync(verdict), false, 'child wrote parent verdict');
process.exit({owner_code});
'''
                    process, verdict = self.run_owner(native_file, body)
                    self.assertEqual(process.returncode, owner_code, process.stderr)
                    self.assertEqual(verdict, 'PASS\n' if owner_code == 0 else 'FAIL\n')

    def test_worker_cannot_write_parent_verdict(self):
        for native_file in HOOKS:
            with self.subTest(hook=native_file):
                body = '''
const worker = new Worker("require(process.argv[3]); process.exit(3)", {
  eval: true, argv: [verdict, hook],
});
worker.on('exit', (code) => {
  assert.equal(code, 3);
  assert.equal(fs.existsSync(verdict), false, 'worker wrote parent verdict');
});
'''
                process, verdict = self.run_owner(native_file, body)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(verdict, 'PASS\n')

    def test_nonowner_and_unbound_hook_write_nothing(self):
        for native_file in HOOKS:
            for body in ('', 'delete process.env.NODEJS_MOBILE_TEST_VERDICT_PID; require(hook);'):
                with self.subTest(hook=native_file, body=body):
                    process, verdict = self.run_owner(native_file, body, owner=False)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    self.assertIsNone(verdict)

    def run_proxy(self, initial, final):
        tree = self.root / 'tree'
        (tree / 'test').mkdir(parents=True)
        script = tree / 'tools/mobile-test/ios/node-ios-sim-proxy.sh'
        script.parent.mkdir(parents=True)
        uuidgen = self.root / 'uuidgen'
        uuidgen.write_text('#!/bin/sh\nprintf \'12345678-1234-1234-1234-123456789abc\\n\'\n')
        uuidgen.chmod(0o755)
        # Stub the macOS absolute dependency when running this check on Linux.
        script.write_text((SOURCE / 'tools/mobile-test/ios/node-ios-sim-proxy.sh').read_text()
                          .replace('/usr/bin/uuidgen', str(uuidgen)))
        container = self.root / 'container'
        (container / 'Documents').mkdir(parents=True)
        mock = self.root / 'xcrun'
        mock.write_text('#!' + sys.executable + '''
import os,sys
from pathlib import Path
if sys.argv[2] == 'get_app_container': print(os.environ['MOCK_CONTAINER'])
elif sys.argv[2] == 'launch':
    token = sys.argv[sys.argv.index('--run-token') + 1]
    (Path(os.environ['MOCK_CONTAINER']) / 'Documents/launch-token.txt').write_text(token)
    print('nodejsmobile.test: ' + os.environ['MOCK_APP_PID'])
else: raise RuntimeError(sys.argv)
''')
        mock.chmod(0o755)
        env = dict(os.environ, DEVICE_ID='mock-device', MOCK_CONTAINER=str(container),
                   NODE_IOS_PROXY_TIMEOUT='2', NODE_IOS_PROXY_LAUNCH_ATTEMPTS='1',
                   PATH=str(self.root) + os.pathsep + os.environ['PATH'])
        app_script = '''
from pathlib import Path
import sys,time
folder = Path(sys.argv[1])
# The mock launcher delivers the actual per-launch token to this app.
launch = folder / 'launch-token.txt'
while not launch.exists():
    time.sleep(0.01)
token = launch.read_text()
result = folder / ('result-' + token + '.txt')
stdout = folder / ('stdout-' + token + '.txt')
result.write_text(sys.argv[2] + '\\n')
if sys.argv[3] == 'hang':
    time.sleep(20)
else:
    time.sleep(0.4)
    result.write_text(sys.argv[3] + '\\n')
    stdout.write_text('output after provisional verdict\\n')
'''
        app = subprocess.Popen([sys.executable, '-c', app_script,
                                str(container / 'Documents'), initial, final],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        env['MOCK_APP_PID'] = str(app.pid)
        reaper = threading.Thread(target=app.wait)
        reaper.start()
        try:
            process = subprocess.run(['bash', str(script), 'test/parallel/example.js'],
                                     env=env, capture_output=True, text=True, timeout=10)
        finally:
            if app.poll() is None:
                app.terminate()
            reaper.join(timeout=5)
            app.stderr.close()
        return process

    def test_ios_proxy_consumes_final_verdict_and_output(self):
        # Each case needs its own fake app container and token files.
        for initial, final in [('PASS', 'FAIL'), ('FAIL', 'PASS')]:
            with self.subTest(initial=initial, final=final):
                previous = self.root
                self.root = previous / initial
                self.root.mkdir()
                try:
                    process = self.run_proxy(initial, final)
                finally:
                    self.root = previous
                self.assertEqual(process.returncode, 0 if final == 'PASS' else 1, process.stderr)
                self.assertIn('output after provisional verdict', process.stdout)

    def test_ios_proxy_rejects_verdict_from_still_running_app(self):
        process = self.run_proxy('PASS', 'hang')
        self.assertEqual(process.returncode, 1, process.stderr)
        self.assertIn('app still running', process.stderr)


if __name__ == '__main__':
    unittest.main()
