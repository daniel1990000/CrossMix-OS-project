"""RetroPass source adaptation inside the existing PSP SDL presentation."""
from dataclasses import replace
import importlib.util
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HOST_UI = importlib.util.find_spec("sdl2") is not None and importlib.util.find_spec("PIL") is not None

from psp_shell.ui.model import NavigationModel, UIItem


@unittest.skipUnless(HOST_UI, "Install host SDL2/Pillow dependencies")
class RetroPassPSPRenderTests(unittest.TestCase):
    def snapshot(self, **preferences):
        model = NavigationModel(demo=True, preferences={"theme": "psp", "motion": False, **preferences})
        model.set_category_items(0, [UIItem(str(i), "Game title " + str(i), system_id="PSP")
                                     for i in range(100)])
        return model.snapshot()

    def test_psp_keeps_waves_crossbar_and_uniform_source_cover_geometry(self):
        from PIL import Image
        from psp_shell.ui.renderer import Renderer
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory, Renderer(software=True) as renderer:
            with mock.patch.object(renderer, "_artwork", wraps=renderer._artwork) as artwork, \
                    mock.patch.object(renderer, "_crossbar", wraps=renderer._crossbar) as crossbar, \
                    mock.patch("builtins.open", side_effect=AssertionError("Render tick file I/O")):
                renderer.render(snapshot, 0)
            self.assertEqual(crossbar.call_count, 1)
            detail = [call for call in artwork.call_args_list if call.args[1] >= 930]
            self.assertEqual(len(detail), 1)
            self.assertEqual(detail[0].args[0].id, "0")
            self.assertAlmostEqual(detail[0].args[3] / detail[0].args[4], 136 / 210, places=2)
            self.assertLessEqual(artwork.call_count, 8)
            self.assertIsNone(renderer._retropass)
            target = Path(directory) / "psp.png"
            renderer.save_screenshot(target)
            with Image.open(target) as image:
                pixels = list(image.convert("RGB").getdata())
                self.assertGreater(sum(b > r * 2 and b > 90 for r, g, b in pixels), 10000)
                self.assertEqual(sum(g > 90 and g > r * 3 and g > b * 3 for r, g, b in pixels), 0)

    def test_source_recent_five_preview_is_read_only_and_bounded(self):
        from psp_shell.ui.renderer import Renderer
        supplied = tuple(UIItem(str(i), "Pick " + str(i)) for i in range(7))
        snapshot = replace(self.snapshot(), items=(UIItem("all", "All games", kind="menu"),),
                           landing_items=supplied)
        with Renderer(software=True) as renderer, \
                mock.patch.object(renderer, "_artwork", wraps=renderer._artwork) as artwork, \
                mock.patch("retropass.psp.landing_items", wraps=__import__("retropass.library", fromlist=["landing_items"]).landing_items) as source:
            renderer.render(snapshot, 0)
            self.assertEqual(source.call_count, 1)
            self.assertEqual([call.args[0].id for call in artwork.call_args_list], ["0", "1", "2", "3", "4"])
            self.assertEqual(snapshot.items[0].id, "all")
            self.assertEqual(snapshot.landing_items, supplied)

    def test_large_text_keeps_full_width_vertical_rows_and_native_dialogs(self):
        from psp_shell.ui.renderer import Renderer
        from psp_shell.ui.model import Dialog, DialogChoice, Keyboard
        with Renderer(software=True) as renderer:
            for scale in (1.25, 1.5, 1.75):
                snapshot = self.snapshot(text_scale=scale)
                with mock.patch.object(renderer, "_artwork", wraps=renderer._artwork) as artwork, \
                        mock.patch.object(renderer, "_text", wraps=renderer._text) as labels:
                    renderer.render(snapshot, 0)
                self.assertFalse(renderer._psp_retropass.visible(snapshot))
                self.assertTrue(all(call.args[1] < 500 for call in artwork.call_args_list))
                title = next(call for call in labels.call_args_list if call.args[0] == "Game title 0")
                self.assertEqual(title.args[5], 780)
                renderer.render(replace(snapshot, dialog=Dialog("Options", "Existing actions", (DialogChoice("Back"),))), 0)
                renderer.render(replace(snapshot, keyboard=Keyboard("Rally", 0)), 0)

    def test_five_landing_images_finish_once_and_reduced_motion_can_idle(self):
        from PIL import Image
        from psp_shell.ui.artwork import ArtworkDecoder
        from psp_shell.ui.renderer import Renderer
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(5):
                Image.new("RGBA", (17, 23), (index * 35, 120, 240, 255)).save(root / f"{index}.png")
            picks = tuple(UIItem(str(i), "Pick " + str(i), artwork=f"{i}.png") for i in range(5))
            snapshot = replace(self.snapshot(), items=(UIItem("all", "All games", kind="menu"),), landing_items=picks)
            decoder = ArtworkDecoder(root)
            with Renderer(software=True, artwork_decoder=decoder) as renderer:
                renderer.render(snapshot, 0)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if renderer.needs_frame(snapshot, 1):
                        renderer.render(snapshot, 1)
                    self.assertLessEqual(len(renderer._art), 6)
                    self.assertLessEqual(len(renderer._art_requested), 5)
                    if len(renderer._art) == 5 and not renderer.needs_frame(snapshot, 2):
                        break
                    time.sleep(.005)
                self.assertEqual(set(renderer._art), {f"{i}.png" for i in range(5)})
                self.assertFalse(renderer.needs_frame(snapshot, 3))
                self.assertFalse(renderer._art_retry)


if __name__ == "__main__":
    unittest.main()
