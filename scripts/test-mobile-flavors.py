#!/usr/bin/env python3
"""Check flavor flags, iOS archive selection and danmu_api ICU regressions."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'out'
if len(sys.argv) > 1:
    del sys.argv[1]
MAJOR = int(re.search(r'^#define NODE_MAJOR_VERSION (\d+)$',
                     (SOURCE / 'src/node_version.h').read_text(), re.M)[1])
# android_configure supports Linux/macOS build hosts; simulate Linux so this
# configure-only test also runs on Termux's Python (which reports Android).
ANDROID_WRAPPER = [sys.executable, '-c',
                   "import platform,runpy,sys; platform.system=lambda:'Linux'; "
                   "sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')",
                   str(SOURCE / 'android_configure.py')]

CUTS = {'--without-amaro', '--without-inspector', '--without-sqlite',
        '--disable-single-executable-application', '--v8-disable-object-print'}
if MAJOR >= 26:
    CUTS |= {'--without-ffi', '--v8-disable-temporal-support'}


class MobileFlavors(unittest.TestCase):
    def test_android_flags_and_pointer_compression(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            ndk = folder / 'ndk'
            ndk.mkdir()
            (ndk / 'marker').touch()
            capture = folder / 'configured.json'
            configure = folder / 'configure'
            configure.write_text(f'#!{sys.executable}\nimport json,sys\n'
                                 f'open({str(capture)!r}, "w").write(json.dumps({{"flags":sys.argv[1:],"gyp":__import__("os").environ.get("GYP_DEFINES","")}}))\n')
            configure.chmod(0o755)
            for flavor in ('full', 'lite'):
                for arch in ('arm', 'arm64', 'x86_64'):
                    with self.subTest(flavor=flavor, arch=arch):
                        env = dict(os.environ, NODEJS_MOBILE_FLAVOR=flavor)
                        env.pop('NODEJS_MOBILE_SCCACHE', None)
                        subprocess.run(ANDROID_WRAPPER + [str(ndk), '24', arch], cwd=folder, env=env,
                                       check=True, capture_output=True, text=True)
                        captured = json.loads(capture.read_text())
                        flags = set(captured['flags'])
                        self.assertEqual('node_mobile_icu_profile=danmu-lite.json' in captured['gyp'],
                                         flavor == 'lite')
                        self.assertIn('--with-intl=full-icu', flags)
                        self.assertIn('--shared', flags)
                        self.assertIn('--cross-compiling', flags)
                        if flavor == 'lite':
                            self.assertTrue(CUTS <= flags, CUTS - flags)
                        else:
                            self.assertFalse(CUTS & flags)
                            if MAJOR >= 26:
                                self.assertIn('--v8-enable-temporal-support', flags)
                        self.assertEqual('--experimental-enable-pointer-compression' in flags,
                                         flavor == 'lite' and arch != 'arm')
            env['NODEJS_MOBILE_FLAVOR'] = 'invalid'
            result = subprocess.run(ANDROID_WRAPPER + [str(ndk), '24', 'arm64'], cwd=folder, env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_ios_flags_and_framework_archives(self):
        script = (SOURCE / 'tools/ios_framework_prepare.sh').read_text()
        prefix = script.split('build_for_arm64_device() {', 1)[0]
        probe = prefix + '''
printf '\nINTL:%s\nFLAGS:%s\nICU_PROFILE:%s\n' "$INTL" "$LITE_FLAGS" "$ICU_PROFILE_GYP_DEFINES"
for archive in "${outputs_arm64[@]}"; do printf 'LIB:%s\n' "$archive"; done
'''
        project = (SOURCE / 'tools/ios-framework/NodeMobile.xcodeproj/project.pbxproj').read_text()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'ios-flavor-probe.sh'
            path.write_text(probe)
            for flavor in ('full', 'lite'):
                with self.subTest(flavor=flavor):
                    result = subprocess.run(['bash', str(path)],
                                            env=dict(os.environ, NODEJS_MOBILE_FLAVOR=flavor),
                                            capture_output=True, text=True, check=True)
                    lines = result.stdout.splitlines()
                    self.assertIn('INTL:full-icu', lines)
                    self.assertIn('ICU_PROFILE:' + ('node_mobile_icu_profile=danmu-lite.json' if flavor == 'lite' else ''), lines)
                    flags = set(shlex.split(next(line[6:] for line in lines
                                                 if line.startswith('FLAGS:'))))
                    archives = {line[4:] for line in lines if line.startswith('LIB:')}
                    self.assertTrue({'libicudata.a', 'libicui18n.a', 'libicuucx.a'} <= archives)
                    self.assertNotIn('libicustubdata.a', archives)
                    self.assertNotIn('libicustubdata.a', project)
                    for archive in archives:
                        self.assertIn(archive, project, f'{archive} has no Xcode link entry')
                    for archive in ('libcrdtp.a', 'libsqlite.a'):
                        self.assertEqual(archive in archives, flavor == 'full')
                    if flavor == 'lite':
                        self.assertTrue(CUTS <= flags, CUTS - flags)
                    else:
                        self.assertFalse(CUTS & flags)
                    if MAJOR >= 26:
                        for archive in ('libffi.a', 'libnode_crates.a'):
                            self.assertEqual(archive in archives, flavor == 'full')

    def test_preview_metadata_matches_flavors(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source, output = folder / 'input', folder / 'output'
            for platform in ('android', 'ios'):
                for flavor in ('full', 'lite'):
                    suffix = '-lite' if flavor == 'lite' else ''
                    artifact = source / f'nodejs-mobile-{platform}{suffix}'
                    required = ['include/node/node_version.h']
                    if platform == 'android':
                        required += [f'bin/{abi}/libnode.so'
                                     for abi in ('arm64-v8a', 'armeabi-v7a', 'x86_64')]
                    else:
                        required += ['NodeMobile.xcframework/Info.plist']
                    for name in required:
                        path = artifact / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b'fixture')
            subprocess.run([sys.executable, str(ROOT / 'scripts/package-preview.py'),
                            str(source), str(output)], cwd=ROOT,
                           env=dict(os.environ, GITHUB_REPOSITORY='fogtape/nodejs-mobile',
                                    GITHUB_RUN_ID='1'), check=True,
                           capture_output=True, text=True)
            for package in output.glob('*.zip'):
                with zipfile.ZipFile(package) as archive:
                    info = json.loads(archive.read('BUILD-INFO.json'))
                lite = info['flavor'] == 'lite'
                self.assertEqual(info['icu_api_mode'], 'full-icu')
                self.assertEqual(info['icu_data_profile'], 'danmu-lite' if lite else 'complete')
                self.assertEqual('full-icu' in info['enabled_features'], not lite)
                self.assertEqual('danmu-icu-profile' in info['enabled_features'], lite)
                for feature in ('node:ffi', 'Temporal'):
                    self.assertEqual(feature in info['enabled_features'], not lite)
                    self.assertEqual(feature in info['disabled_features'], lite)
            lines = (output / 'SHA256SUMS').read_text().splitlines()
            self.assertEqual(len(lines), 4)
            for line in lines:
                digest, name = line.split()
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)

    def test_icu_profile_required_resources_exist_in_pinned_data(self):
        # A version upgrade must fail loudly if renamed ICU data invalidates the
        # reviewed locale/converter closure. Parse the actual canned package.
        import bz2
        import importlib.util
        import re
        import struct
        major = re.search(r'"(\d+)\.',
                          (SOURCE / 'deps/icu-small/source/common/unicode/uvernum.h').read_text()).group(1)
        canned = SOURCE / f'deps/icu-small/source/data/in/icudt{major}l.dat'
        data = canned.read_bytes() if canned.exists() else bz2.decompress(
            canned.with_suffix('.dat.bz2').read_bytes())
        header = struct.unpack_from('<H', data)[0]
        count = struct.unpack_from('<I', data, header)[0]
        items = set()
        for index in range(count):
            offset = struct.unpack_from('<I', data, header + 4 + index * 8)[0] + header
            items.add(data[offset:data.index(b'\0', offset)].decode().split('/', 1)[1])
        helper_path = SOURCE / 'tools/icu/prepare-mobile-icu.py'
        spec = importlib.util.spec_from_file_location('mobile_icu_profile', helper_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        profile = json.loads((SOURCE / 'tools/icu/danmu-lite.json').read_text())
        self.assertFalse(module.required_items(profile, items) - items)
        for item in ('uts46.nrm', 'nfkc.nrm', 'cnvalias.icu', 'zoneinfo64.res',
                     'coll/ucadata.icu', 'windows-950-2000.cnv', 'ibm-1373_P100-2002.cnv'):
            self.assertIn(item, module.required_items(profile, items))

    def test_required_icu_smoke_on_host(self):
        # Exercise the exact shipped smoke with a host Node that has full ICU.
        # FFI/Temporal are specific to the Node 26 host build and are tested by CI.
        source = (SOURCE / 'tools/mobile-test/smoke/mobile-features.js').read_text()
        icu = source.split("console.log('NODEJS_MOBILE_FEATURE_STAGE icu');", 1)[1]
        if MAJOR >= 26:
            icu = icu.split('const ffiEnabled =', 1)[0]
        else:
            icu = icu.split('console.log(`NODEJS_MOBILE_FEATURES_OK', 1)[0]
        subprocess.run(['node', '-e', "const assert=require('node:assert/strict');const lite=false;\n" + icu],
                       check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
