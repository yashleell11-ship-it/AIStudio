"""Authentication: password/token primitives, AuthService, and HTTP flows."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from core import auth as auth_primitives
from core.config import get_settings
from core.errors import AppError
from database.models import User, UserSession
from database.session import get_db
from main import create_app
from services.auth_service import (
    AuthService,
    get_current_user,
    require_admin_user,
)

# These tests drive real registration/login and assert 401/403 behaviour, so
# they must NOT get the suite's default-admin auto-auth.
pytestmark = pytest.mark.real_auth


# --- primitives (core/auth.py) ----------------------------------------------


def test_hash_and_verify_password_roundtrip():
    h = auth_primitives.hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"  # never store plaintext
    assert auth_primitives.verify_password("correct horse battery staple", h)
    assert not auth_primitives.verify_password("wrong password", h)


def test_verify_password_tolerates_malformed_hash():
    # A garbage stored hash must return False, not raise.
    assert auth_primitives.verify_password("anything", "not-a-real-argon2-hash") is False


def test_session_token_is_high_entropy_and_hash_is_stable():
    a = auth_primitives.generate_session_token()
    b = auth_primitives.generate_session_token()
    assert a != b and len(a) >= 32
    assert auth_primitives.hash_session_token(a) == auth_primitives.hash_session_token(a)
    assert auth_primitives.hash_session_token(a) != auth_primitives.hash_session_token(b)
    # what we persist is the digest, never the raw token
    assert a not in auth_primitives.hash_session_token(a)


@pytest.mark.parametrize(
    "password,ok",
    [
        ("short", False),  # < 8 chars
        ("exactly8", True),
        ("a" * 5000, False),  # > MAX_PASSWORD_LENGTH (argon2 DoS guard)
    ],
)
def test_validate_password_strength(password, ok):
    result = auth_primitives.validate_password_strength(password)
    assert (result is None) == ok


# --- AuthService (service layer, direct DB) ----------------------------------


def _svc(db_session) -> AuthService:
    return AuthService(db_session)


def test_first_registered_user_becomes_admin(db_session):
    svc = _svc(db_session)
    first = svc.register("owner", "supersecret")
    # Booleans are stored as Integer across this codebase, so the ORM reads them
    # back as 1/0 (the HTTP boundary coerces them to real bools via Pydantic).
    assert bool(first.is_admin) is True
    second = svc.register("reader", "supersecret")
    assert bool(second.is_admin) is False


def test_register_rejects_duplicate_username(db_session):
    svc = _svc(db_session)
    svc.register("owner", "supersecret")
    with pytest.raises(AppError) as exc:
        svc.register("owner", "anotherpassword")
    assert exc.value.status_code == 409
    assert exc.value.code == "username_taken"


def test_register_rejects_weak_password(db_session):
    svc = _svc(db_session)
    with pytest.raises(AppError) as exc:
        svc.register("owner", "short")
    assert exc.value.status_code == 422


@pytest.mark.parametrize("bad", ["ab", "1", "has space", "bad/slash", "x" * 65])
def test_register_rejects_invalid_username(db_session, bad):
    with pytest.raises(AppError) as exc:
        _svc(db_session).register(bad, "supersecret")
    assert exc.value.status_code == 422


def test_authenticate_success_and_wrong_password(db_session):
    svc = _svc(db_session)
    svc.register("owner", "supersecret")
    assert svc.authenticate("owner", "supersecret").username == "owner"
    with pytest.raises(AppError) as exc:
        svc.authenticate("owner", "WRONG")
    assert exc.value.status_code == 401


def test_authenticate_unknown_user_is_indistinguishable(db_session):
    # Same code/status/message as a wrong password → no username enumeration.
    svc = _svc(db_session)
    svc.register("owner", "supersecret")
    with pytest.raises(AppError) as unknown:
        svc.authenticate("ghost", "supersecret")
    with pytest.raises(AppError) as wrong:
        svc.authenticate("owner", "nope-nope-nope")
    assert unknown.value.status_code == wrong.value.status_code == 401
    assert unknown.value.code == wrong.value.code == "invalid_credentials"
    assert unknown.value.message == wrong.value.message


def test_authenticate_disabled_account_rejected(db_session):
    svc = _svc(db_session)
    user = svc.register("owner", "supersecret")
    user.is_active = False
    db_session.commit()
    with pytest.raises(AppError) as exc:
        svc.authenticate("owner", "supersecret")
    assert exc.value.status_code == 403


def test_session_lifecycle_create_resolve_revoke(db_session):
    svc = _svc(db_session)
    user = svc.register("owner", "supersecret")
    token, session = svc.create_session(user)
    # stored hashed, never raw
    assert session.token_hash != token
    assert svc.resolve_session(token).id == user.id
    assert svc.resolve_session("bogus-token") is None
    assert svc.revoke_token(token) is True
    assert svc.resolve_session(token) is None


def test_expired_session_is_rejected_and_pruned(db_session):
    from datetime import timedelta

    from core.time_utils import utcnow

    svc = _svc(db_session)
    user = svc.register("owner", "supersecret")
    token, session = svc.create_session(user)
    session.expires_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert svc.resolve_session(token) is None
    # expired row pruned on resolve
    assert db_session.get(UserSession, session.id) is None


def test_remember_me_extends_expiry(db_session):
    svc = _svc(db_session)
    user = svc.register("owner", "supersecret")
    _, short = svc.create_session(user, remember=False)
    _, long = svc.create_session(user, remember=True)
    assert long.expires_at > short.expires_at


def test_revoke_all_except_current(db_session):
    svc = _svc(db_session)
    user = svc.register("owner", "supersecret")
    keep_token, _ = svc.create_session(user)
    svc.create_session(user)
    svc.create_session(user)
    removed = svc.revoke_all(user.id, except_token=keep_token)
    assert removed == 2
    assert svc.resolve_session(keep_token).id == user.id
    assert len(svc.list_sessions(user.id)) == 1


def test_revoke_session_id_is_owner_scoped(db_session):
    svc = _svc(db_session)
    a = svc.register("alice", "supersecret")
    b = svc.register("bob", "supersecret")
    _, b_session = svc.create_session(b)
    # alice cannot revoke bob's session
    assert svc.revoke_session_id(a.id, b_session.id) is False
    assert db_session.get(UserSession, b_session.id) is not None
    # bob can
    assert svc.revoke_session_id(b.id, b_session.id) is True


def test_change_password_requires_current_and_updates_hash(db_session):
    svc = _svc(db_session)
    user = svc.register("owner", "supersecret")
    with pytest.raises(AppError):
        svc.change_password(user, "WRONG", "newsupersecret")
    svc.change_password(user, "supersecret", "newsupersecret")
    assert svc.authenticate("owner", "newsupersecret").id == user.id
    with pytest.raises(AppError):
        svc.authenticate("owner", "supersecret")


def test_cleanup_expired_removes_only_expired(db_session):
    from datetime import timedelta

    from core.time_utils import utcnow

    svc = _svc(db_session)
    user = svc.register("owner", "supersecret")
    live_token, _ = svc.create_session(user)
    _, dead = svc.create_session(user)
    dead.expires_at = utcnow() - timedelta(days=1)
    db_session.commit()
    assert svc.cleanup_expired() == 1
    assert svc.resolve_session(live_token).id == user.id


# --- require_admin_user dependency (unit) ------------------------------------


def test_require_admin_user_allows_admin_blocks_others(db_session):
    svc = _svc(db_session)
    admin = svc.register("owner", "supersecret")  # first == admin
    normal = svc.register("reader", "supersecret")
    assert require_admin_user(user=admin) is admin
    with pytest.raises(AppError) as exc:
        require_admin_user(user=normal)
    assert exc.value.status_code == 403


def test_get_current_user_requires_authentication():
    with pytest.raises(AppError) as exc:
        get_current_user(user=None)
    assert exc.value.status_code == 401


# --- claim-on-registration (multi-user data migration) -----------------------


def test_first_registered_user_is_admin_second_is_not(db_session):
    """The bootstrap rule survives the slim-down; the ``_claim_unowned_data``
    adoption machinery does not (spec §5.3 — a wiped DB has no unowned rows and
    every source-native table is ``user_id``/``profile_id`` NOT NULL)."""
    svc = AuthService(db_session)
    admin = svc.register("owner", "supersecret")
    reader = svc.register("reader", "supersecret")
    assert bool(admin.is_admin) is True
    assert bool(reader.is_admin) is False


def test_auth_service_has_no_unowned_claim_hook():
    """Guard: the removed adoption entrypoints stay removed."""
    assert not hasattr(AuthService, "_claim_unowned_data")
    assert not hasattr(AuthService, "claim_unowned_data")


# --- HTTP integration (full app) --------------------------------------------


@pytest.fixture
def client(db_engine, monkeypatch):
    # Local-dev cookie posture so httpx persists the cookie over http://testserver
    # (a Secure cookie would not round-trip in the test client's http jar).
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


def _register(client, username="owner", password="supersecret", **kw):
    return client.post(
        "/auth/register",
        json={"username": username, "password": password, **kw},
    )


def test_http_register_returns_user_and_token_and_sets_cookie(client):
    resp = _register(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["username"] == "owner"
    assert body["user"]["is_admin"] is True
    assert body["token"]
    assert "password" not in body["user"] and "password_hash" not in body["user"]
    set_cookie = resp.headers.get("set-cookie", "")
    assert "mm_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    # cookie is now in the jar → authenticated
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "owner"


def test_http_me_requires_auth(client):
    fresh = TestClient(client.app)  # no cookie jar, no bearer
    assert fresh.get("/auth/me").status_code == 401


def test_http_bearer_token_authenticates(client):
    token = _register(client).json()["token"]
    fresh = TestClient(client.app)
    fresh.cookies.clear()
    resp = fresh.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "owner"
    # a bad bearer token is unauthenticated
    assert fresh.get("/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_http_login_wrong_password_401(client):
    _register(client)
    resp = client.post("/auth/login", json={"username": "owner", "password": "WRONG"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


def test_http_login_success_issues_new_session(client):
    _register(client)
    client.cookies.clear()
    resp = client.post("/auth/login", json={"username": "owner", "password": "supersecret"})
    assert resp.status_code == 200
    assert resp.json()["token"]
    assert client.get("/auth/me").status_code == 200


def test_http_logout_revokes_session(client):
    _register(client)
    assert client.get("/auth/me").status_code == 200
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_http_logout_all_signs_out_every_device(client):
    token = _register(client).json()["token"]  # "device 1" (cookie jar)
    # device 2 = same account, separate login → separate session/token
    device2 = TestClient(client.app)
    device2.cookies.clear()
    t2 = device2.post(
        "/auth/login", json={"username": "owner", "password": "supersecret"}
    ).json()["token"]
    # logout-all from device 1
    assert client.post("/auth/logout-all").status_code == 204
    # both tokens now dead
    check = TestClient(client.app)
    check.cookies.clear()
    assert check.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert check.get("/auth/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 401


def test_http_sessions_list_marks_current(client):
    _register(client)
    resp = client.get("/auth/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 1
    assert sessions[0]["current"] is True
    assert "token_hash" not in sessions[0]  # never expose the stored digest


def test_http_revoke_specific_session(client):
    _register(client)
    # open a second session
    device2 = TestClient(client.app)
    device2.cookies.clear()
    device2.post("/auth/login", json={"username": "owner", "password": "supersecret"})
    sessions = client.get("/auth/sessions").json()
    assert len(sessions) == 2
    other = next(s for s in sessions if not s["current"])
    assert client.delete(f"/auth/sessions/{other['id']}").status_code == 204
    assert len(client.get("/auth/sessions").json()) == 1
    # revoking a nonexistent session → 404
    assert client.delete("/auth/sessions/999999").status_code == 404


def test_http_change_password_keeps_current_session_revokes_others(client):
    _register(client)
    device2 = TestClient(client.app)
    device2.cookies.clear()
    t2 = device2.post(
        "/auth/login", json={"username": "owner", "password": "supersecret"}
    ).json()["token"]
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "supersecret", "new_password": "brandnewsecret"},
    )
    assert resp.status_code == 204
    # current session (cookie) still works
    assert client.get("/auth/me").status_code == 200
    # the other session was revoked
    check = TestClient(client.app)
    check.cookies.clear()
    assert check.get("/auth/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 401


def test_http_second_user_is_not_admin(client):
    _register(client, username="owner")
    client.cookies.clear()
    resp = _register(client, username="reader")
    assert resp.status_code == 201
    assert resp.json()["user"]["is_admin"] is False


def test_http_duplicate_username_conflict(client):
    _register(client, username="owner")
    client.cookies.clear()
    resp = _register(client, username="owner")
    assert resp.status_code == 409


def test_http_registration_can_be_disabled_after_bootstrap(db_engine, monkeypatch):
    # first account always allowed (claims the instance); further signups gated.
    monkeypatch.setenv("MM_COOKIE_SECURE", "false")
    monkeypatch.setenv("MM_REGISTRATION_ENABLED", "false")
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
    with TestClient(app) as c:
        first = c.post("/auth/register", json={"username": "owner", "password": "supersecret"})
        assert first.status_code == 201  # bootstrap admin allowed
        c.cookies.clear()
        second = c.post("/auth/register", json={"username": "reader", "password": "supersecret"})
        assert second.status_code == 403
        assert second.json()["code"] == "registration_disabled"
    get_settings.cache_clear()


def test_http_cookie_is_secure_when_configured(db_engine, monkeypatch):
    monkeypatch.setenv("MM_COOKIE_SECURE", "true")
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
    with TestClient(app) as c:
        resp = c.post("/auth/register", json={"username": "owner", "password": "supersecret"})
        set_cookie = resp.headers.get("set-cookie", "").lower()
        assert "secure" in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
    get_settings.cache_clear()
