"""AUDIT (shard progress-stats): accounting invariants between
``chapter_progress``, ``reading_sessions`` and the statistics screen.

Each test states an invariant a careful operator would expect to hold. A
FAILING test here is the finding — it is deliberately written against the
desired behaviour, not the current one. The property-style tests at the end
(``test_property_*``) re-derive every roll-up in Python from the seeded rows
and are expected to PASS: they show the SQL matches the rows it reads.

Read-only audit: this file adds coverage, it changes nothing else.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

from core.time_utils import utcnow
from database.models import ChapterProgress, ReadingSession
from services.progress_service import (
    MAX_PUSH_SECONDS,
    ProgressInput,
    ProgressService,
)
from services.reading_stats_service import SESSION_SECONDS_CAP, ReadingStatsService


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("auditowner")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def svc(db_session, acct):
    uid, pid = acct
    return ProgressService(db_session, user_id=uid, profile_id=pid)


def _stats(db, uid, pid, *, tz=0):
    return ReadingStatsService(
        db, user_id=uid, profile_id=pid, gate_open=True, tz_offset_minutes=tz
    )


def _push(**kw) -> ProgressInput:
    base = dict(
        source_id="mangadex",
        series_key="series-1",
        chapter_key="ch-1",
        chapter_number=1.0,
        last_page=1,
        page_count=20,
    )
    base.update(kw)
    return ProgressInput(**base)


def _row(db, uid, pid, chapter_key="ch-1") -> ChapterProgress:
    return (
        db.query(ChapterProgress)
        .filter_by(user_id=uid, profile_id=pid, chapter_key=chapter_key)
        .one()
    )


def _sessions(db, uid, pid) -> list[ReadingSession]:
    return (
        db.query(ReadingSession)
        .filter_by(user_id=uid, profile_id=pid)
        .order_by(ReadingSession.id)
        .all()
    )


# ---------------------------------------------------------------------------
# 1. Outbox replay must not double-count reading time
# ---------------------------------------------------------------------------


def test_replayed_batch_does_not_double_count_time_spent(svc, db_session, acct):
    """The mobile outbox clears rows only AFTER a 2xx (progress_outbox_provider
    .dart:65-81) and documents replay as "harmless" (downloads_store.dart:512-514).
    Position is idempotent under replay; ``time_spent_seconds`` is not
    (progress_service.py:158 adds unconditionally, no push id / dedupe)."""
    uid, pid = acct
    t0 = utcnow() - timedelta(minutes=10)
    batch = [_push(last_page=10, time_spent_seconds=120, last_read_at=t0)]

    svc.save_batch(batch)
    svc.save_batch(batch)  # a retry after a lost 2xx / timeout

    row = _row(db_session, uid, pid)
    assert row.last_page == 10  # position: idempotent (furthest-wins)
    assert row.time_spent_seconds == 120, (
        f"replay double-counted: row.time_spent_seconds={row.time_spent_seconds}"
    )


# ---------------------------------------------------------------------------
# 2. The two time ledgers must agree
# ---------------------------------------------------------------------------


def test_row_time_and_session_time_agree_after_non_advancing_pushes(
    svc, db_session, acct
):
    """``chapter_progress.time_spent_seconds`` accepts time from EVERY push
    (all three merge branches), but a ``reading_sessions`` row is written only
    when the position advanced (progress_service.py:505), and the session's
    duration is ``merged - previous`` (line 510) where ``previous`` already
    absorbed the non-advancing pushes. Time read on a page the reader stays on
    (or re-reads) is charged to the row and never reaches the statistics."""
    uid, pid = acct
    t = utcnow() - timedelta(minutes=30)
    svc.save_one(_push(last_page=5, time_spent_seconds=60, last_read_at=t))
    svc.save_one(
        _push(last_page=5, time_spent_seconds=120, last_read_at=t + timedelta(minutes=2))
    )
    svc.save_one(
        _push(last_page=6, time_spent_seconds=30, last_read_at=t + timedelta(minutes=4))
    )

    row = _row(db_session, uid, pid)
    session_seconds = sum(s.duration_seconds for s in _sessions(db_session, uid, pid))
    assert row.time_spent_seconds == 210
    assert session_seconds == row.time_spent_seconds, (
        f"sessions carry {session_seconds}s, the row carries {row.time_spent_seconds}s"
    )


# ---------------------------------------------------------------------------
# 3. Re-reading is reading: it must count toward totals and the streak
# ---------------------------------------------------------------------------


def test_rereading_a_finished_chapter_counts_toward_statistics_and_streak(
    svc, db_session, acct, seed_progress
):
    """A chapter finished last week and re-read today, page by page, for
    ten minutes. Furthest-wins means no push advances, so no session is
    recorded: the statistics screen reports 0 pages, 0 seconds and a broken
    streak for a day the reader spent reading. The live DB shows the same shape
    (chapter_progress.last_read_at on 2026-09-05 with no reading_sessions row
    that day)."""
    uid, pid = acct
    seed_progress(
        uid,
        pid,
        chapter_key="ch-1",
        last_page=20,
        page_count=20,
        is_completed=True,
        completed_at=utcnow() - timedelta(days=7),
        last_read_at=utcnow() - timedelta(days=7),
    )
    now = utcnow()
    svc.save_batch(
        [
            _push(
                last_page=page,
                time_spent_seconds=30,
                last_read_at=now - timedelta(seconds=30 * (20 - page)),
            )
            for page in range(1, 21)
        ]
    )

    out = _stats(db_session, uid, pid).build(7)
    assert out["totals"]["sessions"] > 0, "a ten-minute re-read produced no session"
    assert out["totals"]["seconds_read"] > 0
    assert out["streak"]["current_days"] >= 1, "the day of reading counts as missed"


# ---------------------------------------------------------------------------
# 4. A push's time_spent must be bounded before it back-dates a session
# ---------------------------------------------------------------------------


def test_time_spent_is_bounded_before_it_places_a_session_in_the_past(
    svc, db_session, acct
):
    """``ProgressRequest.time_spent_seconds`` is ``ge=0`` with no upper bound
    (routes/reader.py:75). ``_apply_one`` sets ``started_at = last_read_at -
    elapsed`` (progress_service.py:522-524). ``SESSION_SECONDS_CAP`` caps the
    seconds at read time but not WHERE the session lands, so one push can
    invent an active day three days ago (streak bridging, daily chart)."""
    uid, pid = acct
    now = utcnow()
    svc.save_one(
        _push(last_page=10, time_spent_seconds=3 * 86400, last_read_at=now)
    )

    stats = _stats(db_session, uid, pid)
    active = stats._active_days()
    # The clamp is a duration, not a truncation to midnight, so its window may
    # legitimately straddle one: the invariant is that no day older than a
    # single clamped push can appear, not that only today can.
    window = {
        now.date().isoformat(),
        (now - timedelta(seconds=MAX_PUSH_SECONDS)).date().isoformat(),
    }
    assert set(active) <= window, f"active days invented by one push: {active}"
    daily = {d["date"]: d for d in stats.build(7)["daily"]}
    three_days_ago = (now - timedelta(days=3)).date().isoformat()
    assert daily[three_days_ago]["seconds_read"] == 0


# ---------------------------------------------------------------------------
# 5. A far-past client clock is accepted verbatim on a new row
# ---------------------------------------------------------------------------


def test_far_past_client_clock_is_not_believed_on_a_new_row(svc, db_session, acct):
    """``clamp_client_clock`` caps only the future (core/time_utils.py:55-64).
    A client whose default DateTime serializes as the epoch writes a 1970 row
    and a 1970 session; ``first_session_at`` and the active-day list carry it
    for ever. Low severity — shipped clients stamp ``now()`` — but the server
    is the only place that can refuse it."""
    uid, pid = acct
    epoch = datetime(1970, 1, 1)
    svc.save_one(_push(last_page=3, time_spent_seconds=10, last_read_at=epoch))

    row = _row(db_session, uid, pid)
    assert row.started_at.year >= 2000, f"row started_at={row.started_at}"
    out = _stats(db_session, uid, pid).build(7)
    assert out["totals"]["first_session_at"] is None or out["totals"][
        "first_session_at"
    ] >= "2000"


# ---------------------------------------------------------------------------
# 6. Property-style: the SQL roll-ups equal a Python recomputation of the rows
# ---------------------------------------------------------------------------


def _expected(rows, *, since, tz_minutes, cap=SESSION_SECONDS_CAP):
    off = timedelta(minutes=tz_minutes)

    def secs(r):
        if r.ended_at is None:
            return 0
        raw = int(
            (r.ended_at.replace(microsecond=0) - r.started_at.replace(microsecond=0))
            .total_seconds()
        )
        return min(cap, max(0, raw))

    def roll(sub):
        return {
            "sessions": len(sub),
            "pages_read": sum(r.pages_read for r in sub),
            "chapters_read": len({(r.source_id, r.series_key, r.chapter_key) for r in sub}),
            "series_read": len({(r.source_id, r.series_key) for r in sub}),
            "seconds_read": sum(secs(r) for r in sub),
        }

    windowed = [r for r in rows if r.started_at >= since]
    daily = {}
    for r in windowed:
        daily.setdefault((r.started_at + off).date().isoformat(), []).append(r)
    active = sorted({(r.started_at + off).date() for r in rows})
    longest = run = 0
    prev = None
    for d in active:
        run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        longest = max(longest, run)
        prev = d
    today = (utcnow() + off).date()
    current = run if active and (today - active[-1]).days <= 1 else 0
    return {
        "totals": roll(rows),
        "window": roll(windowed),
        "daily": {k: roll(v) for k, v in daily.items()},
        "streak": {"current_days": current, "longest_days": longest},
    }


@pytest.mark.parametrize("seed", [1, 7, 42, 1234, 99991])
@pytest.mark.parametrize("tz", [0, 330, -420])
def test_property_rollups_match_the_rows(db_session, acct, seed_session, seed, tz):
    uid, pid = acct
    rng = random.Random(seed)
    now = utcnow()
    rows = []
    for _ in range(rng.randint(5, 60)):
        started = now - timedelta(
            days=rng.randint(0, 20), hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
        )
        kind = rng.random()
        if kind < 0.1:
            extra = {"ended_at": None}
        elif kind < 0.2:
            extra = {"ended_at": started - timedelta(seconds=rng.randint(1, 500))}
        else:
            extra = {"ended_at": started + timedelta(seconds=rng.randint(0, 2 * SESSION_SECONDS_CAP))}
        rows.append(
            seed_session(
                uid,
                pid,
                source_id=rng.choice(["mangadex", "asurascans"]),
                series_key=rng.choice(["s1", "s2", "s3"]),
                chapter_key=f"ch-{rng.randint(1, 6)}",
                pages_read=rng.randint(0, 30),
                started_at=started,
                **extra,
            )
        )

    stats = _stats(db_session, uid, pid, tz=tz)
    days = 14
    since, _, labels = stats._bounds(days)
    out = stats.build(days)
    exp = _expected(rows, since=since, tz_minutes=tz)

    for key in ("sessions", "pages_read", "chapters_read", "series_read", "seconds_read"):
        assert out["totals"][key] == exp["totals"][key], key
        assert out["window"][key] == exp["window"][key], key
    got_daily = {d["date"]: d for d in out["daily"]}
    assert list(got_daily) == labels
    for day in labels:
        for key in ("sessions", "pages_read", "seconds_read"):
            assert got_daily[day][key] == exp["daily"].get(day, {}).get(key, 0), (day, key)
    assert out["streak"]["current_days"] == exp["streak"]["current_days"]
    assert out["streak"]["longest_days"] == exp["streak"]["longest_days"]


@pytest.mark.parametrize("seed", [3, 11, 2024])
def test_property_session_time_equals_row_time_when_every_push_advances(
    svc, db_session, acct, seed
):
    """When every push moves forward, the two ledgers agree exactly. This is
    the control for test 2: the divergence there is caused by non-advancing
    pushes alone."""
    uid, pid = acct
    rng = random.Random(seed)
    t = utcnow() - timedelta(hours=2)
    page = 0
    total = 0
    for _ in range(rng.randint(3, 25)):
        page += rng.randint(1, 4)
        spent = rng.randint(0, 300)
        total += spent
        t += timedelta(seconds=max(spent, 1))
        svc.save_one(_push(last_page=page, page_count=200, time_spent_seconds=spent, last_read_at=t))
    row = _row(db_session, uid, pid)
    assert row.time_spent_seconds == total
    assert sum(s.duration_seconds for s in _sessions(db_session, uid, pid)) == total
    assert sum(s.pages_read for s in _sessions(db_session, uid, pid)) == page
