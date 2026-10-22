# SPDX-License-Identifier: MIT
"""Readable controller text entry and stable explicit library refresh."""
from collections import deque
from pathlib import Path
import unittest

import sdl2

from psp_shell.ui.input import InputMapper
from psp_shell.ui.keyboard import (KEYBOARD_ACTIONS, KEYBOARD_CHARACTERS, KEYBOARD_KEYS,
                                    keyboard_hints, keyboard_layout, move_keyboard_focus)
from psp_shell.ui.model import NavigationModel, Preferences
from psp_shell.ui.text import TextRasterizer


def focus_paths():
    """Find actual d-pad routes from A to every visible character/action."""
    pending = deque([(0, None, ())])
    visited = {(0, None)}
    paths = {}
    while pending and len(paths) < len(KEYBOARD_KEYS):
        selected, preferred, path = pending.popleft()
        paths.setdefault(KEYBOARD_KEYS[selected], path)
        for direction in ("left", "right", "up", "down"):
            destination = move_keyboard_focus(selected, direction, preferred)
            if destination not in visited:
                visited.add(destination)
                pending.append((*destination, path + (direction,)))
    return paths


class ControllerKeyboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = focus_paths()

    def select(self, model, key):
        for action in self.paths[key]:
            model.handle(action)
        self.assertEqual(model.snapshot().keyboard.keys[model.snapshot().keyboard.selected], key)

    def test_all_characters_and_actions_are_reachable_by_dpad(self):
        self.assertEqual(set(self.paths), set(KEYBOARD_KEYS))
        for character in KEYBOARD_CHARACTERS:
            with self.subTest(character=character):
                model = NavigationModel()
                model.handle("search")
                self.select(model, character)
                model.handle("confirm")
                self.assertEqual(model.snapshot().keyboard.text, character)

    def test_rows_wrap_horizontally_and_vertical_focus_retains_column(self):
        model = NavigationModel()
        model.handle("search")
        model.handle("left")
        self.assertEqual(model.snapshot().keyboard.keys[model.snapshot().keyboard.selected], "J")
        model.handle("up")
        self.assertEqual(model.snapshot().keyboard.keys[model.snapshot().keyboard.selected], "J")
        for _ in range(5):
            model.handle("down")
        self.assertEqual(model.snapshot().keyboard.keys[model.snapshot().keyboard.selected], "Cancel")
        for _ in range(5):
            model.handle("up")
        self.assertEqual(model.snapshot().keyboard.keys[model.snapshot().keyboard.selected], "J")

    def test_space_delete_find_and_cancel_work_without_desktop_keys(self):
        for key, before, expected in (("Space", "RALLY", "RALLY "), ("Delete", "RALLY!", "RALLY")):
            with self.subTest(key=key):
                model = NavigationModel()
                model.handle("search")
                model.handle("text", before)
                self.select(model, key)
                model.handle("confirm")
                self.assertEqual(model.snapshot().keyboard.text, expected)
        model = NavigationModel()
        model.handle("search")
        model.handle("text", "R-TYPE: DELTA (EU)/?")
        self.select(model, "Find")
        request = model.handle("confirm")[0]
        self.assertEqual(request.params["search"], "R-TYPE: DELTA (EU)/?")
        self.assertIsNone(model.snapshot().keyboard)
        model.receive(request, {"items": [{"game_id": "focused", "label": "Game"}], "total": 1})
        model.handle("search")
        model.handle("text", "Discard this")
        self.select(model, "Cancel")
        self.assertEqual(model.handle("confirm"), [])
        self.assertIsNone(model.snapshot().keyboard)
        self.assertEqual(model.snapshot().selected_item.id, "focused")
        self.assertEqual(model.export_state()["search"], "R-TYPE: DELTA (EU)/?")

    def test_external_unicode_stays_literal_and_length_is_bounded_by_codepoints(self):
        model = NavigationModel()
        model.handle("search")
        value = "é 日本語 👩\u200d💻"
        model.handle("text", value + "\n\r\t\x00\x7f")
        self.assertEqual(model.snapshot().keyboard.text, value)
        model.handle("text", "字" * 400)
        self.assertEqual(len(model.snapshot().keyboard.text), 128)
        model.handle("delete_text")
        self.assertEqual(len(model.snapshot().keyboard.text), 127)
        request = model.handle("submit_text")[0]
        self.assertTrue(request.params["search"].startswith(value))

    def test_physical_help_matches_input_for_both_confirm_preferences(self):
        buttons = {"south": sdl2.SDL_CONTROLLER_BUTTON_A, "east": sdl2.SDL_CONTROLLER_BUTTON_B,
                   "west": sdl2.SDL_CONTROLLER_BUTTON_X, "north": sdl2.SDL_CONTROLLER_BUTTON_Y}
        actions = {"Select key": "confirm", "Cancel": "back", "Delete": "delete_text", "Find": "submit_text"}
        with self.subTest():
            mapper = InputMapper(manage_controllers=False, sample_initial_state=False)
            self.addCleanup(mapper.close)
            for confirm in ("south", "east"):
                for hint in keyboard_hints(confirm):
                    with self.subTest(confirm=confirm, hint=hint):
                        event = sdl2.SDL_Event()
                        event.type = sdl2.SDL_CONTROLLERBUTTONDOWN
                        event.cbutton.which = 17
                        event.cbutton.button = buttons[hint.position]
                        mapped = mapper.process(event, Preferences(confirm=confirm), text_mode=True)
                        self.assertEqual([action.action for action in mapped], [actions[hint.title]])
                        event.type = sdl2.SDL_CONTROLLERBUTTONUP
                        mapper.process(event, Preferences(confirm=confirm), text_mode=True)

    def test_unicode_sdl_text_event_keeps_non_latin_input(self):
        mapper = InputMapper(manage_controllers=False, sample_initial_state=False)
        self.addCleanup(mapper.close)
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_TEXTINPUT
        event.text.text = "é 日本語".encode("utf-8")
        self.assertEqual(mapper.process(event, text_mode=True)[0].text, "é 日本語")


