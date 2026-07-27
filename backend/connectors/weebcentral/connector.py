"""Weeb Central online source connector.

Weeb Central (https://weebcentral.com) is a custom, server-rendered site that
hydrates through HTMX partials -- so it is fully server-scrapable. This
connector talks to those partials directly:

* ``GET /search/data``               -> catalog listing & keyword search
* ``GET /series/<ID>``               -> series metadata
* ``GET /series/<ID>/full-chapter-list`` -> chapter list
* ``GET /chapters/<ID>/images?...``  -> page images (long-strip)

Images are proxied through ManhwaManiacs; the CDN hosts are enforced by the
SSRF allowlist in ``allowed_image_hosts`` and require a site ``Referer``.
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
from connectors.weebcentral.mappers import (
    PAGE_SIZE,
    SEARCH_DATA_PATH,
    SITE_BASE,
    chapter_id_to_path,
    chapter_images_params,
    chapter_images_path,
    normalize_sort,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_data_params,
    series_chapter_list_path,
    series_id_to_path,
)

logger = logging.getLogger(__name__)

# Weeb Central sits behind Cloudflare and 307s HTMX partials that arrive without
# a browser-like request. A full desktop User-Agent plus an HTML Accept header
# is enough to be served the real markup.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": f"{SITE_BASE}/",
}


class WeebCentralConnector(SourceConnector):
    """Browse and read manga/manhwa/manhua from Weeb Central (HTMX HTML)."""

    SOURCE_TYPE = "weebcentral"
    DISPLAY_NAME = "Weeb Central"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from Weeb Central. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False

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
        # Covers: temp.compsci88.com. Chapter page images rotate across a family
        # of Hyperdimension-Neptunia-themed CDN hosts (observed live:
        # hot./scans-hot.planeptune.us, scans.lastation.us, official.lowee.us).
        # Allowlisting the registrable domains matches every rotating subdomain
        # (host_matches_allowlist does suffix matching) while keeping the SSRF
        # allowlist tight to Weeb Central's own CDNs. leanbox.us is the fourth
        # nation host in the same rotation family, included so its subdomains
        # are not silently blocked.
        return frozenset(
            {
                "compsci88.com",
                "planeptune.us",
                "lastation.us",
                "lowee.us",
                "leanbox.us",
            }
        )

    def image_fetch_headers(self) -> dict[str, str]:
        # The image CDNs enforce hotlink protection; a site Referer is required.
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest Updates"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="added", label="Recently Added"),
            BrowseMode(id="alphabetical", label="A-Z"),
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
            f"WeebCentral {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_id(self, value: str) -> str:
        cleaned = fully_unquote(value).strip().strip("/")
        # Accept either a bare ID or a full ``series/<ID>``/``chapters/<ID>`` ref.
        for prefix in ("series/", "chapters/"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        # Drop any trailing slug segment ("<ID>/Some-Slug").
        return cleaned.split("/", 1)[0]

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
        params = search_data_params("", page=page, sort=sort)
        try:
            html = self._http.get_text(SEARCH_DATA_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log_request("browse", SEARCH_DATA_PATH, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._log_request(
            "browse",
            SEARCH_DATA_PATH,
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

        params = search_data_params(normalized, page=page, sort=sort)
        try:
            html = self._http.get_text(SEARCH_DATA_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log_request("search", SEARCH_DATA_PATH, params=params, status="error", detail=str(exc))
            raise
        listing = parse_search_results(html, page=page, query=normalized, page_size=PAGE_SIZE)
        self._log_request(
            "search",
            SEARCH_DATA_PATH,
            params=params,
            status="ok",
            detail=f"page={page} query={normalized!r} count={len(listing.items)} has_more={listing.has_more}",
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_id(series_id)
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

        chapters = self.get_chapters(api_key)
        if chapters:
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=chapters[-1].title,
            )
        self._series_cache.set(api_key, series)
        self._log_request("detail", path, status="ok", detail=f"chapters={series.chapter_count}")
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)

        path = series_chapter_list_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("chapters", path, status="error", detail=str(exc))
            return []

        chapters = parse_chapters(html, api_key)
        if chapters:
            self._chapter_list_cache.set(api_key, chapters)
        enriched = self._enrich_chapters(chapters)
        self._log_request("chapters", path, status="ok", detail=f"count={len(enriched)}")
        return enriched

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached

        path = chapter_images_path(api_key)
        params = chapter_images_params()
        try:
            html = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log_request("pages", path, params=params, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(html, api_key)
        if pages:
            self._page_cache.set(api_key, pages)
            self._remember_page_count(api_key, len(pages))
        self._log_request("pages", path, params=params, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
