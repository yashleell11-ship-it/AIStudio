from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.rate_limit import limiter, sources_limit
from services.browse_service import BrowseService, get_browse_service
from services.reader_service import ReaderService, get_reader_service
from services.source_cache_service import (
    SourceCacheService,
    get_source_cache_service,
    live_cache_info,
)
from services.source_pin_service import (
    SourcePinService,
    get_source_pin_service,
    require_source_pin_service,
)
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/sources", tags=["sources"])


BrowseDep = Annotated[BrowseService, Depends(get_browse_service)]
CacheDep = Annotated[SourceCacheService, Depends(get_source_cache_service)]
ReaderDep = Annotated[ReaderService, Depends(get_reader_service)]
PinDep = Annotated[SourcePinService, Depends(get_source_pin_service)]
PinWriteDep = Annotated[SourcePinService, Depends(require_source_pin_service)]


class SourcePinsUpdate(BaseModel):
    """The complete pinned set, in the order it should be displayed."""

    source_ids: list[str] = Field(default_factory=list)


def _image_proxy_headers() -> dict[str, str]:
    """Response headers for the two byte-proxying routes.

    The service layer already clamps the media type to a bitmap allowlist;
    these headers stop a browser from second-guessing it (nosniff), neuter any
    markup that does get through (CSP sandbox: no script, no same-origin
    access), and keep a top-level navigation from treating the body as a page
    of ours (Content-Disposition).
    """
    return {
        "Cache-Control": "max-age=86400",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Content-Disposition": "inline; filename=image",
    }


# A cover is effectively immutable per URL (the URL embeds the series key, and
# a source swapping a cover is rare), so it gets a long ``public`` max-age:
# the client caches it locally, Cloudflare may cache it at the edge, and both
# stop re-proxying the same bytes through the VPS. ``public`` is load-bearing —
# without it an edge will not cache an authenticated response. No cover bytes
# are ever stored server-side (spec: the VPS never holds image bytes); only
# these headers change.
_COVER_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days


def _etag_for(data: bytes) -> str:
    """Strong validator derived from the actual bytes served."""
    return f'"{hashlib.sha256(data).hexdigest()[:32]}"'


def _if_none_match_hits(header: str | None, etag: str) -> bool:
    """RFC 9110 ``If-None-Match``: ``*``, or a comma-separated list where any
    entry (weak-compared, so ``W/`` prefixes are ignored) equals our ETag."""
    if not header:
        return False
    if header.strip() == "*":
        return True
    for candidate in header.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


def _conditional_image_response(
    request: Request,
    media_type: str,
    data: bytes,
    headers: dict[str, str],
) -> Response:
    """200 with the bytes, or 304 if the client already holds them.

    The upstream fetch has still happened by the time we are here (no bytes
    are stored server-side to validate against), so the 304 saves egress and
    lets clients/edges revalidate a long-lived cache entry — it does not save
    the origin fetch. Every hardening header stays on both status codes.
    """
    etag = _etag_for(data)
    headers = {**headers, "ETag": etag}
    if _if_none_match_hits(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=data, media_type=media_type, headers=headers)


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
@limiter.limit(sources_limit)
async def federated_search(
    request: Request,
    response: Response,
    service: BrowseDep,
    q: str = Query("", description="Search query"),
    page: int = Query(1, ge=1),
    per_page: int = Query(40, ge=1, le=200),
) -> dict[str, object]:
    """Search every browsable source in parallel.

    Rate-limited on the ``sources`` bucket: one request here fans out to *every*
    installed connector at once, so it is the most expensive thing an
    unthrottled caller can ask this box to do.

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
    cache: CacheDep,
    request: Request,
    response: Response,
    page: int = Query(1, ge=1),
    query: str | None = Query(None),
    sort: str | None = Query(None),
    genre: str | None = Query(None),
    refresh: bool = Query(False, description="Bypass the cache and refetch live"),
) -> dict[str, object]:
    """List or search series from an online source.

    Plain browses (no ``query``) are served through ``source_browse_cache``:
    a repeat visit within the TTL never touches the connector, and a dead
    connector serves the last known page flagged stale instead of a 502. The
    response carries a ``cache`` block — ``{"status": "fresh"|"live"|"stale",
    "stale": bool, "fetched_at": ISO-8601 UTC}`` — so clients can badge stale
    grids. Searches bypass the cache (unbounded key cardinality) and always
    report ``status: "live"``. ``refresh=true`` forces a live refetch.
    """
    normalized_query = query.strip() if query else None
    if normalized_query:
        listing = service.list_series(
            source_id, page=page, query=normalized_query, sort=sort, genre=genre
        )
        listing["cache"] = live_cache_info()
        return listing
    return cache.get_browse_page(
        source_id, page=page, sort=sort, genre=genre, force=refresh, warm_next=True
    )


# --- key-bearing routes ----------------------------------------------------
#
# CONTRACT: every ``{series_id}`` / ``{chapter_id}`` / ``{page_id}`` below is a
# ``:path`` parameter, because connector keys are opaque strings that contain
# slashes and percent-encoding (see docs/CLAUDE_HANDOFF.md §2). The ASGI server
# percent-decodes before routing, so a ``%2F`` in a key reaches the router as a
# real ``/`` and a plain segment converter simply 404s. ``fully_unquote`` is
# applied uniformly downstream (browse_service / reader_service), so ``:path``
# costs nothing and the mixture used to mean the same key worked on one route
# and 404'd on the next.
#
# ``:path`` is greedy, so ORDER MATTERS: the suffixed routes must be declared
# before the bare ``/{series_id:path}`` detail route or it swallows their
# suffixes. Do not reorder these without re-reading this comment.
#
# A ``@limiter.limit`` route that returns a dict rather than a ``Response`` MUST
# also take ``response: Response`` — slowapi injects its X-RateLimit-* headers
# into that object and raises at request time if it is missing.


@router.get("/{source_id}/series/{series_id:path}/chapters/{chapter_id:path}/reader")
@limiter.limit(sources_limit)
def get_source_reader_chapter(
    source_id: str,
    series_id: str,
    chapter_id: str,
    service: ReaderDep,
    request: Request,
    response: Response,
) -> dict[str, object]:
    """Return the online reader payload for a chapter, straight from the source."""
    return service.resolve_source_chapter(source_id, series_id, chapter_id)


@router.get("/{source_id}/series/{series_id:path}/chapters")
@limiter.limit(sources_limit)
def get_source_chapters(
    source_id: str,
    series_id: str,
    service: BrowseDep,
    request: Request,
    response: Response,
) -> list[dict[str, object]]:
    """Return chapters for a series from an online source.

    Rate-limited: triggers up to four upstream fetches and runs on the sync
    threadpool, so with no ceiling a caller looping cache-busted keys against
    a dead upstream could pin every worker in retry cycles (audit finding 9).
    """
    items = service.get_chapters(source_id, series_id)
    set_list_total_header(response, len(items))
    return items


@router.get("/{source_id}/series/{series_id:path}/cover")
@limiter.limit(sources_limit)
def get_source_series_cover(
    source_id: str,
    series_id: str,
    service: BrowseDep,
    request: Request,
) -> Response:
    """Proxy a series cover image from an online source.

    Rate-limited: this and the page-image proxy are the two routes that stream
    third-party bytes through the box, so on a metered VPS they are the ones
    that most need a ceiling.

    Covers get the long-lived cacheable treatment (see _COVER_MAX_AGE_SECONDS)
    plus an ETag with 304 handling, so browsing the same grid twice costs the
    box nothing after the first paint.
    """
    media_type, data = service.resolve_series_cover(source_id, series_id)
    headers = {
        **_image_proxy_headers(),
        "Cache-Control": f"public, max-age={_COVER_MAX_AGE_SECONDS}",
    }
    return _conditional_image_response(request, media_type, data, headers)


@router.get("/{source_id}/series/{series_id:path}")
@limiter.limit(sources_limit)
def get_source_series(
    source_id: str,
    series_id: str,
    service: BrowseDep,
    request: Request,
    response: Response,
) -> dict[str, object]:
    """Return series metadata from an online source. Rate-limited — upstream
    fetch on the sync threadpool (audit finding 9; see the chapters route).

    Declared last of the ``/series/...`` routes — see the CONTRACT note above.
    """
    return service.get_series(source_id, series_id)


@router.get("/{source_id}/chapters/{chapter_id:path}/pages")
@limiter.limit(sources_limit)
def get_source_chapter_pages(
    source_id: str,
    chapter_id: str,
    service: BrowseDep,
    request: Request,
    response: Response,
) -> list[dict[str, object]]:
    """Return pages for a chapter from an online source. Rate-limited —
    upstream fetch on the sync threadpool (audit finding 9)."""
    return service.get_chapter_pages(source_id, chapter_id)


@router.get("/{source_id}/pages/{page_id:path}/image")
@limiter.limit(sources_limit)
def get_source_page_image(
    source_id: str,
    page_id: str,
    service: BrowseDep,
    request: Request,
) -> Response:
    """Proxy a page image from an online source. Rate-limited — see the cover
    proxy above; this is the hot one, several dozen requests per chapter read.

    Gets the same ETag/304 revalidation as covers (saves egress on re-reads)
    but keeps the shorter, non-``public`` Cache-Control: page bytes are the
    actual chapter content, so they stay out of shared edge caches.
    """
    media_type, data = service.resolve_page_image(source_id, page_id)
    return _conditional_image_response(
        request, media_type, data, _image_proxy_headers()
    )
