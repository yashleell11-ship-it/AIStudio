"""The chapter-list parse memo may save time, never serve a stale list.

``source_series_cache.chapters`` is JSON, and every read of a series parses it.
Measured on the VPS, novelarchive's "Shadow Slave" is 3,174 chapters / 314 KB
and ``json.loads`` was 9.4 ms of the 9.5 ms a CACHE HIT on /novels/chapter
cost — the whole request, for a row that had not changed.

Memoizing a parse is exactly the kind of optimisation that changes what an
endpoint returns if it is keyed wrong, so these tests pin the answer rather
than the speed: a refreshed chapter list must be visible immediately, and a
caller must not be able to corrupt a later request by mutating what it got.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from core.time_utils import utcnow
from database.models import SourceSeriesCache
from services import source_cache_service as scs


def _chapters(n: int, *, prefix: str = "ch") -> str:
    return json.dumps(
        [
            {
                "key": f"{prefix}-{i}",
                "number": float(i),
                "title": f"Chapter {i}",
                "published_at": None,
                "page_count": 0,
            }
            for i in range(1, n + 1)
        ]
    )


@pytest.fixture(autouse=True)
def _clean_memo():
    scs.reset_chapter_memo()
    yield
    scs.reset_chapter_memo()


def _row(chapters: str, *, fetched=None, source="src", key="series") -> SourceSeriesCache:
    row = SourceSeriesCache(source_id=source, series_key=key)
    row.chapters = chapters
    row.fetched_at = fetched or utcnow()
    return row


def test_the_same_row_parses_once() -> None:
    raw = _chapters(5)
    row = _row(raw)
    first = scs._memoized_chapters(row)
    second = scs._memoized_chapters(row)
    assert first == second
    assert [c["key"] for c in first] == [f"ch-{i}" for i in range(1, 6)]


def test_a_refreshed_chapter_list_is_served_immediately() -> None:
    """The invariant: a new chapter must not wait behind a cached parse."""
    row = _row(_chapters(3))
    assert len(scs._memoized_chapters(row)) == 3

    # What _upsert does when a connector returns a longer list.
    row.chapters = _chapters(4)
    row.fetched_at = row.fetched_at + timedelta(seconds=1)

    assert len(scs._memoized_chapters(row)) == 4
    assert scs._memoized_chapters(row)[-1]["key"] == "ch-4"


def test_a_rewrite_of_the_same_length_is_not_confused_for_the_old_one() -> None:
    """Same chapter count, different keys — the memo must not reuse the parse."""
    row = _row(_chapters(3, prefix="old"))
    assert scs._memoized_chapters(row)[0]["key"] == "old-1"

    row.chapters = _chapters(3, prefix="new")
    row.fetched_at = row.fetched_at + timedelta(seconds=1)

    assert scs._memoized_chapters(row)[0]["key"] == "new-1"


def test_two_series_do_not_share_a_parse() -> None:
    a = _row(_chapters(2, prefix="a"), key="series-a")
    b = _row(_chapters(2, prefix="b"), key="series-b")
    assert scs._memoized_chapters(a)[0]["key"] == "a-1"
    assert scs._memoized_chapters(b)[0]["key"] == "b-1"


def test_two_sources_with_the_same_series_key_do_not_share_a_parse() -> None:
    fetched = utcnow()
    a = _row(_chapters(2, prefix="a"), fetched=fetched, source="one", key="same")
    b = _row(_chapters(2, prefix="b"), fetched=fetched, source="two", key="same")
    assert scs._memoized_chapters(a)[0]["key"] == "a-1"
    assert scs._memoized_chapters(b)[0]["key"] == "b-1"


def test_a_caller_cannot_corrupt_the_memo_by_mutating_its_list() -> None:
    row = _row(_chapters(3))
    got = scs._memoized_chapters(row)
    got.reverse()
    got.pop()
    assert [c["key"] for c in scs._memoized_chapters(row)] == [
        "ch-1",
        "ch-2",
        "ch-3",
    ]


def test_an_empty_or_broken_chapter_list_is_not_memoized_as_content() -> None:
    assert scs._memoized_chapters(_row("")) == []
    assert scs._memoized_chapters(_row("not json")) == []
    assert scs._memoized_chapters(_row('{"not": "a list"}')) == []


def test_the_memo_is_bounded_by_total_chapters(monkeypatch) -> None:
    monkeypatch.setattr(scs, "_CHAPTER_MEMO_MAX_CHAPTERS", 10)
    for i in range(6):
        scs._memoized_chapters(_row(_chapters(4), key=f"series-{i}"))
    with scs._chapter_memo_lock:
        held = sum(len(v) for v in scs._chapter_memo.values())
    assert held <= 10, held


def test_serialize_goes_through_the_memo() -> None:
    """The wiring, not just the helper — _serialize is what every read uses."""
    row = _row(_chapters(3))
    payload = scs.SourceCacheService._serialize(row)
    assert [c["key"] for c in payload["chapters"]] == ["ch-1", "ch-2", "ch-3"]

    row.chapters = _chapters(5)
    row.fetched_at = row.fetched_at + timedelta(seconds=1)
    assert len(scs.SourceCacheService._serialize(row)["chapters"]) == 5
