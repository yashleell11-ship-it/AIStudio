"""Manhwa18.net online source connector (adult manhwa, Inertia payloads)."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.manhwa18net.mappers import (
    BROWSE_PATH,
    IMAGE_HOST_SUFFIX,
    SEARCH_PATH,
    SITE_BASE,
    browse_params,
    chapter_path,
    genre_path,
    list_browse_modes,
    list_genres,
    normalize_chapter_key,
    normalize_series_key,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    search_params,
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

_IMAGE_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/avif", "image/gif"}
)

#: (magic prefix, media type). Ordered longest-first where prefixes overlap.
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _sniff_image_media_type(body: bytes, declared: str | None) -> str:
    """Return a truthful image media type for ``body``.

    A declared type that is already a real image wins -- this only fills in
    for an upstream that mislabels its images.
    """
    cleaned = (declared or "").split(";")[0].strip().lower()
    if cleaned in _IMAGE_MEDIA_TYPES:
        return cleaned
    for magic, media_type in _IMAGE_MAGIC:
        if body.startswith(magic):
            return media_type
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    if body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis"):
        return "image/avif"
    return cleaned or "application/octet-stream"


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses, so a 404 arrives as httpx's ``raise_for_status`` message
    ("Client error '404 Not Found' for url ..."); the attribute check alone
    would be dead code. Verified from the VPS: an unknown series slug answers
    a real 404 carrying the site's own 7KB error page.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class Manhwa18NetConnector(SourceConnector):
    """Browse and read adult manhwa from Manhwa18.net (Inertia payloads).

    Every stage is a single upstream request, because Inertia embeds the whole
    server-side payload in the document:

    * browse / search / genre -- 1 GET, a Laravel paginator of 18-24 series
    * series detail           -- 1 GET (``get_series`` + ``get_chapters`` share
      it via ``_detail_cache``; the page carries the full chapter list)
    * chapter open            -- 1 GET, every page URL inline
    * page image              -- 1 GET, through ``fetch_proxied_image`` below

    DISTINCT from the registered ``manhwa18`` source, which reads
    manhwa18.**cc** over ``/webtoon/<slug>`` with a different theme and only
    partially overlapping content; this connector must never reuse that
    source id. Its sibling manhwa18.**com** IS the same backend as this one
    (identical slugs, same ``min.manhwa18.net`` images) -- only one of that
    pair may ever be registered, and this is the better half because its
    payload arrives as JSON.
    """

    SOURCE_TYPE = "manhwa18net"
    DISPLAY_NAME = "Manhwa18.net"
    DESCRIPTION = (
        "Browse and read adult manhwa, manhua and manga from Manhwa18.net. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
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
        # Detail and chapter list come from ONE document, so they share ONE
        # cache entry: opening a series and then its chapter list is a single
        # upstream GET, not two of the same 70KB page.
        self._detail_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._chapter_page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)

    # --- descriptor ---------------------------------------------------------

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
        # Covers and page images alike come from min.manhwa18.net; the suffix
        # covers that subdomain and the apex, which serves the site's assets.
        return frozenset({IMAGE_HOST_SUFFIX})

    def fetch_proxied_image(self, url: str) -> tuple[str, bytes] | None:
        """Fetch a page image and label it by its actual bytes.

        Measured from the VPS: every chapter image on ``min.manhwa18.net``
        answers ``Content-Type: binary/octet-stream`` (all six pages of the
        sampled chapter, 2-2.5MB PNGs). The image proxy clamps any
        unrecognised type to ``application/octet-stream`` and serves it with
        ``X-Content-Type-Options: nosniff``, so the browser is told not to
        second-guess it and refuses to render -- every page in every chapter
        would arrive as an undisplayable download. Covers are unaffected
        (they come back ``image/jpeg``), which is why this bug hides until a
        chapter is opened.

        Sniffing the magic number restores a truthful ``image/*`` label; a
        header that is already a real image type still wins.
        """
        media_type, body = self._http.get_bytes(url)
        return _sniff_image_media_type(body, media_type), body

    def list_browse_modes(self) -> list[BrowseMode]:
        return list_browse_modes()

    def list_genres(self) -> list[BrowseMode]:
        return list_genres()

    # --- helpers ------------------------------------------------------------

    def _log(
        self,
        operation: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        status: str,
        detail: str | None = None,
    ) -> None:
        message = (
            f"Manhwa18Net {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _listing(
        self,
        operation: str,
        path: str,
        params: dict[str, Any],
        *,
        page: int,
    ) -> PaginatedSeriesList:
        try:
            html = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log(operation, path, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page)
        self._log(
            operation,
            path,
            params=params,
            status="ok",
            detail=f"count={len(listing.items)} total={listing.total}",
        )
        return listing

    def _enrich(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill page_count from chapters already read this session."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached = self._chapter_page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=cached) if cached else chapter)
        return enriched

    def _fetch_detail(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        """One GET for both the series metadata and its full chapter list."""
        cached = self._detail_cache.get(series_key)
        if cached is not None:
            return cached

        path = series_path(series_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("detail", path, status="not_found")
                return None, []
            self._log("detail", path, status="error", detail=str(exc))
            raise

        series = parse_series_detail(html, series_key)
        if series is None:
            self._log("detail", path, status="error", detail="parse failed")
            return None, []

        chapters = parse_chapters(html, series_key)
        if chapters:
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=series.latest_chapter or chapters[-1].title,
            )
        result = (series, chapters)
        self._detail_cache.set(series_key, result)
        self._log("detail", path, status="ok", detail=f"chapters={len(chapters)}")
        return result

    # --- catalog ------------------------------------------------------------

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(page, 1)
        return self._listing("browse", BROWSE_PATH, browse_params(sort, page), page=page)

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        page = max(page, 1)
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing(
            "search", SEARCH_PATH, search_params(normalized, page, sort=sort), page=page
        )

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        page = max(page, 1)
        return self._listing(
            "genre", genre_path(genre), browse_params(sort, page), page=page
        )

    # --- series / chapters --------------------------------------------------

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_detail(normalize_series_key(series_id))[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._enrich(self._fetch_detail(normalize_series_key(series_id))[1])

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = normalize_chapter_key(chapter_id)
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_path(chapter_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("pages", path, status="not_found")
                return []
            self._log("pages", path, status="error", detail=str(exc))
            raise

        pages = parse_chapter_pages(html, chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._chapter_page_count_cache.set(chapter_key, len(pages))
        self._log("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        """O(1) upstream: the page id carries its chapter, which is cached."""
        chapter_key = page_id_chapter_key(page_id)
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
