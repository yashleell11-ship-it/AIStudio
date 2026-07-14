"""FreeAdultComix online source connector."""

from __future__ import annotations

import logging

from connectors.base import SourceConnector
from connectors.freeadultcomix.http import FacSyncHttpClient
from connectors.freeadultcomix.mappers import (
    GENRE_CATALOG,
    SITE_BASE,
    listing_path,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    search_listing_path,
    series_id_to_path,
    tag_listing_path,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_IMPERSONATE = "chrome131"


class FreeAdultComixConnector(SourceConnector):
    """Browse and read comics from FreeAdultComix (WordPress gallery catalog)."""

    SOURCE_TYPE = "freeadultcomix"
    DISPLAY_NAME = "FreeAdultComix"
    DESCRIPTION = (
        "Browse and read adult comics from FreeAdultComix. "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self, *, http_client: FacSyncHttpClient | None = None) -> None:
        self._http = http_client or FacSyncHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            impersonate=BROWSER_IMPERSONATE,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)

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
        return frozenset({"freeadultcomix.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def fetch_proxied_image(self, url: str) -> tuple[str, bytes] | None:
        # Apex DNS is often RPZ-poisoned; always fetch via DoH-pinned client.
        return self._http.get_bytes(url, extra_headers=self.image_fetch_headers())

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest"),
            BrowseMode(id="latest", label="Latest"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=genre_id, label=label) for genre_id, label in GENRE_CATALOG]

    def _normalize_series_id(self, series_id: str) -> str:
        value = series_id.strip().strip("/")
        if value.startswith("tag/") or value.startswith("category/"):
            return value.split("/", 1)[-1]
        if "/" in value:
            value = value.split("/", 1)[0]
        return value

    def _fetch_html(self, path: str) -> str:
        return self._http.get_text(path)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        del sort  # site only exposes chronological home pagination
        if page < 1:
            page = 1
        html = self._fetch_html(listing_path(page))
        return parse_series_list(html, page=page)

    def search_series(
        self,
        query: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        del sort
        if page < 1:
            page = 1
        q = query.strip()
        if not q:
            return PaginatedSeriesList(items=[], page=page, page_size=24, api_has_more=False)
        html = self._fetch_html(search_listing_path(q, page))
        return parse_series_list(html, page=page)

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        del sort
        if page < 1:
            page = 1
        slug = genre.strip().strip("/").lower()
        if not slug:
            return PaginatedSeriesList(items=[], page=page, page_size=24, api_has_more=False)
        html = self._fetch_html(tag_listing_path(slug, page))
        return parse_series_list(html, page=page)

    def get_series(self, series_id: str) -> Series | None:
        slug = self._normalize_series_id(series_id)
        cached = self._series_cache.get(slug)
        if cached is not None:
            return cached
        try:
            html = self._fetch_html(series_id_to_path(slug))
        except ConnectorHttpError as exc:
            logger.info("FreeAdultComix series fetch failed for %s: %s", slug, exc)
            return None
        series = parse_series_detail(html, slug)
        if series is None:
            return None
        self._series_cache.set(slug, series)
        chapters = parse_chapters(html, slug)
        self._chapter_list_cache.set(slug, chapters)
        pages = parse_chapter_pages(html, slug)
        self._page_cache.set(slug, pages)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        slug = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(slug)
        if cached is not None:
            return cached
        try:
            html = self._fetch_html(series_id_to_path(slug))
        except ConnectorHttpError as exc:
            logger.info("FreeAdultComix chapters fetch failed for %s: %s", slug, exc)
            return []
        series = parse_series_detail(html, slug)
        if series is not None:
            self._series_cache.set(slug, series)
        chapters = parse_chapters(html, slug)
        self._chapter_list_cache.set(slug, chapters)
        pages = parse_chapter_pages(html, slug)
        self._page_cache.set(slug, pages)
        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        slug = self._normalize_series_id(chapter_id)
        cached = self._page_cache.get(slug)
        if cached is not None:
            return cached
        try:
            html = self._fetch_html(series_id_to_path(slug))
        except ConnectorHttpError as exc:
            logger.info("FreeAdultComix pages fetch failed for %s: %s", slug, exc)
            return []
        pages = parse_chapter_pages(html, slug)
        self._page_cache.set(slug, pages)
        chapters = parse_chapters(html, slug)
        self._chapter_list_cache.set(slug, chapters)
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
