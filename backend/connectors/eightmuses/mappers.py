"""Map 8muses (comics.8muses.com) HTML to normalized connector models."""

from __future__ import annotations

import html
import re
from urllib.parse import quote

from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SITE_BASE = "https://comics.8muses.com"
ALBUM_PREFIX = "/comics/album/"
PAGE_SIZE = 72

TILE_RE = re.compile(
    r'<a\s+class="c-tile[^"]*"[^>]*href="([^"]+)"[^>]*title="([^"]*)"',
    re.I | re.S,
)
THUMB_RE = re.compile(r'(?:data-src|src)="(/image/th/[^"]+)"', re.I)
PICTURE_LINK_RE = re.compile(
    r'href="(/comics/picture/[^"]+/(\d+))"',
    re.I,
)
TITLE_RE = re.compile(r"<title>([^<|]+)", re.I)
META_KEYWORDS_RE = re.compile(r'<meta\s+name="keywords"\s+content="([^"]*)"', re.I)
ISSUE_NUMBER_RE = re.compile(r"issue\s*(\d+(?:\.\d+)?)", re.I)

SORT_PARAMS: dict[str, str | None] = {
    "default": None,
    "latest": "date",
    "popular": "like",
    "rating": "like",
}


def normalize_sort(sort: str | None) -> str | None:
    if sort is None or sort == "default":
        return None
    return SORT_PARAMS.get(sort, sort)


def album_id_from_href(href: str) -> str | None:
    value = href.strip()
    if value.startswith("http://") or value.startswith("https://"):
        if ALBUM_PREFIX not in value:
            return None
        value = value.split(ALBUM_PREFIX, 1)[1]
    elif value.startswith(ALBUM_PREFIX):
        value = value[len(ALBUM_PREFIX) :]
    else:
        return None
    value = value.split("?", 1)[0].strip("/")
    return value or None


def album_path(series_id: str) -> str:
    slug = series_id.strip().strip("/")
    return f"{ALBUM_PREFIX}{slug}"


def listing_path(page: int, *, sort: str | None = None) -> str:
    path = "/comics" if page <= 1 else f"/comics?page={page}"
    normalized_sort = normalize_sort(sort)
    if normalized_sort:
        separator = "&" if "?" in path else "?"
        return f"{path}{separator}sort={normalized_sort}"
    return path


def publisher_album_path(publisher_id: str, *, sort: str | None = None) -> str:
    path = album_path(publisher_id)
    normalized_sort = normalize_sort(sort)
    if normalized_sort:
        return f"{path}?sort={normalized_sort}"
    return path


def search_path(query: str) -> str:
    return f"/search?q={quote(query.strip())}"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _absolute_url(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if not value or value.startswith("data:"):
        return None
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://"):
        return "https://" + value.removeprefix("http://")
    if value.startswith("https://"):
        return value
    if value.startswith("/"):
        return f"{SITE_BASE}{value}"
    return f"{SITE_BASE}/{value.lstrip('/')}"


def thumbnail_to_full(url: str) -> str:
    return url.replace("/image/th/", "/image/fl/")


def _tile_cover(block: str) -> str | None:
    match = THUMB_RE.search(block)
    return _absolute_url(thumbnail_to_full(match.group(1))) if match else None


def _direct_child_album_id(parent_id: str, href: str) -> str | None:
    album_id = album_id_from_href(href)
    if album_id is None:
        return None
    parent = parent_id.strip().strip("/")
    if not album_id.startswith(f"{parent}/"):
        return None
    remainder = album_id[len(parent) + 1 :]
    if not remainder or "/" in remainder:
        return None
    return album_id


def parse_publishers(document: str) -> list[str]:
    publishers: list[str] = []
    seen: set[str] = set()
    for href, _title in TILE_RE.findall(document):
        album_id = album_id_from_href(href)
        if album_id is None or "/" in album_id:
            continue
        if album_id in seen:
            continue
        seen.add(album_id)
        publishers.append(album_id)
    return publishers


def parse_album_tiles(
    document: str,
    *,
    parent_id: str | None = None,
) -> list[Series]:
    items: list[Series] = []
    seen: set[str] = set()
    for href, title in TILE_RE.findall(document):
        if parent_id is None:
            album_id = album_id_from_href(href)
        else:
            album_id = _direct_child_album_id(parent_id, href)
        if album_id is None or album_id in seen:
            continue
        seen.add(album_id)
        cover_match = None
        href_pattern = re.escape(href)
        tile_match = re.search(
            rf'<a\s+class="c-tile[^"]*"[^>]*href="{href_pattern}"[^>]*>(.*?)</a>',
            document,
            re.I | re.S,
        )
        if tile_match:
            cover_match = _tile_cover(tile_match.group(1))
        items.append(
            Series(
                id=album_id,
                title=_clean_text(title) or album_id.rsplit("/", 1)[-1],
                cover_url=cover_match,
            )
        )
    return items


def parse_series_list(
    document: str,
    *,
    page: int,
    has_more: bool | None = None,
) -> PaginatedSeriesList:
    items = parse_album_tiles(document)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=0,
        api_has_more=has_more,
    )


