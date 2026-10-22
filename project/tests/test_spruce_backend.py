# SPDX-License-Identifier: MIT
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from psp_shell.adapters.spruce import (
    PyUIModelProvider, SourceSnapshotProvider, SpruceBackend, SpruceError,
)


class Card:
    def __init__(self, root):
        self.root = Path(root)
        self.write("spruce/scripts/emu/standard_launch.sh", "#!/bin/sh\nexit 0\n")
        self.write("Emu/GB/engine", "host fake engine; not an emulator")
        self.config = {"label": "Game Boy", "devices": ["TRIMUI_A133P"],
                       "launch": "../../spruce/scripts/emu/standard_launch.sh",
                       "extlist": "gb|gbc|zip", "default_emulator": "gambatte",
                       "menuOptions": {
                           "Emulator_64": {"devices": ["TRIMUI_A133P"],
                                           "options": ["gambatte", "mgba"],
                                           "selected": "gambatte", "overrides": {}},
                           "Governor": {"selected": "Smart", "overrides": {}}}}
        self.save_config()
        self.write("Roms/GB/Alpha.gb", "fixture")
        self.write("Roms/GB/nested/Beta.gbc", "fixture")
        self.write("Roms/GB/.hidden.gb", "fixture")
        self.write("Roms/GB/Imgs/not-a-game.gb", "fixture")
        self.write("Roms/GB/notes.txt", "fixture")

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return path

    def save_config(self):
        self.write("Emu/GB/config.json", json.dumps(self.config))

    def backend(self):
        return SpruceBackend(self.root)

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file() and not path.is_symlink()}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = Card(self.temp.name)

    def test_inventory_never_writes_or_prunes_existing_authority(self):
        self.card.write("Saves/pyui-favorites.json", '{"corrupt": true}')
        self.card.write("Saves/pyui-recents.json", '[{"rom_file_path":"/missing","game_system_name":"GB"}]')
        before = self.card.snapshot()
        backend = self.card.backend()
        self.assertEqual(backend.systems()[0]["game_count"], 2)
        self.assertEqual(backend.games("GB")["total"], 2)
        self.assertEqual(backend.favorites(), [])
        self.assertEqual(backend.recent(), [])
        self.assertEqual(before, self.card.snapshot())
        self.assertFalse((self.card.root / "Saves/pyui-favorites.json.corrupt").exists())

    def test_empty_card_is_a_normal_empty_library(self):
        with tempfile.TemporaryDirectory() as empty:
            backend = SpruceBackend(empty)
            self.assertEqual(backend.systems(), [])
            self.assertEqual(backend.games()["items"], [])
            self.assertEqual(backend.tools(), [])

    def test_tg5040_device_filter_excludes_s_and_brick(self):
        for system, devices in (("S_ONLY", ["TRIMUI_SMART_PRO_S"]), ("BRICK", ["TRIMUI_BRICK"]),
                                ("UNIVERSAL", [])):
            self.card.write(f"Emu/{system}/config.json", json.dumps({"label": system, "devices": devices}))
        ids = {row["id"] for row in self.card.backend().systems()}
        self.assertEqual(ids, {"GB", "UNIVERSAL"})

    def test_hostile_unicode_and_newline_names_are_data_only(self):
        name = 'Café ; $(touch PWNED) `echo x` "quote"\nline.gb'
        self.card.write("Roms/GB/" + name, "fixture")
        backend = self.card.backend()
        games = backend.games("GB", search="café")["items"]
        self.assertEqual(len(games), 1)
        context = backend.resolve_game(games[0]["id"])
        self.assertEqual(context["argv"][1], str(self.card.root / "Roms/GB" / name))
        self.assertFalse((self.card.root / "PWNED").exists())
        self.assertFalse(context["launchable"])
        self.assertEqual(context["gate_reason"], "SNAPSHOT_READ_ONLY")

    def test_shared_launcher_keeps_lexical_emu_system_path(self):
        game = self.card.backend().games("GB")["items"][0]
        context = self.card.backend().resolve_game(game["id"])
        self.assertIn("/Emu/GB/../../spruce/", context["executable"])
        self.assertEqual(context["canonical_executable"], str(self.card.root / "spruce/scripts/emu/standard_launch.sh"))
        self.assertEqual(context["argv"][0], context["executable"])

    def test_presets_use_json_override_basename_including_extension(self):
        self.card.config["menuOptions"]["Emulator_64"]["selected"] = "mgba"
        self.card.config["menuOptions"]["Emulator_64"]["overrides"] = {"Alpha.gb": "gambatte"}
        self.card.config["menuOptions"]["Governor"]["overrides"] = {"Alpha.gb": "Performance"}
        self.card.config["launchlist"] = [{"name": "Utility action", "launch": "does-not-exist.sh"}]
        self.card.save_config()
        self.card.write("Emu/GB/launchers.cfg", "default_launcher=not-spruce-authority")
        self.card.write("Roms/GB/.games_config/Alpha.cfg", "launcher=not-spruce-authority")
        backend = self.card.backend()
        alpha = next(row for row in backend.games("GB")["items"] if row["label"] == "Alpha")
        beta = next(row for row in backend.games("GB")["items"] if row["label"] == "Beta")
        self.assertEqual(backend.resolve_game(alpha["id"])["preset_id"], "gambatte")
        self.assertEqual(backend.resolve_game(alpha["id"])["governor"], "Performance")
        self.assertEqual(backend.resolve_game(beta["id"])["preset_id"], "mgba")
        with self.assertRaises(SpruceError) as error:
            backend.resolve_game(alpha["id"], "renamed-core")
        self.assertEqual(error.exception.code, "PRESET_UNAVAILABLE")

    def test_renamed_saved_choice_reports_explicit_fallback(self):
        self.card.config["menuOptions"]["Emulator_64"]["overrides"] = {"Alpha.gb": "removed-core"}
        self.card.save_config()
        backend = self.card.backend()
        alpha = backend.games("GB", "Alpha")["items"][0]
        context = backend.resolve_game(alpha["id"])
        self.assertEqual(context["preset_id"], "gambatte")
        self.assertIn("SAVED_PRESET_UNAVAILABLE", context["warnings"])

    def test_alias_folders_and_subfolder_launch_file(self):
        self.card.config["alternativeFolderNames"] = ["GAMEBOY"]
        self.card.save_config()
        self.card.write("Roms/GAMEBOY/Other.gb", "fixture")
        self.card.write("Emu/PSP/config.json", json.dumps({"label": "PSP", "default_emulator": "PPSSPP-SA",
                         "launch": "../../spruce/scripts/emu/standard_launch.sh",
                         "subfolder_launch_file": "EBOOT.PBP", "extlist": "iso|pbp"}))
        self.card.write("Roms/PSP/Homebrew/EBOOT.PBP", "fixture")
        backend = self.card.backend()
        self.assertEqual(backend.games("GB")["total"], 3)
        self.assertEqual(backend.games("PSP")["total"], 1)
        self.assertEqual(backend.games("PSP")["items"][0]["selected_preset"], "PPSSPP-SA")

    def test_symlink_escape_and_cycle_are_bounded(self):
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / "Outside.gb").write_text("fixture")
            (self.card.root / "Roms/GB/escape").symlink_to(outside, target_is_directory=True)
            (self.card.root / "Roms/GB/cycle").symlink_to(self.card.root / "Roms/GB", target_is_directory=True)
            backend = self.card.backend()
            self.assertEqual(backend.games("GB")["total"], 2)
            codes = {row["code"] for row in backend.provider.warnings}
            self.assertIn("PATH_UNAVAILABLE", codes)
            self.assertIn("SYMLINK_CYCLE", codes)

    def test_case_and_unicode_normalization_collisions_keep_both(self):
        self.card.write("Roms/GB/ALPHA.gb", "fixture")
        self.card.write("Roms/GB/Café.gb", "fixture")
        self.card.write("Roms/GB/Cafe\u0301.gb", "fixture")
        backend = self.card.backend()
        items = backend.games("GB")["items"]
        collisions = [row for row in items if row["availability"] == "review_required"]
        self.assertEqual(len(collisions), 4)
        self.assertEqual(backend.resolve_game(collisions[0]["id"])["gate_reason"], "GAME_REQUIRES_REVIEW")

    def test_history_arrays_preserve_read_only_unknown_fields(self):
        self.card.write("Saves/pyui-favorites.json", json.dumps([
            {"rom_file_path": "/mnt/SDCARD/Roms/GB/Alpha.gb", "game_system_name": "GB",
             "display_name": "Custom title", "future_field": {"preserve": True}},
            {"rom_file_path": "/missing", "game_system_name": "GB"}]))
        self.card.write("Saves/pyui-recents.json", json.dumps([
            {"rom_file_path": "/mnt/SDCARD/Roms/GB/Alpha.gb", "game_system_name": "GB"}]))
        self.card.write("Saves/states/.gameswitcher/Alpha.state.auto.png", "not proof of a state")
        before = self.card.snapshot()
        backend = self.card.backend()
        favorite = backend.favorites()[0]
        self.assertEqual(favorite["label"], "Custom title")
        self.assertTrue(favorite["legacy_record"]["future_field"]["preserve"])
        self.assertFalse(backend.recent()[0]["resume_available"])
        self.assertEqual(backend.recent()[0]["continue_kind"], "recently_played")
        self.assertEqual(before, self.card.snapshot())

    def test_malformed_manifest_and_query_are_truthful(self):
        self.card.write("Emu/BROKEN/config.json", "{bad json")
        backend = self.card.backend()
        self.assertEqual(backend.games("GB")["total"], 2)
        self.assertIn("INVALID_JSON", {row["code"] for row in backend.provider.warnings})
        for offset, limit in ((-1, 5), (0, 201), (True, 5), (0, 0)):
            with self.assertRaises(SpruceError):
                backend.games("GB", offset=offset, limit=limit)

    def test_gamelist_and_cache_are_metadata_only_and_never_authority_for_missing_roms(self):
        self.card.write("Roms/GB/Imgs/Alpha.png", "image fixture")
        self.card.write("Roms/GB/gamelist.xml", '<gameList><game><path>./Alpha.gb</path><name>Scraped title</name>'
                        '<image>./Imgs/Alpha.png</image></game><game><path>./Missing.gb</path><name>Stale</name></game></gameList>')
        self.card.write("Saves/cache/_mnt_SDCARD_Roms_GB.json", json.dumps({"mtime": 0,
                         "files": ["/mnt/SDCARD/Roms/GB/Missing.gb"], "folders": []}))
        before = self.card.snapshot()
        backend = self.card.backend()
        games = backend.games("GB")
        self.assertEqual(games["total"], 2)
        alpha = next(row for row in games["items"] if row["label"] == "Scraped title")
        self.assertEqual(alpha["artwork"], str(self.card.root / "Roms/GB/Imgs/Alpha.png"))
        self.assertTrue(backend.systems()[0]["cache_snapshots"][0]["available"])
        self.assertEqual(before, self.card.snapshot())

    def test_xml_entities_are_rejected_without_reading_external_files(self):
        self.card.write("Roms/GB/gamelist.xml", '<!DOCTYPE x [<!ENTITY data SYSTEM "file:///etc/passwd">]>'
                        '<gameList><game><path>./Alpha.gb</path><name>&data;</name></game></gameList>')
        backend = self.card.backend()
        self.assertEqual(backend.games("GB")["total"], 2)
        self.assertIn("INVALID_GAMELIST", {row["code"] for row in backend.provider.warnings})

    def test_snapshot_cannot_execute_or_write_even_if_read_only_false(self):
        backend = SpruceBackend(self.card.root, read_only=False)
        game = backend.games("GB")["items"][0]
        with self.assertRaises(SpruceError) as error:
            backend.execute_action("touch anything")
        self.assertEqual(error.exception.code, "SNAPSHOT_READ_ONLY")
        with self.assertRaises(SpruceError):
            backend.set_favorite(game["id"], True)

    def test_snapshot_limits_bounded_directory_and_missing_tool_stays_visible(self):
        provider = SourceSnapshotProvider(self.card.root, max_entries=2)
        self.assertEqual(provider.game_records(), [])
        self.assertIn("SCAN_LIMIT", {item["code"] for item in provider.warnings})
        self.card.write("App/Installed/config.json", '{"label":"Installed tool","launch":"missing.sh"}')
        tool = next(item for item in self.card.backend().tools() if item["id"] == "app:Installed")
        self.assertEqual(tool["availability"], "unavailable")
        self.assertIn("LAUNCHER_UNAVAILABLE", tool["warnings"])

    def test_tools_use_app_singular_and_media_does_not_become_category(self):
        self.card.write("App/Terminal/config.json", json.dumps({"label": "Terminal", "launch": "launch.sh"}))
        self.card.write("App/Terminal/launch.sh", "#!/bin/sh\nexit 0\n")
        self.card.write("Emu/MEDIA/config.json", json.dumps({"label": "Installed media"}))
        backend = self.card.backend()
        self.assertNotIn("MEDIA", {row["id"] for row in backend.systems()})
        ids = {row["id"] for row in backend.tools()}
        self.assertEqual(ids, {"app:Terminal", "system:MEDIA"})
        self.assertFalse(backend.resolve_tool("app:Terminal")["launchable"])


