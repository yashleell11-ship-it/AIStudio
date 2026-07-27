"""Map Weeb Central HTML/HTMX partials to normalized connector models.

Weeb Central (https://weebcentral.com) is a custom (non-Madara) site that
renders everything server-side and hydrates the page through small HTMX
partial endpoints. Every view this connector needs is reachable as plain,
server-fetchable HTML:

* Browse / search  -> ``GET /search/data`` (article cards, ``limit``/``offset``
  pagination, ``sort``/``order`` filters). Used for both the catalog listing
  and keyword search so a single card parser covers both.
* Series detail    -> ``GET /series/<ID>`` (title, cover, author, status, tags,
  synopsis).
* Chapter list     -> ``GET /series/<ID>/full-chapter-list`` (the site's own
  ``hx-get`` partial) returning ``<a href="/chapters/<CHAPTER_ID>">`` rows.
* Chapter pages    -> ``GET /chapters/<CHAPTER_ID>/images?is_prev=False&
  current_page=1&reading_style=long_strip`` returning ``<img src>`` tags.
  ``reading_style=long_strip`` is REQUIRED -- without it the endpoint 307s to
  an empty page and yields no images.

Series and chapter IDs are opaque ULID-style tokens (e.g.
``01J76XYCPSY3C4BNPBRY8JMCBE``) taken verbatim from the URLs, so they
round-trip cleanly. Page IDs are ``<chapter_id>:<page_number>``.
"""

from __future__ import annotations

import html
import re
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://weebcentral.com"

# Weeb Central serves every listing / search view through the same HTMX
# partial. It accepts ``limit``/``offset`` pagination, so the connector uses it
# for both catalog browsing (empty ``text``) and keyword search.
SEARCH_DATA_PATH = "/search/data"
PAGE_SIZE = 32

# Cover art is served from a single deterministic CDN path keyed by series ID.
COVER_TEMPLATE = "https://temp.compsci88.com/cover/fallback/{series_id}.jpg"

# ULID-style identifiers used for both series and chapters.
ID_PATTERN = r"[0-9A-Z]{20,}"

# App-level browse modes -> the exact ``sort`` values Weeb Central's advanced
# search form exposes (radio inputs: Best Match / Alphabet / Popularity /
# Subscribers / Recently Added / Latest Updates).
SORT_TO_MODE: dict[str, str] = {
    "default": "Latest Updates",
    "popular": "Popularity",
    "added": "Recently Added",
    "alphabetical": "Alphabet",
}
SEARCH_SORT = "Best Match"

# --- Card / listing parsing ------------------------------------------------

# The title anchor inside each ``/search/data`` article card. Each card also
# contains a *cover* anchor to the same URL (no class, nested markup); this
# regex targets only the clean-text title anchor via its ``line-clamp`` class,
# giving exactly one (id, title) pair per card in document order.
CARD_RE = re.compile(
    r'<a href="https://weebcentral\.com/series/(' + ID_PATTERN + r')/[^"]*"'
    r'\s+class="[^"]*line-clamp[^"]*">\s*([^<]+?)\s*</a>',
    re.S,
)

# --- Chapter list parsing --------------------------------------------------

# Each row in the full-chapter-list partial:
#   <a href="https://weebcentral.com/chapters/<ID>" ...>
#       ... <span class="">Chapter 200</span> ...
#       <time ... datetime="2024-09-07T17:04:15.717Z">...</time>
#   </a>
CHAPTER_RE = re.compile(
    r'<a href="https://weebcentral\.com/chapters/(' + ID_PATTERN + r')"[^>]*>'
    r'.*?<span class="">\s*([^<]+?)\s*</span>'
    r'.*?datetime="([^"]+)"',
    re.S,
)

# --- Chapter image parsing -------------------------------------------------

IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.S)
IMG_SRC_RE = re.compile(r'src="(https://[^"]+)"')
IMG_WIDTH_RE = re.compile(r'width="(\d+)"')
IMG_HEIGHT_RE = re.compile(r'height="(\d+)"')

# --- Series detail parsing -------------------------------------------------

TITLE_H1_RE = re.compile(
    r'<h1 class="hidden md:block[^"]*">\s*([^<]+?)\s*</h1>', re.I
)
OG_TITLE_RE = re.compile(
    r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', re.I
)
OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.I
)
AUTHOR_BLOCK_RE = re.compile(
    r"<strong>Author\(s\):\s*</strong>(.*?)</li>", re.S | re.I
)
STATUS_RE = re.compile(
    r"<strong>Status:\s*</strong>\s*<a[^>]*>\s*([^<]+?)\s*</a>", re.I
)
TAGS_BLOCK_RE = re.compile(
    r"<strong>Tags?\(s\):\s*</strong>(.*?)</li>", re.S | re.I
)
ANCHOR_TEXT_RE = re.compile(r"<a[^>]*>\s*([^<]+?)\s*</a>", re.S)
DESCRIPTION_RE = re.compile(
    r"<strong>Description</strong>\s*<p[^>]*>(.*?)</p>", re.S | re.I
)


def _clean_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


# --- ID / path helpers -----------------------------------------------------


def normalize_sort(sort: str | None) -> str:
    if not sort or sort == "default":
        return SORT_TO_MODE["default"]
    return SORT_TO_MODE.get(sort, SORT_TO_MODE["default"])


def series_id_to_path(series_id: str) -> str:
    return f"/series/{series_id.strip().strip('/')}"


def series_chapter_list_path(series_id: str) -> str:
    return f"/series/{series_id.strip().strip('/')}/full-chapter-list"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/chapters/{chapter_id.strip().strip('/')}"


