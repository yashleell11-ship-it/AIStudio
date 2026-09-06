"""AUDIT (integrity-lifecycle): the database does not enforce "profile belongs to user".

Every per-profile table carries BOTH ``user_id`` and ``profile_id`` and every
read scopes on the pair, but the only constraints are two independent
single-column FKs (``user_id -> users.id``, ``profile_id -> reading_profiles.id``).
Nothing ties the pair together, so a row whose ``profile_id`` belongs to a
DIFFERENT account than its ``user_id`` is accepted by SQLite with
``PRAGMA foreign_keys=ON`` exactly as production runs it.

Such a row is invisible to every scoped read (silently "lost" data) and its
existence depends entirely on application discipline (``ProfileContext``).
The proposed backstop is a composite FK
``FOREIGN KEY (user_id, profile_id) REFERENCES reading_profiles (user_id, id)``
over a ``UNIQUE (user_id, id)`` index on ``reading_profiles`` — SQLite supports
composite FKs onto any UNIQUE index, and the app's ORM always writes the pair.

These tests are EXPECTED TO FAIL until such a constraint exists.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.time_utils import utcnow
from database.models import (
    Bookmark,
    ChapterProgress,
    FollowedSeries,
    ReadingSession,
)


def _make_rows():
    return {
        "followed_series": lambda uid, pid: FollowedSeries(
            user_id=uid, profile_id=pid, source_id="mangadex",
            series_key="s", title="S", known_chapters="[]",
        ),
        "chapter_progress": lambda uid, pid: ChapterProgress(
            user_id=uid, profile_id=pid, source_id="mangadex",
            series_key="s", chapter_key="c1", last_page=1,
        ),
        "bookmarks": lambda uid, pid: Bookmark(
            user_id=uid, profile_id=pid, client_id="cid-1", source_id="mangadex",
            series_key="s", chapter_key="c1",
        ),
        "reading_sessions": lambda uid, pid: ReadingSession(
            user_id=uid, profile_id=pid, source_id="mangadex",
            series_key="s", chapter_key="c1", start_page=1, end_page=2,
            pages_read=2, started_at=utcnow(), ended_at=utcnow(),
        ),
    }


@pytest.fixture
def fk_on(db_session):
    """Mirror production: ``database.session`` sets ``PRAGMA foreign_keys=ON``
    on every connection; the test engine in conftest does not. StaticPool means
    one connection, so setting it once on the session's connection sticks."""
    db_session.execute(text("PRAGMA foreign_keys=ON"))
    db_session.commit()
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1
    return db_session


@pytest.mark.parametrize("table", sorted(_make_rows()))
def test_db_rejects_profile_owned_by_a_different_user(
    fk_on, make_user, make_profile, table
):
    db = fk_on
    alice = make_user("alice")
    bob = make_user("bob")
    bobs_profile = make_profile(bob.id, "Bob's")
    build = _make_rows()[table]

    # Control: single-column FKs ARE enforced on this connection, so a
    # non-existent profile is rejected. This proves the pass/fail below is
    # about the missing composite constraint, not about FKs being off.
    db.add(build(alice.id, 999_999))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # The gap: alice's user_id paired with bob's profile_id.
    db.add(build(alice.id, bobs_profile.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return  # enforced — the audit gap is closed
    db.rollback()
    stored = db.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE user_id=:u AND profile_id=:p"),
        {"u": alice.id, "p": bobs_profile.id},
    ).scalar()
    pytest.fail(
        f"{table}: SQLite accepted a row with user_id={alice.id} (alice) and "
        f"profile_id={bobs_profile.id} (owned by bob); {stored} such row(s) "
        "now exist and no scoped read will ever return them. No constraint "
        "ties (user_id, profile_id) to reading_profiles(user_id, id)."
    )
