"""ComicAsura online source connector (HTML catalog)."""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import SourceConnector
from connectors.comicasura.mappers import (
    PAGE_SIZE,
    SITE_BASE,
    chapter_path,
    listing_path,
    page_id_chapter_id,
    parse_chapter_id,
    parse_chapter_pages,
    parse_chapters,
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


class ComicAsuraConnector(SourceConnector):
    """Browse and read manhwa from ComicAsura (comicasura.net)."""

    SOURCE_TYPE = "comicasura"
    DISPLAY_NAME = "ComicAsura"
    DESCRIPTION = (
        "Browse and read manhwa and manga from ComicAsura. "
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
        # Covers: storage*.waitst.com / img-r*.2xstorage.com
        # Pages: img-r*.2xstorage.com (fallback imgs-*.2xstorage.com)
        return frozenset({"2xstorage.com", "waitst.com", "comicasura.net"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="rating", label="Top Rated"),
            BrowseMode(id="bookmark", label="Bookmarks"),
            BrowseMode(id="name_asc", label="Name A-Z"),
            BrowseMode(id="name_desc", label="Name Z-A"),
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
            f"ComicAsura {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value[len("manga/") :]
        return value.split("/", 1)[0]

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        value = fully_unquote(chapter_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value[len("manga/") :]
        return value

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = listing_path(page, sort=sort)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("browse", path, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._log_request(
            "browse",
            path,
            status="ok",
            detail=f"page={page} sort={sort!r} count={len(listing.items)} has_more={listing.has_more}",
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        path = listing_path(page, search=normalized, sort=sort)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("search", path, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._log_request(
            "search",
            path,
            status="ok",
            detail=(
                f"page={page} query={normalized!r} sort={sort!r} "
                f"count={len(listing.items)} has_more={listing.has_more}"
            ),
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached

        path = series_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("detail", path, status="error", detail=str(exc))
            return None

        series = parse_series_detail(html, api_key)
        if series is None:
            self._log_request("detail", path, status="error", detail="parse failed")
            return None

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
        self._log_request(
            "detail",
            path,
            status="ok",
            detail=f"chapters={series.chapter_count}",
        )
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return cached

        path = series_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("chapters", path, status="error", detail=str(exc))
            return []

        chapters = parse_chapters(html, api_key)
        if chapters:
            self._chapter_list_cache.set(api_key, chapters)
        self._log_request("chapters", path, status="ok", detail=f"count={len(chapters)}")
        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        normalized = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(normalized)
        if cached is not None:
            return cached

        parsed = parse_chapter_id(normalized)
        if parsed is None:
            self._log_request(
                "pages",
                chapter_path(normalized),
                status="error",
                detail="invalid chapter id format",
            )
            return []

        path = chapter_path(normalized)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("pages", path, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(html, normalized)
        if pages:
            self._page_cache.set(normalized, pages)
        self._log_request("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if not chapter_id:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
