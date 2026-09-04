"""Source-native reader endpoints (spec §4.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from core.errors import AppError
from core.profile_context import require_profile_context
from core.rate_limit import bulk_limit, limiter
from services.bookmark_service import (
    OP_UPSERT,
    BookmarkOp,
    BookmarkService,
    get_bookmark_service,
)
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
BookmarkDep = Annotated[BookmarkService, Depends(get_bookmark_service)]


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


class BookmarkBody(BaseModel):
    """One bookmark on the wire, for both the single POST and the batch.

    The position is the generic anchor triple + ``media_type`` discriminator
    described in ``database.models.Bookmark``: ``anchor_index`` counts pages
    for manga and paragraphs for novels (1-based in both), ``anchor_fraction``
    is 0.0-1.0 *within* that unit, ``anchor_total`` is the unit count the
    client saw (0 = unknown).

    ``page`` is a deprecated alias for ``anchor_index``, kept because the
    shipped web reader still posts it: an old page-only create keeps working
    and lands at offset 0.0 of that page, exactly like the rows the migration
    carried forward.
    """

    client_id: str | None = Field(default=None, max_length=64)
    source_id: str = Field(min_length=1, max_length=64)
    series_key: str = Field(min_length=1, max_length=512)
    chapter_key: str = Field(min_length=1, max_length=512)
    chapter_number: float | None = None
    media_type: str = Field(default="manga", max_length=16)
    anchor_index: int = Field(default=1, ge=1)
    anchor_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    anchor_total: int = Field(default=0, ge=0)
    note: str | None = None
    #: Deprecated: pre-2026-09-05 clients. Used only when anchor_index is unset.
    page: int | None = Field(default=None, ge=1)

    def resolved_index(self) -> int:
        return self.anchor_index if self.anchor_index != 1 else (self.page or 1)


class BookmarkOpRequest(BookmarkBody):
    """One item of an offline flush: a ``BookmarkBody`` plus op + clock.

    ``client_id`` is REQUIRED here (unlike the single POST, which mints one):
    a batch item with no client id has no sync identity, so a retry of the
    same flush would create a duplicate every time.

    The identity fields relax to optional for a delete — a device replaying a
    delete may no longer hold the bookmark's body, and the server re-identifies
    by ``client_id`` alone.
    """

    op: str = Field(default=OP_UPSERT, max_length=16)
    client_id: str = Field(min_length=1, max_length=64)
    source_id: str = Field(default="", max_length=64)
    series_key: str = Field(default="", max_length=512)
    chapter_key: str = Field(default="", max_length=512)
    #: The client's own clock for this change; absent means "server now".
    #: Any offset is accepted and normalized to UTC.
    updated_at: datetime | None = None

    def to_op(self) -> BookmarkOp:
        return BookmarkOp(
            op=self.op,
            client_id=self.client_id,
            source_id=self.source_id,
            series_key=self.series_key,
            chapter_key=self.chapter_key,
            chapter_number=self.chapter_number,
            media_type=self.media_type,
            anchor_index=self.resolved_index(),
            anchor_fraction=self.anchor_fraction,
            anchor_total=self.anchor_total,
            note=self.note,
            updated_at=self.updated_at,
        )


@router.get("/chapter/manifest")
def chapter_manifest(
    service: ReaderDep,
    source: str = Query(..., min_length=1),
    series: str = Query(..., min_length=1),
    chapter: str = Query(..., min_length=1),
) -> dict[str, object]:
    """The download plan for a chapter: ordered page list + prev/next keys."""
    return service.manifest(source, series, chapter)


class BulkManifestRequest(BaseModel):
    """A WINDOW of one series' chapters (spec 2026-09-05 R2/R4).

    The client names the chapters explicitly rather than asking for a numeric
    range: ``chapter_key`` is an opaque connector string and the client already
    holds the ordered list from the series page, so an index range would mean
    both sides parsing keys or agreeing on an ordering that upstream can change
    under them. A window is therefore just "these keys, in this order", and the
    server answers in the same order.
    """

    source_id: str = Field(min_length=1, max_length=64)
    series_key: str = Field(min_length=1, max_length=512)
    chapter_keys: list[str] = Field(min_length=1)


@router.post("/chapters/manifest")
@limiter.limit(bulk_limit)
def chapter_manifest_batch(
    body: BulkManifestRequest,
    service: ReaderDep,
    request: Request,
    response: Response,  # slowapi injects X-RateLimit-* headers into this
) -> dict[str, object]:
    """Download plans for a bounded window of chapters, in one round trip.

    ``{source_id, series_key, max_chapters, requested, ok_count, failed_count,
    items: [{chapter_key, status, manifest, error}]}`` where each ``manifest``
    is byte-identical to what ``GET /reader/chapter/manifest`` serves for that
    chapter (same code path builds both). ``status`` is ``"ok"`` or
    ``"error"``; exactly one of ``manifest`` / ``error`` is non-null per item.

    POST, not GET, because the body is a list of opaque keys that routinely
    contain slashes and percent-encoding — twenty of them do not belong in a
    query string. It is still a read: nothing here mutates.

    Over ``max_chapters`` keys is a 413 ``batch_too_large`` (details carry
    ``max_chapters``), matching ``POST /reader/progress/batch``. Every success
    echoes ``max_chapters`` so a client pages by the server's stride.

    Rate-limited on the ``bulk`` bucket, not ``sources``: one call is worth up
    to ``max_chapters`` upstream scrapes.
    """
    return service.manifest_batch(
        body.source_id, body.series_key, body.chapter_keys
    )


@router.post("/progress", dependencies=[Depends(require_profile_context)])
def save_progress(body: ProgressRequest, service: ProgressDep) -> dict[str, object]:
    """Save reading progress. Applies the furthest-wins merge (never rewinds)."""
    return service.save_one(body.to_input())


# Offline-sync batches are bounded: an unbounded array was parsed fully into
# memory and then hammered the single-writer SQLite (audit finding 12). A
# client with more than this simply sends several batches.
PROGRESS_BATCH_MAX_ITEMS = 200


@router.post("/progress/batch", dependencies=[Depends(require_profile_context)])
def save_progress_batch(
    body: list[ProgressRequest], service: ProgressDep
) -> dict[str, object]:
    """Offline-sync catch-up: an array of progress pushes, merged in one
    transaction. Capped at ``PROGRESS_BATCH_MAX_ITEMS`` items."""
    if len(body) > PROGRESS_BATCH_MAX_ITEMS:
        raise AppError(
            "Too many progress items in one batch.",
            code="batch_too_large",
            status_code=413,
            details={
                "max_items": PROGRESS_BATCH_MAX_ITEMS,
                "received": len(body),
            },
        )
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


# Same cap and the same 413 shape as ``/reader/progress/batch``: an unbounded
# array is parsed fully into memory and then hammers the single-writer SQLite.
BOOKMARK_BATCH_MAX_ITEMS = 200


@router.post("/bookmark", dependencies=[Depends(require_profile_context)])
def create_bookmark(body: BookmarkBody, service: BookmarkDep) -> dict[str, object]:
    """Bookmark the current position, in one action (design §5).

    Returns the stored bookmark, including the server-minted ``client_id``
    when the client did not supply one — a client that wants to delete this
    bookmark through the offline batch later must keep that id.

    409 ``bookmark_deleted`` if the ``client_id`` is already tombstoned: this
    endpoint speaks for one deliberate user action, so silently doing nothing
    would show a bookmark that then vanishes on the next refresh.
    """
    return service.add_bookmark(
        client_id=body.client_id,
        source_id=body.source_id,
        series_key=body.series_key,
        chapter_key=body.chapter_key,
        chapter_number=body.chapter_number,
        media_type=body.media_type,
        anchor_index=body.resolved_index(),
        anchor_fraction=body.anchor_fraction,
        anchor_total=body.anchor_total,
        note=body.note,
    )


@router.post("/bookmarks/batch", dependencies=[Depends(require_profile_context)])
def sync_bookmarks_batch(
    body: list[BookmarkOpRequest], service: BookmarkDep
) -> dict[str, object]:
    """Offline-sync catch-up for bookmarks: creates, edits and deletes.

    Modelled on ``POST /reader/progress/batch`` (one transaction, one commit,
    the same 413 over ``BOOKMARK_BATCH_MAX_ITEMS``) and merged by the OPPOSITE
    rules — bookmarks are user-created objects, not a furthest-wins scalar.
    See ``services.bookmark_service.decide``; in short, a tombstone is
    terminal, so a stale device replaying its create outbox can never
    resurrect a bookmark deleted elsewhere.

    Per item: ``{client_id, op, status, bookmark}`` where ``status`` is
    ``created`` / ``updated`` / ``tombstoned`` / ``already_deleted`` /
    ``stale`` / ``rejected_deleted``. A refused item is reported, never fatal:
    a flush that 400s as a whole leaves the device unable to make progress at
    all.
    """
    if len(body) > BOOKMARK_BATCH_MAX_ITEMS:
        raise AppError(
            "Too many bookmark items in one batch.",
            code="batch_too_large",
            status_code=413,
            details={
                "max_items": BOOKMARK_BATCH_MAX_ITEMS,
                "received": len(body),
            },
        )
    return service.apply_batch([item.to_op() for item in body])


@router.get("/bookmarks")
def list_bookmarks(
    service: BookmarkDep,
    response: Response,
    source: str | None = None,
    series: str | None = None,
    since: datetime | None = Query(
        None,
        description=(
            "Delta pull: only bookmarks changed strictly after this instant, "
            "OLDEST first so a client can page forward on the last updated_at."
        ),
    ),
    include_deleted: bool = Query(
        False, description="Include tombstones, so a device learns about deletes."
    ),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, object]]:
    """The Bookmarks screen, and the pull half of sync.

    Each item carries everything the screen needs without a second round trip:
    ``series_title``, ``chapter_number``, ``position_fraction`` (0.0-1.0 through
    the chapter, or null when the client never recorded a unit count) and, for
    novels, ``snippet`` — the cached sanitized text at that exact position.
    """
    items = service.list_bookmarks(
        source_id=source,
        series_key=series,
        since=since,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
    set_list_total_header(response, len(items))
    return items


@router.delete(
    "/bookmarks/{bookmark_id}",
    status_code=204,
    dependencies=[Depends(require_profile_context)],
)
def delete_bookmark(bookmark_id: int, service: BookmarkDep) -> None:
    """Tombstone one bookmark by row id. The row is never removed."""
    service.delete_bookmark(bookmark_id)
