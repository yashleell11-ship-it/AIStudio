"""Wattpad novel source connector (spec 2026-09-04-novels-design §4).

Probed FROM THE VPS (production egress/TLS, 2026-09-04): the public JSON API
(``/api/v3/stories``, ``/api/v3/stories/<id>``) and the chapter-text endpoint
(``/apiv2/storytext``) all answer 200 with plain httpx and no token — no
Cloudflare interstitial, unlike Webnovel.com which is challenged from the same
egress. English serialized web fiction.

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
from connectors.wattpad.mappers import (
    DETAIL_FIELDS,
    SITE_BASE,
    list_params,
    normalize_chapter_key,
    normalize_series_key,
    novel_chapter_text,
    parse_story_detail,
    parse_story_list,
    story_path,
)

logger = logging.getLogger(__name__)


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the upstream said the story or part does not exist.

    Wattpad answers a missing id with **400**, not 404::

        GET /api/v3/stories/999999999999
        400 {"error_code":1017,"error_type":"NotFound","message":"Story not found"}
        GET /apiv2/storytext?id=999999999999
        400 {"result":"ERROR","code":463,"message":"Could not find any parts ..."}

    and 400 is not in the shared client's RETRYABLE_STATUS, so it surfaces
    re-wrapped with ``status_code=None`` carrying only httpx's message text.
    Both forms of both statuses are matched here; a bare
    ``exc.status_code == 404`` check would be dead code twice over.
    """
    if exc.status_code in (400, 404):
        return True
    message = str(exc)
    return "400 Bad Request" in message or "404 Not Found" in message


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
API_HEADERS = {
    # One client serves both the JSON API and the HTML chapter fragment.
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{SITE_BASE}/",
}


class WattpadConnector(SourceConnector):
    """Browse and read English serialized web fiction from Wattpad."""

    SOURCE_TYPE = "wattpad"
    DISPLAY_NAME = "Wattpad"
    DESCRIPTION = (
        "Browse and read English serialized web fiction from Wattpad. "
        "Chapter text is served as clean plain-text paragraphs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    # NOT a mature source: stories Wattpad flags mature are excluded from
    # listings and from detail lookups (see mappers.is_servable).
    MATURE = False
    CONTENT_KIND = "novel"
    LANGUAGE = "en"

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            user_agent=BROWSER_USER_AGENT,
            headers=API_HEADERS,
        )
        # One detail response carries BOTH story metadata and the full part
        # list, so the parsed pair is cached and shared by get_series,
        # get_chapters and chapter_text's title/number lookup.
        self._story_cache: TTLCache[tuple[Series | None, list[Chapter]]] = TTLCache(
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
        # Covers are served from img.wattpad.com — a subdomain, which the
        # image proxy's allowlist matches on the dot boundary.
        return frozenset({"wattpad.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Hot"),
            BrowseMode(id="new", label="New"),
            BrowseMode(id="featured", label="Featured"),
        ]

    def get_series_list(
        self, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        payload = self._http.get_json("/api/v3/stories", params=list_params(page, sort=sort))
        listing = parse_story_list(payload, page=page)
        logger.info(
            "Wattpad browse sort=%s page=%d count=%d has_more=%s",
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
        payload = self._http.get_json(
            "/api/v3/stories", params=list_params(page, query=normalized)
        )
        listing = parse_story_list(payload, page=page)
        logger.info(
            "Wattpad search %r page=%d count=%d", normalized, page, len(listing.items)
        )
        return listing

    def _fetch_story(self, series_key: str) -> tuple[Series | None, list[Chapter]]:
        series_key = normalize_series_key(series_key)
        cached = self._story_cache.get(series_key)
        if cached is not None:
            return cached
        try:
            payload = self._http.get_json(
                story_path(series_key), params={"fields": DETAIL_FIELDS}
            )
        except ConnectorHttpError as exc:
            logger.warning("Wattpad detail %s failed: %s", series_key, exc)
            if _is_not_found(exc):
                return None, []
            raise
        parsed = parse_story_detail(payload, series_key)
        if parsed[0] is not None:
            self._story_cache.set(series_key, parsed)
        return parsed

    def get_series(self, series_id: str) -> Series | None:
        return self._fetch_story(series_id)[0]

    def get_chapters(self, series_id: str) -> list[Chapter]:
        return self._fetch_story(series_id)[1]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        # Novels have no page images; the reader goes through /novels/chapter.
        return []

    def find_page(self, page_id: str) -> Page | None:
        return None

    def _part_metadata(self, series_key: str, chapter_key: str) -> tuple[str, float | None]:
        """Title and number for a part, from the story's own part list.

        The text endpoint returns prose and nothing else — no title, no
        number — so both come from the (cached) detail response. Best effort
        by design: a story that has since been pulled must not cost the
        reader a chapter that still serves its text.
        """
        try:
            _, chapters = self._fetch_story(series_key)
        except ConnectorHttpError as exc:
            logger.warning("Wattpad part metadata %s unavailable: %s", series_key, exc)
            return "", None
        for chapter in chapters:
            if chapter.id == chapter_key:
                return chapter.title, chapter.number
        return "", None

    def chapter_text(self, series_key: str, chapter_key: str) -> NovelChapterText | None:
        part_id = normalize_chapter_key(chapter_key)
        try:
            # NO ``page`` parameter: without it this returns the whole part,
            # with it a ~4.5 KB slice. See mappers module docstring.
            fragment = self._http.get_text("/apiv2/storytext", params={"id": part_id})
        except ConnectorHttpError as exc:
            if _is_not_found(exc):
                logger.warning("Wattpad part %s not found", part_id)
                return None
            raise
        title, number = self._part_metadata(series_key, part_id)
        text = novel_chapter_text(fragment, title=title, number=number)
        if text is None:
            logger.warning("Wattpad part %s did not parse", part_id)
            return None
        if not looks_english(text.paragraphs):
            # A story the API labels English can still serve a non-English
            # part — observed live on a story pulled from filter=hot.
            logger.warning("Wattpad part %s failed the English check", part_id)
            return None
        logger.info(
            "Wattpad part %s paragraphs=%d words=%d",
            part_id,
            len(text.paragraphs),
            text.word_count,
        )
        return text
