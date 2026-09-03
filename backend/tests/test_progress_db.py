"""DB-level ``ProgressService`` coverage (spec §3.3, §4.1, §7).

The pure furthest-wins merge is pinned in ``test_progress_merge``. This file
exercises the service against a real ``chapter_progress`` table: ``save_one`` /
``save_batch`` persistence, furthest-wins applied per batch item, and
``continue_reading`` ordering + completion filtering.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from services.progress_service import ProgressInput, ProgressService

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


def test_continue_reading_is_latest_unfinished_per_series(svc):
    svc.save_one(
        _push(
            series_key="series-a",
            chapter_key="a1",
            chapter_number=1.0,
            last_page=5,
            last_read_at=T0,
        )
    )
    svc.save_one(
        _push(
            series_key="series-b",
            chapter_key="b1",
            chapter_number=1.0,
            last_page=5,
            last_read_at=T0 + timedelta(hours=1),
        )
    )
    # finish series-b
    svc.save_one(
        _push(
            series_key="series-b",
            chapter_key="b1",
            chapter_number=1.0,
            last_page=20,
            is_completed=True,
            last_read_at=T0 + timedelta(hours=2),
        )
    )

    strip = svc.continue_reading()
    keys = [r["series_key"] for r in strip]
    assert "series-b" not in keys  # completed → dropped
    assert keys == ["series-a"]


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
