"""Alembic environment.

Schema authority for the backend. The app's ``Base.metadata`` is the target;
SQLite requires batch (``render_as_batch``) so column/constraint changes use the
copy-and-swap that plain ``ALTER TABLE`` can't do. The database URL is resolved
from the running app's settings (``MM_DB_PATH``/``config/settings.json``) so the
CLI and the programmatic startup path migrate the very same file — never the
placeholder in alembic.ini.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# backend/alembic/env.py -> backend/ on the path so app modules import.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


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
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as conn:
        context.configure(
            connection=conn,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
