# Artwork formats and limits

The host preview and embedded renderer accept PNG, JPEG, BMP, static WebP and
QOI artwork. The decoder checks the file header rather than trusting its suffix.
All decoding runs in the existing bounded worker; SDL texture creation stays on
the UI thread. Artwork is read from the approved library without modifying it.

| Format | Host preview | Embedded path | Current host evidence |
|---|---|---|---|
| PNG | Installed Pillow | Installed SDL_image PNG codec | Both decoded synthetic RGB and alpha fixtures. |
| JPEG | Installed Pillow | Installed SDL_image JPEG codec | Both decoded the same synthetic fixture. |
| BMP | Installed Pillow | Installed SDL_image BMP loader | Both decoded the same synthetic fixture. |
| Static WebP | Installed Pillow WebP codec | Installed SDL_image WebP codec | Both decoded lossy, extended-alpha and lossless fixtures. |
| QOI | Original project decoder | The same original project decoder | Synthetic opcode fixtures cross-check Pillow's QOI reader; both paths produce the same bounded RGBA thumbnail. |

The tests use Pillow **11.1.0** and an isolated host SDL_image **2.8.8** with
JPEG/PNG/WebP support. These results do not identify or qualify the libraries
installed on a Smart Pro. A missing target codec produces the same optional-art
placeholder as a failed decode; it does not install or replace libraries.
QOI requires neither Pillow nor SDL_image. Pillow 11.1.0 reads QOI but does not
write it; test fixtures are original synthetic byte streams.

Files are limited to **8 MiB**, dimensions to **8192** on either axis and source
area to **16,777,216 pixels**. Both backends inspect dimensions before invoking
a codec and check its returned dimensions. Output is RGBA with at most **512
pixels on either axis**. WebP's static canvas must match its encoded frame;
animation and malformed container lengths are rejected before decoding.
Existing Pillow EXIF orientation behavior remains in the host path; the target
library's orientation behavior still needs device inspection.

QOI is decoded directly into an aspect-preserving nearest-neighbor thumbnail,
without allocating a full-size source bitmap. Its index, RGB/RGBA, difference,
luma and run chunks have bounded work; a run cannot exceed the declared image.
The decoder requires the exact end marker and rejects truncated or trailing
pixel data. Cancellation is checked at least once per 4096 encoded chunks.

Source reads reject symlinks, nonregular files and files whose identity, size or
timestamps change during the read. Opening a special file cannot block the
worker while waiting for a writer. Decode errors return no pixels and the same
failure result on both backends. Every admitted request retains its generation
token, including failures, so refresh handling can reject stale completions.

Run the focused checks with the documented host dependencies installed:

```sh
PYTHONPATH=project /path/to/preview-venv/bin/python -m unittest discover -s project/tests -p test_artwork_formats.py -v
```

The tests exercise actual host codecs, header and size limits, QOI operations,
malformed streams, missing-codec failure, source-read races and worker tokens.
Physical image presentation and target codec availability remain untested.
