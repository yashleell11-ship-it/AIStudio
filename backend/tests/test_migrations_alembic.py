"""Alembic adoption + drift guards.

These lock in the invariants established when Alembic became the schema
authority: the head revision must match the ORM models exactly (no forgotten
migration), a fresh database builds from the baseline, and an existing
pre-Alembic database is adopted at the baseline without losing data.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

import database.session as dbs
from database.models import Base, Library, Series
from database.session import run_alembic_migrations

_BACKEND_ROOT = Path(dbs.__file__).resolve().parents[1]
_BASELINE = "c2b7350c254a"


def _alembic_upgrade(url: str, revision: str) -> None:
    """Upgrade a specific database to an explicit revision (test helper)."""
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    cfg.attributes["db_url"] = url
    command.upgrade(cfg, revision)


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
    # Simulate a real pre-Alembic database: baseline-era schema (what the old
    # create_all produced before ownership existed), with the version table
    # stripped so run_alembic_migrations must adopt then upgrade it.
    _alembic_upgrade(db_url, _BASELINE)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))
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


def test_two_users_can_hold_state_for_same_series(tmp_path):
    """The ownership + profile migrations must relax the old single-column
    uniques so two users — and two profiles on one account — can each have
    progress/state for the same catalog series."""
    engine = create_engine(f"sqlite:///{tmp_path / 'share.db'}")
    run_alembic_migrations(engine)
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(
            text(
                "INSERT INTO series (id,library_id,title,folder_path,sort_title,"
                "content_rating,language,is_favorite,reading_status,total_chapters,"
                "read_chapters,total_pages,is_created,created_at,updated_at) VALUES "
                "(1,1,'S','/s','s','unknown','ko',0,'unread',0,0,0,0,'2026-01-01','2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO chapters (id,series_id,title,page_count,sort_key,is_read,"
                "created_at,updated_at) VALUES (1,1,'c',0,'0001',0,'2026-01-01','2026-01-01')"
            )
        )
        ins = text(
            "INSERT INTO reading_progress (user_id,profile_id,series_id,chapter_id,"
            "last_page,scroll_offset_px,progress_pct,started_at,last_read_at) VALUES "
            "(:u,:p,1,1,1,0,0.0,'2026-01-01','2026-01-01')"
        )
        conn.execute(ins, {"u": 1, "p": 1})
        conn.execute(ins, {"u": 2, "p": 2})  # different user, same series → allowed
        conn.execute(ins, {"u": 1, "p": 3})  # same user, different profile → allowed

    # But the same (user, profile, series) again is still rejected.
    with engine.begin() as conn:
        try:
            conn.execute(ins, {"u": 1, "p": 1})
            raised = False
        except Exception:
            raised = True
    assert raised, "duplicate (user, profile, series) should violate the composite unique"


def test_run_alembic_migrations_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    run_alembic_migrations(engine)
    with engine.connect() as conn:
        rev1 = MigrationContext.configure(conn).get_current_revision()
    run_alembic_migrations(engine)  # second run: no-op at head
    with engine.connect() as conn:
        rev2 = MigrationContext.configure(conn).get_current_revision()
    assert rev1 == rev2


def test_tracker_membership_backfill_rescues_stranded_auto_downloads(tmp_path):
    """f3b71d0c9e42's data step.

    Object-level read authorization requires the caller's account to have a
    claim on a series. Auto-downloads never recorded one: the update checker
    built its DownloadService with no owner, so the Download was (NULL, NULL)
    and the worker filed membership in the unowned bucket. Every chapter that
    arrived because the owner *followed* a series would otherwise be readable
    only via the unowned-bucket fallback, and would never reach their grid.

    The bridge is source_chapter_links, NOT series_trackers.local_series_id —
    nothing has ever written that column. A tracker with no user_id names no
    account and is left alone.
    """
    db_url = f"sqlite:///{tmp_path / 'membership.db'}"
    engine = create_engine(db_url)
    _alembic_upgrade(db_url, "e6d1c73f9a24")  # the revision before the backfill

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(
            text(
                "INSERT INTO libraries (id,name,root_path,scan_interval_minutes,"
                "created_at) VALUES (1,'Main','/lib',60,'2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO series (id,library_id,title,folder_path,sort_title,"
                "content_rating,language,is_favorite,reading_status,total_chapters,"
                "read_chapters,total_pages,is_created,created_at,updated_at) VALUES "
                "(1,1,'Followed','/lib/f','followed','unknown','ko',0,'unread',0,0,0,0,"
                "'2026-01-01','2026-01-01'),"
                "(2,1,'Unrelated','/lib/u','unrelated','unknown','ko',0,'unread',0,0,0,0,"
                "'2026-01-01','2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO chapters (id,series_id,title,page_count,sort_key,is_read,"
                "created_at,updated_at) VALUES "
                "(1,1,'c1',1,'0001',0,'2026-01-01','2026-01-01'),"
                "(2,2,'c1',1,'0001',0,'2026-01-01','2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO source_chapter_links "
                "(source,series_id,chapter_id,local_chapter_id,created_at) VALUES "
                "('mangadex','remote-1','rc-1',1,'2026-01-01'),"
                "('mangadex','remote-2','rc-1',2,'2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO series_trackers (user_id,profile_id,source,series_id,"
                "series_title,track_kind,enabled,notify,auto_download,"
                "known_chapter_ids,created_at,updated_at) VALUES "
                # follower with an account: rescued
                "(7,3,'mangadex','remote-1','Followed','followed',1,1,1,'[]',"
                " '2026-01-01','2026-01-01'),"
                # tracker naming no account: skipped, nothing to attribute it to
                "(NULL,NULL,'mangadex','remote-2','Unrelated','followed',1,1,1,'[]',"
                " '2026-01-01','2026-01-01')"
            )
        )

    run_alembic_migrations(engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT user_id, profile_id, series_id, in_library "
                "FROM user_series_state ORDER BY series_id"
            )
        ).all()
    assert rows == [(7, 3, 1, 1)]

    # Idempotent: a second pass must not duplicate the row.
    run_alembic_migrations(engine)
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT COUNT(*) FROM user_series_state")
        ).scalar() == 1


def test_tracker_maturity_backfill_stamps_existing_adult_source_follows(tmp_path):
    """a7c3e51b90d4's data step.

    Without it the 18+ gate would ship inert for every follow that already
    exists: a tracker created before the rating columns existed has NULL in both
    of them, and the owner would have to re-mark each one by hand. Trackers on a
    general-purpose source are deliberately left NULL — guessing "adult" there
    would hide follows he never asked to hide.
    """
    from connectors.registry import list_installed_connectors

    db_url = f"sqlite:///{tmp_path / 'backfill.db'}"
    engine = create_engine(db_url)
    _alembic_upgrade(db_url, "f1a9c46d2e70")  # the revision before the columns

    adult = next(
        d.source_type for d in list_installed_connectors(include_mature=True) if d.mature
    )
    safe = next(
        d.source_type
        for d in list_installed_connectors(include_mature=True)
        if not d.mature
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO series_trackers "
                "(source, series_id, series_title, track_kind, enabled, notify, "
                " auto_download, known_chapter_ids, created_at, updated_at) VALUES "
                "(:src, 's1', 'T', 'followed', 1, 1, 0, '[]', "
                " '2026-01-01', '2026-01-01')"
            ),
            [{"src": adult}, {"src": safe}],
        )

    run_alembic_migrations(engine)

    with engine.connect() as conn:
        rows = dict(
            conn.execute(
                text("SELECT source, content_rating FROM series_trackers")
            ).all()
        )
    assert rows[adult] == "mature"
    assert rows[safe] is None
