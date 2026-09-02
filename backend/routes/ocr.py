"""OCR ingest + dialogue search (spec §4.4).

The OCR runner is client-side now. The server only:
  * ``POST /ocr/chapter``   — accept an uploaded transcript (global ``chapter_ocr``)
  * ``GET  /ocr/chapter``   — return stored ``page_texts`` for in-reader highlight
  * ``GET  /ocr/search``    — FTS, filtered to the caller's followed series + gate
  * ``GET  /ocr/coverage``  — which chapters already have OCR
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from core.errors import AppError
from core.profile_context import require_profile_context
from services.ocr_ingest_service import OcrIngestService, get_ocr_ingest_service
from services.ocr_search import OcrSearchService, get_ocr_search_service

router = APIRouter(prefix="/ocr", tags=["ocr"])

IngestDep = Annotated[OcrIngestService, Depends(get_ocr_ingest_service)]
SearchDep = Annotated[OcrSearchService, Depends(get_ocr_search_service)]


class OcrPage(BaseModel):
    page: int = Field(ge=1)
    text: str = ""
    boxes: list[Any] | None = None


class OcrChapterUpload(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)
    series_key: str = Field(min_length=1, max_length=512)
    chapter_key: str = Field(min_length=1, max_length=512)
    chapter_number: float | None = None
    language: str | None = None
    engine: str = "unknown"
    pages: list[OcrPage] = Field(min_length=1)


@router.post("/chapter", dependencies=[Depends(require_profile_context)])
def upload_chapter_ocr(body: OcrChapterUpload, service: IngestDep) -> dict[str, Any]:
    return service.ingest_chapter(
        source_id=body.source_id,
        series_key=body.series_key,
        chapter_key=body.chapter_key,
        chapter_number=body.chapter_number,
        language=body.language,
        engine=body.engine,
        pages=[p.model_dump() for p in body.pages],
    )


@router.get("/chapter")
def get_chapter_ocr(
    service: IngestDep,
    source: str = Query(..., min_length=1),
    series: str = Query(..., min_length=1),
    chapter: str = Query(..., min_length=1),
) -> dict[str, Any]:
    payload = service.get_chapter(source, series, chapter)
    if payload is None:
        raise AppError("No OCR for this chapter.", code="not_found", status_code=404)
    return payload


@router.get("/coverage")
def ocr_coverage(
    service: IngestDep,
    source: str = Query(..., min_length=1),
    series: str = Query(..., min_length=1),
) -> dict[str, Any]:
    return service.coverage(source, series)


@router.get("/search")
def search_ocr(
    q: str,
    service: SearchDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return service.search(q, limit=limit, offset=offset)
