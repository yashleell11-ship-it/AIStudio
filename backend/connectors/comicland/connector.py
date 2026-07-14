"""ComicLand online source connector (comicland.org JSON API)."""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import SourceConnector
from connectors.comicland.mappers import (
    API_BASE,
    CDN_HOST,
    PAGE_SIZE,
    SITE_BASE,
    browse_modes,
    chapter_pages_to_pages,
    chapters_from_detail,
    page_id_chapter_id,
    parse_chapter_id,
    series_detail_to_series,
    series_list_to_paginated,
    slice_series_list,
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
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class ComicLandConnector(SourceConnector):
    """Browse and read mature comics from ComicLand (comicland.org)."""

    SOURCE_TYPE = "comicland"
    DISPLAY_NAME = "ComicLand"
    DESCRIPTION = (
        "Browse and read comics from ComicLand. "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            API_BASE,
            headers=API_HEADERS,
            user_agent=BROWSER_USER_AGENT,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._detail_cache: TTLCache[dict[str, Any]] = TTLCache(ttl_seconds=300.0)
        self._popular_cache: TTLCache[list[Series]] = TTLCache(ttl_seconds=300.0)

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
        return frozenset({CDN_HOST})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return browse_modes()

    def list_genres(self) -> list[BrowseMode]:
        # ComicLand has no genres catalog endpoint; genre browse uses URL slugs.
        return []

    def _normalize_series_slug(self, series_id: str) -> str:
        return series_id.strip().strip("/").split("/", 1)[0]

    def _offset(self, page: int) -> int:
        if page < 1:
            page = 1
        return (page - 1) * PAGE_SIZE

    def _get_data(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._http.get_json(path, params=params)
        if not isinstance(payload, dict):
            raise ConnectorHttpError("Expected JSON object response.")
        code = payload.get("code")
        if code not in (0, None):
            message = payload.get("message") or f"API error code={code}"
            raise ConnectorHttpError(str(message))
        return payload

    def _listing(
        self,
        page: int,
        *,
        path: str,
        extra_params: dict[str, Any] | None = None,
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        params: dict[str, Any] = {
            "offset": self._offset(page),
            "limit": PAGE_SIZE,
        }
        if extra_params:
            params.update(extra_params)
        payload = self._get_data(path, params=params)
        return series_list_to_paginated(payload, page=page)

    def _popular_listing(self, page: int) -> PaginatedSeriesList:
        if page < 1:
            page = 1

        def _fetch() -> list[Series]:
            payload = self._get_data("/comics/popular")
            listing = series_list_to_paginated(payload, page=1, page_size=10_000)
            return listing.items

        items = self._popular_cache.get_or_set("popular", _fetch)
        return slice_series_list(items, page=page)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        mode = (sort or "latest").strip().lower()
        if mode in ("", "default", "latest", "new", "recommend"):
            listing = self._listing(page, path="/comics")
        elif mode in ("popular", "top_rated"):
            listing = self._popular_listing(page)
        elif mode == "ongoing":
            listing = self._listing(page, path="/comics", extra_params={"status": "ongoing"})
        elif mode == "official":
            listing = self._listing(page, path="/comics/official")
        elif mode == "uncensored":
            listing = self._listing(
                page,
                path="/comic/search",
                extra_params={"q": "uncensored"},
            )
        else:
            listing = self._listing(page, path="/comics")
        logger.info(
            "ComicLand browse sort=%r page=%d count=%d has_more=%s",
            mode,
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
        del sort  # ComicLand genre endpoint has no sort param.
        name = genre.strip()
        if not name:
            return PaginatedSeriesList(items=[], page=max(page, 1), page_size=PAGE_SIZE, total=0)
        return self._listing(page, path="/comics_by_genre", extra_params={"name": name})

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        del sort
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort="latest")
        listing = self._listing(
            page,
            path="/comic/search",
            extra_params={"q": normalized},
        )
        logger.info(
            "ComicLand search page=%d count=%d query=%r",
            page,
            len(listing.items),
            normalized,
        )
        return listing

    def _fetch_detail(self, slug: str) -> dict[str, Any] | None:
        cached = self._detail_cache.get(slug)
        if cached is not None:
            return cached
        try:
            payload = self._get_data("/comic/detail", params={"slug": slug})
        except ConnectorHttpError:
            return None
        data = unwrap_data(payload)
        if not isinstance(data, dict):
            return None
        self._detail_cache.set(slug, data)
        return data

    def get_series(self, series_id: str) -> Series | None:
        slug = self._normalize_series_slug(series_id)
        cached = self._series_cache.get(slug)
        if cached is not None:
            return cached
        detail = self._fetch_detail(slug)
        if detail is None:
            return None
        series = series_detail_to_series(detail)
        if series is None:
            return None
        self._series_cache.set(slug, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        slug = self._normalize_series_slug(series_id)
        return self._chapter_list_cache.get_or_set(slug, lambda: self._fetch_chapters(slug))

    def _fetch_chapters(self, series_slug: str) -> list[Chapter]:
        detail = self._fetch_detail(series_slug)
        if detail is None:
            return []
        return chapters_from_detail(detail, series_slug=series_slug)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return self._page_cache.get_or_set(chapter_id, lambda: self._fetch_chapter_pages(chapter_id))

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        parsed = parse_chapter_id(chapter_id)
        if parsed is None:
            return []
        series_slug, chapter_index = parsed
        try:
            payload = self._get_data(
                "/chapter/pages_by_index",
                params={"slug": series_slug, "index": chapter_index},
            )
        except ConnectorHttpError:
            return []
        return chapter_pages_to_pages(chapter_id, payload)

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
