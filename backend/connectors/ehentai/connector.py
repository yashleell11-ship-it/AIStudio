"""E-Hentai online source connector (custom HTML + lazy image resolve)."""

from __future__ import annotations

import concurrent.futures as cf
import logging
import math

from connectors.base import SourceConnector
from connectors.ehentai.mappers import (
    ENGLISH_LANGUAGE_QUERY,
    GALLERY_THUMBS_PER_PAGE,
    PAGE_SIZE,
    SITE_BASE,
    build_gallery_pages,
    extract_next_cursor,
    gallery_path,
    is_viewer_url,
    listing_path,
    page_id_gallery_id,
    parse_chapters,
    parse_gallery_id,
    parse_page_count,
    parse_page_tokens,
    parse_reader_image_url,
    parse_series_detail,
    parse_series_list,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError
from connectors.http.ddg_client import DdgSyncHttpClient
from connectors.ids import fully_unquote
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
BROWSER_IMPERSONATE = "chrome131"


# A gallery's thumbnail pages are fetched in bounded parallel batches. E-Hentai
# paginates thumbnails 20 at a time, so a 460-image gallery meant 22 strictly
# serial round trips -- measured at 23.1s from the VPS, the slowest single
# stage in the whole connector audit. The client's 0.35s spacing still applies
# to each request as it starts, so overlapping them does not raise the request
# rate this connector offers the site, only the time it waits on the replies.
_THUMB_PAGE_WORKERS = 4
# The gallery landing page answers three different questions -- metadata,
# chapter row, page tokens -- and opening a gallery asks all three back to
# back. Cache the document so that costs one fetch, not three.
_GALLERY_HTML_TTL_SECONDS = 120.0


class EHentaiConnector(SourceConnector):
    """Browse and read galleries from E-Hentai."""

    SOURCE_TYPE = "ehentai"
    DISPLAY_NAME = "E-Hentai"
    DESCRIPTION = (
        "Browse and read doujinshi, manga, and image sets from E-Hentai. "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = DdgSyncHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            impersonate=BROWSER_IMPERSONATE,
            min_interval=0.35,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._cursor_cache: TTLCache[str] = TTLCache(ttl_seconds=900.0)
        self._gallery_html_cache: TTLCache[str] = TTLCache(
            ttl_seconds=_GALLERY_HTML_TTL_SECONDS
        )

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
        # Viewer URLs live on e-hentai.org; covers on ehgt.org; pages on hath.network.
        return frozenset({"e-hentai.org", "ehgt.org", "hath.network"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def fetch_proxied_image(self, url: str) -> tuple[str, bytes] | None:
        """Resolve short-lived hath.network URLs from E-Hentai viewer pages."""
        headers = self.image_fetch_headers()
        if is_viewer_url(url):
            try:
                document = self._http.get_text(url)
            except ConnectorHttpError as exc:
                logger.warning("E-Hentai viewer fetch failed for %s: %s", url, exc)
                raise
            image_url = parse_reader_image_url(document)
            if not image_url:
                raise ConnectorHttpError(
                    f"E-Hentai reader page missing image for {url}",
                    status_code=502,
                )
            return self._http.get_bytes(image_url, extra_headers=headers)
        return self._http.get_bytes(url, extra_headers=headers)

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="english", label="English Only"),
        ]

    def _fetch_html(self, path: str) -> str:
        return self._http.get_text(path)

    def _gallery_html(self, gallery_id: str) -> str:
        """The gallery landing page, fetched at most once per TTL.

        get_series, get_chapters and _fetch_chapter_pages each need this exact
        document, and opening a gallery calls all three. Without the cache
        that is three identical requests to a site that rate-limits hard.
        """
        cached = self._gallery_html_cache.get(gallery_id)
        if cached is not None:
            return cached
        document = self._fetch_html(gallery_path(gallery_id))
        self._gallery_html_cache.set(gallery_id, document)
        return document

    def _normalize_gallery_id(self, gallery_id: str) -> str:
        value = fully_unquote(gallery_id).strip().strip("/")
        if value.startswith("g/"):
            value = value.removeprefix("g/")
        parsed = parse_gallery_id(value)
        if parsed is None:
            return value
        gid, token = parsed
        return f"{gid}/{token}"

    def _cursor_cache_key(self, query: str | None, sort: str | None, page: int) -> str:
        return f"{sort or ''}:{query or ''}:{page}"

    def _remember_next_cursor(
        self,
        *,
        query: str | None,
        sort: str | None,
        page: int,
        document: str,
    ) -> None:
        next_cursor = extract_next_cursor(document)
        if next_cursor:
            self._cursor_cache.set(
                self._cursor_cache_key(query, sort, page + 1),
                next_cursor,
            )

    def _resolve_listing_path(
        self,
        page: int,
        *,
        query: str | None,
        sort: str | None,
    ) -> str:
        if page < 1:
            page = 1
        if sort == "popular":
            return listing_path(sort="popular")
        if page == 1:
            return listing_path(query=query, sort=sort)
        cursor = self._cursor_cache.get(self._cursor_cache_key(query, sort, page))
        if cursor:
            return listing_path(query=query, cursor=cursor, sort=sort)
        current_page = 1
        while current_page < page:
            path = self._resolve_listing_path(current_page, query=query, sort=sort)
            document = self._fetch_html(path)
            self._remember_next_cursor(
                query=query,
                sort=sort,
                page=current_page,
                document=document,
            )
            current_page += 1
            if extract_next_cursor(document) is None:
                break
        cursor = self._cursor_cache.get(self._cursor_cache_key(query, sort, page))
        return listing_path(query=query, cursor=cursor, sort=sort)

    def _fetch_listing(
        self,
        page: int,
        *,
        query: str | None = None,
        sort: str | None = None,
    ) -> PaginatedSeriesList:
        path = self._resolve_listing_path(page, query=query, sort=sort)
        document = self._fetch_html(path)
        if sort != "popular":
            self._remember_next_cursor(
                query=query,
                sort=sort,
                page=page,
                document=document,
            )
        return parse_series_list(document, page=page, page_size=PAGE_SIZE)

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        query = ENGLISH_LANGUAGE_QUERY if sort == "english" else None
        effective_sort = "popular" if sort == "popular" else None
        listing = self._fetch_listing(page, query=query, sort=effective_sort)
        for item in listing.items:
            if item.cover_url:
                self._series_cache.set(item.id, item)
        logger.info(
            "E-Hentai browse sort=%r page=%d count=%d has_more=%s",
            sort,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if sort == "english":
            combined = (
                f"{ENGLISH_LANGUAGE_QUERY} {normalized}".strip()
                if normalized
                else ENGLISH_LANGUAGE_QUERY
            )
            listing = self._fetch_listing(page, query=combined)
        elif not normalized:
            return self.get_series_list(page, sort=sort)
        else:
            listing = self._fetch_listing(page, query=normalized)
        for item in listing.items:
            if item.cover_url:
                self._series_cache.set(item.id, item)
        logger.info(
            "E-Hentai search page=%d count=%d sort=%r query=%r",
            page,
            len(listing.items),
            sort,
            normalized,
        )
        return listing

    def get_series(self, series_id: str) -> Series | None:
        gallery_id = self._normalize_gallery_id(series_id)
        if parse_gallery_id(gallery_id) is None:
            return None
        cached = self._series_cache.get(gallery_id)
        if cached is not None and cached.description is not None:
            return cached
        try:
            document = self._gallery_html(gallery_id)
        except ConnectorHttpError:
            return None
        series = parse_series_detail(document, gallery_id=gallery_id)
        if series is None:
            return None
        self._series_cache.set(gallery_id, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        gallery_id = self._normalize_gallery_id(series_id)
        return self._chapter_list_cache.get_or_set(
            gallery_id,
            lambda: self._fetch_chapters(gallery_id),
        )

    def _fetch_chapters(self, gallery_id: str) -> list[Chapter]:
        if parse_gallery_id(gallery_id) is None:
            return []
        try:
            document = self._gallery_html(gallery_id)
        except ConnectorHttpError:
            return []
        return parse_chapters(document, gallery_id=gallery_id)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        gallery_id = self._normalize_gallery_id(chapter_id)
        return self._page_cache.get_or_set(
            gallery_id,
            lambda: self._fetch_chapter_pages(gallery_id),
        )

    def _fetch_chapter_pages(self, gallery_id: str) -> list[Page]:
        parsed = parse_gallery_id(gallery_id)
        if parsed is None:
            return []
        gid, _token = parsed
        try:
            first_document = self._gallery_html(gallery_id)
        except ConnectorHttpError:
            return []
        page_count = parse_page_count(first_document)
        if page_count <= 0:
            return []

        tokens = parse_page_tokens(first_document, gid=gid)
        thumb_pages = max(1, math.ceil(page_count / GALLERY_THUMBS_PER_PAGE))
        # How many thumbnail pages exist is known up front from the image
        # count, so they can be fetched in parallel batches instead of one at
        # a time. Batching (rather than firing all 20+ at once) keeps the
        # in-flight count bounded on a 2-vCPU box and lets the early exit
        # below still stop as soon as every token is in hand.
        remaining = list(range(1, thumb_pages))
        while remaining and len(tokens) < page_count:
            batch = remaining[:_THUMB_PAGE_WORKERS]
            remaining = remaining[len(batch):]
            for document in self._fetch_thumb_pages(gallery_id, batch):
                if document is None:
                    remaining = []
                    break
                tokens.update(parse_page_tokens(document, gid=gid))

        if not tokens:
            return []
        return build_gallery_pages(gallery_id=gallery_id, gid=gid, tokens=tokens)

    def _fetch_thumb_pages(
        self, gallery_id: str, thumb_pages: list[int]
    ) -> list[str | None]:
        """Fetch several thumbnail pages at once, returned in page order.

        A failed page yields ``None``; the caller stops there and keeps the
        tokens already collected, exactly as the old serial loop's ``break``
        did, so one bad response does not cost the whole gallery.
        """
        if not thumb_pages:
            return []
        results: dict[int, str | None] = {}
        with cf.ThreadPoolExecutor(
            max_workers=min(_THUMB_PAGE_WORKERS, len(thumb_pages)),
            thread_name_prefix="ehentai-thumbs",
        ) as ex:
            futures = {
                ex.submit(
                    self._fetch_html, gallery_path(gallery_id, thumb_page=thumb_page)
                ): thumb_page
                for thumb_page in thumb_pages
            }
            for future in cf.as_completed(futures):
                thumb_page = futures[future]
                try:
                    results[thumb_page] = future.result()
                except ConnectorHttpError as exc:
                    logger.info(
                        "E-Hentai thumb page %s of gallery %s failed: %s",
                        thumb_page,
                        gallery_id,
                        exc,
                    )
                    results[thumb_page] = None
        return [results.get(thumb_page) for thumb_page in thumb_pages]

    def find_page(self, page_id: str) -> Page | None:
        gallery_id = page_id_gallery_id(fully_unquote(page_id).strip())
        if gallery_id is None:
            return None
        gallery_id = self._normalize_gallery_id(gallery_id)
        for page in self.get_chapter_pages(gallery_id):
            if page.id == page_id or page.id == fully_unquote(page_id).strip():
                return page
        return None
