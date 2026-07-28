"""Pages must reach the reader with their real width/height.

The reader lays a chapter out as one lazy list and needs an extent for every
page before that page's bytes arrive. ``pages.width``/``pages.height`` existed
but nothing ever wrote them, so every page fell back to a single default aspect
ratio (mobile/lib/features/reader/utils/page_layout.dart:55-62) and each image
resized its slot on arrival, shoving everything below it -- i.e. scrolling a
long manhwa randomly threw the reader backwards.

Every test here fails on the pre-fix code (dimensions were unconditionally
null), except the ones asserting the failure modes stay graceful.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import sessionmaker

from database.models import Chapter, Library, Page, Series, UserSeriesState
from database.session import get_db
from main import create_app
from services.image_service import ImageService
from services.library_service import (
    LibraryService,
    PageDimensionBackfill,
    fill_chapter_page_dimensions,
    measure_pages,
)


# --- fixtures / helpers -------------------------------------------------------


def _image_bytes(width: int, height: int, fmt: str = "JPEG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (12, 34, 56)).save(buffer, fmt)
    return buffer.getvalue()


def _write_image(path: Path, width: int, height: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = "PNG" if path.suffix.lower() == ".png" else "JPEG"
    path.write_bytes(_image_bytes(width, height, fmt))
    return path


def _write_cbz(path: Path, members: dict[str, tuple[int, int]]) -> Path:
    """Archive whose members each have a distinct size, so a measurement can be
    traced back to exactly which member answered it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, size in members.items():
            fmt = "PNG" if name.lower().endswith(".png") else "JPEG"
            archive.writestr(name, _image_bytes(size[0], size[1], fmt))
    return path


@pytest.fixture
def client(db_engine):
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _seed_chapter(db, *, pages: list[tuple[int, str]], claim: bool = True) -> Chapter:
    """A series/chapter with unmeasured page rows, claimed by the test caller.

    The claim matters: page and chapter reads are behind object-level
    authorization (core.library_authz), so an unclaimed series 404s.
    """
    library = Library(name="lib", root_path="/tmp/lib")
    db.add(library)
    db.flush()
    series = Series(
        library_id=library.id,
        title="Solo Leveling",
        sort_title="solo leveling",
        folder_path="/tmp/lib/solo",
    )
    db.add(series)
    db.flush()
    if claim:
        db.add(UserSeriesState(user_id=None, profile_id=None, series_id=series.id, in_library=True))
    chapter = Chapter(
        series_id=series.id,
        title="Chapter 1",
        number=1,
        sort_key="0001.000",
        page_count=len(pages),
    )
    db.add(chapter)
    db.flush()
    for number, file_path in pages:
        db.add(Page(chapter_id=chapter.id, number=number, file_path=file_path))
    db.commit()
    return chapter


# --- measure_pages: the pure measurement ------------------------------------


def test_measures_a_loose_image_file(tmp_path: Path) -> None:
    page = _write_image(tmp_path / "001.jpg", 800, 4200)
    assert measure_pages([(1, str(page))]) == {1: (800, 4200)}


def test_measures_every_page_of_a_folder_chapter(tmp_path: Path) -> None:
    entries = []
    for index, height in enumerate([1200, 3400, 900], start=1):
        entries.append(
            (index, str(_write_image(tmp_path / f"{index:03d}.jpg", 700, height)))
        )
    assert measure_pages(entries) == {1: (700, 1200), 2: (700, 3400), 3: (700, 900)}


def test_archive_page_number_measures_the_member_the_reader_serves(
    tmp_path: Path,
) -> None:
    """The one that would silently lie if the member ordering diverged.

    Members are written in an order where lexicographic and natural sort
    disagree, and a non-image member sorts ahead of the pages. Each page has a
    unique height, so a wrong member produces a wrong-but-plausible number
    rather than an error. The measured size for page N must equal the size of
    the bytes ImageService actually serves for page N.
    """
    sizes = {f"{i}.jpg": (600, 1000 + i * 37) for i in range(1, 12)}
    cbz = tmp_path / "Chapter 1.cbz"
    with zipfile.ZipFile(cbz, "w") as archive:
        archive.writestr("ComicInfo.xml", b"<x/>")
        for name, size in sizes.items():
            archive.writestr(name, _image_bytes(*size))

    measured = measure_pages([(n, str(cbz)) for n in range(1, 12)])
    assert len(measured) == 11

    service = ImageService()

    class _StubPage:
        def __init__(self, number: int) -> None:
            self.number = number
            self.file_path = str(cbz)

    for number in range(1, 12):
        _, _, data = service.resolve_page_file(_StubPage(number), [tmp_path])
        with Image.open(BytesIO(data)) as served:
            assert measured[number] == served.size, f"page {number} measured a different member"


