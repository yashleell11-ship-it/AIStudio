"""Map QiManga (Aurora Scans) API payloads to normalized connector models."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

API_BASE = "https://api.qimanga.com/api/v1"
SITE_BASE = "https://qimanga.com"
PAGE_SIZE = 20

_SORT_MAP: dict[str, str] = {
    "latest": "latest",
    "new": "newest",
    "popular": "popular",
    "top_rated": "popular",
    "newest": "newest",
    "alphabetical": "alphabetical",
}


def resolve_sort(sort: str | None) -> str:
    if not sort or sort == "default":
        return "latest"
    return _SORT_MAP.get(sort, sort)


def make_chapter_id(series_slug: str, chapter_slug: str) -> str:
    return f"{series_slug.strip().strip('/')}/chapters/{chapter_slug.strip().strip('/')}"


def parse_chapter_id(chapter_id: str) -> tuple[str, str] | None:
    normalized = chapter_id.strip().strip("/")
    marker = "/chapters/"
    if marker not in normalized:
        return None
    series_slug, _, chapter_slug = normalized.partition(marker)
    if not series_slug or not chapter_slug:
        return None
    return series_slug, chapter_slug


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _format_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return value


def _genre_names(item: dict[str, Any]) -> tuple[str, ...]:
    genres = item.get("genres") or []
    names: list[str] = []
    for genre in genres:
        if isinstance(genre, dict):
            name = genre.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return tuple(names)


def _status(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def series_item_to_series(item: dict[str, Any]) -> Series | None:
    if str(item.get("type") or "").upper() == "NOVEL":
        return None
    slug = str(item.get("slug") or "").strip()
    if not slug:
        return None
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    chapter_count = stats.get("chapterCount")
    return Series(
        id=slug,
        title=str(item.get("title") or slug).strip() or slug,
        chapter_count=int(chapter_count) if isinstance(chapter_count, int) else 0,
        cover_url=item.get("cover") if isinstance(item.get("cover"), str) else None,
        author=item.get("author") if isinstance(item.get("author"), str) else None,
        artist=item.get("artist") if isinstance(item.get("artist"), str) else None,
        status=_status(item.get("status") if isinstance(item.get("status"), str) else None),
        genres=_genre_names(item),
        latest_chapter=None,
    )


def series_detail_to_series(item: dict[str, Any]) -> Series | None:
    series = series_item_to_series(item)
    if series is None:
        return None
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    chapter_count = stats.get("chapterCount")
    return Series(
        id=series.id,
        title=series.title,
        chapter_count=int(chapter_count) if isinstance(chapter_count, int) else series.chapter_count,
        description=_strip_html(item.get("description") if isinstance(item.get("description"), str) else None),
        author=series.author,
        artist=series.artist,
        status=series.status,
        genres=series.genres,
        cover_url=series.cover_url,
        latest_chapter=f"{chapter_count} chapters" if chapter_count else None,
    )


def series_list_to_paginated(payload: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    raw_items = payload.get("data") or []
    items: list[Series] = []
    for entry in raw_items:
        if isinstance(entry, dict):
            series = series_item_to_series(entry)
            if series is not None:
                items.append(series)
    total_pages = int(payload.get("totalPages") or 0)
    current_page = int(payload.get("current") or page)
    total_items = int(payload.get("totalItems") or len(items))
    return PaginatedSeriesList(
        items=items,
        page=current_page,
        page_size=PAGE_SIZE,
        total=total_items,
        api_has_more=current_page < total_pages if total_pages else len(items) >= PAGE_SIZE,
    )


def chapter_item_to_chapter(item: dict[str, Any], *, series_slug: str) -> Chapter | None:
    if item.get("requiresPurchase") is True:
        return None
    slug = str(item.get("slug") or "").strip()
    if not slug:
        return None
    number = item.get("number")
    chapter_number = float(number) if isinstance(number, (int, float)) else 0.0
    title = item.get("title")
    if isinstance(title, str) and title.strip():
        chapter_title = title.strip()
    else:
        chapter_title = f"Chapter {int(chapter_number) if chapter_number == int(chapter_number) else chapter_number}"
    return Chapter(
        id=make_chapter_id(series_slug, slug),
        series_id=series_slug,
        title=chapter_title,
        number=chapter_number,
        page_count=0,
        release_date=_format_date(item.get("createdAt") if isinstance(item.get("createdAt"), str) else None),
    )


def chapter_pages_to_pages(chapter_id: str, payload: dict[str, Any]) -> list[Page]:
    if payload.get("requiresPurchase") is True:
        return []
    images = payload.get("images") or []
    pages: list[Page] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        url = image.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        order = image.get("order")
        page_number = int(order) + 1 if isinstance(order, int) else len(pages) + 1
        width = image.get("width")
        height = image.get("height")
        pages.append(
            Page(
                id=make_page_id(chapter_id, page_number),
                chapter_id=chapter_id,
                number=page_number,
                width=int(width) if isinstance(width, int) else None,
                height=int(height) if isinstance(height, int) else None,
                remote_url=url.strip(),
            )
        )
    return pages


def genres_to_browse_modes(payload: Any) -> list[BrowseMode]:
    if not isinstance(payload, list):
        return []
    modes: list[BrowseMode] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("slug") or "").strip()
        name = str(entry.get("name") or slug).strip()
        if slug and name:
            modes.append(BrowseMode(id=slug, label=name))
    return modes
