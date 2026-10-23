"""Pinned USB launcher branches with disposable device/service substitutes.

The real launcher source runs after replacing its three absolute imports and
shutdown executable with fixture dependencies. No gadget, mount, reboot,
display, service signal or physical device is touched.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("SPRUCE_SOURCE_ROOT", "/workspace/spruce-base"))
LAUNCHER = "App/USBStorageMode/launch.sh"
PATCH = "0004-usb-refuse-unstaged-export.patch"


class UsbStoragePatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original = SOURCE / LAUNCHER
        if not original.is_file():
            raise unittest.SkipTest("Untouched pinned spruce source not available; set SPRUCE_SOURCE_ROOT")
        manifest = json.loads((PROJECT / "patches/manifest.json").read_text())
        item = next(item for item in manifest["patches"] if item["patch"] == PATCH)
        if item["path"] != LAUNCHER or hashlib.sha256(original.read_bytes()).hexdigest() != item["base_sha256"]:
            raise AssertionError("Unexpected pinned USB launcher bytes")
        cls.temp = tempfile.TemporaryDirectory()
        cls.patched_root = Path(cls.temp.name)
        target = cls.patched_root / LAUNCHER
        target.parent.mkdir(parents=True)
        shutil.copyfile(original, target)
        patch = PROJECT / "patches" / PATCH
        for args in (["git", "apply", "--check", str(patch)], ["git", "apply", str(patch)]):
            subprocess.run(args, cwd=cls.patched_root, check=True, capture_output=True, text=True)
        if hashlib.sha256(target.read_bytes()).hexdigest() != item["patched_sha256"]:
            raise AssertionError("Unexpected patched USB launcher bytes")
        cls.original = original.read_text()
        cls.patched = target.read_text()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def probe(self, patched, *, stage_status=1, handoff_status=0, helper_present=True, platform="SmartPro"):
        with tempfile.TemporaryDirectory(prefix="usb launcher fixture ") as temp:
            root = Path(temp)
            source = self.patched if patched else self.original
            for dependency in (
                    ". /mnt/SDCARD/spruce/scripts/helperFunctions.sh",
                    ". /mnt/SDCARD/spruce/scripts/runtimeHelper.sh",
                    ". /mnt/SDCARD/App/USBStorageMode/usb_gadget.sh"):
                self.assertEqual(source.count(dependency), 1)
                source = source.replace(dependency, ": # imported functions supplied by fixture", 1)
            assignment = "SAVE_POWEROFF=/mnt/SDCARD/spruce/scripts/save_poweroff.sh"
            self.assertEqual(source.count(assignment), 1)
            source = source.replace(assignment, 'SAVE_POWEROFF="$PROBE_ROOT/save_poweroff"', 1)
            if helper_present:
                helper = root / "save_poweroff"
                helper.write_text('#!/bin/sh\nprintf "handoff:%s\\n" "$*" >> "$PROBE_ROOT/events"\n'
                                  'exit "$PROBE_HANDOFF_STATUS"\n')
                helper.chmod(0o755)
            substitutes = r'''
record() { printf '%s\n' "$*" >> "$PROBE_ROOT/events"; }
usb_gadget_platform_setup() { record platform_setup; return 0; }
start_pyui_message_writer() { record "message_start:$*"; }
stop_pyui_message_writer() { record message_stop; }
log_message() { printf '%s\n' "$*"; }
log_and_display_message() { printf '%s\n' "$*"; }
usb_host_connected() { return 0; }
confirm() { return 0; }
killall() { record "killall:$*"; }
sleep() { record "sleep:$*"; }
sync() { record sync; }
usb_session_stage() { record "stage:$PROBE_STAGE_STATUS"; return "$PROBE_STAGE_STATUS"; }
configure_usb_gadget() { record legacy_export_of_mounted_card; }
usb_gadget_release() { record gadget_release; }
device_run_reboot_cmd() { record direct_reboot; exit 88; }
'''
            environment = dict(os.environ, PROBE_ROOT=str(root), PROBE_STAGE_STATUS=str(stage_status),
                               PROBE_HANDOFF_STATUS=str(handoff_status), PLATFORM=platform)
            result = subprocess.run(["sh", "-c", substitutes + "\n" + source], env=environment,
                                    capture_output=True, text=True, timeout=5)
            events = (root / "events").read_text().splitlines()
            return result, events

    def test_pinned_staging_failure_reproduces_legacy_mounted_export(self):
        result, events = self.probe(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stage:1", events)
        self.assertIn("legacy_export_of_mounted_card", events)
        self.assertIn("handoff:--reboot --usb-storage", events)

    def test_patch_refuses_every_failed_stage_without_export_or_reboot(self):
        for status in (1, 2, 74):
            with self.subTest(status=status):
                result, events = self.probe(True, stage_status=status)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("stage:" + str(status), events)
                self.assertNotIn("legacy_export_of_mounted_card", events)
                self.assertFalse(any(event.startswith("handoff:") for event in events))
                self.assertNotIn("gadget_release", events)
                self.assertNotIn("direct_reboot", events)
                self.assertIn("refusing to export the mounted SD card", result.stdout)
                self.assertIn("The SD card was not exported.", result.stdout)

    def test_successful_stage_keeps_existing_shutdown_handoff_and_platform_message(self):
        for platform in ("SmartPro", "AnbernicRG28XX"):
            with self.subTest(platform=platform):
                original, original_events = self.probe(False, stage_status=0, platform=platform)
                patched, patched_events = self.probe(True, stage_status=0, platform=platform)
                self.assertEqual(patched.returncode, 0, patched.stderr)
                self.assertEqual(patched_events, original_events)
                self.assertEqual(patched.stdout, original.stdout)
                self.assertIn("handoff:--usb-storage-export", patched_events)
                self.assertNotIn("legacy_export_of_mounted_card", patched_events)
                self.assertEqual(patched_events.count("message_stop"), 1)
                self.assertLess(patched_events.index("message_stop"), patched_events.index("handoff:--usb-storage-export"))

    def test_failed_or_missing_shutdown_helper_cannot_fall_back_to_export(self):
        for present in (True, False):
            with self.subTest(helper_present=present):
                result, events = self.probe(True, stage_status=0, handoff_status=61, helper_present=present)
                self.assertEqual(result.returncode, 61 if present else 127, result.stderr)
                self.assertNotIn("legacy_export_of_mounted_card", events)
                self.assertNotIn("gadget_release", events)
                self.assertNotIn("direct_reboot", events)

    def test_patch_keeps_the_source_prelude_and_staged_path_byte_for_byte(self):
        marker = 'log_message "USB Storage Mode: session staging failed, falling back to the mounted export"\n'
        self.assertTrue(self.patched.startswith(self.original.split(marker, 1)[0]))


if __name__ == "__main__":
    unittest.main()
