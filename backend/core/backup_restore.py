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

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from core.config import get_settings

_PENDING_SUFFIX = ".pending-restore"
# A staged file this build refuses is set aside under this name rather than
# deleted (the operator needs the bytes to see what went wrong) and rather
# than left in place (that would report "restore pending" forever while every
# boot refused it again).
_REJECTED_SUFFIX = ".rejected"
# The database a restore replaces is kept beside it under this name, so a
# wrong upload can be undone from the box itself.
_REPLACED_INFIX = ".pre-restore-"
# Each retained copy is a whole database. Three is enough to undo a restore
# and the restore that "fixed" it, without letting repeated restores fill the
# volume the live database needs.
_KEEP_REPLACED = 3

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def pending_restore_path() -> Path:
    """Where a staged restore file waits until the next process start."""
    return Path(f"{get_settings().db_path}{_PENDING_SUFFIX}")


def has_pending_restore() -> bool:
    return pending_restore_path().exists()


def retained_copy_hint() -> str:
    """How the replaced database will be named, for messages to the operator."""
    db_name = Path(get_settings().db_path).name
    return f"{db_name}{_REPLACED_INFIX}<timestamp> (newest {_KEEP_REPLACED} kept)"


def read_only_uri(path: Path) -> str:
    """A SQLite URI that opens ``path`` read-only.

    Inspecting a file must never be able to change it: a plain ``connect()``
    may recover a journal or checkpoint a WAL on the way in, and the files
    inspected here are either someone's upload or the one thing that must
    stay pristine, the pending restore.
    """
    return f"{path.resolve().as_uri()}?mode=ro"


def recorded_alembic_revision(path: Path) -> str | None:
    """The schema revision a database file is stamped with.

    ``None`` when the file records none, in which case there is nothing to
    compare and the migration runner decides what to do with it, as before.
    """
    try:
        connection = sqlite3.connect(read_only_uri(path), uri=True)
        try:
            row = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def unreadable_problem(path: Path) -> str | None:
    """Why ``path`` cannot be read as a database, or ``None`` if it can.

    ``services.backup_service`` runs the deep ``integrity_check`` when the
    file is uploaded; this is the cheap re-check at the one moment that
    cannot be taken back. The upload is not the last thing that can go wrong
    with a staged file: it can be staged by an older build that never
    validated it, hand-placed on the box, or damaged on disk between the
    upload and the reboot. ``quick_check`` is page-level and finishes in
    milliseconds, which is what a boot path can afford.
    """
    try:
        connection = sqlite3.connect(read_only_uri(path), uri=True)
        try:
            verdict = connection.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            connection.close()
    except (sqlite3.Error, IndexError, TypeError) as exc:
        return f"SQLite cannot read it ({exc})"
    if verdict != "ok":
        return f"SQLite reports it damaged (quick_check: {verdict})"
    return None


def unknown_revision_problem(path: Path) -> str | None:
    """Why ``path`` must not become the live database, or ``None`` if its
    schema revision is one this build has a migration script for.

    A backup taken on a newer build is stamped with a revision this code does
    not know. Alembic would only discover that at startup, after the swap,
    with the previous database already gone -- a crash loop with no way back.
    The known set is read from the Alembic script directory rather than
    listed here, so it can never drift from the migrations actually shipped.
    """
    revision = recorded_alembic_revision(path)
    if revision is None:
        return None

    # Imported lazily: alembic pulls in SQLAlchemy, which this module keeps off
    # its import path (see module docstring). Walking the version scripts
    # never loads ``alembic/env.py`` or ``database.session``, so this is safe
    # at the top of ``main.py``, and it only runs when a restore is actually
    # staged or uploaded.
    from alembic.script import ScriptDirectory

    script = ScriptDirectory(str(_BACKEND_ROOT / "alembic"))
    known = {entry.revision for entry in script.walk_revisions()}
    if revision in known:
        return None
    newest = ", ".join(sorted(script.get_heads()))
    return (
        f"its schema revision {revision!r} is unknown to this build (newest "
        f"known: {newest}), so it was most likely taken from a newer build; "
        "update the server first, then restore it"
    )


