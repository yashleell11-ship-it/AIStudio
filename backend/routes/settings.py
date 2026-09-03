"""Unified settings endpoint for mobile and desktop clients."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.config import get_settings, update_persisted_settings
from core.content_rating import resolve_mature_gate
from core.errors import AppError
from core.profile_context import (
    ACTIVE_PROFILE_HEADER,
    ProfileContext,
    resolve_profile_context,
)
from database.models import ReadingProfile, User
from database.session import get_db
from services.auth_service import get_current_user
from services.update_service import UpdateService, get_update_service

router = APIRouter(prefix="/settings", tags=["settings"])


def _update_service(db: Session = Depends(get_db)) -> UpdateService:
    return get_update_service(db)


UpdateDep = Annotated[UpdateService, Depends(_update_service)]
DbDep = Annotated[Session, Depends(get_db)]
ProfileDep = Annotated[ProfileContext, Depends(resolve_profile_context)]


def _mature_enabled(db: Session, ctx: ProfileContext) -> bool:
    """Active mature gate for this request. Thin alias so GET /settings echoes
    back exactly what every gated read path will act on."""
    return resolve_mature_gate(db, ctx.profile_id, ctx.user_id)


class UnifiedSettingsUpdate(BaseModel):
    updates_enabled: bool | None = None
    updates_check_interval_minutes: int | None = Field(default=None, ge=5)
    updates_notify_enabled: bool | None = None
    updates_check_on_startup: bool | None = None
    source_cache_ttl_minutes: int | None = Field(default=None, ge=5)
    mature_content_enabled: bool | None = None


def _serialize_app_settings(
    update_service: UpdateService,
    mature_content_enabled: bool,
) -> dict[str, object]:
    settings = get_settings()
    update_payload = update_service.serialize_settings(
        update_service.get_global_settings()
    )
    return {
        "version": settings.version,
        "project_name": settings.project_name,
        "mature_content_enabled": mature_content_enabled,
        "updates": update_payload,
        "source_cache_ttl_minutes": settings.source_cache_ttl_minutes,
        "capabilities": {
            "online_sources": True,
            "client_downloads": True,
            "ocr": True,
            "collections": True,
            "bookmarks": True,
            "continue_reading": True,
            "reading_progress": True,
        },
    }


@router.get("")
def get_app_settings(
    update_service: UpdateDep,
    db: DbDep,
    ctx: ProfileDep,
) -> dict[str, object]:
    """Return update and gate settings in one payload for clients."""
    return _serialize_app_settings(update_service, _mature_enabled(db, ctx))


def _require_admin(user: User) -> None:
    """403 unless the caller's account is an admin (same contract as
    ``services.auth_service.require_admin_user``, applied per-field here
    because this route mixes self-service and instance-global writes)."""
    if not user.is_admin:
        raise AppError(
            "Administrator access required.", code="forbidden", status_code=403
        )


@router.put("")
def update_app_settings(
    body: UnifiedSettingsUpdate,
    update_service: UpdateDep,
    db: DbDep,
    ctx: ProfileDep,
    user: Annotated[User, Depends(get_current_user)],
    x_profile_id: Annotated[
        str | None, Header(alias=ACTIVE_PROFILE_HEADER)
    ] = None,
) -> dict[str, object]:
    """Update update-system and gate settings. Unspecified fields are unchanged.

    Authorization (audit findings 1/2/4/5/6/7 — global settings writes had no
    admin gate):

    * ``updates_*`` and ``source_cache_ttl_minutes`` are **instance-global**
      and therefore admin-only.
    * ``mature_content_enabled`` with a valid owned ``X-Profile-Id`` stays a
      self-service per-profile toggle.
    * ``mature_content_enabled`` with a header naming a profile the caller
      does not own is a 404 — a write must never silently degrade to the
      global bucket the way the lenient read resolver does.
    * ``mature_content_enabled`` with **no** profile header writes the global
      default (the 18+ fallback for unscoped requests and the seed for every
      newly created profile on every account) — admin-only.
    """
    update_changes: dict[str, object] = {}
    if body.updates_enabled is not None:
        update_changes["enabled"] = body.updates_enabled
    if body.updates_check_interval_minutes is not None:
        update_changes["check_interval_minutes"] = body.updates_check_interval_minutes
    if body.updates_notify_enabled is not None:
        update_changes["notify_enabled"] = body.updates_notify_enabled
    if body.updates_check_on_startup is not None:
        update_changes["check_on_startup"] = body.updates_check_on_startup

    # Authorize everything up front so a mixed body never partially applies
    # before a 403.
    if update_changes or body.source_cache_ttl_minutes is not None:
        _require_admin(user)
    if body.mature_content_enabled is not None and ctx.profile_id is None:
        if x_profile_id is not None and x_profile_id.strip():
            raise AppError(
                "Profile not found.", code="profile_not_found", status_code=404
            )
        _require_admin(user)

    if update_changes:
        update_service.update_global_settings(update_changes)

    if body.source_cache_ttl_minutes is not None:
        update_persisted_settings(
            source_cache_ttl_minutes=body.source_cache_ttl_minutes
        )

    if body.mature_content_enabled is not None:
        if ctx.profile_id is not None:
            profile = db.get(ReadingProfile, ctx.profile_id)
            if profile is not None:
                profile.mature_content_enabled = bool(body.mature_content_enabled)
                db.commit()
        else:
            update_persisted_settings(
                mature_content_enabled=body.mature_content_enabled
            )

    return _serialize_app_settings(update_service, _mature_enabled(db, ctx))
