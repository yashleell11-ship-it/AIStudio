"""Browse online sources through connector implementations."""

from __future__ import annotations

import logging
from urllib.parse import quote

from core.config import get_settings
from core.errors import AppError
from connectors.base import SourceConnector
from connectors.ids import fully_unquote
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.registry import (
    create_connector,
    list_installed_connectors,
    registry_snapshot,
)
from services.outbound_security import validate_outbound_url

logger = logging.getLogger(__name__)


def _normalize_source_chapter_id(chapter_id: str) -> str:
    """Decode chapter IDs from URL paths (may contain ``/`` for some sources)."""
    return fully_unquote(chapter_id).strip().strip("/")


def _serialize_series(series: Series, source_id: str) -> dict[str, object]:
    return {
        "id": series.id,
        "source_id": source_id,
        "title": series.title,
        "chapter_count": series.chapter_count,
        "description": series.description,
        "author": series.author,
        "artist": series.artist,
        "status": series.status,
        "genres": list(series.genres),
        "latest_chapter": series.latest_chapter,
        "cover_url": f"/sources/{source_id}/series/{quote(series.id, safe='')}/cover",
    }


def _serialize_chapter(chapter: Chapter, source_id: str) -> dict[str, object]:
    return {
        "id": chapter.id,
        "source_id": source_id,
        "series_id": chapter.series_id,
        "title": chapter.title,
        "number": chapter.number,
        "page_count": chapter.page_count,
        "release_date": chapter.release_date,
    }


def _serialize_page(page: Page, source_id: str) -> dict[str, object]:
    return {
        "id": page.id,
        "chapter_id": page.chapter_id,
        "number": page.number,
        "width": page.width,
        "height": page.height,
        "image_url": f"/sources/{source_id}/pages/{quote(page.id, safe='')}/image",
    }


def _serialize_paginated(
    listing: PaginatedSeriesList,
    source_id: str,
) -> dict[str, object]:
    from utils.api_pagination import enrich_pagination_aliases

    return enrich_pagination_aliases(
        {
            "items": [_serialize_series(item, source_id) for item in listing.items],
            "page": listing.page,
            "page_size": listing.page_size,
            "total": listing.total,
            "total_pages": listing.total_pages,
            "has_more": listing.has_more,
        }
    )


