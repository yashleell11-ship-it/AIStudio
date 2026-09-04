"""The per-profile library, source-native (spec §3.2, §4.2, §5.2).

A series is in a profile's library iff a ``followed_series`` row exists for
``(user_id, profile_id, source_id, series_key)``. Replaces the old
``library_service`` + ``library_intelligence_service`` catalog stack.

Everything here is scoped to the request's ``(user_id, profile_id)``. Cross
-profile visibility is none.
"""

from __future__ import annotations

import json
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.orm import Session, defer

from connectors.ids import fully_unquote
from core.config import get_settings
from core.connector_directory import descriptor_for_source
from core.content_rating import (
    TRACKER_RATING_MATURE,
    rating_from_genres,
    resolve_mature_gate,
    resolve_tracker_rating,
)
from core.errors import AppError
from core.profile_context import ProfileContext, resolve_profile_context
from core.time_utils import utcnow
from database.models import (
    ChapterProgress,
    Collection,
    CollectionSeries,
    FollowedSeries,
    ProfileSeriesTag,
    SourceSeriesCache,
    Tag,
)
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service
from services.reading_stats_service import ReadingStatsService
from services.source_cache_service import SourceCacheService

#: Row-value ``IN`` list size. SQLite's default ``SQLITE_MAX_VARIABLE_NUMBER``
#: is 32766 on modern builds but was 999 for years, and each pair here binds
#: two parameters — chunking keeps the statement inside even the old ceiling
#: and keeps the number of distinct prepared statements small.
_IN_CHUNK = 400

READING_STATUSES = {
    "unread",
    "reading",
    "completed",
    "on_hold",
    "dropped",
    "plan_to_read",
}


def _loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


