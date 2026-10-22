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

    def test_invalid_preferences_are_bounded_and_empty_views_are_actionable(self):
        preferences = Preferences.from_mapping({"text_scale": 1e100, "confirm": "gameplay", "motion": False})
        self.assertEqual(preferences.text_scale, 1.75)
        self.assertEqual(preferences.confirm, "south")
        self.assertFalse(preferences.motion)
        model = NavigationModel()
        model.handle("right")
        self.assertIn("compatible state", model.snapshot().empty_message)
        self.assertEqual(model.handle("confirm"), [])


if __name__ == "__main__":
    unittest.main()
