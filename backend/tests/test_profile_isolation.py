"""Per-profile data isolation (spec §5.3, §7).

Each profile has its own follows / progress / notifications / bookmarks /
collections. Cross-profile visibility is none — not between two profiles on one
account, and not between accounts.
"""

from __future__ import annotations

import pytest

from core.errors import AppError
from database.models import Collection, ProfileSeriesTag, UpdateNotification
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


# --- ownership: the unscoped bucket is not a wildcard ---------------------


def test_series_detail_is_404_when_the_profile_header_is_omitted(
    db_session, world, seed_follow
):
    """A service built with no profile (``X-Profile-Id`` absent — which
    ``resolve_profile_context`` leniently allows) must not reach the account's
    profile-owned rows. ``None`` is the unscoped bucket, not a wildcard."""
    row = seed_follow(world["u1"], world["a"], series_key="a-series")

    unscoped = _followed(db_session, world["u1"], None)
    for call in (
        lambda: unscoped.get_detail(row.id),
        lambda: unscoped.patch(row.id, notify=False),
        lambda: unscoped.unfollow(row.id),
    ):
        with pytest.raises(AppError) as excinfo:
            call()
        assert excinfo.value.status_code == 404

    db_session.refresh(row)
    assert row.notify  # untouched


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


def test_series_detail_progress_overlay_is_profile_scoped(
    db_session, world, seed_follow, seed_progress
):
    """Two profiles following the same series must not see one merged overlay
    (which resumes each of them at the other's page)."""
    a_follow = seed_follow(world["u1"], world["a"], series_key="shared")
    b_follow = seed_follow(world["u1"], world["b"], series_key="shared")
    seed_progress(
        world["u1"], world["a"], series_key="shared", chapter_key="ch-a", last_page=11
    )
    seed_progress(
        world["u1"], world["b"], series_key="shared", chapter_key="ch-b", last_page=44
    )

    a_overlay = _followed(db_session, world["u1"], world["a"]).get_detail(
        a_follow.id
    )["progress"]
    b_overlay = _followed(db_session, world["u1"], world["b"]).get_detail(
        b_follow.id
    )["progress"]

    assert set(a_overlay) == {"ch-a"} and a_overlay["ch-a"]["last_page"] == 11
    assert set(b_overlay) == {"ch-b"} and b_overlay["ch-b"]["last_page"] == 44


def test_continue_reading_strip_is_profile_scoped(
    db_session, world, seed_follow, seed_progress
):
    seed_follow(world["u1"], world["a"], series_key="a-series")
    seed_follow(world["u1"], world["b"], series_key="b-series")
    seed_progress(world["u1"], world["a"], series_key="a-series", chapter_key="ca")
    seed_progress(world["u1"], world["b"], series_key="b-series", chapter_key="cb")

    a_strip = _followed(db_session, world["u1"], world["a"]).continue_reading()
    b_strip = _followed(db_session, world["u1"], world["b"]).continue_reading()
    c_strip = _followed(db_session, world["u2"], world["c"]).continue_reading()

    assert [r["series_key"] for r in a_strip] == ["a-series"]
    assert [r["series_key"] for r in b_strip] == ["b-series"]
    assert c_strip == []


def test_continue_reading_strip_only_shows_series_this_profile_follows(
    db_session, world, seed_progress
):
    """Progress with no follow row for this profile is not a library entry."""
    seed_progress(world["u1"], world["a"], series_key="drive-by", chapter_key="c1")
    assert _followed(db_session, world["u1"], world["a"]).continue_reading() == []


def test_continue_reading_strip_honours_the_18plus_gate(
    db_session, make_user, make_profile, seed_follow, seed_progress
):
    """Reading ``chapter_progress`` directly bypassed the maturity gate: the
    strip is joined to ``followed_series`` precisely so the rating resolves."""
    user = make_user("gated")
    profile = make_profile(user.id, "Kid", mature_content_enabled=False)
    seed_follow(
        user.id, profile.id, series_key="adult-series", mature_override=True
    )
    seed_follow(user.id, profile.id, series_key="safe-series", mature_override=False)
    seed_progress(
        user.id, profile.id, series_key="adult-series", chapter_key="a1"
    )
    seed_progress(user.id, profile.id, series_key="safe-series", chapter_key="s1")

    strip = _followed(db_session, user.id, profile.id).continue_reading()
    assert [r["series_key"] for r in strip] == ["safe-series"]

    open_profile = make_profile(user.id, "Grown", mature_content_enabled=True)
    seed_follow(
        user.id, open_profile.id, series_key="adult-series", mature_override=True
    )
    seed_progress(
        user.id, open_profile.id, series_key="adult-series", chapter_key="a1"
    )
    open_strip = _followed(db_session, user.id, open_profile.id).continue_reading()
    assert [r["series_key"] for r in open_strip] == ["adult-series"]


