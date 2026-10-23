#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic large-library fixtures and repeatable host query measurements.

Writes only a new fixture directory. No game data, scans of owner cards, or
device performance claims. The live fixture injects existing-manager-shaped
objects; it does not instantiate or copy PyUI managers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import statistics
import tempfile
import time
from types import SimpleNamespace

from psp_shell.adapters.spruce import PyUIModelProvider, SpruceBackend


def create_library(root, count=10000):
    root = Path(root).absolute()
    if type(count) is not int or not 1 <= count <= 45000:
        raise ValueError("Use 1–45000 synthetic entries")
    if any(p.is_symlink() for p in (root, *root.parents)) or root.exists():
        raise ValueError("Use a new fixture directory without symlinks")
    root.mkdir(parents=True)
    (root / '.synthetic-library').write_text('Host fixture; no playable content\n')
    config = {'label': 'Synthetic library', 'devices': ['TRIMUI_A133P'],
              'extlist': 'gb', 'default_emulator': 'fixture',
              'launch': '../../spruce/scripts/emu/standard_launch.sh'}
    (root / 'Emu/GB').mkdir(parents=True)
    (root / 'Emu/GB/config.json').write_text(json.dumps(config))
    script = root / 'spruce/scripts/emu/standard_launch.sh'
    script.parent.mkdir(parents=True)
    script.write_text('#!/bin/sh\n# Synthetic fixture: never execute\nexit 99\n')
    system = SimpleNamespace(system_name='GB', display_name='Synthetic library')
    models = []
    for index in range(count):
        name = ['Café 雪の冒険', 'العربية', '한국어', 'Adventure'][index % 4]
        path = root / f'Roms/GB/group-{index // 100:04d}/{name}-{index:05d}.gb'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic non-game fixture\n')
        models.append(SimpleNamespace(game_system=system, rom_file_path=str(path),
            display_name=f'{name} {index:05d} ' + ('Long title ' * 20 if index % 100 == 0 else '')))
    return models


def live_backend(root, models):
    system = SimpleNamespace(system_name='GB', display_name='Synthetic library')
    provider = PyUIModelProvider(root,
        system_manager=SimpleNamespace(get_active_systems=lambda: [system]),
        game_list=lambda name: iter(models), device=SimpleNamespace(run_game=lambda model: None),
        favorites_manager=SimpleNamespace(get_favorites=lambda: []),
        recents_manager=SimpleNamespace(get_recents=lambda: []),
        release_resources=lambda: None, quiescent=lambda: True)
    return SpruceBackend(root, managers=provider)


def distribution(values):
    values = sorted(values)
    if not values:
        return {'count': 0, 'median_ms': None, 'p95_ms': None, 'worst_ms': None}
    import math
    return {'count': len(values), 'median_ms': statistics.median(values),
            'p95_ms': values[math.ceil(.95 * len(values)) - 1], 'worst_ms': max(values)}


def measure(backend, repeats=7):
    if type(repeats) is not int or not 2 <= repeats <= 100:
        raise ValueError('Use 2–100 measured query repetitions')
    start = time.perf_counter_ns()
    first = backend.games('GB', limit=50)
    startup = (time.perf_counter_ns() - start) / 1e6
    times = {'page': [], 'search': []}
    for iteration in range(repeats):
        for name, arguments in (('page', {'offset': (iteration * 50) % max(1, first['total'])}),
                                ('search', {'search': '雪の冒険'})):
            start = time.perf_counter_ns()
            backend.games('GB', limit=50, **arguments)
            times[name].append((time.perf_counter_ns() - start) / 1e6)
    return {'total': first['total'], 'startup_ms': startup,
            'page': distribution(times['page']), 'search': distribution(times['search'])}


def run(count=10000, repeats=7):
    with tempfile.TemporaryDirectory(prefix='smartpro-library-') as temporary:
        root = Path(temporary) / 'synthetic-card'
        models = create_library(root, count)
        return {'schema': 1, 'evidence_class': 'synthetic-host-library',
                'host': {'system': platform.system(), 'machine': platform.machine(),
                         'python': platform.python_version()},
                'fixture_count': count, 'repetitions': repeats,
                'snapshot': measure(SpruceBackend(root), repeats),
                'injected_live': measure(live_backend(root, models), repeats),
                'hardware_qualified': False,
                'limits': ['Fixtures contain no playable ROMs or owner data.',
                           'Injected-manager and snapshot timings are separate workloads.',
                           'Host timing is not a TG5040 startup or input-latency result.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=10000)
    parser.add_argument('--repeats', type=int, default=7)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.count, args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
