#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record evidence-backed PSP/PS1 gameplay observations and matched comparisons.

This imports measurements, never launches games or changes an emulator. Native
counters, video, audio and instrument observations remain separate from frontend
presentation timing and from the existing read-only process sampler.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from tools.benchmark import BenchmarkError, _write_report


METRICS = {
    'native_speed_percent': ('percent', {'native-counter'}),
    'native_fps': ('fps', {'native-counter'}),
    'frame_time_p95_ms': ('ms', {'native-frame-log', 'video-analysis'}),
    'audio_faults': ('count', {'audio-review'}),
    'load_time_ms': ('ms', {'native-log', 'video-analysis', 'monotonic-loading'}),
    'input_latency_ms': ('ms', {'video-analysis'}),
    'battery_energy_wh': ('Wh', {'calibrated-instrument'}),
}
IDENTITY_FIELDS = {
    'system_id', 'game_id', 'game_title', 'content_sha256', 'scene_id',
    'scene_definition_sha256', 'device_id', 'environment_sha256', 'evidence_class',
    'emulator', 'settings', 'frontend_id', 'intended_speed_percent',
}


def _need(condition, message):
    if not condition:
        raise BenchmarkError(message)


def _text(value, field):
    _need(isinstance(value, str) and 0 < len(value) <= 2048 and
          all(c >= ' ' for c in value), f'{field} needs bounded, nonempty text')


def _digest(value, field):
    _need(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value),
          f'{field} needs a lowercase SHA-256')


def _number(value, field, *, positive=False):
    _need(type(value) in (int, float) and math.isfinite(value) and
          (value > 0 if positive else value >= 0), f'Invalid {field}')


def validate_identity(identity):
    """Require exact declared identities; a declaration does not qualify hardware."""
    _need(isinstance(identity, dict) and set(identity) == IDENTITY_FIELDS,
          'Gameplay identity has missing or unsupported fields')
    for field in ('game_id', 'game_title', 'scene_id', 'device_id', 'frontend_id'):
        _text(identity[field], field)
    _need(identity['system_id'] in ('PSP', 'PS1'), 'Select PSP or PS1 gameplay')
    _need(identity['evidence_class'] in ('host', 'operator-declared-physical-device'),
          'Declare host or operator-declared-physical-device evidence')
    for field in ('content_sha256', 'scene_definition_sha256', 'environment_sha256'):
        _digest(identity[field], field)
    emulator = identity['emulator']
    _need(isinstance(emulator, dict) and set(emulator) == {'id', 'version', 'binary_sha256'},
          'Record exact emulator ID, version and executable SHA-256')
    _text(emulator['id'], 'emulator ID')
    _text(emulator['version'], 'emulator version')
    _digest(emulator['binary_sha256'], 'emulator binary')
    settings = identity['settings']
    _need(isinstance(settings, dict) and set(settings) == {'sha256', 'resolution', 'frameskip', 'values'},
          'Record settings digest, resolution, frameskip and explicit values')
    _digest(settings['sha256'], 'settings')
    _text(settings['resolution'], 'resolution')
    _text(settings['frameskip'], 'frameskip')
    _need(isinstance(settings['values'], dict) and settings['values'],
          'Record the complete selected gameplay settings')
    _need(all(isinstance(key, str) and 0 < len(key) <= 256 and '.' in key and
              all(character > ' ' for character in key) and
              type(value) in (str, int, float, bool) and
              (not isinstance(value, str) or len(value) <= 2048)
              for key, value in settings['values'].items()),
          'Settings values must be flat scalar values keyed by canonical Section.NativeKey names')
    try:
        serialized = json.dumps(settings['values'], sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise BenchmarkError('Settings must be finite JSON values') from error
    _need(len(serialized) <= 65536, 'Gameplay settings are too large')
    # Hash the exact configuration bytes separately; values describe the tradeoff.
    _number(identity['intended_speed_percent'], 'intended game speed', positive=True)
    return copy.deepcopy(identity)


def validate_run(run, *, verify_files=False):
    _need(isinstance(run, dict) and run.get('schema') == 1 and
          run.get('measurement_domain') == 'gameplay', 'A gameplay run is required; menu timing is incompatible')
    validate_identity(run.get('identity'))
    for field in ('run_id', 'pair_id'):
        _text(run.get(field), field)
    _number(run.get('duration_seconds'), 'actual gameplay duration', positive=True)
    _need(type(run.get('sustained')) is bool and type(run.get('demanding_profile')) is bool,
          'Declare sustained and demanding-profile status')
    if run['sustained']:
        _need(run['duration_seconds'] >= 1800, 'Sustained gameplay needs at least 30 minutes')
    observations = run.get('observations')
    _need(isinstance(observations, dict) and not set(observations) - set(METRICS),
          'Unsupported or missing gameplay observations')
    _need(any(value is not None for value in observations.values()),
          'No gameplay observations supplied; unavailable values cannot form a report')
    for metric, observation in observations.items():
        if observation is None:
            continue
        unit, methods = METRICS[metric]
        _need(isinstance(observation, dict) and set(observation) ==
              {'value', 'unit', 'method', 'evidence_file', 'evidence_sha256', 'start_seconds', 'end_seconds'},
              f'{metric} needs its value, method, evidence and observation window')
        _number(observation['value'], metric)
        _need(observation['unit'] == unit and observation['method'] in methods,
              f'Incompatible {metric} unit or source; process/menu timing cannot supply gameplay counters')
        if metric == 'audio_faults':
            _need(type(observation['value']) is int, 'Audio faults must be an observed integer count')
        _number(observation['start_seconds'], 'observation start')
        _number(observation['end_seconds'], 'observation end', positive=True)
        _need(observation['start_seconds'] < observation['end_seconds'] <= run['duration_seconds'],
              'Observation window is outside the gameplay run')
        if run['sustained']:
            _need(observation['start_seconds'] == 0 and observation['end_seconds'] == run['duration_seconds'],
                  'Sustained observations must cover the complete sustained run')
        _text(observation['evidence_file'], 'evidence file')
        _digest(observation['evidence_sha256'], 'observation evidence')
        if verify_files:
            path = Path(observation['evidence_file'])
            _need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 64 * 1024 * 1024,
                  'Observation evidence must be a nonempty regular file of at most 64 MiB')
            _need(hashlib.sha256(path.read_bytes()).hexdigest() == observation['evidence_sha256'],
                  'Observation evidence is missing or changed')
    return run


