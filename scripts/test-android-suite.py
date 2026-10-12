#!/usr/bin/env python3
"""Check Android shard coverage and preserve failures through the log pipeline."""
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import warnings

RECIPE = Path(__file__).resolve().parent.parent
SOURCE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else RECIPE / 'out'
RUNNER = SOURCE / 'tools/mobile-test/android/run-suite-shard.sh'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuietOutput(io.StringIO):
    def reconfigure(self, **_):
        pass


class AndroidSuite(unittest.TestCase):
    def setUp(self):
        workflow = (RECIPE / '.github/workflows/full-device-suite.yml').read_text()
        android = workflow.split('\n  android:\n', 1)[1].split('\n  ios:\n', 1)[0]
        self.shards = ast.literal_eval(re.search(r'^        shard: (.+)$', android, re.M)[1])
        self.count = int(re.search(r'^      ANDROID_SUITE_SHARDS: (\d+)$', android, re.M)[1])

    def test_matrix_matches_denominator(self):
        self.assertEqual(self.shards, list(range(self.count)))

    def test_watch_cli_exclusions_preserve_in_process_device_tests(self):
        sys.path.insert(0, str(SOURCE / 'tools'))
        self.addCleanup(sys.path.remove, str(SOURCE / 'tools'))
        runner = load_module('mobile_watch_status_runner', SOURCE / 'tools/test.py')
        for suite, names in {
            'sequential': ['test-watch-mode', 'test-watch-mode-inspect', 'test-tls-connect'],
            'parallel': ['test-debugger-run-restart-init', 'test-debugger-wait-for-debugger',
                         'test-fs-watch', 'test-fs-watch-persistent'],
        }.items():
            sections, defs = [], {}
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', ResourceWarning)
                runner.ReadConfigurationInto(str(SOURCE / 'test' / suite / (suite + '.status')),
                                             sections, defs)
            config = runner.Configuration(sections, defs)
            for platform in ('android', 'ios', 'linux'):
                with self.subTest(suite=suite, platform=platform):
                    cases = [SimpleNamespace(path=[suite, name]) for name in names]
                    env = dict(system=platform, arch='x64', mode='release', type='simple',
                               asan='off', pointer_compression='false')
                    classified, _ = config.ClassifyTests(cases, env)
                    skipped = {case.path[-1] for case in classified if runner.SKIP in case.outcomes}
                    expected = set(names[:2]) if suite == 'sequential' and platform != 'linux' else set()
                    self.assertEqual(skipped, expected)

    def test_real_test_selector_covers_every_runnable_case_once(self):
        # Use upstream's actual classification and --run selector, replacing
        # only device execution. This detects missing/duplicate coverage when
        # the workflow matrix or a future upstream test runner changes.
        sys.path.insert(0, str(SOURCE / 'tools'))
        self.addCleanup(sys.path.remove, str(SOURCE / 'tools'))
        runner = load_module('android_suite_test_runner', SOURCE / 'tools/test.py')
        coverage = load_module('android_suite_coverage',
                               SOURCE / 'tools/mobile-test/coverage-manifest.py')
        selected = []

        def collect(cases, *_):
            selected.extend((case.arch, case.mode, case.file, tuple(case.path))
                            for case in cases)
            return {'allPassed': True, 'failed': []}

        runner.RunTestCases = collect
        saved_cwd, saved_argv = os.getcwd(), sys.argv
        try:
            os.chdir(SOURCE)
            with tempfile.TemporaryDirectory() as folder, coverage.host_binary_present():
                stub = str(Path(folder) / 'stub-node')
                coverage.write_stub(stub)

                def select(shard=None):
                    selected.clear()
                    sys.argv = ['tools/test.py', '-j', '1', '--flaky-tests=skip',
                                '--arch', 'android', '--shell', stub]
                    if shard is not None:
                        sys.argv.append(f'--run={shard},{self.count}')
                    sys.argv.extend(['parallel', 'sequential'])
                    with contextlib.redirect_stdout(QuietOutput()), warnings.catch_warnings():
                        # Upstream Execute reads temporary files without an
                        # explicit close. This host-only selection check calls
                        # it repeatedly; keep those warnings out of CI output.
                        warnings.simplefilter('ignore', ResourceWarning)
                        self.assertEqual(runner.Main(), 0)
                    return list(selected)

                expected = select()
                actual = []
                sizes = []
                for shard in self.shards:
                    cases = select(shard)
                    sizes.append(len(cases))
                    actual.extend(cases)
                self.assertTrue(expected)
                self.assertEqual(len(actual), len(set(actual)))
                self.assertCountEqual(actual, expected)
                print(f'Android coverage: {len(expected)} runnable cases, '
                      f'{self.count} shards of {min(sizes)}-{max(sizes)}; no gaps or duplicates')
        finally:
            os.chdir(saved_cwd)
            sys.argv = saved_argv

    def run_fake_suite(self, exit_code, args):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / 'tools/mobile-test/android/run-suite-shard.sh'
            script.parent.mkdir(parents=True)
            shutil.copy2(RUNNER, script)
            record = root / 'invocation.json'
            test = root / 'tools/test.py'
            test.write_text(f'#!{sys.executable}\nimport json,sys\n'
                            f'open({str(record)!r}, "w").write(json.dumps(sys.argv[1:]))\n'
                            'print("suite output")\n'
                            f'sys.exit({exit_code})\n')
            test.chmod(0o755)
            # Keep diagnostics local; no device or adb daemon is required.
            fake_adb = root / 'adb'
            fake_adb.write_text('#!/bin/sh\nexit 0\n')
            fake_adb.chmod(0o755)
            proc = subprocess.run(['bash', str(script), *args], cwd=root,
                                  env=dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH']),
                                  capture_output=True, text=True, timeout=20)
            invocation = json.loads(record.read_text()) if record.exists() else None
            log = (root / 'shard.log').read_text() if (root / 'shard.log').exists() else ''
            resources = (root / 'shard-resources.log').exists()
            return proc, invocation, log, resources

    def test_success_keeps_test_output_and_selector(self):
        proc, invocation, log, resources = self.run_fake_suite(0, ['3', str(self.count)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f'--run=3,{self.count}', invocation)
        self.assertEqual(invocation[-2:], ['parallel', 'sequential'])
        self.assertIn('suite output', log)
        self.assertTrue(resources)

    def test_failure_is_not_hidden_by_tee_or_cleanup(self):
        proc, _, log, resources = self.run_fake_suite(7, ['0', str(self.count)])
        self.assertEqual(proc.returncode, 7, proc.stderr)
        self.assertIn('suite output', log)
        self.assertTrue(resources)

    def test_invalid_shard_cannot_run_tests(self):
        for args in (['-1', '16'], ['16', '16'], ['0', '0'], ['x', '16']):
            with self.subTest(args=args):
                proc, invocation, _, _ = self.run_fake_suite(0, args)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIsNone(invocation)


if __name__ == '__main__':
    unittest.main()
