"""AUDIT CONC-2: a manual per-series check may not interleave with the sweep.

``POST /updates/followed/{id}/check`` runs ``check_followed_by_id`` inline on
the request thread; the scheduled sweep runs ``run_check`` on a worker thread.
Neither takes the other's lock, so both used to load the same
``followed_series`` row, diff the same stale ``known_chapters`` and insert an
``update_notifications`` row for the same chapter — now a UNIQUE violation on
``uq_update_notifications_chapter`` that fails the whole run.

The diff-and-write half of a check is therefore one critical section per
followed series, and whoever loses the race re-reads what the winner wrote.
"""

from __future__ import annotations

import json
import threading

import pytest
from sqlalchemy import create_engine, func, select
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
from database.session import install_sqlite_pragmas
from services.update_service import UpdateService

SRC = "mangadex"


@pytest.fixture
def race_engine(tmp_path):
    """A file-backed engine two threads can hold separate sessions on.

    Not the suite's ``db_engine``: that one is a ``StaticPool``, i.e. a single
    shared connection, so two threads would serialise inside SQLAlchemy and the
    race could never be reproduced.
    """
    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}",
        connect_args={"check_same_thread": False},
    )
    install_sqlite_pragmas(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def race_factory(race_engine):
    return sessionmaker(bind=race_engine, autoflush=False, expire_on_commit=False)


def _seed(factory) -> tuple[int, int, int]:
    with factory() as s:
        user = User(username="racer", password_hash="x", is_admin=False, is_active=True)
        s.add(user)
        s.commit()
        profile = ReadingProfile(user_id=user.id, name="Main", sort_order=0)
        s.add(profile)
        s.add(UpdateSettings(id=1, enabled=True, notify_enabled=True))
        s.commit()
        row = FollowedSeries(
            user_id=user.id,
            profile_id=profile.id,
            source_id=SRC,
            series_key="series-1",
            title="Series One",
            notify=True,
            known_chapters=json.dumps(
                [{"key": "c1", "number": 1.0, "title": "Chapter 1"}]
            ),
        )
        s.add(row)
        s.commit()
        return user.id, profile.id, row.id


def test_manual_check_and_sweep_notify_a_new_chapter_once(
    race_factory, monkeypatch
):
    uid, pid, fid = _seed(race_factory)

    both_fetched = threading.Barrier(2, timeout=10)

    def fake_get_chapters(self, source_id, series_id):  # noqa: ARG001
        # Both checks have loaded the row (same stale snapshot) by the time they
        # reach the "network"; release them together so the diff halves collide.
        both_fetched.wait()
        return [
            {"id": "c1", "number": 1.0, "title": "Chapter 1"},
            {"id": "c2", "number": 2.0, "title": "Chapter 2"},
        ]

    monkeypatch.setattr(
        browse_service.BrowseService, "get_chapters", fake_get_chapters
    )

    errors: dict[str, BaseException] = {}
    runs: dict[str, dict] = {}

    def request_path() -> None:  # POST /updates/followed/{id}/check
        db = race_factory()
        try:
            runs["request"] = UpdateService(
                db, user_id=uid, profile_id=pid
            ).check_followed_by_id(fid)
        except BaseException as exc:  # noqa: BLE001
            errors["request"] = exc
        finally:
            db.close()

    def scheduled_sweep() -> None:  # run_check_in_new_session
        db = race_factory()
        try:
            runs["sweep"] = UpdateService(db, system=True).run_check(
                trigger="scheduled"
            )
        except BaseException as exc:  # noqa: BLE001
            errors["sweep"] = exc
        finally:
            db.close()

    threads = [
        threading.Thread(target=request_path),
        threading.Thread(target=scheduled_sweep),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert errors == {}, {k: repr(v)[:200] for k, v in errors.items()}
    assert [r["status"] for r in runs.values()] == ["completed", "completed"]

    with race_factory() as s:
        notified = s.execute(
            select(func.count())
            .select_from(UpdateNotification)
            .where(
                UpdateNotification.followed_series_id == fid,
                UpdateNotification.chapter_key == "c2",
            )
        ).scalar_one()
        snapshot = json.loads(
            s.get(FollowedSeries, fid).known_chapters
        )
    assert notified == 1, f"chapter c2 notified {notified} times"
    assert [c["key"] for c in snapshot] == ["c1", "c2"]


def test_loser_of_the_race_diffs_the_winners_snapshot(race_factory, monkeypatch):
    """The second checker must not count a chapter the first already recorded.

    Without the re-read inside the critical section the loser still holds the
    row it loaded before the wait, so it diffs against the pre-race snapshot and
    reports the chapter as new all over again — the number the run log and the
    ``/updates/runs`` UI show.
    """
    uid, pid, fid = _seed(race_factory)

    both_fetched = threading.Barrier(2, timeout=10)

    def fake_get_chapters(self, source_id, series_id):  # noqa: ARG001
        both_fetched.wait()
        return [
            {"id": "c1", "number": 1.0, "title": "Chapter 1"},
            {"id": "c2", "number": 2.0, "title": "Chapter 2"},
        ]

    monkeypatch.setattr(
        browse_service.BrowseService, "get_chapters", fake_get_chapters
    )

    found: list[int] = []
    lock = threading.Lock()

    def check(service_kwargs: dict) -> None:
        db = race_factory()
        try:
            result = UpdateService(db, **service_kwargs).run_check(
                trigger="manual", followed_ids=[fid]
            )
            with lock:
                found.append(result["new_chapters_found"])
        finally:
            db.close()

    threads = [
        threading.Thread(target=check, args=({"user_id": uid, "profile_id": pid},)),
        threading.Thread(target=check, args=({"system": True},)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert sorted(found) == [0, 1], f"new_chapters_found per run: {found}"
