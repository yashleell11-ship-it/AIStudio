"""Map RawINU HTML pages to normalized connector models.

RawINU (rawinu.com) is a custom PHP aggregator, not a Madara/WordPress site.
Three things about it drive the shape of this module:

1. **It never answers 404.** A missing series, a missing chapter and a bad
   slug all return ``200`` with the *homepage* body (verified from the VPS).
   The usual ``exc.status_code == 404`` check is therefore not merely dead
   code here, it is inapplicable — nothing ever raises. Every parser that
   stands in for "does this exist?" instead returns ``None``/``[]`` when the
   marker that only a real page carries is absent, and the connector treats
   that as not-found. See ``parse_series_detail`` / ``parse_chapter_pages``.

2. **The chapter list is not on the series page.** The series HTML ships an
   empty ``<div id="list-chapter">`` filled by XHR from
   ``/app/manga/controllers/cont.Listchapter.php?slug=...``. That endpoint
   returns the *complete* list in one 11-19KB response, so the connector
   calls it directly rather than scraping anything paginated.

3. **Titles are base64.** The series name lives in
   ``<h3 data-enc="BASE64">`` with no text node. The visible breadcrumb
   carries the same string in plain text and is used as the fallback.
"""

from __future__ import annotations

import base64
import binascii
import html as html_lib
import re
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://rawinu.com"

#: RawINU renders exactly 20 cards per listing page on every view.
PAGE_SIZE = 20

#: The listing/search/genre endpoint. One path serves all three — they differ
#: only by query parameters, which is why this connector has a single
#: listing code path instead of three.
LIST_PATH = "/manga-list.html"

#: The one-shot chapter-list endpoint the series page's own XHR calls.
CHAPTER_LIST_PATH = "/app/manga/controllers/cont.Listchapter.php"

#: Domains RawINU serves cover art and page images from (``s2``/``s4``
#: subdomains are load-balanced aliases of the same store).
IMAGE_HOSTS = frozenset({"ihlv1.xyz"})

# --- listing -------------------------------------------------------------

#: Cards are parsed by splitting on this marker rather than with one large
#: regex. Scoping matters: the page also links `manga-list-genre-*.html`,
#: `manga-author-*.html`, `manga-list-magazine-*.html` and `manga-on-going.html`,
#: all of which match a naive `manga-([^"]+)\.html` and none of which are series.
CARD_MARKER = 'class="thumb-item-flow'

SERIES_LINK_RE = re.compile(
    r'series-title"[^>]*>\s*<a\s+href="/?manga-([^"]+)\.html"\s+title="([^"]*)"',
    re.I,
)
CARD_COVER_RE = re.compile(r"background-image:\s*url\('([^']+)'", re.I)
CARD_LATEST_RE = re.compile(
    r'chapter-title[^"]*"[^>]*>\s*<a[^>]*>([^<]*)</a>',
    re.I,
)
PAGINATION_BLOCK_RE = re.compile(r'pagination-wrap(.{0,4000}?)</ul>', re.S | re.I)
PAGE_NUMBER_RE = re.compile(r"[?&]page=(\d+)")

# --- series detail -------------------------------------------------------

#: The one structural marker that a real series page has and nothing else
#: does. Verified from the VPS across series pages, listing pages, search
#: pages, genre pages and the homepage that RawINU returns (with HTTP 200)
#: in place of a 404. Requiring it is what stops a soft-404 body — or a
#: listing page, which does carry an ``aria-current="page"`` breadcrumb
#: reading "List manga" — from parsing as a series named after the breadcrumb.
DETAIL_MARKER_RE = re.compile(r'class="manga-info', re.I)

TITLE_ENC_RE = re.compile(r'<h3\s+data-enc="([^"]*)"', re.I)
BREADCRUMB_TITLE_RE = re.compile(
    r'breadcrumb-item active"\s+aria-current="page">([^<]+)<', re.I
)
DETAIL_COVER_RE = re.compile(
    r'<img[^>]*class="thumbnail img-fluid"[^>]*src="([^"]+)"', re.I
)
OTHER_NAMES_RE = re.compile(r"Other names</b>\s*:\s*([^<]*)", re.I)
AUTHOR_RE = re.compile(r"manga-author-[^']*'\s*>([^<]+)</a>", re.I)
GENRE_RE = re.compile(r"manga-list-genre-[a-z0-9\-]+\.html'\s*>([^<]+)</a>", re.I)
STATUS_RE = re.compile(r'Status</b>\s*:\s*<a[^>]*>([^<]+)</a>', re.I)
SUMMARY_RE = re.compile(r'<div class="summary-content">\s*(.*?)\s*</div>', re.S | re.I)

