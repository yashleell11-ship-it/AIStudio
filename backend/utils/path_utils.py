from __future__ import annotations

import re
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
ARCHIVE_EXTENSIONS = {".cbz", ".zip"}


def natural_sort_key(value: str) -> list[int | str]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def is_archive_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ARCHIVE_EXTENSIONS


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
