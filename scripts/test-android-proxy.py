#!/usr/bin/env python3
"""Exercise Android launch recovery without rerunning an acknowledged test."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
PROXY = ROOT / 'out/tools/mobile-test/android/node-android-proxy.sh'

ADB = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['MOCK_ROOT'])
config = json.loads(os.environ['MOCK_CONFIG'])
state_path = root / 'state.json'
state = json.loads(state_path.read_text()) if state_path.exists() else {
    'launches': 0, 'stops': 0, 'clears': 0, 'alive': True, 'started': False,
    'verdict': '', 'old_output': True, 'force_failed': False}
args = sys.argv[1:]
with (root / 'commands.jsonl').open('a') as log:
    log.write(json.dumps(args) + '\n')
if args[:2] == ['-s', 'fixture-device']: args = args[2:]
cmd = args[1] if args[:1] == ['shell'] else ''
code = 0
if 'am force-stop' in cmd:
    state['stops'] += 1
    if state['stops'] <= config.get('stop_failures', 0):
        state['force_failed'] = True
        print('error: closed', file=sys.stderr)
        code = 1
    elif state['stops'] > config.get('stop_keeps_alive', 0):
        state['alive'] = False
    if code == 0 and 'rm -f' in cmd:
        # A late acknowledgement during force-stop must prevent a relaunch.
        state['started'] = False
elif args == ['logcat', '-c']:
    state['clears'] += 1
    if state['clears'] <= config.get('clear_failures', 0):
        print('logcat transport failed', file=sys.stderr)
        code = 1
    else: state['old_output'] = False
elif 'am start -W' in cmd:
    state['launches'] += 1
    assert not state['alive'], 'launched over stale activity'
    assert not state['old_output'], 'launched with stale logs'
    launches = config.get('launches', ['PASS'])
    launch = launches[min(state['launches'] - 1, len(launches) - 1)]
    state['started'] = launch not in ('NO_START', 'QUERY_ERROR', 'LATE_START')
    state['query_error'] = launch == 'QUERY_ERROR'
    state['late_start'] = launch == 'LATE_START'
    state['alive'] = state['started'] and launch != 'CRASH'
    state['verdict'] = launch if launch in ('PASS', 'FAIL') else ''
    if launch == 'LOST_REPLY':
        state['verdict'] = 'PASS'
    if launch in ('NO_START', 'LOST_REPLY'):
        print('am transport failed', file=sys.stderr)
        code = 1
    else: print('Status: ok')
elif 'pids=$(pidof' in cmd:
    print('RUNNING' if state['alive'] else 'STOPPED')
elif 'if [ -f files/started-' in cmd:
    if state.get('query_error'):
        print('sandbox query transport failed', file=sys.stderr)
        code = 1
    else:
        if state.get('late_start') and not state['alive'] and state['stops'] > 1:
            state['started'] = True
        print('STARTED' if state['started'] else 'NOT_STARTED')
elif 'cat files/result-' in cmd:
    print(state['verdict'])
elif 'logcat -d' in cmd:
    if '-v raw' in cmd: print('current test output')
else:
    print('unexpected adb call: ' + repr(args), file=sys.stderr)
    code = 91
state_path.write_text(json.dumps(state))
sys.exit(code)
'''


class AndroidProxy(unittest.TestCase):
    def run_proxy(self, **config):
        with tempfile.TemporaryDirectory(prefix='android-proxy-') as folder:
            root = Path(folder)
            proxy = root / 'tools/mobile-test/android/node-android-proxy.sh'
            proxy.parent.mkdir(parents=True)
            (root / 'tools/test').mkdir()
            shutil.copy2(PROXY, proxy)
            tools = root / 'bin'
            tools.mkdir()
            adb = tools / 'adb'
            adb.write_text(ADB)
            adb.chmod(0o755)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                       MOCK_ROOT=str(root), MOCK_CONFIG=json.dumps(config),
                       DEVICE_ID='fixture-device', NODE_ANDROID_PROXY_TIMEOUT='1',
                       NODE_ANDROID_START_TIMEOUT='1', NODE_ANDROID_LAUNCH_ATTEMPTS='3')
            result = subprocess.run(['bash', str(proxy), '/host/test/parallel/test-https-simple.js'],
                                    env=env, text=True, capture_output=True, timeout=20)
            state = json.loads((root / 'state.json').read_text())
            commands = [json.loads(line) for line in (root / 'commands.jsonl').read_text().splitlines()]
            self.assertTrue(all(args[:2] == ['-s', 'fixture-device'] for args in commands))
            return result, state

    def test_pass_uses_current_output_and_device(self):
        result, state = self.run_proxy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'current test output\n')
        self.assertEqual(state['launches'], 1)

    def test_failed_stop_is_recovered_before_launch(self):
        result, state = self.run_proxy(stop_failures=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state['launches'], 1)
        self.assertEqual(state['stops'], 2)
        self.assertIn('error: closed', result.stderr)

    def test_old_activity_must_be_gone_before_launch(self):
        result, state = self.run_proxy(stop_keeps_alive=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state['launches'], 1)
        self.assertEqual(state['stops'], 2)

    def test_failed_log_clear_is_recovered_before_launch(self):
        result, state = self.run_proxy(clear_failures=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state['launches'], 1)
        self.assertEqual(state['clears'], 2)

    def test_failed_launch_before_node_starts_can_recover(self):
        result, state = self.run_proxy(launches=['NO_START', 'PASS'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state['launches'], 2)
        self.assertIn('am transport failed', result.stderr)

    def test_lost_adb_reply_does_not_rerun_started_test(self):
        result, state = self.run_proxy(launches=['LOST_REPLY', 'FAIL'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(state['launches'], 1)

    def test_started_failure_hang_and_crash_are_never_retried(self):
        for kind in ('FAIL', 'HANG', 'CRASH'):
            with self.subTest(kind=kind):
                result, state = self.run_proxy(launches=[kind, 'PASS'])
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(state['launches'], 1)
                if kind != 'FAIL':
                    self.assertIn('hung' if kind == 'HANG' else 'crashed', result.stderr)

    def test_exhausted_launches_cannot_succeed(self):
        result, state = self.run_proxy(launches=['NO_START'])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(state['launches'], 3)
        self.assertIn('after 3 attempts', result.stderr)

    def test_exhausted_preparation_cannot_launch(self):
        result, state = self.run_proxy(stop_failures=3)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(state['launches'], 0)

    def test_unknown_or_late_start_cannot_authorize_retry(self):
        for kind in ('QUERY_ERROR', 'LATE_START'):
            with self.subTest(kind=kind):
                result, state = self.run_proxy(launches=[kind, 'PASS'])
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(state['launches'], 1)
                self.assertIn('refusing relaunch', result.stderr)


if __name__ == '__main__':
    unittest.main()
