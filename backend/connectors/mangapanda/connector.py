"""MangaPanda online source connector.

MangaPanda (https://mangapanda.onl) is a custom, fully server-rendered React
site — not a Madara install — so every stage is scrapable from the initial
HTML with no AJAX endpoint to discover and no JSON hydration payload to
unpack:

* ``GET /{updates,popular,new,completed,search}[/page/N]`` -> catalog listing
* ``GET /genre/<slug>[/page/N]``                           -> genre browse
* ``GET /search?q=<query>``                                -> keyword search
* ``GET /manga/<series>``      -> series metadata AND its complete chapter list
* ``GET /chapter/<series>/<chapter>`` -> every page image for that chapter

Two of those lines are the whole performance story for this source:

* The series page ships the *entire* chapter list inline — all 886 rows for a
  long-running series, not a paginated slice and not a second AJAX call. It is
  also the largest document the site serves (~650KB for such a series), so
  fetching it twice (once for detail, once for the chapter list) would be the
  single most expensive mistake available here. ``_load_series_page`` fetches
  it once and seeds both parsed caches, making a series open exactly one GET.
* The chapter page ships every page image URL in the initial HTML, so a
  chapter costs one GET regardless of length — no per-page resolution.

Images are proxied through ManhwaManiacs; the CDN hosts are enforced by the
SSRF allowlist in ``allowed_image_hosts``.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.ids import fully_unquote
from connectors.mangapanda.mappers import (
    GENRE_SLUGS,
    PAGE_SIZE,
    SITE_BASE,
    chapter_id_to_path,
    genre_label,
    genre_path,
    listing_path,
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
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": f"{SITE_BASE}/",
}

#: Media types the image proxy will serve as-is. Anything else it clamps to
#: application/octet-stream, which ``nosniff`` then makes unrenderable.
_IMAGE_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/avif", "image/gif"}
)

#: (magic prefix, media type). Ordered longest-first where prefixes overlap.
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _sniff_image_media_type(body: bytes, declared: str | None) -> str:
    """Return a truthful image media type for ``body``.

    Unlike the same-named helper on sources that merely *omit* a label, the
    magic number wins here: ``imgx.mghcdn.com`` serves genuine JPEG bytes for
    every ``.png`` page URL and labels them ``Content-Type: image/png``. That
    is a real image type, so the proxy passes it through untouched and the
    reader is handed a JPEG asserted to be a PNG under
    ``X-Content-Type-Options: nosniff`` — exactly the mismatch a strict client
    is entitled to refuse to decode. Reading the first bytes costs nothing and
    makes the label match the payload.
    """
    for magic, media_type in _IMAGE_MAGIC:
        if body.startswith(magic):
            return media_type
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    if body[4:8] == b"ftyp" and body[8:12] in (b"avif", b"avis"):
        return "image/avif"
    cleaned = (declared or "").split(";")[0].strip().lower()
    return cleaned if cleaned in _IMAGE_MEDIA_TYPES else "application/octet-stream"


class MangaPandaConnector(SourceConnector):
    """Browse and read manga from MangaPanda (server-rendered HTML catalog)."""

    SOURCE_TYPE = "mangapanda"
    DISPLAY_NAME = "MangaPanda"
    DESCRIPTION = (
        "Browse and read manga, manhwa, and manhua from MangaPanda. "
        "Images are proxied through ManhwaManiacs for reliable local reading."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(SITE_BASE, headers=HTML_HEADERS)
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
        # thumb.mghcdn.com serves cover art, imgx.mghcdn.com the page images.
        # The suffix entry covers both (and any sibling image shard).
        return frozenset({"mghcdn.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        # The CDN does not enforce hotlink protection today (verified: page
        # images return full bytes with no Referer). Sending the site Referer
        # anyway costs nothing and keeps this source working unchanged on the
        # day they turn it on, which is the usual failure mode for these CDNs.
        return {"Referer": f"{SITE_BASE}/"}

    def fetch_proxied_image(self, url: str) -> tuple[str, bytes] | None:
        """Fetch a page image and label it by its actual bytes."""
        media_type, body = self._http.get_bytes(url)
        return _sniff_image_media_type(body, media_type), body

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest Updates"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="added", label="New"),
            BrowseMode(id="completed", label="Completed"),
            BrowseMode(id="alphabetical", label="Directory"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=slug, label=genre_label(slug)) for slug in GENRE_SLUGS]

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
            f"MangaPanda {operation} {SITE_BASE}{path} "
            f"params={params or {}} status={status}"
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
        if value.startswith("chapter/"):
            value = value.removeprefix("chapter/")
        return value

    def _enrich_chapters(self, chapters: list[Chapter]) -> list[Chapter]:
        """Fill in page counts learned from chapters already opened."""
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

    def _fetch_listing(
        self,
        operation: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str | None:
        try:
            return self._http.get_text(path, params=params)
        except ConnectorHttpError as exc:
            self._log_request(
                operation, path, params=params, status="error", detail=str(exc)
            )
            raise

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = listing_path(page, sort=sort)
        html = self._fetch_listing("browse", path)
        listing = parse_series_list(html or "", page=page)
        self._log_request(
            "browse",
            path,
            status="ok",
            detail=(
                f"page={page} sort={normalize_sort(sort)!r} count={len(listing.items)} "
                f"has_more={listing.has_more}"
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
        if page < 1:
            page = 1
        path = genre_path(genre, page)
        html = self._fetch_listing("genre", path)
        listing = parse_series_list(html or "", page=page)
        self._log_request(
            "genre",
            path,
            status="ok",
            detail=f"genre={genre!r} page={page} count={len(listing.items)}",
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)

        path = search_path()
        params = search_params(normalized)
        html = self._fetch_listing("search", path, params=params)
        listing = parse_search_results(html or "", page=page)
        self._log_request(
            "search",
            path,
            params=params,
            status="ok",
            detail=f"query={normalized!r} count={len(listing.items)}",
        )
        return listing

    def _load_series_page(self, api_key: str) -> tuple[Series | None, list[Chapter]]:
        """Fetch a series page once and parse BOTH things it contains.

        The metadata block and the complete chapter list live in the same
        document, and it is the heaviest document this source serves. Parsing
        both from one response — and seeding both caches with the result — is
        what keeps opening a series at a single request instead of downloading
        several hundred KB twice in a row.
        """
        path = series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("detail", path, status="error", detail=str(exc))
            return None, []

        series = parse_series_detail(html, api_key)
        chapters = parse_chapters(html, api_key)
        if chapters:
            self._chapter_list_cache.set(api_key, chapters)
        if series is not None:
            if chapters:
                series = replace(
                    series,
                    chapter_count=len(chapters),
                    latest_chapter=chapters[-1].title,
                )
            self._series_cache.set(api_key, series)
        self._log_request(
            "detail",
            path,
            status="ok" if series is not None else "error",
            detail=f"chapters={len(chapters)}",
        )
        return series, chapters

    def get_series(self, series_id: str) -> Series | None:
        api_key = self._normalize_series_id(series_id)
        cached = self._series_cache.get(api_key)
        if cached is not None:
            return cached
        series, _chapters = self._load_series_page(api_key)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)
        _series, chapters = self._load_series_page(api_key)
        return self._enrich_chapters(chapters)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        api_key = self._normalize_chapter_id(chapter_id)
        cached = self._page_cache.get(api_key)
        if cached is not None:
            return cached

        path = chapter_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            self._log_request("pages", path, status="error", detail=str(exc))
            return []

        pages = parse_chapter_pages(html, api_key)
        if pages:
            self._page_cache.set(api_key, pages)
            self._remember_page_count(api_key, len(pages))
        self._log_request("pages", path, status="ok", detail=f"count={len(pages)}")
        return pages

    def find_page(self, page_id: str) -> Page | None:
        chapter_id = page_id_chapter_id(page_id)
        if chapter_id is None:
            return None
        for page in self.get_chapter_pages(chapter_id):
            if page.id == page_id:
                return page
        return None
