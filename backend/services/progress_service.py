"""Source-native reading-position service (spec §3.3, §4.1).

Owns ``chapter_progress`` (per-profile reading position) and
``reading_sessions`` writes. Bookmarks live in ``services.bookmark_service``
(they are objects with tombstones, not a furthest-wins scalar); the three
bookmark methods below are delegating shims for existing callers.

The one rule that matters: **furthest-wins merge**. When a client pushes
progress for a chapter it already has a row for, the row moves *forward* only.
``last_read_at`` is a tie-break, never the deciding signal — last-write-wins
silently rewinds a reader that synced an older device.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.errors import AppError
from core.profile_context import ProfileContext, resolve_profile_context
from core.time_utils import utcnow
from database.models import ChapterProgress, ReadingSession
from database.session import get_db

if TYPE_CHECKING:  # pragma: no cover - typing only
    from services.bookmark_service import BookmarkService

#: Row-value ``IN`` chunk size for the batch prefetch. Matches the library's
#: (``followed_series_service._IN_CHUNK``): three bound parameters per key, so
#: 400 keys stay inside even the old 999-variable SQLite ceiling.
_IN_CHUNK = 300


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
    """The comparable position tuple.

    A ``chapter_number`` that is still NULL on *both* sides sorts to a constant,
    so the comparison falls through to ``last_page``. It is never a "sorts
    lowest" sentinel — see :func:`_resolve_number`.
    """
    return (chapter_number if chapter_number is not None else float("-inf"), last_page)


def _resolve_number(primary: float | None, fallback: float | None) -> float | None:
    """``primary``, or ``fallback`` when the client did not send a number.

    A ``chapter_progress`` row is keyed by ``chapter_key``, so its
    ``chapter_number`` is a constant *within* that row: a NULL means "the client
    did not send one", never "an earlier chapter". Treating NULL as ``-inf``
    broke the merge in both directions —

    * stored ``(5.0, page 3)`` + incoming ``(None, page 20)`` read as a move
      *backwards*, so a legitimate forward push was silently dropped; and
    * stored ``(None, page 40)`` + incoming ``(12.0, page 1)`` read as a move
      *forwards*, rewinding the reader to page 1 — the exact failure
      furthest-wins exists to prevent.

    Coalescing collapses both to "same chapter", which lets ``last_page``
    decide. It also means a push that supplies a number the stored row lacks
    upgrades it: strictly more information, and not a rewind.
    """
    return primary if primary is not None else fallback


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

    # Coalesce across the pair before comparing: within one chapter_key the
    # number is a constant, so a NULL on either side must not decide the
    # ordering. See _resolve_number.
    incoming_number = _resolve_number(incoming.chapter_number, stored.chapter_number)
    stored_number = _resolve_number(stored.chapter_number, incoming.chapter_number)
    stored_pos = _position(stored_number, stored.last_page)
    incoming_pos = _position(incoming_number, incoming.last_page)

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
            chapter_number=incoming_number,
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
            chapter_number=stored_number,
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
        chapter_number=stored_number,
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

    def _require_profile(self) -> tuple[int, int]:
        """Owner + active profile, for the write paths.

        ``profile_id`` is NOT NULL on chapter_progress / reading_sessions, so a write from the unscoped bucket (an account that
        owns no profiles, which ``require_profile_context`` lets through) is an
        IntegrityError 500. Return the documented 400 the clients already
        handle instead.
        """
        user_id, profile_id = self._require_owner()
        if profile_id is None:
            raise AppError(
                "An active profile is required for this action.",
                code="profile_required",
                status_code=400,
            )
        return user_id, profile_id

    def _scope(self, stmt):
        stmt = stmt.where(ChapterProgress.user_id == self._user_id)
        if self._profile_id is None:
            stmt = stmt.where(ChapterProgress.profile_id.is_(None))
        else:
            stmt = stmt.where(ChapterProgress.profile_id == self._profile_id)
        return stmt

    def _prefetch(
        self, payloads: list[ProgressInput]
    ) -> dict[tuple[str, str, str], ChapterProgress]:
        """Every existing row a batch will touch, in one statement per chunk.

        ``_apply_one`` looked its row up with its own SELECT, which is fine for
        one push and an N+1 for a sync: the route accepts 200 items, so an
        offline catch-up issued 200 point queries before it wrote anything.
        Row-value ``IN`` collapses them, chunked exactly like the library's
        lookups so the statement stays inside SQLite's variable ceiling.
        """
        keys = [
            (
                p.source_id,
                fully_unquote(p.series_key),
                fully_unquote(p.chapter_key),
            )
            for p in payloads
        ]
        found: dict[tuple[str, str, str], ChapterProgress] = {}
        target = tuple_(
            ChapterProgress.source_id,
            ChapterProgress.series_key,
            ChapterProgress.chapter_key,
        )
        for start in range(0, len(keys), _IN_CHUNK):
            chunk = keys[start : start + _IN_CHUNK]
            if not chunk:
                continue
            rows = self._db.execute(
                self._scope(select(ChapterProgress).where(target.in_(chunk)))
            ).scalars().all()
            for row in rows:
                found[(row.source_id, row.series_key, row.chapter_key)] = row
        return found

    def _apply_one(
        self,
        payload: ProgressInput,
        *,
        prefetched: dict[tuple[str, str, str], ChapterProgress] | None = None,
    ) -> tuple[ChapterProgress, MergedProgress]:
        """Merge one push into the session WITHOUT committing.

        Ends with a ``flush`` so a later payload in the same batch that targets
        the same chapter sees the pending row (the per-item-commit behaviour it
        replaces provided that visibility implicitly).

        ``prefetched`` is the batch path's shared row map (see ``_prefetch``).
        It is READ AND WRITTEN: a row this call creates is put back into it, so
        a second payload for the same chapter later in the batch merges onto
        the same object rather than inserting a duplicate — exactly what the
        per-item SELECT + flush used to guarantee.
        """
        user_id, profile_id = self._require_profile()
        source_id = payload.source_id
        series_key = fully_unquote(payload.series_key)
        chapter_key = fully_unquote(payload.chapter_key)

        if prefetched is not None:
            row = prefetched.get((source_id, series_key, chapter_key))
        else:
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

        # Captured BEFORE the row is mutated below: a session records only the
        # stretch this push covered, not the chapter's whole history.
        previous_last_page = row.last_page if row is not None else 0
        previous_time_spent = row.time_spent_seconds if row is not None else 0

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
            if prefetched is not None:
                prefetched[(source_id, series_key, chapter_key)] = row

        row.chapter_number = merged.chapter_number
        row.last_page = merged.last_page
        row.page_count = merged.page_count
        row.scroll_offset_px = merged.scroll_offset_px
        row.is_completed = merged.is_completed
        row.last_read_at = merged.last_read_at
        row.completed_at = merged.completed_at
        row.time_spent_seconds = merged.time_spent_seconds

        self._db.flush()

        # A reading session per *advance*, not per push. Clients ping progress
        # repeatedly for the same page (autosave, scroll settle), and one row
        # per ping would bury the real reading history in noise while inflating
        # every statistic built from it. `advanced` is already the merge's own
        # answer to "did this move forward", so sessions and the furthest-wins
        # position can never disagree about whether reading happened.
        if merged.advanced:
            # +1 because the previous position was already read: resuming at
            # page 5 and reaching 8 is three pages (6, 7, 8), not four. A first
            # push has no previous position, so it starts at page 1.
            start_page = previous_last_page + 1 if previous_last_page else 1
            elapsed = max(0, merged.time_spent_seconds - previous_time_spent)
            ended_at = merged.last_read_at
            self.record_session(
                source_id=source_id,
                series_key=series_key,
                chapter_key=chapter_key,
                chapter_number=merged.chapter_number,
                start_page=start_page,
                end_page=merged.last_page,
                # Only claim a start time the client actually reported. Without
                # elapsed time, a zero-length session is honest; inventing a
                # duration would corrupt the time-read statistic outright.
                started_at=(
                    ended_at - timedelta(seconds=elapsed) if elapsed else ended_at
                ),
                ended_at=ended_at,
                commit=False,
            )

        return row, merged

    def save_one(self, payload: ProgressInput) -> dict[str, Any]:
        row, merged = self._apply_one(payload)
        self._db.commit()
        return {**self._serialize(row), "advanced": merged.advanced}

    def save_batch(self, payloads: list[ProgressInput]) -> dict[str, Any]:
        """Offline-sync catch-up, applied in ONE transaction.

        This used to be ``[save_one(p) for p in payloads]`` — N separate
        write-lock acquire/commit(fsync) cycles against the single-writer
        SQLite for a single request, which let one large batch monopolise the
        writer (audit finding 12; the route also caps the batch length).
        """
        prefetched = self._prefetch(payloads)
        applied = [self._apply_one(p, prefetched=prefetched) for p in payloads]
        self._db.commit()
        results = []
        for row, merged in applied:
            # No refresh(). The session is created with expire_on_commit=False
            # and _apply_one flushes, so every column -- including the
            # Python-side defaults -- is already loaded on the object. The
            # refresh was one extra SELECT per item, 200 of them for a full
            # batch, to re-read values this process had just written.
            results.append({**self._serialize(row), "advanced": merged.advanced})
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
    #
    # Bookmarks moved to ``services.bookmark_service`` when they gained exact
    # positions and object-sync semantics (design 2026-09-05-smart-bookmarks).
    # They are NOT progress: progress is an automatic furthest-wins scalar,
    # a bookmark is a deliberate user-created object with a client id and a
    # tombstone, and the two merges are opposites. These three delegating
    # methods remain so existing callers keep working; new code should take a
    # ``BookmarkService`` directly.

    def _bookmarks(self) -> "BookmarkService":
        from services.bookmark_service import BookmarkService

        return BookmarkService(
            self._db, user_id=self._user_id, profile_id=self._profile_id
        )

    def add_bookmark(self, **kwargs: Any) -> dict[str, Any]:
        """``page=`` is translated, not dropped.

        The pre-design signature took a 1-based ``page``; that column is now
        ``anchor_index`` (still 1-based, still the page for manga), so a
        legacy caller keeps working and lands at offset 0.0 of the page it
        named — the same back-compat rule the migration applies to stored
        rows.
        """
        page = kwargs.pop("page", None)
        if page is not None:
            kwargs.setdefault("anchor_index", int(page))
        return self._bookmarks().add_bookmark(**kwargs)

    def list_bookmarks(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._bookmarks().list_bookmarks(**kwargs)

    def delete_bookmark(self, bookmark_id: int) -> None:
        self._bookmarks().delete_bookmark(bookmark_id)

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
        commit: bool = True,
    ) -> None:
        user_id, profile_id = self._require_profile()
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
        # `commit=False` lets a caller already inside a transaction append a
        # session without breaking it — save_batch deliberately applies the
        # whole batch in ONE commit (audit finding 12: per-item commits let a
        # single large batch monopolise SQLite's single writer).
        if commit:
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
