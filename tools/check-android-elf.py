#!/usr/bin/env python3
"""Check Android shared libraries' LOAD and RELRO alignment using ELF headers."""
import pathlib
import struct
import sys


def check(path):
    data = path.read_bytes()
    if data[:4] != b'\x7fELF' or data[4] not in (1, 2) or data[5] != 1:
        raise ValueError('expected a little-endian ELF32/ELF64 library')
    is64 = data[4] == 2
    phoff = struct.unpack_from('<Q' if is64 else '<I', data, 32 if is64 else 28)[0]
    size, count = struct.unpack_from('<HH', data, 54 if is64 else 42)
    expected_size = 56 if is64 else 32
    if size < expected_size or not count or phoff + size * count > len(data):
        raise ValueError('invalid program header table')
    loads = 0
    for index in range(count):
        fields = struct.unpack_from('<IIQQQQQQ' if is64 else '<IIIIIIII',
                                    data, phoff + size * index)
        if is64:
            kind, _, offset, address, _, _, memory, alignment = fields
        else:
            kind, offset, address, _, _, memory, _, alignment = fields
        if kind == 1:
            loads += 1
            if alignment < 16384 or offset % 16384 != address % 16384:
                raise ValueError('PT_LOAD is not 16 KB aligned')
        elif kind == 0x6474e552 and (address + memory) % 16384:
            raise ValueError('GNU_RELRO end is not 16 KB aligned')
    if not loads:
        raise ValueError('missing PT_LOAD')
    print(f'ANDROID_ELF_16K_OK {path}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: check-android-elf.py library.so [...]')
    for argument in sys.argv[1:]:
        try:
            check(pathlib.Path(argument))
        except (ValueError, struct.error, OSError) as error:
            sys.exit(f'{argument}: {error}')
