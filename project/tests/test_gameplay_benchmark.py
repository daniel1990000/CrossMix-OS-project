# SPDX-License-Identifier: MIT
"""Gameplay evidence compatibility; all observations below are explicit fixtures."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.benchmark import BenchmarkError, capture
from tools.gameplay_benchmark import compare, record, validate_run


def identity(system='PSP', frontend='spruce-classic'):
    return {'system_id': system, 'game_id': 'fixture-id', 'game_title': 'Synthetic test fixture',
            'content_sha256': '1' * 64, 'scene_id': 'fixed-scene', 'scene_definition_sha256': '2' * 64,
            'device_id': 'fixture-host', 'environment_sha256': '3' * 64, 'evidence_class': 'host',
            'emulator': {'id': 'ppsspp' if system == 'PSP' else 'existing-ps1',
                         'version': 'fixture', 'binary_sha256': '4' * 64},
            'settings': {'sha256': '5' * 64, 'resolution': '1x', 'frameskip': '0',
                         'values': {'Graphics.InternalResolution': 1, 'Graphics.FrameSkip': 0}},
            'frontend_id': frontend, 'intended_speed_percent': 100}


def run(index, *, evidence_root, frontend='spruce-classic', system='PSP'):
    evidence = evidence_root / (system + '-' + frontend + '-' + str(index) + '.log')
    evidence.write_text('Synthetic fixture native observation: ' + str(evidence) + '\n')
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    return {'schema': 1, 'measurement_domain': 'gameplay', 'identity': identity(system, frontend),
            'run_id': frontend + '-' + str(index), 'pair_id': str(index), 'duration_seconds': 30,
            'sustained': False, 'demanding_profile': False,
            'observations': {'native_fps': {'value': 59, 'unit': 'fps', 'method': 'native-counter',
                'evidence_file': str(evidence), 'evidence_sha256': digest,
                'start_seconds': 0, 'end_seconds': 30}}}


class GameplayBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_fixture(self, index, **kwargs):
        return run(index, evidence_root=self.root, **kwargs)

    def arms(self, system='PSP'):
        return ([self.run_fixture(i, system=system) for i in range(5)],
                [self.run_fixture(i, frontend='project', system=system) for i in range(5)])

    def test_psp_ps1_matched_runs_compare_native_observations(self):
        for system in ('PSP', 'PS1'):
            with self.subTest(system=system):
                before, after = self.arms(system)
                for candidate in after:
                    candidate['observations']['native_fps']['value'] = 60
                result = compare(before, after, metrics=['native_fps'])
                self.assertEqual(len(result['matched_runs']), 5)
                self.assertEqual(result['metrics']['native_fps']['paired_difference_median'], 1)
                self.assertFalse(result['hardware_qualified'])
                self.assertFalse(result['marketing_claim_approved'])

    def test_fewer_than_five_missing_observations_and_reused_ids_are_rejected(self):
        before, after = self.arms()
        for a, b in ((before[:4], after[:4]), (before, before)):
            with self.assertRaises(BenchmarkError):
                compare(a, b, metrics=['native_fps'])
        after[0]['observations']['native_fps'] = None
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'])

    def test_menu_timing_and_proc_fps_are_incompatible(self):
        before, after = self.arms()
        after[0]['measurement_domain'] = 'frontend-menu'
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'])
        for method in ('SDL_RenderPresent', 'proc-cpu', 'video-analysis'):
            value = self.run_fixture(0)
            value['observations']['native_fps']['method'] = method
            with self.subTest(method=method), self.assertRaises(BenchmarkError):
                validate_run(value)

    def test_game_scene_device_environment_and_emulator_mismatch_rejected(self):
        for field in ('content_sha256', 'scene_definition_sha256', 'environment_sha256', 'device_id'):
            before, after = self.arms()
            after[0]['identity'][field] = '9' * 64
            with self.subTest(field=field), self.assertRaises(BenchmarkError):
                compare(before, after, metrics=['native_fps'])
        before, after = self.arms()
        for candidate in after:
            candidate['identity']['emulator']['binary_sha256'] = 'a' * 64
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'])

    def test_incompatible_windows_or_methods_cannot_compare(self):
        before, after = self.arms()
        after[0]['observations']['native_fps']['end_seconds'] = 29
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'])

    def test_unavailable_selected_metric_is_rejected(self):
        before, after = self.arms()
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps', 'input_latency_ms'])

    def test_setting_change_must_be_individual_and_preserve_emulator(self):
        before, after = self.arms()
        for baseline in before:
            baseline['identity']['frontend_id'] = 'project'
        for candidate in after:
            candidate['identity']['settings']['sha256'] = 'a' * 64
            candidate['identity']['settings']['resolution'] = '2x'
            candidate['identity']['settings']['values']['Graphics.InternalResolution'] = 2
        report = compare(before, after, metrics=['native_fps'], comparison='setting')
        self.assertEqual(report['comparison'], 'setting')
        for candidate in after:
            candidate['identity']['settings']['values']['Graphics.FrameSkip'] = 1
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'], comparison='setting')

    def test_emulator_change_cannot_be_bundled_with_settings_change(self):
        before, after = self.arms()
        for baseline in before:
            baseline['identity']['frontend_id'] = 'project'
        for candidate in after:
            candidate['identity']['emulator']['binary_sha256'] = 'a' * 64
        self.assertEqual(compare(before, after, metrics=['native_fps'], comparison='emulator')['comparison'], 'emulator')
        after[0]['identity']['settings']['sha256'] = 'b' * 64
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'], comparison='emulator')

    def test_demanding_profile_needs_separate_matched_thirty_minute_runs(self):
        before, after = self.arms()
        for value in before + after:
            value['demanding_profile'] = True
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'])
        old, new = copy.deepcopy(before[0]), copy.deepcopy(after[0])
        for value in (old, new):
            value['sustained'], value['duration_seconds'] = True, 1799
            value['run_id'] += '-sustained'
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'], sustained_baseline=[old], sustained_candidate=[new])
        for value in (old, new):
            value['duration_seconds'] = 1800
        with self.assertRaises(BenchmarkError):
            compare(before, after, metrics=['native_fps'], sustained_baseline=[old], sustained_candidate=[new])
        for value in (old, new):
            value['observations']['native_fps']['end_seconds'] = 1800
            path = self.root / (value['run_id'] + '.log')
            path.write_text('Synthetic sustained raw observation: ' + value['run_id'])
            value['observations']['native_fps'].update(evidence_file=str(path),
                evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        result = compare(before, after, metrics=['native_fps'], sustained_baseline=[old], sustained_candidate=[new])
        self.assertTrue(result['sustained']['complete'])

    def test_invalid_numeric_values_and_units_are_rejected(self):
        for invalid in (None, True, -1, float('nan'), float('inf'), '60'):
            value = self.run_fixture(0)
            value['observations']['native_fps']['value'] = invalid
            with self.subTest(value=invalid), self.assertRaises(BenchmarkError):
                validate_run(value)
        value = self.run_fixture(0)
        value['observations']['native_fps']['unit'] = 'percent'
        with self.assertRaises(BenchmarkError):
            validate_run(value)

    def test_comparison_rechecks_missing_and_changed_retained_observations(self):
        before, after = self.arms()
        path = Path(after[0]['observations']['native_fps']['evidence_file'])
        path.write_text('changed after recording')
        with self.assertRaisesRegex(BenchmarkError, 'missing or changed'):
            compare(before, after, metrics=['native_fps'])
        path.unlink()
        with self.assertRaisesRegex(BenchmarkError, 'regular file'):
            compare(before, after, metrics=['native_fps'])

    def test_identical_observation_copies_cannot_supply_distinct_runs(self):
        before, after = self.arms()
        source = before[0]['observations']['native_fps']
        duplicate = after[0]['observations']['native_fps']
        Path(duplicate['evidence_file']).write_bytes(Path(source['evidence_file']).read_bytes())
        duplicate['evidence_sha256'] = source['evidence_sha256']
        with self.assertRaisesRegex(BenchmarkError, 'Reused'):
            compare(before, after, metrics=['native_fps'])

    def test_nested_bundled_settings_cannot_masquerade_as_one_key(self):
        before, after = self.arms()
        for value in before:
            value['identity']['frontend_id'] = 'project'
            value['identity']['settings']['values'] = {'Graphics': {'FrameSkip': 0, 'AutoFrameSkip': False}}
        for value in after:
            value['identity']['settings']['sha256'] = 'a' * 64
            value['identity']['settings']['values'] = {'Graphics': {'FrameSkip': 1, 'AutoFrameSkip': True}}
        with self.assertRaisesRegex(BenchmarkError, 'flat scalar'):
            compare(before, after, metrics=['native_fps'], comparison='setting')

    def test_version_label_change_does_not_establish_emulator_change(self):
        before, after = self.arms()
        for value in before:
            value['identity']['frontend_id'] = 'project'
        for value in after:
            value['identity']['emulator']['version'] = 'different label, identical bytes'
        with self.assertRaisesRegex(BenchmarkError, 'executable'):
            compare(before, after, metrics=['native_fps'], comparison='emulator')

    def test_native_speed_has_independent_intended_speed_and_fps(self):
        value = self.run_fixture(0)
        observation = copy.deepcopy(value['observations']['native_fps'])
        observation.update(value=97.5, unit='percent')
        value['observations']['native_speed_percent'] = observation
        self.assertEqual(validate_run(value)['observations']['native_fps']['value'], 59)
        self.assertEqual(value['identity']['intended_speed_percent'], 100)

    def test_record_binds_actual_evidence_and_keeps_absent_metrics_null(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / 'native.log'
            evidence.write_text('synthetic native observation fixture; not real gameplay\n')
            value = self.run_fixture(0)
            observation = value['observations']['native_fps']
            observation.update(evidence_file=str(evidence), evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())
            manifest = {k: v for k, v in value.items() if k not in ('schema', 'measurement_domain', 'observations')}
            result = record(manifest, value['observations'], root / 'report.json')
            self.assertEqual(result['summary']['native_fps'], 59)
            self.assertIsNone(result['summary']['native_speed_percent'])
            self.assertIsNone(result['summary']['input_latency_ms'])
            evidence.write_text('changed\n')
            with self.assertRaises(BenchmarkError):
                record(manifest, value['observations'], root / 'rejected.json')
            self.assertFalse((root / 'rejected.json').exists())

    def test_empty_observations_and_missing_identity_cannot_write_success(self):
        value = self.run_fixture(0)
        value['observations'] = {}
        with self.assertRaises(BenchmarkError):
            validate_run(value)

    def test_record_refuses_unrelated_resources_and_evidence_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.log'
            path.write_text('synthetic native observation\n')
            value = self.run_fixture(0)
            value['observations']['native_fps'].update(evidence_file=str(path),
                evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            manifest = {k: v for k, v in value.items() if k not in ('schema', 'measurement_domain', 'observations')}
            with self.assertRaises(BenchmarkError):
                record(manifest, value['observations'], path)
            with self.assertRaises(BenchmarkError):
                record(manifest, value['observations'], Path(directory) / 'report.json',
                       resources={'samples': [], 'summary': {'fps': None}})
            self.assertEqual(path.read_text(), 'synthetic native observation\n')
        value = self.run_fixture(0)
        del value['identity']['emulator']['binary_sha256']
        with self.assertRaises(BenchmarkError):
            validate_run(value)

    def test_existing_resource_sampler_accepts_game_identity_without_game_authority(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = capture(child.pid, Path(directory) / 'resources.json', port_id='fixture-id',
                                 scene='fixed-scene', seconds=.025, interval=.02,
                                 gameplay_identity=identity())
                self.assertEqual(report['measurement_domain'], 'gameplay-resources')
                self.assertEqual(report['gameplay_identity']['emulator']['version'], 'fixture')
                self.assertIsNone(report['summary']['fps'])
                self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
