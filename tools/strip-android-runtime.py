#!/usr/bin/env python3
"""Strip copied Android runtimes without changing the dynamic-linking ABI."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def dynamic_symbols(nm, library):
    return subprocess.check_output(
        [str(nm), '-D', '--format=posix', str(library)], text=True)


def strip_library(tools, library):
    suffix = '.exe' if os.name == 'nt' else ''
    nm, strip = (tools / ('llvm-' + name + suffix) for name in ('nm', 'strip'))
    before = dynamic_symbols(nm, library)
    if '_ZN4node5StartEiPPc ' not in before:
        raise RuntimeError(f'{library}: missing node::Start embedding entry point')
    original_size = library.stat().st_size
    # Leave the input intact on any tool or symbol verification failure.
    with tempfile.TemporaryDirectory(prefix='.strip-', dir=library.parent) as temp:
        staged = Path(temp) / library.name
        shutil.copy2(library, staged)
        subprocess.run([str(strip), '--strip-unneeded', str(staged)], check=True)
        if dynamic_symbols(nm, staged) != before:
            raise RuntimeError(f'{library}: strip changed dynamic symbols')
        if staged.stat().st_size > original_size:
            raise RuntimeError(f'{library}: stripped file grew unexpectedly')
        os.replace(staged, library)
    print(f'{library}: {original_size} -> {library.stat().st_size} bytes; '
          'dynamic symbols unchanged')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    tools = parser.add_mutually_exclusive_group(required=True)
    tools.add_argument('--ndk', type=Path)
    tools.add_argument('--tools', type=Path, help='LLVM bin directory (local verification)')
    parser.add_argument('path', type=Path, help='libnode.so or out_android directory')
    args = parser.parse_args()
    if args.ndk:
        suffix = '.exe' if os.name == 'nt' else ''
        candidates = sorted((args.ndk / 'toolchains/llvm/prebuilt').glob('*/bin/llvm-strip' + suffix))
        if len(candidates) != 1:
            parser.error('expected one NDK prebuilt LLVM tool directory')
        args.tools = candidates[0].parent
    libraries = [args.path] if args.path.is_file() else sorted(args.path.glob('*/libnode.so'))
    if not libraries:
        parser.error(f'no libnode.so found at {args.path}')
    for library in libraries:
        strip_library(args.tools, library)


if __name__ == '__main__':
    main()
