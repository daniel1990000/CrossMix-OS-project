# SPDX-License-Identifier: MIT
"""Timing math, real presentation calls, and isolated /proc observations."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.benchmark import _read_process, _process_tree, capture
from tools.frame_timing import FrameTimings, compare_metrics
from tools.ui_benchmark import capture_frames

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')


class FrameMeasurementTests(unittest.TestCase):
    def test_known_intervals_have_nearest_rank_p95_and_no_panel_claim(self):
        timing = FrameTimings()
        for now in (0, 10_000_000, 30_000_000, 60_000_000):
            timing.record(now, render_ns=1000000, present_ns=2000000)
        report = timing.report()
        self.assertEqual(report['interval']['median_ms'], 20)
        self.assertEqual(report['interval']['p95_ms'], 30)
        self.assertEqual(report['render_call']['median_ms'], 1)
        self.assertIsNone(report['panel_fps'])
        self.assertIsNone(report['input_latency_ms'])

    def test_non_monotonic_and_invalid_timestamps_are_rejected(self):
        timing = FrameTimings()
        timing.record(5)
        for value in (5, 4, float('nan'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                timing.record(value)

    def test_storage_is_bounded_and_overflow_is_visible(self):
        timing = FrameTimings(2)
        for value in range(20): timing.record(value)
        self.assertEqual(len(timing.samples), 2)
        self.assertEqual(timing.report()['dropped_samples'], 18)

    def test_only_real_presentation_owner_boundaries_are_supported(self):
        with self.assertRaises(ValueError):
            FrameTimings(boundary='embedded-renderer-noop')
        self.assertEqual(FrameTimings(boundary='owning-PyUI-Display.present-return').report()['interval']['count'], 0)

    def test_explicit_regression_budget_preserves_unavailable_metrics(self):
        rules = {'startup': {'ratio': 1.1, 'noise_ms': 5}, 'latency': {'ratio': 1.1, 'noise_ms': 0}}
        report = compare_metrics({'startup': 20}, {'startup': 24}, rules)
        self.assertTrue(report['metrics']['startup']['passed'])
        self.assertIsNone(report['metrics']['latency']['passed'])
        self.assertFalse(report['passed'])
        self.assertFalse(compare_metrics({'x': 10}, {'x': 20}, {'x': {'ratio': 1.1, 'noise_ms': 0}})['passed'])

    def test_invalid_comparison_budget_is_rejected(self):
        for rule in ({'ratio': .5, 'noise_ms': 0}, {'ratio': 1, 'noise_ms': float('nan')}, {}):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                compare_metrics({}, {}, {'x': rule})

    def test_actual_sdl_scene_records_after_present_and_excludes_warmup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'frames.json'
            report = capture_frames(path, frames=4, warmup=2)
            self.assertEqual(len(report['frame_timing']['samples']), 4)
            self.assertEqual(report['frame_timing']['interval']['count'], 3)
            self.assertGreater(report['frame_timing']['render_call']['median_ms'], 0)
            self.assertFalse(json.loads(path.read_text())['hardware_qualified'])

    def test_proc_pss_missing_and_malformed_remains_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / '1'
            directory.mkdir()
            fields = ['S'] + ['0'] * 21
            fields[11], fields[12], fields[19] = '4', '3', '123'
            (directory / 'stat').write_text('1 (process with ) name) ' + ' '.join(fields))
            (directory / 'statm').write_text('10 3')
            self.assertIsNone(_read_process(root, 1)['pss_bytes'])
            (directory / 'smaps_rollup').write_text('Pss: 17 kB\n')
            self.assertEqual(_read_process(root, 1)['pss_bytes'], 17 * 1024)
            (directory / 'smaps_rollup').write_text('Pss: invalid kB\n')
            self.assertIsNone(_read_process(root, 1)['pss_bytes'])
            records, truncated = _process_tree(root, _read_process(root, 1))
            self.assertFalse(truncated)
            self.assertEqual(len(records), 1)

    def test_tree_cpu_retains_departed_work_and_separates_reused_pid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def write(pid, ticks, start, children=()):
                directory = root / str(pid)
                (directory / 'task' / str(pid)).mkdir(parents=True, exist_ok=True)
                fields = ['S'] + ['0'] * 21
                fields[11], fields[19] = str(ticks), str(start)
                (directory / 'stat').write_text(f'{pid} (fixture) ' + ' '.join(fields))
                (directory / 'statm').write_text('10 3')
                (directory / 'task' / str(pid) / 'children').write_text(' '.join(map(str, children)))
            write(1, 100, 10, [2])
            write(2, 10, 20)
            clock = [0]
            step = [0]
            def monotonic():
                clock[0] += .01
                return clock[0]
            def advance(_):
                step[0] += 1
                if step[0] == 1: write(2, 15, 20)
                elif step[0] == 2: write(2, 99, 30)  # Same PID, a new process identity.
                else: write(2, 102, 30)
            with mock.patch('tools.benchmark.time.monotonic', monotonic), mock.patch('tools.benchmark.time.sleep', advance):
                report = capture(1, root / 'report.json', port_id='sonic_mania', scene='special-stage',
                                 seconds=.09, interval=.02, proc_root=root)
            ticks = os.sysconf('SC_CLK_TCK')
            self.assertAlmostEqual(report['summary']['observed_tree_cpu_seconds_delta'], 8 / ticks)
            self.assertEqual(report['summary']['root_cpu_seconds_delta'], 0)
            self.assertIsNone(report['summary']['peak_sampled_tree_pss_bytes'])

    def test_core_frontend_scenes_use_same_readonly_sampler(self):
        import subprocess
        import sys
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])
        try:
            with tempfile.TemporaryDirectory() as temporary:
                report = capture(child.pid, Path(temporary) / 'core.json', port_id='frontend-classic',
                    scene='settings-navigation', seconds=.025, interval=.02,
                    profiles_file=Path(__file__).resolve().parents[1] / 'profiles/measurement-scenes.json')
                self.assertEqual(report['profile_id'], 'frontend-classic')
                self.assertIsNone(report['summary']['input_latency_ms'])
                self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_process_tree_bounds_probes_before_reading_child_pss(self):
        first = {'pid': 1, 'children': list(range(2, 1002))}
        def child(_, pid):
            return {'pid': pid, 'children': []}
        with mock.patch('tools.benchmark._read_process', side_effect=child) as probe:
            records, truncated = _process_tree('/unused-fixture', first)
        self.assertEqual(len(records), 256)
        self.assertEqual(probe.call_count, 255)
        self.assertTrue(truncated)