def record(manifest, observations, output, *, resources=None):
    """Bind operator observations to retained evidence; never infer missing metrics."""
    _need(isinstance(manifest, dict) and set(manifest) ==
          {'identity', 'run_id', 'pair_id', 'duration_seconds', 'sustained', 'demanding_profile'},
          'Run manifest has missing or unsupported fields')
    run = copy.deepcopy(manifest)
    run.update(schema=1, measurement_domain='gameplay', observations=copy.deepcopy(observations))
    validate_run(run, verify_files=True)
    _need(all(Path(observation['evidence_file']).resolve() != Path(output).resolve()
              for observation in observations.values() if observation is not None),
          'Report output must not overwrite observation evidence')
    run['collected_at_utc'] = datetime.now(timezone.utc).isoformat()
    run['summary'] = {name: (observations.get(name) or {}).get('value') for name in METRICS}
    if resources is not None:
        _need(isinstance(resources, dict) and 'samples' in resources and
              resources.get('summary', {}).get('fps') is None and
              resources.get('measurement_domain') == 'gameplay-resources' and
              resources.get('gameplay_identity') == run['identity'] and
              resources.get('requested_seconds') == run['duration_seconds'] and
              resources.get('stop_reason') == 'duration-reached',
              'Use a complete resource-sampler report for the identical gameplay identity/duration, without inferred FPS')
        run['resource_observations'] = copy.deepcopy(resources)
    run['hardware_qualified'] = False
    run['limits'] = [
        'Game, scene, settings and physical identity are operator declarations for review.',
        'Evidence digests detect changed files; they do not authenticate the measurement or device.',
        'Native FPS and game speed are distinct; neither establishes panel pacing or audio quality.',
        'Absent metrics remain unavailable; menu timing and process CPU/RSS cannot supply gameplay FPS.',
    ]
    _write_report(output, run)
    return run


def _changed_settings(before, after):
    """Names are canonical configuration keys, not entire preset bundles."""
    return {key for key in set(before) | set(after) if before.get(key) != after.get(key)}


