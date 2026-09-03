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

from core.errors import AppError
from database.models import (
    SourceSeriesCache,
    UpdateNotification,
    UpdateRun,
)
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

    # Targeting an id is a *scoped* operation, so build the service the way a
    # request does. (This used to be an unscoped ``UpdateService(db_session)``,
    # which is exactly the shape that let one account target another's row.)
    UpdateService(
        db_session, user_id=user.id, profile_id=profile.id
    ).check_followed_by_id(a.id)

    db_session.refresh(a)
    db_session.refresh(b)
    assert len(json.loads(a.known_chapters)) == 2
    assert len(json.loads(b.known_chapters)) == 1  # untouched
    assert db_session.query(UpdateNotification).count() == 1


def test_targeted_sweep_rejects_an_id_outside_the_callers_scope(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    owner = make_user("owner")
    owner_profile = make_profile(owner.id, "Main")
    row = seed_follow(
        owner.id, owner_profile.id, source_id=SRC, series_key="a",
        known_chapters=_known(("c1", 1.0)), notify=True,
    )
    stub_connector["a"] = [_chap("c1", 1.0), _chap("c2", 2.0)]

    stranger = make_user("stranger")
    stranger_profile = make_profile(stranger.id, "Main")
    service = UpdateService(
        db_session, user_id=stranger.id, profile_id=stranger_profile.id
    )
    with pytest.raises(AppError) as excinfo:
        service.check_followed_by_id(row.id)
    assert excinfo.value.status_code == 404

    # Nothing was written — not the snapshot, and not a run-log entry.
    db_session.refresh(row)
    assert len(json.loads(row.known_chapters)) == 1
    assert row.last_checked_at is None
    assert db_session.query(UpdateRun).count() == 0


def test_system_sweep_may_still_target_ids_across_accounts(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    """The background worker has no request context and legitimately walks
    every account — ``system=True`` is how that stays available without
    reopening the request path."""
    users = []
    for name in ("sys-a", "sys-b"):
        user = make_user(name)
        profile = make_profile(user.id, "Main")
        users.append(
            seed_follow(
                user.id, profile.id, source_id=SRC, series_key=name,
                known_chapters=_known(("c1", 1.0)), notify=True,
            )
        )
    for row in users:
        stub_connector[row.series_key] = [_chap("c1", 1.0), _chap("c2", 2.0)]

    result = UpdateService(db_session, system=True).run_check(
        trigger="scheduled", followed_ids=[r.id for r in users]
    )
    assert result["series_checked"] == 2
    assert result["new_chapters_found"] == 2


def test_empty_live_list_never_erases_a_known_snapshot(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    """A connector that degrades to [] instead of raising used to overwrite
    known_chapters with []. The next run then had no baseline, so every chapter
    released in between never diffed as new — permanently un-notifiable."""
    user = make_user("degrader")
    profile = make_profile(user.id, "Main")
    row = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="flaky",
        known_chapters=_known(("c1", 1.0), ("c2", 2.0)), notify=True,
    )
    stub_connector["flaky"] = []  # soft failure: empty, not an exception

    UpdateService(db_session, system=True).run_check(trigger="scheduled")

    db_session.refresh(row)
    assert [c["key"] for c in json.loads(row.known_chapters)] == ["c1", "c2"]
    assert row.last_error  # the degradation is recorded, not swallowed

    # The next pass, once the source recovers, still sees c3 as new.
    stub_connector["flaky"] = [_chap("c1", 1.0), _chap("c2", 2.0), _chap("c3", 3.0)]
    result = UpdateService(db_session, system=True).run_check(trigger="scheduled")
    assert result["new_chapters_found"] == 1
    assert {n.chapter_key for n in db_session.query(UpdateNotification).all()} == {"c3"}
    db_session.refresh(row)
    assert row.last_error is None


def test_empty_live_list_still_seeds_a_row_that_has_no_snapshot(
    db_session, make_user, make_profile, seed_follow, stub_connector
):
    """The guard is about *losing* a baseline; a row that never had one is
    left alone either way, and must not be reported as an error."""
    user = make_user("emptyseed")
    profile = make_profile(user.id, "Main")
    row = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="nothing",
        known_chapters="[]", notify=True,
    )
    stub_connector["nothing"] = []

    UpdateService(db_session, system=True).run_check(trigger="scheduled")
    db_session.refresh(row)
    assert json.loads(row.known_chapters) == []
    assert row.last_error is None
