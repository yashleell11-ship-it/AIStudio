from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from database.models import Bookmark, Chapter, Page, ReadingProgress, Series
from utils.scanner import ScanResult, _extract_chapter_number


def normalize_folder_path(path: str) -> str:
    return str(Path(path).resolve())


def is_child_path(child: str, parent: str) -> bool:
    child_path = Path(child).resolve()
    parent_path = Path(parent).resolve()
    if child_path == parent_path:
        return False
    try:
        child_path.relative_to(parent_path)
        return True
    except ValueError:
        return False


def is_direct_child_path(child: str, parent: str) -> bool:
    child_path = Path(child).resolve()
    parent_path = Path(parent).resolve()
    if child_path == parent_path:
        return False
    try:
        relative = child_path.relative_to(parent_path)
    except ValueError:
        return False
    return len(relative.parts) == 1


def find_closest_parent_series(candidate: Series, all_series: list[Series]) -> Series | None:
    candidate_path = normalize_folder_path(candidate.folder_path)
    best_parent: Series | None = None
    best_parent_depth = -1

    for potential_parent in all_series:
        if potential_parent.id == candidate.id:
            continue
        parent_path = normalize_folder_path(potential_parent.folder_path)
        if not is_direct_child_path(candidate_path, parent_path):
            continue
        depth = len(Path(parent_path).parts)
        if depth > best_parent_depth:
            best_parent = potential_parent
            best_parent_depth = depth

    return best_parent


def find_parent_series_path(series_path: str, scanned_paths: set[str]) -> str | None:
    resolved = normalize_folder_path(series_path)
    candidates = [
        scanned
        for scanned in scanned_paths
        if is_child_path(resolved, scanned)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: len(Path(path).parts))


class ImportCleanupService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def cleanup_after_import(self, library_id: int, scan: ScanResult) -> int:
        removed = self.merge_all_orphans_global()
        scanned_paths = {normalize_folder_path(series.folder_path) for series in scan.series}
        removed += self._remove_stale_series(library_id, scanned_paths)
        return removed

    def merge_all_orphans_global(self) -> int:
        """Merge any series whose folder is a direct child of another series folder."""
        all_series = self._db.query(Series).order_by(Series.id.asc()).all()
        removed = 0

        for candidate in list(all_series):
            if candidate not in self._db:
                continue
            parent = find_closest_parent_series(candidate, all_series)
            if parent is None:
                continue
            if parent.id == candidate.id:
                continue

            self._ensure_parent_chapter(candidate, parent)
            self._migrate_orphan_records(candidate, parent)
            self._delete_series_tree(candidate)
            removed += 1
            all_series = [series for series in all_series if series.id != candidate.id]

        return removed

    def _remove_orphan_series(self, library_id: int, scanned_paths: set[str]) -> int:
        return self.merge_all_orphans_global()

    def _remove_stale_series(self, library_id: int, scanned_paths: set[str]) -> int:
        removed = 0
        all_series = (
            self._db.query(Series).filter(Series.library_id == library_id).all()
        )

        for series in all_series:
            series_path = normalize_folder_path(series.folder_path)
            if series_path in scanned_paths:
                continue
            if any(is_child_path(series_path, scanned) for scanned in scanned_paths):
                continue
            self._delete_series_tree(series)
            removed += 1

        return removed

    def _find_parent_chapter(self, parent: Series, orphan_path: str) -> Chapter | None:
        resolved = normalize_folder_path(orphan_path)
        chapters = (
            self._db.query(Chapter)
            .filter(Chapter.series_id == parent.id)
            .all()
        )
        for chapter in chapters:
            if chapter.folder_path and normalize_folder_path(chapter.folder_path) == resolved:
                return chapter
        return None

    def _ensure_parent_chapter(self, orphan: Series, parent: Series) -> Chapter | None:
        orphan_path = normalize_folder_path(orphan.folder_path)
        existing = self._find_parent_chapter(parent, orphan_path)
        if existing:
            return existing

        orphan_chapters = (
            self._db.query(Chapter)
            .filter(Chapter.series_id == orphan.id)
            .order_by(Chapter.number.asc().nullslast(), Chapter.id.asc())
            .all()
        )
        source = orphan_chapters[0] if orphan_chapters else None
        chapter_title = orphan.title
        chapter_number = _extract_chapter_number(orphan.title)
        if source and source.title and source.title != "Chapter 1":
            chapter_title = source.title
            chapter_number = source.number

        chapter = Chapter(
            series_id=parent.id,
            title=chapter_title,
            number=chapter_number,
            folder_path=orphan_path,
            archive_path=source.archive_path if source else None,
            page_count=source.page_count if source else 0,
        )
        self._db.add(chapter)
        self._db.flush()

        if source:
            pages = (
                self._db.query(Page)
                .filter(Page.chapter_id == source.id)
                .order_by(Page.number.asc())
                .all()
            )
            for page in pages:
                self._db.add(
                    Page(
                        chapter_id=chapter.id,
                        number=page.number,
                        file_path=page.file_path,
                    )
                )
            chapter.page_count = len(pages)

        if not parent.cover_path and chapter.page_count > 0:
            first_page = (
                self._db.query(Page)
                .filter(Page.chapter_id == chapter.id)
                .order_by(Page.number.asc())
                .first()
            )
            if first_page:
                parent.cover_path = first_page.file_path

        self._db.flush()
        return chapter

    def _migrate_orphan_records(self, orphan: Series, parent: Series) -> None:
        orphan_path = normalize_folder_path(orphan.folder_path)
        target_chapter = self._find_parent_chapter(parent, orphan_path)

        orphan_progress = (
            self._db.query(ReadingProgress)
            .filter(ReadingProgress.series_id == orphan.id)
            .first()
        )
        if orphan_progress and target_chapter is not None:
            parent_progress = (
                self._db.query(ReadingProgress)
                .filter(ReadingProgress.series_id == parent.id)
                .first()
            )
            if parent_progress is None:
                parent_progress = ReadingProgress(
                    series_id=parent.id,
                    chapter_id=target_chapter.id,
                    last_page=orphan_progress.last_page,
                    progress_pct=orphan_progress.progress_pct,
                    started_at=orphan_progress.started_at,
                    last_read_at=orphan_progress.last_read_at,
                )
                self._db.add(parent_progress)
            elif orphan_progress.last_read_at >= parent_progress.last_read_at:
                parent_progress.chapter_id = target_chapter.id
                parent_progress.last_page = orphan_progress.last_page
                parent_progress.progress_pct = orphan_progress.progress_pct
                parent_progress.last_read_at = orphan_progress.last_read_at

        for bookmark in (
            self._db.query(Bookmark).filter(Bookmark.series_id == orphan.id).all()
        ):
            if target_chapter is None:
                continue
            bookmark.series_id = parent.id
            bookmark.chapter_id = target_chapter.id

        self._db.flush()

    def _delete_series_tree(self, series: Series) -> None:
        chapter_ids = [
            chapter_id
            for (chapter_id,) in self._db.query(Chapter.id)
            .filter(Chapter.series_id == series.id)
            .all()
        ]
        if chapter_ids:
            self._db.query(Page).filter(Page.chapter_id.in_(chapter_ids)).delete(
                synchronize_session=False
            )
        self._db.query(Bookmark).filter(Bookmark.series_id == series.id).delete(
            synchronize_session=False
        )
        self._db.query(ReadingProgress).filter(
            ReadingProgress.series_id == series.id
        ).delete(synchronize_session=False)
        self._db.query(Chapter).filter(Chapter.series_id == series.id).delete(
            synchronize_session=False
        )
        self._db.delete(series)
        self._db.flush()
