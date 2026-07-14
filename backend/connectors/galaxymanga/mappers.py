"""Map GalaxyManga (Themesia mangareader) HTML to connector models."""

from __future__ import annotations

import html
import json
import re
from typing import Any
from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://galaxymanga.io"
BROWSE_PAGE_SIZE = 24
SEARCH_PAGE_SIZE = 10

SORT_TO_ORDER: dict[str, str] = {
    "default": "update",
    "latest": "latest",
    "popular": "popular",
    "rating": "title",
}

SERIES_CARD_RE = re.compile(
    r'<a href="(?:https?://(?:www\.)?galaxymanga\.io)?/manga/([^"/]+)/"'
    r'[^>]*title="([^"]+)">\s*'
    r'<div class="limit">.*?<img[^>]+src="([^"]+)"',
    re.S | re.I,
)

CHAPTER_RE = re.compile(
    r'<li data-num="([^"]+)">\s*'
    r'<div class="chbox">\s*'
    r'<div class="eph-num">\s*'
    r'<a href="(?:https?://(?:www\.)?galaxymanga\.io)?/([^"/]+)/">\s*'
    r'<span class="chapternum">([^<]+)</span>'
    r'(?:\s*<span class="chapterdate">([^<]*)</span>)?',
    re.S | re.I,
)

TS_READER_RE = re.compile(r"ts_reader\.run\((\{.*?\})\);", re.S)


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def normalize_sort(sort: str | None) -> str:
    if not sort or sort == "default":
        return SORT_TO_ORDER["default"]
    return SORT_TO_ORDER.get(sort, sort)


def series_id_to_path(series_id: str) -> str:
    return f"/manga/{series_id.strip().strip('/')}/"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/{chapter_id.strip().strip('/')}/"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def listing_path() -> str:
    return "/manga/"


def listing_params(*, page: int, sort: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"order": normalize_sort(sort)}
    if page > 1:
        params["page"] = page
    return params


def search_path(page: int) -> str:
    if page <= 1:
        return "/"
    return f"/page/{page}/"


def search_params(query: str) -> dict[str, Any]:
    return {"s": query.strip()}


def parse_series_cards(document: str) -> list[Series]:
    seen: set[str] = set()
    items: list[Series] = []
    for series_id, title, cover_url in SERIES_CARD_RE.findall(document):
        if series_id in seen:
            continue
        seen.add(series_id)
        items.append(
            Series(
                id=series_id,
                title=_clean_text(title),
                cover_url=cover_url,
                canonical_path=series_id_to_path(series_id),
            )
        )
    return items


def parse_series_list(
    document: str,
    *,
    page: int,
    page_size: int = BROWSE_PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(document)
    has_more = len(items) >= page_size
    if has_more:
        total = page * page_size + 1
    else:
        total = (page - 1) * page_size + len(items)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def parse_search_results(
    document: str,
    *,
    page: int,
    page_size: int = SEARCH_PAGE_SIZE,
) -> PaginatedSeriesList:
    return parse_series_list(document, page=page, page_size=page_size)


def parse_series_detail(document: str, series_id: str) -> Series | None:
    title_match = re.search(
        r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>([^<]+)',
        document,
        re.I,
    )
    if title_match is None:
        title_match = re.search(r"<h1[^>]*>([^<]+)", document, re.I)
    if title_match is None:
        og = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
            document,
            re.I,
        )
        if og is None:
            return None
        title = _clean_text(og.group(1))
    else:
        title = _clean_text(title_match.group(1))

    cover_match = re.search(
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        document,
        re.I,
    )
    if cover_match is None:
        cover_match = re.search(
            r'class="thumb"[^>]*>[\s\S]*?<img[^>]+src="([^"]+)"',
            document,
            re.I,
        )
    cover_url = cover_match.group(1) if cover_match else None

    status_match = re.search(r"Status\s*<i>([^<]+)</i>", document, re.I)
    status = _clean_text(status_match.group(1)) if status_match else None

    genres = tuple(
        dict.fromkeys(
            _clean_text(name)
            for name in re.findall(
                r'href="[^"]*/genres/[^"/]+/"[^>]*>([^<]+)',
                document,
                re.I,
            )
            if _clean_text(name)
        )
    )

    desc_match = re.search(
        r'itemprop="description"[^>]*>([\s\S]*?)</div>',
        document,
        re.I,
    )
    if desc_match is None:
        desc_match = re.search(
            r'class="entry-content[^"]*"[^>]*>([\s\S]*?)</div>',
            document,
            re.I,
        )
    description = _clean_text(desc_match.group(1)) if desc_match else None

    return Series(
        id=series_id,
        title=title,
        cover_url=cover_url,
        canonical_path=series_id_to_path(series_id),
        description=description,
        status=status,
        genres=genres,
    )


def _parse_chapter_number(raw: str) -> float | None:
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


def parse_chapters(document: str, series_id: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for data_num, chapter_slug, title, release_date in CHAPTER_RE.findall(document):
        if chapter_slug in seen:
            continue
        seen.add(chapter_slug)
        number = _parse_chapter_number(data_num)
        chapters.append(
            Chapter(
                id=chapter_slug,
                series_id=series_id,
                title=_clean_text(title),
                number=number,
                page_count=0,
                release_date=_clean_text(release_date) if release_date else None,
            )
        )
    chapters.sort(
        key=lambda chapter: (
            chapter.number is None,
            chapter.number if chapter.number is not None else 0.0,
        )
    )
    return chapters


def parse_chapter_pages(document: str, chapter_id: str) -> list[Page]:
    match = TS_READER_RE.search(document)
    if match is None:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    image_urls: list[str] = []
    for source in payload.get("sources") or []:
        images = source.get("images") or []
        if isinstance(images, list) and len(images) > len(image_urls):
            image_urls = [str(url) for url in images if url]

    pages: list[Page] = []
    for index, remote_url in enumerate(image_urls, start=1):
        pages.append(
            Page(
                id=make_page_id(chapter_id, index),
                chapter_id=chapter_id,
                number=index,
                remote_url=remote_url,
            )
        )
    return pages
