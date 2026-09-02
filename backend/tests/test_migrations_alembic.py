"""Alembic baseline guard (spec §3, §7).

The VPS slim-down wiped the database and collapsed ``alembic/versions/*`` to a
single baseline revision ``0001_source_native``. These tests pin that the
baseline upgrades an empty database to head with the full source-native schema
(every ORM table + the ``chapter_ocr_fts`` FTS5 virtual table and its triggers),
matches the ORM models exactly, and is idempotent.
"""

from __future__ import annotations

from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine, inspect, text

import database.session as dbs
from database.models import Base
from database.session import run_alembic_migrations

_BASELINE = "0001_source_native"

# Every ORM-mapped table the baseline must create (spec §3).
_EXPECTED_TABLES = {
    "users",
    "sessions",
    "reading_profiles",
    "source_pins",
    "source_health",
    "update_settings",
    "update_runs",
    "followed_series",
    "chapter_progress",
    "bookmarks",
    "reading_sessions",
    "collections",
    "collection_series",
    "tags",
    "profile_series_tags",
    "update_notifications",
    "chapter_ocr",
    "source_series_cache",
}

# Tables that must be gone (spec §3.11).
_DELETED_TABLES = {
    "libraries",
    "series",
    "chapters",
    "volumes",
    "pages",
    "downloads",
    "download_queue",
    "source_chapter_links",
    "import_history",
    "series_trackers",
    "user_series_state",
    "ocr_jobs",
    "page_texts",
    "chapter_texts",
    "reading_progress",
    "series_fts",
}


def _fresh_engine(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'baseline.db'}")
    run_alembic_migrations(engine)
    return engine


def test_baseline_is_the_only_revision():
    versions_dir = Path(dbs.__file__).resolve().parents[1] / "alembic" / "versions"
    revisions = sorted(p.name for p in versions_dir.glob("*.py"))
    assert revisions == ["0001_source_native.py"], revisions


def test_baseline_upgrades_empty_db_to_full_schema(tmp_path):
    engine = _fresh_engine(tmp_path)
    tables = set(inspect(engine).get_table_names())

    missing = _EXPECTED_TABLES - tables
    assert not missing, f"baseline did not create: {missing}"

    leftover = _DELETED_TABLES & tables
    assert not leftover, f"baseline created deleted tables: {leftover}"

    # Alembic stamped a real head revision.
    with engine.connect() as conn:
        assert (
            MigrationContext.configure(conn).get_current_revision() == _BASELINE
        )


def test_baseline_creates_chapter_ocr_fts_and_triggers(tmp_path):
    engine = _fresh_engine(tmp_path)
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "chapter_ocr_fts" in tables
        triggers = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger'")
            )
        }
        assert {
            "chapter_ocr_fts_ai",
            "chapter_ocr_fts_ad",
            "chapter_ocr_fts_au",
        } <= triggers

    # The FTS index actually populates from a chapter_ocr insert.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO chapter_ocr "
                "(source_id, series_key, chapter_key, full_text, engine, word_count, "
                " created_at, updated_at) "
                "VALUES ('mangadex', 's1', 'c1', 'the dragon roared loudly', 'test', 4, "
                " '2026-01-01', '2026-01-01')"
            )
        )
    with engine.connect() as conn:
        hit = conn.execute(
            text(
                "SELECT c.chapter_key FROM chapter_ocr_fts f "
                "JOIN chapter_ocr c ON c.id = f.rowid "
                "WHERE chapter_ocr_fts MATCH 'dragon'"
            )
        ).all()
        assert [r[0] for r in hit] == ["c1"]


def test_alembic_head_matches_models(tmp_path):
    """``upgrade head`` must reproduce the ORM models exactly — a model change
    without a matching migration shows up here as a non-empty diff."""
    engine = _fresh_engine(tmp_path)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"compare_type": True, "render_as_batch": True}
        )
        diffs = compare_metadata(ctx, Base.metadata)
    # FTS virtual tables and their shadow tables are not ORM-mapped; Alembic
    # reports them as "extra". Everything else must match.
    real = [
        d
        for d in diffs
        if not (
            isinstance(d, tuple)
            and d[0] == "remove_table"
            and getattr(d[1], "name", "").startswith("chapter_ocr_fts")
        )
    ]
    assert real == [], f"ORM models drifted from the Alembic baseline: {real}"


def test_run_alembic_migrations_is_idempotent(tmp_path):
    engine = _fresh_engine(tmp_path)
    with engine.connect() as conn:
        rev1 = MigrationContext.configure(conn).get_current_revision()
    run_alembic_migrations(engine)  # second run: no-op at head
    with engine.connect() as conn:
        rev2 = MigrationContext.configure(conn).get_current_revision()
    assert rev1 == rev2 == _BASELINE
