"""Filesystem-level staging for database restore.

This module must stay import-light (stdlib + ``core.config`` only, no
SQLAlchemy) because :func:`apply_pending_restore_if_present` runs at the very
top of ``main.py`` -- before any other backend module is imported -- so a
staged restore can replace the database file on disk before
``database.session`` ever opens (and process-lifetime caches, via
``@lru_cache``) a connection to it. Swapping the file underneath an
already-open SQLAlchemy engine is not safe, so restores are staged now and
applied only the next time the process starts.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from core.config import get_settings

_PENDING_SUFFIX = ".pending-restore"


def pending_restore_path() -> Path:
    """Where a staged restore file waits until the next process start."""
    return Path(f"{get_settings().db_path}{_PENDING_SUFFIX}")


def has_pending_restore() -> bool:
    return pending_restore_path().exists()


def apply_pending_restore_if_present() -> bool:
    """If a restore was staged, swap it in for the live database file.

    Must run before anything opens the database (see module docstring).
    Also removes any stale WAL/SHM sidecar files left by the *old* database
    so SQLite never tries to replay old WAL frames against the restored
    file. Returns ``True`` if a restore was applied.
    """
    pending = pending_restore_path()
    if not pending.exists():
        return False

    db_path = Path(get_settings().db_path)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pending), str(db_path))
    return True
