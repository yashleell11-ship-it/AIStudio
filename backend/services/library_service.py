from __future__ import annotations

import logging
import time
import zipfile
from collections import deque
from collections.abc import Iterable
from core.time_utils import utcnow
from pathlib import Path
from threading import Lock, Thread
from typing import IO, Annotated

from fastapi import Depends
from PIL import Image
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from core.config import get_settings
from core.content_rating import mature_rating_predicate, resolve_mature_gate
from core.errors import AppError
from core.library_authz import series_read_allowed
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
from database.session import SessionLocal, get_db, get_engine
from core.profile_context import ProfileContext, resolve_profile_context
from services.import_cleanup import ImportCleanupService, normalize_folder_path
from services.source_service import SourceService
from utils.mobile_urls import page_image_url, series_cover_url
from utils.path_utils import (
    ARCHIVE_EXTENSIONS,
    natural_sort_key,
    sorted_archive_image_members,
    validate_absolute_path,
    validate_path_under_roots,
)
from connectors.local_filesystem.scanner import ScanResult
from connectors.registry import list_installed_connectors
from database.models import ChapterProgress

logger = logging.getLogger(__name__)

#: ``Series.content_rating`` as shipped by the schema (``models.Series``) and by
#: the raw-SQL bootstrap (``database.session``). A real third state, not a
#: synonym for "safe": nothing populates a rating on folder import, and
#: core.content_rating deliberately keeps unknown *visible* so turning the 18+
#: gate off does not blank a folder-imported library.
UNRATED_CONTENT_RATING = "unknown"

#: What :meth:`LibraryService.inherit_source_content_rating` stores when a series
#: inherits its source's maturity. Must be a member of
#: ``core.content_rating.MATURE_CONTENT_RATINGS`` so it round-trips through both
#: ``is_mature_rating`` and ``mature_rating_predicate`` -- the stored rating is
#: read back by the Python gate and the SQL gate alike.
SOURCE_INHERITED_MATURE_RATING = "adult"


def _chapter_sort_key(chapter: Chapter) -> tuple[float, list[int | str]]:
    number = chapter.number if chapter.number is not None else float("inf")
    return (number, natural_sort_key(chapter.title))


# ----------------------------------------------------------------------
# Page dimensions
#
# The reader lays a chapter out as one lazy list and needs an extent for
# every page BEFORE that page's bytes arrive. With width/height null it
# falls back to a single guessed aspect ratio for all of them
# (mobile/lib/features/reader/utils/page_layout.dart:55-62), so each image
# that finishes loading resizes its slot and shoves everything below it --
# which reads, mid-scroll, as the reader randomly throwing you backwards.
# Recording the real dimensions is what makes the estimate exact and the
# scroll position stable.
# ----------------------------------------------------------------------

# Only the header is read, never the pixels: Image.open() parses enough of
# the stream to answer .size and stops. A 100 KB JPEG costs ~0.2 ms and a
# few KB of IO, which is why measuring a whole chapter at scan time is
# affordable at all -- decoding it would not be.
def _dimensions_of(source: Path | IO[bytes]) -> tuple[int, int] | None:
    """``(width, height)`` for a path or open file object, else ``None``.

    Every failure is ``None``, never an exception: a truncated, empty,
    mis-named, unreadable or absurdly large page must not abort the scan
    that found it. Null columns simply mean "unknown" and the client
    already falls back to its default ratio for them, so the worst case of
    a bad file is today's behaviour for that one page.
    """
    try:
        with Image.open(source) as image:
            width, height = image.size
    except Exception:  # noqa: BLE001 - unreadable page must not fail the scan
        return None
    if not width or not height or width <= 0 or height <= 0:
        return None
    return int(width), int(height)


