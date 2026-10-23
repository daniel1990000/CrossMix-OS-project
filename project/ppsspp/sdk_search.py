#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Keep GCC 9 C++/intrinsic headers and runtimes, and use pinned SDK C libraries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

GCC = '/usr/lib/gcc-cross/aarch64-linux-gnu/9'
CXX = '/usr/aarch64-linux-gnu/include/c++/9'
SYSROOT = '/opt/sysroot'
C_INCLUDES = (GCC + '/include', SYSROOT + '/usr/include')
CXX_INCLUDES = (CXX, CXX + '/aarch64-linux-gnu', CXX + '/backward') + C_INCLUDES
LIBRARY_DIRS = (GCC, SYSROOT + '/lib', SYSROOT + '/usr/lib')


def include_flags(cxx: bool) -> list[str]:
    return ['-nostdinc'] + ['-I' + path for path in (CXX_INCLUDES if cxx else C_INCLUDES)]


def link_flags() -> list[str]:
    return ['-L' + path for path in LIBRARY_DIRS]


def adapt_script(script: str) -> str:
    """Apply only the explicit search correction to a locked recipe script."""
    additions = {'CMAKE_C_FLAGS': include_flags(False), 'CMAKE_CXX_FLAGS': include_flags(True),
                 'CMAKE_EXE_LINKER_FLAGS': link_flags()}
    for key, flags in additions.items():
        pattern = r'(-D' + key + r'=")([^"\n]+)(")'
        matches = list(re.finditer(pattern, script))
        if len(matches) != 1:
            raise ValueError('Pinned compiler option changed or duplicated: ' + key)
        if any(flag in matches[0][2] for flag in flags):
            raise ValueError('SDK search correction is already present: ' + key)
        script = re.sub(pattern, lambda match: match[1] + match[2] + ' ' + ' '.join(flags) + match[3], script)
    return script


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True)


def preflight() -> dict:
    """Compile/link, inspect headers and ELF; never execute target code."""
    from abi_audit import audit
    version = run(['aarch64-linux-gnu-g++', '-dumpversion']).stdout.strip()
    if version != '9':
        raise ValueError('Strict SDK search is pinned to GCC 9; got ' + version)
    paths = CXX_INCLUDES + LIBRARY_DIRS
    if any(not Path(path).is_dir() for path in paths):
        raise ValueError('Pinned GCC 9/SDK search directory is missing')
    result = {'schema_version': 1, 'policy': 'explicit GCC9 C++/intrinsic includes and runtimes; SDK C headers/libraries',
              'target_executed': False, 'c_flags': include_flags(False), 'cxx_flags': include_flags(True),
              'link_flags': link_flags(), 'compiler_major': version, 'header_checks': {}}
    with tempfile.TemporaryDirectory(prefix='ppsspp-sdk-search-') as directory:
        work = Path(directory)
        for cxx in (False, True):
            compiler = 'aarch64-linux-gnu-g++' if cxx else 'aarch64-linux-gnu-gcc'
            flags = ['--sysroot=' + SYSROOT] + include_flags(cxx)
            source = work / ('headers.cpp' if cxx else 'headers.c')
            source.write_text('#include <features.h>\n#include <fcntl.h>\n')
            macros = run([compiler] + flags + ['-dM', '-E', str(source)]).stdout
            if not re.search(r'^#define __GLIBC__ 2$', macros, re.M) or not re.search(r'^#define __GLIBC_MINOR__ 25$', macros, re.M):
                raise ValueError('C headers are not the pinned glibc 2.25')
            trace = run([compiler] + flags + ['-H', '-E', str(source)])
            headers = sorted(set(re.findall(r'^\.+ (/[^\n]+)', trace.stderr, re.M)))
            outside = [path for path in headers if path.startswith('/usr/aarch64-linux-gnu/include/') and not path.startswith(CXX + '/')]
            if outside or not any(path.endswith('/features.h') and path.startswith(SYSROOT + '/') for path in headers):
                raise ValueError('Ubuntu C header leakage: ' + repr(outside))
            result['header_checks']['cxx' if cxx else 'c'] = {'glibc': '2.25', 'headers': headers, 'macros_sha256': hashlib.sha256(macros.encode()).hexdigest()}
        probe = work / 'probe.cpp'
        probe.write_text('#include <fcntl.h>\n#include <cmath>\n#include <filesystem>\n#include <future>\n#include <fstream>\n'
                         'int main(int argc, char **argv) { std::ifstream f(argv[0]); std::filesystem::path p(argv[0]); '
                         'auto pending = std::async(std::launch::deferred, [] { return 1; }); volatile double x = argc; '
                         'return fcntl(0, F_GETFL) + std::pow(x,x) + pending.get() + p.string().size() + f.good(); }\n')
        obj = work / 'probe.o'
        flags = ['--sysroot=' + SYSROOT] + include_flags(True) + ['-std=c++17', '-D_FILE_OFFSET_BITS=64', '-O2']
        run(['aarch64-linux-gnu-g++'] + flags + ['-c', str(probe), '-o', str(obj)])
        undefined = run(['aarch64-linux-gnu-nm', '-u', str(obj)]).stdout
        if re.search(r'\bfcntl64\b', undefined) or not re.search(r'\bfcntl\b', undefined):
            raise ValueError('Old C header fcntl declaration was not used')
        binary = work / 'probe'
        linked = run(['aarch64-linux-gnu-g++', '--sysroot=' + SYSROOT] + link_flags() +
                     ['-static-libstdc++', '-Wl,-t', str(obj), '-o', str(binary), '-pthread', '-lm'])
        stdlib = GCC + '/libstdc++.a'
        if stdlib not in linked.stdout.splitlines() or SYSROOT + '/lib/libstdc++.a' in linked.stdout.splitlines():
            raise ValueError('GCC 9 static C++ runtime selection was not proved')
        inspected = audit(binary, Path(SYSROOT))
        if not inspected['sdk_dependency_inventory_pass']:
            raise ValueError('Strict-search C++17 probe fails SDK ABI inventory: ' + json.dumps(inspected))
        result.update({'status': 'pass', 'probe_source_sha256': sha(probe), 'undefined_symbols': undefined.splitlines(),
                       'selected_static_stdlib': stdlib, 'static_stdlib_sha256': sha(Path(stdlib)),
                       'link_trace': linked.stdout.splitlines(), 'probe_abi_inventory': inspected})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(preflight(), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
