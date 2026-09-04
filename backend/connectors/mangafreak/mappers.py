"""Map MangaFreak HTML pages to normalized connector models.

MangaFreak serves four distinct listing shapes, one per catalog view, and a
series detail page that already contains the complete chapter table. Every
parser here is pure: it takes HTML and returns models, so the connector can
share a single fetch between ``get_series`` and ``get_chapters``.
"""

from __future__ import annotations

import html as html_module
import re

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

#: mangafreak.net 301s to this host. The shared HTTP client derives its
#: redirect allowlist from its own base URL and rejects any off-domain hop,
#: so pointing the client at mangafreak.net would make EVERY request fail as
#: a blocked redirect. Using the real host also saves a round trip per call.
SITE_BASE = "https://ww3.mangafreak.me"

#: The CDN that serves covers and page images.
IMAGE_HOST = "images.mangafreak.me"

# Each catalog view paginates at its own fixed size (counted from the VPS).
MANGALIST_PAGE_SIZE = 18
LATEST_PAGE_SIZE = 30
RANKING_PAGE_SIZE = 15
SEARCH_PAGE_SIZE = 25

# --- listing item blocks -------------------------------------------------
# Splitting on the item marker and pulling fields out of each block is
# deliberately used instead of one giant regex per shape: these templates
# carry ragged tab indentation and HTML comments between the fields, which a
# single anchored pattern breaks on the first time the site reflows a row.
_LIST_ITEM_MARKER = '<div class="list_item">'
_LATEST_ITEM_MARKER = '<div class="latest_releases_item">'
_SEARCH_ITEM_MARKER = '<div class="manga_search_item">'
_RANKING_ITEM_MARKER = '<div class="ranking_item">'

_SERIES_HREF_RE = re.compile(r'href="/Manga/([^"]+)"')
_IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
_LIST_TITLE_RE = re.compile(
    r"<h3>\s*(?:<!--.*?-->\s*)?<a href=\"/Manga/[^\"]*\">(.*?)</a>", re.S | re.I
)
_LIST_STATUS_RE = re.compile(r"<h6>Status:</h6>\s*([^<]*)", re.I)
_LIST_RELEASED_RE = re.compile(r"<h6>Released:</h6>\s*([^<]*)", re.I)
_LATEST_TITLE_RE = re.compile(
    r'<a href="/Manga/([^"]+)"><strong>(.*?)</strong></a>', re.S | re.I
)
_LATEST_CHAPTER_RE = re.compile(r'<a href="/(Read1_[^"]+)">(.*?)</a>', re.S | re.I)
_SEARCH_TITLE_RE = re.compile(
    r'<h3>\s*<a href="/Manga/([^"]+)">(.*?)</a>', re.S | re.I
)
_RANKING_TITLE_RE = re.compile(
    r'<a href="/Manga/([^"]+)"><h3 class="title">(.*?)</h3></a>', re.S | re.I
)
_RANKING_AUTHOR_RE = re.compile(r"<div>Sensei Name\s*-\s*([^<]*)</div>", re.I)
_PUBLISHED_RE = re.compile(r"([0-9a-z.]+)\s*(?:Chapters\s*)?Published\.\s*\(([^)]*)\)", re.I)
_CHAPTER_COUNT_RE = re.compile(r"([0-9a-z.]+)\s*Chapters", re.I)

# --- series detail -------------------------------------------------------
#: Markers that only ever appear on a real series page. MangaFreak answers a
#: request for a series that does not exist with HTTP 200 and the FULL
#: HOMEPAGE rather than a 404, so "the fetch succeeded" proves nothing --
#: without this check a bogus key silently yields a homepage-shaped parse.
_DETAIL_MARKERS = ("manga_series_image", "manga_series_data")

_DETAIL_TITLE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
_DETAIL_COVER_RE = re.compile(
    r'<div class="manga_series_image">\s*<img[^>]+src="([^"]+)"', re.S | re.I
)
_DETAIL_STATUS_RE = re.compile(r"<div>\s*This is ([A-Za-z\- ]+?) series\s*</div>", re.I)
_DETAIL_AUTHOR_RE = re.compile(r"<div>\s*Written By:\s*([^<]*)</div>", re.I)
_DETAIL_ARTIST_RE = re.compile(r"<div>\s*Illustrated By:\s*([^<]*)</div>", re.I)
_DETAIL_GENRES_BLOCK_RE = re.compile(
    r'<div class="series_sub_genre_list">(.*?)</div>', re.S | re.I
)
_GENRE_LINK_RE = re.compile(r'<a href="/Genre/[^"]*">([^<]*)</a>', re.I)
_DETAIL_DESC_RE = re.compile(
    r'<div class="manga_series_description">\s*<div>Synopsis</div>\s*<p>(.*?)</p>',
    re.S | re.I,
)

