"""MangaTown online source connector.

Speed notes (all timings measured from the OVH VPS, not a laptop):

* **One fetch per series open.** MangaTown ships the complete chapter list
  inside the series page itself, so ``get_series`` and ``get_chapters`` share a
  single GET through ``_series_cache`` instead of downloading the same 335 KB
  document twice (Naruto: 752 chapters, one request).
* **Chapter images in ceil(pages / 2) tiny requests.** The obvious reading of
  this site is one full page fetch per image -- 53 requests of ~173 KB each for
  a single Naruto chapter, ~26 s. The reader's own ``chapterfun.ashx`` endpoint
  instead answers with a packed-JS *look-ahead batch* of two image URLs in
  ~680 bytes, and the chapter page states ``total_pages`` up front, so the whole
  chapter resolves from one page fetch plus 27 parallel 680-byte calls:
  **1.20 s end to end for all 53 pages**, ~18 KB of batch traffic.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.mangatown.mappers import (
    BROWSE_MODE_LABELS,
    GENRES,
    IMAGE_REFERER,
    LIST_PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    SITE_BASE,
    build_pages,
    chapter_id_to_path,
    genre_path,
    is_known_genre,
    listing_path,
    make_page_id,
    normalize_sort,
    page_id_chapter_id,
    parse_chapter_meta,
    parse_chapters,
    parse_image_batch,
    parse_inline_image,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_params,
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

#: How many chapterfun.ashx calls may be in flight at once. The batches are
#: ~680 bytes each and independent, so this is the difference between a 3 s
#: serial walk and the measured 0.71 s for a 53-page chapter. The client's
#: token bucket is given the matching burst so it does not re-serialize them.
IMAGE_BATCH_WORKERS = 8


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses, so a 404 arrives as httpx's ``raise_for_status`` message
    ("Client error '404 Not Found' for url ...") with ``status_code`` unset --
    a bare ``exc.status_code == 404`` check here would be dead code. Match both.

    Note this is NOT how a missing *series* presents on MangaTown: those 302 to
    ``/search?stype=1&name=...`` and answer 200, which is why the series path
    additionally treats "no detail markup" as not-found (see mappers).
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class MangaTownConnector(SourceConnector):
    """Browse and read manga from MangaTown (HTML catalog)."""

    SOURCE_TYPE = "mangatown"
    DISPLAY_NAME = "MangaTown"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from MangaTown. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            user_agent=BROWSER_USER_AGENT,
            burst=IMAGE_BATCH_WORKERS,
        )
        # One entry per series page fetch, holding BOTH products of that fetch.
        self._series_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)

    # -- descriptors --------------------------------------------------------

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
        # Page images come from zjcdn.mangahere.org and covers from
        # fmcdn.mangahere.com; the site's own placeholder cover lives on
        # static.mangatown.com. Listed as registrable domains because the CDN
        # shard prefix varies per series.
        return frozenset({"mangahere.org", "mangahere.com", "mangatown.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        """Both CDNs hotlink-protect: no ``Referer`` gets a 403 HTML page.

        Verified from the VPS -- the bare site root satisfies them for page
        images and covers alike, so this stays static rather than per-chapter.
        """
        return {"Referer": IMAGE_REFERER}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [BrowseMode(id=mode_id, label=label) for mode_id, label in BROWSE_MODE_LABELS]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=slug, label=label) for slug, label in GENRES]

    # -- helpers ------------------------------------------------------------

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
            f"MangaTown {operation} {SITE_BASE}{path} params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value.removeprefix("manga/")
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        value = fully_unquote(chapter_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value.removeprefix("manga/")
        return value

    def _listing(
        self, path: str, *, page: int, page_size: int, operation: str
    ) -> PaginatedSeriesList:
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log(operation, path, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=page_size)
        self._log(
            operation,
            path,
            status="ok",
            detail=f"page={page} count={len(listing.items)} has_more={listing.has_more}",
        )
        return listing

    # -- browse / search ----------------------------------------------------

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(1, page)
        mode = normalize_sort(sort)
        return self._listing(
            listing_path(page, sort=mode),
            page=page,
            page_size=LIST_PAGE_SIZE,
            operation=f"browse[{mode}]",
        )

    def browse_by_genre(
        self, genre: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        page = max(1, page)
        slug = genre.strip().strip("/").lower()
        if not is_known_genre(slug):
            raise NotImplementedError(f"MangaTown has no genre {genre!r}.")
        return self._listing(
            genre_path(slug, page),
            page=page,
            page_size=LIST_PAGE_SIZE,
            operation=f"genre[{slug}]",
        )

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        page = max(1, page)
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        path = "/search"
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

    # -- series detail + chapters (ONE shared fetch) ------------------------

    def _load_series_page(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        """Fetch and parse a series page once, serving detail AND chapters.

        The chapter rows live in the very document the detail comes from, so
        splitting these into two methods with two GETs would double the cost of
        every series open for no gain. Both public methods funnel through here.
        """
        cached = self._series_cache.get(series_key)
        if cached is not None:
            return cached

        path = f"/manga/{series_key}/"
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("detail", path, status="error", detail=str(exc))
            if _is_not_found(exc):
                return None, []
            raise

        series = parse_series_detail(html, series_key)
        if series is None:
            # Missing slugs redirect to /search and answer 200, so this is the
            # real not-found branch for this site -- not an HTTP status.
            self._log("detail", path, status="not_found", detail="no detail markup")
            return None, []

        chapters = parse_chapters(html, series_key)
        if chapters:
            series = Series(
                id=series.id,
                title=series.title,
                chapter_count=len(chapters),
                canonical_path=series.canonical_path,
                description=series.description,
                cover_url=series.cover_url,
                author=series.author,
                artist=series.artist,
                status=series.status,
                genres=series.genres,
                latest_chapter=chapters[-1].title,
            )
        result = (series, chapters)
        self._series_cache.set(series_key, result)
        self._log("detail", path, status="ok", detail=f"chapters={len(chapters)}")
        return result

    def get_series(self, series_id: str) -> Series | None:
        return self._load_series_page(self._normalize_series_id(series_id))[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._load_series_page(self._normalize_series_id(series_id))[1]

    # -- chapter pages ------------------------------------------------------

    def _fetch_image_batch(self, chapter_key: str, cid: int, page: int) -> list[str]:
        """One chapterfun.ashx call -> the URLs for pages ``page`` and ``page+1``."""
        path = f"/manga/{chapter_key}/chapterfun.ashx"
        try:
            payload = self._http.get_text(
                path, params={"cid": cid, "page": page, "key": ""}
            )
        except ConnectorHttpError as exc:
            logger.warning(
                "MangaTown image batch failed chapter=%s page=%d: %s", chapter_key, page, exc
            )
            return []
        return parse_image_batch(payload)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        chapter_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(chapter_key)
        if cached is not None:
            return cached

        path = chapter_id_to_path(chapter_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("pages", path, status="error", detail=str(exc))
            if _is_not_found(exc):
                return []
            raise

        meta = parse_chapter_meta(html)
        inline = parse_inline_image(html)
        if meta is None:
            # No reader script: the best that can be salvaged is the single
            # server-rendered image, which is still a readable one-page chapter.
            if not inline:
                self._log("pages", path, status="error", detail="no chapter meta")
                return []
            pages = build_pages(chapter_key, {1: inline})
            self._page_cache.set(chapter_key, pages)
            self._log("pages", path, status="ok", detail="count=1 (inline fallback)")
            return pages

        total_pages, cid = meta
        # Page 1 is already rendered into the document just fetched -- taking it
        # from there is free and removes one batch call from the fan-out.
        urls: dict[int, str] = {1: inline} if inline else {}

        first_missing = 1 if 1 not in urls else 2
        wanted = list(range(first_missing, total_pages + 1, 2))
        batches = 0
        if wanted:
            batches = len(wanted)
            with ThreadPoolExecutor(
                max_workers=min(IMAGE_BATCH_WORKERS, len(wanted))
            ) as pool:
                results = pool.map(
                    lambda start: (start, self._fetch_image_batch(chapter_key, cid, start)),
                    wanted,
                )
                for start, found in results:
                    for offset, url in enumerate(found):
                        number = start + offset
                        if 1 <= number <= total_pages:
                            urls.setdefault(number, url)

        # A batch that came back short leaves a hole; ask for those directly
        # rather than shipping a chapter with pages missing.
        missing = [n for n in range(1, total_pages + 1) if n not in urls]
        if missing:
            batches += len(missing)
            with ThreadPoolExecutor(
                max_workers=min(IMAGE_BATCH_WORKERS, len(missing))
            ) as pool:
                results = pool.map(
                    lambda start: (start, self._fetch_image_batch(chapter_key, cid, start)),
                    missing,
                )
                for start, found in results:
                    for offset, url in enumerate(found):
                        number = start + offset
                        if 1 <= number <= total_pages:
                            urls.setdefault(number, url)

        pages = build_pages(chapter_key, urls)
        if pages:
            self._page_cache.set(chapter_key, pages)
        self._log(
            "pages",
            path,
            status="ok",
            detail=f"count={len(pages)}/{total_pages} batches={batches}",
        )
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_key = page_id_chapter_id(page_id)
        if chapter_key is None:
            return None
        # get_chapter_pages is cached for 10 minutes, so the image proxy's
        # per-image calls collapse onto one chapter resolution.
        for page in self.get_chapter_pages(chapter_key):
            if page.id == page_id:
                return page
        return None
