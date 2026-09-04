"""Royal Road novel source connector (spec 2026-09-04-novels-design §4).

Probed from the VPS (production egress/TLS, 2026-09-04): browse, search,
fiction detail and chapter pages all answer 200 with plain httpx — no
Cloudflare interstitial, unlike every "NovelBin-class" candidate. English
original web fiction only.

Novel connector contract: ``CONTENT_KIND = "novel"``, ``chapter_text()``
returns sanitized plain-text paragraphs; ``get_chapter_pages`` is
meaningless (novels have no page images) and returns ``[]``.
"""

from __future__ import annotations

import logging

from connectors.base import SourceConnector
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import (
    BrowseMode,
    Chapter,
    NovelChapterText,
    Page,
    PaginatedSeriesList,
    Series,
)
from connectors.novel_text import looks_english
from connectors.royalroad.mappers import (
    SITE_BASE,
    browse_path,
    chapter_path,
    normalize_chapter_key,
    normalize_series_key,
    parse_chapter_page,
    parse_fiction_list,
    parse_fiction_page,
    series_path,
)

logger = logging.getLogger(__name__)


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses; a plain 404 surfaces re-wrapped with ``status_code=None`` and
    httpx's ``raise_for_status`` text ("Client error '404 Not Found' for
    url ..."), so match both forms — a bare ``status_code == 404`` check is
    dead code against this client.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}


class RoyalRoadConnector(SourceConnector):
    """Browse and read English original web fiction from Royal Road."""

    SOURCE_TYPE = "royalroad"
    DISPLAY_NAME = "Royal Road"
    DESCRIPTION = (
        "Browse and read English original web fiction and light novels from "
        "Royal Road. Chapter text is served as clean plain-text paragraphs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False
    CONTENT_KIND = "novel"
    LANGUAGE = "en"

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            user_agent=BROWSER_USER_AGENT,
            headers=HTML_HEADERS,
        )
        # One fiction page carries BOTH series metadata and the full chapter
        # list (window.chapters), so cache the parsed pair and let
        # get_series/get_chapters share a single fetch.
        self._fiction_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
            ttl_seconds=300.0
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
    def allowed_image_hosts(self) -> frozenset[str]:
        # Covers are served from Royal Road's CDN (www.royalroadcdn.com); the
        # site host itself covers the placeholder art.
        return frozenset({"royalroadcdn.com", "royalroad.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Best Rated"),
            BrowseMode(id="trending", label="Trending"),
            BrowseMode(id="popular", label="Popular"),
            BrowseMode(id="latest", label="Latest Updates"),
            BrowseMode(id="complete", label="Completed"),
        ]

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = browse_path(sort)
        html = self._http.get_text(path, params={"page": page})
        listing = parse_fiction_list(html, page=page)
        logger.info(
            "RoyalRoad browse %s page=%d count=%d has_more=%s",
            path,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        html = self._http.get_text(
            "/fictions/search", params={"title": normalized, "page": page}
        )
        listing = parse_fiction_list(html, page=page)
        logger.info(
            "RoyalRoad search %r page=%d count=%d", normalized, page, len(listing.items)
        )
        return listing

    def _fetch_fiction(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        series_key = normalize_series_key(series_key)
        cached = self._fiction_cache.get(series_key)
        if cached is not None:
            return cached
        try:
            html = self._http.get_text(series_path(series_key))
        except ConnectorHttpError as exc:
            logger.warning("RoyalRoad detail %s failed: %s", series_key, exc)
            if _is_not_found(exc):
                return None, []
            raise
        parsed = parse_fiction_page(html, series_key)
        if parsed[0] is not None:
            self._fiction_cache.set(series_key, parsed)
        return parsed

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_fiction(series_id)[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._fetch_fiction(series_id)[1]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        # Novels have no page images; the reader goes through /novels/chapter.
        return []

    def find_page(self, page_id: str) -> Page | None:
        return None

    def chapter_text(self, series_key: str, chapter_key: str) -> NovelChapterText | None:
        path = chapter_path(series_key, chapter_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                logger.warning("RoyalRoad chapter %s not found", path)
                return None
            raise
        text = parse_chapter_page(html)
        if text is None:
            logger.warning("RoyalRoad chapter %s did not parse", path)
            return None
        if not looks_english(text.paragraphs):
            logger.warning("RoyalRoad chapter %s failed the English check", path)
            return None
        number = _number_from_chapter_key(normalize_chapter_key(chapter_key))
        if number is not None and text.chapter_number is None:
            text = NovelChapterText(
                title=text.title,
                paragraphs=text.paragraphs,
                chapter_number=number,
            )
        logger.info(
            "RoyalRoad chapter %s paragraphs=%d words=%d",
            path,
            len(text.paragraphs),
            text.word_count,
        )
        return text


def _number_from_chapter_key(chapter_key: str) -> float | None:
    """RR chapter slugs usually lead with the number ("301778/1-good-morning...").

    Best-effort only — the novel service backfills the authoritative number
    from the chapter list, this just covers a chapter no longer listed.
    """
    slug = chapter_key.split("/", 1)[1] if "/" in chapter_key else chapter_key
    head = slug.split("-", 1)[0]
    try:
        return float(head)
    except ValueError:
        return None