#: One row of the chapter table on the series detail page: the reader link,
#: its label, and the release date in the next cell.
_CHAPTER_ROW_RE = re.compile(
    r'<a class="chapter-link" href="/(Read1_[^"]+)"[^>]*>(.*?)</a>\s*</td>\s*'
    r"<td>\s*([^<]*?)\s*</td>",
    re.S | re.I,
)

#: Page images on the reader page. Anchoring to the CDN's ``/mangas/`` prefix
#: is what keeps the six social-share icons (``/share/*.webp``) that sit in
#: the same document out of the page list.
_PAGE_IMAGE_RE = re.compile(
    r'<img[^>]+src="(https://images\.mangafreak\.me/mangas/[^"]+)"', re.I
)

_PAGINATION_LAST_RE = re.compile(r'class="last_p"\s+href="([^"]+)"', re.I)
_PAGINATION_NUM_RE = re.compile(r'class="n_p[^"]*"[^>]*href="[^"]*?(\d+)"', re.I)

#: A chapter reference is the site's own numbering: digits, optionally with a
#: letter suffix marking a split release (1053a, 1053b, 430f).
_CHAPTER_REF_RE = re.compile(r"^(\d+(?:\.\d+)?)([a-z]*)$", re.I)


def _clean(value: str) -> str:
    """Strip tags, collapse whitespace and decode entities."""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def series_path(series_key: str) -> str:
    return f"/Manga/{series_key.strip().strip('/')}"


def chapter_path(chapter_key: str) -> str:
    return f"/{chapter_key.strip().strip('/')}"


def make_page_id(chapter_key: str, page_number: int) -> str:
    return f"{chapter_key}:{page_number}"


def page_id_chapter_key(page_id: str) -> str | None:
    """Recover the chapter key from a page id.

    Chapter keys are opaque and contain underscores but never a colon, so the
    final colon is an unambiguous separator.
    """
    if ":" not in page_id:
        return None
    chapter_key, _, _number = page_id.rpartition(":")
    return chapter_key or None


def parse_chapter_number(chapter_key: str) -> float | None:
    """Stable float from MangaFreak's own chapter numbering.

    The site marks split releases with a letter suffix (``1053a``, ``1053b``,
    ``430f``). Those are folded into the fraction -- ``1053a`` -> 1053.01 --
    so a split sorts immediately after its base chapter and never collides
    with it, while a plain ``1053`` stays exactly 1053.0.
    """
    _, _, ref = chapter_key.strip().rpartition("_")
    match = _CHAPTER_REF_RE.match(ref)
    if match is None:
        return None
    number = float(match.group(1))
    for index, letter in enumerate(match.group(2).lower()):
        number += (ord(letter) - 96) / (100.0 ** (index + 1))
    return number


def extract_total_pages(html: str) -> int:
    """Total pages from the paginator, via the explicit "last page" link."""
    last = _PAGINATION_LAST_RE.search(html)
    if last is not None:
        numbers = re.findall(r"(\d+)", last.group(1))
        if numbers:
            return max(1, int(numbers[-1]))
    numbers = [int(value) for value in _PAGINATION_NUM_RE.findall(html)]
    return max(numbers) if numbers else 1


def _blocks(html: str, marker: str) -> list[str]:
    parts = html.split(marker)
    return parts[1:] if len(parts) > 1 else []


def _paginate(
    items: list[Series], *, page: int, page_size: int, total_pages: int
) -> PaginatedSeriesList:
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


def _dedupe(items: list[Series]) -> list[Series]:
    seen: set[str] = set()
    unique: list[Series] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        unique.append(item)
    return unique


def _chapter_count(text: str) -> int:
    """Leading integer of a "23 Chapters" / "187e Chapters" style count."""
    match = re.match(r"\s*(\d+)", text or "")
    return int(match.group(1)) if match else 0


