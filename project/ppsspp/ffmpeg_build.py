#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild the pinned FFmpeg fork out of source with its pinned codec selection."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from sdk_search import include_flags, link_flags

COMPONENTS = ('avcodec', 'avformat', 'avutil', 'swresample', 'swscale')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header_inventory(prefix: Path) -> list[dict]:
    include = prefix / 'include'
    if not include.is_dir() or include.is_symlink():
        raise ValueError('Rebuilt FFmpeg headers are missing')
    result = []
    for path in sorted(include.rglob('*')):
        if path.is_symlink():
            raise ValueError('Rebuilt FFmpeg headers cannot contain symlinks')
        if path.is_file():
            result.append({'path': str(path.relative_to(prefix)), 'size': path.stat().st_size, 'sha256': sha(path)})
    if not result:
        raise ValueError('Rebuilt FFmpeg headers are empty')
    return result


def configuration(script: Path, expected_sha256: str, prefix: Path) -> tuple[list[str], list[str]]:
    if sha(script) != expected_sha256:
        raise ValueError('Pinned FFmpeg build script changed')
    text = script.read_text()
    head = text[:text.index('function build_ARM64')]
    start = text.index('./configure --target-os=linux')
    command = text[start:text.index('\nmake clean', start)]
    if command.count('./configure') != 1:
        raise ValueError('Pinned FFmpeg configure boundary changed')
    # Expand the exact shell recipe as argv without invoking configure/make.
    payload = head + '\n' + command.replace('./configure', 'set --', 1) + '\nprintf "%s\\0" "$@"\n'
    result = subprocess.run(['bash', '--noprofile', '--norc', '-c', payload], check=True, capture_output=True)
    original = [item.decode() for item in result.stdout.split(b'\0') if item]
    changed = list(original)
    for option, value in (('--prefix=', str(prefix)), ('--extra-cflags=', None)):
        matches = [index for index, item in enumerate(changed) if item.startswith(option)]
        if len(matches) != 1:
            raise ValueError('Pinned FFmpeg option changed or duplicated: ' + option)
        index = matches[0]
        changed[index] = option + (value if value is not None else changed[index][len(option):].strip() + ' ' + ' '.join(include_flags(False)))
    if any(item.startswith(('--sysroot=', '--extra-ldflags=')) for item in original):
        raise ValueError('Pinned FFmpeg already specifies a sysroot/link search policy')
    changed += ['--sysroot=/opt/sysroot', '--extra-ldflags=' + ' '.join(link_flags())]
    return original, changed


def build(source: Path, build_dir: Path, prefix: Path, metadata: Path, inputs: dict, jobs: int) -> dict:
    pinned = inputs['ffmpeg']
    head = subprocess.run(['git', '-c', 'safe.directory=' + str(source), 'rev-parse', 'HEAD'],
                          cwd=source, check=True, capture_output=True, text=True).stdout.strip()
    if head != pinned['commit'] or sha(source / 'configure') != pinned['configure_sha256']:
        raise ValueError('FFmpeg source identity differs')
    original, changed = configuration(source / pinned['script_path'], pinned['script_sha256'], prefix)
    manifest = metadata / 'manifest.json'
    if manifest.exists():
        old = json.loads(manifest.read_text())
        if old.get('status') != 'complete' or old.get('configure_args') != changed or old.get('commit') != head:
            raise ValueError('FFmpeg rebuild metadata is failed or stale')
        if not old.get('header_inventory') or old['header_inventory'] != header_inventory(prefix):
            raise ValueError('Rebuilt FFmpeg headers changed or were not inventoried')
        expected_archives = {'lib/lib' + component + '.a' for component in COMPONENTS}
        if {item['path'] for item in old.get('archives', [])} != expected_archives:
            raise ValueError('Rebuilt FFmpeg archive inventory differs')
        if any((prefix / item['path']).is_symlink() for item in old['archives']):
            raise ValueError('Rebuilt FFmpeg archives cannot be symlinks')
        if any(sha(prefix / item['path']) != item['sha256'] for item in old['archives']):
            raise ValueError('Rebuilt FFmpeg archive changed')
        return old
    if any(build_dir.iterdir()) or any(prefix.iterdir()):
        raise ValueError('FFmpeg out-of-tree build/install directories must be empty')
    metadata.mkdir(exist_ok=True)
    report = {'schema_version': 1, 'status': 'building', 'commit': head,
              'script_path': pinned['script_path'], 'script_sha256': pinned['script_sha256'],
              'configure_sha256': pinned['configure_sha256'], 'original_configure_args': original,
              'configure_args': changed, 'jobs': jobs, 'target_executed': False,
              'source_and_prebuilt_files_modified': False,
              'raw_config_log': 'private build directory only; environment dump excluded from retained source metadata'}
    try:
        subprocess.run([str(source / 'configure')] + changed, cwd=build_dir, check=True)
        subprocess.run(['make', '-j' + str(jobs), 'install'], cwd=build_dir, check=True)
        archives = []
        for component in COMPONENTS:
            path = prefix / ('lib/lib' + component + '.a')
            archives.append({'path': str(path.relative_to(prefix)), 'size': path.stat().st_size, 'sha256': sha(path)})
        refs = subprocess.run(['aarch64-linux-gnu-nm', '-u', '-A', str(prefix / 'lib/libavutil.a')],
                              check=True, capture_output=True, text=True).stdout.splitlines()
        fcntl = [line for line in refs if 'fcntl' in line]
        if not fcntl or any('fcntl64' in line for line in fcntl):
            raise ValueError('Rebuilt FFmpeg still imports newer fcntl64')
        generated = metadata / 'generated-config'
        generated.mkdir()
        for directory, _, files in os.walk(build_dir, followlinks=False):
            for name in files:
                path = Path(directory) / name
                if not path.is_symlink() and (path.suffix in ('.h', '.mak') or name == 'Makefile'):
                    target = generated / path.relative_to(build_dir)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
        shutil.copytree(prefix / 'include', metadata / 'installed-headers')
        generated_version = (build_dir / 'libavutil/ffversion.h').read_text()
        git_description = subprocess.run(['git', '-c', 'safe.directory=' + str(source),
            'describe', '--tags', '--always'], cwd=source, check=True, capture_output=True, text=True).stdout.strip()
        report.update({'status': 'complete', 'archives': archives, 'header_inventory': header_inventory(prefix),
                       'libavutil_fcntl_refs': fcntl,
                       'generated_ffversion_header': generated_version, 'source_git_description': git_description,
                       'raw_config_log_sha256': sha(build_dir / 'config.log') if (build_dir / 'config.log').is_file() else None})
    except Exception as error:
        report.update({'status': 'failed', 'error': str(error)})
        raise
    finally:
        manifest.write_text(json.dumps(report, indent=2) + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'build_dir', 'prefix', 'metadata', 'input_lock'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--jobs', type=int, choices=range(1,33), default=4)
    args = parser.parse_args()
    result = build(args.source, args.build_dir, args.prefix, args.metadata,
                   json.loads(args.input_lock.read_text()), args.jobs)
    print(json.dumps(result, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
