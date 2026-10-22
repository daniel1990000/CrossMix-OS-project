"""Integration checks for UI operations and the snapshot boundary."""
import json
from pathlib import Path
import tempfile
import unittest

from psp_shell.app import AppError, Dispatcher, guard_snapshot_outputs
from psp_shell.demo import DemoBackend
from psp_shell.settings import SettingsStore


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.backend = DemoBackend()
        self.store = SettingsStore(str(self.root / "preferences"))
        self.dispatcher = Dispatcher(self.backend, self.store, self.root / "reports")

    def tearDown(self):
        self.tmp.cleanup()

    def test_preference_preview_commit_undo_does_not_change_library(self):
        before = self.dispatcher.dispatch("library.query", {"system_id": "PSP"})
        current = self.dispatcher.dispatch("settings.get")
        preview = self.dispatcher.dispatch("settings.preview", {
            "changes": {"confirm": "east", "motion": False},
            "expected_generation": current["generation"]})
        applied = self.dispatcher.dispatch("settings.apply", {
            "preview_id": preview["preview_id"], "request_id": "integration-apply",
            "expected_generation": current["generation"]})
        self.assertEqual(applied["preferences"]["confirm"], "east")
        undone = self.dispatcher.dispatch("settings.undo", {
            "transaction_id": applied["transaction_id"], "request_id": "integration-undo",
            "expected_generation": applied["generation"]})
        self.assertEqual(undone["preferences"]["confirm"], current["preferences"]["confirm"])
        self.assertEqual(self.dispatcher.dispatch("library.query", {"system_id": "PSP"}), before)

    def test_no_standalone_launch_even_with_a_sample_game_id(self):
        game = self.backend.games()["items"][0]
        with self.assertRaises(AppError) as caught:
            self.dispatcher.dispatch("game.launch", {"game_id": game["game_id"], "mode": "normal"})
        self.assertEqual(caught.exception.code, "DEMO_ONLY")
        self.assertIsNone(self.dispatcher.pending_launch)

    def test_no_command_or_storage_endpoint(self):
        for method, params in (("shell.execute", {"command": "do-not-execute"}),
                               ("usb.begin", {}), ("power.request", {"action": "shutdown"})):
            with self.assertRaises(AppError):
                self.dispatcher.dispatch(method, params)
        with self.assertRaises(AppError):
            self.dispatcher.dispatch("library.query", {"command": "unexpected"})
        with self.assertRaises(AppError):
            self.dispatcher.dispatch("library.query", {"limit": True})

    def test_control_capabilities_do_not_offer_unqualified_writes(self):
        result = self.dispatcher.dispatch("controls.capabilities")
        self.assertEqual(len(result["profiles"]), 3)
        self.assertFalse(any(item["writable"] for item in result["profiles"]))
        for method in ("controls.preview", "controls.apply", "controls.undo"):
            with self.assertRaises(AppError) as caught:
                self.dispatcher.dispatch(method, {"profile_id": "ppsspp-native-unqualified"})
            self.assertEqual(caught.exception.code, "UNQUALIFIED_CONTROLS")

    def test_search_pagination_and_favorites_use_the_same_game_id(self):
        matches = self.dispatcher.dispatch("library.query", {"search": "skyline", "limit": 1})
        self.assertEqual(matches["total"], 1)
        game_id = matches["items"][0]["game_id"]
        self.dispatcher.dispatch("library.favorite.set", {"game_id": game_id, "enabled": False})
        self.assertNotIn(game_id, {g["game_id"] for g in self.backend.favorites()})
        self.dispatcher.dispatch("library.favorite.set", {"game_id": game_id, "enabled": True})
        self.assertIn(game_id, {g["game_id"] for g in self.backend.favorites()})

    def test_support_report_collects_no_rom_names_or_paths(self):
        self.dispatcher.dispatch("library.query", {"search": "Skyline"})
        report = self.dispatcher.dispatch("support.export")
        raw = Path(report["path"]).read_text()
        parsed = json.loads(raw)
        self.assertEqual(parsed["evidence"], "host")
        self.assertNotIn("Skyline", raw)
        self.assertNotIn("sample:PSP", raw)
        self.assertFalse(parsed["physical_device_verified"])

    def test_snapshot_rejects_report_screenshot_and_symlinked_parent_writes(self):
        card = self.root / "card"
        card.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(card, target_is_directory=True)
        for output in (card / "report.json", card / "screen.png", alias / "screen.png"):
            with self.assertRaises(AppError) as caught:
                guard_snapshot_outputs(card, [output])
            self.assertEqual(caught.exception.code, "READ_ONLY_SNAPSHOT")
        guard_snapshot_outputs(card, [self.root / "report.json"])
        self.assertEqual(list(card.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
