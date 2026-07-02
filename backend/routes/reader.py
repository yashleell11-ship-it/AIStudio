from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from services.image_service import ImageService, get_image_service
from services.library_service import LibraryService, get_library_service
from services.reader_service import ReaderService, get_reader_service
from utils.api_pagination import set_list_total_header, set_progress_found_header

router = APIRouter(prefix="/reader", tags=["reader"])


LibraryDep = Annotated[LibraryService, Depends(get_library_service)]
ReaderDep = Annotated[ReaderService, Depends(get_reader_service)]
ImageDep = Annotated[ImageService, Depends(get_image_service)]


class ProgressRequest(BaseModel):
    series_id: int = Field(ge=1)
    chapter_id: int = Field(ge=1)
    last_page: int = Field(ge=1)
    scroll_offset_px: int | None = Field(default=None, ge=0)


class BookmarkRequest(BaseModel):
    series_id: int = Field(ge=1)
    chapter_id: int = Field(ge=1)
    page: int = Field(ge=1)
    note: str | None = None


@router.get("/chapter/{chapter_id}")
def get_reader_chapter(chapter_id: int, service: LibraryDep) -> dict[str, object]:
    """Return chapter with ordered pages for the reader."""
    return service.get_chapter(chapter_id)


@router.get("/page/{page_id}/image")
def get_reader_page_image(
    page_id: int,
    service: LibraryDep,
    image_service: ImageDep,
) -> Response:
    """Serve a page image for the reader."""
    payload, media_type = image_service.serve_page(service, page_id)
    if isinstance(payload, bytes):
        return Response(
            content=payload,
            media_type=media_type,
            headers={"Cache-Control": "max-age=86400"},
        )
    return FileResponse(
        payload,
        media_type=media_type,
        headers={"Cache-Control": "max-age=86400"},
    )


@router.post("/progress")
def save_progress(body: ProgressRequest, service: ReaderDep) -> dict[str, object]:
    """Save reading progress for a series."""
    return service.save_progress(
        series_id=body.series_id,
        chapter_id=body.chapter_id,
        last_page=body.last_page,
        scroll_offset_px=body.scroll_offset_px,
    )


@router.get("/progress/{series_id}")
def get_progress(
    series_id: int,
    service: ReaderDep,
    response: Response,
) -> dict[str, object] | None:
    """Return saved reading progress for a series."""
    progress = service.get_progress(series_id)
    set_progress_found_header(response, progress is not None)
    return progress


@router.delete("/progress/{series_id}", status_code=204)
def delete_progress(series_id: int, service: ReaderDep) -> None:
    """Clear saved reading progress for a series."""
    service.delete_progress(series_id)


@router.post("/bookmarks")
def create_bookmark(body: BookmarkRequest, service: ReaderDep) -> dict[str, object]:
    """Bookmark the current page."""
    return service.add_bookmark(
        series_id=body.series_id,
        chapter_id=body.chapter_id,
        page=body.page,
        note=body.note,
    )


@router.get("/bookmarks")
def list_all_bookmarks(
    service: ReaderDep,
    response: Response,
    limit: int = Query(200, ge=1, le=500),
) -> list[dict[str, object]]:
    """List the most recent bookmarks across every series (Bookmark Manager)."""
    items = service.list_all_bookmarks(limit=limit)
    set_list_total_header(response, len(items))
    return items


@router.get("/bookmarks/{series_id}")
def list_bookmarks(
    series_id: int,
    service: ReaderDep,
    response: Response,
) -> list[dict[str, object]]:
    """List bookmarks for a series."""
    items = service.list_bookmarks(series_id)
    set_list_total_header(response, len(items))
    return items


@router.delete("/bookmarks/{bookmark_id}", status_code=204)
def delete_bookmark(bookmark_id: int, service: ReaderDep) -> None:
    """Remove a bookmark."""
    service.delete_bookmark(bookmark_id)


@router.get("/chapter/{chapter_id}/adjacent")
def adjacent_chapter(
    chapter_id: int,
    service: ReaderDep,
    direction: str = Query("next", pattern="^(previous|next)$"),
) -> dict[str, object] | None:
    """Return the previous or next chapter in a series."""
    return service.get_adjacent_chapter(chapter_id, direction)
