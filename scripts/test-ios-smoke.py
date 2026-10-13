#!/usr/bin/env python3
"""Check iOS smoke launch/output handling and authoritative verdicts."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / 'mobile-src/tools/mobile-test/smoke/run-ios-smoke.sh'


class IOSSmoke(unittest.TestCase):
    def run_smoke(self, verdicts):
        with tempfile.TemporaryDirectory(prefix='ios-smoke-') as folder:
            root = Path(folder)
            docs = root / 'container/Documents'
            docs.mkdir(parents=True)
            scripts = root / 'scripts'
            scripts.mkdir()
            shutil.copy2(SMOKE, scripts / SMOKE.name)
            (scripts / 'mobile-features.js').write_text('// fixture\n')
            tools = root / 'bin'
            tools.mkdir()
            uuid = tools / 'uuidgen'
            uuid.write_text('#!/bin/sh\nprintf "%s\\n" "12345678-1234-1234-1234-123456789ABC"\n')
            uuid.chmod(0o755)
            xcrun = tools / 'xcrun'
            xcrun.write_text('''#!/usr/bin/env python3
import json,os,pathlib,sys
args=sys.argv[1:]
record=pathlib.Path(os.environ['COMMANDS'])
with record.open('a') as f: f.write(json.dumps(args)+'\\n')
if '--console' in args: sys.exit(99)
if args[1]=='get_app_container': print(os.environ['CONTAINER'])
if args[1]=='launch':
    count=pathlib.Path(os.environ['COUNT'])
    n=int(count.read_text()) if count.exists() else 0
    count.write_text(str(n+1))
    verdicts=json.loads(os.environ['VERDICTS'])
    verdict=verdicts[min(n,len(verdicts)-1)]
    token=args[args.index('--run-token')+1]
    docs=pathlib.Path(os.environ['CONTAINER'])/'Documents'
    if verdict:
        (docs/f'result-{token}.txt').write_text(verdict+'\\n')
        (docs/f'stdout-{token}.txt').write_text('sandbox smoke output\\n')
    print('nodejsmobile.test: 2147483647')
''')
            xcrun.chmod(0o755)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                       COMMANDS=str(root / 'commands'), COUNT=str(root / 'count'),
                       CONTAINER=str(docs.parent), VERDICTS=json.dumps(verdicts),
                       SMOKE_POLL_SECONDS='1', SMOKE_MAX_ATTEMPTS='3')
            result = subprocess.run(['bash', str(scripts / SMOKE.name), 'fixture.app', 'fixture-udid'],
                                    text=True, capture_output=True, env=env, timeout=15)
            commands = [json.loads(line) for line in (root / 'commands').read_text().splitlines()]
            return result, commands

    def test_pass_reads_sandbox_output_and_avoids_console_fifo(self):
        result, commands = self.run_smoke(['PASS'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('sandbox smoke output', result.stderr)
        self.assertTrue(all('--console' not in args for args in commands))
        self.assertEqual(sum(args[1] == 'launch' for args in commands), 1)

    def test_real_fail_is_not_retried_or_turned_into_pass(self):
        result, commands = self.run_smoke(['FAIL', 'PASS'])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(sum(args[1] == 'launch' for args in commands), 1)
        self.assertIn('real failure', result.stdout)

    def test_no_verdict_retries_only_within_bound(self):
        result, commands = self.run_smoke(['', 'PASS'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(args[1] == 'launch' for args in commands), 2)
        self.assertTrue(any(args[1] == 'shutdown' for args in commands))

    def test_no_verdict_never_succeeds_without_pass(self):
        result, commands = self.run_smoke([''])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(sum(args[1] == 'launch' for args in commands), 3)
        self.assertIn('after 3 attempts', result.stdout)


if __name__ == '__main__':
    unittest.main()
