"""Synthetic artwork codecs, resource limits and asynchronous acknowledgement.

These tests exercise the installed host codecs. They do not establish a target
device's SDL_image build, performance or installed-library identity.
"""
# SPDX-License-Identifier: MIT
import builtins
import io
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image
import sdl2
from sdl2 import sdlimage

from psp_shell.ui.artwork import ArtworkDecoder, ArtworkResult, SDLArtworkDecoder, image_header


END = b"\0" * 7 + b"\x01"


def qoi(width, height, chunks, *, channels=4, colorspace=0):
    return b"qoif" + struct.pack(">II", width, height) + bytes((channels, colorspace)) + chunks + END


def qoi_solid(width, height, pixel=(43, 135, 207, 255)):
    remaining = width * height - 1
    runs, tail = divmod(remaining, 62)
    chunks = b"\xff" + bytes(pixel) + b"\xfd" * runs
    if tail:
        chunks += bytes((0xC0 | (tail - 1),))
    return qoi(width, height, chunks)


def encoded(image_format, width=13, height=7, *, alpha=False, **options):
    image = Image.new("RGBA" if alpha else "RGB", (width, height),
                      (43, 135, 207, 109) if alpha else (43, 135, 207))
    stream = io.BytesIO()
    image.save(stream, format=image_format, **options)
    return stream.getvalue()


