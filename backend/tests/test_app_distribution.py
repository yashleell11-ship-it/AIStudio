from __future__ import annotations

import json
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
    (shots / "shot-library-screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\n fake png")
    monkeypatch.setattr("routes.app_distribution.SCREENSHOTS_DIR", shots)

    response = client.get("/app/media/shot-library-screenshot.png")
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


def test_download_treats_directory_path_as_not_built(
    client: TestClient, tmp_path: Path, monkeypatch
):
    # In production the APK is a read-only bind mount; when no APK has been built
    # the mount surfaces as an (empty) directory, not a file. That must read as
    # "not built yet" (404), never a 500 from trying to stream a directory.
    apk_dir = tmp_path / "apk" / "app-release.apk"
    apk_dir.mkdir(parents=True)
    monkeypatch.setattr("routes.app_distribution.APK_PATH", apk_dir)

    assert client.get("/app/download").status_code == 404
    # The landing page still renders (in its build-pending state).
    landing = client.get("/", headers={"accept": "text/html"})
    assert landing.status_code == 200
    assert "APK not built yet" in landing.text


# ── iOS / SideStore source ───────────────────────────────────────────────────


def _fake_ipa(tmp_path: Path, monkeypatch) -> Path:
    ipa = tmp_path / "ManhwaManiacs.ipa"
    ipa.write_bytes(b"PK\x03\x04 fake ipa bytes")
    monkeypatch.setattr("routes.app_distribution.IPA_PATH", ipa)
    # The metadata is looked up beside the .ipa; make sure a stray env override
    # from the host can't point these tests at a real deploy's file.
    monkeypatch.delenv("MM_IOS_META_PATH", raising=False)
    return ipa


def test_ios_source_lists_published_build(
    client: TestClient, tmp_path: Path, monkeypatch
):
    ipa = _fake_ipa(tmp_path, monkeypatch)
    monkeypatch.setenv("MM_PUBLIC_BASE_URL", "https://app.manhwamaniacs.xyz")

    source = client.get("/app/source.json").json()
    assert source["name"] == "ManhwaManiacs"
    assert source["news"] == []

    app = source["apps"][0]
    # Bundle id must match the Xcode project or SideStore treats an update as a
    # separate app instead of replacing the installed one.
    assert app["bundleIdentifier"] == "com.manhwamaniacs.reader"

    version = app["versions"][0]
    assert version["downloadURL"] == (
        "https://app.manhwamaniacs.xyz/app/ios/download"
    )
    assert version["size"] == ipa.stat().st_size
    # No CI metadata beside this .ipa, so the pubspec numbers are the fallback.
    assert version["version"] == client.get("/app/version").json()["version"]
    assert version["buildVersion"] == str(client.get("/app/version").json()["build"])


def test_ios_source_advertises_ci_build_metadata(
    client: TestClient, tmp_path: Path, monkeypatch
):
    # The whole point of the metadata file: the build number CI stamped into the
    # binary is what gets advertised, *not* this server's pubspec. Without it,
    # pushing code would never surface an update on the phone.
    _fake_ipa(tmp_path, monkeypatch)
    (tmp_path / "ios-build.json").write_text(
        json.dumps(
            {
                "version": "9.9.9",
                "buildVersion": "1042",
                "date": "2026-01-02",
                "commit": "deadbee",
                "runId": "5",
            }
        ),
        encoding="utf-8",
    )

    version = client.get("/app/source.json").json()["apps"][0]["versions"][0]
    assert version["version"] == "9.9.9"
    assert version["buildVersion"] == "1042"
    assert version["date"] == "2026-01-02"
    # ...and the pubspec numbers it overrode are genuinely different, so this
    # test would fail if the fallback path were silently taken.
    assert client.get("/app/version").json()["version"] != "9.9.9"


def test_ios_source_survives_unusable_metadata(
    client: TestClient, tmp_path: Path, monkeypatch
):
    # A half-written or garbled metadata file must degrade to the pubspec
    # numbers, never 500 — a broken source URL takes SideStore out entirely.
    _fake_ipa(tmp_path, monkeypatch)
    pubspec = client.get("/app/version").json()

    for junk in ("not json at all", "[]", '{"buildVersion": "not-a-number"}'):
        (tmp_path / "ios-build.json").write_text(junk, encoding="utf-8")
        response = client.get("/app/source.json")
        assert response.status_code == 200, junk
        version = response.json()["apps"][0]["versions"][0]
        assert version["version"] == pubspec["version"], junk
        assert version["buildVersion"] == str(pubspec["build"]), junk


def test_ios_download_filename_names_the_published_build(
    client: TestClient, tmp_path: Path, monkeypatch
):
    _fake_ipa(tmp_path, monkeypatch)
    (tmp_path / "ios-build.json").write_text(
        json.dumps({"version": "9.9.9", "buildVersion": "1042"}), encoding="utf-8"
    )

    disposition = client.get("/app/ios/download").headers.get("content-disposition", "")
    assert "manhwamaniacs-9.9.9-1042.ipa" in disposition


def test_ios_source_uses_request_origin_when_unconfigured(
    client: TestClient, tmp_path: Path, monkeypatch
):
    # Without MM_PUBLIC_BASE_URL the manifest must still emit absolute URLs —
    # they are fetched by the phone, so a relative path would be unusable.
    _fake_ipa(tmp_path, monkeypatch)
    monkeypatch.delenv("MM_PUBLIC_BASE_URL", raising=False)

    version = client.get("/app/source.json").json()["apps"][0]["versions"][0]
    assert version["downloadURL"].startswith("http")
    assert version["downloadURL"].endswith("/app/ios/download")


def test_ios_source_valid_with_no_build_published(
    client: TestClient, tmp_path: Path, monkeypatch
):
    # A source with no installable version is still a *valid* source; SideStore
    # must be able to add it rather than erroring on an unpublished app.
    monkeypatch.setattr("routes.app_distribution.IPA_PATH", tmp_path / "missing.ipa")

    source = client.get("/app/source.json")
    assert source.status_code == 200
    assert source.json()["apps"][0]["versions"] == []
    assert client.get("/app/ios/download").status_code == 404


def test_ios_download_serves_ipa(client: TestClient, tmp_path: Path, monkeypatch):
    _fake_ipa(tmp_path, monkeypatch)
    response = client.get("/app/ios/download")
    assert response.status_code == 200
    assert response.content == b"PK\x03\x04 fake ipa bytes"
    assert ".ipa" in response.headers.get("content-disposition", "")


def test_ios_download_treats_directory_path_as_not_published(
    client: TestClient, tmp_path: Path, monkeypatch
):
    # Same failure mode as the APK: an empty read-only bind mount is a directory.
    ipa_dir = tmp_path / "ipa" / "ManhwaManiacs.ipa"
    ipa_dir.mkdir(parents=True)
    monkeypatch.setattr("routes.app_distribution.IPA_PATH", ipa_dir)
    assert client.get("/app/ios/download").status_code == 404
