"""Flame Scans / Flame Comics online source connector."""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import SourceConnector
from connectors.flamescans.mappers import (
    PAGE_SIZE,
    SITE_BASE,
    chapter_item_to_chapter,
    chapter_pages_to_pages,
    filter_series_items,
    page_id_chapter_id,
    paginate_series,
    parse_chapter_id,
    parse_next_data,
    series_detail_to_series,
    series_list_item_to_series,
    sort_series_items,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)


class FlameScansConnector(SourceConnector):
    """Browse and read from Flame Comics (formerly Flame Scans)."""

    SOURCE_TYPE = "flamescans"
    DISPLAY_NAME = "Flame Scans"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from Flame Comics "
        "(flamecomics.xyz). Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": f"{SITE_BASE}/",
            },
        )
        self._catalog_cache: TTLCache[list[dict[str, Any]]] = TTLCache(ttl_seconds=300.0)
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._detail_cache: TTLCache[dict[str, Any]] = TTLCache(ttl_seconds=180.0)

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
        return frozenset({"cdn.flamecomics.xyz", "flamecomics.xyz"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="alphabetical", label="A–Z"),
        ]

    def _normalize_series_id(self, series_id: str) -> str:
        return series_id.strip().strip("/").split("/", 1)[0]

    def _fetch_catalog(self) -> list[dict[str, Any]]:
        payload = self._http.get_json_value("/api/series")
        if not isinstance(payload, list):
            raise ConnectorHttpError("Expected Flame Comics series list.")
        return [item for item in payload if isinstance(item, dict)]

    def _catalog(self) -> list[dict[str, Any]]:
        return self._catalog_cache.get_or_set("catalog", self._fetch_catalog)

    def _listing(
        self,
        page: int,
        *,
        sort: str | None = None,
        query: str | None = None,
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        items = filter_series_items(sort_series_items(self._catalog(), sort), query)
        series_items: list[Series] = []
        for entry in items:
            series = series_list_item_to_series(entry)
            if series is not None:
                series_items.append(series)
        listing = paginate_series(series_items, page=page, page_size=PAGE_SIZE)
        logger.info(
            "Flame Scans browse sort=%r query=%r page=%d count=%d has_more=%s",
            sort,
            query,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._listing(page, sort=sort)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing(page, sort=sort, query=normalized)

    def _fetch_series_page_props(self, series_id: str) -> dict[str, Any] | None:
        try:
            html_text = self._http.get_text(f"/series/{series_id}")
        except ConnectorHttpError:
            return None
        return parse_next_data(html_text)

    def _series_page_props(self, series_id: str) -> dict[str, Any] | None:
        cached = self._detail_cache.get(series_id)
        if cached is not None:
            return cached
        props = self._fetch_series_page_props(series_id)
        if props is not None:
            self._detail_cache.set(series_id, props)
        return props

    def get_series(self, series_id: str) -> Series | None:
        sid = self._normalize_series_id(series_id)
        cached = self._series_cache.get(sid)
        if cached is not None:
            return cached
        props = self._series_page_props(sid)
        if props is None:
            return None
        raw_series = props.get("series")
        if not isinstance(raw_series, dict):
            return None
        chapters = props.get("chapters") if isinstance(props.get("chapters"), list) else []
        series = series_detail_to_series(raw_series, chapter_count=len(chapters))
        if series is None:
            return None
        self._series_cache.set(sid, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        sid = self._normalize_series_id(series_id)
        return self._chapter_list_cache.get_or_set(sid, lambda: self._fetch_chapters(sid))

    def _fetch_chapters(self, series_id: str) -> list[Chapter]:
        props = self._series_page_props(series_id)
        if props is None:
            return []
        raw_chapters = props.get("chapters") or []
        chapters: list[Chapter] = []
        for entry in raw_chapters:
            if isinstance(entry, dict):
                chapter = chapter_item_to_chapter(entry, series_id=series_id)
                if chapter is not None:
                    chapters.append(chapter)
        chapters.sort(key=lambda chapter: chapter.number if chapter.number is not None else 0)
        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return self._page_cache.get_or_set(chapter_id, lambda: self._fetch_chapter_pages(chapter_id))

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        parsed = parse_chapter_id(chapter_id)
        if parsed is None:
            return []
        series_id, token = parsed
        try:
            html_text = self._http.get_text(f"/series/{series_id}/{token}")
        except ConnectorHttpError:
            return []
        props = parse_next_data(html_text)
        if props is None:
            return []
        return chapter_pages_to_pages(chapter_id, props)

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
