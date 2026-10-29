"""Exercise the SDL RetroPass port without asserting physical-device results."""
from dataclasses import replace
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HOST_UI = importlib.util.find_spec("sdl2") is not None and importlib.util.find_spec("PIL") is not None

from psp_shell.ui.model import NavigationModel, UIItem


@unittest.skipUnless(HOST_UI, "Install the host PySDL2/Pillow dependencies")
class RetroPassRenderTests(unittest.TestCase):
    def snapshot(self, **preferences):
        model = NavigationModel(demo=True, preferences={"theme": "retropass", "motion": False, **preferences})
        model.set_category_items(0, [UIItem(str(index), "A long title · 日本語 " + str(index),
                                          system_id="PSP", system_label="PlayStation Portable")
                                     for index in range(100)])
        return model.snapshot()

    def test_dark_shelf_focus_and_static_frame_without_file_reads(self):
        from PIL import Image
        from psp_shell.ui.renderer import Renderer
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory, Renderer(software=True) as renderer:
            with mock.patch("builtins.open", side_effect=AssertionError("Render tick file read")):
                renderer.render(snapshot, 0)
            first, second = Path(directory) / "first.png", Path(directory) / "second.png"
            renderer.save_screenshot(first)
            renderer.render(snapshot, 20)
            renderer.save_screenshot(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with Image.open(first) as picture:
                image = picture.convert("RGB")
                self.assertEqual(image.getpixel((0, 0)), (9, 9, 9))
                self.assertEqual(image.getpixel((0, 400)), (31, 31, 31))
                self.assertGreater(sum(g > 90 and g > r * 3 and g > b * 3
                                       for r, g, b in image.getdata()), 1500)

    def test_last_item_stays_visible_and_cover_admission_is_bounded(self):
        from psp_shell.ui.renderer import Renderer
        snapshot = replace(self.snapshot(), selected=99)
        snapshot = replace(snapshot, items=tuple(replace(item, kind="game") for item in snapshot.items))
        with Renderer(software=True) as renderer:
            with mock.patch.object(renderer, "_artwork", wraps=renderer._artwork) as artwork:
                renderer.render(snapshot, 0)
            shown = [call.args[0].id for call in artwork.call_args_list]
            self.assertIn("99", shown)
            self.assertLessEqual(len(shown), 8)
            self.assertEqual(renderer._retropass.scroll.target, 95)

    def test_accessible_scale_high_contrast_and_dialog_keyboard(self):
        from psp_shell.ui.renderer import Renderer
        from psp_shell.ui.model import Dialog, DialogChoice, Keyboard
        with Renderer(software=True) as renderer:
            for scale in (.75, 1, 1.25, 1.5, 1.75):
                snapshot = self.snapshot(text_scale=scale, high_contrast=True)
                with mock.patch.object(renderer, "_paragraph", wraps=renderer._paragraph) as paragraph:
                    renderer.render(snapshot, 0)
                for call in paragraph.call_args_list:
                    self.assertGreater(call.args[5], 0)
                dialog = Dialog("Game options", "Existing launch authority remains active.",
                                (DialogChoice("Back"),))
                renderer.render(replace(snapshot, dialog=dialog), 0)
                renderer.render(replace(snapshot, keyboard=Keyboard("Rally", 0)), 0)
            self.assertLessEqual(renderer._text_bytes, renderer.TEXT_CACHE_BYTES)

    def test_retargeted_scroll_settles_and_motion_off_snaps(self):
        from psp_shell.ui.renderer import Renderer
        snapshot = self.snapshot(motion=True)
        with Renderer(software=True) as renderer:
            renderer.render(snapshot, 0)
            self.assertFalse(renderer.needs_frame(snapshot, .001))
            renderer.render(replace(snapshot, selected=6), .01)
            self.assertTrue(renderer.needs_frame(replace(snapshot, selected=6), .02))
            renderer.render(replace(snapshot, selected=8), .03)
            renderer.render(replace(snapshot, selected=8), .5)
            glide = renderer._retropass.scroll
            self.assertEqual(glide.sample(.5), glide.target)
            self.assertFalse(renderer.needs_frame(replace(snapshot, selected=8), .51))
            still = replace(snapshot, selected=30,
                            preferences=replace(snapshot.preferences, motion=False))
            renderer.render(still, .51)
            self.assertEqual(glide.sample(.51), glide.target)
            self.assertEqual(glide.duration, 0)


if __name__ == "__main__":
    unittest.main()
