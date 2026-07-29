"""Library Intelligence service.

Handles global search, metadata indexing, similar series, recommendations,
continue reading, reading history, favorites, collections, smart tags,
statistics, recently added/updated.

Production-ready features:
- Relevance-ranked search with BM25 + custom boost
- Diverse, engagement-weighted recommendations via SQL
- Pre-aggregated statistics (streaks, velocity, reading calendar)
- Efficient collections with smart-filter support and pagination
- Metadata completeness scoring
- Query-optimized N+1 reduction via subqueries and batch counts
"""

from __future__ import annotations

import heapq
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from core.time_utils import utcnow
from sqlalchemy import (
    and_,
    case,
    cast,
    func,
    or_,
    select,
    text,
    tuple_,
)
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
)

from core.content_rating import (
    is_mature_rating,
    mature_rating_predicate,
    resolve_mature_gate,
)
from core.errors import AppError
from core.library_authz import series_read_allowed
from core.profile_context import ProfileContext, resolve_profile_context
from database.models import (
    Chapter,
    ChapterProgress,
    ChapterText,
    Collection,
    CollectionSeries,
    Library,
    OcrJob,
    Page,
    ReadingProgress,
    ReadingSession,
    Series,
    SeriesTag,
    SeriesTracker,
    SourceChapterLink,
    Tag,
    UserSeriesState,
)
from database.session import get_db
from utils.path_utils import natural_sort_key

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Sort helpers (repeated here to avoid cross-import cycle)
# ------------------------------------------------------------------


def _chapter_sort_key(chapter: Chapter) -> tuple[float, list[int | str]]:
    number = chapter.number if chapter.number is not None else float("inf")
    return (number, natural_sort_key(chapter.title))


