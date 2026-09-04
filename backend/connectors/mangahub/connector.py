"""MangaHub online source connector (GraphQL).

Probed from the VPS (production egress and TLS, 2026-09-04): mangahub.io and
its API host ``api.mghcdn.com`` both answer 200 with plain httpx -- no
Cloudflare interstitial, no impersonation client needed. ``robots.txt`` is
``User-agent: * / Disallow:`` (empty), so nothing here is disallowed.

Every stage is a single GraphQL request, which is the whole reason this source
is worth having:

============================  ========================  ===================
stage                         query                     requests
============================  ========================  ===================
browse / search               ``search``                1 (+ exact ``count``)
genre browse                  ``genreManga``            1
series detail                 ``manga``                 1, shared with...
chapter list                  ``manga`` (same response) ...0
chapter pages (any length)    ``chapter``               1
============================  ========================  ===================

``manga`` returns metadata *and* the full chapter list in one response, so the
detail + chapter-list pair that costs two page fetches on an HTML source costs
one request here (the royalroad pattern: parse once, cache the pair, serve both
accessors from it). Page images resolve from a single ``pages`` payload, so a
33-image chapter is still one request.

The one wrinkle is access control. ``search``/``manga``/``genres`` need only a
browser ``User-Agent`` plus ``Origin: https://mangahub.io`` -- without the
Origin the router 404s, without the UA Cloudflare interstitials. ``chapter``
additionally needs an ``x-mhub-access`` nonce. On the site that nonce is the
``mhub_access`` cookie, minted fresh by every SSR page view and worth exactly
four ``chapter`` calls before it is spent for good (measured: still refused
after 130s, so it is a hard budget, not a rolling window). Re-fetching it from
the site does NOT help from a server: mangahub.io hands this egress IP the same
cached nonce every time, so once burnt it stays burnt -- a bootstrap-based
connector would stop serving pages after four chapters, permanently. The nonce
is not a credential (unsigned, identity-free, and any 32-hex value is accepted
identically), so the connector mints its own and spends each one to the same
four-call budget a browser gets. Net traffic is strictly below a real reader's:
one API call per chapter opened, and no HTML page view alongside it.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.mangahub.mappers import (
    API_BASE,
    BROWSE_MODES,
    GRAPHQL_PATH,
    PAGE_SIZE,
    SITE_BASE,
    chapter_query,
    genre_manga_query,
    genres_query,
    graphql_errors,
    is_rate_limited,
    make_chapter_key,
    manga_query,
    normalize_series_key,
    normalize_sort,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_genre_series_list,
    parse_genres,
    parse_series_detail,
    parse_series_list,
    search_query,
    split_chapter_key,
)
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

#: Without ``Origin`` the API router answers "Cannot GET /graphql"; without a
#: browser UA Cloudflare serves its interstitial. Both are mandatory.
API_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": SITE_BASE,
    "Referer": f"{SITE_BASE}/",
}

#: ``chapter`` calls one access nonce is worth before the API refuses it.
TOKEN_CHAPTER_BUDGET = 4


class MangaHubConnector(SourceConnector):
    """Browse and read manga, manhwa and manhua from MangaHub."""

    SOURCE_TYPE = "mangahub"
    DISPLAY_NAME = "MangaHub"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from MangaHub. Backed by "
        "MangaHub's GraphQL API, so listings, chapter lists and page images "
        "each resolve in a single request."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False

    def __init__(self) -> None:
        self._http = self._build_client()
        # ``chapter`` needs a rotating access header and SyncConnectorHttpClient
        # fixes its headers at construction, so the gated query gets its own
        # client that is rebuilt when its nonce is spent. Metadata traffic --
        # the hot path while browsing -- keeps one pooled connection untouched.
        self._chapter_http: SyncConnectorHttpClient | None = None
        self._chapter_budget = 0
        self._token_lock = threading.Lock()

        # One ``manga`` response carries BOTH the series metadata and the full
        # chapter list, so get_series/get_chapters share a single fetch.
        self._detail_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)
        self._genre_cache: TTLCache[list[BrowseMode]] = TTLCache(ttl_seconds=3600.0)

    @staticmethod
    def _build_client(extra_headers: dict[str, str] | None = None) -> SyncConnectorHttpClient:
        headers = dict(API_HEADERS)
        if extra_headers:
            headers.update(extra_headers)
        return SyncConnectorHttpClient(
            API_BASE,
            user_agent=BROWSER_USER_AGENT,
            headers=headers,
        )

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
        # Page images come from imgx.mghcdn.com and covers from
        # thumb.mghcdn.com; allowlisting the registrable domain covers both
        # (host_matches_allowlist does suffix matching on a dot boundary) and
        # nothing else -- mangahub.io itself serves no artwork.
        return frozenset({"mghcdn.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        # Measured from the VPS: the CDN serves these without a Referer, but
        # send the site's own headers so a future hotlink rule does not break
        # every image at once.
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return list(BROWSE_MODES)

    def list_genres(self) -> list[BrowseMode]:
        cached = self._genre_cache.get("genres")
        if cached is not None:
            return cached
        try:
            payload = self._query(genres_query())
        except ConnectorHttpError as exc:
            logger.warning("MangaHub genres failed: %s", exc)
            return []
        genres = parse_genres(payload)
        if genres:
            self._genre_cache.set("genres", genres)
        return genres

    # --- GraphQL plumbing ---------------------------------------------------

    def _query(self, query: str) -> dict[str, Any]:
        """Run an ungated GraphQL query (search / manga / genres)."""
        return self._http.get_json(GRAPHQL_PATH, params={"query": query})

    def _rotate_chapter_client(self) -> SyncConnectorHttpClient:
        """Replace the chapter client with one carrying a fresh access nonce."""
        previous = self._chapter_http
        client = self._build_client({"x-mhub-access": secrets.token_hex(16)})
        self._chapter_http = client
        self._chapter_budget = TOKEN_CHAPTER_BUDGET
        if previous is not None:
            try:
                previous.close()
            except Exception:  # pragma: no cover - close is best effort
                logger.debug("MangaHub: closing the spent chapter client failed.")
        return client

    def _take_chapter_client(self) -> SyncConnectorHttpClient:
        with self._token_lock:
            client = self._chapter_http
            if client is None or self._chapter_budget <= 0:
                client = self._rotate_chapter_client()
            # Decrement for THIS call too, so one nonce serves exactly
            # TOKEN_CHAPTER_BUDGET requests -- not one more.
            self._chapter_budget -= 1
            return client

    def _burn_chapter_client(self, client: SyncConnectorHttpClient) -> None:
        """Mark the nonce spent after the API rejected it as over budget."""
        with self._token_lock:
            if self._chapter_http is client:
                self._chapter_budget = 0

    def _query_chapter(self, query: str) -> dict[str, Any]:
        """Run the gated ``chapter`` query, rotating a spent nonce once.

        The API answers HTTP 200 for a refusal, so the retry decision is made
        on the body: exactly one extra attempt with a fresh nonce, never a
        loop -- a persistent refusal must surface, not spin.
        """
        client = self._take_chapter_client()
        payload = client.get_json(GRAPHQL_PATH, params={"query": query})
        if not is_rate_limited(payload):
            return payload
        logger.info("MangaHub access nonce spent; rotating and retrying once.")
        self._burn_chapter_client(client)
        retry_client = self._take_chapter_client()
        return retry_client.get_json(GRAPHQL_PATH, params={"query": query})

    def _normalize_series_key(self, value: str) -> str:
        return normalize_series_key(fully_unquote(value))

    # --- browse / search ----------------------------------------------------

    def _listing(
        self,
        query: str,
        page: int,
        *,
        operation: str,
        genre: bool = False,
        detail: str = "",
    ) -> PaginatedSeriesList:
        try:
            payload = self._query(query)
        except ConnectorHttpError as exc:
            logger.warning("MangaHub %s failed: %s", operation, exc)
            raise
        errors = graphql_errors(payload)
        parser = parse_genre_series_list if genre else parse_series_list
        listing = parser(payload, page=page, page_size=PAGE_SIZE)
        logger.info(
            "MangaHub %s page=%d count=%d total=%d has_more=%s%s%s",
            operation,
            page,
            len(listing.items),
            listing.total,
            listing.has_more,
            f" {detail}" if detail else "",
            f" errors={errors}" if errors else "",
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        mod = normalize_sort(sort)
        query = search_query(
            "", limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, mod=mod
        )
        return self._listing(query, page, operation="browse", detail=f"mod={mod}")

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        mod = normalize_sort(sort)
        gql = search_query(
            normalized, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, mod=mod
        )
        return self._listing(
            gql, page, operation="search", detail=f"query={normalized!r}"
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
        slug = genre.strip().strip("/")
        if not slug:
            return self.get_series_list(page, sort=sort)
        gql = genre_manga_query(
            slug,
            limit=PAGE_SIZE,
            offset=(page - 1) * PAGE_SIZE,
            mod=normalize_sort(sort),
        )
        return self._listing(
            gql, page, operation="genre", genre=True, detail=f"genre={slug!r}"
        )

    # --- detail / chapters --------------------------------------------------

    def _fetch_detail(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        """One ``manga`` request serving both get_series and get_chapters."""
        key = self._normalize_series_key(series_key)
        if not key:
            return None, []
        cached = self._detail_cache.get(key)
        if cached is not None:
            return cached
        try:
            payload = self._query(manga_query(key))
        except ConnectorHttpError as exc:
            logger.warning("MangaHub detail %s failed: %s", key, exc)
            return None, []
        series = parse_series_detail(payload, key)
        if series is None:
            # A missing slug arrives as HTTP 200 with data.manga = null and an
            # errors array; there is no 404 to key off.
            logger.info(
                "MangaHub detail %s not found (errors=%s)", key, graphql_errors(payload)
            )
            return None, []
        chapters = parse_chapters(payload, series.id)
        parsed = (series, chapters)
        self._detail_cache.set(key, parsed)
        if series.id != key:
            self._detail_cache.set(series.id, parsed)
        logger.info("MangaHub detail %s ok chapters=%d", key, len(chapters))
        return parsed

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_detail(series_id)[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        chapters = self._fetch_detail(series_id)[1]
        if not chapters:
            return []
        # Backfill page counts already learned from get_chapter_pages so the
        # list does not re-report 0 for chapters the reader has opened.
        enriched: list[Chapter] = []
        for chapter in chapters:
            count = self._page_count_cache.get(chapter.id)
            enriched.append(
                replace(chapter, page_count=count) if count else chapter
            )
        return enriched

    # --- pages --------------------------------------------------------------

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = fully_unquote(chapter_id).strip()
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached
        parts = split_chapter_key(chapter_key)
        if parts is None:
            logger.warning("MangaHub pages: unusable chapter key %r", chapter_id)
            return []
        series_key, number = parts
        # Rebuild the key canonically so the ids on the Page objects match what
        # find_page will be handed back, whatever form the caller passed in.
        canonical_key = make_chapter_key(series_key, number)
        try:
            payload = self._query_chapter(chapter_query(series_key, number))
        except ConnectorHttpError as exc:
            logger.warning("MangaHub pages %s failed: %s", canonical_key, exc)
            return []
        pages = parse_chapter_pages(payload, canonical_key)
        if not pages:
            logger.info(
                "MangaHub pages %s empty (errors=%s)",
                canonical_key,
                graphql_errors(payload),
            )
            return []
        self._page_cache.set(canonical_key, pages)
        if canonical_key != chapter_key:
            self._page_cache.set(chapter_key, pages)
        self._page_count_cache.set(canonical_key, len(pages))
        logger.info("MangaHub pages %s ok count=%d", canonical_key, len(pages))
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_key = page_id_chapter_key(fully_unquote(page_id).strip())
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
