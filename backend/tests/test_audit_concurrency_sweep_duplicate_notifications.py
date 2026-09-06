"""AUDIT (concurrency): the request-path check bypasses the sweep lock.

``POST /updates/followed/{id}/check`` (routes/updates.py:141-143) runs
``UpdateService.check_followed_by_id`` synchronously on the REQUEST session and
never takes ``UpdateSchedulerManager._check_lock`` (update_scheduler.py:89),
so it can overlap the scheduled sweep on the same ``followed_series`` row.
Both sessions load the row, both diff the live list against the same stale
``known_chapters``, and both insert an ``update_notifications`` row for the
same chapter — ``update_notifications`` has no unique key on
(followed_series_id, chapter_key) (database/models.py:661-669).

Expected: exactly one notification per new chapter, however the two checks
interleave.
"""

from __future__ import annotations

import json
import threading

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

import services.browse_service as browse_service
from database.models import (
    Base,
    FollowedSeries,
    ReadingProfile,
    UpdateNotification,
    UpdateSettings,
    User,
)
from services.update_service import UpdateService


@pytest.fixture
def race_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_manual_check_overlapping_sweep_notifies_once(race_engine, monkeypatch):
    factory = sessionmaker(bind=race_engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        user = User(username="u", password_hash="x", is_admin=False, is_active=True)
        s.add(user)
        s.commit()
        prof = ReadingProfile(user_id=user.id, name="P", sort_order=0)
        s.add(prof)
        s.add(UpdateSettings(id=1, enabled=True, notify_enabled=True))
        s.commit()
        row = FollowedSeries(
            user_id=user.id,
            profile_id=prof.id,
            source_id="mangadex",
            series_key="series-1",
            title="S",
            notify=True,
            known_chapters=json.dumps([{"key": "c1", "number": 1, "title": "1"}]),
        )
        s.add(row)
        s.commit()
        uid, pid, fid = user.id, prof.id, row.id

    both_loaded = threading.Barrier(2, timeout=10)

    def fake_get_chapters(self, source_id, series_id):  # noqa: ARG001
        # Both checks have SELECTed the row (same known_chapters) by the time
        # they reach the "network"; let them proceed together.
        both_loaded.wait()
        return [
            {"id": "c1", "number": 1, "title": "1"},
            {"id": "c2", "number": 2, "title": "2"},  # the new chapter
        ]

    monkeypatch.setattr(browse_service.BrowseService, "get_chapters", fake_get_chapters)
    errors: dict[str, BaseException] = {}

    def request_path() -> None:  # POST /updates/followed/{id}/check
        db = factory()
        try:
            UpdateService(db, user_id=uid, profile_id=pid).check_followed_by_id(fid)
        except BaseException as exc:  # noqa: BLE001
            errors["request"] = exc
        finally:
            db.close()

    def scheduled_sweep() -> None:  # update_scheduler -> run_check_in_new_session
        db = factory()
        try:
            UpdateService(db, system=True).run_check(trigger="scheduled")
        except BaseException as exc:  # noqa: BLE001
            errors["sweep"] = exc
        finally:
            db.close()

    threads = [threading.Thread(target=request_path), threading.Thread(target=scheduled_sweep)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert errors == {}, {k: repr(v)[:200] for k, v in errors.items()}

    with factory() as s:
        n = s.execute(
            select(func.count())
            .select_from(UpdateNotification)
            .where(
                UpdateNotification.followed_series_id == fid,
                UpdateNotification.chapter_key == "c2",
            )
        ).scalar_one()
    assert n == 1, f"chapter c2 notified {n} times"
