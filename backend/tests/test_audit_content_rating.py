"""Audit (content-rating shard): the two guards inside ``core.content_rating``
that nothing was watching.

Both were proved unpinned by mutation. With the ``user_id`` ownership check
deleted from :func:`~core.content_rating.resolve_mature_gate`, and again with
``trim``/``coalesce`` deleted from
:func:`~core.content_rating.mature_rating_predicate`, every one of the 153
tests in the suite's mature-gate / profile / isolation files still passed --
not one failure appeared that was not already failing on the real code. The
module documents both behaviours at length and executes them on every gated
read; no test asserted either.

That is the specific danger of a guard living in the *single* resolution path:
it is the one function every surface trusts, so the day it stops guarding, all
of them stop guarding at once and silently.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from core.content_rating import (
    is_mature_rating,
    mature_rating_predicate,
    resolve_mature_gate,
)
from database.models import FollowedSeries


# ---------------------------------------------------------------------------
# resolve_mature_gate: the ownership check
# ---------------------------------------------------------------------------


@pytest.fixture
def two_households(make_user, make_profile):
    """Two accounts, and the profile whose gate the other one must not read."""
    alice = make_user("alice-gate")
    bob = make_user("bob-gate")
    return SimpleNamespace(
        alice=alice.id,
        bob=bob.id,
        bobs_open=make_profile(bob.id, "Grown", mature_content_enabled=True).id,
        bobs_shut=make_profile(bob.id, "Kid", mature_content_enabled=False, sort_order=1).id,
    )


def test_a_foreign_profile_id_does_not_open_the_gate(db_session, two_households):
    """Bob's 18+ profile answers for Bob, and for nobody else.

    The pair is the whole point: the same call, the same profile id, and the
    only difference is which account is asking. Assert only the first line and
    a function that ignored ``user_id`` entirely would still pass.
    """
    ids = two_households

    assert resolve_mature_gate(db_session, ids.bobs_open, ids.bob) is True
    assert resolve_mature_gate(db_session, ids.bobs_open, ids.alice) is False


def test_the_denial_is_about_ownership_not_about_the_caller(
    db_session, two_households, make_profile
):
    """Alice is refused Bob's open profile, not refused an open gate.

    Without this the test above passes for a function that has simply stopped
    resolving anything for Alice -- broken feature, closed gate, green suite.
    Alice's own 18+ profile has to keep working through the same call.
    """
    ids = two_households
    alices_open = make_profile(ids.alice, "Grown", mature_content_enabled=True).id

    assert resolve_mature_gate(db_session, alices_open, ids.alice) is True
    assert resolve_mature_gate(db_session, ids.bobs_open, ids.alice) is False


def test_an_unknown_profile_id_is_closed_the_same_way(db_session, two_households):
    """A profile that does not exist is the same answer as one owned elsewhere
    -- absence, never a 500 and never the caller's own profile."""
    ids = two_households

    assert resolve_mature_gate(db_session, 9_999_999, ids.alice) is False


def test_omitting_user_id_still_honours_the_profile(db_session, two_households):
    """The documented back-compat path stays open.

    ``user_id`` is optional because the pre-existing callers hand over a
    ProfileContext-validated id. A "fix" that made the ownership check
    mandatory would shut the gate for every one of them -- an 18+ profile
    losing its own library -- so pin that this is still a real two-argument
    call.
    """
    ids = two_households

    assert resolve_mature_gate(db_session, ids.bobs_open, None) is True


# ---------------------------------------------------------------------------
# mature_rating_predicate: the trim/coalesce regression fix
# ---------------------------------------------------------------------------

#: Every case the docstring on ``mature_rating_predicate`` names, plus the
#: ordinary ones. The whitespace and NULL rows are the regression itself: a
#: stored ``" adult"`` was mature to Python and safe to SQL, and ``IN`` against
#: NULL is NULL, so a negated filter dropped unrated rows instead of keeping
#: them.
#:
#: Padding is SPACES only, which is the padding the fix is written against:
#: SQLite's ``trim`` strips spaces where Python's ``strip`` strips all
#: whitespace, so a tab- or newline-padded rating would still divide the two
#: layers. Nothing can store one -- ``content_rating`` is only ever written
#: from ``rating_from_genres``, which returns an already-normalized vocabulary
#: term -- so asserting it here would pin a divergence the app cannot reach
#: rather than the rule it does.
RATING_SAMPLES = [
    "adult",
    "ADULT",
    " adult",
    "adult ",
    "  Erotica  ",
    "pornographic",
    "18+",
    "r-18",
    "safe",
    "suggestive",
    " safe ",
    "",
    "   ",
    None,
]


@pytest.fixture
def rated_follow(db_session, make_user, make_profile, seed_follow):
    """One followed row carrying whatever ``content_rating`` is asked for."""

    def _make(content_rating_value: str | None) -> FollowedSeries:
        user = make_user()
        profile = make_profile(user.id, "P")
        return seed_follow(
            user.id, profile.id, content_rating=content_rating_value
        )

    return _make


@pytest.mark.parametrize("stored", RATING_SAMPLES, ids=repr)
def test_the_sql_rule_answers_exactly_as_the_python_rule(
    db_session, rated_follow, stored
):
    """SQL and Python are one rule, value by value.

    ``is_mature_rating`` is the authority the predicate calls itself a mirror
    of, so it is the oracle here rather than a second hand-written expectation
    that could drift with it.
    """
    row = rated_follow(stored)

    selected = db_session.execute(
        select(FollowedSeries.id).where(
            mature_rating_predicate(FollowedSeries.content_rating)
        )
    ).scalars().all()

    assert (row.id in selected) is is_mature_rating(stored)


@pytest.mark.parametrize("stored", RATING_SAMPLES, ids=repr)
def test_negating_the_rule_keeps_every_row_it_does_not_match(
    db_session, rated_follow, stored
):
    """The half three-valued logic breaks, and the reason for ``coalesce``.

    A row is either matched by the rule or kept by its negation -- never
    neither. Without ``coalesce`` an unrated row answers NULL to both, so a
    ``NOT`` filter silently deletes exactly the rows the gate is supposed to
    keep showing (unknown is not adult; see ``resolve_series_rating``).
    """
    row = rated_follow(stored)

    kept = db_session.execute(
        select(FollowedSeries.id).where(
            ~mature_rating_predicate(FollowedSeries.content_rating)
        )
    ).scalars().all()

    assert (row.id in kept) is (not is_mature_rating(stored))
