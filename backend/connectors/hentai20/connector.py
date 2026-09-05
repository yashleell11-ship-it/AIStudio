"""Hentai20 online source connector (Themesia MangaReader HTML)."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse

from connectors.base import SourceConnector
from connectors.elftoon.mappers import (
    PAGE_SIZE,
    chapter_id_to_path,
    listing_params,
    listing_path,
    page_id_chapter_id,
    parse_chapter_id,
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
from connectors.http.cf_client import CfSyncHttpClient
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

SITE_BASE = "https://hentai20.io"
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "Referer": f"{SITE_BASE}/",
}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_THUMB_COVER_RE = re.compile(
    r'class="thumb"[^>]*>.*?<img[^>]+src="([^"]+)"',
    re.I | re.S,
)


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404."""
    return exc.status_code == 404 or "404 Not Found" in str(exc)


def _cover_from_detail_html(html_text: str) -> str | None:
    """Hentai20 detail pages omit og:image; read the sidebar thumb instead."""
    match = _THUMB_COVER_RE.search(html_text)
    if match is None:
        return None
    url = match.group(1).strip()
    return url or None


class Hentai20Connector(SourceConnector):
    """Browse and read manga from Hentai20 (hentai20.io)."""

    SOURCE_TYPE = "hentai20"
    DISPLAY_NAME = "Hentai20"
    DESCRIPTION = (
        "Browse and read from Hentai20. "
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
        )
        self._image_http = CfSyncHttpClient(
            SITE_BASE,
            impersonate="chrome131",
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
    def is_mature(self) -> bool:
        return self.MATURE

    @property
    def allowed_image_hosts(self) -> frozenset[str]:
        return frozenset({"hentai20.io", "hentai1.io", "img.hentai1.io", "wp.com"})

    def _image_referer_for_url(self, url: str) -> dict[str, str]:
        host = urlparse(url).netloc.lower()
        if host.endswith("hentai1.io") or host.endswith("img.hentai1.io"):
            return {"Referer": f"{SITE_BASE}/"}
        return {"Referer": f"{SITE_BASE}/"}

    def image_fetch_headers(self) -> dict[str, str]:
        return self._image_referer_for_url(SITE_BASE)

    def fetch_proxied_image(self, url: str) -> tuple[str, bytes] | None:
        return self._image_http.get_bytes(
            url,
            extra_headers=self._image_referer_for_url(url),
        )

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest"),
            BrowseMode(id="latest", label="New"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="rating", label="Top Rated"),
        ]

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
            f"Hentai20 {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value.removeprefix("manga/")
        return value.split("/", 1)[0]

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return fully_unquote(chapter_id).strip().strip("/")

    def _remember_page_count(self, chapter_id: str, page_count: int) -> None:
        if page_count > 0:
            self._chapter_page_count_cache.set(chapter_id, page_count)

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        out: list[Chapter] = []
        for chapter in chapters:
            cached = self._chapter_page_count_cache.get(chapter.id)
            if cached is not None and cached > 0:
                out.append(replace(chapter, page_count=cached))
            else:
                out.append(chapter)
        return out

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = listing_path()
        params = listing_params(page=page, sort=sort)
        try:
            html = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log("browse", path, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._log(
            "browse",
            path,
            params=params,
            status="ok",
            detail=f"count={len(listing.items)} has_more={listing.has_more}",
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        del sort
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page)
        path = search_path(page)
        params = search_params(normalized)
        try:
            html = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            # Same WordPress 404-past-the-end as elftoon; see that connector.
            if page > 1 and _is_not_found(exc):
                self._log("search", path, params=params, status="ok", detail="past last page")
                return PaginatedSeriesList(
                    items=[],
                    page=page,
                    page_size=PAGE_SIZE,
                    total=(page - 1) * PAGE_SIZE,
                    api_has_more=False,
                )
            self._log("search", path, params=params, status="error", detail=str(exc))
            raise
        # Hentai20's search pages hold 20 posts, not WordPress's default 10
        # (measured from the VPS), so it keeps PAGE_SIZE where elftoon does not.
        listing = parse_search_results(html, page=page, page_size=PAGE_SIZE)
        self._log(
            "search",
            path,
            params=params,
            status="ok",
            detail=f"count={len(listing.items)}",
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached
        path = series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("detail", path, status="error", detail=str(exc))
            return None
        series = parse_series_detail(html, api_key)
        if series is None:
            self._log("detail", path, status="error", detail="parse failed")
            return None
        if not series.cover_url:
            cover_url = _cover_from_detail_html(html)
            if cover_url:
                series = replace(series, cover_url=cover_url)
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
        self._log("detail", path, status="ok", detail=f"chapters={series.chapter_count}")
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)
        path = series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("chapters", path, status="error", detail=str(exc))
            return []
        chapters = parse_chapters(html, api_key)
        self._chapter_list_cache.set(api_key, chapters)
        enriched = self._enrich_chapters(chapters)
        self._log("chapters", path, status="ok", detail=f"count={len(enriched)}")
        return enriched

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached
        path = chapter_id_to_path(api_key)
        if path is None:
            if parse_chapter_id(api_key) is None and "-chapter-" in api_key:
                path = f"/{api_key.strip().strip('/')}/"
            else:
                self._log("pages", api_key, status="error", detail="bad chapter id")
                return []
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("pages", path, status="error", detail=str(exc))
            return []
        pages = parse_chapter_pages(html, api_key)
        self._page_cache.set(api_key, pages)
        self._remember_page_count(api_key, len(pages))
        self._log("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if not chapter_id:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
