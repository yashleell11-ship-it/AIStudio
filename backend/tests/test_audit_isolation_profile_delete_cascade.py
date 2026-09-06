"""Audit (isolation shard): profile deletion is ONE ``DELETE FROM reading_profiles``.

``ProfileService.delete_profile`` (services/profile_service.py:194-203) does
``db.delete(profile)`` and nothing else. ``ReadingProfile`` declares no ORM
relationships, so SQLAlchemy cascades nothing in Python: every profile-scoped
table (followed_series, chapter_progress, bookmarks, reading_sessions,
collections, tags, profile_series_tags, update_notifications, source_pins) is
cleaned up only by SQLite's ``ON DELETE CASCADE``, which SQLite honours only
while ``PRAGMA foreign_keys=ON`` is set on *that* connection
(database/session.py:38 sets it for the app engine).

``reading_profiles.id`` has no AUTOINCREMENT (the live DB has no
``sqlite_sequence`` table), so the profile created right after deleting the
highest-id one gets the SAME id back. On a connection without the pragma the
new profile therefore inherits its predecessor's entire library, history,
bookmarks, notifications and pins through every ``_scope`` helper.

The suite's engine (tests/conftest.py:31-48) is exactly such a connection, so
``tests/test_profiles.py::test_delete_profile`` cannot notice a lost CASCADE.
Two of the tests below are expected to FAIL on the suite engine — that is the
finding. The production-pragma variant passes today because the live schema
(checked read-only on the VPS) carries ON DELETE CASCADE on every profile_id
FK; the last test guards the ORM metadata so that stays true.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.profile_context import ProfileContext
from database.models import (
    Base,
    Bookmark,
    ChapterProgress,
    Collection,
    CollectionSeries,
    FollowedSeries,
    ProfileSeriesTag,
    ReadingSession,
    SourcePin,
    Tag,
    UpdateNotification,
    User,
)
from services.bookmark_service import BookmarkService
from services.followed_series_service import FollowedSeriesService
from services.profile_service import ProfileService
from services.progress_service import ProgressService
from services.source_pin_service import SourcePinService
from services.update_service import UpdateService

SRC, SERIES = "mangadex", "series-1"


def _seed_everything(db, user_id: int, profile_id: int) -> None:
    """One row in every profile-scoped table, owned by (user_id, profile_id)."""
    follow = FollowedSeries(
        user_id=user_id, profile_id=profile_id, source_id=SRC,
        series_key=SERIES, title="Series One", known_chapters="[]",
    )
    db.add(follow)
    db.flush()
    db.add(ChapterProgress(
        user_id=user_id, profile_id=profile_id, source_id=SRC,
        series_key=SERIES, chapter_key="c1", chapter_number=1.0, last_page=3,
    ))
    db.add(Bookmark(
        user_id=user_id, profile_id=profile_id, client_id="bm-1", source_id=SRC,
        series_key=SERIES, chapter_key="c1", media_type="manga",
        anchor_index=1, anchor_fraction=0.0, anchor_total=0,
    ))
    db.add(ReadingSession(
        user_id=user_id, profile_id=profile_id, source_id=SRC,
        series_key=SERIES, chapter_key="c1", pages_read=3,
    ))
    coll = Collection(user_id=user_id, profile_id=profile_id, name="Coll")
    db.add(coll)
    db.flush()
    db.add(CollectionSeries(collection_id=coll.id, source_id=SRC, series_key=SERIES))
    tag = Tag(user_id=user_id, profile_id=profile_id, name="tag")
    db.add(tag)
    db.flush()
    db.add(ProfileSeriesTag(
        user_id=user_id, profile_id=profile_id, source_id=SRC,
        series_key=SERIES, tag_id=tag.id,
    ))
    db.add(UpdateNotification(
        user_id=user_id, profile_id=profile_id, followed_series_id=follow.id,
        source_id=SRC, series_key=SERIES, chapter_key="c2", chapter_title="Two",
    ))
    db.add(SourcePin(user_id=user_id, profile_id=profile_id, source_id=SRC, sort_order=0))
    db.commit()


def _visible_to(db, user_id: int, profile_id: int) -> dict[str, int]:
    """What the (user, profile) sees through the real service scope helpers."""
    followed = FollowedSeriesService(
        db, MagicMock(), user_id=user_id, profile_id=profile_id
    )
    progress = ProgressService(db, user_id=user_id, profile_id=profile_id)
    bookmarks = BookmarkService(db, user_id=user_id, profile_id=profile_id)
    updates = UpdateService(db, user_id=user_id, profile_id=profile_id)
    pins = SourcePinService(db, ProfileContext(user_id=user_id, profile_id=profile_id))
    sessions = db.execute(
        select(func.count()).select_from(ReadingSession).where(
            ReadingSession.user_id == user_id,
            ReadingSession.profile_id == profile_id,
        )
    ).scalar_one()
    return {
        "followed": followed.list_series()["total"],
        "collections": len(followed.list_collections()),
        "tags": len(followed.list_tags()),
        "history": len(progress.reading_history()),
        "bookmarks": len(bookmarks.list_bookmarks()),
        "notifications": updates.count_notifications(),
        "pins": len(pins.list_pins()),
        "sessions": int(sessions),
    }


NOTHING = {
    "followed": 0, "collections": 0, "tags": 0, "history": 0,
    "bookmarks": 0, "notifications": 0, "pins": 0, "sessions": 0,
}


def _delete_then_recreate(db, user_id: int) -> tuple[int, int]:
    svc = ProfileService(db, user_id=user_id)
    old = svc.create_profile(name="Old")
    _seed_everything(db, user_id, old.id)
    assert _visible_to(db, user_id, old.id) != NOTHING  # seed is really visible
    svc.delete_profile(old.id)
    new = svc.create_profile(name="New")
    return old.id, new.id


# --- the gap: the suite engine ------------------------------------------------


def test_suite_engine_sets_the_pragma_production_relies_on(db_engine):
    """conftest.db_engine mirrors SessionLocal's flags but not its pragmas."""
    with db_engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_recreated_profile_inherits_nothing_on_the_suite_engine(db_session, make_user):
    user = make_user("cascade-suite")
    old_id, new_id = _delete_then_recreate(db_session, user.id)
    # SQLite reuses the highest freed rowid: no AUTOINCREMENT on reading_profiles.
    assert new_id == old_id
    assert _visible_to(db_session, user.id, new_id) == NOTHING


