"""A completed download must land in the *downloader's* library.

Library membership is per-(user, profile) — it lives on
``user_series_state.in_library`` — so the worker that imports a finished
chapter has to know which (user, profile) it is importing *for*. It learns that
from the ``Download`` row: ``user_id`` records the account and ``profile_id``
the reading profile that pressed download.

Before ``Download.profile_id`` existed, the worker built an unscoped
``LibraryService(db)``, so every downloaded series' membership row landed in the
legacy ``(NULL, NULL)`` bucket and no real profile's ``list_series`` could ever
see it: you downloaded a chapter and the series was invisible in your library on
every client. ``test_completed_download_enters_downloaders_library`` is the
regression guard — it fails against the unscoped worker.

The isolation has to hold in both directions, so the same tests assert the
series does NOT appear for a second profile on the same account, nor for another
account, and that being downloaded does not buy a series past the 18+ gate.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from connectors.models import Chapter as ConnectorChapter
from connectors.models import Page as ConnectorPage
from connectors.models import Series as ConnectorSeries
from database.models import (
    Download,
    DownloadQueue,
    ReadingProfile,
    Series,
    User,
    UserSeriesState,
)
from services.download_manager import DownloadManager, reset_download_manager_for_tests
from services.download_service import DownloadService
from services.library_service import LibraryService

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


def _mock_connector(page_count: int = 2) -> MagicMock:
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
            for i in range(1, page_count + 1)
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


@pytest.fixture
def accounts(db_session: Session) -> dict[str, int]:
    """Two accounts; the first owns two profiles, the second owns one."""
    alice = User(username="alice", password_hash="x")
    bob = User(username="bob", password_hash="x")
    db_session.add_all([alice, bob])
    db_session.flush()
    alice_main = ReadingProfile(user_id=alice.id, name="Main", sort_order=0)
    alice_kid = ReadingProfile(user_id=alice.id, name="Kid", sort_order=1)
    bob_main = ReadingProfile(user_id=bob.id, name="Main", sort_order=0)
    db_session.add_all([alice_main, alice_kid, bob_main])
    db_session.commit()
    return {
        "alice": alice.id,
        "bob": bob.id,
        "alice_main": alice_main.id,
        "alice_kid": alice_kid.id,
        "bob_main": bob_main.id,
    }


def _complete_download(
    manager: DownloadManager,
    db: Session,
    *,
    user_id: int | None,
    profile_id: int | None,
    series_title: str = "Solo Leveling",
    series_id: str = "series-1",
    chapter_id: str = "chapter-1",
) -> Download:
    download = Download(
        user_id=user_id,
        profile_id=profile_id,
        source="mangadex",
        series_id=series_id,
        chapter_id=chapter_id,
        series_title=series_title,
        chapter_title="Chapter 1",
        status="queued",
    )
    db.add(download)
    db.flush()
    db.add(DownloadQueue(download_id=download.id, state="pending"))
    db.commit()
    download_id = download.id

    connector = _mock_connector()
    with patch("services.download_manager.create_connector", return_value=connector):
        with patch(
            "services.download_manager.fetch_image_resumable",
            side_effect=_fake_fetch_image,
        ):
            manager._process_download(download_id)

    db.expire_all()
    completed = db.get(Download, download_id)
    assert completed is not None
    assert completed.status == "completed", completed.error
    return completed


def _titles(db: Session, user_id: int | None, profile_id: int | None) -> list[str]:
    service = LibraryService(db, user_id=user_id, profile_id=profile_id)
    return [item["title"] for item in service.list_series()["items"]]


def test_completed_download_enters_downloaders_library(
    db_session: Session,
    download_manager: DownloadManager,
    accounts: dict[str, int],
):
    """The regression guard: the series must be in the downloading profile's
    library, and in nobody else's. Fails against the unscoped LibraryService the
    worker used to build — there the membership row lands under (NULL, NULL)."""
    _complete_download(
        download_manager,
        db_session,
        user_id=accounts["alice"],
        profile_id=accounts["alice_main"],
    )

    assert "Solo Leveling" in _titles(
        db_session, accounts["alice"], accounts["alice_main"]
    )
    # Same account, other profile: separate shelf.
    assert _titles(db_session, accounts["alice"], accounts["alice_kid"]) == []
    # A different account entirely.
    assert _titles(db_session, accounts["bob"], accounts["bob_main"]) == []
    # And not stranded in the legacy unscoped bucket.
    assert _titles(db_session, None, None) == []


def test_membership_row_is_owned_by_the_initiating_profile(
    db_session: Session,
    download_manager: DownloadManager,
    accounts: dict[str, int],
):
    """Exactly one membership row, carrying the download's own (user, profile)."""
    _complete_download(
        download_manager,
        db_session,
        user_id=accounts["alice"],
        profile_id=accounts["alice_kid"],
    )

    states = db_session.query(UserSeriesState).all()
    assert len(states) == 1
    assert states[0].user_id == accounts["alice"]
    assert states[0].profile_id == accounts["alice_kid"]
    assert bool(states[0].in_library) is True


