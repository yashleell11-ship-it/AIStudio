"""The ``user_id`` half of every ``_scope`` (audit TC-3).

``test_profile_isolation`` pins the *profile* half thoroughly, but every case
in it differs in ``user_id`` AND ``profile_id`` at once, so the profile
predicate alone satisfies all of them: deleting ``user_id`` from
``ProgressService._scope`` broke no test in the suite. Profile ids are globally
unique, which is why nothing leaked in practice — and exactly why nothing
failed either.

The account-level repro that would fail loudest cannot be built: ``profile_id``
is NOT NULL on ``chapter_progress`` / ``bookmarks`` / ``followed_series``, so
the unscoped bucket two profile-less accounts would share holds no rows at all
(a write from it is the documented ``400 profile_required``, not an insert).
What IS reachable is the mismatched pair — a service carrying one account's id
and another account's profile id. ``resolve_profile_context`` is what keeps
that pair off the wire today (a foreign ``X-Profile-Id`` resolves to ``None``),
which makes ``user_id`` the second line: the moment a new route, worker or
service factory builds a service without going through that ownership check,
it is the only predicate left standing between two accounts.
"""

from __future__ import annotations

import contextlib

import pytest
from sqlalchemy.exc import IntegrityError

from core.errors import AppError
from services.bookmark_service import BookmarkService
from services.followed_series_service import FollowedSeriesService
from services.progress_service import ProgressInput, ProgressService
from tests._fakes import FakeBrowse


@pytest.fixture
def two_accounts(make_user, make_profile):
    """One account that owns the profile and all the rows, and one that owns
    neither.

    The pins below build the intruder's services around the OWNER's profile id
    — the pair the ownership check exists to prevent — so the only thing left
    that can separate the two accounts is the ``user_id`` predicate.
    """
    u1 = make_user("owner")
    u2 = make_user("intruder")
    return {"owner": u1.id, "intruder": u2.id, "profile": make_profile(u1.id, "P").id}


def _intruder_progress(db, world):
    return ProgressService(
        db, FakeBrowse(), user_id=world["intruder"], profile_id=world["profile"]
    )


# --- progress -------------------------------------------------------------


def test_progress_reads_are_account_scoped_not_only_profile_scoped(
    db_session, two_accounts, seed_progress
):
    seed_progress(
        two_accounts["owner"],
        two_accounts["profile"],
        series_key="s1",
        chapter_key="c1",
        last_page=40,
    )
    intruder = _intruder_progress(db_session, two_accounts)

    assert intruder.reading_history() == []
    assert intruder.get_series_progress("mangadex", "s1") == []


def test_progress_write_cannot_merge_into_another_accounts_row(
    db_session, two_accounts, seed_progress
):
    """The furthest-wins merge looks the target row up through ``_scope``, so
    an unscoped-by-account lookup does not just *show* another account's
    position — it advances it. The push below is ahead of the owner's, which is
    what makes the merge bite."""
    owned = seed_progress(
        two_accounts["owner"],
        two_accounts["profile"],
        series_key="s1",
        chapter_key="c1",
        last_page=40,
    )

    # A correctly scoped push finds nothing and inserts the intruder's own
    # row; once the composite ``(user_id, profile_id)`` FK lands
    # (``test_audit_isolation_scope_consistency``) the schema refuses that pair
    # outright. Both are right answers, and neither is what this pins: what it
    # pins is that the OWNER's row is not what the push advances.
    with contextlib.suppress(IntegrityError):
        _intruder_progress(db_session, two_accounts).save_one(
            ProgressInput(
                source_id="mangadex",
                series_key="s1",
                chapter_key="c1",
                chapter_number=1.0,
                last_page=99,
            )
        )
    db_session.rollback()

    db_session.refresh(owned)
    assert owned.last_page == 40


# --- bookmarks ------------------------------------------------------------


def test_bookmarks_are_account_scoped_not_only_profile_scoped(
    db_session, two_accounts, seed_bookmark
):
    seed_bookmark(two_accounts["owner"], two_accounts["profile"], page=7)
    intruder = BookmarkService(
        db_session, user_id=two_accounts["intruder"], profile_id=two_accounts["profile"]
    )

    assert intruder.list_bookmarks() == []
    # Tombstone pulls read the same rows through the same scope, so a delta
    # sync must not become the way one account enumerates another's.
    assert intruder.list_bookmarks(include_deleted=True) == []


# --- followed series ------------------------------------------------------


def test_follows_are_account_scoped_not_only_profile_scoped(
    db_session, two_accounts, seed_follow, seed_progress
):
    row = seed_follow(
        two_accounts["owner"], two_accounts["profile"], series_key="s1", title="Owned"
    )
    seed_progress(
        two_accounts["owner"], two_accounts["profile"], series_key="s1", last_page=12
    )
    intruder = FollowedSeriesService(
        db_session,
        FakeBrowse(),
        user_id=two_accounts["intruder"],
        profile_id=two_accounts["profile"],
    )

    listing = intruder.list_series()
    assert listing["items"] == []
    assert listing["total"] == 0
    assert intruder.continue_reading() == []
    with pytest.raises(AppError) as excinfo:
        intruder.get_detail(row.id)
    assert excinfo.value.status_code == 404
