from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from database.models import Chapter, Library, Page, ReadingSession, Series
from services.reader_service import ReaderService


@pytest.fixture
def db(db_engine) -> Session:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _seed_chapter_with_pages(db: Session, page_count: int = 3) -> Chapter:
    library = Library(name="Test Library", root_path="/tmp/test")
    db.add(library)
    db.flush()

    series = Series(
        library_id=library.id,
        title="Solo Leveling",
        folder_path="/tmp/test/solo-leveling",
    )
    db.add(series)
    db.flush()

    chapter = Chapter(
        series_id=series.id,
        title="Chapter 1",
        number=1,
        folder_path="/tmp/test/solo-leveling/ch1",
        page_count=page_count,
    )
    db.add(chapter)
    db.flush()

    for i in range(1, page_count + 1):
        db.add(Page(chapter_id=chapter.id, number=i, file_path=f"page_{i}.jpg"))
    db.flush()
    return chapter


def test_save_progress_records_reading_session(db: Session):
    chapter = _seed_chapter_with_pages(db)
    service = ReaderService(db)

    service.save_progress(
        series_id=chapter.series_id,
        chapter_id=chapter.id,
        last_page=2,
    )
    service.save_progress(
        series_id=chapter.series_id,
        chapter_id=chapter.id,
        last_page=2,
    )
    service.save_progress(
        series_id=chapter.series_id,
        chapter_id=chapter.id,
        last_page=4,
    )

    sessions = (
        db.query(ReadingSession)
        .filter(ReadingSession.series_id == chapter.series_id)
        .order_by(ReadingSession.id.asc())
        .all()
    )
    assert len(sessions) == 2
    assert sessions[0].pages_read == 2
    assert sessions[0].end_page == 2
    assert sessions[1].pages_read == 2
    assert sessions[1].start_page == 3
    assert sessions[1].end_page == 4


def test_add_bookmark_populates_page_id(db: Session):
    chapter = _seed_chapter_with_pages(db)
    service = ReaderService(db)

    result = service.add_bookmark(
        series_id=chapter.series_id,
        chapter_id=chapter.id,
        page=2,
        note="Great scene",
    )

    expected_page_id = (
        db.query(Page).filter(Page.chapter_id == chapter.id, Page.number == 2).first().id
    )
    assert result["page_id"] == expected_page_id
    assert result["page_id"] is not None
    assert result["page"] == 2


def test_add_bookmark_with_out_of_range_page_leaves_page_id_none(db: Session):
    chapter = _seed_chapter_with_pages(db, page_count=3)
    service = ReaderService(db)

    result = service.add_bookmark(
        series_id=chapter.series_id,
        chapter_id=chapter.id,
        page=999,
        note=None,
    )

    assert result["page_id"] is None
    assert result["page"] == 999


def test_list_bookmarks_includes_page_id(db: Session):
    chapter = _seed_chapter_with_pages(db)
    service = ReaderService(db)
    service.add_bookmark(series_id=chapter.series_id, chapter_id=chapter.id, page=1)

    bookmarks = service.list_bookmarks(chapter.series_id)

    assert len(bookmarks) == 1
    assert bookmarks[0]["page_id"] is not None