#: Genre chips in the browse sidebar: the source's own genre vocabulary.
GENRE_ITEM_RE = re.compile(
    r'genres-item"\s+href="[^"]*manga-list-genre-([a-z0-9\-]+)\.html"[^>]*>([^<]+)</a>',
    re.I,
)

# --- chapters ------------------------------------------------------------

CHAPTER_ENTRY_RE = re.compile(
    r'<a\s+href="/?unir-([^"]+)\.html"[^>]*>\s*<li>\s*'
    r'<div class="chapter-name[^"]*">([^<]*)</div>\s*'
    r'<div class="chapter-time">([^<]*)</div>',
    re.I,
)
CHAPTER_NUMBER_RE = re.compile(r"chapter\s*[-_ ]?\s*([0-9]+(?:\.[0-9]+)?)", re.I)
TRAILING_NUMBER_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*$")

# --- chapter pages -------------------------------------------------------

#: ``data-src`` (not ``src``) — the reader lazy-loads every image, and the
#: attribute value is padded with newlines that must be stripped.
#:
#: The leading ``\s`` is load-bearing. Without it ``[^>]*?`` can consume the
#: ``data-`` prefix and match the ``src`` inside ``data-src``, which means the
#: pattern would also match a plain ``src``. RawINU emits no ``src`` on these
#: tags today, but the standard lazy-load shape is
#: ``<img src="placeholder.gif" data-src="real.jpg">`` — and against that the
#: looser pattern grabs the placeholder for every page in the chapter.
PAGE_IMAGE_RE = re.compile(r'class="chapter-img"[^>]*?\sdata-src="([^"]+)"', re.S | re.I)


# ---------------------------------------------------------------------------
# sorting
# ---------------------------------------------------------------------------

#: RawINU's own <a> sort controls use `sort` + `sort_type`. All three values
#: below were verified from the VPS to return genuinely different first pages
#: (last_update -> newest upload, views -> One Piece, name -> A-Z), so no
#: browse mode is a silent alias of another.
SORT_TO_PARAMS: dict[str, tuple[str, str]] = {
    "default": ("last_update", "DESC"),
    "latest": ("last_update", "DESC"),
    "popular": ("views", "DESC"),
    "alpha": ("name", "ASC"),
}


def normalize_sort(sort: str | None) -> tuple[str, str]:
    """Return the ``(sort, sort_type)`` pair for an app-level browse mode."""
    if not sort:
        return SORT_TO_PARAMS["default"]
    return SORT_TO_PARAMS.get(sort, SORT_TO_PARAMS["default"])


# ---------------------------------------------------------------------------
# paths and identity keys
# ---------------------------------------------------------------------------


def series_id_to_path(series_id: str) -> str:
    """Build the series URL. ``series_id`` is opaque and used verbatim."""
    return f"/manga-{series_id}.html"


def chapter_id_to_path(chapter_id: str) -> str:
    """Build the chapter URL. ``chapter_id`` is opaque and used verbatim."""
    return f"/unir-{chapter_id}.html"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    """Split a page id this module built. Never applied to upstream keys."""
    if ":" not in page_id:
        return None
    chapter_id, _, _number = page_id.rpartition(":")
    return chapter_id or None