def _fresh_retained_path(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = Path(f"{db_path}{_REPLACED_INFIX}{stamp}")
    # Two restores inside one second (a fast undo) must not clobber each other.
    serial = 1
    while candidate.exists():
        candidate = Path(f"{db_path}{_REPLACED_INFIX}{stamp}-{serial}")
        serial += 1
    return candidate


def _retain_replaced_database(db_path: Path) -> Path | None:
    """Move the live database aside under a timestamped name.

    Renames rather than copies: same directory, so it is atomic and costs no
    extra space at the one moment the volume must have room for both files.
    The WAL goes with it because in WAL mode the main file alone is stale --
    everything committed since the last checkpoint lives only in the ``-wal``
    until SQLite next opens the pair. The ``-shm`` is a rebuildable index of
    that WAL and is dropped, so nothing stale is ever replayed against the
    restored file.
    """
    wal = Path(f"{db_path}-wal")
    Path(f"{db_path}-shm").unlink(missing_ok=True)
    if not db_path.exists():
        wal.unlink(missing_ok=True)
        return None

    retained = _fresh_retained_path(db_path)
    db_path.rename(retained)
    if wal.exists():
        wal.rename(Path(f"{retained}-wal"))
    _fold_wal_into(retained)
    return retained


def _fold_wal_into(retained: Path) -> None:
    """Best effort: checkpoint the retained copy into one self-contained file.

    An operator undoing a restore will reach for the ``.pre-restore-*`` file
    alone; a companion ``-wal`` is easy to forget and losing it silently
    drops the last commits. If SQLite cannot checkpoint (the old database was
    itself damaged) the pair is left as it is and replays on open.
    """
    try:
        connection = sqlite3.connect(str(retained))
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()
    except sqlite3.Error:
        pass


def _prune_retained_copies(db_path: Path) -> None:
    prefix = f"{db_path.name}{_REPLACED_INFIX}"
    # Timestamped names sort oldest-first.
    copies = sorted(
        entry
        for entry in db_path.parent.iterdir()
        if entry.name.startswith(prefix) and not entry.name.endswith(("-wal", "-shm"))
    )
    for stale in copies[:-_KEEP_REPLACED]:
        for victim in (stale, Path(f"{stale}-wal"), Path(f"{stale}-shm")):
            victim.unlink(missing_ok=True)


def apply_pending_restore_if_present() -> bool:
    """If a restore was staged, swap it in for the live database file.

    Must run before anything opens the database (see module docstring). The
    database being replaced is kept beside it as ``<db>.pre-restore-<stamp>``
    (the newest ``_KEEP_REPLACED`` survive) so a wrong restore can be undone;
    a staged file this build cannot read, or whose schema revision it cannot
    migrate, is set aside as ``<pending>.rejected`` and the live database left
    untouched. Returns ``True`` if a restore was applied.
    """
    pending = pending_restore_path()
    if not pending.exists():
        return False

    # WARNING rather than INFO: this runs before uvicorn configures logging,
    # and only warnings reach stderr (and so the container log) unconfigured.
    log = logging.getLogger("uvicorn.error")
    problem = unreadable_problem(pending) or unknown_revision_problem(pending)
    if problem is not None:
        rejected = Path(f"{pending}{_REJECTED_SUFFIX}")
        pending.replace(rejected)
        log.warning(
            "Refused the staged database restore and left the live database "
            "untouched: %s. The refused file was moved to %s.",
            problem,
            rejected,
        )
        return False

    db_path = Path(get_settings().db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    retained = _retain_replaced_database(db_path)
    shutil.move(str(pending), str(db_path))
    _prune_retained_copies(db_path)
    if retained is not None:
        log.warning(
            "Applied a staged database restore. The database it replaced is "
            "kept at %s (newest %d such copies are kept); stage that file to "
            "undo the restore.",
            retained,
            _KEEP_REPLACED,
        )
    return True
