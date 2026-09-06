"""Alembic environment.

Schema authority for the backend. The app's ``Base.metadata`` is the target;
SQLite requires batch (``render_as_batch``) so column/constraint changes use the
copy-and-swap that plain ``ALTER TABLE`` can't do. The database URL is resolved
from the running app's settings (``MM_DB_PATH``/``config/settings.json``) so the
CLI and the programmatic startup path migrate the very same file — never the
placeholder in alembic.ini.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import datetime
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, event, make_url, pool
from sqlalchemy.engine import Engine

from alembic import context

# backend/alembic/env.py -> backend/ on the path so app modules import.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None and not config.attributes.get("db_url"):
    # Only load alembic.ini's logging config when Alembic is driven from its
    # own CLI (no ``db_url`` attribute -- see ``_resolve_url`` above). The
    # programmatic path (``database.session.run_alembic_migrations``, called
    # at app boot) always sets ``config.attributes["db_url"]``; running
    # ``fileConfig`` there would tear down every logger already configured by
    # the app (``disable_existing_loggers`` defaults to True), silencing all
    # backend logging from that point on. Even on the CLI path, pass
    # ``disable_existing_loggers=False`` so this can't clobber loggers set up
    # by modules already imported above (e.g. ``database.models``).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

log = logging.getLogger("alembic.env")

# Databases copied aside just before a boot that has revisions to apply. The
# nightly VACUUM INTO backup (``ops/vps/backup-db.sh``) is the real safety net,
# so these only have to cover the minutes around one upgrade -- a couple of
# copies, next to the database, on a box with ~20GB of disk.
_SNAPSHOT_PREFIX = ".pre-migration-"
_SNAPSHOT_RETAIN = 2

# FTS5 virtual tables built by raw DDL in the migrations. SQLAlchemy has no
# FTS5 construct, so these can never appear in ``Base.metadata``, and each one
# drags shadow tables (``_data``, ``_idx``, ``_docsize``, ``_config``,
# ``_content``) that SQLite maintains on its behalf.
_FTS_TABLES = ("chapter_ocr_fts",)


def _include_name(
    name: str | None,
    type_: str,
    parent_names: dict,  # noqa: ARG001
) -> bool:
    """Hide the FTS5 index and its shadow tables from autogenerate.

    Autogenerate diffs the reflected database against ``Base.metadata`` and
    proposes dropping whatever it finds only in the database. ``chapter_ocr_fts``
    and its four shadow tables are exactly that, so without this filter a plain
    ``alembic revision --autogenerate`` writes a revision whose ``upgrade()``
    drops the OCR search index — and whoever applies the suggestion loses it.
    Names the metadata does declare are never filtered, so a future real table
    that happens to sit under one of these prefixes still diffs normally.
    """
    if type_ != "table" or name is None or name in target_metadata.tables:
        return True
    return not any(name == fts or name.startswith(f"{fts}_") for fts in _FTS_TABLES)


def _install_transactional_ddl(engine: Engine) -> None:
    """Make a revision's DDL roll back with the rest of that revision.

    Alembic already runs each revision inside a SQLAlchemy transaction, but on
    SQLite that transaction does not cover DDL: pysqlite in its legacy mode
    emits ``BEGIN`` only ahead of DML, so a table-rebuild revision's ``CREATE
    TABLE <x>_new`` is committed the instant it runs. A crash before the
    rebuild's final RENAME then leaves the scratch table behind with
    ``alembic_version`` unmoved, and every boot after that dies on "table
    <x>_new already exists" -- on a box where this file is the only copy of
    everything. SQLAlchemy's documented pysqlite recipe: take the driver out of
    the transaction business and emit ``BEGIN`` ourselves, so DDL lands inside
    the transaction alembic opened for the revision.
    """

    @event.listens_for(engine, "connect")
    def _no_implicit_begin(dbapi_connection, connection_record):  # noqa: ARG001
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _explicit_begin(connection):
        connection.exec_driver_sql("BEGIN")


def _sqlite_file(url: str) -> Path | None:
    """The file behind a SQLite URL; ``None`` for in-memory or another backend."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return None
    if not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def _has_outstanding_revisions() -> bool:
    """Does this run have anything left to apply?

    An untracked file is a fresh install whose baseline builds the schema out
    of nothing, so there is no prior state worth copying aside.
    """
    try:
        revision_argument = context.get_revision_argument()
    except KeyError:
        # ``revision --autogenerate``, ``check`` and ``stamp`` run env.py too
        # but name no destination revision (alembic raises straight out of
        # ``context_opts``). They apply nothing, so there is nothing to copy
        # aside — and no reason to log a failure for it.
        return False
    current = set(context.get_context().get_current_heads())
    if not current:
        return False
    destination = {
        script.revision for script in context.script.get_revisions(revision_argument)
    }
    return current != destination


def _snapshot_database(db_path: Path) -> None:
    """Copy the database aside before the first revision touches it."""
    # Microseconds, not seconds: the stamp has to be unique and keep sorting
    # chronologically, or the prune below drops a copy at random.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = db_path.parent / f"{db_path.name}{_SNAPSHOT_PREFIX}{stamp}.db"
    # VACUUM INTO over a read-only connection rather than a file copy: the
    # database runs in WAL mode, where the main file on its own is missing
    # everything committed since the last checkpoint (ops/vps/backup-db.sh).
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        source.execute("VACUUM INTO ?", (str(dest),))
    except Exception:
        # A half-written copy is worse than none: it would count towards the
        # retention below and push a good one out.
        dest.unlink(missing_ok=True)
        raise
    finally:
        source.close()
    log.info("pre-migration snapshot written: %s", dest)

    prefix = f"{db_path.name}{_SNAPSHOT_PREFIX}"
    existing = sorted(
        (
            path
            for path in db_path.parent.iterdir()
            if path.name.startswith(prefix) and path.name.endswith(".db")
        ),
        reverse=True,
    )
    for stale in existing[_SNAPSHOT_RETAIN:]:
        stale.unlink(missing_ok=True)


def _snapshot_before_migrating(connection, url: str) -> None:
    """Snapshot the database, but only when a revision is about to run."""
    db_path = _sqlite_file(url)
    if db_path is None or not db_path.exists():
        return
    try:
        if not _has_outstanding_revisions():
            return
        # Reading the version table autobegan a transaction; end it so the
        # snapshot reads the same committed state the revisions will start from.
        connection.rollback()
        _snapshot_database(db_path)
    except Exception:
        # Insurance must never be the reason the service fails to start.
        log.warning("pre-migration snapshot skipped", exc_info=True)


def _resolve_url() -> str:
    """The database URL to migrate: explicit override, else app settings."""
    # Programmatic callers (startup) or `alembic -x db_url=...` win.
    override = config.attributes.get("db_url") or context.get_x_argument(
        as_dictionary=True
    ).get("db_url")
    if override:
        return override
    from core.config import get_settings

    return f"sqlite:///{get_settings().db_path}"


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
        include_name=_include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # If a caller supplied a live connection (startup integration), use it;
    # otherwise build a short-lived engine from the resolved URL.
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            include_name=_include_name,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    url = _resolve_url()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    _install_transactional_ddl(connectable)
    with connectable.connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            include_name=_include_name,
        )
        _snapshot_before_migrating(conn, url)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
