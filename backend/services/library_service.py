from __future__ import annotations

from core.time_utils import utcnow
from pathlib import Path
from threading import Lock
from typing import Annotated

from fastapi import Depends
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from core.config import get_settings
from core.content_rating import mature_rating_predicate, resolve_mature_gate
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
    SeriesTracker,
    SourceChapterLink,
    Tag,
    User,
    UserSeriesState,
)
from database.session import get_db
from core.profile_context import ProfileContext, resolve_profile_context
from services.import_cleanup import ImportCleanupService, normalize_folder_path
from services.source_service import SourceService
from utils.mobile_urls import page_image_url, series_cover_url
from utils.path_utils import (
    natural_sort_key,
    validate_absolute_path,
    validate_path_under_roots,
)
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
    def __init__(
        self,
        db: Session,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        self._settings = get_settings()
        # Library membership, per-series state and reading progress are all
        # per-(user, profile); None/None scopes to the anonymous/legacy
        # unscoped rows.
        self._user_id = user_id
        self._profile_id = profile_id

    # ------------------------------------------------------------------
    # Per-(user, profile) scoping helpers
    # ------------------------------------------------------------------

    def _library_on(self):
        """Join predicate binding a ``Series`` to *this* (user, profile)'s
        membership row.

        ``in_library`` is the membership bit, not the presence of the row: a
        state row legitimately exists with ``in_library`` false once progress or
        a favourite was recorded from Browse without adding the series. Joining
        without this predicate would hand every account the whole catalog.
        """
        return and_(
            UserSeriesState.series_id == Series.id,
            UserSeriesState.user_id == self._user_id,
            UserSeriesState.profile_id == self._profile_id,
            UserSeriesState.in_library == True,  # noqa: E712 - SQL, not Python
        )

    def _mature_enabled(self) -> bool:
        """The active 18+ gate for this (user, profile)."""
        return resolve_mature_gate(self._db, self._profile_id, self._user_id)

    def _apply_mature_filter(self, query):
        """Hide adult-rated series from a ``Series`` query while 18+ is off.

        Mirrors LibraryIntelligenceService._apply_mature_filter — same rule,
        same helper — because "My Library" and discovery disagreeing about what
        exists is precisely the bug this closes. Purely a visibility filter:
        membership, progress and the rows themselves are untouched, and the
        series reappears the moment the profile turns 18+ back on.
        """
        if self._mature_enabled():
            return query
        return query.filter(~mature_rating_predicate(Series.content_rating))

    def _get_or_create_state(self, series_id: int) -> UserSeriesState:
        state = (
            self._db.query(UserSeriesState)
            .filter(
                UserSeriesState.user_id == self._user_id,
                UserSeriesState.profile_id == self._profile_id,
                UserSeriesState.series_id == series_id,
            )
            .first()
        )
        if state is None:
            state = UserSeriesState(
                user_id=self._user_id,
                profile_id=self._profile_id,
                series_id=series_id,
            )
            self._db.add(state)
            self._db.flush()
        return state

    def _state_map(self, series_ids: list[int]) -> dict[int, UserSeriesState]:
        if not series_ids:
            return {}
        rows = (
            self._db.query(UserSeriesState)
            .filter(
                UserSeriesState.user_id == self._user_id,
                UserSeriesState.profile_id == self._profile_id,
                UserSeriesState.series_id.in_(series_ids),
            )
            .all()
        )
        return {row.series_id: row for row in rows}

    def _progress_map(self, series_ids: list[int]) -> dict[int, ReadingProgress]:
        """Batch-load this (user, profile)'s progress rows.

        Deliberately not ``Series.reading_progress``: that relationship is
        ``uselist=False`` with no owner predicate, so it resolves to an
        arbitrary user's row and used to hand one account another's page number.
        """
        if not series_ids:
            return {}
        rows = (
            self._db.query(ReadingProgress)
            .filter(
                ReadingProgress.user_id == self._user_id,
                ReadingProgress.profile_id == self._profile_id,
                ReadingProgress.series_id.in_(series_ids),
            )
            .all()
        )
        return {row.series_id: row for row in rows}

    def _read_chapter_map(self, series_ids: list[int]) -> dict[int, int]:
        """Per-(user, profile) completed-chapter counts, keyed by series.

        The denormalized ``series.read_chapters`` column counts *every* user's
        completed chapters, so it can never be reported to a single caller.
        """
        if not series_ids:
            return {}
        rows = (
            self._db.query(Chapter.series_id, func.count(ChapterProgress.id))
            .join(ChapterProgress, ChapterProgress.chapter_id == Chapter.id)
            .filter(
                Chapter.series_id.in_(series_ids),
                ChapterProgress.user_id == self._user_id,
                ChapterProgress.profile_id == self._profile_id,
                ChapterProgress.is_completed == True,  # noqa: E712 - SQL, not Python
            )
            .group_by(Chapter.series_id)
            .all()
        )
        return {series_id: count for series_id, count in rows}

    def get_scan_status(self) -> dict[str, object]:
        return _scan_status.snapshot()

    def get_library_roots(self) -> list[Path]:
        libraries = self._db.query(Library).all()
        return [Path(library.root_path).resolve() for library in libraries]

    def _allowed_import_roots(self) -> list[Path]:
        """Directories a folder import is permitted to read from.

        The allowlist is the union of: operator-configured roots
        (``MM_IMPORT_ROOTS`` / settings.import_roots), every already-registered
        library root (so rescans of a known library keep working), and the
        downloads path (imports of downloaded content are always in-scope). Any
        import target that does not resolve under one of these is rejected with
        403 — an admin cannot mount an arbitrary host path such as ``/`` or
        ``/etc``. On a fresh instance with nothing configured, only the downloads
        path is allowed until the operator sets ``MM_IMPORT_ROOTS``.
        """
        roots: list[Path] = [Path(root) for root in self._settings.import_roots]
        roots.extend(Path(library.root_path) for library in self._db.query(Library).all())
        roots.append(Path(self._settings.downloads_path))
        return roots

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
        validate_path_under_roots(path, self._allowed_import_roots())
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
            started_at=utcnow(),
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
            history.finished_at = utcnow()
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
            history.finished_at = utcnow()
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
                series.updated_at = utcnow()

            # An import is the operator saying "these are mine". Without this
            # the catalog row would exist while nobody's library contained it,
            # so whoever ran the scan would land back on an empty grid.
            state = self._get_or_create_state(series.id)
            if not state.in_library:
                state.in_library = True
                state.updated_at = utcnow()

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
            # Source-linked series get their cover from the real source cover at
            # serve time; baking a chapter's first page (often a credits/title
            # page) as the cover is what produced the wrong-cover bug. Leave
            # cover_path unset for these so the serve-time source path is used.
            series_is_source_linked = self.resolve_source_link(series.id) is not None

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
                    chapter.scanned_at = utcnow()
                    self._clear_chapter_page_data(chapter.id)

                chapter.page_count = len(chapter_data.pages)
                chapter.scanned_at = utcnow()
                if (
                    chapter_data.pages
                    and not series.cover_path
                    and not series_is_source_linked
                ):
                    series.cover_path = chapter_data.pages[0].file_path

                for page_data in chapter_data.pages:
                    page = Page(
                        chapter_id=chapter.id,
                        number=page_data.number,
                        file_path=page_data.file_path,
                    )
                    self._db.add(page)
                # Flush this chapter's new pages now, right after its old ones
                # were bulk-deleted above. Pages have no AUTOINCREMENT, so
                # SQLite can reuse a rowid freed by that delete; batching many
                # chapters' deletes and inserts into one flush at the end of
                # the scan let a later chapter's new Page collide with an
                # earlier chapter's still identity-mapped (but deleted) Page,
                # which is what emitted the "Identity map already had an
                # identity for Page" SAWarning. Flushing per-chapter keeps
                # each chapter's delete+insert pair settled before the next.
                self._db.flush()

                total_chapters += 1
                total_pages += chapter.page_count

            for key, chapter in existing_chapters.items():
                if key not in seen_keys:
                    # Repoint EVERY progress row off the disappearing chapter,
                    # not just the first one found: progress is per-(user,
                    # profile), so one chapter can be referenced by as many rows
                    # as there are readers.
                    stale_progress = (
                        self._db.query(ReadingProgress)
                        .filter(ReadingProgress.chapter_id == chapter.id)
                        .all()
                    )
                    if stale_progress:
                        replacement = (
                            self._db.query(Chapter)
                            .filter(
                                Chapter.series_id == series.id,
                                Chapter.id != chapter.id,
                            )
                            .order_by(Chapter.number.asc().nullslast(), Chapter.id.asc())
                            .first()
                        )
                        for row in stale_progress:
                            if replacement:
                                row.chapter_id = replacement.id
                                row.last_page = min(
                                    row.last_page,
                                    replacement.page_count or row.last_page,
                                )
                            else:
                                self._db.delete(row)
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
    has_chapters: bool | None = None,
) -> dict[str, object]:
        # INNER JOIN on membership: "My Library" is whatever THIS (user,
        # profile) added, never the catalog. Every filter, the total, and the
        # page below therefore start from a per-caller row set.
        #
        # The 18+ filter is applied HERE, before every other filter and before
        # ``total = query.count()``, so the count and the page can never
        # disagree — a total that includes hidden rows renders phantom pages.
        query = self._apply_mature_filter(
            self._db.query(Series)
            .join(UserSeriesState, self._library_on())
            .filter(Series.deleted_at.is_(None))
        )

        if library_id is not None:
            query = query.filter(Series.library_id == library_id)

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(Series.title.ilike(term), Series.author.ilike(term))
            )

        # Join the current user's progress rows only, so "reading"/"unread"/
        # "recent" reflect this user — not anyone else in the household.
        progress_on = and_(
            ReadingProgress.series_id == Series.id,
            ReadingProgress.user_id == self._user_id,
            ReadingProgress.profile_id == self._profile_id,
        )
        if status == "reading":
            query = query.join(ReadingProgress, progress_on)
        elif status == "unread":
            query = query.outerjoin(ReadingProgress, progress_on).filter(
                ReadingProgress.id.is_(None)
            )

        if reading_status is not None:
            query = query.filter(UserSeriesState.reading_status == reading_status)

        if has_chapters is True:
            query = query.filter(Series.total_chapters > 0)
        elif has_chapters is False:
            query = query.filter(Series.total_chapters == 0)

        if collection_id is not None:
            query = query.join(CollectionSeries).filter(
                CollectionSeries.collection_id == collection_id
            )

        if tag_id is not None:
            query = query.join(SeriesTag).filter(SeriesTag.tag_id == tag_id)

        if is_favorite is not None:
            query = query.filter(UserSeriesState.is_favorite == is_favorite)

        if language is not None:
            query = query.filter(Series.language == language)

        if sort == "updated":
            query = query.order_by(Series.updated_at.desc())
        elif sort == "recent":
            query = query.outerjoin(ReadingProgress, progress_on).order_by(
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

        # Per-caller now that the membership join is in place.
        total = query.count()
        offset = max(page - 1, 0) * per_page
        series_list = (
            query.options(joinedload(Series.chapters))
            .offset(offset)
            .limit(per_page)
            .all()
        )

        all_chapter_ids = [chapter.id for series in series_list for chapter in series.chapters]
        ocr_map = self._get_ocr_status_for_chapters(all_chapter_ids)
        series_ids = [series.id for series in series_list]
        state_map = self._state_map(series_ids)
        progress_map = self._progress_map(series_ids)
        read_map = self._read_chapter_map(series_ids)
        items = [
            self._series_summary(
                series,
                ocr_map=ocr_map,
                state=state_map.get(series.id),
                progress=progress_map.get(series.id),
                read_chapters=read_map.get(series.id, 0),
            )
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
        state: UserSeriesState | None = None,
        progress: ReadingProgress | None = None,
        read_chapters: int = 0,
    ) -> dict[str, object]:
        """Serialize a catalog series *as seen by this (user, profile)*.

        Everything owner-specific — favourite, reading status, read count,
        progress — comes from the caller's own rows, never from the shared
        ``series`` columns. A caller with no state row simply sees the defaults.
        """
        chapter_count = len(series.chapters)
        page_count = sum(chapter.page_count for chapter in series.chapters)
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
            "is_favorite": bool(state.is_favorite) if state else False,
            "reading_status": state.reading_status if state else "unread",
            "chapter_count": chapter_count,
            "read_chapters": read_chapters,
            "page_count": page_count,
            "total_chapters": series.total_chapters,
            "total_pages": series.total_pages,
            "first_chapter_id": first_chapter_id,
            "created_at": series.created_at.isoformat(),
            "updated_at": series.updated_at.isoformat(),
            "reading_progress": self._progress_dict(progress) if progress else None,
            "ocr_summary": ocr_summary,
        }

    def resolve_source_link(self, series_id: int) -> tuple[str, str] | None:
        """Resolve a local series to its ``(source, source_series_id)`` if it is
        source-linked (imported/downloaded from an online source).

        Prefers ``series_trackers.local_series_id`` (a direct series->source
        mapping); falls back to ``source_chapter_links`` joined through the
        series' chapters. Returns ``None`` for purely local series.
        """
        tracker = (
            self._db.query(SeriesTracker)
            .filter(SeriesTracker.local_series_id == series_id)
            .order_by(SeriesTracker.id.asc())
            .first()
        )
        if tracker and tracker.source and tracker.series_id:
            return tracker.source, tracker.series_id

        link = (
            self._db.query(SourceChapterLink)
            .join(Chapter, Chapter.id == SourceChapterLink.local_chapter_id)
            .filter(Chapter.series_id == series_id)
            .order_by(SourceChapterLink.id.asc())
            .first()
        )
        if link and link.source and link.series_id:
            return link.source, link.series_id
        return None

    def get_series(self, series_id: int) -> dict[str, object]:
        # Gated like the grid, not just like the detail screen. This method is
        # the shared reader behind the cover route (image_service) and the
        # reader's chapter list (reading_service), so leaving it open meant a
        # hidden 18+ series was still one numeric id away -- its cover being the
        # single most identifying artefact of it. 404 rather than 403, matching
        # how a mature *source* is made to look absent rather than forbidden.
        series = (
            self._apply_mature_filter(
                self._db.query(Series).options(
                    joinedload(Series.chapters).joinedload(Chapter.pages)
                )
            )
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
            **self._series_summary(
                series,
                state=self._state_map([series.id]).get(series.id),
                progress=self._progress_map([series.id]).get(series.id),
                read_chapters=self._read_chapter_map([series.id]).get(series.id, 0),
            ),
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
        # Gated via the owning series for the same reason as get_series: this
        # backs both /library/chapters/{id} and /reader/chapter/{id}, and an
        # ungated chapter payload hands back the title and the whole page list
        # of a series the gate is hiding.
        chapter = (
            self._apply_mature_filter(
                self._db.query(Chapter)
                .options(joinedload(Chapter.pages))
                .join(Series, Series.id == Chapter.series_id)
            )
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
                    # Deliberately blank, never page.file_path. This used to ship
                    # the absolute in-container path (/data/downloads/<series>/
                    # <chapter>/001.jpg) to every reader client, which handed out
                    # the server's filesystem layout, the library root and the
                    # on-disk titles of other series -- the exact disclosure that
                    # image_service.py:118-125 and path_utils.validate_path_under_roots
                    # go out of their way to withhold on the error path.
                    #
                    # The key itself has to stay: mobile parses it as a required
                    # non-nullable String (mobile/lib/features/library/models/
                    # chapter.dart:74), so dropping it crashes ChapterDetail.fromJson
                    # on every existing installed build. No client reads the value
                    # -- clients address pages by id/number and load bytes from
                    # image_url -- so emptying it is inert. Drop the key once mobile
                    # has shipped a build that no longer requires it.
                    "file_path": "",
                    "image_url": page_image_url(page.id),
                    "width": page.width,
                    "height": page.height,
                }
                for page in pages
            ],
        }

    def set_in_library(self, series_id: int, in_library: bool) -> dict[str, object]:
        """Add / remove a catalog series for *this* (user, profile).

        Removing clears membership but keeps the state row, so a favourite,
        reading status, or recorded progress survives a remove-and-re-add.
        """
        series = (
            self._db.query(Series)
            .filter(Series.id == series_id, Series.deleted_at.is_(None))
            .first()
        )
        if not series:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )
        state = self._get_or_create_state(series_id)
        state.in_library = in_library
        state.updated_at = utcnow()
        self._db.commit()
        return {"series_id": series_id, "in_library": in_library}

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
        # Joined (not left-joined) to Series so the 18+ gate applies: a series
        # hidden from the grid must not reappear on the home screen's
        # Continue Reading strip, which is the surface that shows its title and
        # cover most prominently. Progress rows are untouched.
        rows = (
            self._apply_mature_filter(
                self._db.query(ReadingProgress).join(
                    Series, Series.id == ReadingProgress.series_id
                )
            )
            .filter(
                ReadingProgress.user_id == self._user_id,
                ReadingProgress.profile_id == self._profile_id,
            )
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
        # Roots are operator config, so every account sees the same list -- but
        # the counts are what the caller would actually get back from
        # ``list_series(library_id=...)``, so they are membership-scoped.
        counts = dict(
            self._db.query(Series.library_id, func.count())
            .join(UserSeriesState, self._library_on())
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
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> LibraryService:
    return LibraryService(db, user_id=ctx.user_id, profile_id=ctx.profile_id)
