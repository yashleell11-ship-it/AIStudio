"""Per-source scheduling and pacing for the download queue.

Two rules, both about the same thing: a bulk run must go as fast as each site
will tolerate, and no faster.

**Spread.** The dispatcher used to take the top N pending rows by priority
alone. Queue 100 series from one source and all N workers land on that one
host at once, while every other source sits idle -- the slowest possible
arrangement *and* the one most likely to get the server blocked. Selection is
now round-robin across sources, so N workers mean N sources in flight.

**Pace.** Connector *metadata* calls have always been rate limited
(``SyncConnectorHttpClient._rate_limit``), with per-site intervals tuned per
connector. Page-image fetches went straight to ``httpx`` and inherited none of
it, which is where the real request volume is: a chapter is dozens to hundreds
of images. The same per-site interval now governs both, so a site's known
politeness budget is actually honoured on the path that spends it.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Protocol

#: Chapters in flight per source. Above this a single site sees the whole
#: worker pool; the point of the spread is that it does not.
DEFAULT_PER_SOURCE_LIMIT = 2

#: Fallback pacing when a connector declares no interval of its own. Matches
#: SyncConnectorHttpClient's default so both paths agree by default.
DEFAULT_MIN_INTERVAL = 0.21


class HasSource(Protocol):
    """Just enough of a ``Download`` row to schedule it."""

    id: int
    source: str


def select_round_robin(
    pending: Sequence[HasSource],
    *,
    available: int,
    per_source_limit: int = DEFAULT_PER_SOURCE_LIMIT,
    in_flight: Iterable[str] = (),
) -> list[int]:
    """Pick up to ``available`` download ids, spread across sources.

    ``pending`` must already be in the queue's own order (priority, then age);
    within a source that order is preserved exactly, so priority still decides
    which chapter of a source goes next. What changes is only how many of one
    source may run at once.

    ``in_flight`` is the sources already downloading, counted against the same
    per-source limit -- otherwise each dispatch pass would top every source
    back up to the limit and the cap would not hold.
    """
    if available <= 0 or per_source_limit <= 0:
        return []

    counts: defaultdict[str, int] = defaultdict(int)
    for source in in_flight:
        counts[source] += 1

    # Deal one round at a time: one chapter from each eligible source, then
    # around again. A source that is already at its limit is skipped rather
    # than blocking the sources behind it.
    by_source: defaultdict[str, list[HasSource]] = defaultdict(list)
    order: list[str] = []
    for item in pending:
        if item.source not in by_source:
            order.append(item.source)
        by_source[item.source].append(item)

    picked: list[int] = []
    while len(picked) < available:
        progressed = False
        for source in order:
            if len(picked) >= available:
                break
            if counts[source] >= per_source_limit:
                continue
            queue = by_source[source]
            if not queue:
                continue
            picked.append(queue.pop(0).id)
            counts[source] += 1
            progressed = True
        if not progressed:
            break

    return picked


class SourcePacer:
    """Least-recent-request clock per source, shared by every worker.

    One lock per source rather than one global lock: pacing asurascans must
    never make a worker on toonily wait. Sleeping happens outside the shared
    map so two sources genuinely overlap.
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()

    def _lock_for(self, source: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(source)
            if lock is None:
                lock = threading.Lock()
                self._locks[source] = lock
            return lock

    def wait(self, source: str, min_interval: float) -> float:
        """Block until ``source`` may be hit again. Returns seconds slept."""
        if min_interval <= 0:
            return 0.0

        lock = self._lock_for(source)
        with lock:
            now = time.monotonic()
            last = self._last.get(source, 0.0)
            elapsed = now - last
            delay = min_interval - elapsed
            if delay > 0:
                time.sleep(delay)
            else:
                delay = 0.0
            self._last[source] = time.monotonic()
            return delay


#: Process-wide pacer. The download workers share one so the interval is a
#: property of the *site*, not of whichever thread happens to reach it.
_PACER = SourcePacer()


def pace_source(source: str, min_interval: float = DEFAULT_MIN_INTERVAL) -> float:
    """Honour ``source``'s minimum request interval before the next fetch."""
    return _PACER.wait(source, min_interval)


def connector_min_interval(connector: object, default: float = DEFAULT_MIN_INTERVAL) -> float:
    """The interval a connector already declares for its own metadata calls.

    Read off the connector rather than configured separately: the per-site
    values were tuned once (nhentai 1.25s, asmhentai 0.5s, and so on) and the
    image path should spend the same budget, not a second one invented here.
    """
    client = getattr(connector, "_client", None) or getattr(connector, "client", None)
    interval = getattr(client, "_min_interval", None)
    if isinstance(interval, (int, float)) and interval > 0:
        return float(interval)
    return default
