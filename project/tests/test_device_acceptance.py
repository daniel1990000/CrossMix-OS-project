# SPDX-License-Identifier: MIT
"""Private operator evidence stays distinct from trusted device qualification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import device_acceptance as acceptance


class DeviceAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="device-acceptance-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.card, self.root, self.session = self.base / "card", self.base / "root", self.base / "session"
        self.card.mkdir()
        self.root.mkdir()
        (self.root / "proc/device-tree").mkdir(parents=True)
        (self.root / "proc/device-tree/model").write_text("TrimUI Smart Pro TG5040")
        self.save = self.card / "Saves/saves/fixture.sav"
        self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b"private fixture battery-save bytes")
        acceptance.create(self.session)

    def capture(self, phase):
        return acceptance.capture(self.session, phase, self.root, self.card, saves=["Saves/saves/fixture.sav"])

    def test_prepare_and_captures_never_change_selected_save_or_activate_profile(self):
        before_bytes, before_time = self.save.read_bytes(), self.save.stat().st_mtime_ns
        before = self.capture("before")
        after = self.capture("after")
        self.assertEqual(before["inventory"]["device"]["model"], "trimui-smart-pro")
        self.assertEqual(before["save_hashes_only"][0]["sha256"], hashlib.sha256(before_bytes).hexdigest())
        self.assertEqual(after["save_comparison"], [{"path": "Saves/saves/fixture.sav", "unchanged": True}])
        self.assertNotIn(before_bytes.decode(), json.dumps(after))
        self.assertEqual(self.save.read_bytes(), before_bytes)
        self.assertEqual(self.save.stat().st_mtime_ns, before_time)
        self.assertFalse(after["hardware_qualified"])
        profile, _ = acceptance.read_json(self.session / "expected-profile.json")
        self.assertFalse(profile["hardware_qualified"])
        self.assertFalse(profile["runtime_verified"])
        self.assertFalse(profile["source_use_verified"])

    def test_changed_save_is_reported_without_restoring_older_data(self):
        self.capture("before")
        self.save.write_bytes(b"newer save content")
        after = self.capture("after")
        self.assertFalse(after["save_comparison"][0]["unchanged"])
        self.assertEqual(self.save.read_bytes(), b"newer save content")

    def test_missing_save_after_testing_is_retained_as_failure_evidence(self):
        self.capture("before")
        self.save.unlink()
        after = self.capture("after")
        self.assertEqual(after["save_hashes_only"], [{"path": "Saves/saves/fixture.sav", "missing": True}])
        expected = [{"path": "Saves/saves/fixture.sav", "unchanged": False, "missing": True}]
        self.assertEqual(after["save_comparison"], expected)
        acceptance.record(self.session, "save_resume", "fail", "Selected battery save disappeared during fixture test")
        report = acceptance.report(self.session)
        self.assertTrue(report["snapshots_complete"])
        self.assertEqual(report["save_comparison"], expected)
        self.assertEqual(report["cases"]["save_resume"]["status"], "fail")
        self.assertFalse(self.save.exists())
        self.assertFalse(report["hardware_qualified"])

    def test_missing_save_directory_after_testing_is_retained_without_recreation(self):
        self.capture("before")
        shutil.rmtree(self.card / "Saves")
        self.capture("after")
        self.assertTrue(acceptance.report(self.session)["save_comparison"][0]["missing"])
        self.assertFalse((self.card / "Saves").exists())

    def test_missing_baseline_save_cannot_be_recorded_as_a_valid_before_snapshot(self):
        self.save.unlink()
        with self.assertRaises(FileNotFoundError):
            self.capture("before")
        self.assertFalse((self.session / "before.json").exists())

    def test_after_snapshot_does_not_treat_dangling_symlink_or_special_file_as_missing(self):
        self.capture("before")
        self.save.unlink()
        self.save.symlink_to(self.base / "nonexistent")
        with self.assertRaises(OSError):
            self.capture("after")
        self.save.unlink()
        os.mkfifo(self.save)
        with self.assertRaisesRegex(ValueError, "regular file"):
            self.capture("after")
        self.assertFalse((self.session / "after.json").exists())

    def test_missing_save_marker_is_after_only_and_cannot_hide_an_inconsistent_comparison(self):
        self.capture("before")
        before_path = self.session / "before.json"
        raw = before_path.read_bytes()
        before = json.loads(raw)
        before.pop("content_sha256")
        before["save_hashes_only"] = [{"path": "Saves/saves/fixture.sav", "missing": True}]
        before_path.write_bytes(acceptance.encoded(acceptance.checksummed(before)))
        with self.assertRaisesRegex(ValueError, "save identity"):
            acceptance.report(self.session)
        before_path.write_bytes(raw)
        self.save.unlink()
        self.capture("after")
        path = self.session / "after.json"
        after = json.loads(path.read_bytes())
        after.pop("content_sha256")
        after["save_comparison"][0]["unchanged"] = True
        path.write_bytes(acceptance.encoded(acceptance.checksummed(after)))
        with self.assertRaisesRegex(ValueError, "comparison is inconsistent"):
            acceptance.report(self.session)

    def test_capture_refuses_replacement_card_location_and_stale_profile(self):
        with self.assertRaises(ValueError):
            acceptance.capture(self.session, "after", self.root, self.card, saves=[])
        with self.assertRaises(ValueError):
            acceptance.capture(self.card, "before", self.root, self.card)
        self.capture("before")
        with self.assertRaises(ValueError):
            self.capture("before")
        with self.assertRaises(ValueError):
            acceptance.capture(self.session, "after", self.root, self.card, saves=[])
        path = self.session / "expected-profile.json"
        expected = json.loads(path.read_text())
        expected["hardware_qualified"] = True
        path.write_text(json.dumps(expected))
        with self.assertRaisesRegex(ValueError, "profile changed"):
            acceptance.report(self.session)

    def test_save_selection_rejects_escape_symlinks_and_non_save_files(self):
        tree = acceptance.InstalledTree(self.root, self.card)
        for name in ("../secret", "/Saves/save.sav", "Saves/../secret", "Roms/private.iso", "Saves//file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                acceptance.save_identity(tree, name)
        outside = self.base / "private"
        outside.write_bytes(b"do not collect")
        (self.card / "Saves/outside.sav").symlink_to(outside)
        with self.assertRaises((OSError, ValueError)):
            acceptance.save_identity(tree, "Saves/outside.sav")

    def test_operator_attempts_are_append_only_and_cannot_mint_qualification(self):
        self.capture("before")
        first = acceptance.record(self.session, "input", "fail", "Fixture disconnect left held keys")
        first_raw = (self.session / "input/001.json").read_bytes()
        latest = acceptance.record(self.session, "input", "pass", "Fixture retest passed after reviewed fix")
        self.assertEqual((self.session / "input/001.json").read_bytes(), first_raw)
        self.assertEqual(latest["previous_sha256"], hashlib.sha256(first_raw).hexdigest())
        self.assertFalse(first["hardware_qualified"])
        report = acceptance.report(self.session)
        self.assertEqual(report["cases"]["input"], {"status": "pass", "attempts": 2})
        self.assertEqual(report["cases"]["usb"]["status"], "not_run")
        self.assertFalse(report["operator_cases_all_pass"])
        self.assertFalse(report["hardware_qualified"])
        self.assertTrue(report["review_required"])

    def test_changed_attempt_or_cross_session_snapshot_is_rejected(self):
        self.capture("before")
        acceptance.record(self.session, "input", "pass", "Fixture observation")
        path = self.session / "before.json"
        snapshot = json.loads(path.read_text())
        snapshot["session_id"] = "f" * 32
        path.write_text(json.dumps(snapshot))
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            acceptance.report(self.session)
        with self.assertRaisesRegex(ValueError, "another acceptance session"):
            acceptance.record(self.session, "boot", "pass", "Must reject this fixture")

    def test_all_operator_passes_still_require_review_and_no_activation(self):
        for case in acceptance.CASES:
            acceptance.record(self.session, case, "pass", "Synthetic host fixture result only")
        report = acceptance.report(self.session)
        self.assertTrue(report["operator_cases_all_pass"])
        self.assertFalse(report["hardware_qualified"])
        self.assertFalse(report["automatic_activation"])
        self.assertTrue(report["review_required"])

    def test_session_and_case_files_are_private_and_symlinks_are_refused(self):
        self.assertEqual(self.session.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.session / "session.json").stat().st_mode & 0o777, 0o600)
        (self.base / "linked-session").symlink_to(self.session)
        with self.assertRaises(ValueError):
            acceptance.report(self.base / "linked-session")
        with self.assertRaises(FileExistsError):
            acceptance.create(self.session)
        for case, status, note in (("unknown", "pass", "x"), ("boot", "maybe", "x"), ("boot", "pass", "")):
            with self.assertRaises(ValueError):
                acceptance.record(self.session, case, status, note)

    def test_cli_reports_unrun_device_work_without_upload_or_hardware_commands(self):
        cmd = [sys.executable, str(PROJECT / "tools/device_acceptance.py"), "report", "--session", str(self.session)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(set(row["status"] for row in report["cases"].values()), {"not_run"})
        self.assertFalse(report["hardware_qualified"])

    def test_save_alias_cannot_read_a_different_file_inside_the_inspected_card(self):
        private_rom = self.card / "Roms/private.iso"
        private_rom.parent.mkdir()
        private_rom.write_bytes(b"owner game data must not be collected as a save")
        (self.card / "Saves/alias.sav").symlink_to("/mnt/SDCARD/Roms/private.iso")
        tree = acceptance.InstalledTree(self.root, self.card)
        with self.assertRaises(OSError):
            acceptance.save_identity(tree, "Saves/alias.sav")
        (self.card / "Saves/aliased-directory").symlink_to(self.card / "Roms", target_is_directory=True)
        with self.assertRaises(OSError):
            acceptance.save_identity(tree, "Saves/aliased-directory/private.iso")

    def test_fifo_lock_is_rejected_promptly_without_opening_hardware(self):
        os.mkfifo(self.session / ".lock", 0o600)
        result = subprocess.run([sys.executable, str(PROJECT / "tools/device_acceptance.py"), "report", "--session", str(self.session)],
                                text=True, capture_output=True, timeout=2)
        self.assertEqual(result.returncode, 2)
        self.assertIn("regular file", result.stderr)

    def test_directory_swap_during_append_cannot_write_outside_the_retained_case(self):
        outside = self.base / "outside"
        outside.mkdir()
        case = self.session / "input"
        retained = self.session / "retained-input"
        original_open = os.open
        changed = False
        def swap(path, flags, *args, **kwargs):
            nonlocal changed
            if Path(path).name == "001.json" and flags & os.O_CREAT and not changed:
                changed = True
                case.rename(retained)
                case.symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)
        with mock.patch.object(acceptance.os, "open", side_effect=swap):
            acceptance.record(self.session, "input", "blocked", "Case directory replaced during append fixture")
        self.assertTrue(changed)
        self.assertFalse((outside / "001.json").exists())
        self.assertTrue((retained / "001.json").is_file())

    def test_editing_latest_operator_attempt_does_not_turn_a_failure_into_pass(self):
        acceptance.record(self.session, "input", "fail", "Observed failure fixture")
        path = self.session / "input/001.json"
        value = json.loads(path.read_text())
        value["status"] = "pass"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "checksum"):
            acceptance.report(self.session)

    def test_historical_snapshot_references_are_checked_even_if_latest_chain_is_consistent(self):
        self.capture("before")
        acceptance.record(self.session, "input", "fail", "First observation")
        acceptance.record(self.session, "input", "pass", "Later observation")
        first_path = self.session / "input/001.json"
        first = json.loads(first_path.read_text())
        first.pop("content_sha256")
        first["snapshot_sha256"]["before"] = "f" * 64
        first_raw = acceptance.encoded(acceptance.checksummed(first))
        first_path.write_bytes(first_raw)
        latest_path = self.session / "input/002.json"
        latest = json.loads(latest_path.read_text())
        latest.pop("content_sha256")
        latest["previous_sha256"] = hashlib.sha256(first_raw).hexdigest()
        latest_path.write_bytes(acceptance.encoded(acceptance.checksummed(latest)))
        with self.assertRaisesRegex(ValueError, "referenced snapshot"):
            acceptance.report(self.session)

    def test_replacement_filesystem_copy_cannot_be_compared_as_the_original_card(self):
        self.capture("before")
        original = self.base / "original-card"
        self.card.rename(original)
        shutil.copytree(original, self.card)
        with self.assertRaisesRegex(ValueError, "filesystem identity changed"):
            self.capture("after")

    def test_duplicate_or_nonfinite_json_fields_cannot_hide_evidence_values(self):
        path = self.base / "invalid.json"
        for raw in (b'{"schema":1,"schema":2}', b'{"value":NaN}'):
            path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                acceptance.read_json(path)


if __name__ == "__main__":
    unittest.main()