class FollowedSeriesService:
    def __init__(
        self,
        db: Session,
        browse: BrowseService,
        *,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        self._browse = browse
        self._cache = SourceCacheService(db, browse)
        self._user_id = user_id
        self._profile_id = profile_id
        # Resolved once per request. The gate is a property of the (user,
        # profile) pair, which cannot change mid-request, and every list path
        # asked for it again per call — `statistics` alone resolved it three
        # times, each a `Session.get(ReadingProfile, ...)`.
        self._gate_cache: bool | None = None

    # --- helpers -------------------------------------------------------

    def _require_owner(self) -> None:
        if self._user_id is None:
            raise AppError(
                "Authentication is required.",
                code="auth_required",
                status_code=401,
            )

    def _scope(self, stmt):
        stmt = stmt.where(FollowedSeries.user_id == self._user_id)
        if self._profile_id is None:
            return stmt.where(FollowedSeries.profile_id.is_(None))
        return stmt.where(FollowedSeries.profile_id == self._profile_id)

    #: ``known_chapters`` holds a series' whole chapter list — kilobytes per
    #: row. The paths that scan the profile's *entire* followed set (list,
    #: statistics, recommendations, the recently-updated strip) never read it,
    #: yet SQLite still had to read every blob off disk and SQLAlchemy still
    #: had to build a Python string for each: ~5 MB of text per request for a
    #: 300-series library. Deferring it makes those statements fetch the small
    #: columns only. Any path that *does* need the array (``get_detail``,
    #: ``follow``, ``patch``) simply does not apply this option.
    _NO_CHAPTERS = (defer(FollowedSeries.known_chapters),)

    def _progress_scope(self, stmt):
        """``_scope`` for ``chapter_progress``.

        Reading position is per-``(user_id, profile_id)`` exactly like a follow
        is; a statement that filters only on ``user_id`` merges the account's
        profiles together and resumes one reader at another's page.
        """
        stmt = stmt.where(ChapterProgress.user_id == self._user_id)
        if self._profile_id is None:
            return stmt.where(ChapterProgress.profile_id.is_(None))
        return stmt.where(ChapterProgress.profile_id == self._profile_id)

    def _require_profile(self) -> int:
        """The active profile id, or a clean 400.

        Profile-owned rows key on ``(user_id, profile_id, ...)`` with a NOT NULL
        ``profile_id``, so the unscoped bucket has no row to address: a
        ``Session.get()`` with a null key component is not a lookup, and an
        insert would surface as an IntegrityError 500.
        """
        self._require_owner()
        if self._profile_id is None:
            raise AppError(
                "An active profile is required for this action.",
                code="profile_required",
                status_code=400,
            )
        return self._profile_id

    def _gate_open(self) -> bool:
        if self._gate_cache is None:
            self._gate_cache = resolve_mature_gate(
                self._db, self._profile_id, self._user_id
            )
        return self._gate_cache

    def _descriptor(self, source_id: str):
        # Was a linear scan over a freshly *rebuilt* descriptor list, run once
        # per followed row; see core.connector_directory.
        return descriptor_for_source(source_id)

    def _rating(self, row: FollowedSeries) -> str:
        return resolve_tracker_rating(row, self._descriptor(row.source_id))

    def _visible(self, rows: list[FollowedSeries]) -> list[FollowedSeries]:
        if self._gate_open():
            return rows
        return [r for r in rows if self._rating(r) != TRACKER_RATING_MATURE]

    def _get_owned(self, followed_id: int) -> FollowedSeries:
        """Fetch a follow by id, or 404.

        The profile predicate is **unconditional**: ``None`` means the unscoped
        bucket, exactly as ``_scope`` reads it. Guarding it on
        ``self._profile_id is not None`` would let a caller that simply omits
        ``X-Profile-Id`` (which ``resolve_profile_context`` leniently allows)
        read and mutate any of the account's rows across every profile.
        """
        row = self._db.get(FollowedSeries, followed_id)
        if (
            row is None
            or row.user_id != self._user_id
            or row.profile_id != self._profile_id
        ):
            raise AppError(
                "Series not found.", code="series_not_found", status_code=404
            )
        return row

    # --- CRUD --------------------------------------------------------

    def follow(self, source_id: str, series_key: str) -> dict[str, Any]:
        self._require_profile()
        series_key = fully_unquote(series_key)
        existing = self._db.execute(
            self._scope(
                select(FollowedSeries).where(
                    FollowedSeries.source_id == source_id,
                    FollowedSeries.series_key == series_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return self.serialize(existing)

        # Follows are the row count the scheduled sweep walks (a live upstream
        # fetch per row, every interval), so they are capped per profile —
        # uncapped follows let one profile turn the sweep into an hours-long
        # network job for the whole instance (audit finding 14).
        max_follows = get_settings().max_follows_per_profile
        if max_follows > 0:
            count = int(
                self._db.execute(
                    self._scope(select(func.count()).select_from(FollowedSeries))
                ).scalar_one()
                or 0
            )
            if count >= max_follows:
                raise AppError(
                    "Follow limit reached for this profile.",
                    code="follow_limit_reached",
                    status_code=400,
                    details={"max_follows": max_follows},
                )

        meta: dict[str, Any] = {}
        chapters: list[dict[str, Any]] = []
        try:
            meta = self._browse.get_series(source_id, series_key)
            chapters = self._browse.get_chapters(source_id, series_key)
        except Exception:  # noqa: BLE001 - follow must work while a source is down
            meta = {}

        content_rating = rating_from_genres(tuple(meta.get("genres") or ()))
        row = FollowedSeries(
            user_id=self._user_id,
            profile_id=self._profile_id,
            source_id=source_id,
            series_key=series_key,
            title=str(meta.get("title") or series_key),
            cover_url=meta.get("cover_url"),
            content_rating=content_rating,
            known_chapters=json.dumps(
                [
                    {
                        "key": c.get("id"),
                        "number": c.get("number"),
                        "title": c.get("title"),
                        "published_at": c.get("release_date"),
                    }
                    for c in chapters
                ]
            ),
            last_checked_at=utcnow() if chapters else None,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        if meta or chapters:
            self._cache.write_through(source_id, series_key, meta, chapters)
        return self.serialize(row)

    def unfollow(self, followed_id: int) -> None:
        self._require_owner()
        row = self._get_owned(followed_id)
        self._db.delete(row)
        self._db.commit()

    def patch(self, followed_id: int, **changes: Any) -> dict[str, Any]:
        self._require_owner()
        row = self._get_owned(followed_id)
        if "is_favorite" in changes and changes["is_favorite"] is not None:
            row.is_favorite = bool(changes["is_favorite"])
        if changes.get("reading_status") is not None:
            status = str(changes["reading_status"])
            if status not in READING_STATUSES:
                raise AppError(
                    f"Unknown reading_status '{status}'.",
                    code="invalid_reading_status",
                    status_code=422,
                )
            row.reading_status = status
        if "notify" in changes and changes["notify"] is not None:
            row.notify = bool(changes["notify"])
        if "mature_override" in changes and changes["mature_override"] is not None:
            row.mature_override = bool(changes["mature_override"])
        if changes.get("sort_order") is not None:
            row.sort_order = int(changes["sort_order"])
        row.updated_at = utcnow()
        self._db.commit()
        self._db.refresh(row)
        return self.serialize(row)

    # --- reads ------------------------------------------------------

    def list_series(
        self,
        *,
        page: int = 1,
        per_page: int = 40,
        sort: str = "title",
        search: str | None = None,
        reading_status: str | None = None,
        is_favorite: bool | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        self._require_owner()
        stmt = self._scope(select(FollowedSeries).options(*self._NO_CHAPTERS))
        if reading_status:
            stmt = stmt.where(FollowedSeries.reading_status == reading_status)
        if is_favorite is not None:
            stmt = stmt.where(FollowedSeries.is_favorite == is_favorite)
        if search:
            stmt = stmt.where(FollowedSeries.title.ilike(f"%{search.strip()}%"))

        rows = self._visible(list(self._db.execute(stmt).scalars().all()))

        reverse = sort.startswith("-")
        key = sort.lstrip("-")
        if key in ("title", "sort_title"):
            rows.sort(key=lambda r: (r.title or "").lower(), reverse=reverse)
        elif key == "sort_order":
            rows.sort(key=lambda r: r.sort_order, reverse=reverse)
        elif key in ("updated_at", "recently_updated"):
            rows.sort(
                key=lambda r: r.last_checked_at or r.created_at, reverse=True
            )
        elif key in ("created_at", "recently_added"):
            rows.sort(key=lambda r: r.created_at, reverse=True)

        total = len(rows)
        start = (page - 1) * per_page
        window = rows[start : start + per_page]
        return {
            "items": [
                self.serialize(r, include_chapters=False) for r in window
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "page_size": per_page,
            "has_next": start + per_page < total,
            "has_more": start + per_page < total,
            "total_pages": max(1, -(-total // per_page)),
        }

    def get_detail(self, followed_id: int) -> dict[str, Any]:
        self._require_owner()
        row = self._get_owned(followed_id)
        if not self._gate_open() and self._rating(row) == TRACKER_RATING_MATURE:
            raise AppError(
                "Series not found.", code="series_not_found", status_code=404
            )
        payload = self.serialize(row)
        try:
            meta = self._cache.get_series_meta(row.source_id, row.series_key)
            payload["description"] = meta.get("description")
            payload["author"] = meta.get("author")
            payload["genres"] = meta.get("genres")
            payload["chapters"] = meta.get("chapters")
        except Exception:  # noqa: BLE001
            payload["chapters"] = _loads(row.known_chapters) or []
        # Progress overlay — scoped to (user_id, profile_id) like everything
        # else. Filtering on user_id alone merges two profiles that follow the
        # same series into one overlay and resumes each at the other's page.
        prog = self._db.execute(
            self._progress_scope(
                select(ChapterProgress).where(
                    ChapterProgress.source_id == row.source_id,
                    ChapterProgress.series_key == row.series_key,
                )
            )
        ).scalars().all()
        payload["progress"] = {
            p.chapter_key: {
                "last_page": p.last_page,
                "is_completed": bool(p.is_completed),
            }
            for p in prog
        }
        return payload

    def continue_reading(self, limit: int = 10) -> list[dict[str, Any]]:
        """Most recent unfinished chapter per followed series, for this profile.

        Two things this must not do, both of which it used to:

        * read ``chapter_progress`` filtered on ``user_id`` alone — that shows
          one profile the account's other profiles' reading positions;
        * read ``chapter_progress`` *directly* — with no ``followed_series`` row
          in the statement there is nothing to resolve a rating against, so the
          18+ gate never ran and a mature series surfaced on a gated profile's
          home strip. The inner join is therefore load-bearing, not an
          optimisation: it both restricts the strip to series this profile
          follows and supplies the row ``_rating`` resolves the gate from.

        The "one row per series" collapse happens in SQL rather than in Python.
        It used to hydrate **every** unfinished ``chapter_progress`` row in the
        profile — with its matching ``followed_series`` row, both as full ORM
        entities — and then throw all but ten away: 6,000 progress rows cost
        318 ms to produce a ten-item strip, and the query grew with every
        chapter the owner ever opened. A window function picks the latest
        unfinished chapter per series inside the database, so the number of
        rows crossing into Python is the number of *series*, not chapters, and
        the columns fetched are the seven this payload prints.
        """
        self._require_owner()
        # (last_read_at DESC, id DESC): the old loop kept whichever row the
        # database happened to return first within a last_read_at tie, so the
        # tiebreak is new — but it is a *defined* one replacing an arbitrary
        # one, and it matches the id ordering an insert sequence gives.
        newest_first = (ChapterProgress.last_read_at.desc(), ChapterProgress.id.desc())
        ranked = (
            self._progress_scope(
                self._scope(
                    select(
                        ChapterProgress.source_id.label("source_id"),
                        ChapterProgress.series_key.label("series_key"),
                        ChapterProgress.chapter_key.label("chapter_key"),
                        ChapterProgress.chapter_number.label("chapter_number"),
                        ChapterProgress.last_page.label("last_page"),
                        ChapterProgress.page_count.label("page_count"),
                        ChapterProgress.last_read_at.label("last_read_at"),
                        # Carried so the 18+ gate can be resolved without a
                        # second lookup; the join itself is load-bearing (it is
                        # what restricts the strip to *followed* series).
                        FollowedSeries.mature_override.label("mature_override"),
                        FollowedSeries.content_rating.label("content_rating"),
                        func.row_number()
                        .over(
                            partition_by=(
                                ChapterProgress.source_id,
                                ChapterProgress.series_key,
                            ),
                            order_by=newest_first,
                        )
                        .label("rank"),
                    ).join(
                        FollowedSeries,
                        and_(
                            FollowedSeries.user_id == ChapterProgress.user_id,
                            FollowedSeries.profile_id == ChapterProgress.profile_id,
                            FollowedSeries.source_id == ChapterProgress.source_id,
                            FollowedSeries.series_key == ChapterProgress.series_key,
                        ),
                    )
                )
            )
            .where(ChapterProgress.is_completed.is_(False))
            .subquery()
        )

        gate_open = self._gate_open()
        stmt = (
            select(ranked)
            .where(ranked.c.rank == 1)
            .order_by(ranked.c.last_read_at.desc())
        )
        if gate_open:
            # Nothing can be dropped after the fact, so the database can do the
            # cutting too. With the gate shut the mature rows are removed below
            # and the limit has to be applied after that; the row count is then
            # bounded by the profile's follow count, not its history.
            stmt = stmt.limit(limit)

        out: list[dict[str, Any]] = []
        for row in self._db.execute(stmt).all():
            if not gate_open and self._rating(row) == TRACKER_RATING_MATURE:
                continue
            out.append(
                {
                    "source_id": row.source_id,
                    "series_key": row.series_key,
                    "chapter_key": row.chapter_key,
                    "chapter_number": row.chapter_number,
                    "last_page": row.last_page,
                    "page_count": row.page_count,
                    "last_read_at": row.last_read_at.isoformat()
                    if row.last_read_at
                    else None,
                }
            )
            if len(out) >= limit:
                break
        return out

    def recently_updated(self, limit: int = 10) -> list[dict[str, Any]]:
        self._require_owner()
        rows = self._db.execute(
            self._scope(select(FollowedSeries).options(*self._NO_CHAPTERS))
            .where(FollowedSeries.last_checked_at.is_not(None))
            .order_by(FollowedSeries.last_checked_at.desc())
            .limit(limit)
        ).scalars().all()
        return [
            self.serialize(r, include_chapters=False)
            for r in self._visible(list(rows))
        ]

    def statistics(
        self, *, days: int = 30, tz_offset_minutes: int = 0
    ) -> dict[str, Any]:
        """Library shape + what ``reading_sessions`` actually recorded.

        The first four keys are the original payload and keep their meaning so
        clients can migrate at their own pace. Everything else comes from
        :class:`~services.reading_stats_service.ReadingStatsService`, which owns
        the session aggregation (and its own ``(user_id, profile_id)`` scoping
        and 18+ gating) rather than growing another set of scope helpers here.
        """
        self._require_owner()
        rows = self._visible(
            list(
                self._db.execute(
                    self._scope(select(FollowedSeries).options(*self._NO_CHAPTERS))
                ).scalars().all()
            )
        )
        by_status: dict[str, int] = {}
        for r in rows:
            by_status[r.reading_status] = by_status.get(r.reading_status, 0) + 1
        # Profile-scoped like every other field in this payload — counting the
        # whole account here made one profile's number jump when a sibling read.
        stats = ReadingStatsService(
            self._db,
            user_id=self._user_id,
            profile_id=self._profile_id,
            gate_open=self._gate_open(),
            tz_offset_minutes=tz_offset_minutes,
        )
        payload: dict[str, Any] = {
            "followed_total": len(rows),
            "favorites": sum(1 for r in rows if r.is_favorite),
            "by_reading_status": by_status,
            "chapters_completed": stats.chapters_completed(),
        }
        payload.update(stats.build(days))
        return payload

    def recommendations(self, limit: int = 10) -> list[dict[str, Any]]:
        """Simple genre-similarity over the followed set (spec §5.2)."""
        self._require_owner()
        rows = self._visible(
            list(
                self._db.execute(
                    self._scope(select(FollowedSeries).options(*self._NO_CHAPTERS))
                ).scalars().all()
            )
        )
        # One statement, not one per followed series. This was a
        # ``Session.get`` inside the loop — 300 follows meant 300 round trips
        # (the endpoint issued 308 queries and took 191 ms) to build a
        # ten-entry genre histogram.
        genre_counts: dict[str, int] = {}
        keys = [(r.source_id, r.series_key) for r in rows]
        for chunk_start in range(0, len(keys), _IN_CHUNK):
            chunk = keys[chunk_start : chunk_start + _IN_CHUNK]
            genre_blobs = self._db.execute(
                select(SourceSeriesCache.genres).where(
                    tuple_(
                        SourceSeriesCache.source_id, SourceSeriesCache.series_key
                    ).in_(chunk)
                )
            ).scalars().all()
            for blob in genre_blobs:
                for g in _loads(blob) or []:
                    name = str(g).lower()
                    genre_counts[name] = genre_counts.get(name, 0) + 1
        # Without an external catalog there is nothing to recommend beyond the
        # followed set; return the top genres so the client can drive a browse.
        top = sorted(genre_counts.items(), key=lambda kv: kv[1], reverse=True)
        return [{"genre": g, "weight": n} for g, n in top[:limit]]

    def search(self, q: str, *, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        return self.list_series(search=q, page=page, per_page=per_page)

    # --- collections ----------------------------------------------

    def _collection_scope(self, stmt):
        stmt = stmt.where(Collection.user_id == self._user_id)
        if self._profile_id is None:
            return stmt.where(Collection.profile_id.is_(None))
        return stmt.where(Collection.profile_id == self._profile_id)

    def list_collections(self) -> list[dict[str, Any]]:
        self._require_owner()
        rows = self._db.execute(
            self._collection_scope(select(Collection)).order_by(Collection.sort_order)
        ).scalars().all()
        # ``series_count`` used to come from ``len(row.series)``, which lazy
        # -loads the whole membership relationship — one SELECT per collection,
        # returning every member row, to print a number. One GROUP BY answers
        # them all.
        counts = dict(
            self._db.execute(
                select(
                    CollectionSeries.collection_id, func.count()
                )
                .where(
                    CollectionSeries.collection_id.in_([c.id for c in rows])
                )
                .group_by(CollectionSeries.collection_id)
            ).all()
        )
        return [
            self._serialize_collection(c, series_count=counts.get(c.id, 0))
            for c in rows
        ]

    def create_collection(
        self, *, name: str, description: str | None = None
    ) -> dict[str, Any]:
        self._require_profile()
        row = Collection(
            user_id=self._user_id,
            profile_id=self._profile_id,
            name=name.strip(),
            description=description,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return self._serialize_collection(row)

    def get_collection(self, collection_id: int) -> dict[str, Any]:
        self._require_owner()
        row = self._owned_collection(collection_id)
        # Production sessions are built with ``expire_on_commit=False``, so a
        # ``series`` collection loaded earlier in this same request survives
        # the commit that changed membership and would serialize one write
        # behind. ``add_series_to_collection`` does exactly that: it reads
        # ``row.series`` for the new ``sort_order``, inserts, commits, then
        # calls this method. Expire the relationship so the reads below come
        # from the database rather than the identity map.
        self._db.expire(row, ["series"])
        payload = self._serialize_collection(row)
        payload["series"] = [
            {
                "source_id": cs.source_id,
                "series_key": cs.series_key,
                "sort_order": cs.sort_order,
            }
            for cs in sorted(row.series, key=lambda x: x.sort_order)
        ]
        return payload

    def update_collection(self, collection_id: int, **changes: Any) -> dict[str, Any]:
        self._require_owner()
        row = self._owned_collection(collection_id)
        if changes.get("name") is not None:
            row.name = str(changes["name"]).strip()
        if "description" in changes and changes["description"] is not None:
            row.description = changes["description"]
        if changes.get("sort_order") is not None:
            row.sort_order = int(changes["sort_order"])
        self._db.commit()
        self._db.refresh(row)
        return self._serialize_collection(row)

    def delete_collection(self, collection_id: int) -> None:
        self._require_owner()
        self._db.delete(self._owned_collection(collection_id))
        self._db.commit()

    def add_series_to_collection(
        self, collection_id: int, source_id: str, series_key: str
    ) -> dict[str, Any]:
        self._require_owner()
        row = self._owned_collection(collection_id)
        series_key = fully_unquote(series_key)
        exists = self._db.get(
            CollectionSeries, (collection_id, source_id, series_key)
        )
        if exists is None:
            self._db.add(
                CollectionSeries(
                    collection_id=collection_id,
                    source_id=source_id,
                    series_key=series_key,
                    sort_order=len(row.series),
                )
            )
            self._db.commit()
        return self.get_collection(collection_id)

    def remove_series_from_collection(
        self, collection_id: int, source_id: str, series_key: str
    ) -> None:
        self._require_owner()
        self._owned_collection(collection_id)
        row = self._db.get(
            CollectionSeries, (collection_id, source_id, fully_unquote(series_key))
        )
        if row is not None:
            self._db.delete(row)
            self._db.commit()

    def _owned_collection(self, collection_id: int) -> Collection:
        """Fetch a collection by id, or 404.

        Collections are *created* with a ``profile_id`` and *listed* through
        ``_collection_scope``, so a sibling profile cannot see one — but with
        only the ``user_id`` check here it could still rename, empty or
        ``DELETE`` one by guessing a small integer. The predicate must match
        ``_collection_scope`` exactly, ``None`` bucket included.
        """
        row = self._db.get(Collection, collection_id)
        if (
            row is None
            or row.user_id != self._user_id
            or row.profile_id != self._profile_id
        ):
            raise AppError(
                "Collection not found.", code="not_found", status_code=404
            )
        return row

    @staticmethod
    def _serialize_collection(
        row: Collection, *, series_count: int | None = None
    ) -> dict[str, Any]:
        """``series_count`` supplied by the caller avoids the relationship load;
        omitted, it falls back to the relationship (single-collection paths,
        where the membership is usually loaded already)."""
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "cover_url": row.cover_url,
            "sort_order": row.sort_order,
            "series_count": len(row.series) if series_count is None else series_count,
        }

    # --- tags -----------------------------------------------------

    def _tag_scope(self, stmt):
        stmt = stmt.where(Tag.user_id == self._user_id)
        if self._profile_id is None:
            return stmt.where(Tag.profile_id.is_(None))
        return stmt.where(Tag.profile_id == self._profile_id)

    def _owned_tag(self, tag_id: int) -> Tag:
        row = self._db.get(Tag, tag_id)
        if (
            row is None
            or row.user_id != self._user_id
            or row.profile_id != self._profile_id
        ):
            raise AppError("Tag not found.", code="not_found", status_code=404)
        return row

    @staticmethod
    def _serialize_tag(row: Tag) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "category": row.category,
            "color": row.color,
        }

    def list_tags(self, *, category: str | None = None) -> list[dict[str, Any]]:
        self._require_owner()
        stmt = self._tag_scope(select(Tag))
        if category:
            stmt = stmt.where(Tag.category == category)
        rows = self._db.execute(stmt.order_by(Tag.name)).scalars().all()
        return [self._serialize_tag(t) for t in rows]

    def create_tag(
        self, *, name: str, category: str = "custom", color: str | None = None
    ) -> dict[str, Any]:
        """Create (or return) this profile's tag of that name.

        The case-insensitive dedupe is scope-local: it used to search every
        row in the table, so a colliding name handed the caller a tag belonging
        to another account — a read of somebody else's data and a write that
        then attached *their* row to *this* profile's series.
        """
        profile_id = self._require_profile()
        name = name.strip()
        existing = self._db.execute(
            self._tag_scope(select(Tag).where(func.lower(Tag.name) == name.lower()))
        ).scalar_one_or_none()
        if existing is not None:
            return self._serialize_tag(existing)
        row = Tag(
            user_id=self._user_id,
            profile_id=profile_id,
            name=name,
            category=category,
            color=color,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return self._serialize_tag(row)

    def delete_tag(self, tag_id: int) -> None:
        self._require_owner()
        self._db.delete(self._owned_tag(tag_id))
        self._db.commit()

    def add_tag_to_series(
        self, source_id: str, series_key: str, tag_id: int
    ) -> dict[str, Any]:
        profile_id = self._require_profile()
        self._owned_tag(tag_id)
        series_key = fully_unquote(series_key)
        pk = (self._user_id, profile_id, source_id, series_key, tag_id)
        if self._db.get(ProfileSeriesTag, pk) is None:
            self._db.add(
                ProfileSeriesTag(
                    user_id=self._user_id,
                    profile_id=profile_id,
                    source_id=source_id,
                    series_key=series_key,
                    tag_id=tag_id,
                )
            )
            self._db.commit()
        return {"source_id": source_id, "series_key": series_key, "tag_id": tag_id}

    def remove_tag_from_series(
        self, source_id: str, series_key: str, tag_id: int
    ) -> None:
        profile_id = self._require_profile()
        row = self._db.get(
            ProfileSeriesTag,
            (self._user_id, profile_id, source_id, fully_unquote(series_key), tag_id),
        )
        if row is not None:
            self._db.delete(row)
            self._db.commit()

    # --- serialization -------------------------------------------

    def serialize(
        self, row: FollowedSeries, *, include_chapters: bool = True
    ) -> dict[str, Any]:
        """One followed series as JSON.

        ``include_chapters=False`` omits the ``known_chapters`` array while
        keeping ``chapter_count``. That array is the series' *entire* chapter
        list — 17 KB for a 200-chapter series — and the list endpoints embedded
        it once per row: one page of 40 followed series measured 832 KB, of
        which 830 KB was chapter arrays no list view draws (the web client
        declares the field and reads only ``chapter_count``; the Flutter model
        defaults it to ``const []`` when absent). The detail endpoint, follow
        and patch still send it, so nothing that had the data loses it.

        ``known_chapters`` is parsed once either way: this used to call
        ``json.loads`` on the blob twice per row — once for the array, once to
        measure it for ``chapter_count``.
        """
        chapters = _loads(row.known_chapters) or []
        payload: dict[str, Any] = {
            "id": row.id,
            "source_id": row.source_id,
            "series_key": row.series_key,
            "title": row.title,
            "cover_url": row.cover_url
            or f"/sources/{row.source_id}/series/{quote(row.series_key, safe='')}/cover",
            "is_favorite": bool(row.is_favorite),
            "reading_status": row.reading_status,
            "notify": bool(row.notify),
            "sort_order": row.sort_order,
            "content_rating": row.content_rating,
            "rating": self._rating(row),
            "mature_override": row.mature_override,
            "chapter_count": len(chapters),
            "last_checked_at": row.last_checked_at.isoformat()
            if row.last_checked_at
            else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        if include_chapters:
            payload["known_chapters"] = chapters
        return payload


def get_followed_series_service(
    db: Annotated[Session, Depends(get_db)],
    browse: Annotated[BrowseService, Depends(get_browse_service)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> FollowedSeriesService:
    return FollowedSeriesService(
        db, browse, user_id=ctx.user_id, profile_id=ctx.profile_id
    )
