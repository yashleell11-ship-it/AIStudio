"""DemonicScans online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any
from connectors.base import SourceConnector
from connectors.demonicscans.mappers import (
    PAGE_SIZE,
    SEARCH_PATH,
    SITE_BASE,
    chapter_id_to_reader_path,
    listing_path,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_params,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series


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
        # Cover thumbnails are hosted on readermc.org; reader page images moved
        # to mangareadon.org (demoniclibs.com kept as a legacy fallback host).
        return frozenset(
            {
                "demonicscans.org",
                "demoniclibs.com",
                "readermc.org",
                "mangareadon.org",
            }
        )

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest"),
            BrowseMode(id="popular", label="Popular"),
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
            f"DemonicScans {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_id(self, series_id: str) -> str:
        return fully_unquote(series_id).strip().strip("/").removeprefix("manga/")

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return fully_unquote(chapter_id).strip().strip("/")

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        mode = "popular" if sort == "popular" else "latest"
        path = listing_path(page, kind=mode)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("browse", path, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._log_request(
            "browse",
            path,
            status="ok",
            detail=f"page={page} sort={sort!r} count={len(listing.items)} total={listing.total}",
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        """Query DemonicScans' own search endpoint.

        This used to fetch ``/advanced.php`` -- one fixed 85KB catalog page --
        and substring-filter its titles in Python. That is not a search: it
        could only ever find the ~56 series that happened to be on that page,
        so a query for anything else returned nothing while reporting success.
        ``/search.php?manga=<q>`` is the site's real search, answers in ~0.2s
        with 17KB, and covers the whole catalog.
        """
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            # An empty query is a browse, not a search.
            path = listing_path(page, kind="search")
            try:
                html = self._http.get_text(path)
            except ConnectorHttpError as exc:
                self._log_request("search", path, status="error", detail=str(exc))
                raise
            listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
            self._log_request(
                "search",
                path,
                status="ok",
                detail=f"page={page} query='' count={len(listing.items)} total={listing.total}",
            )
            return listing

        params = search_params(normalized)
        try:
            html = self._http.get_text(SEARCH_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log_request("search", SEARCH_PATH, params=params, status="error", detail=str(exc))
            raise
        result = parse_search_results(
            html, page=page, query=normalized, page_size=PAGE_SIZE
        )
        self._log_request(
            "search",
            SEARCH_PATH,
            params=params,
            status="ok",
            detail=f"page={page} query={normalized!r} count={len(result.items)}",
        )
        return result

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached
        path = series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("detail", path, status="error", detail=str(exc))
            return None
        series = parse_series_detail(html, api_key)
        if series is None:
            self._log_request("detail", path, status="error", detail="parse failed")
            return None
        # The chapter rows are already in the document just fetched, so seed
        # the cache from it. get_chapters -- called on the next line, and again
        # by the reader a moment later -- would otherwise re-download this
        # exact page: a second full-page GET on every series detail open.
        if self._chapter_list_cache.get(api_key) is None:
            self._chapter_list_cache.set(api_key, parse_chapters(html, api_key))
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
        except ConnectorHttpError as exc:
            self._log_request("chapters", path, status="error", detail=str(exc))
            return []
        chapters = parse_chapters(html, api_key)
        self._chapter_list_cache.set(api_key, chapters)
        enriched = self._enrich_chapters(chapters)
        self._log_request("chapters", path, status="ok", detail=f"count={len(enriched)}")
        return enriched

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached
        path = chapter_id_to_reader_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("pages", path, status="error", detail=str(exc))
            return []
        pages = parse_chapter_pages(html, api_key)
        self._page_cache.set(api_key, pages)
        self._remember_page_count(api_key, len(pages))
        self._log_request("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if not chapter_id:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None

