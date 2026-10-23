"""One bounded artwork decoder; SDL texture uploads remain on the UI thread.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from dataclasses import dataclass, replace
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
    generation: int = 0


class ArtworkDecoder:
    MAX_SOURCE_BYTES = 8 * 1024 * 1024
    MAX_PIXELS = 16 * 1024 * 1024
    MAX_DIMENSION = 8192
    OUTPUT_DIMENSION = 512

    def __init__(self, allowed_root: str | Path | None = None):
        # Canonicalization is startup work, not rendering work.
        self._root = os.path.realpath(allowed_root) if allowed_root else None
        self._root_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)) if self._root else None
        self._requests: queue.Queue[tuple[str, int] | None] = queue.Queue(maxsize=2)
        self._results: queue.Queue[ArtworkResult] = queue.Queue(maxsize=2)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="psp-artwork", daemon=True)
        self._thread.start()

    def request(self, path: str, generation: int = 0) -> bool:
        """Acknowledge admission; callers can retry a full queue later."""
        if not self._root or not path or self._stop.is_set() or type(generation) is not int or generation < 0:
            return False
        try:
            self._requests.put_nowait((path, generation))
        except queue.Full:
            return False
        return True

    def poll(self) -> list[ArtworkResult]:
        result = []
        while True:
            try:
                result.append(self._results.get_nowait())
            except queue.Empty:
                return result

    def _decode(self, requested_path: str) -> ArtworkResult:
        assert self._root is not None
        candidate = os.path.abspath(requested_path if os.path.isabs(requested_path) else os.path.join(self._root, requested_path))
        resolved = os.path.realpath(candidate)
        if os.path.commonpath((self._root, resolved)) != self._root or os.path.commonpath((self._root, candidate)) != self._root:
            return ArtworkResult(requested_path, error="Artwork is outside the approved library")
        # Walk from an already-open approved directory. Refuse intermediate and
        # final symlinks, including a directory swapped after canonicalization.
        parts = Path(os.path.relpath(candidate, self._root)).parts
        if not parts or any(part in ("..", ".", "") for part in parts):
            raise ValueError("Invalid artwork path")
        parent = os.dup(self._root_fd)
        try:
            for component in parts[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
                os.close(parent)
                parent = child
            descriptor = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                                 getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        finally:
            os.close(parent)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= self.MAX_SOURCE_BYTES:
                raise ValueError("Artwork exceeds its source size limit")
            with os.fdopen(descriptor, "rb", closefd=False) as source:
                data = source.read(self.MAX_SOURCE_BYTES + 1)
            after = os.fstat(descriptor)
            identity = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                      value.st_mtime_ns, value.st_ctime_ns)
            if len(data) != info.st_size or identity(info) != identity(after):
                raise ValueError("Artwork changed during its bounded read")
        finally:
            os.close(descriptor)
        return self._decode_image(data, requested_path)

    def _decode_image(self, data: bytes, requested_path: str) -> ArtworkResult:
        image_format, width, height = self._preflight(data)
        if image_format == "QOI":
            return self._qoi_image(data, requested_path, width, height)
        from PIL import Image, ImageOps
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source_image:
                if source_image.size != (width, height) or source_image.format != image_format:
                    raise ValueError("Decoded artwork differs from its preflight header")
                source_image.thumbnail((self.OUTPUT_DIMENSION, self.OUTPUT_DIMENSION), Image.Resampling.LANCZOS)
                image = ImageOps.exif_transpose(source_image).convert("RGBA")
                return ArtworkResult(requested_path, image.width, image.height, image.tobytes())

    def _preflight(self, data: bytes) -> tuple[str, int, int]:
        if not 0 < len(data) <= self.MAX_SOURCE_BYTES:
            raise ValueError("Artwork exceeds its source size limit")
        image_format, width, height = image_header(data)
        if not (0 < width <= self.MAX_DIMENSION and 0 < height <= self.MAX_DIMENSION and
                width * height <= self.MAX_PIXELS):
            raise ValueError("Artwork exceeds its decoded size limit")
        return image_format, width, height

    def _qoi_image(self, data: bytes, requested_path: str, width: int, height: int) -> ArtworkResult:
        output_width, output_height, pixels = decode_qoi(data, width, height,
                                                        self.OUTPUT_DIMENSION, self._stop)
        return ArtworkResult(requested_path, output_width, output_height, pixels)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                request = self._requests.get(timeout=0.2)
            except queue.Empty:
                continue
            if request is None:
                return
            path, generation = request
            try:
                result = self._decode(path)
            except Exception:
                # A bad optional image must not terminate the presentation worker.
                result = ArtworkResult(path, error="Artwork could not be decoded safely")
            result = replace(result, generation=generation)
            if self._stop.is_set():
                return
            # Every admitted request receives an acknowledgement, including
            # failures. Backpressure stays on this worker, never the UI thread.
            while not self._stop.is_set():
                try:
                    self._results.put(result, timeout=0.1)
                    break
                except queue.Full:
                    continue

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


def image_header(data: bytes) -> tuple[str, int, int]:
    """Read dimensions before a native decoder can allocate a source surface.

    This is format preflight, not a replacement for the codecs' full validation.
    Static WebP's canvas and frame must agree; animation is outside this artwork
    contract. QOI uses the same original bounded normalizer on both backends.
    """
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return ("PNG", *struct.unpack(">II", data[16:24]))
    if data[:2] == b"\xff\xd8":
        offset = 2
        dimensions = None
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
                if dimensions is not None:
                    raise ValueError("Multiple JPEG frame headers are unsupported")
                height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
                dimensions = width, height
            offset += length
        if dimensions is not None:
            return "JPEG", *dimensions
    if data[:2] == b"BM" and len(data) >= 26:
        header_size = int.from_bytes(data[14:18], "little")
        if header_size == 12:
            width, height = struct.unpack("<HH", data[18:22])
        elif header_size in (40, 52, 56, 64, 108, 124) and 14 + header_size <= len(data):
            width, height = struct.unpack("<ii", data[18:26])
            height = abs(height)  # BMP can store its rows from top to bottom.
        else:
            raise ValueError("Unsupported or truncated BMP header")
        return "BMP", width, height
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        if int.from_bytes(data[4:8], "little") + 8 != len(data):
            raise ValueError("Invalid WebP container length")
        offset, canvas, frame = 12, None, None
        while offset + 8 <= len(data):
            kind = data[offset:offset + 4]
            length = int.from_bytes(data[offset + 4:offset + 8], "little")
            start = offset + 8
            end = start + length
            if end + (length & 1) > len(data):
                raise ValueError("Invalid WebP chunk length")
            payload = data[start:end]
            if kind in (b"ANIM", b"ANMF"):
                raise ValueError("Animated artwork is unsupported")
            if kind == b"VP8X":
                if len(payload) != 10 or canvas is not None or payload[0] & 0x02:
                    raise ValueError("Invalid or animated WebP canvas")
                canvas = (int.from_bytes(payload[4:7], "little") + 1,
                          int.from_bytes(payload[7:10], "little") + 1)
            elif kind in (b"VP8 ", b"VP8L"):
                if frame is not None:
                    raise ValueError("Multiple WebP frames are unsupported")
                if kind == b"VP8L":
                    if len(payload) < 5 or payload[0] != 0x2F:
                        raise ValueError("Invalid lossless WebP frame")
                    bits = int.from_bytes(payload[1:5], "little")
                    if bits >> 29:
                        raise ValueError("Unsupported lossless WebP version")
                    frame = (1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF))
                else:
                    if len(payload) < 10 or payload[0] & 1 or payload[3:6] != b"\x9d\x01\x2a":
                        raise ValueError("Invalid WebP key frame")
                    width, height = struct.unpack("<HH", payload[6:10])
                    frame = width & 0x3FFF, height & 0x3FFF
            offset = end + (length & 1)
        if offset != len(data) or frame is None or (canvas is not None and canvas != frame):
            raise ValueError("WebP canvas and frame dimensions differ or are missing")
        return "WEBP", *frame
    if data[:4] == b"qoif" and len(data) >= 22:
        width, height = struct.unpack(">II", data[4:12])
        if data[12] not in (3, 4) or data[13] not in (0, 1):
            raise ValueError("Invalid QOI channel or color-space header")
        return "QOI", width, height
    raise ValueError("Unsupported or truncated artwork header")


def image_dimensions(data: bytes) -> tuple[int, int]:
    """Compatibility wrapper for bounded format-header inspection."""
    _, width, height = image_header(data)
    return width, height


def decode_qoi(data: bytes, width: int, height: int, limit: int,
               stop: threading.Event) -> tuple[int, int, bytes]:
    """Decode original QOI chunks into a bounded nearest-neighbor thumbnail.

    The caller has already bounded source bytes/dimensions. Work is limited by
    source chunks and the declared pixel count; runs cannot cross that count.
    No full-size image, third-party decoder or SDL surface is allocated.
    """
    marker = b"\0\0\0\0\0\0\0\x01"
    if data[-8:] != marker:
        raise ValueError("QOI end marker is missing")
    factor = min(1.0, limit / max(width, height))
    output_width, output_height = max(1, round(width * factor)), max(1, round(height * factor))
    output = bytearray(output_width * output_height * 4)
    index = [(0, 0, 0, 0)] * 64
    pixel = (0, 0, 0, 255)
    offset, source_position, sample_position, sample_index, steps = 14, 0, 0, 0, 0
    end = len(data) - 8
    count = width * height
    while source_position < count:
        if steps & 4095 == 0 and stop.is_set():
            raise ValueError("Artwork decode cancelled")
        steps += 1
        if offset >= end:
            raise ValueError("QOI pixel stream is truncated")
        code = data[offset]
        offset += 1
        span = 1
        if code in (0xFE, 0xFF):
            channels = 3 if code == 0xFE else 4
            if offset + channels > end:
                raise ValueError("QOI color chunk is truncated")
            pixel = tuple(data[offset:offset + channels]) + ((pixel[3],) if channels == 3 else ())
            offset += channels
        elif code >> 6 == 0:
            pixel = index[code & 63]
        elif code >> 6 == 1:
            r, g, b, a = pixel
            pixel = ((r + ((code >> 4) & 3) - 2) & 255,
                     (g + ((code >> 2) & 3) - 2) & 255,
                     (b + (code & 3) - 2) & 255, a)
        elif code >> 6 == 2:
            if offset >= end:
                raise ValueError("QOI luma chunk is truncated")
            differences = data[offset]
            offset += 1
            r, g, b, a = pixel
            green = (code & 63) - 32
            pixel = ((r + green + (differences >> 4) - 8) & 255,
                     (g + green) & 255, (b + green + (differences & 15) - 8) & 255, a)
        else:
            span = (code & 63) + 1
        if source_position + span > count:
            raise ValueError("QOI run exceeds the declared image")
        index[(pixel[0] * 3 + pixel[1] * 5 + pixel[2] * 7 + pixel[3] * 11) & 63] = pixel
        chunk_end = source_position + span
        while sample_index < output_width * output_height and sample_position < chunk_end:
            start = sample_index * 4
            output[start:start + 4] = bytes(pixel)
            sample_index += 1
            sample_position = ((sample_index // output_width) * height // output_height) * width + \
                              ((sample_index % output_width) * width // output_width)
        source_position = chunk_end
    if offset != end or sample_index != output_width * output_height:
        raise ValueError("QOI stream has trailing or missing pixel data")
    return output_width, output_height, bytes(output)


class SDLArtworkDecoder(ArtworkDecoder):
    """Existing SDL_image alternative for a target without Pillow."""

    def _decode_image(self, data: bytes, requested_path: str) -> ArtworkResult:
        image_format, width, height = self._preflight(data)
        if image_format == "QOI":
            return self._qoi_image(data, requested_path, width, height)
        import ctypes
        import sdl2
        from sdl2 import sdlimage
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
