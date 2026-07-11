"""Map 1st Kiss Manga (Madara theme) HTML to normalized connector models."""

from __future__ import annotations

import html
import re
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SITE_BASE = "https://1stkissmanga.io"
PAGE_SIZE = 20

BROWSE_CARD_SPLIT_RE = re.compile(r'(?=<div class="page-item-detail)', re.I)
SEARCH_CARD_SPLIT_RE = re.compile(r'(?=<div class="row c-tabs-item__content")', re.I)
CARD_ANCHOR_RE = re.compile(
    r'<a href="https?://[^"]+/manga/([^"/]+)/"[^>]*title="([^"]*)"',
    re.I,
)
CARD_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)

CHAPTER_LINK_RE = re.compile(
    r'<li class="wp-manga-chapter[^"]*">\s*'
    r'<a[^>]+href="(?:https?://[^"]+)?/manga/([^"]+)/"[^>]*>\s*([^<]+)</a>',
    re.S | re.I,
)

CHAPTER_IMG_TAG_RE = re.compile(r"<img\b[^>]*wp-manga-chapter-img[^>]*>", re.I)
_IMG_DATA_SRC_RE = re.compile(r'data-src="\s*([^"]+?)\s*"', re.I)
_IMG_DATA_LAZY_SRC_RE = re.compile(r'data-lazy-src="\s*([^"]+?)\s*"', re.I)
_IMG_SRC_RE = re.compile(r'(?<!-)\bsrc="\s*([^"]+?)\s*"', re.I)

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
    return f"/manga/{series_id.strip().strip('/')}/"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/manga/{chapter_id.strip().strip('/')}/"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def parse_chapter_segment(segment: str) -> float | None:
    parts = _parse_chapter_segment_parts(segment)
    if parts is None:
        return None
    return _display_number_from_parts(parts)


def _parse_chapter_segment_parts(segment: str) -> tuple[int, int, int] | None:
    value = segment.strip().strip("/")
    if not value.startswith("chapter-"):
        return None
    body = value.removeprefix("chapter-")
    match = re.fullmatch(r"(\d+)(?:-(\d+))?(?:_(\d+))?", body)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) is not None else 0
    part = int(match.group(3)) if match.group(3) is not None else 0
    return (major, minor, part)


def _display_number_from_parts(parts: tuple[int, int, int]) -> float:
    major, minor, _part = parts
    if minor:
        return float(f"{major}.{minor}")
    return float(major)


def chapter_id_sort_key(chapter_id: str) -> tuple[int, int, int]:
    if "/" not in chapter_id:
        return (2**31 - 1, 2**31 - 1, 2**31 - 1)
    _, segment = chapter_id.rsplit("/", 1)
    parts = _parse_chapter_segment_parts(segment)
    if parts is None:
        return (2**31 - 1, 2**31 - 1, 2**31 - 1)
    return parts


def parse_chapter_number(chapter_id: str) -> float | None:
    if "/" not in chapter_id:
        return None
    _, segment = chapter_id.rsplit("/", 1)
    return parse_chapter_segment(segment)


def _clean_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def _extract_total_pages(html_text: str) -> int:
    pages = [int(value) for value in re.findall(r"/manga/page/(\d+)/", html_text)]
    if pages:
        return max(pages)
    if 'class="next page-numbers"' in html_text or 'class="next"' in html_text:
        return 2
    return 1


def _extract_image_url(tag: str) -> str | None:
    for pattern in (_IMG_DATA_SRC_RE, _IMG_DATA_LAZY_SRC_RE, _IMG_SRC_RE):
        match = pattern.search(tag)
        if match:
            url = match.group(1).strip()
            if url.startswith("http"):
                return url
    return None


def _card_cover_url(segment: str) -> str | None:
    for tag in CARD_IMG_TAG_RE.findall(segment):
        url = _extract_image_url(tag)
        if url:
            return url
    return None


