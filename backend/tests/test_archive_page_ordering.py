"""Page N of a .cbz must be the same member the scanner numbered N.

The scanner assigns page numbers at import time; the reader maps a number back
to a member at serve time. These live in two different packages and used to use
two different orderings, so an imported .cbz served the wrong image for most of
its pages without erroring. Every test here fails on the pre-fix code.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from connectors.local_filesystem.scanner import _scan_archive_file
from database.models import Page
from database.session import get_db
from main import create_app
from services.image_service import ImageService
from utils.path_utils import sorted_archive_image_members


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


def _write_cbz(path: Path, members: list[str]) -> None:
    """Write an archive whose member bytes name the member, so a served page can
    be traced back to exactly which member answered it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name in members:
            zf.writestr(name, f"IMG:{name}".encode())


class _StubPage:
    """Stands in for a Page row; resolve_page_file only reads these two."""

    def __init__(self, number: int, file_path: Path) -> None:
        self.number = number
        self.file_path = str(file_path)


# --- the shared helper itself -------------------------------------------------


def test_helper_orders_double_digit_pages_naturally() -> None:
    members = sorted_archive_image_members(
        ["10.jpg", "2.jpg", "1.jpg", "11.jpg", "9.jpg"]
    )
    assert members == ["1.jpg", "2.jpg", "9.jpg", "10.jpg", "11.jpg"]


def test_helper_drops_non_image_members() -> None:
    # A stray ComicInfo.xml sorts ahead of the pages and would shift every page
    # by one if it were counted.
    members = sorted_archive_image_members(
        ["ComicInfo.xml", "Thumbs.db", "001.jpg", "002.png", "notes/", "003.webp"]
    )
    assert members == ["001.jpg", "002.png", "003.webp"]


def test_helper_keeps_directory_prefixes_in_order() -> None:
    members = sorted_archive_image_members(
        ["ch1/10.jpg", "ch1/2.jpg", "ch1/1.jpg"]
    )
    assert members == ["ch1/1.jpg", "ch1/2.jpg", "ch1/10.jpg"]


# --- scanner / reader agreement ----------------------------------------------


@pytest.mark.parametrize(
    "members",
    [
        # Lexicographic and natural order disagree from page 2 onward.
        [f"{i}.jpg" for i in range(1, 12)],
        # Zero padding hides the sort bug, but a non-image member that sorts
        # ahead of the pages still shifts every one of them unless it is
        # filtered out -- "ComicInfo.xml" < "p01.jpg" lexicographically.
        ["ComicInfo.xml", *[f"p{i:02d}.jpg" for i in range(1, 6)]],
        # Both problems at once, plus arbitrary zip write order.
        ["9.png", "10.png", "ComicInfo.xml", "1.png", "2.png", "11.png"],
    ],
    ids=["natural-sort", "non-image-member", "both"],
)
def test_reader_serves_the_member_the_scanner_numbered(
    tmp_path: Path, members: list[str]
) -> None:
    cbz = tmp_path / "Chapter 1.cbz"
    _write_cbz(cbz, members)

    chapter = _scan_archive_file(cbz)
    assert chapter is not None
    assert chapter.pages, "scanner found no pages"

    service = ImageService()
    for scanned in chapter.pages:
        _, _, data = service.resolve_page_file(
            _StubPage(scanned.number, cbz), [tmp_path]
        )
        assert data == f"IMG:{scanned.archive_member}".encode(), (
            f"page {scanned.number} served the wrong member: scanner numbered "
            f"{scanned.archive_member!r}"
        )


def test_scanner_and_helper_stay_in_sync(tmp_path: Path) -> None:
    """Drift guard: the scanner cannot import the helper yet (third-party
    package), so pin the two orderings against each other directly. If either
    side changes its filter or its sort, this fails."""
    members = [
        "ComicInfo.xml",
        "20.jpg",
        "3.jpg",
        "sub/1.png",
        "sub/10.png",
        "1.jpg",
        "cover.txt",
    ]
    cbz = tmp_path / "sync.cbz"
    _write_cbz(cbz, members)

    scanned = _scan_archive_file(cbz)
    assert scanned is not None
    scanner_order = [page.archive_member for page in scanned.pages]

    with zipfile.ZipFile(cbz, "r") as zf:
        helper_order = sorted_archive_image_members(zf.namelist())

    assert scanner_order == helper_order


