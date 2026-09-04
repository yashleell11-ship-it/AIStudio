"""MangaHere online source connector.

MangaHere (mangahere.cc) is a very large, long-established catalog -- roughly
ten thousand series across 143 directory pages -- running the old "dm5" engine
rather than Madara or a JSON API. Everything below was mapped and timed
against the production VPS; the parsing rules and their justifications live in
``connectors/mangahere/mappers.py``.

Three things drive the shape of this file:

* **One fetch per series.** The detail document already contains the entire
  chapter list, so ``get_series`` and ``get_chapters`` share a single cached
  HTML fetch instead of downloading the same ~120KB page twice.
* **Two page-resolution modes.** Long-strip chapters embed every image URL in
  the reader document (1 request). Classic manga hide them behind
  ``chapterfun.ashx``, which returns only two images per call -- so those
  calls are fanned out across a thread pool, with the HTTP client's token
  bucket given a matching burst so the fan-out is not immediately
  re-serialized by the rate limiter.
* **Taken-down titles are real.** MangaHere honours copyright claims by
  replacing a series or chapter with a notice while leaving it in the
  catalog. Those are detected and reported as "no pages" rather than served
  as the site's warning graphic.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.mangahere.mappers import (
    GENRE_SLUGS,
    PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    SITE_BASE,
    build_pages,
    chapter_path,
    chapterfun_path,
    drop_last_advert,
    extract_chapterfun_context,
    extract_inline_page_urls,
    is_age_gated,
    is_removed,
    is_valid_genre,
    listing_path,
    normalize_chapter_key,
    normalize_series_key,
    normalize_sort,
    page_id_chapter_key,
    parse_chapters,
    parse_chapterfun_response,
    parse_image_info,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_path,
    series_path,
)
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

#: How many ``chapterfun.ashx`` calls a classic chapter issues at once. A
#: 55-image chapter needs 28 of them; serially (0.21s apart) that is a
#: five-second stall before the first page renders.
_PAGE_WORKERS = 8

#: One ``chapterfun.ashx`` reply covers the requested page AND the next one,
#: so only every other page number has to be asked for.
_PAGES_PER_CHAPTERFUN = 2

#: How many times the chapterfun fan-out is attempted. The endpoint answers
#: an empty 200 rather than an error when it is refusing, so the shared
#: client's own retry loop never sees a failure to retry.
_CHAPTERFUN_ATTEMPTS = 2

#: Backoff before re-asking for the pages a previous attempt did not resolve.
_CHAPTERFUN_RETRY_DELAY = 0.75

#: Consecutive blank replies that mean the endpoint is refusing this chapter
#: outright rather than dropping the odd request. When it refuses, it refuses
#: EVERY call (measured: 0/28 across serial, paced-serial and parallel runs
#: of the same chapter), so the rest of the fan-out is cancelled instead of
#: spending four more seconds learning the same answer.
_CHAPTERFUN_BLANK_ABORT = 3

#: MangaHere's CDNs refuse a request that carries no ``Referer`` -- verified
#: from the VPS: 403 with an HTML body without it, 200 with it, for BOTH the
#: cover host (fmcdn.mangahere.com) and the page-image host
#: (zjcdn.mangahere.org). The site root is enough; the exact chapter URL is
#: not checked, so the proxy can send one static header for every image.
_IMAGE_REFERER = f"{SITE_BASE}/"


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    ``SyncConnectorHttpClient`` only attaches ``status_code`` for
    RETRYABLE_STATUS, so a 404 reaches us as httpx's ``raise_for_status``
    message instead and a bare ``exc.status_code == 404`` test would be dead
    code. Both forms are checked. Verified from the VPS: a missing chapter
    answers a real 404 (a missing *series* instead 302s to the search page,
    which is handled by the detail parser returning ``None``).
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class MangaHereConnector(SourceConnector):
    """Browse and read manga from MangaHere."""

    SOURCE_TYPE = "mangahere"
    DISPLAY_NAME = "MangaHere"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from MangaHere, a large "
        "long-running catalog of roughly ten thousand series. Images are "
        "proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            # Classic chapters fan _PAGE_WORKERS chapterfun calls out at once
            # (see _resolve_via_chapterfun). Without a matching burst the
            # token bucket spaces them 0.21s apart and the fan-out buys
            # nothing; the long-run request rate is unchanged either way.
            burst=_PAGE_WORKERS,
        )
        # The detail document carries the whole chapter list, so caching the
        # RAW HTML is what stops one series open from downloading the same
        # ~120KB page twice (once for metadata, once for chapters).
        self._series_html_cache: TTLCache[str] = TTLCache(ttl_seconds=180.0)
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        # Page image URLs are unsigned paths on zjcdn (no expiring token), so
        # a 10-minute cache is safe and covers a whole reading session.
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
        # fmcdn.mangahere.com  -> cover art
        # zjcdn.mangahere.org  -> chapter page images
        # static.mangahere.cc  -> the site's own "no picture" placeholder,
        #                          which listing cards fall back to
        return frozenset({"mangahere.com", "mangahere.org", "mangahere.cc"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": _IMAGE_REFERER}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Popular"),
            BrowseMode(id="latest", label="Recently Updated"),
            BrowseMode(id="rating", label="Top Rated"),
            BrowseMode(id="chapters", label="Most Chapters"),
            BrowseMode(id="alphabetical", label="A-Z"),
            BrowseMode(id="completed", label="Completed"),
            BrowseMode(id="ongoing", label="Ongoing"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=slug, label=label) for slug, label in GENRE_SLUGS]

    # --- logging ------------------------------------------------------------

    def _log(
        self,
        operation: str,
        path: str,
        *,
        status: str,
        detail: str | None = None,
    ) -> None:
        message = f"MangaHere {operation} {SITE_BASE}{path} status={status}"
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    # --- browse -------------------------------------------------------------

    def _browse(
        self,
        page: int,
        *,
        sort: str | None,
        genre: str | None = None,
    ) -> PaginatedSeriesList:
        page = max(1, page)
        path = listing_path(page, sort=sort, genre=genre)
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
                f"page={page} sort={normalize_sort(sort)!r} genre={genre!r} "
                f"count={len(listing.items)} total={listing.total} "
                f"has_more={listing.has_more}"
            ),
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._browse(page, sort=sort)

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        slug = genre.strip().strip("/").lower()
        if not is_valid_genre(slug):
            raise NotImplementedError(f"MangaHere has no genre {genre!r}.")
        return self._browse(page, sort=sort, genre=slug)

    def search_series(
        self,
        query: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        page = max(1, page)
        path = search_path(normalized, page)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("search", path, status="error", detail=str(exc))
            raise
        listing = parse_search_results(html, page=page, page_size=SEARCH_PAGE_SIZE)
        self._log(
            "search",
            path,
            status="ok",
            detail=(
                f"query={normalized!r} page={page} count={len(listing.items)} "
                f"total={listing.total} has_more={listing.has_more}"
            ),
        )
        return listing

    # --- series detail ------------------------------------------------------

    def _series_html(self, series_key: str) -> str | None:
        """Fetch (or reuse) the detail document for ``series_key``.

        This is the single fetch that both ``get_series`` and
        ``get_chapters`` are built on -- MangaHere renders the complete
        chapter list inside the detail page, so a second request for it would
        be pure waste.
        """
        cached = self._series_html_cache.get(series_key)
        if cached is not None:
            return cached
        path = series_path(series_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            level = "not_found" if _is_not_found(exc) else "error"
            self._log("detail", path, status=level, detail=str(exc))
            return None
        self._series_html_cache.set(series_key, html)
        return html

    def _enrich(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            count = self._page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=count) if count else chapter)
        return enriched

    def get_series(self, series_id: str) -> Series | None:
        series_key = normalize_series_key(fully_unquote(series_id))
        cached = self._series_cache.get(series_key)
        if cached is not None:
            return cached

        html = self._series_html(series_key)
        if html is None:
            return None

        series = parse_series_detail(html, series_key)
        if series is None:
            # Either a copyright takedown notice, or the search page the site
            # 302s an unknown slug onto. Neither is a readable series.
            if is_removed(html):
                reason = "removed on copyright claim"
            elif is_age_gated(html):
                reason = "behind the site age gate"
            else:
                reason = "no detail block"
            self._log(
                "detail",
                series_path(series_key),
                status="unavailable",
                detail=reason,
            )
            return None

        chapters = self._chapter_list_cache.get(series_key)
        if chapters is None:
            chapters = parse_chapters(html, series_key)
            self._chapter_list_cache.set(series_key, chapters)
        if chapters:
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

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_key = normalize_series_key(fully_unquote(series_id))
        cached = self._chapter_list_cache.get(series_key)
        if cached is not None:
            return self._enrich(cached)

        html = self._series_html(series_key)
        if html is None:
            return []
        if is_removed(html) or is_age_gated(html):
            self._log(
                "chapters",
                series_path(series_key),
                status="unavailable",
                detail=(
                    "removed on copyright claim"
                    if is_removed(html)
                    else "behind the site age gate"
                ),
            )
            return []

        chapters = parse_chapters(html, series_key)
        self._chapter_list_cache.set(series_key, chapters)
        self._log(
            "chapters",
            series_path(series_key),
            status="ok",
            detail=f"count={len(chapters)}",
        )
        return self._enrich(chapters)

    # --- chapter pages ------------------------------------------------------

    def _resolve_via_chapterfun(
        self,
        chapter_key: str,
        chapter_numeric_id: str,
        guidkey: str,
        image_count: int,
    ) -> list[str]:
        """Resolve a classic chapter's images through ``chapterfun.ashx``.

        Each call answers with the requested page and the one after it, so
        only every second page number is asked for, and the calls -- being
        independent -- go out on a thread pool rather than one after another.

        The endpoint is NOT dependable from a datacentre IP. Measured from
        the production VPS it answers correctly for a while and then serves
        an empty ``200`` for every request for minutes at a time (0/18 over
        three minutes in one measured window, recovering later). That reply
        is indistinguishable from success at the HTTP layer, so it is caught
        here: missing pages are retried once after a backoff, and a chapter
        that STILL will not resolve completely returns nothing at all. A
        partial resolve must never be served -- pages are renumbered from 1,
        so a hole in the middle would silently renumber the rest of the
        chapter and show the reader the wrong page under the right number.
        """
        path = chapterfun_path(chapter_key)
        wanted = list(range(1, image_count + 1, _PAGES_PER_CHAPTERFUN))
        if not wanted:
            return []

        def fetch(page_number: int) -> tuple[int, list[str]]:
            try:
                script = self._http.get_text(
                    path,
                    params={
                        "cid": chapter_numeric_id,
                        "page": page_number,
                        "key": guidkey,
                    },
                )
            except ConnectorHttpError as exc:
                self._log("pages", path, status="error", detail=str(exc))
                return page_number, []
            return page_number, parse_chapterfun_response(script)

        def fan_out(numbers: list[int]) -> tuple[dict[int, str], bool]:
            """Fetch ``numbers`` in parallel; bail early on a flat refusal."""
            found: dict[int, str] = {}
            blanks = 0
            refused = False
            workers = min(_PAGE_WORKERS, len(numbers))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(fetch, number): number for number in numbers}
                for future in as_completed(futures):
                    page_number, urls = future.result()
                    if not urls:
                        blanks += 1
                        if not found and blanks >= _CHAPTERFUN_BLANK_ABORT:
                            refused = True
                            for pending in futures:
                                pending.cancel()
                            break
                        continue
                    for offset, url in enumerate(urls):
                        found.setdefault(page_number + offset, url)
            return found, refused

        resolved: dict[int, str] = {}
        outstanding = wanted
        for attempt in range(_CHAPTERFUN_ATTEMPTS):
            if attempt:
                time.sleep(_CHAPTERFUN_RETRY_DELAY * attempt)
            found, refused = fan_out(outstanding)
            resolved.update(found)
            if refused:
                # Nothing came back at all. Re-asking returns the identical
                # answer, so stop rather than pay for a second fan-out.
                self._log(
                    "pages",
                    path,
                    status="refused",
                    detail="chapterfun returned only blank replies",
                )
                return []
            outstanding = [
                number for number in wanted if number not in resolved
            ]
            if not outstanding:
                break

        if len(resolved) != image_count:
            self._log(
                "pages",
                path,
                status="incomplete",
                detail=(
                    f"resolved={len(resolved)} expected={image_count} -- "
                    "refusing to serve a chapter with holes"
                ),
            )
            return []

        ordered = [resolved[number] for number in sorted(resolved)]
        # The site counts its own advert as the final image of every classic
        # chapter (see mappers.drop_last_advert).
        return drop_last_advert(ordered)

    def _resolve_pages(self, chapter_key: str) -> list[Page]:
        path = chapter_path(chapter_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            level = "not_found" if _is_not_found(exc) else "error"
            self._log("pages", path, status=level, detail=str(exc))
            return []

        if is_removed(html):
            self._log(
                "pages", path, status="unavailable", detail="removed on copyright claim"
            )
            return []
        if is_age_gated(html):
            self._log(
                "pages", path, status="unavailable", detail="behind the site age gate"
            )
            return []

        # Fast path: a long-strip chapter ships every image URL in the reader
        # document, so the whole chapter costs exactly one request.
        inline = extract_inline_page_urls(html)
        if inline:
            pages = build_pages(chapter_key, inline, parse_image_info(html))
            self._log("pages", path, status="ok", detail=f"mode=inline count={len(pages)}")
            return pages

        context = extract_chapterfun_context(html)
        if context is None:
            self._log("pages", path, status="error", detail="no image script found")
            return []
        chapter_numeric_id, guidkey, image_count = context
        urls = self._resolve_via_chapterfun(
            chapter_key, chapter_numeric_id, guidkey, image_count
        )
        if not urls:
            self._log("pages", path, status="error", detail="chapterfun resolved nothing")
            return []
        pages = build_pages(chapter_key, urls, [])
        self._log(
            "pages",
            path,
            status="ok",
            detail=f"mode=chapterfun count={len(pages)} expected={image_count}",
        )
        return pages

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = normalize_chapter_key(fully_unquote(chapter_id))
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached
        pages = self._resolve_pages(chapter_key)
        if pages:
            self._page_cache.set(chapter_key, pages)
            self._page_count_cache.set(chapter_key, len(pages))
        return pages

    def find_page(self, page_id: str) -> Page | None:
        """Resolve one page by id with a single chapter lookup.

        Compares on the page NUMBER rather than the raw id string so a
        caller that hands back a differently-wrapped chapter key (a leading
        ``/manga/``, a trailing ``/1.html``) still resolves, instead of
        silently missing and rendering a broken image.
        """
        raw = fully_unquote(page_id)
        chapter_key = page_id_chapter_key(raw)
        if chapter_key is None:
            return None
        number = int(raw.rpartition(":")[2])
        for page in self.get_chapter_pages(normalize_chapter_key(chapter_key)):
            if page.number == number:
                return page
        return None

    def _debug_params(self) -> dict[str, Any]:  # pragma: no cover - diagnostics
        return {"base_url": SITE_BASE, "page_size": PAGE_SIZE}
