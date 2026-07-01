"""Filesystem-safe names for downloaded content."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

_INVALID_WIN_CHARS = '<>:"/\\|?*'


def sanitize_path_segment(name: str, *, fallback: str = "untitled") -> str:
    cleaned = "".join(
        character if character not in _INVALID_WIN_CHARS else "_"
        for character in name.strip()
    )
    cleaned = cleaned.rstrip(". ") or fallback
    return cleaned[:200]


def page_extension(remote_url: str) -> str:
    path = urlparse(remote_url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        return suffix
    return ".jpg"
