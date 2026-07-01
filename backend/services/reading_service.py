"""Resolve reading sessions from local library or online sources."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends
from sqlalchemy.orm import Session

from core.errors import AppError
from database.models import SourceChapterLink
from database.session import get_db
from services.browse_service import BrowseService, get_browse_service
from services.library_service import LibraryService


class ReadingService:
    """Picks local or remote chapter content without exposing source details to callers."""

    def __init__(self, db: Session, browse_service: BrowseService) -> None:
        self._db = db
        self._browse = browse_service
        self._library = LibraryService(db)

    def resolve_source_chapter(
        self,
        source_id: str,
        series_id: str,
        chapter_id: str,
    ) -> dict[str, object]:
        """Read from a local copy when available, otherwise stream from the source."""
        normalized_chapter_id = unquote(chapter_id).strip().strip("/")
        local_chapter_id = self._find_local_chapter(source_id, series_id, normalized_chapter_id)
        if local_chapter_id is not None:
            return self._local_reader_payload(local_chapter_id)

        return self._browse.get_reader_chapter(source_id, series_id, normalized_chapter_id)

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
) -> ReadingService:
    return ReadingService(db, browse_service)
