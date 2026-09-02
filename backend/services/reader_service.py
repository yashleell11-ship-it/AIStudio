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

from connectors.ids import fully_unquote
from core.errors import AppError
from core.profile_context import ProfileContext, resolve_profile_context
from services.browse_service import BrowseService, get_browse_service


class ReaderService:
    def __init__(
        self,
        browse: BrowseService,
        *,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._browse = browse
        self._user_id = user_id
        self._profile_id = profile_id

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

        chapters = self._browse.get_chapters(source_id, series_key)
        if not chapters:
            raise AppError(
                "Series not found.", code="series_not_found", status_code=404
            )

        keys = [str(c["id"]) for c in chapters]
        try:
            idx = keys.index(chapter_key)
        except ValueError:
            idx = next(
                (i for i, c in enumerate(chapters) if str(c["id"]).strip("/") == chapter_key.strip("/")),
                -1,
            )
        if idx < 0:
            raise AppError(
                "Chapter not found.", code="chapter_not_found", status_code=404
            )

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
    browse: Annotated[BrowseService, Depends(get_browse_service)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> ReaderService:
    return ReaderService(browse, user_id=ctx.user_id, profile_id=ctx.profile_id)
