"""MangaBuddy online source connector.

mangabuddy.com 301s to comizy.io, whose Next.js front end is served by a
public, unauthenticated JSON API at ``api.comizy.io``. Every stage is a single
JSON call, so this connector never parses HTML:

* ``GET /titles/search``                       -> catalog listing, search, genre browse
* ``GET /titles/<hsid>``                       -> series metadata (+ newest 50 chapters)
* ``GET /titles/<hsid>/chapters``              -> the complete chapter list, one shot
* ``GET /titles/<hsid>/chapters/<chapter>``    -> every page image, with dimensions

Cost per operation (measured from the VPS, see the module docstring in
``mappers`` for the routes' quirks):

* browse / search      1 request
* open a series        1 request when the series has <= 50 chapters (detail and
                       chapter list share the single detail fetch), 2 otherwise
* open a chapter       1 request for all of its images -- never one per page
* proxy a page image   0 requests (served from the chapter's cached page list)

Images are proxied through ManhwaManiacs; the CDN hosts are pinned by the SSRF
allowlist in ``allowed_image_hosts`` and require a site ``Referer`` (verified:
the CDN answers 403 without one).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.mangabuddy.mappers import (
    API_BASE,
    PAGE_SIZE,
    SEARCH_PATH,
    SITE_BASE,
    chapter_detail_path,
    chapters_path,
    declared_chapter_count,
    is_api_id,
    list_browse_modes,
    list_genres,
    make_chapter_key,
    normalize_series_key,
    normalize_sort,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_embedded_chapters,
    parse_series_detail,
    parse_series_list,
    search_params,
    series_path,
    split_chapter_key,
)
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
API_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": SITE_BASE,
    "Referer": f"{SITE_BASE}/",
}


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses; a 404 otherwise surfaces only as httpx's ``raise_for_status``
    message ("Client error '404 Not Found' for url ..."), so match both forms.
    Verified from the VPS: unknown title and chapter ids both answer a real
    404 (``{"success": false, "code": "NOT_FOUND", ...}``).
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class MangaBuddyConnector(SourceConnector):
    """Browse and read manga, manhwa and manhua from MangaBuddy (JSON API)."""

    SOURCE_TYPE = "mangabuddy"
    DISPLAY_NAME = "MangaBuddy"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from MangaBuddy. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    # A general, all-genre database like MangaDex or Weeb Central rather than a
    # dedicated adult site, so it stays visible without the mature opt-in.
    # Individual titles carry the site's own ``is_adult`` flag.
    MATURE = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            API_BASE,
            user_agent=BROWSER_USER_AGENT,
            headers=API_HEADERS,
        )
        # One detail fetch serves get_series AND get_chapters -- the cached
        # entry carries the parsed series, whatever chapters came embedded, and
        # whether that embedded list is already the whole thing.
        self._detail_cache: TTLCache[tuple[Series, list[Chapter], bool]] = TTLCache(
            ttl_seconds=300.0
        )
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
        # Page images round-robin across x1..x10.cmzcdn.org; covers are served
        # from rx.comizy.io. Allowlisting the registrable domains matches every
        # rotating shard (the proxy does suffix matching) while keeping the
        # SSRF allowlist to this site's own CDNs.
        return frozenset({"cmzcdn.org", "comizy.io"})

    def image_fetch_headers(self) -> dict[str, str]:
        # cmzcdn.org enforces hotlink protection: verified from the VPS, the
        # same image URL answers 403 with no Referer and 200 with one.
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return list_browse_modes()

    def list_genres(self) -> list[BrowseMode]:
        return list_genres()

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
            f"MangaBuddy {operation} {API_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_id(self, value: str) -> str:
        return normalize_series_key(fully_unquote(value or ""))

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill in page counts already learned from opening chapters."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached_count = self._chapter_page_count_cache.get(chapter.id)
            if cached_count is not None and cached_count > 0:
                enriched.append(replace(chapter, page_count=cached_count))
            else:
                enriched.append(chapter)
        return enriched

    def _remember_page_count(self, chapter_key: str, page_count: int) -> None:
        if page_count > 0:
            self._chapter_page_count_cache.set(chapter_key, page_count)

    # --- listing ------------------------------------------------------------

    def _listing(
        self,
        operation: str,
        query: str,
        page: int,
        *,
        sort: str | None,
        genre: str | None = None,
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        params = search_params(query, page=page, sort=sort, genre=genre)
        try:
            payload = self._http.get_json(SEARCH_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log_request(
                operation, SEARCH_PATH, params=params, status="error", detail=str(exc)
            )
            raise
        listing = parse_series_list(payload, page=page, page_size=PAGE_SIZE)
        self._log_request(
            operation,
            SEARCH_PATH,
            params=params,
            status="ok",
            detail=(
                f"page={page} sort={normalize_sort(sort)!r} "
                f"count={len(listing.items)} has_more={listing.has_more}"
            ),
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._listing("browse", "", page, sort=sort)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        normalized = (query or "").strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing("search", normalized, page, sort=sort)

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        return self._listing("genre", "", page, sort=sort, genre=genre)

    # --- detail + chapters --------------------------------------------------

    def _fetch_detail(self, series_key: str) -> tuple[Series, list[Chapter], bool] | None:
        """One ``/titles/<hsid>`` fetch, shared by detail and chapter list.

        Returns ``(series, embedded_chapters, embedded_is_complete)``. Opening
        a series calls ``get_series`` and ``get_chapters`` back to back; going
        through this cache is what keeps that at one upstream request instead
        of the two the obvious implementation would spend.
        """
        cached = self._detail_cache.get(series_key)
        if cached is not None:
            return cached

        path = series_path(series_key)
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            level = "missing" if _is_not_found(exc) else "error"
            self._log_request("detail", path, status=level, detail=str(exc))
            return None

        series = parse_series_detail(payload, series_key)
        if series is None:
            self._log_request("detail", path, status="error", detail="parse failed")
            return None

        embedded = parse_embedded_chapters(payload, series_key)
        declared = declared_chapter_count(payload)
        complete = bool(embedded) and len(embedded) >= declared

        if series.chapter_count <= 0 and embedded:
            series = replace(series, chapter_count=len(embedded))
        if not series.latest_chapter and embedded:
            series = replace(series, latest_chapter=embedded[-1].title)

        entry = (series, embedded, complete)
        self._detail_cache.set(series_key, entry)
        self._log_request(
            "detail",
            path,
            status="ok",
            detail=(
                f"chapters={series.chapter_count} embedded={len(embedded)} "
                f"complete={complete}"
            ),
        )
        return entry

    def get_series(self, series_id: str) -> Series | None:
        series_key = self._normalize_id(series_id)
        if not series_key or not is_api_id(series_key):
            return None
        entry = self._fetch_detail(series_key)
        return entry[0] if entry is not None else None

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_key = self._normalize_id(series_id)
        if not series_key or not is_api_id(series_key):
            return []

        cached = self._chapter_list_cache.get(series_key)
        if cached is not None:
            return self._enrich_chapters(cached)

        entry = self._fetch_detail(series_key)
        if entry is None:
            return []
        _series, embedded, complete = entry
        if complete:
            # The detail fetch already carried every chapter -- opening this
            # series costs one request in total.
            self._chapter_list_cache.set(series_key, embedded)
            return self._enrich_chapters(embedded)

        path = chapters_path(series_key)
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            self._log_request("chapters", path, status="error", detail=str(exc))
            # Degrade to the newest 50 rather than showing an empty series.
            return self._enrich_chapters(embedded)

        chapters = parse_chapters(payload, series_key)
        if not chapters:
            return self._enrich_chapters(embedded)
        self._chapter_list_cache.set(series_key, chapters)
        self._log_request("chapters", path, status="ok", detail=f"count={len(chapters)}")
        return self._enrich_chapters(chapters)

    # --- pages --------------------------------------------------------------

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = fully_unquote(chapter_id or "").strip().strip("/")
        parts = split_chapter_key(chapter_key)
        if parts is None:
            return []
        series_key, chapter_hsid = parts
        if not is_api_id(series_key) or not is_api_id(chapter_hsid):
            return []
        # Rebuild the key so cache lookups are stable regardless of how the
        # caller spelled it (stray slashes, percent-encoding).
        chapter_key = make_chapter_key(series_key, chapter_hsid)

        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_detail_path(series_key, chapter_hsid)
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            level = "missing" if _is_not_found(exc) else "error"
            self._log_request("pages", path, status=level, detail=str(exc))
            return []

        pages = parse_chapter_pages(payload, chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._remember_page_count(chapter_key, len(pages))
        self._log_request("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_key = page_id_chapter_key(fully_unquote(page_id or ""))
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
