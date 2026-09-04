"""Rawkuma online source connector (raw Japanese manga)."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.rawkuma.mappers import (
    BROWSE_MODES,
    GENRE_TERMS,
    PAGE_SIZE,
    REST_MANGA_PATH,
    SITE_BASE,
    chapter_id_to_path,
    listing_params,
    normalize_key,
    normalize_sort,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list_json,
    rerank_by_title,
    series_id_to_path,
)

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}

def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses, so a 404 arrives as httpx's ``raise_for_status`` message
    ("Client error '404 Not Found' for url ...") with ``status_code`` unset.
    Checking only the attribute would be dead code. Verified from the VPS:
    a missing series and a missing chapter both answer a real 404.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class RawkumaConnector(SourceConnector):
    """Browse and read raw Japanese manga from Rawkuma.

    Every stage is a single upstream request:

    * browse / genre  -> one ``/wp-json/wp/v2/manga`` page (JSON, ~100 KB)
    * series + chapters -> ONE ``/manga/<slug>/`` fetch, shared through a TTL
      cache so opening a series does not download the same page twice
    * chapter pages   -> one reader fetch yields every page image URL
    """

    SOURCE_TYPE = "rawkuma"
    DISPLAY_NAME = "Rawkuma"
    DESCRIPTION = (
        "Raw (untranslated) Japanese manga, manhwa and manhua from Rawkuma. "
        "Titles and metadata are romaji/English; the page images are Japanese. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=REQUEST_HEADERS,
            user_agent=BROWSER_USER_AGENT,
        )
        # One entry per series page: the parsed detail AND its chapter list,
        # so get_series() followed by get_chapters() -- which is exactly what
        # opening a series does -- costs one HTTP request, not two.
        self._series_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=1800.0)

    # -- descriptor ------------------------------------------------------

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
        # rawkuma.net serves cover art out of /wp-content/uploads/; page
        # images come from the site's own CDN, which uses two subdomains
        # (kuma.kyut.dev and rcdn.kyut.dev) across the catalog.
        return frozenset({"rawkuma.net", "kyut.dev"})

    def list_browse_modes(self) -> list[BrowseMode]:
        return list(BROWSE_MODES)

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=slug, label=label) for slug, label, _term in GENRE_TERMS]

    # -- logging ---------------------------------------------------------

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
            f"Rawkuma {operation} {SITE_BASE}{path} params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    # -- catalog ---------------------------------------------------------

    def _rest_listing(
        self,
        page: int,
        *,
        operation: str,
        sort: str | None = None,
        genre: str | None = None,
        search: str | None = None,
    ) -> PaginatedSeriesList:
        params = listing_params(page, sort=sort, genre=genre, search=search)
        try:
            payload = self._http.get_json_value(REST_MANGA_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log(
                operation, REST_MANGA_PATH, params=params, status="error", detail=str(exc)
            )
            # WordPress answers 400 for a page number past the end of the
            # collection; that is an empty page, not a failure to report.
            if exc.status_code == 400 or "400 Bad Request" in str(exc):
                return PaginatedSeriesList(
                    items=[], page=max(1, page), page_size=PAGE_SIZE, api_has_more=False
                )
            raise
        listing = parse_series_list_json(payload, page=page, page_size=PAGE_SIZE)
        self._log(
            operation,
            REST_MANGA_PATH,
            params=params,
            status="ok",
            detail=f"count={len(listing.items)} has_more={listing.has_more}",
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._rest_listing(
            max(1, page), operation="browse", sort=normalize_sort(sort)
        )

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        return self._rest_listing(
            max(1, page),
            operation="genre",
            sort=normalize_sort(sort),
            genre=genre.strip().lower(),
        )

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        """Search the REST collection, then float verbatim title matches.

        Rawkuma also runs a private ``admin-ajax`` search that indexes the
        theme's ``search_index`` meta (romaji title PLUS the native Japanese
        title), which is the only surface where "壁ドン" finds "Kabedon!".
        It is unreachable from here, and not because of the site: verified
        from the VPS, that endpoint answers 200 to a normal httpx POST but
        403 ("Just a moment...", a Cloudflare bot interstitial) the moment
        the request carries an explicitly-passed, all-lowercase header name --
        which is exactly what ``SyncConnectorHttpClient.post_text`` sends,
        since it re-supplies ``dict(self._client.headers)`` and httpx has
        already lowercased those keys. One lowercase header is enough to
        trip it; the same call with the original casing succeeds. Rather
        than keep a path that always fails (and, because a 403 carries no
        ``status_code``, burns three retries and ~1.5s of backoff every
        search), search stays on REST until that shared client is fixed.
        """
        page = max(1, page)
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        listing = self._rest_listing(page, operation="search", search=normalized)
        return rerank_by_title(listing, normalized)

    # -- series detail + chapters ---------------------------------------

    def _fetch_series(self, series_id: str) -> tuple[Series | None, list[Chapter]]:
        """Fetch and parse one series page once, for both detail and chapters.

        The document carries the metadata AND the complete chapter list, so
        the two public methods below share this result instead of each
        downloading the same half-megabyte page.
        """
        key = normalize_key(series_id)
        cached = self._series_cache.get(key)
        if cached is not None:
            return cached

        path = series_id_to_path(key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("detail", path, status="error", detail=str(exc))
            if _is_not_found(exc):
                self._series_cache.set(key, (None, []))
            return None, []

        series = parse_series_detail(html, key)
        chapters = parse_chapters(html, key)
        if series is not None and chapters:
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=chapters[-1].title,
            )
        elif series is not None:
            series = replace(series, chapter_count=len(chapters))

        if series is not None:
            self._series_cache.set(key, (series, chapters))
        self._log(
            "detail",
            path,
            status="ok" if series is not None else "error",
            detail=f"chapters={len(chapters)}",
        )
        return series, chapters

    def _with_known_page_counts(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            count = self._page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=count) if count else chapter)
        return enriched

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_series(series_id)[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._with_known_page_counts(self._fetch_series(series_id)[1])

    # -- pages -----------------------------------------------------------

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        key = normalize_key(chapter_id)
        cached = self._page_cache.get(key)
        if cached is not None:
            return cached

        path = chapter_id_to_path(key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("pages", path, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(html, key)
        if pages:
            self._page_cache.set(key, pages)
            self._page_count_cache.set(key, len(pages))
        self._log("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
