# SPDX-License-Identifier: MIT
import hashlib
import asyncio
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from tools import host_gameplay_audit as audit


class HostGameplayAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def file(self, path, contents):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)
        return target

    def test_unknown_executable_cannot_use_corrected_source_alone(self):
        binary = self.file('emulator', 'arbitrary')
        source = self.file('statistics.cpp', 'corrected declaration')
        with self.assertRaisesRegex(audit.AuditError, 'reviewed build receipt'):
            audit.verify_statistics(binary, source)

    def test_new_build_receipt_rejects_wrong_executable_binding(self):
        binary = self.file('emulator', 'arbitrary')
        source = self.file('statistics.cpp', 'corrected declaration')
        receipt = self.file('receipt.json', json.dumps({'kind': 'reviewed-host-statistics-build',
            'executable_sha256': '0' * 64}))
        with self.assertRaisesRegex(audit.AuditError, 'does not bind'):
            audit.verify_statistics(binary, source, receipt, audit.sha(receipt))
        with self.assertRaisesRegex(audit.AuditError, 'receipt changed'):
            audit.verify_statistics(binary, source, receipt, '0' * 64)

    def test_changed_inputs_and_configuration_rejected(self):
        from types import SimpleNamespace
        args = SimpleNamespace(emulator=self.file('emulator', 'engine'), iso=self.file('game.iso', 'game'),
            starting_state=self.file('state', 'state'), frozen_config=self.root / 'config')
        self.file('config/ppsspp.ini', 'frozen')
        manifest = {'emulator_sha256': audit.sha(args.emulator), 'iso_sha256': audit.sha(args.iso),
            'starting_state_sha256': audit.sha(args.starting_state), 'configuration': audit.inventory(args.frozen_config)}
        audit.frozen_check(args, manifest)
        args.iso.write_text('changed')
        with self.assertRaisesRegex(audit.AuditError, 'ISO changed'):
            audit.frozen_check(args, manifest)
        args.iso.write_text('game')
        self.file('config/ppsspp.ini', 'native materialized local')
        with self.assertRaisesRegex(audit.AuditError, 'configuration changed'):
            audit.frozen_check(args, manifest)

    def test_configuration_symlinks_rejected(self):
        source = self.file('original', 'x')
        (self.root / 'config').mkdir()
        (self.root / 'config/link').symlink_to(source)
        with self.assertRaisesRegex(audit.AuditError, 'symlinks'):
            audit.inventory(self.root / 'config')

    def test_occupied_observer_port_rejected(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with self.assertRaisesRegex(audit.AuditError, 'occupied'):
                audit.check_port(listener.getsockname()[1])

    def process(self, pid, exe, name='PPSSPPSDL'):
        task = self.root / 'proc' / str(pid)
        task.mkdir(parents=True)
        (task / 'exe').symlink_to(exe)
        (task / 'comm').write_text(name)
        (task / 'stat').write_text(str(pid) + ' (some process) S ' + ' '.join(['0'] * 18 + ['12345']))
        return task

    def test_competing_processes_rejected_without_touching_them(self):
        engine = self.file('PPSSPPSDL', 'engine')
        one = self.process(101, engine)
        audit.competing(engine, owned=101, proc=self.root / 'proc')
        two = self.process(102, engine)
        with self.assertRaisesRegex(audit.AuditError, '102'):
            audit.competing(engine, owned=101, proc=self.root / 'proc')
        self.assertTrue((one / 'exe').exists())
        self.assertTrue((two / 'exe').exists())

    def test_wrong_executable_and_foreign_listener_rejected(self):
        engine = self.file('engine', 'engine')
        foreign = self.file('foreign', 'other')
        task = self.process(101, engine)
        (task / 'fd').mkdir()
        (task / 'fd/3').symlink_to('socket:[45]')
        net = self.root / 'proc/net'
        net.mkdir()
        (net / 'tcp').write_text('header\n0: 0100007F:4BA2 0:0 0A 0 0 0 0 0 45\n')
        (net / 'tcp6').write_text('header\n')
        binding = audit.bind_listener(101, '12345', audit.sha(engine), 19362, self.root / 'proc')
        self.assertEqual(binding['socket_inodes'], ['45'])
        (task / 'exe').unlink()
        (task / 'exe').symlink_to(foreign)
        with self.assertRaisesRegex(audit.AuditError, 'executable differs'):
            audit.bind_listener(101, '12345', audit.sha(engine), 19362, self.root / 'proc')
        (task / 'exe').unlink()
        (task / 'exe').symlink_to(engine)
        (task / 'fd/3').unlink()
        with self.assertRaisesRegex(audit.AuditError, 'listener'):
            audit.bind_listener(101, '12345', audit.sha(engine), 19362, self.root / 'proc')
        with self.assertRaisesRegex(audit.AuditError, 'identity changed'):
            audit.bind_listener(101, 'old-start', audit.sha(engine), 19362, self.root / 'proc')

    @staticmethod
    def rows():
        return [
            {'elapsed_seconds': 2, 'message': {'event': 'game.status', 'ticket': 'status-start'}},
            {'elapsed_seconds': 3, 'message': {'event': 'gpu.stats.get', 'ticket': 's1',
                'fps': {'actual': 30, 'target': 30}, 'vblanksPerSecond': {'actual': 60, 'target': 60}}},
            {'elapsed_seconds': 32, 'message': {'event': 'gpu.stats.get', 'ticket': 'late',
                'fps': {'actual': 1, 'target': 30}, 'vblanksPerSecond': {'actual': 1, 'target': 60}}},
            {'elapsed_seconds': 32.1, 'message': {'event': 'game.status', 'ticket': 'status-end'}}]

    def test_late_observations_preserved_but_excluded(self):
        rows = self.rows()
        included, excluded = audit.select_samples(rows, 30)
        self.assertEqual([r['message']['ticket'] for r in included], ['s1'])
        self.assertEqual([r['message']['ticket'] for r in excluded], ['late'])
        self.assertEqual(len(rows), 4)

    def test_interrupted_or_short_output_never_forms_completion(self):
        with self.assertRaisesRegex(audit.AuditError, 'Interrupted output'):
            audit.select_samples(self.rows()[:-1], 30)
        rows = self.rows()
        rows.pop(2)
        rows[-1]['elapsed_seconds'] = 20
        with self.assertRaisesRegex(audit.AuditError, 'Incomplete observation'):
            audit.select_samples(rows, 30)

    def test_wrong_game_paused_duplicate_or_nonmonotonic_raw_status_rejected(self):
        rows = self.rows()
        for row in (rows[0], rows[-1]):
            row['message'].update(game={'id': 'ULUS10160'}, paused=False)
        audit.select_samples(rows, 30, 'ULUS10160')
        rows[-1]['message']['paused'] = True
        with self.assertRaisesRegex(audit.AuditError, 'paused'):
            audit.select_samples(rows, 30, 'ULUS10160')
        rows[-1]['message']['paused'] = False
        rows[-1]['message']['game']['id'] = 'OTHER'
        with self.assertRaisesRegex(audit.AuditError, 'Wrong game'):
            audit.select_samples(rows, 30, 'ULUS10160')
        rows[-1]['message']['game']['id'] = 'ULUS10160'
        with self.assertRaisesRegex(audit.AuditError, 'Duplicate'):
            audit.select_samples(rows + [rows[-1]], 30, 'ULUS10160')
        rows[1]['elapsed_seconds'] = float('nan')
        with self.assertRaisesRegex(audit.AuditError, 'monotonic'):
            audit.select_samples(rows, 30, 'ULUS10160')

    def test_actual_frozen_settings_resolution_and_frameskip_are_derived(self):
        root = self.root / 'config'
        self.file('config/ppsspp/PSP/SYSTEM/ppsspp.ini',
            '[Graphics]\nInternalResolution=1\nFrameSkip=0\nAutoFrameSkip=False\n')
        local = self.file('config/ppsspp/PSP/SYSTEM/ULUS10160_ppsspp.ini', '[Graphics]\nInternalResolution=2\n')
        settings = audit.configuration_identity(root, 'ULUS10160')
        self.assertEqual(settings['resolution'], '2x')
        self.assertEqual(settings['values']['Graphics.FrameSkip'], '0')
        before = settings['sha256']
        local.write_text('[Graphics]\nInternalResolution=1\n')
        self.assertNotEqual(audit.configuration_identity(root, 'ULUS10160')['sha256'], before)
        local.write_text('[Graphics]\nInternalResolution=2\nAutoFrameSkip=True\n')
        with self.assertRaisesRegex(audit.AuditError, 'disabled'):
            audit.configuration_identity(root, 'ULUS10160')

    @staticmethod
    def publish_native_fixture(folder, context):
        fields = tuple('Synthetic successful load' if value is None else value
                       for value in audit.native_probe.expected_result(context))
        raw = audit.native_probe.encode_packet(b'TPSE1R\n', fields)
        for name in ('result', 'load-completed'):
            audit.native_probe._private_bytes(folder / 'native-load-session' / name, raw)

    def collected_fixture(self):
        folder = self.root / 'collected'
        folder.mkdir()
        config = folder / 'frozen-config/ppsspp/PSP/SYSTEM'
        config.mkdir(parents=True)
        (config / 'ppsspp.ini').write_text('[Graphics]\nInternalResolution=1\nFrameSkip=0\nAutoFrameSkip=False\n')
        (config / 'ULUS10160_ppsspp.ini').write_text('[Graphics]\nInternalResolution=1\n')
        (folder / 'starting.ppst').write_text('Synthetic state fixture')
        engine = folder / 'reference-engine'
        iso = folder / 'reference-iso'
        engine.write_text('Synthetic reference engine')
        iso.write_text('Synthetic reference ISO')
        audit.write(folder / 'scene.json', {'id': 'fixture-scene',
            'starting_state_sha256': audit.sha(folder / 'starting.ppst'), 'camera': 'Synthetic fixed camera',
            'warmup_seconds': 10, 'duration_seconds': 30, 'input_sequence_sha256': None,
            'native_slot': 0, 'native_disc_version': '1.03'})
        (folder / 'statistics-source.cpp').write_text('Synthetic provenance fixture')
        identity = {'system_id': 'PSP', 'game_id': 'ULUS10160', 'game_title': 'Synthetic fixture',
            'content_sha256': audit.sha(iso), 'scene_id': 'fixture-scene',
            'scene_definition_sha256': audit.sha(folder / 'scene.json'), 'device_id': 'host-fixture',
            'environment_sha256': '2' * 64, 'evidence_class': 'host',
            'emulator': {'id': 'fixture', 'version': 'fixture', 'binary_sha256': audit.sha(engine)},
            'settings': audit.configuration_identity(folder / 'frozen-config', 'ULUS10160'),
            'frontend_id': 'fixture-native', 'intended_speed_percent': 100}
        manifest = dict(identity=identity, run_id='fixture-1x', pair_id='pair-1', duration_seconds=30,
            sustained=False, demanding_profile=False, emulator_sha256=audit.sha(engine), iso_sha256=audit.sha(iso),
            native_slot=0, native_disc_version='1.03', native_architecture='x86_64',
            starting_state_sha256=audit.sha(folder / 'starting.ppst'),
            configuration=audit.inventory(folder / 'frozen-config'), warmup_seconds=10)
        audit.write(folder / 'manifest.json', manifest)
        rows = self.rows()
        for row in (rows[0], rows[-1]):
            row['message'].update(game={'id': 'ULUS10160'}, paused=False)
        (folder / 'observations.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        audit.import_raw(manifest, folder / 'observations.jsonl', folder / 'run.json')
        completion = {'root_pid': 101, 'exit_status': 0, 'children_reaped': 1}
        audit.write(folder / 'completion.json', completion)
        context = audit.native_probe.prepare_load_session(folder, emulator=engine, iso=iso, manifest=manifest)
        self.publish_native_fixture(folder, context)
        native_load = audit.native_probe.verify_load_session(folder, context, manifest)
        binding = {'executable_sha256': audit.sha(engine)}
        audit.write(folder / 'receipt.json', dict(status='complete', completion=completion,
            manifest_sha256=audit.sha(folder / 'manifest.json'), frozen_inputs=manifest,
            statistics_binding=binding, raw_sha256=audit.sha(folder / 'observations.jsonl'),
            implementation_sha256=audit.retain_implementation(folder),
            native_load_context_sha256=audit.sha(folder / 'native-load-session/context.json'),
            native_load_before_warmup=native_load, native_load_after_exit=native_load))
        return folder, binding

    def test_import_recomputes_window_and_comparison_rejects_numeric_tampering(self):
        folder, binding = self.collected_fixture()
        with patch.object(audit, 'verify_statistics_binding', return_value=binding):
            run = audit.validate_collected_run(folder / 'run.json')
            self.assertEqual(run['observations']['native_fps']['value'], 30)
            self.assertEqual(run['analysis']['excluded_samples'][0]['message']['ticket'], 'late')
            run['observations']['native_fps']['value'] = 31
            run['summary']['native_fps'] = 31
            audit.write(folder / 'run.json', run)
            with self.assertRaisesRegex(audit.AuditError, 'raw FPS'):
                audit.validate_collected_run(folder / 'run.json')

    def test_metric_window_and_analysis_tampering_rejected(self):
        folder, binding = self.collected_fixture()
        run = json.loads((folder / 'run.json').read_text())
        with patch.object(audit, 'verify_statistics_binding', return_value=binding):
            run['observations']['native_fps']['end_seconds'] = 15
            audit.write(folder / 'run.json', run)
            with self.assertRaisesRegex(audit.AuditError, 'exact nominal'):
                audit.validate_collected_run(folder / 'run.json')
            run['observations']['native_fps']['end_seconds'] = 30
            run['analysis']['included_samples'] = 100
            audit.write(folder / 'run.json', run)
            with self.assertRaisesRegex(audit.AuditError, 'analysis differs'):
                audit.validate_collected_run(folder / 'run.json')

    def test_retained_state_or_completion_tampering_rejects_run(self):
        folder, binding = self.collected_fixture()
        with patch.object(audit, 'verify_statistics_binding', return_value=binding):
            audit.validate_collected_run(folder / 'run.json')
            (folder / 'starting.ppst').write_text('changed')
            with self.assertRaisesRegex(audit.AuditError, 'starting state changed'):
                audit.validate_collected_run(folder / 'run.json')
            (folder / 'starting.ppst').write_text('Synthetic state fixture')
            receipt = json.loads((folder / 'receipt.json').read_text())
            receipt['status'] = 'incomplete'
            audit.write(folder / 'receipt.json', receipt)
            with self.assertRaisesRegex(audit.AuditError, 'normal owned-tree exit'):
                audit.validate_collected_run(folder / 'run.json')

    def test_unsafe_native_id_cannot_escape_frozen_tree(self):
        with self.assertRaisesRegex(audit.AuditError, 'Native game ID'):
            audit.configuration_identity(self.root, '../other')

    def test_scene_freezes_repeat_and_sustained_sequences_under_one_identity(self):
        scene = dict(id='fixture', starting_state_sha256='1' * 64, camera='Fixed forward',
            warmup_seconds=10, duration_seconds=30, input_sequence_sha256='2' * 64,
            sustained_duration_seconds=1800, sustained_input_sequence_sha256='3' * 64)
        manifest = dict(identity={'scene_id': 'fixture'}, starting_state_sha256='1' * 64,
            warmup_seconds=10, duration_seconds=30, input_sequence_sha256='2' * 64, sustained=False)
        audit.validate_scene(manifest, scene)
        manifest.update(sustained=True, duration_seconds=1800, input_sequence_sha256='3' * 64)
        audit.validate_scene(manifest, scene)
        manifest['input_sequence_sha256'] = '2' * 64
        with self.assertRaisesRegex(audit.AuditError, 'selected input sequence'):
            audit.validate_scene(manifest, scene)
        manifest['input_sequence_sha256'] = '3' * 64
        manifest['duration_seconds'] = 30
        with self.assertRaisesRegex(audit.AuditError, 'selected duration'):
            audit.validate_scene(manifest, scene)
        del scene['sustained_duration_seconds']
        manifest['duration_seconds'] = 1800
        with self.assertRaises(audit.AuditError):
            audit.validate_scene(manifest, scene)

    def test_frozen_replay_rejects_overlap_and_out_of_window(self):
        event = dict(at_seconds=0, seconds=1, axes=[0, 1, 0, 0], buttons=1)
        audit.validate_sequence([event], 30)
        with self.assertRaisesRegex(audit.AuditError, 'nonoverlapping'):
            audit.validate_sequence([event, event], 30)
        event['at_seconds'] = 30
        with self.assertRaisesRegex(audit.AuditError, 'within observation'):
            audit.validate_sequence([event], 30)

    def test_native_replay_receipts_must_match_frozen_axes_and_timing(self):
        folder = self.root / 'controller'
        folder.mkdir()
        event = dict(at_seconds=1, seconds=1, axes=[0, 1, 0, 0], buttons=1)
        request = dict(sequence=0, pid=101, axes=[0, 32767, 0, 0], buttons=1,
            requested_monotonic_ns=101000000000, published_monotonic_ns=101010000000,
            expires_monotonic_ns=102000000000)
        observed = dict(event='applied', sequence=0, pid=101, axes=request['axes'], buttons=1,
            result=0, observed_monotonic_ns=101020000000)
        (folder / 'requests.jsonl').write_text(json.dumps(request) + '\n')
        neutral = dict(event='deadline_neutral', sequence=0, pid=101, result=0, observed_monotonic_ns=102020000000)
        (folder / 'observed.jsonl').write_text(json.dumps(observed) + '\n' + json.dumps(neutral) + '\n')
        audit.validate_input_receipts(self.root, [event], 100, .1)
        neutral['observed_monotonic_ns'] = 102200000000
        (folder / 'observed.jsonl').write_text(json.dumps(observed) + '\n' + json.dumps(neutral) + '\n')
        with self.assertRaisesRegex(audit.AuditError, 'hold duration'):
            audit.validate_input_receipts(self.root, [event], 100, .1)
        observed['observed_monotonic_ns'] = 101200000000
        (folder / 'observed.jsonl').write_text(json.dumps(observed) + '\n')
        with self.assertRaisesRegex(audit.AuditError, 'outside frozen timing'):
            audit.validate_input_receipts(self.root, [event], 100, .1)
        request['axes'] = [0, 0, 0, 0]
        observed['axes'] = request['axes']
        (folder / 'requests.jsonl').write_text(json.dumps(request) + '\n')
        (folder / 'observed.jsonl').write_text(json.dumps(observed) + '\n')
        with self.assertRaisesRegex(audit.AuditError, 'differs from frozen sequence'):
            audit.validate_input_receipts(self.root, [event], 100, .1)

    def test_compare_cli_validates_both_sustained_arms_and_delegates(self):
        identity = {'settings': {'resolution': '1x', 'values': {
            'Graphics.FrameSkip': '0', 'Graphics.AutoFrameSkip': 'False'}}}
        before = {'identity': identity}
        after = {'identity': {'settings': dict(identity['settings'], resolution='2x')}}
        baseline = [str(self.root / ('b' + str(i))) for i in range(5)]
        candidate = [str(self.root / ('c' + str(i))) for i in range(5)]
        seen = []
        def validated(path):
            seen.append(Path(path).name)
            return before if Path(path).name.startswith('b') else after
        with patch.object(audit, 'validate_collected_run', side_effect=validated), patch.object(audit, 'compare', return_value={}) as comparator:
            audit.main(['compare', '--baseline', *baseline, '--candidate', *candidate,
                '--sustained-baseline', str(self.root / 'b-soak'),
                '--sustained-candidate', str(self.root / 'c-soak'), '--output', str(self.root / 'comparison.json')])
        self.assertEqual(seen[-2:], ['b-soak', 'c-soak'])
        self.assertEqual(comparator.call_args.kwargs['sustained_baseline'], [before])
        self.assertEqual(comparator.call_args.kwargs['sustained_candidate'], [after])

    def test_input_evidence_binds_final_quit_neutralization_bytes(self):
        folder = self.root / 'controller'
        folder.mkdir()
        (self.root / 'input-sequence.json').write_text('[]')
        (folder / 'requests.jsonl').write_text('request\n')
        observed = folder / 'observed.jsonl'
        observed.write_text('applied\n')
        before_exit = audit.final_input_evidence(self.root)
        with observed.open('a') as stream:
            stream.write('quit_neutral\n')
        final = audit.final_input_evidence(self.root)
        self.assertNotEqual(before_exit['controller/observed.jsonl'], final['controller/observed.jsonl'])
        self.assertEqual(final['controller/observed.jsonl'], audit.sha(observed))
        self.assertEqual(before_exit['controller/requests.jsonl'], final['controller/requests.jsonl'])

    def test_collect_waits_for_owned_exit_before_validating_and_hashing_input_log(self):
        from types import SimpleNamespace
        folder, binding = self.collected_fixture()
        manifest = json.loads((folder / 'manifest.json').read_text())
        scene = json.loads((folder / 'scene.json').read_text())
        engine = self.file('source-engine', 'Synthetic engine identity')
        iso = self.file('source-iso', 'Synthetic game identity')
        source = self.file('source.cpp', 'Synthetic source identity')
        shim = self.file('shim.so', 'Synthetic shim identity')
        event = dict(at_seconds=1, seconds=1, axes=[0, 1, 0, 0], buttons=1)
        sequence = self.file('sequence.json', json.dumps([event]))
        scene.update(warmup_seconds=0, input_sequence_sha256=audit.sha(sequence))
        audit.write(folder / 'scene.json', scene)
        manifest.update(warmup_seconds=0, interval_seconds=1, input_sequence_sha256=audit.sha(sequence),
            controller_shim_sha256=audit.sha(shim), input_tolerance_seconds=.1,
            emulator_sha256=audit.sha(engine), iso_sha256=audit.sha(iso))
        manifest['identity'].update(content_sha256=audit.sha(iso), scene_definition_sha256=audit.sha(folder / 'scene.json'))
        manifest['identity']['emulator']['binary_sha256'] = audit.sha(engine)
        audit.write(folder / 'manifest.json', manifest)
        output = self.root / 'captured'
        args = SimpleNamespace(output=output, emulator=engine, iso=iso,
            starting_state=folder / 'starting.ppst', statistics_source=source,
            manifest=folder / 'manifest.json', scene_definition=folder / 'scene.json',
            frozen_config=folder / 'frozen-config', input_sequence=sequence, controller_shim=shim,
            build_receipt=None, build_receipt_sha256=None, review_evidence=None, port=19362,
            xdotool=self.root / 'not-invoked-xdotool')
        request = dict(sequence=0, pid=101, axes=[0, 32767, 0, 0], buttons=1,
            requested_monotonic_ns=101000000000, published_monotonic_ns=101010000000,
            expires_monotonic_ns=102000000000)
        applied = dict(event='applied', sequence=0, pid=101, axes=request['axes'], buttons=1,
            result=0, observed_monotonic_ns=101020000000)
        class FakeOwnedHelper:
            def __init__(self):
                self.finished = False
                audit.write(output / 'root.json', {'pid': 101, 'start_ticks': '12345'})
                context = audit.native_probe.read_context(output)
                HostGameplayAuditTests.publish_native_fixture(output, context)
            def poll(self):
                return 0 if self.finished else None
            def wait(self, timeout):
                with (output / 'controller/observed.jsonl').open('a') as stream:
                    stream.write(json.dumps(dict(event='quit_neutral', sequence=0, pid=101,
                        result=0, observed_monotonic_ns=102020000000)) + '\n')
                audit.write(output / 'completion.json', {'root_pid': 101, 'exit_status': 0, 'children_reaped': 1})
                self.finished = True
                return 0
        async def fake_replay(*_args, **_kwargs):
            return None
        async def fake_observe(raw, **kwargs):
            await kwargs['replay'](100)
            (output / 'controller/requests.jsonl').write_text(json.dumps(request) + '\n')
            (output / 'controller/observed.jsonl').write_text(json.dumps(applied) + '\n')
            rows = self.rows()
            for row in (rows[0], rows[-1]):
                row['message'].update(game={'id': 'ULUS10160'}, paused=False)
            Path(raw).write_text(''.join(json.dumps(row) + '\n' for row in rows))
            return rows
        with patch.object(audit, 'verify_statistics', return_value=binding), \
             patch.object(audit, 'competing'), patch.object(audit, 'check_port'), \
             patch.object(audit, 'bind_listener', return_value={}), patch.object(audit, 'normal_exit'), \
             patch.object(audit, 'replay_inputs', side_effect=fake_replay), \
             patch.object(audit, 'observe', side_effect=fake_observe), \
             patch.object(audit.subprocess, 'Popen', side_effect=lambda *_args, **_kw: FakeOwnedHelper()):
            audit.collect(args)
        receipt = json.loads((output / 'receipt.json').read_text())
        self.assertEqual(receipt['status'], 'complete')
        self.assertEqual(receipt['input_evidence']['controller/observed.jsonl'], audit.sha(output / 'controller/observed.jsonl'))
        self.assertIn('quit_neutral', (output / 'controller/observed.jsonl').read_text())

    def test_warmup_and_measured_requests_validate_as_separate_frozen_phases(self):
        controller = self.root / 'controller'
        controller.mkdir()
        warmup = dict(at_seconds=0, seconds=.1, axes=[.01, .01, .01, .01], buttons=0)
        measured = dict(at_seconds=1, seconds=1, axes=[0, 1, 0, 0], buttons=1)
        warmup_request = dict(sequence=0, pid=101, axes=[328, 328, 328, 328], buttons=0,
            requested_monotonic_ns=100000000000, published_monotonic_ns=100010000000,
            expires_monotonic_ns=100100000000)
        measured_request = dict(sequence=1, pid=101, axes=[0, 32767, 0, 0], buttons=1,
            requested_monotonic_ns=111000000000, published_monotonic_ns=111010000000,
            expires_monotonic_ns=112000000000)
        observed = [dict(event='applied', sequence=0, pid=101, axes=warmup_request['axes'], buttons=0,
                result=0, observed_monotonic_ns=100020000000),
            dict(event='deadline_neutral', sequence=0, pid=101, result=0, observed_monotonic_ns=100120000000),
            dict(event='applied', sequence=1, pid=101, axes=measured_request['axes'], buttons=1,
                result=0, observed_monotonic_ns=111020000000),
            dict(event='deadline_neutral', sequence=1, pid=101, result=0, observed_monotonic_ns=112020000000)]
        (controller / 'warmup-requests.jsonl').write_text(json.dumps(warmup_request) + '\n')
        (controller / 'requests.jsonl').write_text(json.dumps(measured_request) + '\n')
        (controller / 'observed.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in observed))
        audit.validate_input_receipts(self.root, [warmup], 100, .1, request_name='warmup-requests.jsonl')
        audit.validate_input_receipts(self.root, [measured], 110, .1)
        # Changing the warmup phase does not silently alter measured validation.
        warmup['axes'] = [0, 0, 0, 0]
        with self.assertRaisesRegex(audit.AuditError, 'differs from frozen sequence'):
            audit.validate_input_receipts(self.root, [warmup], 100, .1, request_name='warmup-requests.jsonl')
        audit.validate_input_receipts(self.root, [measured], 110, .1)

    def test_scene_warmup_sequence_digest_is_explicitly_bound(self):
        scene = dict(id='fixture', starting_state_sha256='1' * 64, camera='Fixed forward',
            warmup_seconds=10, duration_seconds=30, input_sequence_sha256='2' * 64,
            warmup_input_sequence_sha256='3' * 64)
        manifest = dict(identity={'scene_id': 'fixture'}, starting_state_sha256='1' * 64,
            warmup_seconds=10, duration_seconds=30, input_sequence_sha256='2' * 64,
            warmup_input_sequence_sha256='3' * 64, sustained=False)
        audit.validate_scene(manifest, scene)
        manifest['warmup_input_sequence_sha256'] = '4' * 64
        with self.assertRaises(audit.AuditError):
            audit.validate_scene(manifest, scene)

    def test_native_failed_load_and_fresh_context_mismatch_rejected(self):
        folder, _ = self.collected_fixture()
        context = audit.native_probe.read_context(folder)
        manifest = json.loads((folder / 'manifest.json').read_text())
        audit.native_probe.verify_load_session(folder, context, manifest)
        result = folder / 'native-load-session/result'
        original = result.read_bytes()
        fields = list(audit.native_probe._decode_packet(original, b'TPSE1R\n', 27))
        fields[8] = 'failure'
        fields[10:] = [''] * 17
        result.write_bytes(audit.native_probe.encode_packet(b'TPSE1R\n', fields))
        with self.assertRaisesRegex(audit.native_probe.NativeAuditError, 'load failed'):
            audit.native_probe.verify_load_session(folder, context, manifest)
        result.write_bytes(original)
        fields = list(audit.native_probe._decode_packet(original, b'TPSE1R\n', 27))
        fields[0] = '0' * 32
        result.write_bytes(audit.native_probe.encode_packet(b'TPSE1R\n', fields))
        with self.assertRaisesRegex(audit.native_probe.NativeAuditError, 'another session'):
            audit.native_probe.verify_load_session(folder, context, manifest)

    def test_native_wrong_slot_future_sequence_and_incomplete_publication_rejected(self):
        folder, _ = self.collected_fixture()
        context = audit.native_probe.read_context(folder)
        manifest = json.loads((folder / 'manifest.json').read_text())
        result = folder / 'native-load-session/result'
        completed = folder / 'native-load-session/load-completed'
        original = result.read_bytes()
        for index, value, reason in [(7, '2', 'stale sequence'), (21, '1', 'exact game/engine/state/slot')]:
            fields = list(audit.native_probe._decode_packet(original, b'TPSE1R\n', 27))
            fields[index] = value
            packet = audit.native_probe.encode_packet(b'TPSE1R\n', fields)
            result.write_bytes(packet)
            completed.write_bytes(packet)
            with self.assertRaisesRegex(audit.native_probe.NativeAuditError, reason):
                audit.native_probe.verify_load_session(folder, context, manifest)
        result.write_bytes(original)
        completed.write_bytes(original[:-1])
        with self.assertRaises(ValueError):
            audit.native_probe.verify_load_session(folder, context, manifest)
        completed.write_bytes(original)
        completed.chmod(0o644)
        with self.assertRaisesRegex(audit.native_probe.NativeAuditError, '0600'):
            audit.native_probe.verify_load_session(folder, context, manifest)

    def test_phase_waits_for_unpaused_game_ack_before_replaying_input(self):
        from types import SimpleNamespace
        class Socket:
            async def send(self, payload):
                self.request = json.loads(payload)
            async def recv(self):
                request = self.request
                event, ticket = request['event'], request['ticket']
                message = {'event': event, 'ticket': ticket}
                if event == 'game.status':
                    message.update(game={'id': 'ULUS10160'}, paused=ticket == 'status-ready-0')
                elif event == 'gpu.stats.get':
                    message.update(fps={'actual': 30, 'target': 30},
                        vblanksPerSecond={'actual': 60, 'target': 60})
                return json.dumps(message)
        class Connection:
            async def __aenter__(self):
                return Socket()
            async def __aexit__(self, *_args):
                pass
        replay_origins = []
        async def replay(origin):
            replay_origins.append(origin)
        raw = self.root / 'warmup-observations.jsonl'
        with patch.dict('sys.modules', {'websockets': SimpleNamespace(connect=lambda *_args, **_kw: Connection())}):
            rows = asyncio.run(audit.observe(raw, port=19362, seconds=.01, interval=.25,
                game_id='ULUS10160', check=lambda: None, replay=replay))
        ready = [row for row in rows if row['message'].get('ticket', '').startswith('status-ready-')]
        self.assertEqual([row['message']['paused'] for row in ready], [True, False])
        start = next(row for row in rows if row['message'].get('ticket') == 'status-start')
        self.assertEqual(replay_origins, [start['monotonic_ns'] / 1e9])
        self.assertGreater(start['elapsed_seconds'], ready[0]['elapsed_seconds'])
        self.assertTrue(raw.exists())

    def test_ppsspp_collector_rejects_ps1_identity_before_launch(self):
        from types import SimpleNamespace
        folder, _ = self.collected_fixture()
        manifest = json.loads((folder / 'manifest.json').read_text())
        manifest['identity']['system_id'] = 'PS1'
        with self.assertRaisesRegex(audit.AuditError, 'admitted PSP engine'):
            audit.validate_manifest(SimpleNamespace(scene_definition=folder / 'scene.json'), manifest)

    def test_retained_collector_helper_source_tampering_rejected(self):
        folder, binding = self.collected_fixture()
        with patch.object(audit, 'verify_statistics_binding', return_value=binding):
            audit.validate_collected_run(folder / 'run.json')
            (folder / 'collector-source/tools/host_audit_native.py').write_text('changed helper')
            with self.assertRaisesRegex(audit.AuditError, 'helper implementation changed'):
                audit.validate_collected_run(folder / 'run.json')

    def test_nonfinite_counters_rejected(self):
        rows = self.rows()
        rows[1]['message']['fps']['actual'] = float('nan')
        with self.assertRaisesRegex(audit.AuditError, 'Invalid native counter'):
            audit.select_samples(rows, 30)

    def test_failed_preflight_retained_as_failed_not_success(self):
        from types import SimpleNamespace
        args = SimpleNamespace(output=self.root / 'out', emulator=self.root / 'engine',
            iso=self.root / 'game', starting_state=self.root / 'state', statistics_source=self.root / 'source',
            manifest=self.file('manifest', '{}'), frozen_config=self.root / 'config')
        with self.assertRaises(KeyError):
            audit.collect(args)
        receipt = json.loads((args.output / 'receipt.json').read_text())
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse((args.output / 'run.json').exists())
        self.assertGreaterEqual(receipt['acquisition_seconds'], 0)

    def test_atomic_interrupted_report_does_not_replace_last_valid(self):
        output = self.root / 'report.json'
        audit.write(output, {'valid': 1})
        with patch.object(audit.os, 'replace', side_effect=OSError('interrupted publication')):
            with self.assertRaises(OSError):
                audit.write(output, {'valid': 2})
        self.assertEqual(json.loads(output.read_text()), {'valid': 1})
        self.assertTrue(output.with_name('report.json.partial').exists())


if __name__ == '__main__':
    unittest.main()
