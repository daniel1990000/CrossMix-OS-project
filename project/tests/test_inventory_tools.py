# SPDX-License-Identifier: MIT
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import inventory
import support_bundle


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spruce-inventory-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.device = self.root / "device"
        self.card = self.root / "card"
        self.device.mkdir()
        self.card.mkdir()

    def put(self, root, name, contents):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
        return path

    def test_pure_collection_preserves_lists_and_never_reads_secrets(self):
        self.put(self.device, "proc/cpuinfo", "Hardware: TG5040\nSerial: PRIVATE-SERIAL")
        self.put(self.device, "etc/version", "1.1.1\n")
        self.put(self.device, "etc/wpa_supplicant.conf", "psk=DO-NOT-READ")
        original = b'[{"rom_file_path":"/mnt/SDCARD/Roms/GBA/a.gba","unknown":"preserve"}]\n'
        path = self.put(self.card, "Saves/pyui-favorites.json", original)
        self.put(self.card, "Saves/spruce/spruce-config.json", '{"password":"DO-NOT-READ"}')
        before = path.stat().st_mtime_ns
        report = inventory.collect(self.device, self.card)
        encoded = json.dumps(report)
        self.assertEqual(report["device"]["model"], "trimui-smart-pro")
        self.assertEqual(report["device"]["firmware"], "1.1.1")
        self.assertEqual(report["frontend_lists_summary_only"]["pyui-favorites.json"]["count"], 1)
        self.assertNotIn("DO-NOT-READ", encoded)
        self.assertNotIn("PRIVATE-SERIAL", encoded)
        self.assertNotIn("a.gba", encoded)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_unknown_and_other_models_stay_unsupported(self):
        self.assertIsNone(inventory.collect(self.device, self.card)["device"]["model"])
        self.put(self.device, "proc/device-tree/model", "TrimUI Smart Pro S")
        self.assertIsNone(inventory.collect(self.device, self.card)["device"]["model"])

    def test_source_hash_match_then_changed_source_is_reported(self):
        data = b"pinned spruce contract\n"
        path = self.put(self.card, "spruce/scripts/runtime.sh", data)
        git_hash = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        profile = {"id": "fixture", "base_commit": "a" * 40, "pyui_git_tree": "b" * 40,
                   "baseline_files": {"spruce/scripts/runtime.sh": git_hash}}
        report = inventory.collect(self.device, self.card, profile)
        self.assertTrue(report["source_profile_verified"])
        self.assertEqual(report["device"]["base_commit"], "a" * 40)
        path.write_text("changed")
        report = inventory.collect(self.device, self.card, profile)
        self.assertFalse(report["source_profile_verified"])
        self.assertIsNone(report["device"]["base_commit"])

    def test_symlink_escape_and_oversize_are_not_collected(self):
        outside = self.put(self.root, "secret", "psk=private")
        (self.device / "etc").mkdir()
        (self.device / "etc/version").symlink_to(outside)
        self.assertIsNone(inventory.read_at(self.device, "etc/version"))
        huge = self.put(self.device, "proc/version", b"x" * (inventory.MAX_TEXT + 1))
        self.assertIsNone(inventory.bounded_read(huge))

    def test_fifo_metadata_is_refused_without_waiting_for_a_writer(self):
        path = self.device / "named-pipe"
        os.mkfifo(path)
        self.assertIsNone(inventory.bounded_read(path))
        self.assertIsNone(inventory.hash_at(self.device, "named-pipe"))

    def test_file_growth_during_hashing_is_rejected_with_a_finite_read(self):
        path = self.put(self.device, "growing", b"original bytes")
        actual = hashlib.sha256()
        class GrowingHash:
            def update(self, block):
                actual.update(block)
                with path.open("ab") as stream:
                    stream.write(b"new bytes")
        with patch.object(inventory.hashlib, "sha256", return_value=GrowingHash()):
            self.assertIsNone(inventory.hash_at(self.device, "growing"))

    def test_mount_credentials_and_process_arguments_absent(self):
        self.put(self.device, "proc/mounts", "//user:password@192.168.0.1/share /mnt/share cifs rw,password=hunter2,username=foo 0 0\n")
        self.put(self.device, "proc/1/comm", "runtime")
        self.put(self.device, "proc/1/cmdline", "runtime --token secret-value")
        report = inventory.collect(self.device, self.card)
        text = json.dumps(report)
        self.assertNotIn("hunter2", text)
        self.assertNotIn("secret-value", text)
        self.assertNotIn("192.168", text)
        self.assertEqual(report["mounts"][0]["flags"], ["rw"])

    def test_explicit_output_refuses_save_folder_and_existing(self):
        output = self.root / "inventory.json"
        inventory.write_output(output, {}, self.card)
        with self.assertRaises(ValueError):
            inventory.write_output(output, {}, self.card)
        (self.root / "Saves").mkdir()
        with self.assertRaises(ValueError):
            inventory.write_output(self.root / "Saves/report.json", {}, self.card)

    def test_support_bundle_is_local_and_redacts_structured_and_raw_data(self):
        report = self.put(self.root, "inventory.json", json.dumps({"device": {"model": "trimui-smart-pro"}, "password": "HIDDEN"}))
        raw = self.put(self.root, "selected.log", "Authorization: Bearer SECRET\nWiFi 192.168.1.2 aa:bb:cc:dd:ee:ff\n/home/daniel/log\nRoms/GBA/PrivateGame.gba")
        output = self.root / "support.json"
        result = support_bundle.export(report, [raw], output)
        text = output.read_text()
        for secret in ("HIDDEN", "SECRET", "192.168", "aa:bb", "daniel", "PrivateGame"):
            self.assertNotIn(secret, text)
        self.assertFalse(result["uploaded"])
        self.assertEqual(result["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())

    def test_cli_requires_explicit_output(self):
        cmd = [sys.executable, str(PROJECT / "tools/inventory.py"), "--root", str(self.device), "--sd-root", str(self.card)]
        self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        output = self.root / "report.json"
        completed = subprocess.run(cmd + ["--output", str(output)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output.is_file())

    def test_support_redacts_complete_private_paths_in_values_and_keys(self):
        private_paths = [
            "Saves/saves/Private Game.sav",
            '/mnt/SDCARD/Roms/PSP/Owner "Special" Game.iso',
            "Saves/saves/Owner's Game.sav",
            "Saves/saves/Private\nGame.sav",
            r"C:\card\Saves\Private Game.sav",
        ]
        diagnostic = self.put(self.root, "paths.json", json.dumps({
            "selected": private_paths,
            "by_path": {path: "private associated metadata" for path in private_paths},
            "note": "changed: " + private_paths[0],
            "status": "FAILED",
        }))
        report = self.put(self.root, "inventory.json", "{}")
        output = self.root / "support-paths.json"
        support_bundle.export(report, [diagnostic], output)
        text = output.read_text()
        for fragment in ("Private", "Owner", "Special", ".sav", ".iso", "associated metadata"):
            self.assertNotIn(fragment, text)
        data = json.loads(text)["entries"][1]["data"]
        self.assertEqual(len(data["by_path"]), len(private_paths))
        self.assertEqual(data["status"], "FAILED")

    def test_support_raw_path_with_spaces_does_not_leak_filename_suffix(self):
        report = self.put(self.root, "inventory.json", "{}")
        diagnostic = self.put(self.root, "selected.log", "changed Saves/saves/Private Game Name.sav after test")
        output = self.root / "support-raw-path.json"
        support_bundle.export(report, [diagnostic], output)
        self.assertNotIn("Game Name", output.read_text())

    def test_support_refuses_config_journals_and_strips_encoded_snapshots(self):
        report = self.put(self.root, "inventory.json", "{}")
        private = self.put(self.root, "transactions/one/journal.json", '{"before":"c2VjcmV0"}')
        with self.assertRaisesRegex(ValueError, "snapshots"):
            support_bundle.export(report, [private], self.root / "blocked.json")
        diagnostic = self.put(self.root, "diagnostic.json", '{"snapshot":"c2VjcmV0","code":"FAILED","content_base64":"c2VjcmV0"}')
        support_bundle.export(report, [diagnostic], self.root / "safe.json")
        self.assertNotIn("c2VjcmV0", (self.root / "safe.json").read_text())


if __name__ == "__main__":
    unittest.main()
