"""FreeWebNovel source connector (spec 2026-09-04-novels-design §4).

The big English-translation webnovel/light-novel archive. Probed from the
VPS (production egress/TLS, 2026-09-04): all views answer 200 with plain
httpx, where NovelBin was NXDOMAIN and the LightNovelWorld family was
Cloudflare-challenged. See ``mappers`` for the view map and the synthesized
chapter list.
"""

from __future__ import annotations

import logging

from connectors.base import SourceConnector
from connectors.freewebnovel.mappers import (
    SITE_BASE,
    browse_path,
    chapter_path,
    normalize_chapter_key,
    normalize_series_key,
    parse_browse_page,
    parse_chapter_page,
    parse_novel_page,
    parse_search_results,
    search_params,
    series_path,
)
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

logger = logging.getLogger(__name__)


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses; a 404 surfaces as httpx's ``raise_for_status`` message
    ("Client error '404 Not Found' for url ..."), so match both forms.
    Verified from the VPS: missing novels/chapters answer a real 404.
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


class FreeWebNovelConnector(SourceConnector):
    """Browse and read English-translated webnovels from FreeWebNovel."""

    SOURCE_TYPE = "freewebnovel"
    DISPLAY_NAME = "FreeWebNovel"
    DESCRIPTION = (
        "Browse and read English translations of webnovels and light novels "
        "from FreeWebNovel's archive. Chapter text is served as clean "
        "plain-text paragraphs."
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
        self._novel_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
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
        # Covers are site-relative (/files/..., /cache/cover-webp/...).
        return frozenset({"freewebnovel.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Latest Release"),
            BrowseMode(id="popular", label="Most Popular"),
        ]

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = browse_path(sort, page)
        html = self._http.get_text(path)
        listing = parse_browse_page(html, page=page)
        logger.info(
            "FreeWebNovel browse %s count=%d has_more=%s",
            path,
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
        # The site's search form POSTs and 303s to this GET; paginated via
        # ``page=N`` query params (verified from the VPS).
        html = self._http.get_text("/search", params=search_params(normalized, page))
        listing = parse_search_results(html, page=page)
        logger.info(
            "FreeWebNovel search %r page=%d count=%d has_more=%s",
            normalized,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def _fetch_novel(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        series_key = normalize_series_key(series_key)
        cached = self._novel_cache.get(series_key)
        if cached is not None:
            return cached
        try:
            html = self._http.get_text(series_path(series_key))
        except ConnectorHttpError as exc:
            logger.warning("FreeWebNovel detail %s failed: %s", series_key, exc)
            if _is_not_found(exc):
                return None, []
            raise
        parsed = parse_novel_page(html, series_key)
        if parsed[0] is not None:
            self._novel_cache.set(series_key, parsed)
        return parsed

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_novel(series_id)[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._fetch_novel(series_id)[1]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return []

    def find_page(self, page_id: str) -> Page | None:
        return None

    def chapter_text(self, series_key: str, chapter_key: str) -> NovelChapterText | None:
        path = chapter_path(series_key, chapter_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                logger.warning("FreeWebNovel chapter %s not found", path)
                return None
            raise
        text = parse_chapter_page(html, normalize_chapter_key(chapter_key))
        if text is None:
            logger.warning("FreeWebNovel chapter %s did not parse", path)
            return None
        if not looks_english(text.paragraphs):
            logger.warning("FreeWebNovel chapter %s failed the English check", path)
            return None
        logger.info(
            "FreeWebNovel chapter %s paragraphs=%d words=%d",
            path,
            len(text.paragraphs),
            text.word_count,
        )
        return text
