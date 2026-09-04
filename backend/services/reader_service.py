"""Source-native reader service (spec §4.1, §5.2).

There are no local chapters any more — every read goes through a connector with
the caller's own request context. This service does two things:

* ``manifest()`` — the client's *download plan* for a chapter: the ordered page
  list (number + proxy URL), chapter number, and prev/next chapter keys. No
  bytes.
* ``resolve_source_chapter()`` — the online reader payload (the old online path,
  minus the deleted "local copy shortcut" branch).

Reading position, bookmarks and history live in ``progress_service``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.errors import AppError
from core.profile_context import ProfileContext, resolve_profile_context
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service
from services.source_cache_service import SourceCacheService


def _chapter_key(entry: dict[str, Any]) -> str:
    """The chapter's key, whichever shape the entry arrived in.

    A connector serializes chapters with ``id``; ``source_series_cache`` stores
    them with ``key`` (see ``SourceCacheService._merge_series_row``). Both are
    the same value, and this service now reads from either source.
    """
    return str(entry.get("id") or entry.get("key") or "")


def _locate(chapters: list[dict[str, Any]], chapter_key: str) -> int:
    """Index of ``chapter_key`` in ``chapters``, or -1.

    Exact match first, then ignoring surrounding slashes — connectors are not
    consistent about leading/trailing separators in chapter ids.
    """
    keys = [_chapter_key(c) for c in chapters]
    try:
        return keys.index(chapter_key)
    except ValueError:
        target = chapter_key.strip("/")
        return next(
            (i for i, k in enumerate(keys) if k.strip("/") == target), -1
        )


class ReaderService:
    def __init__(
        self,
        browse: BrowseService,
        *,
        db: Session | None = None,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._browse = browse
        # Optional so a caller with no session (tests, scripts) still gets a
        # working reader — it simply goes to the connector every time, which is
        # what this service did unconditionally before.
        self._cache = SourceCacheService(db, browse) if db is not None else None
        self._user_id = user_id
        self._profile_id = profile_id

    def _chapters(
        self, source_id: str, series_key: str, *, force: bool = False
    ) -> list[dict[str, Any]]:
        """The series' chapter list, from ``source_series_cache`` when it can be.

        This is the single most expensive thing the reader did. ``manifest``
        needs the chapter list only to locate the chapter and name its
        neighbours, but it asked the *connector* for it — and
        ``BrowseService.get_chapters`` fetches the series page upstream first.
        Measured against the owner's own asurascans follows on the VPS, that
        cost 272 ms and 355 ms per chapter open against ~1 ms from the cache.
        The connector keeps its own 180-second in-process cache, so consecutive
        chapters of one series were cheap, but the first chapter of a session,
        anything after a container restart, and any pause longer than three
        minutes all paid full price.

        ``force`` bypasses the cached row; see ``manifest`` for the one case
        that needs it.
        """
        if self._cache is None:
            return self._browse.get_chapters(source_id, series_key)
        return self._cache.get_chapter_list(source_id, series_key, force=force)

    def resolve_source_chapter(
        self,
        source_id: str,
        series_key: str,
        chapter_key: str,
    ) -> dict[str, Any]:
        """Online reader payload straight from the connector."""
        return self._browse.get_reader_chapter(
            source_id,
            fully_unquote(series_key),
            fully_unquote(chapter_key),
        )

    def manifest(
        self,
        source_id: str,
        series_key: str,
        chapter_key: str,
    ) -> dict[str, Any]:
        """The download plan for one chapter (spec §4.1).

        ``{ page_count, chapter_number, pages: [{number, url}], prev, next }``.
        ``url`` points at the existing image proxy. ``sha256``/``size`` are
        omitted for v1 (open question O-1) — the client content-addresses by
        hashing what it downloads.
        """
        series_key = fully_unquote(series_key)
        chapter_key = fully_unquote(chapter_key)

        chapters = self._chapters(source_id, series_key)
        idx = _locate(chapters, chapter_key)
        if idx < 0 and chapters and self._cache is not None:
            # The cached list is up to ``source_cache_ttl_minutes`` old, so a
            # chapter published since it was written is legitimately absent.
            # That is the one case worth a live fetch: without this retry,
            # serving the reader from cache would 404 exactly the newest
            # chapter — the one the owner is most likely to be opening.
            chapters = self._chapters(source_id, series_key, force=True)
            idx = _locate(chapters, chapter_key)
        if not chapters:
            raise AppError(
                "Series not found.", code="series_not_found", status_code=404
            )
        if idx < 0:
            raise AppError(
                "Chapter not found.", code="chapter_not_found", status_code=404
            )

        keys = [_chapter_key(c) for c in chapters]
        chapter = chapters[idx]
        pages = self._browse.get_chapter_pages(source_id, chapter_key)

        return {
            "source_id": source_id,
            "series_key": series_key,
            "chapter_key": chapter_key,
            "chapter_number": chapter.get("number"),
            "page_count": len(pages),
            "pages": [
                {"number": p["number"], "url": p["image_url"]} for p in pages
            ],
            "prev": keys[idx - 1] if idx > 0 else None,
            "next": keys[idx + 1] if idx < len(keys) - 1 else None,
        }


def get_reader_service(
    db: Annotated[Session, Depends(get_db)],
    browse: Annotated[BrowseService, Depends(get_browse_service)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> ReaderService:
    return ReaderService(
        browse, db=db, user_id=ctx.user_id, profile_id=ctx.profile_id
    )
