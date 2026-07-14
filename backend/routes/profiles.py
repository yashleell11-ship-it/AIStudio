"""Reading-profile CRUD, scoped to the session user (household model).

Every endpoint operates only on the current user's profiles; a profile id that
belongs to another account (or does not exist) returns 404. The optional
``X-Profile-Id`` header is recorded into request-scoped context via a router-level
dependency — supplying it never fails a request.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from core.profile_context import get_active_profile_id
from services.profile_service import ProfileService, get_profile_service

# Kept in lockstep with services.profile_service.ALLOWED_MOODS.
Mood = Literal[
    "romantic", "action", "comedy", "horror", "slice_of_life", "fantasy", "default"
]

router = APIRouter(
    prefix="/profiles",
    tags=["profiles"],
    dependencies=[Depends(get_active_profile_id)],
)

ProfileDep = Annotated[ProfileService, Depends(get_profile_service)]


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    avatar_key: str | None = Field(default=None, max_length=64)
    mood: Mood = "default"
    sort_order: int | None = Field(default=None, ge=0)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    avatar_key: str | None = Field(default=None, max_length=64)
    mood: Mood | None = None
    sort_order: int | None = Field(default=None, ge=0)


@router.get("")
def list_profiles(service: ProfileDep) -> list[dict[str, object]]:
    """List the current user's profiles, ordered by sort_order."""
    return [service.serialize(p) for p in service.list_profiles()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(body: ProfileCreate, service: ProfileDep) -> dict[str, object]:
    """Create a profile for the current user (max 5 per account)."""
    profile = service.create_profile(
        name=body.name,
        avatar_key=body.avatar_key,
        mood=body.mood,
        sort_order=body.sort_order,
    )
    return service.serialize(profile)


@router.patch("/{profile_id}")
def update_profile(
    profile_id: int, body: ProfileUpdate, service: ProfileDep
) -> dict[str, object]:
    """Update a profile the current user owns (404 otherwise)."""
    profile = service.update_profile(
        profile_id,
        name=body.name,
        avatar_key=body.avatar_key,
        mood=body.mood,
        sort_order=body.sort_order,
    )
    return service.serialize(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: int, service: ProfileDep) -> Response:
    """Delete a profile the current user owns (404 otherwise)."""
    service.delete_profile(profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
