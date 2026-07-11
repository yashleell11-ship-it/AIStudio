"""Alembic adoption + drift guards.

These lock in the invariants established when Alembic became the schema
authority: the head revision must match the ORM models exactly (no forgotten
migration), a fresh database builds from the baseline, and an existing
pre-Alembic database is adopted at the baseline without losing data.
"""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from database.models import Base, Library, Series
from database.session import run_alembic_migrations


def _pending_changes(engine):
    """Schema differences between the live DB and the ORM models."""
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"compare_type": True, "render_as_batch": True}
        )
        return compare_metadata(ctx, Base.metadata)


def test_alembic_head_matches_models(tmp_path):
    """`alembic upgrade head` must reproduce the models exactly.

    If a model changes without a matching revision, autogenerate reports a
    non-empty diff — this test fails, forcing a migration to be written.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'head.db'}")
    run_alembic_migrations(engine)  # fresh DB → runs every revision to head
    diffs = _pending_changes(engine)
    assert diffs == [], f"ORM models have drifted from Alembic migrations: {diffs}"


def test_fresh_database_builds_full_schema(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    run_alembic_migrations(engine)
    from sqlalchemy import inspect

    tables = set(inspect(engine).get_table_names())
    assert {"users", "sessions", "series", "chapters", "alembic_version"} <= tables
    # version table is at a real head revision
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() is not None


def test_preexisting_database_adopted_without_data_loss(tmp_path):
    """A pre-Alembic DB (built by create_all, no version) keeps its rows and is
    stamped at the baseline rather than having its tables re-created."""
    db_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(db_url)
    # Simulate the OLD boot path: create_all only, no alembic_version.
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        lib = Library(name="Main", root_path="/tmp/lib")
        db.add(lib)
        db.flush()
        db.add(
            Series(
                library_id=lib.id,
                title="Solo Leveling",
                folder_path="/tmp/lib/solo",
                sort_title="solo leveling",
                is_favorite=True,
                read_chapters=42,
            )
        )
        db.commit()

    # Precondition: not yet under Alembic.
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() is None

    run_alembic_migrations(engine)

    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() is not None
    with Session(engine) as db:
        rows = db.query(Series).all()
        assert len(rows) == 1
        assert rows[0].title == "Solo Leveling"
        assert bool(rows[0].is_favorite) is True
        assert rows[0].read_chapters == 42


def test_run_alembic_migrations_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    run_alembic_migrations(engine)
    with engine.connect() as conn:
        rev1 = MigrationContext.configure(conn).get_current_revision()
    run_alembic_migrations(engine)  # second run: no-op at head
    with engine.connect() as conn:
        rev2 = MigrationContext.configure(conn).get_current_revision()
    assert rev1 == rev2
