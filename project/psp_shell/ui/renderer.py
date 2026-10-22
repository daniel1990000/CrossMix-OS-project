"""Original SDL2 interface renderer with a software backend and PyUI embedding.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
import ctypes
import hashlib
import math
from pathlib import Path
from typing import Any, Iterator

import sdl2

from .artwork import ArtworkDecoder, SDLArtworkDecoder
from .model import Dialog, Preferences, UIItem, UISnapshot
from .text import Raster, TextRasterizer


LOGICAL_WIDTH = 1280
LOGICAL_HEIGHT = 720


class RendererError(RuntimeError):
    pass


def _error(action: str) -> RendererError:
    message = sdl2.SDL_GetError()
    return RendererError(action + ": " + (message.decode("utf-8", "replace") if message else "SDL failed"))


class Renderer:
    """A presentation-only SDL renderer.

    In standalone mode this object owns one window/renderer and a logical frame
    target. In embedded mode pass PyUI's raw ``Display.renderer.renderer`` and
    ``Display.window.window`` as ``external_renderer``/``external_window`` with
    ``own_resources=False``. The existing target (normally PyUI's render_canvas)
    and renderer state are restored after each frame; ``present`` becomes a no-op
    so PyUI retains sole presentation and lifecycle ownership.

    Font/gradient loading happens at construction. Artwork I/O happens only on
    the bounded decoder thread. ``render`` accepts an immutable UISnapshot and
    performs no file reads, subprocess work, backend calls or device writes.
    """

    TEXT_CACHE_BYTES = 12 * 1024 * 1024
    TEXT_CACHE_ENTRIES = 256
    ART_CACHE_ENTRIES = 3

    def __init__(self, width: int = 1280, height: int = 720,
                 font_path: str | Path | None = None, software: bool = False,
                 external_renderer: Any = None, external_window: Any = None,
                 own_resources: bool | None = None, external_target: Any = None,
                 artwork_root: str | Path | None = None, title: str = "spruce interface preview",
                 text_backend: Any = None, artwork_decoder: Any = None):
        if not (320 <= width <= 3840 and 240 <= height <= 2160):
            raise ValueError("Window dimensions exceed the supported preview range")
        self._external = external_renderer is not None
        self._owns_resources = not self._external if own_resources is None else bool(own_resources)
        if self._external and self._owns_resources:
            raise ValueError("An embedded view cannot own the existing PyUI renderer")
        if not self._external and not self._owns_resources:
            raise ValueError("A standalone renderer must own its window")
        self.window = getattr(external_window, "window", external_window)
        self.renderer = getattr(external_renderer, "renderer", external_renderer)
        self._external_target = external_target
        self._frame = None
        self._gradient = None
        self._decoder = None
        self._text_cache: OrderedDict[tuple[Any, ...], tuple[Any, int, int, int]] = OrderedDict()
        self._text_bytes = 0
        self._art: OrderedDict[str, tuple[Any, int, int]] = OrderedDict()
        self._art_requested: OrderedDict[str, None] = OrderedDict()
        self._last_selected_art = ""
        self._fingerprint = None
        self._last_change = 0.0
        self._last_now = 0.0
        self._selected_y = None
        self._closed = False
        self._audio_device = 0
        self._click_buffer = None
        self._last_target = None
        try:
            if not self._external:
                if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_EVENTS) != 0:
                    raise _error("Initialize SDL")
                self.window = sdl2.SDL_CreateWindow(title.encode("utf-8"), sdl2.SDL_WINDOWPOS_CENTERED,
                                                   sdl2.SDL_WINDOWPOS_CENTERED, width, height,
                                                   sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_ALLOW_HIGHDPI)
                if not self.window:
                    raise _error("Create window")
                flags = sdl2.SDL_RENDERER_SOFTWARE if software else sdl2.SDL_RENDERER_ACCELERATED | sdl2.SDL_RENDERER_PRESENTVSYNC
                self.renderer = sdl2.SDL_CreateRenderer(self.window, -1, flags | sdl2.SDL_RENDERER_TARGETTEXTURE)
                if not self.renderer and not software:
                    self.renderer = sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_SOFTWARE | sdl2.SDL_RENDERER_TARGETTEXTURE)
                if not self.renderer:
                    raise _error("Create renderer")
                self._frame = sdl2.SDL_CreateTexture(self.renderer, sdl2.SDL_PIXELFORMAT_RGBA8888,
                                                   sdl2.SDL_TEXTUREACCESS_TARGET, LOGICAL_WIDTH, LOGICAL_HEIGHT)
                if not self._frame:
                    raise _error("Create logical frame")
            if text_backend is not None:
                self.text = text_backend
            elif self._external:
                raise ValueError("Embedded rendering requires an injected existing SDL_ttf text backend")
            else:
                if font_path is None:
                    font_path = self.default_font_path()
                self.text = TextRasterizer(font_path)
            self._gradient = self._make_gradient()
            self._decoder = artwork_decoder if artwork_decoder is not None else (SDLArtworkDecoder(artwork_root) if self._external else ArtworkDecoder(artwork_root))
            info = sdl2.SDL_RendererInfo()
            if sdl2.SDL_GetRendererInfo(self.renderer, ctypes.byref(info)) == 0:
                self.backend = info.name.decode("utf-8", "replace") if info.name else "unknown"
            else:
                self.backend = "unknown"
        except BaseException:
            self.close()
            raise

    @staticmethod
    def default_font_path() -> Path:
        return Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoSans.ttf"

    def _texture(self, raster: Raster) -> Any:
        texture = sdl2.SDL_CreateTexture(self.renderer, sdl2.SDL_PIXELFORMAT_RGBA32,
                                        sdl2.SDL_TEXTUREACCESS_STATIC, raster.width, raster.height)
        if not texture:
            raise _error("Create interface texture")
        buffer = ctypes.create_string_buffer(raster.pixels)
        if sdl2.SDL_UpdateTexture(texture, None, buffer, raster.width * 4) != 0:
            sdl2.SDL_DestroyTexture(texture)
            raise _error("Upload interface texture")
        sdl2.SDL_SetTextureBlendMode(texture, sdl2.SDL_BLENDMODE_BLEND)
        return texture

    def _make_gradient(self) -> Any:
        top, bottom = (13, 18, 38), (12, 45, 55)
        pixels = bytearray()
        for y in range(LOGICAL_HEIGHT):
            amount = y / (LOGICAL_HEIGHT - 1)
            color = tuple(round(a + (b - a) * amount) for a, b in zip(top, bottom)) + (255,)
            pixels.extend(bytes(color) * 32)
        return self._texture(Raster(32, LOGICAL_HEIGHT, bytes(pixels)))

    @contextmanager
    def _state(self) -> Iterator[None]:
        target = sdl2.SDL_GetRenderTarget(self.renderer)
        viewport, clip = sdl2.SDL_Rect(), sdl2.SDL_Rect()
        sdl2.SDL_RenderGetViewport(self.renderer, ctypes.byref(viewport))
        sdl2.SDL_RenderGetClipRect(self.renderer, ctypes.byref(clip))
        clipping = bool(sdl2.SDL_RenderIsClipEnabled(self.renderer))
        logical_w, logical_h = ctypes.c_int(), ctypes.c_int()
        scale_x, scale_y = ctypes.c_float(), ctypes.c_float()
        sdl2.SDL_RenderGetLogicalSize(self.renderer, ctypes.byref(logical_w), ctypes.byref(logical_h))
        sdl2.SDL_RenderGetScale(self.renderer, ctypes.byref(scale_x), ctypes.byref(scale_y))
        color = [ctypes.c_uint8() for _ in range(4)]
        sdl2.SDL_GetRenderDrawColor(self.renderer, *(ctypes.byref(part) for part in color))
        blend = ctypes.c_int()
        sdl2.SDL_GetRenderDrawBlendMode(self.renderer, ctypes.byref(blend))
        try:
            yield
        finally:
            sdl2.SDL_SetRenderTarget(self.renderer, target)
            sdl2.SDL_RenderSetLogicalSize(self.renderer, logical_w.value, logical_h.value)
            sdl2.SDL_RenderSetScale(self.renderer, scale_x.value, scale_y.value)
            sdl2.SDL_RenderSetViewport(self.renderer, ctypes.byref(viewport))
            sdl2.SDL_RenderSetClipRect(self.renderer, ctypes.byref(clip) if clipping else None)
            sdl2.SDL_SetRenderDrawColor(self.renderer, *(part.value for part in color))
            sdl2.SDL_SetRenderDrawBlendMode(self.renderer, blend.value)

    def _color(self, color: tuple[int, ...]) -> None:
        sdl2.SDL_SetRenderDrawColor(self.renderer, *color[:3], color[3] if len(color) == 4 else 255)

    def _rect(self, x: float, y: float, width: float, height: float, color: tuple[int, ...]) -> None:
        if width <= 0 or height <= 0:
            return
        self._color(color)
        rect = sdl2.SDL_Rect(round(x), round(y), round(width), round(height))
        sdl2.SDL_RenderFillRect(self.renderer, ctypes.byref(rect))

    def _round_rect(self, x: float, y: float, width: float, height: float,
                    color: tuple[int, ...], radius: int = 12) -> None:
        radius = min(radius, int(width / 2), int(height / 2))
        self._rect(x + radius, y, width - 2 * radius, height, color)
        self._rect(x, y + radius, radius, height - 2 * radius, color)
        self._rect(x + width - radius, y + radius, radius, height - 2 * radius, color)
        for offset in range(radius):
            inset = radius - math.sqrt(max(0, radius * radius - (radius - offset - 0.5) ** 2))
            self._rect(x + inset, y + offset, width - 2 * inset, 1, color)
            self._rect(x + inset, y + height - offset - 1, width - 2 * inset, 1, color)

    def _line(self, x1: float, y1: float, x2: float, y2: float,
              color: tuple[int, ...], thickness: int = 1) -> None:
        self._color(color)
        for offset in range(thickness):
            sdl2.SDL_RenderDrawLine(self.renderer, round(x1), round(y1 + offset), round(x2), round(y2 + offset))

    def _circle(self, x: float, y: float, radius: int, color: tuple[int, ...]) -> None:
        for offset in range(-radius, radius + 1):
            half = math.sqrt(max(0, radius * radius - offset * offset))
            self._rect(x - half, y + offset, half * 2 + 1, 1, color)

    def _label(self, text: str, x: float, y: float, size: int, color: tuple[int, ...], max_width: int,
               scale: float = 1.0) -> tuple[int, int]:
        rgba = tuple(color[:3]) + (color[3] if len(color) == 4 else 255,)
        pixels = max(10, min(92, round(size * scale)))
        key = (str(text)[:2048], pixels, rgba, int(max_width))
        cached = self._text_cache.get(key)
        if cached is None:
            raster = self.text.raster(key[0], pixels, rgba, max(1, int(max_width)))
            texture = self._texture(raster)
            cost = raster.width * raster.height * 4
            cached = (texture, raster.width, raster.height, cost)
            self._text_cache[key] = cached
            self._text_bytes += cost
            while len(self._text_cache) > self.TEXT_CACHE_ENTRIES or self._text_bytes > self.TEXT_CACHE_BYTES:
                _, removed = self._text_cache.popitem(last=False)
                self._text_bytes -= removed[3]
                sdl2.SDL_DestroyTexture(removed[0])
        else:
            self._text_cache.move_to_end(key)
        texture, width, height, _ = cached
        destination = sdl2.SDL_Rect(round(x), round(y), width, height)
        sdl2.SDL_RenderCopy(self.renderer, texture, None, ctypes.byref(destination))
        return width, height

    def _paragraph(self, text: str, x: float, y: float, size: int, color: tuple[int, ...],
                   width: int, max_lines: int = 5, scale: float = 1.0) -> int:
        pixels = round(size * scale)
        lines = self.text.wrap(text, pixels, width, max_lines)
        line_height = pixels + 7
        for index, line in enumerate(lines):
            self._label(line, x, y + index * line_height, size, color, width, scale)
        return len(lines) * line_height

    def _icon(self, kind: str, x: float, y: float, size: int, color: tuple[int, ...]) -> None:
        unit = size / 32
        def line(a: float, b: float, c: float, d: float) -> None:
            self._line(x + a * unit, y + b * unit, x + c * unit, y + d * unit, color, max(1, round(2 * unit)))
        if kind in ("Games", "game", "system", "all"):
            for a, b, c, d in ((7, 9, 25, 9), (7, 9, 3, 24), (25, 9, 29, 24), (3, 24, 10, 24), (10, 24, 13, 20), (13, 20, 19, 20), (19, 20, 22, 24), (22, 24, 29, 24), (7, 15, 15, 15), (11, 11, 11, 19)):
                line(a, b, c, d)
            self._circle(x + 23 * unit, y + 14 * unit, max(1, round(1.7 * unit)), color)
            self._circle(x + 20 * unit, y + 17 * unit, max(1, round(1.7 * unit)), color)
        elif kind in ("Continue Playing", "recent", "random"):
            points = [(x + 16 * unit + math.cos(t * math.tau / 28) * 12 * unit,
                       y + 16 * unit + math.sin(t * math.tau / 28) * 12 * unit) for t in range(29)]
            self._polyline(points, color)
            line(16, 8, 16, 17)
            line(16, 17, 23, 20)
        elif kind in ("Tools", "tool"):
            for a, b, c, d in ((5, 5, 13, 13), (13, 13, 24, 26), (24, 26, 28, 22), (28, 22, 16, 11), (16, 11, 8, 3), (4, 26, 11, 19), (22, 11, 28, 5)):
                line(a, b, c, d)
        elif kind == "favorites":
            points = [(16, 27), (4, 16), (4, 10), (8, 6), (12, 6), (16, 10), (20, 6), (24, 6), (28, 10), (28, 16), (16, 27)]
            self._polyline([(x + a * unit, y + b * unit) for a, b in points], color)
        elif kind == "search":
            points = [(x + 13 * unit + math.cos(t * math.tau / 24) * 8 * unit,
                       y + 13 * unit + math.sin(t * math.tau / 24) * 8 * unit) for t in range(25)]
            self._polyline(points, color)
            line(19, 19, 28, 28)
        else:
            for index in range(8):
                angle = index * math.tau / 8
                line(16 + math.cos(angle) * 9, 16 + math.sin(angle) * 9,
                     16 + math.cos(angle) * 14, 16 + math.sin(angle) * 14)
            points = [(x + 16 * unit + math.cos(t * math.tau / 24) * 8 * unit,
                       y + 16 * unit + math.sin(t * math.tau / 24) * 8 * unit) for t in range(25)]
            self._polyline(points, color)

    def _polyline(self, coordinates: list[tuple[float, float]], color: tuple[int, ...]) -> None:
        if len(coordinates) < 2:
            return
        self._color(color)
        points = (sdl2.SDL_Point * len(coordinates))(*(sdl2.SDL_Point(round(x), round(y)) for x, y in coordinates))
        sdl2.SDL_RenderDrawLines(self.renderer, points, len(points))

    def _background(self, now: float, preferences: Preferences) -> None:
        if preferences.high_contrast:
            self._rect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT, (0, 0, 0))
            return
        destination = sdl2.SDL_Rect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT)
        sdl2.SDL_RenderCopy(self.renderer, self._gradient, None, ctypes.byref(destination))
        phase = now * 0.16 if preferences.motion else 0.0
        # Original geometry: six sparse flowing ribbons; no firmware art/shaders.
        for ribbon in range(6):
            points = []
            for index in range(97):
                x = index * LOGICAL_WIDTH / 96
                fraction = x / LOGICAL_WIDTH
                y = 505 + ribbon * 14 + math.sin(fraction * 5.2 + phase + ribbon * 0.23) * (44 + ribbon * 2)
                y += math.sin(fraction * 2.7 - phase * 0.6 + ribbon * 0.4) * 22
                points.append((x, y))
            self._polyline(points, (98, 219, 203, 23 + ribbon * 6))
            self._polyline([(x, y + 1) for x, y in points], (98, 219, 203, 12 + ribbon * 4))

    def _poll_artwork(self) -> None:
        if not self._decoder:
            return
        for image in self._decoder.poll():
            if image.error or not image.pixels:
                continue
            texture = self._texture(Raster(image.width, image.height, image.pixels))
            previous = self._art.pop(image.path, None)
            if previous:
                sdl2.SDL_DestroyTexture(previous[0])
            self._art[image.path] = (texture, image.width, image.height)
            while len(self._art) > self.ART_CACHE_ENTRIES:
                _, removed = self._art.popitem(last=False)
                sdl2.SDL_DestroyTexture(removed[0])

    def _artwork(self, item: UIItem, x: int, y: int, width: int, height: int,
                  preferences: Preferences) -> None:
        if item.artwork and item.artwork not in self._art_requested:
            self._art_requested[item.artwork] = None
            if self._decoder:
                self._decoder.request(item.artwork)
            while len(self._art_requested) > 128:
                self._art_requested.popitem(last=False)
        image = self._art.get(item.artwork)
        if image:
            texture, image_width, image_height = image
            factor = min(width / image_width, height / image_height)
            dw, dh = round(image_width * factor), round(image_height * factor)
            destination = sdl2.SDL_Rect(x + (width - dw) // 2, y + (height - dh) // 2, dw, dh)
            sdl2.SDL_RenderCopy(self.renderer, texture, None, ctypes.byref(destination))
            return
        seed = hashlib.sha256(item.id.encode("utf-8", "replace")).digest()
        accent = (190 + seed[0] % 50, 158 + seed[1] % 60, 100 + seed[2] % 60)
        self._round_rect(x, y, width, height, (21, 42, 62) if not preferences.high_contrast else (18, 18, 18), 12)
        self._circle(x + width * 0.72, y + height * 0.32, 24, accent + (200,))
        for layer in range(5):
            points = [(x + width * index / 32,
                       y + height * (0.58 + layer * 0.06) + math.sin(index / 32 * 5 + layer + seed[3]) * 15)
                      for index in range(33)]
            self._polyline(points, (110, 211, 193, 65 + layer * 27))
        for index in range(7):
            sx = x + 15 + seed[index + 4] % max(1, width - 30)
            sy = y + 13 + seed[index + 11] % max(1, height // 2)
            self._rect(sx, sy, 2, 2, (224, 239, 246, 130))

    @staticmethod
    def _frame_key(snapshot: UISnapshot) -> tuple[Any, ...]:
        return (snapshot.category, snapshot.title, snapshot.items, snapshot.selected,
                snapshot.dialog, snapshot.keyboard, snapshot.preferences, snapshot.status, snapshot.loading)

    def needs_frame(self, snapshot: UISnapshot, now: float) -> bool:
        key = self._frame_key(snapshot)
        return key != self._fingerprint or bool(snapshot.preferences.motion and now - self._last_change < 8)

    def render(self, snapshot: UISnapshot, now: float = 0.0) -> None:
        if self._closed:
            raise RendererError("Renderer has already been closed")
        key = self._frame_key(snapshot)
        if key != self._fingerprint:
            self._last_change = now
            self._fingerprint = key
        wave_time = min(now, self._last_change + 8)
        elapsed = max(0.0, min(0.1, now - self._last_now))
        self._last_now = now
        prefs = snapshot.preferences
        scale = prefs.text_scale
        high = prefs.high_contrast
        primary = (255, 255, 255) if high else (238, 247, 249)
        muted = (207, 207, 207) if high else (147, 173, 188)
        accent = (255, 229, 110) if high else (111, 232, 211)
        panel = (20, 20, 20, 255) if high else (14, 28, 47, 223)
        self._poll_artwork()
        with self._state():
            target = self._external_target if self._external_target is not None else sdl2.SDL_GetRenderTarget(self.renderer) if self._external else self._frame
            self._last_target = target
            sdl2.SDL_SetRenderTarget(self.renderer, target)
            sdl2.SDL_RenderSetLogicalSize(self.renderer, LOGICAL_WIDTH, LOGICAL_HEIGHT)
            sdl2.SDL_RenderSetClipRect(self.renderer, None)
            sdl2.SDL_SetRenderDrawBlendMode(self.renderer, sdl2.SDL_BLENDMODE_BLEND)
            self._background(wave_time, prefs)
            self._label("spruce", 64, 36, 29, primary, 250)
            self._label("PERSONAL INTERFACE", 179, 44, 13, muted, 350)
            badge = "SAMPLE COLLECTION" if snapshot.demo else "YOUR COLLECTION"
            self._label(badge, 984, 45, 13, accent, 232)
            self._line(64, 91, 1216, 91, (151, 185, 194, 36))
            for index, title in enumerate(snapshot.categories):
                x = 64 + index * 292
                selected = index == snapshot.category
                self._icon(title, x + 4, 117, 31, accent if selected else muted)
                self._label(title, x + 51, 121, 20, primary if selected else muted, 217, min(scale, 1.3))
                if selected:
                    self._round_rect(x, 166, 245, 3, accent, 1)
            self._label(snapshot.breadcrumb.upper(), 64, 195, 12, accent, 1100)
            self._label(snapshot.title, 64, 220, 32, primary, 1100, scale)
            list_y, list_height = 291, 301
            self._round_rect(64, list_y, 730, list_height, panel, 16)
            self._round_rect(822, list_y, 394, list_height, panel, 16)
            row_height = max(62, round(58 * scale))
            visible = max(2, int((list_height - 20) // row_height))
            top = max(0, snapshot.selected - visible + 1)
            top = min(top, max(0, len(snapshot.items) - visible))
            if snapshot.items:
                selected_y = list_y + 10 + (snapshot.selected - top) * row_height
                if self._selected_y is None or not prefs.motion or snapshot.category != getattr(self, "_last_category", snapshot.category):
                    self._selected_y = float(selected_y)
                else:
                    self._selected_y += (selected_y - self._selected_y) * (1 - math.exp(-elapsed * 24))
                self._last_category = snapshot.category
                self._round_rect(75, self._selected_y, 708, row_height - 5, accent, 10)
                for row, item in enumerate(snapshot.items[top:top + visible]):
                    index = top + row
                    selected = index == snapshot.selected
                    y = list_y + 10 + row * row_height
                    foreground = (8, 29, 36) if selected else primary
                    secondary = (34, 80, 85) if selected else muted
                    icon = item.kind if item.kind != "menu" else item.id
                    self._icon(icon, 93, y + (row_height - 32) / 2 - 2, 28, foreground)
                    title_size = round(23 * scale)
                    self._label(item.title, 143, y + 6, title_size, foreground, 583)
                    self._label(item.subtitle, 143, y + 9 + title_size, 13, secondary, 584, scale)
                    if item.favorite:
                        self._circle(755, y + row_height / 2 - 3, 3, foreground)
                if snapshot.total > visible:
                    track_height = list_height - 32
                    self._round_rect(786, list_y + 16, 2, track_height, (255, 255, 255, 25), 1)
                    thumb = max(15, track_height * min(1, visible / max(1, snapshot.total)))
                    position = (snapshot.offset + snapshot.selected) / max(1, snapshot.total - 1)
                    self._round_rect(786, list_y + 16 + (track_height - thumb) * position, 2, thumb, accent, 1)
                self._details(snapshot.selected_item, snapshot, primary, muted, accent)
            else:
                self._icon(snapshot.categories[snapshot.category], 112, 326, 42, accent)
                self._paragraph(snapshot.empty_message, 112, 392, 21, primary, 624, 5, min(scale, 1.35))
                self._label("A quieter space", 854, 325, 24, primary, 325, min(scale, 1.3))
                self._paragraph("Your collection stays in its existing folders. Nothing needs to be moved for this interface.",
                                854, 379, 18, muted, 324, 6, min(scale, 1.3))
            if snapshot.status:
                self._label(snapshot.status, 67, 613, 16, accent, 1148)
            elif snapshot.loading:
                self._label("Loading…", 67, 613, 16, accent, 1148)
            else:
                number = snapshot.offset + snapshot.selected + 1 if snapshot.items else 0
                self._label(f"{number:02d} / {snapshot.total:02d}", 67, 613, 14, muted, 300)
                if snapshot.demo:
                    self._label("Original sample titles · No game launches", 819, 613, 14, muted, 397)
            self._line(64, 652, 1216, 652, (151, 185, 194, 36))
            confirm = "South" if prefs.confirm == "south" else "East"
            back = "East" if prefs.confirm == "south" else "South"
            self._label(f"Enter / {confirm}   Open", 66, 675, 15, primary, 320)
            self._label(f"Esc / {back}   Back", 372, 675, 15, muted, 300)
            self._label("X   Find a game", 700, 675, 15, muted, 250)
            self._label("Y   Favorite", 1022, 675, 15, muted, 193)
            if snapshot.dialog:
                self._draw_dialog(snapshot.dialog, prefs, primary, muted, accent)
            if snapshot.keyboard:
                self._draw_keyboard(snapshot, primary, muted, accent)

    def _details(self, item: UIItem | None, snapshot: UISnapshot, primary: tuple[int, ...],
                 muted: tuple[int, ...], accent: tuple[int, ...]) -> None:
        if item is None:
            return
        scale = min(snapshot.preferences.text_scale, 1.35)
        if item.kind in ("game", "system"):
            self._artwork(item, 846, 313, 346, 124, snapshot.preferences)
            caption = item.system_id or ("GAME" if item.kind == "game" else "SYSTEM")
            self._label(caption.upper(), 850, 454, 12, accent, 332)
            height = self._paragraph(item.title, 850, 478, 22, primary, 333, 2, scale)
            if item.kind == "game":
                detail = ("Sample resume card · demonstration" if snapshot.demo else "Verified state available") if item.resume_available else "Normal launch · in-game saves retained"
                if not item.available:
                    detail = "Review required before launch"
                self._label(detail, 850, min(563, 486 + height), 12, muted, 332)
        else:
            self._icon("Tools" if item.kind == "tool" else "Settings" if item.kind == "setting" else item.id,
                       850, 321, 46, accent)
            self._paragraph(item.title, 850, 392, 25, primary, 333, 2, scale)
            description = item.subtitle or "Select an entry to continue."
            if item.id == "all":
                description = "Browse your collection across systems. Game files and saves stay in their existing spruce folders."
            elif item.id == "favorites":
                description = "Keep your favorites inside Games. Add or remove one with the Favorite button."
            elif item.id == "random":
                description = "Choose from available games using the same validated launcher as the rest of your collection."
            elif item.kind == "tool":
                description = "This installed app keeps its own interface. Its launch and return must use the existing spruce contract."
            self._paragraph(description, 850, 468, 17, muted, 332, 4, min(scale, 1.15))

    def _draw_dialog(self, dialog: Dialog, preferences: Preferences, primary: tuple[int, ...],
                      muted: tuple[int, ...], accent: tuple[int, ...]) -> None:
        self._rect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT, (0, 0, 0, 192))
        self._round_rect(270, 137, 740, 458, (18, 33, 50) if not preferences.high_contrast else (8, 8, 8), 20)
        self._round_rect(270, 137, 740, 4, (248, 156, 136) if dialog.error else accent, 2)
        rows = min(4, len(dialog.choices))
        row_height = max(48, round(38 * preferences.text_scale))
        first_y = 571 - rows * (row_height + 8)
        self._label(dialog.title, 307, 173, 29, primary, 666, preferences.text_scale)
        max_lines = max(2, int((first_y - 245) // (18 * preferences.text_scale + 7)))
        body_size = round(18 * preferences.text_scale)
        lines = self.text.wrap(dialog.message, body_size, 662, 128)
        page_count = max(1, math.ceil(len(lines) / max_lines))
        current_page = dialog.message_page % page_count
        first_line = current_page * max_lines
        for index, line in enumerate(lines[first_line:first_line + max_lines]):
            self._label(line, 308, 239 + index * (body_size + 7), 18, muted, 662, preferences.text_scale)
        if page_count > 1:
            self._label(f"X  More text     {current_page + 1} / {page_count}", 305, 609, 15, primary, 670)
        for index, choice in enumerate(dialog.choices[:4]):
            y = first_y + index * (row_height + 8)
            selected = index == dialog.selected
            self._round_rect(305, y, 670, row_height, accent if selected else (255, 255, 255, 10), 9)
            self._label(choice.title, 323, y + 11, 20, (7, 27, 33) if selected else primary, 630, preferences.text_scale)

    def _draw_keyboard(self, snapshot: UISnapshot, primary: tuple[int, ...], muted: tuple[int, ...],
                        accent: tuple[int, ...]) -> None:
        keyboard = snapshot.keyboard
        if keyboard is None:
            return
        self._rect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT, (0, 0, 0, 205))
        self._round_rect(165, 113, 950, 492, (18, 33, 50) if not snapshot.preferences.high_contrast else (0, 0, 0), 20)
        self._label("Find a game", 199, 143, 30, primary, 876)
        self._round_rect(198, 202, 884, 59, (0, 0, 0, 90), 10)
        self._label(keyboard.text or "Type a title, or use the keys below", 216, 219, 23, primary if keyboard.text else muted, 847)
        for index, key in enumerate(keyboard.keys):
            column, row = index % 10, index // 10
            x, y = 198 + column * 89, 288 + row * 63
            selected = index == keyboard.selected
            self._round_rect(x, y, 80, 52, accent if selected else (255, 255, 255, 10), 8)
            label_width = self.text.measure(key, 17 if len(key) > 1 else 22)
            self._label(key, x + max(7, (80 - label_width) / 2), y + 15, 17 if len(key) > 1 else 22,
                        (7, 27, 33) if selected else primary, 67)
        self._label("Enter / Y  Find     Backspace / X  Delete     Esc  Cancel", 201, 558, 15, muted, 876)

    def present(self) -> None:
        if self._external or self._closed:
            return
        with self._state():
            sdl2.SDL_SetRenderTarget(self.renderer, None)
            sdl2.SDL_RenderSetLogicalSize(self.renderer, LOGICAL_WIDTH, LOGICAL_HEIGHT)
            sdl2.SDL_RenderSetClipRect(self.renderer, None)
            sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 255)
            sdl2.SDL_RenderClear(self.renderer)
            sdl2.SDL_RenderCopy(self.renderer, self._frame, None, None)
            sdl2.SDL_RenderPresent(self.renderer)

    def save_screenshot(self, path: str | Path) -> None:
        if self._closed:
            raise RendererError("Renderer has already been closed")
        with self._state():
            sdl2.SDL_SetRenderTarget(self.renderer, self._last_target if self._external else self._frame)
            sdl2.SDL_RenderSetLogicalSize(self.renderer, LOGICAL_WIDTH, LOGICAL_HEIGHT)
            surface = sdl2.SDL_CreateRGBSurfaceWithFormat(0, LOGICAL_WIDTH, LOGICAL_HEIGHT, 32, sdl2.SDL_PIXELFORMAT_RGBA32)
            if not surface:
                raise _error("Create screenshot surface")
            try:
                if sdl2.SDL_RenderReadPixels(self.renderer, None, sdl2.SDL_PIXELFORMAT_RGBA32,
                                            surface.contents.pixels, surface.contents.pitch) != 0:
                    raise _error("Read screenshot pixels")
                # One explicit output operation; no screenshot path is read.
                suffix = Path(path).suffix.lower()
                if suffix == ".bmp":
                    if sdl2.SDL_SaveBMP(surface, str(path).encode()) != 0:
                        raise _error("Write screenshot")
                else:
                    try:
                        from PIL import Image
                    except ImportError:
                        from sdl2 import sdlimage
                        if sdlimage.IMG_SavePNG(surface, str(path).encode()) != 0:
                            raise _error("Write PNG screenshot")
                    else:
                        pixels = ctypes.string_at(surface.contents.pixels, surface.contents.pitch * LOGICAL_HEIGHT)
                        image = Image.frombytes("RGBA", (LOGICAL_WIDTH, LOGICAL_HEIGHT), pixels, "raw", "RGBA", surface.contents.pitch)
                        image.save(path, format="PNG")
            finally:
                sdl2.SDL_FreeSurface(surface)

    screenshot = save_screenshot

    def feedback(self, enabled: bool = True) -> None:
        """Optional original click tone for standalone previews only.

        Embedded views retain PyUI's existing audio owner and never open another
        audio device. Audio failure is silent and cannot block navigation.
        """
        if self._external or not enabled or self._closed:
            return
        if not self._audio_device:
            if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) != 0:
                return
            desired = sdl2.SDL_AudioSpec(22050, sdl2.AUDIO_S16SYS, 1, 256)
            obtained = sdl2.SDL_AudioSpec(0, 0, 0, 0)
            self._audio_device = sdl2.SDL_OpenAudioDevice(None, 0, ctypes.byref(desired), ctypes.byref(obtained), 0)
            if not self._audio_device:
                return
            samples = (ctypes.c_int16 * 441)()
            for index in range(441):
                envelope = (1 - index / 441) ** 2
                samples[index] = round(math.sin(index * math.tau * 760 / 22050) * 1100 * envelope)
            self._click_buffer = samples
            sdl2.SDL_PauseAudioDevice(self._audio_device, 0)
        if sdl2.SDL_GetQueuedAudioSize(self._audio_device) < 2205:
            sdl2.SDL_QueueAudio(self._audio_device, self._click_buffer, ctypes.sizeof(self._click_buffer))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._decoder:
            self._decoder.close()
            self._decoder = None
        if self._audio_device:
            sdl2.SDL_ClearQueuedAudio(self._audio_device)
            sdl2.SDL_CloseAudioDevice(self._audio_device)
            self._audio_device = 0
        for texture, *_ in self._text_cache.values():
            sdl2.SDL_DestroyTexture(texture)
        self._text_cache.clear()
        for texture, *_ in self._art.values():
            sdl2.SDL_DestroyTexture(texture)
        self._art.clear()
        if self._gradient:
            sdl2.SDL_DestroyTexture(self._gradient)
            self._gradient = None
        if self._frame:
            sdl2.SDL_DestroyTexture(self._frame)
            self._frame = None
        if self._owns_resources:
            if self.renderer:
                sdl2.SDL_DestroyRenderer(self.renderer)
                self.renderer = None
            if self.window:
                sdl2.SDL_DestroyWindow(self.window)
                self.window = None
            sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_EVENTS | sdl2.SDL_INIT_AUDIO)

    def __enter__(self) -> "Renderer":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
