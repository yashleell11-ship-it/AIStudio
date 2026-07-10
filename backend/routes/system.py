"""System/status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.config import get_settings
from routes.app_distribution import render_landing_html

router = APIRouter(tags=["system"])


class SystemStatus(BaseModel):
    status: str
    name: str
    version: str


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
    """Mobile-friendly health probe (JSON status)."""
    return _status()
