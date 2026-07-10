"""Part 5/6: configurable concurrent chapter downloads, persisted settings."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from connectors.models import Page as ConnectorPage
from core.config import Settings, get_settings, update_persisted_settings
from database.models import Download, DownloadQueue
from database.session import get_db
from main import create_app
from services.download_manager import (
    MAX_CONCURRENT_CHAPTER_DOWNLOADS,
    DownloadManager,
    reset_download_manager_for_tests,
)


@pytest.fixture
def downloads_root(tmp_path: Path) -> Path:
    root = tmp_path / "downloads"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(autouse=True)
def _isolated_settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point SETTINGS_PATH at a throwaway file so these tests never touch
    the real config/settings.json, and clear the get_settings() cache
    before and after so no state leaks between tests."""
    fake_path = tmp_path / "settings.json"
    monkeypatch.setattr("core.config.SETTINGS_PATH", fake_path)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


def test_default_concurrent_chapters_is_one():
    """Part 5: downloads must default to fully sequential (1 chapter at a
    time) unless the user has explicitly configured otherwise."""
    settings = Settings()
    assert settings.download_concurrent_chapters == 1


def test_update_persisted_settings_writes_file_and_refreshes_cache(tmp_path: Path):
    before = get_settings()
    assert before.download_concurrent_chapters == 1

    updated = update_persisted_settings(download_concurrent_chapters=5)

    assert updated.download_concurrent_chapters == 5
    # The very next get_settings() call reflects the change immediately --
    # no restart, no re-import.
    assert get_settings().download_concurrent_chapters == 5


def test_update_persisted_settings_survives_a_fresh_read_from_disk():
    """Simulates an app restart: clear the cache and read settings.json
    from scratch. The value must still be there."""
    update_persisted_settings(download_concurrent_chapters=7)
    get_settings.cache_clear()
    assert get_settings().download_concurrent_chapters == 7


def test_update_persisted_settings_preserves_unrelated_keys(tmp_path: Path):
    from core import config as config_module

    config_module.SETTINGS_PATH.write_text(
        json.dumps({"project_name": "Custom Name", "custom_setting": "keep-me"}),
        encoding="utf-8",
    )
    get_settings.cache_clear()

    update_persisted_settings(download_concurrent_chapters=3)

    on_disk = json.loads(config_module.SETTINGS_PATH.read_text(encoding="utf-8"))
    assert on_disk["project_name"] == "Custom Name"
    assert on_disk["custom_setting"] == "keep-me"
    assert on_disk["download_concurrent_chapters"] == 3


class TestDownloadManagerConcurrency:
    def test_constructor_reads_configured_concurrency(self):
        update_persisted_settings(download_concurrent_chapters=3)
        manager = DownloadManager()
        assert manager.max_workers == 3

    def test_constructor_clamps_to_the_absolute_ceiling(self):
        manager = DownloadManager(max_workers=999)
        assert manager.max_workers == MAX_CONCURRENT_CHAPTER_DOWNLOADS

    def test_set_max_workers_changes_the_limit_immediately(self):
        manager = DownloadManager(max_workers=1)
        assert manager.max_workers == 1

        manager.set_max_workers(6)

        assert manager.max_workers == 6

    def test_set_max_workers_clamps_to_valid_range(self):
        manager = DownloadManager(max_workers=1)

        manager.set_max_workers(999)
        assert manager.max_workers == MAX_CONCURRENT_CHAPTER_DOWNLOADS

        manager.set_max_workers(0)
        assert manager.max_workers == 1

    def test_active_count_reflects_currently_dispatched_downloads(self):
        manager = DownloadManager(max_workers=2)
        assert manager.active_count == 0


