"""Server-side cover downscaling (the ``?w=`` parameter on the cover proxy).

THE PROBLEM THIS FIXES. Covers were proxied at whatever resolution the source
publishes them at and painted into a thumbnail-sized box. Measured in a real
browser at a 375 px viewport on ``/sources/mangadex``, 13 of the 24 covers on
one page transferred **20.79 MB** — mean 1.64 MB, max 6.27 MB — into a
153x230 CSS px slot. A full page of 24 is ~39 MB against ~25-40 KB for a
correctly sized cover: a 40-60x overdraw, on every browse/library/search
screen, on every device, mostly over cellular.

WHY IT HAD TO BE SERVER-SIDE. ``next/image``'s optimizer fetches the URL
without cookies, and the cover route requires ``mm_session``, so the optimizer
gets a 401 and the frontend component is forced to set ``unoptimized``. There
is no client-side fix; the bytes have to be shrunk before they leave the box.

WHAT THIS MODULE IS. Pure functions: bytes in, bytes out, no I/O, no DB, no
settings. ``SourceCacheService.get_series_cover`` owns fetching, the 18+ gate
and the cache; this owns only the pixels. Every failure mode returns ``None``,
which the caller reads as "serve the original" — a heavy cover grid is a
performance problem, a broken cover grid is a bug.

WIDTH ALLOWLIST. ``COVER_WIDTHS`` is a closed set of six widths, and any
requested width SNAPS to it (``snap_cover_width``). A free-form integer would
be both a cache explosion and a trivial DoS: a thousand distinct ``?w=``
values is a thousand decode+encode cycles and a thousand rows, from one
attacker, on a 2-vCPU box. Snapping (rather than rejecting) means a client
that hard-codes an odd number still gets a right-sized image instead of a 422,
and the served width is echoed back in ``X-Cover-Width`` so nothing has to
guess. The steps are ~1.5x apart, so the worst case from snapping up is ~2.25x
the pixels actually needed — against the 2500x this replaces.

The six cover slots the clients actually paint, at DPR 1-3:
    32/44 css  -> 96      64/80 css  -> 160/240
    112 css    -> 240/360 153/176 css-> 360/480
    200 css    -> 480     220 css    -> 480/720
Anything larger asks for the original by omitting ``?w=`` entirely.

FORMAT. WebP when the client's ``Accept`` says so, JPEG otherwise. Measured
on the VPS over page-1 covers from three real sources, WebP came out 20-22%
smaller than JPEG at the same width and quality — and, more usefully, WebP
never lost the "is this actually smaller?" test below while JPEG did on
sources that already serve small covers. Only an explicit ``image/webp`` in
``Accept`` counts, never a bare ``*/*``: guessing wrong there shows a broken
image, while guessing conservatively only costs some bytes.

MEASURED (VPS, 2 vCPU, one 24-cover browse page, w=360 WebP — the phone grid):

    source        page before   page after   saving   CPU/cover (median)
    mangadex          34.3 MB      1.03 MB    33.4x               133 ms
    mangapill          2.65 MB      869 KB     3.1x                45 ms
    weebcentral        1.29 MB      978 KB     1.4x                47 ms

That spread is the honest shape of this fix: MangaDex publishes 1.5 MB covers
and is where the 34 MB grid came from; sources that already serve sensible
covers get a modest win, and at 480 px JPEG 23 of weebcentral's 24 covers hit
the never-bigger rule and were passed through untouched. The CPU is paid ONCE
per (series, width, format) — a cache hit is 0.04 ms and skips the upstream
fetch entirely.

DEPENDENCY. Pillow, imported lazily so the process still boots (serving
originals) if the wheel is ever missing. It is the only imaging library that
was a plausible choice: it ships prebuilt manylinux wheels with libwebp and
libjpeg-turbo bundled (no apt packages in the Dockerfile, which currently has
none at all), and it is ~7 MB installed against a ~20 GB disk budget. The
alternatives were worse: pyvips needs libvips from apt, and shelling out to
ImageMagick/cjpeg means a process spawn per cover on 2 vCPU.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger("manhwamaniacs.image_resize")

#: The closed set of widths the cover proxy will render. See the module
#: docstring for how these map to the clients' cover slots. Changing this is a
#: client-visible contract change AND invalidates nothing (rows are keyed by
#: width, so a removed width simply stops being read and ages out).
COVER_WIDTHS: tuple[int, ...] = (96, 160, 240, 360, 480, 720)

#: Encoded formats we will ever produce. Keys are the ``fmt`` cache-key value.
COVER_FORMATS: dict[str, str] = {"webp": "image/webp", "jpeg": "image/jpeg"}

# Quality knobs. 80/82 is the usual "no visible loss at thumbnail scale" band;
# a cover is displayed at 96-720 px, well below where these become visible.
_WEBP_QUALITY = 80
_JPEG_QUALITY = 82

#: Source formats we are willing to DECODE. Deliberately narrower than what
#: Pillow can open: this data comes from third-party sites, so the decoders
#: reachable from a hostile upstream should be the four boring bitmap ones and
#: not, say, the postscript or FITS plugins.
_DECODABLE_FORMATS = frozenset({"JPEG", "MPO", "PNG", "WEBP", "AVIF"})

#: Formats that can carry animation. A static resize of an animated cover is a
#: behaviour change, not an optimisation, so those are handed back untouched.
#: (MPO is excluded deliberately: Pillow reports plain stereoscopic JPEGs as
#: multi-frame MPO, and frame 0 is exactly what a browser paints.)
_ANIMATABLE_FORMATS = frozenset({"PNG", "WEBP"})

#: Refuse anything whose declared dimensions are absurd, before decoding a
#: single row. Pillow's own DecompressionBomb guard sits at ~89 MP and only
#: warns; a real cover is < 5 MP, so 40 MP is generous and still keeps a
#: decompression bomb from turning into ~500 MB of RGB on a 3.8 GB box.
_MAX_SOURCE_PIXELS = 40_000_000

#: Sanity ceiling on the resized height, so a pathologically tall "cover"
#: (a stitched webtoon strip served as the cover) cannot be re-encoded into
#: something larger than the thing it replaced. Above this the aspect ratio is
#: preserved and the height is what binds instead of the width.
_MAX_OUTPUT_HEIGHT = 4096


def snap_cover_width(requested: int | None) -> int | None:
    """Snap a requested width onto :data:`COVER_WIDTHS`.

    ``None`` (no ``?w=``) means "the original, untouched" and stays ``None``.
    Anything else snaps UP to the first allowed width that is at least as
    large, and anything above the largest snaps DOWN to it — a caller wanting
    more than 720 px wants the original and should omit the parameter. This is
    what bounds the cache's key space and the CPU an attacker can buy with one
    URL.
    """
    if requested is None:
        return None
    for width in COVER_WIDTHS:
        if requested <= width:
            return width
    return COVER_WIDTHS[-1]


def negotiate_cover_format(accept: str | None) -> str:
    """``"webp"`` if the client explicitly accepts it, else ``"jpeg"``.

    Only a literal ``image/webp`` token counts. ``*/*`` and ``image/*`` are
    deliberately NOT treated as WebP support: they are what a bare HTTP client
    sends, and the cost of guessing wrong is a broken image, while the cost of
    guessing conservatively is a somewhat larger JPEG.

    Responses that depend on this MUST carry ``Vary: Accept`` or a shared
    cache will hand a WebP to a client that cannot read it.
    """
    if not accept:
        return "jpeg"
    for part in accept.split(","):
        if part.split(";")[0].strip().lower() == "image/webp":
            return "webp"
    return "jpeg"


def cover_media_type(fmt: str) -> str:
    """The ``Content-Type`` for a ``fmt`` from :func:`negotiate_cover_format`."""
    return COVER_FORMATS.get(fmt, "image/jpeg")


def resize_cover(data: bytes, *, width: int, fmt: str) -> tuple[str, bytes] | None:
    """Downscale + re-encode one cover. ``None`` means "serve the original".

    ``None`` is returned — never an exception — for every one of:

      * Pillow missing, or any decoder/encoder error whatsoever;
      * bytes that are not an image at all (a source serving an HTML error
        page, which is a real and regular occurrence here);
      * a format outside :data:`_DECODABLE_FORMATS`, animated GIF/WebP (a
        static resize of an animated cover is a behaviour change, not an
        optimisation), or dimensions past :data:`_MAX_SOURCE_PIXELS`;
      * a result that is not actually SMALLER than the input.

    That last rule is the one that makes this safe to apply unconditionally:
    whatever happens, the client never receives more bytes than it would have
    before. It also removes the need for a separate "don't upscale" branch —
    ``Image.thumbnail`` never enlarges, so a cover that is already small
    re-encodes at its native size and is kept only if that wins.

    EXIF orientation is applied rather than stripped: browsers honour the
    orientation tag on the original JPEG, so dropping it silently while
    stripping metadata would rotate people's covers.
    """
    if fmt not in COVER_FORMATS:
        return None
    try:
        from PIL import Image, ImageOps
    except Exception:  # noqa: BLE001 - no Pillow -> originals, not errors
        logger.warning("cover resize unavailable: Pillow not importable", exc_info=True)
        return None

    try:
        with Image.open(io.BytesIO(data)) as image:
            source_format = (image.format or "").upper()
            if source_format not in _DECODABLE_FORMATS:
                return None
            if (
                source_format in _ANIMATABLE_FORMATS
                and getattr(image, "n_frames", 1) > 1
            ):
                return None
            source_width, source_height = image.size
            if source_width <= 0 or source_height <= 0:
                return None
            if source_width * source_height > _MAX_SOURCE_PIXELS:
                logger.info(
                    "cover resize skipped: %dx%d exceeds the pixel ceiling",
                    source_width,
                    source_height,
                )
                return None

            # ``in_place=True`` is load-bearing, not tidiness: the default
            # exif_transpose returns ``image.copy()`` even when there is
            # nothing to rotate, and copy() forces a full-size decode. That
            # would defeat ``thumbnail``'s internal ``draft()`` call, which is
            # where most of the CPU win lives — draft lets libjpeg emit the
            # image at 1/2, 1/4 or 1/8 scale straight out of the DCT instead
            # of decoding every pixel and then throwing 98% of them away.
            # in_place does nothing at all for the overwhelmingly common
            # orientation=1 case, so draft still applies.
            ImageOps.exif_transpose(image, in_place=True)
            image.thumbnail((width, _MAX_OUTPUT_HEIGHT), Image.LANCZOS, reducing_gap=2.0)

            buffer = io.BytesIO()
            if fmt == "webp":
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if _has_alpha(image) else "RGB")
                image.save(buffer, "WEBP", quality=_WEBP_QUALITY, method=4)
            else:
                image = _flatten_to_rgb(image)
                image.save(
                    buffer,
                    "JPEG",
                    quality=_JPEG_QUALITY,
                    optimize=True,
                    progressive=True,
                )
    except Exception:  # noqa: BLE001 - a bad cover must not be a 500
        logger.info("cover resize failed; serving the original", exc_info=True)
        return None

    encoded = buffer.getvalue()
    if not encoded or len(encoded) >= len(data):
        # Re-encoding lost. Serve what we already have rather than spend both
        # the CPU and the extra bytes.
        return None
    return cover_media_type(fmt), encoded


def _has_alpha(image) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info


def _flatten_to_rgb(image):
    """RGB for JPEG, compositing any alpha onto white.

    Covers are artwork, not UI assets; a transparent margin flattened onto
    white is what every one of these sites already shows on its own page, and
    it is far better than PNG-encoding a photographic image.
    """
    if image.mode == "RGB":
        return image
    if _has_alpha(image):
        from PIL import Image

        rgba = image.convert("RGBA")
        backdrop = Image.new("RGB", rgba.size, (255, 255, 255))
        backdrop.paste(rgba, mask=rgba.split()[-1])
        return backdrop
    return image.convert("RGB")
