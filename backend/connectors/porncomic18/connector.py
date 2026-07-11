"""18PornComic online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.porncomic18.mappers import (
    PAGE_SIZE,
    SITE_BASE,
    chapter_id_to_path,
    listing_path,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    series_id_to_path,
)

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class PornComic18Connector(SourceConnector):
    """Browse and read comics from 18PornComic (manga-club HTML catalog)."""

    SOURCE_TYPE = "18porncomic"
    DISPLAY_NAME = "18PornComic"
    DESCRIPTION = (
        "Browse and read porn comics, manhwa, and hentai from 18PornComic. "
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
        return frozenset({"18porncomic.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest"),
            BrowseMode(id="latest", label="New"),
            BrowseMode(id="popular", label="Popular"),
        ]

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("comic/"):
            value = value.removeprefix("comic/")
        if "/" in value and value.startswith("chapter-"):
            value = value.split("/", 1)[0]
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        value = fully_unquote(chapter_id).strip().strip("/")
        if value.startswith("comic/"):
            value = value.removeprefix("comic/")
        return value

    def _fetch_html(self, path: str) -> str:
        return self._http.get_text(path)

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached_count = self._chapter_page_count_cache.get(chapter.id)
            if cached_count is not None and cached_count > 0:
                enriched.append(replace(chapter, page_count=cached_count))
            else:
                enriched.append(chapter)
        return enriched

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized_sort = sort if sort in {None, "default", "latest", "popular"} else None
        if normalized_sort == "default":
            normalized_sort = None
        path = listing_path(page, sort=normalized_sort)
        document = self._fetch_html(path)
        listing = parse_series_list(document, page=page)
        logger.info(
            "18PornComic browse path=%s page=%d count=%d has_more=%s",
            path,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        normalized_sort = sort if sort in {None, "default", "latest", "popular"} else None
        if normalized_sort == "default":
            normalized_sort = None
        path = listing_path(page, sort=normalized_sort, query=normalized)
        document = self._fetch_html(path)
        listing = parse_series_list(document, page=page)
        logger.info(
            "18PornComic search path=%s page=%d count=%d query=%r",
            path,
            page,
            len(listing.items),
            normalized,
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        series_id = self._normalize_series_id(series_id)
        cached = self._series_cache.get(series_id)
        if cached is not None:
            return cached
        try:
            document = self._fetch_html(series_id_to_path(series_id))
        except ConnectorHttpError:
            return None
        series = parse_series_detail(document, series_id=series_id)
        if series is None:
            return None
        self._series_cache.set(series_id, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_id = self._normalize_series_id(series_id)
        return self._enrich_chapters(
            self._chapter_list_cache.get_or_set(
                series_id,
                lambda: self._fetch_chapters(series_id),
            )
        )

    def _fetch_chapters(self, series_id: str) -> list[Chapter]:
        try:
            document = self._fetch_html(series_id_to_path(series_id))
        except ConnectorHttpError:
            return []
        return parse_chapters(document, series_id=series_id)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_id = self._normalize_chapter_id(chapter_id)
        pages = self._page_cache.get_or_set(
            chapter_id,
            lambda: self._fetch_chapter_pages(chapter_id),
        )
        self._chapter_page_count_cache.set(chapter_id, len(pages))
        return pages

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        try:
            document = self._fetch_html(chapter_id_to_path(chapter_id))
        except ConnectorHttpError:
            return []
        return parse_chapter_pages(document, chapter_id=chapter_id)

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
