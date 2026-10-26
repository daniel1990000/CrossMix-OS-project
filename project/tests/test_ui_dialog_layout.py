"""Long metadata stays readable without colliding with menu choices."""
import importlib.util
import os
import unittest
from dataclasses import replace
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HOST_UI = importlib.util.find_spec("sdl2") is not None and importlib.util.find_spec("PIL") is not None


@unittest.skipUnless(HOST_UI, "Install the host PySDL2/Pillow dependencies")
class ContextHeaderTests(unittest.TestCase):
    def test_two_line_header_preserves_the_complete_title_above_body(self):
        from psp_shell.ui.model import Dialog, DialogChoice, NavigationModel
        from psp_shell.ui.renderer import Renderer
        title = "Skyline Circuit: The Complete Championship Edition"
        model = NavigationModel(preferences={"motion": False})
        state = replace(model.snapshot(), dialog=Dialog(title, "Your existing save is available.",
            (DialogChoice("Start game"), DialogChoice("Cancel"))))
        drawn = []
        with Renderer(software=True) as renderer:
            label = renderer._label
            def record(text, x, y, size, color, max_width, scale=1):
                result = label(text, x, y, size, color, max_width, scale)
                drawn.append((text, y, result[1], size))
                return result
            with mock.patch.object(renderer, "_label", side_effect=record):
                renderer.render(state, 0)
        header = [row for row in drawn if row[3] == 28]
        self.assertEqual(len(header), 2)
        self.assertEqual(" ".join(row[0] for row in header), title)
        body = next(row for row in drawn if row[0] == "Your existing save is available.")
        self.assertLess(max(y + h for _, y, h, _ in header), body[1])
        choice = next(row for row in drawn if row[0] == "Start game")
        self.assertLess(body[1] + body[2], choice[1])

    def test_full_overflowing_title_is_available_in_large_text_body_pages(self):
        from psp_shell.ui.model import Dialog, DialogChoice, NavigationModel
        from psp_shell.ui.renderer import Renderer
        title = "A long game title " * 14 + "Final Edition"
        choices = tuple(DialogChoice(x) for x in ("Resume", "Fresh start", "Game options", "Cancel"))
        model = NavigationModel(preferences={"motion": False, "text_scale": 1.75})
        state = replace(model.snapshot(), dialog=Dialog(title, "Existing saves stay available.", choices))
        body = []
        with Renderer(software=True) as renderer:
            label = renderer._label
            page_count = None
            def record(text, x, y, size, color, max_width, scale=1):
                nonlocal page_count
                result = label(text, x, y, size, color, max_width, scale)
                if size == 18:
                    body.append((text, y, result[1]))
                if text.startswith("More text"):
                    page_count = int(text.rsplit("/", 1)[1])
                return result
            with mock.patch.object(renderer, "_label", side_effect=record):
                renderer.render(state, 0)
                self.assertIsNotNone(page_count)
                for page in range(1, page_count):
                    renderer.render(replace(state, dialog=replace(state.dialog, message_page=page)), 0)
        readable = " ".join(line for line, _, _ in body).split()
        self.assertEqual(readable, ("Existing saves stay available. Full title: " + title).split())
        first_choice_y = 626 - 4 * (round(38 * 1.75) + 8) + 12
        self.assertLess(max(y + h for _, y, h in body), first_choice_y)


if __name__ == "__main__":
    unittest.main()
