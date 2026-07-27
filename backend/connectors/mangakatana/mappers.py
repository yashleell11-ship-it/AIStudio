"""Map MangaKatana HTML pages to normalized connector models."""

from __future__ import annotations

import html
import re
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://mangakatana.com"
PAGE_SIZE = 20

SERIES_ITEM_RE = re.compile(
    r'<div class="item" data-genre="[^"]*" data-id="\d+">.*?'
    r'<img src="([^"]+)"[^>]*alt="\[Cover\]".*?'
    r'<h3 class="title">\s*<a href="https?://[^"]+/manga/([^"/]+)"[^>]*>([^<]+)</a>',
    re.S | re.I,
)

CHAPTER_LINK_RE = re.compile(
    r'<div class="chapter"><a href="https?://[^"]+/manga/([^"]+)"[^>]*>([^<]+)</a>',
    re.I,
)

PAGE_SCRIPT_RE = re.compile(r"var\s+\w+\s*=\s*\[(.*?)\];", re.S)
PAGE_URL_RE = re.compile(r"'(https?://[^']+)'")

# MangaKatana's directory listing (GET /manga/, also served at /manga/page/N)
# is driven by its "Filter" form: `filter=1` marks the request as filtered and
# is REQUIRED for `order` to take effect at all — `order` alone (without
# `filter=1`) is silently ignored and the site falls back to its default
# ordering, which is what made every sort mode look identical. The order
# values recognized by the site's own <select name="order"> are exactly:
# "latest" (Latest update), "new" (New manga), "az" (A-Z), "numc" (Number of
# chapters). MangaKatana has no true "popularity" or "rating" signal on this
# endpoint, so those two app-level modes are mapped to the closest available
# proxies rather than left broken.
FILTER_MARKER = 1

SORT_TO_ORDER: dict[str, str] = {
    "default": "latest",  # Recently Updated -> site's "Latest update"
    "latest": "new",  # Latest -> site's "New manga" (newest catalog additions)
    "popular": "numc",  # Popular -> "Number of chapters" (no popularity metric exists)
    "rating": "az",  # Top Rated -> "A-Z" (no rating metric exists)
}


def normalize_sort(sort: str | None) -> str:
    if not sort or sort == "default":
        return SORT_TO_ORDER["default"]
    return SORT_TO_ORDER.get(sort, sort)


def series_id_to_path(series_id: str) -> str:
    return f"/manga/{series_id.strip().strip('/')}"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/manga/{chapter_id.strip().strip('/')}"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def parse_chapter_number(chapter_id: str) -> float | None:
    if "/" not in chapter_id:
        return None
    _, _, ref = chapter_id.rpartition("/")
    if ref.startswith("c"):
        ref = ref[1:]
    try:
        value = float(ref)
        return int(value) if value.is_integer() else value
    except ValueError:
        return None


def _clean_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def _extract_total_pages(html: str) -> int:
    pages = [int(value) for value in re.findall(r"/manga/page/(\d+)", html)]
    if pages:
        return max(pages)
    return 1


def _series_from_match(cover_url: str, series_id: str, title: str) -> Series:
    return Series(
        id=series_id,
        title=_clean_text(title),
        cover_url=cover_url,
        canonical_path=series_id_to_path(series_id),
    )


def parse_series_cards(html: str) -> list[Series]:
    seen: set[str] = set()
    items: list[Series] = []
    for cover_url, series_id, title in SERIES_ITEM_RE.findall(html):
        if series_id in seen:
            continue
        seen.add(series_id)
        items.append(_series_from_match(cover_url, series_id, title))
    return items


def parse_series_list(
    html: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html)
    total_pages = _extract_total_pages(html)
    total = total_pages * page_size
    if page == total_pages:
        total = (total_pages - 1) * page_size + len(items)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=page < total_pages,
    )