class TestSchedulerRespectsTheConfiguredLimit:
    """End-to-end: real DownloadManager.start()/dispatch() lifecycle with
    several chapters queued at once, proving the scheduler never runs more
    concurrent chapter downloads than configured -- and that lowering or
    raising the limit at runtime (Part 5) changes behavior on the next
    dispatch without needing to stop/restart anything."""

    @staticmethod
    def _mock_connector() -> MagicMock:
        # A single page per chapter, so the only concurrency the fetch mock
        # can observe is CHAPTER-level -- Part 3's internal page-concurrency
        # is a separate, independent axis and must not confound this test.
        connector = MagicMock()
        connector.allowed_image_hosts = frozenset({"example.com"})
        connector.get_chapter_pages.return_value = [
            ConnectorPage(
                id="p1", chapter_id="irrelevant", number=1,
                remote_url="https://example.com/1.png",
            )
        ]
        return connector

    def _seed_queued_chapters(self, db_session, count: int) -> list[int]:
        ids: list[int] = []
        for i in range(count):
            download = Download(
                source="mangadex",
                series_id="series-1",
                chapter_id=f"c{i}",
                series_title="Concurrency Test Series",
                chapter_title=f"Chapter {i}",
                status="queued",
            )
            db_session.add(download)
            db_session.flush()
            db_session.add(DownloadQueue(download_id=download.id, state="pending"))
            ids.append(download.id)
        db_session.commit()
        return ids

    @staticmethod
    def _slow_fetch(url, *, connector, final_path, partial_path, **kwargs):
        # Long enough that concurrently-dispatched chapters reliably overlap
        # inside this sleep even under a loaded CI machine — otherwise the
        # "chapters overlapped" assertions become timing-flaky under load.
        time.sleep(0.2)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff"
            b"\xff?\x00\x05\xfe\x02\xfe\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return final_path.read_bytes()

    def _track_chapter_concurrency(self, manager: DownloadManager) -> dict[str, int]:
        """Wrap the real _process_download so we count concurrent CHAPTERS
        being processed, independent of how many pages each one fetches
        internally in parallel."""
        lock = threading.Lock()
        state = {"concurrent": 0, "max_seen": 0}
        original = manager._process_download

        def _tracked(download_id: int) -> None:
            with lock:
                state["concurrent"] += 1
                state["max_seen"] = max(state["max_seen"], state["concurrent"])
            try:
                original(download_id)
            finally:
                with lock:
                    state["concurrent"] -= 1

        manager._process_download = _tracked
        return state

    def _run_until_drained(self, db_session, chapter_ids: list[int], manager: DownloadManager) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            db_session.expire_all()
            remaining = (
                db_session.query(Download)
                .filter(Download.id.in_(chapter_ids), Download.status == "queued")
                .count()
            )
            if remaining == 0 and manager.active_count == 0:
                return
            time.sleep(0.05)
        pytest.fail("downloads did not drain within the test deadline")

    def test_never_exceeds_the_configured_concurrent_chapter_limit(
        self, db_engine, downloads_root, db_session
    ):
        session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
        manager = DownloadManager(max_workers=2)
        manager._downloads_root = downloads_root
        reset_download_manager_for_tests(manager)
        state = self._track_chapter_concurrency(manager)

        chapter_ids = self._seed_queued_chapters(db_session, count=6)
        connector = self._mock_connector()

        with patch("services.download_manager.SessionLocal", session_factory):
            with patch("services.download_manager.create_connector", return_value=connector):
                with patch(
                    "services.download_manager.fetch_image_resumable",
                    side_effect=self._slow_fetch,
                ):
                    manager.start()
                    self._run_until_drained(db_session, chapter_ids, manager)
                    manager.stop()

        assert state["max_seen"] <= 2, (
            f"scheduler ran {state['max_seen']} chapters concurrently, "
            "exceeding the configured limit of 2"
        )
        assert state["max_seen"] >= 2, (
            "expected at least 2 chapters to overlap -- if this is 1, "
            "concurrency isn't actually happening and the test is too weak"
        )

    def test_raising_the_limit_at_runtime_allows_more_concurrent_chapters(
        self, db_engine, downloads_root, db_session
    ):
        session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
        manager = DownloadManager(max_workers=1)
        manager._downloads_root = downloads_root
        reset_download_manager_for_tests(manager)
        state = self._track_chapter_concurrency(manager)

        chapter_ids = self._seed_queued_chapters(db_session, count=6)
        connector = self._mock_connector()

        with patch("services.download_manager.SessionLocal", session_factory):
            with patch("services.download_manager.create_connector", return_value=connector):
                with patch(
                    "services.download_manager.fetch_image_resumable",
                    side_effect=self._slow_fetch,
                ):
                    manager.start()
                    # Give it one dispatch cycle at concurrency=1, then raise
                    # the limit -- exactly the "Settings" UI flow, without
                    # stopping/restarting the manager.
                    time.sleep(0.05)
                    manager.set_max_workers(3)

                    self._run_until_drained(db_session, chapter_ids, manager)
                    manager.stop()

        assert manager.max_workers == 3
        assert state["max_seen"] > 1, (
            "raising the limit at runtime should have allowed more than 1 "
            "chapter to download concurrently without restarting anything"
        )


class TestDownloadSettingsApi:
    """Part 6: GET/PUT /downloads/settings."""

    def test_get_settings_returns_defaults_and_active_count(self, client: TestClient):
        response = client.get("/downloads/settings")
        assert response.status_code == 200
        payload = response.json()
        assert payload["download_concurrent_chapters"] == 1
        assert payload["download_page_concurrency"] == 4
        assert payload["download_retry_count"] == 4
        assert payload["download_retry_delay_seconds"] == 0.75
        assert payload["download_timeout_seconds"] == 30.0
        assert payload["active_download_count"] == 0

    def test_put_settings_updates_concurrent_chapters_and_applies_immediately(
        self, client: TestClient, download_manager: DownloadManager
    ):
        response = client.put(
            "/downloads/settings", json={"download_concurrent_chapters": 5}
        )
        assert response.status_code == 200
        assert response.json()["download_concurrent_chapters"] == 5
        # The exact manager instance backing this API call picked it up
        # without needing a restart.
        assert download_manager.max_workers == 5

    def test_put_settings_persists_across_a_cache_clear(self, client: TestClient):
        client.put("/downloads/settings", json={"download_retry_count": 8})
        get_settings.cache_clear()
        assert get_settings().download_retry_count == 8

    def test_put_settings_rejects_out_of_range_values(self, client: TestClient):
        response = client.put(
            "/downloads/settings", json={"download_concurrent_chapters": 11}
        )
        assert response.status_code == 422

    def test_put_settings_only_updates_provided_fields(self, client: TestClient):
        client.put("/downloads/settings", json={"download_concurrent_chapters": 4})
        response = client.put(
            "/downloads/settings", json={"download_retry_count": 2}
        )
        payload = response.json()
        assert payload["download_retry_count"] == 2
        # Untouched by this second call.
        assert payload["download_concurrent_chapters"] == 4
