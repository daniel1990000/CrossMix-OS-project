"""RetroPass directions, modal ownership and saved-style compatibility."""
import json
from pathlib import Path
import tempfile
import unittest

from psp_shell.settings import DEFAULT_PREFERENCES, SettingsStore
from psp_shell.ui.model import NavigationModel, UIItem


class RetroPassNavigationTests(unittest.TestCase):
    def model(self):
        model = NavigationModel(preferences={"theme": "retropass"})
        model.set_category_items(0, [UIItem("one", "One"), UIItem("two", "Two")])
        return model

    def test_shelf_directions_and_shoulders_preserve_native_interface_selection(self):
        model = self.model()
        model.handle("right")
        self.assertEqual(model.snapshot().selected_item.id, "two")
        self.assertEqual(model.category, 0)
        model.handle("left")
        self.assertEqual(model.snapshot().selected_item.id, "one")
        model.handle("down")
        self.assertEqual(model.category, 1)
        model.handle("up")
        self.assertEqual(model.category, 0)
        model.handle("category_next")
        self.assertEqual(model.category, 1)
        model.handle("category_previous")
        self.assertEqual(model.category, 0)
        self.assertEqual(model.preferences.interface, "classic")

    def test_modal_directions_are_not_remapped_to_categories(self):
        model = self.model()
        model.handle("confirm")
        self.assertIsNotNone(model.snapshot().dialog)
        selected = model.snapshot().dialog.selected
        model.handle("right")
        self.assertNotEqual(model.snapshot().dialog.selected, selected)
        self.assertEqual(model.category, 0)
        model.handle("category_next")
        self.assertEqual(model.category, 0)

    def test_native_pyui_shoulders_switch_categories_only_outside_text_entry(self):
        from types import SimpleNamespace
        from psp_shell.embedded import logical_action
        model = self.model()
        device = SimpleNamespace()
        for name, action in (("L1", "category_previous"), ("R1", "category_next")):
            button = SimpleNamespace(name=name)
            self.assertEqual(logical_action(button, model.preferences, device), action)
            self.assertIsNone(logical_action(button, model.preferences, device, text_mode=True))
    def test_category_shoulder_rejects_stale_game_information(self):
        model = self.model()
        model.set_category_items(0, [UIItem("one", "One", state_verification_required=True)])
        model._capabilities["game_information"] = True
        command = model.handle("confirm")[0]
        model.handle("category_next")
        model.receive(command, {"game_id": "one", "display_name": "One"})
        self.assertIsNone(model.snapshot().dialog)
        self.assertEqual(model.category, 1)

    def test_old_preference_file_is_read_without_rewrite_and_style_can_be_undone(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(directory)
            old = {"schema": 1, "generation": 7,
                   "preferences": {k: v for k, v in DEFAULT_PREFERENCES.items() if k != "theme"}}
            raw = json.dumps(old).encode()
            store.target.write_bytes(raw)
            reopened = SettingsStore(directory, default_theme="retropass")
            self.assertEqual(reopened.get()["preferences"]["theme"], "psp")
            self.assertEqual(reopened.target.read_bytes(), raw)
            preview = reopened.preview({"changes": {"theme": "retropass"}, "expected_generation": 7})
            applied = reopened.apply({"preview_id": preview["preview_id"], "request_id": "style-switch",
                                      "expected_generation": 7})
            self.assertEqual(applied["preferences"]["theme"], "retropass")
            undone = reopened.undo({"transaction_id": applied["transaction_id"],
                                    "request_id": "style-undo", "expected_generation": 8})
            self.assertEqual(undone["preferences"]["theme"], "psp")

    def test_fresh_preview_selects_retropass_and_reopen_preserves_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory), default_theme="retropass")
            self.assertEqual(store.get()["preferences"]["theme"], "retropass")
            self.assertEqual(SettingsStore(directory).get()["preferences"]["theme"], "retropass")


if __name__ == "__main__":
    unittest.main()
