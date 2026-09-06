"""AUDIT (shard: backups) -- safety of the in-app export/import/restore path.

Four findings, one file, because they are one story: an admin uploads a file
and the box either survives it or does not.

- BK-2 the boot-time swap overwrote the live database and kept no copy.
- BK-3 validation only listed ``sqlite_master``, so a corrupt file staged.
- BK-4 a backup from a newer build staged fine and then crash-looped Alembic
  with the old database already gone.
- ADD-2 the export carried the four derived cache tables, which dominate it.
- BK-7 both spool files were built in the system temp dir, so the move into
  place crossed a filesystem and stopped being a rename.

These cover the edges around ``tests/test_backup_restore.py``: what happens to
the *displaced* database (including the frames its WAL had not checkpointed),
what a boot does with a staged file it cannot migrate, and whether an export
can still be imported after the cache rows are dropped out of it.

Fixture layout mirrors tests/test_backup_restore.py so the real production
database can never be touched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.backup_restore as backup_restore
import services.backup_service as backup_service
from core.errors import AppError, register_error_handlers

_REQUIRED_TABLES = ("users", "followed_series", "chapter_progress")
_CACHE_TABLES = (
    "source_series_cache",
    "novel_chapter_cache",
    "source_cover_cache",
    "source_browse_cache",
)


def _make_db(
    path: Path, *, marker: str, revision: str | None = "0001_source_native"
) -> None:
    """A file shaped like a real backup: the required tables, a stamped
    ``alembic_version``, the cache tables, and enough payload to spill well
    past page 1."""
    conn = sqlite3.connect(str(path))
    try:
        for table in _REQUIRED_TABLES:
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.execute("INSERT INTO users (id, username) VALUES (1, ?)", (marker,))
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        if revision is not None:
            conn.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
        for table in _CACHE_TABLES:
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, blob BLOB)")
            conn.executemany(
                f"INSERT INTO {table} (blob) VALUES (?)",
                [(b"c" * 3000,) for _ in range(20)],
            )
        conn.execute("CREATE TABLE payload (id INTEGER PRIMARY KEY, blob BLOB)")
        conn.executemany(
            "INSERT INTO payload (blob) VALUES (?)", [(b"x" * 3000,) for _ in range(40)]
        )
        conn.commit()
    finally:
        conn.close()


def _corrupt_interior_page(path: Path) -> None:
    """Zero the b-tree page-type byte of page 4. Page 1 (sqlite_master) and the
    header page count stay intact, so the file still opens and still lists its
    tables -- only a real integrity check sees the damage."""
    page_size = 4096
    data = bytearray(path.read_bytes())
    assert len(data) > page_size * 5, "fixture db too small to corrupt safely"
    data[page_size * 3] = 0x00
    path.write_bytes(bytes(data))


def _read_username(path: Path) -> str | None:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT username FROM users WHERE id = 1").fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _retained_copies(db_path: Path) -> list[Path]:
    """The databases displaced by past restores, oldest first."""
    prefix = f"{db_path.name}.pre-restore-"
    return sorted(
        entry
        for entry in db_path.parent.iterdir()
        if entry.name.startswith(prefix)
        and not entry.name.endswith(("-wal", "-shm"))
    )


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


# ── BK-2: the replaced database survives ─────────────────────────────────────


def test_apply_restore_retains_the_database_it_replaces(tmp_path: Path, live_db: Path):
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded")
    backup_service.stage_restore(upload)

    assert backup_restore.apply_pending_restore_if_present() is True
    assert _read_username(live_db) == "uploaded"

    retained = _retained_copies(live_db)
    assert len(retained) == 1, f"expected one retained copy, got {retained}"
    assert _read_username(retained[0]) == "live-owner"


def test_retained_copy_keeps_writes_that_were_still_only_in_the_wal(
    tmp_path: Path, live_db: Path
):
    """The subtle half of BK-2: in WAL mode the main database file is stale by
    design -- everything committed since the last checkpoint lives only in the
    ``-wal``. A retained copy that dropped that file would be missing exactly
    the newest writes, which is the data an operator is undoing a restore to
    get back."""
    # The connection stays open across the restore: SQLite checkpoints and
    # deletes the WAL on a clean close, so a closed database never reproduces
    # the state this is about. A live server's connections are open too.
    conn = sqlite3.connect(str(live_db))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("UPDATE users SET username = 'written-just-before' WHERE id = 1")
        conn.commit()
        assert Path(f"{live_db}-wal").stat().st_size > 0, "no uncheckpointed WAL"

        upload = tmp_path / "upload.db"
        _make_db(upload, marker="uploaded")
        backup_service.stage_restore(upload)
        assert backup_restore.apply_pending_restore_if_present() is True
    finally:
        conn.close()

    # The live sidecars must be gone so SQLite cannot replay old frames.
    assert not Path(f"{live_db}-wal").exists()
    assert not Path(f"{live_db}-shm").exists()

    retained = _retained_copies(live_db)
    assert _read_username(retained[0]) == "written-just-before"


def test_apply_restore_on_a_box_with_no_database_yet(tmp_path: Path, live_db: Path):
    live_db.unlink()
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded")
    backup_service.stage_restore(upload)

    assert backup_restore.apply_pending_restore_if_present() is True
    assert _read_username(live_db) == "uploaded"
    assert _retained_copies(live_db) == []


# ── BK-3: a corrupt upload is refused ────────────────────────────────────────


def test_validation_rejects_a_backup_with_corrupt_data_pages(tmp_path: Path):
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded")
    _corrupt_interior_page(upload)

    # Precondition: the file still opens and still lists its tables, which is
    # why listing sqlite_master could never have caught this. SQLite reports
    # the damage either as a non-"ok" verdict or by refusing the page
    # outright, depending on what the shredded page was carrying.
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

    with pytest.raises(AppError) as excinfo:
        backup_service.stage_restore(upload)
    assert excinfo.value.status_code == 422
    assert backup_service.restore_pending() is False


def test_validation_rejects_a_backup_with_broken_foreign_keys(tmp_path: Path):
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded")
    conn = sqlite3.connect(str(upload))
    try:
        conn.execute(
            "CREATE TABLE bookmarks ("
            "  id INTEGER PRIMARY KEY,"
            "  user_id INTEGER NOT NULL REFERENCES users(id)"
            ")"
        )
        # FK enforcement is off by default, so an orphan inserts happily and
        # only shows up under foreign_key_check.
        conn.execute("INSERT INTO bookmarks (id, user_id) VALUES (1, 999)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(AppError) as excinfo:
        backup_service.stage_restore(upload)
    assert excinfo.value.status_code == 422
    assert "bookmarks" in excinfo.value.message
    assert backup_service.restore_pending() is False


# ── BK-4: a backup from a newer build never reaches the swap ─────────────────


def test_upload_from_an_unknown_revision_is_refused(tmp_path: Path):
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded", revision="9999_from_the_future")

    with pytest.raises(AppError) as excinfo:
        backup_service.stage_restore(upload)
    assert excinfo.value.status_code == 422
    assert "9999_from_the_future" in excinfo.value.message
    assert backup_service.restore_pending() is False


def test_boot_refuses_a_staged_file_from_an_unknown_revision(
    tmp_path: Path, live_db: Path
):
    """The upload check is the first line, not the only one: a file staged by
    an older build, or dropped onto the box by hand, reaches the swap without
    ever having been validated. That is the one step that cannot be undone."""
    staged = backup_restore.pending_restore_path()
    _make_db(staged, marker="from-the-future", revision="9999_from_the_future")

    assert backup_restore.apply_pending_restore_if_present() is False
    assert _read_username(live_db) == "live-owner", "the live database was replaced"
    assert not staged.exists(), "the refused file was left to fail again every boot"
    assert _retained_copies(live_db) == []


def test_boot_refuses_a_staged_file_it_cannot_read(live_db: Path):
    """Staging is a move, and a move across filesystems is a copy. A crash
    part-way through one leaves a truncated file sitting exactly where the
    next boot looks -- and the swap is the step with no undo."""
    staged = backup_restore.pending_restore_path()
    staged.write_bytes(b"SQLite format 3\x00" + b"\x00" * 4000)

    assert backup_restore.apply_pending_restore_if_present() is False
    assert _read_username(live_db) == "live-owner", "the live database was replaced"
    assert not staged.exists()
    assert Path(f"{staged}.rejected").exists(), "the refused bytes were thrown away"
    assert _retained_copies(live_db) == []


def test_validation_accepts_a_backup_from_a_known_revision(tmp_path: Path):
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded", revision="0001_source_native")

    backup_service.stage_restore(upload)
    assert backup_service.restore_pending() is True


def test_validation_accepts_an_unstamped_backup(tmp_path: Path):
    """An ``alembic_version`` with no row is a database that was never
    stamped; there is no revision to disagree with, so this is not the
    newer-build case BK-4 is about."""
    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded", revision=None)

    backup_service.stage_restore(upload)
    assert backup_service.restore_pending() is True


# ── ADD-2: the export is user data, not cache ────────────────────────────────


def test_export_snapshot_excludes_the_derived_cache_tables(live_db: Path):
    snapshot = backup_service.create_backup_snapshot()
    try:
        conn = sqlite3.connect(str(snapshot))
        try:
            for table in _CACHE_TABLES:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert count == 0, f"{table} carried {count} row(s) into the export"
            # User data and the schema itself are untouched.
            assert conn.execute("SELECT COUNT(*) FROM payload").fetchone()[0] == 40
            assert conn.execute(
                "SELECT username FROM users WHERE id = 1"
            ).fetchone() == ("live-owner",)
        finally:
            conn.close()
        assert snapshot.stat().st_size < live_db.stat().st_size
    finally:
        snapshot.unlink(missing_ok=True)
        snapshot.parent.rmdir()


def test_export_keeps_the_cache_rows_when_explicitly_asked(live_db: Path):
    """Dropping them is the default, not the only option: cloning a box that
    should come up warm is the one case where the derived rows are the point."""
    snapshot = backup_service.create_backup_snapshot(include_cache=True)
    try:
        conn = sqlite3.connect(str(snapshot))
        try:
            for table in _CACHE_TABLES:
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 20
        finally:
            conn.close()
    finally:
        snapshot.unlink(missing_ok=True)
        snapshot.parent.rmdir()


def test_export_does_not_empty_the_live_cache_tables(live_db: Path):
    """The rows are dropped from the copy. Doing it to the live database would
    cost the running app every warm cache it has."""
    snapshot = backup_service.create_backup_snapshot()
    try:
        conn = sqlite3.connect(str(live_db))
        try:
            for table in _CACHE_TABLES:
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 20
        finally:
            conn.close()
    finally:
        snapshot.unlink(missing_ok=True)
        snapshot.parent.rmdir()


def test_export_does_not_create_the_database_it_reads(live_db: Path):
    """The snapshot connection is read-only, so exporting cannot write to the
    live database -- and on a box that has none yet, cannot quietly conjure
    one either. The caller still gets a valid (empty) SQLite file."""
    live_db.unlink()

    snapshot = backup_service.create_backup_snapshot()
    try:
        assert snapshot.read_bytes().startswith(b"SQLite format 3")
        assert not live_db.exists(), "exporting created the database it was reading"
    finally:
        snapshot.unlink(missing_ok=True)
        snapshot.parent.rmdir()


def test_an_exported_snapshot_can_be_staged_back(live_db: Path):
    """Round trip: emptying the cache tables must not make an export fail the
    import validation it has to pass to be worth anything."""
    snapshot = backup_service.create_backup_snapshot()
    backup_service.stage_restore(snapshot)
    assert backup_service.restore_pending() is True


# ── BK-7: spooled beside the database, not on the root overlay ───────────────


def test_export_snapshot_is_spooled_beside_the_database(live_db: Path):
    """In the container the system temp dir is the small, shared root overlay
    while the database lives on the data volume, so a snapshot built there
    fills the wrong disk -- and it is the wrong filesystem for the move that
    puts a file into place."""
    snapshot = backup_service.create_backup_snapshot()
    try:
        assert snapshot.parent.parent == live_db.parent
    finally:
        snapshot.unlink(missing_ok=True)
        snapshot.parent.rmdir()


def test_upload_is_spooled_beside_the_database(
    tmp_path: Path, live_db: Path, monkeypatch: pytest.MonkeyPatch
):
    """Staging *moves* the upload onto ``<db>.pending-restore``. Within one
    filesystem that is a rename and cannot be seen half-done; across two it is
    a copy, and a crash part-way through one leaves a truncated file sitting
    exactly where the next boot looks for a restore to apply."""
    import routes.backup as backup_routes

    spooled: list[Path] = []

    def _capture(path: Path) -> None:
        spooled.append(path)
        path.unlink(missing_ok=True)

    monkeypatch.setattr(backup_routes, "stage_restore", _capture)

    upload = tmp_path / "upload.db"
    _make_db(upload, marker="uploaded")

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(backup_routes.router)
    with TestClient(app) as client, upload.open("rb") as handle:
        response = client.post(
            "/backup/import",
            files={"file": ("backup.db", handle, "application/octet-stream")},
        )

    assert response.status_code == 200
    assert spooled, "the upload never reached staging"
    assert spooled[0].parent == live_db.parent
    # BK-2's other half: the admin is told, in the same breath, that the
    # database being replaced is kept and under what name.
    assert ".pre-restore-" in response.json()["message"]
