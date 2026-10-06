#!/usr/bin/env python3
"""Package this run's tested mobile artifacts without publishing a release."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile


def main():
    source, output = map(Path, sys.argv[1:])
    header = Path('mobile-src/src/node_mobile_version.h').read_text()
    values = [re.search(rf'^#define {key} (\d+)$', header, re.M).group(1)
              for key in ('NODE_MOBILE_MAJOR_VERSION', 'NODE_MOBILE_MINOR_VERSION',
                          'NODE_MOBILE_PATCH_VERSION', 'NODE_MOBILE_REVISION')]
    version = '.'.join(values[:3]) + '-' + values[3]
    base = next(line.strip() for line in Path('upstream-base.txt').read_text().splitlines()
                if line.strip() and not line.startswith('#'))
    tree = next(line for line in Path('expected-tree.txt').read_text().splitlines()
                if re.fullmatch(r'[0-9a-f]{40}', line))
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    output.mkdir(parents=True, exist_ok=True)
    checksums = []
    for platform in ('android', 'ios'):
        for flavor in ('full', 'lite'):
            suffix = '-lite' if flavor == 'lite' else ''
            name = f'nodejs-mobile-{platform}{suffix}'
            artifact = source / name
            required = ['include/node/node_version.h']
            if platform == 'android':
                required += [f'bin/{abi}/libnode.so'
                             for abi in ('arm64-v8a', 'armeabi-v7a', 'x86_64')]
            else:
                required += ['NodeMobile.xcframework/Info.plist']
            for path in required:
                if not (artifact / path).is_file():
                    raise SystemExit(f'Missing {name}/{path}')
            info = dict(version=version, upstream=base, platform=platform,
                        flavor=flavor, recipe_commit=sha, source_tree=tree,
                        branch=os.environ.get('GITHUB_REF_NAME', ''),
                        run_url=f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
                        preview=True, icu_api_mode='full-icu',
                        icu_data_profile='complete' if flavor == 'full' else 'danmu-lite',
                        android_symbols='stripped' if platform == 'android' and flavor == 'lite' else 'default',
                        enabled_features=(['full-icu', 'node:ffi', 'Temporal'] if flavor == 'full' else ['icu', 'danmu-icu-profile']),
                        disabled_features=[] if flavor == 'full' else [
                            'node:ffi', 'Temporal', 'node:sqlite', 'Web Storage',
                            'Inspector', 'TypeScript type-stripping', 'SEA',
                            'V8 native debugger object print'])
            (artifact / 'BUILD-INFO.json').write_text(json.dumps(info, indent=2) + '\n')
            package = output / f'{name}-{version}-preview.zip'
            with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(artifact.rglob('*')):
                    if file.is_file():
                        archive.write(file, file.relative_to(artifact))
            with package.open('rb') as package_file:
                digest = hashlib.file_digest(package_file, 'sha256').hexdigest()
            checksums.append(f'{digest}  {package.name}')
            print(package)
    (output / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')


if __name__ == '__main__':
    main()
