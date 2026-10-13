#!/usr/bin/env python3
"""Exercise verified emulator installs and SDK forwarding without the network."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
ACTION = ROOT / '.github/actions/prepare-android-emulator'


class EmulatorPreparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mobile-emulator-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.action = self.root / 'action'
        shutil.copytree(ACTION, self.action)
        self.sdk = self.root / 'android sdk'
        self.manager = self.sdk / 'cmdline-tools/latest/bin/sdkmanager'
        self.manager.parent.mkdir(parents=True)
        self.manager.write_text(
            '#!/usr/bin/env python3\nimport json,os,sys\n'
            'open(os.environ["FORWARDED"],"w").write(json.dumps(sys.argv[1:]))\n'
            'sys.exit(int(os.environ.get("SDK_EXIT", "0")))\n')
        self.manager.chmod(0o755)
        self.original = self.manager.read_bytes()
        self.runner = self.root / 'runner temp'
        self.runner.mkdir()
        self.archive = self.runner / 'emulator-linux_x64-16428233.zip'
        self.payload = self.root / 'good.zip'
        info = zipfile.ZipInfo('emulator/emulator')
        info.external_attr = 0o100755 << 16
        with zipfile.ZipFile(self.payload, 'w') as archive:
            archive.writestr(info, '#!/bin/sh\nprintf "%s\\n" "Android emulator version '
                             '37.2.12.0 (build_id 16428233)"\n')
            archive.writestr('emulator/source.properties',
                             'Pkg.Revision=37.2.12\nPkg.BuildId=16428233\n')
        pin = (self.action / 'pin.sh').read_text()
        import re
        pin = re.sub(r'^EMULATOR_SIZE=.*$', f'EMULATOR_SIZE={self.payload.stat().st_size}', pin, flags=re.M)
        digest = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        pin = re.sub(r'^EMULATOR_SHA256=.*$', 'EMULATOR_SHA256=' + digest, pin, flags=re.M)
        (self.action / 'pin.sh').write_text(pin)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        curl = self.bin / 'curl'
        curl.write_text('''#!/usr/bin/env python3
import os,pathlib,shutil,sys
count=pathlib.Path(os.environ['CURL_COUNT'])
n=int(count.read_text())+1 if count.exists() else 1
count.write_text(str(n))
output=pathlib.Path(sys.argv[sys.argv.index('-o')+1])
if n <= int(os.environ.get('BAD_TRANSFERS','0')):
    output.write_bytes(b'truncated zip')
else:
    shutil.copyfile(os.environ['GOOD_ARCHIVE'],output)
''')
        curl.chmod(0o755)
        sleep = self.bin / 'sleep'
        sleep.write_text('#!/bin/sh\nexit 0\n')
        sleep.chmod(0o755)
        self.env = dict(os.environ, ANDROID_HOME=str(self.sdk), RUNNER_TEMP=str(self.runner),
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        FORWARDED=str(self.root / 'forwarded.json'),
                        CURL_COUNT=str(self.root / 'curl-count'), GOOD_ARCHIVE=str(self.payload))

    def install(self, **overrides):
        return subprocess.run(['bash', str(self.action / 'install.sh')],
                              env=dict(self.env, **overrides), text=True, capture_output=True)

    def sdkmanager(self, *args, **overrides):
        return subprocess.run([str(self.manager), *args], env=dict(self.env, **overrides),
                              text=True, capture_output=True)

    def test_verified_cache_avoids_network_and_stable_update(self):
        shutil.copyfile(self.payload, self.archive)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(Path(self.env['CURL_COUNT']).exists())
        result = self.sdkmanager('--install', 'emulator', '--channel=0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('checksum-verified', result.stdout)
        self.assertFalse(Path(self.env['FORWARDED']).exists())

    def test_corrupt_cache_and_transfer_are_replaced_only_after_verification(self):
        self.archive.write_bytes(b'corrupt cached response')
        result = self.install(BAD_TRANSFERS='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(self.env['CURL_COUNT']).read_text(), '2')
        self.assertEqual(self.archive.read_bytes(), self.payload.read_bytes())

    def test_exhausted_download_does_not_replace_tools_or_start_tests(self):
        result = self.install(BAD_TRANSFERS='9')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(Path(self.env['CURL_COUNT']).read_text(), '3')
        self.assertEqual(self.manager.read_bytes(), self.original)
        self.assertFalse((self.sdk / 'emulator').exists())

    def test_sdk_installs_arguments_and_failures_are_forwarded_unchanged(self):
        self.assertEqual(self.install().returncode, 0)
        for args in [('--licenses',), ('--install', 'system-images;android-30;default;x86_64', '--channel=0'),
                     ('--install', 'emulator', 'platform-tools', '--channel=0'),
                     ('--install', 'emulator', '--channel=1'), ('ndk;27.3.13750724',)]:
            with self.subTest(args=args):
                result = self.sdkmanager(*args, SDK_EXIT='7')
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(json.loads(Path(self.env['FORWARDED']).read_text()), list(args))

    def test_preparation_is_idempotent_and_damaged_binary_fails(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.install().returncode, 0)
        emulator = self.sdk / 'emulator/emulator'
        emulator.write_text('#!/bin/sh\nexit 9\n')
        result = self.sdkmanager('--install', 'emulator', '--channel=0')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(Path(self.env['FORWARDED']).exists())

    def test_all_emulator_jobs_prepare_before_launch(self):
        import yaml
        found = 0
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            for job in workflow.get('jobs', {}).values():
                prepared = False
                for step in job.get('steps', []):
                    if step.get('uses') == './.github/actions/prepare-android-emulator':
                        prepared = True
                    if step.get('uses', '').startswith('reactivecircus/android-emulator-runner@'):
                        self.assertTrue(prepared, str(path))
                        found += 1
        self.assertEqual(found, 3)

    def test_emulator_runtime_dependency_is_installed_before_binary_validation(self):
        import yaml
        action = yaml.load((ACTION / 'action.yml').read_text(), Loader=yaml.BaseLoader)
        steps = action['runs']['steps']
        installer = next(i for i, step in enumerate(steps) if 'install.sh' in step.get('run', ''))
        self.assertTrue(any('apt-get install -y libpulse0' in step.get('run', '')
                            for step in steps[:installer]))


if __name__ == '__main__':
    unittest.main()
