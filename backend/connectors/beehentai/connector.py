"""BeeHentai online source connector (beehentai.com → toontop.io API)."""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import SourceConnector
from connectors.beehentai.mappers import (
    API_BASE,
    PAGE_SIZE,
    SITE_BASE,
    chapter_images_to_pages,
    chapter_item_to_chapter,
    genres_to_browse_modes,
    page_id_chapter_id,
    parse_chapter_id,
    resolve_sort,
    series_detail_to_series,
    series_list_to_paginated,
    title_hsid,
    unwrap_data,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": SITE_BASE,
    "Referer": f"{SITE_BASE}/",
}


class BeeHentaiConnector(SourceConnector):
    """Browse and read from BeeHentai (redirects to ToonTop)."""

    SOURCE_TYPE = "beehentai"
    DISPLAY_NAME = "BeeHentai"
    DESCRIPTION = (
        "Browse and read manga and manhwa from BeeHentai (now ToonTop). "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(API_BASE, headers=API_HEADERS)
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._hsid_cache: TTLCache[str] = TTLCache(ttl_seconds=300.0)
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
        return frozenset({"rx.toontop.io", "toontop.io"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="new", label="New"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="top_rated", label="Top Rated"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return self._genre_cache.get_or_set("genres", self._fetch_genres)

    def _fetch_genres(self) -> list[BrowseMode]:
        payload = self._http.get_json("/genres")
        if not isinstance(payload, dict):
            return []
        try:
            data = unwrap_data(payload)
        except ValueError:
            return []
        return genres_to_browse_modes(data)

    def _api_data(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        payload = self._http.get_json(path, params=params)
        if not isinstance(payload, dict):
            raise ConnectorHttpError("Expected JSON object response.")
        try:
            return unwrap_data(payload)
        except ValueError as exc:
            raise ConnectorHttpError(str(exc)) from exc

    def _listing_params(
        self,
        page: int,
        *,
        sort: str | None = None,
        query: str | None = None,
        genre: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": page,
            "limit": PAGE_SIZE,
            "sort": resolve_sort(sort),
        }
        if query:
            params["q"] = query
        if genre:
            params["genres"] = genre.strip().lower().replace(" ", "-")
        return params

    def _fetch_listing(
        self,
        page: int,
        *,
        sort: str | None = None,
        query: str | None = None,
        genre: str | None = None,
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        data = self._api_data(
            "/titles/search",
            params=self._listing_params(page, sort=sort, query=query, genre=genre),
        )
        if not isinstance(data, dict):
            raise ConnectorHttpError("Expected listing data object.")
        return series_list_to_paginated(data, page=page)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        listing = self._fetch_listing(page, sort=sort)
        logger.info(
            "BeeHentai browse sort=%r page=%d count=%d has_more=%s",
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
        return self._fetch_listing(page, sort=sort, genre=genre)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        listing = self._fetch_listing(page, sort=sort, query=normalized)
        logger.info(
            "BeeHentai search page=%d count=%d sort=%r query=%r",
            page,
            len(listing.items),
            sort,
            normalized,
        )
        return listing

    def _normalize_series_slug(self, series_id: str) -> str:
        return series_id.strip().strip("/").split("/", 1)[0]

    def _resolve_hsid(self, series_slug: str) -> str | None:
        cached = self._hsid_cache.get(series_slug)
        if cached is not None:
            return cached
        try:
            data = self._api_data(
                f"/titles/by-slug/{series_slug}",
                params={"include": "details"},
            )
        except ConnectorHttpError:
            return None
        if not isinstance(data, dict):
            return None
        title = data.get("title")
        if not isinstance(title, dict):
            return None
        hsid = title_hsid(title)
        if hsid:
            self._hsid_cache.set(series_slug, hsid)
        return hsid

    def get_series(self, series_id: str) -> Series | None:
        slug = self._normalize_series_slug(series_id)
        cached = self._series_cache.get(slug)
        if cached is not None:
            return cached
        try:
            data = self._api_data(
                f"/titles/by-slug/{slug}",
                params={"include": "details"},
            )
        except ConnectorHttpError:
            return None
        if not isinstance(data, dict):
            return None
        title = data.get("title")
        if not isinstance(title, dict):
            return None
        series = series_detail_to_series(title)
        if series is None:
            return None
        hsid = title_hsid(title)
        if hsid:
            self._hsid_cache.set(slug, hsid)
        self._series_cache.set(slug, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        slug = self._normalize_series_slug(series_id)
        return self._chapter_list_cache.get_or_set(slug, lambda: self._fetch_chapters(slug))

    def _fetch_chapters(self, series_slug: str) -> list[Chapter]:
        hsid = self._resolve_hsid(series_slug)
        if not hsid:
            return []
        try:
            data = self._api_data(f"/titles/{hsid}/chapters")
        except ConnectorHttpError:
            return []
        if not isinstance(data, dict):
            return []
        chapters: list[Chapter] = []
        for entry in data.get("chapters") or []:
            if isinstance(entry, dict):
                chapter = chapter_item_to_chapter(entry, series_slug=series_slug)
                if chapter is not None:
                    chapters.append(chapter)
        # API returns newest-first; present oldest-first for reader navigation.
        chapters.reverse()
        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return self._page_cache.get_or_set(chapter_id, lambda: self._fetch_chapter_pages(chapter_id))

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        parsed = parse_chapter_id(chapter_id)
        if parsed is None:
            return []
        series_slug, chapter_slug = parsed
        try:
            data = self._api_data(
                f"/titles/by-slug/{series_slug}/chapters/{chapter_slug}",
                params={"include": "details"},
            )
        except ConnectorHttpError:
            return []
        if not isinstance(data, dict):
            return []
        chapter = data.get("chapter")
        if not isinstance(chapter, dict):
            return []
        return chapter_images_to_pages(chapter_id, chapter.get("images"))

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
