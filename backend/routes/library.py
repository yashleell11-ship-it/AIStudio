from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from core.security import require_admin
from services.image_service import ImageService, get_image_service
from services.library_intelligence_service import (
    LibraryIntelligenceService,
    get_library_intelligence_service,
)
from services.library_service import LibraryService, get_library_service
from utils.api_pagination import set_list_total_header

router = APIRouter(prefix="/library", tags=["library"])

ServiceDep = Annotated[LibraryService, Depends(get_library_service)]
IntelDep = Annotated[LibraryIntelligenceService, Depends(get_library_intelligence_service)]


class ImportRequest(BaseModel):
    folder_path: str = Field(min_length=1, max_length=1024)


class ImportResponse(BaseModel):
    status: str
    library_id: int
    series_count: int
    chapter_count: int
    page_count: int
    removed_orphans: int = 0


class ReadingProgressSummary(BaseModel):
    series_id: int
    chapter_id: int
    last_page: int
    scroll_offset_px: int = 0
    progress_pct: float
    last_read_at: str


class OcrSummary(BaseModel):
    completed: int
    processing: int
    failed: int
    not_started: int
    total: int


class SeriesSummary(BaseModel):
    id: int
    library_id: int
    title: str
    sort_title: str
    original_title: str | None = None
    author: str | None = None
    artist: str | None = None
    description: str | None = None
    status: str | None = None
    content_rating: str | None = None
    language: str | None = None
    year: int | None = None
    cover_path: str | None = None
    cover_url: str
    folder_path: str
    is_favorite: bool = False
    reading_status: str = "unread"
    chapter_count: int
    read_chapters: int = 0
    page_count: int
    total_chapters: int | None = None
    total_pages: int | None = None
    first_chapter_id: int | None = None
    created_at: str
    updated_at: str
    reading_progress: ReadingProgressSummary | None = None
    ocr_summary: OcrSummary | None = None


class SeriesListResponse(BaseModel):
    items: list[SeriesSummary]
    total: int
    page: int
    per_page: int
    has_next: bool
    page_size: int
    has_more: bool
    total_pages: int


class ScanStatusResponse(BaseModel):
    running: bool
    progress_pct: float
    message: str
    series_count: int
    chapter_count: int
    page_count: int
    error: str | None = None


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class CollectionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    sort_order: int | None = None


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(default="custom")
    color: str | None = Field(default=None, max_length=16)


class SeriesUpdateRequest(BaseModel):
    title: str | None = None
    author: str | None = None
    artist: str | None = None
    description: str | None = None
    status: str | None = None
    content_rating: str | None = None
    language: str | None = None
    year: int | None = None
    reading_status: str | None = None
    is_favorite: bool | None = None

ImageDep = Annotated[ImageService, Depends(get_image_service)]


@router.get("/series", response_model=SeriesListResponse)
def list_series(
    service: ServiceDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(40, ge=1, le=200),
    sort: str = Query("sort_title"),
    search: str | None = None,
    status: str | None = None,
    reading_status: str | None = None,
    collection_id: int | None = None,
    tag_id: int | None = None,
    library_id: int | None = None,
    is_favorite: bool | None = None,
    language: str | None = None,
    has_chapters: bool | None = None,
) -> SeriesListResponse:
    """Return a paginated list of series in the library."""
    result = service.list_series(
        page=page,
        per_page=per_page,
        sort=sort,
        search=search,
        status=status,
        reading_status=reading_status,
        collection_id=collection_id,
        tag_id=tag_id,
        library_id=library_id,
        is_favorite=is_favorite,
        language=language,
        has_chapters=has_chapters,
    )
    return SeriesListResponse(**result)


@router.get("/series/{series_id}")
def get_series(series_id: int, intel: IntelDep) -> dict[str, object]:
    """Return series detail with chapter list, tags, and collections."""
    return intel.get_series_detail(series_id)


@router.patch("/series/{series_id}")
def patch_series(
    series_id: int,
    body: SeriesUpdateRequest,
    intel: IntelDep,
) -> dict[str, object]:
    """Update series metadata."""
    return intel.update_series_metadata(
        series_id,
        **body.model_dump(exclude_none=True),
    )


