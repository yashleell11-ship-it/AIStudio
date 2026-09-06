"""IDX-5: ``reading_day_stats`` answering for ``reading_sessions`` (audit 2026-09-07).

The statistics screen asks one question of the WHOLE history -- which local
days did this profile read on, which is the streak -- and it asked it by
sorting the append-only session table under ``strftime`` on every open, so it
got slower with every chapter the owner ever read. ``reading_day_stats`` holds
that answer, one row per CLOSED day, maintained by the reader itself because
nothing else on this box will.

Most of this file is one assertion seen from different sides: the roll-up path
and the session path return the SAME numbers. A statistics screen that loads
faster and quietly reports a different streak is a worse outcome than the slow
query, so the guards that make the reader ignore the roll-up (wrong timezone,
shut 18+ gate, a session it cannot account for) are tested as hard as the fast
path, and the repair that a backdated session triggers is pinned by name.

The last test is the other half: proof that the closed history is no longer
read row by row once it has been summarised.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, select, update

from core.time_utils import utcnow
from database.models import ReadingDayStats
from services.reading_stats_service import (
    ROLLUP_TZ_OFFSET_MINUTES,
    ReadingStatsService,
    backfill_reading_day_stats,
)

MATURE_SOURCE = "nhentai"


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("rollupowner")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


def _stats(db, user_id, profile_id, *, gate_open=True, tz=ROLLUP_TZ_OFFSET_MINUTES):
    return ReadingStatsService(
        db,
        user_id=user_id,
        profile_id=profile_id,
        gate_open=gate_open,
        tz_offset_minutes=tz,
    )


def _at(days_ago: int, *, hour: int = 12) -> datetime:
    """A UTC instant ``days_ago`` days back, at a fixed hour of that UTC day."""
    return datetime.combine(
        (utcnow() - timedelta(days=days_ago)).date(), datetime.min.time()
    ) + timedelta(hours=hour)


def _day(moment: datetime, *, tz: int = ROLLUP_TZ_OFFSET_MINUTES) -> str:
    return (moment + timedelta(minutes=tz)).date().isoformat()


def _rows(db, user_id, profile_id) -> dict[str, ReadingDayStats]:
    return {
        r.day: r
        for r in db.execute(
            select(ReadingDayStats)
            .where(ReadingDayStats.user_id == user_id)
            .where(ReadingDayStats.profile_id == profile_id)
        ).scalars()
    }


def _payload(out: dict) -> dict:
    """``build()`` minus the wall clock it stamps, so two calls compare equal."""
    return {k: v for k, v in out.items() if k != "range"}


def _capture(db, fn) -> list[tuple[str, tuple]]:
    """Run ``fn``; return every statement it emitted, with its parameters."""
    seen: list[tuple[str, tuple]] = []

    def _listen(conn, cursor, statement, parameters, context, executemany):
        seen.append((statement, tuple(parameters or ())))

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _listen)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _listen)
    return seen


def _plan(db, sql: str, params: tuple) -> list[str]:
    raw = db.connection().connection.driver_connection
    return [row[3] for row in raw.execute("EXPLAIN QUERY PLAN " + sql, params)]


def _sessions_only(monkeypatch) -> None:
    """Force the pre-roll-up path: the numbers this change must not move."""
    monkeypatch.setattr(ReadingStatsService, "_rollup_usable", lambda self: False)


def _busy_history(seed_session, uid, pid) -> None:
    """Reading across many days, of the shapes the payload distinguishes.

    Two runs of consecutive days (so ``current`` and ``longest`` differ), a day
    with two series on it, a session past ``SESSION_SECONDS_CAP``, one the
    client never closed, a mature series (the gate is open, so it counts), and
    a day older than any window the screen offers.
    """
    for n in (0, 1, 2):
        seed_session(uid, pid, series_key="a", chapter_key=f"c{n}",
                     started_at=_at(n), pages_read=n + 4)
    for n in (5, 6, 7, 8):
        seed_session(uid, pid, series_key="b", chapter_key=f"c{n}",
                     started_at=_at(n, hour=21), pages_read=n)
    seed_session(uid, pid, series_key="b", chapter_key="second",
                 started_at=_at(6, hour=23), pages_read=3, duration_seconds=99_999)
    seed_session(uid, pid, source_id="mangakakalot", series_key="c",
                 chapter_key="c1", started_at=_at(7, hour=4), pages_read=11)
    seed_session(uid, pid, source_id=MATURE_SOURCE, series_key="adult",
                 chapter_key="c1", started_at=_at(2, hour=1), pages_read=6)
    seed_session(uid, pid, series_key="a", chapter_key="open",
                 started_at=_at(1, hour=8), duration_seconds=None)
    seed_session(uid, pid, series_key="old", chapter_key="c1",
                 started_at=_at(40), pages_read=2)


# --- what gets materialised ------------------------------------------------


def test_a_read_materialises_the_closed_days_and_nothing_else(
    db_session, acct, seed_session
):
    """The reader is the writer: no backfill is called anywhere here.

    Two days, two series on the first of them, one session long enough to be
    clamped by ``SESSION_SECONDS_CAP`` -- and one today, which must stay out of
    the table because today is still being read into.
    """
    uid, pid = acct
    seed_session(uid, pid, series_key="a", chapter_key="c1",
                 started_at=_at(3), pages_read=10, duration_seconds=600)
    seed_session(uid, pid, series_key="a", chapter_key="c2",
                 started_at=_at(3, hour=14), pages_read=5, duration_seconds=99_999)
    seed_session(uid, pid, series_key="b", chapter_key="c1",
                 started_at=_at(3, hour=16), pages_read=7, duration_seconds=60)
    seed_session(uid, pid, series_key="a", chapter_key="c3",
                 started_at=_at(1), pages_read=3, duration_seconds=120)
    seed_session(uid, pid, series_key="a", chapter_key="c4",
                 started_at=_at(0), pages_read=99, duration_seconds=120)

    _stats(db_session, uid, pid).build(7)

    rolled = _rows(db_session, uid, pid)
    first, second = _day(_at(3)), _day(_at(1))
    assert set(rolled) == {first, second}, "today must not be summarised"
    assert (rolled[first].sessions, rolled[first].pages_read) == (3, 22)
    assert rolled[first].seconds_read == 600 + 3600 + 60
    assert rolled[first].series_count == 2
    assert (rolled[second].sessions, rolled[second].pages_read) == (1, 3)
    assert (rolled[second].seconds_read, rolled[second].series_count) == (120, 1)


def test_today_is_still_counted_while_it_is_not_materialised(
    db_session, acct, seed_session
):
    uid, pid = acct
    seed_session(uid, pid, chapter_key="c1", started_at=_at(1))
    seed_session(uid, pid, chapter_key="c2", started_at=_at(0))

    out = _stats(db_session, uid, pid).build(7)

    assert _day(_at(0)) not in _rows(db_session, uid, pid)
    assert out["streak"] == {
        "current_days": 2,
        "longest_days": 2,
        "last_active_date": _day(_at(0)),
    }


def test_a_second_read_on_the_same_day_writes_nothing(
    db_session, acct, seed_session
):
    """The steady state is a read, not a read-modify-write.

    The count that guards the roll-up also proves it is current, so once the
    days have closed and been summarised a reload does not touch the table --
    which matters on SQLite, where every commit takes the single writer.
    """
    uid, pid = acct
    seed_session(uid, pid, chapter_key="c1", started_at=_at(3))
    seed_session(uid, pid, chapter_key="c2", started_at=_at(0))
    _stats(db_session, uid, pid).build(7)

    stmts = _capture(db_session, lambda: _stats(db_session, uid, pid).build(7))

    writes = [
        s for s, _ in stmts
        if s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert writes == []


def test_the_backfill_rebuilds_rather_than_doubles_and_stays_in_its_scope(
    db_session, acct, make_user, make_profile, seed_session
):
    uid, pid = acct
    other = make_user("rollupother")
    other_pid = make_profile(other.id, "Main").id
    seed_session(uid, pid, started_at=_at(2), pages_read=4)
    seed_session(other.id, other_pid, started_at=_at(2), pages_read=9)

    backfill_reading_day_stats(db_session)
    # The whole-table rebuild is for a changed ROLLUP_TZ_OFFSET_MINUTES or
    # SESSION_SECONDS_CAP, so it has to be safe to re-run: the second pass must
    # replace the first, not add to it.
    backfill_reading_day_stats(db_session, user_id=uid, profile_id=pid)

    mine = _rows(db_session, uid, pid)
    theirs = _rows(db_session, other.id, other_pid)
    assert [r.pages_read for r in mine.values()] == [4]
    assert [r.pages_read for r in theirs.values()] == [9]


# --- identical numbers ----------------------------------------------------


@pytest.mark.parametrize("days", [7, 30, 365])
def test_the_payload_is_identical_with_and_without_the_rollup(
    db_session, acct, seed_follow, seed_session, monkeypatch, days
):
    """Every number the screen shows, computed both ways, compared whole.

    Not just the streak: the roll-up is maintained on the read path now, so
    this also says that the write it does moves nothing else in the payload.
    """
    uid, pid = acct
    seed_follow(uid, pid, series_key="a", title="A")
    _busy_history(seed_session, uid, pid)

    _sessions_only(monkeypatch)
    raw = _payload(_stats(db_session, uid, pid).build(days))
    assert not _rows(db_session, uid, pid), "the session path must not write"
    monkeypatch.undo()

    rolled = _payload(_stats(db_session, uid, pid).build(days))

    assert _stats(db_session, uid, pid)._rollup_usable(), "the roll-up was skipped"
    assert rolled == raw
    # Named rather than derived, so this fails loudly if the fixture drifts.
    assert raw["streak"] == {
        "current_days": 3,
        "longest_days": 4,
        "last_active_date": _day(_at(0)),
    }


def test_the_streak_is_read_from_the_rollup(db_session, acct, seed_session):
    """White-box: the roll-up is the source, not a second opinion.

    The stored day is moved to one the session table cannot vouch for, while
    the session COUNT it carries -- everything the reader verifies -- stays
    right, so only a reader that actually reads ``reading_day_stats`` can
    report it.
    """
    uid, pid = acct
    seed_session(uid, pid, started_at=_at(2))
    _stats(db_session, uid, pid).build(7)
    db_session.execute(
        update(ReadingDayStats)
        .where(ReadingDayStats.user_id == uid)
        .values(day=_day(_at(1)))
    )
    db_session.commit()

    out = _stats(db_session, uid, pid).build(7)
    assert out["streak"]["last_active_date"] == _day(_at(1))


# --- the repairs ----------------------------------------------------------


def test_a_backdated_session_reaches_a_day_already_rolled_up(
    db_session, acct, seed_session, monkeypatch
):
    """The case the trailing re-derive exists for.

    ``started_at`` is the client's: a phone that read on the train and flushed
    when it found wifi inserts rows into days that were summarised hours ago.
    The roll-up has nowhere to record which days changed since it last ran (see
    ``_REPAIR_DAYS``), so the reader re-derives the whole window.
    """
    uid, pid = acct
    seed_session(uid, pid, chapter_key="c1", started_at=_at(4))
    _stats(db_session, uid, pid).build(7)
    assert _rows(db_session, uid, pid)[_day(_at(4))].sessions == 1

    seed_session(uid, pid, series_key="offline", chapter_key="c2",
                 started_at=_at(4, hour=20), pages_read=7)
    seed_session(uid, pid, chapter_key="c3", started_at=_at(3))

    out = _stats(db_session, uid, pid).build(7)

    rolled = _rows(db_session, uid, pid)[_day(_at(4))]
    assert (rolled.sessions, rolled.pages_read, rolled.series_count) == (2, 17, 2)
    _sessions_only(monkeypatch)
    assert _payload(out) == _payload(_stats(db_session, uid, pid).build(7))


def test_a_session_older_than_the_repair_window_is_still_counted(
    db_session, acct, seed_session, monkeypatch
):
    """Beyond the window the count is the only thing that can notice.

    A device out of contact for a month, a restore, an import. The trailing
    re-derive cannot reach it, so the count stays short and the reader rebuilds
    the scope -- the scan this table exists to avoid, paid once rather than
    reported wrong forever.
    """
    uid, pid = acct
    seed_session(uid, pid, chapter_key="c1", started_at=_at(2))
    _stats(db_session, uid, pid).build(7)

    seed_session(uid, pid, chapter_key="ancient", started_at=_at(40))
    out = _stats(db_session, uid, pid).build(90)

    assert _day(_at(40)) in _rows(db_session, uid, pid)
    assert out["streak"]["longest_days"] == 1
    _sessions_only(monkeypatch)
    assert _payload(out) == _payload(_stats(db_session, uid, pid).build(90))


def test_a_rollup_it_cannot_account_for_is_rebuilt_not_believed(
    db_session, acct, seed_session
):
    """A row nothing here wrote -- an import, a restore, a half-run job."""
    uid, pid = acct
    seed_session(uid, pid, started_at=_at(3))
    db_session.add(
        ReadingDayStats(
            user_id=uid, profile_id=pid, day="2021-03-04", sessions=9,
            pages_read=99, seconds_read=99, series_count=9,
        )
    )
    db_session.commit()

    out = _stats(db_session, uid, pid).build(7)

    assert set(_rows(db_session, uid, pid)) == {_day(_at(3))}
    assert out["streak"]["last_active_date"] == _day(_at(3))


# --- the guards -----------------------------------------------------------


def test_the_rollup_is_ignored_at_another_timezone_offset(
    db_session, acct, seed_session
):
    """A day is the caller's choice (see the module docstring of the service).

    19:00 UTC is already tomorrow at +05:30, so a roll-up bucketed at one
    offset answers a different question than a request at another one.
    """
    uid, pid = acct
    seed_session(uid, pid, started_at=_at(3, hour=19))
    backfill_reading_day_stats(db_session)

    ist = _stats(db_session, uid, pid, tz=330).build(7)
    assert ist["streak"]["last_active_date"] == _day(_at(3, hour=19), tz=330)
    assert ist["streak"]["last_active_date"] != _day(_at(3, hour=19))


def test_the_rollup_is_ignored_while_the_gate_is_shut(
    db_session, acct, seed_follow, seed_session
):
    """The roll-up counts every session; the gate hides some of them."""
    uid, pid = acct
    seed_session(uid, pid, series_key="safe", chapter_key="c1", started_at=_at(5))
    seed_session(uid, pid, source_id=MATURE_SOURCE, series_key="adult",
                 chapter_key="c1", started_at=_at(2))
    backfill_reading_day_stats(db_session)

    shut = _stats(db_session, uid, pid, gate_open=False).build(7)
    assert shut["streak"]["last_active_date"] == _day(_at(5))
    assert _stats(db_session, uid, pid).build(7)["streak"][
        "last_active_date"
    ] == _day(_at(2))


def test_the_rollup_is_scoped_to_one_profile(
    db_session, acct, make_profile, seed_session
):
    uid, pid = acct
    sibling = make_profile(uid, "Sibling").id
    seed_session(uid, pid, started_at=_at(6))
    seed_session(uid, sibling, started_at=_at(1))

    assert _stats(db_session, uid, pid).build(30)["streak"][
        "last_active_date"
    ] == _day(_at(6))
    assert _stats(db_session, uid, sibling).build(30)["streak"][
        "last_active_date"
    ] == _day(_at(1))


# --- the point of the change ----------------------------------------------


def test_the_streak_no_longer_reads_the_closed_days_it_summarised(
    db_session, acct, seed_session
):
    """The finding itself: 60 closed days of sessions, none of them read.

    Two statements touch ``reading_sessions`` on a warm roll-up. One is the
    count that guards it, which SQLite answers out of
    ``ix_reading_sessions_started_at`` without visiting a single table row. The
    other is today, seeked to by the same index. What is gone is the statement
    this finding was about: ``GROUP BY strftime(...)`` over the whole history,
    which had no index to use and sorted every session ever recorded into a
    temp b-tree.
    """
    uid, pid = acct
    for n in range(1, 61):
        seed_session(uid, pid, chapter_key=f"c{n}", started_at=_at(n))
    seed_session(uid, pid, chapter_key="today", started_at=_at(0))
    _stats(db_session, uid, pid).build(7)

    svc = _stats(db_session, uid, pid)
    stmts = _capture(db_session, svc._active_days)

    reads = [(s, p) for s, p in stmts if "FROM reading_sessions" in s]
    assert len(reads) == 2, [s for s, _ in stmts]
    plans = {sql: _plan(db_session, sql, params) for sql, params in reads}
    for sql, plan in plans.items():
        # A seek into the index, never a walk of the table: neither statement
        # can reach a row outside the range it names.
        assert not any(line.startswith("SCAN") for line in plan), (sql, plan)
        assert any(
            "SEARCH reading_sessions USING COVERING INDEX "
            "ix_reading_sessions_started_at" in line
            for line in plan
        ), (sql, plan)

    guard = next(sql for sql in plans if "count(*)" in sql)
    assert any("started_at<?" in line.replace(" ", "") for line in plans[guard])
    # Nothing is sorted or bucketed over the closed history any more -- that
    # temp b-tree, over every session ever recorded, was the finding.
    assert not any("TEMP B-TREE" in line for line in plans[guard]), plans[guard]

    # The row-count probe: the one statement that reads session rows at all is
    # bounded to the open day, and there is exactly one day in it. (It groups
    # in a temp b-tree, over the rows in that range and no others.)
    today = next(sql for sql in plans if sql is not guard)
    assert any("started_at>?" in line.replace(" ", "") for line in plans[today])
    visited = db_session.connection().connection.driver_connection.execute(
        today, dict(reads)[today]
    ).fetchall()
    assert [row[0] for row in visited] == [_day(_at(0))]
    assert svc._active_days()[-1] == _day(_at(0))