def parse_mangalist(html: str, *, page: int) -> PaginatedSeriesList:
    """Parse the A-Z directory (``/Mangalist/All/N``)."""
    items: list[Series] = []
    for block in _blocks(html, _LIST_ITEM_MARKER):
        key_match = _SERIES_HREF_RE.search(block)
        title_match = _LIST_TITLE_RE.search(block)
        if key_match is None or title_match is None:
            continue
        cover = _IMG_SRC_RE.search(block)
        status = _LIST_STATUS_RE.search(block)
        released = _LIST_RELEASED_RE.search(block)
        key = key_match.group(1)
        items.append(
            Series(
                id=key,
                title=_clean(title_match.group(1)),
                canonical_path=series_path(key),
                cover_url=cover.group(1) if cover else None,
                status=_clean(status.group(1)) if status else None,
                chapter_count=_chapter_count(released.group(1)) if released else 0,
            )
        )
    return _paginate(
        _dedupe(items),
        page=page,
        page_size=MANGALIST_PAGE_SIZE,
        total_pages=extract_total_pages(html),
    )


def parse_latest_releases(html: str, *, page: int) -> PaginatedSeriesList:
    """Parse the recently-updated view (``/Latest_Releases/N``)."""
    items: list[Series] = []
    for block in _blocks(html, _LATEST_ITEM_MARKER):
        title_match = _LATEST_TITLE_RE.search(block)
        if title_match is None:
            continue
        cover = _IMG_SRC_RE.search(block)
        latest = _LATEST_CHAPTER_RE.search(block)
        key = title_match.group(1)
        items.append(
            Series(
                id=key,
                title=_clean(title_match.group(2)),
                canonical_path=series_path(key),
                cover_url=cover.group(1) if cover else None,
                latest_chapter=_clean(latest.group(2)) if latest else None,
            )
        )
    return _paginate(
        _dedupe(items),
        page=page,
        page_size=LATEST_PAGE_SIZE,
        total_pages=extract_total_pages(html),
    )


def parse_ranking(html: str, *, page: int) -> PaginatedSeriesList:
    """Parse a ranked genre view (``/Genre/<Genre>/N``, ``/Genre/All/N``)."""
    items: list[Series] = []
    for block in _blocks(html, _RANKING_ITEM_MARKER):
        title_match = _RANKING_TITLE_RE.search(block)
        if title_match is None:
            continue
        cover = _IMG_SRC_RE.search(block)
        author = _RANKING_AUTHOR_RE.search(block)
        published = _PUBLISHED_RE.search(block)
        key = title_match.group(1)
        items.append(
            Series(
                id=key,
                title=_clean(title_match.group(2)),
                canonical_path=series_path(key),
                cover_url=cover.group(1) if cover else None,
                author=_clean(author.group(1)) if author else None,
                chapter_count=_chapter_count(published.group(1)) if published else 0,
                status=_clean(published.group(2)) if published else None,
            )
        )
    return _paginate(
        _dedupe(items),
        page=page,
        page_size=RANKING_PAGE_SIZE,
        total_pages=extract_total_pages(html),
    )


def parse_search_results(html: str, *, page: int) -> PaginatedSeriesList:
    """Parse the search view (``/Find/<query>``)."""
    items: list[Series] = []
    for block in _blocks(html, _SEARCH_ITEM_MARKER):
        title_match = _SEARCH_TITLE_RE.search(block)
        if title_match is None:
            continue
        cover = _IMG_SRC_RE.search(block)
        published = _PUBLISHED_RE.search(block)
        genres_block = block.split("</h3>", 1)[-1]
        genres = tuple(
            _clean(name) for name in _GENRE_LINK_RE.findall(genres_block) if name.strip()
        )
        key = title_match.group(1)
        items.append(
            Series(
                id=key,
                title=_clean(title_match.group(2)),
                canonical_path=series_path(key),
                cover_url=cover.group(1) if cover else None,
                chapter_count=_chapter_count(published.group(1)) if published else 0,
                status=_clean(published.group(2)) if published else None,
                genres=genres,
            )
        )
    # total_pages is deliberately pinned to 1: MangaFreak's search PAGINATOR
    # IS DECORATIVE. It renders "1 2 3 »" links of the form `/Find/<q>?page=N`,
    # but the server ignores the parameter completely -- verified from the VPS,
    # `?page=1`, `?page=2`, `?p=2` and `?pages=2` all return a byte-identical
    # document (same md5), and the path form `/Find/<q>/2` returns HTTP 200
    # with zero results. Trusting the paginator would make the app re-serve
    # the SAME 25 results as page 2, 3, 4 ... forever. Search on this source
    # genuinely reaches only its first page of results.
    return _paginate(
        _dedupe(items),
        page=page,
        page_size=SEARCH_PAGE_SIZE,
        total_pages=1,
    )


