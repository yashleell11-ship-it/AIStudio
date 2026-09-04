"""NovelBuddy novel source connector (spec 2026-09-04-novels-design §4).

Probed FROM THE VPS (production egress/TLS, 2026-09-04): browse, search,
title detail, chapter list and chapter text all answer 200 with plain httpx —
no Cloudflare interstitial from the OVH egress. English translated web novels
and light novels, updated daily; the same aggregator family as the existing
``freewebnovel`` and ``novelfull`` connectors, and the one of the three with
a catalogue an actual reader would use.

Everything is read from the site's public JSON API (``api.novelbuddy.me``)
rather than its Next.js HTML — see ``mappers`` for why, and for the robots
verdict on both hosts.

Request budget:

* browse / search: **1 request**.
* ``get_series``: **1 request** (``/titles/<hsid>``), then cached.
* ``get_chapters``: **1 request** for the WHOLE list however long it is
  (verified against a 1,230-chapter title), then cached.
* ``chapter_text``: **1 request** per chapter, and ``novel_chapter_cache``
  keeps it server-side afterwards.

Novel connector contract: ``CONTENT_KIND = "novel"``, ``chapter_text()``
returns sanitized plain-text paragraphs; ``get_chapter_pages`` is meaningless
(novels have no page images) and returns ``[]``.
"""

from __future__ import annotations

import logging
import re

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
from connectors.novelbuddy.mappers import (
    API_BASE,
    CHAPTER_LIMIT,
    SITE_BASE,
    browse_params,
    chapter_path,
    chapters_path,
    normalize_chapter_key,
    normalize_series_key,
    parse_chapter,
    parse_chapters,
    parse_title,
    parse_title_list,
    series_path,
)

logger = logging.getLogger(__name__)


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses; a plain 404 surfaces re-wrapped with ``status_code=None`` and
    httpx's ``raise_for_status`` text ("Client error '404 Not Found' for
    url ..."), so match both forms — a bare ``status_code == 404`` check is
    dead code against this client, as royalroad/freewebnovel/archiveorg all
    document.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


def _is_rejected_key(exc: ConnectorHttpError) -> bool:
    """True when the API refused the identifier itself (HTTP 400).

    ``/titles/<id>`` validates its path segment as a Sqid and answers 400
    ("Title ID must be a valid Sqid") for anything else — a stale or
    hand-edited key. To a reader that means the same as a missing series, so
    it is mapped to None rather than raised as a network failure, which the
    novel service would otherwise answer from stale cache forever.
    """
    return exc.status_code == 400 or "400 Bad Request" in str(exc)


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
API_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    # The API is the site's own backend and expects the site as its caller.
    "Origin": SITE_BASE,
    "Referer": f"{SITE_BASE}/",
}