def chapter_images_path(chapter_id: str) -> str:
    return f"/chapters/{chapter_id.strip().strip('/')}/images"


def chapter_images_params() -> dict[str, Any]:
    # ``reading_style=long_strip`` is mandatory: it makes the endpoint return
    # every page image in one partial. Omitting it 307s to an empty response.
    return {"is_prev": "False", "current_page": 1, "reading_style": "long_strip"}


def cover_url(series_id: str) -> str:
    return COVER_TEMPLATE.format(series_id=series_id.strip().strip("/"))


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def parse_chapter_number(title: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", title)
    if match is None:
        return None
    try:
        value = float(match.group(1))
        return int(value) if value.is_integer() else value
    except ValueError:
        return None


def search_data_params(
    query: str,
    *,
    page: int,
    sort: str | None = None,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    normalized_query = query.strip()
    resolved_sort = SEARCH_SORT if normalized_query else normalize_sort(sort)
    offset = max(page - 1, 0) * page_size
    return {
        "text": normalized_query,
        "sort": resolved_sort,
        "order": "Descending",
        "official": "Any",
        "anime": "Any",
        # This is a general (non-mature) connector -- exclude adult titles from
        # both catalog browsing and search so the listing matches is_mature=False.
        "adult": "False",
        "display_mode": "Full Display",
        "limit": page_size,
        "offset": offset,
    }


# --- Parsers ---------------------------------------------------------------


def parse_series_cards(html_text: str) -> list[Series]:
    seen: set[str] = set()
    items: list[Series] = []
    for series_id, title in CARD_RE.findall(html_text):
        if series_id in seen:
            continue
        seen.add(series_id)
        items.append(
            Series(
                id=series_id,
                title=_clean_text(title),
                cover_url=cover_url(series_id),
                canonical_path=series_id_to_path(series_id),
            )
        )
    return items


def parse_series_list(
    html_text: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html_text)
    # The partial has no total count; a full page implies another page exists.
    has_more = len(items) >= page_size
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=(page - 1) * page_size + len(items),
        api_has_more=has_more,
    )


def parse_search_results(
    html_text: str,
    *,
    page: int,
    query: str,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    return parse_series_list(html_text, page=page, page_size=page_size)


def parse_series_detail(html_text: str, series_id: str) -> Series | None:
    title_match = TITLE_H1_RE.search(html_text)
    if title_match is not None:
        title = _clean_text(title_match.group(1))
    else:
        og_title = OG_TITLE_RE.search(html_text)
        if og_title is None:
            return None
        # og:title is "<Title> | Weeb Central".
        title = _clean_text(re.sub(r"\s*\|\s*Weeb Central\s*$", "", og_title.group(1)))
    if not title:
        return None

    og_image = OG_IMAGE_RE.search(html_text)
    cover = og_image.group(1) if og_image else cover_url(series_id)

    status_match = STATUS_RE.search(html_text)
    status = _clean_text(status_match.group(1)) if status_match else None

    authors: list[str] = []
    author_block = AUTHOR_BLOCK_RE.search(html_text)
    if author_block:
        authors = [_clean_text(name) for name in ANCHOR_TEXT_RE.findall(author_block.group(1))]
    author = ", ".join(a for a in authors if a) or None

    genres: tuple[str, ...] = ()
    tags_block = TAGS_BLOCK_RE.search(html_text)
    if tags_block:
        genres = tuple(
            _clean_text(name)
            for name in ANCHOR_TEXT_RE.findall(tags_block.group(1))
            if _clean_text(name)
        )

    description = None
    desc_match = DESCRIPTION_RE.search(html_text)
    if desc_match:
        description = _clean_text(re.sub(r"<[^>]+>", " ", desc_match.group(1)))

    return Series(
        id=series_id,
        title=title,
        cover_url=cover,
        canonical_path=series_id_to_path(series_id),
        description=description,
        author=author,
        status=status,
        genres=genres,
    )


def parse_chapters(html_text: str, series_id: str) -> list[Chapter]:
    parsed: list[Chapter] = []
    seen: set[str] = set()
    for chapter_id, title, datetime_value in CHAPTER_RE.findall(html_text):
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        clean_title = _clean_text(title)
        parsed.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=clean_title,
                number=parse_chapter_number(clean_title),
                # No per-chapter page count in the list; filled from cache once
                # the chapter's image partial has been fetched.
                page_count=0,
                release_date=datetime_value.strip() or None,
            )
        )
    # Weeb Central lists chapters newest-first; present oldest-first so reader
    # navigation and progress tracking move forward through the series.
    parsed.reverse()
    parsed.sort(key=lambda chapter: chapter.number if chapter.number is not None else float("inf"))
    return parsed


def parse_chapter_pages(html_text: str, chapter_id: str) -> list[Page]:
    pages: list[Page] = []
    number = 0
    for tag in IMG_TAG_RE.findall(html_text):
        src_match = IMG_SRC_RE.search(tag)
        if src_match is None:
            continue
        remote_url = src_match.group(1)
        if "broken_image" in remote_url:
            continue
        number += 1
        width_match = IMG_WIDTH_RE.search(tag)
        height_match = IMG_HEIGHT_RE.search(tag)
        pages.append(
            Page(
                id=make_page_id(chapter_id, number),
                chapter_id=chapter_id,
                number=number,
                remote_url=remote_url,
                width=int(width_match.group(1)) if width_match else None,
                height=int(height_match.group(1)) if height_match else None,
            )
        )
    return pages
