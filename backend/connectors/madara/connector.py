"""Generic Madara-theme source connector."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any
from connectors.ids import fully_unquote

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.cf_client import CfSyncHttpClient
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.madara.config import MadaraSiteConfig
from connectors.madara.mappers import MadaraHtml
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

#: Sent with page/cover image GETs. The image proxy passes only
#: ``image_fetch_headers()`` upstream, so without this these CDNs see the bare
#: httpx default and several of them 403 it.
IMAGE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_IMPERSONATE = "chrome131"

# Alternate url_segment values when the configured one returns an empty listing.
LISTING_FALLBACKS = ("manga", "serie")


class MadaraConnector(SourceConnector):
    """Browse/read any WordPress Madara-theme catalog via site config."""

    # Subclasses set these from factory.
    CONFIG: MadaraSiteConfig
    SOURCE_TYPE: str
    DISPLAY_NAME: str
    DESCRIPTION: str
    MATURE: bool = False

    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        cfg = self.CONFIG
        if cfg.use_cf:
            self._http: SyncConnectorHttpClient | CfSyncHttpClient = CfSyncHttpClient(
                cfg.base_url,
                headers=HTML_HEADERS,
                impersonate=BROWSER_IMPERSONATE,
            )
        else:
            self._http = SyncConnectorHttpClient(cfg.base_url, headers=HTML_HEADERS)
        self._html = MadaraHtml(cfg)
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._chapter_page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)

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
        return self.CONFIG.image_hosts

    def image_fetch_headers(self) -> dict[str, str]:
        # A browser User-Agent is as load-bearing as the Referer here. The
        # image proxy sends only these headers (no default UA), and several of
        # these CDNs answer a bare python-httpx request with 403 while the
        # same request with a desktop UA returns the image — manhwatop's
        # c3.manhwatop.com did exactly that, making the source browsable but
        # completely unreadable.
        return {
            "Referer": f"{self.CONFIG.base_url.rstrip('/')}/",
            "User-Agent": IMAGE_USER_AGENT,
        }

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest"),
            BrowseMode(id="latest", label="New"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="rating", label="Top Rated"),
        ]

    def _log(self, operation: str, path: str, **detail: object) -> None:
        logger.info("%s %s %s %s", self.DISPLAY_NAME, operation, path, detail)

    def _normalize_series_id(self, series_id: str) -> str:
        seg = self.CONFIG.url_segment
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith(f"{seg}/"):
            value = value.removeprefix(f"{seg}/")
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        return self._normalize_series_id(chapter_id)

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        for chapter in chapters:
            cached_count = self._chapter_page_count_cache.get(chapter.id)
            if cached_count is not None and cached_count > 0:
                enriched.append(replace(chapter, page_count=cached_count))
            else:
                enriched.append(chapter)
        return enriched

    def _remember_page_count(self, chapter_id: str, page_count: int) -> None:
        if page_count <= 0:
            return
        self._chapter_page_count_cache.set(chapter_id, page_count)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        segments = [self.CONFIG.url_segment]
        for alt in LISTING_FALLBACKS:
            if alt not in segments:
                segments.append(alt)

        last_error: Exception | None = None
        for seg in segments:
            cfg = self.CONFIG if seg == self.CONFIG.url_segment else replace(
                self.CONFIG, url_segment=seg
            )
            html_parser = MadaraHtml(cfg) if seg != self.CONFIG.url_segment else self._html
            path = html_parser.listing_path(page)
            params = html_parser.listing_params(sort=sort, page=page)
            try:
                html = self._http.get_text(path, params=params)
            except ConnectorHttpError as exc:
                last_error = exc
                continue
            listing = html_parser.parse_series_list(html, page=page)
            if listing.items:
                if seg != self.CONFIG.url_segment:
                    logger.info(
                        "%s browse via alternate segment %r (%d items)",
                        self.DISPLAY_NAME,
                        seg,
                        len(listing.items),
                    )
                return listing
        if last_error is not None:
            raise last_error
        return PaginatedSeriesList(
            items=[],
            page=page,
            page_size=self.CONFIG.page_size,
            total=0,
            api_has_more=False,
        )

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        path = "/"
        params = self._html.search_params(normalized, page=page)
        html = self._http.get_text(path, params=params)
        return self._html.parse_search_results(
            html, page=page, query=normalized
        )

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached

        path = self._html.series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return None

        series = self._html.parse_series_detail(html, api_key)
        if series is None:
            return None

        chapters = self._html.parse_chapters(html, api_key)
        if chapters:
            if self._chapter_list_cache.get(api_key) is None:
                self._chapter_list_cache.set(api_key, chapters)
        else:
            # Lazy-loading Madara builds ship an empty chapter list in the
            # series HTML and fill it over AJAX. This used to call
            # get_chapters(), which re-GET the series page we are already
            # holding -- a second full-page fetch on every detail open. The
            # AJAX resolution now runs against this HTML directly; measured
            # from the VPS the detail stage was 2.7-3.2s on the sites that
            # take this branch (manhwatop, manhuanext, lilymanga, cocomic).
            chapters = self._chapters_from_html(html, api_key, path)

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
        self._series_cache.set(api_key, series)
        return series

    def _fetch_ajax_chapters(self, manga_id: str, series_id: str, referer: str) -> list[Chapter]:
        """Load chapters via Madara AJAX when they are not embedded in the HTML.

        Older Madara builds POST to ``admin-ajax.php?action=manga_get_chapters``.
        Newer builds POST to ``{series_url}ajax/chapters/``.  Try both.
        """
        chapters = self._fetch_admin_ajax_chapters(manga_id, series_id, referer)
        if chapters:
            return chapters
        return self._fetch_relative_ajax_chapters(series_id, referer)

    def _fetch_admin_ajax_chapters(
        self, manga_id: str, series_id: str, referer: str
    ) -> list[Chapter]:
        try:
            html_fragment = self._http.post_text(
                "/wp-admin/admin-ajax.php",
                data={"action": "manga_get_chapters", "manga": manga_id},
                extra_headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": referer,
                    "Accept": "*/*",
                },
            )
        except ConnectorHttpError:
            return []
        if not html_fragment.strip() or html_fragment.strip() in {"0", "-1"}:
            return []
        return self._html.parse_chapters(html_fragment, series_id)

    def _fetch_relative_ajax_chapters(
        self, series_id: str, referer: str
    ) -> list[Chapter]:
        path = f"{self._html.series_id_to_path(series_id)}ajax/chapters/"
        try:
            html_fragment = self._http.post_text(
                path,
                data={},
                extra_headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": referer,
                    "Accept": "*/*",
                },
            )
        except ConnectorHttpError:
            return []
        return self._html.parse_chapters(html_fragment, series_id)

    def _chapters_from_html(
        self, html: str, api_key: str, path: str
    ) -> list[Chapter]:
        """Resolve a series' chapter list from series HTML already in hand.

        Takes the HTML rather than a series id so both callers can share one
        fetch: ``get_chapters`` has just downloaded the page, and
        ``get_series`` is holding the very same document.
        """
        chapters = self._html.parse_chapters(html, api_key)
        manga_id = self._html.parse_manga_id(html)
        if manga_id:
            referer = f"{self.CONFIG.base_url.rstrip('/')}{path}"
            ajax_chapters = self._fetch_ajax_chapters(manga_id, api_key, referer)
            if len(ajax_chapters) > len(chapters):
                logger.info(
                    "%s AJAX chapters series=%s inline=%d ajax=%d",
                    self.DISPLAY_NAME,
                    api_key,
                    len(chapters),
                    len(ajax_chapters),
                )
                chapters = ajax_chapters
        elif not chapters:
            logger.info(
                "%s no inline chapters and no manga_id for series=%s",
                self.DISPLAY_NAME,
                api_key,
            )

        if chapters:
            self._chapter_list_cache.set(api_key, chapters)
        return chapters

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)

        path = self._html.series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return []

        return self._enrich_chapters(self._chapters_from_html(html, api_key, path))

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached

        path = self._html.chapter_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return []

        pages = self._html.parse_chapter_pages(html, api_key)
        if pages:
            self._page_cache.set(api_key, pages)
            self._remember_page_count(api_key, len(pages))
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = MadaraHtml.page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
