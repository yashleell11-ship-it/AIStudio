"""Automatic update system API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.errors import AppError
from database.session import get_db
from services.update_scheduler import get_update_manager
from services.update_service import UpdateService, get_update_service
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/updates", tags=["updates"])


def _service(db: Session = Depends(get_db)) -> UpdateService:
    return get_update_service(db)


UpdateDep = Annotated[UpdateService, Depends(_service)]


class GlobalSettingsUpdate(BaseModel):
    enabled: bool | None = None
    check_interval_minutes: int | None = Field(default=None, ge=5)
    notify_enabled: bool | None = None
    auto_download_enabled: bool | None = None
    check_on_startup: bool | None = None


class FollowSeriesRequest(BaseModel):
    source: str
    series_id: str
    series_title: str


class TrackerUpdateRequest(BaseModel):
    enabled: bool | None = None
    notify: bool | None = None
    auto_download: bool | None = None
    check_interval_minutes: int | None = Field(default=None, ge=5)
    series_title: str | None = None


class ManualCheckRequest(BaseModel):
    tracker_ids: list[int] | None = None


@router.get("/settings")
def get_settings(service: UpdateDep) -> dict[str, object]:
    return service.serialize_settings(service.get_global_settings())


@router.put("/settings")
def put_settings(body: GlobalSettingsUpdate, service: UpdateDep) -> dict[str, object]:
    return service.update_global_settings(body.model_dump(exclude_none=True))


@router.get("/sources")
def list_sources(service: UpdateDep) -> list[dict[str, str]]:
    return service.list_sources()


@router.get("/trackers")
def list_trackers(
    service: UpdateDep,
    response: Response,
    track_kind: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> list[dict[str, object]]:
    items = service.list_trackers(track_kind=track_kind, source=source)
    set_list_total_header(response, service.count_trackers(track_kind=track_kind, source=source))
    return items


@router.post("/trackers/follow")
def follow_series(body: FollowSeriesRequest, service: UpdateDep) -> dict[str, object]:
    return service.follow_series(
        source=body.source,
        series_id=body.series_id,
        series_title=body.series_title,
    )


@router.patch("/trackers/{tracker_id}")
def patch_tracker(
    tracker_id: int,
    body: TrackerUpdateRequest,
    service: UpdateDep,
) -> dict[str, object]:
    return service.update_tracker(tracker_id, body.model_dump(exclude_none=True))


@router.delete("/trackers/{tracker_id}")
def delete_tracker(tracker_id: int, service: UpdateDep) -> dict[str, bool]:
    service.unfollow_tracker(tracker_id)
    return {"deleted": True}


@router.post("/trackers/sync-downloaded")
def sync_downloaded(service: UpdateDep) -> dict[str, object]:
    return service.sync_downloaded_trackers()


@router.get("/notifications")
def list_notifications(
    service: UpdateDep,
    response: Response,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    items = service.list_notifications(unread_only=unread_only, limit=limit)
    set_list_total_header(response, service.count_notifications(unread_only=unread_only))
    return items


@router.get("/notifications/unread-count")
def unread_count(service: UpdateDep) -> dict[str, int]:
    return {"count": service.unread_count()}


@router.patch("/notifications/{notification_id}/read")
def mark_read(notification_id: int, service: UpdateDep) -> dict[str, object]:
    return service.mark_notification_read(notification_id)


@router.post("/notifications/read-all")
def mark_all_read(service: UpdateDep) -> dict[str, int]:
    return service.mark_all_notifications_read()


@router.get("/runs")
def list_runs(
    service: UpdateDep,
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, object]]:
    items = service.list_runs(limit=limit)
    set_list_total_header(response, service.count_runs())
    return items


@router.get("/runs/{run_id}")
def get_run(run_id: int, service: UpdateDep) -> dict[str, object]:
    return service.get_run(run_id)


@router.post("/check")
def manual_check(body: ManualCheckRequest, service: UpdateDep) -> dict[str, object]:
    """Trigger an update check without blocking the request thread.

    When the background worker pool is running (the standard production
    configuration), the check always executes on a worker thread: this
    returns immediately with ``{"queued": True}``, or 409 if a check is
    already in progress. Only when the worker pool itself is disabled
    (``run_workers=False``, used in tests/dev tooling) does this fall back
    to running the check inline, since there is no worker to dispatch to.
    """
    manager = get_update_manager()
    if not manager.is_running:
        return service.run_check(trigger="manual", tracker_ids=body.tracker_ids)
    if manager.trigger_check(trigger="manual", tracker_ids=body.tracker_ids):
        return {"queued": True, "trigger": "manual"}
    raise AppError(
        "An update check is already running.",
        code="check_already_running",
        status_code=409,
    )


@router.post("/trackers/{tracker_id}/check")
def check_tracker(tracker_id: int, service: UpdateDep) -> dict[str, object]:
    return service.check_tracker_by_id(tracker_id)
