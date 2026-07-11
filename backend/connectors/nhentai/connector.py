"""nHentai online source connector (API v2)."""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.nhentai.mappers import (
    API_BASE,
    PAGE_SIZE,
    gallery_detail_to_series,
    gallery_pages_to_pages,
    gallery_to_chapter,
    listing_to_paginated,
    page_id_gallery_id,
)

logger = logging.getLogger(__name__)

_LIST_PATHS: dict[str, str] = {
    "default": "/api/v2/galleries",
    "latest": "/api/v2/galleries",
    "popular": "/api/v2/galleries/popular",
}


class NHentaiConnector(SourceConnector):
    """Browse and read galleries from nHentai via the public API v2."""

    SOURCE_TYPE = "nhentai"
    DISPLAY_NAME = "nHentai"
    DESCRIPTION = (
        "Browse and read doujinshi and hentai manga from nHentai. "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(API_BASE)
        self._config_cache: TTLCache[dict[str, list[str]]] = TTLCache(ttl_seconds=3600.0)
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
        return frozenset({"nhentai.net"})

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="popular", label="Popular"),
        ]

    def _cdn_servers(self) -> tuple[list[str], list[str]]:
        cached = self._config_cache.get("cdn")
        if cached is not None:
            return cached["image"], cached["thumb"]

        payload = self._http.get_json("/api/v2/config")
        image_servers = [
            str(url).rstrip("/")
            for url in payload.get("image_servers") or []
            if isinstance(url, str)
        ]
        thumb_servers = [
            str(url).rstrip("/")
            for url in payload.get("thumb_servers") or []
            if isinstance(url, str)
        ]
        if not image_servers:
            image_servers = ["https://i1.nhentai.net"]
        if not thumb_servers:
            thumb_servers = ["https://t1.nhentai.net"]
        self._config_cache.set("cdn", {"image": image_servers, "thumb": thumb_servers})
        return image_servers, thumb_servers

    def _fetch_listing(self, path: str, page: int) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        _, thumb_servers = self._cdn_servers()
        payload = self._http.get_json_value(path, params={"page": page})
        return listing_to_paginated(
            payload,
            page=page,
            page_size=PAGE_SIZE,
            thumb_servers=thumb_servers,
        )

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        path = _LIST_PATHS.get(sort or "default", _LIST_PATHS["default"])
        listing = self._fetch_listing(path, page)
        logger.info(
            "nHentai browse %s page=%d count=%d total=%d has_more=%s",
            path,
            page,
            len(listing.items),
            listing.total,
            listing.has_more,
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        _, thumb_servers = self._cdn_servers()
        payload = self._http.get_json(
            "/api/v2/search",
            params={"query": normalized, "page": page},
        )
        listing = listing_to_paginated(
            payload,
            page=page,
            page_size=PAGE_SIZE,
            thumb_servers=thumb_servers,
        )
        logger.info(
            "nHentai search page=%d count=%d total=%d query=%r",
            page,
            len(listing.items),
            listing.total,
            normalized,
        )
        return listing

    def _fetch_gallery(self, gallery_id: str) -> dict[str, Any] | None:
        try:
            payload = self._http.get_json(f"/api/v2/galleries/{gallery_id}")
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def get_series(self, series_id: str) -> Series | None:
        cached = self._series_cache.get(series_id)
        if cached is not None:
            return cached

        payload = self._fetch_gallery(series_id)
        if payload is None:
            return None

        _, thumb_servers = self._cdn_servers()
        series = gallery_detail_to_series(payload, thumb_servers=thumb_servers)
        self._series_cache.set(series_id, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._chapter_list_cache.get_or_set(
            series_id,
            lambda: self._fetch_chapters(series_id),
        )

    def _fetch_chapters(self, series_id: str) -> list[Chapter]:
        payload = self._fetch_gallery(series_id)
        if payload is None:
            return []
        chapter = gallery_to_chapter(payload)
        if chapter.page_count <= 0:
            return []
        return [chapter]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return self._page_cache.get_or_set(
            chapter_id,
            lambda: self._fetch_chapter_pages(chapter_id),
        )

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        payload = self._fetch_gallery(chapter_id)
        if payload is None:
            return []
        image_servers, _ = self._cdn_servers()
        return gallery_pages_to_pages(chapter_id, payload, image_servers=image_servers)

    def find_page(self, page_id: str) -> Page | None:
        gallery_id = page_id_gallery_id(page_id)
        if gallery_id is None:
            return None
        for page in self.get_chapter_pages(gallery_id):
            if page.id == page_id:
                return page
        return None
