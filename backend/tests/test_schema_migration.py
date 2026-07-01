from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from database.models import Series
from database.session import _migrate_intelligence_columns, init_db


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


def test_init_db_upgrades_legacy_schema_with_integer_chapters(tmp_path, monkeypatch):
    """init_db must add intelligence columns before rebuilding chapters.number."""
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

    monkeypatch.setenv("DB_PATH", str(db_path))

    from core.config import Settings, get_settings

    original = get_settings()
    patched = Settings(**{**original.model_dump(), "db_path": str(db_path)})
    get_settings.cache_clear()

    import database.session as session_module

    monkeypatch.setattr(session_module, "get_settings", lambda: patched)
    session_module.get_engine.cache_clear()

    init_db()

    inspector = inspect(session_module.get_engine())
    series_columns = {column["name"] for column in inspector.get_columns("series")}
    chapter_columns = {column["name"] for column in inspector.get_columns("chapters")}
    assert "sort_title" in series_columns
    assert "sort_key" in chapter_columns

    number_col = next(c for c in inspector.get_columns("chapters") if c["name"] == "number")
    assert "INT" not in str(number_col["type"]).upper()

    from sqlalchemy.orm import sessionmaker

    db = sessionmaker(bind=session_module.get_engine(), autoflush=False)()
    try:
        row = db.query(Series).first()
        assert row is not None
        assert row.sort_title == "Legacy Series"
    finally:
        db.close()

    get_settings.cache_clear()
    session_module.get_engine.cache_clear()
