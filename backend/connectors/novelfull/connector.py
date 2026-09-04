"""NovelFull source connector (spec 2026-09-04-novels-design §4).

The light-novel archive slot: full catalogues of English-TRANSLATED JP/KR/CN
light novels. See ``mappers`` for the probe record that put NovelFull here
(the named LightNovelWorld/NovelHall/ranobes ladder is Cloudflare-challenged
at the VPS egress; NovelFull answers 200 everywhere with plain httpx).
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
from connectors.novelfull.mappers import (
    SITE_BASE,
    browse_path,
    chapter_path,
    normalize_series_key,
    parse_chapter_options,
    parse_chapter_page,
    parse_novel_id,
    parse_novel_list,
    parse_novel_page,
    series_path,
)

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}


class NovelFullConnector(SourceConnector):
    """Browse and read English-translated light novels from NovelFull."""

    SOURCE_TYPE = "novelfull"
    DISPLAY_NAME = "NovelFull"
    DESCRIPTION = (
        "Browse and read English translations of Japanese, Korean, and "
        "Chinese light novels from NovelFull's archive. Chapter text is "
        "served as clean plain-text paragraphs."
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
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._novel_id_cache: TTLCache[str] = TTLCache(ttl_seconds=3600.0)
        self._chapters_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=300.0)

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
        # Covers are site-relative (/uploads/...).
        return frozenset({"novelfull.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Most Popular"),
            BrowseMode(id="latest", label="Latest Release"),
            BrowseMode(id="completed", label="Completed"),
        ]

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        path = browse_path(sort)
        html = self._http.get_text(path, params={"page": page} if page > 1 else None)
        listing = parse_novel_list(html, page=page)
        logger.info(
            "NovelFull browse %s page=%d count=%d has_more=%s",
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
        params: dict[str, object] = {"keyword": normalized}
        if page > 1:
            params["page"] = page
        html = self._http.get_text("/search", params=params)
        listing = parse_novel_list(html, page=page)
        logger.info(
            "NovelFull search %r page=%d count=%d",
            normalized,
            page,
            len(listing.items),
        )
        return listing

    def _fetch_detail_html(self, series_key: str) -> str | None:
        try:
            return self._http.get_text(series_path(series_key))
        except ConnectorHttpError as exc:
            logger.warning("NovelFull detail %s failed: %s", series_key, exc)
            if exc.status_code == 404:
                return None
            raise

    def get_series(self, series_id: str) -> Series | None:
        series_key = normalize_series_key(series_id)
        cached = self._series_cache.get(series_key)
        if cached is not None:
            return cached
        html = self._fetch_detail_html(series_key)
        if html is None:
            return None
        series = parse_novel_page(html, series_key)
        if series is None:
            return None
        novel_id = parse_novel_id(html)
        if novel_id:
            self._novel_id_cache.set(series_key, novel_id)
        chapters = self.get_chapters(series_key)
        if chapters:
            series = Series(
                id=series.id,
                title=series.title,
                chapter_count=len(chapters),
                description=series.description,
                cover_url=series.cover_url,
                author=series.author,
                status=series.status,
                genres=series.genres,
                latest_chapter=chapters[-1].title,
            )
        self._series_cache.set(series_key, series)
        return series

    def _novel_id(self, series_key: str) -> str | None:
        cached = self._novel_id_cache.get(series_key)
        if cached is not None:
            return cached
        html = self._fetch_detail_html(series_key)
        if html is None:
            return None
        novel_id = parse_novel_id(html)
        if novel_id:
            self._novel_id_cache.set(series_key, novel_id)
        return novel_id

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_key = normalize_series_key(series_id)
        cached = self._chapters_cache.get(series_key)
        if cached is not None:
            return cached
        novel_id = self._novel_id(series_key)
        if novel_id is None:
            return []
        try:
            html = self._http.get_text(
                "/ajax-chapter-option", params={"novelId": novel_id}
            )
        except ConnectorHttpError as exc:
            logger.warning("NovelFull chapters %s failed: %s", series_key, exc)
            return []
        chapters = parse_chapter_options(html, series_key)
        if chapters:
            self._chapters_cache.set(series_key, chapters)
        logger.info("NovelFull chapters %s count=%d", series_key, len(chapters))
        return chapters

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return []

    def find_page(self, page_id: str) -> Page | None:
        return None

    def chapter_text(self, series_key: str, chapter_key: str) -> NovelChapterText | None:
        path = chapter_path(series_key, chapter_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError as exc:
            if exc.status_code == 404:
                logger.warning("NovelFull chapter %s not found", path)
                return None
            raise
        text = parse_chapter_page(html)
        if text is None:
            logger.warning("NovelFull chapter %s did not parse", path)
            return None
        if not looks_english(text.paragraphs):
            logger.warning("NovelFull chapter %s failed the English check", path)
            return None
        logger.info(
            "NovelFull chapter %s paragraphs=%d words=%d",
            path,
            len(text.paragraphs),
            text.word_count,
        )
        return text
