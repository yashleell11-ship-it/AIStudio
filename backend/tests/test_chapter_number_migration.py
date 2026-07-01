from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from database.session import _migrate_chapter_number_to_float


def _create_legacy_schema(engine) -> None:
    """Build a pre-fix schema where chapters.number is INTEGER, mirroring
    a real production database created before this migration existed."""
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(
            text(
                """
                CREATE TABLE series (
                    id INTEGER PRIMARY KEY,
                    library_id INTEGER NOT NULL,
                    title VARCHAR(512) NOT NULL,
                    folder_path VARCHAR(1024) NOT NULL
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
                    title VARCHAR(255),
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
                    series_id INTEGER NOT NULL REFERENCES series(id),
                    volume_id INTEGER REFERENCES volumes(id),
                    title VARCHAR(512) NOT NULL,
                    number INTEGER,
                    folder_path VARCHAR(1024),
                    archive_path VARCHAR(1024),
                    page_count INTEGER DEFAULT 0,
                    cover_path VARCHAR(1024),
                    sort_key VARCHAR(32) NOT NULL DEFAULT '',
                    is_read INTEGER NOT NULL DEFAULT 0,
                    read_at DATETIME,
                    updated_at DATETIME,
                    created_at DATETIME,
                    scanned_at DATETIME
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_chapters_series_id ON chapters (series_id)"))
        conn.execute(
            text("CREATE UNIQUE INDEX uq_chapter_series_folder ON chapters (series_id, folder_path)")
        )
        conn.execute(
            text(
                "INSERT INTO series (id, library_id, title, folder_path) "
                "VALUES (1, 1, 'Solo Leveling', '/library/solo-leveling')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO chapters
                    (id, series_id, title, number, folder_path, sort_key, created_at, updated_at)
                VALUES
                    (1, 1, 'Chapter 1', 1, '/library/solo-leveling/ch1', '0001.000', '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
                    (2, 1, 'Chapter 2', 2, '/library/solo-leveling/ch2', '0002.000', '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
                    (3, 1, 'Chapter 3 (no folder)', 3, NULL, '0003.000', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
                """
            )
        )
        conn.execute(text("PRAGMA foreign_keys=ON"))


def test_migration_widens_integer_column_to_real(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_legacy_schema(engine)

    inspector = inspect(engine)
    before = next(c for c in inspector.get_columns("chapters") if c["name"] == "number")
    assert "INT" in str(before["type"]).upper()

    _migrate_chapter_number_to_float(engine)

    inspector = inspect(engine)
    after = next(c for c in inspector.get_columns("chapters") if c["name"] == "number")
    assert "INT" not in str(after["type"]).upper()


def test_migration_preserves_existing_rows(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_legacy_schema(engine)

    _migrate_chapter_number_to_float(engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, series_id, title, number, folder_path FROM chapters ORDER BY id")
        ).fetchall()

    assert len(rows) == 3
    assert rows[0] == (1, 1, "Chapter 1", 1.0, "/library/solo-leveling/ch1")
    assert rows[1] == (2, 1, "Chapter 2", 2.0, "/library/solo-leveling/ch2")
    assert rows[2] == (3, 1, "Chapter 3 (no folder)", 3.0, None)


def test_migration_recreates_indexes(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_legacy_schema(engine)

    _migrate_chapter_number_to_float(engine)

    inspector = inspect(engine)
    index_names = {idx["name"] for idx in inspector.get_indexes("chapters")}
    assert "ix_chapters_series_id" in index_names
    assert "ix_chapters_folder_path" in index_names
    assert "ix_chapters_series_sort" in index_names


def test_migration_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_legacy_schema(engine)

    _migrate_chapter_number_to_float(engine)
    # Second call must be a no-op, not an error, since the column is
    # already REAL.
    _migrate_chapter_number_to_float(engine)

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM chapters")).scalar()
    assert count == 3


def test_migration_accepts_decimal_values_after_running(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _create_legacy_schema(engine)

    _migrate_chapter_number_to_float(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO chapters "
                "(id, series_id, title, number, sort_key, page_count, is_read, created_at, updated_at) "
                "VALUES "
                "(4, 1, 'Chapter 13.5', 13.5, '0013.500', 0, 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )

    with engine.connect() as conn:
        value = conn.execute(
            text("SELECT number FROM chapters WHERE id = 4")
        ).scalar()
    assert value == 13.5


def test_migration_is_noop_on_fresh_database(tmp_path: Path):
    """No 'chapters' table yet — nothing to migrate; must not raise."""
    db_path = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _migrate_chapter_number_to_float(engine)  # should not raise
