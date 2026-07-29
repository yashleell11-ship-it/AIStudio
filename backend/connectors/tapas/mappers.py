"""Map Tapas (tapas.io) API/HTML payloads to connector models."""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

STORY_API_BASE = "https://story-api.tapas.io/cosmos/api/v1/landing"
SITE_BASE = "https://tapas.io"
BROWSE_PAGE_SIZE = 30
EPISODE_PAGE_SIZE = 20
SEARCH_PAGE_SIZE = 30

IMAGE_HOSTS = frozenset({"us-a.tapas.io", "story-a.tapas.io"})

_SORT_ENDPOINTS: dict[str, str] = {
    "default": "ranking",
    "popular": "ranking",
    "latest": "genre",
    "new": "new",
    "completed": "completed",
}


def resolve_browse_endpoint(sort: str | None) -> str:
    if not sort or sort == "default":
        return "ranking"
    return _SORT_ENDPOINTS.get(sort, "ranking")


def make_chapter_id(series_slug: str, episode_id: int | str) -> str:
    return f"{series_slug.strip()}:{episode_id}"


def parse_chapter_id(chapter_id: str) -> tuple[str, str] | None:
    normalized = chapter_id.strip()
    if ":" not in normalized:
        return None
    slug, _, episode_id = normalized.rpartition(":")
    if not slug or not episode_id:
        return None
    return slug, episode_id


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", value))
    text = re.sub(r"#/_?h_i_g_h_l_i_g_h_t_#", " ", text, flags=re.I)
    text = re.sub(r"#_h_i_g_h_l_i_g_h_t_#", "", text, flags=re.I)
    text = text.replace("#", " ")
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


def _thumbnail_url(item: dict[str, Any]) -> str | None:
    asset = item.get("assetProperty")
    if not isinstance(asset, dict):
        return None
    for key in ("thumbnailImage", "bookCoverImage"):
        block = asset.get(key)
        if isinstance(block, dict):
            path = block.get("path")
            if isinstance(path, str) and path.strip():
                return path.strip()
    return None


def _author_names(item: dict[str, Any]) -> str | None:
    authors = item.get("authorList")
    if not isinstance(authors, list):
        return None
    names = [str(name).strip() for name in authors if isinstance(name, str) and name.strip()]
    return ", ".join(names) if names else None


