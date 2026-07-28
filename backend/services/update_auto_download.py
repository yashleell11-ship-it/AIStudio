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

    # Queue AS the follower. The tracker row is the only place the follower's
    # identity survives into the scheduler, which has no request context -- and
    # without it every Download this creates is (NULL, NULL), so the worker
    # files the resulting library membership in the unowned bucket and the whole
    # point of following a series (its chapters arriving in YOUR library)
    # silently never happens.
    #
    # Side effect, and the correct one: the 18+ enqueue gate now resolves
    # against the follower's own profile rather than the global fallback, so
    # auto-download honours the same gate the manual enqueue does.
    service = DownloadService(
        db,
        get_download_manager(),
        user_id=tracker.user_id,
        profile_id=tracker.profile_id,
    )
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
