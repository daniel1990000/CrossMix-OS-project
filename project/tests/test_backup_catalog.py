# SPDX-License-Identifier: MIT
"""Named offline backup history preserves payloads and truthful check state."""
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from psp_shell.backup_catalog import BackupCatalog, BackupCatalogError
from psp_shell.recovery import BackupHistoryAdapter
from psp_shell.settings import SettingsError
from tools import recovery_payload, recovery_preflight


class BackupCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="backup-catalog-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "offline-source"
        self.source.mkdir(mode=0o700)
        (self.source / "memory-card.sav").write_bytes(b"existing owner progress\0" * 30)
        self.payload = self.root / "payload"
        recovery_payload.backup(self.source, self.payload, "saves")
        self.path = self.root / "ui-state" / "backups.json"
        self.catalog = BackupCatalog(self.path, forbidden_roots=(self.source,))

    def register(self):
        return self.catalog.register(self.payload, "Before changing settings", note="Offline fixture")

    def adapter(self):
        adapter = BackupHistoryAdapter(self.path, forbidden_roots=(self.source,))
        self.addCleanup(adapter.close)
        return adapter

    def finish(self, adapter, job):
        deadline = time.monotonic() + 10
        while job["state"] == "running" and time.monotonic() < deadline:
            adapter._thread.join(0.02)
            job = adapter.job(job["job_id"])
        self.assertNotEqual(job["state"], "running", "verification did not finish")
        return job

    def hashes(self, root):
        return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob("*") if path.is_file()}

    def test_browsing_missing_catalog_creates_nothing(self):
        before = set(self.root.iterdir())
        adapter = self.adapter()
        self.assertEqual(adapter.history()["entries"], [])
        self.assertFalse(adapter.history()["available"])
        self.assertTrue(adapter.status()["history_available"])
        self.assertEqual(set(self.root.iterdir()), before)

    def test_register_restart_rename_and_remove_preserve_payload_and_source(self):
        source, payload = self.hashes(self.source), self.hashes(self.payload)
        registered = self.register()
        identifier = registered["entry_id"]
        self.assertEqual(len(identifier), 32)
        restarted = BackupCatalog(self.path)
        row, generation = restarted.entry(identifier)
        self.assertEqual(row["scope"], "saves")
        self.assertEqual(row["last_check"]["status"], "verified")
        restarted.rename(identifier, "October backup", generation, "Keep for review")
        detail = self.adapter().detail(identifier)
        self.assertEqual(detail["label"], "October backup")
        self.assertEqual(detail["status"], "previously_verified")
        self.assertNotIn(str(self.root), str(detail))
        removed = restarted.remove(identifier, detail["generation"])
        self.assertFalse(removed["payload_deleted"])
        self.assertEqual(restarted.read()["entries"], [])
        self.assertEqual(self.hashes(self.source), source)
        self.assertEqual(self.hashes(self.payload), payload)

    def test_duplicate_registration_keeps_id_label_and_generation(self):
        first = self.register()
        second = self.catalog.register(self.payload, "Do not silently rename")
        self.assertEqual(first["entry_id"], second["entry_id"])
        self.assertEqual(first["generation"], second["generation"])
        self.assertTrue(second["unchanged"])
        self.assertEqual(self.catalog.entry(first["entry_id"])[0]["label"], "Before changing settings")

    def test_new_payload_at_same_path_cannot_rebind_existing_entry(self):
        first = self.register()
        self.payload.rename(self.root / "old-payload")
        (self.source / "memory-card.sav").write_bytes(b"newer progress")
        recovery_payload.backup(self.source, self.payload, "saves")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(BackupCatalogError, "different payload"):
            self.catalog.register(self.payload, "Replacement")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.catalog.read()["entries"][0]["entry_id"], first["entry_id"])

    def test_alias_copy_dedupes_without_silently_changing_location(self):
        import shutil
        first = self.register()
        duplicate = self.root / "another-copy"
        shutil.copytree(self.payload, duplicate)
        result = self.catalog.register(duplicate, "Copied payload")
        self.assertEqual(result["entry_id"], first["entry_id"])
        self.assertFalse(result["same_location"])
        self.assertEqual(self.catalog.entry(first["entry_id"])[0]["payload_path"], str(self.payload))

    def test_catalog_and_journal_never_enter_card_or_payload(self):
        for root in (self.source, self.payload, self.payload / "data"):
            with self.subTest(root=root), self.assertRaises(BackupCatalogError):
                BackupCatalog(root / "catalog.json", forbidden_roots=(self.source,))
            self.assertFalse((root / "catalog.json").exists())
            self.assertFalse((root / ".catalog.json.lock").exists())

    def test_symlink_catalog_parent_and_payload_are_rejected(self):
        linked = self.root / "linked"
        linked.symlink_to(self.payload, target_is_directory=True)
        with self.assertRaises(BackupCatalogError):
            self.catalog.register(linked, "No linked payload")
        with self.assertRaises(BackupCatalogError):
            BackupCatalog(linked / "catalog.json")

    def test_malformed_duplicate_fields_and_oversize_catalog_are_preserved(self):
        self.path.parent.mkdir()
        for raw in (b'{"schema":1,"schema":1}', b'not json', b' ' * (1024**2 + 1)):
            self.path.write_bytes(raw)
            with self.subTest(size=len(raw)), self.assertRaises((BackupCatalogError, SettingsError)):
                self.catalog.read()
            self.assertEqual(self.path.read_bytes(), raw)

    def test_labels_normalize_and_bounds_generation_are_enforced(self):
        first = self.catalog.register(self.payload, "Cafe\u0301")
        self.assertEqual(self.catalog.entry(first["entry_id"])[0]["label"], "Café")
        for bad in ("", "x" * 81, "line\nbreak", "bad\x00label"):
            with self.subTest(label=repr(bad)), self.assertRaises(BackupCatalogError):
                self.catalog.rename(first["entry_id"], bad, first["generation"])
        self.catalog.rename(first["entry_id"], "Newest label", first["generation"])
        with self.assertRaises(BackupCatalogError):
            self.catalog.remove(first["entry_id"], first["generation"])
        self.assertEqual(self.catalog.entry(first["entry_id"])[0]["label"], "Newest label")

    def test_wrong_schema_and_excess_entry_count_cannot_be_read(self):
        self.register()
        good = json.loads(self.path.read_text())
        for changed in (dict(good, schema=True), dict(good, entries=[good["entries"][0]] * 1001)):
            self.path.write_text(json.dumps(changed))
            with self.assertRaises(BackupCatalogError):
                self.catalog.read()

    def test_malformed_entry_field_types_raise_bounded_catalog_errors(self):
        self.register()
        good = json.loads(self.path.read_text())
        fields = ("entry_id", "label", "note", "scope", "payload_path", "registered_at_utc",
                  "captured_at_utc", "digests", "bytes", "last_verified_at_utc")
        for field in fields:
            for invalid in ([], {}, None, True):
                # None explicitly means there has never been a successful check.
                if field == "last_verified_at_utc" and invalid is None:
                    continue
                changed = copy.deepcopy(good)
                changed["entries"][0][field] = invalid
                self.path.write_text(json.dumps(changed))
                with self.subTest(field=field, value=invalid), self.assertRaises(BackupCatalogError):
                    self.catalog.read()
        for field in ("status", "reason", "checked_at_utc"):
            changed = copy.deepcopy(good)
            changed["entries"][0]["last_check"][field] = []
            self.path.write_text(json.dumps(changed))
            with self.subTest(check_field=field), self.assertRaises(BackupCatalogError):
                self.catalog.read()

    def test_interrupted_catalog_edit_requires_explicit_recovery_and_restores_prior_bytes(self):
        first = self.register()
        before = self.path.read_bytes()
        def crash(point, index):
            if point == "after_replace":
                raise KeyboardInterrupt()
        self.catalog.fault_hook = crash
        with self.assertRaises(KeyboardInterrupt):
            self.catalog.rename(first["entry_id"], "Interrupted change", first["generation"])
        with self.assertRaisesRegex(BackupCatalogError, "interrupted"):
            BackupCatalog(self.path).read()
        BackupCatalog(self.path).recover()
        self.assertEqual(self.path.read_bytes(), before)

    def test_storage_failure_preserves_old_catalog(self):
        first = self.register()
        before = self.path.read_bytes()
        with patch("psp_shell.settings.tempfile.mkstemp", side_effect=OSError(errno.ENOSPC, "full")):
            with self.assertRaises(SettingsError):
                self.catalog.rename(first["entry_id"], "Cannot persist", first["generation"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_existing_and_successful_restore_only_use_new_directory(self):
        first = self.register()
        before = self.hashes(self.payload)
        destination = self.root / "rehearsal"
        result = self.catalog.restore(first["entry_id"], destination)
        self.assertFalse(result["physical_restore_tested"])
        self.assertEqual((destination / "data/memory-card.sav").read_bytes(), (self.source / "memory-card.sav").read_bytes())
        with self.assertRaises(FileExistsError):
            self.catalog.restore(first["entry_id"], destination)
        self.assertEqual(self.hashes(self.payload), before)

    def test_restore_refuses_inspected_card_and_other_registered_payload(self):
        first = self.register()
        second = self.root / "second-payload"
        recovery_payload.backup(self.source, second, "card-files")
        self.catalog.register(second, "Whole card")
        before = self.hashes(self.root)
        for output in (self.source / "rehearsal", second / "rehearsal", second / "data" / "rehearsal"):
            with self.subTest(output=output), self.assertRaises(BackupCatalogError):
                self.catalog.restore(first["entry_id"], output)
            self.assertFalse(output.exists())
        self.assertEqual(self.hashes(self.root), before)

    def test_fast_history_does_not_rehash_and_job_records_fresh_readback(self):
        first = self.register()
        adapter = self.adapter()
        with patch.object(recovery_payload, "inspect_payload", side_effect=AssertionError("history must not hash")):
            self.assertEqual(adapter.detail(first["entry_id"])["status"], "previously_verified")
            self.assertEqual(adapter.status()["status"], "history")
        job = self.finish(adapter, adapter.verify(first["entry_id"], first["generation"]))
        self.assertEqual(job["state"], "verified")
        self.assertGreater(job["bytes_checked"], 0)
        self.assertEqual(job["files_checked"], 1)
        self.assertEqual(adapter.detail(first["entry_id"])["last_check"]["checked_at_utc"], job["checked_at_utc"])
        self.assertEqual(adapter.detail(first["entry_id"])["status"], "previously_verified")

    def test_tamper_missing_and_symlink_replacement_remain_visible_unavailable(self):
        first = self.register()
        adapter = self.adapter()
        (self.payload / "data/memory-card.sav").write_bytes(b"changed")
        job = self.finish(adapter, adapter.verify(first["entry_id"], first["generation"]))
        self.assertEqual(job["state"], "unavailable")
        self.assertIsNotNone(adapter.detail(first["entry_id"])["last_verified_at_utc"])
        moved = self.root / "moved-payload"
        self.payload.rename(moved)
        self.payload.symlink_to(moved, target_is_directory=True)
        self.assertEqual(len(adapter.history()["entries"]), 1)
        job = self.finish(adapter, adapter.verify(first["entry_id"], adapter.history()["generation"]))
        self.assertEqual(job["state"], "unavailable")
        self.payload.unlink()
        job = self.finish(adapter, adapter.verify(first["entry_id"], adapter.history()["generation"]))
        self.assertEqual(job["state"], "unavailable")

    def test_changed_manifest_identity_fails_even_if_replacement_payload_is_valid(self):
        first = self.register()
        self.payload.rename(self.root / "original-payload")
        recovery_payload.backup(self.source, self.payload, "card-files")
        adapter = self.adapter()
        job = self.finish(adapter, adapter.verify(first["entry_id"], first["generation"]))
        self.assertEqual(job["state"], "unavailable")
        self.assertEqual(adapter.detail(first["entry_id"])["scope"], "saves")

    def test_cancel_and_busy_queue_do_not_publish_a_new_check(self):
        first = self.register()
        adapter = self.adapter()
        before = self.path.read_bytes()
        started, proceed = threading.Event(), threading.Event()
        inspect = recovery_payload.inspect_payload
        def held(*args, **kwargs):
            started.set()
            self.assertTrue(proceed.wait(5))
            return inspect(*args, **kwargs)
        with patch.object(recovery_payload, "inspect_payload", side_effect=held):
            job = adapter.verify(first["entry_id"], first["generation"])
            self.assertTrue(started.wait(5))
            with self.assertRaisesRegex(BackupCatalogError, "still running"):
                adapter.verify(first["entry_id"], first["generation"])
            self.assertTrue(adapter.cancel(job["job_id"])["cancel_requested"])
            proceed.set()
            job = self.finish(adapter, job)
        self.assertEqual(job["state"], "cancelled")
        self.assertEqual(self.path.read_bytes(), before)

    def test_catalog_edit_during_verify_supersedes_late_completion(self):
        first = self.register()
        adapter = self.adapter()
        started, proceed = threading.Event(), threading.Event()
        inspect = recovery_payload.inspect_payload
        def held(*args, **kwargs):
            started.set()
            self.assertTrue(proceed.wait(5))
            return inspect(*args, **kwargs)
        with patch.object(recovery_payload, "inspect_payload", side_effect=held):
            job = adapter.verify(first["entry_id"], first["generation"])
            self.assertTrue(started.wait(5))
            self.catalog.rename(first["entry_id"], "New label", first["generation"])
            after = self.path.read_bytes()
            proceed.set()
            job = self.finish(adapter, job)
        self.assertEqual(job["state"], "superseded")
        self.assertEqual(self.path.read_bytes(), after)

    def test_unexpected_verifier_failure_never_leaves_running_or_successful_job(self):
        first = self.register()
        before = self.path.read_bytes()
        adapter = self.adapter()
        with patch.object(recovery_payload, "inspect_payload", side_effect=RuntimeError("fixture failure")):
            job = self.finish(adapter, adapter.verify(first["entry_id"], first["generation"]))
        self.assertEqual(job["state"], "unavailable")
        self.assertEqual(self.path.read_bytes(), before)

    def test_deeply_nested_payload_records_finish_as_unavailable(self):
        first = self.register()
        adapter = self.adapter()
        for name in ("COMPLETE.json", "manifest.json"):
            path = self.payload / name
            before = path.read_bytes()
            path.write_text("[" * 10000 + "0" + "]" * 10000)
            with self.subTest(name=name), self.assertRaises(ValueError):
                recovery_payload.inspect_payload(self.payload)
            job = self.finish(adapter, adapter.verify(first["entry_id"], adapter.history()["generation"]))
            self.assertEqual(job["state"], "unavailable")
            path.write_bytes(before)

    def test_read_only_verifier_can_cancel_between_hash_chunks(self):
        (self.source / "large.sav").write_bytes(b"x" * (3 * 1024**2))
        larger = self.root / "large-payload"
        recovery_payload.backup(self.source, larger, "saves")
        seen = []
        class Cancel(Exception):
            pass
        def progress(phase, byte_count, file_count):
            seen.append((phase, byte_count, file_count))
            if byte_count >= 1024**2:
                raise Cancel()
        before = self.hashes(larger)
        with self.assertRaises(Cancel):
            recovery_payload.inspect_payload(larger, progress=progress)
        self.assertEqual(max(item[1] for item in seen), 1024**2)
        self.assertEqual(self.hashes(larger), before)

    def test_quiesce_stops_job_but_adapter_can_verify_after_return(self):
        first = self.register()
        adapter = self.adapter()
        job = self.finish(adapter, adapter.verify(first["entry_id"], first["generation"]))
        adapter.quiesce()
        again = self.finish(adapter, adapter.verify(first["entry_id"], job["catalog_generation"]))
        self.assertEqual(again["state"], "verified")
        adapter.close()
        with self.assertRaisesRegex(BackupCatalogError, "closed"):
            adapter.verify(first["entry_id"], again["catalog_generation"])

    def test_failed_handoff_can_retry_verification_after_cancelled_worker_finishes(self):
        first = self.register()
        adapter = self.adapter()
        started, proceed = threading.Event(), threading.Event()
        inspect = recovery_payload.inspect_payload
        def held(*args, **kwargs):
            started.set()
            self.assertTrue(proceed.wait(5))
            return inspect(*args, **kwargs)
        with patch.object(recovery_payload, "inspect_payload", side_effect=held):
            job = adapter.verify(first["entry_id"], first["generation"])
            self.assertTrue(started.wait(5))
            try:
                with self.assertRaisesRegex(BackupCatalogError, "has not stopped"):
                    adapter.quiesce(timeout=0.001)
            finally:
                proceed.set()
            self.assertEqual(self.finish(adapter, job)["state"], "cancelled")
        next_job = self.finish(adapter, adapter.verify(first["entry_id"], first["generation"]))
        self.assertEqual(next_job["state"], "verified")

    def test_cli_register_list_verify_restore_and_index_removal(self):
        tool = Path(__file__).resolve().parents[1] / "tools/backup_catalog.py"
        def command(*args):
            result = subprocess.run([sys.executable, str(tool), "--catalog", str(self.path), *args],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        created = command("register", "--payload", str(self.payload), "--label", "Named CLI backup")
        identifier = created["entry_id"]
        self.assertEqual(command("list")["entries"][0]["label"], "Named CLI backup")
        self.assertEqual(command("verify", identifier)["state"], "verified")
        self.assertEqual(command("restore", identifier, "--output", str(self.root / "cli-rehearsal"))["action"], "restore-rehearsal")
        detail = command("detail", identifier)
        result = command("remove", identifier, "--generation", str(detail["generation"]))
        self.assertFalse(result["payload_deleted"])
        self.assertTrue(self.payload.is_dir())


if __name__ == "__main__":
    unittest.main()