class LibraryIntelligenceService:
    """Intelligence-layer operations over the library catalog."""

    def __init__(
        self,
        db: Session,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        # Library membership, per-series state, collections, reading history,
        # and recommendations are all per-(user, profile); None/None is the
        # anonymous/legacy unscoped bucket.
        self._user_id = user_id
        self._profile_id = profile_id

    # ------------------------------------------------------------------
    # Per-profile scoping helpers
    # ------------------------------------------------------------------

    def _mature_enabled(self) -> bool:
        """The active gate for this (user, profile)."""
        return resolve_mature_gate(self._db, self._profile_id, self._user_id)

    @property
    def mature_content_enabled(self) -> bool:
        """Public view of the active profile's mature-content gate (or the
        global default when no profile is active). Used by callers outside the
        library — e.g. federated source search — to scope adult sources."""
        return self._mature_enabled()

    def _apply_mature_filter(self, query):
        """Drop adult-rated series from a ``Series`` query while the gate is off.

        Applied to every surface that can put a series in front of the user --
        the library grid, search, discovery strips, recommendations, continue-
        reading, history, collections and statistics -- not just discovery. A
        series hidden from the grid but still showing in Continue Reading is
        worse than not hiding it at all, so the gate is all-or-nothing.

        This HIDES, it never deletes: the rows, the membership and the progress
        all stay intact and reappear the moment the profile turns 18+ back on.

        Note ``~mature_rating_predicate`` rather than ``notin_``: the latter is
        NULL against an unrated row, which silently dropped it. Unrated stays
        visible on purpose -- ``Series.content_rating`` defaults to "unknown"
        for every folder import, so hiding unknown would blank the library."""
        if self._mature_enabled():
            return query
        return query.filter(~mature_rating_predicate(Series.content_rating))

    def _mature_series_ids(self):
        """Subquery of adult-rated series ids, for surfaces that filter rows
        hanging off a series (progress, sessions) rather than ``Series`` itself."""
        return (
            self._db.query(Series.id)
            .filter(mature_rating_predicate(Series.content_rating))
            .scalar_subquery()
        )

    def _gate_sessions(self, query):
        """Drop reading sessions belonging to a hidden series.

        ``notin_`` against the id subquery rather than a join, so a session
        whose series row has gone (soft-deleted, or never resolved) is kept
        rather than silently disappearing with the adult ones."""
        if self._mature_enabled():
            return query
        return query.filter(ReadingSession.series_id.notin_(self._mature_series_ids()))

    def _scope_sessions(self, query):
        return query.filter(
            ReadingSession.user_id == self._user_id,
            ReadingSession.profile_id == self._profile_id,
        )

    def _scope_progress(self, query):
        return query.filter(
            ReadingProgress.user_id == self._user_id,
            ReadingProgress.profile_id == self._profile_id,
        )

    def _scope_collections(self, query):
        return query.filter(
            Collection.user_id == self._user_id,
            Collection.profile_id == self._profile_id,
        )

    # ------------------------------------------------------------------
    # Library membership (repeated from LibraryService to avoid an import
    # cycle, same as the sort helpers above)
    # ------------------------------------------------------------------

    def _library_on(self):
        """Join predicate binding a ``Series`` to this (user, profile)'s
        membership row. ``in_library`` is the membership bit — a state row can
        exist with it false (a favourite or progress recorded from Browse
        without adding), so the join alone is not membership."""
        return and_(
            UserSeriesState.series_id == Series.id,
            UserSeriesState.user_id == self._user_id,
            UserSeriesState.profile_id == self._profile_id,
            UserSeriesState.in_library == True,  # noqa: E712 - SQL, not Python
        )

    def _scope_library(self, query):
        """Narrow a ``Series`` query to what this (user, profile) added."""
        return query.join(UserSeriesState, self._library_on())

    def _can_read(self, series_id: int) -> bool:
        """Object-level read authorization, shared verbatim with LibraryService.

        The membership helpers above are duplicated between the two services to
        dodge an import cycle; the authorization rule deliberately is NOT. It
        lives in core.library_authz so /library/series/{id} (this service) and
        /reader/chapter/{id} (LibraryService) cannot drift into disagreeing
        about who may read what.
        """
        return series_read_allowed(self._db, self._user_id, series_id)

    def _library_series_id_query(self):
        """This (user, profile)'s series ids as a query, for aggregates that
        count rows hanging off series (chapters, tags) rather than series."""
        return self._db.query(UserSeriesState.series_id).filter(
            UserSeriesState.user_id == self._user_id,
            UserSeriesState.profile_id == self._profile_id,
            UserSeriesState.in_library == True,  # noqa: E712 - SQL, not Python
        )

    # Membership and visibility are kept as separate helpers on purpose:
    # ``_scope_library`` / ``_library_series_id_query`` answer "did this profile
    # add it", the pair below answers "and may this profile see it right now".
    # Every *read* surface uses the visible pair; conflating the two would
    # quietly under-report anywhere membership is what is actually being asked
    # (imports, cleanup, exports).

    def _visible_library(self, query):
        """This (user, profile)'s library, minus whatever the 18+ gate hides."""
        return self._apply_mature_filter(self._scope_library(query))

    def _visible_library_series_ids(self):
        """Gate-filtered series-id subquery, so aggregates over chapters/tags
        cannot count rows belonging to a hidden series."""
        query = self._library_series_id_query()
        if not self._mature_enabled():
            query = query.join(Series, Series.id == UserSeriesState.series_id).filter(
                ~mature_rating_predicate(Series.content_rating)
            )
        return query.scalar_subquery()

    def _get_or_create_state(self, series_id: int) -> UserSeriesState:
        state = (
            self._db.query(UserSeriesState)
            .filter(
                UserSeriesState.user_id == self._user_id,
                UserSeriesState.profile_id == self._profile_id,
                UserSeriesState.series_id == series_id,
            )
            .first()
        )
        if state is None:
            state = UserSeriesState(
                user_id=self._user_id,
                profile_id=self._profile_id,
                series_id=series_id,
            )
            self._db.add(state)
            self._db.flush()
        return state

    def _state_map(self, series_ids: set[int]) -> dict[int, UserSeriesState]:
        if not series_ids:
            return {}
        return {
            row.series_id: row
            for row in self._db.query(UserSeriesState).filter(
                UserSeriesState.user_id == self._user_id,
                UserSeriesState.profile_id == self._profile_id,
                UserSeriesState.series_id.in_(series_ids),
            )
        }

    def _read_chapter_map(self, series_ids: set[int]) -> dict[int, int]:
        """Per-(user, profile) completed-chapter counts. The denormalized
        ``series.read_chapters`` column aggregates every user's chapter
        progress, so it can never be reported to one caller."""
        if not series_ids:
            return {}
        rows = (
            self._db.query(Chapter.series_id, func.count(ChapterProgress.id))
            .join(ChapterProgress, ChapterProgress.chapter_id == Chapter.id)
            .filter(
                Chapter.series_id.in_(series_ids),
                ChapterProgress.user_id == self._user_id,
                ChapterProgress.profile_id == self._profile_id,
                ChapterProgress.is_completed == True,  # noqa: E712 - SQL, not Python
            )
            .group_by(Chapter.series_id)
            .all()
        )
        return {series_id: count for series_id, count in rows}

    def _series_summaries(self, series_list: list[Series]) -> list[dict[str, object]]:
        """Serialize a bounded list of series with their owner-specific state
        batch-loaded once, so no surface pays an N+1 for scoping."""
        series_ids = {s.id for s in series_list}
        state_map = self._state_map(series_ids)
        progress_map = self._reading_progress_map(series_ids)
        read_map = self._read_chapter_map(series_ids)
        return [
            self._series_summary(
                s,
                state=state_map.get(s.id),
                reading_progress=progress_map.get(s.id),
                read_chapters=read_map.get(s.id, 0),
            )
            for s in series_list
        ]

    # ------------------------------------------------------------------
    # Search (relevance-ranked)
    # ------------------------------------------------------------------

    def search_series(self, query: str, page: int = 1, per_page: int = 40) -> dict[str, object]:
        """Relevance-ranked search over series titles, authors, and descriptions.

        Scoring (higher = better):
          - exact title match          +10
          - prefix title match         +5
          - title substring match      +3
          - author match               +3
          - description match          +1
          - is currently being read    +2
          - not yet started            +1
        """
        q = query.strip()
        if not q:
            raise AppError(
                "Search query is empty.",
                code="validation_error",
                status_code=422,
            )

        q_lower = q.lower()
        q_like = f"%{q}%"
        q_prefix = f"{q}%"

        # Try FTS5 first (fastest path)
        fts_ids: set[int] = set()
        try:
            fts_sql = text(
                "SELECT rowid FROM series_fts WHERE series_fts MATCH :query"
            )
            rows = self._db.execute(fts_sql, {"query": q}).fetchall()
            fts_ids = {r[0] for r in rows}
        except Exception:
            pass

        # Fallback / expansion: broad SQL scan with scoring
        # This is a single indexed query that filters to candidate rows.
        candidates = self._apply_mature_filter(
            self._db.query(
                Series,
                ReadingProgress,
                case(
                    (Series.title.ilike(q), 10),            # exact title
                    (Series.title.ilike(q_prefix), 5),       # prefix title
                    (Series.title.ilike(q_like), 3),       # substring title
                    else_=0,
                ).label("title_score"),
                case(
                    (Series.author.ilike(q), 3),
                    else_=0,
                ).label("author_score"),
                case(
                    (Series.description.ilike(q_like), 1),
                    else_=0,
                ).label("desc_score"),
            )
            .join(UserSeriesState, self._library_on())
            .outerjoin(
                ReadingProgress,
                and_(
                    ReadingProgress.series_id == Series.id,
                    ReadingProgress.user_id == self._user_id,
                    ReadingProgress.profile_id == self._profile_id,
                ),
            )
            .filter(
                Series.deleted_at.is_(None),
                or_(
                    Series.title.ilike(q_like),
                    Series.author.ilike(q_like),
                    Series.description.ilike(q_like),
                ),
            )
        ).all()

        # The FTS hit set is raw rowids straight off the virtual table, so it
        # bypasses the ORM filter above entirely. Left unfiltered it is not just
        # a scoring boost -- an adult series matched by FTS alone short-circuits
        # the empty-result branch below. Gate it with the same rule.
        if fts_ids and not self._mature_enabled():
            allowed = {
                row[0]
                for row in self._db.query(Series.id)
                .filter(
                    Series.id.in_(fts_ids),
                    ~mature_rating_predicate(Series.content_rating),
                )
                .all()
            }
            fts_ids &= allowed

        if not candidates and not fts_ids:
            from utils.api_pagination import enrich_pagination_aliases

            return enrich_pagination_aliases(
                {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "per_page": per_page,
                    "has_next": False,
                }
            )

        scored: list[tuple[float, Series]] = []
        seen_ids: set[int] = set()

        for row in candidates:
            series, progress, t_score, a_score, d_score = row
            if series.id in seen_ids:
                continue
            seen_ids.add(series.id)

            score = t_score + a_score + d_score
            # FTS presence boost
            if series.id in fts_ids:
                score += 2
            # Engagement boost
            if progress:
                if progress.progress_pct > 0 and progress.progress_pct < 100:
                    score += 2  # actively reading
                elif progress.progress_pct == 0:
                    score += 1  # started but not read

            scored.append((score, series))

        scored.sort(key=lambda x: (-x[0], x[1].sort_title))
        total = len(scored)
        offset = max(page - 1, 0) * per_page
        page_items = scored[offset : offset + per_page]

        from utils.api_pagination import enrich_pagination_aliases

        return enrich_pagination_aliases(
            {
                "items": self._series_summaries([s for _, s in page_items]),
                "total": total,
                "page": page,
                "per_page": per_page,
                "has_next": offset + per_page < total,
            }
        )

    # ------------------------------------------------------------------
    # Metadata indexing + quality
    # ------------------------------------------------------------------

    def update_series_metadata(
        self,
        series_id: int,
        **fields: object,
    ) -> dict[str, object]:
        """Update series metadata. Only fields present are updated."""
        series = self._db.query(Series).filter(Series.id == series_id).first()
        # Gated identically to get_series_detail, on both axes, because it ends
        # by returning ``_series_detail`` -- the same payload, now including the
        # series' originating source. This is the second entrance to that
        # serializer; leaving it open would mean the source identity (and the
        # chapter list, and the caller's own collections) was readable through
        # PATCH for a series the caller may not read, which is the leak
        # ``core.library_authz`` was just added to close. Same 404 as its
        # siblings: a distinct code would confirm the id exists.
        if (
            not series
            or (not self._mature_enabled() and is_mature_rating(series.content_rating))
            or not self._can_read(series_id)
        ):
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )

        # Catalog facts, shared by everyone who has the series. ``reading_status``
        # and ``is_favorite`` are deliberately NOT here: they are the caller's
        # own opinion of the series and land on their UserSeriesState row below,
        # so one account can no longer rewrite another's shelf.
        allowed = {
            "title",
            "author",
            "artist",
            "description",
            "status",
            "content_rating",
            "language",
            "year",
        }
        owned = {"reading_status", "is_favorite"}
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(series, key, value)
                if key == "title":
                    series.sort_title = self._compute_sort_title(str(value))

        owned_updates = {
            key: value
            for key, value in fields.items()
            if key in owned and value is not None
        }
        if owned_updates:
            state = self._get_or_create_state(series_id)
            if "reading_status" in owned_updates:
                state.reading_status = str(owned_updates["reading_status"])
            if "is_favorite" in owned_updates:
                state.is_favorite = bool(owned_updates["is_favorite"])
            state.updated_at = utcnow()

        series.updated_at = utcnow()
        self._db.commit()
        self._db.refresh(series)
        return self._series_detail(series)

    def get_metadata_quality(self, series_id: int) -> dict[str, object]:
        """Return metadata completeness score and gaps."""
        series = self._db.query(Series).filter(Series.id == series_id).first()
        # Same family as get_series_detail and gated with it, on both axes: the
        # response names which of title/author/description/rating are present,
        # which is enough to identify a series by id without ever opening it --
        # and to confirm that an 18+ series the gate is hiding exists.
        if (
            not series
            or (not self._mature_enabled() and is_mature_rating(series.content_rating))
            or not self._can_read(series_id)
        ):
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )

        fields = {
            "title": bool(series.title),
            "author": bool(series.author),
            "artist": bool(series.artist),
            "description": bool(series.description),
            "status": bool(series.status) and series.status != "unknown",
            "content_rating": bool(series.content_rating) and series.content_rating != "unknown",
            "language": bool(series.language),
            "year": bool(series.year),
            "cover_path": bool(series.cover_path),
        }
        total_fields = len(fields)
        filled = sum(1 for v in fields.values() if v)
        score = round(filled / total_fields * 100, 1)

        missing = [k for k, v in fields.items() if not v]
        suggestions = []
        if "author" in missing:
            suggestions.append("Add author for search and filtering")
        if "description" in missing:
            suggestions.append("Add description for AI summarization and recommendations")
        if "year" in missing:
            suggestions.append("Add year for historical browsing")
        if "status" in missing or series.status == "unknown":
            suggestions.append("Set status (ongoing/completed) for recommendation weighting")

        return {
            "series_id": series_id,
            "score": score,
            "missing": missing,
            "suggestions": suggestions,
            "fields": fields,
        }

    # ------------------------------------------------------------------
    # Similar series (SQL-based scoring, no N+1)
    # ------------------------------------------------------------------

    def get_similar_series(self, series_id: int, limit: int = 10) -> list[dict[str, object]]:
        """Return series similar to the given one based on tags, author, and artist.

        Scoring:
          - shared tag                   +3
          - same author                  +2
          - same artist                  +1
          - same content_rating          +1
          - same language                +1
        """
        source = self._db.query(Series).filter(Series.id == series_id).first()
        # The candidates were always scoped to the caller's own library, so this
        # never leaked content -- but answering 404 for an unknown id and [] for
        # a real one made it an existence oracle for series ids, which is the
        # same disclosure the reader's 404-not-403 rule exists to deny. Nothing
        # legitimate is lost: this hangs off the series detail page, which now
        # requires the same claim.
        if not source or not self._can_read(series_id):
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )

        # Gather source tag IDs once
        source_tag_ids = {
            t[0]
            for t in self._db.query(SeriesTag.tag_id)
            .filter(SeriesTag.series_id == series_id)
            .all()
        }

        # Score via SQL subquery — no Python N+1 loop
        score_expr = (
            func.sum(case((SeriesTag.tag_id.in_(source_tag_ids), 3), else_=0)).label("tag_score")
        )

        subq = (
            self._db.query(SeriesTag.series_id, score_expr)
            .filter(SeriesTag.series_id != series_id)
            .group_by(SeriesTag.series_id)
            .subquery()
        )

        # Candidates come from the caller's own library only — recommending a
        # title another account added would disclose that they added it.
        results = (
            self._visible_library(self._db.query(Series, subq.c.tag_score))
            .outerjoin(subq, subq.c.series_id == Series.id)
            .filter(
                Series.id != series_id,
                Series.deleted_at.is_(None),
            )
            .all()
        )

        scored: list[tuple[int, Series]] = []
        for row in results:
            series, tag_score = row
            score = (tag_score or 0)
            if source.author and series.author == source.author:
                score += 2
            if source.artist and series.artist == source.artist:
                score += 1
            if source.content_rating and series.content_rating == source.content_rating:
                score += 1
            if source.language and series.language == source.language:
                score += 1
            if score >= 3:
                scored.append((score, series))

        scored.sort(key=lambda x: (-x[0], x[1].sort_title))
        # Diversify: at most 2 from the same author
        final: list[Series] = []
        author_counts: dict[str, int] = defaultdict(int)
        for score, s in scored:
            author = s.author or ""
            if author_counts[author] < 2 or score >= 8:
                author_counts[author] += 1
                final.append(s)
            if len(final) >= limit:
                break

        return self._series_summaries(final)

    # ------------------------------------------------------------------
    # Recommendations (engagement-weighted, diverse, SQL-optimized)
    # ------------------------------------------------------------------

    def get_recommendations(self, limit: int = 10) -> list[dict[str, object]]:
        """Recommend unread series based on reading history and similar tags.

        Scoring:
          - shared tag from a COMPLETED series      +3 per tag
          - shared tag from a READING series        +2 per tag
          - shared tag from a started series        +1 per tag
          - same author as a liked series            +3
          - same artist as a liked series            +1
          - recency (added in last 30 days)         +1
          - high total chapters (popularity)         +1
        """
        # Build user preference profile from reading history
        profile = self._build_reading_profile()
        if not profile:
            return self.get_recently_added(limit=limit)

        liked_tag_ids = set(profile["tag_ids"])
        liked_author = profile["author"]
        liked_artist = profile["artist"]
        active_ids = profile["active_ids"]

        # Tag-based scoring via SQL subquery
        if liked_tag_ids:
            tag_subq = (
                self._db.query(
                    SeriesTag.series_id,
                    func.count(SeriesTag.tag_id).label("shared_tags"),
                )
                .filter(
                    SeriesTag.tag_id.in_(liked_tag_ids),
                    SeriesTag.series_id.notin_(active_ids),
                )
                .group_by(SeriesTag.series_id)
                .subquery()
            )
        else:
            # No tags profile: use author/artist fallback
            tag_subq = None

        # Select the already-joined shared_tags column directly — the subquery
        # above already computes it per candidate, so no per-row query is needed.
        # Candidates are drawn from the caller's own library only.
        if tag_subq is not None:
            rows = (
                self._visible_library(self._db.query(Series, tag_subq.c.shared_tags))
                .outerjoin(tag_subq, tag_subq.c.series_id == Series.id)
                .filter(
                    Series.id.notin_(active_ids),
                    Series.deleted_at.is_(None),
                    tag_subq.c.shared_tags.isnot(None),
                )
                .all()
            )
        else:
            rows = [
                (s, 0)
                for s in self._visible_library(self._db.query(Series))
                .filter(
                    Series.id.notin_(active_ids),
                    Series.deleted_at.is_(None),
                )
                .all()
            ]

        if not rows:
            return self.get_recently_added(limit=limit)

        month_ago = utcnow() - timedelta(days=30)
        scored: list[tuple[int, Series]] = []
        for s, shared_tags in rows:
            score = (shared_tags or 0) * 2

            if liked_author and s.author == liked_author:
                score += 3
            if liked_artist and s.artist == liked_artist:
                score += 1
            if s.created_at and s.created_at >= month_ago:
                score += 1
            if s.total_chapters and s.total_chapters > 50:
                score += 1

            if score > 0:
                scored.append((score, s))

        scored.sort(key=lambda x: (-x[0], x[1].sort_title))

        # Diversify: max 2 per author, max 3 per tag-weight group
        final: list[Series] = []
        author_counts: dict[str, int] = defaultdict(int)
        for score, s in scored:
            author = s.author or ""
            if author_counts[author] < 2:
                author_counts[author] += 1
                final.append(s)
            if len(final) >= limit:
                break

        return self._series_summaries(final)

    def _build_reading_profile(self) -> dict[str, object] | None:
        """Build a user preference profile from reading history."""
        # Get series with meaningful reading engagement
        active = (
            self._scope_progress(self._db.query(ReadingProgress))
            .filter(ReadingProgress.progress_pct > 0)
            .order_by(ReadingProgress.progress_pct.desc())
            .limit(20)
            .all()
        )
        if not active:
            return None

        active_ids = {r.series_id for r in active}
        # Highest-progress series is the "anchor"
        anchor = active[0]
        anchor_series = self._db.query(Series).filter(Series.id == anchor.series_id).first()

        tag_ids = [
            t[0]
            for t in self._db.query(SeriesTag.tag_id)
            .filter(SeriesTag.series_id.in_(active_ids))
            .distinct()
            .all()
        ]

        return {
            "active_ids": active_ids,
            "tag_ids": tag_ids,
            "author": anchor_series.author if anchor_series else None,
            "artist": anchor_series.artist if anchor_series else None,
        }

    # ------------------------------------------------------------------
    # Reading history (aggregated, with calendar + velocity)
    # ------------------------------------------------------------------

    def get_reading_history(self, limit: int = 50) -> list[dict[str, object]]:
        """Return recent reading sessions with series and chapter names.

        Gate-filtered by the session's series: history carries the title, so
        leaving it unfiltered would name every adult series the profile has
        read while the grid pretends they do not exist.

        ``id`` breaks ties on ``started_at``: sessions are opened by
        ``ReaderService`` as the user reads, and flipping between two chapters
        can open two of them inside the same second — without the tiebreaker
        their order on the history screen is whatever SQLite happens to return.
        """
        sessions = (
            self._gate_sessions(self._scope_sessions(self._db.query(ReadingSession)))
            .options(
                selectinload(ReadingSession.series),
                selectinload(ReadingSession.chapter),
            )
            .order_by(ReadingSession.started_at.desc(), ReadingSession.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "session_id": s.id,
                "series_id": s.series_id,
                "series_title": s.series.title if s.series else None,
                "chapter_id": s.chapter_id,
                "chapter_title": s.chapter.title if s.chapter else None,
                "start_page": s.start_page,
                "end_page": s.end_page,
                "pages_read": s.pages_read,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            }
            for s in sessions
        ]

    def get_reading_calendar(self, days: int = 30) -> list[dict[str, object]]:
        """Return daily reading aggregates for the last N days."""
        cutoff = utcnow() - timedelta(days=days)

        # Aggregate by date (SQLite DATE truncation)
        rows = (
            self._scope_sessions(
                self._db.query(
                    func.date(ReadingSession.started_at).label("day"),
                    func.count(ReadingSession.id).label("sessions"),
                    func.sum(ReadingSession.pages_read).label("pages"),
                    func.sum(ReadingSession.chapter_id).label("chapters_approx"),  # not exact but fast
                )
            )
            .filter(ReadingSession.started_at >= cutoff)
            .group_by(func.date(ReadingSession.started_at))
            .order_by(func.date(ReadingSession.started_at).desc())
            .all()
        )

        return [
            {
                "day": r.day,
                "sessions": r.sessions or 0,
                "pages_read": r.pages or 0,
                "has_activity": (r.pages or 0) > 0,
            }
            for r in rows
        ]

    def get_series_reading_history(self, series_id: int, limit: int = 50) -> list[dict[str, object]]:
        """Return reading history for a specific series."""
        sessions = (
            self._gate_sessions(self._scope_sessions(self._db.query(ReadingSession)))
            .options(selectinload(ReadingSession.chapter))
            .filter(ReadingSession.series_id == series_id)
            .order_by(ReadingSession.started_at.desc(), ReadingSession.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "session_id": s.id,
                "chapter_id": s.chapter_id,
                "chapter_title": s.chapter.title if s.chapter else None,
                "start_page": s.start_page,
                "end_page": s.end_page,
                "pages_read": s.pages_read,
                "started_at": s.started_at.isoformat() if s.started_at else None,
            }
            for s in sessions
        ]

    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------

    def toggle_favorite(self, series_id: int) -> dict[str, object]:
        """Toggle the favorite status of a series *for this (user, profile)*.

        This used to flip ``series.is_favorite`` on the shared catalog row, so a
        second account's toggle silently un-favourited the owner's series. The
        flag lives on the caller's own state row instead. Membership is left
        alone on purpose: favouriting from Browse must not also add the series.
        """
        series = self._db.query(Series).filter(Series.id == series_id).first()
        if not series:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )
        state = self._get_or_create_state(series_id)
        state.is_favorite = not bool(state.is_favorite)
        state.updated_at = utcnow()
        self._db.commit()
        return {"series_id": series_id, "is_favorite": bool(state.is_favorite)}

    # ------------------------------------------------------------------
    # Collections (smart, paginated, cover-aware)
    # ------------------------------------------------------------------

    def list_collections(self) -> list[dict[str, object]]:
        """Return the active profile's collections with series counts."""
        # Pre-aggregate series counts in one query, gate-filtered so the count
        # on the card matches what opening the collection actually shows.
        counts = {
            c.collection_id: c.cnt
            for c in self._apply_mature_filter(
                self._db.query(
                    CollectionSeries.collection_id,
                    func.count(CollectionSeries.series_id).label("cnt"),
                ).join(Series, Series.id == CollectionSeries.series_id)
            )
            .group_by(CollectionSeries.collection_id)
            .all()
        }
        collections = (
            self._scope_collections(self._db.query(Collection))
            .order_by(Collection.sort_order.asc())
            .all()
        )
        return [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "cover_path": c.cover_path,
                "series_count": counts.get(c.id, 0),
                "sort_order": c.sort_order,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
            }
            for c in collections
        ]

    def get_collection(self, collection_id: int) -> dict[str, object]:
        collection = (
            self._scope_collections(self._db.query(Collection))
            .filter(Collection.id == collection_id)
            .first()
        )
        if not collection:
            raise AppError(
                "Collection not found.",
                code="collection_not_found",
                status_code=404,
                details={"collection_id": collection_id},
            )
        return self._collection_detail(collection)

    def create_collection(self, name: str, description: str | None = None) -> dict[str, object]:
        existing = (
            self._scope_collections(self._db.query(Collection))
            .filter(Collection.name == name)
            .first()
        )
        if existing:
            raise AppError(
                "Collection name already exists.",
                code="validation_error",
                status_code=422,
                details={"field": "name", "reason": "must be unique"},
            )
        collection = Collection(
            name=name,
            description=description,
            user_id=self._user_id,
            profile_id=self._profile_id,
        )
        self._db.add(collection)
        self._db.commit()
        self._db.refresh(collection)
        return self._collection_summary(collection)

    def update_collection(
        self, collection_id: int, name: str | None = None, description: str | None = None, sort_order: int | None = None
    ) -> dict[str, object]:
        collection = (
            self._scope_collections(self._db.query(Collection))
            .filter(Collection.id == collection_id)
            .first()
        )
        if not collection:
            raise AppError(
                "Collection not found.",
                code="collection_not_found",
                status_code=404,
                details={"collection_id": collection_id},
            )
        if name is not None:
            duplicate = (
                self._scope_collections(self._db.query(Collection))
                .filter(Collection.name == name, Collection.id != collection_id)
                .first()
            )
            if duplicate:
                raise AppError(
                    "Collection name already exists.",
                    code="validation_error",
                    status_code=422,
                    details={"field": "name", "reason": "must be unique"},
                )
            collection.name = name
        if description is not None:
            collection.description = description
        if sort_order is not None:
            collection.sort_order = sort_order
        collection.updated_at = utcnow()
        self._db.commit()
        self._db.refresh(collection)
        return self._collection_summary(collection)

    def delete_collection(self, collection_id: int) -> None:
        collection = (
            self._scope_collections(self._db.query(Collection))
            .filter(Collection.id == collection_id)
            .first()
        )
        if not collection:
            raise AppError(
                "Collection not found.",
                code="collection_not_found",
                status_code=404,
                details={"collection_id": collection_id},
            )
        self._db.delete(collection)
        self._db.commit()

    def add_series_to_collection(self, collection_id: int, series_id: int) -> dict[str, object]:
        collection = (
            self._scope_collections(self._db.query(Collection))
            .filter(Collection.id == collection_id)
            .first()
        )
        if not collection:
            raise AppError(
                "Collection not found.",
                code="collection_not_found",
                status_code=404,
            )
        series = self._db.query(Series).filter(Series.id == series_id).first()
        if not series:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
            )
        link = (
            self._db.query(CollectionSeries)
            .filter(
                CollectionSeries.collection_id == collection_id,
                CollectionSeries.series_id == series_id,
            )
            .first()
        )
        if not link:
            link = CollectionSeries(collection_id=collection_id, series_id=series_id)
            self._db.add(link)
            self._db.commit()
        # If collection has no cover, use series cover as cover
        if not collection.cover_path and series.cover_path:
            collection.cover_path = series.cover_path
            self._db.commit()
        return {
            "collection_id": collection_id,
            "series_id": series_id,
            "added_at": link.added_at.isoformat(),
        }

    def remove_series_from_collection(self, collection_id: int, series_id: int) -> None:
        collection = (
            self._scope_collections(self._db.query(Collection))
            .filter(Collection.id == collection_id)
            .first()
        )
        if not collection:
            raise AppError(
                "Collection not found.",
                code="collection_not_found",
                status_code=404,
            )
        series = self._db.query(Series).filter(Series.id == series_id).first()
        if not series:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
            )
        link = (
            self._db.query(CollectionSeries)
            .filter(
                CollectionSeries.collection_id == collection_id,
                CollectionSeries.series_id == series_id,
            )
            .first()
        )
        if link:
            self._db.delete(link)
            self._db.commit()
            # If collection used this series cover, clear it
            if collection.cover_path == series.cover_path:
                collection.cover_path = None
                self._db.commit()

    def reorder_collection_series(self, collection_id: int, series_ids: list[int]) -> dict[str, object]:
        """Reorder series in a collection by providing a sorted list of series IDs."""
        collection = (
            self._scope_collections(self._db.query(Collection))
            .filter(Collection.id == collection_id)
            .first()
        )
        if not collection:
            raise AppError(
                "Collection not found.",
                code="collection_not_found",
                status_code=404,
            )
        for order, series_id in enumerate(series_ids):
            link = (
                self._db.query(CollectionSeries)
                .filter(
                    CollectionSeries.collection_id == collection_id,
                    CollectionSeries.series_id == series_id,
                )
                .first()
            )
            if link:
                link.sort_order = order
        self._db.commit()
        return self._collection_detail(collection)

    # ------------------------------------------------------------------
    # Smart Tags (batch-count optimized)
    # ------------------------------------------------------------------

    def list_tags(self, category: str | None = None) -> list[dict[str, object]]:
        """Tags on series this (user, profile) can currently see, with counts.

        Scoped to the visible library rather than to every Tag row on the
        instance. Tags carry no owner of their own, so an unscoped listing both
        named other accounts' tags and — once the 18+ gate started hiding
        series — kept naming a tag that existed solely on a hidden adult series,
        while the statistics screen had already stopped counting it. A tag whose
        only series is invisible is at best useless as a filter and at worst
        exactly the label the gate was asked to hide.
        """
        q = self._db.query(Tag)
        if category is not None:
            q = q.filter(Tag.category == category)
        tags = q.order_by(Tag.name.asc()).all()
        if not tags:
            return []

        tag_ids = [t.id for t in tags]

        def _counts(*, gated: bool) -> dict[int, int]:
            query = self._db.query(
                SeriesTag.tag_id, func.count(func.distinct(SeriesTag.series_id))
            ).filter(SeriesTag.tag_id.in_(tag_ids))
            if gated and not self._mature_enabled():
                query = query.filter(
                    SeriesTag.series_id.notin_(self._mature_series_ids())
                )
            return dict(query.group_by(SeriesTag.tag_id).all())

        applied = _counts(gated=False)
        counts = _counts(gated=True)
        # A tag is dropped only when it HAS series and none of them are visible
        # -- that is the leak: a label whose sole series is hidden by the 18+
        # gate was still being named here while statistics had stopped counting
        # it. A tag with no series at all is an unapplied label the user just
        # created, so it stays; hiding those would make tag creation look broken.
        tags = [t for t in tags if applied.get(t.id, 0) == 0 or counts.get(t.id, 0) > 0]
        if not tags:
            return []
        return [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "color": t.color,
                "series_count": counts.get(t.id, 0),
            }
            for t in tags
        ]

    def create_tag(self, name: str, category: str = "custom", color: str | None = None) -> dict[str, object]:
        existing = self._db.query(Tag).filter(Tag.name == name).first()
        if existing:
            raise AppError(
                "Tag name already exists.",
                code="validation_error",
                status_code=422,
                details={"field": "name", "reason": "must be unique"},
            )
        tag = Tag(name=name, category=category, color=color)
        self._db.add(tag)
        self._db.commit()
        self._db.refresh(tag)
        return {"id": tag.id, "name": tag.name, "category": tag.category, "color": tag.color}

    def delete_tag(self, tag_id: int) -> None:
        tag = self._db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise AppError(
                "Tag not found.",
                code="tag_not_found",
                status_code=404,
                details={"tag_id": tag_id},
            )
        self._db.delete(tag)
        self._db.commit()

    def add_tag_to_series(self, series_id: int, tag_id: int) -> dict[str, object]:
        series = self._db.query(Series).filter(Series.id == series_id).first()
        if not series:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
            )
        tag = self._db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise AppError(
                "Tag not found.",
                code="tag_not_found",
                status_code=404,
            )
        link = (
            self._db.query(SeriesTag)
            .filter(SeriesTag.series_id == series_id, SeriesTag.tag_id == tag_id)
            .first()
        )
        if not link:
            link = SeriesTag(series_id=series_id, tag_id=tag_id)
            self._db.add(link)
            self._db.commit()
        return {"series_id": series_id, "tag_id": tag_id, "is_ai_generated": link.is_ai_generated}

    def remove_tag_from_series(self, series_id: int, tag_id: int) -> None:
        series = self._db.query(Series).filter(Series.id == series_id).first()
        if not series:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
            )
        tag = self._db.query(Tag).filter(Tag.id == tag_id).first()
        if not tag:
            raise AppError(
                "Tag not found.",
                code="tag_not_found",
                status_code=404,
            )
        link = (
            self._db.query(SeriesTag)
            .filter(SeriesTag.series_id == series_id, SeriesTag.tag_id == tag_id)
            .first()
        )
        if link:
            self._db.delete(link)
            self._db.commit()

    # ------------------------------------------------------------------
    # Statistics (comprehensive: streaks, velocity, distribution)
    # ------------------------------------------------------------------

    def get_statistics(self) -> dict[str, object]:
        """Return comprehensive library statistics for this (user, profile).

        Every count is membership-scoped: a brand-new account must read zeros,
        not a census of what everyone else on the instance has. Counts are also
        gate-scoped: while 18+ is off an adult series contributes to nothing,
        because a series count that does not match the visible grid is itself a
        disclosure ("47 series" over 46 covers).
        """
        library_series = self._visible_library(self._db.query(Series)).filter(
            Series.deleted_at.is_(None)
        )
        total_series = library_series.count()
        total_chapters = (
            self._db.query(Chapter)
            .filter(Chapter.series_id.in_(self._visible_library_series_ids()))
            .count()
        )
        total_pages = (
            self._visible_library(self._db.query(func.sum(Series.total_pages)))
            .filter(Series.deleted_at.is_(None))
            .scalar()
            or 0
        )
        # Session-derived numbers below (reading time, pages this week, streak,
        # velocity, weekly chart) are deliberately NOT gate-filtered. They name
        # nothing -- unlike the series/tag/author aggregates above, which would
        # otherwise put an adult series' author or genre on the stats screen --
        # and filtering them would break the reading streak on every toggle,
        # which is a visible, confusing side effect for no privacy gain.
        total_reading_time = (
            self._scope_sessions(
                self._db.query(func.sum(ReadingSession.pages_read))
            ).scalar()
            or 0
        )
        # reading_status / is_favorite are the caller's own opinion, so they are
        # read off UserSeriesState rather than the shared catalog columns.
        state_counts = self._apply_mature_filter(
            self._db.query(UserSeriesState)
            .join(Series, Series.id == UserSeriesState.series_id)
            .filter(
                UserSeriesState.user_id == self._user_id,
                UserSeriesState.profile_id == self._profile_id,
                UserSeriesState.in_library == True,  # noqa: E712 - SQL, not Python
                Series.deleted_at.is_(None),
            )
        )
        completed_series = state_counts.filter(
            UserSeriesState.reading_status == "completed"
        ).count()
        in_progress = state_counts.filter(
            UserSeriesState.reading_status == "reading"
        ).count()
        favorites = state_counts.filter(
            UserSeriesState.is_favorite == True  # noqa: E712 - SQL, not Python
        ).count()

        # Pages read in last 7 days
        week_ago = utcnow() - timedelta(days=7)
        pages_this_week = (
            self._scope_sessions(self._db.query(func.sum(ReadingSession.pages_read)))
            .filter(ReadingSession.started_at >= week_ago)
            .scalar()
            or 0
        )

        # Reading streak
        streak = self._compute_reading_streak()

        # Reading velocity (pages per hour) — last 30 days
        velocity = self._compute_reading_velocity()

        # Genre/tag distribution
        tag_distribution = self._get_tag_distribution()

        # Top authors
        top_authors = self._get_top_authors()

        # Weekly reading chart
        weekly_chart = self._get_weekly_reading_chart()

        # Completion rate
        completion_rate = round(
            completed_series / total_series * 100, 1
        ) if total_series else 0.0

        return {
            "total_series": total_series,
            "total_chapters": total_chapters,
            "total_pages": total_pages,
            "completed_series": completed_series,
            "in_progress": in_progress,
            "favorites": favorites,
            "completion_rate_pct": completion_rate,
            "total_reading_time_estimate_minutes": total_reading_time * 2,
            "pages_read_this_week": pages_this_week,
            "reading_streak_days": streak,
            "reading_velocity_pages_per_hour": velocity,
            "tag_distribution": tag_distribution,
            "top_authors": top_authors,
            "weekly_chart": weekly_chart,
        }

    def _compute_reading_streak(self) -> int:
        """Count consecutive days with reading activity ending today."""
        rows = (
            self._scope_sessions(
                self._db.query(func.date(ReadingSession.started_at).label("day"))
            )
            .filter(ReadingSession.started_at.isnot(None))
            .group_by(func.date(ReadingSession.started_at))
            .order_by(func.date(ReadingSession.started_at).desc())
            .all()
        )
        if not rows:
            return 0

        streak = 0
        today = utcnow().date()
        expected = today
        for row in rows:
            day = datetime.strptime(row.day, "%Y-%m-%d").date()
            if day == expected:
                streak += 1
                expected = day - timedelta(days=1)
            elif day < expected:
                break
        return streak

    def _compute_reading_velocity(self) -> float:
        """Approximate reading velocity in pages per hour over last 30 days."""
        month_ago = utcnow() - timedelta(days=30)
        total_pages = (
            self._scope_sessions(self._db.query(func.sum(ReadingSession.pages_read)))
            .filter(ReadingSession.started_at >= month_ago)
            .scalar()
            or 0
        )
        total_sessions = (
            self._scope_sessions(self._db.query(func.count(ReadingSession.id)))
            .filter(ReadingSession.started_at >= month_ago)
            .scalar()
            or 0
        )
        # Assume average session is 15 minutes = 0.25 hours
        hours = total_sessions * 0.25
        if hours == 0:
            return 0.0
        return round(total_pages / hours, 1)

    def _get_tag_distribution(self) -> list[dict[str, object]]:
        """Return top 10 genres/themes by series count, over this (user,
        profile)'s library only."""
        rows = (
            self._db.query(
                Tag.name,
                Tag.category,
                Tag.color,
                func.count(SeriesTag.series_id).label("series_count"),
            )
            .join(SeriesTag, SeriesTag.tag_id == Tag.id)
            .filter(SeriesTag.series_id.in_(self._visible_library_series_ids()))
            .group_by(Tag.id)
            .order_by(func.count(SeriesTag.series_id).desc())
            .limit(10)
            .all()
        )
        return [
            {
                "name": r.name,
                "category": r.category,
                "color": r.color,
                "series_count": r.series_count,
            }
            for r in rows
        ]

    def _get_top_authors(self, limit: int = 5) -> list[dict[str, object]]:
        """Return top authors by series count and total pages, over this (user,
        profile)'s library only."""
        rows = (
            self._visible_library(
                self._db.query(
                    Series.author,
                    func.count(Series.id).label("series_count"),
                    func.sum(Series.total_pages).label("total_pages"),
                )
            )
            .filter(Series.author.isnot(None), Series.deleted_at.is_(None))
            .group_by(Series.author)
            .order_by(func.count(Series.id).desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "author": r.author,
                "series_count": r.series_count,
                "total_pages": r.total_pages or 0,
            }
            for r in rows
        ]

    def _get_weekly_reading_chart(self) -> list[dict[str, object]]:
        """Return 7-day reading chart with pages read per day."""
        today = utcnow().date()
        days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
        day_strs = [d.strftime("%Y-%m-%d") for d in days]

        rows = (
            self._scope_sessions(
                self._db.query(
                    func.date(ReadingSession.started_at).label("day"),
                    func.sum(ReadingSession.pages_read).label("pages"),
                )
            )
            .filter(ReadingSession.started_at >= datetime.combine(today - timedelta(days=6), datetime.min.time()))
            .group_by(func.date(ReadingSession.started_at))
            .all()
        )
        pages_by_day = {r.day: r.pages or 0 for r in rows}

        return [
            {
                "day": d_str,
                "label": d.strftime("%a"),
                "pages_read": pages_by_day.get(d_str, 0),
            }
            for d, d_str in zip(days, day_strs)
        ]

    # ------------------------------------------------------------------
    # Recently added / updated
    # ------------------------------------------------------------------

    def get_recently_added(self, limit: int = 10) -> list[dict[str, object]]:
        series = (
            self._visible_library(self._db.query(Series))
            .filter(Series.deleted_at.is_(None))
            .order_by(Series.created_at.desc())
            .limit(limit)
            .all()
        )
        return self._series_summaries(series)

    def get_recently_updated(self, limit: int = 10) -> list[dict[str, object]]:
        series = (
            self._visible_library(self._db.query(Series))
            .filter(Series.deleted_at.is_(None))
            .order_by(Series.updated_at.desc())
            .limit(limit)
            .all()
        )
        return self._series_summaries(series)

    # ------------------------------------------------------------------
    # Internal helpers (batch + memoized)
    # ------------------------------------------------------------------

    def _reading_progress_map(self, series_ids: set[int]) -> dict[int, ReadingProgress]:
        """Batch load *this* (user, profile)'s reading progress for a set of
        series IDs. Unscoped, this handed one account another's page number."""
        if not series_ids:
            return {}
        return {
            rp.series_id: rp
            for rp in self._scope_progress(self._db.query(ReadingProgress))
            .filter(ReadingProgress.series_id.in_(series_ids))
            .all()
        }

    def _compute_sort_title(self, title: str) -> str:
        t = title.strip().lower()
        for prefix in ("the ", "a ", "an "):
            if t.startswith(prefix):
                return t[len(prefix):]
        return t

    def _series_summary(
        self,
        series: Series,
        *,
        reading_progress: ReadingProgress | None = None,
        state: UserSeriesState | None = None,
        read_chapters: int = 0,
    ) -> dict[str, object]:
        """Serialize a catalog series *as seen by this (user, profile)*.

        Owner-specific fields come from the caller's own rows. Notably there is
        no fallback to ``series.reading_progress``: that relationship is
        ``uselist=False`` with no owner predicate, so it resolves to whichever
        user's row the ORM happened to load.
        """
        # Compute chapter count from denormalized column instead of len(series.chapters)
        # to avoid triggering lazy loads on list endpoints.
        chapter_count = series.total_chapters or 0
        page_count = series.total_pages or 0
        return {
            "id": series.id,
            "library_id": series.library_id,
            "title": series.title,
            "sort_title": series.sort_title,
            "original_title": series.original_title,
            "author": series.author,
            "artist": series.artist,
            "description": series.description,
            "status": series.status,
            "content_rating": series.content_rating,
            "language": series.language,
            "year": series.year,
            "cover_path": series.cover_path,
            "cover_url": f"/library/covers/{series.id}",
            "folder_path": series.folder_path,
            "is_favorite": bool(state.is_favorite) if state else False,
            # Whether THIS (user, profile) has the series on their shelf.
            # list_series inner-joins on it so everything there is a member by
            # construction, but the detail route deliberately does not filter on
            # it -- without this field a client opening a series by URL could
            # not tell "on my shelf" from "merely exists", and had to infer it
            # by re-querying the gated list and matching on id.
            "in_library": bool(state.in_library) if state else False,
            "reading_status": state.reading_status if state else "unread",
            "chapter_count": chapter_count,
            "read_chapters": read_chapters,
            "page_count": page_count,
            "total_chapters": series.total_chapters,
            "total_pages": series.total_pages,
            "created_at": series.created_at.isoformat(),
            "updated_at": series.updated_at.isoformat(),
            "reading_progress": self._progress_dict(reading_progress) if reading_progress else None,
        }

    def get_series_detail(self, series_id: int) -> dict[str, object]:
        """Return full series detail including chapters, tags, collections, and reading progress."""
        series = (
            self._db.query(Series)
            .options(
                selectinload(Series.chapters),
                selectinload(Series.tags).selectinload(SeriesTag.tag),
            )
            .filter(Series.id == series_id, Series.deleted_at.is_(None))
            .first()
        )
        # Hidden by the 18+ gate reads as not-found, matching the precedent for
        # mature *sources* (BrowseService._get_connector): a 403 would confirm
        # the series exists, and the whole point of the gate is that nothing
        # about adult content surfaces while it is off. The row is untouched.
        #
        # ``_can_read`` is the second, independent gate: this endpoint returns
        # the full chapter list, so leaving it on the row id alone kept the
        # object-level leak open on /library/series/{id} even once the reader
        # was fixed. Both denials use the same code for the same reason the 18+
        # one does.
        if (
            not series
            or (not self._mature_enabled() and is_mature_rating(series.content_rating))
            or not self._can_read(series_id)
        ):
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"series_id": series_id},
            )
        return self._series_detail(series)

    def _series_detail(self, series: Series) -> dict[str, object]:
        detail = self._series_summary(
            series,
            reading_progress=self._reading_progress_map({series.id}).get(series.id),
            state=self._state_map({series.id}).get(series.id),
            read_chapters=self._read_chapter_map({series.id}).get(series.id, 0),
        )
        chapters = sorted(series.chapters, key=_chapter_sort_key)

        # Batch query OCR status for all chapters in this series
        chapter_ids = [c.id for c in chapters]
        texts = self._db.query(ChapterText).filter(ChapterText.chapter_id.in_(chapter_ids)).all()
        text_map = {t.chapter_id: t for t in texts}
        jobs = self._db.query(OcrJob).filter(OcrJob.chapter_id.in_(chapter_ids)).filter(
            OcrJob.status.in_(("queued", "processing", "failed"))
        ).all()
        job_map = {j.chapter_id: j for j in jobs}

        def _ocr_status(chapter_id: int) -> dict:
            if chapter_id in text_map:
                t = text_map[chapter_id]
                return {"status": "completed", "word_count": t.word_count, "engine": t.engine}
            if chapter_id in job_map:
                j = job_map[chapter_id]
                return {"status": j.status, "progress": j.progress, "engine": j.engine}
            return {"status": "not_started"}

        local_chapters = [
            {
                "id": chapter.id,
                "series_id": chapter.series_id,
                "title": chapter.title,
                "number": chapter.number,
                "page_count": chapter.page_count,
                "folder_path": chapter.folder_path,
                "archive_path": chapter.archive_path,
                "ocr_status": _ocr_status(chapter.id),
                # Source-merge annotations (defaults for a purely-local chapter).
                "local_chapter_id": chapter.id,
                "is_downloaded": True,
                "is_read": bool(chapter.is_read),
                "source_chapter_id": None,
            }
            for chapter in chapters
        ]

        # Where this series came from, resolved ONCE from local rows and stated
        # unconditionally. It used to be filled in only from the merge below --
        # i.e. only when the connector was reachable AND returned a non-empty
        # catalog -- so a downloaded series on a dead, offline or rate-limited
        # source reported source_id=None. That is precisely the series the owner
        # cared enough to download, and with no source identity the local series
        # page had nothing to offer Follow on: no update checks, no new-chapter
        # notifications. The link is a local database fact and must not depend on
        # a network call to be true.
        #
        # Resolved here rather than inside the merge so the identity in this
        # payload and the identity the merge used are the same tuple by
        # construction; two resolutions of "where did this come from" that can
        # disagree is the bug this code keeps re-growing. Deliberately outside
        # the try below: that except exists to swallow *connector* failures, and
        # a local query failing is not something to report as "no source".
        resolved = self._resolve_source_link(series, chapters)
        detail["source_id"] = resolved[0] if resolved else None
        detail["source_series_id"] = resolved[1] if resolved else None

        # Follow state for THIS (user, profile), so the client renders Follow vs
        # Unfollow (and can act on it) without a second round trip. Null/false
        # for a hand-imported CBZ folder: there is genuinely nothing to track.
        followed = self._followed_tracker(*resolved) if resolved else None
        detail["is_followed"] = followed is not None
        detail["follow_tracker_id"] = followed.id if followed else None

        # Default: local-only chapter list. If the series is source-linked we
        # enrich this with the source's full catalog below; any failure degrades
        # gracefully back to these local chapters -- but no longer takes the
        # source identity down with it.
        detail["chapters"] = local_chapters
        try:
            merged = self._merge_source_chapters(
                series, chapters, local_chapters, resolved
            )
            if merged is not None:
                detail["chapters"] = merged
        except Exception:  # noqa: BLE001 - never fail series detail on source issues
            logger.warning(
                "Source chapter merge failed for series_id=%s; "
                "falling back to local-only chapter list.",
                series.id,
                exc_info=True,
            )

        detail["tags"] = [
            {"id": t.tag.id, "name": t.tag.name, "category": t.tag.category, "color": t.tag.color}
            for t in series.tags
        ]
        # Only the caller's OWN collections: ``series.collections`` is every
        # account's, so it used to disclose other people's list names on any
        # series they happened to share.
        own_collections = (
            self._scope_collections(
                self._db.query(Collection).join(
                    CollectionSeries, CollectionSeries.collection_id == Collection.id
                )
            )
            .filter(CollectionSeries.series_id == series.id)
            .order_by(Collection.sort_order.asc())
            .all()
        )
        detail["collections"] = [
            {"id": c.id, "name": c.name} for c in own_collections
        ]
        return detail

    # ------------------------------------------------------------------
    # Source-linked chapter merge
    # ------------------------------------------------------------------

    def _resolve_source_link(
        self, series: Series, chapters: list[Chapter]
    ) -> tuple[str, str] | None:
        """Resolve the (source, source_series_id) a library series is linked to.

        Preference order:
          1. A ``series_trackers`` row whose ``local_series_id`` is this series
             (the authoritative follow/download link).
          2. Any ``source_chapter_links`` row joined through one of this series'
             local chapters (a per-chapter download link).

        Returns ``None`` when the series has no source linkage at all.

        Deliberately NOT scoped to (user, profile): "which source did this series
        come from" is a property of the series, and a download made under one
        profile has to still resolve for a sibling profile reading it -- the same
        account-level call ``core.library_authz`` makes and for the same reason.
        Whether the *caller* follows it is the separate, profile-scoped question
        ``_followed_tracker`` answers.

        This is the resolver the detail path uses, in preference to the
        equivalent ``LibraryService.resolve_source_link`` (library_service.py:763),
        on two grounds. Cost: this one takes the chapters the caller already
        loaded and probes ``source_chapter_links`` by ``local_chapter_id IN (...)``
        on ``ix_source_chapter_links_local``, where the LibraryService copy
        re-joins ``chapters`` to re-read rows already in memory. Cycle: importing
        ``LibraryService`` here is the import cycle the duplicated membership
        helpers above exist to dodge. The two implementations must agree; the
        preference order above is verbatim theirs, and
        ``test_series_source_link.py`` pins them against each other so a change to
        either fails rather than silently letting the detail page and the cover
        route disagree about where a series came from.
        """
        tracker = (
            self._db.query(SeriesTracker)
            .filter(SeriesTracker.local_series_id == series.id)
            .order_by(SeriesTracker.id.asc())
            .first()
        )
        if tracker and tracker.source and tracker.series_id:
            return tracker.source, tracker.series_id

        local_ids = [c.id for c in chapters]
        if local_ids:
            link = (
                self._db.query(SourceChapterLink)
                .filter(SourceChapterLink.local_chapter_id.in_(local_ids))
                .order_by(SourceChapterLink.id.asc())
                .first()
            )
            if link and link.source and link.series_id:
                return link.source, link.series_id
        return None

    def _followed_tracker(self, source: str, source_series_id: str) -> SeriesTracker | None:
        """This (user, profile)'s *follow* row for a remote series, if any.

        Scoped with exactly the tuple ``UpdateService.follow_series`` uses for its
        duplicate check (update_service.py:480) and that ``uq_series_tracker``
        enforces: (user_id, profile_id, source, series_id, track_kind). Anything
        looser would report one profile's follow as another's -- and the tracker
        is what decides who gets the new-chapter notification, so a wrong answer
        here is a notification sent to, or withheld from, the wrong person.

        ``track_kind`` is load-bearing, not incidental: the download pipeline
        writes a ``"downloaded"`` tracker for every series it downloads
        (``sync_downloaded_trackers``), so matching on (source, series_id) alone
        would report every downloaded series as already-followed -- hiding the
        Follow button on exactly the series this field exists to expose it for.
        """
        return (
            self._db.query(SeriesTracker)
            .filter(
                SeriesTracker.user_id == self._user_id,
                SeriesTracker.profile_id == self._profile_id,
                SeriesTracker.source == source,
                SeriesTracker.series_id == source_series_id,
                SeriesTracker.track_kind == "followed",
            )
            .order_by(SeriesTracker.id.asc())
            .first()
        )

    def _merge_source_chapters(
        self,
        series: Series,
        chapters: list[Chapter],
        local_chapters: list[dict[str, object]],
        resolved: tuple[str, str] | None,
    ) -> list[dict[str, object]] | None:
        """Merge the source's full chapter catalog into the local chapter list.

        ``resolved`` is the caller's already-resolved ``(source,
        source_series_id)`` -- passed in rather than re-derived so the detail
        payload and this merge cannot name different origins for one series, and
        so a detail request costs one link resolution, not two.

        Returns the merged chapters, or ``None`` when the series is not
        source-linked or the source returns no catalog. Raises on
        connector/network failure -- the caller degrades to local-only.
        """
        if not resolved:
            return None
        source, source_series_id = resolved

        # Read-only use of the source connector to fetch the ordered catalog.
        from services.source_service import SourceService

        catalog = SourceService(source_type=source).get_chapters(source_series_id)
        if not catalog:
            return None

        links = (
            self._db.query(SourceChapterLink)
            .filter(
                SourceChapterLink.source == source,
                SourceChapterLink.series_id == source_series_id,
            )
            .all()
        )
        src_to_local = {link.chapter_id: link.local_chapter_id for link in links}
        local_to_src = {link.local_chapter_id: link.chapter_id for link in links}
        local_by_id = {d["id"]: d for d in local_chapters}

        merged: list[dict[str, object]] = []
        used_local: set[int] = set()

        for sc in catalog:
            local_id = src_to_local.get(sc.id)
            local = local_by_id.get(local_id) if local_id is not None else None
            if local is not None:
                entry = dict(local)
                entry["source_chapter_id"] = sc.id
                entry["is_downloaded"] = True
                if entry.get("number") is None and sc.number is not None:
                    entry["number"] = sc.number
                used_local.add(local_id)
            else:
                entry = {
                    "id": None,
                    "series_id": series.id,
                    "title": sc.title,
                    "number": sc.number,
                    "page_count": sc.page_count or 0,
                    "folder_path": None,
                    "archive_path": None,
                    "ocr_status": {"status": "not_started"},
                    "local_chapter_id": None,
                    "is_downloaded": False,
                    "is_read": False,
                    "source_chapter_id": sc.id,
                }
            merged.append(entry)

        # Local chapters that aren't present in the source catalog still appear.
        for d in local_chapters:
            if d["id"] not in used_local:
                extra = dict(d)
                if extra.get("source_chapter_id") is None:
                    extra["source_chapter_id"] = local_to_src.get(d["id"])
                merged.append(extra)

        merged.sort(
            key=lambda e: (
                e["number"] if e["number"] is not None else float("inf"),
                natural_sort_key(str(e.get("title") or "")),
            )
        )
        return merged

    def _collection_summary(self, collection: Collection) -> dict[str, object]:
        series_count = (
            self._db.query(CollectionSeries)
            .filter(CollectionSeries.collection_id == collection.id)
            .count()
        )
        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "cover_path": collection.cover_path,
            "series_count": series_count,
            "sort_order": collection.sort_order,
            "created_at": collection.created_at.isoformat(),
            "updated_at": collection.updated_at.isoformat(),
        }

    def _collection_detail(self, collection: Collection) -> dict[str, object]:
        summary = self._collection_summary(collection)
        # Series in collection, ordered by sort_order, with pagination
        # Gate-filtered via the join, not after the fact, so the reported
        # total matches the items -- a collection that says "12" over 11 covers
        # is the same disclosure as showing the twelfth.
        links = self._apply_mature_filter(
            self._db.query(CollectionSeries)
            .join(Series, Series.id == CollectionSeries.series_id)
            .filter(CollectionSeries.collection_id == collection.id)
            .order_by(CollectionSeries.sort_order.asc())
            .options(selectinload(CollectionSeries.series))
        ).all()
        summary["series"] = {
            "items": self._series_summaries([link.series for link in links]),
            "total": len(links),
            "page": 1,
            "per_page": len(links),
            "has_next": False,
        }
        return summary

    def _progress_dict(self, progress: ReadingProgress | None) -> dict[str, object] | None:
        if not progress:
            return None
        return {
            "series_id": progress.series_id,
            "chapter_id": progress.chapter_id,
            "last_page": progress.last_page,
            "scroll_offset_px": progress.scroll_offset_px,
            "progress_pct": progress.progress_pct,
            "started_at": progress.started_at.isoformat(),
            "last_read_at": progress.last_read_at.isoformat(),
        }


def get_library_intelligence_service(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> LibraryIntelligenceService:
    return LibraryIntelligenceService(
        db, user_id=ctx.user_id, profile_id=ctx.profile_id
    )
