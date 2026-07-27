"""MangaDex online source connector."""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import SyncConnectorHttpClient
from connectors.mangadex.mappers import (
    API_BASE,
    PAGE_SIZE,
    at_home_to_pages,
    chapter_item_to_chapter,
    manga_list_to_paginated,
    manga_to_series,
    page_id_chapter_id,
)
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

MANGA_SORT_ORDERS: dict[str, dict[str, str]] = {
    "default": {"order[latestUploadedChapter]": "desc"},
    "updated": {"order[latestUploadedChapter]": "desc"},
    "popular": {"order[followedCount]": "desc"},
    "latest": {"order[createdAt]": "desc"},
    "rating": {"order[rating]": "desc"},
    "year": {"order[year]": "desc"},
}


class MangaDexConnector(SourceConnector):
    """Browse and read manga/manhwa from the official MangaDex API."""

    SOURCE_TYPE = "mangadex"
    DISPLAY_NAME = "MangaDex"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from MangaDex. "
        "Images are proxied through ManhwaManiacs to comply with MangaDex hotlinking rules."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(API_BASE)
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
        # api.mangadex.org / mangadex.org: cover art (UPLOADS_BASE).
        # mangadex.network: the @Home distributed CDN — page images are
        # served from a different node hostname on every request (returned
        # dynamically by the /at-home/server API call), always under this
        # domain.
        return frozenset({"mangadex.org", "mangadex.network"})

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="updated", label="Recently Updated"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="rating", label="Top Rated"),
            BrowseMode(id="year", label="Newest Year"),
        ]

    def _manga_params(
        self,
        *,
        page: int,
        title: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        offset = max(page - 1, 0) * PAGE_SIZE
        params: dict[str, Any] = {
            "limit": PAGE_SIZE,
            "offset": offset,
            "contentRating[]": ["safe", "suggestive", "erotica"],
            "includes[]": ["cover_art", "author", "artist"],
            "hasAvailableChapters": "true",
            # get_chapters() reads the feed filtered to translatedLanguage[]=en,
            # so browse must be filtered the same way. Without this, browse
            # surfaces series whose only chapters are in other languages
            # (e.g. Russian- or Vietnamese-only titles), and the English feed
            # then returns 0 chapters -> the series looks empty to the reader.
            "availableTranslatedLanguage[]": ["en"],
        }
        order = MANGA_SORT_ORDERS.get(sort or "default", MANGA_SORT_ORDERS["default"])
        params.update(order)
        if title:
            params["title"] = title
        return params

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = "/manga"
        params = self._manga_params(page=page, sort=sort)
        payload = self._http.get_json(path, params=params)
        listing = manga_list_to_paginated(payload, page=page, page_size=PAGE_SIZE)
        logger.info(
            "MangaDex browse %s%s params=%s count=%d total=%d has_more=%s",
            API_BASE,
            path,
            params,
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
        path = "/manga"
        params = self._manga_params(page=page, title=normalized, sort=sort)
        payload = self._http.get_json(path, params=params)
        listing = manga_list_to_paginated(payload, page=page, page_size=PAGE_SIZE)
        logger.info(
            "MangaDex search %s%s params=%s count=%d total=%d has_more=%s query=%r",
            API_BASE,
            path,
            params,
            len(listing.items),
            listing.total,
            listing.has_more,
            normalized,
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        cached = self._series_cache.get(series_id)
        if cached is not None:
            return cached

        try:
            payload = self._http.get_json(
                f"/manga/{series_id}",
                params={
                    "includes[]": ["cover_art", "author", "artist", "tag"],
                },
            )
        except Exception:
            return None

        data = payload.get("data")
        if not isinstance(data, dict):
            return None

        data = {
            **data,
            "_included": payload.get("included") or [],
        }
        chapters = self.get_chapters(series_id)
        series = manga_to_series(data, chapter_count=len(chapters))
        self._series_cache.set(series_id, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._chapter_list_cache.get_or_set(
            series_id,
            lambda: self._fetch_all_chapters(series_id),
        )

    def _fetch_all_chapters(self, series_id: str) -> list[Chapter]:
        chapters: list[Chapter] = []
        offset = 0
        limit = 500

        while True:
            payload = self._http.get_json(
                f"/manga/{series_id}/feed",
                params={
                    "limit": limit,
                    "offset": offset,
                    "translatedLanguage[]": ["en"],
                    "order[chapter]": "asc",
                    "includeFuturePublishAt": "0",
                    # NOTE: do NOT send includeEmptyPages=0. Officially-licensed
                    # series (e.g. Solo Leveling) host no page images on MangaDex,
                    # so every chapter counts as "empty" and that filter drops the
                    # entire feed -> get_chapters() returns []. Include them.
                },
            )
            data = payload.get("data") or []
            if not data:
                break

            for item in data:
                if isinstance(item, dict):
                    chapters.append(chapter_item_to_chapter(item, series_id=series_id))

            total = int(payload.get("total") or 0)
            offset += len(data)
            if offset >= total:
                break

        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return self._page_cache.get_or_set(
            chapter_id,
            lambda: self._fetch_chapter_pages(chapter_id),
        )

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        try:
            payload = self._http.get_json(f"/at-home/server/{chapter_id}")
        except Exception:
            return []
        return at_home_to_pages(chapter_id, payload)

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
