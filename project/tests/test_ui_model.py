"""Navigation acceptance tests independent of SDL and any physical card."""
import dataclasses
import tempfile
import unittest

from psp_shell.ui.model import NavigationModel, Preferences, UICommand, UIItem


def game(identifier="gba:test", **changes):
    return {"game_id": identifier, "label": "A game", "system_id": "GBA",
            "availability": "available", **changes}


class NavigationTests(unittest.TestCase):
    def test_four_categories_restore_independent_focus(self):
        model = NavigationModel()
        model.handle("down")
        self.assertEqual(model.snapshot().selected_item.id, "favorites")
        for expected in (1, 2, 3, 0):
            model.handle("right")
            self.assertEqual(model.snapshot().category, expected)
        self.assertEqual(model.snapshot().selected_item.id, "favorites")
        self.assertEqual(model.snapshot().categories, ("Games", "Continue Playing", "Tools", "Settings"))

    def test_system_browse_back_restores_root_focus(self):
        model = NavigationModel()
        systems = next(c for c in model.initial_commands() if c.method == "library.systems")
        model.receive(systems, [{"id": "GBA", "label": "Game Boy Advance", "game_count": 2}])
        for _ in range(4):
            model.handle("down")
        command = model.handle("confirm")[0]
        self.assertEqual(command.params["system_id"], "GBA")
        model.receive(command, {"items": [game()], "offset": 0, "total": 1})
        self.assertEqual(model.snapshot().title, "Game Boy Advance")
        model.handle("back")
        self.assertEqual(model.snapshot().selected_item.id, "GBA")

    def test_outdated_search_response_cannot_replace_newer_results(self):
        model = NavigationModel()
        model.handle("search")
        model.handle("text", "old")
        old = model.handle("submit_text")[0]
        model.handle("search")
        for _ in range(3):
            model.handle("delete_text")
        model.handle("text", "new")
        new = model.handle("submit_text")[0]
        model.receive(new, {"items": [game("new")], "total": 1, "offset": 0})
        model.receive(old, {"items": [game("old")], "total": 1, "offset": 0})
        self.assertEqual(model.snapshot().selected_item.id, "new")

    def test_search_accepts_unicode_literal_and_bounds_length(self):
        model = NavigationModel()
        model.handle("search")
        model.handle("text", "日本語 $(touch /tmp/wrong); 'quoted'")
        command = model.handle("submit_text")[0]
        self.assertIn("$(touch /tmp/wrong)", command.params["search"])
        self.assertIn("日本語", command.params["search"])
        model.handle("search")
        model.handle("text", "é" * 400)
        self.assertLessEqual(len(model.snapshot().keyboard.text), 128)
        model.handle("delete_text")
        self.assertTrue(model.snapshot().keyboard.text.encode("utf-8"))

    def test_controller_keyboard_can_submit_and_cancel_without_typing(self):
        model = NavigationModel()
        model.handle("search")
        model.handle("confirm")  # A
        for _ in range(2):
            model.handle("right")
        model.handle("confirm")  # C
        command = model.handle("submit_text")[0]
        self.assertEqual(command.params["search"], "AC")
        model.handle("search")
        model.handle("back")
        self.assertIsNone(model.snapshot().keyboard)

    def test_continue_without_verified_state_never_offers_resume(self):
        model = NavigationModel()
        model.set_category_items(1, [game(resume_available=False)])
        model.handle("right")
        model.handle("confirm")
        self.assertEqual([c.title for c in model.snapshot().dialog.choices], ["Fresh start", "Cancel"])
        launch = model.handle("confirm")[0]
        self.assertEqual(launch.method, "game.launch")
        self.assertEqual(launch.params["mode"], "fresh")

    def test_verified_state_offers_resume_and_fresh_separately(self):
        model = NavigationModel()
        model.set_category_items(1, [game(resume_available=True)])
        model.handle("right")
        model.handle("confirm")
        self.assertEqual([c.title for c in model.snapshot().dialog.choices], ["Resume", "Fresh start", "Cancel"])
        model.handle("down")
        command = model.handle("confirm")[0]
        self.assertEqual(command.params["mode"], "fresh")

    def test_resume_dialog_keeps_original_checkpoint_verification_time(self):
        model = NavigationModel()
        record = game(resume_available=True, state_recorded_at="2026-10-20T12:34:56.123456+00:00")
        model.set_category_items(1, [record])
        model.handle("right")
        self.assertEqual(model.snapshot().selected_item.state_recorded_at, record["state_recorded_at"])
        model.handle("confirm")
        self.assertIn("Checkpoint verified 2026-10-20 12:34:56 UTC", model.snapshot().dialog.message)
        self.assertNotIn("Checkpoint saved", model.snapshot().dialog.message)
        model.handle("back")
        model.set_category_items(1, [{**record, "last_save_attempt": "failed", "last_session_at": "2026-10-22T15:00:00+00:00"}])
        model.handle("confirm")
        self.assertIn("Checkpoint verified 2026-10-20 12:34:56 UTC", model.snapshot().dialog.message)
        self.assertNotIn("2026-10-22", model.snapshot().dialog.message)

    def test_checkpoint_time_requires_real_utc_and_is_never_fabricated_in_demo(self):
        for value in ("", "not a timestamp", "2026-10-20T12:34:56", "2026-10-20T12:34:56+03:00", 123):
            with self.subTest(value=value):
                model = NavigationModel()
                model.set_category_items(0, [game(resume_available=True, state_recorded_at=value)])
                model.handle("confirm")
                self.assertNotIn("Checkpoint verified", model.snapshot().dialog.message)
        model = NavigationModel(demo=True)
        model.set_category_items(0, [game(resume_available=True, state_recorded_at="2026-10-20T12:34:56Z")])
        model.handle("confirm")
        self.assertNotIn("Checkpoint verified", model.snapshot().dialog.message)
        model = NavigationModel()
        model.set_category_items(0, [game(resume_available=False, state_recorded_at="2026-10-20T12:34:56Z")])
        model.handle("confirm")
        self.assertNotIn("Checkpoint verified", model.snapshot().dialog.message)

    def test_demo_launch_is_a_notice_and_never_a_backend_command(self):
        model = NavigationModel(demo=True)
        model.set_category_items(0, [game(resume_available=True)])
        self.assertEqual(model.handle("confirm"), [])
        self.assertIn("demonstration", model.snapshot().dialog.message)
        self.assertEqual(model.handle("confirm"), [])
        self.assertIn("Sample", model.snapshot().dialog.title)
        self.assertIsNone(model.exit_request)

    def test_unreviewed_tool_uses_explicit_classic_route(self):
        model = NavigationModel()
        model.set_category_items(2, [{"id": "app:system", "label": "System tools", "availability": "legacy_only"}])
        model.handle("right")
        model.handle("right")
        self.assertEqual(model.handle("confirm"), [])
        self.assertEqual(model.snapshot().dialog.selected, 1)
        model.handle("up")
        command = model.handle("confirm")[0]
        self.assertEqual(command.method, "interface.switch")
        self.assertEqual(command.params, {"interface": "classic"})

    def test_preference_preview_requires_explicit_apply_and_preserves_gameplay(self):
        model = NavigationModel()
        for _ in range(3):
            model.handle("right")
        preview = model.handle("confirm")[0]
        self.assertEqual(preview.method, "settings.preview")
        self.assertEqual(preview.params["changes"], {"confirm": "east"})
        self.assertEqual(model.preferences.confirm, "south")
        model.receive(preview, {"preview_id": "p1", "diff": [{"key": "confirm", "before": "south", "after": "east"}]})
        apply = model.handle("confirm")[0]
        self.assertEqual(apply.method, "settings.apply")
        self.assertNotIn("gameplay", repr(apply.params))
        model.receive(apply, {"transaction_id": "t1", "generation": 1, "preferences": {"confirm": "east"}})
        self.assertEqual(model.preferences.confirm, "east")
        self.assertIn("undo", [item.id for item in model.snapshot().items])

    def test_launch_exit_requires_explicit_backend_acceptance(self):
        model = NavigationModel()
        model.set_category_items(0, [game()])
        model.handle("confirm")
        command = model.handle("confirm")[0]
        model.error(command, "UNSUPPORTED_PROFILE", "Return to spruce.")
        self.assertIsNone(model.exit_request)
        self.assertTrue(model.snapshot().dialog.error)
        model.handle("back")
        model.handle("confirm")
        retry = model.handle("confirm")[0]
        model.receive(retry, {"state": "releasing_ui"})
        self.assertEqual(model.exit_request, "launch")

    def test_favorite_is_updated_after_acknowledgement(self):
        model = NavigationModel()
        model.set_category_items(0, [game()])
        command = model.handle("favorite")[0]
        self.assertFalse(model.snapshot().selected_item.favorite)
        model.receive(command, {"updated": True})
        self.assertTrue(model.snapshot().selected_item.favorite)

    def test_pagination_requests_next_batch_and_previous_last_item(self):
        model = NavigationModel()
        first = model.handle("confirm")[0]
        model.receive(first, {"items": [game(str(i)) for i in range(40)], "total": 41, "offset": 0})
        for _ in range(39):
            model.handle("down")
        next_page = model.handle("down")[0]
        self.assertEqual(next_page.params["offset"], 40)
        model.receive(next_page, {"items": [game("40")], "total": 41, "offset": 40})
        previous = model.handle("up")[0]
        model.receive(previous, {"items": [game(str(i)) for i in range(40)], "total": 41, "offset": 0})
        self.assertEqual(model.snapshot().selected_item.id, "39")

    def test_focus_survives_launch_return_state_export(self):
        model = NavigationModel()
        first = model.handle("confirm")[0]
        model.receive(first, {"items": [game("a"), game("b")], "total": 2})
        model.handle("down")
        restored = NavigationModel(restored_state=model.export_state())
        query = next(c for c in restored.initial_commands() if c.method == "library.query")
        restored.receive(query, {"items": [game("a"), game("b")], "total": 2})
        self.assertEqual(restored.snapshot().selected_item.id, "b")

    def test_snapshot_and_dialog_arguments_are_immutable(self):
        model = NavigationModel()
        model.set_category_items(0, [game()])
        snapshot = model.snapshot()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.selected = 2
        model.handle("confirm")
        with self.assertRaises(TypeError):
            model.snapshot().dialog.choices[0].params["game_id"] = "other"

    def test_clock_is_explicit_frame_data_and_does_not_change_navigation(self):
        model = NavigationModel()
        before = model.export_state()
        self.assertEqual(model.snapshot().display_clock, "")
        first = model.snapshot(10.0, display_clock="10/22  16:45")
        self.assertEqual(first, model.snapshot(900.0, display_clock="10/22  16:45"))
        second = model.snapshot(901.0, display_clock="10/22  16:46")
        self.assertEqual(first.display_clock, "10/22  16:45")
        self.assertNotEqual(first, second)
        self.assertEqual(before, model.export_state())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            first.display_clock = "10/22  16:46"

    def test_separate_ui_sessions_do_not_collide_in_persistent_settings(self):
        from psp_shell.settings import SettingsStore
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(directory)
            request_ids = []
            for _ in range(2):
                model = NavigationModel()
                initial = next(c for c in model.initial_commands() if c.method == "settings.get")
                model.receive(initial, store.get())
                for _ in range(3):
                    model.handle("right")
                preview = model.handle("confirm")[0]
                model.receive(preview, store.preview(dict(preview.params)))
                apply = model.handle("confirm")[0]
                request_ids.append(apply.params["request_id"])
                result = store.apply(dict(apply.params))
                model.receive(apply, result)
                retry = store.apply(dict(apply.params))
                self.assertTrue(retry["idempotent"])
            self.assertNotEqual(request_ids[0], request_ids[1])
            self.assertEqual(store.get()["generation"], 2)

    @staticmethod
    def _settings_item(model, identifier):
        for _ in range(3):
            model.handle("right")
        while model.snapshot().selected_item.id != identifier:
            model.handle("down")

    def test_controls_lists_actual_capability_and_refuses_unqualified_profile(self):
        model = NavigationModel()
        self._settings_item(model, "controls")
        capability = model.handle("confirm")[0]
        self.assertEqual(capability.method, "controls.capabilities")
        model.receive(capability, {"generation": 3, "profiles": [
            {"profile_id": "ppsspp-unqualified", "writable": False,
             "error": {"code": "UNQUALIFIED", "message": "Independent menu mapping is unverified"}}]})
        self.assertEqual(model.snapshot().title, "Emulator menu controls")
        self.assertEqual(model.handle("confirm"), [])
        self.assertIn("unverified", model.snapshot().dialog.message)
        model.handle("back")
        model.handle("back")
        self.assertEqual(model.snapshot().title, "Make it yours")

    def test_controls_profile_preview_apply_and_undo_keep_separate_generation(self):
        model = NavigationModel(session_id="fixture-session")
        self._settings_item(model, "controls")
        capability = model.handle("confirm")[0]
        model.receive(capability, {"generation": 7, "profiles": [{"profile_id": "ra-test", "writable": True, "surface": "retroarch"}]})
        model.handle("confirm")
        model.handle("down")  # East confirm
        preview = model.handle("confirm")[0]
        self.assertEqual(preview.params, {"profile_id": "ra-test", "confirm": "east", "expected_generation": 7})
        model.receive(preview, {"profile_id": "ra-test", "preview_id": "p1", "diff": [
            {"key": "menu_swap_ok_cancel_buttons", "before": False, "after": True}]})
        apply = model.handle("confirm")[0]
        self.assertEqual(apply.method, "controls.apply")
        self.assertEqual(apply.params["expected_generation"], 7)
        refresh = model.receive(apply, {"transaction_id": "t1", "generation": 8, "gameplay_changed": False})[0]
        model.receive(refresh, {"generation": 8, "profiles": [{"profile_id": "ra-test", "writable": True}]})
        model.handle("down")
        undo = model.handle("confirm")[0]
        self.assertEqual(undo.method, "controls.undo")
        self.assertEqual(undo.params["transaction_id"], "t1")
        self.assertEqual(undo.params["expected_generation"], 8)
        self.assertEqual(model.generation, 0)

    def test_about_credits_are_reachable_and_retain_pyui_attribution(self):
        model = NavigationModel()
        self._settings_item(model, "about")
        self.assertEqual(model.handle("confirm"), [])
        self.assertEqual(model.snapshot().dialog.title, "About & credits")
        self.assertIn("PyUI", model.snapshot().dialog.message)
        self.assertIn("Copyright (c) 2025 Christopher Jacobs", model.snapshot().dialog.message)
        self.assertIn("non-commercial license", model.snapshot().dialog.message)
        self.assertIn("separate GPL notices", model.snapshot().dialog.message)
        model.handle("search")
        self.assertEqual(model.snapshot().dialog.message_page, 1)
        model.handle("favorite")
        self.assertEqual(model.snapshot().dialog.message_page, 0)

    def test_ppsspp_menu_preview_includes_opt_in_and_both_physical_buttons(self):
        model = NavigationModel()
        self._settings_item(model, "controls")
        command = model.handle("confirm")[0]
        model.receive(command, {"generation": 0, "profiles": [{"profile_id": "ppsspp-test", "writable": True,
                               "configuration_effective": False, "configured_confirm": None}]})
        self.assertIn("Ready to configure", model.snapshot().selected_item.subtitle)
        model.handle("confirm")
        preview = model.handle("confirm")[0]
        model.receive(preview, {"profile_id": "ppsspp-test", "preview_id": "p1", "diff": [
            {"key": "IndependentMenuControls", "before": False, "after": True},
            {"key": "NativeMenuConfirm", "before": "east", "after": "south"},
            {"key": "NativeMenuBack", "before": "south", "after": "east"}]})
        message = model.snapshot().dialog.message
        self.assertIn("Independent menu controls: Off → On", message)
        self.assertIn("Confirm button: east → south", message)
        self.assertIn("Back button: south → east", message)
        model.handle("back")
        model.receive(command, {"generation": 1, "profiles": [{"profile_id": "ppsspp-test", "writable": True,
                               "configuration_effective": True, "configured_confirm": "south"}]})
        self.assertIn("Confirm: South button", model.snapshot().selected_item.subtitle)

    def test_invalid_preferences_are_bounded_and_empty_views_are_actionable(self):
        preferences = Preferences.from_mapping({"text_scale": 1e100, "confirm": "gameplay", "motion": False})
        self.assertEqual(preferences.text_scale, 1.75)
        self.assertEqual(preferences.confirm, "south")
        self.assertFalse(preferences.motion)
        model = NavigationModel()
        model.handle("right")
        self.assertIn("compatible state", model.snapshot().empty_message)
        self.assertEqual(model.handle("confirm"), [])


