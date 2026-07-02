"""DemonicScans online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any
from urllib.parse import unquote

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.demonicscans.mappers import (
    PAGE_SIZE,
    SITE_BASE,
    chapter_id_to_reader_path,
    listing_path,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
)

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def series_id_to_path(series_id: str) -> str:
    return f"/manga/{series_id.strip().strip('/')}"


class DemonicScansConnector(SourceConnector):
    SOURCE_TYPE = "demonicscans"
    DISPLAY_NAME = "DemonicScans"
    DESCRIPTION = "Browse and read manga/manhwa from DemonicScans (HTML catalog)."
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            user_agent=BROWSER_USER_AGENT,
        )
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
        return frozenset({"demonicscans.org", "demoniclibs.com"})

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest"),
            BrowseMode(id="popular", label="Popular"),
        ]

    def _normalize_series_id(self, series_id: str) -> str:
        return unquote(series_id).strip().strip("/").removeprefix("manga/")

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return unquote(chapter_id).strip().strip("/")

    def _slice_page(self, items: list[Series], page: int) -> PaginatedSeriesList:
        safe_page = max(page, 1)
        start = (safe_page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        sliced = items[start:end]
        total = len(items)
        return PaginatedSeriesList(
            items=sliced,
            page=safe_page,
            page_size=PAGE_SIZE,
            total=total,
            api_has_more=end < total,
        )

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        mode = "popular" if sort == "popular" else "latest"
        path = listing_path(page, kind=mode)
        html = self._http.get_text(path)
        listing = parse_series_list(html, page=1, page_size=PAGE_SIZE)
        return self._slice_page(listing.items, page)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        normalized = query.strip().casefold()
        path = listing_path(page, kind="search")
        html = self._http.get_text(path)
        listing = parse_series_list(html, page=1, page_size=PAGE_SIZE)
        if not normalized:
            return self._slice_page(listing.items, page)
        filtered = [item for item in listing.items if normalized in item.title.casefold()]
        return self._slice_page(filtered, page)

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached
        path = series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return None
        series = parse_series_detail(html, api_key)
        if series is None:
            return None
        chapters = self.get_chapters(api_key)
        if chapters:
            series = Series(
                id=series.id,
                title=series.title,
                chapter_count=len(chapters),
                canonical_path=series.canonical_path,
                description=series.description,
                cover_url=series.cover_url,
                author=series.author,
                artist=series.artist,
                status=series.status,
                genres=series.genres,
                latest_chapter=chapters[-1].title,
            )
        self._series_cache.set(api_key, series)
        return series

    def _remember_page_count(self, chapter_id: str, page_count: int) -> None:
        if page_count > 0:
            self._chapter_page_count_cache.set(chapter_id, page_count)

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        out: list[Chapter] = []
        for ch in chapters:
            cached = self._chapter_page_count_cache.get(ch.id)
            out.append(replace(ch, page_count=cached) if cached else ch)
        return out

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)
        path = series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return []
        chapters = parse_chapters(html, api_key)
        self._chapter_list_cache.set(api_key, chapters)
        return self._enrich_chapters(chapters)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached
        path = chapter_id_to_reader_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return []
        pages = parse_chapter_pages(html, api_key)
        self._page_cache.set(api_key, pages)
        self._remember_page_count(api_key, len(pages))
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if not chapter_id:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None

