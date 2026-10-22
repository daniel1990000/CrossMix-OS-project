"""Capture actual SDL menus using original synthetic metadata; no game launch.

Run from the repository: PYTHONPATH=project python project/evidence/source-study/capture.py
Requires the same host dependencies as project/dev/check.sh.
"""
from pathlib import Path
import os
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from psp_shell.app import main
from psp_shell.demo import DemoBackend
from psp_shell.ui.model import NavigationModel
from psp_shell.ui.renderer import Renderer


OUTPUT = Path(__file__).resolve().parent


def capture_options(name, title, scale):
    backend = DemoBackend()
    records = backend.recent()
    records[0]["label"] = records[0]["display_name"] = title
    model = NavigationModel(demo=True, preferences={"motion": False, "text_scale": scale})
    model.set_category_items(1, records)
    model.handle("right")
    model.handle("confirm")
    with Renderer(software=True) as renderer:
        renderer.render(model.snapshot(display_clock=time.strftime("%m/%d  %H:%M")), 0)
        renderer.present()
        renderer.save_screenshot(OUTPUT / name)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="psp-source-study-captures-") as scratch:
        for name, screen in (("home", "home"), ("library", "library")):
            result = main(["--demo", "--headless", "--frames", "3", "--screen", screen,
                           "--state-dir", str(Path(scratch) / name),
                           "--screenshot", str(OUTPUT / (name + ".png"))])
            if result:
                raise SystemExit(result)
    capture_options("options.png", "Skyline Circuit: The Complete Championship Edition", 1.0)
    capture_options("large-text-options.png",
                    "Skyline Circuit: The Complete Championship Edition — World Tour", 1.75)
