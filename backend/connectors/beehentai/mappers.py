"""Map ToonDex (BeeHentai successor) API payloads to connector models."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

API_BASE = "https://api.toondex.io"
SITE_BASE = "https://toondex.io"
PAGE_SIZE = 24

_SORT_MAP: dict[str, str] = {
    "latest": "latest",
    "new": "newest",
    "newest": "newest",
    "popular": "popular",
    "top_rated": "rating",
    "rating": "rating",
    "views": "views",
    "bookmarks": "bookmarks",
}


def resolve_sort(sort: str | None) -> str:
    if not sort or sort == "default":
        return "latest"
    return _SORT_MAP.get(sort, "latest")


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


def unwrap_data(payload: dict[str, Any]) -> Any:
    """Return the ``data`` field from a ToonDex success envelope."""
    if payload.get("success") is False:
        message = payload.get("message") or "ToonDex API error"
        raise ValueError(str(message))
    return payload.get("data")


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


def _people_names(entries: Any) -> str | None:
    if not isinstance(entries, list):
        return None
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        elif isinstance(entry, str) and entry.strip():
            names.append(entry.strip())
    return ", ".join(names) if names else None


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


def _chapter_count(item: dict[str, Any]) -> int:
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    for key in ("chapters_count", "chaptersCount", "chapterCount"):
        value = stats.get(key)
        if isinstance(value, int):
            return value
    display = item.get("displayChapters")
    if isinstance(display, str):
        match = re.search(r"(\d+)", display)
        if match:
            return int(match.group(1))
    return 0


def _latest_chapter_label(item: dict[str, Any]) -> str | None:
    latest = item.get("latest_chapters") or item.get("latestChapters") or []
    if isinstance(latest, list) and latest:
        first = latest[0]
        if isinstance(first, dict):
            name = first.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    count = _chapter_count(item)
    return f"{count} chapters" if count else None


def series_item_to_series(item: dict[str, Any]) -> Series | None:
    slug = str(item.get("slug") or "").strip()
    if not slug:
        url = item.get("url")
        if isinstance(url, str) and url.strip().startswith("/"):
            slug = url.strip().strip("/").split("/", 1)[0]
    if not slug:
        return None
    title = str(item.get("name") or item.get("title") or slug).strip() or slug
    cover = item.get("cover")
    return Series(
        id=slug,
        title=title,
        chapter_count=_chapter_count(item),
        cover_url=cover if isinstance(cover, str) else None,
        author=_people_names(item.get("authors")),
        artist=_people_names(item.get("artists")),
        status=_status(item.get("status") if isinstance(item.get("status"), str) else None),
        genres=_genre_names(item),
        latest_chapter=_latest_chapter_label(item),
    )


def series_detail_to_series(item: dict[str, Any]) -> Series | None:
    series = series_item_to_series(item)
    if series is None:
        return None
    summary = item.get("summary") or item.get("description")
    return Series(
        id=series.id,
        title=series.title,
        chapter_count=series.chapter_count,
        description=_strip_html(summary if isinstance(summary, str) else None),
        author=series.author,
        artist=series.artist,
        status=series.status,
        genres=series.genres,
        cover_url=series.cover_url,
        latest_chapter=series.latest_chapter,
    )


def series_list_to_paginated(data: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    raw_items = data.get("items") or []
    items: list[Series] = []
    for entry in raw_items:
        if isinstance(entry, dict):
            series = series_item_to_series(entry)
            if series is not None:
                items.append(series)
    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    current_page = int(pagination.get("page") or page)
    total_items = int(pagination.get("total") or len(items))
    total_pages = int(pagination.get("total_pages") or 0)
    has_next = pagination.get("has_next")
    if isinstance(has_next, bool):
        api_has_more = has_next
    elif total_pages:
        api_has_more = current_page < total_pages
    else:
        api_has_more = len(items) >= PAGE_SIZE
    return PaginatedSeriesList(
        items=items,
        page=current_page,
        page_size=PAGE_SIZE,
        total=total_items,
        api_has_more=api_has_more,
    )


def chapter_item_to_chapter(item: dict[str, Any], *, series_slug: str) -> Chapter | None:
    slug = str(item.get("slug") or "").strip()
    if not slug:
        url = item.get("url")
        if isinstance(url, str) and "/" in url:
            slug = url.rstrip("/").rsplit("/", 1)[-1]
    if not slug:
        return None
    number = item.get("number")
    chapter_number = float(number) if isinstance(number, (int, float)) else 0.0
    name = item.get("name")
    if isinstance(name, str) and name.strip():
        chapter_title = name.strip()
    else:
        chapter_title = (
            f"Chapter {int(chapter_number)}"
            if chapter_number == int(chapter_number)
            else f"Chapter {chapter_number}"
        )
    return Chapter(
        id=make_chapter_id(series_slug, slug),
        series_id=series_slug,
        title=chapter_title,
        number=chapter_number,
        page_count=0,
        release_date=_format_date(
            item.get("updated_at") if isinstance(item.get("updated_at"), str) else None
        ),
    )


def chapter_images_to_pages(chapter_id: str, images: Any) -> list[Page]:
    if not isinstance(images, list):
        return []
    pages: list[Page] = []
    for image in images:
        url: str | None = None
        if isinstance(image, str) and image.strip():
            url = image.strip()
        elif isinstance(image, dict):
            raw = image.get("url") or image.get("src")
            if isinstance(raw, str) and raw.strip():
                url = raw.strip()
        if not url:
            continue
        page_number = len(pages) + 1
        pages.append(
            Page(
                id=make_page_id(chapter_id, page_number),
                chapter_id=chapter_id,
                number=page_number,
                remote_url=url,
            )
        )
    return pages


def genres_to_browse_modes(data: Any) -> list[BrowseMode]:
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    modes: list[BrowseMode] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("slug") or "").strip()
        name = str(entry.get("name") or slug).strip()
        if slug and name:
            modes.append(BrowseMode(id=slug, label=name))
    return modes


def title_hsid(item: dict[str, Any]) -> str | None:
    hsid = item.get("id")
    if isinstance(hsid, str) and hsid.strip():
        return hsid.strip()
    return None
