"""OCR ingest + dialogue search (spec §4.4).

The OCR runner is client-side now. The server only:
  * ``POST /ocr/chapter``   — accept an uploaded transcript (global ``chapter_ocr``)
  * ``GET  /ocr/chapter``   — return stored ``page_texts`` for in-reader highlight
  * ``GET  /ocr/search``    — FTS, filtered to the caller's followed series + gate
  * ``GET  /ocr/coverage``  — which chapters already have OCR

The write is global (spec §3.9); all three reads are scoped to the caller's
followed series + 18+ gate. Denial is a 404 that looks like absence, never a
403 — see ``OcrIngestService._may_read``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError

from core.errors import AppError
from core.profile_context import require_profile_context
from services.ocr_ingest_service import OcrIngestService, get_ocr_ingest_service
from services.ocr_search import OcrSearchService, get_ocr_search_service

router = APIRouter(prefix="/ocr", tags=["ocr"])

IngestDep = Annotated[OcrIngestService, Depends(get_ocr_ingest_service)]
SearchDep = Annotated[OcrSearchService, Depends(get_ocr_search_service)]

# Upload bounds (audit finding 13). The upload used to be unbounded — pages,
# per-page text, and free-form ``list[Any]`` boxes — all json.dumps'd into one
# global row and pushed through the FTS triggers, so a single request could
# pin the writer and bloat the DB on a small-disk VPS. Real chapters are a few
# hundred pages of dialogue at most; these ceilings are far above legitimate
# use and far below abuse.
OCR_MAX_PAGES = 500
OCR_MAX_PAGE_TEXT_CHARS = 20_000
OCR_MAX_BOXES_PER_PAGE = 300
OCR_MAX_BOX_TEXT_CHARS = 1_000
OCR_MAX_TOTAL_TEXT_CHARS = 2_000_000


class OcrBox(BaseModel):
    """One recognized text region (spec §3.9 ``{page, text, boxes}``).

    Typed instead of ``Any``: unknown keys are dropped, strings are capped,
    and only flat scalar geometry survives — an uploader can no longer park
    arbitrarily deep/huge JSON in the global ``chapter_ocr`` row.
    """

    model_config = {"extra": "ignore"}

    text: str = Field(default="", max_length=OCR_MAX_BOX_TEXT_CHARS)
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    left: float | None = None
    top: float | None = None
    right: float | None = None
    bottom: float | None = None
    confidence: float | None = None


class OcrPage(BaseModel):
    page: int = Field(ge=1)
    text: str = Field(default="", max_length=OCR_MAX_PAGE_TEXT_CHARS)
    boxes: list[OcrBox] | None = Field(default=None, max_length=OCR_MAX_BOXES_PER_PAGE)


class OcrChapterUpload(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)
    series_key: str = Field(min_length=1, max_length=512)
    chapter_key: str = Field(min_length=1, max_length=512)
    chapter_number: float | None = None
    language: str | None = Field(default=None, max_length=32)
    engine: str = Field(default="unknown", max_length=64)
    pages: list[OcrPage] = Field(min_length=1, max_length=OCR_MAX_PAGES)

    @model_validator(mode="after")
    def _cap_total_text(self) -> "OcrChapterUpload":
        total = sum(
            len(p.text) + sum(len(b.text) for b in (p.boxes or []))
            for p in self.pages
        )
        if total > OCR_MAX_TOTAL_TEXT_CHARS:
            # PydanticCustomError: its context stays JSON-serializable all the
            # way through the app's 422 envelope (a bare ValueError lands in
            # exc.errors() as an unserializable object).
            raise PydanticCustomError(
                "ocr_payload_too_large",
                "OCR payload too large: total text exceeds {limit} characters.",
                {"limit": OCR_MAX_TOTAL_TEXT_CHARS},
            )
        return self


@router.post("/chapter", dependencies=[Depends(require_profile_context)])
def upload_chapter_ocr(body: OcrChapterUpload, service: IngestDep) -> dict[str, Any]:
    return service.ingest_chapter(
        source_id=body.source_id,
        series_key=body.series_key,
        chapter_key=body.chapter_key,
        chapter_number=body.chapter_number,
        language=body.language,
        engine=body.engine,
        # exclude_none keeps the stored page_texts lean: geometry fields a
        # client did not send are omitted rather than stored as nulls.
        pages=[p.model_dump(exclude_none=True) for p in body.pages],
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
