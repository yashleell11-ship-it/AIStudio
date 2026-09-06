"""AUDIT (shard test-coverage): the suite's SQLite engine never runs the
production ``connect`` pragmas, so every test executes with
``PRAGMA foreign_keys=OFF`` while production (database/session.py:36-40)
runs with it ON. These tests are EXPECTED TO FAIL on the current conftest and
document the gap; they pass once ``db_engine`` installs the same listener.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database.models import ReadingProfile, SourcePin, User


def test_db_engine_enforces_foreign_keys_like_production(db_engine):
    with db_engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_orphan_profile_row_is_rejected(db_session):
    db_session.add(ReadingProfile(user_id=999_999, name="ghost"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_a_profile_cascades_its_source_pins(db_session):
    user = User(username="alice", password_hash="x", is_admin=False, is_active=True)
    db_session.add(user)
    db_session.commit()
    profile = ReadingProfile(user_id=user.id, name="P")
    db_session.add(profile)
    db_session.commit()
    db_session.add(SourcePin(user_id=user.id, profile_id=profile.id, source_id="mangadex"))
    db_session.commit()
    db_session.delete(profile)
    db_session.commit()
    db_session.expire_all()
    assert db_session.query(SourcePin).count() == 0, "ON DELETE CASCADE did not fire"
