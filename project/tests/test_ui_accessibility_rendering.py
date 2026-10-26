"""Essential help stays readable and complete in actual host SDL renders."""
# SPDX-License-Identifier: MIT
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from psp_shell.ui.model import Dialog, DialogChoice, Keyboard, NavigationModel, UIItem
from psp_shell.ui.renderer import Renderer


class AccessibleRenderingTests(unittest.TestCase):
    def snapshot(self, scale=1, confirm="south", contrast=False):
        model = NavigationModel(preferences={"text_scale": scale, "confirm": confirm,
                                            "motion": False, "high_contrast": contrast})
        model.set_category_items(0, [UIItem("one", "A selected game", system_id="PSP")])
        return model.snapshot()

    def test_footer_scales_reflows_and_keeps_every_hint_readable_in_both_themes(self):
        from PIL import Image
        favorite_sizes = {}
        for scale in (.75, 1, 1.15, 1.3, 1.5, 1.75):
            for confirm in ("south", "east"):
                for contrast in (False, True):
                    with self.subTest(scale=scale, confirm=confirm, contrast=contrast), Renderer(software=True) as renderer:
                        labels, buttons = [], []
                        active = False
                        footer, label, button = renderer._footer, renderer._label, renderer._button
                        def record_footer(*args):
                            nonlocal active
                            active = True
                            try:
                                return footer(*args)
                            finally:
                                active = False
                        def record_label(text, x, y, size, color, width, scale=1):
                            result = label(text, x, y, size, color, width, scale)
                            if active:
                                labels.append((text, x, y, size, width, *result))
                            return result
                        def record_button(position, x, y, color, scale=1):
                            if active:
                                buttons.append(position)
                            return button(position, x, y, color, scale)
                        with mock.patch.object(renderer, "_footer", side_effect=record_footer), \
                             mock.patch.object(renderer, "_label", side_effect=record_label), \
                             mock.patch.object(renderer, "_button", side_effect=record_button):
                            renderer.render(self.snapshot(scale, confirm, contrast), 0)
                        self.assertEqual(buttons, [confirm, "east" if confirm == "south" else "south", "west", "north"])
                        self.assertEqual({row[0] for row in labels}, {"Enter", "Back", "Search", "Favorite", "Start: Library tools", "1 / 1"})
                        for text, x, y, size, limit, width, height in labels:
                            self.assertEqual(renderer.text.fit(text, size, limit), text)
                            self.assertTrue(0 <= x and 0 <= y and x + width <= 1280 and y + height <= 720)
                        favorite_sizes[scale] = next(row[3] for row in labels if row[0] == "Favorite")
                        if scale == 1.75:
                            self.assertEqual(len({row[2] for row in labels}), 2)
                        with tempfile.TemporaryDirectory() as temporary:
                            output = Path(temporary) / "footer.png"
                            renderer.save_screenshot(output)
                            with Image.open(output) as captured:
                                pixels = captured.convert("RGB")
                                background = pixels.getpixel((1200, 719))
                                if scale == 1 and confirm == "south":
                                    # A half-pixel center previously left alternate
                                    # rows blank in the selected physical-button dot.
                                    white = {(x, y) for x in range(54, 82) for y in range(670, 710)
                                             if min(pixels.getpixel((x, y))) > 240}
                                    self.assertGreater(len(white), 20)
                                    reached, pending = set(), [next(iter(white))]
                                    while pending:
                                        point = pending.pop()
                                        if point in reached:
                                            continue
                                        reached.add(point)
                                        x, y = point
                                        pending.extend(neighbor for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                                                       if neighbor in white and neighbor not in reached)
                                    self.assertEqual(reached, white)
                            # Essential help must not fall back onto the bright
                            # animated waves. Check rendered pixels, not palette constants.
                            self.assertLess(max(background), 80)
        self.assertGreater(favorite_sizes[1.75], favorite_sizes[1] * 1.6)

    def test_body_pages_and_hidden_actions_have_independent_physical_hints(self):
        choices = tuple(DialogChoice(value) for value in ("Resume", "Start game", "Game information", "Existing options", "Back"))
        for scale in (.75, 1, 1.75):
            with self.subTest(scale=scale), Renderer(software=True) as renderer:
                state = replace(self.snapshot(scale), dialog=Dialog("Game information", "Detail line\n" * 20, choices))
                labels, buttons = [], []
                label, button = renderer._label, renderer._button
                def record(text, x, y, size, color, width, scale=1):
                    result = label(text, x, y, size, color, width, scale)
                    labels.append((text, x, y, *result))
                    return result
                def record_button(position, *args, **kwargs):
                    buttons.append(position)
                    return button(position, *args, **kwargs)
                with mock.patch.object(renderer, "_label", side_effect=record), \
                     mock.patch.object(renderer, "_button", side_effect=record_button):
                    renderer.render(state, 0)
                more = next(row for row in labels if row[0].startswith("More text"))
                actions = next(row for row in labels if row[0].startswith("Actions 1–4 / 5"))
                self.assertLess(more[1] + more[3], actions[1])
                self.assertIn("west", buttons)
                self.assertIn("north", buttons)
                self.assertIn("Previous text", [row[0] for row in labels])
                self.assertTrue(all(0 <= y and y + height <= 720 for _, _, y, _, height in labels))

    def test_selected_title_uses_two_measured_lines_before_subtitle(self):
        for scale, title in ((1, "Skyline Circuit: The Complete Championship Edition and Anniversary Collection"),
                             (1.75, "Skyline Circuit: The Complete Championship Edition")):
            with self.subTest(scale=scale), Renderer(software=True) as renderer:
                state = self.snapshot(scale)
                state = replace(state, items=(UIItem("one", title, "A useful subtitle", system_id="PSP"),))
                drawn = []
                text = renderer._text
                def record(value, x, y, size, color, width, scale=1):
                    result = text(value, x, y, size, color, width, scale)
                    drawn.append((value, y, size, result[1]))
                    return result
                with mock.patch.object(renderer, "_text", side_effect=record):
                    renderer.render(state, 0)
                lines = [row for row in drawn if row[2] == 31]
                self.assertEqual(len(lines), 2)
                self.assertEqual(" ".join(row[0] for row in lines), title)
                subtitle = next(row for row in drawn if "A useful subtitle" in row[0])
                self.assertLess(max(y + height for _, y, _, height in lines), subtitle[1])

    def test_rename_keyboard_displays_its_own_title_and_submit_action(self):
        with Renderer(software=True) as renderer:
            state = replace(self.snapshot(1.75), keyboard=Keyboard("Before the final boss", 0,
                            title="Name this backup", submit_label="Save name"))
            labels = []
            label = renderer._label
            def record(text, *args, **kwargs):
                labels.append(text)
                return label(text, *args, **kwargs)
            with mock.patch.object(renderer, "_label", side_effect=record):
                renderer.render(state, 0)
            self.assertIn("Name this backup", labels)
            self.assertIn("Save name", labels)
            self.assertNotIn("Find a game", labels)
            self.assertNotIn("Find", labels)

    def test_actual_sdl_ttf_help_remains_inside_the_viewport(self):
        from sdl2 import sdlttf
        from psp_shell.ui.text import SDLTextRasterizer
        self.assertEqual(sdlttf.TTF_Init(), 0)
        fonts = {}
        def provider(size):
            if size not in fonts:
                fonts[size] = sdlttf.TTF_OpenFont(str(Renderer.default_font_path()).encode(), size)
                self.assertTrue(fonts[size])
            return fonts[size]
        try:
            with Renderer(software=True, text_backend=SDLTextRasterizer(provider)) as renderer:
                labels = []
                original = renderer._label
                def record(text, x, y, size, color, width, scale=1):
                    result = original(text, x, y, size, color, width, scale)
                    labels.append((text, x, y, *result))
                    return result
                state = self.snapshot(1.75, "east")
                with mock.patch.object(renderer, "_label", side_effect=record):
                    renderer.render(state, 0)
                    renderer.render(replace(state, dialog=Dialog("Game details", "Detail\n" * 20,
                                    tuple(DialogChoice(x) for x in ("Start game", "Options", "Back", "Details", "Help")))), 0)
                essential = [row for row in labels if row[0] in ("Enter", "Back", "Search", "Favorite", "Start: Library tools", "Previous text")
                             or row[0].startswith(("More text", "Actions"))]
                self.assertTrue(essential)
                self.assertTrue(all(0 <= x and 0 <= y and x + width <= 1280 and y + height <= 720
                                    for _, x, y, width, height in essential))
        finally:
            for font in fonts.values():
                sdlttf.TTF_CloseFont(font)
            sdlttf.TTF_Quit()


if __name__ == "__main__":
    unittest.main()
