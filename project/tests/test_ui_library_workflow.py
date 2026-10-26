"""Behavioral host regressions for library navigation and backup history."""
import unittest

from psp_shell.demo import DemoBackend
from psp_shell.ui.model import NavigationModel


def games(start=0, stop=85, **extra):
    return [{"game_id": str(index), "label": f"Game {index:03d}", "system_id": "PSP",
             "availability": "available", **extra} for index in range(start, stop)]


def reply(model, context, value, method="fixture", params=None):
    return model.receive(model._request(method, params, context), value)


def choose(model, title):
    dialog = model.snapshot().dialog
    for _ in dialog.choices:
        current = model.snapshot().dialog
        if current.choices[current.selected].title == title:
            return model.handle("confirm")
        model.handle("down")
    raise AssertionError("Missing choice " + title)


def select(model, identifier):
    for _ in range(len(model.snapshot().items)):
        if model.snapshot().selected_item.id == identifier:
            return model.handle("confirm")
        model.handle("down")
    raise AssertionError("Missing item " + identifier)


class LibraryWorkflowTests(unittest.TestCase):
    def test_page_two_and_legacy_identity_restore_request_anchor(self):
        model = NavigationModel()
        request = model.handle("confirm")[0]
        model.receive(request, {"items": games(0, 40), "offset": 0, "total": 85})
        for _ in range(40):
            requests = model.handle("down")
        model.receive(requests[0], {"items": games(40, 80), "offset": 40, "total": 85})
        model.handle("down")
        state = model.export_state()
        self.assertEqual(state["schema"], 2)
        restored = NavigationModel(restored_state=state)
        query = next(c for c in restored.initial_commands() if c.context == "games")
        self.assertEqual(query.params["offset"], 40)
        self.assertEqual(query.params["focus_game_id"], "41")
        # The backend finds the same identity after sorting/refresh moved it.
        restored.receive(query, {"items": [games(41, 42)[0]] + games(0, 39), "offset": 0, "total": 85, "focus_id": "41"})
        self.assertEqual(restored.snapshot().selected_item.id, "41")
        old = NavigationModel(restored_state={"schema": 1, "games_view": "all", "focus": {"0": "41"}})
        self.assertEqual(next(c for c in old.initial_commands() if c.context == "games").params["focus_game_id"], "41")

    def test_favorites_restore_finds_identity_across_all_history_pages(self):
        model = NavigationModel()
        model.handle("down")
        model.receive(model.handle("confirm")[0], games())
        for _ in range(41):
            model.handle("down")
        restored = NavigationModel(restored_state=model.export_state())
        query = next(c for c in restored.initial_commands() if c.context == "favorites")
        restored.receive(query, games(1, 85))
        self.assertEqual(restored.snapshot().selected_item.id, "41")
        self.assertEqual(restored.snapshot().offset, 40)

    def test_search_stays_in_favorites_and_global_search_clears_old_system(self):
        model = NavigationModel()
        model.handle("down")
        model.receive(model.handle("confirm")[0], games())
        model.handle("search")
        model.handle("text", "041")
        request = model.handle("submit_text")[0]
        self.assertEqual(request.method, "library.favorites")
        self.assertEqual(request.params, {"search": "041"})
        model.receive(request, games(41, 42))
        self.assertEqual(model.snapshot().title, "Favorites")
        model.handle("back")
        model._system_id = "PSP"
        model.handle("search")
        model.handle("text", "Island")
        request = model.handle("submit_text")[0]
        self.assertNotIn("system_id", request.params)

    def test_all_loaded_systems_and_unknown_counts_are_truthful(self):
        model = NavigationModel()
        reply(model, "systems", [{"system_id": "GBA", "label": "Game Boy Advance", "game_count": None},
                                 {"system_id": "PORTS", "label": "Ports", "game_count": 3}])
        self.assertEqual(next(i.subtitle for i in model.snapshot().items if i.id == "GBA"), "Browse games")
        model.handle("menu")
        choose(model, "System: All systems")
        command = choose(model, "Game Boy Advance")[0]
        self.assertEqual(command.params["system_id"], "GBA")

    def test_favorite_removal_overrides_cached_record_and_late_cache(self):
        model = NavigationModel()
        cache = model._request("library.favorites", context="favorites_cache")
        model.set_category_items(0, games(0, 1, favorite=True))
        request = model.handle("favorite")[0]
        self.assertFalse(request.params["enabled"])
        model.receive(request, {"enabled": False})
        model.receive(cache, games(0, 1, favorite=True))
        self.assertFalse(model.snapshot().selected_item.favorite)
        # A later fresh native read supersedes the local acknowledged override.
        reply(model, "favorites_cache", games(0, 1, favorite=True))
        self.assertTrue(model.snapshot().selected_item.favorite)

    def test_surprise_and_pick_another_use_current_scope_without_launch(self):
        model = NavigationModel(demo=True)
        model._games_view = "favorites"
        model._history_filters["favorites"] = "GBA"
        model._history_search["favorites"] = "Island"
        model.handle("menu")
        request = choose(model, "Surprise me")[0]
        self.assertEqual(request.params, {"source": "favorites", "system_id": "GBA", "search": "Island"})
        model.receive(request, games(0, 1)[0])
        request = choose(model, "Pick another")[0]
        self.assertEqual(request.method, "library.random")
        self.assertEqual(request.params["exclude_game_id"], "0")
        self.assertIsNone(model.exit_request)

    def test_demo_collections_reuse_game_ids_and_readonly_management(self):
        backend, model = DemoBackend(), NavigationModel(demo=True)
        reply(model, "systems", backend.systems())
        request = select(model, "collections")[0]
        model.receive(request, backend.collections())
        collection = model.snapshot().selected_item.id
        request = model.handle("confirm")[0]
        self.assertEqual(request.params["source"], "collection")
        self.assertEqual(request.params["collection_id"], collection)
        result = backend.games(**request.params)
        model.receive(request, result)
        self.assertTrue(all(item.id.startswith("sample:") for item in model.snapshot().items))
        model.handle("back")
        select(model, "manage_collections")
        self.assertIn("preview", model.snapshot().dialog.title.lower())
        self.assertFalse(any(c.method == "tool.launch" for c in model.snapshot().dialog.choices))

    def test_jump_selects_backend_focus_without_changing_filter(self):
        model = NavigationModel()
        model._games_view = "system"
        model._system_id = "GBA"
        model.handle("menu")
        choose(model, "Jump to letter")
        command = choose(model, "M")[0]
        self.assertEqual(command.params["jump"], "M")
        self.assertEqual(command.params["sort"], "title_asc")
        self.assertEqual(command.params["system_id"], "GBA")
        model.receive(command, {"items": games(40, 80), "total": 100, "offset": 40, "focus_id": "49"})
        self.assertEqual(model.snapshot().selected_item.id, "49")

    def test_text_size_help_and_empty_state_are_controller_reachable(self):
        model = NavigationModel()
        select(model, "help")
        choose(model, "Text size")
        command = choose(model, "175%")[0]
        self.assertEqual(command.params["changes"], {"text_scale": 1.75})
        model = NavigationModel()
        model.set_category_items(0, [])
        model.handle("confirm")
        self.assertIn("Clear filters", [c.title for c in model.snapshot().dialog.choices])

    def test_long_disc_names_never_hide_warning_or_details(self):
        model = NavigationModel()
        discs = [{"label": str(index) + " long title" * 40, "available": index != 19} for index in range(20)]
        reply(model, "game_info", {**games(0, 1)[0], "warnings": ["REQUIRED_FILES_MISSING"],
              "disc_set": {"kind": "playlist", "disc_count": 20, "discs": discs, "warnings": ["MISSING_DISC_FILE"]}})
        dialog = model.snapshot().dialog
        self.assertTrue(dialog.message.startswith("Warning:"))
        self.assertIn("Required system files are missing", dialog.message)
        self.assertLess(len(dialog.message), 2048)
        choose(model, "Details")
        seen = []
        while True:
            seen.append(model.snapshot().dialog.message)
            self.assertLess(len(seen[-1]), 2048)
            if not any(c.title == "Next details" for c in model.snapshot().dialog.choices):
                break
            choose(model, "Next details")
        self.assertIn("Disc 20:", "\n".join(seen))
        self.assertIn(" · missing", "\n".join(seen))


