"""OCR pipeline API endpoints.

Provides queue control, progress monitoring, text retrieval, and full-text
search over extracted chapter text.

Authorization
-------------

An OCR transcript *is* the content: ``/ocr/chapters/{id}/text`` hands back every
word of a chapter, and ``/ocr/search`` indexes every word of every chapter. This
router used to carry no authorization at all -- a bare ``Depends(get_db)`` -- so
any signed-in account could read any chapter's or page's text by id, and
``/ocr/search`` joined ChapterText -> Chapter -> Series with no user scoping,
making it a full-text search across every account's library.

The gate applied here is the *same* one the reader got (core.library_authz.
series_read_allowed for object-level authorization, plus the per-profile 18+
filter), reached through ``LibraryService``'s collaborator methods rather than
restated -- so the two surfaces cannot drift. Denials are 404 with the same code
an id that never existed produces.

What is deliberately NOT gated per-caller: the job-control surface
(``/ocr/queue/all``, ``/ocr/jobs*``, ``/ocr/metrics``). Those are pipeline
operations over the household's single shared catalog, they disclose no
transcribed content, and the pipeline itself has to keep running with no user
context at all -- ``OcrJobService`` is therefore left unscoped on purpose, the
same way the download worker and the update scheduler build unscoped services.
Authorization is applied *here*, at the request edge, where a caller exists.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.session import get_db
from services.library_service import LibraryService, get_library_service
from services.ocr_pipeline import OcrJobService
from services.ocr_search import OcrSearchService, get_ocr_search_service
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/ocr", tags=["ocr"])

DbDep = Annotated[Session, Depends(get_db)]
#: The caller's gate. Built from the request's (account, profile) exactly as the
#: library and reader routers build theirs; carries no OCR logic of its own.
LibraryDep = Annotated[LibraryService, Depends(get_library_service)]
OcrSearchDep = Annotated[OcrSearchService, Depends(get_ocr_search_service)]


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
    library: LibraryDep,
) -> dict[str, Any]:
    # A chapter this caller may not read is reported as *skipped*, which is
    # already how the service reports an id that does not exist -- so the
    # response cannot be used to tell "not yours" from "not real", and a batch
    # containing one foreign id still processes the caller's own ids.
    readable = [cid for cid in body.chapter_ids if library.can_read_chapter(cid)]
    service = OcrJobService(db)
    result = service.queue_chapters(readable, engine=body.engine, force=body.force)
    result["skipped"] = sorted(
        {*result["skipped"], *(set(body.chapter_ids) - set(readable))}
    )
    return result


@router.post("/queue/series/{series_id}")
def queue_series(
    series_id: int,
    body: QueueSeriesRequest,
    db: DbDep,
    library: LibraryDep,
) -> dict[str, Any]:
    library.assert_series_visible(series_id)
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
    library: LibraryDep,
) -> dict[str, Any]:
    # Not just progress numbers: the payload carries every chapter's title, so
    # ungated it enumerated the shape of another account's series by id.
    library.assert_series_visible(series_id)
    service = OcrJobService(db)
    return service.get_series_ocr_status(series_id)


@router.get("/chapters/{chapter_id}/text")
def get_chapter_text(
    chapter_id: int,
    db: DbDep,
    library: LibraryDep,
) -> dict[str, Any]:
    # The transcript IS the chapter, so it is gated exactly as get_chapter is:
    # object-level authorization plus the profile's 18+ filter, 404 with the
    # same code a chapter id that never existed produces. Note this replaces a
    # 200-with-nulls for an unknown id -- that response was itself an existence
    # oracle, since a real-but-unprocessed chapter answered identically.
    library.assert_chapter_readable(chapter_id)
    service = OcrJobService(db)
    return service.get_chapter_text(chapter_id)


@router.get("/pages/{page_id}/text")
def get_page_text(
    page_id: int,
    db: DbDep,
    library: LibraryDep,
) -> dict[str, Any]:
    library.assert_page_readable(page_id)
    service = OcrJobService(db)
    return service.get_page_text(page_id)


@router.get("/search")
def search_ocr(
    q: str,
    service: OcrSearchDep,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    # Scoped inside the service so ``total`` and the page window agree with what
    # the caller may actually read; see OcrSearchService.search.
    return service.search(q, limit=limit, offset=offset)


@router.get("/metrics")
def get_metrics(
    db: DbDep,
) -> dict[str, Any]:
    service = OcrJobService(db)
    return service.get_metrics()
