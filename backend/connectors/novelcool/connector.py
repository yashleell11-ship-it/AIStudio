"""Novel Cool online source connector (manga side).

Novel Cool aggregates manga and web novels behind one ``/novel/<slug>.html``
namespace. This connector serves the **manga** half: every listing is filtered
on the site's own ``book-type-manga`` badge (see ``mappers.parse_series_cards``).

Three site behaviours shape the request plan, all measured from the VPS:

* **The chapter list is inline on the series detail page.** There is no
  separate chapter endpoint, so ``get_series`` and ``get_chapters`` share ONE
  fetch through ``_detail_cache`` — the detail-then-chapters sequence the app
  performs on every series open costs one request, not two.
* **The reader paginates images, 10 per view at most.** A 13-image chapter is
  two fetches, not thirteen; views past the first go out in parallel, so a
  chapter of any length costs two round trips.
* **Nothing 404s.** A bad slug returns HTTP 200 with the homepage. Missing
  content is detected by parse failure, never by status code.
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series
from connectors.novelcool.mappers import (
    BROWSE_MODES,
    GENRES,
    IMAGES_PER_VIEW,
    PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    SEARCH_PAGES_PER_REQUEST,
    SITE_BASE,
    chapter_id_to_path,
    genre_path,
    is_single_page_mode,
    listing_path,
    make_page_id,
    normalize_sort,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_params,
    search_path,
    series_id_to_path,
)

logger = logging.getLogger(__name__)

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

#: Widest deliberate fan-out: three search pages, or the reader views of one
#: chapter. The token bucket must allow that many to leave together or the
#: parallelism is cancelled by the rate limiter (see ``_rate_limit``).
_MAX_PARALLEL = 4

#: Hard ceiling on reader views fetched for one chapter. At 10 images per view
#: this covers a 200-image chapter; anything claiming more is a parse problem,
#: not a comic, and must not turn into an unbounded fetch loop.
_MAX_CHAPTER_VIEWS = 20


class NovelCoolConnector(SourceConnector):
    """Browse and read manga from Novel Cool."""

    SOURCE_TYPE = "novelcool"
    DISPLAY_NAME = "Novel Cool"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from Novel Cool. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            burst=_MAX_PARALLEL,
            extra_redirect_hosts=frozenset({"novelcool.com", "www.novelcool.com"}),
        )
        # One entry per series: (detail, chapters) parsed from a single fetch.
        self._detail_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
        )
        # Page URLs are signed and expire ~18h out (measured), so a 10 minute
        # TTL never serves a link that has gone stale.
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)

    # -- identity -----------------------------------------------------------

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
        # Covers: img.novelcool.com. Chapter images round-robin across
        # en2..en10.movietop.cc, so the registrable domain is allowlisted and
        # suffix matching covers every shard.
        return frozenset({"novelcool.com", "movietop.cc"})

    # -- logging ------------------------------------------------------------

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
            f"NovelCool {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    # -- key normalization --------------------------------------------------

    def _normalize_series_id(self, series_id: str) -> str:
        """Strip transport decoration only.

        Keys are OPAQUE: ``original/id-251898`` is a real series key and keeps
        its slash. Nothing here splits on one.
        """
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("novel/"):
            value = value.removeprefix("novel/")
        if value.endswith(".html"):
            value = value.removesuffix(".html")
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        value = fully_unquote(chapter_id).strip().strip("/")
        if value.startswith("chapter/"):
            value = value.removeprefix("chapter/")
        if value.endswith(".html"):
            value = value.removesuffix(".html")
        return value

    # -- browse -------------------------------------------------------------

    def list_browse_modes(self) -> list[BrowseMode]:
        return [BrowseMode(id=mode, label=label) for mode, label in BROWSE_MODES]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=genre, label=genre) for genre in GENRES]

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(1, page)
        mode = normalize_sort(sort)
        single = is_single_page_mode(mode)
        if single and page > 1:
            # latest/popular/new_list have exactly one page. Asking for
            # `latest_2.html` does NOT 404 and does NOT continue the list — it
            # serves the generic directory, which would show unrelated titles
            # under a "Latest" heading. Answer empty without a request.
            self._log(
                "browse",
                listing_path(mode, page),
                status="ok",
                detail=f"page={page} sort={mode!r} single-page mode, no page {page}",
            )
            return PaginatedSeriesList(
                items=[], page=page, page_size=PAGE_SIZE, total=0, api_has_more=False
            )

        path = listing_path(mode, page)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("browse", path, status="error", detail=str(exc))
            raise
        listing = parse_series_list(
            html, page=page, page_size=PAGE_SIZE, single_page=single
        )
        self._log(
            "browse",
            path,
            status="ok",
            detail=(
                f"page={page} sort={mode!r} count={len(listing.items)} "
                f"total={listing.total} has_more={listing.has_more}"
            ),
        )
        return listing

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        page = max(1, page)
        path = genre_path(genre, page)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("genre", path, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._log(
            "genre",
            path,
            status="ok",
            detail=f"genre={genre!r} page={page} count={len(listing.items)}",
        )
        return listing

    # -- search -------------------------------------------------------------

    def _search_page(self, query: str, upstream_page: int) -> PaginatedSeriesList:
        params = search_params(query, upstream_page)
        html = self._http.get_text(search_path(), params=params)
        return parse_search_results(html, page=upstream_page)

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        page = max(1, page)
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        span = SEARCH_PAGES_PER_REQUEST
        first_upstream = (page - 1) * span + 1
        try:
            head = self._search_page(normalized, first_upstream)
        except ConnectorHttpError as exc:
            self._log("search", search_path(), status="error", detail=str(exc))
            raise

        upstream_total = head.total_pages if head.api_has_more is not None else 1
        if head.api_has_more is False and head.total <= 0:
            upstream_total = first_upstream

        # Only the pages that exist, and only the rest of this app page's span.
        remaining = [
            upstream
            for upstream in range(first_upstream + 1, first_upstream + span)
            if upstream <= max(upstream_total, first_upstream)
        ]
        merged: list[Series] = list(head.items)
        if remaining:
            results: dict[int, PaginatedSeriesList] = {}
            with cf.ThreadPoolExecutor(
                max_workers=len(remaining), thread_name_prefix="novelcool-search"
            ) as pool:
                futures = {
                    pool.submit(self._search_page, normalized, upstream): upstream
                    for upstream in remaining
                }
                for future in cf.as_completed(futures):
                    upstream = futures[future]
                    try:
                        results[upstream] = future.result()
                    except ConnectorHttpError as exc:
                        # One page of a span failing degrades the result set;
                        # it must not fail the whole search.
                        self._log(
                            "search",
                            search_path(),
                            status="error",
                            detail=f"upstream page {upstream}: {exc}",
                        )
            for upstream in remaining:
                extra = results.get(upstream)
                if extra is not None:
                    merged.extend(extra.items)

        seen: set[str] = set()
        deduped: list[Series] = []
        for series in merged:
            if series.id in seen:
                continue
            seen.add(series.id)
            deduped.append(series)

        last_upstream = first_upstream + span - 1
        has_more = last_upstream < upstream_total
        listing = PaginatedSeriesList(
            items=deduped,
            page=page,
            page_size=max(SEARCH_PAGE_SIZE, len(deduped)),
            total=len(deduped) if not has_more else len(deduped) + 1,
            api_has_more=has_more,
        )
        self._log(
            "search",
            search_path(),
            params={"name": normalized, "page": page},
            status="ok",
            detail=(
                f"upstream={first_upstream}..{last_upstream}/{upstream_total} "
                f"count={len(deduped)} has_more={has_more}"
            ),
        )
        return listing

    # -- series detail + chapters (ONE shared fetch) ------------------------

    def _fetch_detail(self, series_id: str) -> tuple[Series | None, list[Chapter]]:
        """Fetch and parse a series page once, serving detail AND chapters.

        The chapter rows are inline on the same document as the metadata, so
        parsing both from one response is what keeps a series open at a single
        request instead of the two the naive split would cost.
        """
        cached = self._detail_cache.get(series_id)
        if cached is not None:
            return cached

        path = series_id_to_path(series_id)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("detail", path, status="error", detail=str(exc))
            return None, []

        detail = parse_series_detail(html, series_id)
        if detail is None:
            # Novel Cool answers an unknown slug with HTTP 200 + its homepage,
            # so a failed parse -- not a status code -- is what "missing" looks
            # like here.
            self._log("detail", path, status="error", detail="not a series page")
            self._detail_cache.set(series_id, (None, []))
            return None, []

        chapters = parse_chapters(html, series_id)
        if chapters:
            # The newest chapter is the highest-NUMBERED one, not simply the
            # last element: parse_chapters parks unnumbered oddments (notices,
            # omake) after the numbered run, and reading chapters[-1] blindly
            # advertised "136.5 {NOTICE}" as the latest chapter of a series
            # whose real head was Ch.272.
            numbered = [chapter for chapter in chapters if chapter.number is not None]
            newest = numbered[-1] if numbered else chapters[-1]
            detail = replace(
                detail,
                chapter_count=len(chapters),
                latest_chapter=newest.title,
            )
        parsed = (detail, chapters)
        self._detail_cache.set(series_id, parsed)
        self._log("detail", path, status="ok", detail=f"chapters={len(chapters)}")
        return parsed

    def _enrich(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill in page_count for chapters whose pages were already resolved."""
        enriched: list[Chapter] = []
        for chapter in chapters:
            count = self._page_count_cache.get(chapter.id)
            enriched.append(replace(chapter, page_count=count) if count else chapter)
        return enriched

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_detail(self._normalize_series_id(series_id))[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        chapters = self._fetch_detail(self._normalize_series_id(series_id))[1]
        return self._enrich(chapters)

    # -- chapter pages ------------------------------------------------------

    def _fetch_view(self, chapter_id: str, view: int) -> tuple[list[Page], int, int]:
        path = chapter_id_to_path(chapter_id, view)
        html = self._http.get_text(path)
        return parse_chapter_pages(html, chapter_id)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached

        path = chapter_id_to_path(api_key, 1)
        try:
            pages, total_pages, total_views = self._fetch_view(api_key, 1)
        except ConnectorHttpError as exc:
            self._log("pages", path, status="error", detail=str(exc))
            return []

        if not pages:
            self._log("pages", path, status="error", detail="no images on view 1")
            return []

        # View 1 already reported the whole chapter's shape ("<n>/<total>" next
        # to each image, plus the view selector), so the remaining views are
        # known up front and go out together rather than one after another.
        expected_views = max(
            total_views,
            -(-total_pages // IMAGES_PER_VIEW) if total_pages > 0 else 1,
        )
        expected_views = min(expected_views, _MAX_CHAPTER_VIEWS)

        collected: dict[int, Page] = {page.number: page for page in pages}
        if expected_views > 1:
            views = list(range(2, expected_views + 1))
            with cf.ThreadPoolExecutor(
                max_workers=min(_MAX_PARALLEL, len(views)),
                thread_name_prefix="novelcool-pages",
            ) as pool:
                futures = {
                    pool.submit(self._fetch_view, api_key, view): view for view in views
                }
                for future in cf.as_completed(futures):
                    view = futures[future]
                    try:
                        extra, _total, _views = future.result()
                    except ConnectorHttpError as exc:
                        self._log(
                            "pages",
                            chapter_id_to_path(api_key, view),
                            status="error",
                            detail=str(exc),
                        )
                        continue
                    for page in extra:
                        collected.setdefault(page.number, page)

        ordered = [collected[number] for number in sorted(collected)]
        if ordered:
            self._page_cache.set(api_key, ordered)
            self._page_count_cache.set(api_key, len(ordered))
        self._log(
            "pages",
            path,
            status="ok",
            detail=(
                f"count={len(ordered)} reported={total_pages} "
                f"views={expected_views}"
            ),
        )
        return ordered

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
