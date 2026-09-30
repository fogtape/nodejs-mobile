#!/usr/bin/env python3
"""Check mobile Rust action isolation and libffi's iOS ABI headers."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else Path('out').resolve()


class MobileToolchains(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='node-mobile-toolchains-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rustc = self.root / 'rustc'
        rustc.write_text('#!/bin/sh\nprintf "host: x86_64-unknown-linux-gnu\\n"\n')
        rustc.chmod(0o755)
        cargo = self.root / 'cargo'
        cargo.write_text('#!' + sys.executable + '''
import json, os
from pathlib import Path
import sys
args = sys.argv[1:]
target = args[args.index('--target') + 1]
folder = Path(args[args.index('--target-dir') + 1])
profile = 'release' if '--release' in args else 'debug'
archive = folder / target / profile / 'libnode_crates.a'
archive.parent.mkdir(parents=True, exist_ok=True)
archive.write_text(target)
Path(os.environ['MOBILE_TEST_RECORD']).write_text(json.dumps({'args': args, 'env': dict(os.environ)}))
''')
        cargo.chmod(0o755)
        self.env = dict(os.environ, RUSTC=str(rustc), CARGO=str(cargo),
                        MOBILE_TEST_RECORD=str(self.root / 'record.json'))
        self.ndk = self.root / 'NDK with spaces'
        tools = self.ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
        tools.mkdir(parents=True)
        for triple in ('armv7a-linux-androideabi', 'aarch64-linux-android', 'x86_64-linux-android'):
            (tools / (triple + '24-clang')).touch()
        (tools / 'llvm-ar').touch()

    def run_action(self, arch, toolset, configuration='Release', os_name='android', simulator='false'):
        output = self.root / toolset / 'libnode_crates.a'
        env = dict(self.env, SDKROOT='must-not-leak-into-host')
        if os_name == 'ios':
            xcrun = self.root / 'xcrun'
            xcrun.write_text('#!/bin/sh\nprintf "/mock/%s.sdk\\n" "$2"\n')
            xcrun.chmod(0o755)
            env['PATH'] = str(self.root) + os.pathsep + env['PATH']
        subprocess.run([sys.executable, str(SOURCE / 'deps/crates/mobile-cargo-build.py'),
                        '--os', os_name, '--arch', arch, '--toolset', toolset,
                        '--configuration', configuration, '--output', str(output),
                        '--ndk', str(self.ndk), '--ios-simulator', simulator],
                       env=env, check=True, cwd=SOURCE / 'deps/crates')
        return output.read_text(), json.loads((self.root / 'record.json').read_text())

    def test_android_target_and_native_host_are_separate(self):
        for arch, target in [('arm', 'armv7-linux-androideabi'),
                             ('arm64', 'aarch64-linux-android'),
                             ('x64', 'x86_64-linux-android')]:
            with self.subTest(arch=arch):
                built, record = self.run_action(arch, 'target')
                self.assertEqual(built, target)
                self.assertIn('--release', record['args'])
                self.assertIn('--frozen', record['args'])
                key = target.upper().replace('-', '_')
                self.assertTrue(record['env'][f'CARGO_TARGET_{key}_LINKER'].endswith('24-clang'))
                self.assertIn('relocation-model=pic', record['env'][f'CARGO_TARGET_{key}_RUSTFLAGS'])
                built, record = self.run_action(arch, 'host')
                self.assertEqual(built, 'x86_64-unknown-linux-gnu')
                self.assertNotIn('SDKROOT', record['env'])
                self.assertFalse(any(key.endswith('_LINKER') for key in record['env'] if key.startswith('CARGO_TARGET_')))

    def test_debug_profile_does_not_use_release_archive(self):
        _, record = self.run_action('arm64', 'target', 'Debug')
        self.assertNotIn('--release', record['args'])

    def test_ios_device_and_simulator_archives_use_correct_sdk(self):
        for simulator, target, sdk in [('false', 'aarch64-apple-ios', 'iphoneos'),
                                      ('true', 'aarch64-apple-ios-sim', 'iphonesimulator')]:
            built, record = self.run_action('arm64', 'target', os_name='ios', simulator=simulator)
            self.assertEqual(built, target)
            self.assertEqual(record['env']['SDKROOT'], f'/mock/{sdk}.sdk')
            self.assertEqual(record['env']['IPHONEOS_DEPLOYMENT_TARGET'], '14.0')

    def test_gyp_links_host_and_target_archives_and_backends_separately(self):
        for name in ('crates', 'libffi'):
            folder = self.root / 'deps' / name
            folder.mkdir(parents=True)
            (folder / (name + '.gyp')).write_text((SOURCE / 'deps' / name / (name + '.gyp')).read_text())
        project = self.root / 'check.gyp'
        project.write_text(repr({'targets': [{
            'target_name': 'check', 'type': 'executable', 'toolsets': ['host', 'target'],
            'sources': ['check.c'], 'dependencies': [
                str(self.root / 'deps/crates/crates.gyp') + ':node_crates',
                str(self.root / 'deps/libffi/libffi.gyp') + ':libffi',
            ],
        }]}))
        (self.root / 'check.c').write_text('int main(void) { return 0; }\n')
        for os_name, host_os in [('android', 'linux'), ('ios', 'mac')]:
            with self.subTest(os=os_name):
                generated = self.root / os_name
                subprocess.run([sys.executable, str(SOURCE / 'tools/gyp/gyp_main.py'),
                    str(project), '-f', 'make', '--depth=' + str(self.root),
                    '--generator-output=' + str(generated),
                    '-DOS=' + os_name, '-Dhost_os=' + host_os,
                    '-Dtarget_arch=arm64', '-Dhost_arch=x64', '-Dbuild_type=Release',
                    '-Dpython=' + sys.executable, '-Dandroid_ndk_path=' + str(self.ndk),
                    '-Dandroid_api_level=24', '-Diossim=true'],
                    env=dict(self.env, GYP_CROSSCOMPILE='1'), check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                host = (generated / 'check.host.mk').read_text()
                target = (generated / 'check.target.mk').read_text()
                self.assertIn('mobile-rust/host/libnode_crates.a', host)
                self.assertNotIn('mobile-rust/target/libnode_crates.a', host)
                self.assertIn('mobile-rust/target/libnode_crates.a', target)
                self.assertNotIn('mobile-rust/host/libnode_crates.a', target)
                self.assertNotIn('-llog', host)
                if os_name == 'android':
                    self.assertIn('-llog', target)
                    self.assertIn('-lunwind', target)
                mk_root = generated / 'deps/libffi'
                host_ffi = (mk_root / 'libffi.host.mk').read_text()
                target_ffi = (mk_root / 'libffi.target.mk').read_text()
                self.assertIn('src/x86/ffi64.o', host_ffi)
                self.assertNotIn('src/aarch64/ffi.o', host_ffi)
                self.assertIn('src/aarch64/ffi.o', target_ffi)
                self.assertNotIn('src/x86/ffi64.o', target_ffi)

    def test_ios_libffi_uses_precompiled_callbacks_and_apple_long_double_abi(self):
        script = SOURCE / 'deps/libffi/generate-headers.py'
        spec = importlib.util.spec_from_file_location('ffi_headers', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.generate_headers(self.root / 'ios', 'arm64', 'ios')
        header = (self.root / 'ios/fficonfig.h').read_text()
        self.assertIn('#define FFI_EXEC_TRAMPOLINE_TABLE 1', header)
        self.assertEqual(module.has_long_double('ios', 'arm64'), '0')
        self.assertEqual(module.has_long_double('android', 'arm64'), '1')
        module.generate_headers(self.root / 'android', 'arm64', 'android')
        android = (self.root / 'android/fficonfig.h').read_text()
        self.assertIn('#define FFI_MMAP_EXEC_WRIT 1', android)


if __name__ == '__main__':
    unittest.main()
