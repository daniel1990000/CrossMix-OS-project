"""One bounded artwork decoder; SDL texture uploads remain on the UI thread.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from dataclasses import dataclass
import io
import os
from pathlib import Path
import queue
import stat
import struct
import threading
import warnings


@dataclass(frozen=True)
class ArtworkResult:
    path: str
    width: int = 0
    height: int = 0
    pixels: bytes = b""
    error: str = ""


class ArtworkDecoder:
    MAX_SOURCE_BYTES = 8 * 1024 * 1024
    MAX_PIXELS = 16 * 1024 * 1024
    MAX_DIMENSION = 8192
    OUTPUT_DIMENSION = 512

    def __init__(self, allowed_root: str | Path | None = None):
        # Canonicalization is startup work, not rendering work.
        self._root = os.path.realpath(allowed_root) if allowed_root else None
        self._root_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)) if self._root else None
        self._requests: queue.Queue[str | None] = queue.Queue(maxsize=2)
        self._results: queue.Queue[ArtworkResult] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="psp-artwork", daemon=True)
        self._thread.start()

    def request(self, path: str) -> None:
        if not self._root or not path or self._stop.is_set():
            return
        try:
            self._requests.put_nowait(path)
        except queue.Full:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                pass
            try:
                self._requests.put_nowait(path)
            except queue.Full:
                pass

    def poll(self) -> list[ArtworkResult]:
        result = []
        while True:
            try:
                result.append(self._results.get_nowait())
            except queue.Empty:
                return result

    def _decode(self, requested_path: str) -> ArtworkResult:
        assert self._root is not None
        candidate = requested_path if os.path.isabs(requested_path) else os.path.join(self._root, requested_path)
        resolved = os.path.realpath(candidate)
        if os.path.commonpath((self._root, resolved)) != self._root:
            return ArtworkResult(requested_path, error="Artwork is outside the approved library")
        # Walk from an already-open approved directory. Refuse intermediate and
        # final symlinks, including a directory swapped after canonicalization.
        parts = Path(os.path.relpath(resolved, self._root)).parts
        if not parts or any(part in ("..", ".", "") for part in parts):
            raise ValueError("Invalid artwork path")
        parent = os.dup(self._root_fd)
        try:
            for component in parts[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
                os.close(parent)
                parent = child
            descriptor = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
        finally:
            os.close(parent)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= self.MAX_SOURCE_BYTES:
                raise ValueError("Artwork exceeds its source size limit")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                data = source.read(self.MAX_SOURCE_BYTES + 1)
            if len(data) > self.MAX_SOURCE_BYTES:
                raise ValueError("Artwork exceeds its source size limit")
        finally:
            os.close(descriptor)
        return self._decode_image(data, requested_path)

    def _decode_image(self, data: bytes, requested_path: str) -> ArtworkResult:
        from PIL import Image, ImageOps
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source_image:
                width, height = source_image.size
                if not (0 < width <= self.MAX_DIMENSION and 0 < height <= self.MAX_DIMENSION and width * height <= self.MAX_PIXELS):
                    raise ValueError("Artwork exceeds its decoded size limit")
                if source_image.format not in ("PNG", "JPEG", "BMP", "WEBP"):
                    raise ValueError("Unsupported artwork format")
                source_image.thumbnail((self.OUTPUT_DIMENSION, self.OUTPUT_DIMENSION), Image.Resampling.LANCZOS)
                image = ImageOps.exif_transpose(source_image).convert("RGBA")
                return ArtworkResult(requested_path, image.width, image.height, image.tobytes())

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                path = self._requests.get(timeout=0.2)
            except queue.Empty:
                continue
            if path is None:
                return
            try:
                result = self._decode(path)
            except Exception:
                # A bad optional image must not terminate the presentation worker.
                result = ArtworkResult(path, error="Artwork could not be decoded safely")
            if self._stop.is_set():
                return
            try:
                self._results.put_nowait(result)
            except queue.Full:
                try:
                    self._results.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._results.put_nowait(result)
                except queue.Full:
                    pass

    def close(self) -> None:
        self._stop.set()
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=2)
        if not self._thread.is_alive() and self._root_fd is not None:
            os.close(self._root_fd)
            self._root_fd = None


def image_dimensions(data: bytes) -> tuple[int, int]:
    """Bounded PNG/JPEG header preflight before passing bytes to SDL_image."""
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        offset = 2
        while offset + 4 <= len(data):
            if data[offset] != 0xFF:
                raise ValueError("Invalid JPEG marker")
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD8, 0xD9, 0xDA):
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                continue
            length = int.from_bytes(data[offset:offset + 2], "big")
            if length < 2 or offset + length > len(data):
                raise ValueError("Invalid JPEG segment")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if length < 8:
                    raise ValueError("Invalid JPEG frame")
                height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
                return width, height
            offset += length
    raise ValueError("A PNG or JPEG header is required by the embedded artwork backend")


class SDLArtworkDecoder(ArtworkDecoder):
    """Existing SDL_image alternative for a target without Pillow."""

    def _decode_image(self, data: bytes, requested_path: str) -> ArtworkResult:
        import ctypes
        import sdl2
        from sdl2 import sdlimage
        width, height = image_dimensions(data)
        if not (0 < width <= self.MAX_DIMENSION and 0 < height <= self.MAX_DIMENSION and width * height <= self.MAX_PIXELS):
            raise ValueError("Artwork exceeds its decoded size limit")
        buffer = ctypes.create_string_buffer(data)
        source = sdlimage.IMG_Load_RW(sdl2.SDL_RWFromConstMem(buffer, len(data)), 1)
        if not source:
            raise ValueError("The existing SDL_image backend could not decode artwork")
        output = None
        try:
            if source.contents.w != width or source.contents.h != height:
                raise ValueError("Decoded artwork dimensions differ from its header")
            factor = min(1.0, self.OUTPUT_DIMENSION / max(width, height))
            width, height = max(1, round(width * factor)), max(1, round(height * factor))
            output = sdl2.SDL_CreateRGBSurfaceWithFormat(0, width, height, 32, sdl2.SDL_PIXELFORMAT_RGBA32)
            if not output:
                raise ValueError("Could not allocate bounded artwork surface")
            sdl2.SDL_SetSurfaceBlendMode(source, sdl2.SDL_BLENDMODE_NONE)
            if sdl2.SDL_BlitScaled(source, None, output, None) != 0:
                raise ValueError("Could not resize artwork")
            pixels = b"".join(ctypes.string_at(output.contents.pixels + row * output.contents.pitch, width * 4) for row in range(height))
            return ArtworkResult(requested_path, width, height, pixels)
        finally:
            if output:
                sdl2.SDL_FreeSurface(output)
            sdl2.SDL_FreeSurface(source)
