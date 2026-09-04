"""Doujins.com online source connector (custom HTML + folders JSON API)."""

from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import time
from typing import Any
from urllib.parse import unquote

from connectors.base import SourceConnector
from connectors.doujins.mappers import (
    HOME_PAGE_SIZE,
    MAX_DAY_LOOKBACK,
    SITE_BASE,
    TOP_PAGE_SIZE,
    extract_csrf_token,
    gallery_path,
    normalize_path,
    page_id_series_id,
    paginate_series,
    parse_chapters,
    parse_folders_payload,
    parse_gallery_pages,
    parse_html_listing,
    parse_searchbox_payload,
    parse_series_detail,
)
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

logger = logging.getLogger(__name__)

#: Day panes fetched together on a cold "latest" build. The exit test below
#: cannot fire before day 8, so these eight calls are unconditional.
_EAGER_DAYS = 8
_DAY_WORKERS = 8

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class DoujinsConnector(SourceConnector):
    """Browse and read English-translated doujinshi from doujins.com."""

    SOURCE_TYPE = "doujins"
    DISPLAY_NAME = "Doujins"
    DESCRIPTION = (
        "Browse and read English-translated hentai doujinshi from Doujins.com. "
        "Images are proxied through ManhwaManiacs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            headers=HTML_HEADERS,
            user_agent=BROWSER_USER_AGENT,
            min_interval=0.35,
            # The "latest" listing is assembled from one /folders call per DAY
            # (see _collect_latest_series); without a matching burst the rate
            # limiter would space the first batch 0.35s apart and undo the
            # fan-out. Long-run request rate is unchanged.
            burst=_DAY_WORKERS,
        )
        self._series_cache: TTLCache[Series] = TTLCache(ttl_seconds=300.0)
        self._chapter_list_cache: TTLCache[list[Chapter]] = TTLCache(ttl_seconds=180.0)
        self._page_cache: TTLCache[list[Page]] = TTLCache(ttl_seconds=600.0)
        self._latest_cache: TTLCache[list[Series]] = TTLCache(ttl_seconds=120.0)
        self._top_cache: TTLCache[list[Series]] = TTLCache(ttl_seconds=300.0)

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
        return frozenset({"static.doujins.com"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/"}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="latest", label="Latest"),
            BrowseMode(id="popular", label="Popular"),
        ]

    def _fetch_html(self, path: str) -> str:
        return self._http.get_text(path)

    def _fetch_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._http.get_json(path, params=params)
        if not isinstance(payload, dict):
            raise ConnectorHttpError("Expected JSON object from Doujins.")
        return payload

    def _normalize_series_id(self, series_id: str) -> str:
        return normalize_path(series_id)

    def _utc_day_bounds(self, day_offset: int) -> tuple[int, int]:
        now = int(time.time())
        start_today = now - (now % 86400)
        start = start_today - day_offset * 86400
        return start, start + 86400

    def _collect_latest_series(self) -> list[Series]:
        cached = self._latest_cache.get("latest")
        if cached is not None:
            return cached

        items: list[Series] = []
        seen: set[str] = set()

        def _absorb(day_offset: int, payload: dict[str, Any] | None) -> None:
            if payload is None:
                return
            for series in parse_folders_payload(payload):
                if series.id in seen:
                    continue
                seen.add(series.id)
                items.append(series)

        # The loop below can never stop before day 8 (its exit test requires
        # ``day_offset >= 7``), so those eight /folders calls are unconditional
        # and independent — fetch them together instead of one at a time.
        # Measured from the VPS this stage was 8 serial requests / 2.80s.
        # Merged in DAY ORDER so the listing (and therefore its pagination and
        # its first-seen dedup) is byte-identical to the serial version.
        first_batch = list(range(min(_EAGER_DAYS, MAX_DAY_LOOKBACK)))
        for day_offset, payload in self._fetch_days(first_batch):
            _absorb(day_offset, payload)

        if not (len(first_batch) >= 8 and len(items) >= HOME_PAGE_SIZE * 2):
            for day_offset in range(len(first_batch), MAX_DAY_LOOKBACK):
                start, end = self._utc_day_bounds(day_offset)
                try:
                    payload = self._fetch_json(
                        "/folders",
                        params={"start": start, "end": end},
                    )
                except ConnectorHttpError:
                    logger.warning(
                        "Doujins folders day offset=%d failed",
                        day_offset,
                        exc_info=True,
                    )
                    continue
                _absorb(day_offset, payload)
                # Homepage typically exposes ~20 day panes; stop once we have a
                # solid catalog.
                if day_offset >= 7 and len(items) >= HOME_PAGE_SIZE * 2:
                    break

        self._latest_cache.set("latest", items)
        return items

    def _fetch_days(
        self, day_offsets: list[int]
    ) -> list[tuple[int, dict[str, Any] | None]]:
        """Fetch several /folders day panes at once, returned in day order.

        A failed day yields ``None`` — the same treatment the serial loop gave
        it (``continue``), so one bad day still leaves the rest of the catalog
        intact rather than emptying the listing.
        """
        if not day_offsets:
            return []
        results: dict[int, dict[str, Any] | None] = {}

        def _one(day_offset: int) -> dict[str, Any]:
            start, end = self._utc_day_bounds(day_offset)
            return self._fetch_json("/folders", params={"start": start, "end": end})

        with cf.ThreadPoolExecutor(
            max_workers=min(_DAY_WORKERS, len(day_offsets)),
            thread_name_prefix="doujins-folders",
        ) as pool:
            futures = {pool.submit(_one, day): day for day in day_offsets}
            for future in cf.as_completed(futures):
                day = futures[future]
                try:
                    results[day] = future.result()
                except ConnectorHttpError:
                    logger.warning(
                        "Doujins folders day offset=%d failed", day, exc_info=True
                    )
                    results[day] = None
        return [(day, results.get(day)) for day in day_offsets]

    def _collect_popular_series(self) -> list[Series]:
        cached = self._top_cache.get("top")
        if cached is not None:
            return cached
        document = self._fetch_html("/top")
        items = parse_html_listing(document)
        self._top_cache.set("top", items)
        return items

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        mode = (sort or "latest").strip().casefold()
        if mode in {"popular", "top", "top_rated", "rating"}:
            items = self._collect_popular_series()
            page_size = TOP_PAGE_SIZE
        else:
            items = self._collect_latest_series()
            page_size = HOME_PAGE_SIZE
        listing = paginate_series(items, page=page, page_size=page_size)
        logger.info(
            "Doujins browse sort=%r page=%d count=%d has_more=%s",
            sort,
            page,
            len(listing.items),
            listing.has_more,
        )
        return listing

    def _csrf_headers(self) -> tuple[str, dict[str, str]]:
        home = self._fetch_html("/")
        token = extract_csrf_token(home)
        if not token:
            raise ConnectorHttpError("Doujins CSRF token missing from homepage.")
        xsrf = ""
        try:
            raw = self._http._client.cookies.get("XSRF-TOKEN")  # noqa: SLF001
            if raw:
                xsrf = unquote(str(raw))
        except Exception:  # noqa: BLE001
            xsrf = ""
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-TOKEN": token,
            "Referer": f"{SITE_BASE}/",
        }
        if xsrf:
            headers["X-XSRF-TOKEN"] = xsrf
        return token, headers

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        # Site searchbox returns a single suggestion page (no pagination).
        if page > 1:
            return PaginatedSeriesList(items=[], page=page, page_size=HOME_PAGE_SIZE, total=0)

        token, headers = self._csrf_headers()
        raw = self._http.post_text(
            "/searchbox",
            data={"q": normalized, "_token": token},
            extra_headers=headers,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConnectorHttpError("Doujins searchbox returned non-JSON.") from exc
        if not isinstance(payload, dict):
            raise ConnectorHttpError("Doujins searchbox returned unexpected payload.")
        items = parse_searchbox_payload(payload)
        logger.info(
            "Doujins search page=%d count=%d query=%r",
            page,
            len(items),
            normalized,
        )
        return PaginatedSeriesList(
            items=items,
            page=1,
            page_size=max(len(items), 1),
            total=len(items),
            api_has_more=False,
        )

    def get_series(self, series_id: str) -> Series | None:
        path = self._normalize_series_id(series_id)
        cached = self._series_cache.get(path)
        if cached is not None:
            return cached
        try:
            document = self._fetch_html(gallery_path(path))
        except ConnectorHttpError:
            return None
        series = parse_series_detail(document, series_id=path)
        if series is None:
            return None
        self._series_cache.set(path, series)
        return series

    def get_chapters(self, series_id: str) -> list[Chapter]:
        path = self._normalize_series_id(series_id)
        return self._chapter_list_cache.get_or_set(
            path,
            lambda: self._fetch_chapters(path),
        )

    def _fetch_chapters(self, path: str) -> list[Chapter]:
        try:
            document = self._fetch_html(gallery_path(path))
        except ConnectorHttpError:
            return []
        return parse_chapters(document, series_id=path)

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        path = self._normalize_series_id(chapter_id)
        return self._page_cache.get_or_set(
            path,
            lambda: self._fetch_chapter_pages(path),
        )

    def _fetch_chapter_pages(self, path: str) -> list[Page]:
        try:
            document = self._fetch_html(gallery_path(path))
        except ConnectorHttpError:
            return []
        return parse_gallery_pages(document, series_id=path)

    def find_page(self, page_id: str) -> Page | None:
        series_id = page_id_series_id(page_id)
        if series_id is None:
            return None
        for page in self.get_chapter_pages(series_id):
            if page.id == page_id:
                return page
        return None
