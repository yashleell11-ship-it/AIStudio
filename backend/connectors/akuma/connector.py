"""Akuma online source connector."""

from __future__ import annotations

import logging

from connectors.akuma.mappers import (
    ENGLISH_LANGUAGE_QUERY,
    PAGE_SIZE,
    SITE_BASE,
    build_gallery_pages,
    extract_csrf_token,
    extract_media_base,
    extract_next_cursor,
    gallery_path,
    listing_path,
    page_id_gallery_id,
    parse_chapters,
    parse_image_filenames,
    parse_series_detail,
    parse_series_list,
    reader_path,
)
from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError
from connectors.http.ddg_client import DdgSyncHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_IMPERSONATE = "chrome131"


class AkumaConnector(SourceConnector):
    """Browse and read galleries from akuma.moe (custom Laravel catalog)."""

    SOURCE_TYPE = "akuma"
    DISPLAY_NAME = "Akuma"
    DESCRIPTION = (
        "Browse and read doujinshi and hentai manga from akuma.moe. "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = DdgSyncHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            impersonate=BROWSER_IMPERSONATE,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._cursor_cache: TTLCache[str] = TTLCache(ttl_seconds=900.0)

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
        return frozenset({"akuma.moe"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="english", label="English Only"),
        ]

    def _normalize_gallery_id(self, gallery_id: str) -> str:
        value = gallery_id.strip().strip("/")
        if value.startswith("g/"):
            value = value.removeprefix("g/")
        if "/" in value:
            value = value.split("/", 1)[0]
        return value

    def _cursor_cache_key(self, query: str | None, page: int) -> str:
        return f"{query or ''}:{page}"

    def _remember_next_cursor(self, query: str | None, page: int, document: str) -> None:
        next_cursor = extract_next_cursor(document)
        if next_cursor:
            self._cursor_cache.set(self._cursor_cache_key(query, page + 1), next_cursor)

    def _resolve_listing_path(self, page: int, query: str | None) -> str:
        if page < 1:
            page = 1
        if page == 1:
            return listing_path(1, query=query)
        cursor = self._cursor_cache.get(self._cursor_cache_key(query, page))
        if cursor:
            return listing_path(page, query=query, cursor=cursor)
        current_page = 1
        while current_page < page:
            path = self._resolve_listing_path(current_page, query)
            document = self._http.get_text(path)
            self._remember_next_cursor(query, current_page, document)
            current_page += 1
        cursor = self._cursor_cache.get(self._cursor_cache_key(query, page))
        return listing_path(page, query=query, cursor=cursor)

    def _fetch_listing(self, page: int, *, query: str | None = None) -> PaginatedSeriesList:
        path = self._resolve_listing_path(page, query)
        document = self._http.get_text(path)
        self._remember_next_cursor(query, page, document)
        return parse_series_list(document, page=page, page_size=PAGE_SIZE)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        query = ENGLISH_LANGUAGE_QUERY if sort == "english" else None
        listing = self._fetch_listing(page, query=query)
        logger.info(
            "Akuma browse sort=%r page=%d count=%d has_more=%s",
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
        if sort == "english":
            combined = (
                f"{ENGLISH_LANGUAGE_QUERY} {normalized}".strip()
                if normalized
                else ENGLISH_LANGUAGE_QUERY
            )
            listing = self._fetch_listing(page, query=combined)
        elif not normalized:
            return self.get_series_list(page, sort=sort)
        else:
            listing = self._fetch_listing(page, query=normalized)
        logger.info(
            "Akuma search page=%d count=%d sort=%r query=%r",
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
            document = self._http.get_text(gallery_path(gallery_id))
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
            document = self._http.get_text(gallery_path(gallery_id))
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
            reader_document = self._http.get_text(reader_path(gallery_id, 1))
        except ConnectorHttpError:
            return []
        media_base = extract_media_base(reader_document)
        if not media_base:
            return []
        csrf_token = extract_csrf_token(reader_document)
        extra_headers = {"X-CSRF-TOKEN": csrf_token} if csrf_token else None
        try:
            payload = self._http.post_text(
                gallery_path(gallery_id),
                extra_headers=extra_headers,
            )
        except ConnectorHttpError:
            return []
        filenames = parse_image_filenames(payload)
        if not filenames:
            return []
        return build_gallery_pages(
            gallery_id=gallery_id,
            media_base=media_base,
            filenames=filenames,
        )

    def find_page(self, page_id: str) -> Page | None:
        gallery_id = page_id_gallery_id(page_id)
        if gallery_id is None:
            return None
        for page in self.get_chapter_pages(gallery_id):
            if page.id == page_id:
                return page
        return None
