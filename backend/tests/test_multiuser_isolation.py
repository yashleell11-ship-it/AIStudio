"""Cross-user isolation for per-user state (household model).

Each test drives the *service* layer with two different user_ids and asserts
one user can never see or mutate another user's rows. This is the core
"no shared user data" security property.
"""

from __future__ import annotations

import pytest

from unittest.mock import MagicMock

from core.errors import AppError
from database.models import Chapter, Download, Library, Page, Series, User
from services.download_service import DownloadService
from services.library_service import LibraryService
from services.reader_service import ReaderService


@pytest.fixture
def catalog(db_session):
    """A shared catalog (library + series + chapter + page) and two users."""
    lib = Library(name="Main", root_path="/lib")
    db_session.add(lib)
    db_session.flush()
    series = Series(
        library_id=lib.id, title="Solo Leveling", folder_path="/lib/solo", sort_title="solo"
    )
    db_session.add(series)
    db_session.flush()
    chapter = Chapter(series_id=series.id, title="Ch1", number=1.0, page_count=10, sort_key="0001")
    db_session.add(chapter)
    db_session.flush()
    db_session.add(Page(chapter_id=chapter.id, number=1, file_path="/lib/solo/1/001.jpg"))
    alice = User(username="alice", password_hash="x")
    bob = User(username="bob", password_hash="x")
    db_session.add_all([alice, bob])
    db_session.commit()
    return {"series": series.id, "chapter": chapter.id, "alice": alice.id, "bob": bob.id}


def test_reading_progress_is_isolated_between_users(db_session, catalog):
    alice = ReaderService(db_session, user_id=catalog["alice"])
    bob = ReaderService(db_session, user_id=catalog["bob"])

    alice.save_progress(series_id=catalog["series"], chapter_id=catalog["chapter"], last_page=7)

    # Bob sees nothing for the same series.
    assert bob.get_progress(catalog["series"]) is None
    # Alice sees her own.
    assert alice.get_progress(catalog["series"])["last_page"] == 7

    # Bob records his own progress on the SAME series — no collision.
    bob.save_progress(series_id=catalog["series"], chapter_id=catalog["chapter"], last_page=2)
    assert bob.get_progress(catalog["series"])["last_page"] == 2
    # Alice's is untouched.
    assert alice.get_progress(catalog["series"])["last_page"] == 7


def test_bookmarks_are_isolated_between_users(db_session, catalog):
    alice = ReaderService(db_session, user_id=catalog["alice"])
    bob = ReaderService(db_session, user_id=catalog["bob"])

    created = alice.add_bookmark(series_id=catalog["series"], chapter_id=catalog["chapter"], page=3)

    assert len(alice.list_bookmarks(catalog["series"])) == 1
    assert bob.list_bookmarks(catalog["series"]) == []
    assert alice.list_all_bookmarks() and bob.list_all_bookmarks() == []

    # Bob cannot delete Alice's bookmark (ownership scoped → 404).
    with pytest.raises(AppError) as exc:
        bob.delete_bookmark(created["id"])
    assert exc.value.status_code == 404
    # Alice's bookmark survives Bob's attempt.
    assert len(alice.list_bookmarks(catalog["series"])) == 1
    # Alice can delete her own.
    alice.delete_bookmark(created["id"])
    assert alice.list_bookmarks(catalog["series"]) == []


def test_continue_reading_is_isolated_between_users(db_session, catalog):
    ReaderService(db_session, user_id=catalog["alice"]).save_progress(
        series_id=catalog["series"], chapter_id=catalog["chapter"], last_page=9
    )
    alice_lib = LibraryService(db_session, user_id=catalog["alice"])
    bob_lib = LibraryService(db_session, user_id=catalog["bob"])

    assert len(alice_lib.get_continue_reading()) == 1
    # Bob's "continue reading" must not surface Alice's activity.
    assert bob_lib.get_continue_reading() == []


def test_delete_progress_is_owner_scoped(db_session, catalog):
    alice = ReaderService(db_session, user_id=catalog["alice"])
    bob = ReaderService(db_session, user_id=catalog["bob"])
    alice.save_progress(series_id=catalog["series"], chapter_id=catalog["chapter"], last_page=5)

    # Bob deleting "the series progress" must not remove Alice's row.
    with pytest.raises(AppError):
        bob.delete_progress(catalog["series"])
    assert alice.get_progress(catalog["series"]) is not None


def test_download_queue_is_isolated_between_users(db_session, catalog):
    db_session.add(
        Download(
            user_id=catalog["alice"], source="mangadex", series_id="s1", chapter_id="c1",
            series_title="A", chapter_title="A1", status="queued",
        )
    )
    db_session.add(
        Download(
            user_id=catalog["bob"], source="mangadex", series_id="s1", chapter_id="c2",
            series_title="A", chapter_title="A2", status="queued",
        )
    )
    db_session.commit()

    manager = MagicMock()
    manager.get_speed_snapshot.return_value = (0, None, 0.0)  # (bps, eta, mbps)
    alice = DownloadService(db_session, manager, user_id=catalog["alice"])
    bob = DownloadService(db_session, manager, user_id=catalog["bob"])

    alice_rows = alice.list_downloads()
    bob_rows = bob.list_downloads()
    assert len(alice_rows) == 1 and alice_rows[0]["chapter_id"] == "c1"
    assert len(bob_rows) == 1 and bob_rows[0]["chapter_id"] == "c2"

    # Bob cannot pause/act on Alice's download (ownership scoped → 404).
    with pytest.raises(AppError) as exc:
        bob.pause(alice_rows[0]["id"])
    assert exc.value.status_code == 404
