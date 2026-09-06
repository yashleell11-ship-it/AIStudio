"""AUDIT (caches shard): where the retention sweep is actually run from.

The sweep itself is tested in ``test_audit_caches_orphans``; this pins the two
places that call it, because a policy nothing runs is not a policy. Boot covers
the deregistration case (a source leaves the build in a deploy, and the deploy
restarts the process); the daily pass on the existing update-scheduler thread
covers everything that accumulates while the process stays up.
"""

from __future__ import annotations

from types import SimpleNamespace

import main
from services import update_scheduler as sched
from services.update_scheduler import UpdateSchedulerManager


def test_boot_sweeps_the_caches(monkeypatch):
    """The lifespan runs it beside the other startup maintenance, so a source
    dropped by a deploy loses its rows on the boot that dropped it."""
    from fastapi.testclient import TestClient

    calls: list[str] = []
    monkeypatch.setattr(main, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(main, "prune_expired_sessions", lambda: calls.append("prune"))
    monkeypatch.setattr(main, "log_registration_posture", lambda: calls.append("log"))
    monkeypatch.setattr(
        main, "sweep_cache_retention_at_startup", lambda: calls.append("sweep")
    )

    with TestClient(main.create_app(run_migrations=True, run_workers=False)):
        pass

    assert "sweep" in calls, f"boot did not sweep the caches: {calls}"
    # After the schema is current: the sweep reads four tables migrations own.
    assert calls.index("sweep") > calls.index("init_db")


def test_a_failing_startup_sweep_does_not_stop_the_boot(monkeypatch):
    """Cache retention is maintenance. A cache table that cannot be swept must
    cost the deployment some disk, never the deployment itself."""
    def _boom(_db):
        raise RuntimeError("sweep exploded")

    monkeypatch.setattr(
        "services.source_cache_service.sweep_cache_retention", _boom
    )
    main.sweep_cache_retention_at_startup()  # must not raise


def test_the_scheduler_sweeps_once_a_day_not_once_a_tick(monkeypatch):
    """The scheduler thread wakes on the UPDATE interval, which can be five
    minutes; the sweep's own clock is what keeps it daily."""
    swept: list[int] = []
    monkeypatch.setattr(
        sched, "sweep_cache_retention", lambda db: swept.append(1) or {}
    )
    clock = {"t": 1000.0}
    # The module reads nothing else off ``time``, so a stub keeps the fake
    # clock out of every other thread running under this test.
    monkeypatch.setattr(sched, "time", SimpleNamespace(monotonic=lambda: clock["t"]))

    manager = UpdateSchedulerManager()
    monkeypatch.setattr(manager, "_scheduled_checks_enabled", lambda: False)

    manager._tick()
    assert len(swept) == 1

    clock["t"] += 60 * 60  # an hour later
    manager._tick()
    assert len(swept) == 1, "swept again inside the daily interval"

    clock["t"] += 24 * 60 * 60
    manager._tick()
    assert len(swept) == 2, "did not sweep after a day"


def test_disabled_update_checks_still_sweep(monkeypatch):
    """Turning update checks off is a statement about contacting upstreams, not
    about letting the disk fill."""
    swept: list[int] = []
    monkeypatch.setattr(
        sched, "sweep_cache_retention", lambda db: swept.append(1) or {}
    )
    manager = UpdateSchedulerManager()
    monkeypatch.setattr(manager, "_scheduled_checks_enabled", lambda: False)
    triggered: list[str] = []
    monkeypatch.setattr(
        manager, "trigger_check", lambda **kw: triggered.append(kw.get("trigger", ""))
    )

    manager._tick()

    assert swept == [1]
    assert triggered == []