class Favorites:
    def __init__(self):
        self.items = []

    def get_favorites(self):
        return list(self.items)

    def add_favorite(self, model):
        if model not in self.items:
            self.items.insert(0, model)

    def remove_favorite(self, model):
        self.items.remove(model)


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.card = Card(self.temp.name)
        self.events = []
        self.idle = True
        self.system = SimpleNamespace(system_name="GB", display_name="Game Boy")
        self.model = SimpleNamespace(game_system=self.system, rom_file_path=str(self.card.root / "Roms/GB/Alpha.gb"), display_name="Alpha")
        self.favorites = Favorites()
        self.provider = PyUIModelProvider(self.card.root,
            system_manager=SimpleNamespace(get_active_systems=lambda: [self.system]),
            game_list=lambda system: [self.model], device=SimpleNamespace(run_game=lambda model: self.events.append(("launch", model))),
            favorites_manager=self.favorites, recents_manager=SimpleNamespace(get_recents=lambda: [self.model]),
            release_resources=lambda: self.events.append(("release", None)), quiescent=lambda: self.idle)
        self.backend = SpruceBackend(self.card.root, read_only=False, managers=self.provider)
        self.game = self.backend.games("GB")["items"][0]

    def test_registered_live_callback_is_one_use_and_releases_first(self):
        context = self.backend.resolve_game(self.game["id"])
        self.assertTrue(context["launchable"])
        self.assertEqual(self.events, [])
        self.backend.execute_action(context["action_id"])
        self.assertEqual([event[0] for event in self.events], ["release", "launch"])
        self.assertIs(self.events[-1][1], self.model)
        with self.assertRaises(SpruceError):
            self.backend.execute_action(context["action_id"])

    def test_coordinator_can_own_cleanup_without_double_release(self):
        action = self.backend.resolve_game(self.game["id"])["action_id"]
        self.backend.validate_action(action, "normal")
        self.backend.execute_action(action, "normal", release_ui=False)
        self.assertEqual([event[0] for event in self.events], ["launch"])

    def test_busy_stale_and_wrong_mode_fail_before_any_callback(self):
        action = self.backend.resolve_game(self.game["id"])["action_id"]
        self.idle = False
        with self.assertRaises(SpruceError) as error:
            self.backend.validate_action(action)
        self.assertEqual(error.exception.code, "BUSY_SESSION")
        self.idle = True
        with self.assertRaises(SpruceError) as error:
            self.backend.execute_action(action, "resume")
        self.assertEqual(error.exception.code, "ACTION_MODE_MISMATCH")
        self.card.config["menuOptions"]["Governor"]["selected"] = "Performance"
        self.card.save_config()
        with self.assertRaises(SpruceError) as error:
            self.backend.execute_action(action)
        self.assertEqual(error.exception.code, "STALE_ACTION")
        self.assertEqual(self.events, [])

    def test_explicit_other_preset_needs_existing_menu_apply(self):
        context = self.backend.resolve_game(self.game["id"], "mgba")
        self.assertFalse(context["launchable"])
        self.assertEqual(context["gate_reason"], "PRESET_REQUIRES_EXISTING_MENU")

    def test_invalid_stored_preset_cannot_launch_suggested_fallback_without_repair(self):
        self.card.config["menuOptions"]["Emulator_64"]["overrides"]["Alpha.gb"] = "removed-core"
        self.card.save_config()
        context = self.backend.resolve_game(self.game["id"])
        self.assertFalse(context["launchable"])
        self.assertEqual(context["preset_id"], "gambatte")
        self.assertEqual(context["stored_preset"], "removed-core")
        self.assertEqual(context["gate_reason"], "SAVED_PRESET_UNAVAILABLE")
        self.assertEqual(self.events, [])

    def test_favorites_only_call_existing_manager_with_preview_and_idle(self):
        preview = self.backend.preview_favorite(self.game["id"], True)
        self.backend.set_favorite(self.game["id"], True, preview)
        self.assertEqual(self.favorites.items, [self.model])
        self.assertFalse((self.card.root / "Saves/pyui-favorites.json").exists())
        self.idle = False
        with self.assertRaises(SpruceError):
            self.backend.set_favorite(self.game["id"], False)

    def evidence(self):
        state = self.card.write("Saves/states/Gambatte-64/Alpha.state.auto", "verified fake state")
        engine = self.card.root / "Emu/GB/engine"
        profile = {"engine_id": "fake-gambatte-64", "executable": "Emu/GB/engine",
                   "sha256": hashlib.sha256(engine.read_bytes()).hexdigest(), "architecture": "aarch64",
                   "state_format_id": "fake-format-1", "state_roots": ["Saves/states/Gambatte-64"]}
        record = {"schema": 1, "game_id": self.game["id"], "engine_id": profile["engine_id"],
                  "engine_sha256": profile["sha256"], "clean_shutdown": True,
                  "state": {"path": "Saves/states/Gambatte-64/Alpha.state.auto", "format_id": "fake-format-1",
                            "slot": 0, "sha256": hashlib.sha256(state.read_bytes()).hexdigest()}}
        return record, profile

    def test_resume_needs_identity_format_hash_clean_exit_and_existing_handler(self):
        record, profile = self.evidence()
        self.backend.set_resume_evidence({self.game["id"]: record}, {"gambatte": profile})
        self.assertTrue(self.backend.recent()[0]["resume_eligible"])
        self.assertFalse(self.backend.recent()[0]["resume_available"])
        self.provider.mode_actions = {"gambatte": {"resume": lambda model, evidence: self.events.append(("resume", evidence))}}
        context = self.backend.resolve_game(self.game["id"], mode="resume")
        self.assertTrue(context["resume_available"])
        self.backend.execute_action(context["action_id"], mode="resume", release_ui=False)
        self.assertEqual(self.events[0][0], "resume")
        for key, value, reason in (("game_id", "wrong", "UNCLEAN_OR_WRONG_GAME"),
                                   ("engine_id", "wrong", "ENGINE_CHANGED"),
                                   ("clean_shutdown", False, "UNCLEAN_OR_WRONG_GAME")):
            altered = copy.deepcopy(record)
            altered[key] = value
            self.backend.set_resume_evidence({self.game["id"]: altered}, {"gambatte": profile})
            self.assertEqual(self.backend.recent()[0]["resume_reason"], reason)
        altered = copy.deepcopy(record)
        altered["state"]["format_id"] = "another-core"
        self.backend.set_resume_evidence({self.game["id"]: altered}, {"gambatte": profile})
        self.assertEqual(self.backend.recent()[0]["resume_reason"], "STATE_FORMAT_MISMATCH")

    def test_changed_state_invalidates_resume_before_callback(self):
        record, profile = self.evidence()
        self.provider.mode_actions = {"gambatte": {"resume": lambda model, evidence: self.events.append(("resume", None))}}
        self.backend.set_resume_evidence({self.game["id"]: record}, {"gambatte": profile})
        action = self.backend.resolve_game(self.game["id"], mode="resume")["action_id"]
        self.card.write("Saves/states/Gambatte-64/Alpha.state.auto", "corrupt")
        with self.assertRaises(SpruceError) as error:
            self.backend.execute_action(action, "resume")
        self.assertEqual(error.exception.code, "RESUME_UNAVAILABLE")
        self.assertEqual(self.events, [])

    def test_malformed_resume_records_are_rejected_without_losing_normal_launch(self):
        with self.assertRaises(SpruceError) as error:
            self.backend.set_resume_evidence({self.game["id"]: "broken"}, {})
        self.assertEqual(error.exception.code, "INVALID_RESUME_EVIDENCE")
        self.assertTrue(self.backend.resolve_game(self.game["id"])["launchable"])


if __name__ == "__main__":
    unittest.main()