class DelayedActionTests(unittest.TestCase):
    def test_moving_to_another_game_invalidates_pending_information(self):
        model = NavigationModel()
        model.set_category_items(0, games(0, 2))
        reply(model, "capabilities", {"game_information": True})
        model.handle("confirm")
        request = choose(model, "Game information")[0]
        model.handle("down")
        self.assertEqual(model.snapshot().selected_item.id, "1")
        model.receive(request, games(0, 1)[0])
        self.assertIsNone(model.snapshot().dialog)

    def test_cancelled_information_and_error_do_not_reopen_screen(self):
        model = NavigationModel()
        request = model._request("game.info", {"game_id": "0"}, "game_info")
        model.handle("right")
        model.receive(request, games(0, 1)[0])
        self.assertIsNone(model.snapshot().dialog)
        request = model._request("game.info", {"game_id": "0"}, "game_info")
        model.handle("left")
        model.error(request, "MISSING", "Game disappeared")
        self.assertIsNone(model.snapshot().dialog)
        self.assertFalse(model.snapshot().loading)

    def test_stale_hardware_receipt_has_no_discarded_request_loading_leak(self):
        model = NavigationModel()
        request = model._request("hardware.apply", {}, "hardware_apply")
        model.handle("right")
        self.assertEqual(model.receive(request, {"generation": 4}), [])
        self.assertFalse(model.snapshot().loading)
        self.assertFalse(model._pending)
        self.assertEqual(model._hardware_generation, 4)

    def test_stale_setting_receipt_and_failure_remain_in_recent_actions(self):
        model = NavigationModel()
        request = model._request("settings.apply", {}, "apply")
        model.handle("right")
        model.receive(request, {"generation": 3, "transaction_id": "t3", "preferences": {"text_scale": 1.75}})
        self.assertEqual(model.preferences.text_scale, 1.75)
        self.assertEqual(model._last_transaction, "t3")
        self.assertIsNone(model.snapshot().dialog)
        request = model._request("settings.apply", {}, "apply")
        model.handle("right")
        model.error(request, "DISK_FULL", "Preference could not be saved")
        self.assertTrue(any("DISK_FULL" in message for message in model._mutation_messages))

    def test_superseded_backup_start_is_cancelled_without_touching_current_job(self):
        model = NavigationModel()
        first = model._request("backup.verify", {"entry_id": "old"}, "backup_verify")
        latest = model._request("backup.verify", {"entry_id": "new"}, "backup_verify")
        model.receive(latest, {"job_id": "new-job", "entry_id": "new", "state": "running"})
        cancel = model.receive(first, {"job_id": "old-job", "entry_id": "old", "state": "running"})[0]
        self.assertEqual(cancel.params, {"job_id": "old-job"})
        model.receive(cancel, {"state": "cancelled"})
        self.assertEqual(model._backup_job["job_id"], "new-job")

    def test_old_manual_cancel_receipt_cannot_stop_a_new_verification(self):
        model = NavigationModel()
        reply(model, "backup_verify", {"job_id": "old-job", "entry_id": "old", "state": "running"})
        cancel = model.handle("back")[0]
        model.handle("right")
        reply(model, "backup_verify", {"job_id": "new-job", "entry_id": "new", "state": "running"})
        model.receive(cancel, {"job_id": "old-job", "state": "cancelled"})
        self.assertEqual(model._backup_job["job_id"], "new-job")
        self.assertEqual(model.poll_commands(1)[0].params, {"job_id": "new-job"})


