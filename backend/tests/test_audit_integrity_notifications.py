"""AUDIT (integrity-lifecycle): ``update_notifications`` has no uniqueness on
``(followed_series_id, chapter_key)`` and the sweep can emit the same chapter
twice.

``UpdateService._check_one`` diffs the live chapter list against
``followed_series.known_chapters`` and then OVERWRITES the snapshot with the
live list. The "empty list" guard only protects against a connector returning
NOTHING; a connector that returns a *shorter but non-empty* list (pagination
hiccup, a chapter briefly unlisted, a partial parse) shrinks the snapshot, and
when the chapter reappears on the next pass it is "new" again and notifies
again. Nothing at the DB level stops the duplicate either.

Proposed fix (two layers): a UNIQUE index on
``update_notifications (followed_series_id, chapter_key)`` as the backstop, and
``_check_one`` skipping chapter keys that already have a notification row for
that ``followed_series_id`` (otherwise the UNIQUE would surface as an
IntegrityError at the per-row commit and fail the whole run).

These tests are EXPECTED TO FAIL until that exists.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

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
    return {"id": key, "number": number, "title": f"Chapter {number}",
            "release_date": f"2026-01-{int(number):02d}"}


def _known(*pairs):
    return json.dumps(
        [{"key": k, "number": n, "title": f"Chapter {n}", "published_at": None}
         for k, n in pairs]
    )


def _count_for(db, followed_id, chapter_key) -> int:
    return db.execute(
        select(func.count()).select_from(UpdateNotification).where(
            UpdateNotification.followed_series_id == followed_id,
            UpdateNotification.chapter_key == chapter_key,
        )
    ).scalar_one()


def test_flapping_chapter_list_notifies_the_same_chapter_twice(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    user = make_user("flap")
    profile = make_profile(user.id, "Main")
    row = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="flappy",
        known_chapters=_known(("c1", 1.0), ("c2", 2.0), ("c3", 3.0)),
        notify=True,
    )
    full = [_chap("c1", 1.0), _chap("c2", 2.0), _chap("c3", 3.0)]
    short = full[:2]  # c3 briefly unlisted — non-empty, so the guard does not fire

    # flap #1: c3 vanishes then returns -> one (legitimate-looking) notification
    stub_connector["flappy"] = short
    UpdateService(db_session).run_check(trigger="manual")
    stub_connector["flappy"] = full
    UpdateService(db_session).run_check(trigger="manual")
    assert _count_for(db_session, row.id, "c3") == 1

    # flap #2: exactly the same upstream behaviour -> the same chapter again
    stub_connector["flappy"] = short
    UpdateService(db_session).run_check(trigger="manual")
    stub_connector["flappy"] = full
    UpdateService(db_session).run_check(trigger="manual")

    n = _count_for(db_session, row.id, "c3")
    assert n == 1, (
        f"followed_series {row.id} now has {n} notification rows for chapter "
        "'c3': a connector that flaps between a short and a full chapter list "
        "re-notifies the same chapter on every recovery, and nothing dedupes."
    )


def test_db_rejects_duplicate_notification_for_same_chapter(
    db_session, make_user, make_profile, seed_follow
):
    user = make_user("dup")
    profile = make_profile(user.id, "Main")
    row = seed_follow(user.id, profile.id, source_id=SRC, series_key="dupe")

    def _notif():
        return UpdateNotification(
            user_id=user.id, profile_id=profile.id, followed_series_id=row.id,
            source_id=SRC, series_key="dupe", chapter_key="c9",
            chapter_title="Chapter 9", chapter_number=9.0,
        )

    db_session.add(_notif())
    db_session.commit()
    db_session.add(_notif())
    with pytest.raises(IntegrityError):
        db_session.commit()
