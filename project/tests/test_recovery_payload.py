# SPDX-License-Identifier: MIT
"""Real new-tree copies and failures; synthetic data proves no physical restore."""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).absolute().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import recovery_payload as payload
import recovery_preflight as verifier


class RecoveryPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="recovery-payload-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        self.source.mkdir(mode=0o700)
        self.backup = self.base / "backup"
        self.restored = self.base / "restored"
        (self.source / "empty-directory").mkdir()
        (self.source / "日本語 game.sav").write_bytes(b"original-save\x00" * 100)
        (self.source / "empty.sav").write_bytes(b"")
        (self.source / "nested").mkdir()
        (self.source / "nested/config.json").write_bytes(b'{"unknown":"preserve"}\n')

    def copy(self, scope="saves", **kwargs):
        return payload.backup(self.source, self.backup, scope, **kwargs)

    def incomplete(self, output=None):
        output = output or self.backup
        self.assertTrue((output / "INCOMPLETE.json").exists())
        self.assertFalse((output / "COMPLETE.json").exists())
        self.assertTrue((output / "FAILED.json").exists())
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)

    def test_whole_tree_copy_readback_and_new_rehearsal_preserve_source(self):
        before = verifier.scan_tree(self.source, "card-files")
        complete = self.copy("card-files")
        self.assertEqual(verifier.tree_differences(before, verifier.scan_tree(self.source, "card-files"), "card-files"), [])
        manifest, _, fresh = payload.inspect_payload(self.backup)
        self.assertTrue(fresh["all_trees_match"])
        self.assertEqual(manifest["scope"], "card-files")
        result = payload.restore(self.backup, self.restored)
        self.assertEqual(verifier.tree_differences(before, verifier.scan_tree(self.restored / "data", "card-files"), "card-files"), [])
        for record in (complete, result):
            for name in payload.FALSE_FLAGS:
                self.assertIs(record[name], False)
        self.assertEqual(result["action"], "restore-rehearsal")
        self.assertTrue((self.restored / "rehearsal.json").exists())
        self.assertTrue((self.backup / "data/empty-directory").is_dir())

    def test_saves_scope_does_not_claim_full_save_discovery(self):
        complete = self.copy("saves")
        self.assertEqual(complete["scope"], "saves")
        self.assertTrue(complete["review_required"])
        self.assertFalse(complete["independent_media_verified"])
        self.assertEqual(json.loads((self.backup / "manifest.json").read_text())["scope"], "saves")

    def test_internal_metadata_including_root_is_preserved(self):
        self.source.chmod(0o750)
        (self.source / "nested").chmod(0o710)
        (self.source / "nested/config.json").chmod(0o640)
        (self.source / "日本語 game.sav").chmod(0o600)
        before = verifier.scan_tree(self.source, "internal-files")
        self.copy("internal-files")
        payload.restore(self.backup, self.restored)
        for root in (self.backup / "data", self.restored / "data"):
            self.assertEqual(verifier.tree_differences(before, verifier.scan_tree(root, "internal-files"), "internal-files"), [])
        self.assertEqual(stat.S_IMODE((self.backup / "data").stat().st_mode), 0o750)

    def test_existing_output_of_any_kind_is_never_overwritten(self):
        self.backup.mkdir()
        sentinel = self.backup / "owner-data"
        sentinel.write_bytes(b"newer original")
        with self.assertRaises(FileExistsError):
            self.copy()
        self.assertEqual(sentinel.read_bytes(), b"newer original")
        self.assertEqual(set(os.listdir(self.backup)), {"owner-data"})

    def test_restore_existing_tree_and_existing_file_are_refused(self):
        self.copy()
        for kind in ("directory", "file"):
            destination = self.base / kind
            if kind == "directory":
                destination.mkdir()
                (destination / "newer.sav").write_bytes(b"newer")
            else:
                destination.write_bytes(b"newer")
            with self.subTest(kind=kind), self.assertRaises(FileExistsError):
                payload.restore(self.backup, destination)
            self.assertEqual((destination / "newer.sav").read_bytes() if kind == "directory" else destination.read_bytes(), b"newer")

    def test_output_replaced_between_mkdir_and_open_is_never_chmodded_or_written(self):
        unrelated = self.base / "unrelated"
        unrelated.mkdir(mode=0o755)
        unrelated.chmod(0o755)
        (unrelated / "owner-data").write_bytes(b"unrelated owner data")
        real_open = os.open
        swapped = False
        def replace(name, flags, *args, **kwargs):
            nonlocal swapped
            if name == self.backup.name and flags & os.O_DIRECTORY and kwargs.get("dir_fd") is not None and not swapped:
                swapped = True
                self.backup.rename(self.base / "owned-output-moved")
                unrelated.rename(self.backup)
            return real_open(name, flags, *args, **kwargs)
        with patch.object(payload.os, "open", side_effect=replace), self.assertRaises(ValueError):
            self.copy()
        self.assertTrue(swapped)
        self.assertEqual(stat.S_IMODE(self.backup.stat().st_mode), 0o755)
        self.assertEqual(set(os.listdir(self.backup)), {"owner-data"})
        self.assertEqual((self.backup / "owner-data").read_bytes(), b"unrelated owner data")
        self.assertEqual(list((self.base / "owned-output-moved").iterdir()), [])

    def test_nested_directory_replaced_before_open_is_never_adopted(self):
        unrelated = self.base / "unrelated-child"
        unrelated.mkdir(mode=0o755)
        unrelated.chmod(0o755)
        (unrelated / "owner-data").write_bytes(b"unrelated child data")
        real_open = os.open
        swapped = False
        def replace(name, flags, *args, **kwargs):
            nonlocal swapped
            parent = kwargs.get("dir_fd")
            if name == "nested" and flags & os.O_DIRECTORY and parent is not None and not swapped:
                if os.readlink("/proc/self/fd/" + str(parent)) == str(self.backup / "data"):
                    swapped = True
                    (self.backup / "data/nested").rename(self.backup / "data/nested-created")
                    unrelated.rename(self.backup / "data/nested")
            return real_open(name, flags, *args, **kwargs)
        with patch.object(payload.os, "open", side_effect=replace), self.assertRaises(ValueError):
            self.copy()
        self.incomplete()
        changed = self.backup / "data/nested"
        self.assertEqual(stat.S_IMODE(changed.stat().st_mode), 0o755)
        self.assertEqual(set(os.listdir(changed)), {"owner-data"})
        self.assertEqual((changed / "owner-data").read_bytes(), b"unrelated child data")

    def test_data_root_replacement_before_copy_does_not_receive_new_files(self):
        unrelated = self.base / "unrelated-data"
        unrelated.mkdir(mode=0o755)
        unrelated.chmod(0o755)
        (unrelated / "owner-data").write_bytes(b"unrelated data root")
        real_copy = payload.copy_tree
        def replace(*args, **kwargs):
            (self.backup / "data").rename(self.backup / "data-created")
            unrelated.rename(self.backup / "data")
            return real_copy(*args, **kwargs)
        with patch.object(payload, "copy_tree", side_effect=replace), self.assertRaises(ValueError):
            self.copy()
        self.incomplete()
        changed = self.backup / "data"
        self.assertEqual(stat.S_IMODE(changed.stat().st_mode), 0o755)
        self.assertEqual(set(os.listdir(changed)), {"owner-data"})
        self.assertEqual((changed / "owner-data").read_bytes(), b"unrelated data root")

    def test_overlapping_source_or_payload_outputs_are_refused(self):
        for destination in (self.source, self.source / "backup", self.base):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                payload.backup(self.source, destination, "saves")
        self.copy()
        with self.assertRaises(ValueError):
            payload.restore(self.backup, self.backup / "restore")

    def test_source_symlink_is_rejected_before_output_creation(self):
        outside = self.base / "secret"
        outside.write_bytes(b"secret")
        (self.source / "unsafe-link").symlink_to(outside)
        with self.assertRaises(ValueError):
            self.copy()
        self.assertFalse(self.backup.exists())
        self.assertEqual(outside.read_bytes(), b"secret")

    def test_special_files_and_hardlinks_require_a_reviewed_image(self):
        fifo = self.source / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            self.copy()
        self.assertFalse(self.backup.exists())
        fifo.unlink()
        os.link(self.source / "empty.sav", self.source / "linked.sav")
        with self.assertRaises(ValueError):
            self.copy()
        self.assertFalse(self.backup.exists())

    def test_entry_and_byte_limits_reject_before_creating_output(self):
        for kwargs in ({"max_entries": 2}, {"max_bytes": 1}, {"max_entries": 0}, {"max_bytes": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.copy(**kwargs)
            self.assertFalse(self.backup.exists())

    def test_empty_source_does_not_claim_coverage(self):
        empty = self.base / "empty-source"
        empty.mkdir()
        with self.assertRaises(ValueError):
            payload.backup(empty, self.backup, "saves")
        self.assertFalse(self.backup.exists())

    def test_extended_metadata_is_not_silently_dropped(self):
        with patch.object(payload.os, "listxattr", return_value=["user.fixture"]), self.assertRaises(ValueError):
            self.copy("internal-files")
        self.incomplete()

    def test_late_source_extended_attribute_is_rejected_after_copy(self):
        real_copy = payload.copy_tree
        def changed(*args, **kwargs):
            result = real_copy(*args, **kwargs)
            os.setxattr(self.source / "nested", "user.review_probe", b"late-metadata")
            return result
        with patch.object(payload, "copy_tree", side_effect=changed), self.assertRaises(ValueError):
            self.copy("internal-files")
        self.incomplete()
        self.assertEqual(os.getxattr(self.source / "nested", "user.review_probe"), b"late-metadata")

    def test_fresh_inspect_rejects_new_retained_extended_attributes(self):
        self.copy("internal-files")
        os.setxattr(self.backup / "data/nested", "user.review_probe", b"retained-metadata")
        with self.assertRaises(ValueError):
            payload.inspect_payload(self.backup)
        with self.assertRaises(ValueError):
            payload.restore(self.backup, self.restored)
        self.assertFalse(self.restored.exists())

    def test_late_restored_extended_attribute_cannot_complete_rehearsal(self):
        self.copy("internal-files")
        real_verify = verifier.verify
        def changed(*args, **kwargs):
            result = real_verify(*args, **kwargs)
            if len(args) > 2:
                os.setxattr(self.restored / "data/nested", "user.review_probe", b"restored-metadata")
            return result
        with patch.object(verifier, "verify", side_effect=changed), self.assertRaises(ValueError):
            payload.restore(self.backup, self.restored)
        self.incomplete(self.restored)

    def test_unavailable_metadata_api_is_not_silently_accepted(self):
        with patch.object(payload.os, "listxattr", None), self.assertRaises(ValueError):
            self.copy("internal-files")
        self.incomplete()

    def test_full_destination_retains_partial_private_output_and_original(self):
        original = (self.source / "日本語 game.sav").read_bytes()
        real_write = payload.write_all
        def full(fd, raw):
            if "/data/" in os.readlink("/proc/self/fd/" + str(fd)):
                os.write(fd, raw[:2])
                raise OSError(errno.ENOSPC, "disposable destination full")
            return real_write(fd, raw)
        with patch.object(payload, "write_all", side_effect=full), self.assertRaises(OSError):
            self.copy()
        self.incomplete()
        self.assertEqual((self.source / "日本語 game.sav").read_bytes(), original)
        self.assertTrue(any(path.is_file() for path in (self.backup / "data").rglob("*")))

    def test_interrupt_retains_intent_and_failure_without_deleting_paths(self):
        with patch.object(payload, "copy_tree", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.copy()
        self.incomplete()
        self.assertEqual(json.loads((self.backup / "FAILED.json").read_text())["reason"], "KeyboardInterrupt")

    def test_data_fsync_failure_is_not_success(self):
        real_fsync = os.fsync
        def failed(fd):
            if "/data/" in os.readlink("/proc/self/fd/" + str(fd)) and stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError(errno.EIO, "disposable fsync failed")
            return real_fsync(fd)
        with patch.object(payload.os, "fsync", side_effect=failed), self.assertRaises(OSError):
            self.copy()
        self.incomplete()

    def test_internal_metadata_permission_failure_is_not_a_flattened_backup(self):
        original = verifier.scan_tree(self.source, "internal-files")
        with patch.object(payload, "metadata", side_effect=PermissionError("cannot preserve ownership")), self.assertRaises(PermissionError):
            self.copy("internal-files")
        self.incomplete()
        self.assertEqual(verifier.tree_differences(original, verifier.scan_tree(self.source, "internal-files"), "internal-files"), [])

    def test_readonly_destination_failure_keeps_evidence_without_overwrite(self):
        real_open = os.open
        def readonly(path, flags, *args, **kwargs):
            if flags & os.O_WRONLY and kwargs.get("dir_fd") is not None:
                directory = os.readlink("/proc/self/fd/" + str(kwargs["dir_fd"]))
                if "/data" in directory:
                    raise OSError(errno.EROFS, "disposable destination read-only")
            return real_open(path, flags, *args, **kwargs)
        with patch.object(payload.os, "open", side_effect=readonly), self.assertRaises(OSError):
            self.copy()
        self.incomplete()
        self.assertEqual((self.source / "nested/config.json").read_bytes(), b'{"unknown":"preserve"}\n')

    def test_failed_independent_readback_cannot_write_completion(self):
        real_verify = verifier.verify
        def mismatch(*args, **kwargs):
            result = real_verify(*args, **kwargs)
            result["all_trees_match"] = False
            return result
        with patch.object(verifier, "verify", side_effect=mismatch), self.assertRaises(ValueError):
            self.copy()
        self.incomplete()

    def test_failed_completion_sync_still_refuses_future_restore(self):
        real_fsync = os.fsync
        def failed(fd):
            if os.readlink("/proc/self/fd/" + str(fd)).endswith("/COMPLETE.json"):
                raise OSError(errno.EIO, "completion sync failed")
            return real_fsync(fd)
        with patch.object(payload.os, "fsync", side_effect=failed), self.assertRaises(OSError):
            self.copy()
        self.assertTrue((self.backup / "FAILED.json").exists())
        with self.assertRaises(ValueError):
            payload.restore(self.backup, self.restored)
        self.assertFalse(self.restored.exists())

    def test_source_file_replacement_during_copy_is_refused(self):
        real_read = os.read
        changed = False
        def replace(fd, count):
            nonlocal changed
            raw = real_read(fd, count)
            path = os.readlink("/proc/self/fd/" + str(fd))
            if path.endswith("/nested/config.json") and raw and not changed:
                changed = True
                original = self.source / "nested/config.json"
                original.rename(self.source / "nested/original-moved.json")
                original.write_bytes(raw)
            return raw
        with patch.object(payload.os, "read", side_effect=replace), self.assertRaises(ValueError):
            self.copy()
        self.incomplete()
        self.assertTrue(changed)
        self.assertTrue((self.source / "nested/original-moved.json").exists())

    def test_source_contents_changed_after_copy_are_not_manifested_as_success(self):
        real_copy = payload.copy_tree
        def changed(*args, **kwargs):
            real_copy(*args, **kwargs)
            (self.source / "empty.sav").write_bytes(b"new owner save")
        with patch.object(payload, "copy_tree", side_effect=changed), self.assertRaises(ValueError):
            self.copy()
        self.incomplete()
        self.assertEqual((self.source / "empty.sav").read_bytes(), b"new owner save")

    def test_same_bytes_source_root_replacement_before_copy_is_refused(self):
        real_create = payload.create_output
        def replaced(*args, **kwargs):
            result = real_create(*args, **kwargs)
            self.source.rename(self.base / "source-held")
            shutil.copytree(self.base / "source-held", self.source)
            return result
        with patch.object(payload, "create_output", side_effect=replaced), self.assertRaises(ValueError):
            self.copy()
        self.incomplete()
        self.assertEqual((self.source / "empty.sav").read_bytes(), b"")
        self.assertTrue((self.base / "source-held/empty.sav").exists())

    def test_source_root_replacement_is_detected_and_preserved(self):
        real_copy = payload.copy_tree
        def replaced(*args, **kwargs):
            real_copy(*args, **kwargs)
            self.source.rename(self.base / "source-held")
            self.source.mkdir()
            (self.source / "replacement-owner-data").write_bytes(b"untouched")
        with patch.object(payload, "copy_tree", side_effect=replaced), self.assertRaises(ValueError):
            self.copy()
        self.incomplete()
        self.assertEqual((self.source / "replacement-owner-data").read_bytes(), b"untouched")
        self.assertTrue((self.base / "source-held/empty.sav").exists())

    def test_output_root_replacement_never_writes_or_deletes_replacement_data(self):
        real_copy = payload.copy_tree
        def replaced(*args, **kwargs):
            real_copy(*args, **kwargs)
            self.backup.rename(self.base / "backup-held")
            self.backup.mkdir()
            (self.backup / "replacement-owner-data").write_bytes(b"untouched")
        with patch.object(payload, "copy_tree", side_effect=replaced), self.assertRaises(ValueError):
            self.copy()
        self.assertEqual(set(os.listdir(self.backup)), {"replacement-owner-data"})
        self.assertEqual((self.backup / "replacement-owner-data").read_bytes(), b"untouched")
        self.assertTrue((self.base / "backup-held/FAILED.json").exists())

    def test_destination_directory_swap_cannot_redirect_writes(self):
        real_open = payload.open_directory
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "sentinel").write_bytes(b"untouched")
        swapped = False
        def replaced(root_fd, relative, expected=None):
            nonlocal swapped
            if expected is not None and relative == "nested" and not swapped:
                swapped = True
                target = self.backup / "data/nested"
                target.rename(self.backup / "data/nested-held")
                target.symlink_to(outside)
            return real_open(root_fd, relative, expected)
        with patch.object(payload, "open_directory", side_effect=replaced), self.assertRaises(OSError):
            self.copy()
        self.incomplete()
        self.assertEqual(set(os.listdir(outside)), {"sentinel"})
        self.assertEqual((outside / "sentinel").read_bytes(), b"untouched")

    def test_retained_corruption_or_manifest_change_prevents_restore_creation(self):
        self.copy()
        data = self.backup / "data/empty.sav"
        data.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            payload.restore(self.backup, self.restored)
        self.assertFalse(self.restored.exists())
        data.write_bytes(b"")
        manifest = self.backup / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            payload.restore(self.backup, self.restored)
        self.assertFalse(self.restored.exists())

    def test_retained_payload_changed_during_restore_leaves_incomplete_rehearsal(self):
        self.copy()
        real_copy = payload.copy_tree
        def changed(*args, **kwargs):
            real_copy(*args, **kwargs)
            path = self.backup / "manifest.json"
            path.write_bytes(path.read_bytes() + b" ")
        with patch.object(payload, "copy_tree", side_effect=changed), self.assertRaises(ValueError):
            payload.restore(self.backup, self.restored)
        self.incomplete(self.restored)

    def test_incomplete_extra_or_nonprivate_payload_is_not_accepted(self):
        self.copy()
        (self.backup / "unreviewed").write_bytes(b"unknown")
        with self.assertRaises(ValueError):
            payload.inspect_payload(self.backup)
        (self.backup / "unreviewed").unlink()
        self.backup.chmod(0o755)
        with self.assertRaises(ValueError):
            payload.inspect_payload(self.backup)

    def test_restore_obeys_its_own_budgets_before_output_creation(self):
        self.copy()
        for kwargs in ({"max_bytes": 1}, {"max_entries": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                payload.restore(self.backup, self.restored, **kwargs)
            self.assertFalse(self.restored.exists())

    def test_symlink_output_ancestor_is_refused_without_writing_through_it(self):
        target = self.base / "target"
        target.mkdir()
        (self.base / "linked-parent").symlink_to(target)
        with self.assertRaises(OSError):
            payload.backup(self.source, self.base / "linked-parent/new", "saves")
        self.assertEqual(list(target.iterdir()), [])

    def test_cli_requires_scope_and_returns_success_only_after_readback(self):
        self.assertEqual(payload.main(["backup", "--source", str(self.source), "--scope", "saves", "--output", str(self.backup)]), 0)
        self.assertEqual(payload.main(["restore", "--payload", str(self.backup), "--output", str(self.restored)]), 0)
        self.assertEqual(payload.main(["restore", "--payload", str(self.backup), "--output", str(self.restored)]), 2)
        self.assertTrue(json.loads((self.restored / "rehearsal.json").read_text())["all_trees_match"])


if __name__ == "__main__":
    unittest.main()