class NovelBuddyConnector(SourceConnector):
    """Browse and read English translated web novels from NovelBuddy."""

    SOURCE_TYPE = "novelbuddy"
    DISPLAY_NAME = "NovelBuddy"
    DESCRIPTION = (
        "Browse and read English translated web novels and light novels from "
        "NovelBuddy — cultivation, LitRPG, regression and romance, updated "
        "daily. Chapter text is served as clean plain-text paragraphs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False
    CONTENT_KIND = "novel"
    LANGUAGE = "en"

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            API_BASE,
            user_agent=BROWSER_USER_AGENT,
            headers=API_HEADERS,
        )
        # Detail and chapter list are separate endpoints, so they get separate
        # caches; both are read repeatedly while a reader walks a series.
        self._series_cache: TTLCache[Series | None] = TTLCache(ttl_seconds=300.0)
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
        # Covers are served from rs.novelbuddy.me; the site domains cover the
        # CDN subdomain and the .com alias without widening past this source.
        return frozenset({"novelbuddy.me", "novelbuddy.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Most Read"),
            BrowseMode(id="trending", label="Trending This Week"),
            BrowseMode(id="latest", label="Latest Updates"),
            BrowseMode(id="newest", label="Newly Added"),
            BrowseMode(id="rating", label="Top Rated"),
        ]

    # --- listings (1 request) ---------------------------------------------

    def _listing(
        self, query: str | None, page: int, sort: str | None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        payload = self._http.get_json(
            "/titles/search", params=browse_params(query, page, sort)
        )
        listing = parse_title_list(payload, page=page)
        logger.info(
            "NovelBuddy listing q=%r page=%d sort=%s count=%d has_more=%s",
            query or "",
            page,
            sort or "default",
            len(listing.items),
            listing.has_more,
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._listing(None, page, sort)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing(normalized, page, sort)

    # --- detail -------------------------------------------------------------

    def get_series(self, series_id: str) -> Series | None:
        series_key = normalize_series_key(series_id)
        if not series_key:
            return None
        cached = self._series_cache.get(series_key)
        if cached is not None:
            return cached
        try:
            payload = self._http.get_json(series_path(series_key))
        except ConnectorHttpError as exc:
            logger.warning("NovelBuddy detail %s failed: %s", series_key, exc)
            if _is_not_found(exc) or _is_rejected_key(exc):
                return None
            raise
        series = parse_title(payload, series_key)
        if series is not None:
            self._series_cache.set(series_key, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        series_key = normalize_series_key(series_id)
        if not series_key:
            return []
        cached = self._chapters_cache.get(series_key)
        if cached is not None:
            return list(cached)
        try:
            payload = self._http.get_json(
                chapters_path(series_key), params={"limit": CHAPTER_LIMIT}
            )
        except ConnectorHttpError as exc:
            logger.warning("NovelBuddy chapters %s failed: %s", series_key, exc)
            if _is_not_found(exc) or _is_rejected_key(exc):
                return []
            raise
        chapters = parse_chapters(payload, series_key)
        if chapters:
            self._chapters_cache.set(series_key, chapters)
        logger.info("NovelBuddy chapters %s count=%d", series_key, len(chapters))
        return list(chapters)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        # Novels have no page images; the reader goes through /novels/chapter.
        return []

    def find_page(self, page_id: str) -> Page | None:
        return None

    # --- chapter text -------------------------------------------------------

    def chapter_text(self, series_key: str, chapter_key: str) -> NovelChapterText | None:
        path = chapter_path(series_key, chapter_key)
        try:
            payload = self._http.get_json(path)
        except ConnectorHttpError as exc:
            if _is_not_found(exc) or _is_rejected_key(exc):
                logger.warning("NovelBuddy chapter %s not found", path)
                return None
            raise
        text = parse_chapter(payload)
        if text is None:
            logger.warning("NovelBuddy chapter %s did not parse", path)
            return None
        if not looks_english(text.paragraphs):
            # Aggregators occasionally leak an untranslated raw; caching it
            # would pin garbage in novel_chapter_cache for a week.
            logger.warning("NovelBuddy chapter %s failed the English check", path)
            return None
        if text.chapter_number is None:
            number = _number_from_chapter_key(normalize_chapter_key(chapter_key))
            if number is not None:
                text = NovelChapterText(
                    title=text.title,
                    paragraphs=text.paragraphs,
                    chapter_number=number,
                )
        logger.info(
            "NovelBuddy chapter %s paragraphs=%d words=%d",
            path,
            len(text.paragraphs),
            text.word_count,
        )
        return text


def _number_from_chapter_key(chapter_key: str) -> float | None:
    """Best-effort chapter number from a slug like ``<hsid>/chapter-268-...``.

    Only a fallback for a chapter whose payload carries no ``number``; the
    novel service backfills the authoritative number from the chapter list.
    """
    slug = chapter_key.split("/", 1)[1] if "/" in chapter_key else chapter_key
    match = re.search(r"chapter[-_]?(\d+(?:\.\d+)?)", slug, re.IGNORECASE)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None
