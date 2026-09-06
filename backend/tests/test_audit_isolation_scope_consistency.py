"""Audit (isolation shard): nothing in the schema ties ``user_id`` to ``profile_id``.

Every profile-scoped table carries both columns and every ``_scope`` helper
filters on both, but the two are independent foreign keys: ``user_id`` ->
``users.id`` and ``profile_id`` -> ``reading_profiles.id``. The database will
happily store a row whose ``profile_id`` belongs to a *different* account than
its ``user_id``. No application path writes such a row today (every write
takes ``profile_id`` from a ``ProfileContext`` validated against ``user_id`` in
core/profile_context.py:69-80), so this is defense in depth, not a live leak;
but a single future bug of the form ``profile_id=body.profile_id`` would be
accepted silently, and the row would then be invisible to *both* accounts'
scopes (user A's scope requires A's profile; B's scope requires B's user_id).

Expected to FAIL today: the insert succeeds. Fix design: a composite FK
``(user_id, profile_id) REFERENCES reading_profiles (user_id, id) ON DELETE
CASCADE`` on each child table, backed by ``UNIQUE (user_id, id)`` on
``reading_profiles`` (SQLite requires the parent columns to be uniquely
constrained together). Alembic batch mode rebuilds each table once.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base, FollowedSeries, ReadingProfile, User


@pytest.fixture
def fk_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'fk.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, _record) -> None:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_db_rejects_a_row_whose_profile_belongs_to_another_account(fk_session):
    db = fk_session
    alice = User(username="alice", password_hash="x")
    bob = User(username="bob", password_hash="x")
    db.add_all([alice, bob])
    db.commit()
    bobs_profile = ReadingProfile(user_id=bob.id, name="Bob")
    db.add(bobs_profile)
    db.commit()

    db.add(
        FollowedSeries(
            user_id=alice.id,               # Alice's account...
            profile_id=bobs_profile.id,     # ...Bob's profile.
            source_id="mangadex",
            series_key="s1",
            title="S1",
            known_chapters="[]",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
