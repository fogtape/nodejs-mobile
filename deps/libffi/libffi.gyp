{
  'variables': {
    'host_os%': '<(OS)',
    'libffi_sources': [
      'src/closures.c',
      'src/debug.c',
      'src/java_raw_api.c',
      'src/prep_cif.c',
      'src/raw_api.c',
      'src/tramp.c',
      'src/types.c',
    ],
    'libffi_defines%': [],
    'libffi_arch_sources%': [],
  },
  'conditions': [
    ['OS == "win"', {
      'conditions': [
        ['target_arch == "ia32" or target_arch == "x86"', {
          'variables': {
            'libffi_arch_sources': [
              'src/x86/ffi.c',
            ],
          },
        }],
        ['target_arch == "x64" or target_arch == "x86_64"', {
          'variables': {
            'libffi_arch_sources': [
              'src/x86/ffiw64.c',
            ],
          },
        }],
        ['target_arch == "arm"', {
          'variables': {
            'libffi_arch_sources': [
              'src/arm/ffi.c',
            ],
          },
        }],
        ['target_arch == "arm64"', {
          'variables': {
            'libffi_arch_sources': [
              'src/aarch64/ffi.c',
            ],
          },
        }],
      ],
    }],
    ['OS != "win"', {
      'conditions': [
        ['target_arch == "ia32" or target_arch == "x86"', {
          'variables': {
            'libffi_arch_sources': [
              'src/x86/ffi.c',
              'src/x86/sysv.S',
            ],
          },
        }],
        ['target_arch == "x64" or target_arch == "x86_64"', {
          'variables': {
            'libffi_arch_sources': [
              'src/x86/ffiw64.c',
              'src/x86/ffi64.c',
              'src/x86/unix64.S',
              'src/x86/win64.S',
            ],
          },
        }],
        ['target_arch == "arm"', {
          'variables': {
            'libffi_arch_sources': [
              'src/arm/ffi.c',
              'src/arm/sysv.S',
            ],
          },
        }],
        ['target_arch == "arm64"', {
          'variables': {
            'libffi_arch_sources': [
              'src/aarch64/ffi.c',
              'src/aarch64/sysv.S',
            ],
          },
        }],
        ['target_arch == "riscv64"', {
          'variables': {
            'libffi_arch_sources': [
              'src/riscv/ffi.c',
              'src/riscv/sysv.S',
            ],
          },
        }],
        ['target_arch == "loong64"', {
          'variables': {
            'libffi_arch_sources': [
              'src/loongarch/ffi.c',
              'src/loongarch/sysv.S',
            ],
          },
        }],
        ['target_arch == "mips" or target_arch == "mipsel" or target_arch == "mips64el"', {
          'variables': {
            'libffi_arch_sources': [
              'src/mips/ffi.c',
              'src/mips/o32.S',
              'src/mips/n32.S',
            ],
          },
        }],
        ['target_arch == "ppc64" and OS == "mac"', {
          'variables': {
            'libffi_arch_sources': [
              'src/powerpc/ffi_darwin.c',
              'src/powerpc/darwin.S',
              'src/powerpc/darwin_closure.S',
            ],
          },
        }],
        ['target_arch == "ppc64" and OS == "aix"', {
          'variables': {
            'libffi_arch_sources': [
              'src/powerpc/ffi_darwin.c',
              'src/powerpc/aix.S',
              'src/powerpc/aix_closure.S',
            ],
          },
        }],
        ['target_arch == "ppc64" and (OS == "freebsd" or OS == "openbsd")', {
          'variables': {
            'libffi_arch_sources': [
              'src/powerpc/ffi.c',
              'src/powerpc/ffi_sysv.c',
              'src/powerpc/sysv.S',
              'src/powerpc/ppc_closure.S',
            ],
          },
        }],
        ['target_arch == "ppc64" and OS == "linux"', {
          'variables': {
            'libffi_arch_sources': [
              'src/powerpc/ffi.c',
              'src/powerpc/ffi_sysv.c',
              'src/powerpc/ffi_linux64.c',
              'src/powerpc/sysv.S',
              'src/powerpc/ppc_closure.S',
              'src/powerpc/linux64.S',
              'src/powerpc/linux64_closure.S',
            ],
          },
        }],
      ],
    }],
  ],
  'targets': [
    {
      'target_name': 'libffi',
      # Snapshot tools also link Node's FFI support during mobile cross-builds.
      'toolsets': ['host', 'target'],
      'type': 'static_library',
      'hard_dependency': 1,
      'cflags': ['-fvisibility=hidden'],
      'xcode_settings': {
        'GCC_SYMBOLS_PRIVATE_EXTERN': 'YES',
      },
      'defines': [
        'FFI_STATIC_BUILD',
        '<@(libffi_defines)',
      ],
      'include_dirs': [
        'include',
        'src',
        '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)',
      ],
      'sources': [
        '<@(libffi_sources)',
        '<@(libffi_arch_sources)',
      ],
      'actions': [
        {
          'action_name': 'generate_libffi_headers',
          'inputs': [
            'generate-headers.py',
            'include/ffi.h.in',
            'src/aarch64/ffitarget.h',
            'src/arm/ffitarget.h',
            'src/loongarch/ffitarget.h',
            'src/mips/ffitarget.h',
            'src/powerpc/ffitarget.h',
            'src/riscv/ffitarget.h',
            'src/x86/ffitarget.h',
          ],
          'outputs': [
            '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/ffi.h',
            '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/fficonfig.h',
            '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/ffitarget.h',
          ],
          'action': [
            '<(python)',
            'generate-headers.py',
            '--output-dir',
            '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)',
            '--target-arch',
            '<(target_arch)',
            '--os',
            '<(OS)',
            '--toolset', '<(_toolset)',
            # GYP deduplicates equal list entries (e.g. target/host arm64).
            '--host-arch=<(host_arch)',
            '--host-os=<(host_os)',
          ],
        },
      ],
      'conditions': [
        ['OS == "win" and (target_arch == "x64" or target_arch == "x86_64")', {
          'actions': [
            {
              'action_name': 'preprocess_win64_intel_asm',
              'process_outputs_as_sources': 1,
              'inputs': [
                'preprocess_asm.py',
                'include/ffi_cfi.h',
                'src/x86/asmnames.h',
                'src/x86/win64_intel.S',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/ffi.h',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/fficonfig.h',
              ],
              'outputs': [
                '<(INTERMEDIATE_DIR)/win64_intel.asm',
              ],
              'action': [
                '<(python)',
                'preprocess_asm.py',
                '--input',
                'src/x86/win64_intel.S',
                '--output',
                '<@(_outputs)',
                '--include-dir',
                'include',
                '--include-dir',
                'src/x86',
                '--include-dir',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)',
                '--define',
                'FFI_STATIC_BUILD',
              ],
            },
          ],
        }],
        ['OS == "win" and (target_arch == "ia32" or target_arch == "x86")', {
          'actions': [
            {
              'action_name': 'preprocess_win32_intel_asm',
              'process_outputs_as_sources': 1,
              'inputs': [
                'preprocess_asm.py',
                'include/ffi_cfi.h',
                'src/x86/asmnames.h',
                'src/x86/sysv_intel.S',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/ffi.h',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/fficonfig.h',
              ],
              'outputs': [
                '<(INTERMEDIATE_DIR)/sysv_intel.asm',
              ],
              'action': [
                '<(python)',
                'preprocess_asm.py',
                '--input',
                'src/x86/sysv_intel.S',
                '--output',
                '<@(_outputs)',
                '--include-dir',
                'include',
                '--include-dir',
                'src/x86',
                '--include-dir',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)',
                '--define',
                'FFI_STATIC_BUILD',
              ],
            },
          ],
        }],
        ['OS == "win" and target_arch == "arm"', {
          'actions': [
            {
              'action_name': 'preprocess_win32_arm_asm',
              'process_outputs_as_sources': 1,
              'inputs': [
                'preprocess_asm.py',
                'include/ffi_cfi.h',
                'src/arm/sysv_msvc_arm32.S',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/ffi.h',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/fficonfig.h',
              ],
              'outputs': [
                '<(INTERMEDIATE_DIR)/sysv_msvc_arm32.asm',
              ],
              'action': [
                '<(python)',
                'preprocess_asm.py',
                '--input',
                'src/arm/sysv_msvc_arm32.S',
                '--output',
                '<@(_outputs)',
                '--include-dir',
                'include',
                '--include-dir',
                'src/arm',
                '--include-dir',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)',
                '--define',
                'FFI_STATIC_BUILD',
              ],
            },
          ],
        }],
        ['OS == "win" and target_arch == "arm64"', {
          # Link the prebuilt object file directly
          'libraries': [
            '<(INTERMEDIATE_DIR)/win64_armasm.obj',
          ],
          'actions': [
            {
              'action_name': 'assemble_win64_arm_asm',
              # Don't use process_outputs_as_sources - we link the .obj directly
              'inputs': [
                'preprocess_asm.py',
                'include/ffi_cfi.h',
                'src/aarch64/internal.h',
                'src/aarch64/win64_armasm.S',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/ffi.h',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)/fficonfig.h',
              ],
              'outputs': [
                '<(INTERMEDIATE_DIR)/win64_armasm.obj',
              ],
              'action': [
                '<(python)',
                'preprocess_asm.py',
                '--input',
                'src/aarch64/win64_armasm.S',
                '--output',
                '<(INTERMEDIATE_DIR)/win64_armasm.asm',
                '--include-dir',
                'include',
                '--include-dir',
                'src/aarch64',
                '--include-dir',
                '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)',
                '--define',
                'FFI_STATIC_BUILD',
                '--assemble',
                '<@(_outputs)',
              ],
            },
          ],
        }],
      ],
      # The global architecture selection above belongs to the mobile
      # target. Native host tools need their own source backend and headers.
      'target_conditions': [
        ['_toolset=="host" and OS in "android ios"', {
          # Architecture variables from config.gypi are available in early
          # conditions, but not in the late _toolset expression above.
          'conditions': [
            ['host_arch!=target_arch and not (OS=="android" and host_arch=="x64" and target_arch=="ia32")', {
              'sources!': ['<@(libffi_arch_sources)'],
              'conditions': [
                ['host_arch=="ia32" or (OS=="android" and host_arch=="x64" and target_arch=="arm")', {
                  'sources': ['src/x86/ffi.c', 'src/x86/sysv.S'],
                }],
                ['host_arch=="x64" and not (OS=="android" and target_arch=="arm")', {
                  'sources': [
                    'src/x86/ffiw64.c', 'src/x86/ffi64.c',
                    'src/x86/unix64.S', 'src/x86/win64.S',
                  ],
                }],
                ['host_arch=="arm64"', {
                  'sources': ['src/aarch64/ffi.c', 'src/aarch64/sysv.S'],
                }],
              ],
            }],
          ],
        }],
      ],
      'direct_dependent_settings': {
        'include_dirs': [
          'include',
          '<(SHARED_INTERMEDIATE_DIR)/libffi/<(_toolset)',
        ],
        'defines': [
          'FFI_STATIC_BUILD',
        ],
      },
    },
  ],
}
