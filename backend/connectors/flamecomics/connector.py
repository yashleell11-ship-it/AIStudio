"""Flame Comics source connector (flamecomics.xyz).

A scanlation group's own Next.js site, not a Madara clone. Probed from the VPS
(production egress + TLS, 2026-09-04): every stage -- catalog, search, series
detail, chapter list and page-image bytes -- answers 200 with plain httpx, no
Cloudflare interstitial anywhere, and the CDN needs neither a ``Referer`` nor a
browser user agent.

``robots.txt`` disallows ``/api/`` for ``*`` (and blocks a list of named AI
crawlers outright). Nothing here touches ``/api/``: the connector reads the
same statically generated ``/_next/data/...`` payloads that back the site's own
pages, which are the JSON twins of ordinary content routes.

Request budget per user action -- the point of this design:

===========================  ==========================================
browse / search / genre      1 request, cached (whole catalog per fetch)
series detail + chapter list 1 request, shared by both calls
open a chapter               1 request for every page URL in the chapter
===========================  ==========================================

Search costs *zero* requests once the catalog is warm, because ``/browse.json``
is statically generated and ignores ``?search=`` -- the site's own search box
filters the same array client-side.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from connectors.base import SourceConnector
from connectors.flamecomics.mappers import (
    BROWSE_MODES,
    PAGE_SIZE,
    SITE_BASE,
    browse_data_path,
    build_id_path,
    chapter_data_path,
    collect_genres,
    latest_data_path,
    make_chapter_key,
    matches_query,
    normalize_series_key,
    order_catalog,
    page_id_chapter_key,
    paginate,
    parse_build_id,
    parse_catalog,
    parse_catalog_rankings,
    parse_chapter_pages,
    parse_chapters,
    parse_latest_feed,
    parse_series_detail,
    search_rank,
    series_data_path,
    split_chapter_key,
    uses_latest_feed,
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
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}

#: The build id only changes when the site redeploys, and a wrong one is
#: self-correcting (see ``_fetch_data``), so it is held far longer than content.
_BUILD_ID_TTL = 1800.0
#: One catalog fetch backs browse, search and genre browse.
_CATALOG_TTL = 600.0
_SERIES_TTL = 300.0
_PAGES_TTL = 900.0

_CATALOG_KEY = "browse"
_LATEST_KEY = "latest"


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    ``SyncConnectorHttpClient`` only attaches ``status_code`` for statuses in
    RETRYABLE_STATUS; a 404 otherwise surfaces only in httpx's
    ``raise_for_status`` message ("Client error '404 Not Found' for url ..."),
    so a bare ``exc.status_code == 404`` check would be dead code. Match both
    forms (same fix as ``connectors/freewebnovel``).
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class FlameComicsConnector(SourceConnector):
    """Browse and read manga from Flame Comics."""

    SOURCE_TYPE = "flamecomics"
    DISPLAY_NAME = "Flame Comics"
    DESCRIPTION = (
        "Browse and read manhwa, manhua, and manga from the Flame Comics "
        "scanlation group. Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers={"User-Agent": BROWSER_USER_AGENT, **REQUEST_HEADERS},
        )
        self._build_id_cache: TTLCache[str] = TTLCache(ttl_seconds=_BUILD_ID_TTL)
        self._catalog_cache: TTLCache[list[Series]] = TTLCache(ttl_seconds=_CATALOG_TTL)
        self._ranking_cache: TTLCache[tuple[dict[str, int], dict[str, int]]] = TTLCache(
            ttl_seconds=_CATALOG_TTL
        )
        self._latest_cache: TTLCache[list[Series]] = TTLCache(ttl_seconds=_CATALOG_TTL)
        # One entry per series holds BOTH the detail and its chapter list, so
        # get_series followed by get_chapters -- what every series open does --
        # costs a single upstream request rather than the same page twice.
        self._series_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=_SERIES_TTL
        )
        self._pages_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=_PAGES_TTL)
        self._build_lock = threading.Lock()

    # ------------------------------------------------------------------
    # descriptors
    # ------------------------------------------------------------------

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
        # cdn.flamecomics.xyz serves both cover art and every page image.
        return frozenset({"flamecomics.xyz"})

    def list_browse_modes(self) -> list[BrowseMode]:
        return list(BROWSE_MODES)

    def _log(self, operation: str, path: str, *, status: str, detail: str | None = None) -> None:
        message = f"FlameComics {operation} {SITE_BASE}{path} status={status}"
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    # ------------------------------------------------------------------
    # build id + data fetch
    # ------------------------------------------------------------------

    def _resolve_build_id(self, *, force: bool = False) -> str | None:
        """Fetch and cache Next.js' build id.

        Serialized on a lock so a burst of concurrent calls on a cold cache
        resolves it once instead of N times.
        """
        if not force:
            cached = self._build_id_cache.get(_CATALOG_KEY)
            if cached is not None:
                return cached
        with self._build_lock:
            if not force:
                cached = self._build_id_cache.get(_CATALOG_KEY)
                if cached is not None:
                    return cached
            path = build_id_path()
            try:
                html = self._http.get_text(path)
            except ConnectorHttpError as exc:
                self._log("buildid", path, status="error", detail=str(exc))
                return None
            build_id = parse_build_id(html)
            if build_id is None:
                self._log("buildid", path, status="error", detail="no buildId in page")
                return None
            self._build_id_cache.set(_CATALOG_KEY, build_id)
            return build_id

    def _fetch_data(self, make_path: Any) -> dict[str, Any] | None:
        """GET a ``/_next/data/<buildId>/...`` payload, healing a stale build id.

        Two different failures both answer HTTP 404 here:

        * the series/chapter genuinely does not exist -> ``{"notFound":true}``
        * the site redeployed and our cached build id is gone ->
          ``{"__N_SSG":true,"pageProps":{}}``

        Both were confirmed from the VPS. The client raises on either, so the
        body cannot be inspected; instead a 404 triggers one build-id
        re-resolution. If the id came back *different*, the first 404 was the
        stale-build case and the request is retried once. If it is unchanged,
        the resource really is missing and ``None`` is returned without a
        second pointless round trip.
        """
        build_id = self._resolve_build_id()
        if build_id is None:
            return None
        path = make_path(build_id)
        try:
            return self._http.get_json(path)
        except ConnectorHttpError as exc:
            if not _is_not_found(exc):
                self._log("data", path, status="error", detail=str(exc))
                raise
            refreshed = self._resolve_build_id(force=True)
            if refreshed is None or refreshed == build_id:
                self._log("data", path, status="not_found")
                return None
            retry_path = make_path(refreshed)
            self._log("data", path, status="stale_build", detail=f"retry as {retry_path}")
            try:
                return self._http.get_json(retry_path)
            except ConnectorHttpError as retry_exc:
                if _is_not_found(retry_exc):
                    self._log("data", retry_path, status="not_found")
                    return None
                self._log("data", retry_path, status="error", detail=str(retry_exc))
                raise

    # ------------------------------------------------------------------
    # catalog
    # ------------------------------------------------------------------

    def _catalog(self) -> list[Series]:
        cached = self._catalog_cache.get(_CATALOG_KEY)
        if cached is not None:
            return cached
        payload = self._fetch_data(browse_data_path)
        if payload is None:
            return []
        catalog = parse_catalog(payload)
        if catalog:
            self._catalog_cache.set(_CATALOG_KEY, catalog)
            self._ranking_cache.set(_CATALOG_KEY, parse_catalog_rankings(payload))
        self._log("catalog", "/browse.json", status="ok", detail=f"count={len(catalog)}")
        return catalog

    def _rankings(self) -> tuple[dict[str, int], dict[str, int]]:
        return self._ranking_cache.get(_CATALOG_KEY) or ({}, {})

    def _latest(self) -> list[Series]:
        cached = self._latest_cache.get(_LATEST_KEY)
        if cached is not None:
            return cached
        payload = self._fetch_data(latest_data_path)
        if payload is None:
            return []
        feed = parse_latest_feed(payload)
        if feed:
            self._latest_cache.set(_LATEST_KEY, feed)
        self._log("latest", "/latest.json", status="ok", detail=f"count={len(feed)}")
        return feed

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if uses_latest_feed(sort):
            items = self._latest()
        else:
            catalog = self._catalog()
            rank_map, added_map = self._rankings()
            items = order_catalog(catalog, rank_map, added_map, sort)
        listing = paginate(items, page)
        self._log(
            "browse",
            "/browse",
            status="ok",
            detail=f"page={page} sort={sort or 'default'} count={len(listing.items)} total={listing.total}",
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        normalized = (query or "").strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        catalog = self._catalog()
        hits = [series for series in catalog if matches_query(series, normalized)]
        hits.sort(key=lambda series: search_rank(series, normalized))
        listing = paginate(hits, page)
        self._log(
            "search",
            "/browse.json",
            status="ok",
            detail=f"query={normalized!r} page={page} count={len(listing.items)} total={listing.total}",
        )
        return listing

    def list_genres(self) -> list[BrowseMode]:
        return collect_genres(self._catalog())

    def browse_by_genre(
        self, genre: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        wanted = (genre or "").strip().lower()
        if not wanted:
            return self.get_series_list(page, sort=sort)
        catalog = self._catalog()
        rank_map, added_map = self._rankings()
        hits = [
            series
            for series in catalog
            if any(name.lower() == wanted for name in series.genres)
        ]
        listing = paginate(order_catalog(hits, rank_map, added_map, sort), page)
        self._log(
            "genre",
            "/browse.json",
            status="ok",
            detail=f"genre={genre!r} page={page} count={len(listing.items)} total={listing.total}",
        )
        return listing

    # ------------------------------------------------------------------
    # series detail + chapters (one shared fetch)
    # ------------------------------------------------------------------

    def _fetch_series(self, series_id: str) -> tuple[Series | None, list[Chapter]]:
        key = normalize_series_key(series_id)
        if not key:
            return None, []
        cached = self._series_cache.get(key)
        if cached is not None:
            return cached

        payload = self._fetch_data(lambda build_id: series_data_path(build_id, key))
        if payload is None:
            return None, []
        series = parse_series_detail(payload, key)
        chapters = parse_chapters(payload, key)
        if series is not None:
            # Cached as one entry: get_series then get_chapters -- what a
            # series open always does -- must not fetch this payload twice.
            self._series_cache.set(key, (series, chapters))
        self._log(
            "detail",
            f"/series/{key}",
            status="ok" if series else "error",
            detail=f"chapters={len(chapters)}",
        )
        return series, chapters

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_series(series_id)[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._fetch_series(series_id)[1]

    # ------------------------------------------------------------------
    # chapter pages
    # ------------------------------------------------------------------

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        split = split_chapter_key(chapter_id)
        if split is None:
            self._log("pages", f"/{chapter_id}", status="error", detail="bad chapter key")
            return []
        series_key, token = split
        cache_key = make_chapter_key(series_key, token)
        cached = self._pages_cache.get(cache_key)
        if cached is not None:
            return cached

        payload = self._fetch_data(
            lambda build_id: chapter_data_path(build_id, series_key, token)
        )
        if payload is None:
            return []
        pages = parse_chapter_pages(payload, cache_key)
        if pages:
            self._pages_cache.set(cache_key, pages)
        self._log(
            "pages",
            f"/series/{series_key}/{token}",
            status="ok",
            detail=f"count={len(pages)}",
        )
        return pages

    def find_page(self, page_id: str) -> Page | None:
        """Resolve one page by id.

        The chapter key is embedded in the page id, so this is a single cached
        manifest lookup -- never a walk over the catalog.
        """
        chapter_key = page_id_chapter_key(page_id)
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