def is_series_document(html: str) -> bool:
    """True when this HTML is a real series page.

    MangaFreak answers an unknown series with HTTP 200 and the homepage, so
    every detail/chapter parse must gate on structure rather than status.
    """
    return all(marker in html for marker in _DETAIL_MARKERS)


def parse_series_detail(html: str, series_key: str) -> Series | None:
    if not is_series_document(html):
        return None
    title_match = _DETAIL_TITLE_RE.search(html)
    if title_match is None:
        return None
    title = _clean(title_match.group(1))
    if not title:
        return None

    cover = _DETAIL_COVER_RE.search(html)
    status = _DETAIL_STATUS_RE.search(html)
    author = _DETAIL_AUTHOR_RE.search(html)
    artist = _DETAIL_ARTIST_RE.search(html)
    description = _DETAIL_DESC_RE.search(html)
    genres_block = _DETAIL_GENRES_BLOCK_RE.search(html)
    genres = (
        tuple(
            _clean(name)
            for name in _GENRE_LINK_RE.findall(genres_block.group(1))
            if name.strip()
        )
        if genres_block
        else ()
    )

    return Series(
        id=series_key,
        title=title,
        canonical_path=series_path(series_key),
        cover_url=cover.group(1) if cover else None,
        description=_clean(description.group(1)) if description else None,
        author=_clean(author.group(1)) or None if author else None,
        artist=_clean(artist.group(1)) or None if artist else None,
        status=_normalize_status(status.group(1)) if status else None,
        genres=genres,
    )


def _normalize_status(raw: str) -> str | None:
    """"ON-GOING" / "COMPLETED" -> title case the UI can show."""
    text = _clean(raw).replace("-", " ").strip()
    if not text:
        return None
    lowered = text.lower()
    if "going" in lowered:
        return "Ongoing"
    if "complete" in lowered:
        return "Completed"
    return text.title()


def parse_chapters(html: str, series_key: str) -> list[Chapter]:
    """Parse the chapter table carried by the series detail page."""
    if not is_series_document(html):
        return []
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_key, title, released in _CHAPTER_ROW_RE.findall(html):
        if chapter_key in seen:
            continue
        seen.add(chapter_key)
        chapters.append(
            Chapter(
                id=chapter_key,
                series_id=series_key,
                title=_clean(title),
                number=parse_chapter_number(chapter_key),
                # Page counts are only knowable from the reader page; the
                # connector backfills this from cache once a chapter is read.
                page_count=0,
                release_date=_clean(released) or None,
            )
        )
    chapters.sort(key=lambda chapter: (chapter.number is None, chapter.number or 0.0))
    return chapters


def parse_chapter_pages(html: str, chapter_key: str) -> list[Page]:
    """Parse every page image from one reader document.

    The reader ships all of a chapter's image URLs inline, so a whole chapter
    costs exactly one request -- no per-page resolution.
    """
    pages: list[Page] = []
    seen: set[str] = set()
    for url in _PAGE_IMAGE_RE.findall(html):
        if url in seen:
            continue
        seen.add(url)
        pages.append(
            Page(
                id=make_page_id(chapter_key, len(pages) + 1),
                chapter_id=chapter_key,
                number=len(pages) + 1,
                remote_url=url,
            )
        )
    return pages


def parse_genre_list(html: str) -> list[tuple[str, str]]:
    """(slug, label) pairs from the genre sidebar, minus the "All" entry."""
    block_start = html.find('class="genre_list"')
    if block_start < 0:
        return []
    block = html[block_start : block_start + 6000]
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for slug, label in re.findall(
        r'<a[^>]*href="/Genre/([^"]+)"[^>]*>([^<]*)</a>', block, re.I
    ):
        if slug in seen or slug.lower() == "all":
            continue
        seen.add(slug)
        pairs.append((slug, _clean(label) or slug.replace("_", " ")))
    return pairs
