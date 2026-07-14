"""CManhua online source connector (custom ASP.NET HTML catalog)."""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import SourceConnector
from connectors.cmanhua.mappers import (
    ALL_COMICS_PATH,
    MANGA_UPDATE_PATH,
    PAGE_SIZE,
    SEARCH_PATH,
    SITE_BASE,
    jump_page_form,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    series_path,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class CManhuaConnector(SourceConnector):
    """Browse and read manhua from CManhua (cmanhua.com)."""

    SOURCE_TYPE = "cmanhua"
    DISPLAY_NAME = "CManhua"
    DESCRIPTION = (
        "Browse and read Chinese manhua from CManhua. "
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
            min_interval=0.35,
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
        return frozenset({"cmanhua.com", "manhua.5um.net"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="All Comics"),
            BrowseMode(id="latest", label="Recently Updated"),
        ]

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("comic/"):
            value = value.removeprefix("comic/")
        if "/" in value:
            value = value.split("/", 1)[0]
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        value = fully_unquote(chapter_id).strip()
        if "id=" in value:
            value = value.split("id=", 1)[1]
        if "&" in value:
            value = value.split("&", 1)[0]
        return value.strip()

    def _fetch_html(self, path: str, *, params: dict[str, Any] | None = None) -> str:
        return self._http.get_text(path, params=params)

    def _fetch_all_comics_page(self, page: int) -> str:
        if page <= 1:
            return self._fetch_html(ALL_COMICS_PATH)
        bootstrap = self._fetch_html(ALL_COMICS_PATH)
        form = jump_page_form(bootstrap, page)
        return self._http.post_text(
            ALL_COMICS_PATH,
            data=form,
            extra_headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{SITE_BASE}{ALL_COMICS_PATH}",
                "Origin": SITE_BASE,
            },
        )

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        mode = (sort or "default").strip().casefold()
        if mode in {"latest", "updated", "recent"}:
            document = self._fetch_html(MANGA_UPDATE_PATH)
            listing = parse_series_list(document, page=1, page_size=PAGE_SIZE)
            # MangaUpdate is a single recent-updates shelf (no pager).
            listing = PaginatedSeriesList(
                items=listing.items,
                page=1,
                page_size=max(len(listing.items), 1),
                total=len(listing.items),
                api_has_more=False,
            )
            if page > 1:
                listing = PaginatedSeriesList(
                    items=[],
                    page=page,
                    page_size=listing.page_size,
                    total=listing.total,
                    api_has_more=False,
                )
        else:
            document = self._fetch_all_comics_page(page)
            listing = parse_series_list(document, page=page, page_size=PAGE_SIZE)

        logger.info(
            "CManhua browse sort=%r page=%d count=%d has_more=%s",
            sort,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        del sort  # SearchHandler has no sort param.
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page)
        if len(normalized) < 2:
            return PaginatedSeriesList(items=[], page=page, page_size=1, total=0, api_has_more=False)
        try:
            payload = self._http.get_json_value(SEARCH_PATH, params={"q": normalized})
        except ConnectorHttpError:
            logger.exception("CManhua search failed query=%r", normalized)
            return PaginatedSeriesList(items=[], page=page, page_size=1, total=0, api_has_more=False)
        listing = parse_search_results(payload, page=page)
        logger.info(
            "CManhua search page=%d count=%d query=%r",
            page,
            len(listing.items),
            normalized,
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        slug = self._normalize_series_id(series_id)
        cached = self._series_cache.get(slug)
        if cached is not None:
            return cached
        try:
            document = self._fetch_html(series_path(slug))
        except ConnectorHttpError:
            return None
        series = parse_series_detail(document, series_id=slug)
        if series is None:
            return None
        self._series_cache.set(slug, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        slug = self._normalize_series_id(series_id)
        return self._chapter_list_cache.get_or_set(
            slug,
            lambda: self._fetch_chapters(slug),
        )

    def _fetch_chapters(self, slug: str) -> list[Chapter]:
        try:
            document = self._fetch_html(series_path(slug))
        except ConnectorHttpError:
            return []
        chapters = parse_chapters(document, series_id=slug)
        series = parse_series_detail(document, series_id=slug)
        if series is not None:
            self._series_cache.set(slug, series)
        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        cid = self._normalize_chapter_id(chapter_id)
        return self._page_cache.get_or_set(
            cid,
            lambda: self._fetch_chapter_pages(cid),
        )

    def _fetch_chapter_pages(self, chapter_id: str) -> list[Page]:
        try:
            document = self._fetch_html("/ReadComic", params={"id": chapter_id})
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
