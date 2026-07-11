from __future__ import annotations

import mimetypes
import zipfile
from functools import lru_cache
from pathlib import Path

from core.errors import AppError
from database.models import Page
from services.library_service import LibraryService
from utils.path_utils import validate_path_under_roots


class ImageService:
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