# --- recently updated ----------------------------------------------------


def test_recently_updated_strip_is_profile_scoped(
    db_session, world, seed_follow
):
    """The home "recently updated" strip is a *library* view like any other.

    It reads ``followed_series`` directly with no join to lean on, so its
    ``_scope`` call is the only thing standing between one profile and the rest
    of the account's follows.
    """
    from core.time_utils import utcnow

    seed_follow(
        world["u1"], world["a"], series_key="a-series", last_checked_at=utcnow()
    )
    seed_follow(
        world["u1"], world["b"], series_key="b-series", last_checked_at=utcnow()
    )
    seed_follow(
        world["u2"], world["c"], series_key="c-series", last_checked_at=utcnow()
    )

    a = _followed(db_session, world["u1"], world["a"]).recently_updated()
    b = _followed(db_session, world["u1"], world["b"]).recently_updated()
    c = _followed(db_session, world["u2"], world["c"]).recently_updated()

    assert [r["series_key"] for r in a] == ["a-series"]
    assert [r["series_key"] for r in b] == ["b-series"]
    assert [r["series_key"] for r in c] == ["c-series"]


# --- statistics ---------------------------------------------------------


def test_statistics_completed_count_is_profile_scoped(
    db_session, world, seed_follow, seed_progress
):
    seed_follow(world["u1"], world["a"], series_key="a-series")
    seed_progress(
        world["u1"],
        world["a"],
        series_key="a-series",
        chapter_key="ca",
        is_completed=True,
    )
    for n in range(3):
        seed_progress(
            world["u1"],
            world["b"],
            series_key="b-series",
            chapter_key=f"cb{n}",
            is_completed=True,
        )

    a_stats = _followed(db_session, world["u1"], world["a"]).statistics()
    b_stats = _followed(db_session, world["u1"], world["b"]).statistics()
    assert a_stats["chapters_completed"] == 1
    assert b_stats["chapters_completed"] == 3


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

    # ...and a sibling cannot clear the badge it cannot see.
    notif_id = db_session.query(UpdateNotification).one().id
    for svc in (b_svc, c_svc):
        with pytest.raises(AppError) as excinfo:
            svc.mark_notification_read(notif_id)
        assert excinfo.value.status_code == 404
    assert a_svc.unread_count() == 1
    assert a_svc.mark_notification_read(notif_id)["is_read"] is True


# --- bookmarks --------------------------------------------------------


def test_bookmarks_isolated_across_profiles(db_session, world, seed_bookmark):
    seed_bookmark(world["u1"], world["a"], chapter_key="c1", page=4)

    a_bm = _progress(db_session, world["u1"], world["a"]).list_bookmarks()
    b_bm = _progress(db_session, world["u1"], world["b"]).list_bookmarks()
    c_bm = _progress(db_session, world["u2"], world["c"]).list_bookmarks()
    assert len(a_bm) == 1
    assert b_bm == []
    assert c_bm == []


def test_bookmarks_cannot_be_deleted_from_another_profile(
    db_session, world, seed_bookmark
):
    """``list_bookmarks`` is profile-scoped, so the delete has to be too — an
    id-only check let a profile delete a bookmark it could not see."""
    bookmark = seed_bookmark(world["u1"], world["a"], chapter_key="c1", page=4)

    for svc in (
        _progress(db_session, world["u1"], world["b"]),
        _progress(db_session, world["u2"], world["c"]),
        _progress(db_session, world["u1"], None),
    ):
        with pytest.raises(AppError) as excinfo:
            svc.delete_bookmark(bookmark.id)
        assert excinfo.value.status_code == 404

    owner = _progress(db_session, world["u1"], world["a"])
    assert len(owner.list_bookmarks()) == 1
    owner.delete_bookmark(bookmark.id)
    assert owner.list_bookmarks() == []


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


