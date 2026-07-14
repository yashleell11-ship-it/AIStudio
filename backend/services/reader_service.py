from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, joinedload, selectinload

from core.errors import AppError
from core.time_utils import utcnow
from core.profile_context import ProfileContext, resolve_profile_context
from database.models import Bookmark, Chapter, Page, ReadingProgress, Series, User
from database.session import get_db
from utils.path_utils import natural_sort_key


def _chapter_sort_key(chapter: Chapter) -> tuple[float, list[int | str]]:
    number = chapter.number if chapter.number is not None else float("inf")
    return (number, natural_sort_key(chapter.title))


class ReaderService:
    def __init__(
        self,
        db: Session,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        # Reading progress and bookmarks are per-(user, profile); None/None
        # scopes to the anonymous/legacy (unclaimed, unscoped) rows.
        self._user_id = user_id
        self._profile_id = profile_id

    def save_progress(
        self,
        *,
        series_id: int,
        chapter_id: int,
        last_page: int,
        scroll_offset_px: int | None = None,
    ) -> dict[str, object]:
        series = self._db.query(Series).filter(Series.id == series_id).first()
        if not series:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )

        chapter = (
            self._db.query(Chapter)
            .options(joinedload(Chapter.pages))
            .filter(Chapter.id == chapter_id, Chapter.series_id == series_id)
            .first()
        )
        if not chapter:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
                details={"chapter_id": chapter_id},
            )

        page_count = chapter.page_count or len(chapter.pages)
        if page_count <= 0:
            progress_pct = 0.0
        else:
            progress_pct = min(100.0, (last_page / page_count) * 100.0)

        progress = (
            self._db.query(ReadingProgress)
            .filter(
                ReadingProgress.series_id == series_id,
                ReadingProgress.user_id == self._user_id,
                ReadingProgress.profile_id == self._profile_id,
            )
            .first()
        )
        if not progress:
            progress = ReadingProgress(
                user_id=self._user_id,
                profile_id=self._profile_id,
                series_id=series_id,
                chapter_id=chapter_id,
                last_page=last_page,
                progress_pct=progress_pct,
                scroll_offset_px=scroll_offset_px if scroll_offset_px is not None else 0,
            )
            self._db.add(progress)
        else:
            progress.chapter_id = chapter_id
            progress.last_page = last_page
            progress.progress_pct = progress_pct
            progress.last_read_at = utcnow()
            if scroll_offset_px is not None:
                progress.scroll_offset_px = scroll_offset_px

        self._db.commit()
        self._db.refresh(progress)
        return {
            "series_id": progress.series_id,
            "chapter_id": progress.chapter_id,
            "last_page": progress.last_page,
            "scroll_offset_px": progress.scroll_offset_px,
            "progress_pct": progress.progress_pct,
            "last_read_at": progress.last_read_at.isoformat(),
        }

    def get_progress(self, series_id: int) -> dict[str, object] | None:
        progress = (
            self._db.query(ReadingProgress)
            .filter(
                ReadingProgress.series_id == series_id,
                ReadingProgress.user_id == self._user_id,
                ReadingProgress.profile_id == self._profile_id,
            )
            .first()
        )
        if not progress:
            return None
        return {
            "series_id": progress.series_id,
            "chapter_id": progress.chapter_id,
            "last_page": progress.last_page,
            "scroll_offset_px": progress.scroll_offset_px,
            "progress_pct": progress.progress_pct,
            "last_read_at": progress.last_read_at.isoformat(),
        }

    def delete_progress(self, series_id: int) -> None:
        progress = (
            self._db.query(ReadingProgress)
            .filter(
                ReadingProgress.series_id == series_id,
                ReadingProgress.user_id == self._user_id,
                ReadingProgress.profile_id == self._profile_id,
            )
            .first()
        )
        if not progress:
            raise AppError(
                "Reading progress not found.",
                code="progress_not_found",
                status_code=404,
                details={"series_id": series_id},
            )
        self._db.delete(progress)
        self._db.commit()

    def add_bookmark(
        self,
        *,
        series_id: int,
        chapter_id: int,
        page: int,
        note: str | None = None,
    ) -> dict[str, object]:
        chapter = (
            self._db.query(Chapter)
            .filter(Chapter.id == chapter_id, Chapter.series_id == series_id)
            .first()
        )
        if not chapter:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
            )

        page_row = (
            self._db.query(Page)
            .filter(Page.chapter_id == chapter_id, Page.number == page)
            .first()
        )

        bookmark = Bookmark(
            user_id=self._user_id,
            profile_id=self._profile_id,
            series_id=series_id,
            chapter_id=chapter_id,
            page=page,
            page_id=page_row.id if page_row is not None else None,
            note=note,
        )
        self._db.add(bookmark)
        self._db.commit()
        self._db.refresh(bookmark)
        return {
            "id": bookmark.id,
            "series_id": bookmark.series_id,
            "chapter_id": bookmark.chapter_id,
            "page": bookmark.page,
            "page_id": bookmark.page_id,
            "note": bookmark.note,
            "created_at": bookmark.created_at.isoformat(),
        }

    def list_all_bookmarks(self, limit: int = 200) -> list[dict[str, object]]:
        """Return the most recent bookmarks across every series, with series
        and chapter names attached so the Bookmark Manager can render a
        useful list without a lookup per row."""
        bookmarks = (
            self._db.query(Bookmark)
            .filter(
                Bookmark.user_id == self._user_id,
                Bookmark.profile_id == self._profile_id,
            )
            .options(
                selectinload(Bookmark.series),
                selectinload(Bookmark.chapter),
            )
            .order_by(Bookmark.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": bookmark.id,
                "series_id": bookmark.series_id,
                "series_title": bookmark.series.title if bookmark.series else None,
                "chapter_id": bookmark.chapter_id,
                "chapter_title": bookmark.chapter.title if bookmark.chapter else None,
                "page": bookmark.page,
                "page_id": bookmark.page_id,
                "note": bookmark.note,
                "created_at": bookmark.created_at.isoformat(),
            }
            for bookmark in bookmarks
        ]

    def list_bookmarks(self, series_id: int) -> list[dict[str, object]]:
        bookmarks = (
            self._db.query(Bookmark)
            .filter(
                Bookmark.series_id == series_id,
                Bookmark.user_id == self._user_id,
                Bookmark.profile_id == self._profile_id,
            )
            .order_by(Bookmark.created_at.desc())
            .all()
        )
        return [
            {
                "id": bookmark.id,
                "series_id": bookmark.series_id,
                "chapter_id": bookmark.chapter_id,
                "page": bookmark.page,
                "page_id": bookmark.page_id,
                "note": bookmark.note,
                "created_at": bookmark.created_at.isoformat(),
            }
            for bookmark in bookmarks
        ]

    def delete_bookmark(self, bookmark_id: int) -> None:
        bookmark = (
            self._db.query(Bookmark)
            .filter(
                Bookmark.id == bookmark_id,
                Bookmark.user_id == self._user_id,
                Bookmark.profile_id == self._profile_id,
            )
            .first()
        )
        if not bookmark:
            raise AppError(
                "Bookmark not found.",
                code="bookmark_not_found",
                status_code=404,
                details={"bookmark_id": bookmark_id},
            )
        self._db.delete(bookmark)
        self._db.commit()

    def get_adjacent_chapter(
        self,
        chapter_id: int,
        direction: str,
    ) -> dict[str, object] | None:
        chapter = self._db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
            )
        chapters = sorted(
            self._db.query(Chapter)
            .filter(Chapter.series_id == chapter.series_id)
            .all(),
            key=_chapter_sort_key,
        )
        ids = [item.id for item in chapters]
        try:
            index = ids.index(chapter_id)
        except ValueError:
            return None
        target_index = index - 1 if direction == "previous" else index + 1
        if target_index < 0 or target_index >= len(chapters):
            return None
        target = chapters[target_index]
        return {
            "id": target.id,
            "series_id": target.series_id,
            "title": target.title,
            "number": target.number,
        }


def get_reader_service(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> ReaderService:
    return ReaderService(db, user_id=ctx.user_id, profile_id=ctx.profile_id)
