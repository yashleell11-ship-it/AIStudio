"""The NAS browse mode: what a given source has already put on this server.

Every source connector gets one extra catalog view, alongside its own Latest /
Popular / Rating modes, listing the series whose chapters have actually been
downloaded *from that source*. It answers "what do I already have from here",
which previously required leaving the source browser entirely.

The listing is assembled from ``downloads`` rows rather than from disk. The
rows carry the source and the source's own series id, so an entry links back
into the same ``/sources/{id}/series/{series_id}`` route as any browsed series
-- walking the download directory would give filenames with no way home.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectors.models import PaginatedSeriesList, Series
from database.models import Download

#: Downloads that have actually landed. A queued or failed row is not something
#: the reader has, so it must not appear in a listing that claims otherwise.
COMPLETED = "completed"

#: Page size for the NAS view. Independent of whatever the connector uses for
#: its remote catalog -- this one is a local query and pages cheaply.
PAGE_SIZE = 24


@dataclass(frozen=True, slots=True)
class NasSeriesRow:
    """One downloaded series, as grouped out of the downloads table."""

    series_id: str
    title: str
    chapter_count: int


def nas_series_rows(
    db: Session,
    *,
    source_id: str,
    user_id: int | None,
    profile_id: int | None,
    page: int,
    page_size: int = PAGE_SIZE,
    query: str | None = None,
) -> tuple[list[NasSeriesRow], int]:
    """Downloaded series for ``source_id``, and the total across all pages.

    Scoped to (user, profile) exactly like library membership: a download
    belongs to the profile that queued it, so another profile on the same
    account must not see it here. Missing context returns nothing rather than
    everything -- an unscoped listing would leak one reader's shelf to another.

    ``query`` filters by title here rather than being handed to the connector:
    in this mode the catalog is local, and passing the search upstream would
    return series this server does not have. Without it, typing in the search
    box while NAS is selected would silently do nothing.

    Ordered by title so the view is stable between calls; the downloads table
    has no per-series timestamp to sort by that would not shuffle a series
    every time one more chapter of it finishes.
    """
    if user_id is None:
        return [], 0

    scope = [
        Download.source == source_id,
        Download.status == COMPLETED,
        Download.user_id == user_id,
        Download.profile_id == profile_id,
    ]
    if query:
        scope.append(Download.series_title.ilike(f"%{query}%"))

    # One row per series, not per chapter: a series with 200 downloaded
    # chapters is one entry in a catalog listing.
    grouped = (
        select(
            Download.series_id,
            func.max(Download.series_title).label("title"),
            func.count(func.distinct(Download.chapter_id)).label("chapter_count"),
        )
        .where(*scope)
        .group_by(Download.series_id)
    )

    total = db.execute(
        select(func.count()).select_from(grouped.subquery())
    ).scalar_one()

    offset = max(0, (page - 1) * page_size)
    rows = db.execute(
        grouped.order_by(func.lower(func.max(Download.series_title)))
        .limit(page_size)
        .offset(offset)
    ).all()

    return [
        NasSeriesRow(
            series_id=row.series_id,
            title=row.title or row.series_id,
            chapter_count=int(row.chapter_count or 0),
        )
        for row in rows
    ], int(total)


def nas_listing(
    db: Session,
    *,
    source_id: str,
    user_id: int | None,
    profile_id: int | None,
    page: int,
    page_size: int = PAGE_SIZE,
    query: str | None = None,
) -> PaginatedSeriesList:
    """The NAS view as a ``PaginatedSeriesList``, shaped like any catalog page.

    Deliberately the same type a connector returns, so the route, the
    serializer and every client render it with the code they already have --
    the only difference is where the rows came from.
    """
    rows, total = nas_series_rows(
        db,
        source_id=source_id,
        user_id=user_id,
        profile_id=profile_id,
        page=page,
        page_size=page_size,
        query=query,
    )

    return PaginatedSeriesList(
        items=[
            Series(
                id=row.series_id,
                title=row.title,
                # The count is what is on this server, not what the source
                # publishes -- the whole point of the view.
                chapter_count=row.chapter_count,
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
