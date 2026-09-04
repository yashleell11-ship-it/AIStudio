"""MangaPill online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.mangapill.mappers import (
    IMAGE_CDN_HOST,
    LATEST_MODE,
    PAGE_SIZE,
    SITE_BASE,
    browse_params,
    chapter_path,
    genre_params,
    list_browse_modes,
    list_genres,
    normalize_chapter_key,
    normalize_series_key,
    normalize_sort,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_latest_cards,
    parse_series_detail,
    parse_series_list,
    search_params,
    series_path,
    slice_latest,
)
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_PATH = "/search"
LATEST_PATH = "/chapters"


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses; a 404 arrives carrying httpx's ``raise_for_status`` message
    ("Client error '404 Not Found' for url ..."), so match both forms -- a
    bare ``status_code == 404`` check here would be dead code. Verified from
    the VPS: unknown series and chapter paths both answer a real 404.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class MangaPillConnector(SourceConnector):
    """Browse and read English manga from MangaPill (HTML catalog).

    Request budget, which is the whole point of the caching below:

    * series detail  -- 1 GET (the page carries the full chapter list, so
      ``get_series`` + ``get_chapters`` share one fetch via ``_detail_cache``)
    * chapter open   -- 1 GET (every page image URL is inline in the reader
      HTML, with width/height, so pages cost no extra request)
    * page image     -- 0 GETs to MangaPill; the proxy fetches the CDN direct
    * latest browse  -- 1 GET for all 120 entries, then sliced locally
    """

    SOURCE_TYPE = "mangapill"
    DISPLAY_NAME = "MangaPill"
    DESCRIPTION = (
        "Browse and read English manga from MangaPill. Images are proxied "
        "through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            extra_redirect_hosts=frozenset({IMAGE_CDN_HOST}),
        )
        # Detail and chapter list come from ONE document, so they share ONE
        # cache entry: opening a series and then its chapter list is a single
        # upstream GET, not two of the same 270KB page.
        self._detail_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._latest_cache: TTLCache[list[Series]] = TTLCache(ttl_seconds=180.0)
        self._chapter_page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)

    # --- descriptor ---------------------------------------------------------

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
        # Covers and chapter page images alike come from the one CDN
        # (cdn.readdetectiveconan.com); mangapill.com itself serves no images.
        return frozenset({"readdetectiveconan.com", "mangapill.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        """MangaPill's CDN hotlink-protects every image.

        Measured from the VPS: a page image requested without a Referer
        answers ``403`` with a 4.9KB HTML error body, and the identical URL
        with ``Referer: https://mangapill.com/`` answers ``200 image/png``.
        Covers behave the same way, so without this header the whole source
        renders as broken thumbnails and unreadable chapters.
        """
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return list_browse_modes()

    def list_genres(self) -> list[BrowseMode]:
        return list_genres()

    # --- helpers ------------------------------------------------------------

    def _log(
        self,
        operation: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        status: str,
        detail: str | None = None,
    ) -> None:
        message = (
            f"MangaPill {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _listing(
        self,
        operation: str,
        params: dict[str, Any],
        *,
        page: int,
    ) -> PaginatedSeriesList:
        try:
            html = self._http.get_text(SEARCH_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log(operation, SEARCH_PATH, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page)
        self._log(
            operation,
            SEARCH_PATH,
            params=params,
            status="ok",
            detail=f"count={len(listing.items)} has_more={listing.has_more}",
        )
        return listing

    def _enrich(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill page_count from chapters already read this session."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached = self._chapter_page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=cached) if cached else chapter)
        return enriched

    def _fetch_detail(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        """One GET for both the series metadata and its full chapter list."""
        cached = self._detail_cache.get(series_key)
        if cached is not None:
            return cached

        path = series_path(series_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("detail", path, status="not_found")
                return None, []
            self._log("detail", path, status="error", detail=str(exc))
            raise

        series = parse_series_detail(html, series_key)
        if series is None:
            self._log("detail", path, status="error", detail="parse failed")
            return None, []

        chapters = parse_chapters(html, series_key)
        if chapters:
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=chapters[-1].title,
            )
        result = (series, chapters)
        self._detail_cache.set(series_key, result)
        self._log("detail", path, status="ok", detail=f"chapters={len(chapters)}")
        return result

    # --- catalog ------------------------------------------------------------

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(page, 1)
        mode = normalize_sort(sort)
        if mode == LATEST_MODE:
            return self._latest(page)
        return self._listing("browse", browse_params(mode, page), page=page)

    def _latest(self, page: int) -> PaginatedSeriesList:
        """``/chapters`` is one un-paginated document; fetch once, slice often."""
        cached = self._latest_cache.get(LATEST_PATH)
        if cached is None:
            try:
                html = self._http.get_text(LATEST_PATH)
            except ConnectorHttpError as exc:
                self._log("browse", LATEST_PATH, status="error", detail=str(exc))
                raise
            cached = parse_latest_cards(html)
            if cached:
                self._latest_cache.set(LATEST_PATH, cached)
            self._log("browse", LATEST_PATH, status="ok", detail=f"series={len(cached)}")
        return slice_latest(cached, page=page)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(page, 1)
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing("search", search_params(normalized, page), page=page)

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        page = max(page, 1)
        return self._listing("genre", genre_params(genre, page), page=page)

    # --- series / chapters --------------------------------------------------

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_detail(normalize_series_key(series_id))[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._enrich(self._fetch_detail(normalize_series_key(series_id))[1])

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = normalize_chapter_key(chapter_id)
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_path(chapter_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("pages", path, status="not_found")
                return []
            self._log("pages", path, status="error", detail=str(exc))
            raise

        pages = parse_chapter_pages(html, chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._chapter_page_count_cache.set(chapter_key, len(pages))
        self._log("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        """O(1) upstream: the page id carries its chapter, which is cached."""
        chapter_key = page_id_chapter_key(page_id)
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
