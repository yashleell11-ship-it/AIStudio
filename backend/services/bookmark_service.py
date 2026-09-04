"""Smart bookmarks: exact position, object sync, both media.

Design 2026-09-05-smart-bookmarks. Split out of ``progress_service`` on
purpose: a bookmark and a reading position look superficially alike and merge
by *opposite* rules, and keeping them in one module is how they get conflated.

    ``ChapterProgress``  automatic, one per chapter, FURTHEST-WINS scalar.
    ``Bookmark``         deliberate, many per chapter, a user-created OBJECT.

Three things live here.

**Position.** ``(media_type, anchor_index, anchor_fraction, anchor_total)`` —
one generic anchor triple for both media, see ``database.models.Bookmark`` for
why. ``position_fraction`` on the wire turns it into the "62% of chapter 14"
the Bookmarks screen prints, computed here so the clients cannot each round it
differently.

**Sync.** Client-generated ids plus tombstones (:func:`decide`). The rule that
matters: **an upsert whose ``client_id`` is tombstoned is REFUSED.** Progress'
merge would happily re-create it, which is precisely how a stale device's
replayed outbox resurrects a bookmark the owner deleted on another device.

**Listing enrichment.** The Bookmarks screen must be able to choose between
bookmarks without opening any of them, so a listing carries the series title
(off the follow row that the 18+ gate already joins) and, for novels, the
sanitized text at the bookmarked paragraph — read from ``novel_chapter_cache``,
never refetched upstream.

18+ gate. The gate filters every READ: a gated row is absent from listings, and
server-derived enrichment (title, snippet) is withheld from the body echoed
back by a write. Writes themselves always apply. That is a deliberate
divergence from "refuse the write", and the reason is offline sync: a rejected
op sits in the device's outbox and is retried forever, so refusing would wedge
a client on an item it can never flush — while accepting discloses nothing,
because the row is the caller's own data in the caller's own profile and cannot
be read back while the gate is shut.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Annotated, Any, Iterable, Sequence

from fastapi import Depends
from sqlalchemy import and_, case, literal, select, tuple_
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.connector_directory import descriptors_by_source, mature_source_ids
from core.content_rating import (
    TRACKER_RATING_MATURE,
    mature_rating_predicate,
    resolve_mature_gate,
    resolve_tracker_rating,
)
from core.errors import AppError
from core.profile_context import ProfileContext, resolve_profile_context
from core.time_utils import utcnow
from database.models import (
    BOOKMARK_MEDIA_MANGA,
    BOOKMARK_MEDIA_NOVEL,
    BOOKMARK_MEDIA_TYPES,
    Bookmark,
    FollowedSeries,
    NovelChapterCache,
)
from database.session import get_db

#: Row-value ``IN`` chunk size, matching ``progress_service._IN_CHUNK``.
_IN_CHUNK = 300

#: Longest novel snippet returned per bookmark. Enough to recognise a passage,
#: short enough that a 200-row listing stays a small response.
SNIPPET_MAX_CHARS = 180

OP_UPSERT = "upsert"
OP_DELETE = "delete"
BOOKMARK_OPS = frozenset({OP_UPSERT, OP_DELETE})

#: Per-item outcomes reported by :meth:`BookmarkService.apply_batch`.
STATUS_CREATED = "created"
STATUS_UPDATED = "updated"
STATUS_STALE = "stale"
STATUS_TOMBSTONED = "tombstoned"
STATUS_ALREADY_DELETED = "already_deleted"
STATUS_REJECTED_DELETED = "rejected_deleted"
#: The item never reached the merge: it failed validation. Reported per item
#: rather than 400-ing the flush, because an outbox whose whole batch is
#: refused for one malformed row retries it forever and never drains.
STATUS_INVALID = "invalid"


# ---------------------------------------------------------------------------
# Pure merge — unit-testable without a database
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BookmarkOp:
    """One create/update/delete a client is flushing.

    ``client_id`` is the identity for every op. The identity columns are
    optional on a delete: a client replaying a delete for a bookmark this
    server has never seen still has to be able to record the tombstone (see
    :func:`decide`), and it may no longer hold the body.
    """

    op: str
    client_id: str
    source_id: str = ""
    series_key: str = ""
    chapter_key: str = ""
    chapter_number: float | None = None
    media_type: str = BOOKMARK_MEDIA_MANGA
    anchor_index: int = 1
    anchor_fraction: float = 0.0
    anchor_total: int = 0
    note: str | None = None
    #: The client's own clock for this change. Decides last-write-wins between
    #: two devices editing the same bookmark; absent means "now".
    updated_at: datetime | None = None


@dataclass(frozen=True)
class StoredState:
    """What the server already holds for one ``client_id``."""

    deleted: bool
    updated_at: datetime


def decide(stored: StoredState | None, op: BookmarkOp, *, now: datetime) -> str:
    """The merge rule, in full. Returns one of the ``STATUS_*`` constants.

    A bookmark is an object with an identity, not a scalar with an ordering,
    so the rules are the ones an object store needs:

    * **A tombstone is terminal.** An upsert against a deleted ``client_id``
      is ``rejected_deleted`` and changes nothing. This is the whole point:
      device A deletes a bookmark and syncs; device B, offline for a week,
      later flushes its own create for the same id; the bookmark must stay
      deleted. If the reader wants it back they bookmark again, which mints a
      NEW ``client_id`` — so "undelete" is expressible without ever making a
      tombstone reversible.
    * **A delete of an unknown id still writes a tombstone.** Otherwise the
      race just inverts: B's delete arrives before A's create has ever
      reached the server, the delete no-ops, and A's create then lands as a
      live bookmark that both devices believe is gone.
    * **A delete is never stale.** Deletes are terminal and idempotent, so
      clock order cannot make one lose; the alternative direction of that
      decision resurrects data, which is the failure being designed out.
    * **Two devices creating different bookmarks both survive** — trivially,
      because the identity is the client's uuid and not the position.
    * **Concurrent edits to one bookmark are last-write-wins** on the client
      clock, ties going to the stored row. Furthest-wins would be wrong here:
      dragging a bookmark *back* to an earlier page is a legitimate edit, and
      progress' "never rewind" rule would silently discard it.
    """
    if op.op == OP_DELETE:
        if stored is not None and stored.deleted:
            return STATUS_ALREADY_DELETED
        return STATUS_TOMBSTONED

    if stored is None:
        return STATUS_CREATED
    if stored.deleted:
        return STATUS_REJECTED_DELETED
    if (op.updated_at or now) <= stored.updated_at:
        return STATUS_STALE
    return STATUS_UPDATED


def to_naive_utc(value: datetime | None) -> datetime | None:
    """A client clock, forced into the naive-UTC the DB columns hold.

    Every timestamp column here is a naive SQLite ``DATETIME`` meaning UTC
    (see ``core.time_utils``), while a client is free to send
    ``2026-09-05T10:00:00Z`` or ``+05:30``. Comparing an aware datetime with a
    naive one is a ``TypeError``, so an offline flush carrying a normal
    ISO-8601 timestamp would 500 in the middle of :func:`decide` — convert at
    the boundary, once, and everything downstream stays naive.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def clamp_fraction(value: float | None) -> float:
    """A fraction, forced into 0.0–1.0. ``None``/garbage reads as 0.0."""
    try:
        number = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN
        return 0.0
    return min(1.0, max(0.0, number))


