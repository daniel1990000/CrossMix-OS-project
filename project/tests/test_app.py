"""Integration checks for UI operations and the snapshot boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from psp_shell.app import AppError, Dispatcher, guard_snapshot_outputs, _restore_navigation
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

    def test_discovery_scope_is_forwarded_without_accepting_paths(self):
        class Backend:
            def games(inner, **params):
                return params
            def random(inner, **params):
                return params
            def collections(inner):
                return [{"id": "collection:fixture", "label": "Play later"}]
        dispatcher = Dispatcher(Backend(), self.store, self.root)
        scope = {"source": "collection", "collection_id": "collection:fixture",
                 "system_id": "GBA", "search": "island", "sort": "title_desc", "available_only": True}
        result = dispatcher.dispatch("library.query", {**scope, "offset": 40, "limit": 40})
        self.assertEqual(result, {**scope, "offset": 40, "limit": 40})
        self.assertEqual(dispatcher.dispatch("library.random", {**scope, "exclude_game_id": "game:old"}),
                         {**scope, "exclude_game_id": "game:old"})
        self.assertEqual(dispatcher.dispatch("library.collections")[0]["label"], "Play later")
        for invalid in ({"source": "shell"}, {"source": "collection"},
                        {"source": "all", "collection_id": "stale"}, {"available_only": 1},
                        {"sort": "playtime"}, {"offset": 100001}, {"path": "/tmp/collection"}):
            with self.subTest(invalid=invalid), self.assertRaises(AppError):
                dispatcher.dispatch("library.query", invalid)

    def test_backup_job_routes_accept_only_catalog_ids_and_generation(self):
        class History:
            def verify(inner, **params):
                return params
            def rename(inner, **params):
                return params
            def cancel(inner, **params):
                return params
        dispatcher = Dispatcher(self.backend, self.store, self.root, backup_adapter=History())
        identity = {"entry_id": "entry-opaque", "expected_generation": 2}
        self.assertEqual(dispatcher.dispatch("backup.verify", identity), identity)
        self.assertEqual(dispatcher.dispatch("backup.rename", {**identity, "label": "Before settings"})["label"],
                         "Before settings")
        self.assertEqual(dispatcher.dispatch("backup.cancel", {"job_id": "job-opaque"}), {"job_id": "job-opaque"})
        for invalid in ({**identity, "payload": "/private/save"},
                        {**identity, "expected_generation": True}, {"entry_id": "entry-opaque"}):
            with self.subTest(invalid=invalid), self.assertRaises(AppError):
                dispatcher.dispatch("backup.verify", invalid)
        for method in ("backup.restore", "backup.delete_payload", "backup.register"):
            with self.subTest(method=method), self.assertRaises(AppError):
                dispatcher.dispatch(method, {"path": "/private/save"})

    def test_navigation_reader_accepts_old_and_new_schemas_without_truthy_versions(self):
        for schema in (1, 2):
            (self.root / "navigation.json").write_text(json.dumps({"schema": schema}))
            self.assertEqual(_restore_navigation(self.root), {"schema": schema})
        for schema in (True, 3, "2"):
            (self.root / "navigation.json").write_text(json.dumps({"schema": schema}))
            self.assertIsNone(_restore_navigation(self.root))

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

    def test_appearance_preview_reopens_with_saved_settings_category(self):
        state = self.root / "preview-state"
        command = [sys.executable, "-m", "psp_shell", "--demo", "--headless", "--frames", "1",
                   "--screen", "appearance", "--state-dir", str(state)]
        environment = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        for _ in range(2):
            result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((state / "navigation.json").read_text())["category"], 3)


if __name__ == "__main__":
    unittest.main()
