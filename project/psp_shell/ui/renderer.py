"""Original SDL2 interface renderer with a software backend and PyUI embedding.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
import ctypes
import math
from pathlib import Path
from typing import Any, Iterator

import sdl2

from .artwork import ArtworkDecoder, SDLArtworkDecoder
from .keyboard import keyboard_hints, keyboard_layout
from .model import Dialog, Preferences, UIItem, UISnapshot
from .pictograms import ALIASES, DRAWINGS
from .motion import StepGlide
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
    ART_CACHE_ENTRIES = 6

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
        self._icons: dict[str, Any] = {}
        self._decoder = None
        self._text_cache: OrderedDict[tuple[Any, ...], tuple[Any, int, int, int]] = OrderedDict()
        self._text_bytes = 0
        self._art: OrderedDict[str, tuple[Any, int, int]] = OrderedDict()
        self._art_requested: OrderedDict[str, None] = OrderedDict()
        self._art_retry: OrderedDict[str, None] = OrderedDict()
        self._art_failed: OrderedDict[str, None] = OrderedDict()
        self._art_generation = 0
        self._art_dirty = False
        self._last_selected_art = ""
        self._fingerprint = None
        self._last_change = 0.0
        self._last_now = 0.0
        self._category_glide = StepGlide()
        self._item_glide = StepGlide()
        self._category_target = 0.0
        self._closed = False
        self._audio_device = 0
        self._click_buffer = None
        self._last_target = None
        version = sdl2.SDL_version()
        sdl2.SDL_GetVersion(ctypes.byref(version))
        self._sdl_version = (version.major, version.minor, version.patch)
        self._geometry_supported = self._sdl_version >= (2, 0, 18) and hasattr(sdl2, "SDL_RenderGeometry")
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
        if self._sdl_version >= (2, 0, 12) and hasattr(sdl2, "SDL_SetTextureScaleMode"):
            sdl2.SDL_SetTextureScaleMode(texture, sdl2.SDL_ScaleModeLinear)
        return texture

    def _make_gradient(self) -> Any:
        # A small, smoothly sampled original colour field. Upload once; no
        # full-screen Python pixel generation or file reads in a render tick.
        width, height = 160, 90
        pixels = bytearray()
        for y in range(height):
            vertical = (y / (height - 1)) ** 1.45
            for x in range(width):
                horizontal = x / (width - 1)
                top = (2 + 4 * horizontal, 2 + 84 * horizontal, 75 + 109 * horizontal)
                bottom = (78 - 26 * horizontal, 226 + 26 * horizontal, 247 + 8 * horizontal)
                pixels.extend(bytes(round(a + (b - a) * vertical) for a, b in zip(top, bottom)) + b"\xff")
        return self._texture(Raster(width, height, bytes(pixels)))

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
        # Cache glyph coverage independently of tint, as PPSSPP's TextDrawer
        # does. Shadow, focus and dimming then reuse the same bounded texture.
        key = (str(text)[:2048], pixels, int(max_width))
        cached = self._text_cache.get(key)
        if cached is None:
            raster = self.text.raster(key[0], pixels, (255, 255, 255, 255), max(1, int(max_width)))
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
        sdl2.SDL_SetTextureColorMod(texture, *rgba[:3])
        sdl2.SDL_SetTextureAlphaMod(texture, rgba[3])
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

    def _polygon(self, points: list[tuple[float, float]], color: tuple[int, ...]) -> None:
        """Small convex/concave pictogram fills, supported by every SDL backend."""
        if len(points) < 3:
            return
        for y in range(math.floor(min(p[1] for p in points)), math.ceil(max(p[1] for p in points))):
            crossings = []
            scan = y + .5
            for index, (ax, ay) in enumerate(points):
                bx, by = points[(index + 1) % len(points)]
                if (ay <= scan < by) or (by <= scan < ay):
                    crossings.append(ax + (scan - ay) * (bx - ax) / (by - ay))
            crossings.sort()
            for left, right in zip(crossings[::2], crossings[1::2]):
                self._rect(left, y, max(1, right - left), 1, color)

    def _icon_texture(self, kind: str) -> Any:
        kind = ALIASES.get(kind, kind)
        if kind not in DRAWINGS:
            kind = "settings"
        if kind in self._icons:
            return self._icons[kind]
        # Oversample project-drawn geometry, then use SDL's linear sampler.
        # This path needs neither Pillow nor additional embedded dependencies.
        texture = sdl2.SDL_CreateTexture(self.renderer, sdl2.SDL_PIXELFORMAT_RGBA8888,
                                        sdl2.SDL_TEXTUREACCESS_TARGET, 192, 192)
        if not texture:
            raise _error("Create pictogram")
        try:
            with self._state():
                sdl2.SDL_SetRenderTarget(self.renderer, texture)
                sdl2.SDL_RenderSetLogicalSize(self.renderer, 192, 192)
                sdl2.SDL_RenderSetViewport(self.renderer, None)
                sdl2.SDL_RenderSetClipRect(self.renderer, None)
                sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 0)
                sdl2.SDL_RenderClear(self.renderer)
                sdl2.SDL_SetRenderDrawBlendMode(self.renderer, sdl2.SDL_BLENDMODE_BLEND)
                for operation, data in DRAWINGS[kind]:
                    shade = operation.startswith("shade_")
                    operation = operation.removeprefix("shade_")
                    color = (126, 150, 170, 255) if shade else (255, 255, 255, 255)
                    if operation == "polygon":
                        self._polygon([(a * 3, b * 3) for a, b in data], color)
                    elif operation == "rect":
                        self._rect(*(value * 3 for value in data), color)
                    elif operation == "circle":
                        self._circle(data[0] * 3, data[1] * 3, round(data[2] * 3), color)
                    elif operation in ("ring", "arc"):
                        cx, cy, radius = data[:3]
                        if operation == "ring":
                            self._circle(cx * 3, cy * 3, round(radius * 3), color)
                            sdl2.SDL_SetRenderDrawBlendMode(self.renderer, sdl2.SDL_BLENDMODE_NONE)
                            self._circle(cx * 3, cy * 3, round((radius - data[3]) * 3), (0, 0, 0, 0))
                            sdl2.SDL_SetRenderDrawBlendMode(self.renderer, sdl2.SDL_BLENDMODE_BLEND)
                        else:
                            points = [(3 * (cx + math.cos(math.pi * (data[3] + (data[4] - data[3]) * i / 64)) * radius),
                                       3 * (cy + math.sin(math.pi * (data[3] + (data[4] - data[3]) * i / 64)) * radius)) for i in range(65)]
                            for x, y in points:
                                self._circle(x, y, 4, color)
                    elif operation == "path":
                        points = [(a * 3, b * 3) for a, b in data]
                        for (ax, ay), (bx, by) in zip(points, points[1:]):
                            distance = max(1, math.hypot(bx - ax, by - ay))
                            dx, dy = -(by - ay) * 4 / distance, (bx - ax) * 4 / distance
                            self._polygon([(ax + dx, ay + dy), (bx + dx, by + dy),
                                           (bx - dx, by - dy), (ax - dx, ay - dy)], color)
                        for x, y in points:
                            self._circle(x, y, 4, color)
            sdl2.SDL_SetTextureBlendMode(texture, sdl2.SDL_BLENDMODE_BLEND)
            if self._sdl_version >= (2, 0, 12) and hasattr(sdl2, "SDL_SetTextureScaleMode"):
                sdl2.SDL_SetTextureScaleMode(texture, sdl2.SDL_ScaleModeLinear)
            self._icons[kind] = texture
            return texture
        except BaseException:
            sdl2.SDL_DestroyTexture(texture)
            raise

    def _icon(self, kind: str, x: float, y: float, size: int, color: tuple[int, ...]) -> None:
        texture = self._icon_texture(kind)
        alpha = color[3] if len(color) == 4 else 255
        destination = sdl2.SDL_Rect(round(x + 1), round(y + 2), size, size)
        sdl2.SDL_SetTextureColorMod(texture, 0, 16, 48)
        sdl2.SDL_SetTextureAlphaMod(texture, round(alpha * .25))
        sdl2.SDL_RenderCopy(self.renderer, texture, None, ctypes.byref(destination))
        destination.x, destination.y = round(x), round(y)
        sdl2.SDL_SetTextureColorMod(texture, *color[:3])
        sdl2.SDL_SetTextureAlphaMod(texture, alpha)
        sdl2.SDL_RenderCopy(self.renderer, texture, None, ctypes.byref(destination))

    def _text(self, text: str, x: float, y: float, size: int, color: tuple[int, ...], width: int,
              scale: float = 1.0) -> tuple[int, int]:
        alpha = color[3] if len(color) == 4 else 255
        self._label(text, x + 1, y + 2, size, (0, 12, 44, round(alpha * .65)), width, scale)
        return self._label(text, x, y, size, color, width, scale)

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
        phase = now * .18 if preferences.motion else 0.0
        # Two broad translucent folds, with a soft edge and continuous fill.
        # Original geometry, independently drawn against official PSP references.
        for ribbon in range(2):
            points = []
            for index in range(129):
                fraction = index / 128
                x = fraction * LOGICAL_WIDTH
                center = .80 + .035 * math.sin(phase * .7 + ribbon)
                y = 542 + ribbon * 52 - (190 + ribbon * 8) * math.exp(-((fraction - center) / .53) ** 2)
                y += math.sin(fraction * 5.4 + phase + ribbon * .9) * 15
                points.append((x, y))
            if self._geometry_supported:
                vertices = []
                indices = []
                for index, (x, y) in enumerate(points):
                    vertices.extend((sdl2.SDL_Vertex(sdl2.SDL_FPoint(x, y),
                                     sdl2.SDL_Color(108, 221, 255, 48 - ribbon * 10), sdl2.SDL_FPoint()),
                                     sdl2.SDL_Vertex(sdl2.SDL_FPoint(x, LOGICAL_HEIGHT),
                                     sdl2.SDL_Color(80, 253, 255, 64 - ribbon * 14), sdl2.SDL_FPoint())))
                    if index:
                        k = index * 2
                        indices.extend((k - 2, k - 1, k, k, k - 1, k + 1))
                raw_vertices = (sdl2.SDL_Vertex * len(vertices))(*vertices)
                raw_indices = (ctypes.c_int * len(indices))(*indices)
                if sdl2.SDL_RenderGeometry(self.renderer, None, raw_vertices, len(vertices), raw_indices, len(indices)) != 0:
                    # Some older renderer drivers reject geometry even with a
                    # recent SDL library. Decorative waves must stay optional.
                    self._geometry_supported = False
            if not self._geometry_supported:
                for x, y in points:
                    self._rect(x, y, 11, LOGICAL_HEIGHT - y, (94, 220, 251, 38))
            self._polyline(points, (176, 236, 255, 35 - ribbon * 10))
            self._polyline([(x, y + 2) for x, y in points], (176, 236, 255, 13))

    def _poll_artwork(self, snapshot: UISnapshot | None = None) -> bool:
        if not self._decoder:
            return False
        changed = False
        if snapshot is not None:
            if snapshot.artwork_generation != self._art_generation:
                # Refresh is an explicit library revision boundary. Discard
                # both successful and negative entries without touching the
                # filesystem on the renderer thread. Old worker completions
                # carry their original generation and cannot restore stale art.
                for texture, _, _ in self._art.values():
                    sdl2.SDL_DestroyTexture(texture)
                self._art.clear()
                self._art_requested.clear()
                self._art_retry.clear()
                self._art_failed.clear()
                self._art_generation = snapshot.artwork_generation
                self._art_dirty = True
                changed = True
            selected = snapshot.selected_item
            self._last_selected_art = selected.artwork if selected is not None and selected.kind == "game" else ""
            path = self._last_selected_art
            if path and path not in self._art and path not in self._art_failed:
                self._art_retry[path] = None
                while len(self._art_retry) > self.ART_CACHE_ENTRIES * 2:
                    self._art_retry.popitem(last=False)
        for image in self._decoder.poll():
            if image.generation != self._art_generation:
                continue
            self._art_requested.pop(image.path, None)
            if image.error or not image.pixels:
                self._art_retry.pop(image.path, None)
                self._art_failed[image.path] = None
                while len(self._art_failed) > 128:
                    self._art_failed.popitem(last=False)
                continue
            texture = self._texture(Raster(image.width, image.height, image.pixels))
            previous = self._art.pop(image.path, None)
            if previous:
                sdl2.SDL_DestroyTexture(previous[0])
            self._art[image.path] = (texture, image.width, image.height)
            changed = True
            self._art_dirty = True
            while len(self._art) > self.ART_CACHE_ENTRIES:
                # Late neighboring results must not evict the focused cover.
                oldest = next(path for path in self._art if path != self._last_selected_art)
                removed = self._art.pop(oldest)
                sdl2.SDL_DestroyTexture(removed[0])
        # The focused row is drawn last, so submit it here before neighbors.
        # Rejected admissions remain bounded and are retried without file I/O.
        paths = list(self._art_retry)
        if self._last_selected_art in self._art_retry:
            paths.remove(self._last_selected_art)
            paths.insert(0, self._last_selected_art)
        for path in paths:
            if path in self._art or path in self._art_failed or path in self._art_requested:
                self._art_retry.pop(path, None)
            elif self._decoder.request(path, generation=self._art_generation):
                self._art_requested[path] = None
                self._art_retry.pop(path, None)
            else:
                break
        return changed

    def _artwork(self, item: UIItem, x: int, y: int, width: int, height: int,
                  preferences: Preferences) -> None:
        image = self._art.get(item.artwork)
        if image:
            self._art.move_to_end(item.artwork)
            # EmuCoreA's flat-cover treatment: retain the real aspect ratio and
            # transparent surround, without a fabricated box or drop shadow.
            texture, image_width, image_height = image
            factor = min(width / image_width, height / image_height)
            dw, dh = round(image_width * factor), round(image_height * factor)
            destination = sdl2.SDL_Rect(x + (width - dw) // 2, y + (height - dh) // 2, dw, dh)
            sdl2.SDL_RenderCopy(self.renderer, texture, None, ctypes.byref(destination))
            return
        if item.artwork and item.artwork not in self._art_requested and item.artwork not in self._art_failed:
            if self._decoder and self._decoder.request(item.artwork, generation=self._art_generation):
                self._art_requested[item.artwork] = None
                self._art_retry.pop(item.artwork, None)
            else:
                self._art_retry[item.artwork] = None
                self._art_retry.move_to_end(item.artwork)
                while len(self._art_retry) > self.ART_CACHE_ENTRIES * 2:
                    self._art_retry.popitem(last=False)
        # A quiet original placeholder is visibly a missing cover, not invented
        # game artwork. Text stays alongside the icon in the normal list.
        color = (255, 255, 255, 34) if not preferences.high_contrast else (255, 255, 255, 46)
        self._rect(x, y, width, height, color)
        self._line(x, y, x + width, y, (255, 255, 255, 105))
        self._line(x, y + height, x + width, y + height, (255, 255, 255, 58))
        size = min(height - 8, width - 8)
        self._icon("game", x + (width - size) / 2, y + (height - size) / 2, size, (255, 255, 255, 225))

    @staticmethod
    def _frame_key(snapshot: UISnapshot) -> tuple[Any, ...]:
        return (snapshot,)

    def needs_frame(self, snapshot: UISnapshot, now: float) -> bool:
        self._poll_artwork(snapshot)
        key = self._frame_key(snapshot)
        return self._art_dirty or key != self._fingerprint or bool(snapshot.preferences.motion and now - self._last_change < 8)

    def _crossbar(self, snapshot: UISnapshot, now: float) -> None:
        # Fixed filmstrip arithmetic and the .58 inactive treatment follow
        # PlayFieldPortal XMBCategoryBar.kt (5ee271e); see visual-design notes.
        count = len(snapshot.categories)
        change = (snapshot.category - self._category_target + count / 2) % count - count / 2
        self._category_target += change
        position = self._category_glide.position(self._category_target, now, "categories", snapshot.preferences.motion)
        anchor, spacing, center_y = 292, 224, 186
        for index, title in enumerate(snapshot.categories):
            delta = (index - position + 1.4) % count - 1.4
            center_x = anchor + delta * spacing
            selected = index == snapshot.category
            proximity = max(0.0, 1 - abs(delta))
            size = round(128 + proximity * 16)
            alpha = 255 if selected or snapshot.preferences.high_contrast else 148
            self._icon(title, center_x - size / 2, center_y - size / 2, size, (255, 255, 255, alpha))
            if selected:
                size_text = 23
                scale = min(snapshot.preferences.text_scale, 1.25)
                width = min(270, self.text.measure(title, round(size_text * scale)))
                self._text(title, center_x - width / 2, 243, size_text, (255, 255, 255), 270, scale)

    @staticmethod
    def _row_y(distance: float, gap: float) -> float:
        # The selected row breathes below the category icon. Its nearest
        # neighbors sit above/below it; farther rows have a compact stride.
        if distance < 0:
            return 368 + distance * gap
        if distance < 1:
            return 368 + distance * (gap + 80)
        return 448 + distance * gap

    @staticmethod
    def _item_icon(item: UIItem) -> str:
        if item.kind in ("menu", "setting", "experience_profile", "hardware_control", "hardware_route"):
            return item.id
        if item.kind == "system":
            return "system" if item.system_id in ("PSP", "GBA") else "folder"
        return item.kind

    def _items(self, snapshot: UISnapshot, now: float, primary: tuple[int, ...], muted: tuple[int, ...]) -> None:
        prefs = snapshot.preferences
        scale = prefs.text_scale
        # A replaced page/column is new geometry. Carrying the prior row index
        # through pagination or a reordered result set makes it glide backward.
        identity = (snapshot.category, snapshot.title, snapshot.breadcrumb,
                    snapshot.offset, tuple(item.id for item in snapshot.items))
        position = self._item_glide.position(snapshot.selected, now, identity, prefs.motion)
        gap = max(74, round(70 * min(scale, 1.65)))
        clip = sdl2.SDL_Rect(172, 280, 1035, 348)
        sdl2.SDL_RenderSetClipRect(self.renderer, ctypes.byref(clip))
        try:
            # Farther rows first; the selected row is drawn last and stays clear
            # throughout short transitions and fast held-button repeats.
            indices = sorted(range(len(snapshot.items)), key=lambda i: -abs(i - position))
            for index in indices:
                item = snapshot.items[index]
                distance = index - position
                y = self._row_y(distance, gap)
                if y < 270 or y > 637:
                    continue
                selected = index == snapshot.selected
                emphasis = max(0.0, 1.0 - abs(distance))
                alpha = 255 if selected or prefs.high_contrast else max(124, round(218 - abs(distance) * 12))
                color = primary if selected else (*primary[:3], alpha)
                # Scale makes focus readable without an opaque tile or bar.
                if item.kind == "game":
                    width, height = round(90 + 70 * emphasis), round(51 + 39 * emphasis)
                    self._artwork(item, round(292 - width / 2), round(y - height / 2), width, height, prefs)
                else:
                    size = round(60 + 60 * emphasis)
                    self._icon(self._item_icon(item), 292 - size / 2, y - size / 2, size, color)
                title_size = 31 if selected else 22
                title_scale = scale if selected else min(scale, 1.35)
                title_y = y - (24 if selected else 10)
                title_width, _ = self._text(item.title, 391, title_y, title_size, color,
                                            740 if item.favorite else 780, title_scale)
                if selected:
                    subtitle = item.subtitle
                    if item.kind == "game":
                        subtitle = (item.system_id + "   /   " + subtitle).strip(" / ")
                    if subtitle:
                        self._text(subtitle, 393, y + max(23, round(20 * scale)), 17, muted, 763, min(scale, 1.35))
                    if item.favorite:
                        self._icon("favorites", 405 + title_width, title_y + 2, 22, primary)
            if position > .05:
                self._polyline([(286, 283), (292, 279), (298, 283)], (*primary[:3], 130))
            if self._row_y(len(snapshot.items) - 1 - position, gap) > 620:
                self._polyline([(286, 622), (292, 626), (298, 622)], (*primary[:3], 130))
        finally:
            sdl2.SDL_RenderSetClipRect(self.renderer, None)

    def _button(self, position: str, x: float, y: float, color: tuple[int, ...]) -> None:
        # Physical positions match the existing input policy. The small diamond
        # makes South/East legible without pretending TrimUI has Sony buttons.
        for key, dx, dy in (("north", 0, -6), ("east", 6, 0), ("south", 0, 6), ("west", -6, 0)):
            self._circle(x + dx, y + dy, 3, color if position == key else (*color[:3], 52))

    def _footer(self, snapshot: UISnapshot, primary: tuple[int, ...], muted: tuple[int, ...]) -> None:
        prefs = snapshot.preferences
        confirm = prefs.confirm
        back = "east" if confirm == "south" else "south"
        self._button(confirm, 268, 681, primary)
        self._text("Enter", 287, 674, 15, primary, 100)
        self._button(back, 402, 681, primary)
        self._text("Back", 421, 674, 15, primary, 100)
        self._button("west", 531, 681, muted)
        self._text("Search", 550, 674, 15, muted, 110)
        if snapshot.selected_item and snapshot.selected_item.kind == "game":
            self._button("north", 680, 681, muted)
            self._text("Favorite", 699, 674, 15, muted, 140)
        if snapshot.category in (0, 1):
            self._text("Start  Filters", 866, 674, 15, muted, 180)
        number = snapshot.offset + snapshot.selected + 1 if snapshot.items else 0
        text = f"{number} / {snapshot.total}"
        self._text(text, 1157 - self.text.measure(text, 14), 675, 14, muted, 110)
        if snapshot.demo:
            self._text("Desktop preview", 54, 677, 12, (*muted[:3], 160), 170)

    def render(self, snapshot: UISnapshot, now: float = 0.0) -> None:
        if self._closed:
            raise RendererError("Renderer has already been closed")
        key = self._frame_key(snapshot)
        if key != self._fingerprint:
            self._last_change = now
            self._fingerprint = key
        wave_time = min(now, self._last_change + 8)
        self._last_now = now
        prefs = snapshot.preferences
        primary = (255, 255, 255)
        muted = (222, 238, 251) if not prefs.high_contrast else (235, 235, 235)
        accent = (255, 255, 255)
        self._poll_artwork(snapshot)
        self._art_dirty = False
        with self._state():
            target = self._external_target if self._external_target is not None else sdl2.SDL_GetRenderTarget(self.renderer) if self._external else self._frame
            self._last_target = target
            sdl2.SDL_SetRenderTarget(self.renderer, target)
            sdl2.SDL_RenderSetLogicalSize(self.renderer, LOGICAL_WIDTH, LOGICAL_HEIGHT)
            sdl2.SDL_RenderSetClipRect(self.renderer, None)
            sdl2.SDL_SetRenderDrawBlendMode(self.renderer, sdl2.SDL_BLENDMODE_BLEND)
            self._background(wave_time, prefs)
            if snapshot.display_clock:
                width = self.text.measure(snapshot.display_clock, 19)
                self._text(snapshot.display_clock, 1212 - width, 41, 19, primary, 300)
            self._crossbar(snapshot, now)
            # A small location cue for drilled-in lists, absent on root pages.
            root_titles = ("Your games", "Pick up where you left off", "Tools", "Settings")
            if snapshot.title not in root_titles and snapshot.breadcrumb != snapshot.categories[snapshot.category]:
                self._text(snapshot.breadcrumb.replace(" / ", "  ›  "), 392, 253, 14, (*muted[:3], 190), 786)
            if snapshot.items:
                self._items(snapshot, now, primary, muted)
            else:
                self._icon(snapshot.categories[snapshot.category], 257, 333, 70, primary)
                self._paragraph(snapshot.empty_message, 391, 345, 23, primary, 680, 5, min(prefs.text_scale, 1.35))
            if snapshot.status or snapshot.loading:
                self._text(snapshot.status or "Loading…", 391, 633, 15, primary, 780)
            self._footer(snapshot, primary, muted)
            if snapshot.dialog:
                self._draw_dialog(snapshot.dialog, prefs, primary, muted, accent)
            if snapshot.keyboard:
                self._draw_keyboard(snapshot, primary, muted, accent)

    def _draw_dialog(self, dialog: Dialog, preferences: Preferences, primary: tuple[int, ...],
                      muted: tuple[int, ...], accent: tuple[int, ...]) -> None:
        scale = preferences.text_scale
        expanded = scale > 1.2
        left = 288 if expanded else 610
        content_x = left + 58
        width = LOGICAL_WIDTH - content_x - 66
        # Console-style options sheet. The underlying selection stays visible;
        # flat translucent layers replace the old rounded modal/card stack.
        self._rect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT, (0, 6, 27, 62))
        for index in range(20):
            self._rect(left - 60 + index * 3, 0, 3, LOGICAL_HEIGHT, (3, 23, 63, round(index * 9.5)))
        self._rect(left, 0, LOGICAL_WIDTH - left, LOGICAL_HEIGHT,
                   (2, 20, 54, 242) if preferences.high_contrast else (3, 26, 65, 222))
        self._line(left, 0, left, LOGICAL_HEIGHT, (230, 245, 255, 40))
        if dialog.system_id or dialog.artwork:
            art_width = 180 if expanded else 270
            art_x = max(24, (left - art_width) // 2)
            self._rect(0, 0, left, LOGICAL_HEIGHT, (3, 26, 65, 255))
            self._artwork(UIItem("dialog-art", "", system_id=dialog.system_id, artwork=dialog.artwork),
                          art_x, 250, art_width, round(art_width * 0.67), preferences)
            self._text("PS1" if dialog.system_id in ("PS", "PS1", "PSX") else dialog.system_id,
                       art_x, 268 + round(art_width * 0.67), 17, primary, art_width)
        rows = min(4, len(dialog.choices))
        row_height = max(48, round(38 * scale))
        bottom = 626
        first_y = bottom - rows * (row_height + 8)
        top = 61 if expanded else 92
        # Like PFP's measured context-menu header, reserve space for two title
        # lines before the divider. Longer names stay available in paged text.
        title_pixels = round(28 * scale)
        title_lines = self.text.wrap(dialog.title, title_pixels, width, 2)
        for index, line in enumerate(title_lines):
            self._label(line, content_x, top + index * (title_pixels + 7), 28, primary, width, scale)
        title_height = max(1, len(title_lines)) * (title_pixels + 7)
        divider_y = top + title_height + 20
        self._line(content_x, divider_y, 1214, divider_y,
                   (244, 181, 165, 140) if dialog.error else (255, 255, 255, 60))
        body_y = divider_y + 24
        body_size = round(18 * scale)
        max_lines = max(1, int((first_y - 22 - body_y) // (body_size + 7)))
        message = dialog.message
        if len(self.text.wrap(dialog.title, title_pixels, width, 128)) > 2:
            message = dialog.title + "\n\n" + message
        lines = self.text.wrap(message, body_size, width, 128)
        page_count = max(1, math.ceil(len(lines) / max_lines))
        page = dialog.message_page % page_count
        for index, line in enumerate(lines[page * max_lines:(page + 1) * max_lines]):
            self._label(line, content_x, body_y + index * (body_size + 7), 18, muted, width, scale)
        choice_offset = max(0, min(dialog.selected - rows + 1, len(dialog.choices) - rows))
        for visible_index, choice in enumerate(dialog.choices[choice_offset:choice_offset + rows]):
            index = choice_offset + visible_index
            y = first_y + visible_index * (row_height + 8)
            selected = index == dialog.selected
            if selected:
                self._rect(content_x - 18, y - 1, width + 30, row_height + 2, (255, 255, 255, 18))
                self._line(content_x - 18, y - 1, 1226, y - 1, (255, 255, 255, 105))
                self._line(content_x - 18, y + row_height, 1226, y + row_height, (255, 255, 255, 105))
                self._polygon([(content_x - 34, y + row_height / 2 - 5),
                               (content_x - 28, y + row_height / 2),
                               (content_x - 34, y + row_height / 2 + 5)], primary)
            self._label(choice.title, content_x, y + 12, 21, primary if selected else (*muted[:3], 180), width, scale)
        if page_count > 1:
            self._label(f"X  More text     {page + 1} / {page_count}", content_x, 646, 15, primary, width)
        elif len(dialog.choices) > rows:
            self._label(f"Options {choice_offset + 1}–{choice_offset + rows} / {len(dialog.choices)} · Up / Down", content_x, 646, 15, primary, width)
        self._button(preferences.confirm, content_x + 4, 686, primary)
        self._label("Enter", content_x + 23, 679, 15, primary, 100)
        self._button("east" if preferences.confirm == "south" else "south", content_x + 143, 686, primary)
        self._label("Back", content_x + 162, 679, 15, primary, 100)

    def _draw_keyboard(self, snapshot: UISnapshot, primary: tuple[int, ...], muted: tuple[int, ...],
                        accent: tuple[int, ...]) -> None:
        keyboard = snapshot.keyboard
        if keyboard is None:
            return
        # Give text entry its own clean workspace. Translucent keys should show
        # only the wave field, never a second title or icon behind their labels.
        self._background(min(self._last_now, self._last_change + 8), snapshot.preferences)
        self._rect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT, (1, 14, 48, 105))
        if snapshot.display_clock:
            width = self.text.measure(snapshot.display_clock, 19)
            self._text(snapshot.display_clock, 1212 - width, 41, 19, primary, 300)
        layout = keyboard_layout(snapshot.preferences.text_scale, keyboard.keys)
        x, y, size = layout.title
        self._text("Find a game", x, y, size, primary, 1032)
        x, y, width, height = layout.field
        self._rect(x, y, width, height, (255, 255, 255, 12))
        self._line(x, y + height, x + width, y + height, (255, 255, 255, 165))
        x, y, size, width = layout.text
        value = keyboard.text
        # Text entry appends at the end. Keep the newly typed suffix and caret
        # visible even when a long query no longer fits the input field.
        if value and self.text.measure(value, size) > width - 14:
            low, high = 0, len(value)
            while low < high:
                middle = (low + high) // 2
                if self.text.measure("…" + value[middle:], size) > width - 14:
                    low = middle + 1
                else:
                    high = middle
            value = "…" + value[low:]
        self._text(value or "Type a title", x, y, size, primary if value else muted, width)
        caret_x = x + self.text.measure(value, size) + 4 if value else x
        self._line(caret_x, y, caret_x, y + size, primary)
        for cell in layout.cells:
            selected = cell.index == keyboard.selected
            self._rect(cell.x, cell.y, cell.width, cell.height,
                       (255, 255, 255, 235) if selected else (255, 255, 255, 12))
            if not selected:
                self._line(cell.x, cell.y + cell.height - 1,
                           cell.x + cell.width, cell.y + cell.height - 1, (255, 255, 255, 40))
            label_width = self.text.measure(cell.key, cell.font_size)
            self._label(cell.key, cell.x + max(6, (cell.width - label_width) / 2),
                        cell.y + (cell.height - cell.font_size) / 2, cell.font_size,
                        (5, 39, 86) if selected else primary, cell.width - 12)
        for hint, (x, y) in zip(keyboard_hints(snapshot.preferences.confirm), layout.hint_positions):
            self._button(hint.position, x - 20, y + layout.hint_font_size / 2, primary)
            self._text(hint.title, x, y, layout.hint_font_size, muted, 450)

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
        for texture in self._icons.values():
            sdl2.SDL_DestroyTexture(texture)
        self._icons.clear()
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
