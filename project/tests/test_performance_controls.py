# SPDX-License-Identifier: MIT
"""Real transaction machinery with disposable installed-profile fixtures."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from psp_shell.controls import EmulatorConfigAdapter
from psp_shell.performance import PPSSPPPerformanceManager, unavailable_status, PRESETS
from psp_shell.ppsspp import (PPSSPPExperienceManager, PPSSPPThemeManager, PLATFORM_CONFIG,
                             THEME_DIRECTORY, THEME_SCHEMA_SHA256, UPSTREAM_COMMIT, UPSTREAM_VERSION)
from psp_shell.settings import SettingsError


GLOBAL = (b'; global owner settings\r\n[Graphics]\r\nInternalResolution = 3\r\nFrameSkip = 0\r\n'
          b'AutoFrameSkip = False\r\nSkipBufferEffects = False\r\n[Theme]\r\nThemeName = "Default"\r\n')
GAME = (b'; per-game owner settings\r\n[Graphics]\r\nInternalResolution = 2 # owner\r\n'
        b'VertexCache = False\r\n[ControlMapping]\r\nCross = 10-189\r\n')


class PerformanceTransactions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="performance-controls-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.card = self.root / "card"
        self.card.mkdir()
        self.config = self.card / PLATFORM_CONFIG
        self.config.parent.mkdir(parents=True)
        self.config.write_bytes(GLOBAL)
        self.game = self.config.parent / "ULUS00001_ppsspp.ini"
        self.game.write_bytes(GAME)
        self.other = self.config.parent / "ULUS00002_ppsspp.ini"
        self.other.write_bytes(b'[Graphics]\nInternalResolution = 4\n')
        self.binary = self.card / "Emu/PSP/PPSSPPSDL_TrimUI"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'synthetic never-executed engine')
        self.rom = self.card / "Roms/PSP/game.iso"
        self.rom.parent.mkdir(parents=True)
        self.rom.write_bytes(b'synthetic disposable game content; never executed')
        self.selected_preset = "PPSSPP"
        self.native_game_id = "ULUS00001"
        self.selected_engine = "ppsspp"
        self.profiles = self.root / "profiles"
        self.profiles.mkdir()
        common = {"schema": 1, "id": "fixture", "device": "TRIMUI_SMART_PRO", "engine": "ppsspp",
                  "executable": "Emu/PSP/PPSSPPSDL_TrimUI", "executable_sha256": hashlib.sha256(self.binary.read_bytes()).hexdigest(),
                  "config": PLATFORM_CONFIG, "qualified": True, "writer_inventory_verified": True,
                  "writer_executables": ["Emu/PSP/PPSSPPSDL_TrimUI"], "per_game_inventory_verified": True,
                  "per_game_configs": [path.relative_to(self.card).as_posix() for path in (self.game, self.other)]}
        self.control_profile = {**common, "surface": "native_menu", "native_menu_extension": {
            "qualified": True, "source_commit": UPSTREAM_COMMIT, "section": "ProjectNativeMenu",
            "conventions": {position: {"IndependentMenuControls": True, "NativeMenuConfirm": position,
                "NativeMenuBack": "east" if position == "south" else "south"} for position in ("south", "east")}}}
        self.theme_profile = {**common, "source_commit": UPSTREAM_COMMIT, "source_version": UPSTREAM_VERSION,
            "theme_schema_sha256": THEME_SCHEMA_SHA256, "path_contract_verified": True,
            "installed_version": UPSTREAM_VERSION, "theme_directory": THEME_DIRECTORY}
        (self.profiles / "fixture.json").write_text(json.dumps(self.control_profile))
        self.running = False
        self.idle = True
        self.leases = 0
        self.controls = EmulatorConfigAdapter(self.card, self.root / "controls", self.profiles,
            quiescent=lambda: self.idle, process_probe=lambda _: self.running)
        self.appearance = PPSSPPThemeManager(self.card, self.root / "appearance", self.theme_profile,
            quiescent=lambda: self.idle, process_probe=lambda _: self.running)
        self.experience = PPSSPPExperienceManager(self.controls, self.appearance, self.root / "experience",
                                                profile_id="fixture", write_window=self.window)
        self.manager = self.make_manager()

    @contextmanager
    def window(self):
        self.leases += 1
        try:
            yield
        finally:
            self.leases -= 1

    def make_manager(self, fault=None, mapping=None):
        return PPSSPPPerformanceManager(self.experience, self.root / "performance", fault_hook=fault,
            game_identity=self.observe_identity,
            game_configs=mapping or {"game:one": self.game.relative_to(self.card).as_posix()})

    def observe_identity(self, game_id):
        return {"native_game_id": self.native_game_id, "rom_sha256": hashlib.sha256(self.rom.read_bytes()).hexdigest(),
                "preset_id": self.selected_preset, "engine": self.selected_engine,
                "config_path": self.game.relative_to(self.card).as_posix(),
                "executable": self.control_profile["executable"],
                "executable_sha256": self.control_profile["executable_sha256"]}

    def preview(self, changes=None):
        return self.manager.preview({"game_id": "game:one", "changes": changes or {"resolution": 1},
                                     "expected_generation": self.manager.status("game:one")["generation"]})

    def apply(self, preview=None, request="apply"):
        preview = preview or self.preview()
        return self.manager.apply({"preview_id": preview["preview_id"], "request_id": request,
                                   "expected_generation": preview["generation"]})

    def undo(self, result, request="undo"):
        return self.manager.undo({"transaction_id": result["transaction_id"], "request_id": request,
                                  "expected_generation": result["generation"]})

    def assert_code(self, code, action):
        with self.assertRaises(SettingsError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def test_catalog_reports_local_and_inherited_values_and_untested_candidates(self):
        status = self.manager.status("game:one")
        self.assertTrue(status["writable"])
        self.assertEqual(status["options"][0]["value"], 2)
        self.assertFalse(status["options"][0]["inherited"])
        self.assertEqual(status["options"][1]["effective_value"], 0)
        self.assertTrue(status["options"][1]["inherited"])
        self.assertEqual({value["status"] for value in status["presets"]}, {"untested"})
        self.assertFalse(status["runtime_observed"])

    def test_apply_and_undo_reuse_lease_and_preserve_every_unselected_file(self):
        other = self.other.read_bytes()
        preview = self.preview()
        self.assertEqual(self.game.read_bytes(), GAME)
        self.assertEqual(preview["candidate_status"], "untested")
        result = self.apply(preview)
        self.assertIn(b'InternalResolution = 1 # owner\r\n', self.game.read_bytes())
        self.assertIn(b'Cross = 10-189\r\n', self.game.read_bytes())
        self.assertEqual(self.config.read_bytes(), GLOBAL)
        self.assertEqual(self.other.read_bytes(), other)
        self.assertTrue(self.apply(preview)["idempotent"])
        self.undo(result)
        self.assertEqual(self.game.read_bytes(), GAME)
        self.assertTrue(self.undo(result)["idempotent"])
        self.assertEqual(self.leases, 0)

    def test_undo_keeps_independent_owner_edits_in_game_and_global_settings(self):
        result = self.apply()
        self.game.write_bytes(self.game.read_bytes().replace(b'VertexCache = False', b'VertexCache = True') + b'; owner note\r\n')
        self.config.write_bytes(GLOBAL + b'; global owner note\r\n')
        self.undo(result)
        expected = GAME.replace(b'VertexCache = False', b'VertexCache = True') + b'; owner note\r\n'
        self.assertEqual(self.game.read_bytes(), expected)
        self.assertEqual(self.config.read_bytes(), GLOBAL + b'; global owner note\r\n')

    def test_undo_does_not_replace_an_owned_external_edit(self):
        result = self.apply()
        self.game.write_bytes(self.game.read_bytes().replace(b'InternalResolution = 1', b'InternalResolution = 3'))
        current = self.game.read_bytes()
        self.assert_code("UNDO_CONFLICT", lambda: self.undo(result))
        self.assertEqual(self.game.read_bytes(), current)

    def test_inherit_removes_only_selected_key_and_undo_restores_original_token(self):
        result = self.apply(self.preview({"resolution": None}))
        self.assertNotIn(b'InternalResolution', self.game.read_bytes())
        self.assertEqual(self.manager.status("game:one")["options"][0]["effective_value"], 3)
        self.undo(result)
        self.assertEqual(self.game.read_bytes(), GAME)

    def test_undo_inherit_keeps_original_comment_and_later_unrelated_edits(self):
        result = self.apply(self.preview({"resolution": None}))
        self.game.write_bytes(self.game.read_bytes() + b'; later owner annotation\r\n')
        self.undo(result)
        self.assertIn(b'InternalResolution = 2 # owner\r\n', self.game.read_bytes())
        self.assertTrue(self.game.read_bytes().endswith(b'; later owner annotation\r\n'))
        self.assertIn(b'VertexCache = False\r\n', self.game.read_bytes())

    def test_inserting_and_undoing_new_keys_keeps_later_owner_changes(self):
        result = self.apply(self.preview({"frameskip": 1}))
        self.game.write_bytes(self.game.read_bytes() + b'; later note\r\n')
        self.undo(result)
        self.assertEqual(self.game.read_bytes(), GAME + b'; later note\r\n')

    def test_global_game_and_other_override_changes_each_invalidate_preview(self):
        for path in (self.config, self.game, self.other):
            with self.subTest(path=path.name):
                preview = self.preview()
                original = path.read_bytes()
                path.write_bytes(original + b'; changed\n')
                self.assert_code("STALE_SNAPSHOT", lambda: self.apply(preview))
                self.assertEqual(self.manager._state()["generation"], 0)
                path.write_bytes(original)

    def test_stale_generation_and_reused_request_are_rejected(self):
        result = self.apply()
        self.assert_code("STALE_GENERATION", lambda: self.manager.preview({"game_id": "game:one", "changes": {"resolution": 3}, "expected_generation": 0}))
        preview = self.preview({"resolution": 3})
        self.assert_code("IDEMPOTENCY_CONFLICT", lambda: self.apply(preview))
        self.undo(result)

    def test_every_partial_replace_failure_recovers_both_files(self):
        for failed_index in range(2):
            with self.subTest(index=failed_index):
                def fault(point, index):
                    if point == "after_replace" and index == failed_index:
                        raise RuntimeError("injected interrupted storage write")
                self.manager = self.make_manager(fault)
                with self.assertRaises(RuntimeError):
                    self.apply()
                self.assertEqual(self.game.read_bytes(), GAME)
                self.assertEqual(self.manager.status("game:one")["generation"], 0)

    def test_interrupted_undo_restores_the_committed_selection_for_retry(self):
        result = self.apply()
        selected = self.game.read_bytes()
        def fault(point, index):
            if point == "after_replace" and index == 0:
                raise RuntimeError("interrupted Undo")
        self.manager = self.make_manager(fault)
        with self.assertRaises(RuntimeError):
            self.undo(result)
        self.assertEqual(self.game.read_bytes(), selected)
        self.manager = self.make_manager()
        self.assertEqual(self.manager.status("game:one")["generation"], result["generation"])
        self.undo(result)
        self.assertEqual(self.game.read_bytes(), GAME)

    def test_process_death_reopens_and_rolls_back_without_touching_global_settings(self):
        class ProcessDeath(BaseException):
            pass
        def fault(point, index):
            if point == "after_replace" and index == 0:
                raise ProcessDeath()
        self.manager = self.make_manager(fault)
        with self.assertRaises(ProcessDeath):
            self.apply()
        self.manager = self.make_manager()
        self.assertEqual(self.game.read_bytes(), GAME)
        self.assertEqual(self.config.read_bytes(), GLOBAL)
        self.assertEqual(self.manager.status("game:one")["generation"], 0)

    def test_unknown_mapping_and_changed_inventory_refuse_writes(self):
        self.assertFalse(self.manager.status("game:unknown")["writable"])
        self.assert_code("UNQUALIFIED_PER_GAME_CONFIG", lambda: self.manager.preview({"game_id": "game:unknown", "changes": {"resolution": 1}, "expected_generation": 0}))
        (self.config.parent / "ULUS00003_ppsspp.ini").write_bytes(b'[Graphics]\n')
        self.assertFalse(self.manager.status("game:one")["writable"])
        self.assert_code("PER_GAME_INVENTORY_CHANGED", self.preview)

    def test_shared_native_game_config_is_reported(self):
        relative = self.game.relative_to(self.card).as_posix()
        self.manager = self.make_manager(mapping={"game:one": relative, "game:alias": relative})
        self.assertEqual(self.manager.status("game:one")["shared_game_ids"], ["game:alias"])
        self.assertIn("share", self.preview()["warnings"][1])

    def test_missing_live_identity_cannot_authorize_a_static_mapping(self):
        manager = PPSSPPPerformanceManager(self.experience, self.root / "unbound-performance",
            game_configs={"game:one": self.game.relative_to(self.card).as_posix()})
        status = manager.status("game:one")
        self.assertFalse(status["writable"])
        self.assertEqual(status["gate_reason"], "UNQUALIFIED_GAME_IDENTITY")
        self.assert_code("UNQUALIFIED_GAME_IDENTITY", lambda: manager.preview({"game_id": "game:one", "changes": {"resolution": 1}, "expected_generation": 0}))

    def test_rom_replacement_and_changed_selected_preset_invalidate_preview(self):
        preview = self.preview()
        original_rom = self.rom.read_bytes()
        self.rom.write_bytes(b'replacement content at exactly the same path')
        self.assert_code("GAME_IDENTITY_CHANGED", lambda: self.apply(preview))
        self.rom.write_bytes(original_rom)
        self.selected_preset = "Another PPSSPP preset"
        self.assert_code("GAME_IDENTITY_CHANGED", lambda: self.apply(preview))
        self.assertEqual(self.game.read_bytes(), GAME)

    def test_missing_game_content_reports_unavailable_without_writing(self):
        self.rom.unlink()
        status = self.manager.status("game:one")
        self.assertFalse(status["writable"])
        self.assertEqual(status["gate_reason"], "GAME_IDENTITY_CHANGED")
        self.assertEqual(self.game.read_bytes(), GAME)

    def test_native_id_and_selected_engine_change_refuse_status_and_undo(self):
        result = self.apply()
        selected = self.game.read_bytes()
        self.native_game_id = "ULUS99999"
        self.assertFalse(self.manager.status("game:one")["writable"])
        self.assert_code("UNQUALIFIED_GAME_IDENTITY", lambda: self.undo(result))
        self.native_game_id = "ULUS00001"
        self.selected_engine = "other-emulator"
        self.assertFalse(self.manager.status("game:one")["writable"])
        self.assert_code("GAME_IDENTITY_CHANGED", lambda: self.undo(result))
        self.assertEqual(self.game.read_bytes(), selected)
        self.selected_engine = "ppsspp"
        self.rom.write_bytes(b'another ROM at the same library path')
        self.assert_code("GAME_IDENTITY_CHANGED", lambda: self.undo(result))
        self.assertEqual(self.game.read_bytes(), selected)

    def test_recovery_waits_for_the_same_game_identity_before_restoring_bytes(self):
        class ProcessDeath(BaseException):
            pass
        def fault(point, index):
            if point == "after_replace" and index == 0:
                raise ProcessDeath()
        self.manager = self.make_manager(fault)
        with self.assertRaises(ProcessDeath):
            self.apply()
        selected = self.game.read_bytes()
        original_rom = self.rom.read_bytes()
        self.rom.write_bytes(b'replaced while settings operation was interrupted')
        self.assert_code("GAME_IDENTITY_CHANGED", self.make_manager)
        self.assertEqual(self.game.read_bytes(), selected)
        self.rom.write_bytes(original_rom)
        self.manager = self.make_manager()
        self.assertEqual(self.game.read_bytes(), GAME)

    def test_running_writer_and_nonquiescent_session_refuse_apply(self):
        preview = self.preview()
        self.running = True
        self.assert_code("BUSY_GAME", lambda: self.apply(preview))
        self.running = False
        self.idle = False
        self.assert_code("BUSY_WRITER", lambda: self.apply(preview))
        self.assertEqual(self.game.read_bytes(), GAME)

    def test_native_auto_frameskip_conflict_never_silently_edits_skip_buffer_effects(self):
        self.config.write_bytes(GLOBAL.replace(b'SkipBufferEffects = False', b'SkipBufferEffects = True'))
        self.assert_code("SETTING_CONFLICT", lambda: self.preview({"auto_frameskip": True}))
        self.assertEqual(self.game.read_bytes(), GAME)
        self.assertIn(b'SkipBufferEffects = True', self.config.read_bytes())

    def test_manual_frameskip_requires_auto_off_and_presets_set_both_explicitly(self):
        self.config.write_bytes(GLOBAL.replace(b'AutoFrameSkip = False', b'AutoFrameSkip = True'))
        self.assert_code("SETTING_CONFLICT", lambda: self.preview({"frameskip": 1}))
        result = self.apply(self.preview({"frameskip": 1, "auto_frameskip": False}))
        self.assertIn(b'AutoFrameSkip = False', self.game.read_bytes())
        self.undo(result)
        result = self.apply(self.preview(PRESETS[0]["changes"]), request="preset")
        self.assertEqual(result["candidate_status"], "untested")

    def test_undo_auto_rechecks_newer_native_buffer_effects_before_writing(self):
        self.game.write_bytes(GAME.replace(b'[Graphics]\r\n', b'[Graphics]\r\nAutoFrameSkip = True\r\n'))
        result = self.apply(self.preview({"auto_frameskip": False}))
        self.config.write_bytes(GLOBAL.replace(b'SkipBufferEffects = False', b'SkipBufferEffects = True'))
        current = self.game.read_bytes()
        self.assert_code("UNDO_CONFLICT", lambda: self.undo(result))
        self.assertEqual(self.game.read_bytes(), current)
        self.assertIn(b'SkipBufferEffects = True', self.config.read_bytes())

    def test_undo_to_inherited_auto_rechecks_newer_native_buffer_effects(self):
        self.config.write_bytes(GLOBAL.replace(b'AutoFrameSkip = False', b'AutoFrameSkip = True'))
        result = self.apply(self.preview({"auto_frameskip": False}))
        self.config.write_bytes(self.config.read_bytes().replace(b'SkipBufferEffects = False', b'SkipBufferEffects = True'))
        current = self.game.read_bytes()
        self.assert_code("UNDO_CONFLICT", lambda: self.undo(result))
        self.assertEqual(self.game.read_bytes(), current)

    def test_resolution_is_explicitly_inactive_with_native_software_renderer(self):
        self.config.write_bytes(GLOBAL.replace(b'SkipBufferEffects = False', b'SkipBufferEffects = False\r\nSoftwareRenderer = True'))
        self.assert_code("SETTING_CONFLICT", self.preview)

    def test_unsafe_paths_invalid_options_and_boolean_integer_confusion_rejected(self):
        for changes in ({"resolution": True}, {"frameskip": False}, {"auto_frameskip": 1}, {"cpu_clock": 333}):
            with self.subTest(changes=changes):
                self.assert_code("INVALID_ARGUMENT", lambda: self.preview(changes))
        outside = self.root / "outside_ppsspp.ini"
        outside.write_bytes(GAME)
        self.assert_code("PER_GAME_INVENTORY_CHANGED", lambda: self.make_manager(mapping={"game:one": "../outside_ppsspp.ini"}).preview({"game_id": "game:one", "changes": {"resolution": 1}, "expected_generation": 0}))

    def test_malformed_owned_values_and_duplicate_sections_are_unavailable(self):
        for data in (GAME.replace(b'InternalResolution = 2', b'InternalResolution = ' + b'9' * 5000),
                     GAME + b'[Graphics]\nInternalResolution = 3\n'):
            with self.subTest(length=len(data)):
                self.game.write_bytes(data)
                self.assertFalse(self.manager.status("game:one")["writable"])
                self.assertEqual(self.game.read_bytes(), data)

    def test_ps1_uses_existing_options_and_retains_its_emulator_route(self):
        status = unavailable_status("game:ps1", "PS")
        self.assertEqual(status["route"], "game.options")
        self.assertFalse(status["available"])
        self.assertEqual(status["options"], [])
        self.assertIn("selected PS1 emulator is preserved", status["reason"])
        unknown = unavailable_status("game:unknown")
        self.assertIsNone(unknown["options"][0]["inherited"])
        self.assertFalse(unknown["options"][0]["value_available"])


class NativePerformanceSourceContract(unittest.TestCase):
    def test_supported_keys_and_native_interlocks_match_the_pinned_source(self):
        root = Path(os.environ.get("PPSSPP_SOURCE_ROOT", "/workspace/trimui-sources/ppsspp"))
        if not root.is_dir():
            self.skipTest("Provide untouched pinned PPSSPP_SOURCE_ROOT")
        lock = json.loads((Path(__file__).resolve().parents[1] / "ppsspp/performance-source-lock.json").read_text())
        for entry in lock["inputs"]:
            self.assertEqual(hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])
        config = (root / "Core/Config.cpp").read_text()
        for key in ("InternalResolution", "FrameSkip", "AutoFrameSkip"):
            self.assertRegex(config, r'ConfigSetting\("' + key + r'"[^\n]+CfgFlag::PER_GAME')
        self.assertIn('if (bAutoFrameSkip && bSkipBufferEffects)', config)
        screen = (root / "UI/GameSettingsScreen.cpp").read_text()
        self.assertIn('return !g_Config.bAutoFrameSkip;', screen)
        self.assertIn('return !g_Config.bSoftwareRendering && !g_Config.bSkipBufferEffects;', screen)