# --- production pragmas: passes today, documents what prod depends on ----------


@pytest.fixture
def prod_pragma_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'prod.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, _record) -> None:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_recreated_profile_inherits_nothing_with_production_pragmas(prod_pragma_session):
    db = prod_pragma_session
    user = User(username="cascade-prod", password_hash="x", is_admin=False, is_active=True)
    db.add(user)
    db.commit()
    old_id, new_id = _delete_then_recreate(db, user.id)
    assert new_id == old_id
    assert _visible_to(db, user.id, new_id) == NOTHING
    # And nothing is left behind under the old id in ANY table.
    for model in (
        FollowedSeries, ChapterProgress, Bookmark, ReadingSession, Collection,
        Tag, ProfileSeriesTag, UpdateNotification, SourcePin,
    ):
        left = db.execute(
            select(func.count()).select_from(model).where(model.profile_id == old_id)
        ).scalar_one()
        assert left == 0, f"{model.__tablename__} kept {left} row(s) for profile {old_id}"


def test_every_profile_id_fk_cascades_in_the_orm_schema():
    """Guard: a future migration that rebuilds a table (SQLite batch mode) and
    drops ON DELETE CASCADE turns the inheritance above into production."""
    missing = sorted(
        table.name
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.column.table.name == "reading_profiles"
        and (fk.ondelete or "").upper() != "CASCADE"
    )
    assert missing == []
