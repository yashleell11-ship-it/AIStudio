"""Local filesystem source connector."""

from __future__ import annotations

from pathlib import Path

from connectors.base import SourceConnector
from connectors.local_filesystem.scanner import (
    ScanResult,
    ScannedChapter,
    ScannedSeries,
    scan_library_root,
)
from connectors.models import Chapter, Page, PaginatedSeriesList, Series

DEFAULT_PAGE_SIZE = 50


def _normalize_path(path: str) -> str:
    return str(Path(path).resolve())


def _chapter_id(chapter: ScannedChapter) -> str:
    if chapter.folder_path:
        return _normalize_path(chapter.folder_path)
    if chapter.archive_path:
        return _normalize_path(chapter.archive_path)
    return chapter.title


def _series_id(scanned: ScannedSeries) -> str:
    return _normalize_path(scanned.folder_path)


def _page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}#{page_number}"


def _to_series(scanned: ScannedSeries) -> Series:
    series_id = _series_id(scanned)
    return Series(
        id=series_id,
        title=scanned.title,
        chapter_count=len(scanned.chapters),
        canonical_path=series_id,
    )


def _to_chapter(scanned: ScannedChapter, series_id: str) -> Chapter:
    chapter_id = _chapter_id(scanned)
    return Chapter(
        id=chapter_id,
        series_id=series_id,
        title=scanned.title,
        number=scanned.number,
        page_count=len(scanned.pages),
        folder_path=_normalize_path(scanned.folder_path)
        if scanned.folder_path
        else None,
        archive_path=scanned.archive_path,
    )


def _to_page(scanned_chapter_id: str, scanned_page) -> Page:
    return Page(
        id=_page_id(scanned_chapter_id, scanned_page.number),
        chapter_id=scanned_chapter_id,
        number=scanned_page.number,
        file_path=scanned_page.file_path,
        archive_path=scanned_page.archive_path,
        archive_member=scanned_page.archive_member,
    )


class LocalFilesystemConnector(SourceConnector):
    """Discovers series, chapters, and pages from a folder on disk."""

    SOURCE_TYPE = "local_filesystem"
    DISPLAY_NAME = "Local Filesystem"
    DESCRIPTION = "Import series from folders on disk."
    BROWSABLE = False
    SUPPORTS_IMPORT = True

    def __init__(self, root_path: str | Path, *, page_size: int = DEFAULT_PAGE_SIZE) -> None:
        self._root_path = Path(root_path)
        self._page_size = page_size
        self._scan: ScanResult | None = None
        self._series_index: dict[str, ScannedSeries] = {}
        self._chapter_index: dict[str, ScannedChapter] = {}
        self._chapter_series: dict[str, str] = {}

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    @property
    def is_browsable(self) -> bool:
        return self.BROWSABLE

    @property
    def supports_import(self) -> bool:
        return self.SUPPORTS_IMPORT

    def _ensure_index(self) -> ScanResult:
        if self._scan is not None:
            return self._scan

        self._scan = scan_library_root(self._root_path)
        self._series_index = {_series_id(series): series for series in self._scan.series}

        for scanned_series in self._scan.series:
            series_id = _series_id(scanned_series)
            for chapter in scanned_series.chapters:
                chapter_id = _chapter_id(chapter)
                self._chapter_index[chapter_id] = chapter
                self._chapter_series[chapter_id] = series_id

        return self._scan

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        scan = self._ensure_index()
        if page < 1:
            page = 1

        total = len(scan.series)
        start = (page - 1) * self._page_size
        end = start + self._page_size
        page_items = [_to_series(item) for item in scan.series[start:end]]

        return PaginatedSeriesList(
            items=page_items,
            page=page,
            page_size=self._page_size,
            total=total,
        )

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        scan = self._ensure_index()
        if page < 1:
            page = 1

        normalized = query.strip().casefold()
        if normalized:
            filtered = [
                item
                for item in scan.series
                if normalized in item.title.casefold()
            ]
        else:
            filtered = list(scan.series)

        total = len(filtered)
        start = (page - 1) * self._page_size
        end = start + self._page_size
        page_items = [_to_series(item) for item in filtered[start:end]]

        return PaginatedSeriesList(
            items=page_items,
            page=page,
            page_size=self._page_size,
            total=total,
        )

    def get_series(self, series_id: str) -> Series | None:
        self._ensure_index()
        scanned = self._series_index.get(series_id)
        if scanned is None:
            return None
        return _to_series(scanned)

    def get_chapters(self, series_id: str) -> list[Chapter]:
        self._ensure_index()
        scanned = self._series_index.get(series_id)
        if scanned is None:
            return []
        return [_to_chapter(chapter, series_id) for chapter in scanned.chapters]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        self._ensure_index()
        scanned = self._chapter_index.get(chapter_id)
        if scanned is None:
            return []
        return [_to_page(chapter_id, page) for page in scanned.pages]