def parse_search_results(
    html: str,
    *,
    page: int,
    query: str,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html)
    if not items and query.strip():
        # Fallback when search layout differs but direct links exist.
        seen: set[str] = set()
        for series_id in re.findall(r'/manga/([a-z0-9.-]+\.\d+)"', html, re.I):
            if series_id in seen or "/" in series_id:
                continue
            seen.add(series_id)
            items.append(
                Series(
                    id=series_id,
                    title=series_id,
                    canonical_path=series_id_to_path(series_id),
                )
            )
    total_pages = _extract_total_pages(html)
    if total_pages <= 1:
        total = len(items)
        has_more = False
    else:
        total = total_pages * page_size
        has_more = page < total_pages
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def parse_series_detail(html: str, series_id: str) -> Series | None:
    title_match = re.search(r'<h1 class="heading">([^<]+)</h1>', html, re.I)
    if title_match is None:
        og_title = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html, re.I)
        if og_title is None:
            return None
        title = _clean_text(og_title.group(1))
    else:
        title = _clean_text(title_match.group(1))

    cover_match = re.search(
        r'<div class="cover">.*?<img src="([^"]+)"',
        html,
        re.S | re.I,
    )
    cover_url = cover_match.group(1) if cover_match else None

    status_match = re.search(r'<div class="status[^"]*">.*?<span>([^<]+)</span>', html, re.S | re.I)
    status = _clean_text(status_match.group(1)) if status_match else None

    genres = tuple(
        _clean_text(name)
        for name in re.findall(
            r'<div class="genres[^"]*">.*?<a href="[^"]+">([^<]+)</a>',
            html,
            re.S | re.I,
        )
    )

    author_match = re.search(r'<span class="attr">Author</span>\s*<span class="value">([^<]+)</span>', html, re.I)
    artist_match = re.search(r'<span class="attr">Artist</span>\s*<span class="value">([^<]+)</span>', html, re.I)
    description_match = re.search(
        r'<div class="summary[^"]*">(.*?)</div>',
        html,
        re.S | re.I,
    )

    return Series(
        id=series_id,
        title=title,
        cover_url=cover_url,
        canonical_path=series_id_to_path(series_id),
        description=_clean_text(re.sub(r"<[^>]+>", " ", description_match.group(1)))
        if description_match
        else None,
        author=_clean_text(author_match.group(1)) if author_match else None,
        artist=_clean_text(artist_match.group(1)) if artist_match else None,
        status=status,
        genres=genres,
    )


def parse_chapters(html: str, series_id: str) -> list[Chapter]:
    prefix = f"{series_id}/"
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_id, title in CHAPTER_LINK_RE.findall(html):
        if not chapter_id.startswith(prefix):
            continue
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        number = parse_chapter_number(chapter_id)
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=_clean_text(title),
                number=number,
                # MangaKatana series HTML has no per-chapter page counts; the connector
                # fills this from cache after the chapter reader HTML is fetched once.
                page_count=0,
            )
        )
    chapters.sort(key=lambda chapter: chapter.number if chapter.number is not None else 0)
    return chapters


def parse_chapter_pages(html: str, chapter_id: str) -> list[Page]:
    best_urls: list[str] = []
    for body in PAGE_SCRIPT_RE.findall(html):
        found = PAGE_URL_RE.findall(body)
        image_urls = [
            url
            for url in found
            if "static/img/s.png" not in url
            and any(ext in url.lower() for ext in (".jpg", ".jpeg", ".png", ".webp"))
        ]
        if len(image_urls) > len(best_urls):
            best_urls = image_urls

    pages: list[Page] = []
    for index, remote_url in enumerate(best_urls, start=1):
        pages.append(
            Page(
                id=make_page_id(chapter_id, index),
                chapter_id=chapter_id,
                number=index,
                remote_url=remote_url,
            )
        )
    return pages


def listing_path(page: int) -> str:
    return f"/manga/page/{max(page, 1)}"


def listing_params(*, sort: str | None = None) -> dict[str, Any]:
    return {"filter": FILTER_MARKER, "order": normalize_sort(sort)}


def search_params(query: str, *, page: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "search": query.strip(),
        "search_by": "m_name",
    }
    if page > 1:
        params["page"] = page
    return params
