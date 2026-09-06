"""AUDIT (shard progress-stats): the floor under a client's own clock.

``clamp_client_clock`` caps only the FUTURE, so the merge used to take any
past stamp verbatim — including the epoch a client emits when its
``last_read_at`` serializes as a DateTime default. That wrote a 1970
``chapter_progress`` row and a 1970 ``reading_sessions`` row, and
``ReadingStatsService._active_days`` scans the whole table, so the 1970 row
owned ``first_session_at`` and the longest streak permanently.

The end-to-end proof lives in
``test_audit_progress_stats_accounting.test_far_past_client_clock_is_not_believed_on_a_new_row``;
these pin the rule itself, including the half that must NOT change — an
honest old offline push is still recorded as old.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from core.time_utils import MAX_CLIENT_CLOCK_SKEW, utcnow
from services.progress_service import (
    MAX_CLIENT_CLOCK_AGE,
    ProgressInput,
    merge_progress,
)

NOW = datetime(2026, 9, 7, 12, 0, 0)


def _push(**kw) -> ProgressInput:
    base = dict(source_id="s", series_key="k", chapter_key="c", last_page=5)
    base.update(kw)
    return ProgressInput(**base)


def test_the_epoch_is_not_believed():
    m = merge_progress(None, _push(last_read_at=datetime(1970, 1, 1)), now=NOW)
    assert m.last_read_at == NOW


def test_a_push_with_no_stamp_is_stamped_now():
    m = merge_progress(None, _push(), now=NOW)
    assert m.last_read_at == NOW


def test_an_honest_offline_push_keeps_its_own_age():
    """The whole point of letting a device stamp its writes. A month-old push
    stays a month old — the floor exists to catch a broken clock, and must
    never quietly restamp reading that really happened."""
    stamp = NOW - timedelta(days=30)
    m = merge_progress(None, _push(last_read_at=stamp), now=NOW)
    assert m.last_read_at == stamp


def test_the_edge_of_the_window_is_still_believed():
    stamp = NOW - MAX_CLIENT_CLOCK_AGE
    m = merge_progress(None, _push(last_read_at=stamp), now=NOW)
    assert m.last_read_at == stamp

    m = merge_progress(None, _push(last_read_at=stamp - timedelta(seconds=1)), now=NOW)
    assert m.last_read_at == NOW


def test_the_future_is_still_only_capped_not_replaced():
    """``clamp_client_clock``'s half of the rule, re-run here because the
    service now applies it itself rather than trusting the route to have."""
    m = merge_progress(None, _push(last_read_at=NOW + timedelta(days=400)), now=NOW)
    assert m.last_read_at == NOW + MAX_CLIENT_CLOCK_SKEW


def test_the_window_is_wide_enough_that_a_test_fixture_cannot_drift_into_it():
    """Guard on the constant itself: it is a floor under broken clocks, not a
    retention policy, and shrinking it would start rewriting honest history."""
    assert utcnow() - MAX_CLIENT_CLOCK_AGE < datetime(2022, 1, 1)
