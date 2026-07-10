"""OCR pipeline manager, queue service, and background workers.

The pipeline is designed to mirror the download subsystem architecture so
engineers familiar with DownloadManager can reason about it immediately.

Production improvements:
- In-memory metrics collection (pages/sec, confidence, retry rate, engine breakdown)
- Exponential backoff for retries with jitter
- Per-page retry counter (independent of job-level retry)
- Queue depth limit to prevent memory bloat
- Structured logging with job/page context
- Error classification (transient vs permanent) for smarter retries
- Adaptive worker count based on recent success/failure rates
- Job-level processing time tracking
- Explicit image cleanup after each page to reduce memory pressure
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, joinedload

from core.time_utils import utcnow

from core.config import get_settings
from core.errors import AppError
from database.models import Chapter, ChapterText, OcrJob, Page, PageText
from database.session import SessionLocal
from services.ocr_engine import (
    OcrEngineNotAvailable,
    OcrError,
    OcrRecognitionError,
    get_ocr_engine,
)
from services.ocr_utils import resolve_page_image

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# In-memory metrics (reset on restart; lightweight, no DB writes)
# ------------------------------------------------------------------

@dataclass
class OcrMetrics:
    """Rolling in-memory metrics for the OCR pipeline."""

    jobs_started: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    pages_processed: int = 0
    pages_skipped: int = 0
    pages_retried: int = 0
    total_elapsed_ms: float = 0.0
    total_confidence: float = 0.0
    confidence_samples: int = 0
    retry_counts: list[int] = field(default_factory=list)
    engine_breakdown: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_page(
        self,
        *,
        elapsed_ms: float,
        confidence: float,
        engine: str,
        was_retry: bool = False,
        was_skipped: bool = False,
    ) -> None:
        with self._lock:
            if was_skipped:
                self.pages_skipped += 1
                return
            self.pages_processed += 1
            self.total_elapsed_ms += elapsed_ms
            self.total_confidence += confidence
            self.confidence_samples += 1
            self.engine_breakdown[engine] = self.engine_breakdown.get(engine, 0) + 1
            if was_retry:
                self.pages_retried += 1

    def record_job(self, *, completed: bool = False, failed: bool = False) -> None:
        with self._lock:
            self.jobs_started += 1
            if completed:
                self.jobs_completed += 1
            if failed:
                self.jobs_failed += 1

    def record_retry(self, retry_count: int) -> None:
        with self._lock:
            self.retry_counts.append(retry_count)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg_conf = (
                self.total_confidence / self.confidence_samples
                if self.confidence_samples
                else 0.0
            )
            avg_ms = (
                self.total_elapsed_ms / self.pages_processed
                if self.pages_processed
                else 0.0
            )
            pages_per_sec = (
                (self.pages_processed / (self.total_elapsed_ms / 1000))
                if self.total_elapsed_ms > 0
                else 0.0
            )
            retry_rate = (
                sum(self.retry_counts) / max(len(self.retry_counts), 1)
                if self.retry_counts
                else 0.0
            )
            return {
                "jobs": {
                    "started": self.jobs_started,
                    "completed": self.jobs_completed,
                    "failed": self.jobs_failed,
                },
                "pages": {
                    "processed": self.pages_processed,
                    "skipped": self.pages_skipped,
                    "retried": self.pages_retried,
                },
                "performance": {
                    "avg_page_ms": round(avg_ms, 2),
                    "pages_per_sec": round(pages_per_sec, 2),
                    "avg_confidence": round(avg_conf, 4),
                },
                "retry_rate": round(retry_rate, 2),
                "engine_breakdown": dict(self.engine_breakdown),
            }


# ------------------------------------------------------------------
# Pipeline manager
# ------------------------------------------------------------------

class OcrPipelineManager:
    """Background OCR worker pool with adaptive queue dispatch.

    Each worker thread creates its own ``OcrEngine`` instance to avoid
    thread-safety issues with underlying libraries (e.g. EasyOCR's Reader).
    """

    def __init__(
        self,
        *,
        max_workers: int | None = None,
        engine_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self._max_workers = max_workers or settings.ocr_workers
        self._engine_name = engine_name or settings.ocr_engine
        self._executor: ThreadPoolExecutor | None = None
        self._active_ids: set[int] = set()
        self._pool_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._started = False
        self._metrics = OcrMetrics()
        self._recent_failures = 0
        self._recent_successes = 0
        self._effective_workers = self._max_workers

    @property
    def metrics(self) -> OcrMetrics:
        return self._metrics

    def start(self) -> None:
        if self._started:
            return
        self._stop_event.clear()
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="ocr-worker",
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
        """Called by the API layer after new jobs are inserted."""
        if self._started:
            self._dispatch()

    def _recover_interrupted(self) -> None:
        """Re-queue jobs left in ``processing`` after an unclean shutdown."""
        db = SessionLocal()
        try:
            rows = db.query(OcrJob).filter(OcrJob.status == "processing").all()
            if not rows:
                return
            for row in rows:
                row.status = "queued"
                row.updated_at = utcnow()
            db.commit()
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _dispatch(self) -> None:
        if self._stop_event.is_set() or self._executor is None:
            return

        with self._pool_lock:
            available = self._effective_workers - len(self._active_ids)
            if available <= 0:
                return

        # Respect queue depth limit to avoid flooding memory
        queue_depth_limit = getattr(
            get_settings(), "ocr_queue_depth_limit", 1000
        )

        db = SessionLocal()
        try:
            total_queued = db.query(OcrJob).filter(
                OcrJob.status == "queued"
            ).count()
            if total_queued > queue_depth_limit:
                logger.warning(
                    "OCR queue depth %s exceeds limit %s; throttling dispatch",
                    total_queued,
                    queue_depth_limit,
                )
                return

            pending = (
                db.query(OcrJob)
                .filter(OcrJob.status == "queued")
                .order_by(OcrJob.created_at.asc())
                .limit(available)
                .all()
            )
            job_ids = [job.id for job in pending]
        finally:
            db.close()

        with self._pool_lock:
            for job_id in job_ids:
                if job_id in self._active_ids:
                    continue
                self._active_ids.add(job_id)
                self._executor.submit(self._run_job, job_id)

    def _run_job(self, job_id: int) -> None:
        try:
            self._process_job(job_id)
            self._recent_successes += 1
        except Exception:
            self._recent_failures += 1
            logger.exception("OCR job %s failed", job_id)
        finally:
            with self._pool_lock:
                self._active_ids.discard(job_id)
            self._tune_workers()
            if not self._stop_event.is_set():
                self._dispatch()

    def _tune_workers(self) -> None:
        """Adaptive worker count based on recent success/failure rate."""
        total = self._recent_failures + self._recent_successes
        if total < 5:
            return
        failure_rate = self._recent_failures / total
        if failure_rate > 0.35 and self._effective_workers > 1:
            self._effective_workers -= 1
            logger.info(
                "OCR worker count reduced to %s (failure rate %.0f%%)",
                self._effective_workers,
                failure_rate * 100,
            )
        elif failure_rate < 0.1 and self._effective_workers < self._max_workers:
            self._effective_workers += 1
            logger.info(
                "OCR worker count increased to %s (failure rate %.0f%%)",
                self._effective_workers,
                failure_rate * 100,
            )
        self._recent_failures = 0
        self._recent_successes = 0

    # ------------------------------------------------------------------
    # Per-page processing with retry
    # ------------------------------------------------------------------

    @staticmethod
    def _backoff_seconds(retry_count: int) -> float:
        """Exponential backoff with jitter: 1s, 2s, 4s, 8s... + random 0-1s."""
        base = getattr(get_settings(), "ocr_retry_backoff_base", 1.0)
        return (base * (2 ** retry_count)) + random.random()

    def _process_page(
        self,
        db: Session,
        job: OcrJob,
        page: Page,
        engine: Any,
    ) -> bool:
        """Process a single page. Returns True if successful, False if skipped.

        Raises OcrError on unrecoverable failure to trigger job-level retry
        or failure.
        """
        page_logger = logging.LoggerAdapter(
            logger, {"job_id": job.id, "page_id": page.id, "page_number": page.number}
        )

        # Check for existing result (incremental indexing)
        existing = (
            db.query(PageText)
            .filter(PageText.page_id == page.id)
            .first()
        )
        if existing is not None:
            page_logger.debug("Page already processed, skipping")
            self._metrics.record_page(
                elapsed_ms=0, confidence=0, engine=job.engine, was_skipped=True
            )
            return True

        # Resolve image
        try:
            image = resolve_page_image(page)
        except AppError as exc:
            page_logger.warning("Failed to resolve page image: %s", exc)
            return False

        # Run OCR with per-page retry
        page_retry_count = 0
        max_page_retries = getattr(get_settings(), "ocr_max_page_retries", 2)
        result = None

        while page_retry_count <= max_page_retries:
            try:
                result = engine.recognize(image)
                break
            except OcrEngineNotAvailable as exc:
                # Permanent failure — don't retry, mark job failed
                page_logger.error("OCR engine not available: %s", exc)
                raise
            except OcrRecognitionError as exc:
                page_logger.warning(
                    "OCR recognition failed (attempt %s/%s): %s",
                    page_retry_count + 1,
                    max_page_retries + 1,
                    exc,
                )
                if page_retry_count < max_page_retries:
                    page_retry_count += 1
                    time.sleep(self._backoff_seconds(page_retry_count))
                else:
                    raise
            finally:
                # Explicit cleanup to reduce memory pressure
                image.close()

        if result is None:
            return False

        # Store result
        page_text = PageText(
            page_id=page.id,
            text=result.text,
            confidence=result.confidence,
            boxes=json.dumps(result.boxes) if result.boxes else None,
            engine=job.engine,
        )
        db.add(page_text)
        db.commit()

        self._metrics.record_page(
            elapsed_ms=result.elapsed_ms,
            confidence=result.confidence,
            engine=job.engine,
            was_retry=page_retry_count > 0,
        )

        page_logger.debug(
            "Page OCR completed in %.1f ms (confidence %.2f)",
            result.elapsed_ms,
            result.confidence,
        )
        return True

    # ------------------------------------------------------------------
    # Per-job processing
    # ------------------------------------------------------------------

    def _process_job(self, job_id: int) -> None:
        job_logger = logging.LoggerAdapter(logger, {"job_id": job_id})
        engine = get_ocr_engine(self._engine_name)
        db = SessionLocal()
        job_started = time.perf_counter()
        try:
            job = db.query(OcrJob).filter(OcrJob.id == job_id).first()
            if job is None or job.status == "cancelled":
                return

            job.status = "processing"
            job.error = None
            job.updated_at = utcnow()
            db.commit()
            job_logger.info("Job started (engine=%s)", job.engine)

            chapter = (
                db.query(Chapter)
                .options(joinedload(Chapter.pages))
                .filter(Chapter.id == job.chapter_id)
                .first()
            )
            if chapter is None:
                raise RuntimeError("Chapter not found.")

            pages = sorted(chapter.pages, key=lambda p: p.number)
            job.pages_total = len(pages)
            db.commit()

            for index, page in enumerate(pages, start=1):
                if self._stop_event.is_set():
                    job.status = "queued"
                    job.updated_at = utcnow()
                    db.commit()
                    job_logger.info("Job re-queued (shutdown in progress)")
                    return

                success = self._process_page(db, job, page, engine)
                if success:
                    job.pages_done = index
                    job.progress = round((index / len(pages)) * 100, 2)
                    job.updated_at = utcnow()
                    db.commit()

            # Aggregate chapter-level text
            self._aggregate_chapter_text(db, chapter, self._engine_name)

            job.status = "completed"
            job.progress = 100.0
            job.error = None
            job.updated_at = utcnow()
            db.commit()

            elapsed = (time.perf_counter() - job_started) * 1000
            job_logger.info(
                "Job completed in %.1f ms (%s pages)", elapsed, job.pages_total
            )
            self._metrics.record_job(completed=True)

        except Exception as exc:
            db.rollback()
            job_logger.error("Job failed: %s", exc)
            self._metrics.record_job(failed=True)
            self._metrics.record_retry(job.retry_count if job else 0)
            self._set_failed(job_id, str(exc))
        finally:
            db.close()

    @staticmethod
    def _aggregate_chapter_text(
        db: Session, chapter: Chapter, engine_name: str
    ) -> None:
        """Aggregate all page texts into a single chapter text record."""
        page_text_rows = (
            db.query(PageText)
            .join(Page, PageText.page_id == Page.id)
            .filter(Page.chapter_id == chapter.id)
            .order_by(Page.number)
            .all()
        )

        full_text = "\n".join(pt.text or "" for pt in page_text_rows)
        word_count = len(full_text.split())

        chapter_text = (
            db.query(ChapterText)
            .filter(ChapterText.chapter_id == chapter.id)
            .first()
        )
        if chapter_text is not None:
            chapter_text.full_text = full_text
            chapter_text.word_count = word_count
            chapter_text.engine = engine_name
            chapter_text.updated_at = utcnow()
        else:
            chapter_text = ChapterText(
                chapter_id=chapter.id,
                full_text=full_text,
                word_count=word_count,
                engine=engine_name,
            )
            db.add(chapter_text)
        db.commit()

    @staticmethod
    def _set_failed(job_id: int, message: str) -> None:
        db = SessionLocal()
        try:
            job = db.query(OcrJob).filter(OcrJob.id == job_id).first()
            if job is not None:
                job.status = "failed"
                job.error = message
                job.updated_at = utcnow()
                db.commit()
        finally:
            db.close()


# ------------------------------------------------------------------
# Singleton manager
# ------------------------------------------------------------------

_ocr_manager: OcrPipelineManager | None = None
_ocr_manager_lock = threading.Lock()


def get_ocr_manager() -> OcrPipelineManager:
    """Return the process-wide OCR manager (lazy-initialised)."""
    global _ocr_manager
    with _ocr_manager_lock:
        if _ocr_manager is None:
            _ocr_manager = OcrPipelineManager()
        return _ocr_manager


def reset_ocr_manager_for_tests(
    manager: OcrPipelineManager | None = None,
) -> None:
    """Replace or clear the global manager.  Used by tests and conftest."""
    global _ocr_manager
    with _ocr_manager_lock:
        if _ocr_manager is not None:
            _ocr_manager.stop()
        _ocr_manager = manager


# ------------------------------------------------------------------
# API-facing service
# ------------------------------------------------------------------

class OcrJobService:
    """Queue, query, and control OCR jobs.  Stateless except for the DB session."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def queue_chapters(
        self,
        chapter_ids: list[int],
        *,
        engine: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Enqueue chapters for OCR processing."""
        settings = get_settings()
        queued: list[int] = []
        skipped: list[int] = []

        for chapter_id in chapter_ids:
            chapter = self._db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if chapter is None:
                skipped.append(chapter_id)
                continue

            if not force:
                existing = (
                    self._db.query(OcrJob)
                    .filter(OcrJob.chapter_id == chapter_id)
                    .filter(OcrJob.status.in_(("queued", "processing", "completed")))
                    .first()
                )
                if existing is not None:
                    skipped.append(chapter_id)
                    continue

            job = OcrJob(
                chapter_id=chapter_id,
                status="queued",
                engine=engine or settings.ocr_engine,
            )
            self._db.add(job)
            self._db.flush()
            queued.append(job.id)

        self._db.commit()
        if queued:
            get_ocr_manager().notify_change()
        return {"queued": queued, "skipped": skipped}

    def queue_series(
        self,
        series_id: int,
        *,
        engine: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Enqueue every chapter in a series for OCR."""
        chapters = (
            self._db.query(Chapter)
            .filter(Chapter.series_id == series_id)
            .all()
        )
        return self.queue_chapters(
            [c.id for c in chapters], engine=engine, force=force
        )

    def get_series_ocr_status(self, series_id: int) -> dict[str, Any]:
        """Return OCR status for all chapters in a series."""
        from sqlalchemy import exists

        chapters = (
            self._db.query(Chapter)
            .filter(Chapter.series_id == series_id)
            .order_by(Chapter.number)
            .all()
        )
        if not chapters:
            return {"series_id": series_id, "chapters": [], "summary": {}}

        chapter_ids = [c.id for c in chapters]

        texts = (
            self._db.query(ChapterText)
            .filter(ChapterText.chapter_id.in_(chapter_ids))
            .all()
        )
        text_map = {t.chapter_id: t for t in texts}

        jobs = (
            self._db.query(OcrJob)
            .filter(OcrJob.chapter_id.in_(chapter_ids))
            .filter(OcrJob.status.in_(("queued", "processing", "failed")))
            .all()
        )
        job_map = {j.chapter_id: j for j in jobs}

        items = []
        completed = 0
        processing = 0
        failed = 0
        for chapter in chapters:
            cid = chapter.id
            if cid in text_map:
                t = text_map[cid]
                items.append({
                    "chapter_id": cid,
                    "chapter_title": chapter.title,
                    "status": "completed",
                    "word_count": t.word_count,
                    "engine": t.engine,
                })
                completed += 1
            elif cid in job_map:
                j = job_map[cid]
                items.append({
                    "chapter_id": cid,
                    "chapter_title": chapter.title,
                    "status": j.status,
                    "progress": j.progress,
                    "engine": j.engine,
                })
                if j.status in ("queued", "processing"):
                    processing += 1
                elif j.status == "failed":
                    failed += 1
            else:
                items.append({
                    "chapter_id": cid,
                    "chapter_title": chapter.title,
                    "status": "not_started",
                })

        return {
            "series_id": series_id,
            "chapters": items,
            "summary": {
                "total": len(chapters),
                "completed": completed,
                "processing": processing,
                "failed": failed,
                "not_started": len(chapters) - completed - processing - failed,
            },
        }

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    def count_jobs(self, *, status: str | None = None) -> int:
        query = self._db.query(OcrJob)
        if status is not None:
            query = query.filter(OcrJob.status == status)
        return query.count()

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = self._db.query(OcrJob)
        if status is not None:
            query = query.filter(OcrJob.status == status)
        jobs = query.order_by(OcrJob.created_at.desc()).limit(limit).all()
        return [self._serialize_job(job) for job in jobs]

    def get_job(self, job_id: int) -> dict[str, Any]:
        job = self._db.query(OcrJob).filter(OcrJob.id == job_id).first()
        if job is None:
            raise AppError(
                "OCR job not found.",
                code="job_not_found",
                status_code=404,
            )
        return self._serialize_job(job)

    def retry_job(self, job_id: int) -> dict[str, Any]:
        job = self._db.query(OcrJob).filter(OcrJob.id == job_id).first()
        if job is None:
            raise AppError(
                "OCR job not found.",
                code="job_not_found",
                status_code=404,
            )
        if job.status not in ("failed", "cancelled"):
            raise AppError(
                "Only failed or cancelled jobs can be retried.",
                code="invalid_state",
                status_code=400,
            )
        job.status = "queued"
        job.retry_count += 1
        job.error = None
        job.updated_at = utcnow()
        self._db.commit()
        get_ocr_manager().notify_change()
        return self._serialize_job(job)

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        job = self._db.query(OcrJob).filter(OcrJob.id == job_id).first()
        if job is None:
            raise AppError(
                "OCR job not found.",
                code="job_not_found",
                status_code=404,
            )
        if job.status == "completed":
            raise AppError(
                "Completed jobs cannot be cancelled.",
                code="invalid_state",
                status_code=400,
            )
        job.status = "cancelled"
        job.updated_at = utcnow()
        self._db.commit()
        return self._serialize_job(job)

    # ------------------------------------------------------------------
    # Result retrieval
    # ------------------------------------------------------------------

    def queue_all_unprocessed(
        self,
        *,
        engine: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Queue all chapters that don't have completed OCR text."""
        from sqlalchemy import exists

        # Find chapters without chapter_text
        subquery = exists().where(ChapterText.chapter_id == Chapter.id)
        chapters = (
            self._db.query(Chapter)
            .filter(~subquery)
            .all()
        )
        return self.queue_chapters(
            [c.id for c in chapters], engine=engine, force=force
        )

    def get_chapter_text(self, chapter_id: int) -> dict[str, Any]:
        chapter_text = (
            self._db.query(ChapterText)
            .filter(ChapterText.chapter_id == chapter_id)
            .first()
        )
        if chapter_text is None:
            return {
                "chapter_id": chapter_id,
                "full_text": None,
                "word_count": 0,
                "engine": None,
            }
        return {
            "chapter_id": chapter_id,
            "full_text": chapter_text.full_text,
            "word_count": chapter_text.word_count,
            "language": chapter_text.language,
            "engine": chapter_text.engine,
            "created_at": chapter_text.created_at.isoformat(),
            "updated_at": chapter_text.updated_at.isoformat(),
        }

    def get_page_text(self, page_id: int) -> dict[str, Any]:
        page_text = (
            self._db.query(PageText)
            .filter(PageText.page_id == page_id)
            .first()
        )
        if page_text is None:
            return {
                "page_id": page_id,
                "text": None,
                "confidence": None,
                "engine": None,
                "boxes": None,
            }
        return {
            "page_id": page_id,
            "text": page_text.text,
            "confidence": page_text.confidence,
            "engine": page_text.engine,
            "boxes": page_text.boxes,
            "created_at": page_text.created_at.isoformat(),
            "updated_at": page_text.updated_at.isoformat(),
        }

    def get_metrics(self) -> dict[str, Any]:
        """Return live in-memory OCR metrics."""
        manager = get_ocr_manager()
        return manager.metrics.snapshot()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_job(job: OcrJob) -> dict[str, Any]:
        return {
            "id": job.id,
            "chapter_id": job.chapter_id,
            "status": job.status,
            "engine": job.engine,
            "progress": job.progress,
            "pages_done": job.pages_done,
            "pages_total": job.pages_total,
            "retry_count": job.retry_count,
            "error": job.error,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }
