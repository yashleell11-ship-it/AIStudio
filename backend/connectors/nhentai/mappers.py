"""Map nHentai API v2 payloads to normalized connector models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

API_BASE = "https://nhentai.net"
PAGE_SIZE = 25


def _pick_title(item: dict[str, Any]) -> str:
    title = item.get("title")
    if isinstance(title, dict):
        for key in ("english", "japanese", "pretty"):
            value = title.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("english_title", "japanese_title"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Untitled"


def _server_base(media_id: str, servers: list[str]) -> str:
    if not servers:
        return "https://i1.nhentai.net"
    index = int(media_id) % len(servers)
    return str(servers[index]).rstrip("/")


def _asset_url(media_id: str, path: str | None, servers: list[str]) -> str | None:
    if not path:
        return None
    return f"{_server_base(media_id, servers)}/{path.lstrip('/')}"


def _tag_values(tags: list[dict[str, Any]] | None, tag_type: str) -> tuple[str, ...]:
    if not tags:
        return ()
    values: list[str] = []
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        if str(tag.get("type") or "") != tag_type:
            continue
        name = tag.get("name")
        if isinstance(name, str) and name.strip():
            values.append(name.strip())
    return tuple(values)


def _format_upload_date(timestamp: int | None) -> str | None:
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return None


def gallery_list_item_to_series(
    item: dict[str, Any],
    *,
    thumb_servers: list[str],
) -> Series:
    gallery_id = str(item["id"])
    media_id = str(item.get("media_id") or gallery_id)
    num_pages = int(item.get("num_pages") or 0)
    thumb_path = item.get("thumbnail")
    if isinstance(item.get("thumbnail"), dict):
        thumb_path = item["thumbnail"].get("path")
    cover_url = _asset_url(media_id, str(thumb_path) if thumb_path else None, thumb_servers)
    return Series(
        id=gallery_id,
        title=_pick_title(item),
        chapter_count=1 if num_pages > 0 else 0,
        cover_url=cover_url,
        latest_chapter=f"{num_pages} pages" if num_pages else None,
    )


def gallery_detail_to_series(
    item: dict[str, Any],
    *,
    thumb_servers: list[str],
) -> Series:
    gallery_id = str(item["id"])
    media_id = str(item.get("media_id") or gallery_id)
    num_pages = int(item.get("num_pages") or 0)
    thumb = item.get("thumbnail") or {}
    cover = item.get("cover") or {}
    thumb_path = thumb.get("path") if isinstance(thumb, dict) else None
    cover_path = cover.get("path") if isinstance(cover, dict) else None
    cover_url = _asset_url(
        media_id,
        str(cover_path or thumb_path) if (cover_path or thumb_path) else None,
        thumb_servers,
    )
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    artists = _tag_values(tags, "artist")
    groups = _tag_values(tags, "group")
    genres = _tag_values(tags, "category") + _tag_values(tags, "parody")
    return Series(
        id=gallery_id,
        title=_pick_title(item),
        chapter_count=1 if num_pages > 0 else 0,
        cover_url=cover_url,
        author=artists[0] if artists else (groups[0] if groups else None),
        artist=artists[0] if artists else None,
        status="completed",
        genres=genres,
        latest_chapter=f"{num_pages} pages" if num_pages else None,
        description=item.get("scanlator") or None,
    )


def gallery_to_chapter(item: dict[str, Any]) -> Chapter:
    gallery_id = str(item["id"])
    num_pages = int(item.get("num_pages") or len(item.get("pages") or []))
    upload_date = _format_upload_date(item.get("upload_date"))
    return Chapter(
        id=gallery_id,
        series_id=gallery_id,
        title="Gallery",
        number=1.0,
        page_count=num_pages,
        release_date=upload_date,
    )


def gallery_pages_to_pages(
    gallery_id: str,
    item: dict[str, Any],
    *,
    image_servers: list[str],
) -> list[Page]:
    media_id = str(item.get("media_id") or gallery_id)
    raw_pages = item.get("pages") or []
    pages: list[Page] = []
    for entry in raw_pages:
        if not isinstance(entry, dict):
            continue
        number = int(entry.get("number") or len(pages) + 1)
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        pages.append(
            Page(
                id=f"{gallery_id}:{number}",
                chapter_id=gallery_id,
                number=number,
                remote_url=_asset_url(media_id, path, image_servers),
                width=int(entry["width"]) if entry.get("width") else None,
                height=int(entry["height"]) if entry.get("height") else None,
            )
        )
    return pages


def listing_to_paginated(
    payload: Any,
    *,
    page: int,
    page_size: int,
    thumb_servers: list[str],
) -> PaginatedSeriesList:
    if isinstance(payload, list):
        items = [
            gallery_list_item_to_series(item, thumb_servers=thumb_servers)
            for item in payload
            if isinstance(item, dict)
        ]
        return PaginatedSeriesList(
            items=items,
            page=page,
            page_size=page_size,
            total=0,
            api_has_more=len(items) >= page_size,
        )

    if not isinstance(payload, dict):
        return PaginatedSeriesList(page=page, page_size=page_size)

    result = payload.get("result") or []
    total = int(payload.get("total") or 0)
    per_page = int(payload.get("per_page") or page_size)
    items = [
        gallery_list_item_to_series(item, thumb_servers=thumb_servers)
        for item in result
        if isinstance(item, dict)
    ]
    api_has_more: bool | None = None
    if total > 0:
        consumed = (page - 1) * per_page + len(items)
        api_has_more = consumed < total
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=per_page,
        total=total,
        api_has_more=api_has_more,
    )


def page_id_gallery_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    gallery_id, _, _page_number = page_id.rpartition(":")
    return gallery_id or None
