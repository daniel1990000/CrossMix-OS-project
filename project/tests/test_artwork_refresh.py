"""Real decode/refresh boundaries; no physical card, game or save is used."""
# SPDX-License-Identifier: MIT
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest import mock

from PIL import Image

from psp_shell.adapters.spruce import PyUIModelProvider, SpruceBackend
from psp_shell.app import AppError, Dispatcher
from psp_shell.settings import SettingsStore
from psp_shell.ui.artwork import ArtworkDecoder, ArtworkResult
from psp_shell.ui.model import NavigationModel, UIItem
from psp_shell.ui.renderer import Renderer


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("Artwork worker did not reach the required observation")


class DelayedDecoder(ArtworkDecoder):
    def __init__(self, root, *, old_error=False):
        self.started = [threading.Event(), threading.Event()]
        self.release = [threading.Event(), threading.Event()]
        self.count = 0
        self.old_error = old_error
        super().__init__(root)

    def _decode(self, path):
        number = min(self.count, 1)
        self.count += 1
        self.started[number].set()
        if not self.release[number].wait(5):
            return ArtworkResult(path, error="Test decode was not released")
        if number == 0 and self.old_error:
            return ArtworkResult(path, error="Old missing artwork")
        color = b"\xff\0\0\xff" if number == 0 else b"\0\0\xff\xff"
        return ArtworkResult(path, 4, 4, color * 16)

    def close(self):
        for event in self.release:
            event.set()
        super().close()


class ArtworkRefreshTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="artwork-refresh-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "cover.png"
        self.model = NavigationModel(preferences={"motion": False})
        self.model.set_category_items(0, [UIItem("stable-id", "Original synthetic title",
                                               artwork=str(self.path))])

    def render_until(self, renderer, predicate):
        def observed():
            snapshot = self.model.snapshot()
            if renderer.needs_frame(snapshot, 10):
                renderer.render(snapshot, 10)
            self.assertLessEqual(len(renderer._art), renderer.ART_CACHE_ENTRIES)
            self.assertLessEqual(len(renderer._art_failed), 128)
            self.assertLessEqual(len(renderer._art_retry), renderer.ART_CACHE_ENTRIES * 2)
            return predicate()
        wait_for(observed)

    def test_same_path_replacement_refreshes_after_equal_size_and_mtime(self):
        Image.new("RGBA", (4, 4), "red").save(self.path)
        original = self.path.stat()
        with Renderer(software=True, artwork_root=self.root) as renderer:
            uploaded = []
            create = renderer._texture
            def record(raster):
                if (raster.width, raster.height) == (4, 4):
                    uploaded.append(raster.pixels)
                return create(raster)
            with mock.patch.object(renderer, "_texture", side_effect=record):
                self.render_until(renderer, lambda: str(self.path) in renderer._art)
                self.assertEqual(uploaded, [b"\xff\0\0\xff" * 16])
                Image.new("RGBA", (4, 4), "blue").save(self.path)
                os.utime(self.path, ns=(original.st_atime_ns, original.st_mtime_ns))
                self.assertEqual(self.path.stat().st_size, original.st_size)
                self.model.handle("refresh")
                with mock.patch("builtins.open", side_effect=AssertionError("Renderer performed file I/O")):
                    renderer.needs_frame(self.model.snapshot(), 10)
                self.render_until(renderer, lambda: len(uploaded) == 2)
                self.assertEqual(uploaded[-1], b"\0\0\xff\xff" * 16)
                self.assertEqual(self.model.snapshot().selected_item.id, "stable-id")

    def test_negative_cache_is_retried_when_same_path_appears(self):
        with Renderer(software=True, artwork_root=self.root) as renderer:
            self.render_until(renderer, lambda: str(self.path) in renderer._art_failed)
            Image.new("RGBA", (4, 4), "green").save(self.path)
            self.model.handle("refresh")
            self.render_until(renderer, lambda: str(self.path) in renderer._art)
            self.assertNotIn(str(self.path), renderer._art_failed)
            self.assertEqual(renderer._art_generation, 1)
            self.assertEqual(self.model.snapshot().selected_item.id, "stable-id")

    def test_late_old_success_and_failure_cannot_replace_or_poison_new_request(self):
        for old_error in (False, True):
            with self.subTest(old_error=old_error):
                self.model = NavigationModel(preferences={"motion": False})
                self.model.set_category_items(0, [UIItem("stable-id", "Synthetic", artwork=str(self.path))])
                decoder = DelayedDecoder(self.root, old_error=old_error)
                with Renderer(software=True, artwork_decoder=decoder) as renderer:
                    renderer.render(self.model.snapshot(), 0)
                    self.assertTrue(decoder.started[0].wait(2))
                    self.model.handle("refresh")
                    renderer.needs_frame(self.model.snapshot(), 10)
                    decoder.release[0].set()
                    self.assertTrue(decoder.started[1].wait(2))
                    renderer.needs_frame(self.model.snapshot(), 10)
                    self.assertNotIn(str(self.path), renderer._art)
                    self.assertNotIn(str(self.path), renderer._art_failed)
                    self.assertIn(str(self.path), renderer._art_requested)
                    decoder.release[1].set()
                    self.render_until(renderer, lambda: str(self.path) in renderer._art)
                    self.assertEqual(renderer._art_generation, 1)
                    self.assertEqual(decoder.count, 2)


class MetadataRefreshTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="artwork-metadata-refresh-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.card = self.root / "card"
        (self.card / "Emu/PSP").mkdir(parents=True)
        (self.card / "Emu/PSP/config.json").write_text(json.dumps({
            "label": "PSP", "extlist": "iso", "launch": "launch.sh"}))
        (self.card / "Roms/PSP").mkdir(parents=True)
        (self.card / "Roms/PSP/Synthetic.iso").write_bytes(b"Original synthetic fixture, not game data")
        self.backend = SpruceBackend(self.card)
        self.dispatcher = Dispatcher(self.backend, SettingsStore(str(self.root / "settings")), self.root / "state")

    def test_refresh_clamps_a_removed_page_to_the_last_surviving_game(self):
        model = NavigationModel()
        model.set_category_items(0, [UIItem(str(i), "Synthetic " + str(i)) for i in range(80, 100)],
                                 offset=80, total=100)
        for _ in range(17):
            model.handle("down")
        request = next(command for command in model.handle("refresh") if command.method == "library.query")
        self.assertEqual(request.params["offset"], 80)
        commands = model.receive(request, {"items": [], "offset": 80, "total": 5})
        self.assertEqual(model.snapshot().selected_item.id, "97")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].params["offset"], 0)
        model.receive(commands[0], {"items": [{"game_id": str(i), "label": "Synthetic " + str(i)}
                                             for i in range(5)], "offset": 0, "total": 5})
        self.assertEqual(model.snapshot().selected_item.id, "4")
        self.assertEqual(model.snapshot().offset, 0)

    def test_refresh_discovers_new_bmp_and_webp_without_changing_owner_files(self):
        protected = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.card.rglob("*") if p.is_file()}
        before = self.backend.games()["items"][0]
        self.assertEqual(before["artwork_ref"], "")
        for suffix in ("bmp", "webp"):
            with self.subTest(suffix=suffix):
                folder = self.card / "Roms/PSP/Imgs"
                folder.mkdir(exist_ok=True)
                cover = folder / ("Synthetic." + suffix)
                Image.new("RGB", (4, 4), "blue").save(cover)
                self.dispatcher.dispatch("library.systems", {"refresh": True})
                after = self.backend.games()["items"][0]
                self.assertEqual(after["artwork_ref"], str(cover))
                self.assertEqual(after["id"], before["id"])
                cover.unlink()
        for path, digest in protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_refresh_field_is_typed_and_normal_reads_do_not_invalidate(self):
        for value in (1, "true", None, []):
            with self.subTest(value=value), self.assertRaises(AppError) as error:
                self.dispatcher.dispatch("library.systems", {"refresh": value})
            self.assertEqual(error.exception.code, "INVALID_PARAMS")
        with mock.patch.object(self.backend, "refresh", wraps=self.backend.refresh) as refresh:
            self.dispatcher.dispatch("library.systems")
            self.dispatcher.dispatch("library.systems", {"refresh": False})
            refresh.assert_not_called()
            self.dispatcher.dispatch("library.systems", {"refresh": True})
            refresh.assert_called_once_with()

    def test_live_refresh_keeps_initialized_authorities_and_avoids_snapshot_scan(self):
        systems = SimpleNamespace(get_active_systems=lambda: [])
        device = SimpleNamespace(run_game=lambda model: None)
        provider = PyUIModelProvider(self.card, system_manager=systems, game_list=lambda name: (),
            device=device, favorites_manager=object(), recents_manager=object(),
            release_resources=lambda: None, quiescent=lambda: True)
        sentinel = object()
        provider.models["retained"] = sentinel
        backend = SpruceBackend(self.card, read_only=False, managers=provider)
        with mock.patch.object(provider, "_load", side_effect=AssertionError("A second scanner was started")):
            backend.refresh()
            self.assertEqual(backend.systems(), [])
        self.assertIs(provider.system_manager, systems)
        self.assertIs(provider.device, device)
        self.assertIs(provider.models["retained"], sentinel)


if __name__ == "__main__":
    unittest.main()
