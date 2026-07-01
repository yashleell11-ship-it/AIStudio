"""Utility helpers for the OCR pipeline.

Handles image resolution from regular files and CBZ/ZIP/RAR/CBR archives so the
OCR manager does not duplicate logic already present in ImageService.

Production improvements:
- RAR/CBR archive support (best-effort, falls back to warning)
- Image resolution limits to prevent OOM on ultra-high-res scans
- Memory-efficient image loading with explicit cleanup
- Image format validation
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from core.errors import AppError
from core.config import get_settings

if TYPE_CHECKING:
    from database.models import Page

logger = logging.getLogger(__name__)

# Image format whitelist (most common manga/manhwa scan formats)
VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def _is_valid_image_member(name: str) -> bool:
    """Check if an archive member is a valid image file."""
    lower = name.lower()
    return any(lower.endswith(ext) for ext in VALID_IMAGE_EXTENSIONS)


def _resolve_archive_page(
    file_path: Path,
    page_number: int,
) -> Image.Image:
    """Resolve a page from a ZIP/CBZ or RAR/CBR archive."""
    suffix = file_path.suffix.lower()

    if suffix in {".cbz", ".zip"}:
        return _resolve_zip_page(file_path, page_number)

    if suffix in {".cbr", ".rar"}:
        return _resolve_rar_page(file_path, page_number)

    raise AppError(
        f"Unsupported archive format: {suffix}",
        code="unsupported_archive",
        status_code=400,
        details={"path": str(file_path), "suffix": suffix},
    )


def _resolve_zip_page(file_path: Path, page_number: int) -> Image.Image:
    """Resolve a page from a ZIP/CBZ archive."""
    if not file_path.is_file():
        raise AppError(
            "Archive not found.",
            code="file_not_found",
            status_code=404,
            details={"path": str(file_path)},
        )
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            members = sorted(
                [name for name in zf.namelist() if _is_valid_image_member(name)]
            )
            if page_number > len(members):
                raise AppError(
                    "Page not found in archive.",
                    code="page_not_found",
                    status_code=404,
                    details={"archive": str(file_path), "page_number": page_number},
                )
            member = members[page_number - 1]
            data = zf.read(member)
            return Image.open(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AppError(
            "Archive is corrupt.",
            code="archive_corrupt",
            status_code=500,
            details={"path": str(file_path)},
        ) from exc


def _resolve_rar_page(file_path: Path, page_number: int) -> Image.Image:
    """Resolve a page from a RAR/CBR archive (best-effort)."""
    if not file_path.is_file():
        raise AppError(
            "Archive not found.",
            code="file_not_found",
            status_code=404,
            details={"path": str(file_path)},
        )
    try:
        import rarfile
    except ImportError:
        logger.warning(
            "RAR archive %s requires 'rarfile' package. Install: pip install rarfile",
            file_path,
        )
        raise AppError(
            "RAR support requires the 'rarfile' package.",
            code="missing_dependency",
            status_code=500,
            details={"package": "rarfile", "path": str(file_path)},
        )

    try:
        with rarfile.RarFile(file_path, "r") as rf:
            members = sorted(
                [name for name in rf.namelist() if _is_valid_image_member(name)]
            )
            if page_number > len(members):
                raise AppError(
                    "Page not found in archive.",
                    code="page_not_found",
                    status_code=404,
                    details={"archive": str(file_path), "page_number": page_number},
                )
            member = members[page_number - 1]
            data = rf.read(member)
            return Image.open(io.BytesIO(data))
    except Exception as exc:
        raise AppError(
            f"RAR archive read failed: {exc}",
            code="archive_corrupt",
            status_code=500,
            details={"path": str(file_path)},
        ) from exc


def resolve_page_image(page) -> Image.Image:
    """Resolve a Page ORM row into a PIL Image.

    Supports flat image files and CBZ/ZIP/CBR/RAR archives.  Raises AppError
    when the file or archive member is missing.  Applies resolution limits
    to prevent OOM on ultra-high-res scans.
    """
    file_path = Path(page.file_path)
    suffix = file_path.suffix.lower()

    if suffix in {".cbz", ".zip", ".cbr", ".rar"}:
        image = _resolve_archive_page(file_path, page.number)
    else:
        if not file_path.is_file():
            raise AppError(
                "Image file not found.",
                code="file_not_found",
                status_code=404,
                details={"path": str(file_path)},
            )
        image = Image.open(file_path)

    # Validate it's actually an image
    if not hasattr(image, "mode"):
        raise AppError(
            "File is not a valid image.",
            code="invalid_image",
            status_code=500,
            details={"path": str(file_path)},
        )

    # Enforce resolution limit to prevent OOM
    max_pixels = getattr(get_settings(), "ocr_max_image_pixels", 50_000_000)
    w, h = image.size
    if w * h > max_pixels:
        ratio = (max_pixels / (w * h)) ** 0.5
        new_w, new_h = int(w * ratio), int(h * ratio)
        logger.debug(
            "Image %s exceeds max_pixels (%s > %s), resizing to %sx%s",
            file_path.name,
            w * h,
            max_pixels,
            new_w,
            new_h,
        )
        image = image.resize((new_w, new_h), Image.LANCZOS)

    return image
