from __future__ import annotations

import logging
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import MetaData, create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable

from core.config import get_settings
from database.models import Base

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


SessionLocal = sessionmaker(
    bind=get_engine(),
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    engine = get_engine()
    _migrate_intelligence_columns(engine)
    _migrate_chapter_number_to_float(engine)
    Base.metadata.create_all(bind=engine)
    _init_fts5(engine)


def _ensure_sqlite_columns(
    engine: Engine,
    table: str,
    columns: dict[str, str],
) -> None:
    """Add missing columns on existing SQLite databases. Idempotent."""
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(table)}
    missing = {name: ddl for name, ddl in columns.items() if name not in existing}
    if not missing:
        return

    with engine.begin() as conn:
        for name, ddl in missing.items():
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    logger.info("Added missing columns to %s: %s", table, ", ".join(missing))


def _migrate_intelligence_columns(engine: Engine) -> None:
    """Backfill Library Intelligence columns on databases created before those fields."""
    _ensure_sqlite_columns(
        engine,
        "series",
        {
            "sort_title": "TEXT NOT NULL DEFAULT ''",
            "original_title": "TEXT",
            "artist": "TEXT",
            "content_rating": "TEXT NOT NULL DEFAULT 'unknown'",
            "language": "TEXT NOT NULL DEFAULT 'ko'",
            "year": "INTEGER",
            "is_favorite": "INTEGER NOT NULL DEFAULT 0",
            "reading_status": "TEXT NOT NULL DEFAULT 'unread'",
            "total_chapters": "INTEGER NOT NULL DEFAULT 0",
            "read_chapters": "INTEGER NOT NULL DEFAULT 0",
            "total_pages": "INTEGER NOT NULL DEFAULT 0",
            "is_created": "INTEGER NOT NULL DEFAULT 0",
            "deleted_at": "DATETIME",
        },
    )
    _ensure_sqlite_columns(
        engine,
        "chapters",
        {
            "sort_key": "TEXT NOT NULL DEFAULT ''",
            "is_read": "INTEGER NOT NULL DEFAULT 0",
            "read_at": "DATETIME",
            "updated_at": "DATETIME",
            "created_at": "DATETIME",
            "scanned_at": "DATETIME",
        },
    )

    inspector = inspect(engine)
    if "chapters" in inspector.get_table_names():
        chapter_columns = {
            column["name"] for column in inspector.get_columns("chapters")
        }
        with engine.begin() as conn:
            if "updated_at" in chapter_columns:
                conn.execute(
                    text(
                        "UPDATE chapters SET updated_at = CURRENT_TIMESTAMP "
                        "WHERE updated_at IS NULL"
                    )
                )
            if "created_at" in chapter_columns:
                conn.execute(
                    text(
                        "UPDATE chapters SET created_at = CURRENT_TIMESTAMP "
                        "WHERE created_at IS NULL"
                    )
                )

    inspector = inspect(engine)
    if "series" not in inspector.get_table_names():
        return

    series_columns = {column["name"] for column in inspector.get_columns("series")}
    if "sort_title" not in series_columns:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE series SET sort_title = title "
                "WHERE sort_title IS NULL OR sort_title = ''"
            )
        )


def _migrate_chapter_number_to_float(engine: Engine) -> None:
    """One-time schema migration: widen chapters.number from INTEGER to REAL.

    SQLite has no ALTER COLUMN TYPE; this performs the standard rebuild-and-
    swap procedure (create new table, copy rows, drop old, rename). Every
    existing row is copied across unchanged column by column — no data is
    dropped, reordered, or reinterpreted. This does not recover chapter
    numbers that were already truncated to integers before this fix (that
    precision was lost at parse time, before it ever reached the database);
    it only guarantees the schema change itself is lossless and idempotent.

    No-op on a brand new database — ``create_all()`` below creates the
    table with the correct REAL type directly. No-op if the migration has
    already run (column is already REAL/FLOAT).
    """
    inspector = inspect(engine)
    if "chapters" not in inspector.get_table_names():
        return

    columns = inspector.get_columns("chapters")
    number_col = next((c for c in columns if c["name"] == "number"), None)
    if number_col is None or "INT" not in str(number_col["type"]).upper():
        return

    chapters_table = Base.metadata.tables["chapters"]
    scratch_metadata = MetaData()
    # chapters.series_id / chapters.volume_id are foreign keys; the referenced
    # tables must also exist in the scratch metadata for DDL compilation to
    # resolve them, even though we never emit CREATE TABLE for them here.
    for referenced_table in ("series", "volumes"):
        Base.metadata.tables[referenced_table].to_metadata(scratch_metadata)
    rebuild_table = chapters_table.to_metadata(scratch_metadata, name="chapters_new")
    column_names = ", ".join(c.name for c in chapters_table.columns)

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(CreateTable(rebuild_table))
        conn.execute(
            text(
                f"INSERT INTO chapters_new ({column_names}) "
                f"SELECT {column_names} FROM chapters"
            )
        )
        conn.execute(text("DROP TABLE chapters"))
        conn.execute(text("ALTER TABLE chapters_new RENAME TO chapters"))
        for index in chapters_table.indexes:
            conn.execute(CreateIndex(index))
        conn.execute(text("PRAGMA foreign_keys=ON"))

    logger.info(
        "Migrated chapters.number column from INTEGER to REAL — existing values preserved."
    )


def _init_fts5(engine) -> None:
    """Create FTS5 virtual tables for full-text search. Idempotent."""
    from sqlalchemy import text

    with engine.begin() as conn:
        # Check if series_fts already exists
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='series_fts'")
        )
        if result.fetchone():
            return

        conn.execute(
            text("""
            CREATE VIRTUAL TABLE series_fts USING fts5(
                title, original_title, author, artist, description,
                content = 'series',
                content_rowid = 'id',
                tokenize = 'unicode61 remove_diacritics 2'
            )
            """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER series_fts_ai AFTER INSERT ON series BEGIN
                INSERT INTO series_fts(rowid, title, original_title, author, artist, description)
                VALUES (new.id, new.title, new.original_title, new.author, new.artist, new.description);
            END
            """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER series_fts_ad AFTER DELETE ON series BEGIN
                INSERT INTO series_fts(series_fts, rowid, title, original_title, author, artist, description)
                VALUES ('delete', old.id, old.title, old.original_title, old.author, old.artist, old.description);
            END
            """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER series_fts_au AFTER UPDATE ON series BEGIN
                INSERT INTO series_fts(series_fts, rowid, title, original_title, author, artist, description)
                VALUES ('delete', old.id, old.title, old.original_title, old.author, old.artist, old.description);
                INSERT INTO series_fts(rowid, title, original_title, author, artist, description)
                VALUES (new.id, new.title, new.original_title, new.author, new.artist, new.description);
            END
            """)
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
