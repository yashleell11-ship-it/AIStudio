"""Background download workers and chapter download execution."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import joinedload

from connectors.base import SourceConnector
from connectors.models import Page
from core.time_utils import utcnow
from connectors.registry import create_connector
from core.config import get_settings
from database.models import Chapter, Download, DownloadQueue, SourceChapterLink
from database.session import SessionLocal
from services.download_support import (
    PARTIAL_SUFFIX,
    ChapterManifest,
    DiskSpaceError,
    DownloadMetrics,
    DownloadProfiler,
    PageManifestEntry,
    ProfileSample,
    directory_size,
    disk_stats,
    ensure_disk_space,
    estimate_chapter_bytes,
    fetch_image_resumable,
    sha256_bytes,
    sha256_file,
    verify_image_file,
)
from services.import_cleanup import normalize_folder_path
from services.library_service import LibraryService
from services.ocr_pipeline import OcrJobService
from services.source_service import SourceService
from utils.filename_utils import page_extension, sanitize_path_segment

logger = logging.getLogger(__name__)


class DownloadCancelled(Exception):
    """Raised when a download is cancelled while in progress."""


class DownloadPaused(Exception):
    """Raised when a download is paused while in progress."""


class _SpeedTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: dict[int, list[tuple[float, int]]] = {}

    def reset(self, download_id: int, *, bytes_downloaded: int = 0) -> None:
        with self._lock:
            now = time.monotonic()
            self._samples[download_id] = [(now, bytes_downloaded)]

    def update(self, download_id: int, bytes_downloaded: int) -> None:
        with self._lock:
            samples = self._samples.setdefault(download_id, [])
            samples.append((time.monotonic(), bytes_downloaded))
            if len(samples) > 20:
                self._samples[download_id] = samples[-20:]

    def pop(self, download_id: int) -> None:
        with self._lock:
            self._samples.pop(download_id, None)

    def snapshot(
        self,
        download_id: int,
        *,
        bytes_downloaded: int,
        pages_total: int,
        pages_done: int,
    ) -> tuple[float | None, int | None, float | None]:
        with self._lock:
            samples = list(self._samples.get(download_id, []))

        if len(samples) < 2:
            return None, None, None

        start_time, start_bytes = samples[0]
        end_time, end_bytes = samples[-1]
        elapsed = max(end_time - start_time, 0.001)
        delta_bytes = max(end_bytes - start_bytes, 0)
        if delta_bytes <= 0:
            return None, None, None

        speed_bps = delta_bytes / elapsed
        speed_mbps = speed_bps / (1024 * 1024)

        eta_seconds: int | None = None
        if pages_total > pages_done and pages_done > 0 and speed_bps > 0:
            avg_bytes_per_page = bytes_downloaded / pages_done
            remaining_bytes = avg_bytes_per_page * (pages_total - pages_done)
            eta_seconds = int(remaining_bytes / speed_bps)

        return speed_bps, eta_seconds, speed_mbps


#: Absolute ceiling on simultaneous chapter downloads -- matches the top of
#: the Settings dropdown (1-10). The executor's real OS thread pool is
#: always sized to this constant, decoupled from the user's configured
#: limit, so raising/lowering the limit at runtime (Part 5) never requires
#: recreating the executor -- only ``_effective_workers`` changes, and
#: ``_dispatch()`` already reads it fresh on every call.
MAX_CONCURRENT_CHAPTER_DOWNLOADS = 10


class DownloadManager:
    """Connector-agnostic download queue with adaptive worker concurrency."""

    def __init__(self, *, max_workers: int | None = None) -> None:
        settings = get_settings()
        configured = max_workers or settings.download_concurrent_chapters
        self._max_workers = max(1, min(configured, MAX_CONCURRENT_CHAPTER_DOWNLOADS))
        self._effective_workers = self._max_workers
        self._downloads_root = Path(settings.downloads_path)
        self._min_free_bytes = 100 * 1024 * 1024
        self._warn_free_bytes = 500 * 1024 * 1024
        self._executor: ThreadPoolExecutor | None = None
        self._active_ids: set[int] = set()
        self._pool_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._speed = _SpeedTracker()
        self._profiler = DownloadProfiler()
        self._started = False
        self._recent_failures = 0
        self._recent_successes = 0

    @property
    def downloads_root(self) -> Path:
        return self._downloads_root

    @property
    def active_count(self) -> int:
        with self._pool_lock:
            return len(self._active_ids)

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def set_max_workers(self, value: int) -> None:
        """Change the configured chapter-download concurrency limit
        immediately -- takes effect on the very next dispatch, no restart
        or executor recreation needed. Never exceeds
        ``MAX_CONCURRENT_CHAPTER_DOWNLOADS``. Lowering the limit does not
        interrupt chapters already downloading; it only stops new ones
        from starting until the count drops back under the new limit."""
        clamped = max(1, min(value, MAX_CONCURRENT_CHAPTER_DOWNLOADS))
        with self._pool_lock:
            self._max_workers = clamped
            self._effective_workers = clamped
            self._recent_failures = 0
            self._recent_successes = 0
        self.notify_change()

    def start(self) -> None:
        if self._started:
            return
        self._stop_event.clear()
        self._downloads_root.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(
            max_workers=MAX_CONCURRENT_CHAPTER_DOWNLOADS,
            thread_name_prefix="download-worker",
        )
        self._started = True
        self._recover_interrupted()
        self._dispatch()

    def stop(self) -> None:
        self._stop_event.set()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        self._started = False

    def notify_change(self) -> None:
        if self._started:
            self._dispatch()

    def check_disk_before_queue(self, *, page_count: int) -> list[str]:
        required = estimate_chapter_bytes(page_count)
        return ensure_disk_space(
            self._downloads_root,
            required_bytes=required,
            min_free_bytes=self._min_free_bytes,
            warn_free_bytes=self._warn_free_bytes,
        )

    def get_metrics(self, db) -> dict[str, object]:
        total = db.query(Download).count()
        completed = db.query(Download).filter(Download.status == "completed").count()
        failed = db.query(Download).filter(Download.status == "failed").count()
        queued = db.query(Download).filter(Download.status == "queued").count()
        paused = db.query(Download).filter(Download.status == "paused").count()
        active = db.query(Download).filter(Download.status == "downloading").count()
        remaining = queued + active + paused
        _total_disk, used_disk, free_disk = disk_stats(self._downloads_root)
        metrics = DownloadMetrics(
            total=total,
            completed=completed,
            failed=failed,
            remaining=remaining,
            active=active,
            storage_used_bytes=directory_size(self._downloads_root),
            storage_free_bytes=free_disk,
        )
        payload = metrics.to_dict()
        payload["queued"] = queued
        payload["paused"] = paused
        payload["workers"] = {
            "configured": self._max_workers,
            "active": self._effective_workers,
            "running": len(self._active_ids),
        }
        payload["profile"] = self._profiler.snapshot()
        payload.update(self._overall_progress(db))
        return payload

    def _overall_progress(self, db) -> dict[str, object]:
        """Aggregate speed/ETA across every currently-downloading chapter.

        Speed is a straight sum of each active download's own tracked
        speed. ETA sums each active download's own remaining-bytes estimate
        and divides by the combined speed -- an estimate of "how long until
        every chapter that is actively downloading right now finishes,"
        not including chapters still waiting in the queue (those have no
        speed sample yet to estimate from).
        """
        active_downloads = (
            db.query(Download).filter(Download.status == "downloading").all()
        )
        total_speed_bps = 0.0
        total_remaining_bytes = 0
        for download in active_downloads:
            speed_bps, _, _ = self.get_speed_snapshot(download)
            if speed_bps:
                total_speed_bps += speed_bps
            if download.pages_total > 0 and download.pages_done > 0 and download.bytes_downloaded > 0:
                avg_bytes_per_page = download.bytes_downloaded / download.pages_done
                remaining_pages = max(download.pages_total - download.pages_done, 0)
                total_remaining_bytes += int(avg_bytes_per_page * remaining_pages)

        overall_eta_seconds: int | None = None
        if total_speed_bps > 0 and total_remaining_bytes > 0:
            overall_eta_seconds = int(total_remaining_bytes / total_speed_bps)

        return {
            "overall_speed_bps": round(total_speed_bps, 2),
            "overall_speed_mbps": round(total_speed_bps / (1024 * 1024), 4),
            "overall_eta_seconds": overall_eta_seconds,
        }

    def get_speed_snapshot(self, download: Download) -> tuple[float | None, int | None, float | None]:
        return self._speed.snapshot(
            download.id,
            bytes_downloaded=download.bytes_downloaded,
            pages_total=download.pages_total,
            pages_done=download.pages_done,
        )

    def _recover_interrupted(self) -> None:
        db = SessionLocal()
        try:
            rows = (
                db.query(Download)
                .options(joinedload(Download.queue))
                .filter(Download.status.in_(("downloading",)))
                .all()
            )
            for row in rows:
                chapter_path = self._chapter_path(row)
                manifest = ChapterManifest().load(chapter_path)
                if manifest is not None and manifest.completed_count() > row.pages_done:
                    row.pages_done = manifest.completed_count()
                    if row.pages_total > 0:
                        row.progress = round((row.pages_done / row.pages_total) * 100, 2)
                row.status = "queued"
                row.updated_at = utcnow()
                if row.queue:
                    row.queue.state = "pending"
            db.commit()
        finally:
            db.close()

    def _tune_workers(self, queue_depth: int) -> None:
        total = self._recent_failures + self._recent_successes
        if total >= 5:
            failure_rate = self._recent_failures / total
            if failure_rate > 0.35:
                self._effective_workers = max(1, self._effective_workers - 1)
            elif failure_rate < 0.1 and queue_depth > self._effective_workers:
                self._effective_workers = min(self._max_workers, self._effective_workers + 1)
            self._recent_failures = 0
            self._recent_successes = 0

    def _dispatch(self) -> None:
        if self._stop_event.is_set() or self._executor is None:
            return

        with self._pool_lock:
            db = SessionLocal()
            try:
                queue_depth = (
                    db.query(Download)
                    .join(DownloadQueue)
                    .filter(
                        Download.status == "queued",
                        DownloadQueue.state == "pending",
                    )
                    .count()
                )
            finally:
                db.close()

            self._tune_workers(queue_depth)
            available = self._effective_workers - len(self._active_ids)
            if available <= 0:
                return

            db = SessionLocal()
            try:
                pending = (
                    db.query(Download)
                    .join(DownloadQueue)
                    .filter(
                        Download.status == "queued",
                        DownloadQueue.state == "pending",
                    )
                    .order_by(DownloadQueue.priority.asc(), Download.created_at.asc())
                    .limit(available)
                    .all()
                )
                download_ids = [item.id for item in pending]
            finally:
                db.close()

            for download_id in download_ids:
                if download_id in self._active_ids:
                    continue
                self._active_ids.add(download_id)
                self._executor.submit(self._run_download, download_id)

    def _run_download(self, download_id: int) -> None:
        try:
            self._process_download(download_id)
            self._recent_successes += 1
        except Exception:
            self._recent_failures += 1
        finally:
            with self._pool_lock:
                self._active_ids.discard(download_id)
            self._speed.pop(download_id)
            if not self._stop_event.is_set():
                self._dispatch()

    def _chapter_path(self, download: Download) -> Path:
        series_dir = sanitize_path_segment(download.series_title, fallback=download.series_id)
        chapter_dir = sanitize_path_segment(download.chapter_title, fallback=download.chapter_id)
        return self._downloads_root / series_dir / chapter_dir

    def _fetch_page(
        self,
        connector: SourceConnector,
        page: Page,
        index: int,
        chapter_path: Path,
    ) -> tuple[int, str, str, int]:
        """Fetch, verify, and hash a single page. Runs on a worker thread as
        part of a chapter's page pool -- touches only this page's own
        uniquely-named file, so it needs no locking or shared state. Returns
        the data the caller applies to the manifest/DB on its own thread."""
        assert page.remote_url is not None
        extension = page_extension(page.remote_url)
        filename = f"{index:03d}{extension}"
        target = chapter_path / filename
        partial = chapter_path / f"{filename}{PARTIAL_SUFFIX}"

        ensure_disk_space(
            self._downloads_root,
            required_bytes=estimate_chapter_bytes(1),
            min_free_bytes=self._min_free_bytes,
            warn_free_bytes=self._warn_free_bytes,
        )

        settings = get_settings()
        content = fetch_image_resumable(
            page.remote_url,
            connector=connector,
            final_path=target,
            partial_path=partial,
            max_retries=max(1, settings.download_retry_count),
            backoff_base=max(0.0, settings.download_retry_delay_seconds),
            timeout=max(1.0, settings.download_timeout_seconds),
        )
        if not verify_image_file(target):
            target.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded page {index} failed verification.")
        file_hash = sha256_bytes(content)
        return index, filename, file_hash, len(content)

    def _process_download(self, download_id: int) -> None:
        db = SessionLocal()
        started = time.perf_counter()
        fetch_ms = 0.0
        verify_ms = 0.0
        import_ms = 0.0
        try:
            download = (
                db.query(Download)
                .options(joinedload(Download.queue))
                .filter(Download.id == download_id)
                .first()
            )
            if download is None or download.queue is None:
                return
            if download.status in ("cancelled", "completed"):
                return
            if download.status == "paused" or download.queue.state == "paused":
                return

            download.status = "downloading"
            download.queue.state = "active"
            download.error = None
            download.updated_at = utcnow()
            db.commit()

            connector = create_connector(download.source)
            pages = connector.get_chapter_pages(download.chapter_id)
            logger.info(
                "chapter_id=%s get_chapter_pages_called=yes pages_found=%d",
                download.chapter_id,
                len(pages),
            )
            if not pages:
                raise RuntimeError("Chapter has no downloadable pages.")

            remote_pages = [page for page in pages if page.remote_url]
            if not remote_pages:
                raise RuntimeError("Chapter pages do not expose remote URLs.")

            if download.pages_total <= 0:
                download.pages_total = len(remote_pages)
            download.updated_at = utcnow()
            db.commit()

            ensure_disk_space(
                self._downloads_root,
                required_bytes=estimate_chapter_bytes(len(remote_pages)),
                min_free_bytes=self._min_free_bytes,
                warn_free_bytes=self._warn_free_bytes,
            )

            chapter_path = self._chapter_path(download)
            chapter_path.mkdir(parents=True, exist_ok=True)
            manifest = ChapterManifest().load(chapter_path) or ChapterManifest(
                download_id=download.id,
                chapter_id=download.chapter_id,
            )
            manifest.download_id = download.id
            manifest.chapter_id = download.chapter_id

            if download.pages_done <= 0 and manifest.completed_count() > 0:
                download.pages_done = manifest.completed_count()

            bytes_total = self._sum_existing_bytes(chapter_path, manifest)
            if download.bytes_downloaded < bytes_total:
                download.bytes_downloaded = bytes_total
            if download.pages_total > 0 and download.pages_done > 0:
                download.progress = round((download.pages_done / download.pages_total) * 100, 2)
            db.commit()
            self._speed.reset(download.id, bytes_downloaded=download.bytes_downloaded)

            # Phase 1 (sequential, local-only): figure out which pages are
            # already downloaded and verified on disk, so a resumed download
            # doesn't re-fetch them. This is pure filesystem/hash work, fast
            # enough not to need parallelizing.
            pending: list[tuple[int, Page]] = []
            for index, page in enumerate(remote_pages, start=1):
                assert page.remote_url is not None
                filename = f"{index:03d}{page_extension(page.remote_url)}"
                target = chapter_path / filename
                existing_entry = manifest.entry_for_index(index)
                if (
                    target.is_file()
                    and verify_image_file(target)
                    and existing_entry is not None
                    and existing_entry.remote_url == page.remote_url
                    and existing_entry.sha256 == sha256_file(target)
                ):
                    continue
                if target.is_file() and not verify_image_file(target):
                    target.unlink(missing_ok=True)
                pending.append((index, page))

            skipped_count = len(remote_pages) - len(pending)
            if skipped_count > download.pages_done:
                download.pages_done = skipped_count
                download.progress = round((skipped_count / len(remote_pages)) * 100, 2)
                download.updated_at = utcnow()
                db.commit()

            # Phase 2 (parallel): fetch the remaining pages concurrently.
            # Each worker thread only does network I/O + local file I/O +
            # hashing on its own uniquely-named file -- no shared mutable
            # state -- so the results are applied to the manifest and the
            # DB row on this (owning) thread only, one at a time as they
            # complete, regardless of completion order.
            fetch_started = time.perf_counter()
            if pending:
                page_concurrency = max(1, get_settings().download_page_concurrency)
                worker_count = min(page_concurrency, len(pending))
                page_pool = ThreadPoolExecutor(
                    max_workers=worker_count,
                    thread_name_prefix=f"download-{download.id}-page",
                )
                page_map = dict(pending)
                futures: dict[Future, int] = {
                    page_pool.submit(self._fetch_page, connector, page, index, chapter_path): index
                    for index, page in pending
                }
                try:
                    for future in as_completed(futures):
                        self._assert_can_continue(db, download.id)
                        index, filename, file_hash, size = future.result()

                        manifest.pages = [
                            entry for entry in manifest.pages if entry.index != index
                        ]
                        manifest.pages.append(
                            PageManifestEntry(
                                index=index,
                                filename=filename,
                                remote_url=page_map[index].remote_url,
                                sha256=file_hash,
                                size=size,
                            )
                        )
                        manifest.save(chapter_path)

                        bytes_total = self._sum_existing_bytes(chapter_path, manifest)
                        download = db.query(Download).filter(Download.id == download_id).first()
                        if download is None:
                            return
                        download.pages_done = manifest.completed_count()
                        download.bytes_downloaded = bytes_total
                        download.progress = round(
                            (download.pages_done / len(remote_pages)) * 100, 2
                        )
                        download.updated_at = utcnow()
                        db.commit()
                        self._speed.update(download.id, bytes_total)
                except Exception:
                    # Drop pending futures immediately rather than blocking
                    # on in-flight fetches -- keeps cancel/pause responsive.
                    # Already-completed page files on disk are harmless: the
                    # Phase 1 resume-scan picks them up on the next attempt.
                    page_pool.shutdown(wait=False, cancel_futures=True)
                    raise
                else:
                    page_pool.shutdown(wait=True)
            fetch_ms += (time.perf_counter() - fetch_started) * 1000

            import_started = time.perf_counter()
            local_chapter = self._import_and_verify(
                db,
                download,
                chapter_path,
                expected_page_count=len(remote_pages),
            )
            import_ms = (time.perf_counter() - import_started) * 1000

            download = db.query(Download).filter(Download.id == download_id).first()
            if download is None:
                return
            download.status = "completed"
            download.progress = 100.0
            download.pages_done = len(remote_pages)
            download.local_chapter_id = local_chapter.id
            download.updated_at = utcnow()
            if download.queue:
                download.queue.state = "completed"
            db.commit()

            # Auto-queue OCR for newly imported chapters
            if local_chapter is not None and get_settings().ocr_auto_queue:
                try:
                    ocr_service = OcrJobService(db)
                    result = ocr_service.queue_chapters([local_chapter.id])
                    if result["queued"]:
                        logger.info(
                            "Auto-queued chapter %s for OCR (job_ids=%s)",
                            local_chapter.id,
                            result["queued"],
                        )
                except Exception:
                    logger.warning(
                        "Failed to auto-queue OCR for chapter %s", local_chapter.id, exc_info=True
                    )
        except DownloadCancelled:
            db.rollback()
            self._set_terminal_state(download_id, status="cancelled", queue_state="cancelled")
        except DownloadPaused:
            db.rollback()
            self._set_paused(download_id)
        except DiskSpaceError as exc:
            db.rollback()
            self._set_failed(download_id, str(exc), pause=True)
        except Exception as exc:
            db.rollback()
            self._set_failed(download_id, str(exc))
        finally:
            total_ms = (time.perf_counter() - started) * 1000
            self._profiler.record(
                ProfileSample(
                    fetch_ms=fetch_ms,
                    verify_ms=verify_ms,
                    import_ms=import_ms,
                    total_ms=total_ms,
                )
            )
            db.close()

    def _sum_existing_bytes(self, chapter_path: Path, manifest: ChapterManifest) -> int:
        total = 0
        for entry in manifest.pages:
            file_path = chapter_path / entry.filename
            if file_path.is_file():
                total += file_path.stat().st_size
        return total

    def _import_and_verify(
        self,
        db,
        download: Download,
        chapter_path: Path,
        *,
        expected_page_count: int,
    ) -> Chapter:
        # Import AS the person who queued this download. Indexing the series
        # creates its library-membership row, and that row is keyed on
        # (user_id, profile_id) -- so an unscoped service here files the
        # membership under the legacy (NULL, NULL) bucket and the
        # just-downloaded series is invisible in every real profile's library,
        # on every client. The worker has no request context, so the only place
        # the initiating (user, profile) can come from is the Download row.
        #
        # profile_id is NULL for downloads queued before the column existed
        # (and for anonymous/unscoped ones). That is honoured as-is rather than
        # resolved to, say, the account's oldest profile: the row has never
        # recorded who asked, and inventing an answer drops someone else's
        # series into a profile's shelf. Such a download lands in its account's
        # unscoped bucket; the owner can move it with the explicit
        # "add to library" action (LibraryService.set_in_library).
        library = LibraryService(
            db, user_id=download.user_id, profile_id=download.profile_id
        )
        if download.user_id is not None and download.profile_id is None:
            logger.info(
                "download_id=%s has no initiating profile (legacy row); "
                "library membership filed under the account's unscoped bucket",
                download.id,
            )
        self._index_downloaded_series(library, chapter_path)

        normalized_folder = normalize_folder_path(str(chapter_path.resolve()))
        local_chapter = (
            db.query(Chapter)
            .options(joinedload(Chapter.pages))
            .filter(Chapter.folder_path == normalized_folder)
            .first()
        )
        if local_chapter is None:
            raise RuntimeError("Downloaded chapter could not be indexed in the library.")
        if local_chapter.page_count != expected_page_count:
            raise RuntimeError(
                "Imported chapter page count mismatch: "
                f"expected {expected_page_count}, got {local_chapter.page_count}."
            )
        page_rows = sorted(local_chapter.pages, key=lambda item: item.number)
        if len(page_rows) != expected_page_count:
            raise RuntimeError(
                "Imported chapter is missing pages after library scan."
            )
        for page_row in page_rows:
            if not verify_image_file(Path(page_row.file_path)):
                raise RuntimeError(f"Imported page {page_row.number} failed verification.")

        link = (
            db.query(SourceChapterLink)
            .filter(
                SourceChapterLink.source == download.source,
                SourceChapterLink.series_id == download.series_id,
                SourceChapterLink.chapter_id == download.chapter_id,
            )
            .first()
        )
        if link is None:
            link = SourceChapterLink(
                source=download.source,
                series_id=download.series_id,
                chapter_id=download.chapter_id,
                local_chapter_id=local_chapter.id,
            )
            db.add(link)
        else:
            link.local_chapter_id = local_chapter.id
        db.flush()

        # Now that the series has a real source link, let it inherit the
        # source's maturity. Deliberately AFTER the flush above: on the first
        # chapter of a new series the link is created right here, and
        # LibraryService.resolve_source_link -- which is what distinguishes a
        # downloaded series from a hand-imported folder -- cannot see it any
        # earlier. (_index_downloaded_series ran before this block, so doing it
        # inside _persist_scan would find no link and silently skip.)
        #
        # A series downloaded from an 18+ source is 18+; without this it stayed
        # at the schema default "unknown", and the gate keeps unknown visible on
        # purpose, so it appeared for profiles with 18+ switched off. Never
        # overwrites an existing rating and never touches a series with no
        # source link -- see LibraryService.inherit_source_content_rating.
        library.inherit_source_content_rating(local_chapter.series_id)
        return local_chapter

    def _index_downloaded_series(
        self, library: LibraryService, chapter_path: Path
    ) -> None:
        """Index only the series folder that owns the just-completed chapter,
        instead of re-scanning the entire downloads root on every completion.

        A completed download only ever *adds* one chapter directory beneath one
        series directory; nothing anywhere else in the library changes. The old
        behaviour re-indexed the whole downloads root on every completion, which
        made each completion O(total library chapters) -- i.e. O(n^2) work across
        a large multi-chapter download, and re-touched every unrelated series'
        rows each time. Scoping the scan+persist to the single owning series
        folder keeps a completion proportional to just that series and leaves
        every other series untouched.

        Correctness is preserved by reusing the exact same discovery
        (``SourceService.discover_folder``) and persistence
        (``LibraryService._persist_scan``) the full rescan used: a "series"-mode
        scan of the series folder yields the identical ``ScannedSeries`` that a
        library-mode scan of the whole downloads root produced for it, so the
        resulting Series/Chapter/Page rows -- including page order, titles,
        chapter numbers, cover, and aggregate counts -- match a full rescan
        exactly. The global orphan-merge / stale-series cleanup that
        ``index_downloads_root`` also ran is intentionally skipped here: a
        download never removes on-disk content, so there is nothing stale to
        prune, and running that cleanup against a single-series scan would
        wrongly treat every *other* series as missing and delete it.
        """
        series_folder = chapter_path.parent
        library_row = library._get_or_create_library(self._downloads_root)
        scan = SourceService().discover_folder(str(series_folder.resolve()))
        library._persist_scan(library_row, scan)
        library._db.flush()

    def _assert_can_continue(self, db, download_id: int) -> None:
        db.expire_all()
        download = db.query(Download).filter(Download.id == download_id).first()
        if download is None:
            raise DownloadCancelled()
        if download.status == "cancelled" or (download.queue and download.queue.state == "cancelled"):
            raise DownloadCancelled()
        if download.status == "paused" or (download.queue and download.queue.state == "paused"):
            raise DownloadPaused()

    def _set_terminal_state(self, download_id: int, *, status: str, queue_state: str) -> None:
        db = SessionLocal()
        try:
            download = db.query(Download).filter(Download.id == download_id).first()
            if download is None:
                return
            download.status = status
            download.updated_at = utcnow()
            if download.queue:
                download.queue.state = queue_state
            db.commit()
        finally:
            db.close()

    def _set_paused(self, download_id: int) -> None:
        db = SessionLocal()
        try:
            download = db.query(Download).filter(Download.id == download_id).first()
            if download is None:
                return
            download.status = "paused"
            download.updated_at = utcnow()
            if download.queue:
                download.queue.state = "paused"
            db.commit()
        finally:
            db.close()

    def _set_failed(self, download_id: int, message: str, *, pause: bool = False) -> None:
        db = SessionLocal()
        try:
            download = db.query(Download).filter(Download.id == download_id).first()
            if download is None:
                return
            download.status = "paused" if pause else "failed"
            download.error = message
            download.updated_at = utcnow()
            if download.queue:
                download.queue.state = "paused" if pause else "pending"
            db.commit()
        finally:
            db.close()


_manager: DownloadManager | None = None
_manager_lock = threading.Lock()


def get_download_manager() -> DownloadManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = DownloadManager()
        return _manager


def reset_download_manager_for_tests(manager: DownloadManager | None = None) -> None:
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.stop()
        _manager = manager
