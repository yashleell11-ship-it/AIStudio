"""Revision ``0012_audit_indexes`` — what it does to a database with rows in it.

The production database is a live 21 MB file and this revision runs at boot, so
what is pinned here is not "the DDL parsed" but the three things that can go
wrong on real data: the dedupe that has to happen *before* the new UNIQUE index
can be built, the index inventory landing exactly as designed (DESC included —
an ASC index would silently not cover ``continue_reading``'s sort), and the
downgrade putting the schema back the way 0011 left it so the revision is
reversible rather than one-way.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import database.session as dbs

_PREV = "0011_source_cover_cache"
_HEAD = "0012_audit_indexes"

#: Indexes 0012 removes, by table. Each is either a strict prefix of another
#: index on the same table or a duplicate of a UNIQUE constraint's autoindex,
#: except ``ix_followed_series_content_rating`` — never a leading predicate
#: anywhere in the app (``content_rating`` is only ever projected).
_DROPPED = {
    "sessions": {"ix_sessions_token_hash"},
    "users": {"ix_users_username"},
    "bookmarks": {"ix_bookmarks_user_id"},
    "reading_profiles": {"ix_reading_profiles_user_id"},
    "source_pins": {"ix_source_pins_user_id"},
    "collections": {"ix_collections_user_id"},
    "followed_series": {"ix_followed_series_content_rating"},
    "chapter_ocr": {"ix_chapter_ocr_series"},
    "tags": {"ix_tags_scope"},
    "update_notifications": {
        "ix_update_notifications_user_id",
        "ix_update_notifications_is_read",
        "ix_update_notifications_created_at",
    },
}

#: Indexes 0012 adds, by table.
_ADDED = {
    "chapter_progress": {"ix_chapter_progress_profile_id"},
    "reading_sessions": {"ix_reading_sessions_profile_id"},
    "followed_series": {"ix_followed_series_profile_id"},
    "update_notifications": {
        "ix_update_notifications_scope_unread",
        "ix_update_notifications_scope_created",
        "uq_update_notifications_chapter",
    },
}


def _config():
    from alembic.config import Config

    backend_root = Path(dbs.__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    return cfg


def _migrate(engine, revision: str) -> None:
    from alembic import command

    cfg = _config()
    cfg.attributes["db_url"] = engine.url.render_as_string(hide_password=False)
    command.upgrade(cfg, revision)


def _downgrade(engine, revision: str) -> None:
    from alembic import command

    cfg = _config()
    cfg.attributes["db_url"] = engine.url.render_as_string(hide_password=False)
    command.downgrade(cfg, revision)


def _index_sql(engine) -> dict[str, str]:
    """``{index name: CREATE INDEX ...}`` for every named index in the file."""
    with engine.connect() as conn:
        return {
            row[0]: row[1] or ""
            for row in conn.execute(
                text(
                    "SELECT name, sql FROM sqlite_master WHERE type = 'index'"
                    " AND name NOT LIKE 'sqlite_autoindex%'"
                )
            )
        }


def _engine(tmp_path: Path, name: str):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    from database.session import install_sqlite_pragmas

    install_sqlite_pragmas(engine)
    return engine


def _seed_scope(conn) -> None:
    """One account, one profile, one follow — the parents every row needs."""
    conn.execute(
        text(
            "INSERT INTO users (id, username, password_hash, is_admin,"
            " is_active, created_at, updated_at) VALUES"
            " (1, 'owner', 'x', 1, 1, '2026-01-01', '2026-01-01')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO reading_profiles (id, user_id, name, avatar_key, mood,"
            " mature_content_enabled, sort_order, created_at)"
            " VALUES (10, 1, 'A', 'a', 'calm', 0, 0, '2026-01-01')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO followed_series (id, user_id, profile_id, source_id,"
            " series_key, title, is_favorite, reading_status, notify,"
            " sort_order, known_chapters, chapter_count, created_at, updated_at)"
            " VALUES (100, 1, 10, 'mangadex', 's1', 'S1', 0, 'reading', 1, 0,"
            " '[]', 0, '2026-01-01', '2026-01-01')"
        )
    )


def _insert_notification(conn, nid: int, chapter_key: str, created_at: str) -> None:
    conn.execute(
        text(
            "INSERT INTO update_notifications (id, user_id, profile_id,"
            " followed_series_id, source_id, series_key, chapter_key,"
            " chapter_title, chapter_number, is_read, created_at) VALUES"
            " (:i, 1, 10, 100, 'mangadex', 's1', :c, :t, 1.0, 0, :d)"
        ),
        {"i": nid, "c": chapter_key, "t": f"Chapter {chapter_key}", "d": created_at},
    )


@pytest.fixture
def at_0011(tmp_path):
    """A database sitting on 0011 with a user, a profile and a follow."""
    engine = _engine(tmp_path, "audit0012.db")
    _migrate(engine, _PREV)
    with engine.begin() as conn:
        _seed_scope(conn)
    return engine


def test_upgrade_lands_the_designed_index_inventory(at_0011):
    before = _index_sql(at_0011)
    for table, names in _DROPPED.items():
        assert names <= set(before), f"{table}: 0011 should still have {names}"

    _migrate(at_0011, "head")
    after = _index_sql(at_0011)

    still_there = {n for names in _DROPPED.values() for n in names} & set(after)
    assert not still_there, f"0012 left redundant indexes behind: {still_there}"

    missing = {n for names in _ADDED.values() for n in names} - set(after)
    assert not missing, f"0012 did not create: {missing}"


def test_continue_reading_index_carries_the_descending_sort(at_0011):
    """The whole point of IDX-1: an ASC index does not cover the window sort.

    ``continue_reading`` partitions by ``(source_id, series_key)`` and orders
    each partition by ``(last_read_at DESC, id DESC)``. Reflection reports
    column names only, so the direction has to be read off the DDL — which is
    also the only place a silently-ASC index would show up.
    """
    _migrate(at_0011, "head")
    sql = _index_sql(at_0011)["ix_chapter_progress_series"]
    normalised = " ".join(sql.split()).lower()
    assert (
        "(user_id, profile_id, source_id, series_key, last_read_at desc, id desc)"
        in normalised
    ), sql


def test_duplicate_notifications_are_deduped_before_the_unique_index(at_0011):
    """A connector that re-lists a chapter already wrote duplicates; the
    revision has to survive them, and it keeps the row the reader has seen.

    The lowest id is the one that was there first — the one whose read state
    and position in the list the owner already knows — so it is the survivor
    and the later re-notifications are what disappear.
    """
    with at_0011.begin() as conn:
        _insert_notification(conn, 1, "c1", "2026-01-01")
        _insert_notification(conn, 2, "c1", "2026-01-02")  # re-list #1
        _insert_notification(conn, 3, "c1", "2026-01-03")  # re-list #2
        _insert_notification(conn, 4, "c2", "2026-01-04")

    _migrate(at_0011, "head")

    with at_0011.connect() as conn:
        rows = sorted(
            conn.execute(
                text("SELECT id, chapter_key FROM update_notifications")
            ).all()
        )
    assert rows == [(1, "c1"), (4, "c2")], rows

    with pytest.raises(IntegrityError):
        with at_0011.begin() as conn:
            _insert_notification(conn, 5, "c1", "2026-01-05")


def test_dedupe_is_scoped_to_one_followed_series(at_0011):
    """Two series that happen to name a chapter the same are not duplicates."""
    with at_0011.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO followed_series (id, user_id, profile_id, source_id,"
                " series_key, title, is_favorite, reading_status, notify,"
                " sort_order, known_chapters, chapter_count, created_at,"
                " updated_at) VALUES (101, 1, 10, 'mangadex', 's2', 'S2', 0,"
                " 'reading', 1, 0, '[]', 0, '2026-01-01', '2026-01-01')"
            )
        )
        _insert_notification(conn, 1, "c1", "2026-01-01")
        conn.execute(
            text(
                "INSERT INTO update_notifications (id, user_id, profile_id,"
                " followed_series_id, source_id, series_key, chapter_key,"
                " chapter_title, chapter_number, is_read, created_at) VALUES"
                " (2, 1, 10, 101, 'mangadex', 's2', 'c1', 'Chapter 1', 1.0, 0,"
                " '2026-01-01')"
            )
        )

    _migrate(at_0011, "head")

    with at_0011.connect() as conn:
        kept = conn.execute(
            text("SELECT id FROM update_notifications ORDER BY id")
        ).scalars().all()
    assert kept == [1, 2], kept


def test_reading_day_stats_rolls_up_per_profile_and_cascades(at_0011):
    _migrate(at_0011, "head")

    with at_0011.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO reading_day_stats (user_id, profile_id, day,"
                " sessions, pages_read, seconds_read, series_count)"
                " VALUES (1, 10, '2026-01-01', 3, 40, 900, 2)"
            )
        )
    # The primary key is the rollup identity: one row per (user, profile, day).
    with pytest.raises(IntegrityError):
        with at_0011.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO reading_day_stats (user_id, profile_id, day,"
                    " sessions, pages_read, seconds_read, series_count)"
                    " VALUES (1, 10, '2026-01-01', 1, 1, 1, 1)"
                )
            )

    with at_0011.begin() as conn:
        conn.execute(text("DELETE FROM reading_profiles WHERE id = 10"))
    with at_0011.connect() as conn:
        left = conn.execute(
            text("SELECT COUNT(*) FROM reading_day_stats")
        ).scalar_one()
    assert left == 0, "profile delete did not cascade into reading_day_stats"


def test_cover_cache_can_hold_a_negative_entry(at_0011):
    """A cover that cannot be downscaled must be recordable as such."""
    _migrate(at_0011, "head")
    with at_0011.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO source_cover_cache (source_id, series_key, width,"
                " fmt, media_type, byte_size, data, fetched_at, last_used_at,"
                " resize_failure, resize_failed_at) VALUES ('asurascans', 's1',"
                " 360, 'jpeg', 'image/jpeg', 0, X'', '2026-01-01',"
                " '2026-01-01', 'no_gain', '2026-01-01')"
            )
        )
        # A positive row leaves both new columns NULL.
        conn.execute(
            text(
                "INSERT INTO source_cover_cache (source_id, series_key, width,"
                " fmt, media_type, byte_size, data, fetched_at, last_used_at)"
                " VALUES ('asurascans', 's2', 360, 'jpeg', 'image/webp', 3,"
                " X'616263', '2026-01-01', '2026-01-01')"
            )
        )
    with at_0011.connect() as conn:
        rows = dict(
            conn.execute(
                text(
                    "SELECT series_key, resize_failure FROM source_cover_cache"
                    " ORDER BY series_key"
                )
            ).all()
        )
    assert rows == {"s1": "no_gain", "s2": None}


def test_downgrade_restores_the_0011_schema_and_keeps_the_rows(at_0011):
    """0012 must be reversible: the 21 MB production file has to be able to go
    back if the deploy is rolled back, without losing notifications."""
    with at_0011.begin() as conn:
        _insert_notification(conn, 1, "c1", "2026-01-01")
        _insert_notification(conn, 2, "c2", "2026-01-02")
    before = _index_sql(at_0011)

    _migrate(at_0011, "head")
    _downgrade(at_0011, _PREV)

    after = _index_sql(at_0011)
    assert after == before, {
        "gained": sorted(set(after) - set(before)),
        "lost": sorted(set(before) - set(after)),
    }
    with at_0011.connect() as conn:
        assert "reading_day_stats" not in set(inspect(at_0011).get_table_names())
        cover_cols = {
            r[1] for r in conn.execute(text("PRAGMA table_info(source_cover_cache)"))
        }
        assert not {"resize_failure", "resize_failed_at"} & cover_cols
        kept = conn.execute(
            text("SELECT id FROM update_notifications ORDER BY id")
        ).scalars().all()
    assert kept == [1, 2]

    # ...and forward again, which is what a re-deploy does.
    _migrate(at_0011, "head")
    assert "uq_update_notifications_chapter" in _index_sql(at_0011)
