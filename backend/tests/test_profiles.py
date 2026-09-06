"""Reading profiles: per-user CRUD, ownership isolation, limits, and auth gate.

Service-level tests drive :class:`ProfileService` directly with real ``user_id``s
(mirroring test_multiuser_isolation) to prove ownership scoping without threading
HTTP auth through every case. HTTP tests use the real auth stack to prove the 401
gate and that the advisory ``X-Profile-Id`` header never fails a request.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import (
    Base,
    Bookmark,
    ChapterProgress,
    Collection,
    CollectionSeries,
    FollowedSeries,
    ProfileSeriesTag,
    ReadingDayStats,
    ReadingSession,
    SourcePin,
    Tag,
    UpdateNotification,
    User,
    UserSession,
)
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


def test_mature_content_enabled_is_settable_on_create_and_update(db_session, users):
    svc = ProfileService(db_session, user_id=users["alice"])
    p = svc.create_profile(name="Adult", mature_content_enabled=True)
    assert bool(p.mature_content_enabled) is True

    updated = svc.update_profile(p.id, mature_content_enabled=False)
    assert bool(updated.mature_content_enabled) is False


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


# --- ON DELETE CASCADE -------------------------------------------------------
#
# ``test_delete_profile`` above asserts the profile is gone. Nothing asserted
# that its *rows* are, and they are the half the database is doing on its own:
# ``ProfileService.delete_profile`` is one ``db.delete(profile)`` and
# ``ReadingProfile`` declares no ORM relationships, so every dependent row is
# removed by SQLite's ``ON DELETE CASCADE`` and by nothing else. SQLite honours
# that only while ``PRAGMA foreign_keys=ON`` is set on the connection, which is
# why these tests are meaningful at all (``install_sqlite_pragmas``, wired into
# the suite engine in conftest).
#
# The parametrisation is derived from the ORM metadata rather than typed out,
# so a table added later with a ``profile_id`` or ``user_id`` foreign key
# arrives here as a new failing case instead of quietly going uncovered --
# which is exactly how ``reading_day_stats`` came to sit outside the
# hand-written list in test_audit_isolation_profile_delete_cascade.


def _fk_children_of(parent_table: str) -> set[str]:
    return {
        table.name
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.column.table.name == parent_table
    }


#: Reached through ``collections``, not by a foreign key of its own: a
#: collection's membership rows must die with the profile that owned the
#: collection, and only a second cascade hop takes them.
TRANSITIVE_DEPENDENTS = {"collection_series"}

PROFILE_DEPENDENTS = sorted(_fk_children_of("reading_profiles") | TRANSITIVE_DEPENDENTS)
USER_DEPENDENTS = sorted(
    _fk_children_of("users") | _fk_children_of("reading_profiles") | TRANSITIVE_DEPENDENTS
)

#: What ``_seed_one_row_everywhere`` actually writes. ``reading_profiles`` is
#: absent because the test creates that row itself.
SEEDED_TABLES = frozenset(
    {
        "followed_series",
        "chapter_progress",
        "bookmarks",
        "reading_sessions",
        "reading_day_stats",
        "collections",
        "collection_series",
        "tags",
        "profile_series_tags",
        "update_notifications",
        "source_pins",
        "sessions",
    }
)

SRC, SERIES = "mangadex", "series-1"


def _seed_one_row_everywhere(db, user_id: int, profile_id: int) -> None:
    """One row in every table that hangs off a profile or an account."""
    follow = FollowedSeries(
        user_id=user_id, profile_id=profile_id, source_id=SRC,
        series_key=SERIES, title="Series One", known_chapters="[]",
    )
    collection = Collection(user_id=user_id, profile_id=profile_id, name="Coll")
    tag = Tag(user_id=user_id, profile_id=profile_id, name="tag")
    db.add_all([follow, collection, tag])
    db.flush()
    db.add_all([
        ChapterProgress(
            user_id=user_id, profile_id=profile_id, source_id=SRC,
            series_key=SERIES, chapter_key="c1", chapter_number=1.0, last_page=3,
        ),
        Bookmark(
            user_id=user_id, profile_id=profile_id, client_id="bm-1", source_id=SRC,
            series_key=SERIES, chapter_key="c1", media_type="manga",
            anchor_index=1, anchor_fraction=0.0, anchor_total=0,
        ),
        ReadingSession(
            user_id=user_id, profile_id=profile_id, source_id=SRC,
            series_key=SERIES, chapter_key="c1", pages_read=3,
        ),
        ReadingDayStats(user_id=user_id, profile_id=profile_id, day="2026-01-01"),
        CollectionSeries(
            collection_id=collection.id, source_id=SRC, series_key=SERIES
        ),
        ProfileSeriesTag(
            user_id=user_id, profile_id=profile_id, source_id=SRC,
            series_key=SERIES, tag_id=tag.id,
        ),
        UpdateNotification(
            user_id=user_id, profile_id=profile_id, followed_series_id=follow.id,
            source_id=SRC, series_key=SERIES, chapter_key="c2", chapter_title="Two",
        ),
        SourcePin(
            user_id=user_id, profile_id=profile_id, source_id=SRC, sort_order=0
        ),
        UserSession(
            user_id=user_id, token_hash="tok", expires_at=utcnow() + timedelta(days=1)
        ),
    ])
    db.commit()


def _rows_in(db, table_name: str) -> int:
    return db.execute(
        select(func.count()).select_from(Base.metadata.tables[table_name])
    ).scalar_one()


def test_the_cascade_seed_covers_every_dependent_table():
    """Guard against the parametrised tests below passing on an empty table.

    Each case asserts the row count falls to zero; a table nobody seeded starts
    at zero and passes for free. This is the assertion that turns "no rows
    left" into "the rows that were there are gone".
    """
    assert SEEDED_TABLES == set(USER_DEPENDENTS) - {"reading_profiles"}


@pytest.mark.parametrize("table", PROFILE_DEPENDENTS)
def test_deleting_a_profile_removes_every_dependent_row(db_session, users, table):
    """A deleted profile leaves nothing behind, table by table.

    Not academic: ``reading_profiles.id`` has no AUTOINCREMENT, so the next
    profile created gets the freed id back and inherits, through every
    ``_scope`` helper, whatever the cascade failed to take.
    """
    svc = ProfileService(db_session, user_id=users["alice"])
    profile = svc.create_profile(name="Doomed")
    _seed_one_row_everywhere(db_session, users["alice"], profile.id)
    assert _rows_in(db_session, table) == 1

    svc.delete_profile(profile.id)

    assert _rows_in(db_session, table) == 0


@pytest.mark.parametrize("table", USER_DEPENDENTS)
def test_deleting_a_user_removes_every_dependent_row(db_session, users, table):
    """The same, one level up -- and it takes two mechanisms, not one.

    ``users`` cascades to ``reading_profiles`` in the database, which cascades
    to everything profile-scoped; ``sessions`` is the odd one out, carrying no
    ``ondelete`` and being cleared by the ``User.sessions`` ORM relationship
    instead. Both are asserted the same way here because the row is equally
    gone either way, and a change that removed either mechanism would leave
    rows pointing at an account that no longer exists.
    """
    profile = ProfileService(db_session, user_id=users["alice"]).create_profile(
        name="Doomed"
    )
    _seed_one_row_everywhere(db_session, users["alice"], profile.id)
    assert _rows_in(db_session, table) == 1

    db_session.delete(db_session.get(User, users["alice"]))
    db_session.commit()

    assert _rows_in(db_session, table) == 0


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
