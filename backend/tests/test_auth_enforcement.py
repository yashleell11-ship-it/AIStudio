"""Global API authentication gate, admin gating, and import-path containment.

These exercise the *real* auth stack (no default-admin auto-auth), proving that
the public instance is closed by default: every route needs a session except an
explicit public allowlist, destructive/admin operations need an admin session,
and library imports cannot escape the configured roots.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from database.session import get_db
from main import create_app

# Drive real registration/login; opt out of the suite's default-admin auto-auth.
pytestmark = pytest.mark.real_auth


@pytest.fixture
def client(db_engine, monkeypatch):
    # Local-dev cookie posture so httpx persists the session cookie over
    # http://testserver (a Secure cookie would not round-trip in the test jar).
    monkeypatch.setenv("MM_COOKIE_SECURE", "false")
    get_settings.cache_clear()

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
    get_settings.cache_clear()


def _register(client: TestClient, username: str = "owner", password: str = "supersecret", **kw):
    return client.post(
        "/auth/register",
        json={"username": username, "password": password, **kw},
    )


def _fresh(client: TestClient) -> TestClient:
    """A second client against the same app with no cookie jar (anonymous)."""
    anon = TestClient(client.app)
    anon.cookies.clear()
    return anon


def _build_series(library_root: Path) -> None:
    chapter_dir = library_root / "Solo Leveling" / "Chapter 001"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"fake-image")
    (chapter_dir / "002.jpg").write_bytes(b"fake-image-2")


# --- the global gate: public allowlist vs everything else --------------------


def test_public_routes_need_no_session(client):
    anon = _fresh(client)
    assert anon.get("/health").status_code == 200
    status = anon.get("/auth/bootstrap-status")
    assert status.status_code == 200
    assert status.json()["needs_bootstrap"] is True


def test_unauthenticated_api_request_is_401(client):
    anon = _fresh(client)
    listing = anon.get("/library/series")
    assert listing.status_code == 401
    assert listing.json()["code"] == "not_authenticated"
    # write surface is closed too
    assert anon.post("/library/import", json={"folder_path": "/tmp"}).status_code == 401


def test_authenticated_user_can_read_the_library(client):
    _register(client)  # first account → admin, cookie now in the jar
    assert client.get("/library/series").status_code == 200


def test_bootstrap_status_flips_after_first_account(client):
    _register(client)
    status = _fresh(client).get("/auth/bootstrap-status").json()
    assert status["needs_bootstrap"] is False


# --- admin gating on destructive/admin operations ----------------------------


def _login_second_nonadmin(client) -> TestClient:
    """Register the bootstrap admin, then a second (non-admin) user, and return a
    client authenticated as that non-admin."""
    _register(client, username="owner")
    _register(client, username="reader")  # second account is not admin
    reader = _fresh(client)
    reader.post("/auth/login", json={"username": "reader", "password": "supersecret"})
    return reader


def test_library_import_requires_admin(client, tmp_path):
    reader = _login_second_nonadmin(client)
    library_root = tmp_path / "Library"
    _build_series(library_root)
    resp = reader.post(
        "/library/import", json={"folder_path": str(library_root.resolve())}
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "forbidden"


def test_admin_can_import_and_list(client, tmp_path):
    _register(client)  # admin
    library_root = tmp_path / "Library"
    _build_series(library_root)
    resp = client.post(
        "/library/import", json={"folder_path": str(library_root.resolve())}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["series_count"] == 1
    items = client.get("/library/series").json()["items"]
    assert [item["title"] for item in items] == ["Solo Leveling"]


def test_backup_export_requires_admin(client):
    anon = _fresh(client)
    assert anon.get("/backup/export").status_code == 401  # no session
    reader = _login_second_nonadmin(client)
    assert reader.get("/backup/export").status_code == 403  # session, not admin


def test_backup_import_requires_admin(client, tmp_path):
    reader = _login_second_nonadmin(client)
    upload = tmp_path / "backup.db"
    upload.write_bytes(b"SQLite format 3\x00")
    with upload.open("rb") as handle:
        resp = reader.post(
            "/backup/import",
            files={"file": ("backup.db", handle, "application/octet-stream")},
        )
    assert resp.status_code == 403


def test_admin_can_export_backup(client):
    _register(client)  # admin
    resp = client.get("/backup/export")
    assert resp.status_code == 200
    assert resp.content.startswith(b"SQLite format 3")


# --- import-path containment (cannot escape the configured roots) -------------


@pytest.mark.parametrize("escape", ["/etc", "/", "/root", "/nonexistent-xyz-path"])
def test_import_outside_allowlist_is_forbidden_even_for_admin(client, escape):
    """An admin session is necessary but NOT sufficient: the target must resolve
    under a configured import root. Arbitrary host paths are 403 (not 500), and
    the check runs before any filesystem probe so even non-existent paths are
    rejected at the containment layer rather than as 'not a directory'."""
    _register(client)  # admin
    resp = client.post("/library/import", json={"folder_path": escape})
    assert resp.status_code == 403
    assert resp.json()["code"] == "path_traversal"


def test_import_rejects_relative_paths(client):
    _register(client)  # admin
    resp = client.post("/library/import", json={"folder_path": "relative/dir"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_path"
