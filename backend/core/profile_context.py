"""Active reading-profile request context.

Clients name the profile a request acts under via the ``X-Profile-Id`` header.
Two resolution modes are exposed:

* :func:`get_active_profile_id` / :func:`resolve_profile_context` — *lenient*.
  The header never fails a request; a missing / non-numeric / foreign id simply
  resolves the profile to ``None`` (the legacy/unscoped bucket). Used to build
  the per-request services and for read endpoints, which must degrade gracefully.

* :func:`require_profile_context` — *strict*. Used as a dependency on mutating
  profile-owned endpoints (follow, save progress, bookmark, collection CRUD).
  If the account owns any profiles, a valid ``X-Profile-Id`` naming one they own
  is required (``400 profile_required`` when absent, ``404 profile_not_found``
  when it does not belong to them). An account with NO profiles degrades to the
  unscoped bucket so pre-profile / anonymous flows keep working.

Profile ownership is always scoped to the authenticated user; a profile id from
another account is treated as not-found (never disclosed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from core.errors import AppError
from database.models import ReadingProfile, User
from database.session import get_db
from services.auth_service import get_optional_user

ACTIVE_PROFILE_HEADER = "X-Profile-Id"


@dataclass(frozen=True)
class ProfileContext:
    """The (account, profile) a request acts under. ``profile_id`` is ``None``
    for the legacy/unscoped bucket (anonymous, or an account with no profiles)."""

    user_id: int | None
    profile_id: int | None


def _parse_profile_id(raw: str | None) -> int | None:
    """Parse the raw header value into an int, or ``None`` for absent/blank/
    non-numeric input. Never raises — the header is advisory."""
    if raw is not None and raw.strip():
        try:
            return int(raw.strip())
        except ValueError:
            return None
    return None


def get_active_profile_id(
    request: Request,
    x_profile_id: Annotated[str | None, Header(alias=ACTIVE_PROFILE_HEADER)] = None,
) -> int | None:
    """Record the client's active profile id into ``request.state.
    active_profile_id`` and return it. Never raises — the header is advisory."""
    profile_id = _parse_profile_id(x_profile_id)
    request.state.active_profile_id = profile_id
    return profile_id


def _owned_profile_id(
    db: Session, user_id: int | None, profile_id: int | None
) -> int | None:
    """Return ``profile_id`` iff it names a profile owned by ``user_id``."""
    if profile_id is None or user_id is None:
        return None
    exists = (
        db.query(ReadingProfile.id)
        .filter(ReadingProfile.id == profile_id, ReadingProfile.user_id == user_id)
        .first()
    )
    return profile_id if exists is not None else None


def _user_has_profiles(db: Session, user_id: int | None) -> bool:
    if user_id is None:
        return False
    return (
        db.query(ReadingProfile.id)
        .filter(ReadingProfile.user_id == user_id)
        .first()
        is not None
    )


def resolve_profile_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)] = None,
    x_profile_id: Annotated[str | None, Header(alias=ACTIVE_PROFILE_HEADER)] = None,
) -> ProfileContext:
    """Lenient resolver used to construct per-request services and for read
    endpoints. The profile is set only when the header names one the user owns;
    otherwise it is ``None`` (never raises)."""
    profile_id = _parse_profile_id(x_profile_id)
    request.state.active_profile_id = profile_id
    user_id = user.id if user else None
    return ProfileContext(
        user_id=user_id,
        profile_id=_owned_profile_id(db, user_id, profile_id),
    )


def require_profile_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)] = None,
    x_profile_id: Annotated[str | None, Header(alias=ACTIVE_PROFILE_HEADER)] = None,
) -> ProfileContext:
    """Strict guard for mutating profile-owned endpoints.

    * header names a profile the user owns  → that context
    * header absent/invalid, user owns profiles → 400 ``profile_required``
    * header names a foreign/unknown profile → 404 ``profile_not_found``
    * user owns no profiles                  → unscoped context (legacy bucket)
    """
    profile_id = _parse_profile_id(x_profile_id)
    request.state.active_profile_id = profile_id
    user_id = user.id if user else None

    if profile_id is None:
        if _user_has_profiles(db, user_id):
            raise AppError(
                "An active profile is required for this action.",
                code="profile_required",
                status_code=400,
            )
        return ProfileContext(user_id=user_id, profile_id=None)

    owned = _owned_profile_id(db, user_id, profile_id)
    if owned is None:
        raise AppError(
            "Profile not found.",
            code="profile_not_found",
            status_code=404,
            details={"profile_id": profile_id},
        )
    return ProfileContext(user_id=user_id, profile_id=owned)
