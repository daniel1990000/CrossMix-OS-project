# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
sys.path.insert(0, str(PROJECT / "packaging"))
import migrate_crossmix as migration
import overlay


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spruce-migration-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.target = self.root / "source", self.root / "target"
        self.source.mkdir()
        self.target.mkdir()
        self.rom = "Roms/GBA/a $;' é.gba"
        self.put(self.source, self.rom, b"ROM source")
        self.put(self.target, self.rom, b"ROM target: never read/modified")
        self.put(self.target, "Emu/GBA/config.json", b"{}\n")
        self.record = {"rompath": "/mnt/SDCARD/" + self.rom, "launch": "/mnt/SDCARD/Emus/GBA/launch.sh",
                       "label": "My game", "unknown": {"preserve": 42}}
        self.legacy = self.put(self.source, "Roms/favourite2.json", json.dumps(self.record).encode() + b"\n")
        self.favorites = self.put(self.target, "Saves/pyui-favorites.json", b"[]\n")
        self.save_path = "RetroArch/.retroarch/saves/mGBA/a.srm"
        self.battery = self.put(self.source, self.save_path, b"battery save")
        self.destination = "Saves/saves/mGBA/a.srm"
        self.selection = {"systems": {"GBA": "GBA"}, "battery_saves": [{"source": self.save_path,
            "destination": self.destination, "compatibility": {"reviewed": True, "kind": "battery-save",
            "evidence": "Owner confirmed same game/core native SRAM format; test on a copy"}}]}
        self.plan = self.root / "plan.json"

    def put(self, root, path, data):
        path = root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def preview(self):
        return migration.preview(self.source, self.target, self.selection, self.plan)

    def test_preview_no_mutation_and_exact_pyui_array_schema(self):
        original = self.legacy.read_bytes()
        report = self.preview()
        self.assertEqual(self.legacy.read_bytes(), original)
        self.assertEqual(self.favorites.read_bytes(), b"[]\n")
        self.assertFalse((self.target / self.destination).exists())
        self.assertEqual(report["provenance"][0]["original_record"]["unknown"], {"preserve": 42})
        result = migration.apply(self.plan, "first")
        records = json.loads(self.favorites.read_bytes())
        self.assertEqual(set(records[0]), {"rom_file_path", "game_system_name", "display_name"})
        self.assertEqual(records[0]["rom_file_path"], "/mnt/SDCARD/" + self.rom)
        self.assertEqual((self.target / self.destination).read_bytes(), b"battery save")
        self.assertEqual(self.legacy.read_bytes(), original)
        self.assertEqual(self.battery.read_bytes(), b"battery save")
        self.assertFalse(result["source_modified"])

    def test_apply_and_undo_preserve_unknown_files_and_original_saves(self):
        sentinel = self.put(self.target, "Saves/unrelated.data", b"keep newer data")
        self.preview()
        result = migration.apply(self.plan, "one")
        migration.undo(result["transaction"])
        self.assertEqual(self.favorites.read_bytes(), b"[]\n")
        self.assertFalse((self.target / self.destination).exists())
        self.assertEqual(sentinel.read_bytes(), b"keep newer data")
        self.assertEqual(self.battery.read_bytes(), b"battery save")

    def test_stale_source_or_target_blocks_all_writes(self):
        self.preview()
        self.battery.write_bytes(b"changed source save")
        with self.assertRaisesRegex(overlay.OverlayError, "source changed"):
            migration.apply(self.plan, "stale")
        self.assertEqual(self.favorites.read_bytes(), b"[]\n")
        self.battery.write_bytes(b"battery save")
        self.favorites.write_bytes(b"[ ]\n")
        with self.assertRaisesRegex(overlay.OverlayError, "destination changed"):
            migration.apply(self.plan, "stale")
        self.assertFalse((self.target / self.destination).exists())

    def test_newer_destination_save_blocks_undo(self):
        self.preview()
        result = migration.apply(self.plan, "one")
        save = self.target / self.destination
        save.write_bytes(b"new progress after migration")
        current_favorites = self.favorites.read_bytes()
        with self.assertRaisesRegex(overlay.OverlayError, "newer"):
            migration.undo(result["transaction"])
        self.assertEqual(save.read_bytes(), b"new progress after migration")
        self.assertEqual(self.favorites.read_bytes(), current_favorites)

    def test_save_recreated_after_undo_preflight_is_preserved(self):
        self.preview()
        result = migration.apply(self.plan, "late-save")
        save = self.target / self.destination
        favorites = self.favorites.read_bytes()
        real_hash, calls = migration.maybe_hash, []
        def recreate_after_preflight(path):
            value = real_hash(path)
            if path == save and not calls:
                calls.append(path)
                save.unlink()
                save.write_bytes(b"newer external save progress")
            return value
        with mock.patch.object(migration, "maybe_hash", side_effect=recreate_after_preflight):
            with self.assertRaisesRegex(overlay.OverlayError, "changed during undo"):
                migration.undo(result["transaction"])
        self.assertEqual(save.read_bytes(), b"newer external save progress")
        self.assertEqual(self.favorites.read_bytes(), favorites)
        journal = Path(result["transaction"]) / "journal.json"
        self.assertEqual(overlay.read_record(journal)["status"], "committed")

    def test_partial_undo_keeps_late_edit_and_retryable_journal(self):
        save = self.put(self.target, self.destination, b"prior battery save")
        self.selection["battery_saves"][0]["replace_existing"] = True
        self.preview()
        result = migration.apply(self.plan, "late-list")
        applied_favorites = self.favorites.read_bytes()
        real_write = migration.atomic_write
        def edit_after_first_restore(path, data):
            real_write(path, data)
            if path == save:
                self.favorites.write_bytes(b"newer external favorite list")
        with mock.patch.object(migration, "atomic_write", side_effect=edit_after_first_restore):
            with self.assertRaisesRegex(overlay.OverlayError, "changed during undo"):
                migration.undo(result["transaction"])
        self.assertEqual(save.read_bytes(), b"prior battery save")
        self.assertEqual(self.favorites.read_bytes(), b"newer external favorite list")
        transaction = Path(result["transaction"])
        self.assertEqual(overlay.read_record(transaction / "journal.json")["status"], "committed")
        self.assertEqual((transaction / "1.backup").read_bytes(), b"prior battery save")
        self.favorites.write_bytes(applied_favorites)  # Explicit conflict resolution.
        self.assertEqual(migration.undo(transaction)["restored"], 1)
        self.assertEqual(save.read_bytes(), b"prior battery save")
        self.assertEqual(self.favorites.read_bytes(), b"[]\n")
        self.assertEqual(overlay.read_record(transaction / "journal.json")["status"], "undone")

    def test_late_deleted_existing_save_is_not_recreated_by_undo(self):
        save = self.put(self.target, self.destination, b"prior battery save")
        self.selection["battery_saves"][0]["replace_existing"] = True
        self.preview()
        result = migration.apply(self.plan, "late-delete")
        real_hash, removed = migration.maybe_hash, []
        def delete_after_preflight(path):
            value = real_hash(path)
            if path == save and not removed:
                removed.append(path)
                save.unlink()
            return value
        with mock.patch.object(migration, "maybe_hash", side_effect=delete_after_preflight):
            with self.assertRaisesRegex(overlay.OverlayError, "changed during undo"):
                migration.undo(result["transaction"])
        self.assertFalse(save.exists())

    def test_conflict_requires_explicit_replacement_then_backup_hash_undo(self):
        existing = self.put(self.target, self.destination, b"destination battery")
        report = self.preview()
        self.assertFalse(any(x["kind"] == "battery-save" for x in report["operations"]))
        self.assertTrue(any("replace_existing" in x["reason"] for x in report["review"]))
        self.plan.unlink()
        self.selection["battery_saves"][0]["replace_existing"] = True
        self.preview()
        result = migration.apply(self.plan, "replace")
        self.assertEqual(existing.read_bytes(), b"battery save")
        migration.undo(result["transaction"])
        self.assertEqual(existing.read_bytes(), b"destination battery")

    def test_states_unknown_formats_and_unreviewed_saves_never_copy(self):
        self.selection["battery_saves"].extend([
            {"source": "foo.state", "destination": "Saves/saves/mGBA/foo.srm", "compatibility": {"reviewed": True}},
            {"source": self.save_path, "destination": "Saves/states/foo.auto", "compatibility": {"reviewed": True}},
            {"source": self.save_path, "destination": "Saves/saves/mGBA/no.srm", "compatibility": {"reviewed": False}}
        ])
        report = self.preview()
        self.assertEqual(sum(x["kind"] == "battery-save" for x in report["operations"]), 1)
        self.assertEqual(sum(x["kind"] == "battery-save" for x in report["review"]), 3)

    def test_generic_path_field_is_not_rom_identity(self):
        self.legacy.write_text(json.dumps({"path": "/mnt/SDCARD/" + self.rom}) + "\n")
        report = self.preview()
        self.assertFalse(any(x["kind"] == "favorites" for x in report["operations"]))
        self.assertTrue(any("rompath missing" in x["reason"] for x in report["review"]))

    def test_existing_unknown_target_fields_block_list_change(self):
        raw = json.dumps([{"rom_file_path": "/mnt/SDCARD/" + self.rom, "game_system_name": "GBA", "unknown": 1}]).encode()
        self.favorites.write_bytes(raw)
        report = self.preview()
        self.assertFalse(any(x["kind"] == "favorites" for x in report["operations"]))
        self.assertEqual(self.favorites.read_bytes(), raw)

    def test_existing_duplicate_preserves_metadata(self):
        original = [{"rom_file_path": "/mnt/SDCARD/" + self.rom, "game_system_name": "GBA", "display_name": "Current custom label"}]
        self.favorites.write_text(json.dumps(original))
        report = self.preview()
        self.assertFalse(any(x["kind"] == "favorites" for x in report["operations"]))
        self.assertEqual(json.loads(self.favorites.read_text()), original)

    def test_symlinks_traversal_and_case_collision_rejected(self):
        self.selection["battery_saves"].append({"source": "../outside.srm", "destination": "Saves/saves/x.srm"})
        report = self.preview()
        self.assertTrue(any("traversal" in x["reason"] for x in report["review"]))
        self.plan.unlink()
        self.battery.unlink()
        self.battery.symlink_to(self.legacy)
        report = self.preview()
        self.assertFalse(any(x["kind"] == "battery-save" for x in report["operations"]))

    def test_interrupted_copy_can_undo_using_prepared_journal(self):
        self.preview()
        real_write = migration.atomic_write
        def fail_battery(path, data):
            if path == self.target / self.destination:
                raise OSError("interrupted copy fixture")
            return real_write(path, data)
        with mock.patch.object(migration, "atomic_write", side_effect=fail_battery):
            with self.assertRaises(OSError):
                migration.apply(self.plan, "partial")
        self.assertNotEqual(self.favorites.read_bytes(), b"[]\n")
        transaction = self.target / "App/PSPMode/state/migrations/partial"
        migration.undo(transaction)
        self.assertEqual(self.favorites.read_bytes(), b"[]\n")

    def test_undo_refuses_corrupted_backup(self):
        self.preview()
        result = migration.apply(self.plan, "one")
        backup = Path(result["transaction"]) / "0.backup"
        backup.write_bytes(b"corrupt")
        with self.assertRaisesRegex(overlay.OverlayError, "backup hash"):
            migration.undo(result["transaction"])


if __name__ == "__main__":
    unittest.main()