@router.post("/series/{series_id}/favorite")
def toggle_favorite(series_id: int, intel: IntelDep) -> dict[str, object]:
    """Toggle the favorite status of a series."""
    return intel.toggle_favorite(series_id)


@router.get("/series/{series_id}/similar")
def similar_series(
    series_id: int,
    intel: IntelDep,
    response: Response,
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, object]]:
    """Return series similar to the given one."""
    items = intel.get_similar_series(series_id, limit=limit)
    set_list_total_header(response, len(items))
    return items


@router.get("/series/{series_id}/metadata-quality")
def metadata_quality(
    series_id: int,
    intel: IntelDep,
) -> dict[str, object]:
    """Return metadata completeness score and suggestions for a series."""
    return intel.get_metadata_quality(series_id)


@router.get("/series/{series_id}/reading-history")
def series_reading_history(
    series_id: int,
    intel: IntelDep,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, object]]:
    """Return reading history for a specific series."""
    return intel.get_series_reading_history(series_id, limit=limit)


@router.get("/reading-calendar")
def reading_calendar(
    intel: IntelDep,
    days: int = Query(30, ge=1, le=365),
) -> list[dict[str, object]]:
    """Return daily reading aggregates for the last N days."""
    return intel.get_reading_calendar(days=days)


@router.get("/chapters/{chapter_id}")
def get_chapter(chapter_id: int, service: ServiceDep) -> dict[str, object]:
    """Return chapter detail with ordered page list."""
    return service.get_chapter(chapter_id)


@router.get("/libraries")
def list_libraries(service: ServiceDep, response: Response) -> list[dict[str, object]]:
    """Return configured library roots (for mobile library filtering)."""
    items = service.list_libraries()
    set_list_total_header(response, len(items))
    return items


@router.get("/continue-reading")
def continue_reading(
    service: ServiceDep,
    response: Response,
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, object]]:
    """Return in-progress series for the Continue Reading strip."""
    items = service.get_continue_reading(limit=limit)
    set_list_total_header(response, len(items))
    return items


@router.get("/reading-history")
def reading_history(
    intel: IntelDep,
    response: Response,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, object]]:
    """Return recent reading activity."""
    items = intel.get_reading_history(limit=limit)
    set_list_total_header(response, len(items))
    return items


@router.get("/recently-added")
def recently_added(
    intel: IntelDep,
    response: Response,
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, object]]:
    """Return recently added series."""
    items = intel.get_recently_added(limit=limit)
    set_list_total_header(response, len(items))
    return items


@router.get("/recently-updated")
def recently_updated(
    intel: IntelDep,
    response: Response,
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, object]]:
    """Return recently updated series."""
    items = intel.get_recently_updated(limit=limit)
    set_list_total_header(response, len(items))
    return items


@router.get("/recommendations")
def recommendations(
    intel: IntelDep,
    response: Response,
    limit: int = Query(10, ge=1, le=50),
) -> list[dict[str, object]]:
    """Return recommended series based on reading history."""
    items = intel.get_recommendations(limit=limit)
    set_list_total_header(response, len(items))
    return items


@router.get("/statistics")
def statistics(intel: IntelDep) -> dict[str, object]:
    """Return library statistics."""
    return intel.get_statistics()


@router.post("/import", response_model=ImportResponse, dependencies=[Depends(require_admin)])
def import_library(body: ImportRequest, service: ServiceDep) -> ImportResponse:
    """Scan a folder and import series, chapters, and pages into the database."""
    result = service.import_folder(body.folder_path)
    return ImportResponse(**result)


@router.get("/scan-status", response_model=ScanStatusResponse)
def scan_status(service: ServiceDep) -> ScanStatusResponse:
    """Poll current library scan progress."""
    return ScanStatusResponse(**service.get_scan_status())


# ------------------------------------------------------------------
# Collections
# ------------------------------------------------------------------

