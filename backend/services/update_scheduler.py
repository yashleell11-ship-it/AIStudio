"""Background scheduler and worker for automatic update checks.

Mirrors the OCR/download subsystem lifecycle:
- ``UpdateScheduler`` sleeps between scheduled checks.
- ``UpdateWorkerManager`` runs checks on a thread pool without blocking the API.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from core.config import get_settings
from database.session import SessionLocal
from services.update_service import UpdateService, run_check_in_new_session

logger = logging.getLogger(__name__)

_update_manager: UpdateSchedulerManager | None = None
_update_manager_lock = threading.Lock()


class UpdateSchedulerManager:
    """Coordinates scheduled and on-demand update checks."""

    def __init__(self, *, max_workers: int | None = None) -> None:
        settings = get_settings()
        self._max_workers = max_workers or settings.update_workers
        self._executor: ThreadPoolExecutor | None = None
        self._scheduler_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._check_lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._stop_event.clear()
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="update-worker",
        )
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="update-scheduler",
            daemon=True,
        )
        self._started = True
        # Commit the singleton settings row BEFORE any thread reads it, so the
        # scheduler thread and the startup-check always see a committed row and
        # never race to INSERT it simultaneously.
        self._ensure_settings_row()
        self._scheduler_thread.start()
        self._maybe_run_startup_check()

    def stop(self) -> None:
        self._stop_event.set()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        if self._scheduler_thread is not None:
            self._scheduler_thread.join(timeout=2.0)
            self._scheduler_thread = None
        self._started = False

    @property
    def is_running(self) -> bool:
        """Whether the background worker pool is active (i.e. checks execute
        asynchronously). False in test/dev configurations started with
        ``run_workers=False``, where there is no worker thread to dispatch to."""
        return self._started

    def trigger_check(
        self,
        *,
        trigger: str = "manual",
        tracker_ids: list[int] | None = None,
    ) -> bool:
        """Queue an update check on the background worker pool.

        Returns False if the worker pool isn't running, or if a check is
        already in progress. Never blocks the caller — the check itself
        always executes on a worker thread, not the calling thread.
        """
        if not self._started or self._executor is None:
            return False
        if not self._check_lock.acquire(blocking=False):
            return False

        def _run() -> None:
            try:
                run_check_in_new_session(trigger=trigger, tracker_ids=tracker_ids)
            except Exception:
                logger.exception("Update check worker failed")
            finally:
                self._check_lock.release()

        self._executor.submit(_run)
        return True

    def _ensure_settings_row(self) -> None:
        """Create and commit the update_settings singleton before any thread touches it."""
        db = SessionLocal()
        try:
            UpdateService(db).get_global_settings()
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to initialize update_settings singleton")
        finally:
            db.close()

    def _maybe_run_startup_check(self) -> None:
        db = SessionLocal()
        try:
            service = UpdateService(db)
            settings = service.get_global_settings()
            if settings.check_on_startup and settings.enabled:
                self.trigger_check(trigger="startup")
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Startup update check failed to queue")
        finally:
            db.close()

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            interval_minutes = self._current_interval_minutes()
            sleep_seconds = max(interval_minutes * 60, 60)
            if self._stop_event.wait(timeout=sleep_seconds):
                break
            self._tick()

    def _tick(self) -> None:
        """One scheduler cycle: trigger a sweep iff scheduled checks are on.

        ``settings.enabled`` used to change only the sleep interval — the
        sweep itself ran regardless, so "disabled" still hammered every
        upstream on the config-default cadence (noted in audit findings
        1/5/6/7). Disabled now means no scheduled sweep; manual checks via
        ``POST /updates/check`` still work.
        """
        if self._scheduled_checks_enabled():
            self.trigger_check(trigger="scheduled")

    def _scheduled_checks_enabled(self) -> bool:
        db = SessionLocal()
        try:
            return bool(UpdateService(db).get_global_settings().enabled)
        except Exception:
            # Fail open: a transient DB error must not silently kill the
            # update feature.
            return True
        finally:
            db.close()

    def _current_interval_minutes(self) -> int:
        db = SessionLocal()
        try:
            service = UpdateService(db)
            settings = service.get_global_settings()
            if not settings.enabled:
                return get_settings().update_check_interval_minutes
            return max(settings.check_interval_minutes, 5)
        except Exception:
            return get_settings().update_check_interval_minutes
        finally:
            db.close()


def get_update_manager() -> UpdateSchedulerManager:
    global _update_manager
    with _update_manager_lock:
        if _update_manager is None:
            _update_manager = UpdateSchedulerManager()
        return _update_manager


def reset_update_manager_for_tests(manager: UpdateSchedulerManager | None = None) -> None:
    global _update_manager
    with _update_manager_lock:
        if _update_manager is not None:
            _update_manager.stop()
        _update_manager = manager
