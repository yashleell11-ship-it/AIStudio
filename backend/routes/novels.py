"""Novel chapter-text endpoint (spec 2026-09-04-novels-design §3).

DARK IN PRODUCTION: this router is only mounted when MM_NOVELS_ENABLED is on
(see ``create_app``), so on an unflagged deployment ``/novels/*`` is a stock
404 — indistinguishable from a route that was never built, which is the
point. The router-level dependency below re-checks the flag as belt and
braces for any process whose settings flipped after mount.

Browse/search/detail for novel sources need no routes of their own: a novel
source is a source, so the existing ``/sources/*`` surface serves them the
moment the registry gate lets the connectors through.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import get_settings
from core.rate_limit import limiter, sources_limit
from services.novel_service import NovelService, get_novel_service


def require_novels_enabled() -> None:
    """404 (the stock not-found shape) when the novels flag is off."""
    if not bool(getattr(get_settings(), "novels_enabled", False)):
        raise StarletteHTTPException(status_code=404, detail="Not Found")


router = APIRouter(
    prefix="/novels",
    tags=["novels"],
    dependencies=[Depends(require_novels_enabled)],
)

NovelDep = Annotated[NovelService, Depends(get_novel_service)]


@router.get("/chapter")
@limiter.limit(sources_limit)
def get_novel_chapter(
    request: Request,
    response: Response,  # slowapi injects X-RateLimit-* headers into this
    service: NovelDep,
    source: str = Query(..., min_length=1, max_length=64),
    series: str = Query(..., min_length=1, max_length=512),
    chapter: str = Query(..., min_length=1, max_length=512),
) -> dict[str, object]:
    """One chapter as sanitized plain-text paragraphs.

    ``{title, chapter_number, paragraphs: [str], prev, next, word_count}``
    plus the identity triple and the standard ``cache`` block. Query-param
    identity (like ``/reader/chapter/manifest``) because connector keys are
    opaque strings that may contain slashes and percent-encoding.

    Rate-limited on the ``sources`` bucket — a cache miss is a full upstream
    page scrape on the sync threadpool.
    """
    return service.get_chapter(source, series, chapter)
