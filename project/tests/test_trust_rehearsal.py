# SPDX-License-Identifier: MIT
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools import trust_rehearsal as tr


class TrustRehearsalTests(unittest.TestCase):
    def test_real_rotation_revocation_and_recovery_preserve_fixture_data(self):
        report = tr.rehearse()
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["operational_trust_established"])
        self.assertFalse(report["hardware_tested"])
        self.assertFalse(report["source_use_verified"])
        self.assertFalse(report["distribution_cleared"])
        self.assertTrue(report["disposable_keys_and_packages_removed"])
        self.assertEqual(len(set(report["public_key_fingerprints"].values())), 2)
        self.assertEqual(len(report["packages"]), 3)
        self.assertEqual(report["recovery"]["retired_release_rollback"], "passed-in-host-fixture")
        self.assertEqual(report["recovery"]["revoked_release_rollback"], "blocked-selector-preserved")
        self.assertFalse(report["recovery"]["classic_request_is_physical_recovery_proof"])
        names = {item["check"] for item in report["checks"] if item["passed"] is True}
        self.assertIn("signed_archive_payload_tamper_rejected", names)
        self.assertIn("mutated_public_key_rejected", names)
        self.assertIn("duplicate_registry_identity_rejected", names)
        self.assertIn("retired_key_cannot_authorize_signing", names)
        self.assertIn("new_key_is_unknown_to_original_registry", names)
        self.assertIn("revoked_archive_rejected", names)
        self.assertIn("blocked_rollback_retains_selector_classic_request_and_newer_save", names)
        self.assertIn("new_current_key_recovery_package_preserves_newer_save", names)
        for archive in report["packages"].values():
            self.assertRegex(archive["sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(archive["manifest_sha256"], r"^[a-f0-9]{64}$")
            self.assertGreater(archive["bytes"], 0)

    def test_report_excludes_raw_private_keys_paths_and_recoverable_packages(self):
        secrets, paths = [], []
        original = tr.ov.keygen

        def observe(private, public):
            value = original(private, public)
            secrets.append(Path(private).read_bytes())
            paths.extend((str(private), str(public)))
            return value

        with mock.patch.object(tr.ov, "keygen", side_effect=observe):
            report = tr.rehearse()
        raw = tr.ov.canonical(report)
        self.assertEqual(len(secrets), 2)
        for secret in secrets:
            self.assertNotIn(secret.hex().encode(), raw)
            self.assertNotIn(base64.b64encode(secret), raw)
        for path in paths:
            self.assertNotIn(path.encode(), raw)
            self.assertFalse(Path(path).exists())

    def test_failure_still_removes_generated_private_material(self):
        paths = []
        original = tr.ov.keygen

        def observe(private, public):
            value = original(private, public)
            paths.extend((Path(private), Path(public)))
            return value

        with mock.patch.object(tr.ov, "keygen", side_effect=observe), \
                mock.patch.object(tr.ov, "create_archive", side_effect=OSError("injected full-storage failure")):
            with self.assertRaisesRegex(OSError, "full-storage"):
                tr.rehearse()
        self.assertEqual(len(paths), 4)
        for path in paths:
            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())

    def test_required_rejection_cannot_silently_be_counted_as_pass(self):
        original = tr.ov.load_trust_store

        def ignore_retired(primary, registry_path=None, signing=False):
            return original(primary, registry_path, signing=False)

        with mock.patch.object(tr.ov, "load_trust_store", side_effect=ignore_retired):
            with self.assertRaisesRegex(RuntimeError, "required rejection did not occur"):
                tr.rehearse()

    def test_publish_reads_back_exact_report_without_replacing_existing_file(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "rehearsal.json"
            report = tr.rehearse()
            digest = tr.write_report(output, report)
            raw = output.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            self.assertEqual(json.loads(raw), report)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                tr.write_report(output, {"different": True})
            self.assertEqual(output.read_bytes(), raw)
            self.assertEqual(list(Path(name).iterdir()), [output])

    def test_report_symlink_and_parent_symlink_refused(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            existing = root / "existing"
            existing.write_bytes(b"keep original")
            link = root / "report.json"
            link.symlink_to(existing)
            with self.assertRaises(FileExistsError):
                tr.write_report(link, {"status": "passed"})
            self.assertEqual(existing.read_bytes(), b"keep original")
            directory = root / "directory"
            directory.mkdir()
            (root / "alias").symlink_to(directory, target_is_directory=True)
            with self.assertRaisesRegex(tr.ov.OverlayError, "symlink"):
                tr.write_report(root / "alias/report.json", {"status": "passed"})
            self.assertFalse((directory / "report.json").exists())

    def test_failed_directory_fsync_does_not_publish_success_report(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / "report.json"
            original = os.fsync

            def fail_directory(descriptor):
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    raise OSError("injected directory fsync failure")
                return original(descriptor)

            with mock.patch.object(tr.os, "fsync", side_effect=fail_directory):
                with self.assertRaisesRegex(OSError, "directory fsync"):
                    tr.write_report(output, {"status": "passed"})
            self.assertFalse(output.exists())
            self.assertEqual(list(root.iterdir()), [])

    def test_published_report_must_match_actual_readback_before_returning_digest(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / "report.json"
            original = os.fsync

            def change_published(descriptor):
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    output.write_bytes(b'{"status":"changed after publication"}\n')
                return original(descriptor)

            with mock.patch.object(tr.os, "fsync", side_effect=change_published):
                with self.assertRaisesRegex(tr.ov.OverlayError, "published report"):
                    tr.write_report(output, {"status": "passed"})
            self.assertFalse(output.exists())

    def test_swapped_published_report_is_preserved_but_never_receives_success_digest(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / "report.json"
            displaced = root / "owned-report-held"
            original = os.fsync

            def replace_published(descriptor):
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    output.rename(displaced)
                    output.write_bytes(b"unrelated concurrent output")
                return original(descriptor)

            with mock.patch.object(tr.os, "fsync", side_effect=replace_published):
                with self.assertRaisesRegex(tr.ov.OverlayError, "published report"):
                    tr.write_report(output, {"status": "passed"})
            self.assertEqual(output.read_bytes(), b"unrelated concurrent output")
            self.assertEqual(json.loads(displaced.read_bytes()), {"status": "passed"})

    def test_renamed_report_parent_cannot_receive_success_for_a_replacement_path(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            parent, held = root / "reports", root / "held-reports"
            parent.mkdir()
            output = parent / "report.json"
            original = os.fsync

            def replace_parent(descriptor):
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    parent.rename(held)
                    parent.mkdir()
                    output.write_bytes(b"unrelated report at requested pathname")
                return original(descriptor)

            with mock.patch.object(tr.os, "fsync", side_effect=replace_parent):
                with self.assertRaisesRegex(tr.ov.OverlayError, "parent pathname changed"):
                    tr.write_report(output, {"status": "passed"})
            self.assertEqual(output.read_bytes(), b"unrelated report at requested pathname")
            self.assertEqual(list(parent.iterdir()), [output])

    def test_report_size_bound_precedes_any_output(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "report.json"
            with self.assertRaisesRegex(tr.ov.OverlayError, "bound"):
                tr.write_report(output, {"value": "x" * tr.MAX_REPORT_BYTES})
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(name).iterdir()), [])

    def test_cli_has_no_key_input_or_device_route_and_keeps_only_public_report(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "report.json"
            result = subprocess.run([sys.executable, str(Path(tr.__file__)), "--output", str(output)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            printed = json.loads(result.stdout)
            self.assertFalse(printed["operational_trust_established"])
            self.assertEqual(printed["report_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(list(Path(name).iterdir()), [output])
            result = subprocess.run([sys.executable, str(Path(tr.__file__)), "--output", str(output)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn(".private", result.stderr)


if __name__ == "__main__":
    unittest.main()
