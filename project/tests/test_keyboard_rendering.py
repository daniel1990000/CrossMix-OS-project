"""Exercise the actual SDL keyboard at supported text sizes and long queries."""
# SPDX-License-Identifier: MIT
from dataclasses import replace
import os
import unittest
from unittest import mock

from psp_shell.ui.keyboard import KEYBOARD_KEYS, keyboard_layout
from psp_shell.ui.model import Keyboard, NavigationModel
from psp_shell.ui.renderer import Renderer


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


class KeyboardRenderingTests(unittest.TestCase):
    def capture(self, renderer, snapshot):
        labels, buttons = [], []
        active = False
        draw, label, button = renderer._draw_keyboard, renderer._label, renderer._button
        def record_label(text, x, y, size, color, max_width, scale=1):
            result = label(text, x, y, size, color, max_width, scale)
            if active:
                labels.append((text, x, y, size, max_width, *result))
            return result
        def record_button(position, x, y, color):
            if active:
                buttons.append((position, x, y))
            return button(position, x, y, color)
        def keyboard(*args):
            nonlocal active
            active = True
            try:
                return draw(*args)
            finally:
                active = False
        with mock.patch.object(renderer, "_draw_keyboard", side_effect=keyboard), \
             mock.patch.object(renderer, "_label", side_effect=record_label), \
             mock.patch.object(renderer, "_button", side_effect=record_button):
            renderer.render(snapshot, 0)
        return labels, buttons

    def test_actual_labels_fit_every_key_and_physical_help_at_all_supported_sizes(self):
        for scale in (.75, 1, 1.75):
            for confirm in ("south", "east"):
                with self.subTest(scale=scale, confirm=confirm):
                    model = NavigationModel(preferences={"motion": False, "text_scale": scale, "confirm": confirm})
                    model.handle("search")
                    layout = keyboard_layout(scale)
                    with Renderer(software=True) as renderer:
                        labels, buttons = self.capture(renderer, model.snapshot())
                        visible = []
                        for cell in layout.cells:
                            draws = [entry for entry in labels if entry[0] == cell.key and
                                     cell.x <= entry[1] < cell.x + cell.width and
                                     cell.y <= entry[2] < cell.y + cell.height]
                            self.assertEqual(len(draws), 1, cell.key)
                            text, x, y, size, width, raster_width, raster_height = draws[0]
                            self.assertEqual(renderer.text.fit(text, size, width), text)
                            self.assertLessEqual(x + raster_width, cell.x + cell.width)
                            self.assertLessEqual(y + raster_height, cell.y + cell.height)
                            visible.append(text)
                        self.assertEqual(tuple(visible), KEYBOARD_KEYS)
                        self.assertEqual([entry[0] for entry in buttons],
                            [confirm, "east" if confirm == "south" else "south", "west", "north"])
                        for _, x, y, _, _, width, height in labels:
                            self.assertTrue(0 <= x and 0 <= y and x + width <= 1280 and y + height <= 720)

    def test_long_query_shows_newest_characters_and_keeps_cursor_in_field(self):
        model = NavigationModel(preferences={"motion": False, "text_scale": 1.75})
        model.handle("search")
        snapshot = replace(model.snapshot(), keyboard=Keyboard("W" * 120 + "END!", 0))
        with Renderer(software=True) as renderer:
            labels, _ = self.capture(renderer, snapshot)
            field = keyboard_layout(1.75).field
            queries = [entry for entry in labels if field[1] <= entry[2] < field[1] + field[3]]
            self.assertEqual(len(queries), 2)  # shadow plus foreground
            for text, x, _, _, _, width, _ in queries:
                self.assertTrue(text.startswith("…"), text)
                self.assertTrue(text.endswith("END!"), text)
                self.assertLessEqual(x + width + 14, field[0] + field[2])


if __name__ == "__main__":
    unittest.main()