def _parse_cards(html_text: str, split_re: re.Pattern[str], marker: str) -> list[Series]:
    items: list[Series] = []
    seen: set[str] = set()
    for segment in split_re.split(html_text):
        if marker not in segment[:80]:
            continue
        anchor = CARD_ANCHOR_RE.search(segment)
        if anchor is None:
            continue
        slug, title = anchor.group(1), anchor.group(2)
        if slug in seen:
            continue
        seen.add(slug)
        items.append(
            Series(
                id=slug,
                title=_clean_text(title),
                cover_url=_card_cover_url(segment),
                canonical_path=series_id_to_path(slug),
            )
        )
    return items


def parse_series_cards(html_text: str) -> list[Series]:
    return _parse_cards(html_text, BROWSE_CARD_SPLIT_RE, "page-item-detail")


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
    items = _parse_cards(html_text, SEARCH_CARD_SPLIT_RE, "c-tabs-item__content")

    if not items and query.strip():
        seen: set[str] = set()
        for series_id in re.findall(r"/manga/([a-z0-9-]+)/", html_text, re.I):
            if series_id in seen:
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
        r'<div class="post-title">.*?<h1>\s*([^<]+)',
        html_text,
        re.S | re.I,
    )
    title = _clean_text(title_match.group(1)) if title_match else ""
    if not title:
        og_title = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
            html_text,
            re.I,
        )
        if og_title is None:
            return None
        title = _clean_text(og_title.group(1))
    if not title:
        return None

    cover_match = re.search(
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        html_text,
        re.I,
    )
    if cover_match is None:
        cover_match = re.search(
            r'<div class="summary_image">.*?<img[^>]+src="\s*([^"]+?)\s*"',
            html_text,
            re.S | re.I,
        )
    cover_url = cover_match.group(1).strip() if cover_match else None

    status_match = re.search(
        r'<h5>\s*Status\s*</h5>\s*</div>\s*<div class="summary-content">\s*([^<]+)',
        html_text,
        re.S | re.I,
    )
    status = _clean_text(status_match.group(1)) if status_match else None

    genres_block = re.search(
        r'<div class="genres-content">(.*?)</div>',
        html_text,
        re.S | re.I,
    )
    genres = (
        tuple(
            _clean_text(name)
            for name in re.findall(r"<a[^>]*>([^<]+)</a>", genres_block.group(1), re.S | re.I)
        )
        if genres_block
        else ()
    )

    author_match = re.search(
        r'<h5>\s*Author\(s\)\s*</h5>\s*</div>\s*<div class="summary-content">.*?<a[^>]*>([^<]+)</a>',
        html_text,
        re.S | re.I,
    )
    artist_match = re.search(
        r'<h5>\s*Artist\(s\)\s*</h5>\s*</div>\s*<div class="summary-content">.*?<a[^>]*>([^<]+)</a>',
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
    chapters.sort(key=lambda chapter: chapter_id_sort_key(chapter.id))
    return chapters


def parse_chapter_pages(html_text: str, chapter_id: str) -> list[Page]:
    image_urls: list[str] = []
    for tag in CHAPTER_IMG_TAG_RE.findall(html_text):
        url = _extract_image_url(tag)
        if url and url not in image_urls:
            image_urls.append(url)

    if not image_urls:
        for body in PRELOADED_IMAGES_RE.findall(html_text):
            for url in PRELOADED_URL_RE.findall(body):
                cleaned = url.strip()
                if cleaned and cleaned not in image_urls:
                    image_urls.append(cleaned)

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
        return "/manga/"
    return f"/manga/page/{page}/"


def listing_params(*, sort: str | None = None) -> dict[str, Any]:
    order = normalize_sort(sort)
    if order == SORT_TO_ORDER["default"]:
        return {}
    return {"m_orderby": order}


def search_params(query: str, *, page: int) -> dict[str, Any]:
    params: dict[str, Any] = {"s": query.strip(), "post_type": "wp-manga"}
    if page > 1:
        params["paged"] = page
    return params