def measure_pages(entries: Iterable[tuple[int, str]]) -> dict[int, tuple[int, int]]:
    """Map ``page number -> (width, height)`` for ``(number, file_path)`` pairs.

    Takes exactly what a ``Page`` row carries, so the same function serves
    both the scanner (which is minting those rows) and the backfill (which
    is repairing them) and the two can never disagree.

    Archive pages are the reason this is batched rather than per-page. For a
    .cbz every page shares one ``file_path`` -- the archive -- and the member
    that *is* page N is derived positionally. Grouping by archive means one
    open and one ``sorted_archive_image_members`` call per chapter instead of
    per page, and it forces the measurement through the same shared helper
    ImageService.resolve_page_file serves bytes with, so the dimensions
    reported for page N always describe the image page N actually renders.

    Pages that cannot be measured are simply absent from the result.
    """
    sizes: dict[int, tuple[int, int]] = {}
    archives: dict[str, list[int]] = {}

    for number, file_path in entries:
        if not file_path:
            continue
        if Path(file_path).suffix.lower() in ARCHIVE_EXTENSIONS:
            archives.setdefault(file_path, []).append(number)
            continue
        dimensions = _dimensions_of(Path(file_path))
        if dimensions is not None:
            sizes[number] = dimensions

    for archive_path, numbers in archives.items():
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                members = sorted_archive_image_members(archive.namelist())
                for number in numbers:
                    if not 1 <= number <= len(members):
                        continue
                    try:
                        with archive.open(members[number - 1]) as stream:
                            dimensions = _dimensions_of(stream)
                    except Exception:  # noqa: BLE001 - bad member, keep going
                        dimensions = None
                    if dimensions is not None:
                        sizes[number] = dimensions
        except Exception:  # noqa: BLE001 - unreadable archive leaves nulls
            logger.debug("Could not read archive for page sizes", exc_info=True)
            continue

    return sizes


def fill_chapter_page_dimensions(db: Session, chapter_id: int) -> int:
    """Measure and store dimensions for one chapter's unmeasured pages.

    Returns how many rows were filled. Commits, so hand it a session it owns
    -- it is the unit of work the background backfill runs one chapter at a
    time, sized so an interrupted sweep leaves whole chapters done rather
    than a chapter half done.
    """
    rows = (
        db.query(Page)
        .filter(
            Page.chapter_id == chapter_id,
            or_(Page.width.is_(None), Page.height.is_(None)),
        )
        .all()
    )
    if not rows:
        return 0

    sizes = measure_pages((row.number, row.file_path) for row in rows)
    filled = 0
    for row in rows:
        dimensions = sizes.get(row.number)
        if dimensions is None:
            continue
        row.width, row.height = dimensions
        filled += 1
    if filled:
        db.commit()
    return filled


# Pause between chapters so a several-hundred-chapter sweep stays background
# noise against the reader's own image requests rather than competing with
# them for the disk.
_BACKFILL_CHAPTER_PAUSE_SECONDS = 0.05
# Cap on remembered chapter ids; a library this large has long since been
# swept, and forgetting simply allows a later re-attempt.
_BACKFILL_SEEN_LIMIT = 100_000


