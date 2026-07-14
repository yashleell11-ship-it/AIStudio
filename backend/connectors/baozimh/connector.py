"""BaoZiMH online source connector (baozimh.com AMP catalog + twmanga reader)."""

from __future__ import annotations

import logging

from connectors.base import SourceConnector
from connectors.baozimh.mappers import (
    LIST_API_PATH,
    PAGE_SIZE,
    SITE_BASE,
    chapter_page_path,
    comic_id_from_path,
    genres_to_browse_modes,
    listing_params,
    page_id_chapter_id,
    parse_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_search_listing,
    parse_series_detail,
    resolve_list_state,
    series_list_to_paginated,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

REQUEST_HEADERS = {
    "Accept": "application/json, text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Referer": f"{SITE_BASE}/",
}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BaoZiMHConnector(SourceConnector):
    """Browse and read manhua from BaoZiMH (包子漫畫)."""

    SOURCE_TYPE = "baozimh"
    DISPLAY_NAME = "BaoZiMH"
    DESCRIPTION = (
        "Browse and read Chinese manhua from BaoZiMH (baozimh.com). "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=REQUEST_HEADERS,
            user_agent=BROWSER_USER_AGENT,
            min_interval=0.35,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)

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
        return frozenset(
            {
                "static-tw.baozimh.com",
                "static-cn.baozimh.com",
                "bzcdn.net",
                "twmanga.com",
            }
        )

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": "https://www.twmanga.com/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="serial", label="Ongoing"),
            BrowseMode(id="completed", label="Completed"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return genres_to_browse_modes()

    def _fetch_listing(
        self,
        page: int,
        *,
        sort: str | None = None,
        genre: str | None = None,
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        params = listing_params(
            page,
            state=resolve_list_state(sort),
            type_filter=(genre.strip() if genre else "all") or "all",
        )
        payload = self._http.get_json(LIST_API_PATH, params=params)
        if not isinstance(payload, dict):
            raise ConnectorHttpError("Expected JSON object from BaoZiMH list API.")
        listing = series_list_to_paginated(payload, page=page)
        logger.info(
            "BaoZiMH browse sort=%r genre=%r page=%d count=%d has_more=%s",
            sort,
            genre,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._fetch_listing(page, sort=sort)

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        return self._fetch_listing(page, sort=sort, genre=genre)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        del sort  # BaoZiMH search HTML has no sort/pagination query.
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page)
        if page > 1:
            return PaginatedSeriesList(items=[], page=page, page_size=PAGE_SIZE, total=0, api_has_more=False)
        html = self._http.get_text("/search", params={"q": normalized})
        items = parse_search_listing(html)
        return PaginatedSeriesList(
            items=items,
            page=1,
            page_size=max(len(items), 1),
            total=len(items),
            api_has_more=False,
        )

    def get_series(self, series_id: str) -> Series | None:
        comic_id = comic_id_from_path(series_id)
        cached = self._series_cache.get(comic_id)
        if cached is not None:
            return cached
        try:
            html = self._http.get_text(f"/comic/{comic_id}")
        except ConnectorHttpError:
            return None
        series = parse_series_detail(html, comic_id=comic_id)
        if series is None:
            return None
        self._series_cache.set(comic_id, series)
        self._chapter_list_cache.set(comic_id, parse_chapters(html, comic_id=comic_id))
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        comic_id = comic_id_from_path(series_id)
        cached = self._chapter_list_cache.get(comic_id)
        if cached is not None:
            return cached
        try:
            html = self._http.get_text(f"/comic/{comic_id}")
        except ConnectorHttpError:
            return []
        chapters = parse_chapters(html, comic_id=comic_id)
        self._chapter_list_cache.set(comic_id, chapters)
        series = parse_series_detail(html, comic_id=comic_id)
        if series is not None:
            self._series_cache.set(comic_id, series)
        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return self._page_cache.get_or_set(chapter_id, lambda: self._fetch_chapter_pages(chapter_id))

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        parsed = parse_chapter_id(chapter_id)
        if parsed is None:
            return []
        comic_id, section_slot, chapter_slot = parsed
        try:
            html = self._http.get_text(chapter_page_path(comic_id, section_slot, chapter_slot))
        except ConnectorHttpError:
            return []
        return parse_chapter_pages(html, chapter_id=chapter_id)

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
