from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.rate_limit import limiter, sources_limit
from services.browse_service import BrowseService, get_browse_service
from services.reader_service import ReaderService, get_reader_service
from services.source_pin_service import (
    SourcePinService,
    get_source_pin_service,
    require_source_pin_service,
)
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/sources", tags=["sources"])


BrowseDep = Annotated[BrowseService, Depends(get_browse_service)]
ReaderDep = Annotated[ReaderService, Depends(get_reader_service)]
PinDep = Annotated[SourcePinService, Depends(get_source_pin_service)]
PinWriteDep = Annotated[SourcePinService, Depends(require_source_pin_service)]


class SourcePinsUpdate(BaseModel):
    """The complete pinned set, in the order it should be displayed."""

    source_ids: list[str] = Field(default_factory=list)


@router.get("")
def list_sources(service: BrowseDep, response: Response) -> list[dict[str, object]]:
    """List installed browsable source connectors."""
    items = service.list_sources()
    set_list_total_header(response, len(items))
    return items


# NOTE: this literal ``/search`` route MUST be declared before the
# ``/{source_id}/...`` routes below so "search" is never captured as a
# ``source_id`` path parameter.
@router.get("/search")
async def federated_search(
    request: Request,
    service: BrowseDep,
    q: str = Query("", description="Search query"),
    page: int = Query(1, ge=1),
    per_page: int = Query(40, ge=1, le=200),
) -> dict[str, object]:
    """Search every browsable source in parallel.

    Source-native: there is no local catalog to search — the library is the
    per-profile ``followed_series`` set, searched via ``GET /library/search``.
    """
    return await service.federated_search(
        q.strip(),
        page=page,
        per_page=per_page,
        include_mature=service._gate_open(),
        base_url=str(request.base_url),
    )


# NOTE: like ``/search`` above, this literal route MUST stay ahead of the
# ``/{source_id}/...`` routes or FastAPI captures "health" as a source id.
@router.get("/health")
def list_source_health(service: BrowseDep, response: Response) -> list[dict[str, object]]:
    """List sources with their recorded reachability, worst first.

    Same rows and same 18+ gate as ``GET /sources`` -- health is stored
    globally (a site being down is a property of the site) but is only ever
    read back through the caller's own gated source list, so a mature source's
    health never reaches a profile that cannot see the source.

    Nothing is hidden here: a dead source is listed and flagged, because the
    failure this endpoint exists to fix is a source dying silently.
    """
    items = service.list_source_health()
    set_list_total_header(response, len(items))
    return items


# NOTE: like ``/search`` above, both literal ``/pins`` routes MUST stay ahead of
# the ``/{source_id}/...`` routes or FastAPI captures "pins" as a source id.
@router.get("/pins")
def list_source_pins(service: PinDep, response: Response) -> list[dict[str, object]]:
    """Return the caller's pinned sources, ordered."""
    items = service.list_pins()
    set_list_total_header(response, len(items))
    return items


@router.put("/pins")
def replace_source_pins(
    payload: SourcePinsUpdate,
    service: PinWriteDep,
    response: Response,
) -> list[dict[str, object]]:
    """Replace the pinned set with exactly the sources given, in that order."""
    items = service.replace_pins(payload.source_ids)
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


@router.get("/{source_id}/series/{series_id:path}/cover")
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
    service: ReaderDep,
) -> dict[str, object]:
    """Return the online reader payload for a chapter, straight from the source."""
    return service.resolve_source_chapter(source_id, series_id, chapter_id)
