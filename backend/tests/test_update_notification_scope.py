"""Update notifications: (user, profile) scope + the 18+ gate (spec §4.5, §7).

An ``update_notifications`` row prints its ``series_key`` and ``chapter_title``,
so it is a disclosure of the series it names. The rows were correctly scoped to
the caller's own (user, profile), but nothing resolved the *rating*: a profile
that had shut the 18+ gate — the same profile that 404s that series in browse
and never sees it in its library or on the home strips — was still listed and
counted "new chapter" notifications for it, badge and all.

``followed_series_id`` is the FK the rating resolves through, the technique
``continue_reading`` already uses. The denial tests below are the ones that
would have caught the gap.

The unscoped tests at the bottom pin the other half: ``_notif_scope`` used to
drop its ``user_id`` predicate entirely when the service had no user, which
would have spanned every account. Unreachable through the router (``/updates/*``
requires a session), and pinned here so it stays that way.
"""

from __future__ import annotations

import pytest

from core.errors import AppError
from database.models import ReadingProfile, UpdateNotification
from services.update_service import UpdateService

SRC = "mangadex"
#: An installed connector that is adult by nature, so a follow carrying no
#: rating signal of its own still resolves mature through the source.
MATURE_SRC = "nhentai"


@pytest.fixture
def household(make_user, make_profile):
    """One account, two profiles: the gate is the only difference between them."""
    user = make_user("household")
    return {
        "user": user.id,
        "kid": make_profile(user.id, "Kid", mature_content_enabled=False).id,
        "grown": make_profile(
            user.id, "Grown", mature_content_enabled=True, sort_order=1
        ).id,
    }


def _svc(db, user_id, profile_id):
    return UpdateService(db, user_id=user_id, profile_id=profile_id)


def _notify(db, follow, *, chapter_key="c9", is_read=False):
    row = UpdateNotification(
        user_id=follow.user_id,
        profile_id=follow.profile_id,
        followed_series_id=follow.id,
        source_id=follow.source_id,
        series_key=follow.series_key,
        chapter_key=chapter_key,
        chapter_title=f"Chapter {chapter_key}",
        chapter_number=None,
        is_read=is_read,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- the gate, per signal -------------------------------------------------


@pytest.mark.parametrize(
    "source_id,follow_kwargs",
    [
        # 1. the user said so explicitly
        (SRC, {"mature_override": True}),
        # 2. the rating captured from the connector's genres at follow time
        (SRC, {"content_rating": "adult"}),
        # 3. the source is adult by nature and there is no other signal
        (MATURE_SRC, {}),
    ],
    ids=["override", "captured-rating", "mature-source"],
)
def test_a_shut_gate_hides_its_own_mature_notifications(
    db_session, household, seed_follow, source_id, follow_kwargs
):
    """All three ``resolve_tracker_rating`` signals, not just the override.

    The notification is the profile's own row — this is not a cross-profile
    leak — but "new chapter of <mature series>" is exactly what a shut gate is
    supposed to withhold.
    """
    follow = seed_follow(
        household["user"],
        household["kid"],
        source_id=source_id,
        series_key="adult-series",
        **follow_kwargs,
    )
    _notify(db_session, follow)

    kid = _svc(db_session, household["user"], household["kid"])
    assert kid.list_notifications() == []
    assert kid.count_notifications() == 0
    assert kid.unread_count() == 0


def test_the_gate_is_per_profile_not_per_instance(
    db_session, household, seed_follow, monkeypatch
):
    """Two profiles on one account, differing only in their own toggle.

    The instance-wide ``Settings.mature_content_enabled`` is forced ON
    underneath, so this also fails against a ``get_settings()`` gate in the
    service layer — reading the global value there is what made the in-app
    toggle inert once before.
    """
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "mature_content_enabled", True)

    kid_follow = seed_follow(
        household["user"],
        household["kid"],
        series_key="adult-series",
        mature_override=True,
    )
    grown_follow = seed_follow(
        household["user"],
        household["grown"],
        series_key="adult-series",
        mature_override=True,
    )
    _notify(db_session, kid_follow)
    _notify(db_session, grown_follow)

    assert _svc(db_session, household["user"], household["kid"]).unread_count() == 0
    assert _svc(db_session, household["user"], household["grown"]).unread_count() == 1


