#!/usr/bin/env python3
"""Prepare complete or profiled ICU data without enabling Node's small-ICU mode."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def listing(icupkg, data):
    return set(subprocess.check_output([str(icupkg), '-l', str(data)], text=True).splitlines())


def required_items(profile, original):
    required = set(profile['keep'])
    # Protect selected locale resources and aliases, including parent fallbacks.
    for tree, settings in profile['trees'].items():
        if isinstance(settings, str):
            settings = profile['variables'][settings]
        prefix = '' if tree in ('ROOT', 'converters') else tree + '/'
        extension = '.cnv' if tree == 'converters' else '.res'
        for item in settings.get('only', []):
            name = prefix + item + extension
            if tree == 'converters' or name in original:
                required.add(name)
    return required


def prepare(tools, source, output, endian, profile_path):
    icupkg = tools / 'icupkg'
    output.parent.mkdir(parents=True, exist_ok=True)
    if not profile_path:
        subprocess.run([str(icupkg), '-t' + endian, str(source), str(output)], check=True)
        return
    profile = json.loads(Path(profile_path).read_text())
    original = listing(icupkg, source)
    required = required_items(profile, original)
    if missing := required - original:
        raise RuntimeError('ICU source is missing required data: ' + ', '.join(sorted(missing)))
    match = re.fullmatch(r'icudt(\d+)[bl]\.dat', source.name)
    if not match:
        raise RuntimeError(f'unrecognized ICU source data filename: {source.name}')
    # An independent package name prevents an installed host's complete ICU
    # from supplying resources that were deleted from the candidate package.
    name = 'dmlt' + match[1].zfill(3) + endian + '.dat'
    with tempfile.TemporaryDirectory(prefix='icu-profile-', dir=output.parent) as folder:
        folder = Path(folder)
        result = subprocess.run([
            sys.executable, str(Path(__file__).with_name('icutrim.py')),
            '-P', str(tools), '-D', str(source), '-T', str(folder / 'trim'),
            '-F', str(Path(profile_path).resolve()), '-O', name,
            '-e', 'little' if endian == 'l' else 'big',
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('ICU profile generation failed:\n' + result.stdout[-8000:])
        trimmed = folder / 'trim' / name
        if missing := required - listing(icupkg, trimmed):
            raise RuntimeError('ICU trimming removed required data: ' + ', '.join(sorted(missing)))
        staged = folder / output.name
        subprocess.run([str(icupkg), '-t' + endian, str(trimmed), str(staged)], check=True)
        # icupkg verifies data dependencies while repackaging. The conventional
        # package/entry-point name must remain icudt<N> for V8 and Node.
        staged.replace(output)
    print(f'ICU profile {Path(profile_path).name}: '
          f'{source.stat().st_size} -> {output.stat().st_size} bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endian', choices=('l', 'b'), required=True)
    parser.add_argument('--profile', default='')
    args = parser.parse_args()
    prepare(args.tools.resolve(), args.input.resolve(), args.output.resolve(),
            args.endian, args.profile)


if __name__ == '__main__':
    main()
