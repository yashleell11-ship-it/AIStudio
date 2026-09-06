"""Which chapter a series RESUMES at, when several chapters carry progress.

``chapter_progress`` is one row per chapter, and the furthest-wins merge
(``test_progress_merge``) only ever decides a fight WITHIN one row. Which row
speaks for the series — the one Continue Reading opens — is a separate rule,
and it is the one that can send a reader backwards across chapters without any
single row ever rewinding. These tests pin that rule from both ends:

* pushes for an OLDER chapter that arrive LATER (a debounced save, an offline
  outbox flushed out of order, a reversed batch) must not overtake the chapter
  actually read last — the client's capture time decides, not arrival; and
* finishing the newest chapter must never fall back to an older unfinished
  one. That is exactly the "sent back 2-3 chapters" a continuous feed
  produces: the mobile reader leaves mid-chapter rows behind for chapters it
  scrolled through (it completes a chapter only when its LAST page settles),
  and a strip that skips completed rows then resumes the newest of the ones
  it skimmed past.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from services.followed_series_service import FollowedSeriesService
from services.progress_service import ProgressInput, ProgressService
from tests._fakes import FakeBrowse

SRC = "mangadex"
SERIES = "solo-leveling"
T0 = datetime(2026, 9, 1, 12, 0, 0)

KNOWN = json.dumps(
    [{"key": f"ch-{n}", "number": float(n), "title": f"Chapter {n}"} for n in range(1, 9)]
)


@pytest.fixture
def account(make_user, make_profile):
    user = make_user("resume-owner")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def progress(db_session, account):
    uid, pid = account
    return ProgressService(db_session, user_id=uid, profile_id=pid)


@pytest.fixture
def library(db_session, account):
    uid, pid = account
    return FollowedSeriesService(db_session, FakeBrowse(), user_id=uid, profile_id=pid)


@pytest.fixture
def followed(account, seed_follow):
    uid, pid = account
    return seed_follow(uid, pid, source_id=SRC, series_key=SERIES, known_chapters=KNOWN)


def _push(chapter: int, *, at: datetime, number: float | None = "auto", **kw) -> ProgressInput:
    base = dict(
        source_id=SRC,
        series_key=SERIES,
        chapter_key=f"ch-{chapter}",
        chapter_number=float(chapter) if number == "auto" else number,
        last_page=4,
        page_count=20,
        last_read_at=at,
    )
    base.update(kw)
    return ProgressInput(**base)


def _resume(library) -> list[tuple[str, int]]:
    return [(r["chapter_key"], r["last_page"]) for r in library.continue_reading()]


# --- arrival order never beats capture time ---------------------------------


def test_an_older_chapter_pushed_later_does_not_overtake_the_newest(
    progress, library, followed
):
    """Chapter 5 was read at 12:10; chapter 3's debounced save lands after it
    but was captured at 12:00. The series resumes at 5."""
    progress.save_one(_push(5, at=T0 + timedelta(minutes=10), last_page=9))
    progress.save_one(_push(3, at=T0, last_page=17))

    assert _resume(library) == [("ch-5", 9)]


def test_a_reversed_batch_resumes_at_the_chapter_read_last(progress, library, followed):
    """An outbox flushed as one batch, newest push first."""
    progress.save_batch(
        [
            _push(5, at=T0 + timedelta(minutes=10), last_page=9),
            _push(4, at=T0 + timedelta(minutes=5), last_page=20, is_completed=True),
            _push(3, at=T0, last_page=17),
        ]
    )

    assert _resume(library) == [("ch-5", 9)]


def test_a_numberless_newest_chapter_still_wins(progress, library, followed):
    """The mobile reader sends ``chapter_number = null`` for a chapter whose
    number it never learned. The resume rule is by time, so a NULL number must
    neither sink the row below numbered ones nor break the ordering."""
    progress.save_batch(
        [
            _push(5, at=T0 + timedelta(minutes=10), number=None, last_page=9),
            _push(3, at=T0, last_page=17),
        ]
    )

    assert _resume(library) == [("ch-5", 9)]


def test_an_unstamped_batch_is_ordered_by_its_position_in_the_batch(
    progress, library, followed
):
    """A push with no ``last_read_at`` is dated when the server merges it, so a
    batch without stamps is read in the order it was sent. Pinned so the
    contract is explicit: a client that batches MUST stamp its pushes (the
    mobile outbox does, at capture) or send them oldest first."""
    progress.save_batch(
        [
            _push(3, at=None, last_page=17),
            _push(5, at=None, last_page=9),
        ]
    )

    assert _resume(library) == [("ch-5", 9)]


# --- finishing a chapter never resumes an earlier one ------------------------


def test_finishing_the_newest_chapter_offers_the_next_one_not_an_older_unfinished_row(
    progress, library, followed
):
    """The continuous-feed shape: chapters 3 and 4 were scrolled through and
    left with mid-chapter rows (their last pages never settled), chapter 5 was
    finished on its last page. Continue must go FORWARD to chapter 6 — not
    back to chapter 4, the newest row that happens to be unfinished."""
    progress.save_batch(
        [
            _push(3, at=T0, last_page=12),
            _push(4, at=T0 + timedelta(minutes=5), last_page=11),
            _push(5, at=T0 + timedelta(minutes=10), last_page=20, is_completed=True),
        ]
    )

    strip = library.continue_reading()

    assert [(r["chapter_key"], r["last_page"]) for r in strip] == [("ch-6", 1)]
    assert strip[0]["chapter_number"] == 6.0
    assert strip[0]["page_count"] == 0


def test_finishing_the_last_known_chapter_drops_the_series_rather_than_rewinding(
    progress, library, account, seed_follow
):
    uid, pid = account
    seed_follow(
        uid, pid, source_id=SRC, series_key=SERIES,
        known_chapters=json.dumps([{"key": "ch-4", "number": 4.0}, {"key": "ch-5", "number": 5.0}]),
    )
    progress.save_batch(
        [
            _push(4, at=T0, last_page=11),
            _push(5, at=T0 + timedelta(minutes=10), last_page=20, is_completed=True),
        ]
    )

    assert _resume(library) == []


def test_finishing_a_chapter_with_no_known_list_drops_the_series(
    progress, library, account, seed_follow
):
    """No ``known_chapters`` means no way to name the next chapter; absent
    beats a rewind."""
    uid, pid = account
    seed_follow(uid, pid, source_id=SRC, series_key=SERIES)
    progress.save_batch(
        [
            _push(4, at=T0, last_page=11),
            _push(5, at=T0 + timedelta(minutes=10), last_page=20, is_completed=True),
        ]
    )

    assert _resume(library) == []


def test_the_next_chapter_is_resolved_by_number_not_listing_order(
    progress, library, account, seed_follow
):
    """Connectors that list newest-first must not make "next" mean "older"."""
    uid, pid = account
    newest_first = [{"key": f"ch-{n}", "number": float(n)} for n in (7, 6, 5, 4)]
    seed_follow(
        uid, pid, source_id=SRC, series_key=SERIES, known_chapters=json.dumps(newest_first)
    )
    progress.save_one(_push(5, at=T0, last_page=20, is_completed=True))

    assert _resume(library) == [("ch-6", 1)]


# --- the same rule through the HTTP surface ---------------------------------


def test_reversed_batch_endpoint_then_continue_reading(client, as_user, account, followed):
    uid, pid = account
    headers = as_user(uid, pid)
    stamp = lambda minutes: (T0 + timedelta(minutes=minutes)).isoformat() + "Z"  # noqa: E731

    resp = client.post(
        "/reader/progress/batch",
        json=[
            {"source_id": SRC, "series_key": SERIES, "chapter_key": "ch-5",
             "chapter_number": 5.0, "last_page": 9, "page_count": 20,
             "last_read_at": stamp(10)},
            {"source_id": SRC, "series_key": SERIES, "chapter_key": "ch-3",
             "chapter_number": 3.0, "last_page": 17, "page_count": 20,
             "last_read_at": stamp(0)},
        ],
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"] == 2

    strip = client.get("/library/continue-reading", headers=headers)
    assert strip.status_code == 200, strip.text
    assert [(r["chapter_key"], r["last_page"]) for r in strip.json()] == [("ch-5", 9)]
