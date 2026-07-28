"""System/status endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.config import get_settings
from routes.app_distribution import render_landing_html
from services.browse_service import BrowseService, get_browse_service

router = APIRouter(tags=["system"])

BrowseDep = Annotated[BrowseService, Depends(get_browse_service)]


class SystemStatus(BaseModel):
    status: str
    name: str
    version: str


class SourceHealthSummary(BaseModel):
    """How many of the caller's sources are in each health state."""

    total: int
    ok: int
    failing: int
    dead: int
    unknown: int
    demoted: int


def _status() -> SystemStatus:
    settings = get_settings()
    return SystemStatus(
        status="online",
        name=settings.project_name,
        version=settings.version,
    )


@router.get("/", response_model=None)
def get_status(request: Request) -> SystemStatus | HTMLResponse:
    """Root endpoint.

    Browsers (``Accept: text/html``) get the phone-friendly APK install page;
    API clients keep receiving the unchanged JSON status payload, so existing
    integrations and the ``/health`` probe are unaffected.
    """
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(render_landing_html())
    return _status()


@router.get("/health", response_model=SystemStatus)
def health_check() -> SystemStatus:
    """Mobile-friendly health probe (JSON status).

    Deliberately unchanged: ``/`` and ``/health`` are the only two public
    (unauthenticated) routes on the API, so source health -- which says how many
    connectors this install has and how many are dead -- does not belong here.
    It is served from the authenticated route below instead.
    """
    return _status()


@router.get("/system/source-health", response_model=SourceHealthSummary)
def source_health_summary(service: BrowseDep) -> SourceHealthSummary:
    """Aggregate source reachability, for the status page's one-line banner.

    The per-source detail lives at ``GET /sources/health``; this is the count a
    status header needs without pulling ~151 rows. Counted over the sources the
    caller can actually see, so the 18+ gate holds here too -- a profile with
    adult content off must not learn how many adult sources exist by reading a
    total.
    """
    return SourceHealthSummary(**service.source_health_summary())
