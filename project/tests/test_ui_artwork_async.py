"""Artwork admission, completion and repaint contracts under real backpressure."""
# SPDX-License-Identifier: MIT
import collections
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from psp_shell.ui.artwork import ArtworkDecoder, ArtworkResult
from psp_shell.ui.model import NavigationModel, UIItem


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HOST_UI = importlib.util.find_spec("sdl2") is not None and importlib.util.find_spec("PIL") is not None


class ControlledDecoder(ArtworkDecoder):
    def __init__(self, root):
        self.started = threading.Event()
        self.release = threading.Event()
        self.counts = collections.Counter()
        super().__init__(root)

    def _decode(self, path):
        self.counts[path] += 1
        self.started.set()
        if not self.release.wait(5):
            return ArtworkResult(path, error="Test decode was not released")
        if path == "missing":
            return ArtworkResult(path, error="Missing optional artwork")
        return ArtworkResult(path, 4, 4, b"\x55\xdd\x88\xff" * 16)

    def close(self):
        self.release.set()
        super().close()


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


class ArtworkQueueTests(unittest.TestCase):
    def test_full_queue_rejects_without_losing_admitted_results(self):
        with tempfile.TemporaryDirectory() as directory:
            decoder = ControlledDecoder(directory)
            try:
                self.assertTrue(decoder.request("first"))
                self.assertTrue(decoder.started.wait(2))
                self.assertTrue(decoder.request("second"))
                self.assertTrue(decoder.request("third"))
                self.assertFalse(decoder.request("retry"))
                decoder.release.set()
                results = []
                def completed():
                    results.extend(decoder.poll())
                    return len(results) == 3
                self.assertTrue(wait_until(completed))
                self.assertEqual({image.path for image in results}, {"first", "second", "third"})
                self.assertTrue(decoder.request("retry"))
                self.assertTrue(wait_until(lambda: bool(decoder.poll())))
                self.assertEqual(decoder.counts["retry"], 1)
            finally:
                decoder.close()
            self.assertFalse(decoder._thread.is_alive())


@unittest.skipUnless(HOST_UI, "Install the optional host PySDL2/Pillow dependencies")
class ArtworkRepaintTests(unittest.TestCase):
    def test_reduced_motion_loads_neighbors_and_refocused_evicted_cover(self):
        from psp_shell.ui.renderer import Renderer
        model = NavigationModel(preferences={"motion": False})
        model.set_category_items(0, [UIItem(str(i), "Game " + str(i), artwork="cover" + str(i))
                                     for i in range(9)] + [UIItem("missing", "Missing cover", artwork="missing")])
        with tempfile.TemporaryDirectory() as directory:
            decoder = ControlledDecoder(Path(directory))
            with Renderer(software=True, artwork_decoder=decoder) as renderer:
                snapshot = model.snapshot()
                renderer.render(snapshot, 0)
                self.assertTrue(decoder.started.wait(2))
                self.assertEqual(next(iter(decoder.counts)), "cover0")
                self.assertFalse(renderer.needs_frame(snapshot, 1))
                decoder.release.set()
                self.assertTrue(wait_until(lambda: renderer.needs_frame(snapshot, 1)))
                # Rechecking readiness must not consume the pending repaint.
                self.assertTrue(renderer.needs_frame(snapshot, 1))
                renderer.render(snapshot, 1)

                def settle(selected):
                    state = model.snapshot()
                    def loaded():
                        if renderer.needs_frame(state, 10):
                            renderer.render(state, 10)
                        self.assertLessEqual(len(renderer._art), renderer.ART_CACHE_ENTRIES)
                        self.assertLessEqual(len(renderer._art_retry), renderer.ART_CACHE_ENTRIES * 2)
                        self.assertLessEqual(len(renderer._art_requested), 5)
                        return selected in renderer._art or selected in renderer._art_failed
                    self.assertTrue(wait_until(loaded), selected)

                settle("cover0")
                def neighbors_loaded():
                    if renderer.needs_frame(snapshot, 10):
                        renderer.render(snapshot, 10)
                    return {"cover0", "cover1", "cover2"} <= set(renderer._art)
                self.assertTrue(wait_until(neighbors_loaded))
                # More rows than both queue and texture cache exercise misses
                # after scrolling, rather than one permanent requested marker.
                for index in range(1, 10):
                    model.handle("down")
                    settle("cover" + str(index) if index < 9 else "missing")
                self.assertNotIn("cover0", renderer._art)
                for _ in range(15):
                    renderer.render(model.snapshot(), 20)
                self.assertEqual(decoder.counts["missing"], 1)
                for _ in range(9):
                    model.handle("up")
                settle("cover0")
                self.assertGreaterEqual(decoder.counts["cover0"], 2)
                self.assertEqual(decoder.counts["missing"], 1)


if __name__ == "__main__":
    unittest.main()