class KeyboardLayoutTests(unittest.TestCase):
    def test_actual_font_labels_fit_every_key_at_all_supported_scales(self):
        font = TextRasterizer(Path(__file__).resolve().parents[1] / "assets/fonts/NotoSans.ttf")
        previous = None
        for scale in (.75, 1, 1.3, 1.5, 1.75):
            layout = keyboard_layout(scale)
            self.assertEqual({cell.key for cell in layout.cells}, set(KEYBOARD_KEYS))
            for cell in layout.cells:
                with self.subTest(scale=scale, key=cell.key):
                    self.assertTrue(0 <= cell.x < cell.x + cell.width <= 1280)
                    self.assertTrue(0 <= cell.y < cell.y + cell.height <= 720)
                    self.assertLessEqual(font.measure(cell.key, cell.font_size), cell.width - 16)
                    raster = font.raster(cell.key, cell.font_size, (255, 255, 255, 255), cell.width - 16)
                    self.assertLessEqual(raster.height, cell.height - 8)
                    self.assertEqual(font.fit(cell.key, cell.font_size, cell.width - 16), cell.key)
            for cell in layout.cells:
                for other in layout.cells:
                    if cell.index == other.index:
                        continue
                    self.assertFalse(cell.x < other.x + other.width and other.x < cell.x + cell.width and
                                     cell.y < other.y + other.height and other.y < cell.y + cell.height)
            for hint, (_, top) in zip(keyboard_hints(), layout.hint_positions):
                raster = font.raster(hint.title, layout.hint_font_size, (255, 255, 255, 255), 460)
                self.assertLessEqual(top + raster.height, 720)
                self.assertLessEqual(raster.height, 35)
            if previous is not None:
                self.assertGreater(layout.cells[0].font_size, previous)
            previous = layout.cells[0].font_size
        self.assertEqual({cell.key for cell in keyboard_layout().cells if cell.width > 100}, set(KEYBOARD_ACTIONS))


class ExplicitRefreshTests(unittest.TestCase):
    @staticmethod
    def model_and_records(selected=2):
        records = [{"game_id": f"game:{i}", "label": f"Game {i}"} for i in range(40, 80)]
        model = NavigationModel()
        model.set_category_items(0, records, offset=40, total=90)
        for _ in range(selected):
            model.handle("down")
        return model, records

    def test_explicit_refresh_preserves_later_page_and_selected_identity(self):
        model, records = self.model_and_records()
        refresh = next(c for c in model.handle("refresh") if c.method == "library.query")
        self.assertEqual(refresh.params["offset"], 40)
        self.assertEqual(model.snapshot().artwork_generation, 1)
        self.assertEqual(model.snapshot().selected_item.id, "game:42")
        model.receive(refresh, {"items": list(reversed(records)), "offset": 40, "total": 90})
        self.assertEqual(model.snapshot().offset, 40)
        self.assertEqual(model.snapshot().selected_item.id, "game:42")
        self.assertEqual(model.snapshot().selected, 37)
        model.handle("down")
        self.assertEqual(model.snapshot().artwork_generation, 1)

    def test_refresh_missing_focus_retains_nearest_row_and_stale_reply_is_rejected(self):
        model, records = self.model_and_records(selected=3)
        old = next(c for c in model.handle("refresh") if c.method == "library.query")
        latest = next(c for c in model.handle("refresh") if c.method == "library.query")
        model.receive(old, {"items": [], "offset": 0, "total": 0})
        self.assertEqual(model.snapshot().selected_item.id, "game:43")
        model.receive(latest, {"items": records[:3] + records[4:], "offset": 40, "total": 89})
        self.assertEqual(model.snapshot().selected, 3)
        self.assertEqual(model.snapshot().selected_item.id, "game:44")
        self.assertEqual(model.snapshot().artwork_generation, 2)

    def test_controller_refresh_entry_keeps_existing_system_positions(self):
        model = NavigationModel()
        request = next(c for c in model.initial_commands() if c.method == "library.systems")
        model.receive(request, [{"id": "GBA", "label": "Game Boy Advance", "game_count": 2}])
        self.assertEqual(model.snapshot().items[4].id, "GBA")
        self.assertEqual(model.snapshot().items[-1].id, "refresh_library")
        while model.snapshot().selected_item.id != "refresh_library":
            model.handle("down")
        commands = model.handle("confirm")
        self.assertIn("library.systems", [c.method for c in commands])
        self.assertEqual(model.snapshot().artwork_generation, 1)
        refreshed = next(c for c in commands if c.method == "library.systems")
        self.assertEqual(refreshed.params, {"refresh": True})
        model.receive(refreshed, [{"id": "GBA", "label": "Game Boy Advance", "game_count": 2}])
        self.assertEqual(model.snapshot().selected_item.id, "refresh_library")
