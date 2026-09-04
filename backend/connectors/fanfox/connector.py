"""Manga Fox (fanfox.net) online source connector.

Verified end to end from the VPS on 2026-09-04 — listing, search, series
detail, chapter list and real page-image bytes — through production's egress.
Fanfox answers the plain ManhwaManiacs user agent on every stage, so this uses
the shared httpx client with no impersonation.
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.fanfox.mappers import (
    GENRE_SLUGS,
    IMAGE_HOSTS,
    PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    SITE_BASE,
    SORT_TO_FLAG,
    chapter_path,
    chapterfun_path,
    listing_path,
    make_page_id,
    normalize_chapter_key,
    normalize_series_key,
    normalize_sort,
    page_id_chapter_key,
    pages_from_urls,
    parse_chapter_ident,
    parse_chapterfun,
    parse_chapters,
    parse_embedded_image_urls,
    parse_guidkey,
    parse_image_count,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_params,
    search_path,
    series_path,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

#: The ``Referer`` is load-bearing, not politeness. Once the client is holding
#: fanfox's own session cookies (which it is from the first page fetch), a
#: ``chapterfun.ashx`` request WITHOUT a referer is answered ``200`` with an
#: EMPTY BODY rather than an error — a mode-B chapter silently reads as zero
#: pages. Verified from the VPS: cookies + no referer -> 0 bytes; cookies +
#: referer -> 783 bytes. A site-root value satisfies it (the exact chapter URL
#: is not required), so it can live in the client's default headers.
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}

#: How many ``chapterfun.ashx`` calls run at once for a mode-B chapter. Each
#: response carries two pages, so a 40-page chapter needs 20 calls; issuing
#: them eight at a time keeps the reader's first paint under a second while
#: leaving the long-run request rate to the client's token bucket.
_PAGE_WORKERS = 8

#: A ``chapterfun.ashx`` response returns the requested page AND the next one.
_PAGES_PER_CHAPTERFUN = 2

#: Fanfox's image CDN rejects a request with no ``Referer`` (verified: 403
#: without, 200 with). A site-root referer is enough — it does not check the
#: exact chapter URL — so the proxy can send one static header.
_IMAGE_REFERER = f"{SITE_BASE}/"


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS, so a
    404 arrives as httpx's ``raise_for_status`` text instead. Both forms are
    matched — checking ``status_code`` alone would be dead code. Verified from
    the VPS: a missing chapter answers a real 404.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class FanFoxConnector(SourceConnector):
    """Browse and read manga from Manga Fox."""

    SOURCE_TYPE = "fanfox"
    DISPLAY_NAME = "Manga Fox"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from Manga Fox (fanfox.net), "
        "a long-established catalog of roughly ten thousand series. Images are "
        "proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            # Mode-B chapters fan out _PAGE_WORKERS chapterfun calls at once
            # (see _resolve_pages). Without a matching burst the rate limiter
            # spaces them 0.21s apart and the fan-out buys nothing.
            burst=_PAGE_WORKERS,
            extra_redirect_hosts=frozenset({"fanfox.net", "m.fanfox.net"}),
        )
        # Fanfox hides the chapter table of ecchi/mature-tagged titles behind a
        # self-declared age gate. Those titles are still listed in the ordinary
        # /directory/ catalog, so without this cookie the connector shows the
        # reader series it then reports as having ZERO chapters — a listed but
        # unopenable title, which reads as a connector bug rather than a gate.
        # Verified from the VPS: isekai_meikyuu_de_harem_o returns 0 chapters
        # without it and 117 with it, and its pages then serve real bytes.
        # (Source-level adult gating remains the app's own MATURE/mature_content
        # mechanism; this only stops fanfox from truncating its own catalog.)
        self._http._client.cookies.set(  # noqa: SLF001
            "isAdult", "1", domain=".fanfox.net"
        )

        # One series fetch feeds BOTH get_series and get_chapters: fanfox
        # renders the whole chapter table inside the detail page, so caching
        # the raw HTML is what stops a series open from downloading that same
        # 120KB document twice.
        self._series_html_cache: TTLCache[str] = TTLCache(ttl_seconds=180.0)
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        # Page URLs carry a signed ``ttl`` roughly a day out; a 10-minute cache
        # stays comfortably inside that while covering a reading session.
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)

    # --- descriptors --------------------------------------------------------

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
        # fmcdn.mfcdn.net -> cover art; zjcdn.mangafox.me -> page images.
        return IMAGE_HOSTS

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": _IMAGE_REFERER}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Browse"),
            BrowseMode(id="latest", label="Latest Updates"),
            BrowseMode(id="news", label="New Series"),
            BrowseMode(id="rating", label="Top Rated"),
            BrowseMode(id="az", label="A-Z"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=slug, label=label) for slug, label in GENRE_SLUGS]

    # --- logging ------------------------------------------------------------

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
            f"FanFox {operation} {SITE_BASE}{path} params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    # --- browse / search ----------------------------------------------------

    def _browse(
        self, page: int, *, genre: str | None, sort: str | None
    ) -> PaginatedSeriesList:
        page = max(1, page)
        path = listing_path(page, genre=genre, sort=sort)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("browse", path, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._log(
            "browse",
            path,
            status="ok",
            detail=(
                f"page={page} genre={genre!r} sort={normalize_sort(sort)!r} "
                f"count={len(listing.items)} has_more={listing.has_more}"
            ),
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._browse(page, genre=None, sort=sort)

    def browse_by_genre(
        self, genre: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        return self._browse(page, genre=genre, sort=sort)

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        page = max(1, page)
        normalized = (query or "").strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        path = search_path()
        params = search_params(normalized, page)
        try:
            html = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log("search", path, params=params, status="error", detail=str(exc))
            raise
        listing = parse_search_results(html, page=page, page_size=SEARCH_PAGE_SIZE)
        self._log(
            "search",
            path,
            params=params,
            status="ok",
            detail=f"query={normalized!r} count={len(listing.items)} has_more={listing.has_more}",
        )
        return listing

    # --- series detail + chapters (one shared fetch) ------------------------

    def _series_html(self, series_key: str) -> str | None:
        cached = self._series_html_cache.get(series_key)
        if cached is not None:
            return cached
        path = series_path(series_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("detail", path, status="error", detail=str(exc))
            return None
        self._series_html_cache.set(series_key, html)
        return html

    def get_series(self, series_id: str) -> Series | None:
        series_key = normalize_series_key(series_id)
        if not series_key:
            return None
        cached = self._series_cache.get(series_key)
        if cached is not None:
            return cached

        html = self._series_html(series_key)
        if html is None:
            return None
        series = parse_series_detail(html, series_key)
        if series is None:
            # Fanfox answers an unknown slug with its search page under HTTP
            # 200 rather than a 404, so a failed parse is the real signal.
            self._log("detail", series_path(series_key), status="error", detail="not found")
            return None

        chapters = parse_chapters(html, series_key)
        if chapters:
            self._chapter_list_cache.set(series_key, chapters)
            series = replace(
                series,
                chapter_count=len(chapters),
                latest_chapter=chapters[-1].title,
            )
        self._series_cache.set(series_key, series)
        self._log(
            "detail",
            series_path(series_key),
            status="ok",
            detail=f"chapters={series.chapter_count}",
        )
        return series

    def _enrich(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill in page counts already learned by reading a chapter."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            count = self._page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=count) if count else chapter)
        return enriched

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_key = normalize_series_key(series_id)
        if not series_key:
            return []
        cached = self._chapter_list_cache.get(series_key)
        if cached is not None:
            return self._enrich(cached)

        html = self._series_html(series_key)
        if html is None:
            return []
        chapters = parse_chapters(html, series_key)
        if chapters:
            self._chapter_list_cache.set(series_key, chapters)
        self._log(
            "chapters", series_path(series_key), status="ok", detail=f"count={len(chapters)}"
        )
        return self._enrich(chapters)

    # --- reader -------------------------------------------------------------

    def _fetch_chapterfun(
        self, chapter_key: str, chapter_id: str, guidkey: str, page: int
    ) -> list[str]:
        params: dict[str, Any] = {"cid": chapter_id, "page": page, "key": guidkey}
        try:
            body = self._http.get_text(chapterfun_path(chapter_key), params=params)
        except ConnectorHttpError as exc:
            self._log(
                "pages", chapterfun_path(chapter_key), params=params, status="error", detail=str(exc)
            )
            return []
        return parse_chapterfun(body)

    def _resolve_mode_b(
        self, chapter_key: str, document: str, count: int
    ) -> list[str]:
        """Resolve page images through the guidkey handshake.

        Newer chapters keep their image URLs out of the markup: the page ships
        a ``guidkey`` and the reader asks ``chapterfun.ashx`` for them. Each
        response covers two pages, so the requests are issued for every other
        page number and run concurrently — serially this is the "one request
        per page" shape that makes a chapter open feel slow.
        """
        chapter_id, _comic_id = parse_chapter_ident(document)
        guidkey = parse_guidkey(document)
        if not chapter_id or not guidkey or count <= 0:
            return []

        wanted = list(range(1, count + 1, _PAGES_PER_CHAPTERFUN))
        resolved: dict[int, str] = {}
        with cf.ThreadPoolExecutor(
            max_workers=min(_PAGE_WORKERS, len(wanted)),
            thread_name_prefix="fanfox-pages",
        ) as executor:
            futures = {
                executor.submit(
                    self._fetch_chapterfun, chapter_key, chapter_id, guidkey, start
                ): start
                for start in wanted
            }
            for future in cf.as_completed(futures):
                start = futures[future]
                try:
                    urls = future.result()
                except ConnectorHttpError:
                    continue
                for offset, url in enumerate(urls):
                    number = start + offset
                    if 1 <= number <= count:
                        resolved.setdefault(number, url)

        # A gap means one call failed; stop at the first hole rather than
        # handing the reader a chapter with a page silently missing.
        ordered: list[str] = []
        for number in range(1, count + 1):
            url = resolved.get(number)
            if url is None:
                break
            ordered.append(url)
        return ordered

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = normalize_chapter_key(chapter_id)
        if not chapter_key:
            return []
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_path(chapter_key)
        try:
            document = self._http.get_text(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                self._log("pages", path, status="error", detail="404")
                return []
            self._log("pages", path, status="error", detail=str(exc))
            return []

        count = parse_image_count(document)
        # Mode A: older chapters embed every URL, so the page we just fetched
        # already holds the whole chapter — no further request at all.
        urls = parse_embedded_image_urls(document)
        mode = "embedded"
        if urls:
            if count and len(urls) > count:
                urls = urls[:count]
        else:
            mode = "chapterfun"
            urls = self._resolve_mode_b(chapter_key, document, count)

        if not urls:
            self._log("pages", path, status="error", detail=f"no images (mode={mode})")
            return []

        pages = pages_from_urls(chapter_key, urls)
        self._page_cache.set(chapter_key, pages)
        self._page_count_cache.set(chapter_key, len(pages))
        self._log(
            "pages",
            path,
            status="ok",
            detail=f"mode={mode} count={len(pages)} imagecount={count}",
        )
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_key = page_id_chapter_key(page_id)
        if chapter_key is None:
            return None
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