def _genre_names(item: dict[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    main = item.get("mainGenre")
    if isinstance(main, dict):
        value = main.get("value")
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    for entry in item.get("genreList") or []:
        if isinstance(entry, dict):
            value = entry.get("value")
            if isinstance(value, str) and value.strip() and value not in names:
                names.append(value.strip())
    return tuple(names)


def landing_item_to_series(item: dict[str, Any], *, slug: str | None = None) -> Series | None:
    series_id = slug
    if not series_id:
        series_id = str(item.get("url") or "").strip()
    if not series_id:
        numeric = item.get("seriesId")
        if numeric is not None:
            series_id = str(numeric)
    if not series_id:
        return None
    title = str(item.get("title") or series_id).strip() or series_id
    description = item.get("description")
    status = item.get("issueStatus")
    return Series(
        id=series_id,
        title=title,
        description=_clean_text(description if isinstance(description, str) else None),
        author=_author_names(item),
        cover_url=_thumbnail_url(item),
        genres=_genre_names(item),
        status=str(status).strip().lower() if isinstance(status, str) else None,
    )


def landing_response_to_paginated(
    payload: dict[str, Any],
    *,
    page: int,
    page_size: int = BROWSE_PAGE_SIZE,
) -> PaginatedSeriesList:
    data = payload.get("data")
    if not isinstance(data, dict):
        return PaginatedSeriesList(items=[], page=page, page_size=page_size, total=0, api_has_more=False)

    raw_items: list[dict[str, Any]] = []
    top_items = data.get("items")
    if isinstance(top_items, list) and top_items and isinstance(top_items[0], dict) and "day" in top_items[0]:
        for group in top_items:
            if isinstance(group, dict):
                nested = group.get("items")
                if isinstance(nested, list):
                    raw_items.extend(entry for entry in nested if isinstance(entry, dict))
    elif isinstance(top_items, list):
        raw_items = [entry for entry in top_items if isinstance(entry, dict)]

    series_items: list[Series] = []
    for entry in raw_items:
        numeric_id = entry.get("seriesId")
        slug = str(entry.get("url") or "").strip() or (str(numeric_id) if numeric_id is not None else "")
        series = landing_item_to_series(entry, slug=slug or None)
        if series is not None:
            series_items.append(series)

    api_page = max(page, 1) - 1
    has_more = len(series_items) >= page_size
    return PaginatedSeriesList(
        items=series_items,
        page=page,
        page_size=page_size,
        total=len(series_items) if not has_more else (api_page + 2) * page_size,
        api_has_more=has_more,
    )


def series_json_to_series(payload: dict[str, Any], series_id: str) -> Series | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    slug = str(data.get("url") or series_id).strip() or series_id
    title = str(data.get("title") or data.get("escape_title") or slug).strip() or slug
    thumb = data.get("thumb_url")
    genre = data.get("genre")
    genres: tuple[str, ...] = ()
    if isinstance(genre, dict):
        name = genre.get("name")
        if isinstance(name, str) and name.strip():
            genres = (name.strip(),)
    return Series(
        id=slug,
        title=title,
        cover_url=thumb if isinstance(thumb, str) else None,
        genres=genres,
    )


def parse_series_info_html(html: str, series: Series) -> Series:
    description = None
    og_desc = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html, re.I)
    if og_desc:
        description = _clean_text(og_desc.group(1))
    if description is None:
        desc_match = re.search(r'class="[^"]*description[^"]*"[^>]*>(.*?)</', html, re.S | re.I)
        if desc_match:
            description = _clean_text(desc_match.group(1))

    authors: list[str] = []
    for match in re.finditer(r'class="[^"]*creator[^"]*"[^>]*>([^<]+)<', html, re.I):
        name = _clean_text(match.group(1))
        if name:
            authors.append(name)

    return Series(
        id=series.id,
        title=series.title,
        chapter_count=series.chapter_count,
        description=description or series.description,
        author=", ".join(authors) if authors else series.author,
        artist=series.artist,
        status=series.status,
        genres=series.genres,
        cover_url=series.cover_url,
        latest_chapter=series.latest_chapter,
        canonical_path=series.canonical_path,
    )


def episode_to_chapter(entry: dict[str, Any], *, series_slug: str) -> Chapter | None:
    episode_id = entry.get("id")
    if episode_id is None:
        return None
    scene = entry.get("scene")
    number: float | None = None
    if isinstance(scene, (int, float)) and scene != 0:
        number = float(scene)
    title = str(entry.get("title") or "").strip()
    if number is None and title:
        match = re.search(r"Episode\s+(\d+(?:\.\d+)?)", title, re.I)
        if match:
            try:
                number = float(match.group(1))
            except ValueError:
                number = None
    if not title:
        title = (
            f"Episode {int(number)}" if number is not None and number == int(number) else f"Episode {scene}"
        )
    chapter_id = make_chapter_id(series_slug, episode_id)
    return Chapter(
        id=chapter_id,
        series_id=series_slug,
        title=title,
        number=number,
        page_count=0,
        release_date=_format_date(
            entry.get("publish_date") if isinstance(entry.get("publish_date"), str) else None
        ),
    )


def episode_html_to_pages(chapter_id: str, html_fragment: str) -> list[Page]:
    urls: list[str] = []
    for match in re.finditer(
        r'(?:data-src|src)=["\'](https://[^"\']+(?:tapas\.io)[^"\']+)["\']',
        html_fragment,
        re.I,
    ):
        url = html_lib.unescape(match.group(1))
        if url not in urls:
            urls.append(url)
    pages: list[Page] = []
    for index, remote_url in enumerate(urls, start=1):
        pages.append(
            Page(
                id=make_page_id(chapter_id, index),
                chapter_id=chapter_id,
                number=index,
                remote_url=remote_url,
            )
        )
    return pages


def parse_search_html(html: str, *, page: int, page_size: int = SEARCH_PAGE_SIZE) -> PaginatedSeriesList:
    seen: set[str] = set()
    items: list[Series] = []
    for match in re.finditer(
        r'data-series-id="(\d+)"[^>]*href="/series/([^"]+)"[^>]*data-series-title="([^"]*)"',
        html,
        re.I,
    ):
        _numeric_id, slug, title = match.groups()
        if slug in seen:
            continue
        seen.add(slug)
        items.append(
            Series(
                id=slug.strip(),
                title=_clean_text(title) or slug,
            )
        )
    if not items:
        for match in re.finditer(
            r'href="/series/([^"]+)"[^>]*>\s*<img[^>]+alt="([^"]*)"',
            html,
            re.I,
        ):
            slug, title = match.groups()
            if slug in seen:
                continue
            seen.add(slug)
            items.append(Series(id=slug.strip(), title=_clean_text(title) or slug))

    start = (max(page, 1) - 1) * page_size
    window = items[start : start + page_size]
    return PaginatedSeriesList(
        items=window,
        page=page,
        page_size=page_size,
        total=len(items),
        api_has_more=start + page_size < len(items),
    )


def genres_from_landing(payload: dict[str, Any]) -> list[BrowseMode]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    modes: list[BrowseMode] = []
    for entry in data.get("genreList") or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        value = entry.get("value")
        if isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip():
            if key.strip().upper() == "ALL":
                continue
            modes.append(BrowseMode(id=key.strip(), label=value.strip()))
    return modes


def browse_modes() -> list[BrowseMode]:
    return [
        BrowseMode(id="popular", label="Popular"),
        BrowseMode(id="latest", label="Latest"),
        BrowseMode(id="new", label="New"),
        BrowseMode(id="completed", label="Completed"),
    ]
