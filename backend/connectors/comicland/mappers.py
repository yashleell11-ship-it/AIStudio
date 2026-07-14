"""Map ComicLand API payloads to normalized connector models."""

from __future__ import annotations

import html
import re
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

API_BASE = "https://api.comicland.org/api"
SITE_BASE = "https://comicland.org"
CDN_HOST = "cdn.comicland.org"
PAGE_SIZE = 20

_BROWSE_MODES: tuple[BrowseMode, ...] = (
    BrowseMode(id="latest", label="Latest"),
    BrowseMode(id="popular", label="Popular"),
    BrowseMode(id="ongoing", label="Ongoing"),
    BrowseMode(id="official", label="Official"),
    BrowseMode(id="uncensored", label="Uncensored"),
)


def browse_modes() -> list[BrowseMode]:
    return list(_BROWSE_MODES)


def make_chapter_id(series_slug: str, chapter_index: int) -> str:
    return f"{series_slug.strip().strip('/')}/chapters/{chapter_index}"


def parse_chapter_id(chapter_id: str) -> tuple[str, int] | None:
    normalized = chapter_id.strip().strip("/")
    marker = "/chapters/"
    if marker not in normalized:
        return None
    series_slug, _, index_raw = normalized.partition(marker)
    if not series_slug or not index_raw:
        return None
    try:
        return series_slug, int(index_raw)
    except ValueError:
        return None


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def unwrap_data(payload: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
    """Return the ``data`` field from a ComicLand envelope, or None."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, (dict, list)):
        return data
    return None


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _names(entries: Any) -> tuple[str, ...]:
    if not isinstance(entries, list):
        return ()
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        elif isinstance(entry, str) and entry.strip():
            names.append(entry.strip())
    return tuple(names)


def _first_name(entries: Any) -> str | None:
    names = _names(entries)
    return names[0] if names else None


def series_item_to_series(item: dict[str, Any]) -> Series | None:
    slug = str(item.get("slug") or "").strip()
    if not slug:
        return None
    chapter_count = item.get("chapter_count")
    return Series(
        id=slug,
        title=str(item.get("title") or slug).strip() or slug,
        chapter_count=int(chapter_count) if isinstance(chapter_count, int) else 0,
        description=_strip_html(
            item.get("description") if isinstance(item.get("description"), str) else None
        ),
        cover_url=item.get("cover_url") if isinstance(item.get("cover_url"), str) else None,
        author=_first_name(item.get("authors")),
        artist=_first_name(item.get("artists")),
        status=None,
        genres=_names(item.get("genres")),
    )


def series_detail_to_series(item: dict[str, Any]) -> Series | None:
    series = series_item_to_series(item)
    if series is None:
        return None
    chapters = item.get("chapters") if isinstance(item.get("chapters"), list) else []
    chapter_count = len(chapters) if chapters else series.chapter_count
    latest = None
    if chapters:
        last = chapters[-1]
        if isinstance(last, dict):
            title = last.get("title")
            if isinstance(title, str) and title.strip():
                latest = title.strip()
    return Series(
        id=series.id,
        title=series.title,
        chapter_count=chapter_count,
        description=series.description,
        cover_url=series.cover_url,
        author=series.author or _first_name(item.get("authors")),
        artist=series.artist or _first_name(item.get("artists")),
        status=series.status,
        genres=series.genres or _names(item.get("genres")),
        latest_chapter=latest,
    )


def _extract_items(data: dict[str, Any]) -> list[Any]:
    for key in ("list", "items"):
        raw = data.get(key)
        if isinstance(raw, list):
            return raw
    return []


def series_list_to_paginated(
    payload: dict[str, Any],
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    data = unwrap_data(payload)
    if not isinstance(data, dict):
        return PaginatedSeriesList(items=[], page=page, page_size=page_size, total=0, api_has_more=False)

    items: list[Series] = []
    for entry in _extract_items(data):
        if isinstance(entry, dict):
            series = series_item_to_series(entry)
            if series is not None:
                items.append(series)

    has_more_raw = data.get("has_more")
    total_raw = data.get("total")
    if isinstance(has_more_raw, bool):
        api_has_more = has_more_raw
    else:
        api_has_more = len(items) >= page_size

    if isinstance(total_raw, int) and total_raw >= 0:
        total = total_raw
    elif api_has_more:
        total = (page - 1) * page_size + len(items) + 1
    else:
        total = (page - 1) * page_size + len(items)

    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=api_has_more,
    )


def slice_series_list(
    items: list[Series],
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    if page < 1:
        page = 1
    start = (page - 1) * page_size
    chunk = items[start : start + page_size]
    return PaginatedSeriesList(
        items=chunk,
        page=page,
        page_size=page_size,
        total=len(items),
        api_has_more=start + len(chunk) < len(items),
    )


def chapters_from_detail(item: dict[str, Any], *, series_slug: str) -> list[Chapter]:
    raw = item.get("chapters") if isinstance(item.get("chapters"), list) else []
    chapters: list[Chapter] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        index = entry.get("chapter_index")
        if not isinstance(index, int) or index < 1:
            continue
        title = entry.get("title")
        if isinstance(title, str) and title.strip():
            chapter_title = title.strip()
        else:
            chapter_title = f"Chapter {index}"
        page_count = entry.get("page_count")
        chapters.append(
            Chapter(
                id=make_chapter_id(series_slug, index),
                series_id=series_slug,
                title=chapter_title,
                number=float(index),
                page_count=int(page_count) if isinstance(page_count, int) else 0,
            )
        )
    # Newest first for the reader chapter list.
    chapters.sort(key=lambda c: c.number or 0.0, reverse=True)
    return chapters


def chapter_pages_to_pages(chapter_id: str, payload: dict[str, Any]) -> list[Page]:
    data = unwrap_data(payload)
    if not isinstance(data, dict):
        return []
    raw_pages = data.get("pages") or []
    if not isinstance(raw_pages, list):
        return []
    pages: list[Page] = []
    for entry in raw_pages:
        if not isinstance(entry, str) or not entry.strip():
            continue
        page_number = len(pages) + 1
        pages.append(
            Page(
                id=make_page_id(chapter_id, page_number),
                chapter_id=chapter_id,
                number=page_number,
                remote_url=entry.strip(),
            )
        )
    return pages
