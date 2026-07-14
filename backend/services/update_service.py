"""Automatic update engine: track series, detect new chapters, emit notifications.

Uses connectors read-only via ``connectors.registry.create_connector``.
Auto-download is gated behind per-series and global settings; the hook
``on_new_chapters`` can be wired later without modifying the download manager.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
from sqlalchemy.orm import Session

from connectors.models import Chapter as ConnectorChapter
from connectors.registry import create_connector, list_installed_connectors
from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import (
    Download,
    SeriesTracker,
    UpdateNotification,
    UpdateRun,
    UpdateSettings,
    User,
)
from database.session import SessionLocal

logger = logging.getLogger(__name__)

NewChaptersCallback = Callable[
    [Session, SeriesTracker, list[ConnectorChapter]],
    None,
]

_on_new_chapters: NewChaptersCallback | None = None


def register_new_chapters_callback(callback: NewChaptersCallback | None) -> None:
    """Register a hook for future auto-download integration."""
    global _on_new_chapters
    _on_new_chapters = callback


def _bool(value: bool | int) -> bool:
    return bool(value)


def _load_known_ids(raw: str) -> set[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return {str(item) for item in data}
    except json.JSONDecodeError:
        pass
    return set()


def _dump_known_ids(ids: set[str]) -> str:
    return json.dumps(sorted(ids))


class UpdateService:
    """Business logic for the automatic update subsystem."""

    def __init__(
        self,
        db: Session,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        # Follows and notifications are per-(user, profile). The background
        # scheduler runs with user_id=None/profile_id=None but never uses them to
        # scope — it checks every user's trackers and stamps each notification
        # with the tracker's own owner + profile.
        self._user_id = user_id
        self._profile_id = profile_id

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_global_settings(self) -> UpdateSettings:
        # Fast path: row already in DB (normal case after first startup).
        row = self._db.get(UpdateSettings, 1)
        if row is not None:
            return row

        # Slow path: first ever startup. Use INSERT OR IGNORE so concurrent
        # sessions racing here (scheduler thread vs main thread) can never
        # collide on the UNIQUE primary-key constraint.
        config = get_settings()
        self._db.execute(
            _sqlite_insert(UpdateSettings)
            .values(
                id=1,
                enabled=True,
                check_interval_minutes=config.update_check_interval_minutes,
                notify_enabled=True,
                auto_download_enabled=False,
                check_on_startup=True,
            )
            .on_conflict_do_nothing()
        )
        row = self._db.get(UpdateSettings, 1)
        assert row is not None, "update_settings singleton (id=1) missing after upsert"
        return row

    def update_global_settings(self, payload: dict[str, Any]) -> dict[str, object]:
        row = self.get_global_settings()
        if "enabled" in payload:
            row.enabled = bool(payload["enabled"])
        if "check_interval_minutes" in payload:
            minutes = int(payload["check_interval_minutes"])
            if minutes < 5:
                raise AppError("check_interval_minutes must be at least 5", status_code=400)
            row.check_interval_minutes = minutes
        if "notify_enabled" in payload:
            row.notify_enabled = bool(payload["notify_enabled"])
        if "auto_download_enabled" in payload:
            row.auto_download_enabled = bool(payload["auto_download_enabled"])
        if "check_on_startup" in payload:
            row.check_on_startup = bool(payload["check_on_startup"])
        self._db.flush()
        self._db.commit()
        return self.serialize_settings(row)

    def serialize_settings(self, row: UpdateSettings) -> dict[str, object]:
        return {
            "enabled": _bool(row.enabled),
            "check_interval_minutes": row.check_interval_minutes,
            "notify_enabled": _bool(row.notify_enabled),
            "auto_download_enabled": _bool(row.auto_download_enabled),
            "check_on_startup": _bool(row.check_on_startup),
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ------------------------------------------------------------------
    # Trackers
    # ------------------------------------------------------------------

    def list_trackers(
        self,
        *,
        track_kind: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, object]]:
        query = (
            self._db.query(SeriesTracker)
            .filter(
                SeriesTracker.user_id == self._user_id,
                SeriesTracker.profile_id == self._profile_id,
            )
            .order_by(SeriesTracker.series_title)
        )
        if track_kind:
            query = query.filter(SeriesTracker.track_kind == track_kind)
        if source:
            query = query.filter(SeriesTracker.source == source)
        return [self.serialize_tracker(row) for row in query.all()]

    def count_trackers(
        self,
        *,
        track_kind: str | None = None,
        source: str | None = None,
    ) -> int:
        query = self._db.query(SeriesTracker).filter(
            SeriesTracker.user_id == self._user_id,
            SeriesTracker.profile_id == self._profile_id,
        )
        if track_kind:
            query = query.filter(SeriesTracker.track_kind == track_kind)
        if source:
            query = query.filter(SeriesTracker.source == source)
        return query.count()

    def serialize_tracker(self, row: SeriesTracker) -> dict[str, object]:
        known = _load_known_ids(row.known_chapter_ids)
        return {
            "id": row.id,
            "source": row.source,
            "source_id": row.source,
            "series_id": row.series_id,
            "series_title": row.series_title,
            "track_kind": row.track_kind,
            "local_series_id": row.local_series_id,
            "enabled": _bool(row.enabled),
            "notify": _bool(row.notify),
            "auto_download": _bool(row.auto_download),
            "check_interval_minutes": row.check_interval_minutes,
            "known_chapter_count": len(known),
            "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
            "last_error": row.last_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def follow_series(
        self,
        *,
        source: str,
        series_id: str,
        series_title: str,
    ) -> dict[str, object]:
        self._ensure_browsable_source(source)
        # Scoped to this (user, profile): the composite unique now includes
        # profile_id, so a second profile on the same account follows the same
        # remote series as its OWN independent row rather than colliding on the
        # first profile's tracker.
        existing = (
            self._db.query(SeriesTracker)
            .filter(
                SeriesTracker.user_id == self._user_id,
                SeriesTracker.profile_id == self._profile_id,
                SeriesTracker.source == source,
                SeriesTracker.series_id == series_id,
                SeriesTracker.track_kind == "followed",
            )
            .first()
        )
        if existing is not None:
            return self.serialize_tracker(existing)

        row = SeriesTracker(
            user_id=self._user_id,
            profile_id=self._profile_id,
            source=source,
            series_id=series_id,
            series_title=series_title,
            track_kind="followed",
        )
        self._db.add(row)
        self._db.flush()
        self._db.commit()
        return self.serialize_tracker(row)

    def unfollow_tracker(self, tracker_id: int) -> None:
        row = self._require_tracker(tracker_id)
        if row.track_kind == "downloaded":
            raise AppError("Downloaded series trackers cannot be removed directly", status_code=400)
        self._db.delete(row)
        self._db.commit()

    def update_tracker(self, tracker_id: int, payload: dict[str, Any]) -> dict[str, object]:
        row = self._require_tracker(tracker_id)
        if "enabled" in payload:
            row.enabled = bool(payload["enabled"])
        if "notify" in payload:
            row.notify = bool(payload["notify"])
        if "auto_download" in payload:
            row.auto_download = bool(payload["auto_download"])
        if "check_interval_minutes" in payload:
            value = payload["check_interval_minutes"]
            if value is None:
                row.check_interval_minutes = None
            else:
                minutes = int(value)
                if minutes < 5:
                    raise AppError("check_interval_minutes must be at least 5", status_code=400)
                row.check_interval_minutes = minutes
        if "series_title" in payload and payload["series_title"]:
            row.series_title = str(payload["series_title"])
        self._db.flush()
        self._db.commit()
        return self.serialize_tracker(row)

    def sync_downloaded_trackers(self) -> dict[str, object]:
        """Create or refresh downloaded-series trackers from completed downloads."""
        rows = (
            self._db.query(
                Download.source,
                Download.series_id,
                func.max(Download.series_title).label("series_title"),
            )
            .filter(
                Download.status == "completed",
                Download.user_id == self._user_id,
            )
            .group_by(Download.source, Download.series_id)
            .all()
        )
        created = 0
        updated = 0
        for source, series_id, series_title in rows:
            tracker = (
                self._db.query(SeriesTracker)
                .filter(
                    SeriesTracker.user_id == self._user_id,
                    SeriesTracker.profile_id == self._profile_id,
                    SeriesTracker.source == source,
                    SeriesTracker.series_id == series_id,
                    SeriesTracker.track_kind == "downloaded",
                )
                .first()
            )
            if tracker is None:
                self._db.add(
                    SeriesTracker(
                        user_id=self._user_id,
                        profile_id=self._profile_id,
                        source=source,
                        series_id=series_id,
                        series_title=series_title or series_id,
                        track_kind="downloaded",
                    )
                )
                created += 1
            elif series_title and tracker.series_title != series_title:
                tracker.series_title = series_title
                updated += 1
        self._db.flush()
        self._db.commit()
        return {"created": created, "updated": updated, "total": len(rows)}

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def list_notifications(
        self,
        *,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        query = (
            self._db.query(UpdateNotification)
            .filter(
                UpdateNotification.user_id == self._user_id,
                UpdateNotification.profile_id == self._profile_id,
            )
            .order_by(UpdateNotification.created_at.desc())
        )
        if unread_only:
            query = query.filter(UpdateNotification.is_read.is_(False))
        rows = query.limit(max(1, min(limit, 500))).all()
        return [self.serialize_notification(row) for row in rows]

    def count_notifications(self, *, unread_only: bool = False) -> int:
        query = self._db.query(UpdateNotification).filter(
            UpdateNotification.user_id == self._user_id,
            UpdateNotification.profile_id == self._profile_id,
        )
        if unread_only:
            query = query.filter(UpdateNotification.is_read.is_(False))
        return query.count()

    def unread_count(self) -> int:
        return (
            self._db.query(UpdateNotification)
            .filter(
                UpdateNotification.user_id == self._user_id,
                UpdateNotification.profile_id == self._profile_id,
                UpdateNotification.is_read.is_(False),
            )
            .count()
        )

    def serialize_notification(self, row: UpdateNotification) -> dict[str, object]:
        return {
            "id": row.id,
            "tracker_id": row.tracker_id,
            "source": row.source,
            "source_id": row.source,
            "series_id": row.series_id,
            "series_title": row.series_title,
            "chapter_id": row.chapter_id,
            "chapter_title": row.chapter_title,
            "chapter_number": row.chapter_number,
            "is_read": _bool(row.is_read),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def mark_notification_read(self, notification_id: int) -> dict[str, object]:
        row = (
            self._db.query(UpdateNotification)
            .filter(
                UpdateNotification.id == notification_id,
                UpdateNotification.user_id == self._user_id,
                UpdateNotification.profile_id == self._profile_id,
            )
            .first()
        )
        if row is None:
            raise AppError("Notification not found", status_code=404)
        row.is_read = True
        self._db.flush()
        self._db.commit()
        return self.serialize_notification(row)

    def mark_all_notifications_read(self) -> dict[str, int]:
        count = (
            self._db.query(UpdateNotification)
            .filter(
                UpdateNotification.user_id == self._user_id,
                UpdateNotification.profile_id == self._profile_id,
                UpdateNotification.is_read.is_(False),
            )
            .update({UpdateNotification.is_read: True})
        )
        self._db.commit()
        return {"marked_read": count}

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def list_runs(self, *, limit: int = 20) -> list[dict[str, object]]:
        rows = (
            self._db.query(UpdateRun)
            .order_by(UpdateRun.started_at.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [self.serialize_run(row) for row in rows]

    def count_runs(self) -> int:
        return self._db.query(UpdateRun).count()

    def get_run(self, run_id: int) -> dict[str, object]:
        row = self._db.query(UpdateRun).filter(UpdateRun.id == run_id).first()
        if row is None:
            raise AppError("Update run not found", status_code=404)
        return self.serialize_run(row)

    def serialize_run(self, row: UpdateRun) -> dict[str, object]:
        return {
            "id": row.id,
            "trigger": row.trigger,
            "status": row.status,
            "series_checked": row.series_checked,
            "new_chapters_found": row.new_chapters_found,
            "error": row.error,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }

    # ------------------------------------------------------------------
    # Check engine
    # ------------------------------------------------------------------

    def run_check(
        self,
        *,
        trigger: str = "manual",
        tracker_ids: list[int] | None = None,
    ) -> dict[str, object]:
        settings = self.get_global_settings()
        if not _bool(settings.enabled) and trigger == "scheduled":
            return {"skipped": True, "reason": "updates_disabled"}

        run = UpdateRun(trigger=trigger, status="running")
        self._db.add(run)
        self._db.flush()

        try:
            trackers = self._select_trackers_for_check(tracker_ids)
            force = tracker_ids is not None
            new_total = 0
            checked = 0
            for tracker in trackers:
                if not force and not self._is_due(tracker, settings):
                    continue
                new_count = self._check_tracker(tracker, settings)
                new_total += new_count
                checked += 1

            run.status = "completed"
            run.series_checked = checked
            run.new_chapters_found = new_total
            run.finished_at = utcnow()
            settings.last_run_at = run.finished_at
            self._db.flush()
            return self.serialize_run(run)
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            self._db.flush()
            logger.exception("Update check failed")
            raise

    def check_tracker_by_id(self, tracker_id: int) -> dict[str, object]:
        tracker = self._require_tracker(tracker_id)
        settings = self.get_global_settings()
        new_count = self._check_tracker(tracker, settings)
        return {
            "tracker_id": tracker_id,
            "new_chapters": new_count,
            "tracker": self.serialize_tracker(tracker),
        }

    def _select_trackers_for_check(self, tracker_ids: list[int] | None) -> list[SeriesTracker]:
        query = self._db.query(SeriesTracker).filter(SeriesTracker.enabled.is_(True))
        if tracker_ids:
            query = query.filter(SeriesTracker.id.in_(tracker_ids))
        return query.order_by(SeriesTracker.source, SeriesTracker.series_title).all()

    def _is_due(self, tracker: SeriesTracker, settings: UpdateSettings) -> bool:
        if tracker.last_checked_at is None:
            return True
        interval = tracker.check_interval_minutes or settings.check_interval_minutes
        due_at = tracker.last_checked_at + timedelta(minutes=interval)
        return utcnow() >= due_at

    def _check_tracker(self, tracker: SeriesTracker, settings: UpdateSettings) -> int:
        try:
            connector = create_connector(tracker.source)
            remote_chapters = connector.get_chapters(tracker.series_id)
        except Exception as exc:
            tracker.last_error = str(exc)
            tracker.last_checked_at = utcnow()
            self._db.flush()
            logger.warning(
                "Failed to check %s/%s: %s",
                tracker.source,
                tracker.series_id,
                exc,
            )
            return 0

        known_ids = _load_known_ids(tracker.known_chapter_ids)
        remote_by_id = {chapter.id: chapter for chapter in remote_chapters}
        remote_ids = set(remote_by_id)

        if not known_ids:
            tracker.known_chapter_ids = _dump_known_ids(remote_ids)
            tracker.last_checked_at = utcnow()
            tracker.last_error = None
            self._db.flush()
            return 0

        new_ids = sorted(remote_ids - known_ids, key=lambda cid: _chapter_sort_key(remote_by_id[cid]))
        new_chapters = [remote_by_id[cid] for cid in new_ids]
        notify_enabled = _bool(settings.notify_enabled) and _bool(tracker.notify)

        if new_chapters and notify_enabled:
            for chapter in new_chapters:
                self._db.add(
                    UpdateNotification(
                        user_id=tracker.user_id,
                        profile_id=tracker.profile_id,
                        tracker_id=tracker.id,
                        source=tracker.source,
                        series_id=tracker.series_id,
                        series_title=tracker.series_title,
                        chapter_id=chapter.id,
                        chapter_title=chapter.title,
                        chapter_number=chapter.number,
                    )
                )

        auto_download = (
            _bool(settings.auto_download_enabled)
            and _bool(tracker.auto_download)
            and bool(new_chapters)
        )
        if auto_download and _on_new_chapters is not None:
            _on_new_chapters(self._db, tracker, new_chapters)

        tracker.known_chapter_ids = _dump_known_ids(remote_ids)
        tracker.last_checked_at = utcnow()
        tracker.last_error = None
        self._db.flush()
        return len(new_chapters)

    def _require_tracker(self, tracker_id: int) -> SeriesTracker:
        row = (
            self._db.query(SeriesTracker)
            .filter(
                SeriesTracker.id == tracker_id,
                SeriesTracker.user_id == self._user_id,
                SeriesTracker.profile_id == self._profile_id,
            )
            .first()
        )
        if row is None:
            raise AppError("Tracker not found", status_code=404)
        return row

    def _ensure_browsable_source(self, source: str) -> None:
        installed = {item.source_type for item in list_installed_connectors(browsable_only=True)}
        if source not in installed:
            raise AppError(f"Unknown or non-browsable source '{source}'", status_code=400)

    def list_sources(self) -> list[dict[str, str]]:
        return [
            {
                "source_type": item.source_type,
                "name": item.name,
            }
            for item in list_installed_connectors(browsable_only=True)
        ]


def _chapter_sort_key(chapter: ConnectorChapter) -> tuple[float, str]:
    if chapter.number is not None:
        return (chapter.number, chapter.title)
    return (10**9, chapter.title)


def get_update_service(
    db: Session,
    user_id: int | None = None,
    profile_id: int | None = None,
) -> UpdateService:
    return UpdateService(db, user_id=user_id, profile_id=profile_id)


def run_check_in_new_session(
    *, trigger: str, tracker_ids: list[int] | None = None
) -> dict[str, object]:
    """Run an update check with its own DB session (for background workers)."""
    db = SessionLocal()
    try:
        service = UpdateService(db)
        result = service.run_check(trigger=trigger, tracker_ids=tracker_ids)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
