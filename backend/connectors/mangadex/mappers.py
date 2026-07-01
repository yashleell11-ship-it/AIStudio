"""Map MangaDex API payloads to normalized connector models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

API_BASE = "https://api.mangadex.org"
UPLOADS_BASE = "https://uploads.mangadex.org"
PAGE_SIZE = 24
DEFAULT_INCLUDES = ["cover_art", "author", "artist"]
STATUS_MAP = {
    "ongoing": "ongoing",
    "completed": "completed",
    "hiatus": "hiatus",
    "cancelled": "cancelled",
}


def _localized_title(attributes: dict[str, Any]) -> str:
    title = attributes.get("title") or {}
    if isinstance(title, dict):
        for key in ("en", "ja-ro", "ja", "ko", "zh", "zh-hk"):
            value = title.get(key)
            if value:
                return str(value)
        for value in title.values():
            if value:
                return str(value)
    return "Untitled"


def _relationship_map(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    relationships = payload.get("relationships") or []
    included = payload.get("included") or []
    included_by_type_id: dict[tuple[str, str], dict[str, Any]] = {}
    for item in included:
        if isinstance(item, dict) and "type" in item and "id" in item:
            included_by_type_id[(str(item["type"]), str(item["id"]))] = item

    grouped: dict[str, list[dict[str, Any]]] = {}
    for relation in relationships:
        if not isinstance(relation, dict):
            continue
        rel_type = str(relation.get("type") or "")
        rel_id = str(relation.get("id") or "")
        item = included_by_type_id.get((rel_type, rel_id))
        if item is None:
            continue
        grouped.setdefault(rel_type, []).append(item)
    return grouped


def _person_name(item: dict[str, Any]) -> str | None:
    attributes = item.get("attributes") or {}
    name = attributes.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _cover_url(manga_id: str, included: dict[str, list[dict[str, Any]]]) -> str | None:
    covers = included.get("cover_art") or []
    if not covers:
        return None
    cover = covers[0]
    attributes = cover.get("attributes") or {}
    filename = attributes.get("fileName")
    if not filename:
        return None
    return f"{UPLOADS_BASE}/covers/{manga_id}/{filename}"


def _tag_genres(included: dict[str, list[dict[str, Any]]]) -> tuple[str, ...]:
    genres: list[str] = []
    for tag in included.get("tag") or []:
        attributes = tag.get("attributes") or {}
        group = attributes.get("group")
        name = attributes.get("name")
        if group == "genre" and isinstance(name, str):
            genres.append(name)
    return tuple(genres)


def _parse_chapter_number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _format_latest_chapter(attributes: dict[str, Any]) -> str | None:
    latest = attributes.get("latestUploadedChapter")
    if not isinstance(latest, str):
        return None
    try:
        parsed = datetime.fromisoformat(latest.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return latest


def manga_to_series(item: dict[str, Any], *, chapter_count: int = 0) -> Series:
    manga_id = str(item["id"])
    attributes = item.get("attributes") or {}
    included = _relationship_map({"relationships": item.get("relationships"), "included": item.get("_included")})
    authors = included.get("author") or []
    artists = included.get("artist") or []
    status = STATUS_MAP.get(str(attributes.get("status") or ""), str(attributes.get("status") or ""))

    return Series(
        id=manga_id,
        title=_localized_title(attributes),
        chapter_count=chapter_count,
        description=(attributes.get("description") or {}).get("en")
        if isinstance(attributes.get("description"), dict)
        else None,
        cover_url=_cover_url(manga_id, included),
        author=_person_name(authors[0]) if authors else None,
        artist=_person_name(artists[0]) if artists else None,
        status=status or None,
        genres=_tag_genres(included),
        latest_chapter=_format_latest_chapter(attributes),
    )


def manga_list_to_paginated(
    payload: dict[str, Any],
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    data = payload.get("data") or []
    total = int(payload.get("total") or 0)
    included = payload.get("included") or []
    items: list[Series] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        item = {**item, "_included": included}
        items.append(manga_to_series(item))
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


def chapter_item_to_chapter(item: dict[str, Any], *, series_id: str) -> Chapter:
    chapter_id = str(item["id"])
    attributes = item.get("attributes") or {}
    chapter_number = _parse_chapter_number(str(attributes.get("chapter") or ""))
    title = attributes.get("title") or attributes.get("chapter") or "Chapter"
    pages = int(attributes.get("pages") or 0)
    publish_at = attributes.get("publishAt")
    number = (
        int(chapter_number)
        if chapter_number is not None and chapter_number.is_integer()
        else None
    )
    return Chapter(
        id=chapter_id,
        series_id=series_id,
        title=str(title),
        number=number,
        page_count=pages,
        release_date=str(publish_at) if publish_at else None,
    )


def at_home_to_pages(chapter_id: str, payload: dict[str, Any]) -> list[Page]:
    base_url = str(payload.get("baseUrl") or "").rstrip("/")
    chapter = payload.get("chapter") or {}
    chapter_hash = chapter.get("hash")
    filenames = chapter.get("data") or chapter.get("dataSaver") or []
    quality = "data" if chapter.get("data") else "data-saver"

    if not base_url or not chapter_hash or not isinstance(filenames, list):
        return []

    pages: list[Page] = []
    for index, filename in enumerate(filenames, start=1):
        if not isinstance(filename, str) or not filename.strip():
            continue
        pages.append(
            Page(
                id=f"{chapter_id}:{index}",
                chapter_id=chapter_id,
                number=index,
                remote_url=f"{base_url}/{quality}/{chapter_hash}/{filename}",
            )
        )
    return pages


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None
