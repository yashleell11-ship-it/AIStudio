"""WEBTOON (webtoons.com) online source connector.

The official LINE Webtoon site is JavaScript-heavy, but its list, episode-list
and viewer pages are server-rendered HTML, so this connector scrapes them
directly with a desktop browser User-Agent. Page images are hotlink-protected;
see :meth:`WebtoonsConnector.image_fetch_headers`.
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
from connectors.webtoons.mappers import (
    GENRES,
    IMAGE_HOSTS,
    IMAGE_REFERER,
    PAGE_SIZE,
    SITE_BASE,
    canvas_detail_path,
    chapter_viewer_path,
    canvas_path,
    extract_slug_from_canonical_path,
    genre_path,
    make_chapter_id,
    originals_path,
    page_id_chapter_id,
    paginate_cards,
    parse_chapter_id,
    parse_chapter_pages,
    parse_episodes,
    parse_max_list_page,
    parse_search_results,
    parse_series_cards,
    parse_series_detail,
    peek_latest_episode,
    search_params,
    search_path,
    series_detail_path,
    series_page_path,
)

logger = logging.getLogger(__name__)

# Episode-list pages are fetched in bounded parallel batches. WEBTOON paginates
# a long series into ten-episode pages, so a 114-episode title used to cost
# twelve strictly sequential round trips (measured 8.0s from the VPS). The
# pagination strip already names the next ten pages, so they can be fetched
# together. Kept small: the box has 2 vCPU and this must not read as a flood
# to one host -- the shared client's own 0.21s spacing still applies to each
# request as it starts.
_CHAPTER_PAGE_WORKERS = 6
# One episode-list page answers both get_series (metadata) and get_chapters
# (episode rows). Short-lived on purpose: it exists to collapse the two calls
# a single "open this series" makes, not to serve stale chapter lists.
_LIST_HTML_TTL_SECONDS = 60.0

# A real desktop browser User-Agent -- WEBTOON serves a degraded / bot page to
# generic clients.
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": SITE_BASE,
}

# Detail pages paginate episodes 10-per-page. Requesting a page beyond the last
# clamps to the last page (returning already-seen episodes), so pagination
# terminates when a page contributes zero new episodes. This bounds a
# pathological title.
MAX_EPISODE_PAGES = 250


class WebtoonsConnector(SourceConnector):
    """Browse and read comics from WEBTOON (webtoons.com)."""

    SOURCE_TYPE = "webtoons"
    DISPLAY_NAME = "WEBTOON"
    DESCRIPTION = (
        "Browse and read Originals and Canvas comics from WEBTOON "
        "(webtoons.com). Images are proxied through ManhwaManiacs for reliable "
        "local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            user_agent=DESKTOP_USER_AGENT,
            headers=HTML_HEADERS,
        )
        self._catalog_cache: TTLCache[list[Series]] = TTLCache(ttl_seconds=300.0)
        self._slug_cache: TTLCache[tuple[str, str]] = TTLCache(ttl_seconds=3600.0)
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)
        self._list_html_cache: TTLCache[str] = TTLCache(
            ttl_seconds=_LIST_HTML_TTL_SECONDS
        )

    # -- Descriptors --------------------------------------------------------

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
        return IMAGE_HOSTS

    def image_fetch_headers(self) -> dict[str, str]:
        # webtoon-phinf.pstatic.net enforces hotlink protection: a bare GET
        # returns HTTP 403 without a webtoons.com Referer.
        return {"Referer": IMAGE_REFERER, "User-Agent": DESKTOP_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Originals"),
            BrowseMode(id="canvas", label="Canvas"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=slug, label=label) for slug, label in GENRES]

    # -- Logging ------------------------------------------------------------

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
            f"WEBTOON {operation} {SITE_BASE}{path} params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    # -- Browse / search ----------------------------------------------------

    def _remember_slugs(self, items: list[Series]) -> None:
        for item in items:
            slug = extract_slug_from_canonical_path(item.canonical_path)
            if slug is not None:
                self._slug_cache.set(item.id, slug)

    def _load_catalog(self, path: str, cache_key: str) -> list[Series]:
        cached = self._catalog_cache.get(cache_key)
        if cached is not None:
            return cached
        html = self._http.get_text(path)
        items = parse_series_cards(html)
        if items:
            self._remember_slugs(items)
            self._catalog_cache.set(cache_key, items)
        return items

    def _series_list_path(self, series_id: str, page: int) -> str:
        api_key = self._normalize_series_id(series_id)
        slug = self._slug_cache.get(api_key)
        if slug is not None and page > 1:
            genre, series_slug = slug
            return series_page_path(genre, series_slug, api_key, page)
        if slug is not None and page == 1:
            genre, series_slug = slug
            return series_page_path(genre, series_slug, api_key, 1)
        return series_detail_path(api_key)

    def _get_series_html(self, api_key: str, page: int) -> str:
        """Fetch one series detail/list page's HTML.

        ``_series_list_path`` guesses the Originals-shaped placeholder path
        (``/en/_/_/list``) when the real genre/slug hasn't been learned yet
        (cold ``_slug_cache`` -- e.g. right after a restart, before the user
        has browsed or searched this session). That placeholder only
        round-trips for Originals: WEBTOON 301-redirects it to the canonical
        URL for an Originals title, but 404s it for a Canvas title instead.
        On that failure, retry once against the Canvas-shaped placeholder
        (``/en/canvas/_/list``). Whichever guess succeeds, the response body
        carries the real canonical genre/slug, which the caller learns and
        caches -- so this fallback only ever fires on the first, cold-cache
        request for a given series; every later call (including deeper
        pagination) goes straight to the canonical path.
        """
        cache_key = f"{api_key}:{page}"
        cached = self._list_html_cache.get(cache_key)
        if cached is not None:
            return cached

        path = self._series_list_path(api_key, page)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            # Only retry the cold-cache guess-and-check; if the genre/slug is
            # already known, this path was already canonical and a fresh
            # failure is a real error, not a wrong-section guess.
            if page != 1 or self._slug_cache.get(api_key) is not None:
                raise
            html = self._http.get_text(canvas_detail_path(api_key))
        self._list_html_cache.set(cache_key, html)
        return html

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(page, 1)
        if sort == "canvas":
            path = canvas_path()
            cache_key = "canvas"
        else:
            path = originals_path()
            cache_key = "originals"
        try:
            catalog = self._load_catalog(path, cache_key)
        except ConnectorHttpError as exc:
            self._log("browse", path, status="error", detail=str(exc))
            raise
        listing = paginate_cards(catalog, page=page, page_size=PAGE_SIZE)
        self._log(
            "browse",
            path,
            status="ok",
            detail=f"page={page} count={len(listing.items)} total={listing.total}",
        )
        return listing

    def browse_by_genre(
        self,
        genre: str,
        page: int,
        *,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        page = max(page, 1)
        slug = fully_unquote(genre).strip().strip("/")
        path = genre_path(slug)
        try:
            catalog = self._load_catalog(path, f"genre:{slug}")
        except ConnectorHttpError as exc:
            self._log("genre", path, status="error", detail=str(exc))
            raise
        listing = paginate_cards(catalog, page=page, page_size=PAGE_SIZE)
        self._log(
            "genre",
            path,
            status="ok",
            detail=f"genre={slug!r} page={page} count={len(listing.items)} total={listing.total}",
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        page = max(page, 1)
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        path = search_path()
        params = search_params(normalized)
        try:
            html = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log("search", path, params=params, status="error", detail=str(exc))
            raise
        self._remember_slugs(parse_series_cards(html))
        listing = parse_search_results(html, page=page, page_size=PAGE_SIZE)
        self._log(
            "search",
            path,
            params=params,
            status="ok",
            detail=f"query={normalized!r} count={len(listing.items)}",
        )
        return listing

    # -- Series / chapters --------------------------------------------------

    def _normalize_series_id(self, series_id: str) -> str:
        return fully_unquote(series_id).strip().strip("/")

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached

        path = self._series_list_path(api_key, 1)
        try:
            html = self._get_series_html(api_key, 1)
        except ConnectorHttpError as exc:
            self._log("detail", path, status="error", detail=str(exc))
            return None

        series = parse_series_detail(html, api_key)
        if series is None:
            self._log("detail", path, status="error", detail="parse failed")
            return None

        slug = extract_slug_from_canonical_path(series.canonical_path)
        if slug is not None:
            self._slug_cache.set(api_key, slug)

        peek = peek_latest_episode(html, api_key)
        if peek is not None:
            count_hint, latest_title = peek
            series = replace(
                series,
                latest_chapter=latest_title,
                chapter_count=count_hint,
            )
        self._series_cache.set(api_key, series)
        self._log("detail", path, status="ok", detail=f"chapters_hint={series.chapter_count}")
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich(cached)

        collected: dict[str, Chapter] = {}

        # Page 1 must go first and alone: it is what teaches ``_slug_cache``
        # the canonical genre/slug, and every deeper page's URL is built from
        # that. It is also usually already in _list_html_cache, put there by
        # the get_series call the reader made a moment earlier.
        first_path = self._series_list_path(api_key, 1)
        try:
            first_html = self._get_series_html(api_key, 1)
        except ConnectorHttpError as exc:
            self._log("chapters", first_path, status="error", detail=str(exc))
            return []

        first_batch = parse_episodes(first_html, api_key)
        self._learn_slug(api_key, first_html, first_batch)
        for chapter in first_batch:
            collected[chapter.id] = chapter

        if first_batch:
            # WEBTOON's pagination strip names the next ten pages, so they can
            # be fetched together instead of one-at-a-time-until-empty. A
            # 114-episode title was twelve serial round trips (8.0s).
            known_max = min(parse_max_list_page(first_html), MAX_EPISODE_PAGES)
            pending = list(range(2, known_max + 1))
            exhausted = False
            while pending and not exhausted:
                batch_pages = pending[:_CHAPTER_PAGE_WORKERS]
                pending = pending[len(batch_pages):]
                for page, html in self._fetch_list_pages(api_key, batch_pages):
                    if html is None:
                        exhausted = True
                        break
                    episodes = parse_episodes(html, api_key)
                    if not episodes:
                        exhausted = True
                        break
                    added = sum(
                        1 for ch in episodes if collected.setdefault(ch.id, ch) is ch
                    )
                    if added == 0:
                        # Same rows as a previous page: WEBTOON is clamping an
                        # over-range page number rather than serving new ones.
                        exhausted = True
                        break
                    # A later strip reveals the next group of ten.
                    revealed = min(parse_max_list_page(html), MAX_EPISODE_PAGES)
                    if revealed > known_max:
                        pending.extend(range(known_max + 1, revealed + 1))
                        known_max = revealed

        chapters = sorted(
            collected.values(),
            key=lambda ch: ch.number if ch.number is not None else 0.0,
        )
        if chapters:
            self._chapter_list_cache.set(api_key, chapters)
        enriched = self._enrich(chapters)
        self._log("chapters", series_detail_path(api_key), status="ok", detail=f"count={len(enriched)}")
        return enriched

    def _learn_slug(
        self, api_key: str, html: str, episodes: list[Chapter]
    ) -> None:
        """Cache the canonical (genre, slug) this series lives under.

        Every episode-list page past the first is addressed by that pair, so
        it has to be learned from page 1 before anything deeper is requested.
        """
        if self._slug_cache.get(api_key) is None:
            detail = parse_series_detail(html, api_key)
            if detail is not None:
                slug = extract_slug_from_canonical_path(detail.canonical_path)
                if slug is not None:
                    self._slug_cache.set(api_key, slug)
                    return
        if episodes:
            parsed = parse_chapter_id(episodes[0].id)
            if parsed is not None:
                _, _, genre, series_slug = parsed
                self._slug_cache.set(api_key, (genre, series_slug))

    def _fetch_list_pages(
        self, api_key: str, pages: list[int]
    ) -> list[tuple[int, str | None]]:
        """Fetch several episode-list pages at once, returned in page order.

        A failed page yields ``None`` rather than raising: the caller treats
        it the way the old serial loop treated an error, as the end of the
        list, so a transient failure deep in a long series still returns the
        episodes already collected instead of nothing.
        """
        if not pages:
            return []
        results: dict[int, str | None] = {}
        with cf.ThreadPoolExecutor(
            max_workers=min(_CHAPTER_PAGE_WORKERS, len(pages)),
            thread_name_prefix="webtoons-eplist",
        ) as ex:
            futures = {
                ex.submit(self._get_series_html, api_key, page): page
                for page in pages
            }
            for future in cf.as_completed(futures):
                page = futures[future]
                try:
                    results[page] = future.result()
                except ConnectorHttpError as exc:
                    self._log(
                        "chapters",
                        self._series_list_path(api_key, page),
                        status="error",
                        detail=str(exc),
                    )
                    results[page] = None
        return [(page, results.get(page)) for page in pages]

    def _enrich(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            count = self._page_count_cache.get(chapter.id)
            if count is not None and count > 0:
                enriched.append(replace(chapter, page_count=count))
            else:
                enriched.append(chapter)
        return enriched

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = fully_unquote(chapter_id).strip()
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached

        path = chapter_viewer_path(api_key)
        if path is None:
            self._log("pages", api_key, status="error", detail="bad chapter_id")
            return []
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log("pages", path, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(html, api_key)
        if pages:
            self._page_cache.set(api_key, pages)
            self._page_count_cache.set(api_key, len(pages))
        self._log("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        normalized = fully_unquote(page_id).strip()
        chapter_id = page_id_chapter_id(normalized)
        if chapter_id is None or parse_chapter_id(chapter_id) is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == normalized:
                return page
        return None
