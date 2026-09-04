"""Alembic baseline guard (spec §3, §7).

The VPS slim-down wiped the database and collapsed ``alembic/versions/*`` to a
single baseline revision ``0001_source_native``. These tests pin that the
baseline upgrades an empty database to head with the full source-native schema
(every ORM table + the ``chapter_ocr_fts`` FTS5 virtual table and its triggers),
matches the ORM models exactly, and is idempotent.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine, inspect, text

import database.session as dbs
from database.models import Base
from database.session import run_alembic_migrations

_BASELINE = "0001_source_native"
_HEAD = "0006_reading_session_stats_index"

# Every revision, oldest first. A new migration is added here deliberately —
# the point of the guard is that revisions arrive on purpose, not that there is
# only ever one.
_REVISIONS = [
    "0001_source_native.py",
    "0002_tags_per_profile.py",
    "0003_bootstrap_state.py",
    "0004_source_browse_cache.py",
    "0005_single_admin_guard.py",
    "0006_reading_session_stats_index.py",
]

# Every ORM-mapped table the baseline must create (spec §3).
_EXPECTED_TABLES = {
    "users",
    "sessions",
    "bootstrap_state",
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
    "source_browse_cache",
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


def test_revision_set_is_exactly_what_we_expect():
    versions_dir = Path(dbs.__file__).resolve().parents[1] / "alembic" / "versions"
    revisions = sorted(p.name for p in versions_dir.glob("*.py"))
    assert revisions == _REVISIONS, revisions


def test_migrations_upgrade_empty_db_to_full_schema(tmp_path):
    engine = _fresh_engine(tmp_path)
    tables = set(inspect(engine).get_table_names())

    missing = _EXPECTED_TABLES - tables
    assert not missing, f"baseline did not create: {missing}"

    leftover = _DELETED_TABLES & tables
    assert not leftover, f"baseline created deleted tables: {leftover}"

    # Alembic stamped a real head revision.
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == _HEAD


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


def test_create_all_also_builds_a_working_fts_index(db_engine):
    """The other schema path: ``Base.metadata.create_all`` (every test DB, any
    create_all bootstrap) must produce the same working ``chapter_ocr_fts`` index
    the Alembic baseline does — via the ``after_create`` hook in database.models.
    """
    with db_engine.connect() as conn:
        objects = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type IN ('table', 'trigger')"
                )
            )
        }
    assert "chapter_ocr_fts" in objects
    assert {
        "chapter_ocr_fts_ai",
        "chapter_ocr_fts_ad",
        "chapter_ocr_fts_au",
    } <= objects

    with db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO chapter_ocr "
                "(source_id, series_key, chapter_key, full_text, engine, "
                " word_count, created_at, updated_at) "
                "VALUES ('mangadex', 's1', 'c1', 'the phantom knight returned', "
                " 'test', 4, '2026-01-01', '2026-01-01')"
            )
        )
    with db_engine.connect() as conn:
        hit = conn.execute(
            text(
                "SELECT c.chapter_key FROM chapter_ocr_fts f "
                "JOIN chapter_ocr c ON c.id = f.rowid "
                "WHERE chapter_ocr_fts MATCH 'phantom'"
            )
        ).all()
    assert [r[0] for r in hit] == ["c1"]


def test_create_all_fts_hook_is_idempotent(db_engine):
    """A second ``create_all`` on the same engine must not fail on the FTS DDL."""
    from database.models import Base

    Base.metadata.create_all(bind=db_engine)  # would raise without IF NOT EXISTS


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


def test_run_alembic_migrations_does_not_silence_existing_loggers(tmp_path, caplog):
    """Regression test: ``alembic/env.py`` used to call ``fileConfig(...)``
    unconditionally at import time, even when Alembic is driven
    programmatically from app startup (``database.session.run_alembic_migrations``,
    which ``init_db()`` calls). ``fileConfig``'s default
    ``disable_existing_loggers=True`` silently disables every logger that
    already exists in the process at that point — including every
    module-level ``logging.getLogger(__name__)`` logger the app's own modules
    already created at import time — so from that point on the running
    backend emitted zero log lines (no request errors, no update-sweep
    failures, no security warnings). This was invisible precisely because
    nothing tested it.

    Reproduces the real app-boot ordering: obtain a logger the way every
    backend module does, *before* triggering migrations, then confirm it
    still emits and reaches a handler afterward.
    """
    app_logger_name = "app.some_already_imported_module"
    app_logger = logging.getLogger(app_logger_name)
    assert not app_logger.disabled  # sanity: default state before migrating

    engine = create_engine(f"sqlite:///{tmp_path / 'logging.db'}")
    run_alembic_migrations(engine)

    assert not app_logger.disabled, (
        "run_alembic_migrations() disabled a pre-existing logger — "
        "alembic/env.py's fileConfig() call is killing app logging again"
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=app_logger_name):
        app_logger.warning("post-migration warning: this must be visible")
    assert any(
        "post-migration warning" in record.message for record in caplog.records
    ), "logger survived but no record reached the handler — logging is still broken"


def test_run_alembic_migrations_is_idempotent(tmp_path):
    engine = _fresh_engine(tmp_path)
    with engine.connect() as conn:
        rev1 = MigrationContext.configure(conn).get_current_revision()
    run_alembic_migrations(engine)  # second run: no-op at head
    with engine.connect() as conn:
        rev2 = MigrationContext.configure(conn).get_current_revision()
    assert rev1 == rev2 == _HEAD


# --- 0002_tags_per_profile ------------------------------------------------


def _upgrade_to(engine, revision: str) -> None:
    """Upgrade ``engine``'s database to a specific revision (not just head)."""
    from alembic import command
    from alembic.config import Config

    backend_root = Path(dbs.__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.attributes["db_url"] = engine.url.render_as_string(hide_password=False)
    command.upgrade(cfg, revision)


def _seed_legacy_tag_world(engine) -> None:
    """Two accounts, three profiles, and the old *global* tag vocabulary."""
    with engine.begin() as conn:
        for uid, name in ((1, "alice"), (2, "bob")):
            conn.execute(
                text(
                    "INSERT INTO users (id, username, password_hash, is_admin,"
                    " is_active, created_at, updated_at) VALUES"
                    " (:id, :n, 'x', 0, 1, '2026-01-01', '2026-01-01')"
                ),
                {"id": uid, "n": name},
            )
        for pid, uid, name in ((10, 1, "A"), (11, 1, "B"), (20, 2, "C")):
            conn.execute(
                text(
                    "INSERT INTO reading_profiles (id, user_id, name,"
                    " avatar_key, mood, mature_content_enabled, sort_order,"
                    " created_at) VALUES (:p, :u, :n, 'a', 'calm', 0, 0,"
                    " '2026-01-01')"
                ),
                {"p": pid, "u": uid, "n": name},
            )
        for tid, name in ((1, "Peak"), (2, "Dropped"), (3, "Orphan")):
            conn.execute(
                text(
                    "INSERT INTO tags (id, name, category, color, created_at)"
                    " VALUES (:t, :n, 'custom', '#fff', '2026-01-01')"
                ),
                {"t": tid, "n": name},
            )
        # "Peak" is used by profile A (acct 1) and profile C (acct 2);
        # "Dropped" only by profile B; "Orphan" by nobody.
        for uid, pid, tid, series in (
            (1, 10, 1, "s-a"),
            (2, 20, 1, "s-c"),
            (1, 11, 2, "s-b"),
        ):
            conn.execute(
                text(
                    "INSERT INTO profile_series_tags (user_id, profile_id,"
                    " source_id, series_key, tag_id, is_ai_generated)"
                    " VALUES (:u, :p, 'mangadex', :s, :t, 0)"
                ),
                {"u": uid, "p": pid, "t": tid, "s": series},
            )


def test_tags_migration_splits_a_shared_tag_per_profile(tmp_path):
    """The shared "Peak" row becomes one owned tag per profile that used it,
    and every association follows its own copy."""
    engine = create_engine(f"sqlite:///{tmp_path / 'tags.db'}")
    _upgrade_to(engine, _BASELINE)
    _seed_legacy_tag_world(engine)
    _upgrade_to(engine, "head")

    with engine.connect() as conn:
        tags = {
            (r[1], r[2], r[3]): r[0]
            for r in conn.execute(
                text("SELECT id, user_id, profile_id, name FROM tags")
            )
        }
        # "Peak" split in two; "Dropped" kept its single owner.
        assert set(tags) == {
            (1, 10, "Peak"),
            (2, 20, "Peak"),
            (1, 11, "Dropped"),
        }
        # ...and "Orphan" — used by nobody, owner unrecoverable — is gone.
        assert not any(name == "Orphan" for (_u, _p, name) in tags)

        links = {
            (r[0], r[1], r[2]): r[3]
            for r in conn.execute(
                text(
                    "SELECT user_id, profile_id, series_key, tag_id"
                    " FROM profile_series_tags"
                )
            )
        }
        assert links[(1, 10, "s-a")] == tags[(1, 10, "Peak")]
        assert links[(2, 20, "s-c")] == tags[(2, 20, "Peak")]
        assert links[(1, 11, "s-b")] == tags[(1, 11, "Dropped")]

        # Scope-local uniqueness replaced the global UNIQUE(name): two
        # profiles may now both own a tag called "Peak" (proved above), and a
        # single profile still may not own two.
        cols = {
            r[1] for r in conn.execute(text("PRAGMA table_info(tags)"))
        }
        assert {"user_id", "profile_id"} <= cols