def test_unreadable_pages_are_absent_rather_than_raising(tmp_path: Path) -> None:
    good = _write_image(tmp_path / "001.jpg", 500, 700)
    corrupt = tmp_path / "002.jpg"
    corrupt.write_bytes(b"\xff\xd8\xffnot really a jpeg")
    empty = tmp_path / "003.jpg"
    empty.write_bytes(b"")
    missing = tmp_path / "004.jpg"

    result = measure_pages(
        [(1, str(good)), (2, str(corrupt)), (3, str(empty)), (4, str(missing)), (5, "")]
    )
    assert result == {1: (500, 700)}


def test_unreadable_archive_and_member_are_absent(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "broken.cbz"
    not_a_zip.write_bytes(b"PK\x03\x04 truncated")
    assert measure_pages([(1, str(not_a_zip))]) == {}

    mixed = _write_cbz(tmp_path / "mixed.cbz", {"001.jpg": (400, 600)})
    with zipfile.ZipFile(mixed, "a") as archive:
        archive.writestr("002.jpg", b"garbage")
    # Page 3 does not exist in the archive at all.
    assert measure_pages([(1, str(mixed)), (2, str(mixed)), (3, str(mixed))]) == {
        1: (400, 600)
    }


# --- scan time: dimensions are recorded as pages are indexed -----------------


def test_scanned_folder_chapter_records_real_dimensions(db_session, tmp_path: Path) -> None:
    chapter_dir = tmp_path / "Solo Leveling" / "Chapter 1"
    _write_image(chapter_dir / "001.jpg", 800, 2400)
    _write_image(chapter_dir / "002.jpg", 800, 5100)

    LibraryService(db_session).index_downloads_root(str(tmp_path))
    db_session.commit()

    pages = db_session.query(Page).order_by(Page.number).all()
    assert [(p.width, p.height) for p in pages] == [(800, 2400), (800, 5100)]


def test_scanned_cbz_chapter_records_real_dimensions(db_session, tmp_path: Path) -> None:
    series_dir = tmp_path / "Omniscient Reader"
    _write_cbz(
        series_dir / "Chapter 1.cbz",
        {"1.jpg": (720, 1500), "2.jpg": (720, 3300), "10.jpg": (720, 4800)},
    )

    LibraryService(db_session).index_downloads_root(str(tmp_path))
    db_session.commit()

    pages = db_session.query(Page).order_by(Page.number).all()
    # Natural order puts 10.jpg last, so page 3 is the tall one.
    assert [(p.width, p.height) for p in pages] == [
        (720, 1500),
        (720, 3300),
        (720, 4800),
    ]


def test_corrupt_page_leaves_nulls_without_failing_the_scan(
    db_session, tmp_path: Path
) -> None:
    chapter_dir = tmp_path / "Solo Leveling" / "Chapter 1"
    _write_image(chapter_dir / "001.jpg", 640, 1800)
    (chapter_dir / "002.jpg").write_bytes(b"\x89PNG\r\n\x1a\n truncated")
    _write_image(chapter_dir / "003.jpg", 640, 2100)

    LibraryService(db_session).index_downloads_root(str(tmp_path))
    db_session.commit()

    pages = db_session.query(Page).order_by(Page.number).all()
    assert len(pages) == 3, "the corrupt page must still be indexed"
    assert (pages[0].width, pages[0].height) == (640, 1800)
    assert pages[1].width is None and pages[1].height is None
    assert (pages[2].width, pages[2].height) == (640, 2100)


def test_rescan_repairs_a_page_whose_file_became_readable(
    db_session, tmp_path: Path
) -> None:
    """A chapter rescan re-measures; a page that was corrupt at first scan is
    not stuck null forever."""
    chapter_dir = tmp_path / "Solo Leveling" / "Chapter 1"
    broken = chapter_dir / "001.jpg"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"nope")

    LibraryService(db_session).index_downloads_root(str(tmp_path))
    db_session.commit()
    assert db_session.query(Page).one().width is None

    _write_image(broken, 900, 2600)
    LibraryService(db_session).index_downloads_root(str(tmp_path))
    db_session.commit()
    assert (db_session.query(Page).one().width, db_session.query(Page).one().height) == (
        900,
        2600,
    )


