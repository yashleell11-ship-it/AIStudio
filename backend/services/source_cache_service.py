"""Read-through TTL cache over connector metadata (spec §3.10, §5.2).

``source_series_cache`` lets the library grid, continue-reading strip, and
notifications render titles/covers/chapter counts without hitting a connector
on every request. It is *purely* a cache: any row may be deleted at any time
and is repopulated on the next read.

Semantics:
  * fresh row (``fetched_at`` within ``settings.source_cache_ttl_minutes``)  → serve it
  * missing / stale                                                         → refetch, upsert, serve
  * connector failure with a stale row present                              → serve stale
  * connector failure with nothing cached                                   → raise
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import SourceSeriesCache
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service

logger = logging.getLogger("manhwamaniacs.source_cache")


def _loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


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
        if row is not None and not force and self._is_fresh(row):
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
        row = self._db.get(SourceSeriesCache, (source_id, series_key))
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
        row.fetched_at = utcnow()
        self._db.commit()
        self._db.refresh(row)
        return row

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
            "chapters": _loads(row.chapters) or [],
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        }


def get_source_cache_service(
    db: Annotated[Session, Depends(get_db)],
    browse: Annotated[BrowseService, Depends(get_browse_service)],
) -> SourceCacheService:
    return SourceCacheService(db, browse)
