"""GalaxyManga online source connector (Themesia mangareader HTML)."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.galaxymanga.mappers import (
    BROWSE_PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    SITE_BASE,
    chapter_id_to_path,
    listing_params,
    listing_path,
    normalize_sort,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_params,
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


class GalaxyMangaConnector(SourceConnector):
    """Browse and read manga/manhwa from GalaxyManga (galaxymanga.io)."""

    SOURCE_TYPE = "galaxymanga"
    DISPLAY_NAME = "GalaxyManga"
    DESCRIPTION = (
        "Browse and read manga and manhwa from GalaxyManga. "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(SITE_BASE, headers=HTML_HEADERS)
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
        # Covers on galaxymanga.io; chapter pages on dl.galaxymanga.io CDN.
        return frozenset({"galaxymanga.io", "dl.galaxymanga.io"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Recently Updated"),
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="rating", label="A-Z"),
        ]

    def _log_request(
        self,
        operation: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        status: str,
        detail: str | None = None,
    ) -> None:
        message = (
            f"GalaxyManga {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value.removeprefix("manga/")
        return value.strip("/")

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return fully_unquote(chapter_id).strip().strip("/")

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
        path = listing_path()
        params = listing_params(page=page, sort=sort)
        try:
            document = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log_request("browse", path, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(document, page=page, page_size=BROWSE_PAGE_SIZE)
        self._log_request(
            "browse",
            path,
            params=params,
            status="ok",
            detail=(
                f"page={page} sort={normalize_sort(sort)!r} count={len(listing.items)} "
                f"has_more={listing.has_more}"
            ),
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        path = search_path(page)
        params = search_params(normalized)
        try:
            document = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log_request("search", path, params=params, status="error", detail=str(exc))
            raise
        listing = parse_search_results(document, page=page, page_size=SEARCH_PAGE_SIZE)
        self._log_request(
            "search",
            path,
            params=params,
            status="ok",
            detail=(
                f"page={page} query={normalized!r} count={len(listing.items)} "
                f"has_more={listing.has_more}"
            ),
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached

        path = series_id_to_path(api_key)
        try:
            document = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("detail", path, status="error", detail=str(exc))
            return None

        series = parse_series_detail(document, api_key)
        if series is None:
            self._log_request("detail", path, status="error", detail="parse failed")
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
        self._log_request(
            "detail",
            path,
            status="ok",
            detail=f"chapters={series.chapter_count}",
        )
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)

        path = series_id_to_path(api_key)
        try:
            document = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("chapters", path, status="error", detail=str(exc))
            return []

        chapters = parse_chapters(document, api_key)
        if chapters:
            self._chapter_list_cache.set(api_key, chapters)
        enriched = self._enrich_chapters(chapters)
        self._log_request(
            "chapters",
            path,
            status="ok",
            detail=f"count={len(enriched)}",
        )
        return enriched

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached

        path = chapter_id_to_path(api_key)
        try:
            document = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("pages", path, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(document, api_key)
        if pages:
            self._page_cache.set(api_key, pages)
            self._remember_page_count(api_key, len(pages))
        self._log_request(
            "pages",
            path,
            status="ok",
            detail=f"count={len(pages)}",
        )
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
