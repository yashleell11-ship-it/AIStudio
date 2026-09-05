"""GuaziManhua (瓜子漫画) online source connector — general-audience manhua."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.guazimanhua.mappers import (
    CATEGORY_PATH,
    CHAPTER_PATH,
    IMAGE_HOST_SUFFIX,
    PAGE_SIZE,
    SERIES_PATH,
    SITE_BASE,
    browse_params,
    chapter_params,
    genre_params,
    list_browse_modes,
    list_genres,
    normalize_chapter_key,
    normalize_series_key,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    search_params,
    series_params,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"{SITE_BASE}/",
}


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses, so a 404 arrives as httpx's ``raise_for_status`` message
    ("Client error '404 Not Found' for url ..."); the attribute check alone
    would be dead code. Verified from the VPS: ``/comic.php?id=99999999``
    answers a real 404 with the site's own 3.4KB error page.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class GuaziManhuaConnector(SourceConnector):
    """Browse and read general-audience Chinese manhua from 瓜子漫画.

    Every stage is a single upstream request:

    * browse / search / genre -- 1 GET, 36 cards of server-rendered markup
    * series detail           -- 1 GET (``get_series`` + ``get_chapters`` share
      it via ``_detail_cache``; the page carries the full chapter list, 1,187
      entries on the largest series sampled)
    * chapter open            -- 1 GET, every page image inline as an ``<img>``
    * page image              -- 0 GETs here; the proxy fetches the CDN direct

    The origin sits on bare nginx at a single A record with NO Cloudflare in
    front, so plain httpx clears every stage -- no browser-impersonating
    client is needed here.

    General audience (mature=False): the site's whole tag vocabulary is
    mainstream (玄幻/都市/恋爱/古风/热血/校园/系统) and it publishes no adult
    section. Its page images are served out of an ``img.guazicdn.com/dm5/...``
    path space, i.e. it fronts the DM5 (动漫屋) library with flat integer-id
    URLs -- which is why this connector is cheap where a direct DM5 one is not.
    """

    SOURCE_TYPE = "guazimanhua"
    DISPLAY_NAME = "GuaziManhua"
    DESCRIPTION = (
        "Browse and read Chinese manhua from GuaziManhua (瓜子漫画). "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            user_agent=BROWSER_USER_AGENT,
            extra_redirect_hosts=frozenset({IMAGE_HOST_SUFFIX}),
        )
        # Detail and chapter list come from ONE document, so they share ONE
        # cache entry: opening a series and then its chapter list is a single
        # upstream GET, not two of the same 230KB page.
        self._detail_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
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
        # Covers and page images alike come from img.guazicdn.com, a domain
        # distinct from the site itself, so it must be allowlisted explicitly.
        # Measured from the VPS: the CDN does NOT hotlink-protect (cover and
        # page images both answered 200 with and without a Referer), so this
        # connector deliberately ships no image_fetch_headers override.
        return frozenset({IMAGE_HOST_SUFFIX})

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
            f"GuaziManhua {operation} {SITE_BASE}{path} "
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
            html = self._http.get_text(CATEGORY_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log(operation, CATEGORY_PATH, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page)
        self._log(
            operation,
            CATEGORY_PATH,
            params=params,
            status="ok",
            detail=f"count={len(listing.items)} has_more={listing.has_more}",
        )
        return listing

    def _empty_page(self, page: int) -> PaginatedSeriesList:
        return PaginatedSeriesList(
            items=[], page=max(page, 1), page_size=PAGE_SIZE, total=0, api_has_more=False
        )

    def _enrich(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill page_count from chapters already read this session."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached = self._chapter_page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=cached) if cached else chapter)
        return enriched

    def _fetch_detail(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        """One GET for both the series metadata and its full chapter list."""
        if not series_key:
            return None, []
        cached = self._detail_cache.get(series_key)
        if cached is not None:
            return cached

        params = series_params(series_key)
        try:
            html = self._http.get_text(SERIES_PATH, params=params)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("detail", SERIES_PATH, params=params, status="not_found")
                return None, []
            self._log("detail", SERIES_PATH, params=params, status="error", detail=str(exc))
            raise

        series = parse_series_detail(html, series_key)
        if series is None:
            self._log("detail", SERIES_PATH, params=params, status="error", detail="parse failed")
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
        self._log("detail", SERIES_PATH, params=params, status="ok", detail=f"chapters={len(chapters)}")
        return result

    # --- catalog ------------------------------------------------------------

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(page, 1)
        return self._listing("browse", browse_params(sort, page), page=page)

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        page = max(page, 1)
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing("search", search_params(normalized, page, sort=sort), page=page)

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        page = max(page, 1)
        params = genre_params(genre, page, sort=sort)
        if params is None:
            # ``cid`` is numeric, so a key outside the menu cannot be turned
            # into a request; empty beats serving the whole catalog as a genre.
            self._log("genre", CATEGORY_PATH, status="not_found", detail=f"genre={genre}")
            return self._empty_page(page)
        return self._listing("genre", params, page=page)

    # --- series / chapters --------------------------------------------------

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_detail(normalize_series_key(series_id))[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._enrich(self._fetch_detail(normalize_series_key(series_id))[1])

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = normalize_chapter_key(chapter_id)
        if not chapter_key:
            return []
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        params = chapter_params(chapter_key)
        try:
            html = self._http.get_text(CHAPTER_PATH, params=params)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("pages", CHAPTER_PATH, params=params, status="not_found")
                return []
            self._log("pages", CHAPTER_PATH, params=params, status="error", detail=str(exc))
            raise

        pages = parse_chapter_pages(html, chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._chapter_page_count_cache.set(chapter_key, len(pages))
        self._log("pages", CHAPTER_PATH, params=params, status="ok", detail=f"count={len(pages)}")
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
