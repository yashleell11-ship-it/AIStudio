"""Tapas (tapas.io) online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError
from connectors.http.ddg_client import DdgSyncHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.tapas.mappers import (
    BROWSE_PAGE_SIZE,
    EPISODE_PAGE_SIZE,
    IMAGE_HOSTS,
    SITE_BASE,
    STORY_API_BASE,
    browse_modes,
    episode_html_to_pages,
    episode_to_chapter,
    genres_from_landing,
    landing_response_to_paginated,
    make_chapter_id,
    page_id_chapter_id,
    parse_chapter_id,
    parse_search_html,
    parse_series_info_html,
    resolve_browse_endpoint,
    series_json_to_series,
)

logger = logging.getLogger(__name__)

JSON_HEADERS = {
    "Accept": "application/json, text/javascript, */*;",
    "Referer": f"{SITE_BASE}/",
    "X-Requested-With": "XMLHttpRequest",
}
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "Referer": f"{SITE_BASE}/",
}


class TapasConnector(SourceConnector):
    """Browse and read comics from Tapas (tapas.io)."""

    SOURCE_TYPE = "tapas"
    DISPLAY_NAME = "Tapas"
    DESCRIPTION = (
        "Browse and read comics from Tapas (tapas.io). "
        "Free episodes are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False

    def __init__(self) -> None:
        self._story_api = DdgSyncHttpClient(
            STORY_API_BASE,
            headers=HTML_HEADERS,
            min_interval=0.05,
        )
        self._site = DdgSyncHttpClient(
            SITE_BASE,
            headers=JSON_HEADERS,
            min_interval=0.05,
        )
        self._site_html = DdgSyncHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            min_interval=0.05,
        )
        self._numeric_id_cache: TTLCache[int] = TTLCache(ttl_seconds=3600.0)
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._genre_cache: TTLCache[list[BrowseMode]] = TTLCache(ttl_seconds=3600.0)

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    @property
    def is_browsable(self) -> bool:
        return self.BROWSABLE

    @property
    def supports_import(self) -> bool:
        return self.SUPPORTS_IMPORT

    @property
    def allowed_image_hosts(self) -> frozenset[str]:
        return IMAGE_HOSTS

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return browse_modes()

    def list_genres(self) -> list[BrowseMode]:
        return self._genre_cache.get_or_set("genres", self._fetch_genres)

    def _fetch_genres(self) -> list[BrowseMode]:
        try:
            payload = self._story_api.get_json(
                "/ranking",
                params={"category_type": "COMIC", "size": 1, "page": 0},
            )
        except ConnectorHttpError:
            return []
        if not isinstance(payload, dict):
            return []
        return genres_from_landing(payload)

    def _normalize_series_id(self, series_id: str) -> str:
        return series_id.strip().strip("/")

    def _resolve_numeric_id(self, series_slug: str) -> int | None:
        cached = self._numeric_id_cache.get(series_slug)
        if cached is not None:
            return cached
        normalized = series_slug.strip()
        if normalized.isdigit():
            numeric = int(normalized)
            self._numeric_id_cache.set(series_slug, numeric)
            return numeric
        try:
            payload = self._site.get_json(f"/series/{series_slug}?")
        except ConnectorHttpError:
            try:
                payload = self._site.get_json(f"/series/{series_slug}")
            except ConnectorHttpError:
                return None
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        numeric = data.get("id")
        if isinstance(numeric, int):
            self._numeric_id_cache.set(series_slug, numeric)
            slug = data.get("url")
            if isinstance(slug, str) and slug.strip():
                self._numeric_id_cache.set(slug.strip(), numeric)
            return numeric
        return None

    def _landing_params(
        self,
        page: int,
        *,
        sort: str | None = None,
        genre: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "category_type": "COMIC",
            "size": BROWSE_PAGE_SIZE,
            "page": max(page, 1) - 1,
        }
        if genre:
            params["genre"] = genre.strip()
        return params

    def _fetch_landing(
        self,
        page: int,
        *,
        sort: str | None = None,
        genre: str | None = None,
    ) -> PaginatedSeriesList:
        endpoint = resolve_browse_endpoint(sort)
        try:
            payload = self._story_api.get_json(
                f"/{endpoint}",
                params=self._landing_params(page, sort=sort, genre=genre),
            )
        except ConnectorHttpError as exc:
            logger.warning("Tapas browse failed endpoint=%s error=%s", endpoint, exc)
            raise
        if not isinstance(payload, dict):
            raise ConnectorHttpError("Expected JSON object from Tapas story-api.")
        listing = landing_response_to_paginated(payload, page=page)
        # Same reasoning as search_series: resolving a listing's ids up front
        # is N requests spent on behalf of a reader who opens one series.
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        listing = self._fetch_landing(page, sort=sort)
        logger.info(
            "Tapas browse sort=%r page=%d count=%d has_more=%s",
            sort,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        listing = self._fetch_landing(page, sort=sort or "latest", genre=genre)
        logger.info(
            "Tapas genre=%r page=%d count=%d",
            genre,
            page,
            len(listing.items),
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        try:
            html = self._site_html.get_text(
                "/search",
                params={"q": normalized, "t": "COMICS"},
            )
        except ConnectorHttpError as exc:
            logger.warning("Tapas search failed query=%r error=%s", normalized, exc)
            raise
        listing = parse_search_html(html, page=page)
        # No eager numeric-id warm-up here. It used to call
        # _resolve_numeric_id() for every hit -- one extra HTTP request per
        # result, serialized behind the client's rate limiter, so a 10-hit
        # search cost 11 round trips and 1.7s to warm ids for nine series the
        # reader will never open. The id resolves lazily (and caches) the
        # moment a series is actually opened.
        logger.info("Tapas search query=%r page=%d count=%d", normalized, page, len(listing.items))
        return listing

    def _peek_episode_stats(self, series_slug: str) -> tuple[int | None, str | None]:
        numeric_id = self._resolve_numeric_id(series_slug)
        if numeric_id is None:
            return None, None
        try:
            payload = self._site.get_json(
                f"/series/{numeric_id}/episodes",
                params={"page": 1, "sort": "NEWEST", "max_limit": 1},
            )
        except ConnectorHttpError:
            return None, None
        if not isinstance(payload, dict):
            return None, None
        data = payload.get("data")
        if not isinstance(data, dict):
            return None, None
        pagination = data.get("pagination")
        total = pagination.get("total") if isinstance(pagination, dict) else None
        chapter_count = int(total) if isinstance(total, int) else None
        episodes = data.get("episodes")
        latest_title = None
        if isinstance(episodes, list) and episodes:
            first = episodes[0]
            if isinstance(first, dict):
                title = first.get("title")
                if isinstance(title, str) and title.strip():
                    latest_title = title.strip()
        return chapter_count, latest_title

    def get_series(self, series_id: str) -> Series | None:
        slug = self._normalize_series_id(series_id)
        cached = self._series_cache.get(slug)
        if cached is not None:
            return cached
        try:
            payload = self._site.get_json(f"/series/{slug}?")
        except ConnectorHttpError:
            return None
        if not isinstance(payload, dict):
            return None
        series = series_json_to_series(payload, slug)
        if series is None:
            return None
        numeric = self._resolve_numeric_id(slug)
        if numeric is not None:
            self._numeric_id_cache.set(slug, numeric)
        try:
            info_html = self._site_html.get_text(f"/series/{slug}/info")
            series = parse_series_info_html(info_html, series)
        except ConnectorHttpError:
            pass
        chapter_count, latest_chapter = self._peek_episode_stats(slug)
        if chapter_count is not None or latest_chapter is not None:
            series = replace(
                series,
                chapter_count=chapter_count if chapter_count is not None else series.chapter_count,
                latest_chapter=latest_chapter or series.latest_chapter,
            )
        self._series_cache.set(slug, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        slug = self._normalize_series_id(series_id)
        return self._chapter_list_cache.get_or_set(slug, lambda: self._fetch_chapters(slug))

    def _fetch_chapters(self, series_slug: str) -> list[Chapter]:
        numeric_id = self._resolve_numeric_id(series_slug)
        if numeric_id is None:
            return []
        collected: dict[str, Chapter] = {}
        page = 1
        while page <= 500:
            try:
                payload = self._site.get_json(
                    f"/series/{numeric_id}/episodes",
                    params={
                        "page": page,
                        "sort": "OLDEST",
                        "max_limit": EPISODE_PAGE_SIZE,
                    },
                )
            except ConnectorHttpError:
                break
            if not isinstance(payload, dict):
                break
            data = payload.get("data")
            if not isinstance(data, dict):
                break
            episodes = data.get("episodes")
            if not isinstance(episodes, list):
                break
            for entry in episodes:
                if not isinstance(entry, dict):
                    continue
                if entry.get("book"):
                    continue
                chapter = episode_to_chapter(entry, series_slug=series_slug)
                if chapter is not None:
                    collected[chapter.id] = chapter
            pagination = data.get("pagination")
            has_next = isinstance(pagination, dict) and pagination.get("has_next") is True
            if not has_next or not episodes:
                break
            page += 1
        chapters = sorted(
            collected.values(),
            key=lambda ch: ch.number if ch.number is not None else 0.0,
        )
        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return self._page_cache.get_or_set(chapter_id, lambda: self._fetch_chapter_pages(chapter_id))

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        parsed = parse_chapter_id(chapter_id)
        if parsed is None:
            return []
        _slug, episode_id = parsed
        try:
            payload = self._site.get_json(f"/episode/{episode_id}?")
        except ConnectorHttpError:
            return []
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        html_fragment = data.get("html")
        if not isinstance(html_fragment, str):
            return []
        pages = episode_html_to_pages(chapter_id, html_fragment)
        logger.info("Tapas pages chapter_id=%s count=%d", chapter_id, len(pages))
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
