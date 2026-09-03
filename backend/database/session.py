from __future__ import annotations

import logging
from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings

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
        # Writer-vs-writer wait budget, made explicit. pysqlite's default
        # connect timeout already implies ~5s, but the bootstrap-claim
        # transaction (AuthService.register: BEGIN IMMEDIATE) and the update
        # sweep both take SQLite's single write lock, so pin the wait here
        # where the other pragmas live rather than relying on a driver
        # default. WAL keeps readers unaffected; contending writers queue for
        # up to this long instead of failing instantly with SQLITE_BUSY.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


SessionLocal = sessionmaker(
    bind=get_engine(),
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    """Bring a fresh database to the current schema.

    The VPS slim-down wiped the database and reset the Alembic history to the
    single ``0001_source_native`` baseline, so there is no pre-Alembic schema to
    adopt or stamp any more — just run the migrations.
    """
    run_alembic_migrations(get_engine())


def run_alembic_migrations(engine: Engine) -> None:
    """Upgrade the database to the latest Alembic revision (``head``).

    Fresh database → the baseline creates the full schema. Already-tracked
    database → outstanding revisions apply (no-op at head).
    """
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    # Absolute path so migrations resolve regardless of the process CWD.
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    # Point Alembic at this very database (env.py reads this override).
    cfg.attributes["db_url"] = engine.url.render_as_string(hide_password=False)
    command.upgrade(cfg, "head")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
