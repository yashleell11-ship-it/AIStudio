"""AUDIT (shard: backups) -- restore safety of the admin backup import path.

These are the reproductions for two gaps that were found (and since closed)
in ``services.backup_service`` / ``core.backup_restore``:

1. ``_validate_backup_file`` only listed ``sqlite_master`` (page 1). A backup
   whose interior data pages were corrupt passed validation and got staged.
   It now runs ``integrity_check`` / ``foreign_key_check`` on the upload.
2. ``apply_pending_restore_if_present`` replaced the live database file with
   the staged one and kept NO copy of the file it overwrote, so a bad restore
   (corrupt upload, wrong instance, older snapshot) was unrecoverable from the
   box itself. It now keeps the displaced file beside the database.

Fixture layout mirrors tests/test_backup_restore.py so the real database can
never be touched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import core.backup_restore as backup_restore
import services.backup_service as backup_service
from core.errors import AppError

_REQUIRED_TABLES = ("users", "followed_series", "chapter_progress", "alembic_version")


def _make_db(path: Path, *, marker: str) -> None:
    conn = sqlite3.connect(str(path))
    try:
        for table in _REQUIRED_TABLES:
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.execute("INSERT INTO users (id, username) VALUES (1, ?)", (marker,))
        # Enough payload to spill onto several pages beyond sqlite_master.
        conn.execute("CREATE TABLE payload (id INTEGER PRIMARY KEY, blob BLOB)")
        conn.executemany(
            "INSERT INTO payload (blob) VALUES (?)", [(b"x" * 3000,) for _ in range(40)]
        )
        conn.commit()
    finally:
        conn.close()


def _corrupt_interior_page(path: Path) -> None:
    """Zero the b-tree page-type byte of page 4 -- page 1 (sqlite_master) and
    the header page count stay intact, so the file still *opens* and *lists*
    tables, but PRAGMA quick_check reports corruption."""
    page_size = 4096
    data = bytearray(path.read_bytes())
    assert len(data) > page_size * 5, "fixture db too small to corrupt safely"
    data[page_size * 3] = 0x00  # first byte of page 4: invalid b-tree page type
    path.write_bytes(bytes(data))


@pytest.fixture
def live_db(tmp_path: Path) -> Path:
    path = tmp_path / "live.db"
    _make_db(path, marker="live-owner")
    return path


@pytest.fixture(autouse=True)
def _patch_settings(live_db: Path, monkeypatch: pytest.MonkeyPatch):
    from core.config import get_settings

    patched = get_settings().model_copy(update={"db_path": str(live_db)})
    monkeypatch.setattr(backup_service, "get_settings", lambda: patched)
    monkeypatch.setattr(backup_restore, "get_settings", lambda: patched)
    yield
    Path(f"{live_db}.pending-restore").unlink(missing_ok=True)


def test_validation_rejects_a_backup_with_corrupt_data_pages(tmp_path: Path):
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded")
    _corrupt_interior_page(upload)

    # Precondition: the file still opens and lists its tables (which is why
    # listing sqlite_master never caught this), yet SQLite can see the damage.
    # Depending on the SQLite build a shredded page is reported as a non-"ok"
    # verdict or by refusing the page outright; both count.
    conn = sqlite3.connect(str(upload))
    try:
        assert conn.execute("SELECT name FROM sqlite_master").fetchall()
        try:
            verdict = conn.execute("PRAGMA quick_check").fetchone()[0]
        except sqlite3.DatabaseError:
            verdict = "malformed"
        assert verdict != "ok"
    finally:
        conn.close()

    # Expected: a corrupt file must not be staged. Actual: it is.
    with pytest.raises(AppError):
        backup_service.stage_restore(upload)


def test_apply_restore_keeps_a_copy_of_the_database_it_overwrites(
    tmp_path: Path, live_db: Path
):
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded")
    backup_service.stage_restore(upload)

    assert backup_restore.apply_pending_restore_if_present() is True

    # Expected: the pre-restore file survives somewhere next to the db so an
    # operator can undo a bad restore. Actual: only the restored file exists.
    survivors = [
        p for p in live_db.parent.iterdir()
        if p.name.startswith(live_db.name) and p != live_db
    ]
    assert survivors, (
        f"no pre-restore copy left in {live_db.parent}: {sorted(p.name for p in live_db.parent.iterdir())}"
    )
    # And it is the *old* database, intact, not some empty placeholder.
    conn = sqlite3.connect(str(survivors[0]))
    try:
        assert conn.execute("SELECT username FROM users WHERE id = 1").fetchone() == ("live-owner",)
    finally:
        conn.close()
