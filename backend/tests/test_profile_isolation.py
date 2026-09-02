"""Per-profile data isolation (spec §5.3, §7).

Each profile has its own follows / progress / notifications / bookmarks /
collections. Cross-profile visibility is none — not between two profiles on one
account, and not between accounts.
"""

from __future__ import annotations

import pytest

from database.models import Collection, UpdateNotification
from services.followed_series_service import FollowedSeriesService
from services.progress_service import ProgressInput, ProgressService
from services.update_service import UpdateService
from tests._fakes import FakeBrowse


@pytest.fixture
def world(make_user, make_profile):
    """Account 1 with profiles A and B; account 2 with profile C."""
    u1 = make_user("acct1")
    u2 = make_user("acct2")
    a = make_profile(u1.id, "A")
    b = make_profile(u1.id, "B")
    c = make_profile(u2.id, "C")
    return {
        "u1": u1.id,
        "u2": u2.id,
        "a": a.id,
        "b": b.id,
        "c": c.id,
    }


def _followed(db, user_id, profile_id):
    return FollowedSeriesService(
        db, FakeBrowse(), user_id=user_id, profile_id=profile_id
    )


def _progress(db, user_id, profile_id):
    return ProgressService(db, user_id=user_id, profile_id=profile_id)


# --- follows --------------------------------------------------------------


def test_follows_isolated_across_profiles_and_accounts(db_session, world, seed_follow):
    seed_follow(world["u1"], world["a"], series_key="a-series", title="A Series")

    a_list = _followed(db_session, world["u1"], world["a"]).list_series()["items"]
    b_list = _followed(db_session, world["u1"], world["b"]).list_series()["items"]
    c_list = _followed(db_session, world["u2"], world["c"]).list_series()["items"]

    assert [s["series_key"] for s in a_list] == ["a-series"]
    assert b_list == []  # same account, other profile
    assert c_list == []  # other account


# --- progress ------------------------------------------------------------


def test_progress_isolated_across_profiles(db_session, world):
    _progress(db_session, world["u1"], world["a"]).save_one(
        ProgressInput(
            source_id="mangadex",
            series_key="s1",
            chapter_key="c1",
            chapter_number=1.0,
            last_page=9,
        )
    )
    b_hist = _progress(db_session, world["u1"], world["b"]).reading_history()
    c_hist = _progress(db_session, world["u2"], world["c"]).reading_history()
    assert b_hist == []
    assert c_hist == []
    a_hist = _progress(db_session, world["u1"], world["a"]).reading_history()
    assert len(a_hist) == 1 and a_hist[0]["last_page"] == 9


# --- notifications -----------------------------------------------------


def test_notifications_isolated_across_profiles(db_session, world, seed_follow):
    follow = seed_follow(world["u1"], world["a"], series_key="n-series")
    db_session.add(
        UpdateNotification(
            user_id=world["u1"],
            profile_id=world["a"],
            followed_series_id=follow.id,
            source_id="mangadex",
            series_key="n-series",
            chapter_key="c9",
            chapter_title="Chapter 9",
            chapter_number=9.0,
        )
    )
    db_session.commit()

    a_svc = UpdateService(db_session, user_id=world["u1"], profile_id=world["a"])
    b_svc = UpdateService(db_session, user_id=world["u1"], profile_id=world["b"])
    c_svc = UpdateService(db_session, user_id=world["u2"], profile_id=world["c"])

    assert a_svc.unread_count() == 1
    assert b_svc.unread_count() == 0
    assert c_svc.unread_count() == 0


# --- bookmarks --------------------------------------------------------


def test_bookmarks_isolated_across_profiles(db_session, world, seed_bookmark):
    seed_bookmark(world["u1"], world["a"], chapter_key="c1", page=4)

    a_bm = _progress(db_session, world["u1"], world["a"]).list_bookmarks()
    b_bm = _progress(db_session, world["u1"], world["b"]).list_bookmarks()
    c_bm = _progress(db_session, world["u2"], world["c"]).list_bookmarks()
    assert len(a_bm) == 1
    assert b_bm == []
    assert c_bm == []


# --- collections -----------------------------------------------------


def test_collections_isolated_across_profiles(db_session, world):
    db_session.add(
        Collection(user_id=world["u1"], profile_id=world["a"], name="Faves")
    )
    db_session.commit()

    a_cols = _followed(db_session, world["u1"], world["a"]).list_collections()
    b_cols = _followed(db_session, world["u1"], world["b"]).list_collections()
    c_cols = _followed(db_session, world["u2"], world["c"]).list_collections()
    assert [c["name"] for c in a_cols] == ["Faves"]
    assert b_cols == []
    assert c_cols == []
