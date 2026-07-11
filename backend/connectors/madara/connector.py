"""Generic Madara-theme source connector."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any
from connectors.ids import fully_unquote

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.cf_client import CfSyncHttpClient
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.madara.config import MadaraSiteConfig
from connectors.madara.mappers import MadaraHtml
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_IMPERSONATE = "chrome131"

# Alternate url_segment values when the configured one returns an empty listing.
LISTING_FALLBACKS = ("manga", "serie")


class MadaraConnector(SourceConnector):
    """Browse/read any WordPress Madara-theme catalog via site config."""

    # Subclasses set these from factory.
    CONFIG: MadaraSiteConfig
    SOURCE_TYPE: str
    DISPLAY_NAME: str
    DESCRIPTION: str
    MATURE: bool = False

    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        cfg = self.CONFIG
        if cfg.use_cf:
            self._http: SyncConnectorHttpClient | CfSyncHttpClient = CfSyncHttpClient(
                cfg.base_url,
                headers=HTML_HEADERS,
                impersonate=BROWSER_IMPERSONATE,
            )
        else:
            self._http = SyncConnectorHttpClient(cfg.base_url, headers=HTML_HEADERS)
        self._html = MadaraHtml(cfg)
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
        return self.CONFIG.image_hosts

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{self.CONFIG.base_url.rstrip('/')}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest"),
            BrowseMode(id="latest", label="New"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="rating", label="Top Rated"),
        ]

    def _log(self, operation: str, path: str, **detail: object) -> None:
        logger.info("%s %s %s %s", self.DISPLAY_NAME, operation, path, detail)

    def _normalize_series_id(self, series_id: str) -> str:
        seg = self.CONFIG.url_segment
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith(f"{seg}/"):
            value = value.removeprefix(f"{seg}/")
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return self._normalize_series_id(chapter_id)

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
        if page_count <= 0:
            return
        self._chapter_page_count_cache.set(chapter_id, page_count)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        segments = [self.CONFIG.url_segment]
        for alt in LISTING_FALLBACKS:
            if alt not in segments:
                segments.append(alt)

        last_error: Exception | None = None
        for seg in segments:
            cfg = self.CONFIG if seg == self.CONFIG.url_segment else replace(
                self.CONFIG, url_segment=seg
            )
            html_parser = MadaraHtml(cfg) if seg != self.CONFIG.url_segment else self._html
            path = html_parser.listing_path(page)
            params = html_parser.listing_params(sort=sort)
            try:
                html = self._http.get_text(path, params=params)
            except ConnectorHttpError as exc:
                last_error = exc
                continue
            listing = html_parser.parse_series_list(html, page=page)
            if listing.items:
                if seg != self.CONFIG.url_segment:
                    logger.info(
                        "%s browse via alternate segment %r (%d items)",
                        self.DISPLAY_NAME,
                        seg,
                        len(listing.items),
                    )
                return listing
        if last_error is not None:
            raise last_error
        return PaginatedSeriesList(
            items=[],
            page=page,
            page_size=self.CONFIG.page_size,
            total=0,
            api_has_more=False,
        )

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        path = "/"
        params = self._html.search_params(normalized, page=page)
        html = self._http.get_text(path, params=params)
        return self._html.parse_search_results(
            html, page=page, query=normalized
        )

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached

        path = self._html.series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return None

        series = self._html.parse_series_detail(html, api_key)
        if series is None:
            return None

        chapters = self._html.parse_chapters(html, api_key)
        if not chapters:
            chapters = self.get_chapters(api_key)
        elif self._chapter_list_cache.get(api_key) is None:
            self._chapter_list_cache.set(api_key, chapters)

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

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)

        path = self._html.series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return []

        chapters = self._html.parse_chapters(html, api_key)
        if chapters:
            self._chapter_list_cache.set(api_key, chapters)
        return self._enrich_chapters(chapters)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached

        path = self._html.chapter_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return []

        pages = self._html.parse_chapter_pages(html, api_key)
        if pages:
            self._page_cache.set(api_key, pages)
            self._remember_page_count(api_key, len(pages))
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = MadaraHtml.page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
