from __future__ import annotations

import logging
import mimetypes
import time
import zipfile
from functools import lru_cache
from pathlib import Path
from threading import Lock

from core.errors import AppError
from database.models import Page
from services.library_service import LibraryService
from utils.path_utils import validate_path_under_roots

logger = logging.getLogger(__name__)

# Source covers change rarely; cache the fetched bytes per series so rendering a
# dashboard of ~10 covers doesn't hit the upstream source on every request.
_SOURCE_COVER_TTL_SECONDS = 6 * 60 * 60  # 6 hours
_SOURCE_COVER_CACHE_MAX = 512


class ImageService:
    def __init__(self) -> None:
        # series_id -> (data, media_type, monotonic_timestamp)
        self._source_cover_cache: dict[int, tuple[bytes, str, float]] = {}
        self._source_cover_lock = Lock()

    def _resolve_source_cover(
        self, library_service: LibraryService, series_id: int
    ) -> tuple[bytes, str] | None:
        """Return ``(data, media_type)`` for a source-linked series' real cover,
        or ``None`` if the series isn't source-linked or the source fetch fails.

        A cover request must never 500, so every failure here degrades to the
        local ``cover_path`` behavior in :meth:`get_cover_path`.
        """
        now = time.monotonic()
        with self._source_cover_lock:
            cached = self._source_cover_cache.get(series_id)
            if cached is not None:
                data, media_type, ts = cached
                if now - ts < _SOURCE_COVER_TTL_SECONDS:
                    return data, media_type
                self._source_cover_cache.pop(series_id, None)

        try:
            mapping = library_service.resolve_source_link(series_id)
        except Exception:  # noqa: BLE001 - never let cover resolution raise
            logger.warning("Source link lookup failed for series %s", series_id, exc_info=True)
            return None
        if not mapping:
            return None

        source_id, source_series_id = mapping
        try:
            # Local import keeps browse_service off the module import graph and
            # avoids constructing connectors until a source cover is needed.
            # Constructed without a gate: this only ever fetches the cover of a
            # series ALREADY in someone's library, and the gate has already
            # decided whether that series is visible at all. Re-gating here
            # would only break covers for a series the caller can see.
            from services.browse_service import BrowseService

            media_type, data = BrowseService().resolve_series_cover(
                source_id, source_series_id
            )
        except Exception:  # noqa: BLE001 - upstream/connector errors fall back
            logger.warning(
                "Source cover fetch failed for series %s (%s/%s)",
                series_id,
                source_id,
                source_series_id,
                exc_info=True,
            )
            return None
        if not data:
            return None

        with self._source_cover_lock:
            if len(self._source_cover_cache) >= _SOURCE_COVER_CACHE_MAX:
                self._source_cover_cache.clear()
            self._source_cover_cache[series_id] = (data, media_type, now)
        return data, media_type

    def resolve_page_file(
        self,
        page: Page,
        roots: list[Path],
        archive_member: str | None = None,
    ) -> tuple[Path | None, str | None, bytes | None]:
        file_path = Path(page.file_path)
        if file_path.suffix.lower() in {".cbz", ".zip"}:
            validate_path_under_roots(file_path, roots)
            member = archive_member
            if not member:
                chapter = page.chapter
                members = sorted(
                    [
                        name
                        for name in zipfile.ZipFile(file_path).namelist()
                        if not name.endswith("/")
                    ]
                )
                if page.number <= len(members):
                    member = members[page.number - 1]
            if not member:
                raise AppError(
                    "Archive page not found.",
                    code="page_not_found",
                    status_code=404,
                )
            with zipfile.ZipFile(file_path, "r") as zf:
                data = zf.read(member)
            media_type = mimetypes.guess_type(member)[0] or "image/jpeg"
            return None, media_type, data

        validate_path_under_roots(file_path, roots)
        if not file_path.is_file():
            # Do not surface the absolute server path to the client.
            raise AppError(
                "Image file not found on disk.",
                code="file_not_found",
                status_code=404,
            )
        media_type = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
        return file_path, media_type, None

    def serve_page(
        self,
        library_service: LibraryService,
        page_id: int,
        archive_member: str | None = None,
    ) -> tuple[Path | bytes, str]:
        page = library_service.get_page(page_id)
        roots = library_service.get_library_roots()
        if not roots:
            roots = [Path(page.file_path).parent]

        file_path, media_type, data = self.resolve_page_file(
            page, roots, archive_member=archive_member
        )
        if data is not None:
            return data, media_type
        assert file_path is not None
        return file_path, media_type

    def get_cover_path(self, library_service: LibraryService, series_id: int) -> tuple[Path | bytes, str]:
        # For source-linked (imported/downloaded) series, prefer the real source
        # cover. Local imports were baking a chapter's first page (often a
        # credits/title page) into cover_path; serving the source cover fixes
        # every existing source-linked series with no data migration. Any
        # failure falls through to the local cover_path behavior below.
        source_cover = self._resolve_source_cover(library_service, series_id)
        if source_cover is not None:
            data, media_type = source_cover
            return data, media_type

        series_data = library_service.get_series(series_id)
        cover_path = series_data.get("cover_path")
        if not cover_path:
            raise AppError(
                "Cover not available.",
                code="cover_not_found",
                status_code=404,
                details={"series_id": series_id},
            )
        cover = Path(str(cover_path))
        roots = library_service.get_library_roots()
        if cover.suffix.lower() in {".cbz", ".zip"}:
            with zipfile.ZipFile(cover, "r") as zf:
                members = [name for name in zf.namelist() if not name.endswith("/")]
                if not members:
                    raise AppError("Cover archive is empty.", code="cover_not_found", status_code=404)
                data = zf.read(members[0])
            return data, mimetypes.guess_type(members[0])[0] or "image/jpeg"

        if roots:
            validate_path_under_roots(cover, roots)
        media_type = mimetypes.guess_type(cover.name)[0] or "image/jpeg"
        return cover, media_type


@lru_cache
def get_image_service() -> ImageService:
    return ImageService()
