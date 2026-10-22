# SPDX-License-Identifier: MIT
"""Synthetic stopped-writer fixtures; no installed device profile is qualified."""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from psp_shell.controls import EmulatorConfigAdapter
from psp_shell.ppsspp import (PPSSPPExperienceManager, PPSSPPThemeManager, PLATFORM_CONFIG,
    THEME_DIRECTORY, THEME_FILENAME, THEME_NAMES, THEME_SCHEMA_SHA256, UPSTREAM_COMMIT, UPSTREAM_VERSION)
from psp_shell.settings import SettingsError


BASE = (b'; owner settings\r\n[General]\r\nBackgroundAnimation = 1 # retain\r\n'
        b'[Theme]\r\nThemeName = "Default"\r\n[SystemParam]\r\nButtonPreference = 1\r\n'
        b'[ControlMapping]\r\nCross = 10-189\r\nCircle = 10-190\r\n')


class PPSSPPPerGameSourceIdentity(unittest.TestCase):
    def test_explicit_inventory_contract_locks_the_actual_load_and_filename_sources(self):
        source = Path(os.environ.get('PPSSPP_SOURCE_ROOT', '/workspace/ppsspp-source'))
        if not source.is_dir():
            self.skipTest('Provide the untouched pinned PPSSPP_SOURCE_ROOT')
        lock = json.loads((Path(__file__).resolve().parents[1] / 'ppsspp/theme/per-game-source-lock.json').read_text())
        for entry in lock['inputs']:
            self.assertEqual(hashlib.sha256((source / entry['path']).read_bytes()).hexdigest(), entry['sha256'])


class CommonEmulatorTransactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ppsspp-common-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.card, self.profiles = self.root / "card", self.root / "profiles"
        self.card.mkdir()
        self.profiles.mkdir()
        self.config = self.card / PLATFORM_CONFIG
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(BASE)
        self.binary = self.card / "Emu/PSP/PPSSPPSDL_TrimUI"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"synthetic executable; never run")
        digest = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        common = {"schema": 1, "id": "fixture", "device": "TRIMUI_SMART_PRO", "engine": "ppsspp",
                  "executable": "Emu/PSP/PPSSPPSDL_TrimUI", "executable_sha256": digest,
                  "config": PLATFORM_CONFIG, "qualified": True, "writer_inventory_verified": True,
                  "writer_executables": ["Emu/PSP/PPSSPPSDL_TrimUI"],
                  "per_game_inventory_verified": True, "per_game_configs": []}
        self.control_profile = {**common, "surface": "native_menu", "native_menu_extension": {
            "qualified": True, "source_commit": UPSTREAM_COMMIT, "section": "ProjectNativeMenu",
            "conventions": {position: {"IndependentMenuControls": True, "NativeMenuConfirm": position,
                "NativeMenuBack": "east" if position == "south" else "south"} for position in ("south", "east")}}}
        self.theme_profile = {**common, "source_commit": UPSTREAM_COMMIT, "source_version": UPSTREAM_VERSION,
            "theme_schema_sha256": THEME_SCHEMA_SHA256, "path_contract_verified": True,
            "installed_version": UPSTREAM_VERSION, "theme_directory": THEME_DIRECTORY}
        self.save_profiles()
        self.running, self.idle, self.in_window = False, True, False
        self.window_events = []
        self.controls = EmulatorConfigAdapter(self.card, self.root / "controls", self.profiles,
            quiescent=lambda: self.idle, process_probe=lambda _: self.running)
        self.theme = PPSSPPThemeManager(self.card, self.root / "theme", self.theme_profile,
            quiescent=lambda: self.idle, process_probe=lambda _: self.running)
        self.manager = self.make_manager()

    def save_profiles(self):
        (self.profiles / "fixture.json").write_text(json.dumps(self.control_profile))

    @contextmanager
    def window(self):
        self.assertFalse(self.in_window)
        self.in_window = True
        self.window_events.append("enter")
        try:
            yield
        finally:
            self.window_events.append("leave")
            self.in_window = False

    def make_manager(self, fault=None):
        return PPSSPPExperienceManager(self.controls, self.theme, self.root / "common",
            profile_id="fixture", write_window=self.window, fault_hook=fault)

    def preview(self):
        return self.manager.preview({"profile_id": "fixture", "confirm": "east", "theme": THEME_NAMES[1],
                                     "motion": False, "expected_generation": self.manager.status()["generation"]})

    def apply(self, preview=None, **extra):
        preview = preview or self.preview()
        return self.manager.apply({"preview_id": preview["preview_id"], "request_id": "joint-apply",
            "expected_generation": preview["generation"], **extra})

    def undo(self, result):
        return self.manager.undo({"transaction_id": result["transaction_id"], "request_id": "joint-undo",
                                  "expected_generation": result["generation"]})

    def assert_code(self, code, callback):
        with self.assertRaises(SettingsError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_one_ini_replace_and_one_lease_advances_both_generations(self):
        preview = self.preview()
        self.assertEqual(len(preview["diff"]), 5)
        self.assertEqual(self.config.read_bytes(), BASE)
        from psp_shell import settings
        write = settings._atomic_write
        config_writes = []
        def observed(path, data, *args, **kwargs):
            if path == self.config:
                self.assertTrue(self.in_window)
                config_writes.append(data)
            return write(path, data, *args, **kwargs)
        self.window_events.clear()
        with patch.object(settings, "_atomic_write", side_effect=observed):
            result = self.apply(preview)
        self.assertEqual(self.window_events, ["enter", "leave"])
        self.assertEqual(len(config_writes), 1)
        self.assertEqual((result["generation"], result["controls_generation"], result["appearance_generation"]), (1, 1, 1))
        text = self.config.read_text()
        self.assertIn('IndependentMenuControls = "true"', text)
        self.assertIn('NativeMenuConfirm = "east"', text)
        self.assertIn('ThemeName = "Spruce Midnight High Contrast"', text)
        self.assertIn('BackgroundAnimation = 0 # retain', text)
        self.assertIn('ButtonPreference = 1', text)
        self.assertIn('Cross = 10-189', text)
        self.assertTrue(self.apply(preview)["idempotent"])

    def test_targeted_joint_undo_restores_original_keys_and_preserves_external_lines(self):
        result = self.apply()
        self.config.write_bytes(self.config.read_bytes() + b'; external annotation\r\n')
        undone = self.undo(result)
        self.assertEqual(self.config.read_bytes().split(b'; external annotation')[0].split(b'[ProjectNativeMenu]')[0], BASE)
        self.assertTrue(self.config.read_bytes().endswith(b'; external annotation\r\n'))
        self.assertNotIn(b'NativeMenuConfirm', self.config.read_bytes())
        self.assertEqual(undone["controls_generation"], 2)
        self.assertEqual(undone["appearance_generation"], 2)
        self.assertTrue(undone["theme_file_retained_unselected"])
        self.assertTrue(self.undo(result)["idempotent"])

    def test_joint_undo_restores_preexisting_palette_and_exact_config(self):
        palette = self.card / THEME_DIRECTORY / THEME_FILENAME
        palette.parent.mkdir(parents=True)
        palette.write_bytes(b'; owner custom palette\n')
        preview = self.preview()
        self.assertTrue(preview["overwrites_existing_theme"])
        self.assert_code("OVERWRITE_CONFIRMATION_REQUIRED", lambda: self.apply(preview))
        result = self.apply(preview, confirm_overwrite=True)
        self.undo(result)
        self.assertEqual(palette.read_bytes(), b'; owner custom palette\n')
        self.assertEqual(self.config.read_bytes(), BASE)

    def test_each_partial_replace_failure_rolls_back_all_five_files(self):
        palette = self.card / THEME_DIRECTORY / THEME_FILENAME
        for failed_index in range(5):
            def fault(point, index):
                if point == "after_replace" and index == failed_index:
                    raise RuntimeError("injected storage failure")
            self.manager = self.make_manager(fault)
            with self.assertRaises(RuntimeError):
                self.apply()
            self.assertEqual(self.config.read_bytes(), BASE)
            self.assertFalse(palette.exists())
            self.assertEqual(self.manager.status()["generation"], 0)
            self.assertEqual(self.controls._state()["generation"], 0)
            self.assertEqual(self.theme._state()["generation"], 0)

    def test_process_death_reopens_and_recovers_both_adapter_generations(self):
        class ProcessDeath(BaseException):
            pass
        def fault(point, index):
            if point == "after_replace" and index == 3:
                raise ProcessDeath()
        self.manager = self.make_manager(fault)
        with self.assertRaises(ProcessDeath):
            self.apply()
        self.assertEqual(self.controls._state()["generation"], 1)
        self.assertEqual(self.theme._state()["generation"], 1)
        self.manager = self.make_manager()
        self.assertEqual(self.config.read_bytes(), BASE)
        self.assertEqual(self.controls._state()["generation"], 0)
        self.assertEqual(self.theme._state()["generation"], 0)
        self.assertEqual(self.manager.status()["generation"], 0)

    def test_external_owned_edit_blocks_entire_undo_before_a_write(self):
        result = self.apply()
        self.config.write_bytes(self.config.read_bytes().replace(b'NativeMenuConfirm = "east"', b'NativeMenuConfirm = "south"'))
        before = self.config.read_bytes()
        self.assert_code("UNDO_CONFLICT", lambda: self.undo(result))
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(self.controls._state()["generation"], 1)

    def test_component_transactions_and_changed_sources_invalidate_joint_preview(self):
        preview = self.preview()
        cp = self.controls.preview({"profile_id": "fixture", "confirm": "east", "expected_generation": 0})
        self.controls.apply({"preview_id": cp["preview_id"], "request_id": "separate", "expected_generation": 0})
        self.assert_code("STALE_SNAPSHOT", lambda: self.apply(preview))

    def test_busy_writer_and_unqualified_overlay_inventory_refuse_all_writes(self):
        preview = self.preview()
        self.running = True
        self.assert_code("BUSY_GAME", lambda: self.apply(preview))
        self.assertEqual(self.config.read_bytes(), BASE)
        self.running = False
        self.control_profile["per_game_inventory_verified"] = False
        self.save_profiles()
        self.assert_code("UNSUPPORTED_PROFILE", lambda: self.apply(preview))

    def test_writer_start_during_commit_defers_recovery_until_the_writer_stops(self):
        def fault(point, index):
            if point == "after_replace" and index == 0:
                self.running = True
        self.manager = self.make_manager(fault)
        self.assert_code("BUSY_GAME", lambda: self.apply())
        self.assertEqual(self.config.read_bytes(), BASE)
        palette = self.card / THEME_DIRECTORY / THEME_FILENAME
        self.assertTrue(palette.exists())
        self.running = False
        self.manager = self.make_manager()
        self.assertFalse(palette.exists())
        self.assertEqual(self.manager.status()["generation"], 0)

    def test_explicit_per_game_overrides_are_reported_and_preserved(self):
        overlay = self.config.parent / "ULUS12345_ppsspp.ini"
        raw = b'[ProjectNativeMenu]\nNativeMenuConfirm = "south"\n[Graphics]\nFrameSkip = 3\n'
        overlay.write_bytes(raw)
        relative = overlay.relative_to(self.card).as_posix()
        self.control_profile["per_game_configs"] = [relative]
        self.theme_profile["per_game_configs"] = [relative]
        self.save_profiles()
        self.theme.profile_source = copy.deepcopy(self.theme_profile)
        status = self.manager.status()
        self.assertEqual(status["per_game_overrides"][0]["overrides"][0]["key"], "NativeMenuConfirm")
        preview = self.preview()
        self.apply(preview)
        self.assertEqual(overlay.read_bytes(), raw)
        self.assertEqual(len(preview["per_game_overrides"]), 1)

    def test_changed_per_game_overlay_invalidates_preview(self):
        overlay = self.config.parent / "ULUS12345_ppsspp.ini"
        overlay.write_bytes(b'[Graphics]\nFrameSkip = 1\n')
        relative = overlay.relative_to(self.card).as_posix()
        self.control_profile["per_game_configs"] = self.theme_profile["per_game_configs"] = [relative]
        self.save_profiles()
        self.theme.profile_source = copy.deepcopy(self.theme_profile)
        preview = self.preview()
        overlay.write_bytes(b'[Graphics]\nFrameSkip = 2\n')
        self.assert_code("STALE_SNAPSHOT", lambda: self.apply(preview))
        self.assertEqual(self.config.read_bytes(), BASE)

    def test_new_uninventoried_game_file_refuses_common_write(self):
        preview = self.preview()
        overlay = self.config.parent / "ULUS12345_ppsspp.ini"
        raw = b'[Theme]\nThemeName = "Owner override"\n'
        overlay.write_bytes(raw)
        status = self.manager.status()
        self.assertFalse(status['adoption_available'])
        self.assertEqual(status['gate_reason'], 'PER_GAME_INVENTORY_CHANGED')
        self.assert_code('PER_GAME_INVENTORY_CHANGED', lambda: self.apply(preview))
        self.assertEqual(self.config.read_bytes(), BASE)
        self.assertEqual(overlay.read_bytes(), raw)

    def test_modified_undo_metadata_cannot_insert_an_unreviewed_value(self):
        result = self.apply()
        path = self.manager.state_dir / 'transactions' / (result['transaction_id'] + '.json')
        journal = json.loads(path.read_bytes())
        journal['metadata']['diff'][0]['before_present'] = True
        journal['metadata']['diff'][0]['before_token'] = '"tampered"'
        path.write_text(json.dumps(journal))
        self.config.write_bytes(self.config.read_bytes() + b'; unrelated external comment\n')
        before = self.config.read_bytes()
        self.assert_code('UNDO_CONFLICT', lambda: self.undo(result))
        self.assertEqual(self.config.read_bytes(), before)

    def test_tampered_preview_cannot_add_gameplay_changes(self):
        preview = self.preview()
        path = self.manager.previews / (preview["preview_id"] + ".json")
        record = json.loads(path.read_text())
        record["diff"].append({"section": "ControlMapping", "key": "Cross", "after": "bad"})
        path.write_text(json.dumps(record))
        self.assert_code("STALE_SNAPSHOT", lambda: self.apply(preview))
        self.assertEqual(self.config.read_bytes(), BASE)


if __name__ == "__main__":
    unittest.main()
