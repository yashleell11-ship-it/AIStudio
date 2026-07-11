from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import Response

from core.rate_limit import limiter, sources_limit
from services.browse_service import BrowseService, get_browse_service
from services.reading_service import ReadingService, get_reading_service
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/sources", tags=["sources"])


BrowseDep = Annotated[BrowseService, Depends(get_browse_service)]
ReadingDep = Annotated[ReadingService, Depends(get_reading_service)]


@router.get("")
def list_sources(service: BrowseDep, response: Response) -> list[dict[str, object]]:
    """List installed browsable source connectors."""
    items = service.list_sources()
    set_list_total_header(response, len(items))
    return items


@router.get("/{source_id}/browse-modes")
def list_browse_modes(source_id: str, service: BrowseDep) -> list[dict[str, str]]:
    """Return catalog sort modes supported by a source (popular, latest, etc.)."""
    return service.list_browse_modes(source_id)


@router.get("/{source_id}/genres")
def list_source_genres(source_id: str, service: BrowseDep) -> list[dict[str, str]]:
    """Return genre filters supported by a source."""
    return service.list_genres(source_id)


@router.get("/{source_id}/series")
@limiter.limit(sources_limit)
def list_source_series(
    source_id: str,
    service: BrowseDep,
    request: Request,
    response: Response,
    page: int = Query(1, ge=1),
    query: str | None = Query(None),
    sort: str | None = Query(None),
    genre: str | None = Query(None),
) -> dict[str, object]:
    """List or search series from an online source."""
    return service.list_series(source_id, page=page, query=query, sort=sort, genre=genre)


@router.get("/{source_id}/series/{series_id}")
def get_source_series(
    source_id: str,
    series_id: str,
    service: BrowseDep,
) -> dict[str, object]:
    """Return series metadata from an online source."""
    return service.get_series(source_id, series_id)


@router.get("/{source_id}/series/{series_id}/chapters")
def get_source_chapters(
    source_id: str,
    series_id: str,
    service: BrowseDep,
    response: Response,
) -> list[dict[str, object]]:
    """Return chapters for a series from an online source."""
    items = service.get_chapters(source_id, series_id)
    set_list_total_header(response, len(items))
    return items


@router.get("/{source_id}/series/{series_id}/cover")
@limiter.limit(sources_limit)
def get_source_series_cover(
    source_id: str,
    series_id: str,
    service: BrowseDep,
    request: Request,
) -> Response:
    """Proxy a series cover image from an online source."""
    media_type, data = service.resolve_series_cover(source_id, series_id)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get("/{source_id}/chapters/{chapter_id:path}/pages")
def get_source_chapter_pages(
    source_id: str,
    chapter_id: str,
    service: BrowseDep,
) -> list[dict[str, object]]:
    """Return pages for a chapter from an online source."""
    return service.get_chapter_pages(source_id, chapter_id)


@router.get("/{source_id}/pages/{page_id:path}/image")
@limiter.limit(sources_limit)
def get_source_page_image(
    source_id: str,
    page_id: str,
    service: BrowseDep,
    request: Request,
) -> Response:
    """Proxy a page image from an online source."""
    media_type, data = service.resolve_page_image(source_id, page_id)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "max-age=86400"},
    )


@router.get("/{source_id}/series/{series_id}/chapters/{chapter_id:path}/reader")
def get_source_reader_chapter(
    source_id: str,
    series_id: str,
    chapter_id: str,
    service: ReadingDep,
) -> dict[str, object]:
    """Return a unified reader payload, preferring local copies when available."""
    return service.resolve_source_chapter(source_id, series_id, chapter_id)
