from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Annotated

from fastapi import Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from core.config import get_settings
from core.errors import AppError
from database.models import (
    Bookmark,
    Chapter,
    ChapterText,
    Collection,
    CollectionSeries,
    ImportHistory,
    Library,
    OcrJob,
    Page,
    PageText,
    ReadingProgress,
    Series,
    SeriesTag,
    Tag,
)
from database.session import get_db
from services.import_cleanup import ImportCleanupService, normalize_folder_path
from services.source_service import SourceService
from utils.mobile_urls import page_image_url, series_cover_url
from utils.path_utils import natural_sort_key, validate_absolute_path
from connectors.local_filesystem.scanner import ScanResult
from database.models import ChapterProgress


def _chapter_sort_key(chapter: Chapter) -> tuple[float, list[int | str]]:
    number = chapter.number if chapter.number is not None else float("inf")
    return (number, natural_sort_key(chapter.title))


class ScanStatus:
    def __init__(self) -> None:
        self._lock = Lock()
        self.running = False
        self.progress_pct = 0.0
        self.message = "Idle"
        self.series_count = 0
        self.chapter_count = 0
        self.page_count = 0
        self.error: str | None = None

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "running": self.running,
                "progress_pct": self.progress_pct,
                "message": self.message,
                "series_count": self.series_count,
                "chapter_count": self.chapter_count,
                "page_count": self.page_count,
                "error": self.error,
            }

    def start(self, message: str) -> None:
        with self._lock:
            self.running = True
            self.progress_pct = 0.0
            self.message = message
            self.series_count = 0
            self.chapter_count = 0
            self.page_count = 0
            self.error = None

    def update(
        self,
        *,
        progress_pct: float | None = None,
        message: str | None = None,
        series_count: int | None = None,
        chapter_count: int | None = None,
        page_count: int | None = None,
    ) -> None:
        with self._lock:
            if progress_pct is not None:
                self.progress_pct = progress_pct
            if message is not None:
                self.message = message
            if series_count is not None:
                self.series_count = series_count
            if chapter_count is not None:
                self.chapter_count = chapter_count
            if page_count is not None:
                self.page_count = page_count

    def finish(self, scan: ScanResult) -> None:
        with self._lock:
            self.running = False
            self.progress_pct = 100.0
            self.message = "Scan complete"
            self.series_count = scan.series_count
            self.chapter_count = scan.chapter_count
            self.page_count = scan.page_count

    def fail(self, message: str) -> None:
        with self._lock:
            self.running = False
            self.error = message
            self.message = message


_scan_status = ScanStatus()


