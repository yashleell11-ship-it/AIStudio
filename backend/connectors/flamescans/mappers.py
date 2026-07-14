"""Map Flame Comics (Flame Scans) payloads to normalized connector models."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://flamecomics.xyz"
CDN_BASE = "https://cdn.flamecomics.xyz"
PAGE_SIZE = 24

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def make_chapter_id(series_id: str, token: str) -> str:
    return f"{series_id.strip()}/{token.strip()}"


def parse_chapter_id(chapter_id: str) -> tuple[str, str] | None:
    normalized = chapter_id.strip().strip("/")
    if "/" not in normalized:
        return None
    series_id, _, token = normalized.partition("/")
    if not series_id or not token or "/" in token:
        return None
    return series_id, token


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def cover_url(series_id: int | str, image: str | None) -> str | None:
    if not image or not str(image).strip():
        return None
    name = str(image).strip().lstrip("/")
    if name.startswith("http://") or name.startswith("https://"):
        return name
    return f"{CDN_BASE}/uploads/images/series/{series_id}/{name}"


def chapter_image_url(
    series_id: int | str,
    token: str,
    image_name: str,
    *,
    cache_bust: int | str | None = None,
) -> str:
    url = f"{CDN_BASE}/uploads/images/series/{series_id}/{token}/{image_name}"
    if cache_bust is not None and str(cache_bust).strip():
        return f"{url}?{cache_bust}"
    return url


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _join_names(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        names = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(names) if names else None
    return None


def _status(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def _chapter_count(value: Any) -> int:
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _unix_date(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def parse_next_data(html_text: str) -> dict[str, Any] | None:
    match = _NEXT_DATA_RE.search(html_text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    page_props = payload.get("props", {}).get("pageProps")
    return page_props if isinstance(page_props, dict) else None


def series_list_item_to_series(item: dict[str, Any]) -> Series | None:
    series_id = item.get("id")
    if series_id is None:
        return None
    sid = str(series_id).strip()
    if not sid:
        return None
    title = str(item.get("label") or item.get("title") or sid).strip() or sid
    image = item.get("image") if isinstance(item.get("image"), str) else item.get("cover")
    return Series(
        id=sid,
        title=title,
        chapter_count=_chapter_count(item.get("chapter_count")),
        cover_url=cover_url(sid, image if isinstance(image, str) else None),
        status=_status(item.get("status") if isinstance(item.get("status"), str) else None),
        canonical_path=f"/series/{sid}",
    )


def series_detail_to_series(item: dict[str, Any], *, chapter_count: int | None = None) -> Series | None:
    series_id = item.get("series_id")
    if series_id is None:
        return None
    sid = str(series_id).strip()
    if not sid:
        return None
    title = str(item.get("title") or sid).strip() or sid
    tags = item.get("tags") or item.get("categories") or []
    genres = tuple(str(tag).strip() for tag in tags if str(tag).strip()) if isinstance(tags, list) else ()
    count = chapter_count if chapter_count is not None else _chapter_count(item.get("chapter_count"))
    cover = item.get("cover") if isinstance(item.get("cover"), str) else None
    return Series(
        id=sid,
        title=title,
        chapter_count=count,
        description=_strip_html(item.get("description") if isinstance(item.get("description"), str) else None),
        cover_url=cover_url(sid, cover),
        author=_join_names(item.get("author")),
        artist=_join_names(item.get("artist")),
        status=_status(item.get("status") if isinstance(item.get("status"), str) else None),
        genres=genres,
        canonical_path=f"/series/{sid}",
        latest_chapter=f"{count} chapters" if count else None,
    )


def paginate_series(
    items: list[Series],
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    safe_page = max(page, 1)
    start = (safe_page - 1) * page_size
    end = start + page_size
    slice_items = items[start:end]
    return PaginatedSeriesList(
        items=slice_items,
        page=safe_page,
        page_size=page_size,
        total=len(items),
        api_has_more=end < len(items),
    )


def sort_series_items(items: list[dict[str, Any]], sort: str | None) -> list[dict[str, Any]]:
    key = (sort or "latest").strip().lower()
    if key in {"alphabetical", "title", "az"}:
        return sorted(items, key=lambda item: str(item.get("label") or item.get("title") or "").lower())
    if key in {"popular", "chapters"}:
        return sorted(items, key=lambda item: _chapter_count(item.get("chapter_count")), reverse=True)
    # API already returns an activity-ish order; keep it for latest/default.
    return list(items)


def filter_series_items(items: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return list(items)
    needle = query.strip().lower()
    return [
        item
        for item in items
        if needle in str(item.get("label") or item.get("title") or "").lower()
    ]


def chapter_item_to_chapter(item: dict[str, Any], *, series_id: str) -> Chapter | None:
    token = str(item.get("token") or "").strip()
    if not token:
        return None
    raw_number = item.get("chapter")
    try:
        number = float(raw_number) if raw_number is not None else None
    except (TypeError, ValueError):
        number = None
    title = item.get("title")
    if isinstance(title, str) and title.strip():
        chapter_title = title.strip()
        if number is not None:
            pretty = int(number) if number == int(number) else number
            chapter_title = f"Chapter {pretty} - {chapter_title}"
    elif number is not None:
        pretty = int(number) if number == int(number) else number
        chapter_title = f"Chapter {pretty}"
    else:
        chapter_title = token
    return Chapter(
        id=make_chapter_id(series_id, token),
        series_id=series_id,
        title=chapter_title,
        number=number,
        page_count=0,
        release_date=_unix_date(item.get("release_date")),
    )


def chapter_pages_to_pages(chapter_id: str, payload: dict[str, Any]) -> list[Page]:
    chapter = payload.get("chapter") if isinstance(payload.get("chapter"), dict) else payload
    if not isinstance(chapter, dict):
        return []
    series_id = chapter.get("series_id")
    token = str(chapter.get("token") or payload.get("token") or "").strip()
    images = chapter.get("images")
    if series_id is None or not token or not isinstance(images, dict):
        return []
    cache_bust = chapter.get("edit_time")
    pages: list[Page] = []
    for key in sorted(images.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value)):
        entry = images[key]
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        page_number = int(key) + 1 if str(key).isdigit() else len(pages) + 1
        width = entry.get("width")
        height = entry.get("height")
        pages.append(
            Page(
                id=make_page_id(chapter_id, page_number),
                chapter_id=chapter_id,
                number=page_number,
                width=int(width) if isinstance(width, int) else None,
                height=int(height) if isinstance(height, int) else None,
                remote_url=chapter_image_url(series_id, token, name.strip(), cache_bust=cache_bust),
            )
        )
    return pages
