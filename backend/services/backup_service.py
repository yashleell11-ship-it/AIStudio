"""Backup export/import: safe, consistent SQLite snapshots.

Export uses SQLite's own ``VACUUM INTO`` to produce a single-file, fully
consistent snapshot regardless of WAL mode or concurrent readers/writers --
the standard, SQLite-native way to hot-backup a live database without
contending with the app's own connection pool.

Import never touches the live, already-open (and process-lifetime cached)
SQLAlchemy engine. Restoring a database file while connections are open
against the old one is unsafe, so an uploaded backup is only *validated* and
staged; :mod:`core.backup_restore` swaps it in the next time the process
starts, before anything opens the database.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from core.backup_restore import (
    has_pending_restore,
    pending_restore_path,
)
from core.config import get_settings
from core.errors import AppError

# Tables that must exist for an uploaded file to be considered a genuine
# ManhwaManiacs backup, rather than an arbitrary or corrupt SQLite file.
# Source-native schema (spec §3): the catalog tables are gone.
_REQUIRED_TABLES = {"users", "followed_series", "chapter_progress", "alembic_version"}


def backup_filename() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"manhwamaniacs-backup-{stamp}.db"


def create_backup_snapshot() -> Path:
    """Write a consistent, point-in-time snapshot to a fresh temp file.

    Uses a *separate* sqlite3 connection (not the app's SQLAlchemy engine),
    so this never contends with or blocks the live app's connection pool.
    ``VACUUM INTO`` also compacts the snapshot, so exports are never larger
    than the data actually requires.

    Caller owns the returned path's parent directory and is responsible for
    cleaning it up once the snapshot has been used (e.g. after streaming it
    as a download).
    """
    settings = get_settings()
    tmp_dir = Path(tempfile.mkdtemp(prefix="mm_backup_"))
    snapshot_path = tmp_dir / "backup.db"

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute("VACUUM INTO ?", (str(snapshot_path),))
    finally:
        connection.close()

    return snapshot_path


def _validate_backup_file(path: Path) -> None:
    """Raise ``AppError`` unless ``path`` is a real ManhwaManiacs SQLite backup.

    SQLite lazily validates a file's format on first real access rather than
    at ``connect()`` time, so both the connection and the query are wrapped
    together -- an arbitrary non-database file only fails once queried.
    """
    try:
        connection = sqlite3.connect(str(path))
        try:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise AppError(
            "That file isn't a valid SQLite database.",
            code="invalid_backup_file",
            status_code=422,
        ) from exc

    table_names = {row[0] for row in rows}
    missing = _REQUIRED_TABLES - table_names
    if missing:
        raise AppError(
            "That file doesn't look like a ManhwaManiacs backup "
            f"(missing tables: {', '.join(sorted(missing))}).",
            code="invalid_backup_file",
            status_code=422,
        )


def stage_restore(uploaded_path: Path) -> None:
    """Validate an uploaded backup file, then stage it for restore on next start.

    Raises ``AppError`` (and leaves nothing staged) if the file doesn't look
    like a genuine backup.
    """
    _validate_backup_file(uploaded_path)
    target = pending_restore_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(uploaded_path), str(target))


def restore_pending() -> bool:
    return has_pending_restore()


def clear_pending_restore() -> bool:
    """Cancel a staged restore. Returns ``True`` if one was actually cleared."""
    target = pending_restore_path()
    if not target.exists():
        return False
    target.unlink()
    return True