def test_a_safe_series_is_untouched_by_a_shut_gate(
    db_session, household, seed_follow
):
    """The gate hides mature rows and nothing else.

    ``mature_override=False`` is a positive "not adult"; a follow with no
    rating signal at all resolves *unknown*, which is deliberately not folded
    into mature — see ``resolve_tracker_rating``.
    """
    safe = seed_follow(
        household["user"],
        household["kid"],
        series_key="safe-series",
        mature_override=False,
    )
    unknown = seed_follow(
        household["user"], household["kid"], series_key="unrated-series"
    )
    _notify(db_session, safe, chapter_key="s1")
    _notify(db_session, unknown, chapter_key="u1")

    kid = _svc(db_session, household["user"], household["kid"])
    assert {n["chapter_key"] for n in kid.list_notifications()} == {"s1", "u1"}
    assert kid.count_notifications() == 2


# --- the count and the listing agree -------------------------------------


def test_the_badge_counts_exactly_what_the_listing_returns(
    db_session, household, seed_follow
):
    """A count over the ungated set is its own disclosure, and it strands the
    client on a badge that never clears however much the user reads."""
    adult = seed_follow(
        household["user"],
        household["kid"],
        series_key="adult-series",
        mature_override=True,
    )
    safe = seed_follow(
        household["user"],
        household["kid"],
        series_key="safe-series",
        mature_override=False,
    )
    for n in range(3):
        _notify(db_session, adult, chapter_key=f"a{n}")
    _notify(db_session, safe, chapter_key="s1")

    kid = _svc(db_session, household["user"], household["kid"])
    assert kid.unread_count() == len(kid.list_notifications(unread_only=True)) == 1


def test_hidden_rows_do_not_consume_the_page(db_session, household, seed_follow):
    """The gate is applied in SQL, so withheld rows never eat limit slots —
    a page of mature notifications must not come back empty while visible ones
    wait behind it."""
    adult = seed_follow(
        household["user"],
        household["kid"],
        series_key="adult-series",
        mature_override=True,
    )
    safe = seed_follow(
        household["user"],
        household["kid"],
        series_key="safe-series",
        mature_override=False,
    )
    for n in range(5):
        _notify(db_session, adult, chapter_key=f"a{n}")
    _notify(db_session, safe, chapter_key="s1")

    got = _svc(db_session, household["user"], household["kid"]).list_notifications(
        limit=2
    )
    assert [n["chapter_key"] for n in got] == ["s1"]


# --- the write paths agree with the listing ------------------------------


def test_a_hidden_notification_is_not_addressable(
    db_session, household, seed_follow
):
    """404, not 403: withheld is indistinguishable from absent, so the status
    code cannot be used to confirm the notification exists."""
    follow = seed_follow(
        household["user"],
        household["kid"],
        series_key="adult-series",
        mature_override=True,
    )
    hidden = _notify(db_session, follow)

    with pytest.raises(AppError) as excinfo:
        _svc(db_session, household["user"], household["kid"]).mark_notification_read(
            hidden.id
        )
    assert excinfo.value.status_code == 404
    db_session.refresh(hidden)
    assert not hidden.is_read


