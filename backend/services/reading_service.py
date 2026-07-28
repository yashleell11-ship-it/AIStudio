"""Resolve reading sessions from local library or online sources."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from connectors.ids import fully_unquote
from core.library_authz import series_read_allowed
from core.profile_context import ProfileContext, resolve_profile_context
from database.models import Chapter, SourceChapterLink
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service
from services.library_service import LibraryService


class ReadingService:
    """Picks local or remote chapter content without exposing source details to callers."""

    def __init__(
        self,
        db: Session,
        browse_service: BrowseService,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        self._browse = browse_service
        self._user_id = user_id
        # Carries the caller's identity, and must. This is a real authenticated
        # request path (GET /sources/{s}/series/{id}/chapters/{c}/reader) that
        # used to wear a background caller's costume: an unscoped
        # ``LibraryService(db)`` here means get_chapter/get_series authorize
        # against the (NULL, NULL) bucket, so the unified reader would 404 for
        # EVERY user on every locally-downloaded chapter.
        self._library = LibraryService(db, user_id=user_id, profile_id=profile_id)

    def resolve_source_chapter(
        self,
        source_id: str,
        series_id: str,
        chapter_id: str,
    ) -> dict[str, object]:
        """Read from a local copy when available, otherwise stream from the source."""
        normalized_chapter_id = fully_unquote(chapter_id).strip().strip("/")
        local_chapter_id = self._find_local_chapter(source_id, series_id, normalized_chapter_id)
        # The local copy is a shortcut, not an entitlement. A caller with no
        # claim on the local series falls THROUGH to the source rather than
        # getting a 404: browsing a source has never required library
        # membership, and someone else having downloaded the chapter must not
        # take away a read that worked before this gate existed.
        if local_chapter_id is not None and self._may_read_local(local_chapter_id):
            return self._local_reader_payload(local_chapter_id)

        return self._browse.get_reader_chapter(source_id, series_id, normalized_chapter_id)

    def _may_read_local(self, local_chapter_id: int) -> bool:
        """Whether this caller's account may read the local copy, via its series."""
        series_id = (
            self._db.query(Chapter.series_id)
            .filter(Chapter.id == local_chapter_id)
            .scalar()
        )
        if series_id is None:
            return False
        return series_read_allowed(self._db, self._user_id, series_id)

    def _find_local_chapter(
        self,
        source_id: str,
        series_id: str,
        chapter_id: str,
    ) -> int | None:
        link = (
            self._db.query(SourceChapterLink)
            .filter(
                SourceChapterLink.source == source_id,
                SourceChapterLink.series_id == series_id,
                SourceChapterLink.chapter_id == chapter_id,
            )
            .first()
        )
        if link is None:
            return None
        return link.local_chapter_id

    def _local_reader_payload(self, chapter_id: int) -> dict[str, object]:
        chapter = self._library.get_chapter(chapter_id)
        pages = chapter.get("pages", [])
        series_id = chapter.get("series_id")
        chapters = self._library.get_series(int(series_id)).get("chapters", [])
        chapter_ids = [item["id"] for item in chapters]
        index = chapter_ids.index(chapter_id) if chapter_id in chapter_ids else -1

        return {
            "mode": "local",
            "source_id": None,
            "series_id": str(series_id),
            "id": str(chapter_id),
            "title": chapter.get("title"),
            "number": chapter.get("number"),
            "page_count": chapter.get("page_count"),
            "pages": [
                {
                    "id": str(page["id"]),
                    "chapter_id": str(chapter_id),
                    "number": page["number"],
                    "width": page.get("width"),
                    "height": page.get("height"),
                    "image_url": f"/reader/page/{page['id']}/image",
                }
                for page in pages
            ],
            "previous_chapter_id": (
                str(chapter_ids[index - 1]) if index > 0 else None
            ),
            "next_chapter_id": (
                str(chapter_ids[index + 1]) if 0 <= index < len(chapter_ids) - 1 else None
            ),
            "series_title": None,
        }


def get_reading_service(
    db: Annotated[Session, Depends(get_db)],
    browse_service: Annotated[BrowseService, Depends(get_browse_service)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> ReadingService:
    return ReadingService(
        db, browse_service, user_id=ctx.user_id, profile_id=ctx.profile_id
    )