class BrowseService:
    """Source-agnostic facade for browsing online catalogs."""

    def list_sources(self) -> list[dict[str, object]]:
        snapshot = registry_snapshot()
        descriptors = list_installed_connectors(
            browsable_only=True,
            include_mature=get_settings().mature_content_enabled,
        )
        logging.getLogger("uvicorn.error").info(
            "GET /sources registry_id=%s all_types=%s browsable_types=%s returning=%s",
            snapshot["registry_id"],
            snapshot["connector_types"],
            snapshot["browsable_types"],
            [descriptor.source_type for descriptor in descriptors],
        )
        return [
            {
                "id": descriptor.source_type,
                "source_id": descriptor.source_type,
                "name": descriptor.name,
                "description": descriptor.description,
                "browsable": descriptor.browsable,
                "supports_import": descriptor.supports_import,
            }
            for descriptor in descriptors
        ]

    def _get_connector(self, source_id: str) -> SourceConnector:
        try:
            connector = create_connector(source_id)
        except ValueError as exc:
            raise AppError(
                "Source not found.",
                code="source_not_found",
                status_code=404,
                details={"source_id": source_id},
            ) from exc
        if not connector.is_browsable:
            raise AppError(
                "Source is not browsable.",
                code="source_not_browsable",
                status_code=400,
                details={"source_id": source_id},
            )
        # A mature source is hidden entirely when the user has not opted into
        # adult content: report it as not-found rather than "forbidden" so its
        # existence isn't disclosed. This one check covers every read path
        # (browse, search, series, chapters, pages, reader, covers) because
        # they all resolve their connector here.
        if connector.is_mature and not get_settings().mature_content_enabled:
            raise AppError(
                "Source not found.",
                code="source_not_found",
                status_code=404,
                details={"source_id": source_id},
            )
        return connector

    def list_browse_modes(self, source_id: str) -> list[dict[str, str]]:
        connector = self._get_connector(source_id)
        return [{"id": mode.id, "label": mode.label} for mode in connector.list_browse_modes()]

    def list_series(
        self,
        source_id: str,
        *,
        page: int = 1,
        query: str | None = None,
        sort: str | None = None,
    ) -> dict[str, object]:
        connector = self._get_connector(source_id)
        normalized_query = query.strip() if query else None
        normalized_sort = sort.strip() if sort else None
        if normalized_sort == "default":
            normalized_sort = None
        if normalized_query:
            listing = connector.search_series(normalized_query, page, sort=normalized_sort)
            operation = "search"
        else:
            listing = connector.get_series_list(page, sort=normalized_sort)
            operation = "browse"

        logger.info(
            "%s source=%s page=%d sort=%r query=%r parsed=%d total=%d total_pages=%d has_more=%s",
            operation,
            source_id,
            page,
            normalized_sort,
            normalized_query,
            len(listing.items),
            listing.total,
            listing.total_pages,
            listing.has_more,
        )
        return _serialize_paginated(listing, source_id)

    def get_series(self, source_id: str, series_id: str) -> dict[str, object]:
        connector = self._get_connector(source_id)
        series = connector.get_series(fully_unquote(series_id))
        if series is None:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"source_id": source_id, "series_id": series_id},
            )
        return _serialize_series(series, source_id)

    def get_chapters(self, source_id: str, series_id: str) -> list[dict[str, object]]:
        connector = self._get_connector(source_id)
        series_id = fully_unquote(series_id)
        series = connector.get_series(series_id)
        if series is None:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"source_id": source_id, "series_id": series_id},
            )
        return [_serialize_chapter(chapter, source_id) for chapter in connector.get_chapters(series_id)]

    def get_chapter_pages(self, source_id: str, chapter_id: str) -> list[dict[str, object]]:
        connector = self._get_connector(source_id)
        normalized_chapter_id = _normalize_source_chapter_id(chapter_id)
        pages = connector.get_chapter_pages(normalized_chapter_id)
        if not pages:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
                details={"source_id": source_id, "chapter_id": normalized_chapter_id},
            )
        return [_serialize_page(page, source_id) for page in pages]

    def get_reader_chapter(
        self,
        source_id: str,
        series_id: str,
        chapter_id: str,
    ) -> dict[str, object]:
        connector = self._get_connector(source_id)
        normalized_chapter_id = _normalize_source_chapter_id(chapter_id)
        series_id = fully_unquote(series_id)
        series = connector.get_series(series_id)
        if series is None:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
            )

        chapters = connector.get_chapters(series_id)
        chapter = next((item for item in chapters if item.id == normalized_chapter_id), None)
        if chapter is None:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
            )

        pages = connector.get_chapter_pages(normalized_chapter_id)
        chapter_index = chapters.index(chapter)
        previous_chapter_id = chapters[chapter_index - 1].id if chapter_index > 0 else None
        next_chapter_id = (
            chapters[chapter_index + 1].id if chapter_index < len(chapters) - 1 else None
        )

        return {
            "mode": "remote",
            "source_id": source_id,
            "series_id": series_id,
            "id": normalized_chapter_id,
            "title": chapter.title,
            "number": chapter.number,
            "page_count": len(pages),
            "pages": [_serialize_page(page, source_id) for page in pages],
            "previous_chapter_id": previous_chapter_id,
            "next_chapter_id": next_chapter_id,
            "series_title": series.title,
        }

    def resolve_page_image(self, source_id: str, page_id: str) -> tuple[str, bytes]:
        connector = self._get_connector(source_id)
        normalized_page_id = fully_unquote(page_id).strip()
        page = connector.find_page(normalized_page_id)
        if page is None:
            raise AppError(
                "Page not found.",
                code="page_not_found",
                status_code=404,
                details={"source_id": source_id, "page_id": page_id},
            )
        return self._fetch_remote_image(page, connector)

    def resolve_series_cover(self, source_id: str, series_id: str) -> tuple[str, bytes]:
        connector = self._get_connector(source_id)
        series = connector.get_series(fully_unquote(series_id))
        if series is None or not series.cover_url:
            raise AppError(
                "Cover not found.",
                code="cover_not_found",
                status_code=404,
            )
        return self._fetch_url(series.cover_url, connector)

    def _fetch_remote_image(self, page: Page, connector: SourceConnector) -> tuple[str, bytes]:
        if not page.remote_url:
            raise AppError(
                "Remote page URL not available.",
                code="remote_url_missing",
                status_code=404,
            )
        return self._fetch_url(page.remote_url, connector)

    def _validate_outbound_url(self, url: str, connector: SourceConnector) -> str:
        return validate_outbound_url(url, connector)

    def _fetch_url(self, url: str, connector: SourceConnector) -> tuple[str, bytes]:
        import httpx

        self._validate_outbound_url(url, connector)

        try:
            # Redirects are not followed automatically: a redirect target
            # could point off the approved allowlist, silently bypassing it.
            # Connector headers (e.g. Referer) are required for CDNs that
            # enforce hotlink protection — bare GETs often return 403.
            response = httpx.get(
                url,
                timeout=30.0,
                follow_redirects=False,
                headers=connector.image_fetch_headers(),
            )
            if response.is_redirect:
                raise AppError(
                    "Remote host returned a redirect, which is not permitted.",
                    code="ssrf_blocked",
                    status_code=502,
                    details={"url": url},
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError(
                "Failed to fetch remote image.",
                code="remote_fetch_failed",
                status_code=502,
                details={"url": url, "reason": str(exc)},
            ) from exc

        media_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
        return media_type, response.content


def get_browse_service() -> BrowseService:
    return BrowseService()
