"""Actual SDL host captures with original synthetic text/art; no game launch.

Run: PYTHONPATH=project python project/evidence/ui-polish/capture.py
Screenshots are host renders, not photographs of a physical Smart Pro.
"""
from dataclasses import replace
import os
from pathlib import Path
import struct
import tempfile
import time

from PIL import Image, ImageDraw

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from psp_shell.ui.keyboard import KEYBOARD_KEYS
from psp_shell.ui.model import Keyboard, NavigationModel, UIItem
from psp_shell.ui.renderer import Renderer


OUTPUT = Path(__file__).resolve().parent


def clock():
    return time.strftime("%m/%d  %H:%M")


def capture_keyboard(name, scale, confirm):
    model = NavigationModel(demo=True, preferences={
        "motion": False, "text_scale": scale, "confirm": confirm})
    model.handle("search")
    snapshot = replace(model.snapshot(display_clock=clock()), keyboard=Keyboard(
        "Skyline Circuit: The Complete Championship Edition (EU) / Final Lap!",
        KEYBOARD_KEYS.index("Find")))
    with Renderer(software=True) as renderer:
        renderer.render(snapshot, 0)
        renderer.save_screenshot(OUTPUT / name)


def capture_artwork():
    with tempfile.TemporaryDirectory(prefix="synthetic-artwork-capture-") as temporary:
        root = Path(temporary)
        items = []
        for index, image_format in enumerate(("QOI", "PNG", "JPEG", "BMP", "WEBP")):
            path = root / (image_format.lower() + ".cover")
            image = Image.new("RGBA", (320, 180), (25 + index * 30, 115, 195 - index * 20, 255))
            draw = ImageDraw.Draw(image)
            for x in range(0, 320, 40):
                draw.line((x, 0, 320 - x, 180), fill=(150, 220, 255, 255), width=3)
            draw.rectangle((80, 64, 240, 116), fill=(15, 35, 75, 255))
            draw.text((137, 82), image_format, fill="white")
            if image_format == "QOI":
                raw = image.tobytes()
                chunks = b"".join(b"\xff" + raw[start:start + 4] for start in range(0, len(raw), 4))
                path.write_bytes(b"qoif" + struct.pack(">II", 320, 180) + b"\x04\0" + chunks + b"\0" * 7 + b"\x01")
            else:
                image.convert("RGB").save(path, format=image_format)
            items.append(UIItem(str(index), image_format + " synthetic cover",
                                "Original generated artwork; no game data", artwork=str(path)))
        model = NavigationModel(demo=True, preferences={"motion": False})
        model.set_category_items(0, items)
        snapshot = model.snapshot(display_clock=clock())
        with Renderer(software=True, artwork_root=root) as renderer:
            deadline = time.monotonic() + 5
            while str(root / "qoi.cover") not in renderer._art:
                if time.monotonic() > deadline:
                    raise RuntimeError("Synthetic QOI cover was not presented")
                renderer.render(snapshot, 0)
                time.sleep(.005)
            renderer.render(snapshot, 0)
            renderer.save_screenshot(OUTPUT / "artwork.png")


if __name__ == "__main__":
    OUTPUT.mkdir(exist_ok=True)
    capture_keyboard("keyboard.png", 1, "south")
    capture_keyboard("keyboard-large.png", 1.75, "east")
    capture_artwork()