def test_collections_cannot_be_reached_by_id_from_another_profile(db_session, world):
    """Invisible in the listing was never enough: collection ids are small
    integers, so ``_owned_collection`` has to carry the profile predicate too
    or a sibling profile guesses one and deletes it."""
    col = Collection(user_id=world["u1"], profile_id=world["a"], name="Faves")
    db_session.add(col)
    db_session.commit()

    sibling = _followed(db_session, world["u1"], world["b"])
    stranger = _followed(db_session, world["u2"], world["c"])
    unscoped = _followed(db_session, world["u1"], None)
    for svc in (sibling, stranger, unscoped):
        for call in (
            lambda s=svc: s.get_collection(col.id),
            lambda s=svc: s.update_collection(col.id, name="Pwned"),
            lambda s=svc: s.delete_collection(col.id),
            lambda s=svc: s.add_series_to_collection(col.id, "mangadex", "x"),
        ):
            with pytest.raises(AppError) as excinfo:
                call()
            assert excinfo.value.status_code == 404

    db_session.refresh(col)
    assert col.name == "Faves"
    assert _followed(db_session, world["u1"], world["a"]).get_collection(col.id)[
        "name"
    ] == "Faves"


# --- tags --------------------------------------------------------------


def test_tags_are_isolated_across_profiles_and_accounts(db_session, world):
    a = _followed(db_session, world["u1"], world["a"])
    b = _followed(db_session, world["u1"], world["b"])
    c = _followed(db_session, world["u2"], world["c"])
    tag = a.create_tag(name="Peak")

    assert [t["name"] for t in a.list_tags()] == ["Peak"]
    assert b.list_tags() == []
    assert c.list_tags() == []

    # A colliding name is a *new* tag in another scope, never a handle on
    # somebody else's row.
    theirs = c.create_tag(name="peak")
    assert theirs["id"] != tag["id"]
    assert [t["id"] for t in c.list_tags()] == [theirs["id"]]

    # ...while within one scope the case-insensitive dedupe still holds.
    assert a.create_tag(name="PEAK")["id"] == tag["id"]


def test_deleting_a_tag_from_another_scope_is_404(db_session, world):
    """``DELETE /library/tags/{id}`` used to nuke a globally shared row and,
    through the association cascade, every account's use of it."""
    a = _followed(db_session, world["u1"], world["a"])
    tag = a.create_tag(name="Peak")
    a.add_tag_to_series("mangadex", "s1", tag["id"])

    for svc in (
        _followed(db_session, world["u1"], world["b"]),
        _followed(db_session, world["u2"], world["c"]),
    ):
        with pytest.raises(AppError) as excinfo:
            svc.delete_tag(tag["id"])
        assert excinfo.value.status_code == 404
        # ...and it cannot be attached to their series either.
        with pytest.raises(AppError) as excinfo:
            svc.add_tag_to_series("mangadex", "s1", tag["id"])
        assert excinfo.value.status_code == 404

    assert [t["id"] for t in a.list_tags()] == [tag["id"]]
    assert db_session.query(ProfileSeriesTag).count() == 1

    a.delete_tag(tag["id"])
    assert a.list_tags() == []


def test_tag_writes_need_an_active_profile(db_session, world):
    """``profile_id`` is NOT NULL on both tag tables, so the unscoped bucket
    has no row to address — a composite ``db.get()`` with a null key component
    is not a lookup, and the insert would be an IntegrityError 500."""
    unscoped = _followed(db_session, world["u1"], None)
    for call in (
        lambda: unscoped.create_tag(name="Peak"),
        lambda: unscoped.add_tag_to_series("mangadex", "s1", 1),
        lambda: unscoped.remove_tag_from_series("mangadex", "s1", 1),
    ):
        with pytest.raises(AppError) as excinfo:
            call()
        assert excinfo.value.status_code == 400
        assert excinfo.value.code == "profile_required"


# --- the unscoped bucket cannot write profile-owned rows ------------------


def test_profile_owned_writes_from_the_unscoped_bucket_are_a_clean_400(
    db_session, world
):
    """``profile_id`` is NOT NULL on every profile-owned table, but
    ``require_profile_context`` still lets an account that owns *no* profiles
    through as the unscoped bucket — and registration does not create one. Each
    of these writes was therefore an IntegrityError 500 for a fresh account;
    they now return the documented 400 the clients already handle."""
    library = _followed(db_session, world["u1"], None)
    progress = _progress(db_session, world["u1"], None)

    for call in (
        lambda: library.follow("mangadex", "s1"),
        lambda: library.create_collection(name="Faves"),
        lambda: progress.save_one(
            ProgressInput(source_id="mangadex", series_key="s1", chapter_key="c1")
        ),
        lambda: progress.add_bookmark(
            source_id="mangadex", series_key="s1", chapter_key="c1", page=2
        ),
        lambda: progress.record_session(
            source_id="mangadex",
            series_key="s1",
            chapter_key="c1",
            chapter_number=1.0,
            start_page=1,
            end_page=2,
        ),
    ):
        with pytest.raises(AppError) as excinfo:
            call()
        assert excinfo.value.status_code == 400
        assert excinfo.value.code == "profile_required"