def position_fraction(
    anchor_index: int, anchor_fraction: float, anchor_total: int
) -> float | None:
    """How far through the CHAPTER the anchor sits, or ``None`` when unknown.

    ``None`` (rather than 0.0) when ``anchor_total`` is 0: the client did not
    record a unit count, so "0% of the chapter" would be a fabrication. Old
    page-only bookmarks migrated from before this design are exactly that case
    — they land honestly as "page 4, position unknown" rather than claiming to
    be at the start of the chapter.

    The index is clamped into range first, so a bookmark on a chapter that has
    since lost pages degrades to its end instead of reporting >100%.
    """
    if anchor_total <= 0:
        return None
    index = min(max(1, anchor_index), anchor_total)
    raw = (index - 1 + clamp_fraction(anchor_fraction)) / anchor_total
    return round(min(1.0, max(0.0, raw)), 4)


def snippet_at(
    paragraphs: Sequence[str],
    anchor_index: int,
    anchor_fraction: float,
    *,
    max_chars: int = SNIPPET_MAX_CHARS,
) -> tuple[str | None, bool]:
    """``(snippet, anchor_was_out_of_range)`` for a novel bookmark.

    Starts *at the bookmarked point* rather than at the paragraph's start —
    that is what makes a prose bookmark recognisable — snapped back to a word
    boundary and marked with a leading ellipsis so it never reads as the
    beginning of the paragraph when it isn't.

    Degrades honestly (design §3): if the chapter's paragraph count has shrunk
    below the recorded index, the nearest valid paragraph is used and the
    second return value says so, rather than failing or silently showing the
    top of the chapter.
    """
    total = len(paragraphs)
    if total == 0:
        return None, False
    wanted = max(1, anchor_index)
    index = min(wanted, total)
    stale = index != wanted
    text = (paragraphs[index - 1] or "").strip()
    if not text:
        return "", stale

    start = int(len(text) * clamp_fraction(anchor_fraction))
    start = min(start, max(0, len(text) - 1))
    if start > 0:
        boundary = text.rfind(" ", 0, start + 1)
        start = boundary + 1 if boundary != -1 else 0

    excerpt = text[start : start + max_chars]
    if len(text) - start > max_chars:
        cut = excerpt.rfind(" ")
        if cut > max_chars // 2:
            excerpt = excerpt[:cut]
        excerpt = excerpt.rstrip() + "…"
    if start > 0:
        excerpt = "…" + excerpt.lstrip()
    return excerpt, stale


