"""HentaiHand online source connector (adult doujinshi, JSON API)."""

from __future__ import annotations

import logging
from typing import Any

from connectors.base import SourceConnector
from connectors.hentaihand.mappers import (
    COMICS_PATH,
    IMAGE_HOST_SUFFIX,
    PAGE_SIZE,
    SITE_BASE,
    browse_params,
    comic_to_chapter,
    comic_to_series,
    genre_params,
    images_path,
    list_browse_modes,
    list_genres,
    normalize_series_key,
    page_id_series_key,
    parse_images,
    parse_series_list,
    search_params,
    series_path,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses, so a 404 arrives as httpx's ``raise_for_status`` message
    ("Client error '404 Not Found' for url ..."); checking the attribute alone
    would be dead code. Verified from the VPS: an unknown slug answers a real
    404 with an HTML body on both ``/api/comics/<slug>`` and ``.../images``.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class HentaiHandConnector(SourceConnector):
    """Browse and read adult doujinshi from HentaiHand (public JSON API).

    Request budget:

    * browse / search / genre -- 1 GET, a Laravel paginator page of 18
    * series detail           -- 1 GET (``get_chapters`` reuses it from
      ``_detail_cache``: a gallery is one chapter, described by the same body)
    * chapter open            -- 1 GET, every page URL in one response
    * page image              -- 0 GETs here; the proxy fetches the CDN direct

    NOT a mirror of the registered ``nhentai`` source in the technical sense --
    its own origin, its own slug space, its own CDN -- but the CDN paths read
    ``nhentai/storage/...``, so expect the two catalogues to overlap heavily
    on content even though neither connector can reach the other's backend.
    """

    SOURCE_TYPE = "hentaihand"
    DISPLAY_NAME = "HentaiHand"
    DESCRIPTION = (
        "Browse and read adult doujinshi and hentai manga from HentaiHand. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=REQUEST_HEADERS,
            user_agent=BROWSER_USER_AGENT,
        )
        # Detail and chapter list are the same document: a comic is one
        # gallery, so opening a series and then its chapter list costs one
        # upstream GET, not two.
        self._detail_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)

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
        # Covers, thumbnails and page images all come from
        # cdn.hentaihand.com; the suffix covers that subdomain and the apex.
        return frozenset({IMAGE_HOST_SUFFIX})

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
            f"HentaiHand {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _listing(
        self,
        operation: str,
        params: dict[str, Any],
        *,
        page: int,
    ) -> PaginatedSeriesList:
        try:
            payload = self._http.get_json(COMICS_PATH, params=params)
        except ConnectorHttpError as exc:
            self._log(operation, COMICS_PATH, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(payload, page=page)
        self._log(
            operation,
            COMICS_PATH,
            params=params,
            status="ok",
            detail=f"count={len(listing.items)} total={listing.total}",
        )
        return listing

    def _empty_page(self, page: int) -> PaginatedSeriesList:
        return PaginatedSeriesList(
            items=[], page=max(page, 1), page_size=PAGE_SIZE, total=0, api_has_more=False
        )

    def _fetch_detail(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        cached = self._detail_cache.get(series_key)
        if cached is not None:
            return cached

        path = series_path(series_key)
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("detail", path, status="not_found")
                return None, []
            self._log("detail", path, status="error", detail=str(exc))
            raise

        series = comic_to_series(payload)
        if series is None:
            self._log("detail", path, status="error", detail="parse failed")
            return None, []

        chapter = comic_to_chapter(payload)
        chapters = [chapter] if chapter is not None else []
        result = (series, chapters)
        self._detail_cache.set(series_key, result)
        self._log("detail", path, status="ok", detail=f"pages={payload.get('pages')}")
        return result

    # --- catalog ------------------------------------------------------------

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(page, 1)
        return self._listing("browse", browse_params(sort, page), page=page)

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        page = max(page, 1)
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing("search", search_params(normalized, page, sort=sort), page=page)

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        page = max(page, 1)
        params = genre_params(genre, page, sort=sort)
        if params is None:
            # The API filters on tag ids, so a slug outside the menu cannot be
            # turned into a request; answering empty beats quietly serving the
            # unfiltered catalog under a genre heading.
            self._log("genre", COMICS_PATH, status="not_found", detail=f"genre={genre}")
            return self._empty_page(page)
        return self._listing("genre", params, page=page)

    # --- series / chapters --------------------------------------------------

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_detail(normalize_series_key(series_id))[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._fetch_detail(normalize_series_key(series_id))[1]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        # A gallery is its own chapter, so the chapter key IS the series slug.
        series_key = normalize_series_key(chapter_id)
        cached = self._page_cache.get(series_key)
        if cached is not None:
            return cached

        path = images_path(series_key)
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("pages", path, status="not_found")
                return []
            self._log("pages", path, status="error", detail=str(exc))
            raise

        pages = parse_images(payload, series_key)
        if pages:
            self._page_cache.set(series_key, pages)
        self._log("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        """O(1) upstream: the page id carries its gallery, which is cached."""
        series_key = page_id_series_key(page_id)
        if series_key is None:
            return None
        for page in self.get_chapter_pages(series_key):
            if page.id == page_id:
                return page
        return None
