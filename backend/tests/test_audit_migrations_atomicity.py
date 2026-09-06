"""AUDIT (migrations shard) — a migration that dies mid-way must not brick the next boot.

``database.session.run_alembic_migrations`` runs at application start against
the live file. ``alembic/env.py`` builds its own engine from ``db_url`` and
relies on pysqlite's transaction handling, and pysqlite in legacy mode
(``isolation_level=''``) only issues an implicit BEGIN before DML — never before
DDL. So inside a table-rebuild revision (0002 ``tags``, 0010 ``bookmarks``)
the ``CREATE TABLE <x>_new`` is committed the instant it runs, while the
INSERT..SELECT / UPDATE / DROP / RENAME that follow roll back on failure.

Consequence, reproduced here: a crash (OOM-kill, power loss, ``docker stop``
during a deploy) between the CREATE and the final RENAME leaves an empty
``bookmarks_new`` and ``alembic_version`` still at 0009. The container
(``restart=unless-stopped``) comes back, re-runs 0010, and dies on
``table bookmarks_new already exists`` — every boot, until someone drops the
scratch table by hand. There is no backup on the VPS to fall back on.

Fixed in ``alembic/env.py`` with SQLAlchemy's documented pysqlite recipe
(``isolation_level = None`` on connect + an explicit ``BEGIN`` in the ``begin``
event), which puts DDL inside the transaction alembic already opens per
revision. The last two tests cover the snapshot env.py takes on the way in.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import event
from sqlalchemy.engine import Engine

import database.session as dbs

_BEFORE_REBUILD = "0009_reading_session_duration"


def _cfg(db_path: Path) -> Config:
    """Same wiring as ``run_alembic_migrations``: db_url only, env.py builds the engine."""
    root = Path(dbs.__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.attributes["db_url"] = f"sqlite:///{db_path}"
    return cfg


def _head(db_path: Path) -> str:
    """Whatever the newest revision is, so adding one does not fail this file."""
    return ScriptDirectory.from_config(_cfg(db_path)).get_current_head()


def _seed_one_bookmark(db_path: Path) -> None:
    c = sqlite3.connect(db_path)
    c.execute(
        "INSERT INTO users(id,username,password_hash,is_admin,is_active,created_at,updated_at)"
        " VALUES (1,'a','x',1,1,'2026-01-01','2026-01-01')"
    )
    c.execute(
        "INSERT INTO reading_profiles(id,user_id,name,avatar_key,mood,sort_order,"
        "mature_content_enabled,created_at) VALUES (1,1,'p','d','d',0,0,'2026-01-01')"
    )
    c.execute(
        "INSERT INTO bookmarks(id,user_id,profile_id,source_id,series_key,chapter_key,"
        "page,note,created_at) VALUES (1,1,1,'md','s','c',3,'keep','2026-01-01')"
    )
    c.commit()
    c.close()


def _crash_during_0010(db_path: Path) -> None:
    """Upgrade 0009 -> head, but die inside 0010 after ``bookmarks_new`` exists
    and before the old table is dropped (the first UPDATE of ``_assign_client_ids``)."""
    armed = {"on": True}

    def crash(conn, cursor, statement, params, context, executemany):  # noqa: ARG001
        if armed["on"] and statement.lstrip().upper().startswith(
            "UPDATE BOOKMARKS_NEW SET CLIENT_ID"
        ):
            raise RuntimeError("simulated OOM-kill mid-migration")

    # Class-level listener: fires for the engine env.py builds from db_url,
    # i.e. the exact app-boot path — not a hand-made connection.
    event.listen(Engine, "before_cursor_execute", crash)
    try:
        with pytest.raises(RuntimeError):
            command.upgrade(_cfg(db_path), "head")
    finally:
        armed["on"] = False
        event.remove(Engine, "before_cursor_execute", crash)


def test_failed_rebuild_migration_leaves_no_scratch_table(tmp_path):
    db = tmp_path / "crash.db"
    command.upgrade(_cfg(db), _BEFORE_REBUILD)
    _seed_one_bookmark(db)

    _crash_during_0010(db)

    c = sqlite3.connect(db)
    version = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    tables = {
        r[0]
        for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    c.close()
    # The revision did not complete, so the database must look like 0009 —
    # no half-built scratch table left behind by an autocommitted CREATE.
    assert version == _BEFORE_REBUILD
    assert "bookmarks_new" not in tables, (
        "CREATE TABLE bookmarks_new was committed outside the migration "
        "transaction (pysqlite does not BEGIN before DDL)"
    )


def test_next_boot_after_failed_rebuild_migration_reaches_head(tmp_path):
    db = tmp_path / "crash.db"
    command.upgrade(_cfg(db), _BEFORE_REBUILD)
    _seed_one_bookmark(db)

    _crash_during_0010(db)

    # Next container start == run_alembic_migrations again. Today this raises
    # OperationalError: table bookmarks_new already exists, on every boot.
    command.upgrade(_cfg(db), "head")

    c = sqlite3.connect(db)
    assert c.execute("SELECT version_num FROM alembic_version").fetchone()[0] == _head(db)
    assert c.execute("SELECT note, anchor_index FROM bookmarks").fetchall() == [("keep", 3)]
    c.close()


def _snapshots(db_path: Path) -> list[Path]:
    """Pre-migration copies env.py left next to the database, newest first."""
    return sorted(
        db_path.parent.glob(f"{db_path.name}.pre-migration-*.db"), reverse=True
    )


def test_snapshot_taken_before_outstanding_revisions_run(tmp_path):
    db = tmp_path / "boot.db"
    command.upgrade(_cfg(db), _BEFORE_REBUILD)
    _seed_one_bookmark(db)
    # The baseline built this file from nothing -- there was no prior state to
    # copy, so nothing should have been written for it.
    assert _snapshots(db) == []

    command.upgrade(_cfg(db), "head")

    copies = _snapshots(db)
    assert len(copies) == 1
    c = sqlite3.connect(copies[0])
    # Taken before 0010 ran: the copy is still at 0009, with the row intact.
    assert c.execute("SELECT version_num FROM alembic_version").fetchone()[0] == _BEFORE_REBUILD
    assert c.execute("SELECT note FROM bookmarks").fetchall() == [("keep",)]
    c.close()

    # A boot with nothing to apply is the common case; it must not copy the
    # database on every restart.
    command.upgrade(_cfg(db), "head")
    assert _snapshots(db) == copies


def test_snapshots_do_not_accumulate(tmp_path):
    db = tmp_path / "boot.db"
    command.upgrade(_cfg(db), "0005_single_admin_guard")
    for revision in (
        "0006_reading_session_stats_index",
        "0007_novel_chapter_cache",
        "0008_followed_series_chapter_count",
        _BEFORE_REBUILD,
    ):
        command.upgrade(_cfg(db), revision)

    # Four upgrades, but each copy is a whole database on a ~20GB box.
    assert len(_snapshots(db)) == 2
