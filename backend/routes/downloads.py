from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from services.download_service import DownloadService, get_download_service
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/downloads", tags=["downloads"])

DownloadDep = Annotated[DownloadService, Depends(get_download_service)]


class QueueChaptersRequest(BaseModel):
    source_id: str
    series_id: str
    chapter_ids: list[str] = Field(min_length=1)
    series_title: str | None = None
    chapter_titles: dict[str, str] | None = None
    priority: int | None = None


class QueueSeriesRequest(BaseModel):
    source_id: str
    series_id: str
    priority: int | None = None


class SeriesActionRequest(BaseModel):
    source_id: str
    series_id: str


class MoveQueueItemRequest(BaseModel):
    direction: str


class DownloadSettingsUpdate(BaseModel):
    download_concurrent_chapters: int | None = Field(default=None, ge=1, le=10)
    download_page_concurrency: int | None = Field(default=None, ge=1, le=10)
    download_retry_count: int | None = Field(default=None, ge=0, le=10)
    download_retry_delay_seconds: float | None = Field(default=None, ge=0.0, le=30.0)
    download_timeout_seconds: float | None = Field(default=None, ge=1.0, le=300.0)


@router.get("")
def list_downloads(service: DownloadDep, response: Response) -> list[dict[str, object]]:
    items = service.list_downloads()
    set_list_total_header(response, len(items))
    return items


@router.get("/metrics")
def download_metrics(service: DownloadDep) -> dict[str, object]:
    return service.get_metrics()


@router.get("/settings")
def get_download_settings(service: DownloadDep) -> dict[str, object]:
    return service.get_download_settings()


@router.put("/settings")
def update_download_settings(
    body: DownloadSettingsUpdate, service: DownloadDep
) -> dict[str, object]:
    """Update one or more download settings. Applies immediately -- the
    scheduler's concurrent-chapter limit changes on its very next dispatch,
    no restart required -- and persists to config/settings.json so the
    change survives a restart too."""
    return service.update_download_settings(**body.model_dump(exclude_none=True))


@router.post("/chapters")
def queue_chapters(body: QueueChaptersRequest, service: DownloadDep) -> dict[str, object]:
    return service.queue_chapters(
        source_id=body.source_id,
        series_id=body.series_id,
        chapter_ids=body.chapter_ids,
        series_title=body.series_title,
        chapter_titles=body.chapter_titles,
        priority=body.priority,
    )


@router.post("/series")
def queue_series(body: QueueSeriesRequest, service: DownloadDep) -> dict[str, object]:
    return service.queue_series(
        source_id=body.source_id,
        series_id=body.series_id,
        priority=body.priority,
    )


@router.post("/series/pause")
def pause_series(body: SeriesActionRequest, service: DownloadDep) -> dict[str, object]:
    """Pause every active/queued download for one series. Other series'
    downloads are untouched."""
    return service.pause_bulk(source_id=body.source_id, series_id=body.series_id)


@router.post("/series/resume")
def resume_series(body: SeriesActionRequest, service: DownloadDep) -> dict[str, object]:
    return service.resume_bulk(source_id=body.source_id, series_id=body.series_id)


@router.post("/series/cancel")
def cancel_series(body: SeriesActionRequest, service: DownloadDep) -> dict[str, object]:
    """Cancel every non-terminal download for one series only -- downloads
    belonging to any other series are never touched."""
    return service.cancel_bulk(source_id=body.source_id, series_id=body.series_id)


@router.post("/pause-all")
def pause_all(service: DownloadDep) -> dict[str, object]:
    return service.pause_bulk()


@router.post("/resume-all")
def resume_all(service: DownloadDep) -> dict[str, object]:
    return service.resume_bulk()


@router.post("/cancel-all")
def cancel_all(service: DownloadDep) -> dict[str, object]:
    return service.cancel_bulk()


@router.post("/{download_id}/pause")
def pause_download(download_id: int, service: DownloadDep) -> dict[str, object]:
    return service.pause(download_id)


@router.post("/{download_id}/resume")
def resume_download(download_id: int, service: DownloadDep) -> dict[str, object]:
    return service.resume(download_id)


@router.post("/{download_id}/cancel")
def cancel_download(download_id: int, service: DownloadDep) -> dict[str, object]:
    return service.cancel(download_id)


@router.post("/{download_id}/retry")
def retry_download(download_id: int, service: DownloadDep) -> dict[str, object]:
    return service.retry(download_id)


@router.post("/{download_id}/move")
def move_download(
    download_id: int, body: MoveQueueItemRequest, service: DownloadDep
) -> dict[str, object]:
    """Move a queued download up/down within its own series' dispatch order."""
    return service.move_queue_item(download_id, direction=body.direction)
