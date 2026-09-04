"""Standard Ebooks novel source connector (spec 2026-09-04-novels-design §4).

Probed FROM THE VPS (production egress/TLS, 2026-09-04): browse, search, book
pages, tables of contents and chapter documents all answer 200 with plain
httpx — no Cloudflare, no interstitial. English public-domain literature,
hand-proofread and released CC0, so unlike the aggregator sources there is no
watermark text, no ad markup and no takedown risk.

Novel connector contract: ``CONTENT_KIND = "novel"``, ``chapter_text()``
returns sanitized plain-text paragraphs; ``get_chapter_pages`` is meaningless
(novels have no page images) and returns ``[]``.
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
from connectors.standardebooks.mappers import (
    SITE_BASE,
    browse_params,
    chapter_path,
    normalize_series_key,
    parse_book,
    parse_chapter_page,
    parse_ebook_list,
    series_path,
    toc_path,
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


class StandardEbooksConnector(SourceConnector):
    """Browse and read hand-produced public-domain literature."""

    SOURCE_TYPE = "standardebooks"
    DISPLAY_NAME = "Standard Ebooks"
    DESCRIPTION = (
        "Browse and read Standard Ebooks: public-domain literature, "
        "hand-proofread and typographically corrected, released CC0. Chapter "
        "text is served as clean plain-text paragraphs."
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
        # A detail view needs BOTH the book page (metadata) and the contents
        # document (chapter list), so the pair is fetched once and shared by
        # get_series/get_chapters instead of costing two round trips each.
        self._book_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
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
        # Covers are served from the site itself, both as /images/covers/...
        # (listings) and /ebooks/<key>/downloads/cover.jpg (book pages).
        return frozenset({"standardebooks.org"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Newest"),
            BrowseMode(id="popularity", label="Popular"),
            BrowseMode(id="reading-ease", label="Easiest Reads"),
            BrowseMode(id="length", label="Shortest First"),
            BrowseMode(id="author", label="By Author"),
        ]

    def get_series_list(
        self, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        html = self._http.get_text("/ebooks", params=browse_params(page, sort=sort))
        listing = parse_ebook_list(html, page=page)
        logger.info(
            "StandardEbooks browse sort=%s page=%d count=%d has_more=%s",
            sort,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        html = self._http.get_text(
            "/ebooks", params=browse_params(page, sort=sort, query=normalized)
        )
        listing = parse_ebook_list(html, page=page)
        logger.info(
            "StandardEbooks search %r page=%d count=%d",
            normalized,
            page,
            len(listing.items),
        )
        return listing

    def _fetch_book(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        series_key = normalize_series_key(series_key)
        cached = self._book_cache.get(series_key)
        if cached is not None:
            return cached
        try:
            book_html = self._http.get_text(series_path(series_key))
            toc_html = self._http.get_text(toc_path(series_key))
        except ConnectorHttpError as exc:
            logger.warning("StandardEbooks detail %s failed: %s", series_key, exc)
            if _is_not_found(exc):
                return None, []
            raise
        parsed = parse_book(book_html, toc_html, series_key)
        if parsed[0] is not None:
            self._book_cache.set(series_key, parsed)
        return parsed

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_book(series_id)[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._fetch_book(series_id)[1]

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
                logger.warning("StandardEbooks chapter %s not found", path)
                return None
            raise
        text = parse_chapter_page(html)
        if text is None:
            logger.warning("StandardEbooks chapter %s did not parse", path)
            return None
        if not looks_english(text.paragraphs):
            # The catalog is English-language, but it carries translated works
            # whose front matter can quote the original at length.
            logger.warning("StandardEbooks chapter %s failed the English check", path)
            return None
        logger.info(
            "StandardEbooks chapter %s paragraphs=%d words=%d",
            path,
            len(text.paragraphs),
            text.word_count,
        )
        return text
