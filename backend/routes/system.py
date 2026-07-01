"""System/status endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core.config import get_settings

router = APIRouter(tags=["system"])


class SystemStatus(BaseModel):
    status: str
    name: str
    version: str


@router.get("/", response_model=SystemStatus)
def get_status() -> SystemStatus:
    settings = get_settings()
    return SystemStatus(
        status="online",
        name=settings.project_name,
        version=settings.version,
    )


@router.get("/health", response_model=SystemStatus)
def health_check() -> SystemStatus:
    """Mobile-friendly health probe (same payload as GET /)."""
    return get_status()
