# SPDX-License-Identifier: MIT
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from psp_shell.ppsspp import (
    COLOR_KEYS, PLATFORM_CONFIG, PPSSPPThemeManager, THEME_DIRECTORY, THEME_FILENAME,
    THEME_NAMES, THEME_SCHEMA_SHA256, UPSTREAM_COMMIT, UPSTREAM_VERSION,
    palette_contrast, validate_theme,
)
from psp_shell.settings import SettingsError


THEME_SOURCE = Path(__file__).resolve().parents[1] / "ppsspp/theme/spruce-midnight.ini"
BASE_CONFIG = (b'; original config\r\n[General]\r\nBackgroundAnimation = 1 ; keep note\r\n'
               b'Language = en_US\r\n[Theme]\r\nThemeName = "Default" ; keep theme note\r\n'
               b'[SystemParam]\r\nButtonPreference = 1\r\n[Graphics]\r\nFrameSkip = 0\r\n')


class ThemeDataTests(unittest.TestCase):
    def test_original_theme_uses_only_real_ppsspp_keys_and_colors(self):
        result = validate_theme(THEME_SOURCE.read_bytes())
        self.assertEqual(result["names"], list(THEME_NAMES))
        self.assertFalse(result["custom_fonts_or_icons"])
        for colors in result["colors"].values():
            self.assertEqual(set(colors), COLOR_KEYS)
            self.assertGreater(palette_contrast(colors["ItemFocusedStyleFg"], colors["ItemFocusedStyleBg"]), 7)
            self.assertGreater(palette_contrast(colors["PopupStyleFg"], colors["PopupStyleBg"]), 7)
        self.assertEqual(result["colors"]["Spruce Midnight"]["ItemFocusedStyleBg"], "#64FFDFFF")

    def test_theme_keys_match_pinned_actual_parser_when_source_available(self):
        source = Path(os.environ.get("PPSSPP_SOURCE_ROOT", "/workspace/ppsspp-source")) / "UI/Theme.cpp"
        if not source.exists():
            self.skipTest("Pinned PPSSPP source checkout is optional for source-contract test")
        data = source.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), THEME_SCHEMA_SHA256)
        actual = set(re.findall(r'section.Get\("([^"]+)"', data.decode()))
        self.assertEqual(actual, COLOR_KEYS | {"Name"})

    def test_theme_rejects_unknown_keys_duplicate_values_and_wrong_color_format(self):
        data = THEME_SOURCE.read_bytes()
        candidates = [data + b'\nFont = "ripped-font.ttf"\n',
                      data.replace(b'Name = "Spruce Midnight"', b'Name = "Wrong"', 1),
                      data.replace(b'"#64FFDFFF"', b'0xFFDDFF64', 1),
                      data.replace(b'ItemStyleFg =', b'ItemStyleFg = "#FFFFFFFF"\nItemStyleFg =', 1)]
        for candidate in candidates:
            with self.subTest(candidate=candidate[-40:]), self.assertRaises(SettingsError):
                validate_theme(candidate)


class ThemeTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.sd = base / "card"
        self.sd.mkdir()
        self.state = base / "state"
        self.config = self.sd / PLATFORM_CONFIG
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(BASE_CONFIG)
        self.binary = self.sd / "Emu/PSP/PPSSPPSDL_TrimUI"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'host fake executable; never run')
        self.profile = {
            "schema": 1, "id": "host-fixture-ppsspp-theme", "engine": "ppsspp", "device": "TRIMUI_SMART_PRO",
            "source_commit": UPSTREAM_COMMIT, "source_version": UPSTREAM_VERSION,
            "theme_schema_sha256": THEME_SCHEMA_SHA256,
            "qualified": True, "writer_inventory_verified": True, "path_contract_verified": True,
            "installed_version": UPSTREAM_VERSION, "executable": "Emu/PSP/PPSSPPSDL_TrimUI",
            "executable_sha256": hashlib.sha256(self.binary.read_bytes()).hexdigest(),
            "writer_executables": ["Emu/PSP/PPSSPPSDL_TrimUI"],
            "config": PLATFORM_CONFIG, "theme_directory": THEME_DIRECTORY,
            "evidence": "host fixture only; no target compatibility claim"}
        self.idle, self.running = True, False
        self.manager = self.make_manager()

    def make_manager(self, profile=None, fault=None):
        return PPSSPPThemeManager(self.sd, self.state, profile or self.profile,
            quiescent=lambda: self.idle, process_probe=lambda path: self.running,
            theme_file=THEME_SOURCE, fault_hook=fault)

    def preview(self, theme="Spruce Midnight", motion=True):
        return self.manager.preview({"theme": theme, "motion": motion,
                                     "expected_generation": self.manager.status()["generation"]})

    def apply(self, preview=None, request="install-1", overwrite=False):
        preview = preview or self.preview()
        return self.manager.apply({"preview_id": preview["preview_id"], "expected_generation": preview["generation"],
                                   "request_id": request, "confirm_overwrite": overwrite})

    def undo(self, installed, request="undo-1"):
        return self.manager.undo({"transaction_id": installed["transaction_id"],
            "expected_generation": self.manager.status()["generation"], "request_id": request})

    def test_preview_does_not_modify_platform_config_engine_or_add_theme(self):
        before_binary = self.binary.read_bytes()
        preview = self.preview()
        self.assertTrue(preview["adoption_available"])
        self.assertEqual(self.config.read_bytes(), BASE_CONFIG)
        self.assertEqual(self.binary.read_bytes(), before_binary)
        self.assertFalse((self.sd / THEME_DIRECTORY / THEME_FILENAME).exists())
        self.assertEqual({(item["section"], item["key"]) for item in preview["diff"]},
                         {("Theme", "ThemeName"), ("General", "BackgroundAnimation")})

    def test_apply_uses_native_theme_wave_and_keeps_unowned_settings_bytes(self):
        preview = self.preview()
        installed = self.apply(preview)
        data = self.config.read_bytes()
        self.assertIn(b'ThemeName = "Spruce Midnight" ; keep theme note\r\n', data)
        self.assertIn(b'BackgroundAnimation = 3 ; keep note\r\n', data)
        self.assertIn(b'ButtonPreference = 1\r\n[Graphics]\r\nFrameSkip = 0\r\n', data)
        self.assertEqual((self.sd / THEME_DIRECTORY / THEME_FILENAME).read_bytes(), THEME_SOURCE.read_bytes())
        self.assertFalse(installed["gameplay_changed"])
        replay = self.apply(preview)
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["generation"], installed["generation"])

    def test_high_contrast_and_reduced_motion_use_supported_existing_settings(self):
        self.apply(self.preview(THEME_NAMES[1], False))
        self.assertIn(b'BackgroundAnimation = 0 ', self.config.read_bytes())
        self.assertIn(THEME_NAMES[1].encode(), self.config.read_bytes())

    def test_undo_restores_owned_settings_and_keeps_later_unrelated_edits(self):
        installed = self.apply()
        self.config.write_bytes(self.config.read_bytes().replace(b'FrameSkip = 0', b'FrameSkip = 1'))
        undone = self.undo(installed)
        self.assertEqual(self.config.read_bytes(), BASE_CONFIG.replace(b'FrameSkip = 0', b'FrameSkip = 1'))
        self.assertTrue(undone["theme_file_retained_unselected"])
        self.assertEqual(self.manager.status()["theme"], "Default")

    def test_undo_conflict_preserves_external_theme_selection(self):
        installed = self.apply()
        self.config.write_bytes(self.config.read_bytes().replace(b'"Spruce Midnight"', b'"Dark"'))
        before = self.config.read_bytes()
        with self.assertRaises(SettingsError) as error:
            self.undo(installed)
        self.assertEqual(error.exception.code, "UNDO_CONFLICT")
        self.assertEqual(self.config.read_bytes(), before)

    def test_existing_theme_requires_confirmed_overwrite_and_is_restored_on_undo(self):
        target = self.sd / THEME_DIRECTORY / THEME_FILENAME
        target.parent.mkdir(parents=True)
        target.write_bytes(b'; user customized existing file\n[My Theme]\n')
        preview = self.preview()
        self.assertTrue(preview["overwrites_existing_theme"])
        with self.assertRaises(SettingsError):
            self.apply(preview)
        installed = self.apply(preview, overwrite=True)
        self.undo(installed)
        self.assertEqual(target.read_bytes(), b'; user customized existing file\n[My Theme]\n')

    def test_unknown_build_hash_version_and_busy_writer_block_apply(self):
        for field, value in (("qualified", False), ("installed_version", "unknown"),
                             ("path_contract_verified", False), ("executable_sha256", "0" * 64)):
            profile = copy.deepcopy(self.profile)
            profile[field] = value
            manager = self.make_manager(profile)
            preview = manager.preview({"theme": THEME_NAMES[0], "motion": True, "expected_generation": 0})
            self.assertFalse(preview["adoption_available"])
            with self.assertRaises(SettingsError):
                manager.apply({"preview_id": preview["preview_id"], "expected_generation": 0, "request_id": "blocked-" + field})
            self.assertEqual(self.config.read_bytes(), BASE_CONFIG)
        self.running = True
        with self.assertRaises(SettingsError) as error:
            self.apply()
        self.assertEqual(error.exception.code, "BUSY_GAME")

    def test_stale_preview_or_tampered_diff_cannot_change_gameplay(self):
        preview = self.preview()
        path = self.state / "previews" / (preview["preview_id"] + ".json")
        value = json.loads(path.read_text())
        value["diff"][0].update(section="SystemParam", key="ButtonPreference", after="0")
        path.write_text(json.dumps(value))
        with self.assertRaises(SettingsError) as error:
            self.apply(preview)
        self.assertEqual(error.exception.code, "INVALID_PREVIEW")
        self.assertEqual(self.config.read_bytes(), BASE_CONFIG)

    def test_failed_second_replace_rolls_back_theme_config_and_generation(self):
        def fault(point, index):
            if point == "after_replace" and index == 1:
                raise RuntimeError("simulated interrupted apply")
        self.manager = self.make_manager(fault=fault)
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertEqual(self.config.read_bytes(), BASE_CONFIG)
        self.assertFalse((self.sd / THEME_DIRECTORY / THEME_FILENAME).exists())
        self.assertEqual(self.manager.status()["generation"], 0)

    def test_reopening_after_process_death_recovers_partial_adoption(self):
        class ProcessDeath(BaseException):
            pass
        def fault(point, index):
            if point == "after_replace" and index == 1:
                raise ProcessDeath()
        self.manager = self.make_manager(fault=fault)
        with self.assertRaises(ProcessDeath):
            self.apply()
        self.assertIn(b'"Spruce Midnight"', self.config.read_bytes())
        self.manager = self.make_manager()
        self.assertEqual(self.config.read_bytes(), BASE_CONFIG)
        self.assertFalse((self.sd / THEME_DIRECTORY / THEME_FILENAME).exists())

    def test_theme_destination_symlink_is_rejected(self):
        target = self.sd / THEME_DIRECTORY
        target.parent.mkdir(parents=True, exist_ok=True)
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        target.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(SettingsError):
            self.make_manager()


if __name__ == "__main__":
    unittest.main()
