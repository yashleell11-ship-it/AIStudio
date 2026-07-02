"""Queue downloads when update checks detect new chapters."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from connectors.models import Chapter as ConnectorChapter
from database.models import SeriesTracker
from services.download_manager import get_download_manager
from services.download_service import DownloadService

logger = logging.getLogger(__name__)


def auto_download_new_chapters(
    db: Session,
    tracker: SeriesTracker,
    chapters: list[ConnectorChapter],
) -> None:
    """Queue newly detected chapters using the existing download pipeline."""
    if not chapters:
        return

    service = DownloadService(db, get_download_manager())
    chapter_ids = [chapter.id for chapter in chapters]
    chapter_titles = {chapter.id: chapter.title for chapter in chapters}

    try:
        result = service.queue_chapters(
            source_id=tracker.source,
            series_id=tracker.series_id,
            chapter_ids=chapter_ids,
            series_title=tracker.series_title,
            chapter_titles=chapter_titles,
            series_queue=True,
        )
        logger.info(
            "Auto-download for %s/%s: queued=%d skipped=%d",
            tracker.source,
            tracker.series_id,
            len(result.get("queued", [])),
            len(result.get("skipped", [])),
        )
    except Exception:
        logger.exception(
            "Auto-download failed for %s/%s",
            tracker.source,
            tracker.series_id,
        )
