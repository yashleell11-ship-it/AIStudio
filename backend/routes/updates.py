"""Automatic update system API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.errors import AppError
from core.profile_context import (
    ProfileContext,
    require_profile_context,
    resolve_profile_context,
)
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service
from services.update_scheduler import get_update_manager
from services.update_service import UpdateService, get_update_service
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/updates", tags=["updates"])


def _service(
    db: Session = Depends(get_db),
    ctx: ProfileContext = Depends(resolve_profile_context),
) -> UpdateService:
    return get_update_service(db, user_id=ctx.user_id, profile_id=ctx.profile_id)


UpdateDep = Annotated[UpdateService, Depends(_service)]
BrowseDep = Annotated[BrowseService, Depends(get_browse_service)]


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
    # Genres as the client already has them from the series payload it is
    # following from. Optional and advisory: they are the only machine-readable
    # adult signal most sources expose, and taking them from the caller avoids
    # a scraper round-trip on a write path. Absent => rating stays unknown.
    genres: list[str] | None = None


class TrackerUpdateRequest(BaseModel):
    enabled: bool | None = None
    notify: bool | None = None
    auto_download: bool | None = None
    check_interval_minutes: int | None = Field(default=None, ge=5)
    series_title: str | None = None
    # Tri-state, so an explicit null must survive to the service: null means
    # "stop overriding and go back to inferring", which is different from
    # "field absent". Handled via model_fields_set in patch_tracker below,
    # since the shared exclude_none dump would swallow it.
    mature_override: bool | None = None


class ManualCheckRequest(BaseModel):
    tracker_ids: list[int] | None = None


class MigrateTrackerRequest(BaseModel):
    """Preview or perform a source migration for one followed series."""

    target_source: str
    target_series_id: str
    target_series_title: str | None = None
    # Added to every old chapter number before matching, for targets that
    # restart numbering per season. The dry run reports counts.matched so the
    # client can let the user nudge this until the match count peaks.
    chapter_offset: float = 0.0
    # Defaults to preview: nothing is written unless the caller says so.
    dry_run: bool = True
    # Only meaningful on the 409 tracker_target_already_followed path.
    merge: bool = False
    # From a preceding dry run. When supplied and the freshly fetched target
    # catalog hashes differently, the commit is refused (409 migration_stale)
    # rather than applying a map the user never saw.
    expected_chapter_map_hash: str | None = None


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
    # Follows hidden by the 18+ gate are reported in a header rather than
    # omitted silently: a list that shrinks with no explanation reads as data
    # loss, which is the most likely way this filter gets mistaken for a bug.
    response.headers["X-Hidden-By-Mature-Gate"] = str(
        service.count_trackers_hidden_by_gate(track_kind=track_kind, source=source)
    )
    return items


@router.post(
    "/trackers/follow",
    dependencies=[Depends(require_profile_context)],
)
def follow_series(body: FollowSeriesRequest, service: UpdateDep) -> dict[str, object]:
    return service.follow_series(
        source=body.source,
        series_id=body.series_id,
        series_title=body.series_title,
        genres=body.genres,
    )


@router.patch("/trackers/{tracker_id}")
def patch_tracker(
    tracker_id: int,
    body: TrackerUpdateRequest,
    service: UpdateDep,
) -> dict[str, object]:
    payload = body.model_dump(exclude_none=True)
    if "mature_override" in body.model_fields_set:
        # Re-add after the exclude_none dump so an explicit null clears the
        # override rather than being read as "not supplied".
        payload["mature_override"] = body.mature_override
    return service.update_tracker(tracker_id, payload)


@router.delete("/trackers/{tracker_id}")
def delete_tracker(tracker_id: int, service: UpdateDep) -> dict[str, bool]:
    service.unfollow_tracker(tracker_id)
    return {"deleted": True}


@router.get(
    "/trackers/{tracker_id}/migration-candidates",
    dependencies=[Depends(require_profile_context)],
)
async def migration_candidates(
    tracker_id: int,
    request: Request,
    service: UpdateDep,
    browse: BrowseDep,
    q: str | None = Query(default=None, description="Defaults to the followed title"),
    per_page: int = Query(default=10, ge=1, le=50),
) -> dict[str, object]:
    """Where this followed series could be migrated to.

    Backed by the existing federated fan-out, so it inherits its whole-request
    deadline and its partial-failure reporting: a large ``sources_failed`` is
    normal on a registry this size, not an error.
    """
    return await service.list_migration_candidates(
        tracker_id,
        browse=browse,
        query=q,
        base_url=str(request.base_url),
        per_page=per_page,
    )


@router.post(
    "/trackers/{tracker_id}/migrate",
    dependencies=[Depends(require_profile_context)],
)
def migrate_tracker(
    tracker_id: int,
    body: MigrateTrackerRequest,
    service: UpdateDep,
) -> dict[str, object]:
    """Repoint a followed series at another source, preserving progress.

    Preview (``dry_run: true``, the default) and commit return the identical
    shape; ``applied`` says which happened. ``chapter_map`` is the remap the
    client replays over its own online-progress store — online reading progress
    for a non-downloaded remote series exists only there, never on the server.
    """
    return service.migrate_tracker(
        tracker_id,
        target_source=body.target_source,
        target_series_id=body.target_series_id,
        target_series_title=body.target_series_title,
        chapter_offset=body.chapter_offset,
        dry_run=body.dry_run,
        merge=body.merge,
        expected_chapter_map_hash=body.expected_chapter_map_hash,
    )


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
