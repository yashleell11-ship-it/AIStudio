"""RawINU online source connector.

Request budget per user action (measured from the VPS, see module tests):

* browse / search / genre — **1** request. One endpoint, three query shapes.
* series detail — **2** requests (metadata page + the one-shot chapter list),
  and the second one is cached so the ``get_chapters`` call that always
  follows it costs **0**.
* open a chapter — **1** request; every page image URL is in that response.
* image proxy (``find_page``) — **0** while the chapter is warm.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.rawinu.mappers import (
    CHAPTER_LIST_PATH,
    IMAGE_HOSTS,
    LIST_PATH,
    PAGE_SIZE,
    SITE_BASE,
    chapter_id_to_path,
    listing_params,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_genres,
    parse_series_detail,
    parse_series_list,
    series_id_to_path,
)

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}


class RawInuConnector(SourceConnector):
    """Browse and read RAW (untranslated Japanese) manga from RawINU."""

    SOURCE_TYPE = "rawinu"
    DISPLAY_NAME = "RawINU"
    DESCRIPTION = (
        "Browse and read RAW (untranslated Japanese) manga from RawINU. "
        "Titles and metadata are romaji with the native Japanese name listed "
        "alongside. Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            user_agent=BROWSER_USER_AGENT,
            headers=HTML_HEADERS,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._chapter_page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)
        self._genre_cache: TTLCache[list[BrowseMode]] = TTLCache(ttl_seconds=3600.0)

    # -- descriptor ------------------------------------------------------

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
        # Covers and page images both come from s2/s4.ihlv1.xyz.
        return IMAGE_HOSTS

    def image_fetch_headers(self) -> dict[str, str]:
        # Verified from the VPS: the CDN serves image bytes with a correct
        # `image/jpeg` content-type and does NOT enforce hotlink protection.
        # The Referer is sent anyway so a later origin policy change degrades
        # to working rather than to broken pages.
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest Updates"),
            BrowseMode(id="popular", label="Most Viewed"),
            BrowseMode(id="alpha", label="A-Z"),
        ]

    # -- internals -------------------------------------------------------

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
            f"RawINU {operation} {SITE_BASE}{path} params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_id(self, series_id: str) -> str:
        """Percent-decode and trim. The key is otherwise opaque and unparsed."""
        return fully_unquote(series_id).strip().strip("/")

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return fully_unquote(chapter_id).strip().strip("/")

    def _browse(
        self,
        page: int,
        *,
        sort: str | None,
        name: str | None = None,
        genre: str | None = None,
        operation: str = "browse",
    ) -> PaginatedSeriesList:
        """The single listing path shared by browse, search and genre browse."""
        if page < 1:
            page = 1
        params = listing_params(page, sort=sort, name=name, genre=genre)
        try:
            html = self._http.get_text(LIST_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log_request(
                operation, LIST_PATH, params=params, status="error", detail=str(exc)
            )
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._cache_genres(html)
        self._log_request(
            operation,
            LIST_PATH,
            params=params,
            status="ok",
            detail=(
                f"page={page} count={len(listing.items)} total={listing.total} "
                f"has_more={listing.has_more}"
            ),
        )
        return listing

    def _cache_genres(self, html: str) -> None:
        """Harvest the genre sidebar from a listing response already in hand.

        The genre vocabulary ships on every listing page, so ``list_genres``
        never needs a request of its own.
        """
        if self._genre_cache.get("genres") is not None:
            return
        genres = [BrowseMode(id=slug, label=label) for slug, label in parse_genres(html)]
        if genres:
            self._genre_cache.set("genres", genres)

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached_count = self._chapter_page_count_cache.get(chapter.id)
            if cached_count:
                enriched.append(replace(chapter, page_count=cached_count))
            else:
                enriched.append(chapter)
        return enriched

    def _fetch_chapters(self, series_key: str) -> list[Chapter]:
        """Fetch the complete chapter list from the site's own XHR endpoint."""
        params = {"slug": series_key}
        try:
            html = self._http.get_text(CHAPTER_LIST_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log_request(
                "chapters", CHAPTER_LIST_PATH, params=params,
                status="error", detail=str(exc),
            )
            return []
        chapters = parse_chapters(html, series_key)
        if chapters:
            self._chapter_list_cache.set(series_key, chapters)
        self._log_request(
            "chapters", CHAPTER_LIST_PATH, params=params,
            status="ok", detail=f"count={len(chapters)}",
        )
        return chapters

    # -- browse ----------------------------------------------------------

    def get_series_list(
        self, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        return self._browse(page, sort=sort)

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._browse(page, sort=sort, name=normalized, operation="search")

    def list_genres(self) -> list[BrowseMode]:
        cached = self._genre_cache.get("genres")
        if cached is not None:
            return cached
        try:
            self._browse(1, sort=None, operation="genres")
        except ConnectorHttpError:
            return []
        return self._genre_cache.get("genres") or []

    def browse_by_genre(
        self, genre: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        return self._browse(page, sort=sort, genre=genre.strip(), operation="genre")

    # -- detail ----------------------------------------------------------

    def get_series(self, series_id: str) -> Series | None:
        series_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(series_key)
        if cached is not None:
            return cached

        path = series_id_to_path(series_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("detail", path, status="error", detail=str(exc))
            return None

        series = parse_series_detail(html, series_key)
        if series is None:
            # RawINU answers 200 with its homepage for an unknown slug, so a
            # failed parse here IS the not-found signal — never a 404.
            self._log_request("detail", path, status="error", detail="not found")
            return None

        # The chapter list is NOT in the page just fetched — it is XHR-loaded
        # from a separate endpoint. Pull it now (11-19KB, ~180ms) so the
        # get_chapters call the reader makes immediately after this is served
        # from cache instead of costing a second round trip.
        chapters = self.get_chapters(series_key)
        if chapters:
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=chapters[-1].title,
            )

        self._series_cache.set(series_key, series)
        self._log_request(
            "detail", path, status="ok", detail=f"chapters={series.chapter_count}"
        )
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(series_key)
        if cached is None:
            cached = self._fetch_chapters(series_key)
        return self._enrich_chapters(cached)

    # -- reading ---------------------------------------------------------

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_id_to_path(chapter_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("pages", path, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(html, chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._chapter_page_count_cache.set(chapter_key, len(pages))
        self._log_request("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
