"""AUDIT (caches shard, CACHE-7 + CACHE-4's other half): the novel cache wrote
on every read, and evicted by loading the blobs it was deleting.

CACHE-7. ``NovelService._respond`` stamped ``last_used_at`` and committed on
every single chapter read, unlike the cover cache beside it, which has bumped
at most hourly since it was written. Reading a novel therefore took the
single-writer database's write lock once per page turn to record something the
eviction order cannot even distinguish at that resolution -- and the reader is
the one path in the app that turns pages in a tight loop.

CACHE-4. ``_evict_lru`` selected whole ``NovelChapterCache`` entities to hand
to ``Session.delete``. ``paragraphs`` reaches 645 KB on that table, so trimming
to the cap pulled the whole excess into the process purely to throw it away.

Both rules are pinned as SQL rather than timing: on a fast machine a wall-clock
assertion passes while the blob is still being read, and the blob read is the
finding.
"""

from __future__ import annotations

from sqlalchemy import event

from database.models import NovelChapterCache
from tests.test_novel_chapter_cache import (  # noqa: F401 - fixtures by import
    SERIES,
    STUB_SOURCE,
    _seed_row,
    _svc,
    novels_on,
    stub_registered,
)


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

    def starting(self, verb: str, table: str) -> list[str]:
        return [
            s
            for s in self.seen
            if s.lstrip().upper().startswith(verb) and table in s
        ]


def test_a_warm_chapter_read_twice_writes_once(db_session, novels_on):
    """The second read of a chapter already read this hour writes nothing."""
    _seed_row(db_session, used_minutes_ago=180.0)
    service = _svc(db_session)

    service.get_chapter(STUB_SOURCE, SERIES, "ch-2")  # stale stamp: bumps
    db_session.expire_all()
    watch = _Statements(db_session)
    try:
        service.get_chapter(STUB_SOURCE, SERIES, "ch-2")
    finally:
        watch.stop()

    assert watch.starting("UPDATE", "novel_chapter_cache") == [], (
        "a chapter read again within the throttle window still took the "
        "write lock to move a stamp nothing can read at that resolution"
    )


def test_a_chapter_not_touched_for_hours_still_moves_up_the_order(
    db_session, novels_on
):
    """The throttle must not freeze the eviction order it exists to serve."""
    _seed_row(db_session, used_minutes_ago=180.0)
    before = db_session.get(
        NovelChapterCache, (STUB_SOURCE, SERIES, "ch-2")
    ).last_used_at

    _svc(db_session).get_chapter(STUB_SOURCE, SERIES, "ch-2")

    after = db_session.get(
        NovelChapterCache, (STUB_SOURCE, SERIES, "ch-2")
    ).last_used_at
    assert after > before


def test_eviction_never_reads_the_paragraphs_it_deletes(
    db_session, novels_on, monkeypatch
):
    from core.config import get_settings

    monkeypatch.setenv("MM_NOVEL_CACHE_MAX_ROWS", "1")
    get_settings.cache_clear()
    try:
        for n, key in enumerate(("ch-1", "ch-2", "ch-3")):
            _seed_row(db_session, chapter_key=key, used_minutes_ago=100.0 - n)
        db_session.commit()

        service = _svc(db_session)
        watch = _Statements(db_session)
        try:
            service._evict_lru(1)
        finally:
            watch.stop()

        read_blobs = [
            s
            for s in watch.starting("SELECT", "novel_chapter_cache")
            if "paragraphs" in s
        ]
        assert read_blobs == [], (
            f"eviction SELECTed the chapter text it was deleting: {read_blobs}"
        )
    finally:
        get_settings.cache_clear()