class RefreshFocusTests(unittest.TestCase):
    def _open_settings_entry(self, model, identifier):
        while model.snapshot().category != 3:
            model.handle("right")
        for _ in range(len(model.snapshot().items)):
            if model.snapshot().selected_item.id == identifier:
                return model.handle("confirm")[0]
            model.handle("down")
        self.fail("Missing settings entry " + identifier)

    @staticmethod
    def _hardware_rows(group, count=2):
        return {"generation": 0, "controls": [
            {"control_id": f"{group}:{i}", "group": group, "label": f"Setting {i}",
             "writable": False, "value_text": "Unavailable", "reason": "Unavailable on this fixture"}
            for i in range(count)], "routes": []}

    def _open_favorites(self, selected):
        records = [game(f"psp:{i}") for i in range(4)]
        model = NavigationModel()
        model.handle("down")
        request = model.handle("confirm")[0]
        self.assertEqual(request.method, "library.favorites")
        model.receive(request, records)
        for _ in range(selected):
            model.handle("down")
        return model, records

    def _remove_focused_favorite(self, model, remaining):
        removal = model.handle("favorite")[0]
        self.assertEqual(removal.method, "library.favorite.set")
        self.assertFalse(removal.params["enabled"])
        refresh = model.receive(removal, {})[0]
        self.assertEqual(refresh.method, "library.favorites")
        model.receive(refresh, remaining)

    def test_favorite_refresh_after_removing_middle_keeps_next_neighbor(self):
        model, records = self._open_favorites(2)
        self._remove_focused_favorite(model, records[:2] + records[3:])
        self.assertEqual(model.snapshot().selected, 2)
        self.assertEqual(model.snapshot().selected_item.id, "psp:3")

    def test_favorite_refresh_after_removing_last_keeps_previous_neighbor(self):
        model, records = self._open_favorites(3)
        self._remove_focused_favorite(model, records[:-1])
        self.assertEqual(model.snapshot().selected, 2)
        self.assertEqual(model.snapshot().selected_item.id, "psp:2")

    def test_empty_category_refresh_keeps_focus_zero(self):
        model = NavigationModel()
        model.set_category_items(1, [game("psp:0"), game("psp:1")])
        model.handle("right")
        model.handle("down")
        model.set_category_items(1, [])
        self.assertEqual(model.snapshot().selected, 0)
        self.assertIsNone(model.snapshot().selected_item)
        model.set_category_items(1, [game("psp:new")])
        self.assertEqual(model.snapshot().selected, 0)
        self.assertEqual(model.snapshot().selected_item.id, "psp:new")

    def test_reordered_category_refresh_preserves_selected_game_identity(self):
        model = NavigationModel()
        records = [game(f"psp:{i}") for i in range(4)]
        model.set_category_items(0, records)
        model.handle("down")
        model.handle("down")
        model.set_category_items(0, [records[2], records[3], records[0], records[1]])
        self.assertEqual(model.snapshot().selected, 0)
        self.assertEqual(model.snapshot().selected_item.id, "psp:2")

    def test_fresh_game_query_resets_focus_even_when_previous_game_remains(self):
        model = NavigationModel()
        records = [game(f"psp:{i}") for i in range(4)]
        model.set_category_items(0, records)
        model.handle("down")
        model.handle("down")
        model.handle("search")
        model.handle("text", "A game")
        request = model.handle("submit_text")[0]
        self.assertEqual(request.method, "library.query")
        model.receive(request, {"items": records, "offset": 0, "total": len(records)})
        self.assertEqual(model.snapshot().selected, 0)
        self.assertEqual(model.snapshot().selected_item.id, "psp:0")

    def test_common_settings_open_at_first_control_and_restore_parent_focus(self):
        for group in ("display", "sound", "network", "controllers", "power"):
            with self.subTest(group=group):
                model = NavigationModel()
                request = self._open_settings_entry(model, "hardware_" + group)
                model.receive(request, self._hardware_rows(group))
                self.assertEqual(model.snapshot().selected, 0)
                self.assertEqual(model.snapshot().selected_item.id, group + ":0")
                self.assertEqual(model.handle("confirm"), [])
                self.assertEqual(model.snapshot().dialog.selected, 1)
                model.handle("back")  # close the unavailable-control dialog
                model.handle("back")  # return to the selected Settings group
                self.assertEqual(model.snapshot().selected_item.id, "hardware_" + group)

    def test_common_settings_refresh_preserves_the_same_view_focus(self):
        model = NavigationModel()
        request = self._open_settings_entry(model, "hardware_network")
        model.receive(request, self._hardware_rows("network"))
        model.handle("down")
        model.handle("down")
        self.assertEqual(model.snapshot().selected_item.id, "hardware_refresh")
        refresh = model.handle("confirm")[0]
        model.receive(refresh, self._hardware_rows("network", count=3))
        self.assertEqual(model.snapshot().selected, 3)
        self.assertEqual(model.snapshot().selected_item.id, "hardware_refresh")

    def test_control_profiles_open_at_first_and_refresh_keeps_selected_profile(self):
        model = NavigationModel()
        status = {"generation": 0, "profiles": [
            {"profile_id": f"profile:{i}", "label": f"Profile {i}", "writable": True}
            for i in range(3)]}
        request = self._open_settings_entry(model, "controls")
        model.receive(request, status)
        self.assertEqual(model.snapshot().selected_item.id, "profile:0")
        model.handle("down")
        model.handle("confirm")
        preview = model.handle("confirm")[0]
        model.receive(preview, {"profile_id": "profile:1", "preview_id": "preview", "diff": []})
        apply = model.handle("confirm")[0]
        refresh = model.receive(apply, {"generation": 1, "transaction_id": "controls:1"})[0]
        model.receive(refresh, {**status, "generation": 1})
        self.assertEqual(model.snapshot().selected_item.id, "profile:1")
        model.handle("back")
        request = self._open_settings_entry(model, "controls")
        model.receive(request, {**status, "generation": 1})
        self.assertEqual(model.snapshot().selected_item.id, "profile:0")

    def test_reentering_appearance_starts_at_match_instead_of_existing_undo(self):
        model = NavigationModel()
        status = {"generation": 0, "theme": "Original", "preview_available": True}
        request = self._open_settings_entry(model, "appearance")
        model.receive(request, status)
        preview = model.handle("confirm")[0]
        model.receive(preview, {"adoption_available": True, "preview_id": "appearance"})
        apply = model.handle("confirm")[0]
        refresh = model.receive(apply, {"applied": True, "generation": 1,
                                        "transaction_id": "appearance:1"})[0]
        model.receive(refresh, {**status, "generation": 1})
        model.handle("down")
        self.assertEqual(model.snapshot().selected_item.id, "appearance_undo")
        model.handle("back")
        request = self._open_settings_entry(model, "appearance")
        model.receive(request, {**status, "generation": 1})
        self.assertEqual(model.snapshot().selected, 0)
        self.assertEqual(model.snapshot().selected_item.id, "appearance_match")


if __name__ == "__main__":
    unittest.main()
