"""``UpdateService.run_check`` connector-diff sweep (spec §4.5, §7).

Each pass diffs every ``followed_series.known_chapters`` snapshot against a live
connector chapter list:

* new chapters produce ``update_notifications`` rows — but only for rows whose
  ``notify`` flag is set;
* ``known_chapters`` + ``last_checked_at`` are refreshed on every swept row,
  ``notify`` or not (so turning ``notify`` on later does not backfill a storm);
* ``source_series_cache`` is written through from the fetched chapter list;
* a first-ever check (empty snapshot) seeds ``known_chapters`` without notifying.
"""

from __future__ import annotations

import json

import pytest

from database.models import SourceSeriesCache, UpdateNotification
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


def test_sweep_notifies_only_notify_true_rows_and_refreshes_both(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    user = make_user("sweeper")
    profile = make_profile(user.id, "Main")

    on = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="notify-on",
        known_chapters=_known(("c1", 1.0)), notify=True,
    )
    off = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="notify-off",
        known_chapters=_known(("c1", 1.0)), notify=False,
    )
    # both gain the same two new chapters upstream
    stub_connector["notify-on"] = [_chap("c1", 1.0), _chap("c2", 2.0), _chap("c3", 3.0)]
    stub_connector["notify-off"] = [_chap("c1", 1.0), _chap("c2", 2.0), _chap("c3", 3.0)]

    result = UpdateService(db_session).run_check(trigger="manual")
    assert result["status"] == "completed"
    assert result["series_checked"] == 2
    assert result["new_chapters_found"] == 4  # 2 per series

    notifs = db_session.query(UpdateNotification).all()
    assert {n.series_key for n in notifs} == {"notify-on"}
    assert {n.chapter_key for n in notifs} == {"c2", "c3"}

    # known_chapters + last_checked_at refreshed on BOTH rows
    for row in (on, off):
        db_session.refresh(row)
        assert [c["key"] for c in json.loads(row.known_chapters)] == ["c1", "c2", "c3"]
        assert row.last_checked_at is not None

    # source_series_cache written through for both
    cached = {
        c.series_key for c in db_session.query(SourceSeriesCache).all()
    }
    assert cached == {"notify-on", "notify-off"}
    cache_row = db_session.get(SourceSeriesCache, (SRC, "notify-on"))
    assert [c["key"] for c in json.loads(cache_row.chapters)] == ["c1", "c2", "c3"]


def test_first_ever_check_seeds_without_notifying(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    user = make_user("firstcheck")
    profile = make_profile(user.id, "Main")
    row = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="brand-new",
        known_chapters="[]", notify=True,
    )
    stub_connector["brand-new"] = [_chap("c1", 1.0), _chap("c2", 2.0)]

    result = UpdateService(db_session).run_check(trigger="manual")
    assert result["new_chapters_found"] == 0  # empty snapshot → seed, don't count

    assert db_session.query(UpdateNotification).count() == 0
    db_session.refresh(row)
    assert [c["key"] for c in json.loads(row.known_chapters)] == ["c1", "c2"]
    assert row.last_checked_at is not None


def test_sweep_can_target_a_single_followed_id(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    user = make_user("targeted")
    profile = make_profile(user.id, "Main")
    a = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="a",
        known_chapters=_known(("c1", 1.0)), notify=True,
    )
    b = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="b",
        known_chapters=_known(("c1", 1.0)), notify=True,
    )
    stub_connector["a"] = [_chap("c1", 1.0), _chap("c2", 2.0)]
    stub_connector["b"] = [_chap("c1", 1.0), _chap("c2", 2.0)]

    UpdateService(db_session).check_followed_by_id(a.id)

    db_session.refresh(a)
    db_session.refresh(b)
    assert len(json.loads(a.known_chapters)) == 2
    assert len(json.loads(b.known_chapters)) == 1  # untouched
    assert db_session.query(UpdateNotification).count() == 1
