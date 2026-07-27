from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from connectors.models import Chapter as ConnectorChapter
from database.models import Download, SeriesTracker, UpdateNotification, UpdateSettings
from database.session import get_db
from main import create_app
from services.update_service import UpdateService


def _chapter(chapter_id: str, *, number: int | None = None, title: str = "Chapter") -> ConnectorChapter:
    return ConnectorChapter(
        id=chapter_id,
        series_id="series-1",
        title=title,
        number=number,
        page_count=10,
    )


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
    app.dependency_overrides.clear()


@pytest.fixture
def db_session(db_engine) -> Session:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_global_settings_defaults(db_session: Session) -> None:
    service = UpdateService(db_session)
    settings = service.get_global_settings()
    assert settings.id == 1
    payload = service.serialize_settings(settings)
    assert payload["enabled"] is True
    assert payload["check_interval_minutes"] >= 5


def test_get_global_settings_idempotent_across_sessions(db_engine) -> None:
    """get_global_settings must never raise even when called from two separate
    sessions — this guards against the startup race between the scheduler thread
    (_current_interval_minutes) and the main thread (_maybe_run_startup_check)
    where both sessions previously tried to INSERT id=1 concurrently."""
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    s1 = factory()
    s2 = factory()
    try:
        # s1 creates and commits the row (simulates first caller winning the race)
        UpdateService(s1).get_global_settings()
        s1.commit()

        # s2 must return the existing row without raising IntegrityError
        row = UpdateService(s2).get_global_settings()
        s2.commit()

        assert row.id == 1
    finally:
        s1.close()
        s2.close()


def test_get_global_settings_repeated_call_same_session(db_session: Session) -> None:
    """Calling get_global_settings twice on the same session must not raise."""
    svc = UpdateService(db_session)
    r1 = svc.get_global_settings()
    r2 = svc.get_global_settings()
    assert r1.id == r2.id == 1


def test_follow_series_creates_tracker(db_session: Session) -> None:
    service = UpdateService(db_session)
    with patch.object(service, "_ensure_browsable_source"):
        tracker = service.follow_series(
            source="mangadex",
            series_id="abc-123",
            series_title="Test Series",
        )
    assert tracker["track_kind"] == "followed"
    assert tracker["series_id"] == "abc-123"


def test_follow_series_is_idempotent(db_session: Session) -> None:
    service = UpdateService(db_session)
    with patch.object(service, "_ensure_browsable_source"):
        first = service.follow_series(
            source="mangadex",
            series_id="abc-123",
            series_title="Test Series",
        )
        second = service.follow_series(
            source="mangadex",
            series_id="abc-123",
            series_title="Test Series",
        )
    assert first["id"] == second["id"]


def test_sync_downloaded_trackers(db_session: Session) -> None:
    db_session.add(
        Download(
            source="mangadex",
            series_id="series-1",
            chapter_id="ch-1",
            series_title="Downloaded Series",
            chapter_title="Chapter 1",
            status="completed",
        )
    )
    db_session.flush()

    service = UpdateService(db_session)
    result = service.sync_downloaded_trackers()
    assert result["created"] == 1
    trackers = service.list_trackers(track_kind="downloaded")
    assert len(trackers) == 1
    assert trackers[0]["series_title"] == "Downloaded Series"


def test_check_tracker_baseline_no_notifications(db_session: Session) -> None:
    tracker = SeriesTracker(
        source="mangadex",
        series_id="series-1",
        series_title="Series",
        track_kind="followed",
    )
    db_session.add(tracker)
    db_session.flush()

    mock_connector = MagicMock()
    mock_connector.get_chapters.return_value = [
        _chapter("ch-1", number=1),
        _chapter("ch-2", number=2),
    ]

    service = UpdateService(db_session)
    settings = service.get_global_settings()

    with patch("services.update_service.create_connector", return_value=mock_connector):
        new_count = service._check_tracker(tracker, settings)

    assert new_count == 0
    assert db_session.query(UpdateNotification).count() == 0
    db_session.refresh(tracker)
    assert "ch-1" in tracker.known_chapter_ids
    assert "ch-2" in tracker.known_chapter_ids


def test_check_tracker_detects_new_chapters(db_session: Session) -> None:
    tracker = SeriesTracker(
        source="mangadex",
        series_id="series-1",
        series_title="Series",
        track_kind="followed",
        known_chapter_ids='["ch-1"]',
    )
    db_session.add(tracker)
    db_session.flush()

    mock_connector = MagicMock()
    mock_connector.get_chapters.return_value = [
        _chapter("ch-1", number=1),
        _chapter("ch-2", number=2, title="New Chapter"),
    ]

    service = UpdateService(db_session)
    settings = service.get_global_settings()

    with patch("services.update_service.create_connector", return_value=mock_connector):
        new_count = service._check_tracker(tracker, settings)

    assert new_count == 1
    notifications = db_session.query(UpdateNotification).all()
    assert len(notifications) == 1
    assert notifications[0].chapter_id == "ch-2"


