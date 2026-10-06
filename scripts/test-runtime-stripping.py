#!/usr/bin/env python3
"""Exercise the release strip helper on a real dynamically loaded library."""
import ctypes
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'out'
if len(sys.argv) > 1:
    del sys.argv[1]


class RuntimeStripping(unittest.TestCase):
    def test_exports_runtime_and_failure_atomicity(self):
        clang = shutil.which('clang++')
        strip = shutil.which('llvm-strip')
        self.assertIsNotNone(clang, 'clang++ is required')
        self.assertIsNotNone(strip, 'llvm-strip is required')
        tools = Path(strip).parent
        helper = SOURCE / 'tools/strip-android-runtime.py'
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'embedder.cc'
            source.write_text('namespace node { int Start(int argc, char**) { return argc + 40; } }\n'
                              'extern "C" int napi_test_export() { return 42; }\n')
            library = directory / 'libnode.so'
            subprocess.run([clang, '-shared', '-fPIC', '-g', '-O0', str(source),
                            '-o', str(library)], check=True, capture_output=True)
            before = library.stat().st_size
            command = [sys.executable, str(helper), '--tools', str(tools), str(library)]
            subprocess.run(command, check=True, capture_output=True)
            self.assertLess(library.stat().st_size, before)
            runtime = ctypes.CDLL(str(library))
            start = getattr(runtime, '_ZN4node5StartEiPPc')
            start.argtypes = [ctypes.c_int, ctypes.c_void_p]
            start.restype = ctypes.c_int
            self.assertEqual(start(2, None), 42)
            self.assertEqual(runtime.napi_test_export(), 42)
            digest = hashlib.sha256(library.read_bytes()).digest()
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(hashlib.sha256(library.read_bytes()).digest(), digest)

            # A failed entry-point/ABI check must leave the caller's file intact.
            invalid = directory / 'invalid.so'
            invalid.write_bytes(b'not an ELF library')
            result = subprocess.run(command[:-1] + [str(invalid)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(invalid.read_bytes(), b'not an ELF library')


if __name__ == '__main__':
    unittest.main()
