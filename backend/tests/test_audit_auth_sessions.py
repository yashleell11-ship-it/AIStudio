"""Data-layer audit — shard ``auth-sessions`` (users / sessions / bootstrap_state).

Each test here pins a gap found while reading ``services/auth_service.py``,
``routes/auth.py`` and the ``User`` / ``UserSession`` / ``BootstrapState``
models. A FAILING test is the finding; a passing one is a regression guard for
a property that was verified to hold. Nothing in this file edits existing
tests or production code.

Live evidence the tests are anchored to (read-only over ssh, 2026-09-06):
  * GET https://manhwamaniacs.xyz/api/auth/bootstrap-status ->
    ``registration_enabled=true, invite_code_required=false,
    registration_open=true`` — registration is open to anyone.
  * ``sessions``: 4 rows, 0 expired, every ``ip_address`` == 172.18.0.2 (the
    cloudflared container), i.e. the recorded client IP is never the client.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from core.config import get_settings
from core.time_utils import utcnow
from database.models import BootstrapState, User, UserSession
from database.session import get_db
from main import create_app
from services.auth_service import AuthService

pytestmark = pytest.mark.real_auth

PASSWORD = "correct-horse-battery"


@pytest.fixture
def client(session_factory, monkeypatch):
    monkeypatch.setenv("MM_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def _cfg(monkeypatch, *, enabled: bool, invite: str = "", window: int = 30) -> None:
    monkeypatch.setenv("MM_REGISTRATION_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("MM_REGISTRATION_INVITE_CODE", invite)
    monkeypatch.setenv("MM_BOOTSTRAP_WINDOW_MINUTES", str(window))
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# F1. The bootstrap window (migration 0003) did not bound the admin claim
#     when registration is open with no invite code — which is exactly the
#     live VPS configuration. An expired window + empty users table + any
#     stranger => that stranger was the admin/owner. Fixed: past the window
#     the claim is refused (403 bootstrap_window_expired) unless it comes
#     from an operator path. Now a regression guard.
# ---------------------------------------------------------------------------


def test_expired_bootstrap_window_with_open_registration_still_mints_admin(
    client, session_factory, monkeypatch
):
    """Per the intent of 0003 / the BootstrapState docstring: once the window
    has closed, an empty table must not hand the admin bit to an uninvited
    registrant. It used to: ``AuthService.register`` set
    ``is_admin = count == 0`` unconditionally, and the locked policy check
    fell through to ``_ensure_invited``, which passes under the live config
    (registration_enabled=true, no invite code)."""
    _cfg(monkeypatch, enabled=True, invite="", window=30)
    with session_factory() as s:
        # Window opened a day ago and was never claimed (e.g. after a wipe or
        # a restore of an empty DB).
        s.add(BootstrapState(id=1, empty_since=utcnow() - timedelta(days=1)))
        s.commit()

    status = client.get("/auth/bootstrap-status").json()
    assert status["needs_bootstrap"] is True
    assert status["bootstrap_open"] is False  # window is closed…

    resp = client.post(
        "/auth/register", json={"username": "stranger", "password": PASSWORD}
    )
    # …so this must not produce an owner. Either a 403 or a non-admin account
    # would satisfy the invariant; an admin does not.
    assert not (resp.status_code == 201 and resp.json()["user"]["is_admin"]), (
        f"expired window still minted an admin: {resp.status_code} {resp.text}"
    )


# ---------------------------------------------------------------------------
# F2. Sessions per user are unbounded. Every login inserts a row with a 7- or
#     90-day TTL and nothing caps or trims them; a client stuck in a re-login
#     loop (or an attacker with one valid password) grows the table until the
#     next restart's startup prune — and that prune only removes *expired*
#     rows, so 90-day tokens sit for a quarter.
# ---------------------------------------------------------------------------


def test_sessions_per_user_are_capped(db_session):
    svc = AuthService(db_session)
    user = svc.register("owner", PASSWORD)
    for _ in range(60):
        svc.create_session(user, remember=True)
    live = db_session.execute(
        select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)
    ).scalar_one()
    # A careful operator's ceiling: a household member has at most a handful
    # of devices. 20 is generous.
    assert live <= 20, f"{live} live sessions for one user — no per-user cap"


# ---------------------------------------------------------------------------
# F3. Expired sessions are only deleted (a) at process startup or (b) when
#     that exact token is presented again. A token that is never presented
#     again survives until the next deploy/restart. There is no periodic
#     sweep, although a scheduler (services.update_scheduler) already exists.
# ---------------------------------------------------------------------------


def test_expired_sessions_are_swept_while_the_process_runs(db_session):
    svc = AuthService(db_session)
    user = svc.register("owner", PASSWORD)
    live_token, _ = svc.create_session(user)
    _, stale = svc.create_session(user)
    stale.expires_at = utcnow() - timedelta(days=30)
    db_session.commit()

    # Plenty of normal authenticated traffic on the *other* token…
    for _ in range(25):
        assert svc.resolve_session(live_token) is not None

    remaining = db_session.execute(
        select(func.count())
        .select_from(UserSession)
        .where(UserSession.expires_at <= utcnow())
    ).scalar_one()
    assert remaining == 0, (
        f"{remaining} expired session row(s) survive ordinary traffic; only "
        "startup (main.prune_expired_sessions) or presenting the dead token "
        "itself removes them"
    )


# ---------------------------------------------------------------------------
# F4. ``routes.auth._client_meta`` records the FIRST hop of X-Forwarded-For
#     (client-forgeable, and behind Caddy it is the cloudflared container),
#     while the rate limiter in ``core.rate_limit.client_ip`` deliberately
#     keys on CF-Connecting-IP for the reasons documented there. The two
#     disagree, and the sessions screen shows a useless / attacker-chosen IP.
# ---------------------------------------------------------------------------


def test_session_ip_uses_the_trusted_client_ip_header(client, session_factory, monkeypatch):
    _cfg(monkeypatch, enabled=True, invite="", window=30)
    monkeypatch.setenv("MM_TRUSTED_CLIENT_IP_HEADER", "cf-connecting-ip")
    get_settings.cache_clear()

    resp = client.post(
        "/auth/register",
        json={"username": "owner", "password": PASSWORD},
        headers={
            "CF-Connecting-IP": "198.51.100.7",  # what the edge actually saw
            "X-Forwarded-For": "203.0.113.9, 172.18.0.2",  # client-controlled
        },
    )
    assert resp.status_code == 201, resp.text
    with session_factory() as s:
        row = s.execute(select(UserSession)).scalar_one()
    assert row.ip_address == "198.51.100.7", (
        f"session recorded ip_address={row.ip_address!r}: first XFF hop, not "
        "the trusted edge header the rate limiter keys on"
    )


# ---------------------------------------------------------------------------
# Verified properties (regression guards — these PASS today).
# ---------------------------------------------------------------------------


def test_revoked_and_expired_tokens_are_refused_on_the_next_request(db_session):
    """Every request resolves the session by token hash and checks expires_at
    in Python (auth_service.resolve_session); revocation is a row delete."""
    svc = AuthService(db_session)
    user = svc.register("owner", PASSWORD)
    tok_a, sess_a = svc.create_session(user)
    tok_b, _ = svc.create_session(user)
    assert svc.resolve_session(tok_a) is not None
    svc.revoke_token(tok_b)
    assert svc.resolve_session(tok_b) is None
    sess_a.expires_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert svc.resolve_session(tok_a) is None
    assert db_session.get(UserSession, sess_a.id) is None  # pruned lazily


def test_change_password_revokes_other_sessions_and_old_password_dies(client, session_factory, monkeypatch):
    _cfg(monkeypatch, enabled=True, invite="", window=30)
    first = client.post("/auth/register", json={"username": "owner", "password": PASSWORD})
    keep = first.json()["token"]
    client.cookies.clear()
    other = client.post("/auth/login", json={"username": "owner", "password": PASSWORD}).json()["token"]
    client.cookies.clear()

    r = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "another-good-pass"},
        headers={"Authorization": f"Bearer {keep}"},
    )
    assert r.status_code == 204, r.text
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {other}"}).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {keep}"}).status_code == 200
    assert client.post("/auth/login", json={"username": "owner", "password": PASSWORD}).status_code == 401


def test_password_hash_is_argon2id_and_token_is_stored_hashed(db_session):
    svc = AuthService(db_session)
    user = svc.register("owner", PASSWORD)
    assert user.password_hash.startswith("$argon2id$")
    token, sess = svc.create_session(user)
    assert sess.token_hash != token and len(sess.token_hash) == 64
    assert token not in sess.token_hash


def test_profile_header_cannot_reach_another_users_profile(client, session_factory, monkeypatch):
    _cfg(monkeypatch, enabled=True, invite="", window=30)
    a = client.post("/auth/register", json={"username": "alice", "password": PASSWORD}).json()["token"]
    client.cookies.clear()
    b = client.post("/auth/register", json={"username": "bob", "password": PASSWORD}).json()["token"]
    client.cookies.clear()
    pa = client.post("/profiles", json={"name": "A1"}, headers={"Authorization": f"Bearer {a}"})
    assert pa.status_code in (200, 201), pa.text
    a_pid = pa.json()["id"]
    # bob names alice's profile
    r = client.patch(
        f"/profiles/{a_pid}",
        json={"name": "pwned"},
        headers={"Authorization": f"Bearer {b}", "X-Profile-Id": str(a_pid)},
    )
    assert r.status_code == 404, r.text
    # A read under a foreign X-Profile-Id degrades to bob's own unscoped
    # bucket (lenient resolver) rather than reading alice's profile gate.
    r = client.get(
        "/settings",
        headers={"Authorization": f"Bearer {b}", "X-Profile-Id": str(a_pid)},
    )
    assert r.status_code == 200, r.text
