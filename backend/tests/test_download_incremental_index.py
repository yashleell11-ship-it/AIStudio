"""Incremental library indexing on chapter-download completion.

Every completed chapter used to trigger a *full* re-index of the entire
downloads root (``LibraryService.index_downloads_root``). That made each
completion O(total library chapters) and re-touched every unrelated series'
rows, so downloading a series of ``n`` chapters cost O(n^2) work overall.

``DownloadManager`` now indexes only the series folder that owns the
just-completed chapter, reusing the same discovery + persistence code paths so
the resulting library rows are identical to a full rescan. These tests prove:

* (a) a completion incrementally indexes the new chapter (rows + link appear),
* (b) the incremental result matches what a full rescan would produce
      (a subsequent full re-index is a no-op),
* (c) a completion never triggers the whole-downloads-root reindex and only
      ever scans the single owning series folder, leaving other series alone.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from connectors.models import Page as ConnectorPage
from database.models import (
    Chapter,
    Download,
    DownloadQueue,
    Page,
    Series,
    SourceChapterLink,
)
from services.download_manager import DownloadManager, reset_download_manager_for_tests
from services.library_service import LibraryService
from services.source_service import SourceService

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _fake_fetch_image(url: str, *, final_path, partial_path, **kwargs):
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(MINIMAL_PNG)
    partial_path.unlink(missing_ok=True)
    return MINIMAL_PNG


def _mock_connector(pages_by_chapter: dict[str, int]) -> MagicMock:
    connector = MagicMock()
    connector.is_browsable = True
    connector.allowed_image_hosts = frozenset({"example.com"})

    def get_pages(chapter_id: str):
        return [
            ConnectorPage(
                id=f"{chapter_id}:{i}",
                chapter_id=chapter_id,
                number=i,
                remote_url=f"https://example.com/{chapter_id}-p{i}.jpg",
            )
            for i in range(1, pages_by_chapter[chapter_id] + 1)
        ]

    connector.get_chapter_pages.side_effect = get_pages
    return connector


@pytest.fixture
def downloads_root(tmp_path: Path) -> Path:
    root = tmp_path / "downloads"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def download_manager(downloads_root: Path, db_engine) -> DownloadManager:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    manager = DownloadManager(max_workers=1)
    manager._downloads_root = downloads_root
    reset_download_manager_for_tests(manager)
    with patch("services.download_manager.SessionLocal", session_factory):
        yield manager
    manager.stop()
    reset_download_manager_for_tests(None)


def _complete_chapter(
    manager: DownloadManager,
    db: Session,
    connector: MagicMock,
    *,
    series_id: str,
    series_title: str,
    chapter_id: str,
    chapter_title: str,
) -> int:
    download = Download(
        source="mangadex",
        series_id=series_id,
        chapter_id=chapter_id,
        series_title=series_title,
        chapter_title=chapter_title,
        status="queued",
    )
    db.add(download)
    db.flush()
    db.add(DownloadQueue(download_id=download.id, state="pending"))
    db.commit()
    download_id = download.id

    with patch("services.download_manager.create_connector", return_value=connector):
        with patch(
            "services.download_manager.fetch_image_resumable",
            side_effect=_fake_fetch_image,
        ):
            manager._process_download(download_id)

    db.expire_all()
    return download_id


def _library_snapshot(db: Session) -> dict[str, object]:
    """Content-only snapshot of the indexed library, keyed by stable on-disk
    paths so it is invariant to row-id churn (a full rescan re-creates page
    rows). Two snapshots comparing equal means the two indexings produced the
    same library."""
    series_rows = db.query(Series).all()
    series_snap = {}
    for series in series_rows:
        chapters = {}
        for chapter in db.query(Chapter).filter(Chapter.series_id == series.id).all():
            pages = {
                page.number: page.file_path
                for page in db.query(Page).filter(Page.chapter_id == chapter.id).all()
            }
            chapters[chapter.folder_path] = {
                "title": chapter.title,
                "number": chapter.number,
                "sort_key": chapter.sort_key,
                "page_count": chapter.page_count,
                "pages": pages,
            }
        series_snap[series.folder_path] = {
            "title": series.title,
            "sort_title": series.sort_title,
            "cover_path": series.cover_path,
            "total_chapters": series.total_chapters,
            "total_pages": series.total_pages,
            "read_chapters": series.read_chapters,
            "chapters": chapters,
        }
    return series_snap


def test_completion_indexes_chapter_incrementally(
    db_session: Session,
    download_manager: DownloadManager,
    downloads_root: Path,
):
    connector = _mock_connector({"chapter-1": 3})
    download_id = _complete_chapter(
        download_manager,
        db_session,
        connector,
        series_id="series-1",
        series_title="Solo Leveling",
        chapter_id="chapter-1",
        chapter_title="Chapter 1",
    )

    completed = db_session.get(Download, download_id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.local_chapter_id is not None

    chapter = db_session.get(Chapter, completed.local_chapter_id)
    assert chapter is not None
    assert chapter.page_count == 3
    page_numbers = sorted(
        page.number
        for page in db_session.query(Page).filter(Page.chapter_id == chapter.id).all()
    )
    assert page_numbers == [1, 2, 3]

    series = db_session.get(Series, chapter.series_id)
    assert series is not None
    assert series.total_chapters == 1
    assert series.total_pages == 3

    link = (
        db_session.query(SourceChapterLink)
        .filter(SourceChapterLink.chapter_id == "chapter-1")
        .first()
    )
    assert link is not None
    assert link.local_chapter_id == completed.local_chapter_id


def test_incremental_result_matches_full_rescan(
    db_session: Session,
    download_manager: DownloadManager,
    downloads_root: Path,
):
    connector = _mock_connector({"chapter-1": 3, "chapter-2": 2, "chapter-3": 4})
    for chapter_id, title in (
        ("chapter-1", "Chapter 1"),
        ("chapter-2", "Chapter 2"),
        ("chapter-3", "Chapter 3"),
    ):
        _complete_chapter(
            download_manager,
            db_session,
            connector,
            series_id="series-1",
            series_title="Solo Leveling",
            chapter_id=chapter_id,
            chapter_title=title,
        )

    incremental = _library_snapshot(db_session)
    # Sanity: all three chapters landed via the incremental path only.
    assert len(incremental) == 1
    only_series = next(iter(incremental.values()))
    assert len(only_series["chapters"]) == 3
    assert only_series["total_chapters"] == 3
    assert only_series["total_pages"] == 9

    # Ground truth: a full re-index of the whole downloads root must agree with
    # the incrementally-built state exactly, i.e. be a no-op.
    LibraryService(db_session).index_downloads_root(str(downloads_root.resolve()))
    db_session.commit()
    db_session.expire_all()
    after_full_rescan = _library_snapshot(db_session)

    assert after_full_rescan == incremental


def test_completion_does_not_trigger_full_library_reindex(
    db_session: Session,
    download_manager: DownloadManager,
    downloads_root: Path,
):
    # Seed an unrelated, already-indexed series on disk + in the DB. If a
    # completion re-scanned the whole downloads root, it would re-scan this
    # series too; the assertions below prove it does not.
    other_chapter_dir = downloads_root / "Other Series" / "Chapter 99"
    other_chapter_dir.mkdir(parents=True)
    (other_chapter_dir / "001.jpg").write_bytes(MINIMAL_PNG)
    LibraryService(db_session).index_downloads_root(str(downloads_root.resolve()))
    db_session.commit()
    db_session.expire_all()
    other_series = db_session.query(Series).filter(Series.title == "Other Series").first()
    assert other_series is not None
    other_series_id = other_series.id
    other_updated_at = other_series.updated_at

    scanned_folders: list[str] = []
    real_discover = SourceService.discover_folder

    def spy_discover(self, folder_path: str):
        scanned_folders.append(folder_path)
        return real_discover(self, folder_path)

    reindex_calls: list[str] = []
    real_index = LibraryService.index_downloads_root

    def spy_index(self, folder_path: str):
        reindex_calls.append(folder_path)
        return real_index(self, folder_path)

    connector = _mock_connector({"chapter-1": 2})
    with patch.object(SourceService, "discover_folder", spy_discover):
        with patch.object(LibraryService, "index_downloads_root", spy_index):
            _complete_chapter(
                download_manager,
                db_session,
                connector,
                series_id="series-1",
                series_title="Solo Leveling",
                chapter_id="chapter-1",
                chapter_title="Chapter 1",
            )

    # The whole-downloads-root reindex path is never taken on completion.
    assert reindex_calls == []
    # Exactly one folder was scanned, and it is the completing chapter's series
    # folder -- not the downloads root, and not the unrelated series.
    expected_series_folder = str((downloads_root / "Solo Leveling").resolve())
    assert scanned_folders == [expected_series_folder]
    assert str(downloads_root.resolve()) not in scanned_folders

    # The unrelated series' row is untouched (same id, not re-persisted).
    db_session.expire_all()
    reloaded_other = db_session.get(Series, other_series_id)
    assert reloaded_other is not None
    assert reloaded_other.updated_at == other_updated_at
