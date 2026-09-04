"""Read-through TTL cache over connector metadata (spec §3.10, §5.2).

``source_series_cache`` lets the library grid, continue-reading strip, and
notifications render titles/covers/chapter counts without hitting a connector
on every request. ``source_browse_cache`` does the same for whole browse
*pages*, so opening a source renders the grid without a live scrape. Both are
*purely* caches: any row may be deleted at any time and is repopulated on the
next read.

Semantics (both tables):
  * fresh row (``fetched_at`` within its TTL)   → serve it
  * missing / stale                             → refetch, upsert, serve
  * connector failure with any row present      → serve stale (flagged)
  * connector failure with nothing cached       → raise

Rows are GLOBAL — a page one caller fetched serves every caller — but the
18+ gate is applied per caller on every browse-cache read
(``BrowseService.ensure_visible``), so a mature source's cached page can
never reach a profile whose gate is closed.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.config import get_settings
from core.content_rating import rating_from_genres
from core.errors import AppError
from core.time_utils import utcnow
from database.models import SourceBrowseCache, SourceSeriesCache
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service

logger = logging.getLogger("manhwamaniacs.source_cache")

#: ``cache.status`` values in browse responses. The client contract:
#:   * ``fresh`` — served from cache within TTL; no connector was contacted.
#:   * ``live``  — the connector was fetched during this request.
#:   * ``stale`` — the connector FAILED; an expired (or force-refreshed) cached
#:     page was served instead. ``cache.stale`` is true only here, and
#:     ``cache.fetched_at`` says how old the data is.
CACHE_FRESH = "fresh"
CACHE_LIVE = "live"
CACHE_STALE = "stale"


def live_cache_info() -> dict[str, Any]:
    """The ``cache`` block for a response that just came off the connector."""
    return {"status": CACHE_LIVE, "stale": False, "fetched_at": utcnow().isoformat()}


def _loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


# --- chapter-list parse memo ----------------------------------------------
#
# ``source_series_cache.chapters`` is a JSON array, and every read of a series
# — the reader manifest, a novel chapter's prev/next, the series screen —
# parses the whole thing. That is fine for a 40-chapter manhwa and expensive
# for the long tail: measured on the VPS, novelarchive's "Shadow Slave" is
# 3,174 chapters / 314 KB, and ``json.loads`` alone was 9.4 ms of the 9.5 ms a
# CACHE HIT on /novels/chapter took. novelfull carries 3,956; baozimh 3,874.
#
# So the parse is memoized process-wide, keyed by the row's identity AND its
# ``fetched_at``. That key is what keeps this from changing any answer:
# ``_upsert`` bumps ``fetched_at`` whenever a chapter list is written, so a
# refreshed list is a different key and the stale parse can never be served.
# A row deleted outright simply misses.
#
# Bounded by total chapters rather than entries, because entries differ in
# size by two orders of magnitude and a per-entry cap would either waste the
# budget on 40-chapter series or blow it on 4,000-chapter ones.
_CHAPTER_MEMO_MAX_CHAPTERS = 20_000
_chapter_memo: "OrderedDict[tuple[str, str, str], list[Any]]" = OrderedDict()
_chapter_memo_chapters = 0
_chapter_memo_lock = threading.Lock()


def _memoized_chapters(row: SourceSeriesCache) -> list[Any]:
    """``row.chapters`` parsed, reusing the last parse of this exact row.

    Returns a shallow copy of the list: callers only read it today, but a
    shared list that someone later sorts in place would corrupt every
    subsequent request, and copying 3,000 pointers costs ~20 us against the
    9.4 ms it saves.
    """
    global _chapter_memo_chapters
    raw = row.chapters
    if not raw:
        return []
    fetched = row.fetched_at.isoformat() if row.fetched_at else ""
    # Identity + write time + byte length. ``fetched_at`` alone would already
    # be enough (it is bumped by every chapter-list write); the length is a
    # free second opinion, so two different lists written inside the same
    # microsecond cannot share a parse.
    key = (row.source_id, row.series_key, f"{fetched}:{len(raw)}")
    with _chapter_memo_lock:
        hit = _chapter_memo.get(key)
        if hit is not None:
            _chapter_memo.move_to_end(key)
            return list(hit)
    parsed = _loads(raw) or []
    if not isinstance(parsed, list):
        return []
    with _chapter_memo_lock:
        if key not in _chapter_memo:
            _chapter_memo[key] = parsed
            _chapter_memo_chapters += len(parsed)
        _chapter_memo.move_to_end(key)
        while _chapter_memo_chapters > _CHAPTER_MEMO_MAX_CHAPTERS and len(
            _chapter_memo
        ) > 1:
            _evicted_key, evicted = _chapter_memo.popitem(last=False)
            _chapter_memo_chapters -= len(evicted)
    return list(parsed)


def reset_chapter_memo() -> None:
    """Drop the parse memo. For tests; production never needs it."""
    global _chapter_memo_chapters
    with _chapter_memo_lock:
        _chapter_memo.clear()
        _chapter_memo_chapters = 0


def _normalize_sort(sort: str | None) -> str:
    """Cache-key form of the ``sort`` facet; mirrors ``list_series``."""
    cleaned = (sort or "").strip()
    return "" if cleaned == "default" else cleaned


def _normalize_genre(genre: str | None) -> str:
    return (genre or "").strip()


# --- background next-page warm --------------------------------------------
#
# After serving a browse page (fresh or live, never stale), the next page is
# fetched in the background so paging forward is instant. Strictly one page
# ahead, deduplicated, and gated on ``settings.browse_prefetch_enabled`` —
# never a fan-out, and at most one extra connector request per page a human
# actually viewed. The three module hooks below exist so tests can run the
# warm inline against their own session/service.

_warm_inflight: set[tuple[str, str, str, int]] = set()
_warm_lock = threading.Lock()


def _spawn_warm(work) -> None:
    threading.Thread(target=work, name="browse-warm", daemon=True).start()


def _open_warm_session() -> Session:
    from database.session import SessionLocal

    return SessionLocal()


def _build_warm_browse(db: Session, mature_enabled: bool) -> BrowseService:
    return BrowseService(mature_enabled=mature_enabled, db=db)


class SourceCacheService:
    def __init__(self, db: Session, browse: BrowseService) -> None:
        self._db = db
        self._browse = browse

    # --- public API ------------------------------------------------------

    def get_series_meta(
        self, source_id: str, series_key: str, *, force: bool = False
    ) -> dict[str, Any]:
        series_key = fully_unquote(series_key)
        row = self._db.get(SourceSeriesCache, (source_id, series_key))
        # ``chapters is not None`` guards against browse write-through rows: a
        # browse listing carries metadata but no chapter list, so such a row is
        # *partial* — good enough to be the stale fallback below, never good
        # enough to satisfy a fresh read (a "fresh" hit with a silently empty
        # chapter list would blank the series screen).
        if (
            row is not None
            and not force
            and self._is_fresh(row)
            and row.chapters is not None
        ):
            return self._serialize(row)

        try:
            meta = self._browse.get_series(source_id, series_key)
            chapters = self._browse.get_chapters(source_id, series_key)
        except (AppError, Exception) as exc:  # noqa: BLE001 - cache must degrade
            if row is not None:
                logger.warning(
                    "source_cache: connector failed for %s/%s, serving stale (%s)",
                    source_id,
                    series_key,
                    exc,
                )
                return self._serialize(row)
            raise

        row = self._upsert(source_id, series_key, meta, chapters)
        return self._serialize(row)

    def get_chapter_list(
        self, source_id: str, series_key: str, *, force: bool = False
    ) -> list[dict[str, Any]]:
        return self.get_series_meta(source_id, series_key, force=force).get(
            "chapters", []
        )

    def get_browse_page(
        self,
        source_id: str,
        *,
        page: int = 1,
        sort: str | None = None,
        genre: str | None = None,
        force: bool = False,
        warm_next: bool = False,
    ) -> dict[str, Any]:
        """One browse page, served from ``source_browse_cache`` when possible.

        The returned dict is the listing exactly as ``BrowseService.list_series``
        shapes it, plus a ``cache`` block: ``{"status": "fresh"|"live"|"stale",
        "stale": bool, "fetched_at": ISO-8601 UTC}`` (see the constants at the
        top of this module for what each status means).

        ``force`` refetches even a fresh row (client pull-to-refresh) — but a
        connector failure still falls back to whatever row exists, because a
        refresh gesture degrading to "same grid as before" beats an error
        screen. ``warm_next`` opportunistically fetches the next page in the
        background after a fresh/live serve (see ``_maybe_warm_next``).

        Search results (``query=...``) never come through here: they bypass the
        cache entirely (unbounded key cardinality; see ``routes/sources.py``).
        """
        # Per-caller 18+ gate, applied on EVERY read. Cache rows are global;
        # whether *this* caller may see the source is not. No network involved.
        self._browse.ensure_visible(source_id)

        sort_key = _normalize_sort(sort)
        genre_key = _normalize_genre(genre)
        key = (source_id, sort_key, genre_key, page)
        try:
            row = self._db.get(SourceBrowseCache, key)
        except Exception:  # noqa: BLE001 - e.g. a DB predating the migration
            logger.warning(
                "browse_cache unavailable; browsing live", exc_info=True
            )
            self._db.rollback()
            row = None

        if row is not None and not force and self._browse_row_fresh(row):
            payload = self._browse_payload(row, CACHE_FRESH)
            if warm_next:
                self._maybe_warm_next(source_id, sort_key, genre_key, page, payload)
            return payload

        try:
            listing = self._browse.list_series(
                source_id,
                page=page,
                sort=sort_key or None,
                genre=genre_key or None,
            )
        except (AppError, Exception) as exc:  # noqa: BLE001 - cache must degrade
            if row is not None:
                logger.warning(
                    "browse_cache: connector failed for %s (sort=%r genre=%r "
                    "page=%d), serving stale from %s (%s)",
                    source_id,
                    sort_key,
                    genre_key,
                    page,
                    row.fetched_at,
                    exc,
                )
                return self._browse_payload(row, CACHE_STALE)
            raise

        try:
            row = self._store_browse_page(key, listing)
            self._write_through_listing(source_id, listing.get("items") or [])
            self._evict_oldest(
                SourceBrowseCache, get_settings().browse_cache_max_rows
            )
            self._evict_oldest(
                SourceSeriesCache, get_settings().source_cache_max_rows
            )
            self._db.commit()
        except Exception:  # noqa: BLE001 - a cache write must never break a browse
            logger.exception("browse_cache: cache write failed")
            self._db.rollback()

        payload = dict(listing)
        payload["cache"] = live_cache_info()
        if warm_next:
            self._maybe_warm_next(source_id, sort_key, genre_key, page, payload)
        return payload

    def write_through(
        self,
        source_id: str,
        series_key: str,
        meta: dict[str, Any] | None,
        chapters: list[dict[str, Any]] | None = None,
    ) -> None:
        """Opportunistic write when a caller already has fresh connector data
        in hand (spec §3.10 — ``browse_service`` / ``source_service`` writes)."""
        try:
            self._upsert(source_id, fully_unquote(series_key), meta or {}, chapters)
        except Exception:  # noqa: BLE001 - a cache write must never break a read
            logger.exception("source_cache: opportunistic write failed")
            self._db.rollback()

    def invalidate(self, source_id: str, series_key: str) -> None:
        row = self._db.get(
            SourceSeriesCache, (source_id, fully_unquote(series_key))
        )
        if row is not None:
            self._db.delete(row)
            self._db.commit()

    # --- internals -----------------------------------------------------

    def _is_fresh(self, row: SourceSeriesCache) -> bool:
        ttl = timedelta(minutes=get_settings().source_cache_ttl_minutes)
        return (utcnow() - row.fetched_at) < ttl

    def _upsert(
        self,
        source_id: str,
        series_key: str,
        meta: dict[str, Any],
        chapters: list[dict[str, Any]] | None,
    ) -> SourceSeriesCache:
        row = self._merge_series_row(source_id, series_key, meta, chapters)
        self._evict_oldest(SourceSeriesCache, get_settings().source_cache_max_rows)
        self._db.commit()
        self._db.refresh(row)
        return row

    def _merge_series_row(
        self,
        source_id: str,
        series_key: str,
        meta: dict[str, Any],
        chapters: list[dict[str, Any]] | None,
    ) -> SourceSeriesCache:
        """Merge connector data into one ``source_series_cache`` row (no commit).

        ``fetched_at`` is only bumped when a *chapter list* arrives (or the row
        is new): metadata-only writes — the browse-listing write-through — must
        not extend an existing row's freshness, or a grid full of thumbnails
        would keep postponing the chapter refetch that the series screen needs.
        """
        row = self._db.get(SourceSeriesCache, (source_id, series_key))
        is_new = row is None
        if row is None:
            row = SourceSeriesCache(source_id=source_id, series_key=series_key)
            self._db.add(row)

        if meta:
            row.title = str(meta.get("title") or row.title or "")
            row.cover_url = meta.get("cover_url", row.cover_url)
            row.description = meta.get("description", row.description)
            row.author = meta.get("author", row.author)
            row.artist = meta.get("artist", row.artist)
            row.status = meta.get("status", row.status)
            row.year = meta.get("year", row.year)
            row.content_rating = meta.get("content_rating", row.content_rating)
            genres = meta.get("genres")
            if genres is not None:
                row.genres = json.dumps(list(genres))
        if chapters is not None:
            row.chapters = json.dumps(
                [
                    {
                        "key": c.get("id") or c.get("key"),
                        "number": c.get("number"),
                        "title": c.get("title"),
                        "published_at": c.get("release_date")
                        or c.get("published_at"),
                        "page_count": c.get("page_count"),
                    }
                    for c in chapters
                ]
            )
        if chapters is not None or is_new:
            row.fetched_at = utcnow()
        return row

    # --- browse-listing cache internals --------------------------------

    def _browse_row_fresh(self, row: SourceBrowseCache) -> bool:
        ttl = timedelta(minutes=get_settings().browse_cache_ttl_minutes)
        return (utcnow() - row.fetched_at) < ttl

    @staticmethod
    def _browse_payload(row: SourceBrowseCache, status: str) -> dict[str, Any]:
        listing = _loads(row.payload) or {"items": []}
        listing["cache"] = {
            "status": status,
            "stale": status == CACHE_STALE,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }
        return listing

    def _store_browse_page(
        self, key: tuple[str, str, str, int], listing: dict[str, Any]
    ) -> SourceBrowseCache:
        """Upsert one cached page (no commit). Stores the listing verbatim —
        the ``cache`` block is added per response, never persisted."""
        source_id, sort_key, genre_key, page = key
        row = self._db.get(SourceBrowseCache, key)
        if row is None:
            row = SourceBrowseCache(
                source_id=source_id, sort=sort_key, genre=genre_key, page=page
            )
            self._db.add(row)
        row.payload = json.dumps(listing)
        row.fetched_at = utcnow()
        return row

    def _write_through_listing(
        self, source_id: str, items: list[dict[str, Any]]
    ) -> None:
        """Seed ``source_series_cache`` from a browse page's items (no commit).

        A browse already carries per-series metadata, so storing it makes the
        series screen render instantly afterwards (title/cover/description
        while chapters load). Only non-None fields are merged so a listing's
        sparser rows never blank out richer data written by a full series
        fetch, and ``_merge_series_row`` keeps ``fetched_at`` untouched for
        existing rows (no chapter list here — see its docstring).
        """
        for item in items:
            series_key = item.get("id")
            title = item.get("title")
            if not series_key or not title:
                continue
            meta = {
                field: item.get(field)
                for field in (
                    "title",
                    "cover_url",
                    "description",
                    "author",
                    "artist",
                    "status",
                    "genres",
                )
                if item.get(field) is not None
            }
            rating = rating_from_genres(item.get("genres"))
            if rating is not None:
                meta["content_rating"] = rating
            self._merge_series_row(
                source_id, fully_unquote(str(series_key)), meta, None
            )

    def _maybe_warm_next(
        self,
        source_id: str,
        sort_key: str,
        genre_key: str,
        page: int,
        payload: dict[str, Any],
    ) -> None:
        """Fetch the *next* page in the background so paging forward is instant.

        Bounded on purpose: never past the page after the one just served (no
        catalogue crawl — some sources hold 10k+ series), never when the next
        page is already fresh, never twice concurrently for the same key, and
        never after a stale serve (the connector is down; do not pile on). The
        warm carries the requesting caller's resolved 18+ gate so a mature
        source the caller can see warms exactly like any other.
        """
        if not get_settings().browse_prefetch_enabled:
            return
        if not payload.get("has_more"):
            return
        next_page = page + 1
        key = (source_id, sort_key, genre_key, next_page)
        try:
            existing = self._db.get(SourceBrowseCache, key)
            if existing is not None and self._browse_row_fresh(existing):
                return
        except Exception:  # noqa: BLE001 - warm is best-effort, never a failure
            return
        gate_fn = getattr(self._browse, "_gate_open", None)
        mature_enabled = bool(gate_fn()) if callable(gate_fn) else False

        with _warm_lock:
            if key in _warm_inflight:
                return
            _warm_inflight.add(key)

        def _work() -> None:
            db: Session | None = None
            try:
                db = _open_warm_session()
                browse = _build_warm_browse(db, mature_enabled)
                SourceCacheService(db, browse).get_browse_page(
                    source_id,
                    page=next_page,
                    sort=sort_key or None,
                    genre=genre_key or None,
                )
            except Exception:  # noqa: BLE001 - warm failures are invisible
                logger.debug(
                    "browse_cache: background warm failed for %s (sort=%r "
                    "genre=%r page=%d)",
                    source_id,
                    sort_key,
                    genre_key,
                    next_page,
                    exc_info=True,
                )
            finally:
                with _warm_lock:
                    _warm_inflight.discard(key)
                if db is not None:
                    db.close()

        try:
            _spawn_warm(_work)
        except Exception:  # noqa: BLE001
            with _warm_lock:
                _warm_inflight.discard(key)

    def _evict_oldest(self, model, cap: int) -> None:
        """Delete the oldest rows (by ``fetched_at``) past ``cap`` (no commit).

        Keeps both cache tables bounded no matter how many pages get browsed;
        the caller commits. ``cap <= 0`` disables the ceiling.
        """
        if cap <= 0:
            return
        # autoflush is off session-wide; flush so the row(s) just added are
        # visible to the COUNT and to the age ordering below.
        self._db.flush()
        count = self._db.execute(select(func.count()).select_from(model)).scalar_one()
        excess = count - cap
        if excess <= 0:
            return
        victims = (
            self._db.execute(
                select(model).order_by(model.fetched_at.asc()).limit(excess)
            )
            .scalars()
            .all()
        )
        for victim in victims:
            self._db.delete(victim)
        logger.info(
            "source_cache: evicted %d oldest %s row(s) (cap %d)",
            len(victims),
            model.__tablename__,
            cap,
        )

    @staticmethod
    def _serialize(row: SourceSeriesCache) -> dict[str, Any]:
        return {
            "source_id": row.source_id,
            "series_key": row.series_key,
            "title": row.title,
            "cover_url": row.cover_url,
            "description": row.description,
            "author": row.author,
            "artist": row.artist,
            "status": row.status,
            "year": row.year,
            "content_rating": row.content_rating,
            "genres": _loads(row.genres) or [],
            # Memoized: this parse dominated every read of a long series.
            "chapters": _memoized_chapters(row),
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }


def get_source_cache_service(
    db: Annotated[Session, Depends(get_db)],
    browse: Annotated[BrowseService, Depends(get_browse_service)],
) -> SourceCacheService:
    return SourceCacheService(db, browse)
