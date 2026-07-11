"""API-facing download queue operations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.orm import Session, joinedload

from connectors.registry import create_connector
from core.config import get_settings, update_persisted_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import Download, DownloadQueue, SourceChapterLink, User
from database.session import get_db
from services.auth_service import get_optional_user
from services.download_manager import DownloadManager, get_download_manager
from services.download_support import DiskSpaceError, infer_queue_priority

logger = logging.getLogger(__name__)

#: Bounds enforced on every download setting, independent of the frontend's
#: own dropdown/limits -- the API must not trust the client.
_SETTING_BOUNDS: dict[str, tuple[float, float]] = {
    "download_concurrent_chapters": (1, 10),
    "download_page_concurrency": (1, 10),
    "download_retry_count": (0, 10),
    "download_retry_delay_seconds": (0.0, 30.0),
    "download_timeout_seconds": (1.0, 300.0),
}

#: Settings persisted as floats; everything else in _SETTING_BOUNDS is an int.
_FLOAT_SETTINGS = {"download_retry_delay_seconds", "download_timeout_seconds"}


class DownloadService:
    def __init__(
        self, db: Session, manager: DownloadManager, user_id: int | None = None
    ) -> None:
        self._db = db
        self._manager = manager
        self._settings = get_settings()
        # The queue is owned per user (who requested each download); the shared
        # worker still processes everyone's queue, and de-dup stays global so a
        # chapter already in the shared library is never re-fetched.
        self._user_id = user_id

    def list_downloads(self) -> list[dict[str, Any]]:
        rows = (
            self._db.query(Download)
            .filter(Download.user_id == self._user_id)
            .options(joinedload(Download.queue))
            .order_by(Download.created_at.desc())
            .all()
        )
        return [self._serialize_download(row) for row in rows]

    def get_metrics(self) -> dict[str, Any]:
        return self._manager.get_metrics(self._db)

    def get_download_settings(self) -> dict[str, Any]:
        settings = get_settings()
        return {
            "download_concurrent_chapters": settings.download_concurrent_chapters,
            "download_page_concurrency": settings.download_page_concurrency,
            "download_retry_count": settings.download_retry_count,
            "download_retry_delay_seconds": settings.download_retry_delay_seconds,
            "download_timeout_seconds": settings.download_timeout_seconds,
            "active_download_count": self._manager.active_count,
        }

    def update_download_settings(self, **changes: object) -> dict[str, Any]:
        """Persist the given download settings to config/settings.json and
        apply them immediately -- no restart required. Only
        download_concurrent_chapters needs an explicit push to the running
        DownloadManager (it's read once at construction time); every other
        setting is already re-read fresh from get_settings() on each use."""
        validated: dict[str, object] = {}
        for key, value in changes.items():
            if key not in _SETTING_BOUNDS or value is None:
                continue
            low, high = _SETTING_BOUNDS[key]
            numeric = float(value)
            if numeric < low or numeric > high:
                raise AppError(
                    f"{key} must be between {low} and {high}.",
                    code="validation_error",
                    status_code=422,
                    details={"field": key, "min": low, "max": high},
                )
            validated[key] = numeric if key in _FLOAT_SETTINGS else int(numeric)

        if not validated:
            return self.get_download_settings()

        updated = update_persisted_settings(**validated)
        if "download_concurrent_chapters" in validated:
            self._manager.set_max_workers(updated.download_concurrent_chapters)
        return self.get_download_settings()

    def queue_chapters(
        self,
        *,
        source_id: str,
        series_id: str,
        chapter_ids: list[str],
        series_title: str | None = None,
        chapter_titles: dict[str, str] | None = None,
        priority: int | None = None,
        series_queue: bool = False,
    ) -> dict[str, Any]:
        if not chapter_ids:
            raise AppError(
                "No chapters selected.",
                code="no_chapters",
                status_code=400,
            )

        connector = self._get_browsable_connector(source_id)
        resolved_series_title = series_title
        if not resolved_series_title:
            series = connector.get_series(series_id)
            if series is None:
                raise AppError(
                    "Series not found.",
                    code="series_not_found",
                    status_code=404,
                )
            resolved_series_title = series.title

        chapters = connector.get_chapters(series_id)
        chapter_map = {chapter.id: chapter for chapter in chapters}
        titles = chapter_titles or {}
        resolved_priority = infer_queue_priority(
            chapter_count=len(chapter_ids),
            series_queue=series_queue,
            explicit=priority,
        )

        warnings: list[str] = []
        try:
            total_pages = sum(
                (chapter_map.get(chapter_id).page_count if chapter_map.get(chapter_id) else 1)
                for chapter_id in chapter_ids
            )
            warnings.extend(self._manager.check_disk_before_queue(page_count=total_pages))
        except DiskSpaceError as exc:
            raise AppError(
                str(exc),
                code="insufficient_disk_space",
                status_code=507,
            ) from exc

        queued: list[int] = []
        skipped: list[str] = []
        for chapter_id in chapter_ids:
            if self._is_already_downloaded(source_id, series_id, chapter_id):
                logger.info(
                    "chapter_id=%s queued=no skipped_reason=already_downloaded",
                    chapter_id,
                )
                skipped.append(chapter_id)
                continue
            existing = self._find_active_download(source_id, series_id, chapter_id)
            if existing is not None:
                logger.info(
                    "chapter_id=%s queued=no skipped_reason=active_download_exists",
                    chapter_id,
                )
                skipped.append(chapter_id)
                continue

            chapter = chapter_map.get(chapter_id)
            chapter_title = titles.get(chapter_id) or (chapter.title if chapter else chapter_id)
            download = Download(
                user_id=self._user_id,
                source=source_id,
                series_id=series_id,
                chapter_id=chapter_id,
                series_title=resolved_series_title,
                chapter_title=chapter_title,
                status="queued",
                progress=0.0,
            )
            self._db.add(download)
            self._db.flush()
            queue_row = DownloadQueue(
                download_id=download.id,
                priority=resolved_priority,
                state="pending",
            )
            self._db.add(queue_row)
            queued.append(download.id)
            logger.info("chapter_id=%s queued=yes download_id=%d", chapter_id, download.id)

        self._db.commit()
        self._manager.notify_change()
        logger.info(
            "series_id=%s chapters_returned=%d queued=%d skipped=%d",
            series_id,
            len(chapter_map),
            len(queued),
            len(skipped),
        )
        return {"queued": queued, "skipped": skipped, "warnings": warnings}

    def queue_series(
        self,
        *,
        source_id: str,
        series_id: str,
        priority: int | None = None,
    ) -> dict[str, Any]:
        connector = self._get_browsable_connector(source_id)
        series = connector.get_series(series_id)
        if series is None:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
            )
        chapters = connector.get_chapters(series_id)
        # Queue every chapter the connector reports for this series. Some
        # connectors (e.g. MangaKatana) only learn a chapter's page_count
        # lazily, after its pages have been fetched once via the reader --
        # page_count == 0 means "not yet opened," not "empty." Filtering on
        # it here excluded every chapter except whichever ones happened to
        # have already been read, collapsing "download entire series" down
        # to just those.
        chapter_ids = [chapter.id for chapter in chapters]
        return self.queue_chapters(
            source_id=source_id,
            series_id=series_id,
            chapter_ids=chapter_ids,
            series_title=series.title,
            chapter_titles={chapter.id: chapter.title for chapter in chapters},
            priority=priority,
            series_queue=True,
        )

    def pause(self, download_id: int) -> dict[str, Any]:
        download = self._get_download(download_id)
        if download.status in ("completed", "cancelled"):
            raise AppError(
                "Download cannot be paused.",
                code="invalid_state",
                status_code=400,
            )
        download.status = "paused"
        download.updated_at = utcnow()
        if download.queue:
            download.queue.state = "paused"
        self._db.commit()
        return self._serialize_download(download)

    def resume(self, download_id: int) -> dict[str, Any]:
        download = self._get_download(download_id)
        if download.status not in ("paused", "failed"):
            raise AppError(
                "Only paused or failed downloads can be resumed.",
                code="invalid_state",
                status_code=400,
            )
        if self._is_already_downloaded(download.source, download.series_id, download.chapter_id):
            download.status = "completed"
            download.progress = 100.0
            if download.queue:
                download.queue.state = "completed"
            self._db.commit()
            return self._serialize_download(download)

        download.status = "queued"
        download.error = None
        download.updated_at = utcnow()
        if download.queue:
            download.queue.state = "pending"
        self._db.commit()
        self._manager.notify_change()
        return self._serialize_download(download)

    def cancel(self, download_id: int) -> dict[str, Any]:
        download = self._get_download(download_id)
        if download.status == "completed":
            raise AppError(
                "Completed downloads cannot be cancelled.",
                code="invalid_state",
                status_code=400,
            )
        download.status = "cancelled"
        download.updated_at = utcnow()
        if download.queue:
            download.queue.state = "cancelled"
        self._db.commit()
        return self._serialize_download(download)

    # ------------------------------------------------------------------
    # Bulk operations: series-scoped and global.
    #
    # Unlike the single-download variants above, these never raise for a
    # row that isn't in a qualifying state -- they silently skip it and
    # report how many rows were actually affected. A "pause series" click
    # naturally includes chapters that are already completed or cancelled;
    # that isn't an error, just a no-op for that row.
    # ------------------------------------------------------------------

    def _bulk_query(self, *, source_id: str | None, series_id: str | None):
        query = (
            self._db.query(Download)
            .filter(Download.user_id == self._user_id)
            .options(joinedload(Download.queue))
        )
        if source_id is not None:
            query = query.filter(Download.source == source_id)
        if series_id is not None:
            query = query.filter(Download.series_id == series_id)
        return query

    def pause_bulk(
        self, *, source_id: str | None = None, series_id: str | None = None
    ) -> dict[str, Any]:
        rows = self._bulk_query(source_id=source_id, series_id=series_id).filter(
            Download.status.in_(("queued", "downloading"))
        ).all()
        for row in rows:
            row.status = "paused"
            row.updated_at = utcnow()
            if row.queue:
                row.queue.state = "paused"
        self._db.commit()
        return {"affected": len(rows)}

    def resume_bulk(
        self, *, source_id: str | None = None, series_id: str | None = None
    ) -> dict[str, Any]:
        rows = self._bulk_query(source_id=source_id, series_id=series_id).filter(
            Download.status.in_(("paused", "failed"))
        ).all()
        resumed = 0
        for row in rows:
            if self._is_already_downloaded(row.source, row.series_id, row.chapter_id):
                row.status = "completed"
                row.progress = 100.0
                if row.queue:
                    row.queue.state = "completed"
                continue
            row.status = "queued"
            row.error = None
            row.updated_at = utcnow()
            if row.queue:
                row.queue.state = "pending"
            resumed += 1
        self._db.commit()
        if resumed:
            self._manager.notify_change()
        return {"affected": resumed}

    def cancel_bulk(
        self, *, source_id: str | None = None, series_id: str | None = None
    ) -> dict[str, Any]:
        rows = self._bulk_query(source_id=source_id, series_id=series_id).filter(
            Download.status.notin_(("completed", "cancelled"))
        ).all()
        for row in rows:
            row.status = "cancelled"
            row.updated_at = utcnow()
            if row.queue:
                row.queue.state = "cancelled"
        self._db.commit()
        return {"affected": len(rows)}

    def retry(self, download_id: int) -> dict[str, Any]:
        download = self._get_download(download_id)
        if download.status not in ("failed", "paused"):
            raise AppError(
                "Only failed or paused downloads can be retried.",
                code="invalid_state",
                status_code=400,
            )
        if download.queue:
            download.queue.retry_count += 1
            download.queue.state = "pending"
        download.status = "queued"
        download.error = None
        download.updated_at = utcnow()
        self._db.commit()
        self._manager.notify_change()
        return self._serialize_download(download)

    def move_queue_item(self, download_id: int, *, direction: str) -> dict[str, Any]:
        """Reorder a queued download earlier or later within its own series'
        dispatch queue, by swapping priority with the adjacent sibling.

        Dispatch order is ``DownloadQueue.priority ASC`` (see
        ``DownloadManager``'s scheduler), so "up" (dispatched sooner) swaps
        with the next lower-priority neighbour and "down" the next
        higher-priority one. Only downloads still pending dispatch
        (``status="queued"``, queue ``state="pending"``) participate --
        matching exactly what the scheduler itself considers eligible.
        Already at the front/back of its own series' queue is a no-op, not
        an error, since a client can't easily tell in advance.
        """
        if direction not in ("up", "down"):
            raise AppError(
                "direction must be 'up' or 'down'.",
                code="invalid_direction",
                status_code=422,
            )

        download = self._get_download(download_id)
        if (
            download.queue is None
            or download.status != "queued"
            or download.queue.state != "pending"
        ):
            raise AppError(
                "Only queued downloads waiting to start can be reordered.",
                code="invalid_state",
                status_code=400,
            )

        siblings = (
            self._db.query(Download)
            .join(DownloadQueue)
            .options(joinedload(Download.queue))
            .filter(
                Download.source == download.source,
                Download.series_id == download.series_id,
                Download.status == "queued",
                DownloadQueue.state == "pending",
            )
            .order_by(DownloadQueue.priority.asc(), Download.created_at.asc())
            .all()
        )
        index = next(
            (i for i, row in enumerate(siblings) if row.id == download.id), None
        )
        if index is None:
            return self._serialize_download(download)

        neighbour_index = index - 1 if direction == "up" else index + 1
        if neighbour_index < 0 or neighbour_index >= len(siblings):
            return self._serialize_download(download)

        neighbour = siblings[neighbour_index]
        download.queue.priority, neighbour.queue.priority = (
            neighbour.queue.priority,
            download.queue.priority,
        )
        self._db.commit()
        self._manager.notify_change()
        return self._serialize_download(download)

    def _get_browsable_connector(self, source_id: str):
        try:
            connector = create_connector(source_id)
        except ValueError as exc:
            raise AppError(
                "Source not found.",
                code="source_not_found",
                status_code=404,
            ) from exc
        if not connector.is_browsable:
            raise AppError(
                "Source is not browsable.",
                code="source_not_browsable",
                status_code=400,
            )
        return connector

    def _get_download(self, download_id: int) -> Download:
        download = (
            self._db.query(Download)
            .options(joinedload(Download.queue))
            .filter(Download.id == download_id, Download.user_id == self._user_id)
            .first()
        )
        if download is None:
            raise AppError(
                "Download not found.",
                code="download_not_found",
                status_code=404,
            )
        return download

    def _is_already_downloaded(self, source: str, series_id: str, chapter_id: str) -> bool:
        link = (
            self._db.query(SourceChapterLink)
            .filter(
                SourceChapterLink.source == source,
                SourceChapterLink.series_id == series_id,
                SourceChapterLink.chapter_id == chapter_id,
            )
            .first()
        )
        if link is not None:
            return True
        completed = (
            self._db.query(Download)
            .filter(
                Download.source == source,
                Download.series_id == series_id,
                Download.chapter_id == chapter_id,
                Download.status == "completed",
            )
            .first()
        )
        return completed is not None

    def _find_active_download(self, source: str, series_id: str, chapter_id: str) -> Download | None:
        return (
            self._db.query(Download)
            .filter(
                Download.source == source,
                Download.series_id == series_id,
                Download.chapter_id == chapter_id,
                Download.status.in_(("queued", "downloading", "paused")),
            )
            .first()
        )

    def _serialize_download(self, download: Download) -> dict[str, Any]:
        speed_bps, eta_seconds, speed_mbps = self._manager.get_speed_snapshot(download)
        queue = download.queue
        return {
            "id": download.id,
            "source": download.source,
            "source_id": download.source,
            "series_id": download.series_id,
            "chapter_id": download.chapter_id,
            "series_title": download.series_title,
            "chapter_title": download.chapter_title,
            "status": download.status,
            "progress": download.progress,
            "pages_done": download.pages_done,
            "pages_total": download.pages_total,
            "bytes_downloaded": download.bytes_downloaded,
            "speed_bps": speed_bps,
            "speed_mbps": speed_mbps,
            "eta_seconds": eta_seconds,
            "local_chapter_id": download.local_chapter_id,
            "created_at": download.created_at.isoformat(),
            "updated_at": download.updated_at.isoformat(),
            "error": download.error,
            "priority": queue.priority if queue else 0,
            "queue_state": queue.state if queue else None,
            "retry_count": queue.retry_count if queue else 0,
        }


def get_download_service(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)],
) -> DownloadService:
    return DownloadService(db, get_download_manager(), user_id=user.id if user else None)
