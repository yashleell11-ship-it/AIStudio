"""Database backup export/import.

Export streams a consistent, point-in-time SQLite snapshot (see
``services.backup_service.create_backup_snapshot``). Import validates an
uploaded backup and stages it; the actual file swap only happens the next
time the process starts (``core.backup_restore``), since replacing the live
database file out from under an already-open, process-lifetime SQLAlchemy
engine is not safe to do while the server keeps running.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from core.backup_restore import has_pending_restore
from core.errors import AppError
from core.rate_limit import import_limit, limiter
from services.auth_service import require_admin_user
from services.backup_service import (
    backup_filename,
    clear_pending_restore,
    create_backup_snapshot,
    stage_restore,
)

router = APIRouter(prefix="/backup", tags=["backup"])


class BackupStatus(BaseModel):
    restore_pending: bool


class RestoreStaged(BaseModel):
    status: str
    message: str


@router.get("/export", dependencies=[Depends(require_admin_user)])
def export_backup() -> FileResponse:
    """Download a consistent snapshot of the current database."""
    snapshot_path = create_backup_snapshot()
    return FileResponse(
        path=snapshot_path,
        media_type="application/octet-stream",
        filename=backup_filename(),
        background=BackgroundTask(
            shutil.rmtree, snapshot_path.parent, ignore_errors=True
        ),
    )


@router.get("/status", response_model=BackupStatus)
def backup_status() -> BackupStatus:
    return BackupStatus(restore_pending=has_pending_restore())


@router.post("/import", response_model=RestoreStaged, dependencies=[Depends(require_admin_user)])
@limiter.limit(import_limit)
def import_backup(file: UploadFile, request: Request, response: Response) -> RestoreStaged:
    """Validate an uploaded backup and stage it for restore on next start."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        stage_restore(tmp_path)
    except AppError:
        tmp_path.unlink(missing_ok=True)
        raise

    return RestoreStaged(
        status="staged",
        message="Restore staged. Restart the server to finish applying it.",
    )


@router.delete("/pending", response_model=BackupStatus, dependencies=[Depends(require_admin_user)])
def cancel_pending_restore() -> BackupStatus:
    """Cancel a staged restore before it's applied on next start."""
    clear_pending_restore()
    return BackupStatus(restore_pending=has_pending_restore())