def test_mark_all_read_never_consumes_a_hidden_notification(
    db_session, household, seed_follow
):
    """Otherwise the profile silently burns its own mature notifications: turn
    the gate back on and every chapter it missed is already marked seen."""
    adult = seed_follow(
        household["user"],
        household["kid"],
        series_key="adult-series",
        mature_override=True,
    )
    safe = seed_follow(
        household["user"],
        household["kid"],
        series_key="safe-series",
        mature_override=False,
    )
    hidden = _notify(db_session, adult, chapter_key="a1")
    _notify(db_session, safe, chapter_key="s1")

    assert _svc(
        db_session, household["user"], household["kid"]
    ).mark_all_notifications_read() == {"updated": 1}
    db_session.refresh(hidden)
    assert not hidden.is_read

    # ...so it is still waiting when the profile opens its own gate.
    profile = db_session.get(ReadingProfile, household["kid"])
    profile.mature_content_enabled = True
    db_session.commit()
    reopened = _svc(db_session, household["user"], household["kid"])
    assert reopened.unread_count() == 1
    assert [
        n["chapter_key"] for n in reopened.list_notifications(unread_only=True)
    ] == ["a1"]


# --- an unscoped service sees nothing (the latent failure) ----------------


def test_an_unscoped_service_lists_nobodys_notifications(
    db_session, household, make_user, make_profile, seed_follow
):
    """``_notif_scope`` skipped its ``user_id`` predicate when the service had
    no user, so an unscoped read spanned **every account**. Its siblings
    (``_followed_scope``, ``progress_service._scope``) apply theirs
    unconditionally and answer with nothing; this one now does too."""
    _notify(
        db_session,
        seed_follow(household["user"], household["kid"], series_key="one"),
        chapter_key="c1",
    )
    other = make_user("stranger")
    other_profile = make_profile(other.id, "Main")
    _notify(
        db_session,
        seed_follow(other.id, other_profile.id, series_key="two"),
        chapter_key="c2",
    )
    assert db_session.query(UpdateNotification).count() == 2

    unscoped = UpdateService(db_session)
    assert unscoped.list_notifications() == []
    assert unscoped.count_notifications() == 0
    assert unscoped.unread_count() == 0


def test_an_unscoped_service_cannot_mark_anything_read(
    db_session, household, seed_follow
):
    row = _notify(
        db_session,
        seed_follow(household["user"], household["kid"], series_key="one"),
    )
    unscoped = UpdateService(db_session)

    with pytest.raises(AppError) as excinfo:
        unscoped.mark_notification_read(row.id)
    assert excinfo.value.status_code == 404
    assert unscoped.mark_all_notifications_read() == {"updated": 0}
    db_session.refresh(row)
    assert not row.is_read


# --- HTTP surface ---------------------------------------------------------


def test_http_notifications_and_badge_honour_the_gate(
    client, as_user, db_session, household, seed_follow
):
    adult = seed_follow(
        household["user"],
        household["kid"],
        series_key="adult-series",
        mature_override=True,
    )
    safe = seed_follow(
        household["user"],
        household["kid"],
        series_key="safe-series",
        mature_override=False,
    )
    hidden = _notify(db_session, adult, chapter_key="a1")
    _notify(db_session, safe, chapter_key="s1")

    headers = as_user(household["user"], household["kid"])
    listing = client.get("/updates/notifications", headers=headers)
    assert listing.status_code == 200, listing.text
    assert [n["chapter_key"] for n in listing.json()] == ["s1"]
    # The list-total header feeds the same badge, so it is gated too.
    assert listing.headers["X-Total-Count"] == "1"

    badge = client.get("/updates/notifications/unread-count", headers=headers)
    assert badge.json() == {"count": 1}

    assert (
        client.patch(
            f"/updates/notifications/{hidden.id}/read", headers=headers
        ).status_code
        == 404
    )


def test_http_the_same_notification_is_visible_to_an_open_profile(
    client, as_user, db_session, household, seed_follow
):
    """The mirror image: the gate withholds, it does not delete."""
    follow = seed_follow(
        household["user"],
        household["grown"],
        series_key="adult-series",
        mature_override=True,
    )
    _notify(db_session, follow, chapter_key="a1")

    headers = as_user(household["user"], household["grown"])
    got = client.get("/updates/notifications", headers=headers).json()
    assert [n["chapter_key"] for n in got] == ["a1"]
