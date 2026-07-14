"""Reading profiles: per-user CRUD, ownership isolation, limits, and auth gate.

Service-level tests drive :class:`ProfileService` directly with real ``user_id``s
(mirroring test_multiuser_isolation) to prove ownership scoping without threading
HTTP auth through every case. HTTP tests use the real auth stack to prove the 401
gate and that the advisory ``X-Profile-Id`` header never fails a request.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from core.errors import AppError
from database.models import User
from database.session import get_db
from main import create_app
from services.profile_service import ProfileService


@pytest.fixture
def users(db_session):
    """Two distinct accounts sharing nothing."""
    alice = User(username="alice", password_hash="x")
    bob = User(username="bob", password_hash="x")
    db_session.add_all([alice, bob])
    db_session.commit()
    return {"alice": alice.id, "bob": bob.id}


# --- CRUD (service layer) ----------------------------------------------------


def test_create_and_list_profiles_ordered(db_session, users):
    svc = ProfileService(db_session, user_id=users["alice"])
    svc.create_profile(name="Second", mood="action", sort_order=2)
    svc.create_profile(name="First", mood="romantic", sort_order=1)

    names = [p.name for p in svc.list_profiles()]
    assert names == ["First", "Second"]  # ordered by sort_order

    first = svc.list_profiles()[0]
    assert first.mood == "romantic"
    assert first.avatar_key == "default"  # defaulted when omitted


def test_create_appends_sort_order_when_omitted(db_session, users):
    svc = ProfileService(db_session, user_id=users["alice"])
    a = svc.create_profile(name="A")
    b = svc.create_profile(name="B")
    assert (a.sort_order, b.sort_order) == (0, 1)


def test_update_profile(db_session, users):
    svc = ProfileService(db_session, user_id=users["alice"])
    created = svc.create_profile(name="Old", mood="default")
    updated = svc.update_profile(created.id, name="New", mood="horror")
    assert updated.name == "New"
    assert updated.mood == "horror"
    # unspecified fields are unchanged
    assert updated.avatar_key == created.avatar_key


def test_delete_profile(db_session, users):
    svc = ProfileService(db_session, user_id=users["alice"])
    created = svc.create_profile(name="Temp")
    svc.delete_profile(created.id)
    assert svc.list_profiles() == []


def test_invalid_mood_rejected(db_session, users):
    svc = ProfileService(db_session, user_id=users["alice"])
    with pytest.raises(AppError) as exc:
        svc.create_profile(name="X", mood="not-a-mood")
    assert exc.value.status_code == 422
    assert exc.value.code == "invalid_mood"


# --- ownership isolation -----------------------------------------------------


def test_profiles_are_isolated_between_users(db_session, users):
    alice = ProfileService(db_session, user_id=users["alice"])
    bob = ProfileService(db_session, user_id=users["bob"])

    created = alice.create_profile(name="Alice's")

    # Bob sees none of Alice's profiles.
    assert bob.list_profiles() == []
    assert len(alice.list_profiles()) == 1

    # Bob cannot read/modify/delete Alice's profile (scoped → 404, not 403).
    with pytest.raises(AppError) as upd:
        bob.update_profile(created.id, name="hijacked")
    assert upd.value.status_code == 404
    with pytest.raises(AppError) as dele:
        bob.delete_profile(created.id)
    assert dele.value.status_code == 404

    # Alice's profile survives Bob's attempts, unchanged.
    survivor = alice.list_profiles()[0]
    assert survivor.name == "Alice's"


# --- max-5 enforcement -------------------------------------------------------


def test_max_five_profiles_enforced_per_user(db_session, users):
    alice = ProfileService(db_session, user_id=users["alice"])
    for i in range(ProfileService.MAX_PROFILES_PER_USER):
        alice.create_profile(name=f"P{i}")

    with pytest.raises(AppError) as exc:
        alice.create_profile(name="one too many")
    assert 400 <= exc.value.status_code < 500
    assert exc.value.code == "profile_limit_reached"

    # The cap is per-user: Bob is unaffected.
    bob = ProfileService(db_session, user_id=users["bob"])
    assert bob.create_profile(name="Bob's first").name == "Bob's first"


# --- HTTP: auth gate + advisory header ---------------------------------------


@pytest.mark.real_auth
class TestProfilesHttp:
    @pytest.fixture
    def client(self, db_engine, monkeypatch):
        monkeypatch.setenv("MM_COOKIE_SECURE", "false")
        get_settings.cache_clear()
        session_factory = sessionmaker(
            bind=db_engine, autoflush=False, autocommit=False
        )

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

    def test_profiles_require_authentication(self, client):
        fresh = TestClient(client.app)  # no cookie, no bearer
        fresh.cookies.clear()
        assert fresh.get("/profiles").status_code == 401
        assert fresh.post("/profiles", json={"name": "X"}).status_code == 401

    def test_http_create_and_list_roundtrip(self, client):
        client.post("/auth/register", json={"username": "owner", "password": "supersecret"})
        created = client.post("/profiles", json={"name": "Reader", "mood": "fantasy"})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["name"] == "Reader" and body["mood"] == "fantasy"

        listed = client.get("/profiles")
        assert listed.status_code == 200
        assert [p["id"] for p in listed.json()] == [body["id"]]

    def test_x_profile_id_header_never_fails_request(self, client):
        client.post("/auth/register", json={"username": "owner", "password": "supersecret"})
        # Valid, non-numeric, and blank values are all accepted (advisory header).
        for value in ("42", "not-an-int", ""):
            resp = client.get("/profiles", headers={"X-Profile-Id": value})
            assert resp.status_code == 200, (value, resp.text)
