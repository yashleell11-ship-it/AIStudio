"""AsmHentai online source connector (custom HTML catalog)."""

from __future__ import annotations

import logging

from connectors.asmhentai.mappers import (
    HOME_PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    SITE_BASE,
    gallery_path,
    home_listing_path,
    page_id_gallery_id,
    parse_chapters,
    parse_gallery_pages,
    parse_series_detail,
    parse_series_list,
    search_listing_path,
)
from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class AsmHentaiConnector(SourceConnector):
    """Browse and read galleries from AsmHentai (nhentai-style HTML catalog)."""

    SOURCE_TYPE = "asmhentai"
    DISPLAY_NAME = "AsmHentai"
    DESCRIPTION = (
        "Browse and read hentai doujinshi and manga from AsmHentai. "
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
            min_interval=0.5,
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
        return frozenset({"images.asmhentai.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="new", label="New"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="top_rated", label="Top Rated"),
        ]

    def _fetch_html(self, path: str) -> str:
        return self._http.get_text(path)

    def _normalize_gallery_id(self, gallery_id: str) -> str:
        value = gallery_id.strip().strip("/")
        if value.startswith("g/"):
            value = value.removeprefix("g/")
        if "/" in value:
            value = value.split("/", 1)[0]
        return value

    def _listing_path(
        self,
        page: int,
        *,
        sort: str | None = None,
        query: str | None = None,
    ) -> tuple[str, int]:
        if query:
            return search_listing_path(query, page, sort=sort), SEARCH_PAGE_SIZE
        return home_listing_path(page, sort=sort), HOME_PAGE_SIZE

    def _fetch_listing(
        self,
        page: int,
        *,
        sort: str | None = None,
        query: str | None = None,
    ) -> PaginatedSeriesList:
        path, page_size = self._listing_path(page, sort=sort, query=query)
        document = self._fetch_html(path)
        return parse_series_list(document, page=page, page_size=page_size)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        listing = self._fetch_listing(page, sort=sort if sort != "latest" else None)
        logger.info(
            "AsmHentai browse sort=%r page=%d count=%d has_more=%s",
            sort,
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
        listing = self._fetch_listing(
            page,
            query=normalized,
            sort=sort if sort and sort != "latest" else None,
        )
        logger.info(
            "AsmHentai search page=%d count=%d sort=%r query=%r",
            page,
            len(listing.items),
            sort,
            normalized,
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        gallery_id = self._normalize_gallery_id(series_id)
        cached = self._series_cache.get(gallery_id)
        if cached is not None:
            return cached
        try:
            document = self._fetch_html(gallery_path(gallery_id))
        except ConnectorHttpError:
            return None
        series = parse_series_detail(document, gallery_id=gallery_id)
        if series is None:
            return None
        self._series_cache.set(gallery_id, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        gallery_id = self._normalize_gallery_id(series_id)
        return self._chapter_list_cache.get_or_set(
            gallery_id,
            lambda: self._fetch_chapters(gallery_id),
        )

    def _fetch_chapters(self, gallery_id: str) -> list[Chapter]:
        try:
            document = self._fetch_html(gallery_path(gallery_id))
        except ConnectorHttpError:
            return []
        return parse_chapters(document, gallery_id=gallery_id)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        gallery_id = self._normalize_gallery_id(chapter_id)
        return self._page_cache.get_or_set(
            gallery_id,
            lambda: self._fetch_chapter_pages(gallery_id),
        )

    def _fetch_chapter_pages(self, gallery_id: str) -> list[Page]:
        try:
            document = self._fetch_html(gallery_path(gallery_id))
        except ConnectorHttpError:
            return []
        return parse_gallery_pages(document, gallery_id=gallery_id)

    def find_page(self, page_id: str) -> Page | None:
        gallery_id = page_id_gallery_id(page_id)
        if gallery_id is None:
            return None
        for page in self.get_chapter_pages(gallery_id):
            if page.id == page_id:
                return page
        return None
