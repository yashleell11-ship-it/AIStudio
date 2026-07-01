"""Backward-compatible re-exports for the local filesystem scanner."""

from connectors.local_filesystem.scanner import (
    ImportMode,
    ScanResult,
    ScannedChapter,
    ScannedPage,
    ScannedSeries,
    _extract_chapter_number,
    classify_import_root,
    scan_library_root,
)

__all__ = [
    "ImportMode",
    "ScanResult",
    "ScannedChapter",
    "ScannedPage",
    "ScannedSeries",
    "_extract_chapter_number",
    "classify_import_root",
    "scan_library_root",
]
