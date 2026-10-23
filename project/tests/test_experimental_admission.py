# SPDX-License-Identifier: MIT
"""Synthetic host admission cannot activate an unqualified device."""
import copy
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import pickle
import tempfile
import threading
import unittest
from unittest import mock

from bridge.experimental import (ExpectedFile, HostCandidate, HostObservation,
                                 HostReturnObservation, HostViewAdmission,
                                 inspect_host_fixture, prepare_host_view)
from bridge.experimental_journal import read_host_journal
from bridge.qualified_runtime import configuration
from psp_shell.runtime import ContractError


class HostExperimentalAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="experimental-host-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.payload = self.base / "fixture"
        (self.payload / "日本語").mkdir(parents=True)
        (self.payload / "main.py").write_bytes(b"# original host fixture\n")
        (self.payload / "日本語/cover.bin").write_bytes(b"synthetic artwork")
        self.candidate = HostCandidate("a" * 40, "b" * 64, "c" * 64, "d" * 64, "e" * 64,
            (ExpectedFile("main.py", hashlib.sha256(b"# original host fixture\n").hexdigest()),
             ExpectedFile("日本語/cover.bin", hashlib.sha256(b"synthetic artwork").hexdigest())))
        self.time = 100.0
        self.extra = {}
        self.number = 0

    def observe(self):
        value = HostObservation("11111111-2222-3333-4444-555555555555", 123, "456",
                                inspect_host_fixture(self.payload), True, True)
        return replace(value, **self.extra)

    def prepare(self, **kwargs):
        self.number += 1
        directory = self.base / ("private-evidence-%d" % self.number)
        directory.mkdir(mode=0o700)
        value = prepare_host_view(self.candidate, kwargs.pop("observe", self.observe), directory,
                                  clock=lambda: self.time, **kwargs)
        self.addCleanup(value.close)
        return value

    def assert_blocked(self, admission):
        self.assertEqual(admission.phase, "blocked")
        self.assertFalse(admission.classic_return_permitted)
        with self.assertRaises(ContractError):
            admission.perform("navigate", lambda: self.fail("Blocked callback ran"))

    def test_single_view_case_requires_positive_idle_resource_and_classic_observations(self):
        admission = self.prepare()
        self.assertFalse(admission.classic_return_permitted)
        admission.begin()
        ran = []
        for action in ("read_library", "navigate", "search", "poll_input", "render"):
            self.assertTrue(admission.perform(action, lambda: ran.append(True)))
        self.assertEqual(len(ran), 5)
        admission.request_return()
        self.assertFalse(admission.classic_return_permitted)
        admission.complete_return(lambda: HostReturnObservation(True, True, True, True))
        self.assertTrue(admission.classic_return_permitted)
        events = read_host_journal(admission.journal.directory)
        self.assertEqual([row["event"] for row in events], ["prepared", "started", "return_requested", "completed"])
        self.assertTrue(all(row["provenance"] == "host_fixture" for row in events))
        raw = (admission.journal.directory / "events.jsonl").read_text()
        for private_value in (str(self.payload), "日本語", "principal_start", "11111111-2222-3333-4444-555555555555", "synthetic artwork"):
            self.assertNotIn(private_value, raw)

    def test_modified_candidate_is_rejected_before_a_callback_and_cannot_restart(self):
        admission = self.prepare()
        (self.payload / "main.py").write_bytes(b"changed payload")
        with self.assertRaises(ContractError):
            admission.begin()
        self.assert_blocked(admission)
        with self.assertRaises(ContractError):
            admission.begin()

    def test_unlisted_or_missing_import_file_changes_the_exact_expected_inventory(self):
        for operation in ("unlisted", "missing"):
            with self.subTest(operation=operation):
                admission = self.prepare()
                path = self.payload / ("imported.py" if operation == "unlisted" else "main.py")
                previous = path.read_bytes() if path.exists() else None
                if previous is None:
                    path.write_bytes(b"new import")
                else:
                    path.unlink()
                with self.assertRaises(ContractError):
                    admission.begin()
                self.assert_blocked(admission)
                if previous is None:
                    path.unlink()
                else:
                    path.write_bytes(previous)

    def test_boot_pid_and_start_identity_are_rechecked_before_each_view_callback(self):
        for changed in ({"boot_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
                        {"principal_pid": 124}, {"principal_start": "457"}):
            with self.subTest(changed=changed):
                admission = self.prepare()
                admission.begin()
                self.extra = changed
                with self.assertRaises(ContractError):
                    admission.perform("render", lambda: self.fail("Changed owner callback ran"))
                self.assert_blocked(admission)
                self.extra = {}

    def test_dirty_lifetime_staged_handoff_and_missing_readiness_fail_closed(self):
        for changed in ({"dirty": True}, {"staged_command": True}, {"preferences_ready": False}, {"owners_ready": False}):
            with self.subTest(changed=changed):
                admission = self.prepare()
                admission.begin()
                self.extra = changed
                with self.assertRaises(ContractError):
                    admission.poll()
                self.assert_blocked(admission)
                self.extra = {}

    def test_prepare_rejects_live_device_and_serialized_observations(self):
        self.extra = {"live_device": True}
        with self.assertRaises(ContractError):
            self.prepare()
        self.extra = {}
        with self.assertRaises(ContractError):
            self.prepare(observe=lambda: dict(boot_id="copied card evidence"))

    def test_expiry_and_single_use_are_enforced_without_mutating_production_flags(self):
        admission = self.prepare()
        self.time += 60
        with self.assertRaises(ContractError):
            admission.begin()
        self.assert_blocked(admission)
        fresh = self.prepare()
        fresh.begin()
        with self.assertRaises(ContractError):
            fresh.begin()
        self.assertIsNone(configuration())

    def test_final_identity_callback_cannot_extend_startup_expiry(self):
        admission = self.prepare()
        original = admission._observe
        def delayed():
            value = original()
            self.time += 61
            return value
        admission._observe = delayed
        with self.assertRaises(ContractError):
            admission.begin()
        self.assert_blocked(admission)

    def test_view_deadline_requests_ordinary_return_and_never_runs_another_action(self):
        admission = self.prepare()
        admission.begin()
        self.time += 120
        self.assertFalse(admission.perform("render", lambda: self.fail("Expired view callback ran")))
        self.assertEqual(admission.phase, "return_requested")
        self.assertFalse(admission.classic_return_permitted)
        self.time += 5
        with self.assertRaises(ContractError):
            admission.complete_return(lambda: self.fail("Expired restoration ran"))
        self.assert_blocked(admission)

    def test_delayed_render_does_not_claim_a_hard_callback_timeout_or_classic_readiness(self):
        admission = self.prepare(view_seconds=1)
        admission.begin()
        def delayed_render():
            self.time += 2
        self.assertFalse(admission.perform("render", delayed_render))
        self.assertEqual(admission.phase, "return_requested")
        self.assertFalse(admission.classic_return_permitted)

    def test_game_tools_settings_resume_and_favorite_are_never_executed(self):
        for action in ("game", "launch", "tool", "settings-write", "usb", "power", "favorite", "resume", "advanced-menu"):
            with self.subTest(action=action):
                admission = self.prepare()
                admission.begin()
                with self.assertRaises(ContractError):
                    admission.perform(action, lambda: self.fail("Forbidden callback ran"))
                self.assert_blocked(admission)

    def test_view_callback_exception_blocks_even_if_later_idle_would_be_true(self):
        admission = self.prepare()
        admission.begin()
        def failed():
            raise RuntimeError("private callback data")
        with self.assertRaises(ContractError):
            admission.perform("render", failed)
        self.assert_blocked(admission)
        with self.assertRaises(ContractError):
            admission.complete_return(lambda: HostReturnObservation(True, True, True, True))
        self.assertNotIn("private callback data", (admission.journal.directory / "events.jsonl").read_text())

    def test_partial_restoration_or_missing_classic_readiness_never_permits_fallback(self):
        for result in (HostReturnObservation(False, True, True, True),
                       HostReturnObservation(True, False, True, True),
                       HostReturnObservation(True, True, False, True),
                       HostReturnObservation(True, True, True, False),
                       HostReturnObservation(True, True, True, True, True),
                       {"owners_restored": True}, True):
            with self.subTest(result=result):
                admission = self.prepare()
                admission.begin()
                admission.request_return()
                with self.assertRaises(ContractError):
                    admission.complete_return(lambda: result)
                self.assert_blocked(admission)

    def test_restoration_callback_expiry_and_late_identity_checks_block_return(self):
        for delay_at in ("restore", "identity"):
            with self.subTest(delay_at=delay_at):
                admission = self.prepare()
                admission.begin()
                admission.request_return()
                def restore():
                    if delay_at == "restore":
                        self.time += 6
                    else:
                        original = admission._observe
                        def delayed_observation():
                            value = original()
                            self.time += 6
                            return value
                        admission._observe = delayed_observation
                    return HostReturnObservation(True, True, True, True)
                with self.assertRaises(ContractError):
                    admission.complete_return(restore)
                self.assert_blocked(admission)

    def test_monotonic_clock_failure_blocks_without_authorizing_a_new_owner(self):
        for bad in (-1, float("nan"), float("inf"), True):
            with self.subTest(bad=bad):
                admission = self.prepare()
                admission.begin()
                previous, self.time = self.time, bad
                with self.assertRaises(ContractError):
                    admission.poll()
                self.assert_blocked(admission)
                self.time = previous

    def test_cross_thread_use_cannot_drive_the_source_owner(self):
        admission = self.prepare()
        admission.begin()
        result = []
        def wrong_thread():
            try:
                admission.perform("render", lambda: result.append("callback"))
            except ContractError:
                result.append("rejected")
        thread = threading.Thread(target=wrong_thread)
        thread.start()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["rejected"])
        self.assert_blocked(admission)

    def test_clock_callback_exception_blocks_and_records_only_a_fixed_failure(self):
        admission = self.prepare()
        admission.begin()
        def failed_clock():
            raise RuntimeError("private-clock-details")
        admission._clock = failed_clock
        with self.assertRaises(ContractError):
            admission.poll()
        self.assertEqual(admission.phase, "blocked")
        self.assertFalse(admission.classic_return_permitted)
        rows = read_host_journal(admission.journal.directory)
        self.assertEqual(rows[-1]["event"], "clock_failed")
        self.assertNotIn("private-clock-details", (admission.journal.directory / "events.jsonl").read_text())

    def test_repeated_return_request_cannot_reset_the_cooperative_deadline(self):
        admission = self.prepare()
        admission.begin()
        admission.request_return()
        self.time += 4
        self.assertFalse(admission.request_return())
        self.time += 1
        with self.assertRaises(ContractError):
            admission.request_return()
        self.assert_blocked(admission)

    def test_capability_cannot_be_copied_pickled_or_constructed_from_a_record(self):
        admission = self.prepare()
        for copy_operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with self.assertRaises(TypeError):
                copy_operation(admission)
        with self.assertRaises(ContractError):
            HostViewAdmission(None, None, None, None, None, 0, 60, 120, 5)

    def test_evidence_fsync_failure_blocks_before_the_next_callback(self):
        admission = self.prepare()
        admission.begin()
        with mock.patch("bridge.experimental_journal.os.fsync", side_effect=OSError("private path")):
            with self.assertRaises(ContractError):
                admission.request_return()
        self.assert_blocked(admission)

    def test_observation_exception_is_retained_only_as_a_fixed_event(self):
        admission = self.prepare()
        admission.begin()
        def failed():
            raise RuntimeError("credential=must-not-be-retained")
        admission._observe = failed
        with self.assertRaises(ContractError):
            admission.poll()
        self.assert_blocked(admission)
        self.assertNotIn("credential", (admission.journal.directory / "events.jsonl").read_text())

    def test_fixture_inspection_refuses_device_root_symlinks_and_hardlinked_payloads(self):
        with self.assertRaises(ContractError):
            inspect_host_fixture("/mnt/SDCARD/fixture")
        link = self.base / "linked-fixture"
        link.symlink_to(self.payload, target_is_directory=True)
        with self.assertRaises(ContractError):
            inspect_host_fixture(link)
        (self.payload / "escape").symlink_to(self.base / "private-secret")
        with self.assertRaises(ContractError):
            inspect_host_fixture(self.payload)
        (self.payload / "escape").unlink()
        os.link(self.payload / "main.py", self.payload / "second.py")
        with self.assertRaises(ContractError):
            inspect_host_fixture(self.payload)

    def test_expectation_paths_counts_and_time_budgets_are_bounded(self):
        for invalid in ("../private", "/etc/passwd", "folder/../secret", "folder//secret", "bad\\name", "bad\nname"):
            with self.assertRaises(ContractError):
                ExpectedFile(invalid, "a" * 64)
        for kwargs in ({"view_seconds": 121}, {"startup_window": 61}, {"return_seconds": 6},
                       {"view_seconds": 0}, {"view_seconds": True}):
            with self.assertRaises(ContractError):
                self.prepare(**kwargs)
        with self.assertRaises(ContractError):
            replace(self.candidate, files=(self.candidate.files[0], self.candidate.files[0]))


if __name__ == "__main__":
    unittest.main()
