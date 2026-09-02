"""Source-native reader endpoints (spec §4.1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from core.profile_context import require_profile_context
from services.progress_service import (
    ProgressInput,
    ProgressService,
    get_progress_service,
)
from services.reader_service import ReaderService, get_reader_service
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/reader", tags=["reader"])

ReaderDep = Annotated[ReaderService, Depends(get_reader_service)]
ProgressDep = Annotated[ProgressService, Depends(get_progress_service)]


class ProgressRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)
    series_key: str = Field(min_length=1, max_length=512)
    chapter_key: str = Field(min_length=1, max_length=512)
    chapter_number: float | None = None
    last_page: int = Field(default=1, ge=1)
    page_count: int = Field(default=0, ge=0)
    scroll_offset_px: int = Field(default=0, ge=0)
    is_completed: bool = False
    time_spent_seconds: int = Field(default=0, ge=0)

    def to_input(self) -> ProgressInput:
        return ProgressInput(
            source_id=self.source_id,
            series_key=self.series_key,
            chapter_key=self.chapter_key,
            chapter_number=self.chapter_number,
            last_page=self.last_page,
            page_count=self.page_count,
            scroll_offset_px=self.scroll_offset_px,
            is_completed=self.is_completed,
            time_spent_seconds=self.time_spent_seconds,
        )


class BookmarkRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)
    series_key: str = Field(min_length=1, max_length=512)
    chapter_key: str = Field(min_length=1, max_length=512)
    page: int = Field(ge=1)
    note: str | None = None


@router.get("/chapter/manifest")
def chapter_manifest(
    service: ReaderDep,
    source: str = Query(..., min_length=1),
    series: str = Query(..., min_length=1),
    chapter: str = Query(..., min_length=1),
) -> dict[str, object]:
    """The download plan for a chapter: ordered page list + prev/next keys."""
    return service.manifest(source, series, chapter)


@router.post("/progress", dependencies=[Depends(require_profile_context)])
def save_progress(body: ProgressRequest, service: ProgressDep) -> dict[str, object]:
    """Save reading progress. Applies the furthest-wins merge (never rewinds)."""
    return service.save_one(body.to_input())


@router.post("/progress/batch", dependencies=[Depends(require_profile_context)])
def save_progress_batch(
    body: list[ProgressRequest], service: ProgressDep
) -> dict[str, object]:
    """Offline-sync catch-up: an array of progress pushes, each merged."""
    return service.save_batch([item.to_input() for item in body])


@router.get("/progress/series")
def get_series_progress(
    service: ProgressDep,
    source: str = Query(..., min_length=1),
    series: str = Query(..., min_length=1),
) -> list[dict[str, object]]:
    """Every stored chapter position for one series."""
    return service.get_series_progress(source, series)


@router.get("/history")
def reading_history(
    service: ProgressDep,
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict[str, object]]:
    items = service.reading_history(limit=limit, offset=offset)
    set_list_total_header(response, len(items))
    return items


@router.post("/bookmark", dependencies=[Depends(require_profile_context)])
def create_bookmark(body: BookmarkRequest, service: ProgressDep) -> dict[str, object]:
    return service.add_bookmark(
        source_id=body.source_id,
        series_key=body.series_key,
        chapter_key=body.chapter_key,
        page=body.page,
        note=body.note,
    )


@router.get("/bookmarks")
def list_bookmarks(
    service: ProgressDep,
    response: Response,
    source: str | None = None,
    series: str | None = None,
) -> list[dict[str, object]]:
    items = service.list_bookmarks(source_id=source, series_key=series)
    set_list_total_header(response, len(items))
    return items


@router.delete(
    "/bookmarks/{bookmark_id}",
    status_code=204,
    dependencies=[Depends(require_profile_context)],
)
def delete_bookmark(bookmark_id: int, service: ProgressDep) -> None:
    service.delete_bookmark(bookmark_id)
