"""Read-only sampler tests attach only to this test's own child process."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.benchmark import BenchmarkError, capture


class ProcessBenchmark(unittest.TestCase):
    def test_capture_has_real_samples_and_no_invented_frame_rate(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])
        try:
            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / 'report.json'
                report = capture(child.pid, output, port_id='sonic_mania',
                                 scene='special-stage', seconds=0.05, interval=0.02,
                                 metadata={'firmware': 'host test fixture'})
                self.assertGreaterEqual(len(report['samples']), 2)
                self.assertGreater(report['elapsed_seconds'], 0)
                self.assertGreater(report['summary']['peak_sampled_rss_bytes'], 0)
                self.assertIsNone(report['summary']['fps'])
                self.assertIsNone(report['summary']['frame_time_p95_ms'])
                self.assertEqual(report['evidence_class'], 'host-or-unspecified')
                self.assertEqual(json.loads(output.read_text())['pid'], child.pid)
                self.assertIsNone(child.poll(), 'The sampler must never stop a running game')
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_unknown_scene_and_experimental_profile_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'report.json'
            for profile, scene in [('sonic_mania', 'made-up-measurement'), ('gtasa', 'city')]:
                with self.assertRaises(BenchmarkError):
                    capture(1, output, port_id=profile, scene=scene, seconds=0.02)
            self.assertFalse(output.exists())

    def test_absent_process_has_no_success_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(BenchmarkError):
                capture(99999999, Path(temporary) / 'report.json', port_id='celeste',
                        scene='forsaken-city-fixed-room-route', seconds=0.02)


if __name__ == '__main__':
    unittest.main()
