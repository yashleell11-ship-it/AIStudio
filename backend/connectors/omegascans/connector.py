"""Omega Scans online source connector (Heancms JSON API).

Omega Scans is an adult manhwa scanlation group. Its Next.js front end is a
thin client over a public Heancms JSON API, so this connector never parses
HTML -- see ``connectors/omegascans/mappers.py`` for the endpoint map.

Request budget per stage (measured from the production VPS, see the module
tests and the connector report):

* browse / search        1 request
* series detail          1 request
* chapter list           1 request  (the WHOLE list, up to 500 chapters)
* chapter page images    1 request  (every image URL, no per-page cost)

The chapter list needs the series' NUMERIC id, which the slug-keyed detail
endpoint carries and the chapter endpoint demands. Rather than fetch the
detail page twice (the anti-pattern this repo already fixed on royalroad),
one TTL cache holds the parsed detail plus that id, and every browse/search
response pre-seeds the id map -- so opening a series reached from the catalog
costs one detail request and one chapter request, never three.
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
from connectors.omegascans.mappers import (
    API_BASE,
    BROWSE_MODES,
    PAGE_SIZE,
    SITE_BASE,
    chapter_key_series,
    chapter_list_last_page,
    chapter_list_params,
    chapter_path,
    listing_params,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    parse_tags,
    series_numeric_ids,
    series_path,
)

logger = logging.getLogger(__name__)

#: The API answered every endpoint from the VPS under the default connector
#: User-Agent with no challenge, but it is a browser API: sending the site's
#: own Origin/Referer is what a real client does and costs nothing.
API_HEADERS = {
    "Accept": "application/json",
    "Origin": SITE_BASE,
    "Referer": f"{SITE_BASE}/",
}

#: Ceiling on the defensive chapter-list paging loop. With
#: ``CHAPTER_FETCH_SIZE = 500`` the largest series in the catalog (270
#: chapters) already comes back as ``last_page == 1``, so this never engages;
#: it exists so a future 600-chapter series degrades to two requests instead
#: of silently losing chapters.
MAX_CHAPTER_PAGES = 4


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses; a 404 otherwise surfaces only as httpx's ``raise_for_status``
    message, so match both forms. Verified from the VPS: a missing series
    (``/series/no-such-series-xyz``) and a missing chapter both answer a real
    404 with ``{"message": "Row not found"}``.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class OmegaScansConnector(SourceConnector):
    """Browse and read manhwa from Omega Scans."""

    SOURCE_TYPE = "omegascans"
    DISPLAY_NAME = "Omega Scans"
    DESCRIPTION = (
        "Browse and read adult manhwa from the Omega Scans scanlation group. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    #: Omega Scans is an 18+ scanlation group -- its entire catalog is adult.
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(API_BASE, headers=dict(API_HEADERS))
        # Detail responses are tiny (1.4 KB) but every series open needs one,
        # and get_chapters needs the numeric id it carries.
        self._detail_cache: TTLCache[tuple[Series | None, int | None]] = TTLCache(ttl_seconds=300.0)
        # slug -> numeric id, seeded for free by every listing/search page.
        self._series_id_cache: TTLCache[int] = TTLCache(ttl_seconds=1800.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
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
        # Covers and page images both live on media.omegascans.org, a
        # subdomain of the site's own registrable domain (suffix matching in
        # host_matches_allowlist makes the one entry cover both).
        return frozenset({"omegascans.org"})

    def image_fetch_headers(self) -> dict[str, str]:
        # media.omegascans.org served bytes without a Referer from the VPS;
        # sending one anyway is free and survives them enabling hotlink
        # protection later.
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return list(BROWSE_MODES)

    def list_genres(self) -> list[BrowseMode]:
        cached = self._genre_cache.get("genres")
        if cached is not None:
            return cached
        try:
            payload = self._http.get_json_value("/tags")
        except ConnectorHttpError as exc:
            logger.info("Omega Scans genres failed: %s", exc)
            return []
        modes = parse_tags(payload)
        if modes:
            self._genre_cache.set("genres", modes)
        return modes

    # ------------------------------------------------------------------
    # key handling -- keys are OPAQUE; only percent-decoding and the
    # canonical-path prefix are ever stripped, never parsed for meaning.
    # ------------------------------------------------------------------

    def _normalize_series_key(self, value: str) -> str:
        cleaned = fully_unquote(value).strip().strip("/")
        # Tolerate a caller handing back Series.canonical_path ("/series/x").
        if cleaned.startswith("series/"):
            cleaned = cleaned[len("series/"):]
        return cleaned

    def _normalize_chapter_key(self, value: str) -> str:
        cleaned = fully_unquote(value).strip().strip("/")
        if cleaned.startswith("chapter/"):
            cleaned = cleaned[len("chapter/"):]
        return cleaned

    # ------------------------------------------------------------------
    # listing
    # ------------------------------------------------------------------

    def _remember_ids(self, mapping: dict[str, int]) -> None:
        for slug, numeric_id in mapping.items():
            self._series_id_cache.set(slug, numeric_id)

    def _fetch_listing(
        self,
        page: int,
        *,
        sort: str | None = None,
        query: str = "",
        tag_id: str | None = None,
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        params = listing_params(page=page, sort=sort, query=query, tag_id=tag_id)
        try:
            payload = self._http.get_json("/query", params=params)
        except ConnectorHttpError as exc:
            logger.info(
                "Omega Scans listing failed page=%d sort=%r query=%r genre=%r: %s",
                page, sort, query, tag_id, exc,
            )
            raise
        # Free side effect: every listing item carries the numeric series id
        # that /chapter/query requires.
        self._remember_ids(series_numeric_ids(payload))
        listing = parse_series_list(payload, page=page)
        logger.info(
            "Omega Scans listing page=%d sort=%r query=%r genre=%r count=%d has_more=%s",
            page, sort, query, tag_id, len(listing.items), listing.has_more,
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._fetch_listing(page, sort=sort)

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        tag_id = str(genre).strip()
        if not tag_id.isdigit():
            # list_genres() hands out numeric tag ids; anything else would be
            # interpolated into the API's tags_ids array unfiltered.
            return self.get_series_list(page, sort=sort)
        return self._fetch_listing(page, sort=sort, tag_id=tag_id)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._fetch_listing(page, sort=sort, query=normalized)

    # ------------------------------------------------------------------
    # detail + chapters
    # ------------------------------------------------------------------

    def _fetch_detail(self, series_key: str) -> tuple[Series | None, int | None]:
        cached = self._detail_cache.get(series_key)
        if cached is not None:
            return cached

        path = series_path(series_key)
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                logger.info("Omega Scans detail %s: not found", path)
                self._detail_cache.set(series_key, (None, None))
                return None, None
            logger.info("Omega Scans detail %s failed: %s", path, exc)
            return None, None

        parsed = parse_series_detail(payload, series_key)
        series, numeric_id = parsed
        if series is not None:
            self._detail_cache.set(series_key, parsed)
        if numeric_id is not None:
            self._series_id_cache.set(series_key, numeric_id)
        return parsed

    def get_series(self, series_id: str) -> Series | None:
        series_key = self._normalize_series_key(series_id)
        if not series_key:
            return None
        series, _numeric_id = self._fetch_detail(series_key)
        if series is None:
            return None

        # Only decorate from state we already hold -- never fetch the chapter
        # list just to fill a label.
        chapters = self._chapter_list_cache.get(series_key)
        if chapters:
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=chapters[-1].title,
            )
        return series

    def _series_numeric_id(self, series_key: str) -> int | None:
        cached = self._series_id_cache.get(series_key)
        if cached is not None:
            return cached
        return self._fetch_detail(series_key)[1]

    def _fetch_chapter_payloads(self, numeric_id: int) -> list[dict[str, Any]]:
        first = self._http.get_json("/chapter/query", params=chapter_list_params(numeric_id))
        payloads = [first]
        last_page = min(chapter_list_last_page(first), MAX_CHAPTER_PAGES)
        for page in range(2, last_page + 1):
            payloads.append(
                self._http.get_json(
                    "/chapter/query", params=chapter_list_params(numeric_id, page=page)
                )
            )
        return payloads

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached_count = self._page_count_cache.get(chapter.id)
            if cached_count:
                enriched.append(replace(chapter, page_count=cached_count))
            else:
                enriched.append(chapter)
        return enriched

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_key = self._normalize_series_key(series_id)
        if not series_key:
            return []
        cached = self._chapter_list_cache.get(series_key)
        if cached is not None:
            return self._enrich_chapters(cached)

        numeric_id = self._series_numeric_id(series_key)
        if numeric_id is None:
            logger.info("Omega Scans chapters %s: no numeric series id", series_key)
            return []

        try:
            payloads = self._fetch_chapter_payloads(numeric_id)
        except ConnectorHttpError as exc:
            logger.info("Omega Scans chapters %s failed: %s", series_key, exc)
            return []

        chapters = parse_chapters(payloads, series_key)
        if chapters:
            self._chapter_list_cache.set(series_key, chapters)
        logger.info("Omega Scans chapters %s count=%d", series_key, len(chapters))
        return self._enrich_chapters(chapters)

    # ------------------------------------------------------------------
    # pages
    # ------------------------------------------------------------------

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = self._normalize_chapter_key(chapter_id)
        if not chapter_key or chapter_key_series(chapter_key) is None:
            return []
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_path(chapter_key)
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                logger.info("Omega Scans pages %s: not found", path)
            else:
                logger.info("Omega Scans pages %s failed: %s", path, exc)
            return []

        if payload.get("paywall"):
            # Early-access chapter: readable only by a paying account. The
            # chapter list already filters price > 0, so this is the race
            # where a chapter went paid between the two calls.
            logger.info("Omega Scans pages %s: paywalled", path)
            return []

        pages = parse_chapter_pages(payload, chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._page_count_cache.set(chapter_key, len(pages))
        logger.info("Omega Scans pages %s count=%d", path, len(pages))
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_key = page_id_chapter_id(self._normalize_chapter_key(page_id))
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
