"""DB-level ``ProgressService`` coverage (spec §3.3, §4.1, §7).

The pure furthest-wins merge is pinned in ``test_progress_merge``. This file
exercises the service against a real ``chapter_progress`` table: ``save_one`` /
``save_batch`` persistence and furthest-wins applied per batch item.

The continue-reading strip is NOT here: it belongs to
``FollowedSeriesService`` (see ``test_library_payload_guarantees``), which
joins ``followed_series`` so the 18+ gate can be resolved.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services.progress_service import (
    MAX_PUSH_SECONDS,
    ProgressInput,
    ProgressService,
)

T0 = datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
def account(make_user, make_profile):
    user = make_user()
    profile = make_profile(user.id, "Main")
    return user, profile


@pytest.fixture
def svc(db_session, account):
    user, profile = account
    return ProgressService(db_session, user_id=user.id, profile_id=profile.id)


def _push(**kw) -> ProgressInput:
    base = dict(
        source_id="mangadex",
        series_key="solo-leveling",
        chapter_key="ch-1",
        chapter_number=1.0,
        last_page=1,
        page_count=20,
    )
    base.update(kw)
    return ProgressInput(**base)


def test_save_one_creates_then_advances(svc):
    first = svc.save_one(_push(last_page=5))
    assert first["last_page"] == 5
    assert first["advanced"] is True

    second = svc.save_one(_push(last_page=12, last_read_at=T0 + timedelta(hours=1)))
    assert second["last_page"] == 12
    assert second["advanced"] is True


def test_save_one_never_rewinds(svc):
    svc.save_one(_push(last_page=18, last_read_at=T0))
    behind = svc.save_one(_push(last_page=3, last_read_at=T0 + timedelta(hours=2)))
    assert behind["last_page"] == 18
    assert behind["advanced"] is False


def test_save_batch_applies_furthest_wins_per_item(svc):
    # Seed ch-1 at page 10.
    svc.save_one(_push(chapter_key="ch-1", chapter_number=1.0, last_page=10))

    result = svc.save_batch(
        [
            _push(chapter_key="ch-1", chapter_number=1.0, last_page=4),   # behind -> ignored
            _push(chapter_key="ch-2", chapter_number=2.0, last_page=7),   # new
            _push(chapter_key="ch-1", chapter_number=1.0, last_page=15),  # ahead -> wins
        ]
    )
    assert result["saved"] == 3

    ch1 = next(
        r for r in svc.get_series_progress("mangadex", "solo-leveling")
        if r["chapter_key"] == "ch-1"
    )
    ch2 = next(
        r for r in svc.get_series_progress("mangadex", "solo-leveling")
        if r["chapter_key"] == "ch-2"
    )
    assert ch1["last_page"] == 15  # furthest of {10, 4, 15}
    assert ch2["last_page"] == 7


def test_batch_higher_chapter_number_wins_even_with_lower_page(svc):
    svc.save_one(_push(chapter_key="ch-3", chapter_number=3.0, last_page=19))
    svc.save_batch(
        [_push(chapter_key="ch-4", chapter_number=4.0, last_page=2)]
    )
    rows = {r["chapter_key"]: r for r in svc.get_series_progress("mangadex", "solo-leveling")}
    assert rows["ch-4"]["chapter_number"] == 4.0
    assert rows["ch-4"]["last_page"] == 2


def test_numberless_push_is_persisted_over_a_numbered_row(svc):
    """End to end through the session: the dropped-save half of the NULL
    chapter_number bug, where the row simply never moved."""
    svc.save_one(
        ProgressInput(
            source_id="mangadex",
            series_key="s1",
            chapter_key="c1",
            chapter_number=5.0,
            last_page=3,
        )
    )
    saved = svc.save_one(
        ProgressInput(
            source_id="mangadex",
            series_key="s1",
            chapter_key="c1",
            chapter_number=None,
            last_page=20,
        )
    )
    assert saved["advanced"] is True
    assert saved["last_page"] == 20
    assert saved["chapter_number"] == 5.0

    stored = svc.get_series_progress("mangadex", "s1")
    assert [r["last_page"] for r in stored] == [20]


# ---------------------------------------------------------------------------
# Reading sessions
#
# `record_session` existed from the start but nothing in production ever called
# it — only a test did — so `reading_sessions` stayed empty on the live server
# while `chapter_progress` filled up. Every statistic built on that table read
# as "no reading history" no matter how much the owner read.
# ---------------------------------------------------------------------------


def _sessions(db_session):
    from database.models import ReadingSession

    return db_session.query(ReadingSession).order_by(ReadingSession.id).all()


def test_saving_progress_records_a_reading_session(svc, db_session):
    svc.save_one(
        ProgressInput(
            source_id="asurascans",
            series_key="a/b",
            chapter_key="a/b/c-1",
            chapter_number=1.0,
            last_page=15,
            page_count=20,
            last_read_at=T0,
        )
    )

    rows = _sessions(db_session)
    assert len(rows) == 1
    # A first push has no earlier position, so the stint starts at page 1.
    assert (rows[0].start_page, rows[0].end_page, rows[0].pages_read) == (1, 15, 15)


def test_a_resumed_chapter_counts_only_the_newly_read_pages(svc, db_session):
    common = {
        "source_id": "asurascans",
        "series_key": "a/b",
        "chapter_key": "a/b/c-1",
        "chapter_number": 1.0,
        "page_count": 20,
    }
    svc.save_one(ProgressInput(**common, last_page=5, last_read_at=T0))
    svc.save_one(
        ProgressInput(**common, last_page=8, last_read_at=T0 + timedelta(minutes=3))
    )

    rows = _sessions(db_session)
    assert len(rows) == 2
    # Resuming at 5 and reaching 8 is three pages — 6, 7 and 8 — not four.
    assert (rows[1].start_page, rows[1].end_page, rows[1].pages_read) == (6, 8, 3)


def test_a_push_that_does_not_advance_and_reports_no_time_records_no_session(
    svc, db_session
):
    common = {
        "source_id": "asurascans",
        "series_key": "a/b",
        "chapter_key": "a/b/c-1",
        "chapter_number": 1.0,
        "page_count": 20,
    }
    svc.save_one(ProgressInput(**common, last_page=9, last_read_at=T0))
    # Clients re-push the same position constantly (autosave, scroll settle).
    # One row per ping would bury the real history and inflate every statistic.
    # A ping like that reports no seconds either, which is what keeps it out.
    svc.save_one(ProgressInput(**common, last_page=9, last_read_at=T0))
    svc.save_one(ProgressInput(**common, last_page=4, last_read_at=T0))

    assert len(_sessions(db_session)) == 1


def test_a_non_advancing_push_that_carried_time_records_a_session(svc, db_session):
    """Re-reading is reading. Furthest-wins means no push advances while a
    finished chapter is read again, and gating the session on ``advanced``
    alone charged those minutes to ``chapter_progress`` and nothing at all to
    ``reading_sessions`` — the ledger every statistic is built from."""
    common = {
        "source_id": "asurascans",
        "series_key": "a/b",
        "chapter_key": "a/b/c-1",
        "chapter_number": 1.0,
        "page_count": 20,
    }
    svc.save_one(ProgressInput(**common, last_page=20, last_read_at=T0))
    svc.save_one(
        ProgressInput(
            **common,
            last_page=3,
            time_spent_seconds=90,
            last_read_at=T0 + timedelta(minutes=5),
        )
    )

    rows = _sessions(db_session)
    assert len(rows) == 2
    # One page, re-read, for the ninety seconds the client reported.
    assert (rows[1].start_page, rows[1].end_page, rows[1].pages_read) == (3, 3, 1)
    assert rows[1].duration_seconds == 90


def test_time_on_the_page_the_row_already_points_at_counts_no_pages(svc, db_session):
    common = {
        "source_id": "asurascans",
        "series_key": "a/b",
        "chapter_key": "a/b/c-1",
        "chapter_number": 1.0,
        "page_count": 20,
    }
    svc.save_one(ProgressInput(**common, last_page=7, last_read_at=T0))
    svc.save_one(
        ProgressInput(
            **common,
            last_page=7,
            time_spent_seconds=45,
            last_read_at=T0 + timedelta(minutes=1),
        )
    )

    rows = _sessions(db_session)
    assert rows[1].pages_read == 0
    assert rows[1].duration_seconds == 45


def test_a_replayed_push_adds_no_time_and_no_session(svc, db_session):
    """``time_spent_seconds`` is a delta with no id; the device's own
    ``last_read_at`` is the only thing that can tell a replay from a read. The
    phone deletes an outbox row only after the 2xx, so this exact re-send
    happens on every lost response."""
    push = ProgressInput(
        source_id="asurascans",
        series_key="a/b",
        chapter_key="a/b/c-1",
        chapter_number=1.0,
        last_page=12,
        page_count=20,
        time_spent_seconds=120,
        last_read_at=T0,
    )
    first = svc.save_one(push)
    replay = svc.save_one(push)

    assert first["time_spent_seconds"] == 120
    assert replay["time_spent_seconds"] == 120
    assert len(_sessions(db_session)) == 1


def test_one_push_cannot_claim_more_than_the_cap(svc, db_session):
    """An unbounded delta does not just inflate a total: ``started_at`` is
    ``last_read_at - elapsed``, so it back-dates the session and invents active
    days (and a streak) that never happened."""
    svc.save_one(
        ProgressInput(
            source_id="asurascans",
            series_key="a/b",
            chapter_key="a/b/c-1",
            chapter_number=1.0,
            last_page=5,
            page_count=20,
            time_spent_seconds=3 * 86400,
            last_read_at=T0,
        )
    )

    row = _sessions(db_session)[0]
    assert row.duration_seconds == MAX_PUSH_SECONDS
    assert row.started_at == T0 - timedelta(seconds=MAX_PUSH_SECONDS)


def test_batch_progress_records_sessions_in_one_transaction(svc, db_session):
    svc.save_batch(
        [
            ProgressInput(
                source_id="asurascans",
                series_key="a/b",
                chapter_key=f"a/b/c-{n}",
                chapter_number=float(n),
                last_page=10,
                page_count=10,
                last_read_at=T0,
            )
            for n in (1, 2, 3)
        ]
    )

    assert len(_sessions(db_session)) == 3
