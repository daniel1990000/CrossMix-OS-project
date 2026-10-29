#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Development-only, Linux/X11 PPSSPP observation collector.

No installed frontend imports this module. Private input bytes and raw logs belong
outside Git. A declaration binds inputs; it is not device qualification.
"""
from __future__ import annotations

import argparse
import asyncio
import configparser
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time

from tools.gameplay_benchmark import METRICS, compare, record, validate_identity, validate_run
from tools import host_audit_native as native_probe

PROJECT = Path(__file__).resolve().parents[1]
REVIEWED_EXECUTABLE = '6924b0392831517fb54108b98b9faa743492fe7d2709690098f91226fcdf56de'
CORRECTED_SOURCE = '96f6864fb6701313d2ca674f4aa1435c9475828487eb87b93505e43a69301674'
SOURCE_PIN = 'd357e6a32934800d3d80b49f910a603e1b069751'


class AuditError(ValueError):
    pass


def need(value, message):
    if not value:
        raise AuditError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    """Atomic report publication; raw journals are flushed independently."""
    path = Path(path)
    temporary = path.with_name(path.name + '.partial')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def inventory_names(root):
    return [str(p.relative_to(root)) for p in Path(root).rglob('*') if not p.is_dir()]


def inventory(root):
    root = Path(root)
    need(root.is_dir() and not root.is_symlink(), 'Frozen configuration needs a real directory')
    result = {}
    for path in sorted(root.rglob('*')):
        need(not path.is_symlink(), 'Configuration symlinks are unsupported')
        if path.is_file():
            result[str(path.relative_to(root))] = sha(path)
        else:
            need(path.is_dir(), 'Configuration contains a nonregular entry')
    need(result, 'Frozen configuration is empty')
    return result


def configuration_identity(root, game_id):
    """Read effective global/per-game settings, plus other config-file identities."""
    need(isinstance(game_id, str) and game_id.isascii() and game_id.isalnum() and 1 <= len(game_id) <= 32,
         'Native game ID must be bounded ASCII alphanumeric text')
    files = inventory(root)
    system = Path(root) / 'ppsspp/PSP/SYSTEM'
    values = {}
    names = ['ppsspp.ini', game_id + '_ppsspp.ini']
    for name in names:
        path = system / name
        need(path.is_file(), 'Frozen config needs global and game INIs in ppsspp/PSP/SYSTEM')
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(path, encoding='utf-8-sig')
        for section in parser.sections():
            for key, value in parser[section].items():
                values[section + '.' + key] = value
    for name, digest in files.items():
        if name not in ['ppsspp/PSP/SYSTEM/' + n for n in names]:
            values['FrozenFile.' + name.replace(' ', '_')] = digest
    resolution = values.get('Graphics.InternalResolution')
    need(resolution in ('1', '2'), 'Only 1x versus 2x resolution is supported')
    need(values.get('Graphics.FrameSkip') == '0' and
         values.get('Graphics.AutoFrameSkip', '').casefold() == 'false',
         'Comparisons require explicitly disabled manual and automatic frameskip')
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'sha256': digest, 'resolution': resolution + 'x',
            'frameskip': '0 (automatic disabled)', 'values': values}


IMPLEMENTATION_FILES = (
    'tools/host_gameplay_audit.py', 'tools/host_audit_native.py',
    'psp_shell/state_evidence.py', 'bridge/principal.py',
    'dev/host_virtual_controller.py', 'dev/host_virtual_controller.c',
)


def implementation_identity():
    return {name: sha(PROJECT / name) for name in IMPLEMENTATION_FILES}


def retain_implementation(output):
    identities = implementation_identity()
    for name in identities:
        destination = Path(output) / 'collector-source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT / name, destination)
        need(sha(destination) == identities[name], 'Host helper source changed during retention')
    return identities


def verify_statistics(emulator, source, build_receipt=None, receipt_sha256=None, review_evidence=None):
    return verify_statistics_binding(sha(emulator), source, build_receipt, receipt_sha256, review_evidence)


def verify_statistics_binding(executable_hash, source, build_receipt=None, receipt_sha256=None, review_evidence=None):
    """Only the independently reviewed retained build is supported.

    A matching corrected source file alone cannot prove arbitrary executable
    correspondence. The exact build's reviewed evidence is required as well.
    """
    if executable_hash != REVIEWED_EXECUTABLE:
        need(build_receipt is not None and receipt_sha256 is not None,
             'New executable needs an explicitly pinned, independently reviewed build receipt')
        need(sha(build_receipt) == receipt_sha256, 'Reviewed build receipt changed')
        receipt = json.loads(Path(build_receipt).read_text())
        need(receipt.get('kind') == 'reviewed-host-statistics-build' and
             receipt.get('executable_sha256') == executable_hash and
             receipt.get('statistics_source_sha256') == CORRECTED_SOURCE and
             receipt.get('upstream_commit') == SOURCE_PIN and
             receipt.get('statistics_patch_sha256') ==
                 '980d6ad8bdee549e09a42ef9041e12c17331f51e44b7b38bc939557dedd970ec' and
             isinstance(receipt.get('review_evidence_sha256'), str) and
             len(receipt['review_evidence_sha256']) == 64,
             'New build receipt does not bind executable, corrected source, pinned patch and review')
        need(review_evidence is not None and sha(review_evidence) == receipt['review_evidence_sha256'],
             'Retained build review evidence missing or changed')
        review = json.loads(Path(review_evidence).read_text())
        need(review.get('decision') == 'accepted_for_host_counter_collection' and
             review.get('executable_sha256') == executable_hash and
             review.get('statistics_source_sha256') == CORRECTED_SOURCE and
             isinstance(review.get('reviewer'), str) and review['reviewer'].strip(),
             'Retained review does not accept this exact host statistics build')
    need(sha(source) == CORRECTED_SOURCE, 'Statistics implementation is not the exact corrected source')
    native = PROJECT / 'evidence/iso-continuation-20261026/native'
    build = json.loads((native / 'build-report.json').read_text())
    assembly = json.loads((native / 'assembly.json').read_text())
    lock = json.loads((PROJECT / 'ppsspp/gpu-stats.lock.json').read_text())
    need(build['executable_sha256'] == REVIEWED_EXECUTABLE and build['upstream_commit'] == SOURCE_PIN,
         'Reviewed executable identity changed')
    need(build['assembly_sha256'] == sha(native / 'assembly.json'), 'Reviewed assembly evidence changed')
    need(CORRECTED_SOURCE in json.dumps(assembly) and lock['patched_files'][0]['sha256'] == CORRECTED_SOURCE,
         'Corrected implementation binding changed')
    patch = next(p for p in build['project_patches'] if p['path'].endswith('0005-gpu-stats-float-copy.patch'))
    need(patch['sha256'] == lock['patch']['sha256'] == sha(PROJECT / 'ppsspp' / patch['path']),
         'Corrected statistics patch changed')
    return {'executable_sha256': executable_hash, 'statistics_source_sha256': CORRECTED_SOURCE,
            'reviewed_build_receipt_sha256': receipt_sha256,
            'upstream_commit': SOURCE_PIN, 'build_report_sha256': sha(native / 'build-report.json'),
            'scope': 'Historical reviewed build or explicit operator-pinned reviewed build receipt. Receipt provenance requires independent review; not cryptographic source-to-binary proof or device qualification'}


def check_port(port):
    need(type(port) is int and 1024 <= port <= 65535, 'Select an unprivileged observer port')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as error:
            raise AuditError('Observer port occupied') from error


def process_start(pid, proc=Path('/proc')):
    # comm may contain spaces and closing parentheses.
    return (proc / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]


def competing(emulator, owned=None, proc=Path('/proc')):
    result = []
    expected = str(Path(emulator).resolve())
    for task in proc.glob('[0-9]*'):
        try:
            pid = int(task.name)
            exe = os.readlink(task / 'exe')
            comm = (task / 'comm').read_text().strip().casefold()
            if pid != owned and (exe == expected or 'ppsspp' in comm or 'ppsspp' in Path(exe).name.casefold()):
                result.append(pid)
        except (OSError, ValueError):
            continue
    need(not result, 'Competing emulator processes: ' + str(result))


def bind_listener(pid, start, executable_hash, port, proc=Path('/proc')):
    need(process_start(pid, proc) == start, 'Launched process identity changed')
    need(sha(proc / str(pid) / 'exe') == executable_hash, 'Running executable differs from launched identity')
    sockets = set()
    for fd in (proc / str(pid) / 'fd').iterdir():
        try:
            sockets.add(os.readlink(fd))
        except OSError:
            continue
    listeners = []
    for table in ('tcp', 'tcp6'):
        for line in (proc / 'net' / table).read_text().splitlines()[1:]:
            fields = line.split()
            if int(fields[1].split(':')[-1], 16) == port and fields[3] == '0A':
                listeners.append(fields[9])
    need(listeners and all('socket:[' + inode + ']' in sockets for inode in listeners),
         'Observer listener does not belong exclusively to launched PID')
    return {'pid': pid, 'start_ticks': start, 'port': port, 'socket_inodes': listeners,
            'executable_sha256': executable_hash, 'checked_utc': utc()}


def select_samples(rows, seconds, game_id=None):
    previous = -1
    statuses = {}
    for row in rows:
        elapsed = row.get('elapsed_seconds')
        need(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= previous,
             'Raw timestamps must be finite and monotonic')
        previous = elapsed
        need(isinstance(row.get('message'), dict), 'Invalid raw message')
        ticket = row['message'].get('ticket')
        if ticket in ('status-start', 'status-end'):
            need(ticket not in statuses, 'Duplicate status acknowledgement')
            need(row['message'].get('event') == 'game.status', 'Wrong status event')
            if game_id is not None:
                need(row['message'].get('game', {}).get('id') == game_id and
                     row['message'].get('paused') is False, 'Wrong game or paused in retained raw status')
            statuses[ticket] = row
    need('status-start' in statuses and 'status-end' in statuses, 'Interrupted output has no complete status window')
    start = statuses['status-start']['elapsed_seconds']
    need(statuses['status-end']['elapsed_seconds'] - start >= seconds, 'Incomplete observation window')
    included, excluded = [], []
    for row in rows:
        if row.get('message', {}).get('event') != 'gpu.stats.get':
            continue
        elapsed = row['elapsed_seconds'] - start
        (included if 0 <= elapsed < seconds else excluded).append(row)
    need(included, 'No counter responses in nominal window')
    for row in included:
        message = row['message']
        for key in ('fps', 'vblanksPerSecond'):
            for field in ('actual', 'target'):
                value = message[key][field]
                need(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                     'Invalid native counter')
        need(message['vblanksPerSecond']['target'] > 0, 'Invalid native speed denominator')
    return included, excluded


async def observe(raw, *, port, seconds, interval, game_id, check, replay=None):
    # Development dependency only; no runtime/shipped dependency is added.
    import websockets
    started = time.monotonic()
    rows = []
    with Path(raw).open('x') as stream:
        async with websockets.connect(f'ws://127.0.0.1:{port}/debugger',
                subprotocols=['debugger.ppsspp.org'], compression=None, max_size=1048576,
                open_timeout=10, close_timeout=5, proxy=None) as ws:
            async def request(event, ticket, **fields):
                check()
                sent = time.monotonic()
                await ws.send(json.dumps(dict(event=event, ticket=ticket, **fields)))
                while True:
                    remaining = 10 - (time.monotonic() - sent)
                    need(remaining > 0, 'Native request timed out')
                    message = json.loads(await asyncio.wait_for(ws.recv(), remaining))
                    received_ns = time.monotonic_ns()
                    row = {'elapsed_seconds': received_ns / 1e9 - started, 'monotonic_ns': received_ns, 'utc': utc(),
                           'request_sent_elapsed_seconds': sent - started, 'message': message}
                    stream.write(json.dumps(row, allow_nan=False) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                    rows.append(row)
                    if message.get('ticket') == ticket:
                        need(message.get('event') != 'error', 'Native rejected observation request')
                        check()
                        return row
            await request('version', 'version', name='trimui-development-host-audit', version='1')
            ready_deadline = time.monotonic() + 30
            ready_index = 0
            while True:
                ready = await request('game.status', 'status-ready-' + str(ready_index))
                if (ready['message'].get('game', {}).get('id') == game_id and
                        ready['message'].get('paused') is False):
                    break
                need(time.monotonic() < ready_deadline, 'Native game did not become ready before phase startup')
                ready_index += 1
                await asyncio.sleep(.1)
            initial = await request('game.status', 'status-start')
            need(initial['message'].get('game', {}).get('id') == game_id and
                 initial['message'].get('paused') is False, 'Wrong game or paused before observation')
            window_start = initial['monotonic_ns'] / 1e9
            deadline = window_start + seconds
            replay_task = asyncio.create_task(replay(window_start)) if replay else None
            index = 0
            try:
                while time.monotonic() < deadline:
                    if replay_task and replay_task.done():
                        replay_task.result()
                    await request('gpu.stats.get', 'sample-' + str(index))
                    index += 1
                    await asyncio.sleep(max(0, min(interval, deadline - time.monotonic())))
                if replay_task:
                    await replay_task
            finally:
                if replay_task and not replay_task.done():
                    replay_task.cancel()
                    try:
                        await replay_task
                    except asyncio.CancelledError:
                        pass
            final = await request('game.status', 'status-end')
            need(final['message'].get('game', {}).get('id') == game_id and
                 final['message'].get('paused') is False, 'Wrong game or paused after observation')
    return rows


def validate_sequence(sequence, seconds):
    need(isinstance(sequence, list), 'Input sequence needs a list')
    previous_end = 0
    for event in sequence:
        need(isinstance(event, dict) and set(event) == {'at_seconds', 'seconds', 'axes', 'buttons'},
             'Input event needs exact timing, axes and buttons')
        at, duration = event['at_seconds'], event['seconds']
        need(type(at) in (int, float) and math.isfinite(at) and at >= previous_end and
             type(duration) in (int, float) and math.isfinite(duration) and .01 <= duration <= 60 and
             at + duration <= seconds, 'Input timings must be finite, nonoverlapping and within observation')
        need(isinstance(event['axes'], list) and len(event['axes']) == 4 and
             all(type(v) in (int, float) and math.isfinite(v) and -1 <= v <= 1 for v in event['axes']),
             'Input requires four finite analogue axes in [-1,1]')
        need(type(event['buttons']) is int and 0 <= event['buttons'] < 32768, 'Invalid input buttons')
        previous_end = at + duration


async def replay_inputs(sequence, *, window_start, pid, start_ticks, args, output, tolerance, request_name='requests.jsonl'):
    spec = importlib.util.spec_from_file_location('audit_controller', PROJECT / 'dev/host_virtual_controller.py')
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    for event in sequence:
        await asyncio.sleep(max(0, window_start + event['at_seconds'] - time.monotonic()))
        receipt = controller.send(pid=pid, executable=args.emulator.resolve(), sha256=sha(args.emulator),
            expected_start_ticks=int(start_ticks),
            command=output / 'controller/command', record=output / 'controller' / request_name,
            axes=event['axes'], buttons=event['buttons'], seconds=event['seconds'])
        need(0 <= receipt['published_monotonic_ns'] / 1e9 - window_start - event['at_seconds'] <= tolerance,
             'Input publication missed frozen timing tolerance')


def validate_input_receipts(output, sequence, window_start, tolerance, request_name='requests.jsonl'):
    if not sequence:
        return
    requests = [json.loads(line) for line in (output / 'controller' / request_name).read_text().splitlines()]
    observed = [json.loads(line) for line in (output / 'controller/observed.jsonl').read_text().splitlines()]
    need(len(requests) == len(sequence), 'Input replay was interrupted')
    for event, request in zip(sequence, requests):
        expected_axes = [round(value * 32767) for value in event['axes']]
        need(request['axes'] == expected_axes and request['buttons'] == event['buttons'] and
             0 <= request['requested_monotonic_ns'] / 1e9 - window_start - event['at_seconds'] <= tolerance and
             request['requested_monotonic_ns'] <= request['published_monotonic_ns'] <= request['expires_monotonic_ns'] and
             abs((request['expires_monotonic_ns'] - request['requested_monotonic_ns']) / 1e9 - event['seconds']) < .000001,
             'Input request differs from frozen sequence or timing')
        matches = [row for row in observed if row.get('event') == 'applied' and
                   row.get('sequence') == request['sequence'] and row.get('pid') == request['pid']]
        need(len(matches) == 1 and matches[0]['result'] == 0 and
             matches[0]['axes'] == request['axes'] and matches[0]['buttons'] == event['buttons'] and
             request['requested_monotonic_ns'] <= matches[0]['observed_monotonic_ns'] <= request['expires_monotonic_ns'] and
             0 <= matches[0]['observed_monotonic_ns'] / 1e9 - window_start - event['at_seconds'] <= tolerance,
             'Native input application missing, failed or outside frozen timing tolerance')
        applied = matches[0]['observed_monotonic_ns']
        endings = [row for row in observed if row.get('result') == 0 and
            row.get('observed_monotonic_ns', 0) >= applied and row.get('pid') == request['pid'] and
            ((row.get('event') in ('deadline_neutral', 'quit_neutral') and row.get('sequence') == request['sequence']) or
             (row.get('event') == 'applied' and row.get('sequence', -1) > request['sequence']))]
        need(endings, 'Native input hold completion was not observed')
        ended = min(row['observed_monotonic_ns'] for row in endings)
        need(abs((ended - request['expires_monotonic_ns']) / 1e9) <= tolerance,
             'Native input hold duration missed frozen timing tolerance')


def final_input_evidence(output):
    paths = [output / name for name in ('input-sequence.json', 'warmup-input-sequence.json') if (output / name).exists()]
    paths += sorted((output / 'controller').glob('*.jsonl'))
    if (output / 'warmup-observations.jsonl').exists():
        paths.append(output / 'warmup-observations.jsonl')
    return {str(path.relative_to(output)): sha(path) for path in paths}


def import_raw(manifest, raw, output):
    rows = [json.loads(line) for line in Path(raw).read_text().splitlines()]
    seconds = manifest['duration_seconds']
    included, excluded = select_samples(rows, seconds, manifest['identity']['game_id'])
    observations = {metric: None for metric in METRICS}
    values = {'native_fps': statistics.mean(r['message']['fps']['actual'] for r in included),
              'native_speed_percent': statistics.mean(100 * r['message']['vblanksPerSecond']['actual'] /
                  r['message']['vblanksPerSecond']['target'] for r in included)}
    for metric, value in values.items():
        observations[metric] = {'value': value, 'unit': METRICS[metric][0], 'method': 'native-counter',
            'evidence_file': str(Path(raw).resolve()), 'evidence_sha256': sha(raw),
            'start_seconds': 0, 'end_seconds': seconds}
    run = record({k: manifest[k] for k in ('identity', 'run_id', 'pair_id', 'duration_seconds',
                 'sustained', 'demanding_profile')}, observations, output)
    run['analysis'] = {'included_samples': len(included), 'excluded_samples': excluded,
        'window': '[0,duration) from retained status-start; late responses retained and excluded',
        'acquisition_seconds': rows[-1]['elapsed_seconds'], 'raw_sha256': sha(raw),
        'limits': 'Approximate native counters only; audio, pacing, latency and energy unavailable'}
    write(output, run)
    return run


def frozen_check(args, manifest):
    need(sha(args.emulator) == manifest['emulator_sha256'], 'Emulator changed')
    need(sha(args.iso) == manifest['iso_sha256'], 'ISO changed')
    need(sha(args.starting_state) == manifest['starting_state_sha256'], 'Starting state changed')
    if getattr(args, 'scene_definition', None) is not None:
        need(sha(args.scene_definition) == manifest['identity']['scene_definition_sha256'], 'Frozen scene definition changed')
    if getattr(args, 'input_sequence', None) is not None:
        need(sha(args.input_sequence) == manifest.get('input_sequence_sha256'), 'Frozen input sequence changed')
        need(sha(args.controller_shim) == manifest.get('controller_shim_sha256'), 'Frozen controller shim changed')
    if getattr(args, 'warmup_input_sequence', None) is not None:
        need(sha(args.warmup_input_sequence) == manifest.get('warmup_input_sequence_sha256'), 'Frozen warmup input sequence changed')
        need(sha(args.controller_shim) == manifest.get('controller_shim_sha256'), 'Frozen controller shim changed')
    need(inventory(args.frozen_config) == manifest['configuration'], 'Frozen configuration changed')


def validate_scene(manifest, scene):
    sustained = manifest.get('sustained')
    need(type(sustained) is bool, 'Declare sustained scene scope')
    duration_key = 'sustained_duration_seconds' if sustained else 'duration_seconds'
    sequence_key = 'sustained_input_sequence_sha256' if sustained else 'input_sequence_sha256'
    need(scene.get('id') == manifest['identity']['scene_id'] and
         scene.get('starting_state_sha256') == manifest['starting_state_sha256'] and
         scene.get('native_slot') == manifest.get('native_slot') and
         scene.get('native_disc_version') == manifest.get('native_disc_version') and
         scene.get('warmup_seconds') == manifest['warmup_seconds'] and
         scene.get('warmup_input_sequence_sha256') == manifest.get('warmup_input_sequence_sha256') and
         scene.get(duration_key) == manifest['duration_seconds'] and
         sequence_key in scene and scene[sequence_key] == manifest.get('input_sequence_sha256') and
         isinstance(scene.get('camera'), str) and scene['camera'].strip(),
         'Scene must freeze state, selected input sequence, camera, warmup and selected duration')


def validate_manifest(args, manifest):
    validate_identity(manifest['identity'])
    native_probe.validate_declaration(manifest)
    validate_scene(manifest, json.loads(args.scene_definition.read_text()))
    need(manifest['identity']['evidence_class'] == 'host', 'This collector only records host evidence')
    need(manifest['identity']['system_id'] == 'PSP', 'This collector only launches the admitted PSP engine')
    need(manifest['identity']['emulator']['binary_sha256'] == manifest['emulator_sha256'] and
         manifest['identity']['content_sha256'] == manifest['iso_sha256'], 'Manifest identities disagree')
    for key, low, high in [('duration_seconds', 1, 3600), ('warmup_seconds', 0, 300), ('interval_seconds', .25, 10)]:
        value = manifest[key]
        need(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
             'Invalid ' + key)
    need(type(manifest['sustained']) is bool and type(manifest['demanding_profile']) is bool,
         'Declare sustained and demanding-profile scope')
    need(not manifest['sustained'] or manifest['duration_seconds'] >= 1800, 'Sustained run needs 1800 seconds')
    frozen_check(args, manifest)
    need(manifest['identity']['settings'] == configuration_identity(args.frozen_config, manifest['identity']['game_id']),
         'Declared settings do not match actual frozen native configuration')


def normal_exit(pid, start, emulator_hash, xdotool):
    need(process_start(pid) == start and sha(Path('/proc') / str(pid) / 'exe') == emulator_hash,
         'Refusing exit input to changed process')
    result = subprocess.run([str(xdotool), 'search', '--onlyvisible', '--pid', str(pid)],
                            text=True, capture_output=True, check=True, timeout=10)
    windows = result.stdout.split()
    need(len(windows) == 1 and windows[0].isdigit(), 'Need exactly one visible window owned by launched PID')
    subprocess.run([str(xdotool), 'windowfocus', '--sync', windows[0], 'key', '--window', windows[0], 'Escape'],
                   check=True, timeout=10)


def collect(args):
    output = args.output.resolve()
    protected = [args.emulator, args.iso, args.starting_state, args.statistics_source, args.manifest, args.frozen_config] + [p for p in (getattr(args, 'scene_definition', None), getattr(args, 'input_sequence', None), getattr(args, 'controller_shim', None), getattr(args, 'warmup_input_sequence', None)) if p is not None]
    need(all(output != p.resolve() and p.resolve() not in output.parents and
             output not in p.resolve().parents for p in protected), 'Output overlaps retained inputs')
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    receipt = {'schema': 1, 'kind': 'development-host-audit', 'started_utc': utc(), 'status': 'incomplete',
               'hardware_qualified': False, 'private_paths': True}
    began = time.monotonic()
    helper = None
    pid = start = None
    try:
        receipt['implementation_sha256'] = retain_implementation(output)
        manifest = json.loads(args.manifest.read_text())
        validate_manifest(args, manifest)
        sequence, warmup_sequence = [], []
        warmup_path = getattr(args, 'warmup_input_sequence', None)
        if warmup_path is not None:
            need(sha(warmup_path) == manifest.get('warmup_input_sequence_sha256'), 'Frozen warmup input sequence changed')
            warmup_sequence = json.loads(warmup_path.read_text())
            validate_sequence(warmup_sequence, manifest['warmup_seconds'])
            need(args.controller_shim is not None and sha(args.controller_shim) == manifest.get('controller_shim_sha256'),
                 'Warmup input replay requires exact frozen controller shim')
        else:
            need(manifest.get('warmup_input_sequence_sha256') is None, 'Frozen warmup input sequence path missing')
        if args.input_sequence is not None:
            need(sha(args.input_sequence) == manifest.get('input_sequence_sha256'), 'Frozen input sequence changed')
            sequence = json.loads(args.input_sequence.read_text())
            validate_sequence(sequence, manifest['duration_seconds'])
            need(args.controller_shim is not None and sha(args.controller_shim) == manifest.get('controller_shim_sha256'),
                 'Input replay requires exact frozen controller shim')
            need(type(manifest.get('input_tolerance_seconds')) in (int, float) and
                 math.isfinite(manifest['input_tolerance_seconds']) and 0 < manifest['input_tolerance_seconds'] <= 1,
                 'Freeze input timing tolerance before collection')
        else:
            need(manifest.get('input_sequence_sha256') is None, 'Frozen input sequence path missing')
        if warmup_path is not None:
            need(type(manifest.get('input_tolerance_seconds')) in (int, float) and
                 math.isfinite(manifest['input_tolerance_seconds']) and 0 < manifest['input_tolerance_seconds'] <= 1,
                 'Freeze warmup input timing tolerance before collection')
        receipt['statistics_binding'] = verify_statistics(args.emulator, args.statistics_source,
            args.build_receipt, args.build_receipt_sha256, args.review_evidence)
        need(not os.environ.get('LD_PRELOAD'), 'Collector refuses inherited LD_PRELOAD')
        competing(args.emulator)
        check_port(args.port)
        shutil.copytree(args.frozen_config, output / 'frozen-config')
        shutil.copytree(output / 'frozen-config', output / 'config')
        shutil.copyfile(args.starting_state, output / 'starting.ppst')
        shutil.copyfile(args.manifest, output / 'manifest.json')
        shutil.copyfile(args.scene_definition, output / 'scene.json')
        shutil.copyfile(args.statistics_source, output / 'statistics-source.cpp')
        if args.build_receipt is not None:
            shutil.copyfile(args.build_receipt, output / 'build-receipt.json')
        if args.review_evidence is not None:
            shutil.copyfile(args.review_evidence, output / 'build-review.json')
        if args.input_sequence is not None:
            shutil.copyfile(args.input_sequence, output / 'input-sequence.json')
        if warmup_path is not None:
            shutil.copyfile(warmup_path, output / 'warmup-input-sequence.json')
        if args.input_sequence is not None or warmup_path is not None:
            (output / 'controller').mkdir(mode=0o700)
        need(inventory(output / 'config') == manifest['configuration'] and
             sha(output / 'starting.ppst') == manifest['starting_state_sha256'], 'Copied frozen inputs changed')
        load_context = native_probe.prepare_load_session(output, emulator=args.emulator, iso=args.iso, manifest=manifest)
        receipt['native_load_context_sha256'] = sha(output / 'native-load-session/context.json')
        receipt['frozen_inputs'] = manifest
        receipt['manifest_sha256'] = sha(output / 'manifest.json')
        write(output / 'receipt.json', receipt)
        plan = {'emulator': str(args.emulator.resolve()), 'iso': str(args.iso.resolve()),
                'output': str(output), 'emulator_sha256': manifest['emulator_sha256'],
                'native_request': str(output / 'native-load-session/request')}
        write(output / 'launch.json', plan)
        helper_env = dict(os.environ, PYTHONPATH=str(PROJECT), XDG_CONFIG_HOME=str(output / 'config'),
                          DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent')
        if args.input_sequence is not None or warmup_path is not None:
            need(not helper_env.get('LD_PRELOAD'), 'Replay refuses competing inherited LD_PRELOAD')
            helper_env.update(LD_PRELOAD=str(args.controller_shim.resolve()),
                TRIMUI_CONTROLLER_EXECUTABLE=str(args.emulator.resolve()),
                TRIMUI_CONTROLLER_COMMAND=str(output / 'controller/command'),
                TRIMUI_CONTROLLER_LOG=str(output / 'controller/observed.jsonl'))
        with (output / 'native-stdout.log').open('x') as log:
            helper = subprocess.Popen([sys.executable, '-m', 'tools.host_gameplay_audit', '_supervise',
                                       str(output / 'launch.json')], env=helper_env, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 30
            while not (output / 'root.json').exists():
                need(helper.poll() is None and time.monotonic() < deadline, 'Launch failed or timed out')
                time.sleep(.05)
            root = json.loads((output / 'root.json').read_text())
            pid, start = root['pid'], root['start_ticks']
            retained_paths = [args.emulator, args.iso, args.starting_state, args.statistics_source, args.manifest, args.scene_definition] + [PROJECT / name for name in IMPLEMENTATION_FILES] + [p for p in (args.input_sequence, args.controller_shim, warmup_path) if p is not None] + [
                args.frozen_config / name for name in manifest['configuration']]
            def snapshots():
                return {str(p): (p.stat().st_dev, p.stat().st_ino, p.stat().st_size,
                    p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in retained_paths}
            frozen_metadata = snapshots()
            def check():
                need(snapshots() == frozen_metadata, 'Retained inputs changed during acquisition')
                need(set(inventory_names(args.frozen_config)) == set(manifest['configuration']),
                     'Frozen configuration membership changed')
                competing(args.emulator, pid)
                receipt['last_listener_binding'] = bind_listener(pid, start, manifest['emulator_sha256'], args.port)
            # Native startup can create the listener after its initial window.
            while True:
                try:
                    check()
                    break
                except (AuditError, FileNotFoundError):
                    need(helper.poll() is None and time.monotonic() < deadline, 'Listener startup failed')
                    time.sleep(.1)
            load_deadline = time.monotonic() + 90
            while True:
                check()
                try:
                    receipt['native_load_before_warmup'] = native_probe.verify_load_session(output, load_context, manifest)
                    receipt['native_load_before_warmup_utc'] = utc()
                    break
                except FileNotFoundError:
                    need(helper.poll() is None and time.monotonic() < load_deadline,
                         'Native starting-state load acknowledgement missing or timed out')
                    time.sleep(.1)
            warmup_start = None
            if warmup_sequence:
                async def warmup_replay(origin):
                    nonlocal warmup_start
                    warmup_start = origin
                    await replay_inputs(warmup_sequence, window_start=origin, pid=pid, start_ticks=start,
                        args=args, output=output, tolerance=manifest['input_tolerance_seconds'],
                        request_name='warmup-requests.jsonl')
                asyncio.run(observe(output / 'warmup-observations.jsonl', port=args.port,
                    seconds=manifest['warmup_seconds'], interval=manifest['interval_seconds'],
                    game_id=manifest['identity']['game_id'], check=check, replay=warmup_replay))
            else:
                warmup_deadline = time.monotonic() + manifest['warmup_seconds']
                while time.monotonic() < warmup_deadline:
                    check()
                    time.sleep(min(.25, max(0, warmup_deadline - time.monotonic())))
            window_start = []
            async def replay(origin):
                window_start.append(origin)
                await replay_inputs(sequence, window_start=origin, pid=pid, start_ticks=start, args=args, output=output,
                    tolerance=manifest['input_tolerance_seconds'])
            rows = asyncio.run(observe(output / 'observations.jsonl', port=args.port,
                seconds=manifest['duration_seconds'], interval=manifest['interval_seconds'],
                game_id=manifest['identity']['game_id'], check=check, replay=replay if sequence else None))
            select_samples(rows, manifest['duration_seconds'], manifest['identity']['game_id'])
            normal_exit(pid, start, manifest['emulator_sha256'], args.xdotool)
            need(helper.wait(timeout=30) == 0, 'Owned tree did not exit normally')
        completion = json.loads((output / 'completion.json').read_text())
        need(completion['exit_status'] == 0 and completion['root_pid'] == pid, 'Native exit failed')
        receipt['native_load_after_exit'] = native_probe.verify_load_session(output, load_context, manifest)
        receipt['native_load_after_exit_utc'] = utc()
        need(receipt['native_load_after_exit'] == receipt['native_load_before_warmup'],
             'Native load evidence changed between warmup and owned exit')
        if warmup_sequence:
            validate_input_receipts(output, warmup_sequence, warmup_start, manifest['input_tolerance_seconds'],
                request_name='warmup-requests.jsonl')
            receipt['warmup_window_start_monotonic'] = warmup_start
        if sequence:
            # SDL_Quit appends neutralization timing: bind final bytes only
            # after the existing owner observes all descendants closed.
            validate_input_receipts(output, sequence, window_start[0], manifest['input_tolerance_seconds'])
            receipt['input_window_start_monotonic'] = window_start[0]
        if sequence or warmup_sequence:
            receipt['input_evidence'] = final_input_evidence(output)
        frozen_check(args, manifest)
        need(inventory(output / 'frozen-config') == manifest['configuration'] and
             sha(output / 'starting.ppst') == manifest['starting_state_sha256'], 'Retained frozen copy changed')
        need(implementation_identity() == receipt['implementation_sha256'], 'Host observer/helper implementation changed')
        import_raw(manifest, output / 'observations.jsonl', output / 'run.json')
        receipt.update(status='complete', completion=completion)
    except BaseException as error:
        receipt.update(status='failed', failure_type=type(error).__name__, failure=str(error))
        if pid is not None and helper is not None and helper.poll() is None:
            try:
                normal_exit(pid, start, manifest['emulator_sha256'], args.xdotool)
                helper.wait(timeout=30)
            except BaseException as cleanup:
                receipt['normal_exit_failure'] = type(cleanup).__name__
                receipt['operator_action_required'] = 'Owned helper remains supervising; close only its native window normally'
        raise
    finally:
        receipt.update(ended_utc=utc(), acquisition_seconds=time.monotonic() - began)
        if (output / 'observations.jsonl').exists():
            receipt['raw_sha256'] = sha(output / 'observations.jsonl')
        write(output / 'receipt.json', receipt)


def internal(mode, plan_path):
    plan = json.loads(Path(plan_path).read_text())
    output = Path(plan['output'])
    if mode == '_exec':
        need(sha(plan['emulator']) == plan['emulator_sha256'], 'Executable changed before exec')
        write(output / 'root.json', {'pid': os.getpid(), 'start_ticks': process_start(os.getpid())})
        argv = [plan['emulator'], '--windowed', '--graphics=opengl', '--escape-exit',
                '--state=' + str(output / 'starting.ppst'), '--project-state-session=' + plan['native_request'], '--log=' + str(output / 'native.log'), plan['iso']]
        os.execv(plan['emulator'], argv)
    from bridge.principal import run_owned_tree
    result = run_owned_tree([sys.executable, '-m', 'tools.host_gameplay_audit', '_exec', str(plan_path)])
    write(output / 'completion.json', {'root_pid': result.root_pid, 'exit_status': result.exit_status,
                                     'children_reaped': result.children_reaped, 'completed_utc': utc()})
    return 0 if result.exit_status == 0 else 1


def validate_collected_run(path):
    path = Path(path)
    run = json.loads(path.read_text())
    validate_run(run, verify_files=True)
    folder = path.parent
    receipt = json.loads((folder / 'receipt.json').read_text())
    manifest = json.loads((folder / 'manifest.json').read_text())
    need(set(receipt.get('implementation_sha256', {})) == set(IMPLEMENTATION_FILES) and
         all(sha(folder / 'collector-source' / name) == digest
             for name, digest in receipt['implementation_sha256'].items()), 'Retained host helper implementation changed')
    completion = json.loads((folder / 'completion.json').read_text())
    need(receipt.get('status') == 'complete' and completion.get('exit_status') == 0 and
         receipt.get('completion') == completion, 'Run lacks complete normal owned-tree exit')
    need(receipt.get('manifest_sha256') == sha(folder / 'manifest.json') and
         receipt.get('frozen_inputs') == manifest, 'Retained manifest changed')
    need(sha(folder / 'starting.ppst') == manifest['starting_state_sha256'], 'Retained starting state changed')
    load_context = native_probe.read_context(folder)
    need(receipt.get('native_load_context_sha256') == sha(folder / 'native-load-session/context.json'),
         'Retained native load context changed')
    native_load = native_probe.verify_load_session(folder, load_context, manifest)
    need(receipt.get('native_load_before_warmup') == native_load == receipt.get('native_load_after_exit'),
         'Run lacks unchanged actual native starting-state load acknowledgement')
    binding = receipt['statistics_binding']
    need(binding['executable_sha256'] == manifest['emulator_sha256'], 'Executable binding differs from manifest')
    rechecked_binding = verify_statistics_binding(manifest['emulator_sha256'], folder / 'statistics-source.cpp',
        folder / 'build-receipt.json' if (folder / 'build-receipt.json').exists() else None,
        binding.get('reviewed_build_receipt_sha256'),
        folder / 'build-review.json' if (folder / 'build-review.json').exists() else None)
    need(binding == rechecked_binding, 'Statistics provenance binding changed')
    need(sha(folder / 'scene.json') == run['identity']['scene_definition_sha256'], 'Retained scene definition changed')
    validate_scene(manifest, json.loads((folder / 'scene.json').read_text()))
    need(run['identity'] == manifest['identity'] and
         all(run[k] == manifest[k] for k in ('run_id', 'pair_id', 'duration_seconds', 'sustained', 'demanding_profile')),
         'Run identity differs from frozen manifest')
    need(inventory(folder / 'frozen-config') == manifest['configuration'] and
         configuration_identity(folder / 'frozen-config', run['identity']['game_id']) == run['identity']['settings'],
         'Run settings differ from actual frozen native configuration')
    if manifest.get('warmup_input_sequence_sha256') is not None:
        warmup_path = folder / 'warmup-input-sequence.json'
        need(sha(warmup_path) == manifest['warmup_input_sequence_sha256'], 'Retained warmup input sequence changed')
        warmup_sequence = json.loads(warmup_path.read_text())
        validate_sequence(warmup_sequence, manifest['warmup_seconds'])
        if warmup_sequence:
            need(receipt.get('input_evidence'), 'Warmup acquisition evidence missing')
            validate_input_receipts(folder, warmup_sequence, receipt['warmup_window_start_monotonic'],
                manifest['input_tolerance_seconds'], request_name='warmup-requests.jsonl')
            warmup_rows = [json.loads(line) for line in (folder / 'warmup-observations.jsonl').read_text().splitlines()]
            select_samples(warmup_rows, manifest['warmup_seconds'], run['identity']['game_id'])
            warmup_ack = next(row for row in warmup_rows if row['message'].get('ticket') == 'status-start')
            need(type(warmup_ack.get('monotonic_ns')) is int and
                 warmup_ack['monotonic_ns'] / 1e9 == receipt['warmup_window_start_monotonic'],
                 'Warmup input clock is not bound to raw game-ready acknowledgement')
    if manifest.get('input_sequence_sha256') is not None:
        sequence_path = folder / 'input-sequence.json'
        need(sha(sequence_path) == manifest['input_sequence_sha256'], 'Retained input sequence changed')
        sequence = json.loads(sequence_path.read_text())
        validate_sequence(sequence, manifest['duration_seconds'])
        need(all(sha(folder / name) == digest for name, digest in receipt.get('input_evidence', {}).items()),
             'Retained input timing evidence changed')
        if sequence:
            need(receipt.get('input_evidence'), 'Input acquisition evidence missing')
            validate_input_receipts(folder, sequence, receipt['input_window_start_monotonic'], manifest['input_tolerance_seconds'])
    if receipt.get('input_evidence'):
        need(all(sha(folder / name) == digest for name, digest in receipt['input_evidence'].items()),
             'Retained input timing evidence changed')
    raw = folder / 'observations.jsonl'
    need(receipt.get('raw_sha256') == sha(raw) and
         all(Path(run['observations'][metric]['evidence_file']).resolve() == raw.resolve()
             for metric in ('native_fps', 'native_speed_percent')), 'Run raw evidence binding changed')
    rows = [json.loads(line) for line in raw.read_text().splitlines()]
    included, excluded = select_samples(rows, run['duration_seconds'], run['identity']['game_id'])
    if manifest.get('input_sequence_sha256') is not None and json.loads((folder / 'input-sequence.json').read_text()):
        status_start = next(row for row in rows if row['message'].get('ticket') == 'status-start')
        need(type(status_start.get('monotonic_ns')) is int and
             status_start['monotonic_ns'] / 1e9 == receipt['input_window_start_monotonic'],
             'Measured input clock is not bound to raw status-start acknowledgement')
    if (manifest.get('warmup_input_sequence_sha256') is not None and manifest.get('input_sequence_sha256') is not None and
            receipt.get('warmup_window_start_monotonic') is not None and receipt.get('input_window_start_monotonic') is not None):
        need(receipt['warmup_window_start_monotonic'] + manifest['warmup_seconds'] <= receipt['input_window_start_monotonic'],
             'Warmup and measured input phases overlap')
    for metric in ('native_fps', 'native_speed_percent'):
        need(run['observations'][metric]['start_seconds'] == 0 and
             run['observations'][metric]['end_seconds'] == run['duration_seconds'],
             'Native metric window must cover the exact nominal observation window')
    need(all(run['observations'].get(metric) is None for metric in METRICS
             if metric not in ('native_fps', 'native_speed_percent')),
         'Collector cannot supply audio, pacing, latency or energy observations')
    need(run.get('analysis', {}).get('included_samples') == len(included) and
         run['analysis'].get('excluded_samples') == excluded and
         run['analysis'].get('acquisition_seconds') == rows[-1]['elapsed_seconds'] and
         run['analysis'].get('raw_sha256') == sha(raw), 'Run analysis differs from retained raw window')
    need(run.get('summary') == {metric: (run['observations'].get(metric) or {}).get('value') for metric in METRICS},
         'Run summary differs from metric observations')
    need(run['observations']['native_fps']['value'] == statistics.mean(r['message']['fps']['actual'] for r in included),
         'Report does not match retained raw FPS observations')
    need(run['observations']['native_speed_percent']['value'] == statistics.mean(
         100 * r['message']['vblanksPerSecond']['actual'] / r['message']['vblanksPerSecond']['target'] for r in included),
         'Report does not match retained raw speed observations')
    return run


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ('_supervise', '_exec'):
        return internal(argv[0], argv[1])
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    capture = commands.add_parser('collect')
    for name in ('emulator', 'iso', 'starting-state', 'frozen-config', 'statistics-source', 'manifest', 'scene-definition', 'output', 'xdotool'):
        capture.add_argument('--' + name, type=Path, required=True)
    capture.add_argument('--port', type=int, required=True)
    capture.add_argument('--build-receipt', type=Path)
    capture.add_argument('--build-receipt-sha256')
    capture.add_argument('--review-evidence', type=Path)
    capture.add_argument('--input-sequence', type=Path)
    capture.add_argument('--warmup-input-sequence', type=Path)
    capture.add_argument('--controller-shim', type=Path)
    review = commands.add_parser('compare')
    review.add_argument('--baseline', type=Path, nargs=5, required=True)
    review.add_argument('--candidate', type=Path, nargs=5, required=True)
    review.add_argument('--sustained-baseline', type=Path)
    review.add_argument('--sustained-candidate', type=Path)
    review.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'collect':
        collect(args)
    else:
        need(not args.output.exists(), 'Comparison output already exists')
        arms = [[validate_collected_run(path) for path in paths] for paths in (args.baseline, args.candidate)]
        need({arms[0][0]['identity']['settings']['resolution'], arms[1][0]['identity']['settings']['resolution']} == {'1x', '2x'},
             'Compare only 1x versus 2x')
        need(all(run['identity']['settings']['values'].get('Graphics.FrameSkip') == '0' and
                 str(run['identity']['settings']['values'].get('Graphics.AutoFrameSkip')).casefold() == 'false'
                 for run in arms[0] + arms[1]), 'Frameskip must stay disabled')
        need((args.sustained_baseline is None) == (args.sustained_candidate is None),
             'Supply both sustained arms together')
        sustained = [[validate_collected_run(path)] if path is not None else []
                     for path in (args.sustained_baseline, args.sustained_candidate)]
        write(args.output, compare(*arms, metrics=['native_fps', 'native_speed_percent'], comparison='setting',
             sustained_baseline=sustained[0], sustained_candidate=sustained[1]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
