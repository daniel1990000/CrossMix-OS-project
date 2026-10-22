"""Host SDL visual/backend contracts; no device compatibility is inferred."""
import ctypes
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

HOST_UI = importlib.util.find_spec("sdl2") is not None and importlib.util.find_spec("PIL") is not None

from psp_shell.ui.artwork import ArtworkDecoder, image_dimensions
from psp_shell.ui.model import NavigationModel, UIItem


@unittest.skipUnless(HOST_UI, "Install the optional host PySDL2/Pillow dependencies")
class RenderTests(unittest.TestCase):
    def test_keyboard_workspace_hides_the_underlying_menu(self):
        from dataclasses import replace
        from psp_shell.ui.renderer import Renderer
        from psp_shell.ui.model import Keyboard
        model = NavigationModel(demo=True, preferences={"motion": False})
        snapshot = replace(model.snapshot(), keyboard=Keyboard("Rally", 0))
        with tempfile.TemporaryDirectory() as directory, Renderer(software=True) as renderer:
            renderer.render(snapshot, 0)
            first = Path(directory) / "first.png"
            renderer.save_screenshot(first)
            changed = replace(snapshot, category=3, title="Different page",
                              items=(UIItem("other", "A title that must stay hidden"),), selected=0)
            renderer.render(changed, 0)
            second = Path(directory) / "second.png"
            renderer.save_screenshot(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_older_sdl_wave_fallback_does_not_call_newer_runtime_symbols(self):
        from psp_shell.ui.renderer import Renderer
        model = NavigationModel(preferences={"motion": False})
        with Renderer(software=True) as renderer:
            renderer._sdl_version = (2, 0, 10)
            renderer._geometry_supported = False
            with mock.patch("sdl2.SDL_RenderGeometry", side_effect=AssertionError("SDL too old")), \
                 mock.patch("sdl2.SDL_SetTextureScaleMode", side_effect=AssertionError("SDL too old")):
                renderer.render(model.snapshot(), 0)
                renderer.present()
            renderer._geometry_supported = True
            with mock.patch("sdl2.SDL_RenderGeometry", return_value=-1) as unsupported:
                renderer.render(model.snapshot(), 0)
                self.assertFalse(renderer._geometry_supported)
                self.assertEqual(unsupported.call_count, 1)

    def test_deterministic_static_frame_and_no_render_tick_file_reads(self):
        from PIL import Image, ImageChops
        from psp_shell.ui.renderer import Renderer
        model = NavigationModel(demo=True, preferences={"motion": False})
        with tempfile.TemporaryDirectory() as directory, Renderer(software=True) as renderer:
            # Lazy font-size creation uses the already-loaded font bytes.
            with mock.patch("builtins.open", side_effect=AssertionError("Render tick attempted file I/O")):
                renderer.render(model.snapshot(), 10.0)
                renderer.present()
            first = Path(directory) / "first.png"
            renderer.save_screenshot(first)
            renderer.render(model.snapshot(), 900.0)
            second = Path(directory) / "second.png"
            renderer.save_screenshot(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with Image.open(first) as image:
                self.assertEqual(image.size, (1280, 720))
                # The focused pictogram and title remain bright in software
                # rendering; focus no longer depends on a coloured row tile.
                focus = image.convert("RGB").crop((240, 330, 730, 416))
                white_pixels = sum(min(pixel) > 225 for pixel in focus.getdata())
                self.assertGreater(white_pixels, 350)
            model.handle("right")
            renderer.render(model.snapshot(), 901.0)
            changed = Path(directory) / "changed.png"
            renderer.save_screenshot(changed)
            with Image.open(first) as a, Image.open(changed) as b:
                self.assertIsNotNone(ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox())

    def test_long_unicode_large_high_contrast_dialog_and_keyboard_render(self):
        from PIL import Image
        from psp_shell.ui.renderer import Renderer
        model = NavigationModel(demo=True, preferences={"text_scale": 1.75, "high_contrast": True, "motion": False})
        model.set_category_items(0, [UIItem("unicode", "日本語 · café · " + "A very long translated title " * 30,
                                                "Unknown glyphs must stay bounded", resume_available=False)])
        with tempfile.TemporaryDirectory() as directory, Renderer(software=True) as renderer:
            renderer.render(model.snapshot(), 0)
            model.handle("confirm")
            renderer.render(model.snapshot(), 0)
            self.assertIsNotNone(model.snapshot().dialog)
            model.handle("search")
            renderer.render(model.snapshot(), 0)
            self.assertEqual(model.snapshot().dialog.message_page, 1)
            model.handle("back")
            model.handle("search")
            model.handle("text", "Unicode: 日本語 café")
            renderer.render(model.snapshot(), 0)
            target = Path(directory) / "keyboard.bmp"
            renderer.save_screenshot(target)
            with Image.open(target) as image:
                self.assertEqual(image.size, (1280, 720))
            self.assertLessEqual(renderer._text_bytes, renderer.TEXT_CACHE_BYTES)
            self.assertLessEqual(len(renderer._text_cache), renderer.TEXT_CACHE_ENTRIES)

    def test_embedding_restores_target_and_state_without_pillow_import(self):
        project = Path(__file__).resolve().parents[1]
        script = r'''
import ctypes, importlib.abc, sys
class RejectPillow(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PIL" or fullname.startswith("PIL."):
            raise ImportError("Pillow intentionally absent on embedded target")
sys.meta_path.insert(0, RejectPillow())
import sdl2
from psp_shell.ui.model import NavigationModel
from psp_shell.ui.text import Raster
from psp_shell.ui.renderer import Renderer
class ExistingText:
    def measure(self, text, size): return len(str(text)) * 5
    def wrap(self, text, size, width, max_lines=5): return tuple(str(text).split("\n"))[:max_lines]
    def raster(self, text, size, color, width):
        w=max(1,min(width,len(str(text))*5)); h=8
        return Raster(w,h,bytes(color)*w*h)
assert sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO) == 0
window=sdl2.SDL_CreateWindow(b"existing",0,0,1280,720,0)
raw=sdl2.SDL_CreateRenderer(window,-1,sdl2.SDL_RENDERER_SOFTWARE|sdl2.SDL_RENDERER_TARGETTEXTURE)
target=sdl2.SDL_CreateTexture(raw,sdl2.SDL_PIXELFORMAT_RGBA8888,sdl2.SDL_TEXTUREACCESS_TARGET,1280,720)
assert target
sdl2.SDL_SetRenderTarget(raw,target)
clip=sdl2.SDL_Rect(12,17,250,350)
sdl2.SDL_RenderSetClipRect(raw,ctypes.byref(clip))
sdl2.SDL_SetRenderDrawColor(raw,3,7,11,19)
def address(pointer): return ctypes.cast(pointer,ctypes.c_void_p).value
view=Renderer(external_renderer=raw,external_window=window,external_target=target,own_resources=False,text_backend=ExistingText())
view.render(NavigationModel().snapshot(),0.0)
assert address(sdl2.SDL_GetRenderTarget(raw)) == address(target)
current=sdl2.SDL_Rect()
sdl2.SDL_RenderGetClipRect(raw,ctypes.byref(current))
assert (current.x,current.y,current.w,current.h)==(12,17,250,350)
rgba=[ctypes.c_uint8() for _ in range(4)]
sdl2.SDL_GetRenderDrawColor(raw,*(ctypes.byref(c) for c in rgba))
assert tuple(c.value for c in rgba)==(3,7,11,19)
view.close()
assert sdl2.SDL_WasInit(sdl2.SDL_INIT_VIDEO)
assert sdl2.SDL_QueryTexture(target,None,None,None,None)==0
sdl2.SDL_DestroyTexture(target); sdl2.SDL_DestroyRenderer(raw); sdl2.SDL_DestroyWindow(window); sdl2.SDL_Quit()
assert "PIL" not in sys.modules
print("embedded state preserved; Pillow absent")
'''
        env = {**os.environ, "PYTHONPATH": str(project), "SDL_VIDEODRIVER": "dummy"}
        result = subprocess.run([sys.executable, "-c", script], env=env, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Pillow absent", result.stdout)

    def test_four_large_dialog_choices_do_not_overlap_body_or_page_hint(self):
        from psp_shell.ui.model import Dialog, DialogChoice
        from psp_shell.ui.renderer import Renderer
        model = NavigationModel(preferences={"text_scale": 1.75, "motion": False, "high_contrast": True})
        model._dialog = Dialog("Large text", "\n".join("Body line " + str(index) for index in range(20)),
            tuple(DialogChoice(title) for title in ("Resume", "Fresh start", "Game options", "Cancel")))
        drawn = []
        with Renderer(software=True) as renderer:
            label = renderer._label
            def record(text, x, y, size, color, max_width, scale=1.0):
                result = label(text, x, y, size, color, max_width, scale)
                drawn.append((text, y, result[1]))
                return result
            with mock.patch.object(renderer, "_label", side_effect=record):
                renderer.render(model.snapshot(), 0)
            body = [entry for entry in drawn if entry[0].startswith("Body line")]
            choices = [entry for entry in drawn if entry[0] in {"Resume", "Fresh start", "Game options", "Cancel"}]
            hint = next(entry for entry in drawn if entry[0].startswith("X  More text"))
            self.assertTrue(body)
            self.assertEqual(len(choices), 4)
            self.assertLess(max(y + height for _, y, height in body), min(y for _, y, _ in choices))
            self.assertLess(max(y + height for _, y, height in choices), hint[1])


class ArtworkHeaderTests(unittest.TestCase):
    def test_png_and_jpeg_preflight_and_truncated_headers(self):
        png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 640, 480)
        self.assertEqual(image_dimensions(png), (640, 480))
        jpeg = b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", 720, 1280) + b"\x03" + b"\0" * 9
        self.assertEqual(image_dimensions(jpeg), (1280, 720))
        for malformed in (b"", b"\xff\xd8", b"\xff\xd8\xff\xe0\xff\xff", b"not an image"):
            with self.assertRaises(ValueError):
                image_dimensions(malformed)

    @unittest.skipUnless(HOST_UI, "Install the optional host Pillow dependency")
    def test_bounded_decode_and_outside_symlink_refusal(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "card"
            root.mkdir()
            image = root / "wide.png"
            Image.new("RGB", (1600, 100), "green").save(image)
            outside = Path(directory) / "outside.png"
            Image.new("RGB", (10, 10), "red").save(outside)
            (root / "escape.png").symlink_to(outside)
            decoder = ArtworkDecoder(root)
            try:
                result = decoder._decode(str(image))
                self.assertEqual(result.width, 512)
                self.assertLessEqual(len(result.pixels), 512 * 512 * 4)
                self.assertTrue(decoder._decode(str(root / "escape.png")).error)
                self.assertTrue(decoder._decode(str(outside)).error)
                (root / "huge.bin").write_bytes(b"x" * (decoder.MAX_SOURCE_BYTES + 1))
                with self.assertRaises(ValueError):
                    decoder._decode(str(root / "huge.bin"))
            finally:
                decoder.close()
            self.assertFalse(decoder._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
