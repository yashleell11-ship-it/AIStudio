"""Bbato (bbato.com) online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace

from connectors.base import SourceConnector
from connectors.bbato.mappers import (
    BROWSE_MODES,
    GENRES,
    IMAGE_HOST,
    PAGE_SIZE,
    SITE_BASE,
    chapter_id_to_path,
    genre_path,
    last_chapter_path,
    listing_path,
    normalize_type_sort,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters_from_reader,
    parse_chapters_from_series,
    parse_genre_results,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_path,
    series_id_to_path,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BbatoConnector(SourceConnector):
    """Browse and read manga from Bbato (bbato.com BATOTO mirror)."""

    SOURCE_TYPE = "bbato"
    DISPLAY_NAME = "Bbato"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from Bbato (bbato.com). "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            user_agent=BROWSER_USER_AGENT,
            min_interval=0.15,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._chapter_page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)
        self._readable_cache: TTLCache[bool] = TTLCache(ttl_seconds=3600.0)

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
        return frozenset({IMAGE_HOST})

    def image_fetch_headers(self) -> dict[str, str]:
        # CDN returns 403 without a site Referer.
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return list(BROWSE_MODES)

    def list_genres(self) -> list[BrowseMode]:
        return list(GENRES)

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value.removeprefix("manga/")
        if value.startswith("read/"):
            value = value.removeprefix("read/")
        if "/" in value:
            value = value.split("/", 1)[0]
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        value = fully_unquote(chapter_id).strip().strip("/")
        if value.startswith("read/"):
            value = value.removeprefix("read/")
        return value

    def _fetch_html(self, path: str) -> str:
        return self._http.get_text(path)

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached_count = self._chapter_page_count_cache.get(chapter.id)
            if cached_count is not None and cached_count > 0:
                enriched.append(replace(chapter, page_count=cached_count))
            else:
                enriched.append(chapter)
        return enriched

    def _remember_page_count(self, chapter_id: str, page_count: int) -> None:
        if page_count > 0:
            self._chapter_page_count_cache.set(chapter_id, page_count)

    def _series_has_chapters(self, series_id: str) -> bool:
        cached = self._readable_cache.get(series_id)
        if cached is not None:
            return cached
        try:
            html = self._fetch_html(series_id_to_path(series_id))
        except ConnectorHttpError:
            self._readable_cache.set(series_id, False)
            return False
        has = bool(last_chapter_path(html) or parse_chapters_from_series(html, series_id))
        self._readable_cache.set(series_id, has)
        return has

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = listing_path(page, sort=sort)
        html = self._fetch_html(path)
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE, sort=sort)
        logger.info(
            "Bbato browse sort=%r page=%d count=%d has_more=%s",
            normalize_type_sort(sort),
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        path = search_path(normalized, page)
        html = self._fetch_html(path)
        listing = parse_search_results(html, page=page, page_size=PAGE_SIZE)
        logger.info(
            "Bbato search page=%d count=%d query=%r",
            page,
            len(listing.items),
            normalized,
        )
        return listing

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        del sort  # genre pages have a single catalog order
        if page < 1:
            page = 1
        slug = genre.strip().strip("/").lower()
        path = genre_path(slug, page)
        html = self._fetch_html(path)
        listing = parse_genre_results(html, page=page, genre=slug, page_size=PAGE_SIZE)
        logger.info(
            "Bbato genre=%r page=%d count=%d has_more=%s",
            slug,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached
        try:
            html = self._fetch_html(series_id_to_path(api_key))
        except ConnectorHttpError:
            return None
        series = parse_series_detail(html, api_key)
        if series is None:
            return None
        embedded = parse_chapters_from_series(html, api_key)
        if embedded:
            series = replace(
                series,
                latest_chapter=embedded[-1].title,
                chapter_count=series.chapter_count or len(embedded),
            )
        self._series_cache.set(api_key, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        return self._enrich_chapters(
            self._chapter_list_cache.get_or_set(api_key, lambda: self._fetch_chapters(api_key))
        )

    def _fetch_chapters(self, series_id: str) -> list[Chapter]:
        try:
            series_html = self._fetch_html(series_id_to_path(series_id))
        except ConnectorHttpError:
            return []

        # Series page only embeds the latest ~20 chapters; the reader
        # chapter <select> has the full list.
        reader_path = last_chapter_path(series_html)
        if reader_path:
            try:
                reader_html = self._fetch_html(reader_path)
            except ConnectorHttpError:
                reader_html = ""
            chapters = parse_chapters_from_reader(reader_html, series_id)
            if chapters:
                return chapters

        return parse_chapters_from_series(series_html, series_id)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        return self._page_cache.get_or_set(api_key, lambda: self._fetch_chapter_pages(api_key))

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        try:
            html = self._fetch_html(chapter_id_to_path(chapter_id))
        except ConnectorHttpError:
            return []
        pages = parse_chapter_pages(html, chapter_id)
        self._remember_page_count(chapter_id, len(pages))
        logger.info("Bbato pages chapter_id=%s count=%d", chapter_id, len(pages))
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
