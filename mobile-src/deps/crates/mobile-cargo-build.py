#!/usr/bin/env python3
"""Build Temporal's Rust archive for one mobile GYP toolset.

GYP shares variables between host and target projects. Select the Rust triple
at action time and keep their archives separate, so torque/mksnapshot never
link an Android/iOS archive. Cargo consumes Node's vendored, locked crates.
"""

import argparse
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess


ANDROID_TARGETS = {
    'arm': ('armv7-linux-androideabi', 'armv7a-linux-androideabi'),
    'arm64': ('aarch64-linux-android', 'aarch64-linux-android'),
    'ia32': ('i686-linux-android', 'i686-linux-android'),
    'x64': ('x86_64-linux-android', 'x86_64-linux-android'),
}


def rust_host():
    output = subprocess.check_output(
        shlex.split(os.environ.get('RUSTC', 'rustc')) + ['-vV'], text=True)
    for line in output.splitlines():
        if line.startswith('host: '):
            return line.removeprefix('host: ').strip()
    raise RuntimeError('rustc -vV did not identify its host target')


def build(args):
    env = os.environ.copy()
    if args.toolset == 'host':
        target = rust_host()
        # A parent iOS cross-build may export its target SDK. Host proc macros
        # and snapshot tools must use the macOS SDK instead.
        env.pop('SDKROOT', None)
    elif args.os == 'android':
        target, compiler = ANDROID_TARGETS[args.arch]
        host_tag = 'darwin-x86_64' if platform.system() == 'Darwin' else 'linux-x86_64'
        tools = Path(args.ndk) / 'toolchains/llvm/prebuilt' / host_tag / 'bin'
        cc = tools / f'{compiler}{args.android_api}-clang'
        if not cc.is_file():
            raise RuntimeError(f'Android Rust compiler driver not found: {cc}')
        key = target.upper().replace('-', '_')
        env[f'CARGO_TARGET_{key}_LINKER'] = str(cc)
        env[f'CC_{target.replace("-", "_")}'] = str(cc)
        env[f'AR_{target.replace("-", "_")}'] = str(tools / 'llvm-ar')
    else:
        if args.arch == 'arm64':
            target = 'aarch64-apple-ios-sim' if args.ios_simulator == 'true' else 'aarch64-apple-ios'
        elif args.arch == 'x64' and args.ios_simulator == 'true':
            target = 'x86_64-apple-ios'
        else:
            raise RuntimeError(f'Unsupported iOS Rust target: {args.arch}')
        sdk = 'iphonesimulator' if args.ios_simulator == 'true' else 'iphoneos'
        env['SDKROOT'] = subprocess.check_output(
            ['xcrun', '--sdk', sdk, '--show-sdk-path'], text=True).strip()
        env.setdefault('IPHONEOS_DEPLOYMENT_TARGET', '14.0')

    # These flags apply to target dependencies too, without retargeting the
    # native proc macros Cargo builds for its own host.
    key = target.upper().replace('-', '_')
    flags_key = f'CARGO_TARGET_{key}_RUSTFLAGS'
    env[flags_key] = (env.get(flags_key, '') + ' -C relocation-model=pic').strip()
    output = Path(args.output).resolve()
    cargo_dir = output.parent / 'cargo'
    command = shlex.split(env.get('CARGO', 'cargo')) + [
        'rustc', '--frozen', '--target', target, '--target-dir', str(cargo_dir),
    ]
    profile = 'release' if args.configuration == 'Release' else 'debug'
    if profile == 'release':
        command.append('--release')
    subprocess.run(command, env=env, check=True)
    archive = cargo_dir / target / profile / 'libnode_crates.a'
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--os', choices=('android', 'ios'), required=True)
    parser.add_argument('--arch', required=True)
    parser.add_argument('--toolset', choices=('host', 'target'), required=True)
    parser.add_argument('--configuration', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--ndk', default='')
    parser.add_argument('--android-api', default='24')
    parser.add_argument('--ios-simulator', choices=('true', 'false'), default='false')
    build(parser.parse_args())


if __name__ == '__main__':
    main()
