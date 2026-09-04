"""Invite-code registration + the bounded bootstrap window.

The hazard under test: an empty ``users`` table on a public host means whoever
POSTs /auth/register first becomes admin. These tests pin the two mitigations:

* an **invite code** (``MM_REGISTRATION_INVITE_CODE``) gates self-service
  signup once accounts exist — compared in constant time, wrong/missing is a
  403 with a distinct code, and the register endpoint carries its own tight
  rate-limit bucket against brute force;
* the **bootstrap window** (``MM_BOOTSTRAP_WINDOW_MINUTES``, recorded in the
  ``bootstrap_state`` DB row) bounds how long an empty table grants uninvited
  registration, so a wiped database is not an indefinite takeover window.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import BootstrapState
from database.session import get_db
from main import create_app
from services.auth_service import AuthService

# Real registration/login flows: no default-admin auto-auth.
pytestmark = pytest.mark.real_auth

CODE = "household-secret-42"


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def client(db_engine, monkeypatch):
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


def _cfg(monkeypatch, *, enabled: bool, code: str | None, window: int = 30) -> None:
    """Pin the full registration posture via env (isolated from settings.json)."""
    monkeypatch.setenv("MM_REGISTRATION_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("MM_REGISTRATION_INVITE_CODE", code or "")
    monkeypatch.setenv("MM_BOOTSTRAP_WINDOW_MINUTES", str(window))
    get_settings.cache_clear()


def _register(client, username="member", password="supersecret", **kw):
    return client.post(
        "/auth/register", json={"username": username, "password": password, **kw}
    )


def _bootstrap_admin(client):
    """Create the first (admin) account; fresh empty DB => window is open."""
    resp = _register(client, username="owner")
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["is_admin"] is True
    client.cookies.clear()
    return resp


def _expire_window(db_engine, *, minutes_ago: int = 31) -> None:
    """Backdate (creating if needed) the empty-table marker past the window."""
    with Session(db_engine) as s:
        state = s.get(BootstrapState, 1)
        if state is None:
            state = BootstrapState(id=1)
            s.add(state)
        state.empty_since = utcnow() - timedelta(minutes=minutes_ago)
        s.commit()


# --- registration_enabled=false: refused entirely (post-bootstrap) ----------


def test_disabled_refuses_even_with_correct_invite_code(client, monkeypatch):
    _cfg(monkeypatch, enabled=False, code=CODE)
    _bootstrap_admin(client)
    resp = _register(client, invite_code=CODE)
    assert resp.status_code == 403
    assert resp.json()["code"] == "registration_disabled"


# --- invite-code gate (users exist) -----------------------------------------


def test_missing_invite_code_is_403_required(client, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=CODE)
    _bootstrap_admin(client)
    resp = _register(client)
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "invite_code_required"
    assert "message" in body  # standard envelope
    assert CODE not in resp.text


def test_wrong_invite_code_is_403_invalid(client, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=CODE)
    _bootstrap_admin(client)
    resp = _register(client, invite_code="wrong-guess")
    assert resp.status_code == 403
    assert resp.json()["code"] == "invite_code_invalid"
    assert CODE not in resp.text


def test_correct_invite_code_registers_a_non_admin(client, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=CODE)
    _bootstrap_admin(client)
    resp = _register(client, invite_code=CODE)
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["is_admin"] is False
    # and the session works
    assert client.get("/auth/me").status_code == 200


def test_no_code_configured_means_open_registration(client, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=None)
    _bootstrap_admin(client)
    resp = _register(client)
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["is_admin"] is False


def test_invite_gate_runs_before_field_validation(client, monkeypatch):
    """A brute-forcer probing with garbage usernames still burns on the 403
    gate, not a 422 oracle."""
    _cfg(monkeypatch, enabled=True, code=CODE)
    _bootstrap_admin(client)
    resp = _register(client, username="x", invite_code="wrong")
    assert resp.status_code == 403
    assert resp.json()["code"] == "invite_code_invalid"


# --- bootstrap: first user is admin, uninvited, inside the window -----------


def test_first_user_is_admin_without_code_even_when_disabled(client, monkeypatch):
    """Today's bootstrap exception survives: empty table + open window =>
    uninvited registration allowed regardless of registration_enabled, and
    that account is the admin. The second account is neither exempt nor admin."""
    _cfg(monkeypatch, enabled=False, code=CODE)
    first = _register(client, username="owner")
    assert first.status_code == 201, first.text
    assert first.json()["user"]["is_admin"] is True
    client.cookies.clear()
    second = _register(client, invite_code=CODE)
    assert second.status_code == 403
    assert second.json()["code"] == "registration_disabled"


def test_second_user_is_not_admin(client, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=None)
    _bootstrap_admin(client)
    resp = _register(client)
    assert resp.status_code == 201
    assert resp.json()["user"]["is_admin"] is False


# --- bootstrap window expiry ------------------------------------------------


def test_expired_window_rejects_uninvited_bootstrap(client, db_engine, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=CODE)
    _expire_window(db_engine)
    resp = _register(client, username="stranger")
    assert resp.status_code == 403
    assert resp.json()["code"] == "invite_code_required"


def test_expired_window_with_registration_disabled_is_fully_closed(
    client, db_engine, monkeypatch
):
    _cfg(monkeypatch, enabled=False, code=None)
    _expire_window(db_engine)
    resp = _register(client, username="stranger")
    assert resp.status_code == 403
    assert resp.json()["code"] == "registration_disabled"


def test_expired_window_still_admits_the_invite_code_and_grants_admin(
    client, db_engine, monkeypatch
):
    """The owner locked out past the window can still claim the instance with
    the invite code — and, being first, IS admin."""
    _cfg(monkeypatch, enabled=True, code=CODE)
    _expire_window(db_engine)
    resp = _register(client, username="owner", invite_code=CODE)
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["is_admin"] is True


def test_window_zero_disables_uninvited_bootstrap_entirely(
    client, monkeypatch
):
    _cfg(monkeypatch, enabled=True, code=CODE, window=0)
    resp = _register(client, username="stranger")
    assert resp.status_code == 403
    assert resp.json()["code"] == "invite_code_required"


def test_open_window_allows_exactly_one_uninvited_account(client, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=CODE)
    _bootstrap_admin(client)
    resp = _register(client)  # second, uninvited
    assert resp.status_code == 403
    assert resp.json()["code"] == "invite_code_required"


# --- bootstrap_state row lifecycle (service level) ---------------------------


def test_empty_table_lazily_stamps_bootstrap_state(db_session):
    svc = AuthService(db_session)
    assert db_session.get(BootstrapState, 1) is None
    assert svc.bootstrap_window_open() is True
    state = db_session.get(BootstrapState, 1)
    assert state is not None
    assert (utcnow() - state.empty_since).total_seconds() < 5


def test_first_registration_clears_bootstrap_state(db_session):
    svc = AuthService(db_session)
    assert svc.bootstrap_window_open() is True  # stamps the row
    svc.register("owner", "supersecret")
    assert db_session.get(BootstrapState, 1) is None
    # ...so the marker cannot go stale while accounts exist, and window checks
    # simply don't apply.
    assert svc.bootstrap_window_open() is False


def test_stamp_is_stable_across_observations(db_session, monkeypatch):
    monkeypatch.setenv("MM_BOOTSTRAP_WINDOW_MINUTES", "30")
    get_settings.cache_clear()
    svc = AuthService(db_session)
    svc.bootstrap_window_open()
    first = db_session.get(BootstrapState, 1).empty_since
    svc.bootstrap_window_open()
    assert db_session.get(BootstrapState, 1).empty_since == first


def test_ensure_registration_allowed_service_matrix(db_session, monkeypatch):
    """Service-level spot check of the gate's error codes."""
    monkeypatch.setenv("MM_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("MM_REGISTRATION_INVITE_CODE", CODE)
    monkeypatch.setenv("MM_BOOTSTRAP_WINDOW_MINUTES", "30")
    get_settings.cache_clear()
    svc = AuthService(db_session)
    # empty + open window: anything goes
    svc.ensure_registration_allowed(None)
    svc.register("owner", "supersecret")
    # users exist now: code enforced
    with pytest.raises(AppError) as missing:
        svc.ensure_registration_allowed(None)
    assert missing.value.code == "invite_code_required"
    assert missing.value.status_code == 403
    with pytest.raises(AppError) as wrong:
        svc.ensure_registration_allowed("nope")
    assert wrong.value.code == "invite_code_invalid"
    assert wrong.value.status_code == 403
    svc.ensure_registration_allowed(CODE)  # no raise


# --- constant-time comparison ----------------------------------------------


def test_invite_code_uses_constant_time_compare(db_session, monkeypatch):
    """The comparison must go through hmac.compare_digest (never ``==``)."""
    import services.auth_service as auth_module

    monkeypatch.setenv("MM_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("MM_REGISTRATION_INVITE_CODE", CODE)
    get_settings.cache_clear()

    svc = AuthService(db_session)
    svc.register("owner", "supersecret")  # get past bootstrap

    calls: list[tuple[bytes, bytes]] = []
    real = auth_module.compare_digest

    def recording(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(auth_module, "compare_digest", recording)

    with pytest.raises(AppError):
        svc.ensure_registration_allowed("wrong-guess")
    svc.ensure_registration_allowed(CODE)

    assert calls == [
        (b"wrong-guess", CODE.encode()),
        (CODE.encode(), CODE.encode()),
    ]


# --- rate limiting ----------------------------------------------------------


@pytest.fixture
def limited_client(db_engine, monkeypatch):
    monkeypatch.setenv("MM_COOKIE_SECURE", "false")
    monkeypatch.setenv("MM_RATE_LIMIT_REGISTER", "3/minute")  # tiny for the test
    monkeypatch.setenv("MM_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("MM_REGISTRATION_INVITE_CODE", CODE)
    monkeypatch.setenv("MM_BOOTSTRAP_WINDOW_MINUTES", "30")
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


@pytest.mark.rate_limit
def test_repeated_bad_invite_codes_hit_the_register_bucket(limited_client):
    headers = {"CF-Connecting-IP": "203.0.113.66"}
    # burn the bootstrap slot so the code is enforced
    first = limited_client.post(
        "/auth/register",
        json={"username": "owner", "password": "supersecret"},
        headers=headers,
    )
    assert first.status_code == 201
    limited_client.cookies.clear()

    guesses = [
        limited_client.post(
            "/auth/register",
            json={
                "username": f"guess{n}",
                "password": "supersecret",
                "invite_code": f"brute-{n}",
            },
            headers=headers,
        )
        for n in range(3)
    ]
    assert [g.status_code for g in guesses[:2]] == [403, 403]
    limited = guesses[2]
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert "retry-after" in {k.lower() for k in limited.headers}


@pytest.mark.rate_limit
def test_register_bucket_does_not_throttle_login(limited_client):
    """The tighter register bucket must not spill onto /auth/login (which has
    its own auth bucket)."""
    headers = {"CF-Connecting-IP": "203.0.113.67"}
    for n in range(4):  # exhaust 3/minute on register
        limited_client.post(
            "/auth/register",
            json={"username": f"u{n}", "password": "supersecret"},
            headers=headers,
        )
    resp = limited_client.post(
        "/auth/login",
        json={"username": "ghost", "password": "whatever"},
        headers=headers,
    )
    assert resp.status_code == 401  # limited would be 429


# --- GET /auth/bootstrap-status ---------------------------------------------


BOOTSTRAP_KEYS = {
    "needs_bootstrap",
    "bootstrap_open",
    "registration_enabled",
    "invite_code_required",
    "registration_open",
    # Novels flag (spec 2026-09-04 §2): clients mount novel UI only on this.
    "novels_enabled",
}


def test_bootstrap_status_fresh_instance(client, monkeypatch):
    _cfg(monkeypatch, enabled=False, code=CODE)
    resp = client.get("/auth/bootstrap-status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == BOOTSTRAP_KEYS
    assert body["needs_bootstrap"] is True
    assert body["bootstrap_open"] is True
    assert body["registration_enabled"] is False
    # inside the open window no code is demanded, even though one is configured
    assert body["invite_code_required"] is False
    assert body["registration_open"] is True
    assert CODE not in resp.text  # never echo the code


def test_bootstrap_status_after_admin_exists(client, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=CODE)
    _bootstrap_admin(client)
    body = client.get("/auth/bootstrap-status").json()
    assert body["needs_bootstrap"] is False
    assert body["bootstrap_open"] is False
    assert body["registration_enabled"] is True
    assert body["invite_code_required"] is True
    assert body["registration_open"] is True


def test_bootstrap_status_expired_window(client, db_engine, monkeypatch):
    _cfg(monkeypatch, enabled=True, code=CODE)
    _expire_window(db_engine)
    resp = client.get("/auth/bootstrap-status")
    body = resp.json()
    assert body["needs_bootstrap"] is True
    assert body["bootstrap_open"] is False
    assert body["invite_code_required"] is True
    assert body["registration_open"] is True
    assert CODE not in resp.text


def test_bootstrap_status_closed_deployment(client, monkeypatch):
    """Production posture today: registration off, no code, admin exists."""
    _cfg(monkeypatch, enabled=False, code=None)
    _bootstrap_admin(client)
    body = client.get("/auth/bootstrap-status").json()
    assert body["needs_bootstrap"] is False
    assert body["bootstrap_open"] is False
    assert body["registration_enabled"] is False
    assert body["invite_code_required"] is False
    assert body["registration_open"] is False


def test_bootstrap_status_never_contains_the_code_anywhere(client, monkeypatch):
    _cfg(monkeypatch, enabled=True, code="ultra-unique-sentinel-XYZZY")
    for _ in range(2):  # before and after the lazy stamp
        resp = client.get("/auth/bootstrap-status")
        assert "XYZZY" not in resp.text
        assert "XYZZY" not in str(resp.headers)