def listing_params(
    page: int,
    *,
    sort: str | None = None,
    name: str | None = None,
    genre: str | None = None,
) -> dict[str, Any]:
    """Query for the listing endpoint, which also serves search and genre.

    ``name`` is the site's search parameter. It matters that it is ``name``
    and not ``s``/``search``: rawinu.com's robots.txt disallows ``/*?s=`` and
    ``/*?search=``, and allows everything else, so searching by ``name`` is
    within the crawl policy while the other two spellings would not be.
    """
    sort_value, sort_type = normalize_sort(sort)
    return {
        "listType": "pagination",
        "page": max(page, 1),
        "name": name or "",
        "genre": genre or "",
        "sort": sort_value,
        "sort_type": sort_type,
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _clean_text(value: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", value)).strip()


def _strip_tags(value: str) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", value))


def _clean_image_url(url: str) -> str | None:
    """Normalize a CDN image URL out of markup that is sometimes malformed.

    Two upstream defects are handled:

    * A handful of covers were rewritten by mod_pagespeed and the replacement
      leaked unescaped attributes *inside* the CSS ``url('...')`` value, e.g.
      ``...image.png" data-pagespeed-url-hash="123" onload="...(this);?imgmax=100``.
      Everything from the stray double quote on is junk and is cut.
    * ``?imgmax=N`` is appended by the templates at three different sizes.
      Measured from the VPS the CDN **ignores it** — ``?imgmax=100``,
      ``?imgmax=300`` and no parameter all return byte-identical responses —
      so it is dropped. That is not cosmetic: it collapses the browse-card and
      the series-detail cover onto one URL, so the reader's cache (and the
      image proxy) fetch a given cover once instead of once per size spelling.
    """
    candidate = html_lib.unescape(url).strip()
    for cut in ('"', "'", "<", " ", "\n", "\t"):
        if cut in candidate:
            candidate = candidate.split(cut, 1)[0]
    candidate = candidate.split("?", 1)[0]
    if not candidate.startswith(("http://", "https://", "//")):
        return None
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    return candidate or None


def _max_page(html: str) -> int:
    """Highest page number offered by the pagination control (1 when absent)."""
    block = PAGINATION_BLOCK_RE.search(html)
    if block is None:
        return 1
    numbers = [int(value) for value in PAGE_NUMBER_RE.findall(block.group(1))]
    return max(numbers) if numbers else 1


def _iter_cards(html: str) -> list[str]:
    """Split the listing body into one chunk per series card."""
    chunks = html.split(CARD_MARKER)
    return chunks[1:] if len(chunks) > 1 else []


def parse_chapter_number(name: str, chapter_id: str) -> float | None:
    """The site's own chapter number, as a stable float.

    Read from the visible chapter name first. RawINU ships a small number of
    entries with an empty ``chapter-name`` (verified: chapter 20 of
    ``ryoumin-0-nin-start-...``), and for those the trailing number of the
    chapter's own href is the only numbering the site gives.
    """
    for source in (name, chapter_id):
        if not source:
            continue
        match = CHAPTER_NUMBER_RE.search(source) or TRAILING_NUMBER_RE.search(source)
        if match is None:
            continue
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        return value
    return None


# ---------------------------------------------------------------------------
# listing / search
# ---------------------------------------------------------------------------


def parse_series_cards(html: str) -> list[Series]:
    items: list[Series] = []
    seen: set[str] = set()
    for card in _iter_cards(html):
        link = SERIES_LINK_RE.search(card)
        if link is None:
            continue
        series_id = html_lib.unescape(link.group(1))
        if not series_id or series_id in seen:
            continue
        seen.add(series_id)

        cover_url: str | None = None
        for raw in CARD_COVER_RE.findall(card):
            if "lazy-loading" in raw:
                continue
            cover_url = _clean_image_url(raw)
            if cover_url:
                break

        latest = CARD_LATEST_RE.search(card)
        latest_chapter = _clean_text(latest.group(1)) if latest else None

        items.append(
            Series(
                id=series_id,
                title=_clean_text(link.group(2)) or series_id,
                cover_url=cover_url,
                canonical_path=series_id_to_path(series_id),
                latest_chapter=latest_chapter or None,
            )
        )
    return items


def parse_series_list(
    html: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html)
    total_pages = _max_page(html)
    if total_pages <= 1:
        total = len(items)
        has_more = False
    else:
        total = total_pages * page_size
        if page >= total_pages:
            total = (total_pages - 1) * page_size + len(items)
        has_more = page < total_pages
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def parse_genres(html: str) -> list[tuple[str, str]]:
    """``(slug, label)`` for every genre chip in the browse sidebar."""
    seen: set[str] = set()
    genres: list[tuple[str, str]] = []
    for slug, label in GENRE_ITEM_RE.findall(html):
        if slug in seen:
            continue
        seen.add(slug)
        genres.append((slug, _clean_text(label)))
    return genres


# ---------------------------------------------------------------------------
# series detail
# ---------------------------------------------------------------------------


def _decode_title(html: str) -> str | None:
    """Decode ``<h3 data-enc="BASE64">``, falling back to the breadcrumb."""
    match = TITLE_ENC_RE.search(html)
    if match is not None and match.group(1):
        try:
            decoded = base64.b64decode(match.group(1), validate=True)
        except (binascii.Error, ValueError):
            decoded = b""
        text = _clean_text(decoded.decode("utf-8", "replace"))
        if text:
            return text
    crumb = BREADCRUMB_TITLE_RE.search(html)
    if crumb is not None:
        text = _clean_text(crumb.group(1))
        if text:
            return text
    return None


def parse_series_detail(html: str, series_id: str) -> Series | None:
    """Parse a series page, or ``None`` when this is not one.

    RawINU serves its homepage with HTTP 200 for any unknown slug, so a
    structural check is the only available not-found signal — there is no
    status code to test.
    """
    if DETAIL_MARKER_RE.search(html) is None:
        return None
    title = _decode_title(html)
    if title is None:
        return None

    cover = DETAIL_COVER_RE.search(html)
    cover_url = _clean_image_url(cover.group(1)) if cover else None

    authors = [_clean_text(name) for name in AUTHOR_RE.findall(html)]
    author = ", ".join(dict.fromkeys(a for a in authors if a)) or None

    genres = tuple(
        dict.fromkeys(_clean_text(name) for name in GENRE_RE.findall(html) if name.strip())
    )

    status_match = STATUS_RE.search(html)
    status = _clean_text(status_match.group(1)) if status_match else None

    summary_match = SUMMARY_RE.search(html)
    description = _strip_tags(summary_match.group(1)) if summary_match else None

    # RawINU is a RAW (untranslated) source: the card title is romaji and the
    # native Japanese title is only in "Other names". Appending it keeps the
    # native title searchable in the reader without displacing the romaji
    # title the rest of the site — and this connector's own search — uses.
    other = OTHER_NAMES_RE.search(html)
    other_names = _clean_text(other.group(1)) if other else ""
    if other_names:
        alt = f"Also known as: {other_names}"
        description = f"{description}\n\n{alt}" if description else alt

    return Series(
        id=series_id,
        title=title,
        cover_url=cover_url,
        canonical_path=series_id_to_path(series_id),
        description=description or None,
        author=author,
        artist=author,
        status=status,
        genres=genres,
    )


# ---------------------------------------------------------------------------
# chapters
# ---------------------------------------------------------------------------


def parse_chapters(html: str, series_id: str) -> list[Chapter]:
    """Parse the one-shot chapter-list response, oldest chapter first."""
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_id_raw, name, released in CHAPTER_ENTRY_RE.findall(html):
        chapter_id = html_lib.unescape(chapter_id_raw)
        if not chapter_id or chapter_id in seen:
            continue
        seen.add(chapter_id)
        title = _clean_text(name)
        number = parse_chapter_number(title, chapter_id)
        if not title:
            title = f"Chapter {number:g}" if number is not None else chapter_id
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=title,
                number=number,
                # Not published anywhere in the list markup; the connector
                # backfills it from cache once a chapter has been opened.
                page_count=0,
                release_date=_clean_text(released) or None,
            )
        )
    chapters.sort(key=lambda chapter: (chapter.number is None, chapter.number or 0.0))
    return chapters


# ---------------------------------------------------------------------------
# chapter pages
# ---------------------------------------------------------------------------


def parse_chapter_pages(html: str, chapter_id: str) -> list[Page]:
    """Every page image for a chapter, from the single reader response.

    All images are present in that one document, so a chapter costs exactly
    one request no matter how many pages it has.
    """
    pages: list[Page] = []
    seen: set[str] = set()
    for raw in PAGE_IMAGE_RE.findall(html):
        url = _clean_image_url(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        pages.append(
            Page(
                id=make_page_id(chapter_id, len(pages) + 1),
                chapter_id=chapter_id,
                number=len(pages) + 1,
                remote_url=url,
            )
        )
    return pages
