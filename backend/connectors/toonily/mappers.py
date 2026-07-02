"""Map Toonily (Madara theme) HTML to normalized connector models."""

from __future__ import annotations

import html
import re
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SITE_BASE = "https://toonily.com"
PAGE_SIZE = 20

SERIES_ITEM_RE = re.compile(
    r'<div class="page-item-detail[^"]*">.*?'
    r'<a href="https?://[^"]+/serie/([^"/]+)/"[^>]*title="([^"]*)"[^>]*>.*?'
    r'<img[^>]+src="([^"]+)"',
    re.S | re.I,
)

RELATED_ITEM_RE = re.compile(
    r'<a href="https?://[^"]+/serie/([^"/]+)/" class="related-item"[^>]*title="([^"]*)"[^>]*>.*?'
    r'<img[^>]+src="([^"]+)"',
    re.S | re.I,
)

CHAPTER_LINK_RE = re.compile(
    r'<li class="wp-manga-chapter[^"]*">\s*'
    r'<a href="https?://[^"]+/serie/([^"]+)/">\s*([^<]+)</a>',
    re.S | re.I,
)

PAGE_IMG_RE = re.compile(
    r'<img[^>]+class="[^"]*wp-manga-chapter-img[^"]*"[^>]*(?:data-src|src)="([^"]+)"',
    re.I,
)
PAGE_IMG_RE_ALT = re.compile(
    r'<img[^>]+(?:data-src|src)="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"[^>]*class="[^"]*wp-manga-chapter-img',
    re.I,
)

PRELOADED_IMAGES_RE = re.compile(
    r"chapter_preloaded_images\s*=\s*\[(.*?)\];",
    re.S,
)
PRELOADED_URL_RE = re.compile(r"'(https?://[^']+)'")

SORT_TO_ORDER: dict[str, str] = {
    "default": "latest",
    "latest": "new-manga",
    "popular": "views",
    "rating": "ratings",
}


def normalize_sort(sort: str | None) -> str:
    if not sort or sort == "default":
        return SORT_TO_ORDER["default"]
    return SORT_TO_ORDER.get(sort, sort)


def series_id_to_path(series_id: str) -> str:
    return f"/serie/{series_id.strip().strip('/')}/"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/serie/{chapter_id.strip().strip('/')}/"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def parse_chapter_segment(segment: str) -> float | None:
    """Parse ``chapter-240`` or ``chapter-175-8`` into a chapter number."""
    value = segment.strip().strip("/")
    if not value.startswith("chapter-"):
        return None
    body = value.removeprefix("chapter-")
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", body)
    if not match:
        return None
    if match.group(2):
        return float(f"{match.group(1)}.{match.group(2)}")
    return float(match.group(1))


def parse_chapter_number(chapter_id: str) -> float | None:
    if "/" not in chapter_id:
        return None
    _, segment = chapter_id.rsplit("/", 1)
    return parse_chapter_segment(segment)


def _clean_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def _extract_total_pages(html_text: str) -> int:
    pages = [int(value) for value in re.findall(r"/webtoons/page/(\d+)/", html_text)]
    if pages:
        return max(pages)
    if 'class="next page-numbers"' in html_text or 'class="next"' in html_text:
        return 2
    return 1


def _series_from_match(cover_url: str, series_id: str, title: str) -> Series:
    return Series(
        id=series_id,
        title=_clean_text(title),
        cover_url=cover_url,
        canonical_path=series_id_to_path(series_id),
    )


def parse_series_cards(html_text: str) -> list[Series]:
    seen: set[str] = set()
    items: list[Series] = []
    for pattern in (SERIES_ITEM_RE, RELATED_ITEM_RE):
        for series_id, title, cover_url in pattern.findall(html_text):
            if series_id in seen:
                continue
            seen.add(series_id)
            items.append(_series_from_match(cover_url, series_id, title))
    return items


def parse_series_list(
    html_text: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html_text)
    total_pages = _extract_total_pages(html_text)
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
    html_text: str,
    *,
    page: int,
    query: str,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html_text)
    if not items and query.strip():
        seen: set[str] = set()
        for series_id in re.findall(r'/serie/([a-z0-9-]+)/', html_text, re.I):
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
    total_pages = _extract_total_pages(html_text)
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


def parse_series_detail(html_text: str, series_id: str) -> Series | None:
    title_match = re.search(
        r'<div class="post-title"><h1>([^<]+?)(?:\s*<span[^>]*>.*?</span>)?\s*</h1>',
        html_text,
        re.S | re.I,
    )
    if title_match is None:
        og_title = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
            html_text,
            re.I,
        )
        if og_title is None:
            return None
        title = _clean_text(og_title.group(1))
    else:
        title = _clean_text(title_match.group(1))

    cover_match = re.search(
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        html_text,
        re.I,
    )
    if cover_match is None:
        cover_match = re.search(
            r'<div class="summary_image">.*?<img[^>]+src="([^"]+)"',
            html_text,
            re.S | re.I,
        )
    cover_url = cover_match.group(1) if cover_match else None

    status_match = re.search(
        r'<h5>Status</h5>\s*</div>\s*<div class="summary-content">\s*([^<]+)',
        html_text,
        re.S | re.I,
    )
    status = _clean_text(status_match.group(1)) if status_match else None

    genres = tuple(
        _clean_text(name)
        for name in re.findall(
            r'<div class="genres-content">.*?<a[^>]*>([^<]+)</a>',
            html_text,
            re.S | re.I,
        )
    )

    author_match = re.search(
        r'<h5>Writer\(s\)</h5>\s*</div>\s*<div class="summary-content">.*?<a[^>]*>([^<]+)</a>',
        html_text,
        re.S | re.I,
    )
    artist_match = re.search(
        r'<h5>Artist\(s\)</h5>\s*</div>\s*<div class="summary-content">.*?<a[^>]*>([^<]+)</a>',
        html_text,
        re.S | re.I,
    )
    description_match = re.search(
        r'<div class="summary__content[^"]*">(.*?)</div>',
        html_text,
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


def parse_chapters(html_text: str, series_id: str) -> list[Chapter]:
    prefix = f"{series_id}/"
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_id, title in CHAPTER_LINK_RE.findall(html_text):
        if not chapter_id.startswith(prefix):
            continue
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        number = parse_chapter_number(chapter_id)
        normalized_title = normalize_chapter_title(_clean_text(title)) or _clean_text(title)
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=normalized_title,
                number=number,
                page_count=0,
            )
        )
    chapters.sort(key=lambda chapter: chapter.number if chapter.number is not None else 0.0)
    return chapters


def parse_chapter_pages(html_text: str, chapter_id: str) -> list[Page]:
    image_urls: list[str] = []
    for pattern in (PAGE_IMG_RE, PAGE_IMG_RE_ALT):
        for url in pattern.findall(html_text):
            if url not in image_urls:
                image_urls.append(url)

    if not image_urls:
        for body in PRELOADED_IMAGES_RE.findall(html_text):
            for url in PRELOADED_URL_RE.findall(body):
                if url not in image_urls:
                    image_urls.append(url)

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


def listing_path(page: int) -> str:
    if page <= 1:
        return "/webtoons/"
    return f"/webtoons/page/{page}/"


def listing_params(*, sort: str | None = None) -> dict[str, Any]:
    order = normalize_sort(sort)
    if order == SORT_TO_ORDER["default"]:
        return {}
    return {"m_orderby": order}


def search_params(query: str, *, page: int) -> dict[str, Any]:
    params: dict[str, Any] = {"s": query.strip()}
    if page > 1:
        params["paged"] = page
    return params