@router.get("/collections")
def list_collections(intel: IntelDep, response: Response) -> list[dict[str, object]]:
    """Return all collections."""
    items = intel.list_collections()
    set_list_total_header(response, len(items))
    return items


@router.post("/collections")
def create_collection(body: CollectionCreateRequest, intel: IntelDep) -> dict[str, object]:
    """Create a new collection."""
    return intel.create_collection(name=body.name, description=body.description)


@router.get("/collections/{collection_id}")
def get_collection(collection_id: int, intel: IntelDep) -> dict[str, object]:
    """Return collection detail with series list."""
    return intel.get_collection(collection_id)


@router.patch("/collections/{collection_id}")
def update_collection(
    collection_id: int,
    body: CollectionUpdateRequest,
    intel: IntelDep,
) -> dict[str, object]:
    """Update collection metadata."""
    return intel.update_collection(
        collection_id,
        name=body.name,
        description=body.description,
        sort_order=body.sort_order,
    )


@router.delete("/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: int, intel: IntelDep) -> None:
    """Delete a collection."""
    intel.delete_collection(collection_id)


@router.post("/collections/{collection_id}/series/{series_id}")
def add_series_to_collection(
    collection_id: int,
    series_id: int,
    intel: IntelDep,
) -> dict[str, object]:
    """Add a series to a collection."""
    return intel.add_series_to_collection(collection_id, series_id)


class CollectionReorderRequest(BaseModel):
    series_ids: list[int]


@router.post("/collections/{collection_id}/reorder")
def reorder_collection_series(
    collection_id: int,
    body: CollectionReorderRequest,
    intel: IntelDep,
) -> dict[str, object]:
    """Reorder series within a collection."""
    return intel.reorder_collection_series(collection_id, body.series_ids)


@router.delete("/collections/{collection_id}/series/{series_id}", status_code=204)
def remove_series_from_collection(
    collection_id: int,
    series_id: int,
    intel: IntelDep,
) -> None:
    """Remove a series from a collection."""
    intel.remove_series_from_collection(collection_id, series_id)


# ------------------------------------------------------------------
# Tags
# ------------------------------------------------------------------

@router.get("/tags")
def list_tags(
    intel: IntelDep,
    response: Response,
    category: str | None = None,
) -> list[dict[str, object]]:
    """Return all tags, optionally filtered by category."""
    items = intel.list_tags(category=category)
    set_list_total_header(response, len(items))
    return items


@router.post("/tags")
def create_tag(body: TagCreateRequest, intel: IntelDep) -> dict[str, object]:
    """Create a new tag."""
    return intel.create_tag(name=body.name, category=body.category, color=body.color)


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int, intel: IntelDep) -> None:
    """Delete a tag."""
    intel.delete_tag(tag_id)


class TagAddRequest(BaseModel):
    tag_id: int = Field(ge=1)


@router.post("/series/{series_id}/tags")
def add_tag_to_series(
    series_id: int,
    body: TagAddRequest,
    intel: IntelDep,
) -> dict[str, object]:
    """Add a tag to a series."""
    return intel.add_tag_to_series(series_id, body.tag_id)


@router.delete("/series/{series_id}/tags/{tag_id}", status_code=204)
def remove_tag_from_series(
    series_id: int,
    tag_id: int,
    intel: IntelDep,
) -> None:
    """Remove a tag from a series."""
    intel.remove_tag_from_series(series_id, tag_id)


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------

@router.get("/search")
def search(
    intel: IntelDep,
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
) -> dict[str, object]:
    """Search across series titles, authors, and descriptions."""
    return intel.search_series(q, page=page, per_page=per_page)


@router.get("/pages/{page_id}/image")
def get_page_image(
    page_id: int,
    service: ServiceDep,
    image_service: ImageDep,
) -> Response:
    """Serve a page image file."""
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


@router.get("/covers/{series_id}")
def get_series_cover(
    series_id: int,
    service: ServiceDep,
    image_service: ImageDep,
) -> Response:
    """Serve a series cover image."""
    payload, media_type = image_service.get_cover_path(service, series_id)
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
