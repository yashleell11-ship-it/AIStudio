"""Global API authentication gate, admin gating, and per-profile scope.

These exercise the *real* auth stack (no default-admin auto-auth), proving the
public instance is closed by default: every route needs a session except an
explicit public allowlist, admin operations need an admin session, and — new in
the source-native rebuild — a profile's library/progress/collections are scoped
to ``(user_id, profile_id)`` and invisible to the account's other profiles.
"""

from __future__ import annotations

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
        "/auth/register", json={"username": username, "password": password, **kw}
    )


def _fresh(client: TestClient) -> TestClient:
    """A second client against the same app with no cookie jar (anonymous)."""
    anon = TestClient(client.app)
    anon.cookies.clear()
    return anon


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
    # the write surface is closed too
    assert (
        anon.post(
            "/library/follow",
            json={"source_id": "mangadex", "series_key": "s1"},
        ).status_code
        == 401
    )


def test_authenticated_user_can_read_the_library(client):
    _register(client)  # first account → admin, cookie now in the jar
    assert client.get("/library/series").status_code == 200


def test_bootstrap_status_flips_after_first_account(client):
    _register(client)
    status = _fresh(client).get("/auth/bootstrap-status").json()
    assert status["needs_bootstrap"] is False


# --- admin gating -----------------------------------------------------------


def _login_second_nonadmin(client) -> TestClient:
    _register(client, username="owner")
    _register(client, username="reader")  # second account is not admin
    reader = _fresh(client)
    reader.post("/auth/login", json={"username": "reader", "password": "supersecret"})
    return reader


def test_backup_export_requires_admin(client):
    anon = _fresh(client)
    assert anon.get("/backup/export").status_code == 401  # no session
    reader = _login_second_nonadmin(client)
    assert reader.get("/backup/export").status_code == 403  # session, not admin


def test_admin_can_export_backup(client):
    _register(client)  # admin
    resp = client.get("/backup/export")
    assert resp.status_code == 200
    assert resp.content.startswith(b"SQLite format 3")


# --- per-profile scope (spec §5.3) -----------------------------------------


def _make_profile(client: TestClient, name: str) -> int:
    resp = client.post("/profiles", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_follows_are_scoped_per_profile_on_one_account(client):
    _register(client)  # admin, logged in
    p_a = _make_profile(client, "A")
    p_b = _make_profile(client, "B")

    follow = client.post(
        "/library/follow",
        json={"source_id": "mangadex", "series_key": "a-only"},
        headers={"X-Profile-Id": str(p_a)},
    )
    assert follow.status_code == 200, follow.text

    seen_a = client.get("/library/series", headers={"X-Profile-Id": str(p_a)}).json()
    seen_b = client.get("/library/series", headers={"X-Profile-Id": str(p_b)}).json()
    assert [s["series_key"] for s in seen_a["items"]] == ["a-only"]
    assert seen_b["items"] == []


def test_mutating_route_requires_a_profile_when_the_account_has_profiles(client):
    _register(client)
    _make_profile(client, "A")
    # No X-Profile-Id header → 400 profile_required (account owns profiles).
    resp = client.post(
        "/library/follow", json={"source_id": "mangadex", "series_key": "s1"}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "profile_required"


def test_foreign_profile_id_is_not_found_not_disclosed(client):
    _register(client, username="owner")
    _register(client, username="reader")
    # owner creates a profile
    owner = _fresh(client)
    owner.post("/auth/login", json={"username": "owner", "password": "supersecret"})
    owner_profile = _make_profile(owner, "Owner P")

    reader = _fresh(client)
    reader.post("/auth/login", json={"username": "reader", "password": "supersecret"})
    # reader points X-Profile-Id at the owner's profile
    resp = reader.post(
        "/library/follow",
        json={"source_id": "mangadex", "series_key": "s1"},
        headers={"X-Profile-Id": str(owner_profile)},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "profile_not_found"
