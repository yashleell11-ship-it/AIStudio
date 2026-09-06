"""AUDIT (IDX-6): OCR dialogue search scopes in Python, not in SQL.

``chapter_ocr`` is one GLOBAL table shared by every profile. ``search`` ran a
single FTS query across all of it, selecting ``c.full_text`` for every hit, and
only then dropped the rows whose series the caller does not follow. So a search
read — and built a Python string for — every OTHER profile's chapter transcript
before throwing almost all of them away, on a 2-vCPU box with a small disk.

Two properties are pinned here:
  * the scope predicate reaches SQLite (the followed key is a bound parameter
    of the statement that scans the index), and
  * ``full_text`` is only ever selected by a windowed statement, so the text of
    a chapter outside the result page never leaves the database.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import event

from database.models import ChapterOcr
from services.ocr_search import OcrSearchService

SRC = "mangadex"
MINE = "series-i-follow"
TERM = "zenithward"


@dataclass
class _Statement:
    sql: str
    params: object

    @property
    def flat_params(self) -> list[object]:
        if isinstance(self.params, dict):
            return list(self.params.values())
        if isinstance(self.params, (list, tuple)):
            return list(self.params)
        return [self.params]


class _FollowedStub:
    """Just the two members ``OcrSearchService`` uses of the real service."""

    def __init__(self, user_id: int, pairs: list[tuple[str, str]]) -> None:
        self._user_id = user_id
        self._pairs = pairs

    def list_series(self, **_kwargs) -> dict[str, object]:
        return {
            "items": [{"source_id": s, "series_key": k} for s, k in self._pairs]
        }


@pytest.fixture
def seeded(db_session):
    """One followed chapter plus a corpus of chapters the caller never follows."""
    db_session.add(
        ChapterOcr(
            source_id=SRC,
            series_key=MINE,
            chapter_key="ch-1",
            full_text=f"the {TERM} knight said hello",
            word_count=100,
        )
    )
    for i in range(12):
        db_session.add(
            ChapterOcr(
                source_id=SRC,
                series_key=f"someone-elses-series-{i}",
                chapter_key=f"ch-{i}",
                # Higher word_count, so ORDER BY word_count DESC puts every one
                # of them ahead of the row the caller is allowed to see.
                full_text=f"a {TERM} line nobody here may read " * 40,
                word_count=1_000 + i,
            )
        )
    db_session.commit()
    return db_session


def test_search_scopes_and_windows_in_sql(db_engine, seeded):
    service = OcrSearchService(seeded, _FollowedStub(1, [(SRC, MINE)]))

    captured: list[_Statement] = []

    @event.listens_for(db_engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        captured.append(_Statement(statement, parameters))

    try:
        result = service.search(TERM, limit=5)
    finally:
        event.remove(db_engine, "before_cursor_execute", _record)

    # Behaviour is unchanged: still exactly the one chapter the caller follows.
    assert result["total"] == 1
    assert [i["series_key"] for i in result["items"]] == [MINE]

    fts = [s for s in captured if "chapter_ocr_fts" in s.sql]
    assert fts, "no FTS statement was executed"

    unscoped = [s for s in fts if MINE not in s.flat_params]
    assert not unscoped, (
        "FTS statement scanned the global corpus with no scope predicate: "
        f"{[s.sql for s in unscoped]}"
    )

    unbounded_text = [
        s for s in fts if "full_text" in s.sql.lower() and "limit" not in s.sql.lower()
    ]
    assert not unbounded_text, (
        "full_text was selected without a window, so out-of-page transcripts "
        f"were read off disk: {[s.sql for s in unbounded_text]}"
    )
