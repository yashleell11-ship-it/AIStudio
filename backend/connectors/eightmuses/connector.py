"""8muses online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace

from connectors.base import SourceConnector
from connectors.eightmuses.mappers import (
    PAGE_SIZE,
    SITE_BASE,
    album_path,
    listing_path,
    normalize_sort,
    page_id_chapter_id,
    parse_album_tiles,
    parse_chapter_pages,
    parse_chapters,
    parse_publishers,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    publisher_album_path,
    search_path,
)
from connectors.http.cache import TTLCache
from connectors.http.cf_client import CfSyncHttpClient
from connectors.http.client import ConnectorHttpError
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_IMPERSONATE = "chrome131"


class EightMusesConnector(SourceConnector):
    """Browse and read comics from 8muses (Ractive album catalog)."""

    SOURCE_TYPE = "8muses"
    DISPLAY_NAME = "8Muses"
    DESCRIPTION = (
        "Browse and read porn comics, 3D art, and hentai from 8muses. "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = CfSyncHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            impersonate=BROWSER_IMPERSONATE,
        )
        self._publisher_cache: TTLCache[list[str]] = TTLCache(ttl_seconds=3600.0)
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._chapter_page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)

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
        return frozenset({"comics.8muses.com", "8muses.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Views"),
            BrowseMode(id="latest", label="Date"),
            BrowseMode(id="popular", label="Likes"),
        ]

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("comics/album/"):
            value = value.removeprefix("comics/album/")
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return self._normalize_series_id(chapter_id)

    def _fetch_html(self, path: str) -> str:
        return self._http.get_text(path)

    def _publishers(self, *, sort: str | None = None) -> list[str]:
        cache_key = normalize_sort(sort) or "default"
        cached = self._publisher_cache.get(cache_key)
        if cached is not None:
            return cached

        document = self._fetch_html(listing_path(1, sort=sort))
        publishers = parse_publishers(document)
        self._publisher_cache.set(cache_key, publishers)
        return publishers

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached_count = self._chapter_page_count_cache.get(chapter.id)
            if cached_count is not None and cached_count > 0:
                enriched.append(replace(chapter, page_count=cached_count))
            else:
                enriched.append(chapter)
        return enriched

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        publishers = self._publishers(sort=sort)
        if not publishers:
            return PaginatedSeriesList(items=[], page=page, page_size=PAGE_SIZE, total=0)

        publisher_index = page - 1
        if publisher_index >= len(publishers):
            return PaginatedSeriesList(
                items=[],
                page=page,
                page_size=PAGE_SIZE,
                total=len(publishers) * PAGE_SIZE,
                api_has_more=False,
            )

        publisher_id = publishers[publisher_index]
        document = self._fetch_html(publisher_album_path(publisher_id, sort=sort))
        items = parse_album_tiles(document, parent_id=publisher_id)
        listing = parse_series_list(
            document,
            page=page,
            has_more=publisher_index + 1 < len(publishers),
        )
        listing = PaginatedSeriesList(
            items=items,
            page=page,
            page_size=PAGE_SIZE,
            total=len(publishers) * PAGE_SIZE,
            api_has_more=listing.has_more,
        )
        for item in items:
            if item.cover_url:
                self._series_cache.set(item.id, item)
        logger.info(
            "8muses browse publisher=%r page=%d count=%d has_more=%s",
            publisher_id,
            page,
            len(items),
            listing.has_more,
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        document = self._fetch_html(search_path(normalized))
        listing = parse_search_results(document, page=page, query=normalized)
        for item in listing.items:
            if item.cover_url:
                self._series_cache.set(item.id, item)
        logger.info(
            "8muses search query=%r page=%d count=%d",
            normalized,
            page,
            len(listing.items),
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        series_id = self._normalize_series_id(series_id)
        cached = self._series_cache.get(series_id)
        if cached is not None:
            return cached
        try:
            document = self._fetch_html(album_path(series_id))
        except ConnectorHttpError:
            return None
        series = parse_series_detail(document, series_id=series_id)
        if series is None:
            return None
        self._series_cache.set(series_id, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_id = self._normalize_series_id(series_id)
        return self._enrich_chapters(
            self._chapter_list_cache.get_or_set(
                series_id,
                lambda: self._fetch_chapters(series_id),
            )
        )

    def _fetch_chapters(self, series_id: str) -> list[Chapter]:
        try:
            document = self._fetch_html(album_path(series_id))
        except ConnectorHttpError:
            return []
        return parse_chapters(document, series_id=series_id)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_id = self._normalize_chapter_id(chapter_id)
        pages = self._page_cache.get_or_set(
            chapter_id,
            lambda: self._fetch_chapter_pages(chapter_id),
        )
        self._chapter_page_count_cache.set(chapter_id, len(pages))
        return pages

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        try:
            document = self._fetch_html(album_path(chapter_id))
        except ConnectorHttpError:
            return []
        return parse_chapter_pages(document, chapter_id=chapter_id)

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