class PageDimensionBackfill:
    """Fills dimensions for chapters that were indexed before they were recorded.

    Why a background worker and not a migration: the only way to learn a
    page's size is to open the file, and a library holds hundreds of
    thousands of them. Doing that inside an Alembic revision would put an
    unbounded, uninterruptible filesystem walk in front of every app start
    (``run_alembic_migrations`` is called synchronously from ``init_db``),
    and doing it inside ``get_chapter`` would put it in front of every page
    turn. Neither is acceptable, so the request only ever *names* work here
    and returns; a single daemon thread does it afterwards.

    Why it is driven off reads rather than swept blindly: what the owner is
    reading now is what has to be right now. Opening a chapter enqueues that
    chapter first and then the rest of its series in reading order, so by
    the time they reach chapter 2 the whole series is measured. Only the
    very first chapter opened after an upgrade lays out on the old guess.

    One worker, not a pool: this is IO against the same disk the reader is
    pulling images from, and finishing one chapter early beats starting ten.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._pending: deque[int] = deque()
        self._seen: set[int] = set()
        self._thread: Thread | None = None
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled

    def reset(self) -> None:
        """Drop queued and remembered work; leaves enabled/disabled untouched.
        A worker mid-chapter finishes it, then finds an empty queue and exits."""
        with self._lock:
            self._pending.clear()
            self._seen.clear()

    def schedule(self, chapter_ids: Iterable[int]) -> None:
        """Queue chapters, in the order given, skipping ones already attempted."""
        with self._lock:
            if not self._enabled:
                return
            if len(self._seen) > _BACKFILL_SEEN_LIMIT:
                self._seen.clear()
            for chapter_id in chapter_ids:
                if chapter_id in self._seen:
                    continue
                self._seen.add(chapter_id)
                self._pending.append(chapter_id)
            if not self._pending or self._thread is not None:
                return
            # Daemon: this is opportunistic repair, never a reason to hold a
            # shutdown open.
            self._thread = Thread(
                target=self._run,
                name="page-dimension-backfill",
                daemon=True,
            )
            self._thread.start()

    def _next(self) -> int | None:
        with self._lock:
            if not self._pending or not self._enabled:
                # Clearing the handle inside the same lock that starts a
                # thread is what keeps "worker running" single-valued: a
                # schedule() racing this either sees a live thread or gets to
                # start the next one, never both and never neither.
                self._thread = None
                return None
            return self._pending.popleft()

    def _run(self) -> None:
        while True:
            chapter_id = self._next()
            if chapter_id is None:
                return
            db = SessionLocal()
            try:
                filled = fill_chapter_page_dimensions(db, chapter_id)
                if filled:
                    logger.info(
                        "Backfilled dimensions for %d page(s) of chapter %s",
                        filled,
                        chapter_id,
                    )
            except Exception:  # noqa: BLE001 - one bad chapter must not end the sweep
                db.rollback()
                logger.warning(
                    "Page dimension backfill failed for chapter %s",
                    chapter_id,
                    exc_info=True,
                )
            finally:
                db.close()
            time.sleep(_BACKFILL_CHAPTER_PAUSE_SECONDS)


_page_dimension_backfill = PageDimensionBackfill()


def get_page_dimension_backfill() -> PageDimensionBackfill:
    """The process-wide filler. Exposed so the test suite can hold it inert."""
    return _page_dimension_backfill


def _is_application_database(db: Session) -> bool:
    """True when *db* talks to the database the backfill worker writes through.

    The worker opens its own ``SessionLocal``, which is bound to the process
    engine. A LibraryService can legitimately be handed some other session --
    a test fixture's throwaway SQLite file, a restore probe -- and enqueueing
    from one of those would have the worker "repair" chapter ids that mean
    something entirely different in the application database. So the request
    only schedules work when the two are the same database.
    """
    try:
        return db.get_bind() is get_engine()
    except Exception:  # noqa: BLE001 - unbound/partitioned session: don't schedule
        return False


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

    def _can_read(self, series_id: int) -> bool:
        """Object-level read authorization: has this ACCOUNT claimed the series?

        Deliberately account-scoped and deliberately separate from the 18+ gate
        — every fetch-by-id below applies both. See core.library_authz for the
        full rule and why each arm of it exists.
        """
        return series_read_allowed(self._db, self._user_id, series_id)

    def assert_series_readable(self, series_id: int) -> None:
        """Public form of :meth:`_can_read` for collaborators that hold a
        LibraryService but not the caller identity — today ``ImageService.
        get_cover_path``, which must authorize *before* it takes the
        source-cover shortcut and therefore cannot rely on ``get_series``.

        404 ``series_not_found``, byte-identical to a series that does not
        exist: a 403 would confirm the id.
        """
        if not self._can_read(series_id):
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )

    # ------------------------------------------------------------------
    # Collaborator gates
    #
    # The /ocr/* surface reads the same content this service guards (a
    # chapter's transcript, a page's transcript, and a full-text index over
    # both), but through its own service and its own tables. These three
    # methods exist so it applies THIS gate rather than growing a second one:
    # both halves of the rule -- object-level authorization
    # (core.library_authz.series_read_allowed) and the per-profile 18+ filter --
    # stay defined exactly once, in the place that already had to get them
    # right. See routes/ocr.py and services/ocr_search.py for the callers.
    # ------------------------------------------------------------------

    def assert_series_visible(self, series_id: int) -> None:
        """404 ``series_not_found`` unless BOTH gates pass on the series itself.

        The difference from :meth:`assert_series_readable` is the 18+ half.
        That method is authorization-only on purpose -- ``ImageService.
        get_cover_path`` calls it *before* the source-cover shortcut and picks
        the 18+ gate up from ``get_series`` further down. A caller that will not
        go on to call ``get_series`` (the OCR router does not) has to ask for
        both here, or a profile with 18+ off could still address, by id, a series
        that its library grid, its detail screen and its reader all 404.
        """
        visible = (
            self.scope_readable_series(
                self._db.query(Series.id).filter(Series.id == series_id)
            ).first()
        )
        if visible is None:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )

    def _readable_chapter_series(self, chapter_id: int) -> int | None:
        """The owning series id of ``chapter_id``, or ``None`` if this caller
        may not read it -- for *either* reason. Both gates, resolved in one
        query plus the shared predicate, exactly as ``get_chapter`` does."""
        row = (
            self._apply_mature_filter(
                self._db.query(Chapter.series_id).join(
                    Series, Series.id == Chapter.series_id
                )
            )
            .filter(Chapter.id == chapter_id)
            .first()
        )
        if row is None or not self._can_read(row[0]):
            return None
        return row[0]

    def can_read_chapter(self, chapter_id: int) -> bool:
        """Bool form, for callers that already report an unreadable id some
        other way (``OcrJobService.queue_chapters`` reports it as *skipped*,
        which is what it already does for an id that does not exist)."""
        return self._readable_chapter_series(chapter_id) is not None

    def assert_chapter_readable(self, chapter_id: int) -> None:
        """404 ``chapter_not_found`` unless both gates pass.

        Same code and same status as ``get_chapter``'s own denial, and as a
        chapter id that was never real -- a distinct code would confirm the id,
        which is the disclosure.
        """
        if self._readable_chapter_series(chapter_id) is None:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
                details={"chapter_id": chapter_id},
            )

    def assert_page_readable(self, page_id: int) -> None:
        """404 ``page_not_found`` unless both gates pass on the owning series.

        The page-level counterpart of :meth:`assert_chapter_readable`; mirrors
        ``get_page``, which applies the stricter of the two gates because a page
        is the content itself.
        """
        row = (
            self._apply_mature_filter(
                self._db.query(Chapter.series_id)
                .select_from(Page)
                .join(Chapter, Chapter.id == Page.chapter_id)
                .join(Series, Series.id == Chapter.series_id)
            )
            .filter(Page.id == page_id)
            .first()
        )
        if row is None or not self._can_read(row[0]):
            raise AppError(
                "Page not found.",
                code="page_not_found",
                status_code=404,
                details={"page_id": page_id},
            )

    def scope_readable_series(self, query):
        """Narrow a query that joins ``Series`` to the rows this caller may read.

        The list-shaped form of the same two gates. Used by OCR search, which
        used to join ChapterText -> Chapter -> Series with no scoping at all and
        was therefore a full-text search across every account's library.

        The authorization half cannot be expressed as a filter without restating
        ``series_read_allowed``'s five arms in SQL, and a *duplicated
        authorization rule* is precisely the thing core.library_authz exists to
        prevent -- so the shared predicate is called once per distinct candidate
        series instead. Bounded by the number of distinct series that matched the
        text, not by the size of the catalog or by the number of hits, and each
        call is one round trip of covered EXISTS.
        """
        scoped = self._apply_mature_filter(query)
        candidates = [row[0] for row in scoped.with_entities(Series.id).distinct()]
        allowed = [
            series_id for series_id in candidates if self._can_read(series_id)
        ]
        return scoped.filter(Series.id.in_(allowed))

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
                known_sizes: dict[tuple[int, str], tuple[int, int]] = {}
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
                    known_sizes = self._known_page_dimensions(chapter.id)
                    self._clear_chapter_page_data(chapter.id)

                chapter.page_count = len(chapter_data.pages)
                chapter.scanned_at = utcnow()
                if (
                    chapter_data.pages
                    and not series.cover_path
                    and not series_is_source_linked
                ):
                    series.cover_path = chapter_data.pages[0].file_path

                # Measured here, while the files are already being walked, so
                # every page reaches the reader with a real aspect ratio and
                # the lazy list never has to guess. Header reads only (see
                # measure_pages); anything unreadable is left null rather than
                # aborting the import of an otherwise fine chapter.
                #
                # Only pages this scan has never sized are opened. A completed
                # download re-persists EVERY chapter of the series it landed in
                # (the else-branch above drops and re-inserts their pages), so
                # measuring unconditionally would re-open the whole series' pages
                # once per downloaded chapter -- quadratic file IO across a
                # multi-chapter download, and painful on network storage. A page
                # keyed by the same (number, file_path) is the same image, and
                # even a file re-encoded in place keeps its aspect ratio, which
                # is the only thing the client derives from these two numbers.
                page_sizes = measure_pages(
                    (page_data.number, page_data.file_path)
                    for page_data in chapter_data.pages
                    if (page_data.number, page_data.file_path) not in known_sizes
                )
                for page_data in chapter_data.pages:
                    dimensions = known_sizes.get(
                        (page_data.number, page_data.file_path)
                    ) or page_sizes.get(page_data.number)
                    page = Page(
                        chapter_id=chapter.id,
                        number=page_data.number,
                        file_path=page_data.file_path,
                        width=dimensions[0] if dimensions else None,
                        height=dimensions[1] if dimensions else None,
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

    def inherit_source_content_rating(self, series_id: int) -> str | None:
        """Stamp a source-linked series with its *source's* maturity.

        The hole this closes: ``Series.content_rating`` defaults to "unknown"
        for every import and download, and the 18+ gate deliberately keeps
        unknown visible -- so a series downloaded from an adult source was not
        marked adult and showed up on the home page and in the library of a
        profile with 18+ switched OFF. The source's own maturity was known the
        whole time (``ConnectorDescriptor.mature``); nothing was writing it down
        for the local row.

        This is rule 3 of :func:`core.content_rating.resolve_tracker_rating`
        applied to a local ``Series`` instead of a followed tracker: *a series
        whose chapters came from an 18+ source is 18+ by construction*. Same
        signal, same direction, same reason -- the failure the owner cares about
        is adult content appearing where he did not expect it, and a false hide
        costs one toggle while a false show costs the thing the gate exists for.

        Three things it deliberately does NOT do:

        * **Never downgrades.** It only ever writes when the stored rating is
          still the unset default, so a rating a user set, or one captured from
          the source's own metadata (``rating_from_genres`` at follow time),
          survives untouched -- including a deliberate "safe" on one series from
          an otherwise-adult source.
        * **Never marks a hand-imported folder.** Inheritance requires a real
          source link (:meth:`resolve_source_link`: a tracker bound to this
          series, or a ``source_chapter_links`` row for one of its chapters).
          A folder the owner dropped in has no source to inherit from and stays
          "unknown", i.e. stays visible -- which is the whole reason unknown is
          not folded into mature.
        * **Never writes "safe".** A non-mature source says nothing about the
          series; it only fails to say "adult". Writing "safe" would be
          manufacturing a rating and would block a later, better signal.

        Returns the rating it stored, or ``None`` when nothing was written.
        Callers commit -- this only flushes, so it composes with the download
        worker's transaction.
        """
        series = self._db.get(Series, series_id)
        if series is None:
            return None

        # An explicit rating -- from the user or from the source's metadata --
        # is a stronger signal than "which site did the bytes come from", and
        # overwriting it is how a user's own verdict gets silently reverted.
        current = (series.content_rating or "").strip().lower()
        if current and current != UNRATED_CONTENT_RATING:
            return None

        link = self.resolve_source_link(series_id)
        if link is None:
            return None

        descriptor = next(
            (
                item
                for item in list_installed_connectors(include_mature=True)
                if item.source_type == link[0]
            ),
            None,
        )
        if descriptor is None or not descriptor.mature:
            return None

        series.content_rating = SOURCE_INHERITED_MATURE_RATING
        series.updated_at = utcnow()
        self._db.flush()
        logger.info(
            "series_id=%s inherited rating '%s' from adult source '%s'",
            series_id,
            SOURCE_INHERITED_MATURE_RATING,
            link[0],
        )
        return SOURCE_INHERITED_MATURE_RATING

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
        # Two independent gates, both required. The 18+ filter above answers
        # "may this profile see adult content right now"; this answers "has this
        # account any claim on THIS series" -- the object-level authorization
        # that filtering on the row id alone never provided, and which is what
        # let a sibling profile or a different account fetch any series by
        # guessing its id. Same 404 either way; the codes must not diverge or
        # the denial becomes an existence oracle.
        if not series or not self._can_read(series_id):
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
        # Authorized through the OWNING series -- a chapter has no claim of its
        # own. Reported as chapter_not_found, not series_not_found: the denial
        # has to be indistinguishable from a chapter id that was never real.
        if not chapter or not self._can_read(chapter.series_id):
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
                details={"chapter_id": chapter_id},
            )
        pages = sorted(chapter.pages, key=lambda page: page.number)
        if any(page.width is None or page.height is None for page in pages):
            self._schedule_dimension_backfill(chapter)
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

    def _schedule_dimension_backfill(self, chapter: Chapter) -> None:
        """Hand a chapter (and the rest of its series) to the background filler.

        Called only after ``get_chapter`` has already applied the object-level
        gate and the 18+ filter, and only ever with chapters of the series the
        caller just proved they may read -- so this widens nothing. Nothing is
        returned to the caller and no file is touched on this thread: the whole
        method is one indexed query and an append under a lock.

        The rest of the series is enqueued because a reader moves forward. Only
        the chapter open that discovers the gap can be laid out on the old
        guess; by the time they hit "next", the pages it needs are measured.
        """
        if not _is_application_database(self._db):
            return
        siblings = (
            self._db.query(Chapter.id, Chapter.number)
            .filter(
                Chapter.series_id == chapter.series_id,
                Chapter.id != chapter.id,
            )
            .order_by(Chapter.number.asc().nullslast(), Chapter.id.asc())
            .all()
        )
        current = chapter.number
        ahead: list[int] = []
        behind: list[int] = []
        for sibling_id, number in siblings:
            is_ahead = current is None or (number is not None and number > current)
            (ahead if is_ahead else behind).append(sibling_id)
        _page_dimension_backfill.schedule([chapter.id, *ahead, *behind])

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
        # This backs BOTH /reader/page/{id}/image and /library/pages/{id}/image
        # (via ImageService.serve_page), and it was the least guarded read in the
        # app: no ownership check AND no 18+ filter, unlike get_series /
        # get_chapter. A page image is the content itself, so it needs the
        # stricter of the two, not the looser -- both gates are applied here.
        page = (
            self._apply_mature_filter(
                self._db.query(Page)
                .options(joinedload(Page.chapter))
                .join(Chapter, Chapter.id == Page.chapter_id)
                .join(Series, Series.id == Chapter.series_id)
            )
            .filter(Page.id == page_id)
            .first()
        )
        if not page or not self._can_read(page.chapter.series_id):
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

    def _known_page_dimensions(
        self, chapter_id: int
    ) -> dict[tuple[int, str], tuple[int, int]]:
        """Already-recorded sizes for a chapter, keyed by ``(number, file_path)``.

        Read immediately before ``_clear_chapter_page_data`` wipes the rows, so a
        rescan can carry forward what it already knows instead of re-opening
        every file. Half-recorded rows are excluded, which keeps null the single
        meaning of "unmeasured" (see the a1f4c8b27d63 migration).
        """
        rows = (
            self._db.query(Page.number, Page.file_path, Page.width, Page.height)
            .filter(
                Page.chapter_id == chapter_id,
                Page.width.isnot(None),
                Page.height.isnot(None),
            )
            .all()
        )
        return {(number, path): (width, height) for number, path, width, height in rows}

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