def compare(baseline, candidate, *, metrics, comparison='frontend', sustained_baseline=(), sustained_candidate=()):
    """Reject incomplete/mismatched evidence; return measurements without marketing claims."""
    _need(comparison in ('frontend', 'setting', 'emulator'), 'Select frontend, setting or emulator comparison')
    _need(isinstance(metrics, (list, tuple)) and metrics and len(set(metrics)) == len(metrics) and
          all(name in METRICS for name in metrics), 'Select unique measured gameplay metrics')
    _need(len(baseline) == len(candidate) == 5, 'Use exactly five matched runs for each selected scene')
    all_runs = list(baseline) + list(candidate)
    for run in all_runs:
        validate_run(run, verify_files=True)
        _need(not run['sustained'], 'Keep five scene repeats separate from sustained runs')
    _need(len({run['run_id'] for run in all_runs}) == 10, 'Run IDs must be unique; do not reuse observations')
    before = {run['pair_id']: run for run in baseline}
    after = {run['pair_id']: run for run in candidate}
    _need(len(before) == len(after) == 5 and set(before) == set(after), 'Five distinct matched pair IDs are required')
    first_before, first_after = baseline[0]['identity'], candidate[0]['identity']
    invariant_fields = IDENTITY_FIELDS - {'frontend_id', 'settings', 'emulator'}
    for run in all_runs:
        identity = run['identity']
        _need(all(identity[key] == first_before[key] for key in invariant_fields),
              'Incompatible game, scene, environment, intended speed or device')
    for runs, reference in ((baseline, first_before), (candidate, first_after)):
        _need(all(run['identity'] == reference for run in runs), 'Each arm must use identical emulator/settings/frontend identities')
    if comparison == 'frontend':
        _need(first_before['emulator'] == first_after['emulator'] and
              first_before['settings'] == first_after['settings'] and
              first_before['frontend_id'] != first_after['frontend_id'],
              'Frontend comparison must keep emulator and settings identical')
    elif comparison == 'setting':
        _need(first_before['frontend_id'] == first_after['frontend_id'] and
              first_before['emulator'] == first_after['emulator'], 'Change one setting on the same frontend/emulator')
        _need(first_before['settings']['sha256'] != first_after['settings']['sha256'] and
              len(_changed_settings(first_before['settings']['values'], first_after['settings']['values'])) == 1,
              'Setting comparison must change exactly one native setting')
        changed = next(iter(_changed_settings(first_before['settings']['values'], first_after['settings']['values'])))
        if first_before['settings']['resolution'] != first_after['settings']['resolution']:
            _need(changed.casefold() in ('graphics.internalresolution', 'internalresolution', 'resolution'),
                  'Resolution metadata changed alongside an unrelated setting')
        if first_before['settings']['frameskip'] != first_after['settings']['frameskip']:
            _need(changed.casefold() in ('graphics.frameskip', 'frameskip'),
                  'Frameskip metadata changed alongside an unrelated setting')
    else:
        _need(first_before['frontend_id'] == first_after['frontend_id'] and
              first_before['settings'] == first_after['settings'] and
              first_before['emulator']['binary_sha256'] != first_after['emulator']['binary_sha256'],
              'Change only the emulator executable in an emulator comparison')
    evidence_slices = set()
    def independent_observation(run, name):
        observation = run['observations'].get(name)
        _need(observation is not None, f'Missing {name} observation; comparison is unavailable')
        key = (name, observation['evidence_sha256'])
        _need(key not in evidence_slices, f'Reused {name} evidence; retain a distinct run-specific raw observation')
        evidence_slices.add(key)
        return observation
    pairs = []
    for pair_id in before:
        left, right = before[pair_id], after[pair_id]
        _need(left['duration_seconds'] == right['duration_seconds'] and
              left['demanding_profile'] == right['demanding_profile'], 'Matched runs need the same duration/profile')
        measured = {}
        for name in metrics:
            old, new = independent_observation(left, name), independent_observation(right, name)
            _need(all(old[field] == new[field] for field in ('unit', 'method', 'start_seconds', 'end_seconds')),
                  f'Incompatible {name} observation method/window')
            measured[name] = {'baseline': old['value'], 'candidate': new['value'],
                              'difference': new['value'] - old['value'], 'unit': old['unit']}
        pairs.append({'pair_id': pair_id, 'baseline_run_id': left['run_id'],
                      'candidate_run_id': right['run_id'], 'metrics': measured})
    demanding = any(run['demanding_profile'] for run in all_runs)
    sustained = {'required': demanding, 'complete': False}
    if demanding or sustained_baseline or sustained_candidate:
        _need(len(sustained_baseline) == len(sustained_candidate) == 1,
              'Demanding release profiles require a separate matched 30-minute sustained run per arm')
        for run, reference in ((sustained_baseline[0], first_before), (sustained_candidate[0], first_after)):
            validate_run(run, verify_files=True)
            _need(run['sustained'] and run['identity'] == reference and run['demanding_profile'] == demanding,
                  'Sustained run identity/profile does not match its arm')
            _need(all(run['observations'].get(name) is not None for name in metrics),
                  'Sustained run lacks a selected gameplay observation')
            _need(run['run_id'] not in {entry['run_id'] for entry in all_runs},
                  'Sustained evidence must have a separate run identity')
            for name in metrics:
                independent_observation(run, name)
        _need(sustained_baseline[0]['duration_seconds'] == sustained_candidate[0]['duration_seconds'],
              'Sustained runs need matched duration')
        _need(sustained_baseline[0]['run_id'] != sustained_candidate[0]['run_id'] and
              sustained_baseline[0]['pair_id'] == sustained_candidate[0]['pair_id'],
              'Sustained runs need unique run IDs and a matched pair ID')
        for name in metrics:
            _need(sustained_baseline[0]['observations'][name]['method'] ==
                  sustained_candidate[0]['observations'][name]['method'],
                  'Sustained observations use incompatible methods')
        sustained.update(complete=True, baseline_run_id=sustained_baseline[0]['run_id'],
                         candidate_run_id=sustained_candidate[0]['run_id'])
    return {'schema': 1, 'measurement_domain': 'gameplay-comparison', 'comparison': comparison,
            'baseline_identity': copy.deepcopy(first_before), 'candidate_identity': copy.deepcopy(first_after),
            'matched_runs': pairs, 'sustained': sustained,
            'metrics': {name: {'baseline_median': statistics.median(p['metrics'][name]['baseline'] for p in pairs),
                               'candidate_median': statistics.median(p['metrics'][name]['candidate'] for p in pairs),
                               'paired_difference_median': statistics.median(p['metrics'][name]['difference'] for p in pairs),
                               'unit': METRICS[name][0]} for name in metrics},
            'hardware_qualified': False, 'marketing_claim_approved': False,
            'limits': ['Five matched operator observations require independent evidence review.',
                       'Correct speed, frame pacing, audio and image quality need joint interpretation.',
                       'A host comparison is not Smart Pro performance evidence.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('record')
    create.add_argument('--manifest', type=Path, required=True)
    create.add_argument('--observations', type=Path, required=True)
    create.add_argument('--resources', type=Path)
    review = commands.add_parser('compare')
    review.add_argument('--baseline', type=Path, nargs='+', required=True)
    review.add_argument('--candidate', type=Path, nargs='+', required=True)
    review.add_argument('--metric', action='append', required=True, choices=tuple(METRICS))
    review.add_argument('--comparison', choices=('frontend', 'setting', 'emulator'), default='frontend')
    review.add_argument('--sustained-baseline', type=Path, nargs='*', default=[])
    review.add_argument('--sustained-candidate', type=Path, nargs='*', default=[])
    for child in (create, review):
        child.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def read(path):
        _need(path.stat().st_size <= 16 * 1024 * 1024, 'Report input exceeds 16 MiB')
        return json.loads(path.read_text())
    try:
        if args.command == 'record':
            result = record(read(args.manifest), read(args.observations), args.output,
                            resources=read(args.resources) if args.resources else None)
        else:
            result = compare([read(p) for p in args.baseline], [read(p) for p in args.candidate],
                             metrics=args.metric, comparison=args.comparison,
                             sustained_baseline=[read(p) for p in args.sustained_baseline],
                             sustained_candidate=[read(p) for p in args.sustained_candidate])
            _write_report(args.output, result)
    except (BenchmarkError, OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({'output': str(args.output), 'measurement_domain': result['measurement_domain'],
                      'hardware_qualified': False}))


if __name__ == '__main__':
    main()
