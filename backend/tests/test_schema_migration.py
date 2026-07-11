from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from database.models import Series
from database.session import (
    _migrate_chapter_number_to_float,
    _migrate_intelligence_columns,
)


def test_migrate_intelligence_columns_adds_sort_title(tmp_path):
    """Legacy databases missing intelligence columns must upgrade in place."""
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE libraries (
                  id INTEGER PRIMARY KEY,
                  name TEXT NOT NULL,
                  root_path TEXT NOT NULL UNIQUE,
                  scan_interval_minutes INTEGER DEFAULT 60,
                  created_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE series (
                  id INTEGER PRIMARY KEY,
                  library_id INTEGER NOT NULL,
                  title TEXT NOT NULL,
                  author TEXT,
                  description TEXT,
                  status TEXT,
                  cover_path TEXT,
                  folder_path TEXT NOT NULL,
                  created_at DATETIME,
                  updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO series (id, library_id, title, folder_path) "
                "VALUES (1, 1, 'Tower of God', '/comics/tog')"
            )
        )

    _migrate_intelligence_columns(engine)

    with engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(series)")).fetchall()
        }
        assert "sort_title" in columns
        sort_title = conn.execute(
            text("SELECT sort_title FROM series WHERE id = 1")
        ).scalar_one()
        assert sort_title == "Tower of God"


def test_legacy_migrations_upgrade_integer_chapters_in_place(tmp_path):
    """The pre-Alembic bring-up migrations must add intelligence columns and
    widen chapters.number (INTEGER -> REAL) on a legacy database, preserving
    data. These run in init_db() before Alembic adopts the (now baseline)
    schema; here they are exercised directly since a partial legacy schema is
    not a complete baseline Alembic can adopt."""
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE series (
                    id INTEGER PRIMARY KEY,
                    library_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    description TEXT,
                    status TEXT,
                    cover_path TEXT,
                    folder_path TEXT NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE volumes (
                    id INTEGER PRIMARY KEY,
                    series_id INTEGER NOT NULL,
                    title TEXT,
                    number INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE chapters (
                    id INTEGER PRIMARY KEY,
                    series_id INTEGER NOT NULL,
                    volume_id INTEGER,
                    title TEXT NOT NULL,
                    number INTEGER,
                    folder_path TEXT,
                    archive_path TEXT,
                    page_count INTEGER DEFAULT 0,
                    cover_path TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO series (id, library_id, title, folder_path) "
                "VALUES (1, 1, 'Legacy Series', '/legacy')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO chapters (id, series_id, title, number, folder_path) "
                "VALUES (1, 1, 'Chapter 1', 1, '/legacy/ch1')"
            )
        )

    # Order matters: intelligence columns (adds sort_key) before the chapters
    # rebuild, exactly as init_db() sequences them.
    _migrate_intelligence_columns(engine)
    _migrate_chapter_number_to_float(engine)

    inspector = inspect(engine)
    series_columns = {column["name"] for column in inspector.get_columns("series")}
    chapter_columns = {column["name"] for column in inspector.get_columns("chapters")}
    assert "sort_title" in series_columns
    assert "sort_key" in chapter_columns

    number_col = next(c for c in inspector.get_columns("chapters") if c["name"] == "number")
    assert "INT" not in str(number_col["type"]).upper()

    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=engine, autoflush=False)()
    try:
        row = db.query(Series).first()
        assert row is not None
        assert row.sort_title == "Legacy Series"
        # data preserved across the INTEGER -> REAL rebuild
        chapter = db.execute(text("SELECT number FROM chapters WHERE id = 1")).scalar_one()
        assert chapter == 1
    finally:
        db.close()
