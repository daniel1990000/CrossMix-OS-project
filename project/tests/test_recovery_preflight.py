# SPDX-License-Identifier: MIT
"""Offline backup bytes and restored files stay separate from physical acceptance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import recovery_preflight as preflight


class RecoveryPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="recovery-preflight-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source, self.backup, self.restored = (self.base / name for name in ("source", "backup", "restored"))
        self.source.mkdir()
        (self.source / "Saves/日本語").mkdir(parents=True)
        (self.source / "Saves/日本語/fixture.sav").write_bytes(b"owner fixture save bytes")
        (self.source / "empty-directory").mkdir()
        self.copy_trees()
        self.manifest = self.base / "backup-manifest.json"

    def copy_trees(self):
        for tree in (self.backup, self.restored):
            if tree.exists():
                shutil.rmtree(tree)
            shutil.copytree(self.source, tree, symlinks=True)

    def record(self, scope="saves"):
        report = preflight.record(self.source, self.backup, scope)
        preflight.write_report(self.manifest, report, (self.source, self.backup))
        return report

    def test_actual_separate_backup_and_restored_bytes_match_without_writes(self):
        path = self.source / "Saves/日本語/fixture.sav"
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        manifest = self.record()
        self.assertTrue(manifest["source_backup_match"])
        observed = preflight.verify(self.manifest, self.backup, self.restored)
        self.assertTrue(observed["all_trees_match"])
        self.assertFalse(observed["physical_restore_tested"])
        self.assertFalse(observed["hardware_qualified"])
        self.assertFalse(observed["automatic_activation"])
        self.assertFalse(observed["independent_media_verified"])
        self.assertNotIn(before[0].decode(), json.dumps(manifest))
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)
        self.assertEqual(observed["manifest_sha256"], hashlib.sha256(self.manifest.read_bytes()).hexdigest())

    def test_newer_unlisted_saves_and_missing_or_changed_bytes_are_reported_never_restored(self):
        self.record()
        old = self.restored / "Saves/日本語/fixture.sav"
        old.write_bytes(b"newer owner progress")
        extra = self.restored / "Saves/newer-slot.sav"
        extra.write_bytes(b"another slot")
        (self.restored / "empty-directory").rmdir()
        report = preflight.verify(self.manifest, self.backup, self.restored)
        self.assertFalse(report["all_trees_match"])
        self.assertEqual(report["trees"]["restored_tree"]["differences"], [
            {"path": "Saves/newer-slot.sav", "status": "unlisted"},
            {"path": "Saves/日本語/fixture.sav", "status": "changed"},
            {"path": "empty-directory", "status": "missing"},
        ])
        self.assertEqual(old.read_bytes(), b"newer owner progress")
        self.assertEqual(extra.read_bytes(), b"another slot")

    def test_corrupted_retained_backup_fails_even_when_restored_tree_matches(self):
        self.record()
        (self.backup / "Saves/日本語/fixture.sav").write_bytes(b"corrupt")
        report = preflight.verify(self.manifest, self.backup, self.restored)
        self.assertFalse(report["trees"]["retained_backup"]["matches_recorded_source"])
        self.assertTrue(report["trees"]["restored_tree"]["matches_recorded_source"])
        self.assertFalse(report["all_trees_match"])

    def test_different_initial_backup_cannot_be_reused_as_successful_manifest(self):
        (self.backup / "Saves/日本語/fixture.sav").unlink()
        report = self.record()
        self.assertFalse(report["source_backup_match"])
        with self.assertRaises(ValueError):
            preflight.verify(self.manifest, self.backup)

    def test_internal_ownership_modes_and_symlink_text_are_retained_without_following(self):
        internal = self.source / "bin"
        internal.mkdir()
        (internal / "bash").write_bytes(b"original shell fixture")
        (internal / "bash").chmod(0o755)
        (internal / "sh").symlink_to("/bin/bash")
        self.copy_trees()
        report = self.record("internal-files")
        entry = next(row for row in report["source_tree"]["entries"] if row["path"] == "bin/bash")
        self.assertEqual(entry["mode"], 0o755)
        self.assertEqual(entry["uid"], os.getuid())
        self.assertEqual(entry["gid"], os.getgid())
        (self.restored / "bin/bash").chmod(0o644)
        (self.restored / "bin/sh").unlink()
        (self.restored / "bin/sh").symlink_to("/etc/does-not-get-read")
        observed = preflight.verify(self.manifest, self.backup, self.restored)
        self.assertEqual(observed["trees"]["restored_tree"]["differences"], [
            {"path": "bin/bash", "status": "changed"}, {"path": "bin/sh", "status": "changed"}])

    def test_card_files_do_not_claim_posix_ownership_on_fat_copies(self):
        self.record("card-files")
        (self.restored / "Saves/日本語/fixture.sav").chmod(0o400)
        self.assertTrue(preflight.verify(self.manifest, self.backup, self.restored)["all_trees_match"])

    def test_internal_selected_root_metadata_is_compared(self):
        original = self.record("internal-files")
        self.assertEqual(original["source_tree"]["root_metadata"], {
            "mode": stat.S_IMODE(self.source.stat().st_mode),
            "uid": self.source.stat().st_uid, "gid": self.source.stat().st_gid})
        self.restored.chmod(0o700 if stat.S_IMODE(self.restored.stat().st_mode) != 0o700 else 0o755)
        report = preflight.verify(self.manifest, self.backup, self.restored)
        self.assertFalse(report["all_trees_match"])
        self.assertEqual(report["trees"]["restored_tree"]["differences"], [
            {"path": ".", "status": "metadata_changed"}])

    def test_source_moved_over_backup_between_scans_is_rejected(self):
        actual_scan = preflight.scan_tree

        def swap_after_source(root, scope):
            result = actual_scan(root, scope)
            if root == self.source:
                shutil.rmtree(self.backup)
                self.source.rename(self.backup)
            return result

        with mock.patch.object(preflight, "scan_tree", side_effect=swap_after_source):
            with self.assertRaises((ValueError, OSError)):
                preflight.record(self.source, self.backup, "saves")

    def test_backup_moved_over_restored_between_readback_scans_is_rejected(self):
        self.record()
        actual_scan = preflight.scan_tree

        def swap_after_backup(root, scope):
            result = actual_scan(root, scope)
            if root == self.backup:
                shutil.rmtree(self.restored)
                self.backup.rename(self.restored)
            return result

        with mock.patch.object(preflight, "scan_tree", side_effect=swap_after_backup):
            with self.assertRaises((ValueError, OSError)):
                preflight.verify(self.manifest, self.backup, self.restored)

    def test_root_path_change_after_last_scan_is_rejected(self):
        actual_scan = preflight.scan_tree

        def move_after_backup(root, scope):
            result = actual_scan(root, scope)
            if root == self.backup:
                self.source.rename(self.base / "moved-source")
            return result

        with mock.patch.object(preflight, "scan_tree", side_effect=move_after_backup):
            with self.assertRaises((ValueError, OSError)):
                preflight.record(self.source, self.backup, "saves")

    def test_roots_must_be_real_separate_nonoverlapping_directories(self):
        self.record()
        with self.assertRaises(ValueError):
            preflight.record(self.source, self.source, "saves")
        child = self.source / "nested-backup"
        child.mkdir()
        with self.assertRaises(ValueError):
            preflight.record(self.source, child, "saves")
        alias = self.base / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(OSError):
            preflight.record(alias, self.backup, "saves")
        with self.assertRaises(ValueError):
            preflight.verify(self.manifest, self.backup, self.backup)

    def test_special_files_and_multiply_linked_files_are_rejected_without_blocking(self):
        os.mkfifo(self.source / "fifo")
        with self.assertRaises(ValueError):
            preflight.scan_tree(self.source, "saves")
        (self.source / "fifo").unlink()
        os.link(self.source / "Saves/日本語/fixture.sav", self.source / "hardlink")
        with self.assertRaises(ValueError):
            preflight.scan_tree(self.source, "saves")

    def test_budgets_reject_empty_deep_large_and_too_many_entries(self):
        empty = self.base / "empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            preflight.scan_tree(empty, "saves")
        with self.assertRaises(ValueError):
            preflight.scan_tree(self.source, "saves", max_entries=1)
        with self.assertRaises(ValueError):
            preflight.scan_tree(self.source, "saves", max_bytes=1)
        with mock.patch.object(preflight, "MAX_DEPTH", 1):
            with self.assertRaises(ValueError):
                preflight.scan_tree(self.source, "saves")

    def test_file_mutation_during_read_is_rejected(self):
        target = self.source / "Saves/日本語/fixture.sav"
        real_stat = preflight.os.fstat
        mutated = False

        def mutate_after_read(fd):
            nonlocal mutated
            info = real_stat(fd)
            if stat.S_ISREG(info.st_mode) and not mutated:
                mutated = True
                target.write_bytes(b"different concurrent save bytes")
            return info

        with mock.patch.object(preflight.os, "fstat", side_effect=mutate_after_read):
            with self.assertRaises(ValueError):
                preflight.scan_tree(self.source, "saves")

    def test_duplicate_keys_traversal_and_modified_manifest_are_rejected(self):
        original = self.record()
        self.manifest.write_text('{"schema": 1, "schema": 1}')
        with self.assertRaises(ValueError):
            preflight.load_manifest(self.manifest)
        original["source_tree"]["entries"][0]["path"] = "../outside"
        self.manifest.write_bytes(preflight.encoded(original))
        with self.assertRaises(ValueError):
            preflight.load_manifest(self.manifest)
        original["source_tree"]["entries"][0]["path"] = "Saves"
        original["source_tree"]["entries"][0]["type"] = "file"
        self.manifest.write_bytes(preflight.encoded(original))
        with self.assertRaises(ValueError):
            preflight.load_manifest(self.manifest)

    def test_manifest_and_reports_are_regular_private_exclusive_and_external(self):
        report = self.record()
        self.assertEqual(stat.S_IMODE(self.manifest.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            preflight.write_report(self.manifest, report, (self.source, self.backup))
        with self.assertRaises(ValueError):
            preflight.write_report(self.source / "report.json", report, (self.source, self.backup))
        self.manifest.unlink()
        self.manifest.symlink_to(self.base / "would-escape")
        with self.assertRaises(OSError):
            preflight.load_manifest(self.manifest)
        self.assertFalse((self.base / "would-escape").exists())

    def test_file_fsync_failure_leaves_no_success_receipt_or_staging_file(self):
        report = preflight.record(self.source, self.backup, "saves")
        with mock.patch.object(preflight.os, "fsync", side_effect=OSError("injected file fsync failure")):
            with self.assertRaises(OSError):
                preflight.write_report(self.manifest, report, (self.source, self.backup))
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.base.glob(".recovery-preflight-*")), [])

    def test_directory_fsync_failure_removes_owned_published_receipt(self):
        report = preflight.record(self.source, self.backup, "saves")
        actual_fsync = preflight.os.fsync

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("injected directory fsync failure")
            return actual_fsync(fd)

        with mock.patch.object(preflight.os, "fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                preflight.write_report(self.manifest, report, (self.source, self.backup))
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.base.glob(".recovery-preflight-*")), [])

    def test_publication_failure_preserves_an_unrelated_existing_output(self):
        report = preflight.record(self.source, self.backup, "saves")
        self.manifest.write_bytes(b"older independent receipt")
        with self.assertRaises(FileExistsError):
            preflight.write_report(self.manifest, report, (self.source, self.backup))
        self.assertEqual(self.manifest.read_bytes(), b"older independent receipt")
        self.assertEqual(list(self.base.glob(".recovery-preflight-*")), [])

    def test_cli_mismatch_retains_private_report_and_has_nonzero_status(self):
        (self.backup / "Saves/日本語/fixture.sav").write_bytes(b"wrong")
        command = [sys.executable, str(PROJECT / "tools/recovery_preflight.py"), "record",
                   "--source", str(self.source), "--backup", str(self.backup), "--scope", "saves",
                   "--output", str(self.manifest)]
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertFalse(json.loads(self.manifest.read_text())["source_backup_match"])
        self.assertEqual(stat.S_IMODE(self.manifest.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
