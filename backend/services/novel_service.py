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
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Annotated, Any

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
from services.source_cache_service import (
    CACHE_FRESH,
    CACHE_LIVE,
    CACHE_STALE,
    SourceCacheService,
    get_source_cache_service,
)

logger = logging.getLogger("manhwamaniacs.novels")


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

    def _adjacent(
        self, source_id: str, series_key: str, chapter_key: str
    ) -> tuple[str | None, str | None, float | None]:
        """(prev_key, next_key, chapter_number) from the cached chapter list.

        Best-effort: the chapter list has its own cache + stale fallback in
        ``SourceCacheService``; if even that fails, (None, None, None) — the
        caller then falls back to the snapshot on the cache row.
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
            return None, None, None
        keys = [str(c.get("key") or "") for c in chapters]
        try:
            idx = keys.index(chapter_key)
        except ValueError:
            idx = next(
                (
                    i
                    for i, key in enumerate(keys)
                    if key.strip("/") == chapter_key.strip("/")
                ),
                -1,
            )
        if idx < 0:
            return None, None, None
        number = chapters[idx].get("number")
        return (
            keys[idx - 1] if idx > 0 else None,
            keys[idx + 1] if idx < len(keys) - 1 else None,
            float(number) if number is not None else None,
        )

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
        try:
            self._evict_lru(get_settings().novel_cache_max_rows)
            self._db.commit()
        except Exception:  # noqa: BLE001 - a cache write must never break a read
            logger.exception("novels: cache write failed")
            self._db.rollback()
        return row

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


def get_novel_service(
    db: Annotated[Session, Depends(get_db)],
    browse: Annotated[BrowseService, Depends(get_browse_service)],
    source_cache: Annotated[SourceCacheService, Depends(get_source_cache_service)],
) -> NovelService:
    return NovelService(db, browse, source_cache)
