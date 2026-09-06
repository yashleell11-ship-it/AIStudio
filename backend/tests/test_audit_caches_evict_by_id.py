"""AUDIT (caches shard, CACHE-4): eviction reads the rows it is deleting.

``SourceCacheService._evict_oldest`` selected whole ORM entities
(``select(model).order_by(fetched_at)``) purely to hand them to
``Session.delete``. Every column comes back over that statement, including the
two blobs these tables exist to hold: ``source_series_cache.chapters`` (314 KB
for novelarchive's "Shadow Slave", 3,174 entries) and
``source_browse_cache.payload``. So trimming a table to its cap first pulled
the whole excess into the process — on a 2-vCPU, 20 GB VPS, inside the browse
request that triggered it.

Nothing about a delete needs the row. ``_evict_cover_bytes_to_budget`` in the
same module already selects key columns only (its rows are images, so the cost
was noticed there first); these two paths just never got the same treatment.

The rule pinned here is deliberately about the SQL, not the timing: a
wall-clock assertion would pass on a fast machine with the blob still being
read, and the blob read is the finding.
"""

from __future__ import annotations

import json

from sqlalchemy import event, func, select

from database.models import SourceBrowseCache, SourceSeriesCache
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse

SRC = "asurascans"
#: Big enough that reading one is obviously not free, small enough to seed fast.
_FAT_CHAPTERS = json.dumps([{"key": f"c{n}", "number": n} for n in range(2000)])


class _Statements:
    """Every SQL statement the session emits, as text."""

    def __init__(self, db) -> None:
        self.seen: list[str] = []
        self._engine = db.get_bind()
        event.listen(self._engine, "before_cursor_execute", self._record)

    def _record(self, _conn, _cursor, statement, *_args) -> None:
        self.seen.append(statement)

    def stop(self) -> None:
        event.remove(self._engine, "before_cursor_execute", self._record)

    def reading(self, column: str) -> list[str]:
        return [s for s in self.seen if s.lstrip().upper().startswith("SELECT") and column in s]


def _seed_series(db, count: int) -> None:
    for n in range(count):
        db.add(
            SourceSeriesCache(
                source_id=SRC,
                series_key=f"k{n}",
                title=f"T{n}",
                chapters=_FAT_CHAPTERS,
            )
        )
    db.commit()


def _seed_browse(db, count: int) -> None:
    for n in range(count):
        db.add(
            SourceBrowseCache(
                source_id=SRC,
                sort="",
                genre="",
                page=n,
                payload=json.dumps({"items": [{"id": f"k{n}"}] * 200}),
            )
        )
    db.commit()


def _count(db, model) -> int:
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_trimming_the_series_cache_never_reads_the_chapter_blobs(db_session):
    _seed_series(db_session, 10)
    svc = SourceCacheService(db_session, FakeBrowse())

    spy = _Statements(db_session)
    try:
        svc._evict_oldest(SourceSeriesCache, 4)
        db_session.commit()
    finally:
        spy.stop()

    assert _count(db_session, SourceSeriesCache) == 4  # premise: it did evict
    assert spy.reading("chapters") == [], (
        "eviction SELECTed the chapter blobs of the rows it was deleting: "
        f"{spy.reading('chapters')}"
    )


def test_trimming_the_browse_cache_never_reads_the_page_payloads(db_session):
    _seed_browse(db_session, 10)
    svc = SourceCacheService(db_session, FakeBrowse())

    spy = _Statements(db_session)
    try:
        svc._evict_oldest(SourceBrowseCache, 4)
        db_session.commit()
    finally:
        spy.stop()

    assert _count(db_session, SourceBrowseCache) == 4
    assert spy.reading("payload") == [], (
        f"eviction SELECTed the cached page payloads: {spy.reading('payload')}"
    )


def test_the_rows_it_drops_are_still_the_oldest_ones(db_session):
    """The point of the delete is unchanged: oldest ``fetched_at`` first."""
    _seed_series(db_session, 6)
    # Age them in insertion order so "oldest" is decidable.
    for n, row in enumerate(
        db_session.execute(
            select(SourceSeriesCache).order_by(SourceSeriesCache.series_key)
        ).scalars()
    ):
        row.fetched_at = row.fetched_at.replace(year=2020 + n)
    db_session.commit()

    svc = SourceCacheService(db_session, FakeBrowse())
    svc._evict_oldest(SourceSeriesCache, 2)
    db_session.commit()

    left = sorted(
        db_session.execute(select(SourceSeriesCache.series_key)).scalars().all()
    )
    assert left == ["k4", "k5"], left
