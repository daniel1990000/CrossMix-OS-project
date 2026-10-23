# SPDX-License-Identifier: MIT
"""Durable host evidence fails closed on publication and replacement faults."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from bridge.experimental_journal import HostEvidenceJournal, encoded, read_host_journal
from psp_shell.runtime import ContractError


class ExperimentalJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="experimental-journal-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.directory = self.base / "evidence"
        self.directory.mkdir(mode=0o700)
        self.path = self.directory / "events.jsonl"

    def journal(self):
        result = HostEvidenceJournal(self.directory, session="1" * 64, candidate="2" * 64,
                                      boot="3" * 64, owner="4" * 64)
        self.addCleanup(result.close)
        return result

    def test_complete_fresh_readback_preserves_the_hash_chain_without_private_fields(self):
        journal = self.journal()
        first = journal.append("prepared", 1)
        journal.append("started", 2)
        rows = read_host_journal(self.directory)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["previous"], first)
        self.assertEqual(rows[0]["provenance"], "host_fixture")
        self.assertEqual(set(rows[0]), {"schema", "provenance", "session", "candidate", "boot", "owner",
                                      "sequence", "event", "monotonic_ns", "previous", "sha256"})

    def test_private_directory_and_exclusive_new_record_are_required(self):
        self.directory.chmod(0o755)
        with self.assertRaises(ContractError):
            self.journal()
        self.directory.chmod(0o700)
        journal = self.journal()
        journal.append("prepared", 1)
        before = self.path.read_bytes()
        with self.assertRaises(ContractError):
            self.journal()
        self.assertEqual(self.path.read_bytes(), before)

    def test_symlinked_directory_or_evidence_file_cannot_redirect_writes(self):
        alias = self.base / "alias"
        alias.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(ContractError):
            HostEvidenceJournal(alias, session="1" * 64, candidate="2" * 64, boot="3" * 64, owner="4" * 64)
        target = self.base / "owner-file"
        target.write_text("preserve me")
        self.path.symlink_to(target)
        with self.assertRaises(ContractError):
            self.journal()
        self.assertEqual(target.read_text(), "preserve me")

    def test_arbitrary_notes_and_nonmonotonic_time_poison_the_writer(self):
        journal = self.journal()
        journal.append("prepared", 5)
        before = self.path.read_bytes()
        with self.assertRaises(ContractError):
            journal.append("credential=private", 6)
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(ContractError):
            journal.append("started", 7)
        self.assertNotIn(b"credential", self.path.read_bytes())

    def test_backward_clock_and_boolean_timestamps_are_rejected(self):
        for value in (0, True, -1, "one"):
            with self.subTest(value=value):
                directory = self.base / ("time-" + str(value))
                directory.mkdir(mode=0o700)
                journal = HostEvidenceJournal(directory, session="1" * 64, candidate="2" * 64, boot="3" * 64, owner="4" * 64)
                self.addCleanup(journal.close)
                journal.append("prepared", 1)
                with self.assertRaises(ContractError):
                    journal.append("started", value)

    def test_failed_fsync_returns_no_digest_and_the_writer_cannot_retry(self):
        journal = self.journal()
        journal.append("prepared", 1)
        with mock.patch("bridge.experimental_journal.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(ContractError):
                journal.append("started", 2)
        after_failure = self.path.read_bytes()
        with self.assertRaises(ContractError):
            journal.append("started", 3)
        self.assertEqual(self.path.read_bytes(), after_failure)

    def test_short_write_is_uncertain_and_readback_refuses_the_partial_record(self):
        journal = self.journal()
        journal.append("prepared", 1)
        original = os.write
        def partial(descriptor, raw):
            return original(descriptor, raw[:10])
        with mock.patch("bridge.experimental_journal.os.write", side_effect=partial):
            with self.assertRaises(ContractError):
                journal.append("started", 2)
        with self.assertRaises(ContractError):
            read_host_journal(self.directory)
        with self.assertRaises(ContractError):
            journal.append("started", 3)

    def test_same_size_edit_between_fsync_and_publication_cannot_receive_a_success_digest(self):
        journal = self.journal()
        journal.append("prepared", 1)
        original = os.fsync
        def changed_after_sync(descriptor):
            original(descriptor)
            self.path.write_bytes(self.path.read_bytes().replace(b'"started"', b'"blocked"'))
        with mock.patch("bridge.experimental_journal.os.fsync", side_effect=changed_after_sync):
            with self.assertRaises(ContractError):
                journal.append("started", 2)
        with self.assertRaises(ContractError):
            journal.append("blocked", 3)

    def test_replaced_file_is_detected_and_neither_new_nor_old_record_is_appended(self):
        journal = self.journal()
        journal.append("prepared", 1)
        old = self.directory / "old.jsonl"
        self.path.rename(old)
        self.path.write_text("untrusted replacement")
        self.path.chmod(0o600)
        old_bytes, new_bytes = old.read_bytes(), self.path.read_bytes()
        with self.assertRaises(ContractError):
            journal.append("started", 2)
        self.assertEqual(old.read_bytes(), old_bytes)
        self.assertEqual(self.path.read_bytes(), new_bytes)

    def test_replaced_directory_cannot_inherit_the_old_writer(self):
        journal = self.journal()
        journal.append("prepared", 1)
        old = self.base / "old-evidence"
        self.directory.rename(old)
        self.directory.mkdir(mode=0o700)
        with self.assertRaises(ContractError):
            journal.append("started", 2)
        self.assertFalse(self.path.exists())
        self.assertEqual(len(read_host_journal(old)), 1)

    def test_changed_permissions_extra_links_or_external_writes_block_appends(self):
        for change in ("mode", "hardlink", "append", "same-size-edit"):
            with self.subTest(change=change):
                directory = self.base / change
                directory.mkdir(mode=0o700)
                journal = HostEvidenceJournal(directory, session="1" * 64, candidate="2" * 64, boot="3" * 64, owner="4" * 64)
                self.addCleanup(journal.close)
                journal.append("prepared", 1)
                path = directory / "events.jsonl"
                if change == "mode":
                    path.chmod(0o644)
                elif change == "hardlink":
                    os.link(path, directory / "another-link")
                elif change == "same-size-edit":
                    path.write_bytes(path.read_bytes().replace(b'"prepared"', b'"expired "'))
                else:
                    with path.open("ab") as output:
                        output.write(b"external")
                before = path.read_bytes()
                with self.assertRaises(ContractError):
                    journal.append("started", 2)
                self.assertEqual(path.read_bytes(), before)

    def test_readback_rejects_modified_bytes_duplicate_keys_and_unterminated_records(self):
        journal = self.journal()
        journal.append("prepared", 1)
        original = self.path.read_bytes()
        for changed in (original.replace(b'"prepared"', b'"started"'),
                        original.replace(b'{"boot"', b'{"schema":1,"boot"'), original[:-1]):
            with self.subTest(changed=changed[:40]):
                self.path.write_bytes(changed)
                with self.assertRaises(ContractError):
                    read_host_journal(self.directory)

    def test_rehashed_record_cannot_change_session_binding_or_sequence(self):
        journal = self.journal()
        journal.append("prepared", 1)
        journal.append("started", 2)
        originals = self.path.read_bytes().splitlines()
        for field, value in (("session", "9" * 64), ("sequence", 7), ("monotonic_ns", 0), ("schema", True)):
            with self.subTest(field=field):
                row = json.loads(originals[1])
                row[field] = value
                body = {key: item for key, item in row.items() if key != "sha256"}
                row["sha256"] = hashlib.sha256(encoded(body)).hexdigest()
                self.path.write_bytes(originals[0] + b"\n" + encoded(row) + b"\n")
                with self.assertRaises(ContractError):
                    read_host_journal(self.directory)

    def test_journal_event_count_and_size_have_fixed_limits(self):
        journal = self.journal()
        with mock.patch("bridge.experimental_journal.MAX_EVENTS", 2):
            journal.append("prepared", 1)
            journal.append("started", 2)
            with self.assertRaises(ContractError):
                journal.append("blocked", 3)
        self.assertEqual(len(read_host_journal(self.directory)), 2)

    def test_nonowner_thread_cannot_write_evidence(self):
        journal = self.journal()
        result = []
        def other():
            try:
                journal.append("prepared", 1)
            except ContractError:
                result.append("rejected")
        worker = threading.Thread(target=other)
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, ["rejected"])
        self.assertEqual(self.path.read_bytes(), b"")

    def test_private_observation_provenance_is_explicit_and_unknown_claims_are_refused(self):
        journal = HostEvidenceJournal(self.directory, session="1" * 64, candidate="2" * 64,
                                      boot="3" * 64, owner="4" * 64, provenance="private_experimental")
        self.addCleanup(journal.close)
        journal.append("prepared", 1)
        self.assertEqual(read_host_journal(self.directory)[0]["provenance"], "private_experimental")
        other = self.base / "invalid-provenance"
        other.mkdir(mode=0o700)
        with self.assertRaises(ContractError):
            HostEvidenceJournal(other, session="1" * 64, candidate="2" * 64,
                                boot="3" * 64, owner="4" * 64, provenance="hardware_qualified")
        self.assertFalse((other / "events.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
