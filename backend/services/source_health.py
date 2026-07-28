"""Per-source reachability: recording it, reading it, and deciding demotion.

Roughly 100 of the ~151 installed connectors are dead. Nothing recorded that,
so the owner found out only when a followed series quietly stopped updating.
This module owns the whole story: what counts as a failure, when a row is worth
writing, and when a source has failed often enough to be pushed down the search
results and flagged in listings.

Health is **global** -- a site being down is a property of the site, not of the
account that searched while it was down. It is not globally *disclosed*: callers
build their payloads from their own mature-gated descriptor list and look health
up per source, so a mature source's row never reaches a profile that cannot see
the source (see :func:`states_for`).

Write policy (why the search fan-out does not write on every search)
-------------------------------------------------------------------
The database is SQLite with a single writer that page reads already contend
with, and the fan-out probes *every* source on *every* search. Writing an
outcome per source per search would mean ~151 UPDATEs per search forever, with
the dead majority contributing most of them.

Instead a row is written only when the write would change something a reader can
observe:

* the source has no row yet (first observation),
* the outcome flips the state (ok -> failing, failing -> ok), or
* the streak is still climbing towards the thresholds below.

Skipping the rest is safe precisely because in those cases the stored state
already equals the observed state -- a healthy source that succeeded again, or a
long-dead source that failed again, has nothing new to say. The steady state is
therefore **zero writes per search**; a genuine state change costs one commit
covering every source that moved.

The one thing lost is timestamp precision: ``last_ok_at`` / ``last_checked_at``
would otherwise freeze at the last state change, so :data:`REFRESH_INTERVAL`
forces a refresh of an otherwise-unchanged row. Read those two columns as
"accurate to within that interval", not to the second.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.time_utils import utcnow
from database.models import SourceHealth

logger = logging.getLogger(__name__)

# --- status vocabulary -------------------------------------------------------
#: Answered on its last probe.
STATUS_OK = "ok"
#: Failing, but not yet often enough to be demoted.
STATUS_FAILING = "failing"
#: Failing long enough to be treated as dead (still listed, never hidden).
STATUS_DEAD = "dead"
#: Never probed. A real third state, not a synonym for "ok" or for "failing":
#: a source installed since the last search has no evidence either way, and
#: presenting that as healthy is how ~100 dead connectors stayed invisible.
STATUS_UNKNOWN = "unknown"

# --- thresholds --------------------------------------------------------------
# Consecutive failed probes before a source is demoted in search ordering and
# flagged in listings.
#
# 3, not 1: the fan-out probes every installed source on an 8s budget over a
# home connection, so a single miss is routinely transient -- one Cloudflare
# challenge, one DNS blip, one timeout while 151 requests go out at once.
# Demoting on the first miss would reshuffle the search screen at random. Three
# misses means three *separate* searches with no answer at all.
DEMOTE_AFTER_FAILURES = 3
# The stronger flag: not "flaky", "gone". Ten separate searches without a single
# answer is not a bad afternoon, and this is where the ~100 known-dead
# connectors are expected to sit permanently. Demotion is already in force well
# before this; the second tier exists so the status page can distinguish
# "worth a look" from "delete it".
DEAD_AFTER_FAILURES = 10
# The streak stops counting here. Past the point where the number changes no
# decision, incrementing it would cost one write per dead source per search,
# forever -- precisely the hot-path write this design exists to avoid. How long
# a source has been down is read off last_ok_at, which does not saturate.
MAX_STREAK = DEAD_AFTER_FAILURES
# One success clears the streak, so a source that comes back is un-demoted by
# the very search that finds it working -- no operator action, no cooldown.
# Requiring a *streak* of successes was rejected: it would keep a working source
# buried while proving something the next failure would re-arm instantly anyway.

#: How stale ``last_checked_at`` may get on a row whose state has not moved.
#: Bounds the "nothing changed" write cost at one commit per 6h across the whole
#: registry, instead of one per search.
REFRESH_INTERVAL = timedelta(hours=6)

#: Error text is a diagnostic, not a payload: keep a readable line, drop the
#: 200KB Cloudflare interstitial some connectors raise with.
ERROR_MAX_CHARS = 500

#: "Worst first" ordering for the status page. Unknown sits between failing and
#: ok on purpose: never probed is a thing to go look at, not a clean bill.
_SEVERITY: dict[str, int] = {
    STATUS_DEAD: 0,
    STATUS_FAILING: 1,
    STATUS_UNKNOWN: 2,
    STATUS_OK: 3,
}


@dataclass(frozen=True, slots=True)
class SourceHealthState:
    """Immutable snapshot of one source's health.

    A snapshot rather than the ORM row because callers read it *after* the
    recording commit, and because "no row yet" has to be representable
    (:func:`unknown_state`) without inventing a row for every unprobed source.
    """

    source_id: str
    status: str
    consecutive_failures: int
    last_ok_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    last_checked_at: datetime | None = None

    @property
    def demoted(self) -> bool:
        """Whether search ordering should push this source down."""
        return self.consecutive_failures >= DEMOTE_AFTER_FAILURES

    @property
    def severity(self) -> int:
        """Sort key for worst-first listings (lower == worse)."""
        return _SEVERITY.get(self.status, _SEVERITY[STATUS_UNKNOWN])

    def payload(self) -> dict[str, object]:
        """Client-facing block. Timestamps are ISO-8601 UTC or ``null``."""
        return {
            "status": self.status,
            "consecutive_failures": self.consecutive_failures,
            "demoted": self.demoted,
            "last_ok_at": _iso(self.last_ok_at),
            "last_error_at": _iso(self.last_error_at),
            "last_error": self.last_error,
            "last_checked_at": _iso(self.last_checked_at),
        }


def unknown_state(source_id: str) -> SourceHealthState:
    """The state of a source that has never been probed."""
    return SourceHealthState(
        source_id=source_id, status=STATUS_UNKNOWN, consecutive_failures=0
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _classify(row: SourceHealth) -> str:
    if row.consecutive_failures >= DEAD_AFTER_FAILURES:
        return STATUS_DEAD
    if row.consecutive_failures > 0:
        return STATUS_FAILING
    # A row only exists because something observed the source, so zero failures
    # means the last observation succeeded. The last_ok_at guard is for rows
    # written by hand or by a restore, where that is not guaranteed.
    return STATUS_OK if row.last_ok_at is not None else STATUS_UNKNOWN


def _snapshot(row: SourceHealth) -> SourceHealthState:
    return SourceHealthState(
        source_id=row.source_id,
        status=_classify(row),
        consecutive_failures=int(row.consecutive_failures or 0),
        last_ok_at=row.last_ok_at,
        last_error_at=row.last_error_at,
        last_error=row.last_error,
        last_checked_at=row.last_checked_at,
    )


def load_states(db: Session | None) -> dict[str, SourceHealthState]:
    """Every recorded health row, keyed by source id.

    One query for the whole (at most ~151-row) table: the callers need health
    for every source they are about to list anyway, so a per-source lookup would
    only multiply reads against the single-writer database.
    """
    if db is None:
        return {}
    try:
        rows = db.execute(select(SourceHealth)).scalars().all()
    except SQLAlchemyError:
        # Health is diagnostic metadata; losing it must never fail a search or
        # a source listing (e.g. a database that predates the migration).
        logger.warning("source health unavailable; continuing without it", exc_info=True)
        db.rollback()
        return {}
    return {row.source_id: _snapshot(row) for row in rows}


def states_for(
    states: Mapping[str, SourceHealthState], source_ids: Iterable[str]
) -> dict[str, SourceHealthState]:
    """Health for exactly ``source_ids``, filling in unknowns.

    This is the no-leak seam: callers pass the source ids their *own* mature
    gate resolved, so health for a source they cannot see is never selected out
    of the global table.
    """
    return {
        source_id: states.get(source_id) or unknown_state(source_id)
        for source_id in source_ids
    }


def _is_stale(row: SourceHealth, now: datetime) -> bool:
    """Whether an otherwise-unchanged row is due its periodic refresh."""
    if row.last_checked_at is None:
        return True
    return (now - row.last_checked_at) >= REFRESH_INTERVAL


def _should_persist(row: SourceHealth | None, ok: bool, now: datetime) -> bool:
    """Whether this outcome is worth a write. See the module docstring."""
    if row is None:
        return True  # first observation of this source
    if ok:
        # Recovery is a state change; a repeat success is not.
        return row.consecutive_failures > 0 or _is_stale(row, now)
    if row.consecutive_failures == 0:
        return True  # ok -> failing
    if row.consecutive_failures < MAX_STREAK:
        return True  # streak still climbing towards the thresholds
    # Already saturated: this failure changes nothing a reader can observe.
    return _is_stale(row, now)


def record_outcomes(
    db: Session | None,
    results: Mapping[str, str | None],
    *,
    now: datetime | None = None,
) -> dict[str, SourceHealthState]:
    """Record one probe per source and return the resulting states.

    ``results`` maps source id to ``None`` for success or a one-line error
    message for failure. Returns the post-outcome state of every source in
    ``results`` -- including the ones no write was needed for, whose stored
    state already matched.

    Writes are batched into a single commit. Callers pass their request-scoped
    session, which at this point has only read; nothing else is pending to be
    committed by surprise. A failed write is logged and swallowed: recording
    diagnostics must not turn a working search into a 500.
    """
    if db is None or not results:
        return {}

    now = now or utcnow()
    try:
        rows = {
            row.source_id: row
            for row in db.execute(
                select(SourceHealth).where(SourceHealth.source_id.in_(list(results)))
            ).scalars()
        }
    except SQLAlchemyError:
        logger.warning("source health not recorded (read failed)", exc_info=True)
        db.rollback()
        return {}

    states: dict[str, SourceHealthState] = {}
    written = 0
    for source_id, error in results.items():
        row = rows.get(source_id)
        ok = error is None
        if _should_persist(row, ok, now):
            if row is None:
                row = SourceHealth(source_id=source_id, consecutive_failures=0)
                db.add(row)
            row.last_checked_at = now
            if ok:
                row.last_ok_at = now
                row.consecutive_failures = 0
            else:
                row.last_error_at = now
                row.last_error = (error or "")[:ERROR_MAX_CHARS] or None
                row.consecutive_failures = min(
                    int(row.consecutive_failures or 0) + 1, MAX_STREAK
                )
            written += 1
        # Snapshot BEFORE the commit: a rollback below would expire (or discard)
        # the ORM objects, and this response still wants the state it observed.
        states[source_id] = _snapshot(row) if row is not None else unknown_state(source_id)

    if written:
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.warning(
                "source health not recorded (%d row(s) rolled back)",
                written,
                exc_info=True,
            )
    return states


def summarize(states: Iterable[SourceHealthState]) -> dict[str, int]:
    """Counts by status for a status page, plus how many are demoted.

    Callers pass the states of the sources *they* can see, so the summary is
    scoped by the caller's mature gate like everything else.
    """
    counts = {
        "total": 0,
        STATUS_OK: 0,
        STATUS_FAILING: 0,
        STATUS_DEAD: 0,
        STATUS_UNKNOWN: 0,
        "demoted": 0,
    }
    for state in states:
        counts["total"] += 1
        counts[state.status] = counts.get(state.status, 0) + 1
        if state.demoted:
            counts["demoted"] += 1
    return counts
