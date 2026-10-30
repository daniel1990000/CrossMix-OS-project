# SPDX-License-Identifier: MIT
"""Host fixture checks of the stock-App collector; no target execution."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1] / 'device-preflight' / 'Apps' / 'SmartProCheck'


class DevicePilotAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.app = self.base / 'app'
        shutil.copytree(APP, self.app)
        self.root = self.base / 'root'
        for name in ('etc', 'proc/device-tree', 'proc/sys/kernel', 'usr/trimui/bin',
                     'usr/trimui/scene', 'bin', 'mnt/SDCARD/Roms/PSP', 'mnt/SDCARD/Emus'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        for name, data in {
            'etc/version': b'1.1.1\n', 'proc/device-tree/model': b'TrimUI Smart Pro\x00',
            'proc/sys/kernel/osrelease': b'4.9.191\n',
            'proc/mounts': b'/dev/root / squashfs ro 0 0\n/dev/mmc /mnt/SDCARD vfat rw 0 0\n',
            'usr/trimui/bin/runtrimui.sh': b'#!/bin/sh\n# owner-original\n',
            'usr/trimui/scene/fn.sh': b'#!/bin/sh\n# retained\n',
            'mnt/SDCARD/Roms/PSP/private-game.iso': b'private game content',
            'etc/wifi-password': b'do-not-collect-secret',
        }.items():
            (self.root / name).write_bytes(data)
        (self.root / 'bin/bash').symlink_to('/bin/busybox')

    def run_app(self):
        return subprocess.run(['/bin/sh', str(self.app / 'collect.sh'), '--fixture-root', str(self.root)],
                              capture_output=True, text=True, timeout=10)

    def snapshots(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}

    def test_collects_selected_archive_without_changing_source(self):
        before = self.snapshots()
        result = self.run_app()
        self.assertEqual(result.returncode, 0, result.stderr)
        session, = (self.app / 'reports').iterdir()
        report = (session / 'baseline.txt').read_text()
        self.assertIn('provenance=host-fixture-not-device-evidence', report)
        self.assertIn('firmware.etc_version=1.1.1', report)
        self.assertIn('hardware_qualified=false', report)
        self.assertNotIn('private-game', report)
        self.assertNotIn('do-not-collect-secret', report)
        self.assertEqual(before, self.snapshots())
        private = session / 'PRIVATE-internal-recovery'
        with tarfile.open(private / 'internal-files.tar') as archive:
            self.assertEqual(archive.extractfile('usr/trimui/bin/runtrimui.sh').read(),
                             (self.root / 'usr/trimui/bin/runtrimui.sh').read_bytes())
            self.assertTrue(archive.getmember('bin/bash').issym())
            self.assertFalse(any('Roms' in item.name or 'wifi' in item.name for item in archive))
        self.assertEqual((private / 'internal-files.tar.sha256').read_text().strip(),
                         hashlib.sha256((private / 'internal-files.tar').read_bytes()).hexdigest())
        self.assertTrue((session / 'COLLECTED.txt').exists())
        self.assertFalse((session / 'INCOMPLETE.txt').exists())

    def test_rerun_preserves_existing_session(self):
        self.assertEqual(self.run_app().returncode, 0)
        first, = (self.app / 'reports').iterdir()
        before = (first / 'baseline.txt').read_bytes()
        self.assertEqual(self.run_app().returncode, 0)
        self.assertEqual(len(list((self.app / 'reports').iterdir())), 2)
        self.assertEqual((first / 'baseline.txt').read_bytes(), before)

    def test_linked_reports_directory_refused(self):
        external = self.base / 'external'
        external.mkdir()
        (self.app / 'reports').symlink_to(external, target_is_directory=True)
        self.assertEqual(self.run_app().returncode, 2)
        self.assertEqual(list(external.iterdir()), [])

    def test_absence_recorded_without_claiming_backup(self):
        shutil.rmtree(self.root / 'usr/trimui')
        (self.root / 'bin/bash').unlink()
        result = self.run_app()
        self.assertEqual(result.returncode, 1)
        session, = (self.app / 'reports').iterdir()
        self.assertTrue((session / 'INCOMPLETE.txt').exists())
        self.assertFalse((session / 'COLLECTED.txt').exists())
        self.assertIn('absent usr/trimui/bin/runtrimui.sh',
                      (session / 'PRIVATE-internal-recovery/selection.txt').read_text())

    def test_fixture_cannot_claim_live_root(self):
        result = subprocess.run(['/bin/sh', str(self.app / 'collect.sh'), '--fixture-root', '/'],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.app / 'reports').exists())

    def test_app_entry_is_stock_schema_and_does_not_execute_fixture_files(self):
        config = json.loads((self.app / 'config.json').read_text())
        self.assertEqual(config['launch'], 'launch.sh')
        self.assertTrue((self.app / config['icon']).is_file())
        (self.root / 'usr/bin').mkdir(parents=True)
        tool = self.root / 'usr/bin/python3'
        tool.write_text('#!/bin/sh\ntouch ' + str(self.base / 'executed') + '\n')
        tool.chmod(0o755)
        self.assertEqual(self.run_app().returncode, 0)
        self.assertFalse((self.base / 'executed').exists())


if __name__ == '__main__':
    unittest.main()
