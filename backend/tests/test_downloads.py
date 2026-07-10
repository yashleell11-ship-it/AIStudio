from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from connectors.models import Chapter as ConnectorChapter
from connectors.models import Page as ConnectorPage
from database.models import Download, DownloadQueue, SourceChapterLink
from database.session import get_db
from main import create_app
from services.download_manager import DownloadManager, reset_download_manager_for_tests

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
def client(db_engine, download_manager: DownloadManager):
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


def _mock_connector() -> MagicMock:
    connector = MagicMock()
    connector.is_browsable = True
    connector.allowed_image_hosts = frozenset({"example.com"})
    connector.get_series.return_value = MagicMock(title="Solo Leveling")
    connector.get_chapters.return_value = [
        ConnectorChapter(
            id="chapter-1",
            series_id="series-1",
            title="Chapter 1",
            number=1,
            page_count=2,
        ),
        ConnectorChapter(
            id="chapter-2",
            series_id="series-1",
            title="Chapter 2",
            number=2,
            page_count=2,
        ),
    ]
    connector.get_chapter_pages.return_value = [
        ConnectorPage(
            id="chapter-1:1",
            chapter_id="chapter-1",
            number=1,
            remote_url="https://example.com/page1.jpg",
        ),
        ConnectorPage(
            id="chapter-1:2",
            chapter_id="chapter-1",
            number=2,
            remote_url="https://example.com/page2.webp",
        ),
    ]
    return connector


