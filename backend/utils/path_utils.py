from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from core.errors import AppError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
ARCHIVE_EXTENSIONS = {".cbz", ".zip"}


def natural_sort_key(value: str) -> list[int | str]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def sorted_archive_image_members(names: Iterable[str]) -> list[str]:
    """Page-ordered image members of a .cbz/.zip, from its ``namelist()``.

    This is the single definition of "which member is page N" for an archive
    chapter. Two places have to agree on it and they are far apart in the code:
    the scanner mints page numbers 1..N from this order at import time, and the
    reader maps a stored page number back to a member at serve time. When they
    disagreed the reader silently served a different image than the number was
    minted for -- with members 1.jpg..11.jpg, a lexicographic reader served
    10.jpg for page 2. Both rules matter, not just the sort:

    * non-image members (ComicInfo.xml, cover.txt, Thumbs.db) are dropped,
      because the scanner never counted them as pages -- keeping one shifts
      every page after it by one;
    * the sort is natural, not lexicographic, so 10.jpg follows 9.jpg.

    Keep this byte-for-byte equivalent to the scanner's member selection in
    backend/connectors/local_filesystem/scanner.py:135-146 (third-party owned,
    so it cannot import this yet); test_archive_page_ordering.py asserts the two
    still agree.
    """
    members = [
        name
        for name in names
        if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_EXTENSIONS
    ]
    members.sort(key=natural_sort_key)
    return members


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
