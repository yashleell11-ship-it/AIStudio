"""Automatic update engine, source-native (spec §4.5).

Each pass diffs every ``followed_series.known_chapters`` snapshot against a live
connector chapter list. New chapters produce an ``update_notifications`` row
(notification only — the client decides whether to download) and refresh
``source_series_cache``. ``known_chapters`` is then updated to the new list.

No auto-download, no ``register_new_chapters_callback``, no ``SeriesTracker``
migration machinery — all removed. Single-process threaded loop unchanged
(``update_scheduler``).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectors.registry import list_installed_connectors
from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import (
    FollowedSeries,
    UpdateNotification,
    UpdateRun,
    UpdateSettings,
)
from database.session import SessionLocal, get_db

logger = logging.getLogger(__name__)

# Indirection so tests can drive the sweep's clock deterministically.
_monotonic = time.monotonic


def _bool(value: Any) -> bool:
    return bool(value)


def _loads(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        data = json.loads(value)
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


class UpdateService:
    def __init__(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        profile_id: int | None = None,
        system: bool = False,
    ) -> None:
        """``system=True`` marks the background worker's service.

        The scheduled sweep runs with no request context and legitimately walks
        every account's rows. A *request*-built service never may, so the flag
        is opt-in and off by default: a caller that forgets it gets the scoped,
        safe behaviour rather than the unrestricted one.
        """
        self._db = db
        self._user_id = user_id
        self._profile_id = profile_id
        self._system = system

    # --- global settings ------------------------------------------------

    def get_global_settings(self) -> UpdateSettings:
        row = self._db.get(UpdateSettings, 1)
        if row is None:
            row = UpdateSettings(id=1)
            self._db.add(row)
            self._db.commit()
            self._db.refresh(row)
        return row

    def update_global_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = self.get_global_settings()
        for field in (
            "enabled",
            "notify_enabled",
            "check_on_startup",
        ):
            if field in payload and payload[field] is not None:
                setattr(row, field, bool(payload[field]))
        if payload.get("check_interval_minutes") is not None:
            row.check_interval_minutes = max(5, int(payload["check_interval_minutes"]))
        row.updated_at = utcnow()
        self._db.commit()
        self._db.refresh(row)
        return self.serialize_settings(row)

    @staticmethod
    def serialize_settings(row: UpdateSettings) -> dict[str, Any]:
        return {
            "enabled": _bool(row.enabled),
            "check_interval_minutes": row.check_interval_minutes,
            "notify_enabled": _bool(row.notify_enabled),
            "check_on_startup": _bool(row.check_on_startup),
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        }

    # --- notifications ------------------------------------------------

    def _notif_scope(self, stmt):
        if self._user_id is not None:
            stmt = stmt.where(UpdateNotification.user_id == self._user_id)
        if self._profile_id is not None:
            stmt = stmt.where(UpdateNotification.profile_id == self._profile_id)
        elif self._user_id is not None:
            stmt = stmt.where(UpdateNotification.profile_id.is_(None))
        return stmt

    def list_notifications(
        self, *, unread_only: bool = False, limit: int = 100
    ) -> list[dict[str, Any]]:
        stmt = self._notif_scope(select(UpdateNotification))
        if unread_only:
            stmt = stmt.where(UpdateNotification.is_read.is_(False))
        stmt = stmt.order_by(UpdateNotification.created_at.desc()).limit(limit)
        return [
            self.serialize_notification(n)
            for n in self._db.execute(stmt).scalars().all()
        ]

    def count_notifications(self, *, unread_only: bool = False) -> int:
        stmt = self._notif_scope(
            select(func.count()).select_from(UpdateNotification)
        )
        if unread_only:
            stmt = stmt.where(UpdateNotification.is_read.is_(False))
        return int(self._db.execute(stmt).scalar_one() or 0)

    def unread_count(self) -> int:
        return self.count_notifications(unread_only=True)

    @staticmethod
    def serialize_notification(row: UpdateNotification) -> dict[str, Any]:
        return {
            "id": row.id,
            "followed_series_id": row.followed_series_id,
            "source_id": row.source_id,
            "series_key": row.series_key,
            "chapter_key": row.chapter_key,
            "chapter_title": row.chapter_title,
            "chapter_number": row.chapter_number,
            "is_read": _bool(row.is_read),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def mark_notification_read(self, notification_id: int) -> dict[str, Any]:
        """Mark one of *this profile's* notifications read, or 404.

        ``_notif_scope`` (list / count / read-all) is per-profile, so the
        ``user_id``-only check here let one profile clear a sibling's unread
        badge by guessing an id — the notification stayed invisible to them and
        simply vanished from the owner's count.
        """
        row = self._db.get(UpdateNotification, notification_id)
        if row is None or (
            self._user_id is not None
            and (
                row.user_id != self._user_id or row.profile_id != self._profile_id
            )
        ):
            raise AppError(
                "Notification not found.", code="not_found", status_code=404
            )
        row.is_read = True
        self._db.commit()
        return self.serialize_notification(row)

    def mark_all_notifications_read(self) -> dict[str, int]:
        stmt = self._notif_scope(
            select(UpdateNotification).where(UpdateNotification.is_read.is_(False))
        )
        rows = self._db.execute(stmt).scalars().all()
        for row in rows:
            row.is_read = True
        self._db.commit()
        return {"updated": len(rows)}

    # --- runs -------------------------------------------------------

    def list_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.execute(
            select(UpdateRun).order_by(UpdateRun.started_at.desc()).limit(limit)
        ).scalars().all()
        return [self.serialize_run(r) for r in rows]

    def count_runs(self) -> int:
        return int(
            self._db.execute(
                select(func.count()).select_from(UpdateRun)
            ).scalar_one()
            or 0
        )

    def get_run(self, run_id: int) -> dict[str, Any]:
        row = self._db.get(UpdateRun, run_id)
        if row is None:
            raise AppError("Run not found.", code="not_found", status_code=404)
        return self.serialize_run(row)

    @staticmethod
    def serialize_run(row: UpdateRun) -> dict[str, Any]:
        return {
            "id": row.id,
            "trigger": row.trigger,
            "status": row.status,
            "series_checked": row.series_checked,
            "new_chapters_found": row.new_chapters_found,
            "error": row.error,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat()
            if row.finished_at
            else None,
        }

    def list_sources(self) -> list[dict[str, str]]:
        return [
            {"id": d.source_type, "name": d.name}
            for d in list_installed_connectors(browsable_only=True)
        ]

    # --- the check sweep -------------------------------------------

    def _followed_scope(self, stmt):
        stmt = stmt.where(FollowedSeries.user_id == self._user_id)
        if self._profile_id is None:
            return stmt.where(FollowedSeries.profile_id.is_(None))
        return stmt.where(FollowedSeries.profile_id == self._profile_id)

    def resolve_followed_ids(self, followed_ids: list[int]) -> list[int]:
        """Validate caller-supplied followed-series ids against this scope.

        Without this, ``followed_ids`` was applied to an otherwise unscoped
        statement: **any authenticated user could force a check on any other
        account's row**, rewriting its ``known_chapters`` / ``last_checked_at``
        / ``last_error`` and silently consuming its notification window (a
        chapter diffed away by somebody else's forced check never notifies the
        owner, because the next real run no longer sees it as new).

        Raises 404 rather than filtering silently: an id the caller does not own
        is indistinguishable, to them, from one that does not exist.
        """
        wanted = list(dict.fromkeys(followed_ids))
        if self._system:
            return wanted
        owned = set(
            self._db.execute(
                self._followed_scope(
                    select(FollowedSeries.id).where(FollowedSeries.id.in_(wanted))
                )
            ).scalars().all()
        )
        missing = [i for i in wanted if i not in owned]
        if missing:
            raise AppError(
                "Followed series not found.",
                code="series_not_found",
                status_code=404,
                details={"followed_ids": missing},
            )
        return wanted

    def run_check(
        self,
        *,
        trigger: str = "manual",
        followed_ids: list[int] | None = None,
        tracker_ids: list[int] | None = None,  # legacy alias
    ) -> dict[str, Any]:
        followed_ids = followed_ids or tracker_ids
        if followed_ids:
            # Scoped *before* the run row is written, so an out-of-scope id
            # leaves no trace in the run log either.
            followed_ids = self.resolve_followed_ids(followed_ids)
        run = UpdateRun(trigger=trigger, status="running")
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)

        checked = 0
        new_found = 0
        try:
            # Sweep every followed series: ``known_chapters`` is kept fresh even
            # when the row's ``notify`` flag is off, so flipping it on later does
            # not backfill a notification storm. ``notify`` gates only whether a
            # new chapter produces an ``update_notifications`` row (``_check_one``).
            #
            # The id-less full sweep is deliberately unscoped — it is the
            # scheduler's job to check every account. Targeted ids went through
            # ``resolve_followed_ids`` above.
            stmt = select(FollowedSeries)
            if followed_ids:
                stmt = stmt.where(FollowedSeries.id.in_(followed_ids))
            rows = self._db.execute(stmt).scalars().all()

            # Guardrails (audit finding 14): the sweep is a sequential,
            # network-bound walk with a 30s×3-retry budget per fetch, so a
            # large followed set plus a wedged upstream used to make a single
            # run outlast its check interval by hours. Two ceilings, both
            # env-tunable and disabled at 0:
            #   * per-source HTTP budget — once a source has burned its
            #     seconds this pass, its remaining rows are skipped (their
            #     snapshots are untouched; the next run retries them);
            #   * whole-run deadline — the pass stops checking and reports
            #     how much it left on the table.
            cfg = get_settings()
            source_budget = max(0, cfg.update_sweep_source_budget_seconds)
            deadline = max(0, cfg.update_sweep_deadline_minutes) * 60
            sweep_started = _monotonic()
            source_spent: dict[str, float] = {}

            for row in rows:
                if deadline and _monotonic() - sweep_started >= deadline:
                    remaining = len(rows) - checked
                    run.error = (
                        f"Sweep deadline reached; {remaining} of {len(rows)} "
                        "series not checked this pass."
                    )
                    logger.warning("update sweep hit its deadline: %s", run.error)
                    break
                if (
                    source_budget
                    and source_spent.get(row.source_id, 0.0) >= source_budget
                ):
                    logger.debug(
                        "update sweep skipping %s/%s: source budget spent",
                        row.source_id,
                        row.series_key,
                    )
                    continue
                row_started = _monotonic()
                try:
                    new_found += self._check_one(row)
                    checked += 1
                except Exception as exc:  # noqa: BLE001 - one dead source never aborts the sweep
                    row.last_error = str(exc)[:500]
                    logger.warning(
                        "update check failed for %s/%s: %s",
                        row.source_id,
                        row.series_key,
                        exc,
                    )
                finally:
                    source_spent[row.source_id] = source_spent.get(
                        row.source_id, 0.0
                    ) + (_monotonic() - row_started)
                self._db.commit()
            run.status = "completed"
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)[:500]
            logger.exception("update run failed")
        finally:
            run.series_checked = checked
            run.new_chapters_found = new_found
            run.finished_at = utcnow()
            settings = self.get_global_settings()
            settings.last_run_at = run.finished_at
            self._db.commit()

        return self.serialize_run(run)

    def check_followed_by_id(self, followed_id: int) -> dict[str, Any]:
        return self.run_check(trigger="manual", followed_ids=[followed_id])

    # legacy alias kept for routes/scheduler that still say "tracker"
    def check_tracker_by_id(self, tracker_id: int) -> dict[str, Any]:
        return self.check_followed_by_id(tracker_id)

    def _check_one(self, row: FollowedSeries) -> int:
        """Diff one followed series against its live connector chapter list.

        Returns the number of new chapters found.
        """
        # Local import: browse_service pulls in the connector stack, and the
        # scheduler builds this service on a bare session.
        from services.browse_service import BrowseService
        from services.source_cache_service import SourceCacheService

        browse = BrowseService(db=self._db)
        cache = SourceCacheService(self._db, browse)

        live = browse.get_chapters(row.source_id, row.series_key)
        known = _loads(row.known_chapters)

        if not live and known:
            # A connector that *degrades* to an empty list rather than raising
            # (markup drifted, a soft block, an empty page) is not evidence the
            # series lost every chapter. Writing [] here is unrecoverable: the
            # next run has no baseline, so every chapter released in between
            # never diffs as new and never notifies. Keep the snapshot, record
            # why, and let the next pass try again.
            row.last_error = "Source returned no chapters; snapshot kept."
            logger.warning(
                "update check for %s/%s returned an empty chapter list; "
                "keeping the %d-chapter snapshot",
                row.source_id,
                row.series_key,
                len(known),
            )
            return 0

        cache.write_through(row.source_id, row.series_key, {}, live)
        known_keys = {str(c.get("key")) for c in known}

        new_chapters = [c for c in live if str(c["id"]) not in known_keys]
        settings = self.get_global_settings()
        if (
            new_chapters
            and known
            and _bool(row.notify)
            and _bool(settings.notify_enabled)
        ):
            for c in new_chapters:
                self._db.add(
                    UpdateNotification(
                        user_id=row.user_id,
                        profile_id=row.profile_id,
                        followed_series_id=row.id,
                        source_id=row.source_id,
                        series_key=row.series_key,
                        chapter_key=str(c["id"]),
                        chapter_title=str(c.get("title") or c["id"]),
                        chapter_number=c.get("number"),
                    )
                )

        row.known_chapters = json.dumps(
            [
                {
                    "key": c.get("id"),
                    "number": c.get("number"),
                    "title": c.get("title"),
                    "published_at": c.get("release_date"),
                }
                for c in live
            ]
        )
        row.last_checked_at = utcnow()
        row.last_error = None
        return len(new_chapters) if known else 0


def run_check_in_new_session(
    *,
    trigger: str = "scheduled",
    followed_ids: list[int] | None = None,
    tracker_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Entry point for the background worker — owns its own session.

    ``system=True``: there is no request context here, and the scheduled sweep
    legitimately walks every account. Ids that arrive on this path have already
    been ownership-checked by the route that queued them
    (``UpdateService.resolve_followed_ids``).
    """
    db = SessionLocal()
    try:
        return UpdateService(db, system=True).run_check(
            trigger=trigger, followed_ids=followed_ids or tracker_ids
        )
    finally:
        db.close()


def get_update_service(
    db: Session,
    *,
    user_id: int | None = None,
    profile_id: int | None = None,
) -> UpdateService:
    return UpdateService(db, user_id=user_id, profile_id=profile_id)


def get_update_service_dep(
    db: Annotated[Session, Depends(get_db)],
) -> UpdateService:
    return UpdateService(db)
