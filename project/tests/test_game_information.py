# SPDX-License-Identifier: MIT
"""Existing library identities and PS1 disc references stay read-only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from psp_shell import game_information
from psp_shell.adapters.spruce import SpruceBackend, SpruceError
from psp_shell.demo import DemoBackend
from psp_shell.game_information import inspect_disc_set, MAX_PLAYLIST_BYTES, MAX_PLAYLIST_ENTRIES


class GameInformationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.write("spruce/scripts/emu/standard_launch.sh", "existing launcher fixture")
        self.configs = {}
        for system, label in (("PS", "PlayStation"), ("PSP", "PSP")):
            config = {"label": label, "launch": "../../spruce/scripts/emu/standard_launch.sh",
                      "extlist": "m3u|cue|chd|pbp|iso", "default_emulator": "existing-core",
                      "menuOptions": {"Emulator_SmartPro": {"options": ["existing-core", "other-core"],
                                                           "selected": "existing-core", "overrides": {}}}}
            self.configs[system] = config
            self.write("Emu/" + system + "/config.json", json.dumps(config))
        self.write("Roms/PS/Café Disc 1.chd", "disc fixture")
        self.write("Roms/PS/Café Disc 2.chd", "disc fixture")
        self.write("Roms/PSP/Café.iso", "disc fixture")

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
        return path

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_combined_system_and_unicode_search_keep_pagination_and_game_ids(self):
        backend = SpruceBackend(self.root)
        all_ps = backend.games("PS")["items"]
        first = backend.games("PS", "CAFE\u0301", limit=1)
        second = backend.games("PS", "CAFE\u0301", offset=1, limit=1)
        self.assertEqual(first["total"], 2)
        self.assertEqual(second["total"], 2)
        self.assertEqual([r["id"] for r in first["items"] + second["items"]], [r["id"] for r in all_ps])
        self.assertTrue(all(r["system_id"] == "PS" for r in first["items"] + second["items"]))

    def test_filtered_histories_keep_existing_order_and_unknown_fields(self):
        histories = [{"game_system_name": system, "rom_file_path": "/mnt/SDCARD/" + relative,
                      "future_field": {"retain": True}}
                     for system, relative in (("PS", "Roms/PS/Café Disc 2.chd"),
                                              ("PSP", "Roms/PSP/Café.iso"),
                                              ("PS", "Roms/PS/Café Disc 1.chd"))]
        for name in ("favorites", "recents"):
            self.write("Saves/pyui-" + name + ".json", json.dumps(histories))
        before = self.snapshot()
        backend = SpruceBackend(self.root)
        for method in (backend.favorites, backend.recent):
            selected = method("PS", "CAFE\u0301")
            self.assertEqual([r["label"] for r in selected], ["Café Disc 2", "Café Disc 1"])
            self.assertTrue(all(r["legacy_record"]["future_field"]["retain"] for r in selected))
            self.assertEqual(len(method("PSP")), 1)
            self.assertEqual(method("PS", "does not exist"), [])
        self.assertEqual(before, self.snapshot())

    def test_readonly_information_keeps_stored_emulator_and_reports_missing_disc(self):
        self.configs["PS"]["menuOptions"]["Emulator_SmartPro"]["overrides"] = {"Adventure.m3u": "other-core"}
        self.write("Emu/PS/config.json", json.dumps(self.configs["PS"]))
        self.write("Roms/PS/Adventure.m3u", "#EXTM3U\nCafé Disc 1.chd\nMissing.chd\n")
        before = self.snapshot()
        backend = SpruceBackend(self.root)
        record = backend.games("PS", "Adventure")["items"][0]
        info = backend.game_info(record["id"])
        self.assertEqual(info["game_id"], record["game_id"])
        self.assertEqual(info["system_label"], "PlayStation")
        self.assertEqual(info["selected_emulator"], "other-core")
        self.assertEqual(info["disc_set"]["disc_count"], 2)
        self.assertEqual(info["disc_set"]["missing_count"], 1)
        self.assertIn("MISSING_DISC_FILE", info["warnings"])
        self.assertEqual(info["disc_management"]["route"], "native_menu")
        self.assertEqual(info["disc_management"]["game_options_route"], "game.options")
        self.assertEqual(backend._actions, {})
        self.assertEqual(before, self.snapshot())

    def test_information_refreshes_preset_and_retains_unavailable_stored_choice(self):
        backend = SpruceBackend(self.root)
        game = backend.games("PS")["items"][0]
        self.configs["PS"]["menuOptions"]["Emulator_SmartPro"]["overrides"] = {"Café Disc 1.chd": "removed-core"}
        self.write("Emu/PS/config.json", json.dumps(self.configs["PS"]))
        info = backend.game_info(game["id"])
        self.assertEqual(info["selected_emulator"], "removed-core")
        self.assertTrue(info["preset_repair_required"])
        self.assertIn("SAVED_PRESET_UNAVAILABLE", info["warnings"])
        self.assertEqual(json.loads((self.root / "Emu/PS/config.json").read_text()), self.configs["PS"])

    def test_information_reports_disappeared_game_from_existing_snapshot(self):
        backend = SpruceBackend(self.root)
        game = backend.games("PSP")["items"][0]
        Path(game["rom_path"]).unlink()
        info = backend.game_info(game["id"])
        self.assertEqual(info["availability"], "unavailable")
        self.assertIn("ROM_UNAVAILABLE", info["warnings"])
        self.assertEqual(info["disc_set"]["kind"], "none")

    def test_existing_cue_disc_checks_track_files_without_treating_tracks_as_discs(self):
        self.write("Roms/PS/Track 1.bin", "track fixture")
        cue = self.write("Roms/PS/First.cue", 'FILE "Track 1.bin" BINARY\n  TRACK 01 MODE2/2352\n')
        status = inspect_disc_set(self.root, cue, "PS")
        self.assertEqual(status["disc_count"], 1)
        self.assertEqual(status["missing_count"], 0)
        (cue.parent / "Track 1.bin").unlink()
        status = inspect_disc_set(self.root, cue, "PS")
        self.assertEqual(status["missing_count"], 1)
        self.assertIn("MISSING_TRACK_FILE", status["warnings"])

    def test_playlist_cue_failure_is_visible_with_original_disc_order(self):
        self.write("Roms/PS/Bad.cue", 'FILE "Absent.bin" BINARY\n')
        playlist = self.write("Roms/PS/Set.m3u", "Bad.cue\nCafé Disc 2.chd\n")
        status = inspect_disc_set(self.root, playlist, "PS")
        self.assertEqual([r["number"] for r in status["discs"]], [1, 2])
        self.assertEqual([r["available"] for r in status["discs"]], [False, True])
        self.assertIn("MISSING_TRACK_FILE", status["warnings"])

    def test_playlist_handles_bom_comments_device_paths_and_windows_separators(self):
        playlist = self.write("Roms/PS/Set.m3u", "\ufeff#EXTM3U\r\n# comment\r\n/mnt/SDCARD/Roms/PS/Café Disc 1.chd\r\n.\\Café Disc 2.chd\r\n")
        status = inspect_disc_set(self.root, playlist, "PS1")
        self.assertEqual(status["disc_count"], 2)
        self.assertEqual(status["warnings"], [])

    def test_playlist_paths_urls_and_symlinks_cannot_read_outside_card(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "Outside.cue"
            external.write_text('FILE "secret.bin" BINARY\n')
            (self.root / "Roms/PS/escape.cue").symlink_to(external)
            playlist = self.write("Roms/PS/Set.m3u", "../../../../Outside.cue\nhttps://example.test/file.chd\nescape.cue\n")
            status = inspect_disc_set(self.root, playlist, "PS")
        self.assertEqual(status["missing_count"], 3)
        self.assertEqual(status["warnings"], ["DISC_PATH_OUTSIDE_CARD", "DISC_SET_REQUIRES_REVIEW"])
        self.assertTrue(all(not row["relative_path"] for row in status["discs"]))

    def test_parent_symlink_swap_cannot_read_external_cue_or_playlist(self):
        for extension, warning in ((".cue", "CUE_UNREADABLE"), (".m3u", "PLAYLIST_UNREADABLE")):
            with self.subTest(extension=extension), tempfile.TemporaryDirectory() as outside:
                folder = self.root / "Roms/PS" / extension[1:]
                folder.mkdir()
                reference = folder / ("Disc" + extension)
                reference.write_text('FILE "Safe.bin" BINARY\n' if extension == ".cue" else "Safe.chd\n")
                (folder / "Safe.bin").write_bytes(b"inside track fixture")
                (folder / "Safe.chd").write_bytes(b"inside disc fixture")
                external = Path(outside) / reference.name
                external_bytes = b'FILE "Private.bin" BINARY\n' if extension == ".cue" else b"Private.chd\n"
                external.write_bytes(external_bytes)
                original_read = game_information._read_text

                def read_after_parent_swap(root, path):
                    folder.rename(folder.with_name(folder.name + "-original"))
                    folder.symlink_to(outside, target_is_directory=True)
                    return original_read(root, path)

                with patch.object(game_information, "_read_text", side_effect=read_after_parent_swap):
                    status = inspect_disc_set(self.root, reference, "PS")
                self.assertIn(warning, status["warnings"])
                self.assertEqual(external.read_bytes(), external_bytes)
                if extension == ".cue":
                    self.assertFalse(status["discs"][0]["available"])
                    self.assertNotIn("DISC_PATH_OUTSIDE_CARD", status["warnings"])
                else:
                    self.assertEqual(status["discs"], [])

    def test_disc_symlink_swap_cannot_report_external_file_as_available(self):
        disc = self.root / "Roms/PS/Café Disc 1.chd"
        original_regular = game_information._regular
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "External.chd"
            external.write_bytes(b"outside disc fixture")

            def check_after_swap(root, path):
                disc.unlink()
                disc.symlink_to(external)
                return original_regular(root, path)

            with patch.object(game_information, "_regular", side_effect=check_after_swap):
                status = inspect_disc_set(self.root, disc, "PS")
        self.assertFalse(status["discs"][0]["available"])
        self.assertIn("MISSING_DISC_FILE", status["warnings"])

    def test_existing_in_card_symlinks_keep_resolved_disc_references(self):
        cue = self.write("Roms/PS/discs/Real.cue", 'FILE "Track.bin" BINARY\n')
        self.write("Roms/PS/discs/Track.bin", "inside track fixture")
        link = self.root / "Roms/PS/Linked.cue"
        link.symlink_to(cue)
        playlist = self.write("Roms/PS/Set.m3u", "Linked.cue\n")
        status = inspect_disc_set(self.root, playlist, "PS")
        self.assertEqual(status["missing_count"], 0)
        self.assertEqual(status["warnings"], [])
        self.assertEqual(status["discs"][0]["relative_path"], "Roms/PS/discs/Real.cue")

    def test_unreadable_empty_and_oversize_playlists_remain_truthful(self):
        for content, warning in ((b"\xff", "PLAYLIST_UNREADABLE"),
                                 (b"bad\0path", "PLAYLIST_UNREADABLE"),
                                 (b"# comments only\n", "EMPTY_PLAYLIST"),
                                 (b"x" * (MAX_PLAYLIST_BYTES + 1), "PLAYLIST_UNREADABLE")):
            with self.subTest(warning=warning):
                playlist = self.write("Roms/PS/Bad.m3u", content)
                status = inspect_disc_set(self.root, playlist, "PS")
                self.assertIn(warning, status["warnings"])
                self.assertEqual(status["discs"], [])

    def test_nested_playlists_and_entry_limit_are_explicit(self):
        self.write("Roms/PS/Other.m3u", "Café Disc 1.chd\n")
        playlist = self.write("Roms/PS/Set.m3u", "Other.m3u\n" + "Café Disc 1.chd\n" * MAX_PLAYLIST_ENTRIES)
        status = inspect_disc_set(self.root, playlist, "PS")
        self.assertEqual(status["disc_count"], MAX_PLAYLIST_ENTRIES)
        self.assertIn("UNSUPPORTED_DISC_REFERENCE", status["warnings"])
        self.assertIn("DISC_REFERENCE_LIMIT", status["warnings"])

    def test_pbp_internal_disc_count_stays_unknown(self):
        rom = self.write("Roms/PS/Existing.pbp", "not parsed as a PBP")
        status = inspect_disc_set(self.root, rom, "PS")
        self.assertEqual(status["kind"], "native_container")
        self.assertIsNone(status["disc_count"])
        self.assertIn("existing emulator", status["description"])

    def test_invalid_query_data_is_rejected(self):
        backend = SpruceBackend(self.root)
        for call in (lambda: backend.games(4), lambda: backend.favorites(search="\0"), lambda: backend.recent(search=42)):
            with self.assertRaises(SpruceError):
                call()

    def test_demo_obeys_same_filter_contract_and_labels_disc_fixtures(self):
        backend = DemoBackend()
        self.assertEqual(len(backend.favorites("PS")), 1)
        self.assertEqual(len(backend.recent("PSP", "skyline")), 1)
        self.assertEqual(backend.recent("PS", "skyline"), [])
        game = backend.games("PS")["items"][0]
        info = backend.game_info(game["id"])
        self.assertTrue(info["disc_set"]["sample"])
        self.assertEqual(info["disc_set"]["missing_count"], 1)


if __name__ == "__main__":
    unittest.main()
