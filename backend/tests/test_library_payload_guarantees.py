"""The guarantees the library list/detail payload optimisation rests on.

The 2026-09-04 performance pass changed *what these endpoints return*, not just
how fast they return it:

* ``known_chapters`` — the series' whole chapter list — was dropped from every
  **list** payload (832 KB per 40-row page, of which ~830 KB was that array)
  while ``chapter_count`` stayed. The safety argument is entirely "the detail
  endpoint, ``follow`` and ``patch`` still send it, so nothing that had the
  data loses it", and nothing asserted that.
* ``continue_reading`` moved its "latest unfinished chapter per series" collapse
  from a Python loop into a SQL window function. Which chapter you resume on is
  the whole point of the strip, and no test pinned it.
* ``list_collections`` stopped counting members with ``len(row.series)`` and
  started counting them with a ``GROUP BY``.

Each test here was written because deliberately breaking the corresponding line
left the suite green.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from core.time_utils import utcnow
from services.followed_series_service import FollowedSeriesService
from tests._fakes import FakeBrowse

CHAPTERS = json.dumps(
    [{"key": f"ch-{n}", "number": float(n), "title": f"Chapter {n}"} for n in range(1, 6)]
)


@pytest.fixture
def owner(make_user, make_profile):
    user = make_user("payload-owner")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


def _svc(db, user_id, profile_id, browse=None):
    return FollowedSeriesService(
        db, browse or FakeBrowse(), user_id=user_id, profile_id=profile_id
    )


# --- known_chapters: absent from lists, present on detail -----------------


def test_the_series_list_omits_known_chapters_but_keeps_the_count(
    db_session, owner, seed_follow
):
    user_id, profile_id = owner
    seed_follow(user_id, profile_id, series_key="s1", known_chapters=CHAPTERS)

    item = _svc(db_session, user_id, profile_id).list_series()["items"][0]

    assert "known_chapters" not in item
    assert item["chapter_count"] == 5


def test_the_detail_payload_still_carries_known_chapters(
    db_session, owner, seed_follow
):
    """The list payload may drop the array only because the detail keeps it."""
    user_id, profile_id = owner
    row = seed_follow(user_id, profile_id, series_key="s1", known_chapters=CHAPTERS)

    detail = _svc(db_session, user_id, profile_id).get_detail(row.id)

    assert [c["key"] for c in detail["known_chapters"]] == [
        "ch-1", "ch-2", "ch-3", "ch-4", "ch-5"
    ]
    assert detail["chapter_count"] == 5


def test_patch_still_returns_known_chapters(db_session, owner, seed_follow):
    """The web client merges this response over its cached detail entry, so a
    patch that dropped the array would blank a loaded detail screen."""
    user_id, profile_id = owner
    row = seed_follow(user_id, profile_id, series_key="s1", known_chapters=CHAPTERS)

    patched = _svc(db_session, user_id, profile_id).patch(row.id, is_favorite=True)

    assert len(patched["known_chapters"]) == 5


def test_recently_updated_omits_known_chapters_but_keeps_the_count(
    db_session, owner, seed_follow
):
    user_id, profile_id = owner
    seed_follow(
        user_id,
        profile_id,
        series_key="s1",
        known_chapters=CHAPTERS,
        last_checked_at=utcnow(),
    )

    item = _svc(db_session, user_id, profile_id).recently_updated()[0]

    assert "known_chapters" not in item
    assert item["chapter_count"] == 5


# --- continue_reading picks the RIGHT chapter -----------------------------


def test_continue_reading_resumes_the_most_recently_read_chapter(
    db_session, owner, seed_follow, seed_progress
):
    """One row per series, and it must be the *newest* unfinished chapter.

    The collapse is a ``row_number()`` window ordered ``last_read_at DESC,
    id DESC``. Ordered the other way it still returns one row per series and
    still returns the series in the right order — it just resumes the reader on
    a chapter he finished with days ago.
    """
    user_id, profile_id = owner
    now = utcnow()
    seed_follow(user_id, profile_id, series_key="s1")
    seed_progress(
        user_id, profile_id, series_key="s1", chapter_key="ch-1",
        chapter_number=1.0, last_read_at=now - timedelta(days=3),
    )
    seed_progress(
        user_id, profile_id, series_key="s1", chapter_key="ch-4",
        chapter_number=4.0, last_read_at=now - timedelta(minutes=5),
    )
    seed_progress(
        user_id, profile_id, series_key="s1", chapter_key="ch-2",
        chapter_number=2.0, last_read_at=now - timedelta(days=1),
    )

    strip = _svc(db_session, user_id, profile_id).continue_reading()

    assert [(r["series_key"], r["chapter_key"]) for r in strip] == [("s1", "ch-4")]


def test_continue_reading_orders_series_by_how_recently_they_were_read(
    db_session, owner, seed_follow, seed_progress
):
    user_id, profile_id = owner
    now = utcnow()
    for key, minutes in (("old", 600), ("mid", 60), ("new", 1)):
        seed_follow(user_id, profile_id, series_key=key)
        seed_progress(
            user_id, profile_id, series_key=key, chapter_key=f"{key}-c1",
            last_read_at=now - timedelta(minutes=minutes),
        )

    strip = _svc(db_session, user_id, profile_id).continue_reading()

    assert [r["series_key"] for r in strip] == ["new", "mid", "old"]


def test_continue_reading_skips_completed_chapters(
    db_session, owner, seed_follow, seed_progress
):
    user_id, profile_id = owner
    now = utcnow()
    seed_follow(user_id, profile_id, series_key="s1")
    seed_progress(
        user_id, profile_id, series_key="s1", chapter_key="ch-1",
        last_read_at=now - timedelta(days=1),
    )
    seed_progress(
        user_id, profile_id, series_key="s1", chapter_key="ch-2",
        last_read_at=now, is_completed=True,
    )

    strip = _svc(db_session, user_id, profile_id).continue_reading()

    assert [r["chapter_key"] for r in strip] == ["ch-1"]


def test_continue_reading_honours_its_limit(
    db_session, owner, seed_follow, seed_progress
):
    user_id, profile_id = owner
    now = utcnow()
    for n in range(6):
        seed_follow(user_id, profile_id, series_key=f"s{n}")
        seed_progress(
            user_id, profile_id, series_key=f"s{n}", chapter_key="c1",
            last_read_at=now - timedelta(minutes=n),
        )

    strip = _svc(db_session, user_id, profile_id).continue_reading(limit=3)

    assert [r["series_key"] for r in strip] == ["s0", "s1", "s2"]


# --- collection membership counts ----------------------------------------


def test_list_collections_reports_the_real_member_count(
    db_session, owner, seed_follow
):
    """``series_count`` comes from a GROUP BY now, not ``len(row.series)``."""
    user_id, profile_id = owner
    svc = _svc(db_session, user_id, profile_id)
    full = svc.create_collection(name="Full")
    empty = svc.create_collection(name="Empty")
    for key in ("a", "b", "c"):
        seed_follow(user_id, profile_id, series_key=key)
        svc.add_series_to_collection(full["id"], "mangadex", key)

    counts = {c["name"]: c["series_count"] for c in svc.list_collections()}

    assert counts == {"Full": 3, "Empty": 0}
    assert empty["id"] != full["id"]
