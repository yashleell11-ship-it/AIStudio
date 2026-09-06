"""AUDIT (concurrency CONC-4): a progress write that cannot get the writer.

SQLite has ONE writer. ``busy_timeout`` (5 s, ``database/session.py``) already
buys a queued write that long, so an ``OperationalError: database is locked``
that reaches the route is a write that waited its whole budget behind the
update sweep or a 200-item offline flush. Today it falls through
``core.errors``'s catch-all as a 500 ``internal_error``: the reader's
keep-alive push is dropped, the client has nothing to distinguish "retry in a
moment" from "this request is broken", and every device that hits the same busy
window retries at whatever cadence it likes.

Expected instead: retry once (the lock is transient by definition), and if it
is still held, answer 503 ``db_busy`` with a ``Retry-After`` so the client backs
off. These tests are the finding until the fix lands.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from core.errors import AppError
from database.models import ChapterProgress
from database.session import get_db
from services.progress_service import ProgressInput, ProgressService


def _locked() -> OperationalError:
    """What pysqlite raises once ``busy_timeout`` is spent."""
    return OperationalError(
        "INSERT INTO chapter_progress ...",
        {},
        sqlite3.OperationalError("database is locked"),
    )


def _push(**kw) -> ProgressInput:
    base = dict(
        source_id="mangadex",
        series_key="solo-leveling",
        chapter_key="ch-1",
        chapter_number=1.0,
        last_page=5,
        page_count=20,
    )
    base.update(kw)
    return ProgressInput(**base)


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("busy-writer")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


def test_a_transient_lock_is_retried_and_the_write_still_lands(db_session, acct):
    uid, pid = acct
    real_flush = db_session.flush
    calls = {"n": 0}

    def flaky_flush(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _locked()
        return real_flush(*args, **kwargs)

    db_session.flush = flaky_flush
    svc = ProgressService(db_session, user_id=uid, profile_id=pid)
    saved = svc.save_one(_push())
    db_session.flush = real_flush

    assert saved["last_page"] == 5
    assert (
        db_session.query(ChapterProgress).filter_by(user_id=uid, profile_id=pid).count()
        == 1
    )


def test_a_lock_held_past_the_retry_is_a_503_not_a_500(db_session, acct):
    uid, pid = acct
    db_session.flush = lambda *a, **kw: (_ for _ in ()).throw(_locked())
    svc = ProgressService(db_session, user_id=uid, profile_id=pid)

    with pytest.raises(AppError) as caught:
        svc.save_one(_push())
    assert caught.value.status_code == 503
    assert caught.value.code == "db_busy"


def test_the_progress_route_answers_503_with_retry_after(
    app, client, as_user, acct, session_factory
):
    uid, pid = acct

    def locked_db():
        db = session_factory()
        db.flush = lambda *a, **kw: (_ for _ in ()).throw(_locked())
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = locked_db
    body = {
        "source_id": "mangadex",
        "series_key": "solo-leveling",
        "chapter_key": "ch-1",
        "chapter_number": 1.0,
        "last_page": 5,
        "page_count": 20,
    }
    r = client.post("/reader/progress", json=body, headers=as_user(uid, pid))

    assert r.status_code == 503, r.text
    assert r.json()["code"] == "db_busy"
    assert int(r.headers["Retry-After"]) >= 1


def test_the_batch_route_answers_503_with_retry_after(
    app, client, as_user, acct, session_factory
):
    """The offline flush needs the back-off signal even more than the live
    push: it is the endpoint that queues behind everything else."""
    uid, pid = acct

    def locked_db():
        db = session_factory()
        db.flush = lambda *a, **kw: (_ for _ in ()).throw(_locked())
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = locked_db
    body = [
        {
            "source_id": "mangadex",
            "series_key": "solo-leveling",
            "chapter_key": f"ch-{n}",
            "chapter_number": float(n),
            "last_page": 5,
            "page_count": 20,
        }
        for n in (1, 2)
    ]
    r = client.post("/reader/progress/batch", json=body, headers=as_user(uid, pid))

    assert r.status_code == 503, r.text
    assert r.json()["code"] == "db_busy"
    assert int(r.headers["Retry-After"]) >= 1
