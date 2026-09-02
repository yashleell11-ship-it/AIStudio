"""Reading-profile business logic (per-user, household model).

Each account may hold up to :data:`ProfileService.MAX_PROFILES_PER_USER`
lightweight profiles. Every query is scoped to the owning ``user_id`` so one
account can never see or mutate another's profiles; mismatched ids surface as a
404 (indistinguishable from "does not exist"), never a 403.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.errors import AppError
from database.models import ReadingProfile, User
from database.session import get_db
from services.auth_service import get_current_user

# The moods a profile can present. ``default`` is the neutral fallback.
ALLOWED_MOODS: frozenset[str] = frozenset(
    {
        "romantic",
        "action",
        "comedy",
        "horror",
        "slice_of_life",
        "fantasy",
        "default",
    }
)

NAME_MAX = 255
AVATAR_KEY_MAX = 64


class ProfileService:
    # A household account is capped at this many profiles.
    MAX_PROFILES_PER_USER = 5

    def __init__(self, db: Session, user_id: int | None) -> None:
        self._db = db
        # Profiles are per-user; ``None`` scopes to the anonymous/legacy owner
        # (mirrors the other per-user services' NULL-owned semantics).
        self._user_id = user_id

    # --- helpers -------------------------------------------------------------

    def _validate_mood(self, mood: str) -> str:
        if mood not in ALLOWED_MOODS:
            raise AppError(
                "Unknown mood.",
                code="invalid_mood",
                status_code=422,
                details={"allowed": sorted(ALLOWED_MOODS)},
            )
        return mood

    def _validate_name(self, name: str) -> str:
        normalized = (name or "").strip()
        if not normalized or len(normalized) > NAME_MAX:
            raise AppError(
                f"Profile name must be 1-{NAME_MAX} characters.",
                code="invalid_profile_name",
                status_code=422,
            )
        return normalized

    def _get_owned(self, profile_id: int) -> ReadingProfile:
        profile = self._db.execute(
            select(ReadingProfile).where(
                ReadingProfile.id == profile_id,
                ReadingProfile.user_id == self._user_id,
            )
        ).scalar_one_or_none()
        if profile is None:
            raise AppError(
                "Profile not found.",
                code="profile_not_found",
                status_code=404,
                details={"profile_id": profile_id},
            )
        return profile

    @staticmethod
    def serialize(profile: ReadingProfile) -> dict[str, object]:
        return {
            "id": profile.id,
            "name": profile.name,
            "avatar_key": profile.avatar_key,
            "mood": profile.mood,
            "sort_order": profile.sort_order,
            "mature_content_enabled": bool(profile.mature_content_enabled),
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
        }

    # --- CRUD ----------------------------------------------------------------

    def list_profiles(self) -> list[ReadingProfile]:
        return list(
            self._db.execute(
                select(ReadingProfile)
                .where(ReadingProfile.user_id == self._user_id)
                .order_by(ReadingProfile.sort_order, ReadingProfile.id)
            ).scalars()
        )

    def count_profiles(self) -> int:
        return int(
            self._db.execute(
                select(func.count())
                .select_from(ReadingProfile)
                .where(ReadingProfile.user_id == self._user_id)
            ).scalar_one()
        )

    def create_profile(
        self,
        *,
        name: str,
        avatar_key: str | None = None,
        mood: str | None = None,
        sort_order: int | None = None,
        mature_content_enabled: bool | None = None,
    ) -> ReadingProfile:
        clean_name = self._validate_name(name)
        clean_mood = self._validate_mood(mood or "default")
        clean_avatar = (avatar_key or "default").strip()[:AVATAR_KEY_MAX] or "default"

        if self.count_profiles() >= self.MAX_PROFILES_PER_USER:
            raise AppError(
                f"A profile limit of {self.MAX_PROFILES_PER_USER} has been reached.",
                code="profile_limit_reached",
                status_code=409,
            )

        if sort_order is None:
            # Append to the end of the current ordering.
            highest = self._db.execute(
                select(func.max(ReadingProfile.sort_order)).where(
                    ReadingProfile.user_id == self._user_id
                )
            ).scalar_one()
            sort_order = (highest + 1) if highest is not None else 0

        # Seed the per-profile mature gate from the global config default so a
        # new profile inherits the instance's current stance until changed.
        from core.config import get_settings

        profile = ReadingProfile(
            user_id=self._user_id,
            name=clean_name,
            avatar_key=clean_avatar,
            mood=clean_mood,
            sort_order=sort_order,
            mature_content_enabled=(
                get_settings().mature_content_enabled
                if mature_content_enabled is None
                else bool(mature_content_enabled)
            ),
        )
        self._db.add(profile)
        self._db.commit()
        self._db.refresh(profile)
        return profile

    def update_profile(
        self,
        profile_id: int,
        *,
        name: str | None = None,
        avatar_key: str | None = None,
        mood: str | None = None,
        sort_order: int | None = None,
        mature_content_enabled: bool | None = None,
    ) -> ReadingProfile:
        profile = self._get_owned(profile_id)
        if mature_content_enabled is not None:
            profile.mature_content_enabled = bool(mature_content_enabled)
        if name is not None:
            profile.name = self._validate_name(name)
        if avatar_key is not None:
            profile.avatar_key = avatar_key.strip()[:AVATAR_KEY_MAX] or "default"
        if mood is not None:
            profile.mood = self._validate_mood(mood)
        if sort_order is not None:
            profile.sort_order = sort_order
        self._db.commit()
        self._db.refresh(profile)
        return profile

    def delete_profile(self, profile_id: int) -> None:
        # Source-native: every profile-scoped table (followed_series,
        # chapter_progress, collections, bookmarks, notifications, ...) is
        # ON DELETE CASCADE from reading_profiles. Progress for a series is
        # keyed by (source_id, series_key) and is re-created on the next read
        # anyway, so there is nothing to "re-home" (spec §3.2, O-6). A hard
        # cascade is the ratified behaviour.
        profile = self._get_owned(profile_id)
        self._db.delete(profile)
        self._db.commit()


def get_profile_service(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ProfileService:
    return ProfileService(db, user_id=user.id)