class BackupHistoryNavigationTests(unittest.TestCase):
    def detail(self):
        return {"entry_id": "backup-one", "label": "Before update", "scope": "saves", "bytes": 500,
                "generation": 4, "status": "previously_verified", "last_verified_at_utc": "2026-10-26T00:00:00Z"}

    def test_label_edit_and_removal_never_pass_payload_paths(self):
        model = NavigationModel()
        reply(model, "backup_detail", self.detail())
        self.assertIn("Previously checked", model.snapshot().dialog.message)
        choose(model, "Rename label")
        self.assertEqual(model.snapshot().keyboard.submit_label, "Save label")
        model.handle("text", " copy")
        request = model.handle("submit_text")[0]
        self.assertEqual(request.method, "backup.rename")
        self.assertEqual(set(request.params), {"entry_id", "label", "expected_generation"})
        reply(model, "backup_detail", self.detail())
        choose(model, "Remove from history")
        self.assertEqual(model.snapshot().dialog.selected, 1)
        request = choose(model, "Remove history entry")[0]
        self.assertEqual(request.method, "backup.remove")
        self.assertNotIn("path", repr(request.params))

    def test_large_history_pages_and_failed_check_timestamp_are_reachable(self):
        model = NavigationModel()
        entries = [{"entry_id": str(index), "label": f"Backup {index}"} for index in range(1000)]
        reply(model, "backup_history", {"generation": 3, "entries": entries})
        for _ in range(49):
            choose(model, "Next backups")
        request = choose(model, "Backup 999")[0]
        self.assertEqual(request.params, {"entry_id": "999"})
        model.receive(request, {**self.detail(), "last_check": {"status": "unavailable", "checked_at_utc": "2026-10-26T01:00:00Z", "reason": "Missing backup bytes"}})
        self.assertIn("Last check 2026-10-26 01:00:00 UTC · unavailable", model.snapshot().dialog.message)

    def test_history_return_and_both_label_cancel_paths_restore_selection(self):
        entries = [{"entry_id": str(index), "label": f"Backup {index}"} for index in range(80)]
        model = NavigationModel()
        reply(model, "backup_history", {"generation": 4, "entries": entries})
        for _ in range(3):
            choose(model, "Next backups")
        request = choose(model, "Backup 65")[0]
        detail = {**self.detail(), "entry_id": "65", "label": "Backup 65"}
        model.receive(request, detail)
        request = choose(model, "Back to history")[0]
        model.receive(request, {"generation": 4, "entries": entries})
        dialog = model.snapshot().dialog
        self.assertEqual(dialog.choices[dialog.selected].title, "Backup 65")
        model.receive(model.handle("confirm")[0], detail)
        choose(model, "Rename label")
        model.handle("text", " edited")
        model.handle("back")
        self.assertEqual(model.snapshot().dialog.title, "Backup 65")
        choose(model, "Rename label")
        model.handle("text", " edited")
        for _ in range(10):
            model.handle("down")
        for _ in range(4):
            if model.snapshot().keyboard.keys[model.snapshot().keyboard.selected] == "Cancel":
                break
            model.handle("right")
        model.handle("confirm")
        self.assertIsNone(model.snapshot().keyboard)
        self.assertEqual(model.snapshot().dialog.title, "Backup 65")

    def test_verification_polls_one_job_and_back_cancels_it(self):
        model = NavigationModel()
        reply(model, "backup_detail", self.detail())
        request = choose(model, "Check backup bytes")[0]
        model.receive(request, {"job_id": "job-one", "entry_id": "backup-one", "state": "running", "phase": "hashing", "files_checked": 0, "bytes_checked": 0})
        poll = model.poll_commands(1)[0]
        self.assertEqual(model.poll_commands(2), [])
        model.receive(poll, {"job_id": "job-one", "entry_id": "backup-one", "state": "running", "phase": "hashing", "files_checked": 1, "bytes_checked": 200})
        self.assertEqual(model.poll_commands(1.1), [])
        self.assertIn("200 bytes", model.snapshot().dialog.message)
        cancel = model.handle("back")[0]
        self.assertEqual(cancel.method, "backup.cancel")
        self.assertEqual(model.poll_commands(3), [])
        self.assertIsNone(model.snapshot().dialog)

    def test_recording_phase_does_not_promise_cancellation(self):
        model = NavigationModel()
        reply(model, "backup_verify", {"job_id": "job", "entry_id": "backup-one", "state": "running", "phase": "recording", "cancellable": False})
        self.assertNotIn("You can cancel", model.snapshot().dialog.message)
        self.assertEqual([c.title for c in model.snapshot().dialog.choices], ["Back"])
        choose(model, "Back")
        self.assertEqual(model.poll_commands(5), [])


if __name__ == "__main__":
    unittest.main()
