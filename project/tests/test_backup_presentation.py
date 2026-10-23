# SPDX-License-Identifier: MIT
"""Fresh backup bytes and fixed routes, without physical recovery claims."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from psp_shell.app import AppError, Dispatcher
from psp_shell.demo import DemoBackend
from psp_shell.recovery import BackupStatusAdapter
from psp_shell.settings import SettingsStore
from tools.recovery_payload import backup


class BackupPresentationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / "source"
        source.mkdir(mode=0o700)
        (source / "memory-card.sav").write_bytes(b"fixture-save")
        self.payload = self.root / "payload"
        backup(source, self.payload, "saves")

    def dispatcher(self, adapter=None):
        return Dispatcher(DemoBackend(), SettingsStore(self.root / "settings"),
                          self.root / "reports", backup_adapter=adapter)

    def test_fresh_readback_is_scoped_and_does_not_claim_physical_restore(self):
        status = self.dispatcher(BackupStatusAdapter({"saves": self.payload})).dispatch("backup.status")
        self.assertEqual(status["status"], "verified")
        self.assertEqual(status["scope"], ["saves"])
        self.assertIsNotNone(status["verified_at_utc"])
        self.assertFalse(status["physical_restore_tested"])
        self.assertFalse(status["independent_media_verified"])
        self.assertNotIn(str(self.root), str(status))

    def test_receipt_does_not_hide_later_changed_payload_bytes(self):
        adapter = BackupStatusAdapter({"saves": self.payload})
        self.assertEqual(adapter.status()["status"], "verified")
        (self.payload / "data/memory-card.sav").write_bytes(b"tampered-save")
        status = adapter.status()
        self.assertEqual(status["status"], "unavailable")
        self.assertIsNone(status["verified_at_utc"])

    def test_scope_mismatch_missing_scope_and_partial_status_are_visible(self):
        adapter = BackupStatusAdapter({"saves": self.payload, "card-files": self.root / "absent"})
        self.assertEqual(adapter.status()["status"], "partial")
        self.assertEqual(adapter.status()["scope"], ["saves"])
        wrong = BackupStatusAdapter({"card-files": self.payload}).status()
        self.assertEqual(wrong["status"], "unavailable")

    def test_incomplete_backup_and_mutated_receipts_are_unavailable(self):
        (self.payload / "COMPLETE.json").write_text('{"status":"verified"}')
        self.assertEqual(BackupStatusAdapter({"saves": self.payload}).status()["status"], "unavailable")

    def test_ui_cannot_select_paths_or_restore_live_data(self):
        dispatcher = self.dispatcher()
        self.assertEqual(dispatcher.dispatch("backup.status")["status"], "unavailable")
        with self.assertRaises(AppError):
            dispatcher.dispatch("backup.status", {"payload": str(self.payload)})
        with self.assertRaises(AppError):
            dispatcher.dispatch("backup.action", {"action_id": "restore"})
        guide = dispatcher.dispatch("backup.action", {"action_id": "recovery_guide"})
        self.assertIn("NEW expendable directory", guide["message"])
        report = dispatcher.dispatch("backup.action", {"action_id": "support_export"})
        self.assertTrue(Path(report["path"]).is_file())
        self.assertEqual(dispatcher.dispatch("backup.action", {"action_id": "recheck"})["status"], "unavailable")

    def test_installed_verifier_is_not_shadowed_by_an_unrelated_tools_package(self):
        from tools.build_payload import build_payload
        installed = self.root / "installed"
        build_payload(Path(__file__).resolve().parents[1], installed)
        site = self.root / "unrelated-site"
        (site / "tools").mkdir(parents=True)
        (site / "tools/__init__.py").write_text("raise RuntimeError('unrelated tools must not load')\n")
        environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(installed / "app"), str(site))))
        probe = subprocess.run([sys.executable, "-c",
            "import sys; from psp_shell.recovery import BackupStatusAdapter; "
            "assert BackupStatusAdapter({'saves':sys.argv[1]}).status()['status']=='verified'", str(self.payload)],
            cwd=self.root, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr)


if __name__ == "__main__":
    unittest.main()