def test_rescan_does_not_reopen_pages_it_has_already_sized(
    db_session, tmp_path: Path, monkeypatch
) -> None:
    """A finished download re-persists every chapter of its series, so a scan
    that re-measured unconditionally would re-open the whole series' files once
    per downloaded chapter. Sized pages must be carried forward untouched."""
    from services import library_service as module

    chapter_dir = tmp_path / "Solo Leveling" / "Chapter 1"
    _write_image(chapter_dir / "001.jpg", 800, 2400)
    _write_image(chapter_dir / "002.jpg", 800, 5100)

    LibraryService(db_session).index_downloads_root(str(tmp_path))
    db_session.commit()

    measured: list[list[tuple[int, str]]] = []
    real_measure = module.measure_pages

    def _spy(entries):
        batch = list(entries)
        measured.append(batch)
        return real_measure(batch)

    monkeypatch.setattr(module, "measure_pages", _spy)

    # A second chapter arrives; chapter 1 is re-persisted alongside it.
    _write_image(tmp_path / "Solo Leveling" / "Chapter 2" / "001.jpg", 800, 3300)
    LibraryService(db_session).index_downloads_root(str(tmp_path))
    db_session.commit()

    assert [entry for batch in measured for entry in batch] == [
        (1, str((tmp_path / "Solo Leveling" / "Chapter 2" / "001.jpg").resolve()))
    ], "the rescan re-opened pages it had already sized"

    pages = (
        db_session.query(Page).join(Chapter).order_by(Chapter.number, Page.number).all()
    )
    assert [(p.width, p.height) for p in pages] == [
        (800, 2400),
        (800, 5100),
        (800, 3300),
    ]


# --- backfill of already-indexed chapters ------------------------------------


def test_backfill_fills_only_missing_rows(db_session, tmp_path: Path) -> None:
    first = _write_image(tmp_path / "001.jpg", 800, 2000)
    second = _write_image(tmp_path / "002.jpg", 800, 3000)
    chapter = _seed_chapter(
        db_session, pages=[(1, str(first)), (2, str(second))]
    )
    # Page 2 already measured (with a deliberately wrong value): the backfill
    # only repairs what is unknown, it never re-decides a recorded size.
    page_two = db_session.query(Page).filter(Page.number == 2).one()
    page_two.width, page_two.height = 1, 1
    db_session.commit()

    assert fill_chapter_page_dimensions(db_session, chapter.id) == 1

    rows = db_session.query(Page).order_by(Page.number).all()
    assert (rows[0].width, rows[0].height) == (800, 2000)
    assert (rows[1].width, rows[1].height) == (1, 1)


def test_backfill_covers_archive_chapters(db_session, tmp_path: Path) -> None:
    cbz = _write_cbz(
        tmp_path / "Chapter 5.cbz", {"1.jpg": (700, 1100), "2.jpg": (700, 2200)}
    )
    chapter = _seed_chapter(db_session, pages=[(1, str(cbz)), (2, str(cbz))])

    assert fill_chapter_page_dimensions(db_session, chapter.id) == 2

    rows = db_session.query(Page).order_by(Page.number).all()
    assert [(r.width, r.height) for r in rows] == [(700, 1100), (700, 2200)]


def test_backfill_leaves_unreadable_pages_null_and_reports_the_rest(
    db_session, tmp_path: Path
) -> None:
    good = _write_image(tmp_path / "001.jpg", 640, 1600)
    gone = tmp_path / "002.jpg"
    chapter = _seed_chapter(db_session, pages=[(1, str(good)), (2, str(gone))])

    assert fill_chapter_page_dimensions(db_session, chapter.id) == 1

    rows = db_session.query(Page).order_by(Page.number).all()
    assert (rows[0].width, rows[0].height) == (640, 1600)
    assert rows[1].width is None and rows[1].height is None


