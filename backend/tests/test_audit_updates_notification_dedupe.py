"""AUDIT IL-02: a chapter that already notified a follow must not notify again.

``update_notifications`` carries a UNIQUE on
(``followed_series_id``, ``chapter_key``) — ``uq_update_notifications_chapter``
in ``database/models.py``. The sweep therefore cannot simply INSERT whatever
the diff calls new: a connector that drops a chapter from its listing and lists
it again (pagination hiccup, partial parse) makes that chapter "new" a second
time, and the resulting IntegrityError lands on the per-row commit inside
``run_check`` — which fails the whole run, not just the one series.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from database.models import UpdateNotification
from services import browse_service
from services.update_service import UpdateService

SRC = "mangadex"


@pytest.fixture
def stub_connector(monkeypatch):
    by_series: dict[str, list[dict]] = {}

    def _fake_get_chapters(self, source_id, series_key):  # noqa: ARG001
        return list(by_series.get(series_key, []))

    monkeypatch.setattr(
        browse_service.BrowseService, "get_chapters", _fake_get_chapters
    )
    return by_series


def _chap(key, number):
    return {"id": key, "number": number, "title": f"Chapter {number}"}


def _known(*pairs):
    return json.dumps(
        [
            {"key": k, "number": n, "title": f"Chapter {n}", "published_at": None}
            for k, n in pairs
        ]
    )


def _count(db, followed_id, chapter_key) -> int:
    return db.execute(
        select(func.count())
        .select_from(UpdateNotification)
        .where(
            UpdateNotification.followed_series_id == followed_id,
            UpdateNotification.chapter_key == chapter_key,
        )
    ).scalar_one()


def test_relisted_chapter_is_a_noop_not_a_failed_run(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    user = make_user("relist")
    profile = make_profile(user.id, "Main")
    row = seed_follow(
        user.id,
        profile.id,
        source_id=SRC,
        series_key="flappy",
        known_chapters=_known(("c1", 1.0), ("c2", 2.0)),
        notify=True,
    )
    full = [_chap("c1", 1.0), _chap("c2", 2.0), _chap("c3", 3.0)]
    short = full[:2]

    service = UpdateService(db_session)
    stub_connector["flappy"] = full
    assert service.run_check(trigger="manual")["status"] == "completed"
    assert _count(db_session, row.id, "c3") == 1

    # c3 briefly unlisted (non-empty list, so the empty-list guard never fires)
    # and back again: the diff calls it new a second time.
    stub_connector["flappy"] = short
    service.run_check(trigger="manual")
    stub_connector["flappy"] = full
    result = service.run_check(trigger="manual")

    assert result["status"] == "completed", result["error"]
    assert _count(db_session, row.id, "c3") == 1


def test_repeated_chapter_in_one_listing_notifies_once(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    """One fetch, the same chapter id twice — the two inserts collide in a
    single flush, so the dedupe cannot be a per-run "what is already stored"
    check alone."""
    user = make_user("dupe-in-list")
    profile = make_profile(user.id, "Main")
    row = seed_follow(
        user.id,
        profile.id,
        source_id=SRC,
        series_key="doubled",
        known_chapters=_known(("c1", 1.0)),
        notify=True,
    )
    stub_connector["doubled"] = [
        _chap("c1", 1.0),
        _chap("c2", 2.0),
        _chap("c2", 2.0),
    ]

    result = UpdateService(db_session).run_check(trigger="manual")

    assert result["status"] == "completed", result["error"]
    assert _count(db_session, row.id, "c2") == 1
