"""Manhwa18 (manhwa18.cc) online source connector."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.manhwa18.mappers import (
    PAGE_SIZE,
    SITE_BASE,
    browse_modes,
    chapter_path,
    genre_modes,
    genre_path,
    is_known_genre,
    listing_params,
    listing_path,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_params,
    series_path,
)
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    ``SyncConnectorHttpClient`` only attaches ``status_code`` for
    ``RETRYABLE_STATUS`` responses, so a bare ``exc.status_code == 404`` check
    is dead code here — a 404 arrives as httpx's ``raise_for_status`` message
    ("Client error '404 Not Found' for url ..."). Both forms are matched.
    Verified from the VPS: ``/webtoon/<missing-slug>`` answers a real 404.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class Manhwa18Connector(SourceConnector):
    """Browse and read adult manhwa from manhwa18.cc.

    Two site properties shape the whole design, both measured from the VPS:

    * the series page carries the *complete* chapter list inline (227 rows on
      a long series), so ``get_series`` and ``get_chapters`` share one fetch
      through ``_series_cache`` instead of downloading the same ~190KB
      document twice on every detail open; and
    * the chapter page carries every page-image URL inline, so a chapter's
      images cost exactly one request no matter how many pages it has —
      never one request per page.
    """

    SOURCE_TYPE = "manhwa18"
    DISPLAY_NAME = "Manhwa18"
    DESCRIPTION = (
        "Browse and read adult (18+) Korean manhwa from manhwa18.cc. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    #: Adult source — the 18+ gate hides it entirely for profiles with mature
    #: content disabled (see SourceConnector.is_mature).
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(SITE_BASE, headers=HTML_HEADERS)
        # One entry per series holds BOTH the parsed detail and its chapter
        # list, keyed by slug — the pair comes from a single document, so
        # caching them together is what makes the second call free.
        self._series_cache: TTLCache[tuple[Series, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
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
        # manhwa18.cc: cover art under /manga/<slug><hash>.jpg
        # img<NN>.manhwa18.cc: chapter page images (img01/img02/img11/img33
        # observed) — matched as subdomains of the one allowlisted domain.
        return frozenset({"manhwa18.cc"})

    def list_browse_modes(self) -> list[BrowseMode]:
        return browse_modes()

    def list_genres(self) -> list[BrowseMode]:
        # Static site navigation — costs zero requests.
        return genre_modes()

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
            f"Manhwa18 {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_key(self, series_id: str) -> str:
        """Accept a bare slug or a full ``/webtoon/<slug>`` path.

        The key stays opaque past this point — nothing downstream splits it.
        """
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("webtoon/"):
            value = value.removeprefix("webtoon/")
        return value

    def _normalize_chapter_key(self, chapter_id: str) -> str:
        value = fully_unquote(chapter_id).strip().strip("/")
        if value.startswith("webtoon/"):
            value = value.removeprefix("webtoon/")
        return value

    def _fetch_listing(
        self,
        path: str,
        *,
        params: dict[str, str] | None,
        page: int,
        operation: str,
        detail: str = "",
    ) -> PaginatedSeriesList:
        try:
            html_text = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log_request(
                operation, path, params=params, status="error", detail=str(exc)
            )
            raise
        listing = parse_series_list(html_text, page=page, page_size=PAGE_SIZE)
        self._log_request(
            operation,
            path,
            params=params,
            status="ok",
            detail=(
                f"page={page} count={len(listing.items)} "
                f"has_more={listing.has_more}{detail}"
            ),
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        return self._fetch_listing(
            listing_path(sort, page),
            params=listing_params(sort),
            page=page,
            operation="browse",
            detail=f" sort={sort or 'default'!r}",
        )

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        slug = genre.strip().strip("/").lower()
        if not is_known_genre(slug):
            raise ValueError(f"Unknown manhwa18 genre: {genre!r}")
        # The genre listing ignores `orderby` (verified from the VPS: the same
        # cards come back with and without it), so `sort` is deliberately not
        # forwarded rather than sent as a parameter that silently does nothing.
        return self._fetch_listing(
            genre_path(slug, page),
            params=None,
            page=page,
            operation="genre",
            detail=f" genre={slug!r}",
        )

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        path = "/search"
        params = search_params(normalized, page)
        try:
            html_text = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log_request("search", path, params=params, status="error", detail=str(exc))
            raise
        listing = parse_search_results(html_text, page=page, page_size=PAGE_SIZE)
        self._log_request(
            "search",
            path,
            params=params,
            status="ok",
            detail=(
                f"page={page} query={normalized!r} count={len(listing.items)} "
                f"has_more={listing.has_more}"
            ),
        )
        return listing

    def _fetch_series(self, series_key: str) -> tuple[Series, list[Chapter]] | None:
        """Detail + chapter list from ONE document, cached as a pair.

        The single most expensive avoidable mistake on this source would be
        fetching the ~190KB series page twice — once for ``get_series`` and
        again for ``get_chapters`` — on every detail open. Both callers land
        here instead.
        """
        cached = self._series_cache.get(series_key)
        if cached is not None:
            return cached

        path = series_path(series_key)
        try:
            html_text = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("detail", path, status="error", detail=str(exc))
            if _is_not_found(exc):
                return None
            raise

        series = parse_series_detail(html_text, series_key)
        if series is None:
            self._log_request("detail", path, status="error", detail="parse failed")
            return None

        chapters = parse_chapters(html_text, series_key)
        if chapters:
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=chapters[-1].title,
            )
        entry = (series, chapters)
        self._series_cache.set(series_key, entry)
        self._log_request("detail", path, status="ok", detail=f"chapters={len(chapters)}")
        return entry

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill in page counts learned from chapters already opened."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached_count = self._chapter_page_count_cache.get(chapter.id)
            if cached_count is not None and cached_count > 0:
                enriched.append(replace(chapter, page_count=cached_count))
            else:
                enriched.append(chapter)
        return enriched

    def get_series(self, series_id: str) -> Series | None:
        entry = self._fetch_series(self._normalize_series_key(series_id))
        return entry[0] if entry else None

    def get_chapters(self, series_id: str) -> list[Chapter]:
        entry = self._fetch_series(self._normalize_series_key(series_id))
        if entry is None:
            return []
        return self._enrich_chapters(entry[1])

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = self._normalize_chapter_key(chapter_id)
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_path(chapter_key)
        try:
            html_text = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("pages", path, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(html_text, chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._chapter_page_count_cache.set(chapter_key, len(pages))
        self._log_request("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        """Resolve one page without traversing the source.

        The chapter key is recoverable from the page id, so this is a single
        cached chapter lookup — the image proxy calls it once per image.
        """
        normalized = fully_unquote(page_id).strip().strip("/")
        if normalized.startswith("webtoon/"):
            normalized = normalized.removeprefix("webtoon/")
        chapter_key = page_id_chapter_key(normalized)
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == normalized:
                return page
        return None