def test_backfill_of_a_fully_measured_chapter_touches_nothing(
    db_session, tmp_path: Path
) -> None:
    page = _write_image(tmp_path / "001.jpg", 500, 900)
    chapter = _seed_chapter(db_session, pages=[(1, str(page))])
    fill_chapter_page_dimensions(db_session, chapter.id)
    assert fill_chapter_page_dimensions(db_session, chapter.id) == 0


# --- the scheduler that keeps the work off the request path ------------------


def test_scheduler_runs_queued_chapters_and_stops(monkeypatch) -> None:
    backfill = PageDimensionBackfill()
    done: list[int] = []
    monkeypatch.setattr(
        "services.library_service.SessionLocal", lambda: _NullSession()
    )
    monkeypatch.setattr(
        "services.library_service.fill_chapter_page_dimensions",
        lambda _db, chapter_id: done.append(chapter_id) or 0,
    )
    monkeypatch.setattr("services.library_service._BACKFILL_CHAPTER_PAUSE_SECONDS", 0)

    backfill.schedule([4, 1, 7])
    _join_worker(backfill)
    assert done == [4, 1, 7]


def test_scheduler_never_repeats_a_chapter(monkeypatch) -> None:
    backfill = PageDimensionBackfill()
    done: list[int] = []
    monkeypatch.setattr(
        "services.library_service.SessionLocal", lambda: _NullSession()
    )
    monkeypatch.setattr(
        "services.library_service.fill_chapter_page_dimensions",
        lambda _db, chapter_id: done.append(chapter_id) or 0,
    )
    monkeypatch.setattr("services.library_service._BACKFILL_CHAPTER_PAUSE_SECONDS", 0)

    backfill.schedule([1, 2])
    _join_worker(backfill)
    backfill.schedule([2, 1, 3])
    _join_worker(backfill)
    assert done == [1, 2, 3]


def test_scheduler_survives_one_failing_chapter(monkeypatch) -> None:
    backfill = PageDimensionBackfill()
    done: list[int] = []

    def _fill(_db, chapter_id):
        if chapter_id == 2:
            raise RuntimeError("boom")
        done.append(chapter_id)
        return 0

    monkeypatch.setattr(
        "services.library_service.SessionLocal", lambda: _NullSession()
    )
    monkeypatch.setattr("services.library_service.fill_chapter_page_dimensions", _fill)
    monkeypatch.setattr("services.library_service._BACKFILL_CHAPTER_PAUSE_SECONDS", 0)

    backfill.schedule([1, 2, 3])
    _join_worker(backfill)
    assert done == [1, 3]


def test_disabled_scheduler_does_no_work(monkeypatch) -> None:
    backfill = PageDimensionBackfill()
    done: list[int] = []
    monkeypatch.setattr(
        "services.library_service.SessionLocal", lambda: _NullSession()
    )
    monkeypatch.setattr(
        "services.library_service.fill_chapter_page_dimensions",
        lambda _db, chapter_id: done.append(chapter_id) or 0,
    )
    backfill.set_enabled(False)
    backfill.schedule([1, 2, 3])
    _join_worker(backfill)
    assert done == []


class _NullSession:
    def close(self) -> None:  # pragma: no cover - trivial
        pass

    def rollback(self) -> None:  # pragma: no cover - trivial
        pass


def _join_worker(backfill: PageDimensionBackfill, timeout: float = 5.0) -> None:
    thread = backfill._thread
    if thread is not None:
        thread.join(timeout)
        assert not thread.is_alive(), "backfill worker did not finish"


# --- the payload the reader actually receives --------------------------------