def normalize_op(op: BookmarkOp) -> BookmarkOp:
    """Validate + coerce one op into storable values.

    Keys are ``fully_unquote``d exactly like every other identity in the
    backend, and never otherwise parsed.
    """
    if op.op not in BOOKMARK_OPS:
        raise AppError(
            f"Unknown bookmark op {op.op!r}.",
            code="invalid_bookmark_op",
            status_code=400,
            details={"allowed": sorted(BOOKMARK_OPS)},
        )
    client_id = (op.client_id or "").strip()
    if not client_id or len(client_id) > 64:
        raise AppError(
            "A bookmark needs a client id of 1-64 characters.",
            code="invalid_client_id",
            status_code=400,
        )
    media_type = (op.media_type or BOOKMARK_MEDIA_MANGA).strip().lower()
    if media_type not in BOOKMARK_MEDIA_TYPES:
        raise AppError(
            f"Unknown bookmark media type {op.media_type!r}.",
            code="invalid_media_type",
            status_code=400,
            details={"allowed": sorted(BOOKMARK_MEDIA_TYPES)},
        )
    if op.op == OP_UPSERT and not (
        op.source_id and op.series_key and op.chapter_key
    ):
        raise AppError(
            "A bookmark needs source_id, series_key and chapter_key.",
            code="invalid_bookmark",
            status_code=400,
            details={"client_id": client_id},
        )
    return replace(
        op,
        client_id=client_id,
        source_id=op.source_id or "",
        series_key=fully_unquote(op.series_key) if op.series_key else "",
        chapter_key=fully_unquote(op.chapter_key) if op.chapter_key else "",
        media_type=media_type,
        anchor_index=max(1, int(op.anchor_index or 1)),
        anchor_fraction=clamp_fraction(op.anchor_fraction),
        anchor_total=max(0, int(op.anchor_total or 0)),
        note=(op.note or None),
        updated_at=to_naive_utc(op.updated_at),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class BookmarkService:
    def __init__(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._profile_id = profile_id
        self._gate: bool | None = None

    # --- scope + gate ----------------------------------------------------

    def _require_owner(self) -> tuple[int, int | None]:
        if self._user_id is None:
            raise AppError(
                "Authentication is required to use bookmarks.",
                code="auth_required",
                status_code=401,
            )
        return self._user_id, self._profile_id

    def _require_profile(self) -> tuple[int, int]:
        """Owner + active profile, for the write paths.

        ``profile_id`` is NOT NULL on ``bookmarks``, so a write from the
        unscoped bucket would be an IntegrityError 500; return the documented
        400 the clients already handle, exactly like ``ProgressService``.
        """
        user_id, profile_id = self._require_owner()
        if profile_id is None:
            raise AppError(
                "An active profile is required for this action.",
                code="profile_required",
                status_code=400,
            )
        return user_id, profile_id

    def _scope(self, stmt):
        """Every statement in this module goes through here.

        ``None`` is the unscoped bucket, not a wildcard: ``profile_id`` is NOT
        NULL, so an unscoped caller correctly sees nothing rather than the
        account's every profile merged together.
        """
        stmt = stmt.where(Bookmark.user_id == self._user_id)
        if self._profile_id is None:
            return stmt.where(Bookmark.profile_id.is_(None))
        return stmt.where(Bookmark.profile_id == self._profile_id)

    @property
    def gate_open(self) -> bool:
        """Is 18+ content allowed for this (user, profile)? Resolved once."""
        if self._gate is None:
            self._gate = resolve_mature_gate(
                self._db, self._profile_id, self._user_id
            )
        return bool(self._gate)

    def _mature_case(self):
        """1 when a bookmark's series is 18+ for this profile, else 0.

        SQL mirror of :func:`core.content_rating.resolve_tracker_rating` in the
        same priority order — explicit override, rating captured at follow
        time, then the source's own maturity — copied from
        ``reading_stats_service._progress_mature_case`` so bookmarks and the
        statistics screen can never disagree about what is adult. Unknown stays
        0 for the reason recorded there.
        """
        mature_sources = mature_source_ids()
        source_mature = (
            case((Bookmark.source_id.in_(mature_sources), 1), else_=0)
            if mature_sources
            else literal(0)
        )
        return case(
            (FollowedSeries.mature_override == 1, 1),
            (FollowedSeries.mature_override == 0, 0),
            (
                FollowedSeries.content_rating.is_not(None),
                case(
                    (mature_rating_predicate(FollowedSeries.content_rating), 1),
                    else_=0,
                ),
            ),
            else_=source_mature,
        )

    def _follow_join(self, stmt):
        """Outer-join the follow row for the title AND the 18+ rating.

        Joined unconditionally, unlike the statistics screen's conditional
        join: there the join cost was paid per session row across tens of
        thousands, here a profile has a few hundred bookmarks at most and the
        Bookmarks screen wants the series title on every one of them —
        fetching it separately would be the extra round trip this listing
        exists to avoid. ``uq_followed_series`` guarantees at most one match,
        so the join can never fan a bookmark out into duplicates.
        """
        return stmt.outerjoin(
            FollowedSeries,
            and_(
                FollowedSeries.user_id == Bookmark.user_id,
                FollowedSeries.profile_id == Bookmark.profile_id,
                FollowedSeries.source_id == Bookmark.source_id,
                FollowedSeries.series_key == Bookmark.series_key,
            ),
        )

    def _series_meta(
        self, rows: Sequence[Bookmark]
    ) -> dict[tuple[str, str], tuple[str | None, bool]]:
        """``(source_id, series_key) -> (title, is_gated)`` for written rows.

        The WRITE path's counterpart to the listing's SQL gate. It resolves the
        rating in Python through :func:`resolve_tracker_rating` — the canonical
        implementation the SQL in :meth:`_mature_case` mirrors — because here
        the row count is a handful and calling the authority directly is one
        fewer place for the two to drift.
        """
        pairs = sorted({(r.source_id, r.series_key) for r in rows if r.source_id})
        if not pairs:
            return {}
        follows: dict[tuple[str, str], FollowedSeries] = {}
        target = tuple_(FollowedSeries.source_id, FollowedSeries.series_key)
        for start in range(0, len(pairs), _IN_CHUNK):
            chunk = pairs[start : start + _IN_CHUNK]
            stmt = select(FollowedSeries).where(
                FollowedSeries.user_id == self._user_id,
                FollowedSeries.profile_id == self._profile_id,
                target.in_(chunk),
            )
            for row in self._db.execute(stmt).scalars().all():
                follows[(row.source_id, row.series_key)] = row

        gate_open = self.gate_open
        descriptors = descriptors_by_source()
        meta: dict[tuple[str, str], tuple[str | None, bool]] = {}
        for key in pairs:
            follow = follows.get(key)
            descriptor = descriptors.get(key[0])
            if gate_open:
                gated = False
            elif follow is not None:
                gated = resolve_tracker_rating(follow, descriptor) == (
                    TRACKER_RATING_MATURE
                )
            else:
                # No follow row: the only signal left is the source's own
                # maturity, which is exactly what _mature_case falls through to.
                gated = bool(descriptor is not None and descriptor.mature)
            meta[key] = (None if gated else (follow.title if follow else None), gated)
        return meta

    # --- novel snippets --------------------------------------------------

    def _paragraph_index(
        self, rows: Sequence[Bookmark]
    ) -> dict[tuple[str, str, str], list[str]]:
        """Cached paragraphs for every novel bookmark in one batch.

        Reads ``novel_chapter_cache`` and nothing else — a Bookmarks screen
        must never trigger an upstream fetch, and a cache miss simply means no
        snippet. ``last_used_at`` is deliberately NOT bumped: listing a
        bookmark is not reading the chapter, and letting it count as a use
        would distort the cache's LRU eviction in favour of chapters nobody
        has opened.
        """
        keys = sorted(
            {
                (r.source_id, r.series_key, r.chapter_key)
                for r in rows
                if r.media_type == BOOKMARK_MEDIA_NOVEL and r.source_id
            }
        )
        if not keys:
            return {}
        target = tuple_(
            NovelChapterCache.source_id,
            NovelChapterCache.series_key,
            NovelChapterCache.chapter_key,
        )
        found: dict[tuple[str, str, str], list[str]] = {}
        for start in range(0, len(keys), _IN_CHUNK):
            chunk = keys[start : start + _IN_CHUNK]
            cached = self._db.execute(
                select(
                    NovelChapterCache.source_id,
                    NovelChapterCache.series_key,
                    NovelChapterCache.chapter_key,
                    NovelChapterCache.paragraphs,
                ).where(target.in_(chunk))
            ).all()
            for source_id, series_key, chapter_key, blob in cached:
                try:
                    paragraphs = json.loads(blob)
                except (TypeError, ValueError):
                    paragraphs = []
                if isinstance(paragraphs, list):
                    found[(source_id, series_key, chapter_key)] = [
                        str(p) for p in paragraphs
                    ]
        return found

    # --- serialization ---------------------------------------------------

    def _serialize(
        self,
        row: Bookmark,
        *,
        series_title: str | None = None,
        paragraphs: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        snippet: str | None = None
        stale = False
        if row.media_type == BOOKMARK_MEDIA_NOVEL and paragraphs:
            snippet, stale = snippet_at(
                paragraphs, row.anchor_index, row.anchor_fraction
            )
        return {
            "id": row.id,
            "client_id": row.client_id,
            "source_id": row.source_id,
            "series_key": row.series_key,
            "series_title": series_title,
            "chapter_key": row.chapter_key,
            "chapter_number": row.chapter_number,
            "media_type": row.media_type,
            "anchor_index": row.anchor_index,
            "anchor_fraction": row.anchor_fraction,
            "anchor_total": row.anchor_total,
            # Deprecated mirror for clients written before this design. For
            # manga this IS the page number — ``anchor_index`` is 1-based,
            # like the ``page`` column it replaced — so a not-yet-updated
            # reader keeps rendering. Null for novels, where it means nothing.
            "page": (
                row.anchor_index
                if row.media_type == BOOKMARK_MEDIA_MANGA
                else None
            ),
            "position_fraction": position_fraction(
                row.anchor_index, row.anchor_fraction, row.anchor_total
            ),
            "snippet": snippet,
            # False means "not known to be stale", never "verified fresh":
            # it can only be established for a novel whose text is cached.
            "anchor_stale": stale,
            "note": row.note,
            "deleted": row.deleted_at is not None,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "deleted_at": _iso(row.deleted_at),
        }

    def _decorate(
        self, rows: Sequence[Bookmark], titles: dict[tuple[str, str], str | None]
    ) -> list[dict[str, Any]]:
        paragraphs = self._paragraph_index(rows)
        return [
            self._serialize(
                row,
                series_title=titles.get((row.source_id, row.series_key)),
                paragraphs=paragraphs.get(
                    (row.source_id, row.series_key, row.chapter_key)
                ),
            )
            for row in rows
        ]

    # --- reads -----------------------------------------------------------

    def list_bookmarks(
        self,
        *,
        source_id: str | None = None,
        series_key: str | None = None,
        since: datetime | None = None,
        include_deleted: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """The Bookmarks screen, and the pull half of sync.

        Two orderings, because they answer two different questions:

        * no ``since`` — newest change first, which is the order the Bookmarks
          screen wants;
        * with ``since`` — OLDEST change first, because a delta pull pages
          forward by feeding the last ``updated_at`` back in, and newest-first
          plus a ``limit`` would silently strand every change past the page
          boundary.

        ``include_deleted`` is what makes tombstones reachable: a device that
        has been offline learns about deletes by pulling
        ``?since=<cursor>&include_deleted=true`` and removing every returned
        row whose ``deleted`` is true.
        """
        self._require_owner()
        # The column is naive UTC; a client cursor is routinely tz-aware, and
        # SQLite's bind processor would silently drop the offset and compare
        # the wrong instant.
        since = to_naive_utc(since)
        stmt = self._follow_join(select(Bookmark, FollowedSeries.title))
        stmt = self._scope(stmt)
        if not include_deleted:
            stmt = stmt.where(Bookmark.deleted_at.is_(None))
        if since is not None:
            stmt = stmt.where(Bookmark.updated_at > since)
        if source_id:
            stmt = stmt.where(Bookmark.source_id == source_id)
        if series_key:
            stmt = stmt.where(Bookmark.series_key == fully_unquote(series_key))
        if not self.gate_open:
            stmt = stmt.where(self._mature_case() == 0)
        stmt = (
            stmt.order_by(Bookmark.updated_at.asc(), Bookmark.id.asc())
            if since is not None
            else stmt.order_by(Bookmark.updated_at.desc(), Bookmark.id.desc())
        )
        result = self._db.execute(stmt.limit(limit).offset(offset)).all()
        rows = [row for row, _title in result]
        titles = {
            (row.source_id, row.series_key): title for row, title in result
        }
        return self._decorate(rows, titles)

    # --- writes ----------------------------------------------------------

    def _echo(self, rows: Sequence[Bookmark]) -> dict[str, dict[str, Any]]:
        """Serialize written rows, keyed by ``client_id``.

        Rows whose series is gated for this profile lose their server-derived
        enrichment (series title, novel snippet) and keep only what the caller
        itself sent — the write applies, but the response is still a read and
        the gate applies to reads.
        """
        meta = self._series_meta(rows)
        visible = [
            r for r in rows if not meta.get((r.source_id, r.series_key), (None, False))[1]
        ]
        paragraphs = self._paragraph_index(visible)
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = (row.source_id, row.series_key)
            title, gated = meta.get(key, (None, False))
            out[row.client_id] = self._serialize(
                row,
                series_title=title,
                paragraphs=(
                    None
                    if gated
                    else paragraphs.get(
                        (row.source_id, row.series_key, row.chapter_key)
                    )
                ),
            )
        return out

    def _fetch_by_client_ids(
        self, client_ids: Sequence[str]
    ) -> dict[str, Bookmark]:
        """Every row a batch will touch, in one statement per chunk.

        The scoped UNIQUE on ``(user_id, profile_id, client_id)`` means each id
        matches at most one row, and ``_scope`` means it can only ever be one
        of *this* profile's.
        """
        found: dict[str, Bookmark] = {}
        unique = sorted(set(client_ids))
        for start in range(0, len(unique), _IN_CHUNK):
            chunk = unique[start : start + _IN_CHUNK]
            stmt = self._scope(
                select(Bookmark).where(Bookmark.client_id.in_(chunk))
            )
            for row in self._db.execute(stmt).scalars().all():
                found[row.client_id] = row
        return found

    def _apply_one(
        self,
        op: BookmarkOp,
        *,
        known: dict[str, Bookmark],
        now: datetime,
    ) -> tuple[str, Bookmark | None]:
        """Apply one normalized op into the session WITHOUT committing.

        ``known`` is read AND written, so two ops on the same ``client_id``
        inside one batch see each other — an outbox that recorded a create and
        then a delete for the same bookmark must end tombstoned, whichever
        order the flush happens to serialize them in.
        """
        user_id, profile_id = self._require_profile()
        row = known.get(op.client_id)
        stored = (
            StoredState(deleted=row.deleted_at is not None, updated_at=row.updated_at)
            if row is not None
            else None
        )
        status = decide(stored, op, now=now)
        stamp = op.updated_at or now

        if status in (STATUS_STALE, STATUS_REJECTED_DELETED, STATUS_ALREADY_DELETED):
            return status, row

        if status == STATUS_TOMBSTONED:
            if row is None:
                # Pre-emptive tombstone: the delete arrived before (or instead
                # of) the create it refers to. Identity columns are whatever
                # the client could still supply, empty when it no longer holds
                # the body — the client re-identifies by client_id, never by
                # these.
                row = Bookmark(
                    user_id=user_id,
                    profile_id=profile_id,
                    client_id=op.client_id,
                    source_id=op.source_id,
                    series_key=op.series_key,
                    chapter_key=op.chapter_key,
                    chapter_number=op.chapter_number,
                    media_type=op.media_type,
                    anchor_index=op.anchor_index,
                    anchor_fraction=op.anchor_fraction,
                    anchor_total=op.anchor_total,
                    note=op.note,
                    created_at=stamp,
                )
                self._db.add(row)
                known[op.client_id] = row
            row.deleted_at = stamp
            row.updated_at = stamp
            self._db.flush()
            return status, row

        if status == STATUS_CREATED:
            row = Bookmark(
                user_id=user_id,
                profile_id=profile_id,
                client_id=op.client_id,
                source_id=op.source_id,
                series_key=op.series_key,
                chapter_key=op.chapter_key,
                chapter_number=op.chapter_number,
                media_type=op.media_type,
                anchor_index=op.anchor_index,
                anchor_fraction=op.anchor_fraction,
                anchor_total=op.anchor_total,
                note=op.note,
                created_at=stamp,
                updated_at=stamp,
            )
            self._db.add(row)
            known[op.client_id] = row
            self._db.flush()
            return status, row

        # STATUS_UPDATED — a live row moved or its note changed.
        assert row is not None  # decide() cannot return "updated" without one
        row.source_id = op.source_id
        row.series_key = op.series_key
        row.chapter_key = op.chapter_key
        row.chapter_number = op.chapter_number
        row.media_type = op.media_type
        row.anchor_index = op.anchor_index
        row.anchor_fraction = op.anchor_fraction
        row.anchor_total = op.anchor_total
        row.note = op.note
        row.updated_at = stamp
        self._db.flush()
        return status, row

    def apply_batch(self, ops: Sequence[BookmarkOp]) -> dict[str, Any]:
        """Offline-sync catch-up, applied in ONE transaction.

        Deliberately mirrors ``ProgressService.save_batch``' transaction
        discipline (one commit, not N write-lock/fsync cycles against the
        single-writer SQLite) and *nothing* of its merge. Individual items are
        never fatal: a refused op reports its status and the rest of the batch
        still lands, because a client whose whole flush 400s on one bad item
        can make no progress at all.
        """
        self._require_profile()
        # Validate per item, not per batch. A malformed row is the client's
        # bug, but 400-ing the whole flush wedges its outbox on an item it can
        # never send; reported as ``invalid``, it is dropped and the rest lands.
        prepared: list[tuple[BookmarkOp, AppError | None]] = []
        for raw in ops:
            try:
                prepared.append((normalize_op(raw), None))
            except AppError as exc:
                prepared.append((raw, exc))

        known = self._fetch_by_client_ids(
            [op.client_id for op, err in prepared if err is None]
        )
        now = utcnow()

        applied: list[tuple[BookmarkOp, str, Bookmark | None, AppError | None]] = []
        for op, err in prepared:
            if err is not None:
                applied.append((op, STATUS_INVALID, None, err))
                continue
            status, row = self._apply_one(op, known=known, now=now)
            applied.append((op, status, row, None))
        self._db.commit()

        bodies = self._echo(
            [row for _op, _st, row, _err in applied if row is not None]
        )
        counts = {
            STATUS_CREATED: 0,
            STATUS_UPDATED: 0,
            STATUS_STALE: 0,
            STATUS_TOMBSTONED: 0,
            STATUS_ALREADY_DELETED: 0,
            STATUS_REJECTED_DELETED: 0,
            STATUS_INVALID: 0,
        }
        items = []
        for op, status, row, err in applied:
            counts[status] += 1
            items.append(
                {
                    "client_id": op.client_id,
                    "op": op.op,
                    "status": status,
                    "error": None if err is None else err.code,
                    "bookmark": (
                        bodies.get(row.client_id) if row is not None else None
                    ),
                }
            )
        return {
            "received": len(items),
            "created": counts[STATUS_CREATED],
            "updated": counts[STATUS_UPDATED],
            "tombstoned": counts[STATUS_TOMBSTONED],
            "rejected": counts[STATUS_REJECTED_DELETED]
            + counts[STATUS_STALE]
            + counts[STATUS_ALREADY_DELETED]
            + counts[STATUS_INVALID],
            "items": items,
        }

    def add_bookmark(
        self,
        *,
        source_id: str,
        series_key: str,
        chapter_key: str,
        client_id: str | None = None,
        chapter_number: float | None = None,
        media_type: str = BOOKMARK_MEDIA_MANGA,
        anchor_index: int = 1,
        anchor_fraction: float = 0.0,
        anchor_total: int = 0,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Create (or idempotently re-apply) one bookmark, online.

        ``client_id`` is optional here only because a client that is online at
        capture time has nothing to reconcile; one is minted when absent so
        every row has the same identity shape and can be deleted through the
        batch path later.

        Unlike the batch, a create against a tombstone raises rather than
        reporting a status: this endpoint speaks for a single user action, and
        silently doing nothing would look like a working bookmark that then
        vanishes.
        """
        self._require_profile()
        op = normalize_op(
            BookmarkOp(
                op=OP_UPSERT,
                client_id=client_id or str(uuid.uuid4()),
                source_id=source_id,
                series_key=series_key,
                chapter_key=chapter_key,
                chapter_number=chapter_number,
                media_type=media_type,
                anchor_index=anchor_index,
                anchor_fraction=anchor_fraction,
                anchor_total=anchor_total,
                note=note,
            )
        )
        known = self._fetch_by_client_ids([op.client_id])
        status, row = self._apply_one(op, known=known, now=utcnow())
        if status == STATUS_REJECTED_DELETED:
            self._db.rollback()
            raise AppError(
                "That bookmark was deleted; create a new one instead.",
                code="bookmark_deleted",
                status_code=409,
                details={"client_id": op.client_id},
            )
        self._db.commit()
        assert row is not None
        return self._echo([row])[row.client_id]

    def delete_bookmark(self, bookmark_id: int) -> None:
        """Tombstone one of *this profile's* bookmarks by row id, or 404.

        Scoped by ``(user_id, profile_id)`` and not by ``user_id`` alone: the
        listing is profile-scoped, so an id-only check let a profile delete a
        bookmark it could not see by guessing its id.

        An already-tombstoned row is a 404, matching the listing that already
        hides it. The row is never removed — see ``models.Bookmark``.
        """
        user_id, profile_id = self._require_owner()
        row = self._db.get(Bookmark, bookmark_id)
        if (
            row is None
            or row.user_id != user_id
            or row.profile_id != profile_id
            or row.deleted_at is not None
        ):
            raise AppError("Bookmark not found.", code="not_found", status_code=404)
        stamp = utcnow()
        row.deleted_at = stamp
        row.updated_at = stamp
        self._db.commit()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def get_bookmark_service(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> BookmarkService:
    return BookmarkService(db, user_id=ctx.user_id, profile_id=ctx.profile_id)
