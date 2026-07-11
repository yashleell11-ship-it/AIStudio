from __future__ import annotations

import logging
from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

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
    # Legacy idempotent migrations bring any pre-Alembic database up to the
    # baseline schema BEFORE Alembic adopts it. Both are no-ops on a fresh or
    # already-current database (they guard on table existence / column type).
    _migrate_intelligence_columns(engine)
    _migrate_chapter_number_to_float(engine)
    # Alembic is the schema authority from the baseline onward: it creates every
    # table on a fresh database, adopts a pre-Alembic database at the baseline
    # (stamp only — no destructive re-create), and applies later revisions such
    # as the multi-user ownership migration.
    run_alembic_migrations(engine)
    _init_fts5(engine)


def run_alembic_migrations(engine: Engine) -> None:
    """Bring the database schema to the latest Alembic revision.

    - Fresh database (no tables, no version): runs every revision from the
      baseline, creating the full schema.
    - Pre-Alembic database (app tables exist, no ``alembic_version``): adopts it
      at the baseline via ``stamp`` (the tables already match the baseline), then
      applies any later revisions.
    - Already-tracked database: applies outstanding revisions (no-op at head).
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    # Absolute path so migrations resolve regardless of the process CWD (the
    # container runs from /app; the CLI may run from anywhere).
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    # Point Alembic at this very database (env.py reads this override).
    cfg.attributes["db_url"] = engine.url.render_as_string(hide_password=False)

    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
        has_app_tables = inspect(conn).has_table("series")
        stamp_target: str | None = None
        if current is None and has_app_tables:
            # Adopt an untracked database at the revision that matches its actual
            # schema: head if the schema already equals the models (e.g. one
            # built by create_all), otherwise the baseline (a pre-ownership
            # production database) so the upgrade below applies the outstanding
            # revisions. Stamping avoids re-running CREATEs against live tables.
            script = ScriptDirectory.from_config(cfg)
            if _schema_matches_head(conn):
                stamp_target = script.get_current_head()
            else:
                stamp_target = script.get_base()

    if stamp_target is not None:
        command.stamp(cfg, stamp_target)
        logger.info("Adopted existing database into Alembic at %s", stamp_target)
    command.upgrade(cfg, "head")


def _schema_matches_head(conn) -> bool:
    """True if the live schema already equals the ORM models (ignoring the FTS5
    virtual tables, which live outside Alembic in _init_fts5)."""
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    ctx = MigrationContext.configure(
        conn, opts={"compare_type": True, "render_as_batch": True}
    )
    diffs = [d for d in compare_metadata(ctx, Base.metadata) if "series_fts" not in repr(d)]
    return not diffs


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
