from __future__ import annotations

import re
from pathlib import Path

from core.errors import AppError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
ARCHIVE_EXTENSIONS = {".cbz", ".zip"}


def natural_sort_key(value: str) -> list[int | str]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def is_archive_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ARCHIVE_EXTENSIONS


def normalize_path(path: str | Path) -> Path:
    return Path(path).resolve()


def validate_absolute_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise AppError(
            "Path must be absolute.",
            code="invalid_path",
            status_code=400,
            details={"path": path},
        )
    return candidate


def validate_path_under_roots(path: Path, roots: list[Path]) -> None:
    resolved = path.resolve()
    for root in roots:
        root_resolved = root.resolve()
        try:
            resolved.relative_to(root_resolved)
            return
        except ValueError:
            continue
    # Do not surface the absolute resolved server path to the client.
    raise AppError(
        "Path is outside registered library roots.",
        code="path_traversal",
        status_code=403,
    )


def list_image_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files = [entry for entry in directory.iterdir() if is_image_file(entry)]
    return sorted(files, key=lambda item: natural_sort_key(item.name))


def list_archive_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files = [entry for entry in directory.iterdir() if is_archive_file(entry)]
    return sorted(files, key=lambda item: natural_sort_key(item.name))
