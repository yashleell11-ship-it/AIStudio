"""Reading statistics over ``reading_sessions`` (spec §3.3, §5.2).

``reading_sessions`` has been written by :mod:`services.progress_service` since
the source-native rebuild and read by nothing, so every read the owner has ever
done was recorded and thrown away. This module is the reader: it turns those
rows into the numbers behind ``GET /library/statistics``.

Three rules shape everything here.

**Scope.** Every statement filters ``(user_id, profile_id)`` -- see
:meth:`_session_scope`. A statement that filters on ``user_id`` alone reports
one profile the account's *other* profiles' reading, which is the exact
cross-profile leak this project has already shipped and fixed once.

**The 18+ gate.** A session row carries no maturity signal of its own, so the
rating is resolved by joining the profile's ``followed_series`` row -- the same
signals :func:`core.content_rating.resolve_tracker_rating` resolves in Python,
mirrored into SQL by :meth:`_mature_case` so the filter can run inside the
aggregate instead of pulling rows into memory. The join is a LEFT join on
purpose: unfollowing a series must not erase its history from the totals, it
only removes the per-series signal (which then falls back to the source's own
maturity, exactly as rule 3 of ``resolve_tracker_rating`` does). When the gate
is closed a mature series is excluded from *every* number, not just from the
named breakdowns -- a total that silently includes 800 invisible pages tells the
reader that hidden content exists, which is the thing the gate is for.

**Time.** Every timestamp column in this project is a naive SQLite ``DATETIME``
holding UTC. "Day" is therefore not a property of the data; it is a choice the
caller makes. Callers pass ``tz_offset_minutes`` and days are bucketed at that
fixed offset from UTC (``strftime(..., '+330 minutes')``), with the offset
echoed back in the payload so a chart can label its axis honestly. A fixed
offset means no DST transitions -- for a single-household app that is the right
trade against carrying a tz database, but it is a deliberate one.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import Integer, and_, case, distinct, func, literal, select
from sqlalchemy.orm import Session

from connectors.registry import list_installed_connectors
from core.content_rating import mature_rating_predicate
from core.time_utils import utcnow
from database.models import ChapterProgress, FollowedSeries, ReadingSession

#: Longest span a single reading session may contribute to "time spent".
#: ``ended_at`` is written by the client when it stops reporting, so a chapter
#: left open on a locked phone overnight arrives as a nine-hour session. Nobody
#: reads one chapter for an hour; anything past this is a client that stopped
#: talking, not reading time, so it is clamped rather than believed. The cap is
#: published in the payload so a client can say "capped" instead of guessing.
SESSION_SECONDS_CAP = 3600

#: Separator used to fold a composite key into one string for
#: ``COUNT(DISTINCT ...)`` -- SQLite's DISTINCT takes a single expression.
#: ASCII unit-separator: connector keys are URL-ish (slashes, percent-escapes),
#: so a control character cannot collide with one and produce a false match.
_SEP = "\x1f"

_TOP_SOURCES = 8
_TOP_SERIES = 10
_RECENT_SESSIONS = 10


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class ReadingStatsService:
    """Aggregates one profile's ``reading_sessions`` entirely in SQL."""

    def __init__(
        self,
        db: Session,
        *,
        user_id: int | None,
        profile_id: int | None,
        gate_open: bool,
        tz_offset_minutes: int = 0,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._profile_id = profile_id
        self._gate_open = gate_open
        self._tz = int(tz_offset_minutes)

    # --- scope + gate --------------------------------------------------

    def _session_scope(self, stmt):
        """``FollowedSeriesService._scope`` for ``reading_sessions``.

        ``None`` is the unscoped bucket, not a wildcard: ``profile_id`` is NOT
        NULL on this table, so an unscoped caller correctly sees nothing rather
        than the account's every profile merged together.
        """
        stmt = stmt.where(ReadingSession.user_id == self._user_id)
        if self._profile_id is None:
            return stmt.where(ReadingSession.profile_id.is_(None))
        return stmt.where(ReadingSession.profile_id == self._profile_id)

    def _mature_case(self):
        """1 when a session's series is 18+ for this profile, else 0.

        SQL mirror of :func:`core.content_rating.resolve_tracker_rating`, in the
        same priority order: explicit override, then the rating captured at
        follow time, then the source's own maturity. Unknown stays 0 -- folding
        unknown into mature would blank the screen for a gated profile, which is
        the reasoning already recorded on ``resolve_tracker_rating``.
        """
        mature_sources = sorted(
            d.source_type for d in list_installed_connectors() if d.mature
        )
        source_mature = (
            case((ReadingSession.source_id.in_(mature_sources), 1), else_=0)
            if mature_sources
            else literal(0)
        )
        return case(
            (FollowedSeries.mature_override == 1, 1),
            (FollowedSeries.mature_override == 0, 0),
            (
                FollowedSeries.content_rating.is_not(None),
                case(
                    (mature_rating_predicate(FollowedSeries.content_rating), 1),
                    else_=0,
                ),
            ),
            else_=source_mature,
        )

    def _sessions(self, stmt):
        """Scope + gate a statement whose FROM is ``reading_sessions``.

        The follow row is joined unconditionally (not only when the gate is
        shut) because the breakdowns read ``title``/``cover_url`` off it, and
        ``uq_followed_series`` guarantees at most one match so the join cannot
        fan a session row out into several.
        """
        stmt = self._session_scope(
            stmt.outerjoin(
                FollowedSeries,
                and_(
                    FollowedSeries.user_id == ReadingSession.user_id,
                    FollowedSeries.profile_id == ReadingSession.profile_id,
                    FollowedSeries.source_id == ReadingSession.source_id,
                    FollowedSeries.series_key == ReadingSession.series_key,
                ),
            )
        )
        if not self._gate_open:
            stmt = stmt.where(self._mature_case() == 0)
        return stmt

    # --- expressions ---------------------------------------------------

    @property
    def _modifier(self) -> str:
        """SQLite date modifier that shifts UTC into the caller's local day."""
        return f"{self._tz:+d} minutes"

    def _day(self, column=None):
        return func.strftime(
            "%Y-%m-%d", column if column is not None else ReadingSession.started_at,
            self._modifier,
        )

    def _hour(self):
        return func.cast(
            func.strftime("%H", ReadingSession.started_at, self._modifier), Integer
        )

    @staticmethod
    def _seconds():
        """Capped wall-clock seconds for one session row.

        ``max(0, ...)`` because a client with a skewed clock can report an
        ``ended_at`` before its ``started_at``, and a negative session would
        quietly subtract from the day's total.
        """
        raw = func.cast(
            func.strftime("%s", ReadingSession.ended_at), Integer
        ) - func.cast(func.strftime("%s", ReadingSession.started_at), Integer)
        return case(
            (ReadingSession.ended_at.is_(None), 0),
            else_=func.max(0, func.min(literal(SESSION_SECONDS_CAP), raw)),
        )

    @staticmethod
    def _chapter_id():
        return (
            ReadingSession.source_id
            + literal(_SEP)
            + ReadingSession.series_key
            + literal(_SEP)
            + ReadingSession.chapter_key
        )

    @staticmethod
    def _series_id():
        return ReadingSession.source_id + literal(_SEP) + ReadingSession.series_key

    def _aggregates(self) -> list[Any]:
        """The five numbers every roll-up reports, in a fixed column order."""
        return [
            func.count().label("sessions"),
            func.coalesce(func.sum(ReadingSession.pages_read), 0).label("pages_read"),
            func.count(distinct(self._chapter_id())).label("chapters_read"),
            func.count(distinct(self._series_id())).label("series_read"),
            func.coalesce(func.sum(self._seconds()), 0).label("seconds_read"),
        ]

    @staticmethod
    def _roll(row) -> dict[str, int]:
        return {
            "sessions": int(row.sessions or 0),
            "pages_read": int(row.pages_read or 0),
            "chapters_read": int(row.chapters_read or 0),
            "series_read": int(row.series_read or 0),
            "seconds_read": int(row.seconds_read or 0),
        }

    # --- windows --------------------------------------------------------

    def _bounds(self, days: int) -> tuple[datetime, datetime, list[str]]:
        """UTC lower bound of the window, "now", and its dense day labels.

        The bound is computed in Python rather than in SQL so the window filter
        stays a plain ``started_at >= ?`` range predicate and keeps using
        ``ix_reading_sessions_started_at``; wrapping the column in ``strftime``
        to compare local days would make every window scan the whole table.
        """
        now_utc = utcnow()
        offset = timedelta(minutes=self._tz)
        today_local = (now_utc + offset).date()
        first_local = today_local - timedelta(days=days - 1)
        since_utc = datetime.combine(first_local, time.min) - offset
        labels = [(first_local + timedelta(days=i)).isoformat() for i in range(days)]
        return since_utc, now_utc, labels

    # --- queries --------------------------------------------------------

    def _totals(self) -> dict[str, Any]:
        row = self._db.execute(
            self._sessions(
                select(
                    *self._aggregates(),
                    func.min(ReadingSession.started_at).label("first_at"),
                    func.max(ReadingSession.started_at).label("last_at"),
                ).select_from(ReadingSession)
            )
        ).one()
        payload = self._roll(row)
        payload["first_session_at"] = _iso(row.first_at)
        payload["last_session_at"] = _iso(row.last_at)
        return payload

    def _window(self, since: datetime) -> dict[str, int]:
        row = self._db.execute(
            self._sessions(
                select(*self._aggregates()).select_from(ReadingSession)
            ).where(ReadingSession.started_at >= since)
        ).one()
        return self._roll(row)

    def _daily(self, since: datetime, labels: list[str]) -> list[dict[str, Any]]:
        day = self._day().label("day")
        rows = self._db.execute(
            self._sessions(
                select(day, *self._aggregates()).select_from(ReadingSession)
            )
            .where(ReadingSession.started_at >= since)
            .group_by(day)
        ).all()
        found = {r.day: self._roll(r) for r in rows}
        empty = {
            "sessions": 0,
            "pages_read": 0,
            "chapters_read": 0,
            "series_read": 0,
            "seconds_read": 0,
        }
        # Dense on purpose: a chart that only receives the days with data draws
        # a line straight through the gaps and turns a week off into a plateau.
        return [{"date": d, **(found.get(d) or dict(empty))} for d in labels]

    def _active_days(self) -> list[str]:
        """Every local day this profile read on, oldest first.

        DISTINCT is done by the database, so this returns one string per day the
        owner has ever read -- a few thousand rows after a decade, not the
        session table.
        """
        day = self._day().label("day")
        rows = self._db.execute(
            self._sessions(select(day).select_from(ReadingSession))
            .group_by(day)
            .order_by(day)
        ).all()
        return [r.day for r in rows if r.day]

    def _streak(self, active: list[str]) -> dict[str, Any]:
        """Current and longest run of consecutive active days.

        The current streak survives a day with no reading *today*: it stays
        alive while the last active day is today or yesterday, because zeroing
        it at midnight would report a broken streak to someone whose day has
        barely started. It is 0 once a whole day has been missed.
        """
        if not active:
            return {"current_days": 0, "longest_days": 0, "last_active_date": None}
        days = [datetime.strptime(d, "%Y-%m-%d").date() for d in active]
        longest = run = 1
        for prev, cur in zip(days, days[1:]):
            run = run + 1 if (cur - prev).days == 1 else 1
            longest = max(longest, run)
        today = (utcnow() + timedelta(minutes=self._tz)).date()
        current = run if (today - days[-1]).days <= 1 else 0
        return {
            "current_days": current,
            "longest_days": longest,
            "last_active_date": active[-1],
        }

    def _by_hour(self, since: datetime) -> list[dict[str, int]]:
        hour = self._hour().label("hour")
        rows = self._db.execute(
            self._sessions(
                select(
                    hour,
                    func.count().label("sessions"),
                    func.coalesce(func.sum(ReadingSession.pages_read), 0).label(
                        "pages_read"
                    ),
                    func.coalesce(func.sum(self._seconds()), 0).label("seconds_read"),
                ).select_from(ReadingSession)
            )
            .where(ReadingSession.started_at >= since)
            .group_by(hour)
        ).all()
        found = {int(r.hour): r for r in rows if r.hour is not None}
        out = []
        for h in range(24):
            r = found.get(h)
            out.append(
                {
                    "hour": h,
                    "sessions": int(r.sessions) if r else 0,
                    "pages_read": int(r.pages_read) if r else 0,
                    "seconds_read": int(r.seconds_read) if r else 0,
                }
            )
        return out

    def _by_source(self, since: datetime) -> list[dict[str, Any]]:
        names = {d.source_type: d.name for d in list_installed_connectors()}
        rows = self._db.execute(
            self._sessions(
                select(ReadingSession.source_id, *self._aggregates()).select_from(
                    ReadingSession
                )
            )
            .where(ReadingSession.started_at >= since)
            .group_by(ReadingSession.source_id)
            .order_by(func.sum(ReadingSession.pages_read).desc())
            .limit(_TOP_SOURCES)
        ).all()
        return [
            {
                "source_id": r.source_id,
                "name": names.get(r.source_id, r.source_id),
                **self._roll(r),
            }
            for r in rows
        ]

    def _by_series(self, since: datetime) -> list[dict[str, Any]]:
        # ``max()`` over title/cover is an aggregate only for SQL's sake: the
        # LEFT join matches at most one follow row per group, so the group's
        # rows all carry the same value (or NULL for a series no longer
        # followed, whose history still counts).
        rows = self._db.execute(
            self._sessions(
                select(
                    ReadingSession.source_id,
                    ReadingSession.series_key,
                    func.max(FollowedSeries.title).label("title"),
                    func.max(FollowedSeries.cover_url).label("cover_url"),
                    func.max(ReadingSession.started_at).label("last_read_at"),
                    *self._aggregates(),
                ).select_from(ReadingSession)
            )
            .where(ReadingSession.started_at >= since)
            .group_by(ReadingSession.source_id, ReadingSession.series_key)
            .order_by(func.sum(ReadingSession.pages_read).desc())
            .limit(_TOP_SERIES)
        ).all()
        out = []
        for r in rows:
            item = {
                "source_id": r.source_id,
                "series_key": r.series_key,
                "title": r.title,
                "cover_url": r.cover_url,
                "last_read_at": _iso(r.last_read_at),
            }
            item.update(self._roll(r))
            item.pop("series_read")  # always 1 inside a per-series group
            out.append(item)
        return out

    def _recent(self) -> list[dict[str, Any]]:
        """The last few sessions, deliberately *not* windowed.

        "Recent activity" that goes blank because the caller asked for a 7-day
        chart and last read a fortnight ago is worse than useless.
        """
        rows = self._db.execute(
            self._sessions(
                select(
                    ReadingSession.source_id,
                    ReadingSession.series_key,
                    ReadingSession.chapter_key,
                    ReadingSession.chapter_number,
                    ReadingSession.pages_read,
                    ReadingSession.started_at,
                    ReadingSession.ended_at,
                    self._seconds().label("seconds_read"),
                    FollowedSeries.title.label("title"),
                ).select_from(ReadingSession)
            )
            .order_by(ReadingSession.started_at.desc(), ReadingSession.id.desc())
            .limit(_RECENT_SESSIONS)
        ).all()
        return [
            {
                "source_id": r.source_id,
                "series_key": r.series_key,
                "chapter_key": r.chapter_key,
                "chapter_number": r.chapter_number,
                "title": r.title,
                "pages_read": int(r.pages_read or 0),
                "seconds_read": int(r.seconds_read or 0),
                "started_at": _iso(r.started_at),
                "ended_at": _iso(r.ended_at),
            }
            for r in rows
        ]

    def chapters_completed(self) -> int:
        """Chapters marked finished in ``chapter_progress`` for this profile.

        A different number from ``totals.chapters_read`` and both are honest:
        this one counts chapters *finished* (including ones finished before
        session recording existed, and ones synced from another device with no
        session attached), while ``chapters_read`` counts chapters an actual
        recorded session touched. Gated like everything else so the count does
        not move when a gated profile cannot see the chapters behind it.
        """
        stmt = (
            select(func.count())
            .select_from(ChapterProgress)
            .where(ChapterProgress.user_id == self._user_id)
            .where(ChapterProgress.is_completed.is_(True))
        )
        if self._profile_id is None:
            stmt = stmt.where(ChapterProgress.profile_id.is_(None))
        else:
            stmt = stmt.where(ChapterProgress.profile_id == self._profile_id)
        if not self._gate_open:
            stmt = stmt.outerjoin(
                FollowedSeries,
                and_(
                    FollowedSeries.user_id == ChapterProgress.user_id,
                    FollowedSeries.profile_id == ChapterProgress.profile_id,
                    FollowedSeries.source_id == ChapterProgress.source_id,
                    FollowedSeries.series_key == ChapterProgress.series_key,
                ),
            ).where(self._progress_mature_case() == 0)
        return int(self._db.execute(stmt).scalar_one() or 0)

    def _progress_mature_case(self):
        """:meth:`_mature_case` against ``chapter_progress``' source column."""
        mature_sources = sorted(
            d.source_type for d in list_installed_connectors() if d.mature
        )
        source_mature = (
            case((ChapterProgress.source_id.in_(mature_sources), 1), else_=0)
            if mature_sources
            else literal(0)
        )
        return case(
            (FollowedSeries.mature_override == 1, 1),
            (FollowedSeries.mature_override == 0, 0),
            (
                FollowedSeries.content_rating.is_not(None),
                case(
                    (mature_rating_predicate(FollowedSeries.content_rating), 1),
                    else_=0,
                ),
            ),
            else_=source_mature,
        )

    # --- public ---------------------------------------------------------

    def build(self, days: int) -> dict[str, Any]:
        since, now, labels = self._bounds(days)
        return {
            "range": {
                "days": days,
                "since": _iso(since),
                "until": _iso(now),
                "timezone_offset_minutes": self._tz,
                "session_cap_seconds": SESSION_SECONDS_CAP,
            },
            "totals": self._totals(),
            "window": self._window(since),
            "streak": self._streak(self._active_days()),
            "daily": self._daily(since, labels),
            "by_hour": self._by_hour(since),
            "by_source": self._by_source(since),
            "by_series": self._by_series(since),
            "recent_sessions": self._recent(),
        }
