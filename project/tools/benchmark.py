#!/usr/bin/env python3
"""Read-only process sampler for repeatable, operator-run port scenes.

Attach to an already running emulator/port PID. This tool never launches,
signals, suspends or terminates a game and never changes clocks or settings.
RSS/CPU observations do not establish frame rate, audio quality or compatibility.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import time

PROFILES = Path(__file__).resolve().parents[1] / 'profiles/ports.json'


class BenchmarkError(RuntimeError):
    pass


def _read_process(proc_root, pid):
    directory = Path(proc_root) / str(pid)
    try:
        fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        pages = (directory / 'statm').read_text().split()
        children = []
        try:
            children = [int(p) for p in (directory / 'task' / str(pid) / 'children').read_text().split()]
        except (OSError, ValueError):
            pass
        return {
            'pid': pid, 'start_ticks': int(fields[19]),
            'cpu_ticks': int(fields[11]) + int(fields[12]),
            'rss_bytes': int(pages[1]) * os.sysconf('SC_PAGE_SIZE'),
            'children': children,
        }
    except (OSError, ValueError, IndexError):
        return None


def _process_tree(proc_root, first):
    pending, seen, records = [first], set(), []
    while pending and len(records) < 256:
        record = pending.pop()
        if record['pid'] in seen:
            continue
        seen.add(record['pid'])
        records.append(record)
        for child in record['children']:
            found = _read_process(proc_root, child)
            if found:
                pending.append(found)
    return records


def _write_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.benchmark-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def capture(pid, output, *, port_id, scene, seconds=30.0, interval=0.2,
            metadata=None, profiles_file=PROFILES, proc_root='/proc'):
    if type(pid) is not int or pid <= 0:
        raise BenchmarkError('Select a positive running PID')
    if not (math.isfinite(seconds) and math.isfinite(interval)
            and 0 < seconds <= 3600 and 0.02 <= interval <= 60):
        raise BenchmarkError('Use a duration of 0–3600 seconds and an interval of 0.02–60 seconds')
    profiles = json.loads(Path(profiles_file).read_text())
    profile = next((p for p in profiles['ports'] if p['id'] == port_id), None)
    if not profile or not profile.get('enabled') or scene not in profile.get('scenes', []):
        raise BenchmarkError('Select an enabled port and one of its declared repeatable scenes')
    metadata = dict(metadata or {})
    if len(json.dumps(metadata, allow_nan=False)) > 65536:
        raise BenchmarkError('Benchmark metadata is too large')
    first = _read_process(proc_root, pid)
    if not first:
        raise BenchmarkError('The selected process is absent or cannot be observed')
    identity = first['start_ticks']
    started = time.monotonic()
    samples = []
    stop_reason = 'duration-reached'
    while True:
        now = time.monotonic()
        current = _read_process(proc_root, pid)
        if current is None:
            stop_reason = 'process-exited-or-not-observable'
            break
        if current['start_ticks'] != identity:
            stop_reason = 'pid-reused'
            break
        tree = _process_tree(proc_root, current)
        samples.append({
            'elapsed_seconds': now - started,
            'rss_bytes': current['rss_bytes'],
            'tree_rss_bytes': sum(p['rss_bytes'] for p in tree),
            'process_count': len(tree),
            'root_cpu_seconds': current['cpu_ticks'] / os.sysconf('SC_CLK_TCK'),
        })
        remaining = seconds - (time.monotonic() - started)
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    elapsed = time.monotonic() - started
    current = _read_process(proc_root, pid)
    report = {
        'schema': 1,
        'collected_at_utc': datetime.now(timezone.utc).isoformat(),
        'evidence_class': 'operator-declared-physical-device' if metadata.get('physical_device') is True else 'host-or-unspecified',
        'profile_id': port_id, 'scene': scene,
        'spruce_commit': profiles['spruce_commit'],
        'profile_source': profile.get('source'),
        'metadata': metadata,
        'pid': pid, 'process_start_ticks': identity,
        'elapsed_seconds': elapsed, 'requested_seconds': seconds,
        'stop_reason': stop_reason,
        'process_still_running': bool(current and current['start_ticks'] == identity),
        'samples': samples,
        'summary': {
            'peak_sampled_rss_bytes': max((s['rss_bytes'] for s in samples), default=None),
            'peak_sampled_tree_rss_bytes': max((s['tree_rss_bytes'] for s in samples), default=None),
            'root_cpu_seconds_delta': samples[-1]['root_cpu_seconds'] - samples[0]['root_cpu_seconds'] if len(samples) > 1 else None,
            'fps': None, 'frame_time_p95_ms': None, 'audio_faults': None,
            'input_latency_ms': None, 'battery_energy_wh': None,
        },
        'limits': [
            'Fixed-scene execution and physical-device identity are supplied by the operator.',
            'No frame, audio, latency, temperature or energy measurement is inferred from process data.',
            'Sampled tree RSS may double-count shared pages and miss short-lived children.',
            'The sampler does not control or terminate the game; exit through its normal save-safe path.',
            'Compare identical firmware, owner data, settings, brightness and supported CPU profiles.',
        ],
    }
    _write_report(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list-scenes', action='store_true')
    parser.add_argument('--profile')
    parser.add_argument('--scene')
    parser.add_argument('--pid', type=int)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--interval', type=float, default=0.2)
    parser.add_argument('--metadata', type=Path, help='Local JSON with firmware, data/settings hashes and scene conditions')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.list_scenes:
        data = json.loads(PROFILES.read_text())
        print(json.dumps({p['id']: p['scenes'] for p in data['ports'] if p['enabled']}, indent=2))
        return
    if not all((args.profile, args.scene, args.pid, args.output)):
        parser.error('--profile, --scene, --pid and --output are required')
    try:
        metadata = json.loads(args.metadata.read_text()) if args.metadata else {}
        result = capture(args.pid, args.output, port_id=args.profile, scene=args.scene,
                         seconds=args.seconds, interval=args.interval, metadata=metadata)
    except (BenchmarkError, OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({'output': str(args.output), 'samples': len(result['samples']),
                      'elapsed_seconds': result['elapsed_seconds'], 'fps': None}))


if __name__ == '__main__':
    main()
