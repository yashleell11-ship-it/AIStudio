"""Server-side image downscaling — the ``?w=`` parameter on the two proxies.

This docstring is about COVERS, which came first and are the big win. Page
images reuse the same machinery under a much tighter set of guards, and the
measurements that forced those guards are in the "page images" section at the
bottom of this file. Read that before touching anything shared.

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

# libwebp's effort dial, and the one knob where covers and pages genuinely want
# different answers. Measured on the VPS re-encoding a real 720x14668 page at
# w=400: method 0 = 115 ms/251 KB, 2 = 172 ms/203 KB, 4 = 351 ms/197 KB,
# 6 = 702 ms/191 KB. A cover pays its CPU ONCE and is then served from
# ``source_cover_cache`` forever, so it buys the last 3% of bytes at method 4.
# A page image is never stored (see the page section below), so it pays that
# CPU on every single request of every read — at which point method 2 is the
# right end of the curve: half the CPU for 3% more bytes.
_COVER_WEBP_METHOD = 4
_PAGE_WEBP_METHOD = 2

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


#: Neither the ``Accept`` negotiation nor the media-type lookup is specific to
#: covers — the page proxy below does exactly the same thing, so clients only
#: ever learn one rule. The ``cover_`` names came first and are kept so the
#: cover route and its tests are untouched by the page path adopting them.
negotiate_image_format = negotiate_cover_format
image_media_type = cover_media_type


def _render(
    data: bytes,
    *,
    width: int,
    fmt: str,
    max_source_pixels: int,
    max_output_height: int,
    webp_method: int,
    min_downscale_ratio: float | None,
) -> tuple[str, bytes] | None:
    """The decode/downscale/encode core, shared by covers and page images.

    Every rejection above ``thumbnail`` is decided from the container HEADER
    alone — ``Image.open`` is lazy, so format, frame count and dimensions all
    come out of the first few hundred bytes. Measured across 24 real page
    images on the VPS that decision costs 0.04-0.77 ms, which is what makes it
    safe to put this in front of the page proxy, where the overwhelmingly
    common answer is "don't touch it".
    """
    if fmt not in COVER_FORMATS:
        return None
    try:
        from PIL import Image, ImageOps
    except Exception:  # noqa: BLE001 - no Pillow -> originals, not errors
        logger.warning("image resize unavailable: Pillow not importable", exc_info=True)
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
            if (
                min_downscale_ratio is not None
                and source_width < width * min_downscale_ratio
            ):
                return None
            if source_width * source_height > max_source_pixels:
                logger.info(
                    "image resize skipped: %dx%d exceeds the pixel ceiling",
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
            #
            # ``reducing_gap=2.0`` is what thumbnail passes to draft, so the
            # DCT scaling stops at 2x the target and LANCZOS does the last
            # step from real pixels. Drafting all the way to the target is
            # measurably cheaper (59 ms vs 89 ms on a 1114x1600 scan) and
            # measurably softer; on a manga page the sharpness is the product.
            # There is no draft equivalent for PNG or WebP, which is part of
            # why the page path caps source megapixels rather than trusting
            # the cheap path to exist.
            ImageOps.exif_transpose(image, in_place=True)
            image.thumbnail(
                (width, max_output_height), Image.LANCZOS, reducing_gap=2.0
            )

            buffer = io.BytesIO()
            if fmt == "webp":
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if _has_alpha(image) else "RGB")
                image.save(buffer, "WEBP", quality=_WEBP_QUALITY, method=webp_method)
            else:
                image = _flatten_to_rgb(image)
                image.save(
                    buffer,
                    "JPEG",
                    quality=_JPEG_QUALITY,
                    optimize=True,
                    progressive=True,
                )
    except Exception:  # noqa: BLE001 - a bad image must not be a 500
        logger.info("image resize failed; serving the original", exc_info=True)
        return None

    encoded = buffer.getvalue()
    if not encoded or len(encoded) >= len(data):
        # Re-encoding lost. Serve what we already have rather than spend both
        # the CPU and the extra bytes.
        return None
    return image_media_type(fmt), encoded


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
    return _render(
        data,
        width=width,
        fmt=fmt,
        # Read at call time, not bound as a default, so the ceiling stays
        # monkeypatchable from a test.
        max_source_pixels=_MAX_SOURCE_PIXELS,
        max_output_height=_MAX_OUTPUT_HEIGHT,
        webp_method=_COVER_WEBP_METHOD,
        # A cover has no minimum: ``thumbnail`` never enlarges, so a small
        # cover simply re-encodes at its native size and the never-bigger rule
        # decides whether that was worth it.
        min_downscale_ratio=None,
    )


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


# ---------------------------------------------------------------------------
# page images (the ``?w=`` parameter on the reader's page proxy)
# ---------------------------------------------------------------------------
#
# MEASURED FIRST, BUILT SECOND — and the measurement is why this is far more
# conservative than the cover path above. 24 real page images were pulled from
# eight live sources onto the VPS itself (2 vCPU, 3.8 GB, Pillow 12.3), which
# is where every number below comes from:
#
#   omegascans    720 x 14668   3.1 MB     galaxymanga   720 x  9000   488 KB
#   aurorascans   800 x 14405   2.2 MB     manhwaclub    720 x 10864   443 KB
#   asurascans    800 x 15072   932 KB     rawkuma      1120 x  1600   729 KB
#   mangadex     1622 x  1152   711 KB     mangapill    1114 x  1600   252 KB
#
# THE FIRST RESULT KILLED THE OBVIOUS DESIGN. Webtoon sources publish strips
# 720-800 px wide — at or BELOW the device-pixel width a phone already asks
# for, because a 400 CSS px column at DPR 3 wants 1200. Counting how many of
# the 24 a width request would actually downscale at all:
#
#     Android DPR 3    1 of 24        desktop DPR 1   10 of 24
#     iPhone  DPR 3    1 of 24        desktop DPR 2    1 of 24
#     tablet  DPR 2    1 of 24        Android DPR 2.6  8 of 24 (7 under 1.11x)
#
# So this does NOT fix the reader feeling like 30 Hz on Android. That is a
# 720x14668 strip decoding to ~42 MB of client-side bitmap because it is TALL,
# and width is the only axis a resize is allowed to touch here. The fix for
# that lives in the client, decoding at a reduced scale. What this route
# parameter buys is (a) the desktop case, where a 1120x1600 scan at w=800 goes
# 729 KB -> 127 KB, and (b) the ABILITY for a client to ask for fewer pixels
# than DPR x CSS, which today it has no way to express at all.
#
# WHY THERE IS NO CACHE, AND WHY THAT CHANGES EVERYTHING. Chapter images are
# never stored server-side — a library is multi-GB against a ~20 GB budget.
# The cover path is cheap because its CPU is amortised: 133 ms once per
# (series, width, format), then 0.04 ms forever. Nothing here amortises. Every
# page request pays the full render, and a chapter is 17-151 pages against a
# browse grid's 24 covers. That is the whole reason for the ceiling below.
#
# THE CEILING IS A LATENCY BUDGET. Cost scales with SOURCE megapixels, at a
# measured 74-125 ms/MP on the VPS. The corpus splits cleanly in two: every
# page-format scan is 0.93-1.87 MP (105-240 ms) and every webtoon strip is
# 6.05-12.06 MP (500-1700 ms). Refusing above 4 MP keeps the worst case near
# 320 ms, and costs nothing real, because at DPR >= 2.6 the strips were going
# to be passed through anyway. What it buys:
#
#   * latency. The resize happens before a single byte is sent, so rendering a
#     strip would ADD 0.5-1.7 s to a page the reader is waiting on — making
#     the reader slower, which is the opposite of the point.
#   * the box. Five concurrent strip renders (the reader preloads five pages
#     ahead) measured 2.36 s of wall time with both vCPUs pinned, and took RSS
#     from 576 MB to 1082 MB on a box with ~2.5 GB available that also runs
#     everything else.
#   * the DoS bound. The route's 60/minute limit is the only other brake. At
#     4 MP that is 60 x 320 ms = ~19 s of CPU per minute per caller, a third
#     of one core. Uncapped it is 60 x 1700 ms = 102 s per minute — more than
#     both cores, from one rate-limited caller.
#
# Format is not a special case: JPEG decodes at ~11 ms/MP, PNG ~9, WebP ~43
# (WebP has no draft equivalent, so it eats the full decode). All are bounded
# by the same megapixel ceiling, and decode is not the dominant cost anyway —
# the encode is.

#: The closed set of widths the page proxy will render, snapped UP so a client
#: is never handed something SOFTER than it asked for. These are the device
#: widths the clients actually produce: 480 (DPR-1 phone or a data-saver
#: mode), 720/800 (a 400 CSS px column at DPR 2, and desktop's 768 px cap at
#: DPR 1), 1080/1200 (that column at DPR 2.6 and 3), 1440/1600 (a 768 px
#: column at DPR 2). Unlike the cover ladder, a request ABOVE the top rung
#: does NOT clamp down to it — see :func:`snap_page_width`.
PAGE_WIDTHS: tuple[int, ...] = (480, 720, 800, 1080, 1200, 1440, 1600)

#: The CPU ceiling, expressed where the cost actually lives: SOURCE pixels.
#: See the section header — 4 MP is the line between the page-format scans
#: (0.93-1.87 MP, ~105-240 ms) and the long webtoon strips (6-12 MP,
#: 0.5-1.7 s) in a real corpus, with room for a double-page spread.
_MAX_PAGE_SOURCE_PIXELS = 4_000_000

#: Render only when the source is at least this much wider than the request.
#: Below it the resize is not paying for itself: a 1120 px scan asked for
#: 1080 px would cost ~150 ms to shave 4% of the width, and the bytes it saved
#: would come almost entirely from re-encoding sharp line art at q80 rather
#: than from the resize. Serving the original is both cheaper and sharper, and
#: it can never be wrong — the client gets MORE pixels than it asked for,
#: never fewer.
_MIN_PAGE_DOWNSCALE_RATIO = 1.25

#: Height is deliberately NOT clamped: for a 720x14668 strip, width is the
#: only meaningful axis and binding the height would silently narrow the page.
#: This exists purely so ``thumbnail`` has a second element to ignore; the
#: megapixel ceiling above is what actually bounds the work.
_UNBOUNDED_HEIGHT = 1 << 30


def snap_page_width(requested: int | None) -> int | None:
    """Snap a requested width onto :data:`PAGE_WIDTHS`.

    ``None`` (no ``?w=``) means "the original, untouched" and stays ``None``.
    Anything else snaps UP to the first rung at least as large, so the client
    is never handed fewer pixels than it asked for.

    Above the top rung this returns ``None`` — the original — where the cover
    ladder instead clamps down to its largest width. The divergence is
    deliberate and is the sharpness rule: a 4000 px cover request is nonsense
    (covers are thumbnails) but a 2400 px page request from a large tablet is
    real, and clamping it to 1600 would answer a request for detail by
    removing detail. Serving the original is the honest answer, and it costs
    the box nothing.
    """
    if requested is None:
        return None
    for width in PAGE_WIDTHS:
        if requested <= width:
            return width
    return None


def resize_page(data: bytes, *, width: int, fmt: str) -> tuple[str, bytes] | None:
    """Downscale + re-encode one page image. ``None`` means "serve the original".

    Transient by construction: bytes in, bytes out, nothing written down. This
    is the no-chapter-images rule, so unlike :func:`resize_cover` there is no
    cache behind it and every call pays in full.

    ``None`` — never an exception — covers every fallback :func:`resize_cover`
    lists (missing Pillow, junk bytes, an HTML error page, an animated or
    unknown format, a result that is not smaller), plus two of its own:

      * the source is not at least :data:`_MIN_PAGE_DOWNSCALE_RATIO` wider
        than the request, which is the no-upscale rule and the don't-soften-it
        rule in one. It also makes ``X-Page-Width`` exact: whenever this
        renders at all, the output really is ``width`` px wide.
      * the source is past :data:`_MAX_PAGE_SOURCE_PIXELS`, the CPU ceiling.

    Both are decided from the header, so declining costs well under a
    millisecond — which matters, because declining is the common answer.
    """
    return _render(
        data,
        width=width,
        fmt=fmt,
        max_source_pixels=_MAX_PAGE_SOURCE_PIXELS,
        max_output_height=_UNBOUNDED_HEIGHT,
        webp_method=_PAGE_WEBP_METHOD,
        min_downscale_ratio=_MIN_PAGE_DOWNSCALE_RATIO,
    )
