"""ComicsValley online source connector.

Catalog lives on comicsvalley.net (Madara). Chapter/reader content is served
from allporncomics.co because ComicsValley series pages only expose a
"Read Online" deep-link and an empty chapter list.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse

from connectors.base import SourceConnector
from connectors.comicsvalley.mappers import (
    PAGE_SIZE,
    READER_BASE,
    SITE_BASE,
    absolute_reader_url,
    chapter_id_to_reader_path,
    listing_params,
    listing_path,
    normalize_sort,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_manga_id,
    parse_read_online_url,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    reader_series_path,
    search_params,
    series_id_to_path,
)
from connectors.http.cache import TTLCache
from connectors.http.cf_client import CfSyncHttpClient
from connectors.http.client import ConnectorHttpError
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
}
BROWSER_IMPERSONATE = "chrome131"


class ComicsValleyConnector(SourceConnector):
    """Browse ComicsValley (.net) and read via AllPornComics deep-links."""

    SOURCE_TYPE = "comicsvalley"
    DISPLAY_NAME = "ComicsValley"
    DESCRIPTION = (
        "Browse adult comics from ComicsValley. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        # Catalog host (.net). Absolute URLs to allporncomics.co also work via
        # CfSyncHttpClient._resolve_url when chapters/pages are fetched.
        self._http = CfSyncHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            impersonate=BROWSER_IMPERSONATE,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._chapter_page_count_cache: TTLCache[int] = TTLCache(ttl_seconds=600.0)
        self._reader_url_cache: TTLCache[str] = TTLCache(ttl_seconds=3600.0)

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
        return frozenset(
            {
                "comicsvalley.net",
                "allporncomics.co",
                "allporncomic.com",
                "cdn.allporncomic.com",
            }
        )

    def _image_referer_for_url(self, url: str) -> dict[str, str]:
        host = urlparse(url).netloc.lower()
        if host.endswith("comicsvalley.net"):
            return {"Referer": f"{SITE_BASE}/"}
        return {"Referer": f"{READER_BASE}/"}

    def image_fetch_headers(self) -> dict[str, str]:
        return self._image_referer_for_url(READER_BASE)

    def fetch_proxied_image(self, url: str) -> tuple[str, bytes] | None:
        return self._http.get_bytes(url, extra_headers=self._image_referer_for_url(url))

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest"),
            BrowseMode(id="latest", label="New"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="rating", label="Top Rated"),
        ]

    def _log_request(
        self,
        operation: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        status: str,
        detail: str | None = None,
    ) -> None:
        message = (
            f"ComicsValley {operation} {path} "
            f"params={params or {}} status={status}"
        )
        if detail:
            message += f" detail={detail}"
        logger.info(message)

    def _normalize_series_id(self, series_id: str) -> str:
        value = fully_unquote(series_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value.removeprefix("manga/")
        if value.startswith("comic/"):
            value = value.removeprefix("comic/")
        return value

    def _normalize_chapter_id(self, chapter_id: str) -> str:
        value = fully_unquote(chapter_id).strip().strip("/")
        if value.startswith("manga/"):
            value = value.removeprefix("manga/")
        if value.startswith("comic/"):
            value = value.removeprefix("comic/")
        return value

    def _enrich_browse_item(self, item: Series) -> Series:
        """Attach latest chapter labels for browse cards (ComicsValley HTML has none)."""
        api_key = item.id
        chapters = self._chapter_list_cache.get(api_key)
        if chapters is None:
            reader_url = f"{READER_BASE}{reader_series_path(api_key)}"
            chapters = self._fetch_relative_ajax_chapters(api_key, reader_url)
            if chapters:
                self._chapter_list_cache.set(api_key, chapters)
        if not chapters:
            return item
        return Series(
            id=item.id,
            title=item.title,
            chapter_count=len(chapters),
            cover_url=item.cover_url,
            canonical_path=item.canonical_path,
            latest_chapter=chapters[-1].title,
        )

    def _enrich_browse_listing(self, listing: PaginatedSeriesList) -> PaginatedSeriesList:
        if not listing.items:
            return listing
        max_workers = min(6, len(listing.items))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            enriched = list(pool.map(self._enrich_browse_item, listing.items))
        return replace(listing, items=enriched)

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        enriched: list[Chapter] = []
        eager_page_count = len(chapters) == 1
        for chapter in chapters:
            cached_count = self._chapter_page_count_cache.get(chapter.id)
            if cached_count is not None and cached_count > 0:
                enriched.append(replace(chapter, page_count=cached_count))
                continue
            if eager_page_count:
                page_count = len(self.get_chapter_pages(chapter.id))
                enriched.append(replace(chapter, page_count=page_count))
            else:
                enriched.append(chapter)
        return enriched

    def _remember_page_count(self, chapter_id: str, page_count: int) -> None:
        if page_count <= 0:
            return
        self._chapter_page_count_cache.set(chapter_id, page_count)

    def _resolve_reader_series_url(self, series_id: str, catalog_html: str | None = None) -> str:
        cached = self._reader_url_cache.get(series_id)
        if cached is not None:
            return cached

        html = catalog_html
        if html is None:
            path = series_id_to_path(series_id)
            try:
                html = self._http.get_text(path)
            except ConnectorHttpError:
                html = ""

        url = parse_read_online_url(html or "", series_id)
        self._reader_url_cache.set(series_id, url)
        return url

    def _fetch_ajax_chapters(self, series_id: str, reader_url: str) -> list[Chapter]:
        chapters = self._fetch_relative_ajax_chapters(series_id, reader_url)
        if chapters:
            return chapters
        # Fallback: older Madara admin-ajax (needs manga post id from reader page).
        try:
            reader_html = self._http.get_text(reader_url)
        except ConnectorHttpError:
            return []
        manga_id = parse_manga_id(reader_html)
        if not manga_id:
            return parse_chapters(reader_html, series_id)
        try:
            fragment = self._http.post_text(
                f"{READER_BASE}/wp-admin/admin-ajax.php",
                data={"action": "manga_get_chapters", "manga": manga_id},
                extra_headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": reader_url,
                    "Accept": "*/*",
                },
            )
        except ConnectorHttpError:
            return parse_chapters(reader_html, series_id)
        if not fragment.strip() or fragment.strip() in {"0", "-1"}:
            return parse_chapters(reader_html, series_id)
        return parse_chapters(fragment, series_id) or parse_chapters(reader_html, series_id)

    def _fetch_relative_ajax_chapters(self, series_id: str, reader_url: str) -> list[Chapter]:
        parsed = urlparse(reader_url)
        ajax_path = f"{parsed.path.rstrip('/')}/ajax/chapters/"
        ajax_url = f"{parsed.scheme}://{parsed.netloc}{ajax_path}"
        try:
            fragment = self._http.post_text(
                ajax_url,
                data={},
                extra_headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": reader_url,
                    "Accept": "*/*",
                },
            )
        except ConnectorHttpError:
            return []
        return parse_chapters(fragment, series_id)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = listing_path(page)
        params = listing_params(sort=sort)
        try:
            html = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log_request("browse", path, params=params, status="error", detail=str(exc))
            raise
        listing = parse_series_list(html, page=page, page_size=PAGE_SIZE)
        self._log_request(
            "browse",
            path,
            params=params,
            status="ok",
            detail=(
                f"page={page} sort={normalize_sort(sort)!r} count={len(listing.items)} "
                f"total={listing.total} has_more={listing.has_more}"
            ),
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        path = "/"
        params = search_params(normalized, page=page)
        try:
            html = self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log_request("search", path, params=params, status="error", detail=str(exc))
            raise
        listing = parse_search_results(html, page=page, query=normalized, page_size=PAGE_SIZE)
        self._log_request(
            "search",
            path,
            params=params,
            status="ok",
            detail=(
                f"page={page} query={normalized!r} count={len(listing.items)} "
                f"total={listing.total} has_more={listing.has_more}"
            ),
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached

        path = series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("detail", path, status="error", detail=str(exc))
            return None

        series = parse_series_detail(html, api_key)
        if series is None:
            self._log_request("detail", path, status="error", detail="parse failed")
            return None

        reader_url = self._resolve_reader_series_url(api_key, catalog_html=html)
        chapters = self._chapter_list_cache.get(api_key)
        if chapters is None:
            chapters = self._load_chapters(api_key, reader_url)

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
        self._log_request(
            "detail",
            path,
            status="ok",
            detail=f"chapters={series.chapter_count} reader={reader_url}",
        )
        return series

    def _load_chapters(self, series_id: str, reader_url: str) -> list[Chapter]:
        chapters = self._fetch_ajax_chapters(series_id, reader_url)
        if chapters:
            self._chapter_list_cache.set(series_id, chapters)
        return chapters

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)

        reader_url = self._resolve_reader_series_url(api_key)
        chapters = self._load_chapters(api_key, reader_url)
        enriched = self._enrich_chapters(chapters)
        self._log_request(
            "chapters",
            reader_url,
            status="ok",
            detail=f"count={len(enriched)}",
        )
        return enriched

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached

        path = absolute_reader_url(chapter_id_to_reader_path(api_key))
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("pages", path, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(html, api_key)
        if pages:
            self._page_cache.set(api_key, pages)
            self._remember_page_count(api_key, len(pages))
        self._log_request(
            "pages",
            path,
            status="ok",
            detail=f"count={len(pages)}",
        )
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
