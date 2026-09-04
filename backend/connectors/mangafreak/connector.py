"""MangaFreak online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace
from urllib.parse import quote

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.mangafreak.mappers import (
    SEARCH_PAGE_SIZE,
    SITE_BASE,
    chapter_path,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_genre_list,
    parse_latest_releases,
    parse_mangalist,
    parse_ranking,
    parse_search_results,
    parse_series_detail,
    series_path,
)
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses, so a 404 otherwise surfaces only as httpx's ``raise_for_status``
    text ("Client error '404 Not Found' for url ..."). Checking the attribute
    alone is dead code; both forms are matched here.

    Note this is the *secondary* not-found path for MangaFreak: an unknown
    series or chapter is answered with HTTP 200 and the homepage, which is
    caught structurally by the mappers instead (``is_series_document``).
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class MangaFreakConnector(SourceConnector):
    """Browse and read manga from MangaFreak (custom HTML catalog)."""

    SOURCE_TYPE = "mangafreak"
    DISPLAY_NAME = "MangaFreak"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from MangaFreak. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    #: Catalog view -> ("/path/template", parser). Each view paginates at its
    #: own size, which the parser encodes.
    _BROWSE_MODES = {
        "default": ("/Latest_Releases/{page}", parse_latest_releases),
        "popular": ("/Genre/All/{page}", parse_ranking),
        "all": ("/Mangalist/All/{page}", parse_mangalist),
    }

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE, headers=HTML_HEADERS, user_agent=BROWSER_USER_AGENT
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)
        self._genre_cache: TTLCache[list[BrowseMode]] = TTLCache(ttl_seconds=3600.0)

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
        # Covers and page images are both served from images.mangafreak.me,
        # which this suffix covers along with the site host itself.
        return frozenset({"mangafreak.me"})

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest Releases"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="all", label="All Manga (A-Z)"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        cached = self._genre_cache.get("genres")
        if cached is not None:
            return cached
        try:
            html = self._http.get_text("/Genre/All/1")
        except ConnectorHttpError as exc:
            logger.info("MangaFreak genres unavailable: %s", exc)
            return []
        genres = [
            BrowseMode(id=slug, label=label) for slug, label in parse_genre_list(html)
        ]
        if genres:
            self._genre_cache.set("genres", genres)
        return genres

    # -- id normalization -------------------------------------------------

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("Manga/"):
            value = value.removeprefix("Manga/")
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return fully_unquote(chapter_id).strip().strip("/")

    # -- browse / search --------------------------------------------------

    def _listing(
        self, path: str, parser, *, page: int, operation: str
    ) -> PaginatedSeriesList:
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            logger.info(
                "MangaFreak %s %s%s status=error detail=%s",
                operation,
                SITE_BASE,
                path,
                exc,
            )
            raise
        listing = parser(html, page=page)
        logger.info(
            "MangaFreak %s %s%s status=ok count=%d total=%d has_more=%s",
            operation,
            SITE_BASE,
            path,
            len(listing.items),
            listing.total,
            listing.has_more,
        )
        return listing

    def get_series_list(
        self, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        template, parser = self._BROWSE_MODES.get(
            sort or "default", self._BROWSE_MODES["default"]
        )
        return self._listing(
            template.format(page=page), parser, page=page, operation="browse"
        )

    def browse_by_genre(
        self, genre: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        slug = quote(fully_unquote(genre).strip().strip("/"), safe="_-")
        if not slug:
            return self.get_series_list(page, sort=sort)
        return self._listing(
            f"/Genre/{slug}/{page}", parse_ranking, page=page, operation="genre"
        )

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        # MangaFreak search is single-page upstream: the server ignores every
        # pagination parameter its own paginator emits and replays the first
        # page (see parse_search_results). Answering page 2+ from here without
        # a request is both honest and free -- fetching would return the SAME
        # 25 series again, which the app would show as new results.
        if page > 1:
            return PaginatedSeriesList(
                items=[], page=page, page_size=SEARCH_PAGE_SIZE, total=0
            )
        slug = quote(normalized.lower(), safe="")
        path = f"/Find/{slug}"
        try:
            return self._listing(
                path, parse_search_results, page=page, operation="search"
            )
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                return PaginatedSeriesList(
                    items=[], page=page, page_size=SEARCH_PAGE_SIZE, total=0
                )
            raise

    # -- detail / chapters ------------------------------------------------

    def _load_detail(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        """Fetch the series page ONCE and parse both halves out of it.

        The detail document already contains the complete chapter table, so
        fetching it again for the chapter list would double the cost of the
        single most common interaction in the app (open a series, then read
        its chapters). Both caches are seeded here, so whichever entry point
        the client hits first primes the other.
        """
        path = series_path(series_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            logger.info(
                "MangaFreak detail %s%s status=error detail=%s", SITE_BASE, path, exc
            )
            return None, []

        series = parse_series_detail(html, series_key)
        if series is None:
            # MangaFreak serves the homepage (HTTP 200) for an unknown series.
            logger.info(
                "MangaFreak detail %s%s status=not-found (homepage fallback)",
                SITE_BASE,
                path,
            )
            return None, []

        chapters = parse_chapters(html, series_key)
        if chapters:
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=chapters[-1].title,
            )
        self._series_cache.set(series_key, series)
        self._chapter_cache.set(series_key, chapters)
        logger.info(
            "MangaFreak detail %s%s status=ok chapters=%d", SITE_BASE, path, len(chapters)
        )
        return series, chapters

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill page counts for chapters whose reader page was already read."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            count = self._page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=count) if count else chapter)
        return enriched

    def get_series(self, series_id: str) -> Series | None:
        key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(key)
        if cached is not None:
            return cached
        series, _chapters = self._load_detail(key)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        key = self._normalize_series_id(series_id)
        cached = self._chapter_cache.get(key)
        if cached is not None:
            return self._enrich_chapters(cached)
        _series, chapters = self._load_detail(key)
        return self._enrich_chapters(chapters)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(key)
        if cached is not None:
            return cached

        path = chapter_path(key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            logger.info(
                "MangaFreak pages %s%s status=error detail=%s", SITE_BASE, path, exc
            )
            return []

        # One reader document carries every page image URL, so a whole
        # chapter costs exactly one request -- never one per page.
        pages = parse_chapter_pages(html, key)
        if pages:
            self._page_cache.set(key, pages)
            self._page_count_cache.set(key, len(pages))
        logger.info(
            "MangaFreak pages %s%s status=ok count=%d", SITE_BASE, path, len(pages)
        )
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_key = page_id_chapter_key(fully_unquote(page_id).strip())
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
