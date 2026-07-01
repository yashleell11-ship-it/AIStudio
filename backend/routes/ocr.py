"""OCR pipeline API endpoints.

Provides queue control, progress monitoring, text retrieval, and full-text
search over extracted chapter text.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.session import get_db
from services.ocr_pipeline import OcrJobService
from services.ocr_search import OcrSearchService
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/ocr", tags=["ocr"])

DbDep = Annotated[Session, Depends(get_db)]


class QueueChaptersRequest(BaseModel):
    chapter_ids: list[int] = Field(min_length=1)
    engine: str | None = None
    force: bool = False


class QueueSeriesRequest(BaseModel):
    engine: str | None = None
    force: bool = False


class QueueAllRequest(BaseModel):
    engine: str | None = None
    force: bool = False


@router.post("/queue/chapters")
def queue_chapters(
    body: QueueChaptersRequest,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.queue_chapters(
        body.chapter_ids, engine=body.engine, force=body.force
    )


@router.post("/queue/series/{series_id}")
def queue_series(
    series_id: int,
    body: QueueSeriesRequest,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.queue_series(
        series_id, engine=body.engine, force=body.force
    )


@router.post("/queue/all")
def queue_all_unprocessed(
    body: QueueAllRequest,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.queue_all_unprocessed(
        engine=body.engine, force=body.force
    )


@router.get("/jobs")
def list_jobs(
    db: DbDep,
    response: Response,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    service = OcrJobService(db)
    items = service.list_jobs(status=status, limit=limit)
    set_list_total_header(response, service.count_jobs(status=status))
    return items


@router.get("/jobs/{job_id}")
def get_job(
    job_id: int,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.get_job(job_id)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: int,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.retry_job(job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: int,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.cancel_job(job_id)


@router.get("/series/{series_id}/status")
def get_series_ocr_status(
    series_id: int,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.get_series_ocr_status(series_id)


@router.get("/chapters/{chapter_id}/text")
def get_chapter_text(
    chapter_id: int,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.get_chapter_text(chapter_id)


@router.get("/pages/{page_id}/text")
def get_page_text(
    page_id: int,
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.get_page_text(page_id)


@router.get("/search")
def search_ocr(
    q: str,
    db: DbDep,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    service = OcrSearchService(db)
    return service.search(q, limit=limit, offset=offset)


@router.get("/metrics")
def get_metrics(
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.get_metrics()