def test_queue_single_chapter(client: TestClient, db_session: Session):
    connector = _mock_connector()
    with patch("services.download_service.create_connector", return_value=connector):
        response = client.post(
            "/downloads/chapters",
            json={
                "source_id": "mangadex",
                "series_id": "series-1",
                "chapter_ids": ["chapter-1"],
                "series_title": "Solo Leveling",
                "chapter_titles": {"chapter-1": "Chapter 1"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["queued"]) == 1
    assert payload["skipped"] == []

    download = db_session.query(Download).first()
    assert download is not None
    assert download.status == "queued"
    assert download.series_title == "Solo Leveling"
    assert db_session.query(DownloadQueue).count() == 1


def test_skip_duplicate_queue(client: TestClient, db_session: Session):
    connector = _mock_connector()
    with patch("services.download_service.create_connector", return_value=connector):
        first = client.post(
            "/downloads/chapters",
            json={
                "source_id": "mangadex",
                "series_id": "series-1",
                "chapter_ids": ["chapter-1"],
                "series_title": "Solo Leveling",
            },
        )
        second = client.post(
            "/downloads/chapters",
            json={
                "source_id": "mangadex",
                "series_id": "series-1",
                "chapter_ids": ["chapter-1"],
                "series_title": "Solo Leveling",
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["skipped"] == ["chapter-1"]
    assert db_session.query(Download).count() == 1


def test_queue_entire_series(client: TestClient):
    connector = _mock_connector()
    with patch("services.download_service.create_connector", return_value=connector):
        response = client.post(
            "/downloads/series",
            json={"source_id": "mangadex", "series_id": "series-1"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["queued"]) == 2


def test_queue_entire_series_includes_chapters_with_unknown_page_count(
    client: TestClient,
):
    """Regression test: connectors like MangaKatana only learn a chapter's
    page_count lazily, after its pages are fetched once via the reader.
    page_count == 0 means "not yet opened," not "empty" -- queue_series must
    not use it to decide which chapters belong in the download. Before the
    fix, only the one chapter that happened to have a nonzero page_count
    (because it had already been read) was queued; every other chapter in
    the series was silently dropped."""
    connector = MagicMock()
    connector.is_browsable = True
    connector.get_series.return_value = MagicMock(title="Kuroneko to Majo no Kyoushitsu")
    connector.get_chapters.return_value = [
        ConnectorChapter(
            id="c1", series_id="series-1", title="Chapter 1", number=1, page_count=74,
        ),
        # Every chapter below has never been opened in the reader, so the
        # connector has no way to know its real page_count yet -- exactly
        # the state MangaKatana chapters are in until read once.
        ConnectorChapter(
            id="c2", series_id="series-1", title="Chapter 2", number=2, page_count=0,
        ),
        ConnectorChapter(
            id="c3", series_id="series-1", title="Chapter 3", number=3, page_count=0,
        ),
        ConnectorChapter(
            id="c4", series_id="series-1", title="Chapter 4", number=4, page_count=0,
        ),
    ]

    with patch("services.download_service.create_connector", return_value=connector):
        response = client.post(
            "/downloads/series",
            json={"source_id": "mangakatana", "series_id": "series-1"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["queued"]) == 4
    assert payload["skipped"] == []


def test_queue_entire_series_all_unknown_page_counts_still_queues_everything(
    client: TestClient,
):
    """Edge case: a series where NO chapter has been opened yet (all
    page_count == 0) must still queue every chapter, not zero."""
    connector = MagicMock()
    connector.is_browsable = True
    connector.get_series.return_value = MagicMock(title="Brand New Series")
    connector.get_chapters.return_value = [
        ConnectorChapter(
            id=f"c{i}", series_id="series-1", title=f"Chapter {i}", number=i, page_count=0,
        )
        for i in range(1, 6)
    ]

    with patch("services.download_service.create_connector", return_value=connector):
        response = client.post(
            "/downloads/series",
            json={"source_id": "mangakatana", "series_id": "series-1"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["queued"]) == 5


def _seed_download(
    db_session: Session,
    *,
    source: str,
    series_id: str,
    chapter_id: str,
    status: str = "queued",
    queue_state: str = "pending",
    priority: int = 0,
) -> Download:
    download = Download(
        source=source,
        series_id=series_id,
        chapter_id=chapter_id,
        series_title=f"Series {series_id}",
        chapter_title=f"Chapter {chapter_id}",
        status=status,
    )
    db_session.add(download)
    db_session.flush()
    db_session.add(
        DownloadQueue(download_id=download.id, state=queue_state, priority=priority)
    )
    db_session.commit()
    db_session.refresh(download)
    return download


def test_pause_series_only_affects_that_series(client: TestClient, db_session: Session):
    a1 = _seed_download(db_session, source="mangadex", series_id="series-a", chapter_id="a1")
    a2 = _seed_download(db_session, source="mangadex", series_id="series-a", chapter_id="a2")
    b1 = _seed_download(db_session, source="mangadex", series_id="series-b", chapter_id="b1")

    response = client.post(
        "/downloads/series/pause",
        json={"source_id": "mangadex", "series_id": "series-a"},
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 2

    db_session.expire_all()
    assert db_session.get(Download, a1.id).status == "paused"
    assert db_session.get(Download, a2.id).status == "paused"
    assert db_session.get(Download, b1.id).status == "queued"


def test_resume_series_only_affects_that_series(client: TestClient, db_session: Session):
    a1 = _seed_download(
        db_session, source="mangadex", series_id="series-a", chapter_id="a1",
        status="paused", queue_state="paused",
    )
    b1 = _seed_download(
        db_session, source="mangadex", series_id="series-b", chapter_id="b1",
        status="paused", queue_state="paused",
    )

    response = client.post(
        "/downloads/series/resume",
        json={"source_id": "mangadex", "series_id": "series-a"},
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 1

    db_session.expire_all()
    assert db_session.get(Download, a1.id).status == "queued"
    assert db_session.get(Download, b1.id).status == "paused"


def test_cancel_series_only_affects_that_series(client: TestClient, db_session: Session):
    """The exact requirement from the task: cancelling one series must never
    touch another series' downloads."""
    a1 = _seed_download(db_session, source="mangadex", series_id="series-a", chapter_id="a1")
    a2 = _seed_download(
        db_session, source="mangadex", series_id="series-a", chapter_id="a2",
        status="downloading", queue_state="active",
    )
    b1 = _seed_download(db_session, source="mangadex", series_id="series-b", chapter_id="b1")
    b2 = _seed_download(
        db_session, source="mangadex", series_id="series-b", chapter_id="b2",
        status="completed", queue_state="completed",
    )

    response = client.post(
        "/downloads/series/cancel",
        json={"source_id": "mangadex", "series_id": "series-a"},
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 2

    db_session.expire_all()
    assert db_session.get(Download, a1.id).status == "cancelled"
    assert db_session.get(Download, a2.id).status == "cancelled"
    # Series B untouched, including the already-completed chapter.
    assert db_session.get(Download, b1.id).status == "queued"
    assert db_session.get(Download, b2.id).status == "completed"


def test_cancel_series_does_not_affect_same_series_id_on_a_different_source(
    client: TestClient, db_session: Session
):
    """Two different sources can coincidentally use the same series_id
    string -- scoping must include source, not just series_id."""
    mangadex_row = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c1"
    )
    mangakatana_row = _seed_download(
        db_session, source="mangakatana", series_id="series-1", chapter_id="c1"
    )

    response = client.post(
        "/downloads/series/cancel",
        json={"source_id": "mangadex", "series_id": "series-1"},
    )
    assert response.status_code == 200
    assert response.json()["affected"] == 1

    db_session.expire_all()
    assert db_session.get(Download, mangadex_row.id).status == "cancelled"
    assert db_session.get(Download, mangakatana_row.id).status == "queued"


def test_pause_all_and_resume_all_span_every_series(client: TestClient, db_session: Session):
    a1 = _seed_download(db_session, source="mangadex", series_id="series-a", chapter_id="a1")
    b1 = _seed_download(db_session, source="asurascans", series_id="series-b", chapter_id="b1")

    paused = client.post("/downloads/pause-all")
    assert paused.status_code == 200
    assert paused.json()["affected"] == 2

    db_session.expire_all()
    assert db_session.get(Download, a1.id).status == "paused"
    assert db_session.get(Download, b1.id).status == "paused"

    resumed = client.post("/downloads/resume-all")
    assert resumed.status_code == 200
    assert resumed.json()["affected"] == 2

    db_session.expire_all()
    assert db_session.get(Download, a1.id).status == "queued"
    assert db_session.get(Download, b1.id).status == "queued"


def test_cancel_all_spans_every_series_but_skips_completed(
    client: TestClient, db_session: Session
):
    a1 = _seed_download(db_session, source="mangadex", series_id="series-a", chapter_id="a1")
    b1 = _seed_download(
        db_session, source="asurascans", series_id="series-b", chapter_id="b1",
        status="completed", queue_state="completed",
    )

    response = client.post("/downloads/cancel-all")
    assert response.status_code == 200
    assert response.json()["affected"] == 1

    db_session.expire_all()
    assert db_session.get(Download, a1.id).status == "cancelled"
    assert db_session.get(Download, b1.id).status == "completed"


def test_metrics_report_queue_breakdown_and_overall_progress_keys(
    client: TestClient, db_session: Session
):
    _seed_download(db_session, source="mangadex", series_id="series-a", chapter_id="a1")
    _seed_download(
        db_session, source="mangadex", series_id="series-a", chapter_id="a2",
        status="paused", queue_state="paused",
    )

    response = client.get("/downloads/metrics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["queued"] == 1
    assert payload["paused"] == 1
    assert "overall_speed_bps" in payload
    assert "overall_speed_mbps" in payload
    assert "overall_eta_seconds" in payload


def test_pause_resume_cancel_retry(client: TestClient, db_session: Session):
    connector = _mock_connector()
    with patch("services.download_service.create_connector", return_value=connector):
        queued = client.post(
            "/downloads/chapters",
            json={
                "source_id": "mangadex",
                "series_id": "series-1",
                "chapter_ids": ["chapter-1"],
                "series_title": "Solo Leveling",
            },
        )
    download_id = queued.json()["queued"][0]

    paused = client.post(f"/downloads/{download_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = client.post(f"/downloads/{download_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"

    cancelled = client.post(f"/downloads/{download_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    download = db_session.get(Download, download_id)
    assert download is not None
    download.status = "failed"
    download.error = "network"
    db_session.commit()

    retried = client.post(f"/downloads/{download_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["retry_count"] == 1


def _priorities(db_session: Session, ids: list[int]) -> list[int]:
    db_session.expire_all()
    return [db_session.get(Download, i).queue.priority for i in ids]


def test_move_up_swaps_priority_with_the_next_sooner_sibling(
    client: TestClient, db_session: Session
):
    first = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c1", priority=0
    )
    second = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c2", priority=1
    )

    response = client.post(f"/downloads/{second.id}/move", json={"direction": "up"})

    assert response.status_code == 200
    assert _priorities(db_session, [first.id, second.id]) == [1, 0]


def test_move_down_swaps_priority_with_the_next_later_sibling(
    client: TestClient, db_session: Session
):
    first = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c1", priority=0
    )
    second = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c2", priority=1
    )

    response = client.post(f"/downloads/{first.id}/move", json={"direction": "down"})

    assert response.status_code == 200
    assert _priorities(db_session, [first.id, second.id]) == [1, 0]


def test_move_up_at_the_front_of_the_queue_is_a_noop(
    client: TestClient, db_session: Session
):
    first = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c1", priority=0
    )
    second = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c2", priority=1
    )

    response = client.post(f"/downloads/{first.id}/move", json={"direction": "up"})

    assert response.status_code == 200
    assert _priorities(db_session, [first.id, second.id]) == [0, 1]


def test_move_down_at_the_back_of_the_queue_is_a_noop(
    client: TestClient, db_session: Session
):
    first = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c1", priority=0
    )
    second = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c2", priority=1
    )

    response = client.post(f"/downloads/{second.id}/move", json={"direction": "down"})

    assert response.status_code == 200
    assert _priorities(db_session, [first.id, second.id]) == [0, 1]


def test_move_never_reorders_across_different_series(
    client: TestClient, db_session: Session
):
    same_series_item = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c1", priority=0
    )
    other_series_item = _seed_download(
        db_session, source="mangadex", series_id="series-2", chapter_id="c1", priority=1
    )

    response = client.post(
        f"/downloads/{same_series_item.id}/move", json={"direction": "down"}
    )

    assert response.status_code == 200
    # No sibling in the same series to swap with -- untouched, and the
    # unrelated series-2 item is never touched either.
    assert _priorities(db_session, [same_series_item.id, other_series_item.id]) == [0, 1]


def test_move_rejects_a_download_that_is_not_queued(
    client: TestClient, db_session: Session
):
    paused = _seed_download(
        db_session,
        source="mangadex",
        series_id="series-1",
        chapter_id="c1",
        status="paused",
        queue_state="paused",
    )

    response = client.post(f"/downloads/{paused.id}/move", json={"direction": "up"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_state"


def test_move_rejects_an_invalid_direction(client: TestClient, db_session: Session):
    download = _seed_download(
        db_session, source="mangadex", series_id="series-1", chapter_id="c1"
    )

    response = client.post(f"/downloads/{download.id}/move", json={"direction": "sideways"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_direction"


def test_process_download_imports_chapter(
    db_session: Session,
    download_manager: DownloadManager,
    downloads_root: Path,
):
    connector = _mock_connector()
    download = Download(
        source="mangadex",
        series_id="series-1",
        chapter_id="chapter-1",
        series_title="Solo Leveling",
        chapter_title="Chapter 1",
        status="queued",
    )
    db_session.add(download)
    db_session.flush()
    db_session.add(DownloadQueue(download_id=download.id, state="pending"))
    db_session.commit()
    download_id = download.id

    image_bytes = MINIMAL_PNG

    with patch("services.download_manager.create_connector", return_value=connector):
        with patch(
            "services.download_manager.fetch_image_resumable",
            side_effect=_fake_fetch_image,
        ):
            download_manager._process_download(download_id)

    db_session.expire_all()
    completed = db_session.get(Download, download_id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.progress == 100.0
    assert completed.local_chapter_id is not None

    chapter_dir = downloads_root / "Solo Leveling" / "Chapter 1"
    assert (chapter_dir / "001.jpg").exists()
    assert (chapter_dir / "002.webp").exists()
    assert (chapter_dir / ".manhwamaniacs-download.json").exists()

    link = (
        db_session.query(SourceChapterLink)
        .filter(SourceChapterLink.chapter_id == "chapter-1")
        .first()
    )
    assert link is not None
    assert link.local_chapter_id == completed.local_chapter_id


def test_resume_after_restart(download_manager: DownloadManager, db_session: Session):
    download = Download(
        source="mangadex",
        series_id="series-1",
        chapter_id="chapter-1",
        series_title="Solo Leveling",
        chapter_title="Chapter 1",
        status="downloading",
    )
    db_session.add(download)
    db_session.flush()
    db_session.add(DownloadQueue(download_id=download.id, state="active"))
    db_session.commit()

    download_manager._recover_interrupted()

    db_session.expire_all()
    row = db_session.get(Download, download.id)
    assert row is not None
    assert row.status == "queued"
    assert row.queue is not None
    assert row.queue.state == "pending"


def test_reader_uses_local_after_download(
    client: TestClient,
    db_session: Session,
    downloads_root: Path,
    download_manager: DownloadManager,
):
    connector = _mock_connector()
    with patch("services.download_service.create_connector", return_value=connector):
        queued = client.post(
            "/downloads/chapters",
            json={
                "source_id": "mangadex",
                "series_id": "series-1",
                "chapter_ids": ["chapter-1"],
                "series_title": "Solo Leveling",
            },
        )
    download_id = queued.json()["queued"][0]

    manager = download_manager
    with patch("services.download_manager.create_connector", return_value=connector):
        with patch(
            "services.download_manager.fetch_image_resumable",
            side_effect=_fake_fetch_image,
        ):
            manager._process_download(download_id)

    db_session.expire_all()
    completed = db_session.get(Download, download_id)
    assert completed is not None
    assert completed.local_chapter_id is not None

    reader = client.get(
        "/sources/mangadex/series/series-1/chapters/chapter-1/reader"
    )
    assert reader.status_code == 200
    payload = reader.json()
    assert payload["mode"] == "local"
    assert payload["pages"][0]["image_url"].startswith("/reader/page/")


def test_queue_priority_levels(client: TestClient, db_session: Session):
    connector = _mock_connector()
    with patch("services.download_service.create_connector", return_value=connector):
        single = client.post(
            "/downloads/chapters",
            json={
                "source_id": "mangadex",
                "series_id": "series-a",
                "chapter_ids": ["chapter-1"],
                "series_title": "Series A",
            },
        )
        multi = client.post(
            "/downloads/chapters",
            json={
                "source_id": "mangadex",
                "series_id": "series-b",
                "chapter_ids": ["chapter-1", "chapter-2"],
                "series_title": "Series B",
            },
        )
        series = client.post(
            "/downloads/series",
            json={"source_id": "mangadex", "series_id": "series-c"},
        )

    assert single.status_code == 200
    assert multi.status_code == 200
    assert series.status_code == 200

    single_queue = db_session.query(DownloadQueue).filter(
        DownloadQueue.download_id == single.json()["queued"][0]
    ).one()
    multi_queue = db_session.query(DownloadQueue).filter(
        DownloadQueue.download_id == multi.json()["queued"][0]
    ).one()
    series_queue = db_session.query(DownloadQueue).filter(
        DownloadQueue.download_id == series.json()["queued"][0]
    ).one()

    assert single_queue.priority == 0
    assert multi_queue.priority == 10
    assert series_queue.priority == 100


def test_metrics_endpoint(client: TestClient):
    response = client.get("/downloads/metrics")
    assert response.status_code == 200
    payload = response.json()
    assert "total" in payload
    assert "completed" in payload
    assert "failed" in payload
    assert "remaining" in payload
    assert "storage_used_bytes" in payload
    assert "profile" in payload


def test_retry_preserves_partial_progress(client: TestClient, db_session: Session):
    connector = _mock_connector()
    with patch("services.download_service.create_connector", return_value=connector):
        queued = client.post(
            "/downloads/chapters",
            json={
                "source_id": "mangadex",
                "series_id": "series-1",
                "chapter_ids": ["chapter-1"],
                "series_title": "Solo Leveling",
            },
        )
    download_id = queued.json()["queued"][0]
    download = db_session.get(Download, download_id)
    assert download is not None
    download.status = "failed"
    download.pages_done = 1
    download.pages_total = 2
    download.progress = 50.0
    download.bytes_downloaded = 1024
    db_session.commit()

    retried = client.post(f"/downloads/{download_id}/retry")
    assert retried.status_code == 200
    payload = retried.json()
    assert payload["status"] == "queued"
    assert payload["pages_done"] == 1
    assert payload["progress"] == 50.0


def test_resume_partial_chapter_download(
    db_session: Session,
    download_manager: DownloadManager,
    downloads_root: Path,
):
    from services.download_support import ChapterManifest, PageManifestEntry, sha256_bytes

    connector = _mock_connector()
    download = Download(
        source="mangadex",
        series_id="series-1",
        chapter_id="chapter-1",
        series_title="Solo Leveling",
        chapter_title="Chapter 1",
        status="queued",
        pages_done=1,
        pages_total=2,
        progress=50.0,
    )
    db_session.add(download)
    db_session.flush()
    db_session.add(DownloadQueue(download_id=download.id, state="pending"))
    db_session.commit()

    chapter_dir = downloads_root / "Solo Leveling" / "Chapter 1"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(MINIMAL_PNG)
    manifest = ChapterManifest(download_id=download.id, chapter_id="chapter-1")
    manifest.pages.append(
        PageManifestEntry(
            index=1,
            filename="001.jpg",
            remote_url="https://example.com/page1.jpg",
            sha256=sha256_bytes(MINIMAL_PNG),
            size=len(MINIMAL_PNG),
        )
    )
    manifest.save(chapter_dir)

    calls: list[str] = []

    def fetch_second_page(url: str, *, final_path, partial_path, **kwargs):
        calls.append(url)
        return _fake_fetch_image(url, final_path=final_path, partial_path=partial_path)

    with patch("services.download_manager.create_connector", return_value=connector):
        with patch(
            "services.download_manager.fetch_image_resumable",
            side_effect=fetch_second_page,
        ):
            download_manager._process_download(download.id)

    assert len(calls) == 1
    assert calls[0] == "https://example.com/page2.webp"

    db_session.expire_all()
    completed = db_session.get(Download, download.id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.pages_done == 2


def _mock_stream_response(content: bytes) -> MagicMock:
    response = MagicMock()
    response.is_redirect = False
    response.status_code = 200
    response.iter_bytes.return_value = [content]
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_process_download_blocks_ssrf_url(
    db_session: Session,
    download_manager: DownloadManager,
):
    connector = _mock_connector()
    connector.get_chapter_pages.return_value = [
        ConnectorPage(
            id="chapter-1:1",
            chapter_id="chapter-1",
            number=1,
            remote_url="https://evil.test/page1.jpg",
        ),
    ]
    download = Download(
        source="mangadex",
        series_id="series-1",
        chapter_id="chapter-1",
        series_title="Solo Leveling",
        chapter_title="Chapter 1",
        status="queued",
    )
    db_session.add(download)
    db_session.flush()
    db_session.add(DownloadQueue(download_id=download.id, state="pending"))
    db_session.commit()

    with patch("services.download_manager.create_connector", return_value=connector):
        with patch("services.download_support.httpx.stream") as mock_stream:
            download_manager._process_download(download.id)

    mock_stream.assert_not_called()
    db_session.expire_all()
    failed = db_session.get(Download, download.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error is not None


def test_process_download_succeeds_with_validated_fetch(
    db_session: Session,
    download_manager: DownloadManager,
    downloads_root: Path,
):
    connector = _mock_connector()
    download = Download(
        source="mangadex",
        series_id="series-1",
        chapter_id="chapter-1",
        series_title="Solo Leveling",
        chapter_title="Chapter 1",
        status="queued",
    )
    db_session.add(download)
    db_session.flush()
    db_session.add(DownloadQueue(download_id=download.id, state="pending"))
    db_session.commit()

    with patch("services.download_manager.create_connector", return_value=connector):
        with patch("services.outbound_security.is_public_address", return_value=True):
            with patch(
                "services.download_support.httpx.stream",
                return_value=_mock_stream_response(MINIMAL_PNG),
            ):
                download_manager._process_download(download.id)

    db_session.expire_all()
    completed = db_session.get(Download, download.id)
    assert completed is not None
    assert completed.status == "completed"
    assert (downloads_root / "Solo Leveling" / "Chapter 1" / "001.jpg").is_file()
    assert (downloads_root / "Solo Leveling" / "Chapter 1" / "002.webp").is_file()

