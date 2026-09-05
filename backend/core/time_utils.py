"""Shared UTC timestamp helper.

``datetime.utcnow()`` is deprecated (Python 3.12+) in favour of timezone-aware
``datetime.now(timezone.utc)``. Every timestamp column in this project is a
naive SQLite ``DATETIME`` representing UTC (no ``timezone=True``), so we
compute the correct instant via the non-deprecated API and then drop the
tzinfo before it touches the ORM -- this keeps every existing comparison
(naive vs. naive) working exactly as before while silencing the deprecation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive ``datetime`` (matches existing DB columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


#: How far a client's own clock may run AHEAD of the server before we stop
#: believing it. Client clocks are load-bearing here — bookmarks order edits by
#: them (last-write-wins) and progress breaks position ties with them — so a
#: device whose clock says 2030 does not just record one odd timestamp: it
#: writes a stored value nothing can ever beat, and every later edit from every
#: device loses to it for the next four years. Five minutes is wider than any
#: real NTP drift and narrower than any wedge.
MAX_CLIENT_CLOCK_SKEW = timedelta(minutes=5)


def to_naive_utc(value: datetime | None) -> datetime | None:
    """A client clock, forced into the naive-UTC the DB columns hold.

    Every timestamp column here is a naive SQLite ``DATETIME`` meaning UTC
    (see :func:`utcnow`), while a client is free to send
    ``2026-09-05T10:00:00Z`` or ``+05:30``. Comparing an aware datetime with a
    naive one is a ``TypeError``, so an offline flush carrying a normal
    ISO-8601 timestamp would 500 in the middle of the merge -- convert at the
    boundary, once, and everything downstream stays naive.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def clamp_client_clock(
    value: datetime | None, *, now: datetime | None = None
) -> datetime | None:
    """A client-supplied instant, normalized and capped at ``now + skew``.

    Timestamps from the *past* pass through untouched: that is the entire
    point of letting a client stamp its own writes, so a week-old offline push
    is recorded as a week old instead of as "whenever the flush happened".
    Only the future is refused, and only past :data:`MAX_CLIENT_CLOCK_SKEW` --
    see there for what an unclamped future timestamp does to a
    last-write-wins column.
    """
    stamp = to_naive_utc(value)
    if stamp is None:
        return None
    ceiling = (now or utcnow()) + MAX_CLIENT_CLOCK_SKEW
    return min(stamp, ceiling)
