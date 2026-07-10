from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from database.session import get_db
from main import create_app


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


def test_app_version_payload(client: TestClient):
    response = client.get("/app/version")
    assert response.status_code == 200
    data = response.json()
    assert data["apk"] == "/app/download"
    assert isinstance(data["build"], int)
    assert isinstance(data["version"], str) and data["version"]


def test_root_serves_html_to_browsers(client: TestClient, tmp_path: Path, monkeypatch):
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"PK\x03\x04 fake apk bytes")
    monkeypatch.setattr("routes.app_distribution.APK_PATH", apk)

    response = client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ManhwaManiacs" in response.text
    assert "/app/download" in response.text


def test_landing_page_has_product_sections(client: TestClient, tmp_path: Path, monkeypatch):
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"PK\x03\x04 fake apk bytes")
    monkeypatch.setattr("routes.app_distribution.APK_PATH", apk)

    html = client.get("/", headers={"accept": "text/html"}).text
    # Core product sections are present (hero, features, showcase, faq, download).
    for anchor in (
        'id="features"',
        'id="showcase"',
        'id="whatsnew"',
        'id="faq"',
        'id="download"',
        'id="support"',
    ):
        assert anchor in html
    # References its own live health probe and the bundled screenshots.
    assert "/health" in html
    assert "/app/media/" in html
    # Renders live version info from the pubspec.
    version = client.get("/app/version").json()["version"]
    assert version in html


def test_landing_page_handles_missing_apk(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("routes.app_distribution.APK_PATH", tmp_path / "missing.apk")
    response = client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert "ManhwaManiacs" in response.text
    assert "flutter build apk --release" in response.text


def test_changelog_payload(client: TestClient):
    response = client.get("/app/changelog")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert isinstance(entries, list) and entries
    first = entries[0]
    assert isinstance(first["version"], str) and first["version"]
    assert isinstance(first["build"], int)
    assert isinstance(first["highlights"], list) and first["highlights"]


def test_media_serves_known_screenshot(client: TestClient, tmp_path: Path, monkeypatch):
    shots = tmp_path / "screenshots"
    shots.mkdir()
    (shots / "reader-screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\n fake png")
    monkeypatch.setattr("routes.app_distribution.SCREENSHOTS_DIR", shots)

    response = client.get("/app/media/reader-screenshot.png")
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")


def test_media_rejects_traversal_and_unknown_types(
    client: TestClient, tmp_path: Path, monkeypatch
):
    shots = tmp_path / "screenshots"
    shots.mkdir()
    (shots / "ok.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "secret.txt").write_text("top secret")
    monkeypatch.setattr("routes.app_distribution.SCREENSHOTS_DIR", shots)

    # Path traversal is neutralised (only the basename is ever used).
    assert client.get("/app/media/../secret.txt").status_code in (404, 400)
    # Non-image extensions are refused even if present in the directory.
    (shots / "notes.txt").write_text("nope")
    assert client.get("/app/media/notes.txt").status_code == 404
    # Missing files 404.
    assert client.get("/app/media/does-not-exist.png").status_code == 404


def test_root_still_returns_json_for_api_clients(client: TestClient):
    # Default TestClient Accept is */*, so existing API behaviour is preserved.
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_health_probe_unchanged(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_download_returns_404_when_apk_missing(
    client: TestClient, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("routes.app_distribution.APK_PATH", tmp_path / "missing.apk")
    response = client.get("/app/download")
    assert response.status_code == 404


def test_download_serves_latest_apk(client: TestClient, tmp_path: Path, monkeypatch):
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"PK\x03\x04 latest build")
    monkeypatch.setattr("routes.app_distribution.APK_PATH", apk)

    response = client.get("/app/download")
    assert response.status_code == 200
    assert response.content == b"PK\x03\x04 latest build"
    assert "application/vnd.android.package-archive" in response.headers["content-type"]
    assert ".apk" in response.headers.get("content-disposition", "")
