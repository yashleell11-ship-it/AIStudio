"""The bootstrap admin claim under concurrency (privilege-escalation race).

The bug being pinned: the "first account in an empty users table becomes
admin" claim was a check-then-act with nothing serializing it — pysqlite runs
the ``COUNT(*)`` in autocommit, FastAPI runs sync endpoints on a threadpool,
so N simultaneous ``POST /auth/register`` each observed zero users and *every
one* committed as an admin (verified against the live app: 8 of 8 became
admin). The fix has three layers, each tested here:

1. ``AuthService.register`` wraps count → policy re-check → INSERT → consume
   ``bootstrap_state`` in one ``BEGIN IMMEDIATE`` write transaction, so
   concurrent claims serialize and losers re-observe the winner's row;
2. the ``uq_users_single_admin`` partial unique index refuses a second
   ``is_admin=1`` row at the database level should any future path race;
3. ``GET /auth/bootstrap-status`` is rate-limited so it stops being a free
   polling oracle for when the window opens.

On flakiness: these tests are deterministic *by construction*, not by timing.
The barrier maximises overlap, but the assertions hold for every possible
interleaving — the write lock (not luck) guarantees at most one request sees
the empty table, and the losers' 403 is decided by a re-read under that same
lock. The only timing dependency is the 5s busy_timeout, six orders of
magnitude above the sub-millisecond critical section.

Concurrency needs real per-thread connections, so these tests build their own
file-backed engine with the production pragmas instead of the conftest
``db_engine`` (whose StaticPool funnels every thread through one connection
and would serialize the race away).
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import Base, BootstrapState, User
from database.session import get_db
from main import create_app
from services.auth_service import AuthService

pytestmark = pytest.mark.real_auth

PASSWORD = "correct-horse-battery"


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def race_engine(tmp_path):
    """File-backed engine with the production pragmas and a real connection
    pool, so concurrent requests genuinely run on separate connections."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):  # mirror database.session
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def race_factory(race_engine):
    return sessionmaker(
        bind=race_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )


@pytest.fixture
def client(race_factory, monkeypatch):
    monkeypatch.setenv("MM_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    def override_get_db():
        db = race_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    # raise_server_exceptions=False: a regression must show up as a 500 status
    # in the assertions below, not as an exception killing a worker thread.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def _cfg(monkeypatch, *, enabled: bool, window: int = 30) -> None:
    monkeypatch.setenv("MM_REGISTRATION_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("MM_REGISTRATION_INVITE_CODE", "")
    monkeypatch.setenv("MM_BOOTSTRAP_WINDOW_MINUTES", str(window))
    get_settings.cache_clear()


def _stamp_window(factory) -> None:
    """Pre-create the empty-table marker, as an attacker's bootstrap-status
    polling (or the startup posture log) would already have done."""
    with factory() as s:
        s.add(BootstrapState(id=1, empty_since=utcnow()))
        s.commit()


def _register_concurrently(client, n: int, *, username: str | None = None):
    """Fire n barrier-synchronised POST /auth/register and return responses."""
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def fire(i: int) -> None:
        name = username if username is not None else f"racer{i}"
        barrier.wait()
        results[i] = client.post(
            "/auth/register", json={"username": name, "password": PASSWORD}
        )

    threads = [threading.Thread(target=fire, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def _db_counts(factory) -> tuple[int, int, bool]:
    with factory() as s:
        admins = s.query(User).filter(User.is_admin == True).count()  # noqa: E712
        total = s.query(User).count()
        state_present = s.get(BootstrapState, 1) is not None
    return admins, total, state_present


# --- the race itself --------------------------------------------------------


def test_concurrent_bootstrap_mints_exactly_one_admin(client, race_factory, monkeypatch):
    """The exploit scenario: registration disabled, window open, N simultaneous
    registrations with distinct usernames. Exactly one may win the claim; the
    losers must fail cleanly (the policy re-check under the same lock sees the
    winner and applies the normal registration_enabled=false rule) — and must
    NOT be created as regular users either."""
    _cfg(monkeypatch, enabled=False)
    _stamp_window(race_factory)

    results = _register_concurrently(client, 8)
    statuses = sorted(r.status_code for r in results)

    assert statuses.count(201) == 1, f"expected exactly one winner, got {statuses}"
    assert statuses.count(500) == 0, f"a loser blew up instead of failing cleanly: {statuses}"
    winner = next(r for r in results if r.status_code == 201)
    assert winner.json()["user"]["is_admin"] is True
    for loser in (r for r in results if r.status_code != 201):
        assert loser.status_code == 403
        assert loser.json()["code"] == "registration_disabled"

    admins, total, state_present = _db_counts(race_factory)
    assert admins == 1, f"race minted {admins} admins"
    assert total == 1, f"losers leaked {total - 1} extra account(s) past registration_enabled=false"
    assert not state_present, "claim token not consumed in the winning transaction"


def test_concurrent_same_username_creates_one_account(client, race_factory, monkeypatch):
    """Same race, same username, registration otherwise open: the UNIQUE
    constraint backstop must map to a coherent 409, never a 500 or a second
    row (every thread passes the optimistic pre-check before the lock)."""
    _cfg(monkeypatch, enabled=True)
    _stamp_window(race_factory)

    results = _register_concurrently(client, 6, username="highlander")
    statuses = sorted(r.status_code for r in results)

    assert statuses.count(201) == 1, statuses
    assert statuses.count(500) == 0, statuses
    for loser in (r for r in results if r.status_code != 201):
        assert loser.status_code == 409
        assert loser.json()["code"] == "username_taken"

    admins, total, _ = _db_counts(race_factory)
    assert (admins, total) == (1, 1)


# --- claim consumption / window semantics -----------------------------------


def test_first_success_closes_the_claim_mid_window(client, race_factory, monkeypatch):
    """The window is closed by the act of claiming, not by a later observation:
    right after the first success — wall-clock still inside the window — the
    marker row is gone, bootstrap-status reports closed, and a second
    registration faces the normal (disabled) rules."""
    _cfg(monkeypatch, enabled=False)
    _stamp_window(race_factory)

    first = client.post(
        "/auth/register", json={"username": "owner", "password": PASSWORD}
    )
    assert first.status_code == 201
    assert first.json()["user"]["is_admin"] is True
    client.cookies.clear()

    _, _, state_present = _db_counts(race_factory)
    assert not state_present  # consumed atomically with the INSERT

    status = client.get("/auth/bootstrap-status").json()
    assert status["needs_bootstrap"] is False
    assert status["bootstrap_open"] is False

    second = client.post(
        "/auth/register", json={"username": "straggler", "password": PASSWORD}
    )
    assert second.status_code == 403
    assert second.json()["code"] == "registration_disabled"


def test_create_owner_path_still_works(race_factory, monkeypatch):
    """ops/vps/deploy.sh create-owner calls AuthService.register directly (no
    enforce_policy): it must claim an empty instance even when registration is
    disabled AND the bootstrap window has expired, and keep creating plain
    users after bootstrap — both through the serialized claim."""
    _cfg(monkeypatch, enabled=False)
    with race_factory() as s:  # window long expired
        s.add(BootstrapState(id=1, empty_since=utcnow() - timedelta(days=2)))
        s.commit()

    with race_factory() as db:
        owner = AuthService(db).register(username="yeahiamyash", password=PASSWORD)
        assert bool(owner.is_admin) is True

    admins, total, state_present = _db_counts(race_factory)
    assert (admins, total) == (1, 1)
    assert not state_present

    # Post-bootstrap, the same direct path yields a regular (non-admin) user.
    with race_factory() as db:
        second = AuthService(db).register(username="second", password=PASSWORD)
        assert bool(second.is_admin) is False
    admins, total, _ = _db_counts(race_factory)
    assert (admins, total) == (1, 2)


# --- the DB-level backstop ---------------------------------------------------


def test_second_admin_row_is_refused_by_the_database(race_factory):
    """uq_users_single_admin: even a raw INSERT cannot create a second admin."""
    with race_factory() as s:
        s.add(User(username="owner", password_hash="x", is_admin=True, is_active=True))
        s.commit()
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    "INSERT INTO users (username, password_hash, is_admin, "
                    "is_active, created_at, updated_at) "
                    "VALUES ('usurper', 'x', 1, 1, '2026-01-01', '2026-01-01')"
                )
            )
        s.rollback()
        # Demoted rows are untouched by the partial index.
        s.add(User(username="member", password_hash="x", is_admin=False, is_active=True))
        s.commit()


def test_lost_race_maps_admin_index_violation_to_409(race_factory, monkeypatch):
    """If a future code path ever re-introduces a stale emptiness read, the
    index violation must surface as a coherent 409, not a 500. Simulated by
    forcing user_count to lie."""
    with race_factory() as db:
        AuthService(db).register(username="owner", password=PASSWORD)

    monkeypatch.setattr(AuthService, "user_count", lambda self: 0)
    with race_factory() as db:
        with pytest.raises(AppError) as excinfo:
            AuthService(db).register(username="usurper", password=PASSWORD)
    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "bootstrap_already_claimed"

    monkeypatch.undo()
    admins, total, _ = _db_counts(race_factory)
    assert (admins, total) == (1, 1)


# --- the polling oracle ------------------------------------------------------


@pytest.mark.rate_limit
def test_bootstrap_status_poller_is_throttled(client, monkeypatch):
    """A tight poller trips the bucket; the 429 wears the standard envelope."""
    monkeypatch.setenv("MM_RATE_LIMIT_BOOTSTRAP_STATUS", "5/minute")
    get_settings.cache_clear()

    poll = lambda ip: client.get(  # noqa: E731
        "/auth/bootstrap-status", headers={"CF-Connecting-IP": ip}
    )
    codes = [poll("203.0.113.7").status_code for _ in range(5)]
    assert codes == [200] * 5

    limited = poll("203.0.113.7")
    assert limited.status_code == 429
    body = limited.json()
    assert body["code"] == "rate_limited"
    assert "retry-after" in {k.lower() for k in limited.headers}

    # A different client keeps its own budget.
    assert poll("203.0.113.8").status_code == 200


@pytest.mark.rate_limit
def test_bootstrap_status_normal_launches_never_hit_the_limit(client):
    """Under the shipped default bucket, an app-launch pattern — even a burst
    of launches/retries from one household IP — sails through."""
    codes = [
        client.get(
            "/auth/bootstrap-status", headers={"CF-Connecting-IP": "198.51.100.3"}
        ).status_code
        for _ in range(8)
    ]
    assert codes == [200] * 8
