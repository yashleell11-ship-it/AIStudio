"""A progress batch reads its rows once, and returns exactly what it stored.

``_apply_one`` looked its row up with its own SELECT, so a 200-item offline
sync (the route's cap) issued 200 point queries before writing anything, then
``refresh()``d each written row for another 200. Measured on the VPS against
the production database, a 50-item batch was 170 statements.

The invariants a batch prefetch can break are the two the merge depends on:

* **furthest-wins** must survive — including for two pushes to the SAME
  chapter inside one batch, which used to see each other through the per-item
  SELECT + flush and now must see each other through the shared row map;
* the returned payload must still be the STORED row, not the pushed values.
"""

from __future__ import annotations


import pytest
from sqlalchemy import func, select

from core.time_utils import utcnow
from database.models import ChapterProgress
from services.progress_service import ProgressInput, ProgressService


@pytest.fixture
def owner(make_user):
    return make_user("progress-batch-owner")


@pytest.fixture
def profile(make_profile, owner):
    return make_profile(owner.id, "Main")


@pytest.fixture
def sibling_profile(make_profile, owner):
    return make_profile(owner.id, "Sibling", sort_order=1)


def _svc(db, user, prof) -> ProgressService:
    return ProgressService(db, user_id=user.id, profile_id=prof.id)


def _push(chapter: str, page: int, **kw) -> ProgressInput:
    return ProgressInput(
        source_id="src",
        series_key="series",
        chapter_key=chapter,
        last_page=page,
        page_count=kw.pop("page_count", 20),
        **kw,
    )


def test_a_batch_stores_every_item(db_session, owner, profile) -> None:
    svc = _svc(db_session, owner, profile)
    result = svc.save_batch([_push(f"c{i}", i + 1) for i in range(10)])

    assert result["saved"] == 10
    assert {item["chapter_key"] for item in result["items"]} == {
        f"c{i}" for i in range(10)
    }
    assert [item["last_page"] for item in result["items"]] == list(range(1, 11))
    stored = db_session.execute(
        select(func.count()).select_from(ChapterProgress)
    ).scalar_one()
    assert stored == 10


def test_two_pushes_to_one_chapter_in_a_batch_merge_not_duplicate(
    db_session, owner, profile
) -> None:
    """The shared row map has to give the second push the first push's row."""
    svc = _svc(db_session, owner, profile)
    result = svc.save_batch([_push("same", 3), _push("same", 9)])

    rows = db_session.execute(
        select(ChapterProgress).where(ChapterProgress.chapter_key == "same")
    ).scalars().all()
    assert len(rows) == 1, "a repeated key must merge, not insert twice"
    assert rows[0].last_page == 9
    assert result["items"][-1]["last_page"] == 9


def test_a_batch_never_rewinds_an_existing_row(
    db_session, owner, profile
) -> None:
    """Furthest-wins, through the prefetched row rather than a fresh SELECT."""
    svc = _svc(db_session, owner, profile)
    svc.save_one(_push("c1", 30))

    result = svc.save_batch([_push("c1", 5)])

    assert result["items"][0]["last_page"] == 30
    assert result["items"][0]["advanced"] is False
    row = db_session.execute(
        select(ChapterProgress).where(ChapterProgress.chapter_key == "c1")
    ).scalar_one()
    assert row.last_page == 30


def test_a_batch_moves_an_existing_row_forward(
    db_session, owner, profile
) -> None:
    svc = _svc(db_session, owner, profile)
    svc.save_one(_push("c1", 5))

    result = svc.save_batch([_push("c1", 12)])

    assert result["items"][0]["last_page"] == 12
    assert result["items"][0]["advanced"] is True


def test_the_returned_payload_matches_the_row_a_fresh_read_sees(
    db_session, owner, profile
) -> None:
    """Dropping refresh() must not change a single field of the response."""
    svc = _svc(db_session, owner, profile)
    now = utcnow().replace(microsecond=0)
    result = svc.save_batch(
        [
            _push("c1", 4, time_spent_seconds=90, last_read_at=now),
            _push("c2", 20, page_count=20, is_completed=True, last_read_at=now),
        ]
    )
    db_session.expire_all()

    for item in result["items"]:
        row = db_session.execute(
            select(ChapterProgress).where(
                ChapterProgress.chapter_key == item["chapter_key"]
            )
        ).scalar_one()
        assert item["id"] == row.id
        assert item["last_page"] == row.last_page
        assert item["page_count"] == row.page_count
        assert item["is_completed"] is bool(row.is_completed)
        assert item["time_spent_seconds"] == row.time_spent_seconds
        assert item["started_at"] == row.started_at.isoformat()
        assert item["last_read_at"] == row.last_read_at.isoformat()
        assert (
            item["completed_at"] == row.completed_at.isoformat()
            if row.completed_at
            else item["completed_at"] is None
        )


def test_save_one_payload_survives_without_refresh(
    db_session, owner, profile
) -> None:
    svc = _svc(db_session, owner, profile)
    payload = svc.save_one(_push("c9", 7, time_spent_seconds=42))
    db_session.expire_all()
    row = db_session.execute(
        select(ChapterProgress).where(ChapterProgress.chapter_key == "c9")
    ).scalar_one()
    assert payload["id"] == row.id
    assert payload["last_page"] == row.last_page == 7
    assert payload["time_spent_seconds"] == row.time_spent_seconds == 42
    assert payload["started_at"] == row.started_at.isoformat()


def test_the_prefetch_is_scoped_to_this_profile(
    db_session, owner, profile, sibling_profile
) -> None:
    """A sibling profile's row for the same chapter must not be merged onto."""
    mine = _svc(db_session, owner, profile)
    theirs = ProgressService(
        db_session, user_id=owner.id, profile_id=sibling_profile.id
    )
    theirs.save_one(_push("shared", 40))

    result = mine.save_batch([_push("shared", 2)])

    assert result["items"][0]["last_page"] == 2, "must be a NEW row, not theirs"
    rows = db_session.execute(
        select(ChapterProgress).where(ChapterProgress.chapter_key == "shared")
    ).scalars().all()
    assert len(rows) == 2
    assert {r.profile_id for r in rows} == {profile.id, sibling_profile.id}


def test_a_batch_reads_its_rows_in_one_statement_per_chunk(
    db_session, owner, profile
) -> None:
    """The point of the change, stated as a count rather than a stopwatch."""
    from sqlalchemy import event

    svc = _svc(db_session, owner, profile)
    svc.save_batch([_push(f"c{i}", 1) for i in range(20)])

    seen: list[str] = []

    @event.listens_for(db_session.bind, "before_cursor_execute")
    def _capture(conn, cursor, statement, params, context, many):  # noqa: ANN001
        seen.append(statement)

    try:
        svc.save_batch([_push(f"c{i}", 5) for i in range(20)])
    finally:
        event.remove(db_session.bind, "before_cursor_execute", _capture)

    selects = [s for s in seen if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 2, selects
