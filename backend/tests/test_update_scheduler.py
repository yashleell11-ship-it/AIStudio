from __future__ import annotations

import threading
from unittest.mock import patch

from services.update_scheduler import UpdateSchedulerManager


def test_is_running_false_before_start():
    manager = UpdateSchedulerManager()
    assert manager.is_running is False


def test_trigger_check_returns_false_when_not_started():
    """No worker pool at all — trigger_check must not silently run inline;
    it reports False so the caller can decide how to handle it."""
    manager = UpdateSchedulerManager()
    assert manager.trigger_check(trigger="manual") is False


def test_trigger_check_runs_on_background_thread_not_caller():
    """The call to trigger_check must return immediately; the check itself
    runs on a worker thread, never blocking the calling thread."""
    manager = UpdateSchedulerManager(max_workers=2)
    started = threading.Event()
    calling_thread = threading.current_thread()
    observed_thread: dict[str, threading.Thread] = {}

    def _fake_run_check(*, trigger, tracker_ids=None):
        observed_thread["thread"] = threading.current_thread()
        started.set()
        return {"status": "completed"}

    with patch.object(UpdateSchedulerManager, "_maybe_run_startup_check"):
        manager.start()
    try:
        with patch("services.update_scheduler.run_check_in_new_session", side_effect=_fake_run_check):
            accepted = manager.trigger_check(trigger="manual")
            assert accepted is True
            assert started.wait(timeout=2.0), "background check never ran"
    finally:
        manager.stop()

    assert observed_thread["thread"] is not calling_thread


def test_trigger_check_returns_false_while_a_check_is_in_progress():
    """A second trigger_check call while one is already running must report
    busy (False) rather than blocking or running a second check inline."""
    manager = UpdateSchedulerManager(max_workers=2)
    release = threading.Event()
    entered = threading.Event()

    def _blocking_run_check(*, trigger, tracker_ids=None):
        entered.set()
        release.wait(timeout=5.0)
        return {"status": "completed"}

    with patch.object(UpdateSchedulerManager, "_maybe_run_startup_check"):
        manager.start()
    try:
        with patch("services.update_scheduler.run_check_in_new_session", side_effect=_blocking_run_check):
            first = manager.trigger_check(trigger="manual")
            assert first is True
            assert entered.wait(timeout=2.0), "first check never started"

            second = manager.trigger_check(trigger="manual")
            assert second is False, "expected busy (False) while a check is in progress"
    finally:
        release.set()
        manager.stop()


def test_trigger_check_forwards_tracker_ids():
    manager = UpdateSchedulerManager(max_workers=2)
    captured: dict[str, object] = {}
    done = threading.Event()

    def _fake_run_check(*, trigger, tracker_ids=None):
        captured["tracker_ids"] = tracker_ids
        done.set()
        return {"status": "completed"}

    with patch.object(UpdateSchedulerManager, "_maybe_run_startup_check"):
        manager.start()
    try:
        with patch("services.update_scheduler.run_check_in_new_session", side_effect=_fake_run_check):
            manager.trigger_check(trigger="manual", tracker_ids=[1, 2, 3])
            assert done.wait(timeout=2.0)
    finally:
        manager.stop()

    assert captured["tracker_ids"] == [1, 2, 3]