def parse_search_results(document: str, *, page: int, query: str) -> PaginatedSeriesList:
    items = parse_album_tiles(document)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=max(len(items), 1),
        total=len(items),
        api_has_more=False,
    )


def parse_series_detail(document: str, *, series_id: str) -> Series | None:
    title_match = TITLE_RE.search(document)
    title = _clean_text(title_match.group(1)) if title_match else series_id.rsplit("/", 1)[-1]
    keywords = META_KEYWORDS_RE.search(document)
    genres = tuple(
        part.strip()
        for part in (keywords.group(1).split(",") if keywords else [])
        if part.strip()
    )
    chapters = parse_chapters(document, series_id=series_id)
    cover_url = None
    thumb_match = THUMB_RE.search(document)
    if thumb_match:
        cover_url = _absolute_url(thumbnail_to_full(thumb_match.group(1)))
    return Series(
        id=series_id,
        title=title,
        chapter_count=len(chapters),
        cover_url=cover_url,
        genres=genres,
        latest_chapter=chapters[-1].title if chapters else None,
    )


def _chapter_number(title: str, segment: str) -> float | None:
    issue_match = ISSUE_NUMBER_RE.search(title)
    if issue_match:
        return float(issue_match.group(1))
    if segment.isdigit():
        return float(segment)
    return None


def parse_chapters(document: str, *, series_id: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for href, title in TILE_RE.findall(document):
        chapter_id = _direct_child_album_id(series_id, href)
        if chapter_id is None or chapter_id in seen:
            continue
        seen.add(chapter_id)
        clean_title = _clean_text(title) or chapter_id.rsplit("/", 1)[-1]
        segment = chapter_id.rsplit("/", 1)[-1]
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=normalize_chapter_title(clean_title),
                number=_chapter_number(clean_title, segment),
                page_count=0,
            )
        )

    if chapters:
        chapters.sort(
            key=lambda item: (
                item.number is None,
                item.number if item.number is not None else 0.0,
                item.title.casefold(),
            ),
        )
        return chapters

    picture_links = PICTURE_LINK_RE.findall(document)
    if picture_links:
        chapters.append(
            Chapter(
                id=series_id,
                series_id=series_id,
                title="Complete",
                number=1.0,
                page_count=len(picture_links),
            )
        )
    return chapters


def parse_chapter_pages(document: str, *, chapter_id: str) -> list[Page]:
    picture_numbers = sorted({int(value) for _, value in PICTURE_LINK_RE.findall(document)})
    thumbs = THUMB_RE.findall(document)

    if picture_numbers:
        pages: list[Page] = []
        for page_number in picture_numbers:
            remote_url = None
            thumb_index = page_number - 1
            if 0 <= thumb_index < len(thumbs):
                remote_url = _absolute_url(thumbnail_to_full(thumbs[thumb_index]))
            if remote_url is None:
                continue
            pages.append(
                Page(
                    id=make_page_id(chapter_id, page_number),
                    chapter_id=chapter_id,
                    number=page_number,
                    remote_url=remote_url,
                )
            )
        return pages

    pages = []
    for index, thumb in enumerate(thumbs, start=1):
        remote_url = _absolute_url(thumbnail_to_full(thumb))
        if remote_url is None:
            continue
        pages.append(
            Page(
                id=make_page_id(chapter_id, index),
                chapter_id=chapter_id,
                number=index,
                remote_url=remote_url,
            )
        )
    return pages
