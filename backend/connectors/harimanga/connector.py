"""HariManga connector — Madara browse with custom JSON chapter API and CDN images."""

from __future__ import annotations

import logging
import re
from typing import Any

from connectors.http.cf_client import CfSyncHttpClient
from connectors.http.client import ConnectorHttpError
from connectors.madara.config import MadaraSiteConfig
from connectors.madara.connector import MadaraConnector
from connectors.models import Chapter

logger = logging.getLogger(__name__)

HARIMANGA_CONFIG = MadaraSiteConfig(
    source_id="harimanga",
    display_name="HariManga",
    base_url="https://www.harimanga.vip",
    url_segment="manga",
    mature=False,
    use_cf=False,
    extra_image_hosts=frozenset({"img-r2.2xstorage.com", "2xstorage.com"}),
)

_CHAPTERS_API_RE = re.compile(r"window\.getChaptersUrl\s*=\s*'([^']+)'", re.I)


def parse_json_chapters(payload: dict[str, Any], series_id: str) -> list[Chapter]:
    """Map HariManga ``/api/comics/{slug}/chapters`` JSON to Chapter models."""
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    raw = data.get("chapters")
    if not isinstance(raw, list):
        return []

    chapters: list[Chapter] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        slug = item.get("chapter_slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        chapter_id = f"{series_id}/{slug.strip().strip('/')}"
        title = item.get("chapter_name")
        number = item.get("chapter_num")
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=str(title).strip() if title else slug,
                number=float(number) if number is not None else None,
                page_count=0,
            )
        )

    chapters.sort(key=lambda chapter: chapter.number if chapter.number is not None else 0.0)
    return chapters


class HariMangaConnector(MadaraConnector):
    """Madara catalog on harimanga.vip with JSON chapter list and 2xstorage CDN."""

    CONFIG = HARIMANGA_CONFIG
    SOURCE_TYPE = "harimanga"
    DISPLAY_NAME = "HariManga"
    DESCRIPTION = (
        "Browse and read from HariManga. "
        "Images are proxied through ManhwaManiacs."
    )
    MATURE = False

    def __init__(self) -> None:
        super().__init__()
        self._image_http = CfSyncHttpClient(
            self.CONFIG.base_url,
            impersonate="chrome131",
        )

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{self.CONFIG.base_url.rstrip('/')}/"}

    def fetch_proxied_image(self, url: str) -> tuple[str, bytes] | None:
        return self._image_http.get_bytes(url, extra_headers=self.image_fetch_headers())

    def _fetch_json_chapters(self, html: str, series_id: str) -> list[Chapter]:
        match = _CHAPTERS_API_RE.search(html)
        if match is None:
            return []
        api_url = match.group(1).strip()
        api_path = api_url
        base = self.CONFIG.base_url.rstrip("/")
        if api_url.startswith(base):
            api_path = api_url[len(base) :] or "/"
        try:
            payload = self._http.get_json(api_path)
        except ConnectorHttpError as exc:
            logger.info(
                "HariManga chapters API failed series=%s url=%s err=%s",
                series_id,
                api_url,
                exc,
            )
            return []
        if not payload.get("success"):
            return []
        chapters = parse_json_chapters(payload, series_id)
        logger.info(
            "HariManga JSON chapters series=%s count=%d",
            series_id,
            len(chapters),
        )
        return chapters

    def get_chapters(self, series_id: str) -> list[Chapter]:
        api_key = self._normalize_series_id(series_id)
        cached = self._chapter_list_cache.get(api_key)
        if cached is not None:
            return self._enrich_chapters(cached)

        path = self._html.series_id_to_path(api_key)
        try:
            html = self._http.get_text(path)
        except ConnectorHttpError:
            return []

        chapters = self._fetch_json_chapters(html, api_key)
        if not chapters:
            chapters = self._html.parse_chapters(html, api_key)
            manga_id = self._html.parse_manga_id(html)
            if manga_id:
                referer = f"{self.CONFIG.base_url.rstrip('/')}{path}"
                ajax_chapters = self._fetch_ajax_chapters(manga_id, api_key, referer)
                if len(ajax_chapters) > len(chapters):
                    chapters = ajax_chapters

        if chapters:
            self._chapter_list_cache.set(api_key, chapters)
        return self._enrich_chapters(chapters)
