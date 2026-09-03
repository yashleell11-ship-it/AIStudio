"""Source-native reading-position service (spec §3.3, §4.1).

Owns ``chapter_progress`` (per-profile reading position), plus ``bookmarks``
and ``reading_sessions`` writes.

The one rule that matters: **furthest-wins merge**. When a client pushes
progress for a chapter it already has a row for, the row moves *forward* only.
``last_read_at`` is a tie-break, never the deciding signal — last-write-wins
silently rewinds a reader that synced an older device.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.errors import AppError
from core.profile_context import ProfileContext, resolve_profile_context
from core.time_utils import utcnow
from database.models import Bookmark, ChapterProgress, ReadingSession
from database.session import get_db


# ---------------------------------------------------------------------------
# Pure merge — unit-tested in isolation (tests/test_progress_merge.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProgressInput:
    """A single progress push from a client."""

    source_id: str
    series_key: str
    chapter_key: str
    chapter_number: float | None = None
    last_page: int = 1
    page_count: int = 0
    scroll_offset_px: int = 0
    is_completed: bool = False
    last_read_at: datetime | None = None
    time_spent_seconds: int = 0


@dataclass(frozen=True)
class MergedProgress:
    """Result of merging a push against the stored row (or nothing)."""

    chapter_number: float | None
    last_page: int
    page_count: int
    scroll_offset_px: int
    is_completed: bool
    last_read_at: datetime
    completed_at: datetime | None
    time_spent_seconds: int
    advanced: bool  # did the stored position actually move forward?


def _position(chapter_number: float | None, last_page: int) -> tuple[float, int]:
    """The comparable position tuple. NULL chapter_number sorts lowest."""
    return (chapter_number if chapter_number is not None else float("-inf"), last_page)


def merge_progress(
    stored: MergedProgress | None,
    incoming: ProgressInput,
    *,
    now: datetime | None = None,
) -> MergedProgress:
    """Furthest-wins merge (spec §3.3).

    * Position ``(chapter_number, last_page)`` only ever moves forward.
    * ``last_read_at`` decides *only* when the position tuple is equal.
    * ``is_completed`` is sticky — once true it stays true; ``completed_at`` is
      stamped the first time it becomes true and never moved.
    * ``time_spent_seconds`` accumulates.
    """
    now = now or utcnow()
    incoming_read_at = incoming.last_read_at or now

    if stored is None:
        completed_at = now if incoming.is_completed else None
        return MergedProgress(
            chapter_number=incoming.chapter_number,
            last_page=max(1, incoming.last_page),
            page_count=max(0, incoming.page_count),
            scroll_offset_px=max(0, incoming.scroll_offset_px),
            is_completed=bool(incoming.is_completed),
            last_read_at=incoming_read_at,
            completed_at=completed_at,
            time_spent_seconds=max(0, incoming.time_spent_seconds),
            advanced=True,
        )

    stored_pos = _position(stored.chapter_number, stored.last_page)
    incoming_pos = _position(incoming.chapter_number, incoming.last_page)

    is_completed = stored.is_completed or bool(incoming.is_completed)
    completed_at = stored.completed_at
    if is_completed and completed_at is None:
        completed_at = incoming_read_at if incoming.is_completed else now
    time_spent = stored.time_spent_seconds + max(0, incoming.time_spent_seconds)
    # last_read_at always advances to the most recent real read.
    last_read_at = max(stored.last_read_at, incoming_read_at)

    if incoming_pos > stored_pos:
        # Genuine forward movement — take the incoming position + its snapshots.
        return MergedProgress(
            chapter_number=(
                incoming.chapter_number
                if incoming.chapter_number is not None
                else stored.chapter_number
            ),
            last_page=max(1, incoming.last_page),
            page_count=max(stored.page_count, incoming.page_count),
            scroll_offset_px=max(0, incoming.scroll_offset_px),
            is_completed=is_completed,
            last_read_at=last_read_at,
            completed_at=completed_at,
            time_spent_seconds=time_spent,
            advanced=True,
        )

    if incoming_pos == stored_pos and incoming_read_at > stored.last_read_at:
        # Tie on position — the more recent push wins scroll offset only.
        return MergedProgress(
            chapter_number=stored.chapter_number,
            last_page=stored.last_page,
            page_count=max(stored.page_count, incoming.page_count),
            scroll_offset_px=max(0, incoming.scroll_offset_px),
            is_completed=is_completed,
            last_read_at=last_read_at,
            completed_at=completed_at,
            time_spent_seconds=time_spent,
            advanced=False,
        )

    # Incoming is behind (or a stale tie): never rewind. Only sticky flags and
    # bookkeeping fields may change.
    return MergedProgress(
        chapter_number=stored.chapter_number,
        last_page=stored.last_page,
        page_count=max(stored.page_count, incoming.page_count),
        scroll_offset_px=stored.scroll_offset_px,
        is_completed=is_completed,
        last_read_at=last_read_at,
        completed_at=completed_at,
        time_spent_seconds=time_spent,
        advanced=False,
    )


def _row_to_merged(row: ChapterProgress) -> MergedProgress:
    return MergedProgress(
        chapter_number=row.chapter_number,
        last_page=row.last_page,
        page_count=row.page_count,
        scroll_offset_px=row.scroll_offset_px,
        is_completed=bool(row.is_completed),
        last_read_at=row.last_read_at or row.started_at or utcnow(),
        completed_at=row.completed_at,
        time_spent_seconds=row.time_spent_seconds,
        advanced=False,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ProgressService:
    def __init__(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._profile_id = profile_id

    # --- progress ----------------------------------------------------------

    def _require_owner(self) -> tuple[int, int | None]:
        if self._user_id is None:
            raise AppError(
                "Authentication is required to save reading progress.",
                code="auth_required",
                status_code=401,
            )
        return self._user_id, self._profile_id

    def _scope(self, stmt):
        stmt = stmt.where(ChapterProgress.user_id == self._user_id)
        if self._profile_id is None:
            stmt = stmt.where(ChapterProgress.profile_id.is_(None))
        else:
            stmt = stmt.where(ChapterProgress.profile_id == self._profile_id)
        return stmt

    def save_one(self, payload: ProgressInput) -> dict[str, Any]:
        user_id, profile_id = self._require_owner()
        source_id = payload.source_id
        series_key = fully_unquote(payload.series_key)
        chapter_key = fully_unquote(payload.chapter_key)

        row = self._db.execute(
            self._scope(
                select(ChapterProgress).where(
                    ChapterProgress.source_id == source_id,
                    ChapterProgress.series_key == series_key,
                    ChapterProgress.chapter_key == chapter_key,
                )
            )
        ).scalar_one_or_none()

        merged = merge_progress(
            _row_to_merged(row) if row is not None else None, payload
        )

        if row is None:
            row = ChapterProgress(
                user_id=user_id,
                profile_id=profile_id,
                source_id=source_id,
                series_key=series_key,
                chapter_key=chapter_key,
                started_at=merged.last_read_at,
            )
            self._db.add(row)

        row.chapter_number = merged.chapter_number
        row.last_page = merged.last_page
        row.page_count = merged.page_count
        row.scroll_offset_px = merged.scroll_offset_px
        row.is_completed = merged.is_completed
        row.last_read_at = merged.last_read_at
        row.completed_at = merged.completed_at
        row.time_spent_seconds = merged.time_spent_seconds

        self._db.commit()
        self._db.refresh(row)
        return {**self._serialize(row), "advanced": merged.advanced}

    def save_batch(self, payloads: list[ProgressInput]) -> dict[str, Any]:
        results = [self.save_one(p) for p in payloads]
        return {
            "saved": len(results),
            "advanced": sum(1 for r in results if r.get("advanced")),
            "items": results,
        }

    def get_series_progress(
        self, source_id: str, series_key: str
    ) -> list[dict[str, Any]]:
        self._require_owner()
        series_key = fully_unquote(series_key)
        rows = self._db.execute(
            self._scope(
                select(ChapterProgress)
                .where(
                    ChapterProgress.source_id == source_id,
                    ChapterProgress.series_key == series_key,
                )
                .order_by(ChapterProgress.chapter_number)
            )
        ).scalars().all()
        return [self._serialize(r) for r in rows]

    def continue_reading(self, limit: int = 20) -> list[dict[str, Any]]:
        """Most recent unfinished row per (source_id, series_key)."""
        self._require_owner()
        rows = self._db.execute(
            self._scope(
                select(ChapterProgress).order_by(
                    ChapterProgress.last_read_at.desc()
                )
            )
        ).scalars().all()
        seen: set[tuple[str, str]] = set()
        out: list[dict[str, Any]] = []
        for r in rows:
            key = (r.source_id, r.series_key)
            if key in seen:
                continue
            seen.add(key)
            if r.is_completed:
                continue
            out.append(self._serialize(r))
            if len(out) >= limit:
                break
        return out

    def reading_history(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        self._require_owner()
        rows = self._db.execute(
            self._scope(
                select(ChapterProgress)
                .order_by(ChapterProgress.last_read_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return [self._serialize(r) for r in rows]

    # --- bookmarks -------------------------------------------------------

    def add_bookmark(
        self,
        *,
        source_id: str,
        series_key: str,
        chapter_key: str,
        page: int,
        note: str | None = None,
    ) -> dict[str, Any]:
        user_id, profile_id = self._require_owner()
        row = Bookmark(
            user_id=user_id,
            profile_id=profile_id,
            source_id=source_id,
            series_key=fully_unquote(series_key),
            chapter_key=fully_unquote(chapter_key),
            page=max(1, page),
            note=note or None,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return {
            "id": row.id,
            "source_id": row.source_id,
            "series_key": row.series_key,
            "chapter_key": row.chapter_key,
            "page": row.page,
            "note": row.note,
            "created_at": _iso(row.created_at),
        }

    def list_bookmarks(
        self, *, source_id: str | None = None, series_key: str | None = None
    ) -> list[dict[str, Any]]:
        user_id, profile_id = self._require_owner()
        stmt = select(Bookmark).where(Bookmark.user_id == user_id)
        stmt = (
            stmt.where(Bookmark.profile_id.is_(None))
            if profile_id is None
            else stmt.where(Bookmark.profile_id == profile_id)
        )
        if source_id:
            stmt = stmt.where(Bookmark.source_id == source_id)
        if series_key:
            stmt = stmt.where(Bookmark.series_key == fully_unquote(series_key))
        stmt = stmt.order_by(Bookmark.created_at.desc())
        rows = self._db.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "source_id": r.source_id,
                "series_key": r.series_key,
                "chapter_key": r.chapter_key,
                "page": r.page,
                "note": r.note,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ]

    def delete_bookmark(self, bookmark_id: int) -> None:
        """Delete one of *this profile's* bookmarks, or 404.

        ``list_bookmarks`` is profile-scoped, so a ``user_id``-only check here
        let a profile delete a bookmark it could not see by guessing its id.
        """
        user_id, profile_id = self._require_owner()
        row = self._db.get(Bookmark, bookmark_id)
        if row is None or row.user_id != user_id or row.profile_id != profile_id:
            raise AppError("Bookmark not found.", code="not_found", status_code=404)
        self._db.delete(row)
        self._db.commit()

    # --- reading sessions ------------------------------------------------

    def record_session(
        self,
        *,
        source_id: str,
        series_key: str,
        chapter_key: str,
        chapter_number: float | None,
        start_page: int,
        end_page: int,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        user_id, profile_id = self._require_owner()
        pages_read = max(0, end_page - start_page + 1)
        row = ReadingSession(
            user_id=user_id,
            profile_id=profile_id,
            source_id=source_id,
            series_key=fully_unquote(series_key),
            chapter_key=fully_unquote(chapter_key),
            chapter_number=chapter_number,
            start_page=max(1, start_page),
            end_page=max(1, end_page),
            pages_read=pages_read,
            started_at=started_at or utcnow(),
            ended_at=ended_at,
        )
        self._db.add(row)
        self._db.commit()

    # --- serialization -------------------------------------------------

    @staticmethod
    def _serialize(row: ChapterProgress) -> dict[str, Any]:
        return {
            "id": row.id,
            "source_id": row.source_id,
            "series_key": row.series_key,
            "chapter_key": row.chapter_key,
            "chapter_number": row.chapter_number,
            "last_page": row.last_page,
            "page_count": row.page_count,
            "scroll_offset_px": row.scroll_offset_px,
            "is_completed": bool(row.is_completed),
            "started_at": _iso(row.started_at),
            "last_read_at": _iso(row.last_read_at),
            "completed_at": _iso(row.completed_at),
            "time_spent_seconds": row.time_spent_seconds,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def get_progress_service(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> ProgressService:
    return ProgressService(db, user_id=ctx.user_id, profile_id=ctx.profile_id)