def test_chapter_payload_carries_page_dimensions(client, db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    chapter = _seed_chapter(db, pages=[(1, "/tmp/lib/solo/1/001.jpg")])
    page = db.query(Page).one()
    page.width, page.height = 800, 4200
    db.commit()
    chapter_id = chapter.id
    db.close()

    for url in (f"/library/chapters/{chapter_id}", f"/reader/chapter/{chapter_id}"):
        body = client.get(url).json()
        assert body["pages"][0]["width"] == 800, url
        assert body["pages"][0]["height"] == 4200, url


def test_chapter_payload_reports_unknown_dimensions_as_null(client, db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    chapter = _seed_chapter(db, pages=[(1, "/tmp/lib/solo/1/001.jpg")])
    chapter_id = chapter.id
    db.close()

    body = client.get(f"/reader/chapter/{chapter_id}").json()
    assert body["pages"][0]["width"] is None
    assert body["pages"][0]["height"] is None


def test_reading_service_payload_carries_page_dimensions(db_session) -> None:
    """The mobile reader reads /reader/chapter; the unified source reader is the
    other consumer of get_chapter and must not drop the fields in transit."""
    from services.reading_service import ReadingService

    chapter = _seed_chapter(db_session, pages=[(1, "/tmp/lib/solo/1/001.jpg")])
    page = db_session.query(Page).one()
    page.width, page.height = 1080, 7600
    db_session.commit()

    # _local_reader_payload never touches the browse service.
    payload = ReadingService(db_session, browse_service=None)._local_reader_payload(
        chapter.id
    )
    assert payload["pages"][0]["width"] == 1080
    assert payload["pages"][0]["height"] == 7600


def test_reading_a_chapter_does_not_schedule_against_a_foreign_database(
    client, db_engine
) -> None:
    """The request path must never enqueue work whose chapter ids belong to a
    different database than the worker writes to."""
    from services.library_service import get_page_dimension_backfill

    backfill = get_page_dimension_backfill()
    backfill.reset()
    backfill.set_enabled(True)  # the suite-wide fixture leaves it disabled

    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    chapter = _seed_chapter(db, pages=[(1, "/tmp/lib/solo/1/001.jpg")])
    chapter_id = chapter.id
    db.close()

    try:
        response = client.get(f"/reader/chapter/{chapter_id}")
        # The read itself must have succeeded, or this would pass for the wrong
        # reason (a 404 never reaches the scheduling hook at all).
        assert response.status_code == 200
        assert response.json()["pages"][0]["width"] is None
        assert not backfill._pending
        assert backfill._thread is None
    finally:
        backfill.reset()
        backfill.set_enabled(False)


def test_reading_a_chapter_queues_its_series_in_reading_order(
    db_session, db_engine, monkeypatch
) -> None:
    """Opening a chapter with unknown page sizes queues that chapter first, then
    the chapters ahead of it, then the ones behind -- a reader moves forward, so
    only the chapter that discovers the gap can lay out on the old guess."""
    from services import library_service as module

    chapter = _seed_chapter(db_session, pages=[(1, "/tmp/lib/solo/2/001.jpg")])
    chapter.number = 2
    chapter.title = "Chapter 2"
    others = {}
    for number in (1, 3):
        row = Chapter(
            series_id=chapter.series_id,
            title=f"Chapter {number}",
            number=number,
            sort_key=f"{number:08.3f}",
            page_count=0,
        )
        db_session.add(row)
        db_session.flush()
        others[number] = row.id
    db_session.commit()

    queued: list[list[int]] = []
    monkeypatch.setattr(module, "get_engine", lambda: db_engine)
    monkeypatch.setattr(
        module._page_dimension_backfill,
        "schedule",
        lambda ids: queued.append(list(ids)),
    )

    module.LibraryService(db_session).get_chapter(chapter.id)
    assert queued == [[chapter.id, others[3], others[1]]]


def test_a_fully_measured_chapter_queues_nothing(
    db_session, db_engine, monkeypatch
) -> None:
    from services import library_service as module

    chapter = _seed_chapter(db_session, pages=[(1, "/tmp/lib/solo/1/001.jpg")])
    page = db_session.query(Page).one()
    page.width, page.height = 800, 2400
    db_session.commit()

    queued: list[list[int]] = []
    monkeypatch.setattr(module, "get_engine", lambda: db_engine)
    monkeypatch.setattr(
        module._page_dimension_backfill,
        "schedule",
        lambda ids: queued.append(list(ids)),
    )

    module.LibraryService(db_session).get_chapter(chapter.id)
    assert queued == []