def test_auto_download_queues_new_chapters_when_enabled(db_session: Session) -> None:
    from services.update_auto_download import auto_download_new_chapters
    from services.update_service import register_new_chapters_callback

    register_new_chapters_callback(auto_download_new_chapters)

    tracker = SeriesTracker(
        source="mangadex",
        series_id="series-1",
        series_title="Series",
        track_kind="followed",
        known_chapter_ids='["ch-1"]',
        auto_download=True,
    )
    db_session.add(tracker)
    db_session.flush()

    service = UpdateService(db_session)
    settings = service.get_global_settings()
    service.update_global_settings({"auto_download_enabled": True})
    settings = service.get_global_settings()

    mock_connector = MagicMock()
    # A bare MagicMock is truthy for every attribute, including is_mature —
    # which the 18+ enqueue gate now reads. Pin it so this non-adult fixture
    # is not 404'd by the gate.
    mock_connector.is_mature = False
    mock_connector.is_browsable = True
    mock_connector.get_chapters.return_value = [
        _chapter("ch-1", number=1),
        _chapter("ch-2", number=2, title="New Chapter"),
    ]
    mock_connector.get_series.return_value = MagicMock(title="Series")

    with patch("services.update_service.create_connector", return_value=mock_connector):
        with patch("services.download_service.create_connector", return_value=mock_connector):
            new_count = service._check_tracker(tracker, settings)

    assert new_count == 1
    downloads = (
        db_session.query(Download)
        .filter(
            Download.source == "mangadex",
            Download.series_id == "series-1",
            Download.chapter_id == "ch-2",
        )
        .all()
    )
    assert len(downloads) == 1
    assert downloads[0].status == "queued"


def test_run_check_records_run(db_session: Session) -> None:
    tracker = SeriesTracker(
        source="mangadex",
        series_id="series-1",
        series_title="Series",
        track_kind="followed",
        known_chapter_ids='["ch-1"]',
    )
    db_session.add(tracker)
    db_session.flush()

    mock_connector = MagicMock()
    mock_connector.get_chapters.return_value = [_chapter("ch-1", number=1)]

    service = UpdateService(db_session)
    with patch("services.update_service.create_connector", return_value=mock_connector):
        result = service.run_check(trigger="manual", tracker_ids=[tracker.id])

    assert result["status"] == "completed"
    assert result["series_checked"] == 1


def test_api_settings_and_follow(client: TestClient) -> None:
    with patch(
        "services.update_service.list_installed_connectors",
        return_value=[MagicMock(source_type="mangadex", name="MangaDex")],
    ):
        response = client.get("/updates/settings")
        assert response.status_code == 200
        assert response.json()["enabled"] is True

        follow = client.post(
            "/updates/trackers/follow",
            json={
                "source": "mangadex",
                "series_id": "series-1",
                "series_title": "My Series",
            },
        )
        assert follow.status_code == 200
        assert follow.json()["track_kind"] == "followed"


def test_api_notifications_unread_count(client: TestClient, db_session: Session) -> None:
    settings = UpdateSettings(id=1, enabled=True, check_interval_minutes=60)
    tracker = SeriesTracker(
        source="mangadex",
        series_id="series-1",
        series_title="Series",
        track_kind="followed",
    )
    db_session.add_all([settings, tracker])
    db_session.flush()
    db_session.add(
        UpdateNotification(
            tracker_id=tracker.id,
            source="mangadex",
            series_id="series-1",
            series_title="Series",
            chapter_id="ch-2",
            chapter_title="Chapter 2",
        )
    )
    db_session.commit()

    response = client.get("/updates/notifications/unread-count")
    assert response.status_code == 200
    assert response.json()["count"] == 1

    mark_all = client.post("/updates/notifications/read-all")
    assert mark_all.status_code == 200
    assert mark_all.json()["marked_read"] == 1


def test_api_manual_check(client: TestClient, db_session: Session) -> None:
    """With run_workers=False (this fixture's app), there is no worker pool
    to dispatch to, so the route falls back to running the check inline."""
    tracker = SeriesTracker(
        source="mangadex",
        series_id="series-1",
        series_title="Series",
        track_kind="followed",
        known_chapter_ids="[]",
    )
    db_session.add(tracker)
    db_session.commit()

    mock_connector = MagicMock()
    mock_connector.get_chapters.return_value = [_chapter("ch-1", number=1)]

    with patch("services.update_service.create_connector", return_value=mock_connector):
        response = client.post(
            "/updates/check",
            json={"tracker_ids": [tracker.id]},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_api_manual_check_queues_without_blocking_when_manager_running(
    client: TestClient,
) -> None:
    """When the background worker pool is running, the request thread must
    never call the (potentially slow) synchronous check path — it should
    just queue the work and return immediately."""
    fake_manager = MagicMock()
    fake_manager.is_running = True
    fake_manager.trigger_check.return_value = True

    with patch("routes.updates.get_update_manager", return_value=fake_manager):
        with patch(
            "services.update_service.UpdateService.run_check"
        ) as mock_run_check:
            response = client.post("/updates/check", json={})

    assert response.status_code == 200
    assert response.json() == {"queued": True, "trigger": "manual"}
    fake_manager.trigger_check.assert_called_once_with(
        trigger="manual", tracker_ids=None
    )
    # The blocking/synchronous path must never be invoked in this branch.
    mock_run_check.assert_not_called()


def test_api_manual_check_returns_409_when_a_check_is_already_running(
    client: TestClient,
) -> None:
    """A busy manager must surface as 409, not a request that hangs until
    the in-flight scan finishes."""
    fake_manager = MagicMock()
    fake_manager.is_running = True
    fake_manager.trigger_check.return_value = False

    with patch("routes.updates.get_update_manager", return_value=fake_manager):
        with patch(
            "services.update_service.UpdateService.run_check"
        ) as mock_run_check:
            response = client.post("/updates/check", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "check_already_running"
    mock_run_check.assert_not_called()
