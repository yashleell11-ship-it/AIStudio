"""Furthest-wins merge unit tests (spec §3.3).

The merge must never last-write-wins: a client that syncs an older device
must not rewind the reader. These tests pin every branch of
``services.progress_service.merge_progress``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from services.progress_service import (
    MergedProgress,
    ProgressInput,
    merge_progress,
)

T0 = datetime(2026, 1, 1, 12, 0, 0)
T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)


def _stored(**kw) -> MergedProgress:
    base = dict(
        chapter_number=10.0,
        last_page=5,
        page_count=20,
        scroll_offset_px=100,
        is_completed=False,
        last_read_at=T1,
        completed_at=None,
        time_spent_seconds=60,
        advanced=False,
    )
    base.update(kw)
    return MergedProgress(**base)


def _push(**kw) -> ProgressInput:
    base = dict(
        source_id="s",
        series_key="k",
        chapter_key="c",
        chapter_number=10.0,
        last_page=5,
        page_count=20,
        scroll_offset_px=100,
        is_completed=False,
        last_read_at=T1,
        time_spent_seconds=0,
    )
    base.update(kw)
    return ProgressInput(**base)


def test_first_write_creates_position():
    m = merge_progress(None, _push(last_page=7), now=T2)
    assert m.last_page == 7
    assert m.advanced is True


def test_forward_movement_advances():
    m = merge_progress(_stored(last_page=5), _push(last_page=9, last_read_at=T2), now=T2)
    assert m.last_page == 9
    assert m.advanced is True


def test_backward_push_never_rewinds():
    m = merge_progress(
        _stored(last_page=12, last_read_at=T1),
        _push(last_page=3, last_read_at=T2),  # newer, but behind
        now=T2,
    )
    assert m.last_page == 12
    assert m.advanced is False
    # last_read_at still advances (bookkeeping), position does not.
    assert m.last_read_at == T2


def test_higher_chapter_number_wins_even_with_lower_page():
    m = merge_progress(
        _stored(chapter_number=10.0, last_page=18),
        _push(chapter_number=11.0, last_page=2, last_read_at=T2),
        now=T2,
    )
    assert m.chapter_number == 11.0
    assert m.last_page == 2
    assert m.advanced is True


def test_tie_on_position_newer_wins_scroll_offset_only():
    m = merge_progress(
        _stored(last_page=5, scroll_offset_px=100, last_read_at=T1),
        _push(last_page=5, scroll_offset_px=850, last_read_at=T2),
        now=T2,
    )
    assert m.last_page == 5
    assert m.scroll_offset_px == 850
    assert m.advanced is False


def test_tie_on_position_older_push_ignored_for_scroll():
    m = merge_progress(
        _stored(last_page=5, scroll_offset_px=100, last_read_at=T2),
        _push(last_page=5, scroll_offset_px=850, last_read_at=T1),  # older
        now=T2,
    )
    assert m.scroll_offset_px == 100


def test_completion_is_sticky():
    m = merge_progress(
        _stored(is_completed=True, completed_at=T1, last_page=20),
        _push(is_completed=False, last_page=2, last_read_at=T2),
        now=T2,
    )
    assert m.is_completed is True
    assert m.completed_at == T1  # never moved


def test_completion_stamps_completed_at_once():
    m = merge_progress(
        _stored(is_completed=False, completed_at=None, last_page=5),
        _push(is_completed=True, last_page=20, last_read_at=T2),
        now=T2,
    )
    assert m.is_completed is True
    assert m.completed_at is not None


def test_time_spent_accumulates():
    m = merge_progress(
        _stored(time_spent_seconds=60),
        _push(time_spent_seconds=45, last_read_at=T2),
        now=T2,
    )
    assert m.time_spent_seconds == 105


def test_page_count_never_decreases():
    m = merge_progress(
        _stored(page_count=20, last_page=5),
        _push(page_count=0, last_page=3, last_read_at=T2),
        now=T2,
    )
    assert m.page_count == 20
