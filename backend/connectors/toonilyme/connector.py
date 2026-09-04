"""toonily.me online source connector.

``https://toonily.me`` 301-redirects to ``https://toontop.io`` -- the site was
rebranded. This connector talks to the canonical origin so no request pays the
redirect hop, and to that site's JSON API (``https://api.toontop.io``) rather
than scraping its Next.js HTML.

Reading one chapter costs exactly ONE request; opening a series costs one, and
its chapter list costs zero extra for short series (see ``get_chapters``).

Verified end-to-end from the production VPS: browse, search, series detail,
the full chapter list, and real page-image bytes.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.toonilyme.mappers import (
    API_BASE,
    BROWSER_USER_AGENT,
    IMAGE_HOST,
    PAGE_SIZE,
    SEARCH_PATH,
    SITE_BASE,
    browse_modes,
    chapter_detail_path,
    chapter_list_path,
    declared_chapter_count,
    genre_modes,
    make_chapter_key,
    normalize_series_key,
    normalize_sort,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_embedded_chapters,
    parse_series_detail,
    parse_series_list,
    search_params,
    search_query_variant,
    series_detail_path,
    series_hsid,
    split_chapter_key,
)

logger = logging.getLogger(__name__)

JSON_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    # The API is CORS-scoped to the site; sending the site's own Origin and
    # Referer is what a browser does and keeps the edge from treating this as
    # a bare bot request.
    "Origin": SITE_BASE,
    "Referer": f"{SITE_BASE}/",
}


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses; a 404 otherwise surfaces only as httpx's ``raise_for_status``
    text ("Client error '404 Not Found' for url ..."), so BOTH forms must be
    checked -- a bare ``status_code == 404`` test here is dead code. Verified
    from the VPS: an unknown slug answers a real 404 with
    ``{"code": "NOT_FOUND"}``.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class ToonilyMeConnector(SourceConnector):
    """Browse and read manga/manhwa/webtoons from toonily.me (ToonTop)."""

    SOURCE_TYPE = "toonilyme"
    DISPLAY_NAME = "Toonily.me"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and webtoons from toonily.me (ToonTop). "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    # The catalog is adult-leaning: the site's own most-popular and trending
    # views are dominated by explicit titles, and its genre index carries
    # Adult/Hentai/Smut/NTR/Incest/Rape tags. The per-title ``is_adult`` flag
    # upstream is unreliable (explicit series come back ``is_adult: false``),
    # so the source is marked mature at the source level rather than trusting
    # a flag that under-reports.
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            API_BASE,
            user_agent=BROWSER_USER_AGENT,
            headers=JSON_HEADERS,
        )
        # ONE cache for the raw series-detail payload. get_series and
        # get_chapters both read it, so opening a series does not fetch its
        # detail document twice -- the anti-pattern this codebase has already
        # had to fix elsewhere.
        self._detail_cache: TTLCache[dict[str, Any]] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)

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
        # Covers and page images are both served from rx.toontop.io; the
        # registrable domain is allowlisted so sibling CDN subdomains in the
        # same rotation resolve, while everything off-site stays blocked.
        return frozenset({IMAGE_HOST})

    def image_fetch_headers(self) -> dict[str, str]:
        # rx.toontop.io enforces hotlink protection -- an image GET without a
        # site Referer answers 403 (verified from the VPS).
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return browse_modes()

    def list_genres(self) -> list[BrowseMode]:
        return genre_modes()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

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
            f"ToonilyMe {operation} {API_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_key(self, value: str) -> str:
        return normalize_series_key(fully_unquote(value))

    def _listing(
        self,
        operation: str,
        page: int,
        *,
        query: str | None = None,
        sort: str | None = None,
        genre: str | None = None,
    ) -> PaginatedSeriesList:
        page = max(1, page)
        params = search_params(query, page, sort=sort, genre=genre)
        try:
            payload = self._http.get_json(SEARCH_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log(operation, SEARCH_PATH, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(payload, page)
        self._log(
            operation,
            SEARCH_PATH,
            params=params,
            status="ok",
            detail=(
                f"page={page} sort={normalize_sort(sort)!r} count={len(listing.items)} "
                f"total={listing.total} has_more={listing.has_more}"
            ),
        )
        return listing

    def _detail_payload(self, series_key: str) -> dict[str, Any] | None:
        """Fetch (once per TTL) the series-detail document.

        Carries the metadata, the series' hsid, its declared chapter count and
        its newest ~50 chapters -- everything get_series and get_chapters both
        need, from a single request.
        """
        cached = self._detail_cache.get(series_key)
        if cached is not None:
            return cached

        path = series_detail_path(series_key)
        params = {"include": "details"}
        try:
            payload = self._http.get_json(path, params=params)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("detail", path, params=params, status="not_found")
                return None
            self._log("detail", path, params=params, status="error", detail=str(exc))
            raise
        self._detail_cache.set(series_key, payload)
        return payload

    def _enrich(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill page counts for chapters whose images have already been seen."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            count = self._page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=count) if count else chapter)
        return enriched

    # ------------------------------------------------------------------
    # SourceConnector
    # ------------------------------------------------------------------

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._listing("browse", page, sort=sort)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        normalized = " ".join((query or "").split())
        if not normalized:
            return self.get_series_list(page, sort=sort)

        # Multi-word phrases are searched in their hyphenated (slug-shaped)
        # form, which is the only one upstream resolves to the intended title;
        # see search_query_variant. Costs one request in the normal case.
        primary = search_query_variant(normalized)
        listing = self._listing("search", page, query=primary, sort=sort)
        if not listing.items and primary != normalized:
            # Precision found nothing -- retry the raw phrase for recall.
            listing = self._listing("search", page, query=normalized, sort=sort)
        return listing

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        normalized = (genre or "").strip().strip("/")
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing("genre", page, sort=sort, genre=normalized)

    def get_series(self, series_id: str) -> Series | None:
        series_key = self._normalize_series_key(series_id)
        if not series_key:
            return None
        payload = self._detail_payload(series_key)
        if payload is None:
            return None
        series = parse_series_detail(payload, series_key)
        if series is None:
            self._log("detail", series_detail_path(series_key), status="error", detail="parse failed")
            return None
        self._log(
            "detail",
            series_detail_path(series_key),
            status="ok",
            detail=f"chapters={series.chapter_count}",
        )
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_key = self._normalize_series_key(series_id)
        if not series_key:
            return []
        cached = self._chapter_list_cache.get(series_key)
        if cached is not None:
            return self._enrich(cached)

        payload = self._detail_payload(series_key)
        if payload is None:
            return []

        # The detail document already carries the newest ~50 chapters. When
        # that IS the whole series (the common case -- most titles here run
        # well under 50), the chapter list costs no request at all.
        embedded = parse_embedded_chapters(payload, series_key)
        declared = declared_chapter_count(payload)
        chapters = embedded
        source = "embedded"

        if declared > len(embedded):
            hsid = series_hsid(payload)
            if hsid:
                path = chapter_list_path(hsid)
                try:
                    bulk = self._http.get_json(path)
                except ConnectorHttpError as exc:
                    # Fall back to the embedded window rather than losing the
                    # series entirely; the reader still gets recent chapters.
                    self._log("chapters", path, status="error", detail=str(exc))
                    bulk = None
                if bulk is not None:
                    parsed = parse_chapters(bulk, series_key)
                    if parsed:
                        chapters = parsed
                        source = "bulk"

        if chapters:
            self._chapter_list_cache.set(series_key, chapters)
        self._log(
            "chapters",
            series_detail_path(series_key),
            status="ok",
            detail=f"count={len(chapters)} declared={declared} source={source}",
        )
        return self._enrich(chapters)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = fully_unquote(chapter_id or "").strip().strip("/")
        parts = split_chapter_key(chapter_key)
        if parts is None:
            return []
        series_key, chapter_slug = parts
        chapter_key = make_chapter_key(series_key, chapter_slug)

        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_detail_path(series_key, chapter_slug)
        params = {"include": "details"}
        try:
            payload = self._http.get_json(path, params=params)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("pages", path, params=params, status="not_found")
                return []
            self._log("pages", path, params=params, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(payload, chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._page_count_cache.set(chapter_key, len(pages))
        self._log("pages", path, params=params, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_key = page_id_chapter_key(fully_unquote(page_id or ""))
        if not chapter_key:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