def test_out_of_range_page_number_is_404_not_the_last_page(tmp_path: Path) -> None:
    """page.number is 1-based; a 0 must not index members[-1] and quietly serve
    the final page."""
    cbz = tmp_path / "Chapter 2.cbz"
    _write_cbz(cbz, ["1.jpg", "2.jpg", "3.jpg"])
    service = ImageService()

    from core.errors import AppError

    for bad_number in (0, -1, 4):
        with pytest.raises(AppError) as excinfo:
            service.resolve_page_file(_StubPage(bad_number, cbz), [tmp_path])
        assert excinfo.value.code == "page_not_found"


def test_cover_of_an_archive_series_is_page_one(tmp_path: Path) -> None:
    """cover_path for an archive chapter is the archive itself; the cover it
    stands for is page 1, not whatever the zip writer stored first."""
    cbz = tmp_path / "Chapter 1.cbz"
    # Written last-page-first with metadata in front, as real packers often do.
    _write_cbz(cbz, ["ComicInfo.xml", "10.jpg", "2.jpg", "1.jpg"])

    class _StubLibraryService:
        def assert_series_readable(self, series_id: int):
            # get_cover_path now authorizes before the source-cover shortcut;
            # this stub stands in for a caller that already passed.
            return None

        def resolve_source_link(self, series_id: int):
            return None

        def get_series(self, series_id: int):
            return {"cover_path": str(cbz)}

        def get_library_roots(self):
            return [tmp_path]

    data, media_type = ImageService().get_cover_path(_StubLibraryService(), 1)
    assert data == b"IMG:1.jpg"
    assert media_type == "image/jpeg"


# --- end to end through the API ----------------------------------------------


def test_imported_cbz_reads_in_order_end_to_end(
    client: TestClient, tmp_path: Path
) -> None:
    library_root = tmp_path / "Library"
    _write_cbz(
        library_root / "Tower of God" / "Chapter 1.cbz",
        ["ComicInfo.xml", *[f"{i}.jpg" for i in range(1, 12)]],
    )

    response = client.post(
        "/library/import", json={"folder_path": str(library_root.resolve())}
    )
    assert response.status_code == 200, response.text
    assert response.json()["page_count"] == 11

    items = client.get("/library/series").json()["items"]
    chapter_id = items[0]["first_chapter_id"]

    chapter = client.get(f"/reader/chapter/{chapter_id}").json()
    assert [page["number"] for page in chapter["pages"]] == list(range(1, 12))

    for page in chapter["pages"]:
        image = client.get(page["image_url"])
        assert image.status_code == 200, image.text
        assert image.content == f"IMG:{page['number']}.jpg".encode(), (
            f"page {page['number']} served {image.content!r}"
        )


def test_chapter_payload_does_not_leak_server_paths(
    client: TestClient, tmp_path: Path, db_engine
) -> None:
    """The reader payload must not disclose the server's filesystem layout --
    the same reason image_service reports a missing file without its path."""
    library_root = tmp_path / "Library"
    chapter_dir = library_root / "Solo Leveling" / "Chapter 1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"fake-image")
    (chapter_dir / "002.jpg").write_bytes(b"fake-image-2")

    assert (
        client.post(
            "/library/import", json={"folder_path": str(library_root.resolve())}
        ).status_code
        == 200
    )
    items = client.get("/library/series").json()["items"]
    chapter_id = items[0]["first_chapter_id"]

    # The rows really do hold absolute paths -- so the assertion below is about
    # what is withheld, not about there being nothing to withhold.
    session_factory = sessionmaker(bind=db_engine)
    with session_factory() as db:
        stored = [page.file_path for page in db.query(Page).all()]
    assert stored and all(Path(path).is_absolute() for path in stored)

    body = client.get(f"/reader/chapter/{chapter_id}").text
    assert str(tmp_path) not in body
    assert "Solo Leveling/Chapter 1" not in body

    for page in client.get(f"/reader/chapter/{chapter_id}").json()["pages"]:
        # Key retained for mobile's non-nullable parse, but carries no path.
        assert page["file_path"] == ""
        # Clients still get everything they need to address and load a page.
        assert page["id"] and page["number"]
        assert page["image_url"] == f"/reader/page/{page['id']}/image"