class LibraryService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._settings = get_settings()

    def get_scan_status(self) -> dict[str, object]:
        return _scan_status.snapshot()

    def get_library_roots(self) -> list[Path]:
        libraries = self._db.query(Library).all()
        return [Path(library.root_path).resolve() for library in libraries]

    def _get_or_create_library(self, folder_path: Path) -> Library:
        resolved = str(folder_path.resolve())
        library = self._db.query(Library).filter(Library.root_path == resolved).first()
        if library:
            return library
        library = Library(
            name=folder_path.name or "Imported Library",
            root_path=resolved,
        )
        self._db.add(library)
        self._db.flush()
        return library

    def _compute_sort_title(self, title: str) -> str:
        """Normalize title for stable sorting: strip leading articles, lowercase."""
        t = title.strip().lower()
        for prefix in ("the ", "a ", "an "):
            if t.startswith(prefix):
                return t[len(prefix):]
        return t

    def _compute_sort_key(self, number: float | None) -> str:
        """Zero-padded string for stable lexicographic sort.

        Supports decimal chapter numbers (13.5, 120.1) without truncation.
        """
        if number is None:
            return "9999.999"
        return f"{number:08.3f}"

    def import_folder(self, folder_path: str) -> dict[str, object]:
        if _scan_status.running:
            raise AppError(
                "A library scan is already in progress.",
                code="scan_in_progress",
                status_code=409,
            )

        path = validate_absolute_path(folder_path)
        if not path.is_dir():
            raise AppError(
                "Folder does not exist or is not a directory.",
                code="invalid_folder",
                status_code=400,
                details={"folder_path": folder_path},
            )

        _scan_status.start(f"Scanning {path.name}")
        history = ImportHistory(
            folder_path=str(path.resolve()),
            status="running",
            started_at=datetime.utcnow(),
        )
        self._db.add(history)
        self._db.commit()

        try:
            scan = SourceService().discover_folder(str(path.resolve()))
            library = self._get_or_create_library(path)
            self._persist_scan(library, scan)
            removed_orphans = ImportCleanupService(self._db).cleanup_after_import(
                library.id, scan
            )
            history.library_id = library.id
            history.status = "completed"
            history.series_count = scan.series_count
            history.chapter_count = scan.chapter_count
            history.page_count = scan.page_count
            history.finished_at = datetime.utcnow()
            self._db.commit()
            _scan_status.finish(scan)
            return {
                "status": "completed",
                "library_id": library.id,
                "series_count": scan.series_count,
                "chapter_count": scan.chapter_count,
                "page_count": scan.page_count,
                "removed_orphans": removed_orphans,
            }
        except Exception as exc:
            self._db.rollback()
            history.status = "failed"
            history.finished_at = datetime.utcnow()
            self._db.add(history)
            self._db.commit()
            _scan_status.fail(str(exc))
            raise AppError(
                "Library import failed.",
                code="import_failed",
                status_code=500,
                details={"reason": str(exc)},
            ) from exc

    def index_downloads_root(self, folder_path: str) -> None:
        """Index downloaded chapters without blocking the public scan status UI."""
        path = validate_absolute_path(folder_path)
        if not path.is_dir():
            raise AppError(
                "Folder does not exist or is not a directory.",
                code="invalid_folder",
                status_code=400,
                details={"folder_path": folder_path},
            )

        scan = SourceService().discover_folder(str(path.resolve()))
        library = self._get_or_create_library(path)
        self._persist_scan(library, scan)
        ImportCleanupService(self._db).cleanup_after_import(library.id, scan)
        self._db.flush()

    def _persist_scan(self, library: Library, scan: ScanResult) -> None:
        total = max(scan.series_count, 1)

        for index, scanned_series in enumerate(scan.series, start=1):
            series_path = normalize_folder_path(scanned_series.folder_path)
            series = (
                self._db.query(Series)
                .filter(Series.folder_path == series_path)
                .first()
            )
            if not series:
                series = Series(
                    library_id=library.id,
                    title=scanned_series.title,
                    sort_title=self._compute_sort_title(scanned_series.title),
                    folder_path=series_path,
                )
                self._db.add(series)
                self._db.flush()
            else:
                series.library_id = library.id
                series.title = scanned_series.title
                series.sort_title = self._compute_sort_title(scanned_series.title)
                series.updated_at = datetime.utcnow()

            progress = (
                self._db.query(ReadingProgress)
                .filter(ReadingProgress.series_id == series.id)
                .first()
            )

            existing_chapters = {
                normalize_folder_path(chapter.folder_path)
                if chapter.folder_path
                else (chapter.archive_path or ""): chapter
                for chapter in self._db.query(Chapter)
                .filter(Chapter.series_id == series.id)
                .all()
            }
            seen_keys: set[str] = set()
            total_chapters = 0
            total_pages = 0

            for chapter_data in scanned_series.chapters:
                key = chapter_data.folder_path or chapter_data.archive_path or ""
                if chapter_data.folder_path:
                    key = normalize_folder_path(chapter_data.folder_path)
                seen_keys.add(key)
                chapter = existing_chapters.get(key)
                if not chapter:
                    chapter = Chapter(
                        series_id=series.id,
                        title=chapter_data.title,
                        number=chapter_data.number,
                        sort_key=self._compute_sort_key(chapter_data.number),
                        folder_path=normalize_folder_path(chapter_data.folder_path)
                        if chapter_data.folder_path
                        else None,
                        archive_path=chapter_data.archive_path,
                    )
                    self._db.add(chapter)
                    self._db.flush()
                else:
                    chapter.title = chapter_data.title
                    chapter.number = chapter_data.number
                    chapter.sort_key = self._compute_sort_key(chapter_data.number)
                    chapter.scanned_at = datetime.utcnow()
                    self._clear_chapter_page_data(chapter.id)

                chapter.page_count = len(chapter_data.pages)
                chapter.scanned_at = datetime.utcnow()
                if chapter_data.pages and not series.cover_path:
                    series.cover_path = chapter_data.pages[0].file_path

                for page_data in chapter_data.pages:
                    page = Page(
                        chapter_id=chapter.id,
                        number=page_data.number,
                        file_path=page_data.file_path,
                    )
                    self._db.add(page)

                total_chapters += 1
                total_pages += chapter.page_count

            for key, chapter in existing_chapters.items():
                if key not in seen_keys:
                    if progress and progress.chapter_id == chapter.id:
                        replacement = (
                            self._db.query(Chapter)
                            .filter(
                                Chapter.series_id == series.id,
                                Chapter.id != chapter.id,
                            )
                            .order_by(Chapter.number.asc().nullslast(), Chapter.id.asc())
                            .first()
                        )
                        if replacement:
                            progress.chapter_id = replacement.id
                            progress.last_page = min(
                                progress.last_page,
                                replacement.page_count or progress.last_page,
                            )
                        else:
                            self._db.delete(progress)
                            progress = None
                    self._db.delete(chapter)

            series.total_chapters = total_chapters
            series.total_pages = total_pages
            # Recalculate read_chapters from chapter_progress
            series.read_chapters = (
                self._db.query(ChapterProgress)
                .join(Chapter)
                .filter(Chapter.series_id == series.id, ChapterProgress.is_completed == True)
                .count()
            )

            _scan_status.update(
                progress_pct=(index / total) * 100,
                message=f"Imported {scanned_series.title}",
                series_count=index,
                chapter_count=scan.chapter_count,
                page_count=scan.page_count,
            )

        self._db.flush()

    def list_series(
        self,
        *,
        page: int = 1,
        per_page: int = 40,
        sort: str = "title",
        search: str | None = None,
        status: str | None = None,
        reading_status: str | None = None,
        collection_id: int | None = None,
        tag_id: int | None = None,
        library_id: int | None = None,
        is_favorite: bool | None = None,
        language: str | None = None,
    ) -> dict[str, object]:
        query = self._db.query(Series).filter(Series.deleted_at.is_(None))

        if library_id is not None:
            query = query.filter(Series.library_id == library_id)

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(Series.title.ilike(term), Series.author.ilike(term))
            )

        if status == "reading":
            query = query.join(ReadingProgress)
        elif status == "unread":
            query = query.outerjoin(ReadingProgress).filter(ReadingProgress.id.is_(None))

        if reading_status is not None:
            query = query.filter(Series.reading_status == reading_status)

        if collection_id is not None:
            query = query.join(CollectionSeries).filter(
                CollectionSeries.collection_id == collection_id
            )

        if tag_id is not None:
            query = query.join(SeriesTag).filter(SeriesTag.tag_id == tag_id)

        if is_favorite is not None:
            query = query.filter(Series.is_favorite == is_favorite)

        if language is not None:
            query = query.filter(Series.language == language)

        if sort == "updated":
            query = query.order_by(Series.updated_at.desc())
        elif sort == "recent":
            query = query.outerjoin(ReadingProgress).order_by(
                ReadingProgress.last_read_at.desc().nullslast()
            ).distinct()
        elif sort == "date_added":
            query = query.order_by(Series.created_at.desc())
        elif sort == "author":
            query = query.order_by(Series.author.asc().nullslast())
        elif sort == "year":
            query = query.order_by(Series.year.desc().nullslast())
        elif sort == "total_chapters":
            query = query.order_by(Series.total_chapters.desc())
        else:
            query = query.order_by(Series.sort_title.asc())

        total = query.count()
        offset = max(page - 1, 0) * per_page
        series_list = (
            query.options(
                joinedload(Series.chapters),
                joinedload(Series.reading_progress),
            )
            .offset(offset)
            .limit(per_page)
            .all()
        )

        all_chapter_ids = [chapter.id for series in series_list for chapter in series.chapters]
        ocr_map = self._get_ocr_status_for_chapters(all_chapter_ids)
        items = [
            self._series_summary(series, ocr_map=ocr_map)
            for series in series_list
        ]
        from utils.api_pagination import enrich_pagination_aliases

        return enrich_pagination_aliases(
            {
                "items": items,
                "total": total,
                "page": page,
                "per_page": per_page,
                "has_next": offset + per_page < total,
            }
        )

    def _series_summary(
        self,
        series: Series,
        *,
        ocr_map: dict[int, dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        chapter_count = len(series.chapters)
        page_count = sum(chapter.page_count for chapter in series.chapters)
        progress = series.reading_progress
        first_chapter_id = None
        if series.chapters:
            sorted_chapters = sorted(series.chapters, key=_chapter_sort_key)
            first_chapter_id = sorted_chapters[0].id

        chapter_ids = [c.id for c in series.chapters]
        if ocr_map is None:
            chapter_ocr_map = self._get_ocr_status_for_chapters(chapter_ids)
        else:
            chapter_ocr_map = {cid: ocr_map[cid] for cid in chapter_ids if cid in ocr_map}
        ocr_summary = self._summarize_ocr_status(chapter_count, chapter_ocr_map)

        return {
            "id": series.id,
            "library_id": series.library_id,
            "title": series.title,
            "sort_title": series.sort_title,
            "original_title": series.original_title,
            "author": series.author,
            "artist": series.artist,
            "description": series.description,
            "status": series.status,
            "content_rating": series.content_rating,
            "language": series.language,
            "year": series.year,
            "cover_path": series.cover_path,
            "cover_url": series_cover_url(series.id),
            "folder_path": series.folder_path,
            "is_favorite": bool(series.is_favorite),
            "reading_status": series.reading_status,
            "chapter_count": chapter_count,
            "read_chapters": series.read_chapters,
            "page_count": page_count,
            "total_chapters": series.total_chapters,
            "total_pages": series.total_pages,
            "first_chapter_id": first_chapter_id,
            "created_at": series.created_at.isoformat(),
            "updated_at": series.updated_at.isoformat(),
            "reading_progress": self._progress_dict(progress) if progress else None,
            "ocr_summary": ocr_summary,
        }

    def get_series(self, series_id: int) -> dict[str, object]:
        series = (
            self._db.query(Series)
            .options(joinedload(Series.chapters).joinedload(Chapter.pages))
            .filter(Series.id == series_id)
            .first()
        )
        if not series:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )
        chapters = sorted(series.chapters, key=_chapter_sort_key)
        chapter_ids = [c.id for c in chapters]
        ocr_map = self._get_ocr_status_for_chapters(chapter_ids)
        return {
            **self._series_summary(series),
            "chapters": [
                {
                    "id": chapter.id,
                    "series_id": chapter.series_id,
                    "title": chapter.title,
                    "number": chapter.number,
                    "page_count": chapter.page_count,
                    "folder_path": chapter.folder_path,
                    "archive_path": chapter.archive_path,
                    "ocr_status": ocr_map.get(chapter.id, {"status": "not_started"}),
                }
                for chapter in chapters
            ],
        }

    def get_chapter(self, chapter_id: int) -> dict[str, object]:
        chapter = (
            self._db.query(Chapter)
            .options(joinedload(Chapter.pages))
            .filter(Chapter.id == chapter_id)
            .first()
        )
        if not chapter:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
                details={"chapter_id": chapter_id},
            )
        pages = sorted(chapter.pages, key=lambda page: page.number)
        ocr_map = self._get_ocr_status_for_chapters([chapter.id])
        return {
            "id": chapter.id,
            "series_id": chapter.series_id,
            "title": chapter.title,
            "number": chapter.number,
            "page_count": chapter.page_count,
            "ocr_status": ocr_map.get(chapter.id, {"status": "not_started"}),
            "pages": [
                {
                    "id": page.id,
                    "chapter_id": page.chapter_id,
                    "number": page.number,
                    "file_path": page.file_path,
                    "image_url": page_image_url(page.id),
                    "width": page.width,
                    "height": page.height,
                }
                for page in pages
            ],
        }

    def get_page(self, page_id: int) -> Page:
        page = (
            self._db.query(Page)
            .options(joinedload(Page.chapter))
            .filter(Page.id == page_id)
            .first()
        )
        if not page:
            raise AppError(
                "Page not found.",
                code="page_not_found",
                status_code=404,
                details={"page_id": page_id},
            )
        return page

    def get_continue_reading(self, limit: int = 10) -> list[dict[str, object]]:
        rows = (
            self._db.query(ReadingProgress)
            .options(
                joinedload(ReadingProgress.series),
                joinedload(ReadingProgress.chapter),
            )
            .order_by(ReadingProgress.last_read_at.desc())
            .limit(limit)
            .all()
        )
        results: list[dict[str, object]] = []
        for row in rows:
            if row.series is None or row.chapter is None:
                continue
            results.append(
                {
                    "series_id": row.series_id,
                    "series_title": row.series.title,
                    "chapter_id": row.chapter_id,
                    "chapter_title": row.chapter.title,
                    "last_page": row.last_page,
                    "scroll_offset_px": row.scroll_offset_px,
                    "progress_pct": row.progress_pct,
                    "last_read_at": row.last_read_at.isoformat(),
                    "cover_path": row.series.cover_path,
                    "cover_url": series_cover_url(row.series_id),
                }
            )
        return results

    def list_libraries(self) -> list[dict[str, object]]:
        libraries = self._db.query(Library).order_by(Library.name.asc()).all()
        counts = dict(
            self._db.query(Series.library_id, func.count())
            .filter(Series.deleted_at.is_(None))
            .group_by(Series.library_id)
            .all()
        )
        return [
            {
                "id": library.id,
                "name": library.name,
                "root_path": library.root_path,
                "series_count": int(counts.get(library.id, 0)),
                "created_at": library.created_at.isoformat(),
            }
            for library in libraries
        ]

    def _clear_chapter_page_data(self, chapter_id: int) -> None:
        """Remove page rows and dependent OCR text before a chapter rescan."""
        page_ids = [
            row[0]
            for row in self._db.query(Page.id).filter(Page.chapter_id == chapter_id).all()
        ]
        if page_ids:
            self._db.query(PageText).filter(PageText.page_id.in_(page_ids)).delete(
                synchronize_session=False
            )
        self._db.query(ChapterText).filter(ChapterText.chapter_id == chapter_id).delete(
            synchronize_session=False
        )
        self._db.query(Page).filter(Page.chapter_id == chapter_id).delete(
            synchronize_session=False
        )

    def _summarize_ocr_status(
        self,
        chapter_count: int,
        ocr_map: dict[int, dict[str, Any]],
    ) -> dict[str, int]:
        completed = sum(1 for v in ocr_map.values() if v.get("status") == "completed")
        processing = sum(
            1 for v in ocr_map.values() if v.get("status") in ("queued", "processing")
        )
        failed = sum(1 for v in ocr_map.values() if v.get("status") == "failed")
        return {
            "completed": completed,
            "processing": processing,
            "failed": failed,
            "not_started": chapter_count - completed - processing - failed,
            "total": chapter_count,
        }

    def _get_ocr_status_for_chapters(
        self, chapter_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        """Batch-query OCR status for a list of chapter IDs.
        Returns a map of chapter_id -> status dict.
        """
        if not chapter_ids:
            return {}

        # Completed text
        texts = (
            self._db.query(ChapterText)
            .filter(ChapterText.chapter_id.in_(chapter_ids))
            .all()
        )
        text_by_chapter = {t.chapter_id: t for t in texts}

        # Active jobs
        jobs = (
            self._db.query(OcrJob)
            .filter(OcrJob.chapter_id.in_(chapter_ids))
            .filter(OcrJob.status.in_(("queued", "processing", "failed")))
            .all()
        )
        job_by_chapter = {}
        for job in jobs:
            job_by_chapter[job.chapter_id] = job

        result: dict[int, dict[str, Any]] = {}
        for cid in chapter_ids:
            if cid in text_by_chapter:
                result[cid] = {
                    "status": "completed",
                    "word_count": text_by_chapter[cid].word_count,
                    "engine": text_by_chapter[cid].engine,
                }
            elif cid in job_by_chapter:
                job = job_by_chapter[cid]
                result[cid] = {
                    "status": job.status,
                    "progress": job.progress,
                    "engine": job.engine,
                }
            else:
                result[cid] = {"status": "not_started"}
        return result

    def _progress_dict(self, progress: ReadingProgress) -> dict[str, object]:
        return {
            "series_id": progress.series_id,
            "chapter_id": progress.chapter_id,
            "last_page": progress.last_page,
            "scroll_offset_px": progress.scroll_offset_px,
            "progress_pct": progress.progress_pct,
            "last_read_at": progress.last_read_at.isoformat(),
        }


def get_library_service(
    db: Annotated[Session, Depends(get_db)],
) -> LibraryService:
    return LibraryService(db)
