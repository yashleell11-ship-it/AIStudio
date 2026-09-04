"""Chapter text for novel sources, served through ``novel_chapter_cache``.

The novel analog of the reader manifest (spec 2026-09-04-novels-design §3):
``GET /novels/chapter`` returns ``{title, chapter_number, paragraphs, prev,
next, word_count}`` where ``paragraphs`` is sanitized PLAIN TEXT — the
connector sanitizes before anything reaches this service, so the cache rows,
the wire payload, and the future TTS input are one and the same bytes.

Cache semantics mirror ``source_cache_service`` (same read-through shape,
same stale-on-failure guarantee, same bounded-table discipline):

  * fresh row (within ``novel_cache_ttl_minutes``)  -> serve it
  * missing / expired                               -> refetch, upsert, serve
  * connector failure with any row present          -> serve stale (flagged)
  * connector failure with nothing cached           -> raise

The one deliberate divergence: eviction is least-recently-USED
(``last_used_at``, bumped on every serve) rather than oldest-fetched,
because chapter text is immutable — an old row a reader keeps returning to
is exactly the row worth keeping.

``prev``/``next`` are computed per serve from the (itself cached) chapter
list, exactly like ``ReaderService.manifest``; the values snapshotted on the
cache row only answer when that list is unreachable.

``get_chapters_bulk`` (spec 2026-09-05-reading-flow-design R5) serves a bounded
WINDOW of chapters through exactly this machinery — same cache, same LRU, same
English guard and sanitizer (both live inside ``connector.chapter_text``, which
the window still calls one chapter at a time). What it does NOT do per chapter
is talk to the database from a worker thread: the cache reads, the writes and
the eviction sweep all stay on the request thread, and only the upstream fetch
of the chapters that actually missed fans out.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Annotated, Any, Sequence

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from connectors.models import NovelChapterText
from connectors.registry import create_connector
from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import NovelChapterCache
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service
from services.bulk_fetch import map_bounded
from services.source_cache_service import (
    CACHE_FRESH,
    CACHE_LIVE,
    CACHE_STALE,
    SourceCacheService,
    get_source_cache_service,
)

logger = logging.getLogger("manhwamaniacs.novels")


class _Adjacency:
    """prev/next/number for every chapter of one series, from the cached list.

    Chapter keys are opaque connector strings and connectors are not consistent
    about leading/trailing separators, so lookups fall back to a ``strip("/")``
    comparison — the same tolerance ``ReaderService._locate`` applies, and the
    reason a link built with one convention still navigates against a list
    stored with the other.
    """

    __slots__ = ("_by_key", "_by_stripped")

    def __init__(self, chapters: list[dict[str, Any]], keys: list[str]) -> None:
        self._by_key: dict[str, tuple[str | None, str | None, float | None]] = {}
        self._by_stripped: dict[str, str] = {}
        last = len(keys) - 1
        for idx, key in enumerate(keys):
            number = chapters[idx].get("number")
            self._by_key[key] = (
                keys[idx - 1] if idx > 0 else None,
                keys[idx + 1] if idx < last else None,
                float(number) if number is not None else None,
            )
            self._by_stripped.setdefault(key.strip("/"), key)

    def of(self, chapter_key: str) -> tuple[str | None, str | None, float | None]:
        found = self._by_key.get(chapter_key)
        if found is not None:
            return found
        alias = self._by_stripped.get(chapter_key.strip("/"))
        if alias is not None:
            return self._by_key[alias]
        return None, None, None



class NovelService:
    def __init__(
        self,
        db: Session,
        browse: BrowseService,
        source_cache: SourceCacheService,
    ) -> None:
        self._db = db
        self._browse = browse
        self._source_cache = source_cache

    # --- public API ------------------------------------------------------

    def get_chapter(
        self, source_id: str, series_key: str, chapter_key: str
    ) -> dict[str, Any]:
        """The chapter-text payload, cache-first with stale fallback."""
        series_key = fully_unquote(series_key)
        chapter_key = fully_unquote(chapter_key)
        connector = self._require_novel_connector(source_id)

        row = self._db.get(
            NovelChapterCache, (source_id, series_key, chapter_key)
        )
        if row is not None and self._is_fresh(row):
            return self._respond(row, CACHE_FRESH, source_id, series_key)

        try:
            text = connector.chapter_text(series_key, chapter_key)
        except Exception as exc:  # noqa: BLE001 - cache must degrade
            if row is not None:
                logger.warning(
                    "novels: connector failed for %s/%s/%s, serving stale (%s)",
                    source_id,
                    series_key,
                    chapter_key,
                    exc,
                )
                return self._respond(row, CACHE_STALE, source_id, series_key)
            raise AppError(
                "The source did not return this chapter.",
                code="novel_chapter_unavailable",
                status_code=502,
                details={"source_id": source_id},
            ) from exc

        if text is None:
            # The connector reached the site and the chapter is gone (or no
            # longer parses, or failed the English guard). A cached copy is
            # still better than an error — text is immutable, serve it stale.
            if row is not None:
                logger.warning(
                    "novels: %s/%s/%s no longer resolves upstream, serving stale",
                    source_id,
                    series_key,
                    chapter_key,
                )
                return self._respond(row, CACHE_STALE, source_id, series_key)
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
            )

        prev_key, next_key, list_number = self._adjacent(
            source_id, series_key, chapter_key
        )
        number = text.chapter_number if text.chapter_number is not None else list_number
        row = self._upsert(
            source_id,
            series_key,
            chapter_key,
            text,
            number=number,
            prev_key=prev_key,
            next_key=next_key,
        )
        return self._respond(
            row, CACHE_LIVE, source_id, series_key, prev=prev_key, next=next_key
        )

    def get_chapters_bulk(
        self,
        source_id: str,
        series_key: str,
        chapter_keys: Sequence[str],
    ) -> dict[str, Any]:
        """Chapter text for a bounded WINDOW of one novel (spec 2026-09-05 R5).

        Downloading a whole novel one ``GET /novels/chapter`` at a time is one
        round trip per chapter — a 300-chapter web novel is 300 of them, each
        paying the request overhead again for a payload measured in kilobytes.
        This is the same work in one request.

        Everything that guards a single chapter still guards each chapter here,
        and by calling the same code rather than by resembling it:

        * the **novels flag**, the per-caller **18+ gate** and the novel-kind
          check, all through ``_require_novel_connector`` — once, up front,
          before any cache row is read (cache rows are global, the gate is not);
        * the **``novel_chapter_cache``**, including its stale-on-failure
          fallback and its least-recently-USED eviction — the window reads the
          same rows, writes the same rows, and bumps the same ``last_used_at``;
        * the **English guard and the sanitizer**, which live inside
          ``connector.chapter_text`` — the window still calls it once per
          chapter and never reaches past it.

        Degrades per chapter: a chapter that fails upstream with nothing cached
        is one ``error`` item, not a failed window.
        """
        series_key = fully_unquote(series_key)
        keys = [fully_unquote(key) for key in chapter_keys]

        cap = bulk_novel_cap()
        if len(keys) > cap:
            raise AppError(
                "Too many chapters in one window.",
                code="batch_too_large",
                status_code=413,
                details={"max_chapters": cap, "received": len(keys)},
            )

        connector = self._require_novel_connector(source_id)
        adjacency = self._adjacency_index(source_id, series_key)

        # Pass 1 — the cache, on the request thread. A Session is not
        # thread-safe and this one belongs to the request.
        distinct = list(dict.fromkeys(keys))
        rows: dict[str, NovelChapterCache | None] = {
            key: self._db.get(NovelChapterCache, (source_id, series_key, key))
            for key in distinct
        }
        misses = [
            key
            for key in distinct
            if rows[key] is None or not self._is_fresh(rows[key])
        ]

        # Pass 2 — only the misses go upstream, bounded and in parallel.
        fetched = dict(
            zip(
                misses,
                map_bounded(
                    misses, lambda key: connector.chapter_text(series_key, key)
                ),
            )
        )

        # Pass 3 — writes and payloads, back on the request thread. One
        # eviction sweep and one commit for the whole window.
        payloads: dict[str, dict[str, Any]] = {}
        errors: dict[str, dict[str, Any]] = {}
        wrote = False
        for key in distinct:
            row = rows[key]
            if key not in fetched:  # fresh cache hit
                prev, next_key, _ = adjacency.of(key)
                payloads[key] = self._respond(
                    row,
                    CACHE_FRESH,
                    source_id,
                    series_key,
                    prev=prev if prev is not None else row.prev_key,
                    next=next_key if next_key is not None else row.next_key,
                    commit=False,
                )
                continue

            outcome = fetched[key]
            if isinstance(outcome, BaseException):
                # Connector failed. A cached copy — even an expired one — beats
                # an error: published chapter text is immutable.
                if row is not None:
                    logger.warning(
                        "novels: connector failed for %s/%s/%s, serving stale (%s)",
                        source_id,
                        series_key,
                        key,
                        outcome,
                    )
                    prev, next_key, _ = adjacency.of(key)
                    payloads[key] = self._respond(
                        row,
                        CACHE_STALE,
                        source_id,
                        series_key,
                        prev=prev if prev is not None else row.prev_key,
                        next=next_key if next_key is not None else row.next_key,
                        commit=False,
                    )
                else:
                    # Same collapse the single path applies: a connector
                    # failure with nothing cached is one 502 code, whatever the
                    # underlying transport said, so a client's error handling
                    # is identical for a window and for a single chapter.
                    errors[key] = {
                        "code": "novel_chapter_unavailable",
                        "status": 502,
                        "message": "The source did not return this chapter.",
                    }
                continue

            if outcome is None:
                # Reached the site; the chapter is gone, no longer parses, or
                # failed the English guard. Same rule as the single path.
                if row is not None:
                    logger.warning(
                        "novels: %s/%s/%s no longer resolves upstream, serving stale",
                        source_id,
                        series_key,
                        key,
                    )
                    prev, next_key, _ = adjacency.of(key)
                    payloads[key] = self._respond(
                        row,
                        CACHE_STALE,
                        source_id,
                        series_key,
                        prev=prev if prev is not None else row.prev_key,
                        next=next_key if next_key is not None else row.next_key,
                        commit=False,
                    )
                else:
                    errors[key] = {
                        "code": "chapter_not_found",
                        "status": 404,
                        "message": "Chapter not found.",
                    }
                continue

            prev, next_key, list_number = adjacency.of(key)
            number = (
                outcome.chapter_number
                if outcome.chapter_number is not None
                else list_number
            )
            row = self._upsert(
                source_id,
                series_key,
                key,
                outcome,
                number=number,
                prev_key=prev,
                next_key=next_key,
                commit=False,
            )
            wrote = True
            payloads[key] = self._respond(
                row,
                CACHE_LIVE,
                source_id,
                series_key,
                prev=prev,
                next=next_key,
                commit=False,
            )

        if wrote:
            self._flush_cache_writes()
        else:
            # No new rows, but every serve above bumped ``last_used_at`` — the
            # LRU signal is worthless if it is never persisted.
            try:
                self._db.commit()
            except Exception:  # noqa: BLE001 - bookkeeping must never break a read
                self._db.rollback()

        items: list[dict[str, Any]] = []
        for key in keys:
            if key in payloads:
                items.append(
                    {
                        "chapter_key": key,
                        "status": "ok",
                        "chapter": payloads[key],
                        "error": None,
                    }
                )
            else:
                items.append(
                    {
                        "chapter_key": key,
                        "status": "error",
                        "chapter": None,
                        "error": errors[key],
                    }
                )

        ok_count = sum(1 for item in items if item["status"] == "ok")
        return {
            "source_id": source_id,
            "series_key": series_key,
            "max_chapters": cap,
            "requested": len(items),
            "ok_count": ok_count,
            "failed_count": len(items) - ok_count,
            "items": items,
        }

    # --- internals -------------------------------------------------------

    def _require_novel_connector(self, source_id: str):
        """404 for anything that is not a visible novel source.

        ``ensure_visible`` applies the whole standard gate (unknown source,
        per-caller 18+, browsable) — and with MM_NOVELS_ENABLED off the
        registry refuses novel types entirely, so this 404s exactly like the
        source never existed. A MANGA source reaching this endpoint is also a
        404 (not a 400): which kinds exist here is not disclosed.
        """
        self._browse.ensure_visible(source_id)
        connector = create_connector(source_id)
        if connector.content_kind != "novel":
            raise AppError(
                "Source not found.",
                code="source_not_found",
                status_code=404,
                details={"source_id": source_id},
            )
        return connector

    def _is_fresh(self, row: NovelChapterCache) -> bool:
        ttl = timedelta(minutes=get_settings().novel_cache_ttl_minutes)
        return (utcnow() - row.fetched_at) < ttl

    def _adjacency_index(self, source_id: str, series_key: str) -> _Adjacency:
        """Navigation for a whole series, resolved once.

        Best-effort: the chapter list has its own cache + stale fallback in
        ``SourceCacheService``; if even that fails, an EMPTY index — every
        lookup then answers (None, None, None) and the caller falls back to the
        snapshot on the cache row.

        Built per series rather than per chapter because a bulk window would
        otherwise re-read and re-parse the same cached list once for every
        chapter in it.
        """
        try:
            chapters = self._source_cache.get_chapter_list(source_id, series_key)
        except Exception:  # noqa: BLE001 - navigation must never sink the text
            logger.warning(
                "novels: chapter list unavailable for %s/%s",
                source_id,
                series_key,
                exc_info=True,
            )
            return _Adjacency([], [])
        return _Adjacency(chapters, [str(c.get("key") or "") for c in chapters])

    def _adjacent(
        self, source_id: str, series_key: str, chapter_key: str
    ) -> tuple[str | None, str | None, float | None]:
        """(prev_key, next_key, chapter_number) from the cached chapter list."""
        return self._adjacency_index(source_id, series_key).of(chapter_key)

    def _upsert(
        self,
        source_id: str,
        series_key: str,
        chapter_key: str,
        text: NovelChapterText,
        *,
        number: float | None,
        prev_key: str | None,
        next_key: str | None,
        commit: bool = True,
    ) -> NovelChapterCache:
        row = self._db.get(
            NovelChapterCache, (source_id, series_key, chapter_key)
        )
        if row is None:
            row = NovelChapterCache(
                source_id=source_id,
                series_key=series_key,
                chapter_key=chapter_key,
            )
            self._db.add(row)
        row.title = text.title
        row.chapter_number = number
        row.paragraphs = json.dumps(list(text.paragraphs))
        row.word_count = text.word_count
        row.prev_key = prev_key
        row.next_key = next_key
        row.fetched_at = utcnow()
        row.last_used_at = utcnow()
        if commit:
            self._flush_cache_writes()
        return row

    def _flush_cache_writes(self) -> None:
        """Sweep the LRU ceiling and commit the pending cache rows.

        Split out of ``_upsert`` so a bulk window pays for ONE eviction sweep
        and ONE transaction instead of one per chapter — twenty write-lock and
        fsync cycles on the single-writer SQLite is the shape of the batch bug
        that was already fixed once on ``POST /reader/progress/batch``.
        """
        try:
            self._evict_lru(get_settings().novel_cache_max_rows)
            self._db.commit()
        except Exception:  # noqa: BLE001 - a cache write must never break a read
            logger.exception("novels: cache write failed")
            self._db.rollback()

    def _evict_lru(self, cap: int) -> None:
        """Delete the least-recently-used rows past ``cap`` (no commit)."""
        if cap <= 0:
            return
        self._db.flush()
        count = self._db.execute(
            select(func.count()).select_from(NovelChapterCache)
        ).scalar_one()
        excess = count - cap
        if excess <= 0:
            return
        victims = (
            self._db.execute(
                select(NovelChapterCache)
                .order_by(NovelChapterCache.last_used_at.asc())
                .limit(excess)
            )
            .scalars()
            .all()
        )
        for victim in victims:
            self._db.delete(victim)
        logger.info(
            "novels: evicted %d least-recently-used chapter row(s) (cap %d)",
            len(victims),
            cap,
        )

    def _respond(
        self,
        row: NovelChapterCache,
        status: str,
        source_id: str,
        series_key: str,
        *,
        prev: str | None = "__from_row__",
        next: str | None = "__from_row__",  # noqa: A002 - mirrors the wire name
        commit: bool = True,
    ) -> dict[str, Any]:
        """Serialize a cache row; bump ``last_used_at`` (the LRU signal).

        For cache-hit serves, prev/next are recomputed from the (cached)
        chapter list so a chapter that gained a successor since the fetch
        navigates forward; the row's snapshot answers when the list doesn't.
        """
        if prev == "__from_row__" or next == "__from_row__":
            live_prev, live_next, _ = self._adjacent(
                source_id, series_key, row.chapter_key
            )
            prev = live_prev if live_prev is not None else row.prev_key
            next = live_next if live_next is not None else row.next_key

        row.last_used_at = utcnow()
        if commit:
            try:
                self._db.commit()
            except Exception:  # noqa: BLE001 - LRU bookkeeping must never break a read
                self._db.rollback()

        try:
            paragraphs = json.loads(row.paragraphs)
        except (TypeError, ValueError):
            paragraphs = []
        return {
            "source_id": row.source_id,
            "series_key": row.series_key,
            "chapter_key": row.chapter_key,
            "title": row.title,
            "chapter_number": row.chapter_number,
            "paragraphs": paragraphs,
            "prev": prev,
            "next": next,
            "word_count": row.word_count,
            "cache": {
                "status": status,
                "stale": status == CACHE_STALE,
                "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
            },
        }


def bulk_novel_cap() -> int:
    """Chapters per bulk novel window. ``MM_NOVEL_BULK_MAX_CHAPTERS``.

    Read at call time and echoed in every response as ``max_chapters``, so a
    whole-novel download paces itself by whatever the server currently allows
    rather than a number baked into a client release.
    """
    try:
        return max(1, int(getattr(get_settings(), "novel_bulk_max_chapters", 20)))
    except (TypeError, ValueError):
        return 20


def get_novel_service(
    db: Annotated[Session, Depends(get_db)],
    browse: Annotated[BrowseService, Depends(get_browse_service)],
    source_cache: Annotated[SourceCacheService, Depends(get_source_cache_service)],
) -> NovelService:
    return NovelService(db, browse, source_cache)