class ArtworkFormatTests(unittest.TestCase):
    def setUp(self):
        self.host = ArtworkDecoder()
        self.native = SDLArtworkDecoder()
        self.addCleanup(self.host.close)
        self.addCleanup(self.native.close)

    def both(self, data):
        return (self.host._decode_image(data, "fixture"),
                self.native._decode_image(data, "fixture"))

    def test_real_host_and_existing_sdl_image_decode_all_five_formats(self):
        for image_format in ("PNG", "JPEG", "BMP", "WEBP", "QOI"):
            with self.subTest(image_format=image_format):
                data = qoi_solid(13, 7) if image_format == "QOI" else encoded(image_format)
                self.assertEqual(image_header(data), (image_format, 13, 7))
                host, native = self.both(data)
                for result in (host, native):
                    self.assertEqual((result.width, result.height), (13, 7))
                    self.assertEqual(len(result.pixels), 13 * 7 * 4)
                    self.assertFalse(result.error)
                if image_format in ("JPEG", "WEBP"):
                    # Lossy decoder implementations may round channels
                    # differently; byte identity is a lossless-only contract.
                    self.assertLessEqual(max(abs(a - b) for a, b in zip(host.pixels, native.pixels)), 3)
                else:
                    self.assertEqual(host.pixels, native.pixels)

    def test_lossless_alpha_is_retained_on_both_backends(self):
        for image_format in ("PNG", "WEBP", "QOI"):
            with self.subTest(image_format=image_format):
                data = (qoi_solid(13, 7, (43, 135, 207, 109)) if image_format == "QOI" else
                        encoded(image_format, alpha=True, **({"lossless": True} if image_format == "WEBP" else {})))
                host, native = self.both(data)
                self.assertEqual(host.pixels, bytes((43, 135, 207, 109)) * 91)
                self.assertEqual(native.pixels, host.pixels)

    def test_lossy_extended_and_lossless_webp_headers_are_preflighted(self):
        cases = (encoded("WEBP"), encoded("WEBP", alpha=True), encoded("WEBP", lossless=True))
        self.assertEqual([data[12:16] for data in cases], [b"VP8 ", b"VP8X", b"VP8L"])
        for data in cases:
            with self.subTest(kind=data[12:16]):
                self.assertEqual(image_header(data), ("WEBP", 13, 7))
                for result in self.both(data):
                    self.assertEqual((result.width, result.height), (13, 7))

    def test_original_qoi_chunks_match_independent_pillow_decoder(self):
        first = (10, 20, 30, 40)
        slot = (first[0] * 3 + first[1] * 5 + first[2] * 7 + first[3] * 11) & 63
        chunks = (b"\xff" + bytes(first) + b"\xfe\x32\x3c\x46" + bytes((0x79, 0xA5, 0xA5, slot, 0xC1)) +
                  b"\xff\xfa\x00\x80\xff")
        data = qoi(8, 1, chunks)
        with Image.open(io.BytesIO(data)) as independent:
            expected = independent.convert("RGBA").tobytes()
        self.assertEqual(len(expected), 8 * 4)
        for result in self.both(data):
            self.assertEqual(result.pixels, expected)
        # The initial pixel and differences wrap in unsigned byte arithmetic.
        wrap = qoi(2, 1, b"\x40\x80\x00")
        with Image.open(io.BytesIO(wrap)) as independent:
            expected = independent.convert("RGBA").tobytes()
        for result in self.both(wrap):
            self.assertEqual(result.pixels, expected)

    def test_qoi_does_not_import_pillow_or_sdl_image(self):
        original_import = builtins.__import__
        def restricted(name, *arguments, **keywords):
            if name == "PIL" or name.startswith("PIL.") or name in ("sdl2", "sdl2.sdlimage"):
                raise ImportError("codec dependency deliberately unavailable")
            return original_import(name, *arguments, **keywords)
        with patch("builtins.__import__", side_effect=restricted):
            for result in self.both(qoi_solid(13, 7)):
                self.assertEqual(result.pixels, bytes((43, 135, 207, 255)) * 91)

    def test_native_common_formats_do_not_import_pillow(self):
        fixtures = [encoded(image_format) for image_format in ("PNG", "JPEG", "BMP", "WEBP")]
        original_import = builtins.__import__
        def restricted(name, *arguments, **keywords):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("Pillow deliberately unavailable")
            return original_import(name, *arguments, **keywords)
        with patch("builtins.__import__", side_effect=restricted):
            for data in fixtures:
                result = self.native._decode_image(data, "fixture")
                self.assertEqual((result.width, result.height), (13, 7))

    def test_qoi_downsamples_runs_without_allocating_a_full_source_image(self):
        data = qoi_solid(2048, 1024, (12, 27, 39, 81))
        host, native = self.both(data)
        self.assertEqual((host.width, host.height), (512, 256))
        self.assertEqual(host.pixels, bytes((12, 27, 39, 81)) * (512 * 256))
        self.assertEqual(native.pixels, host.pixels)
        self.assertLessEqual(len(host.pixels), 512 * 512 * 4)
        self.host._stop.set()
        with self.assertRaisesRegex(ValueError, "cancelled"):
            self.host._decode_image(data, "fixture")

    def test_qoi_thumbnail_samples_the_correct_rows_and_columns(self):
        width, height = 600, 5
        def pixel(x, y):
            return bytes((x % 251, y * 17, (x + y) % 239, 255))
        chunks = b"".join(b"\xff" + pixel(x, y) for y in range(height) for x in range(width))
        expected = b"".join(pixel(x * width // 512, y * height // 4)
                            for y in range(4) for x in range(512))
        for result in self.both(qoi(width, height, chunks)):
            self.assertEqual((result.width, result.height), (512, 4))
            self.assertEqual(result.pixels, expected)

    def test_dimensions_are_bounded_before_either_codec_is_called(self):
        fixtures = []
        for image_format in ("PNG", "BMP"):
            data = bytearray(encoded(image_format))
            if image_format == "PNG":
                data[16:24] = struct.pack(">II", 8193, 1)
            else:
                data[18:26] = struct.pack("<ii", 8193, 1)
            fixtures.append(bytes(data))
        jpeg = bytearray(encoded("JPEG"))
        start = jpeg.index(b"\xff\xc0")
        jpeg[start + 7:start + 9] = struct.pack(">H", 8193)
        fixtures.append(bytes(jpeg))
        webp = bytearray(encoded("WEBP", lossless=True))
        self.assertEqual(webp[12:16], b"VP8L")
        bits = int.from_bytes(webp[21:25], "little")
        webp[21:25] = ((bits & ~0x3FFF) | 8192).to_bytes(4, "little")
        fixtures.append(bytes(webp))
        fixtures.extend((qoi_solid(1, 1)[:4] + struct.pack(">II", 8193, 1) + qoi_solid(1, 1)[12:],
                         qoi(8192, 8192, b"\xc0"), qoi(0, 1, b"\xc0")))
        with patch.object(Image, "open", side_effect=AssertionError("Pillow must not run")), \
                patch.object(sdlimage, "IMG_Load_RW", side_effect=AssertionError("SDL codec must not run")):
            for data in fixtures:
                for decoder in (self.host, self.native):
                    with self.subTest(decoder=type(decoder).__name__, header=data[:26]), \
                            self.assertRaisesRegex(ValueError, "decoded size limit"):
                        decoder._decode_image(data, "fixture")

    def test_a_second_jpeg_frame_header_cannot_hide_different_dimensions(self):
        data = encoded("JPEG")
        start = data.index(b"\xff\xc0")
        length = int.from_bytes(data[start + 2:start + 4], "big")
        frame = data[start:start + 2 + length]
        duplicate = data[:start] + frame + data[start:]
        for decoder in (self.host, self.native):
            with self.assertRaisesRegex(ValueError, "Multiple JPEG frame"):
                decoder._decode_image(duplicate, "fixture")

    def test_webp_canvas_cannot_hide_a_different_intrinsic_frame_size(self):
        data = bytearray(encoded("WEBP", alpha=True))
        self.assertEqual(data[12:16], b"VP8X")
        data[24:27] = (3 - 1).to_bytes(3, "little")
        with patch.object(sdlimage, "IMG_Load_RW", side_effect=AssertionError("SDL codec must not run")):
            for decoder in (self.host, self.native):
                with self.assertRaisesRegex(ValueError, "canvas and frame"):
                    decoder._decode_image(bytes(data), "fixture")

    def test_animated_webp_is_rejected_before_decoding(self):
        stream = io.BytesIO()
        Image.new("RGBA", (3, 2), (255, 0, 0, 100)).save(
            stream, format="WEBP", save_all=True,
            append_images=[Image.new("RGBA", (3, 2), (0, 0, 255, 100))], duration=50, loop=0)
        for decoder in (self.host, self.native):
            with self.assertRaisesRegex(ValueError, "animated|Animated"):
                decoder._decode_image(stream.getvalue(), "fixture")

    def test_truncated_invalid_and_unsupported_headers_are_rejected(self):
        fixtures = [b"", b"GIF89a" + b"\x01\0\x01\0", b"not an image"]
        fixtures.extend(encoded(image_format)[:12] for image_format in ("PNG", "JPEG", "BMP", "WEBP"))
        fixtures.extend((qoi(1, 1, b"\xff\x01\x02\x03\xff", channels=2),
                         qoi(1, 1, b"\xff\x01\x02\x03\xff", colorspace=2)))
        for data in fixtures:
            for decoder in (self.host, self.native):
                with self.subTest(data=data[:16], decoder=type(decoder).__name__), self.assertRaises(ValueError):
                    decoder._decode_image(data, "fixture")

    def test_qoi_truncation_extra_data_and_run_overflow_are_rejected(self):
        valid = qoi_solid(1, 1)
        fixtures = [valid[:-1], valid + b"x", qoi(1, 1, b"\xff\x01\x02\x03"),
                    qoi(1, 1, b"\x80"), qoi(1, 1, b"\xfd"),
                    qoi(2, 1, b"\xff\x01\x02\x03\xff"),
                    qoi(1, 1, b"\xff\x01\x02\x03\xff\x00")]
        for data in fixtures:
            for decoder in (self.host, self.native):
                with self.subTest(data=data, decoder=type(decoder).__name__), self.assertRaises(ValueError):
                    decoder._decode_image(data, "fixture")

    def test_native_dimensions_are_checked_again_after_decoding(self):
        wrong = sdl2.SDL_CreateRGBSurfaceWithFormat(0, 2, 2, 32, sdl2.SDL_PIXELFORMAT_RGBA32)
        self.assertTrue(wrong)
        # The decoder takes ownership and frees the deliberately mismatched surface.
        with patch.object(sdlimage, "IMG_Load_RW", return_value=wrong):
            with self.assertRaisesRegex(ValueError, "dimensions differ"):
                self.native._decode_image(encoded("PNG"), "fixture")

    def test_missing_native_codec_fails_without_successful_pixels(self):
        with patch.object(sdlimage, "IMG_Load_RW", return_value=None):
            with self.assertRaisesRegex(ValueError, "could not decode"):
                self.native._decode_image(encoded("WEBP"), "fixture")


class ArtworkFileAndWorkerTests(unittest.TestCase):
    def result(self, decoder, path, generation=0):
        self.assertTrue(decoder.request(path, generation=generation))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            results = decoder.poll()
            if results:
                self.assertEqual(len(results), 1)
                return results[0]
            time.sleep(0.005)
        self.fail("The bounded worker did not acknowledge its request")

    def test_worker_failure_placeholder_and_generation_are_consistent_on_both_backends(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad").write_bytes(b"not an image")
            (root / "good").write_bytes(qoi_solid(3, 2))
            for kind in (ArtworkDecoder, SDLArtworkDecoder):
                decoder = kind(root)
                try:
                    failed = self.result(decoder, "bad", generation=17)
                    self.assertEqual(failed.error, "Artwork could not be decoded safely")
                    self.assertFalse(failed.pixels)
                    self.assertEqual(failed.generation, 17)
                    good = self.result(decoder, "good", generation=18)
                    self.assertFalse(good.error)
                    self.assertEqual(good.generation, 18)
                    self.assertEqual((good.width, good.height), (3, 2))
                    self.assertEqual(ArtworkResult("legacy").generation, 0)
                finally:
                    decoder.close()
                self.assertFalse(decoder._thread.is_alive())

    def test_symlinks_special_files_and_oversize_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "real").write_bytes(qoi_solid(3, 2))
            (root / "link").symlink_to(root / "real")
            (root / "large").write_bytes(b"x" * (ArtworkDecoder.MAX_SOURCE_BYTES + 1))
            (root / "empty").write_bytes(b"")
            os.mkfifo(root / "fifo")
            decoder = ArtworkDecoder(root)
            try:
                for name in ("link", "large", "empty", "fifo"):
                    with self.subTest(name=name):
                        result = self.result(decoder, name)
                        self.assertTrue(result.error)
                        self.assertFalse(result.pixels)
            finally:
                decoder.close()

    def test_file_changed_during_read_is_rejected_before_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image"
            path.write_bytes(qoi_solid(3, 2))
            decoder = ArtworkDecoder(directory)
            actual_fstat = os.fstat
            calls = 0
            def change_before_second_stat(descriptor):
                nonlocal calls
                calls += 1
                if calls == 2:
                    path.write_bytes(qoi_solid(4, 2))
                return actual_fstat(descriptor)
            try:
                with patch("psp_shell.ui.artwork.os.fstat", side_effect=change_before_second_stat):
                    with self.assertRaisesRegex(ValueError, "changed during"):
                        decoder._decode("image")
            finally:
                decoder.close()


if __name__ == "__main__":
    unittest.main()
