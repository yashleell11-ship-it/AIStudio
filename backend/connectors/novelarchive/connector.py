"""Novel Archive (novelarchive.cc) source connector — the flagship novel source.

Spec 2026-09-04-novels-design §4 + owner redirect of the same day. JSON API
end to end (see ``mappers`` for the endpoint map and the VPS probe record).
English catalogue; the shared sanitizer + English guard still run on every
chapter before it can reach the cache.
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
from connectors.novelarchive.mappers import (
    PAGE_SIZE,
    SITE_BASE,
    normalize_chapter_key,
    normalize_series_key,
    parse_chapter,
    parse_detail,
    parse_listing,
    sort_param,
)

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _is_client_error(exc: ConnectorHttpError) -> bool:
    """A definitive this-does-not-exist answer from the API (400/404).

    ``SyncConnectorHttpClient.get_json`` folds httpx status errors into
    ConnectorHttpError with the status only in the message, so match both.
    """
    if exc.status_code in (400, 404):
        return True
    message = str(exc)
    return "'404" in message or "'400" in message


class NovelArchiveConnector(SourceConnector):
    """Browse and read English novels from the Novel Archive JSON API."""

    SOURCE_TYPE = "novelarchive"
    DISPLAY_NAME = "Novel Archive"
    DESCRIPTION = (
        "Browse and read English webnovels and light novels from Novel "
        "Archive's ~61k-title catalogue. Chapter text is served as clean "
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
            headers={"Accept": "application/json"},
        )
        # One detail response carries BOTH series metadata and the full
        # chapter-name list; cache the parsed pair so get_series/get_chapters
        # share a single fetch (same shape as the reference stub connector).
        self._detail_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
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
        # Covers are served by the API itself (/api/novels/{id}/cover).
        return frozenset({"novelarchive.cc"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Popular"),
            BrowseMode(id="recent", label="Recently Updated"),
        ]

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        params = {"page": page, "per_page": PAGE_SIZE, "sort": sort_param(sort)}
        payload = self._http.get_json("/api/novels", params=params)
        listing = parse_listing(payload, page=page)
        logger.info(
            "NovelArchive browse sort=%s page=%d count=%d has_more=%s",
            params["sort"],
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
        params = {"page": page, "per_page": PAGE_SIZE, "search": normalized}
        payload = self._http.get_json("/api/novels", params=params)
        listing = parse_listing(payload, page=page)
        logger.info(
            "NovelArchive search %r page=%d count=%d",
            normalized,
            page,
            len(listing.items),
        )
        return listing

    def _fetch_detail(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        series_key = normalize_series_key(series_key)
        cached = self._detail_cache.get(series_key)
        if cached is not None:
            return cached
        try:
            payload = self._http.get_json(f"/api/novels/{series_key}")
        except ConnectorHttpError as exc:
            logger.warning("NovelArchive detail %s failed: %s", series_key, exc)
            if _is_client_error(exc):
                return None, []
            raise
        parsed = parse_detail(payload, series_key)
        if parsed[0] is not None:
            self._detail_cache.set(series_key, parsed)
        return parsed

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_detail(series_id)[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._fetch_detail(series_id)[1]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        # Novels have no page images; reading goes through /novels/chapter.
        return []

    def find_page(self, page_id: str) -> Page | None:
        return None

    def chapter_text(self, series_key: str, chapter_key: str) -> NovelChapterText | None:
        series_key = normalize_series_key(series_key)
        chapter_key = normalize_chapter_key(chapter_key)
        path = f"/api/novels/{series_key}/chapters/{chapter_key}"
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            if _is_client_error(exc):
                logger.warning("NovelArchive chapter %s not found", path)
                return None
            raise
        text = parse_chapter(payload)
        if text is None:
            logger.warning("NovelArchive chapter %s had no usable content", path)
            return None
        if not looks_english(text.paragraphs):
            logger.warning("NovelArchive chapter %s failed the English check", path)
            return None
        logger.info(
            "NovelArchive chapter %s paragraphs=%d words=%d",
            path,
            len(text.paragraphs),
            text.word_count,
        )
        return text