def test_legacy_download_without_profile_stays_in_the_accounts_unscoped_bucket(
    db_session: Session,
    download_manager: DownloadManager,
    accounts: dict[str, int],
):
    """A pre-``profile_id`` download row cannot say which profile queued it, so
    the membership row is created for (account, NULL) — the account's own legacy
    bucket. It is deliberately NOT attributed to an arbitrary profile."""
    _complete_download(
        download_manager,
        db_session,
        user_id=accounts["alice"],
        profile_id=None,
    )

    states = db_session.query(UserSeriesState).all()
    assert len(states) == 1
    assert states[0].user_id == accounts["alice"]
    assert states[0].profile_id is None
    # Not invented into either of Alice's real profiles.
    assert _titles(db_session, accounts["alice"], accounts["alice_main"]) == []
    assert _titles(db_session, accounts["alice"], accounts["alice_kid"]) == []


def test_downloaded_adult_series_still_obeys_the_mature_gate(
    db_session: Session,
    download_manager: DownloadManager,
    accounts: dict[str, int],
):
    """Membership is not a bypass: an 18+ series stays hidden while the
    profile's gate is closed, and appears the moment it is opened."""
    _complete_download(
        download_manager,
        db_session,
        user_id=accounts["alice"],
        profile_id=accounts["alice_main"],
        series_title="Adult Series",
    )
    series = db_session.query(Series).filter(Series.title == "Adult Series").one()
    series.content_rating = "pornographic"
    db_session.commit()

    profile = db_session.get(ReadingProfile, accounts["alice_main"])
    assert bool(profile.mature_content_enabled) is False
    assert _titles(db_session, accounts["alice"], accounts["alice_main"]) == []

    profile.mature_content_enabled = True
    db_session.commit()
    assert "Adult Series" in _titles(
        db_session, accounts["alice"], accounts["alice_main"]
    )


def test_queueing_records_the_initiating_profile(
    db_session: Session,
    accounts: dict[str, int],
):
    """The worker can only file membership correctly if the enqueue side
    recorded the profile in the first place."""
    connector = MagicMock()
    connector.is_browsable = True
    connector.is_mature = False
    connector.get_series.return_value = ConnectorSeries(id="s1", title="Solo Leveling")
    connector.get_chapters.return_value = [
        ConnectorChapter(
            id="c1", series_id="s1", title="Chapter 1", number=1.0, page_count=2
        )
    ]

    manager = MagicMock()
    manager.check_disk_before_queue.return_value = []
    service = DownloadService(
        db_session,
        manager,
        user_id=accounts["alice"],
        profile_id=accounts["alice_kid"],
    )
    with patch(
        "services.download_service.create_connector", return_value=connector
    ):
        result = service.queue_chapters(
            source_id="mangadex", series_id="s1", chapter_ids=["c1"]
        )

    download = db_session.get(Download, result["queued"][0])
    assert download.user_id == accounts["alice"]
    assert download.profile_id == accounts["alice_kid"]


def test_deleting_a_profile_removes_its_downloads_and_their_queue_rows(
    db_session: Session,
    accounts: dict[str, int],
):
    """``downloads.profile_id`` cascades on profile delete, which only works
    because ``download_queue.download_id`` cascades too — its ``download_id`` is
    NOT NULL, so a surviving queue row would abort the delete with a foreign key
    error. Another profile's queue is untouched."""
    doomed = Download(
        user_id=accounts["alice"],
        profile_id=accounts["alice_kid"],
        source="mangadex",
        series_id="s1",
        chapter_id="c1",
        series_title="A",
        chapter_title="A1",
        status="queued",
    )
    kept = Download(
        user_id=accounts["alice"],
        profile_id=accounts["alice_main"],
        source="mangadex",
        series_id="s1",
        chapter_id="c2",
        series_title="A",
        chapter_title="A2",
        status="queued",
    )
    db_session.add_all([doomed, kept])
    db_session.flush()
    db_session.add_all(
        [
            DownloadQueue(download_id=doomed.id, state="pending"),
            DownloadQueue(download_id=kept.id, state="pending"),
        ]
    )
    db_session.commit()
    doomed_id, kept_id = doomed.id, kept.id

    db_session.execute(text("PRAGMA foreign_keys=ON"))
    db_session.delete(db_session.get(ReadingProfile, accounts["alice_kid"]))
    db_session.commit()

    assert db_session.get(Download, doomed_id) is None
    assert db_session.get(Download, kept_id) is not None
    queue_download_ids = {row.download_id for row in db_session.query(DownloadQueue)}
    assert queue_download_ids == {kept_id}
