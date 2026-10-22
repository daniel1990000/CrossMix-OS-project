"""Bounded Pillow text rasterization from a font held entirely in memory.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import io
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    pixels: bytes


class TextRasterizer:
    MAX_FONT_BYTES = 16 * 1024 * 1024
    MAX_TEXT_CHARS = 2048

    def __init__(self, font_path: str | Path):
        # Pillow is a host-preview dependency, not an import-time target dependency.
        from PIL import Image, ImageDraw, ImageFont
        self._image, self._draw, self._imagefont = Image, ImageDraw, ImageFont
        # Startup only. Lazy font-size instances read BytesIO, never this path.
        with open(font_path, "rb") as source:
            self._font_bytes = source.read(self.MAX_FONT_BYTES + 1)
        if not self._font_bytes or len(self._font_bytes) > self.MAX_FONT_BYTES:
            raise ValueError("The interface font is missing or exceeds its size limit")
        self._fonts: OrderedDict[int, Any] = OrderedDict()
        self._measure_cache: OrderedDict[tuple[str, int], float] = OrderedDict()
        self._wrap_cache: OrderedDict[tuple[Any, ...], tuple[str, ...]] = OrderedDict()
        self.font(24)  # Validate before the first frame.

    def font(self, size: int) -> Any:
        size = max(10, min(92, int(size)))
        if size in self._fonts:
            self._fonts.move_to_end(size)
            return self._fonts[size]
        font = self._imagefont.truetype(io.BytesIO(self._font_bytes), size=size)
        self._fonts[size] = font
        while len(self._fonts) > 16:
            self._fonts.popitem(last=False)
        return font

    def measure(self, text: str, size: int) -> float:
        value = str(text)[:self.MAX_TEXT_CHARS].replace("\n", " ")
        key = (value, size)
        if key not in self._measure_cache:
            self._measure_cache[key] = float(self.font(size).getlength(value))
            if len(self._measure_cache) > 512:
                self._measure_cache.popitem(last=False)
        else:
            self._measure_cache.move_to_end(key)
        return self._measure_cache[key]

    def fit(self, text: str, size: int, max_width: int) -> str:
        text = str(text)[:self.MAX_TEXT_CHARS].replace("\n", " ")
        max_width = max(0, max_width)
        if self.measure(text, size) <= max_width:
            return text
        ellipsis = "…"
        if self.measure(ellipsis, size) > max_width:
            return ""
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self.measure(text[:middle] + ellipsis, size) <= max_width:
                low = middle
            else:
                high = middle - 1
        return text[:low].rstrip() + ellipsis

    def wrap(self, text: str, size: int, max_width: int, max_lines: int = 5) -> tuple[str, ...]:
        key = (str(text)[:self.MAX_TEXT_CHARS], size, max_width, max_lines)
        if key in self._wrap_cache:
            self._wrap_cache.move_to_end(key)
            return self._wrap_cache[key]
        lines: list[str] = []
        paragraphs = str(text)[:self.MAX_TEXT_CHARS].split("\n")
        overflow = False
        for paragraph_index, paragraph in enumerate(paragraphs):
            if len(lines) >= max_lines:
                overflow = True
                break
            words = paragraph.split(" ")
            current = ""
            for word in words:
                candidate = (current + " " + word).strip() if current else word
                if self.measure(candidate, size) <= max_width:
                    current = candidate
                    continue
                if current:
                    lines.append(current)
                    current = ""
                while word and self.measure(word, size) > max_width:
                    chunk = self.fit(word, size, max_width)
                    # Strip ellipsis because the following line continues it.
                    chunk = chunk[:-1] if chunk.endswith("…") else chunk
                    if not chunk:
                        chunk = word[0]
                    lines.append(chunk)
                    word = word[len(chunk):]
                    if len(lines) >= max_lines:
                        overflow = True
                        break
                current = word
                if len(lines) >= max_lines:
                    overflow = True
                    break
            if current and len(lines) < max_lines:
                lines.append(current)
            elif current:
                overflow = True
            if len(lines) >= max_lines:
                overflow = overflow or paragraph_index < len(paragraphs) - 1
                break
            if not paragraph:
                lines.append("")
        lines = lines[:max_lines]
        if overflow and lines:
            lines[-1] = self.fit(lines[-1].rstrip("…") + "…", size, max_width)
        result = tuple(lines)
        self._wrap_cache[key] = result
        if len(self._wrap_cache) > 128:
            self._wrap_cache.popitem(last=False)
        return result

    def raster(self, text: str, size: int, color: tuple[int, int, int, int], max_width: int) -> Raster:
        text = self.fit(text, size, max_width)
        if not text:
            return Raster(1, 1, b"\0\0\0\0")
        font = self.font(size)
        scratch = self._image.new("RGBA", (1, 1))
        bounds = self._draw.Draw(scratch).textbbox((0, 0), text, font=font, anchor="lt")
        width = max(1, min(max_width, bounds[2] - bounds[0] + 3))
        height = max(1, min(160, bounds[3] - bounds[1] + 4))
        image = self._image.new("RGBA", (width, height), (0, 0, 0, 0))
        self._draw.Draw(image).text((1 - bounds[0], 1 - bounds[1]), text, font=font, fill=color, anchor="lt")
        return Raster(width, height, image.tobytes())


class SDLTextRasterizer(TextRasterizer):
    """Reuse fonts and SDL_ttf already owned by PyUI, without importing Pillow.

    ``font_provider(pixel_size)`` returns an existing TTF_Font pointer. The caller
    owns those fonts and their lifetime; this adapter never closes/reinitializes
    them. A bridge may prepare a bounded font-size set during its startup stage.
    """

    def __init__(self, font_provider: Callable[[int], Any]):
        import ctypes
        import sdl2
        from sdl2 import sdlttf
        self._ctypes, self._sdl, self._ttf = ctypes, sdl2, sdlttf
        self._font_provider = font_provider
        self._measure_cache = OrderedDict()
        self._wrap_cache = OrderedDict()

    def font(self, size: int) -> Any:
        font = self._font_provider(max(10, min(92, int(size))))
        if not font:
            raise ValueError("The existing SDL_ttf font provider returned no font")
        return font

    def measure(self, text: str, size: int) -> float:
        key = (str(text)[:self.MAX_TEXT_CHARS].replace("\n", " "), size)
        if key in self._measure_cache:
            self._measure_cache.move_to_end(key)
            return self._measure_cache[key]
        width, height = self._ctypes.c_int(), self._ctypes.c_int()
        encoded = key[0].encode("utf-8", "replace")
        if not encoded:
            return 0.0
        if self._ttf.TTF_SizeUTF8(self.font(size), encoded, self._ctypes.byref(width), self._ctypes.byref(height)) != 0:
            raise ValueError("The existing SDL_ttf backend could not measure text")
        self._measure_cache[key] = float(width.value)
        if len(self._measure_cache) > 512:
            self._measure_cache.popitem(last=False)
        return float(width.value)

    def raster(self, text: str, size: int, color: tuple[int, int, int, int], max_width: int) -> Raster:
        text = self.fit(text, size, max_width)
        if not text:
            return Raster(1, 1, b"\0\0\0\0")
        surface = self._ttf.TTF_RenderUTF8_Blended(self.font(size), text.encode("utf-8", "replace"), self._sdl.SDL_Color(*color))
        if not surface:
            raise ValueError("The existing SDL_ttf backend could not rasterize text")
        converted = None
        try:
            converted = self._sdl.SDL_ConvertSurfaceFormat(surface, self._sdl.SDL_PIXELFORMAT_RGBA32, 0)
            if not converted:
                raise ValueError("The existing SDL backend could not convert a text surface")
            width, height = converted.contents.w, converted.contents.h
            if not (0 < width <= max_width + 4 and 0 < height <= 256):
                raise ValueError("The text surface exceeds its rendering budget")
            pixels = b"".join(self._ctypes.string_at(converted.contents.pixels + row * converted.contents.pitch, width * 4)
                              for row in range(height))
            return Raster(width, height, pixels)
        finally:
            if converted:
                self._sdl.SDL_FreeSurface(converted)
            self._sdl.SDL_FreeSurface(surface)
