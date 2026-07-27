from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from utils.path_utils import (
    IMAGE_EXTENSIONS,
    is_archive_file,
    list_archive_files,
    list_image_files,
    natural_sort_key,
)

ImportMode = Literal["series", "library"]


@dataclass
class ScannedPage:
    number: int
    file_path: str
    archive_path: str | None = None
    archive_member: str | None = None


@dataclass
class ScannedChapter:
    title: str
    number: float | None
    folder_path: str | None
    archive_path: str | None
    pages: list[ScannedPage] = field(default_factory=list)


@dataclass
class ScannedSeries:
    title: str
    folder_path: str
    chapters: list[ScannedChapter] = field(default_factory=list)


@dataclass
class ScanResult:
    series: list[ScannedSeries] = field(default_factory=list)
    series_count: int = 0
    chapter_count: int = 0
    page_count: int = 0


def _extract_chapter_number(name: str) -> float | None:
    """Extract a chapter number from a filename or folder name.

    Captures decimal chapter numbers (e.g. "Chapter 13.5", "120.1 - Omake")
    so bonus/half chapters are not truncated to their integer part.
    """
    match = re.search(r"(\d+(?:\.\d+)?)", name)
    if match:
        return float(match.group(1))
    return None


def _first_level_subdirs(path: Path) -> list[Path]:
    return sorted(
        [
            entry
            for entry in path.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        ],
        key=lambda item: natural_sort_key(item.name),
    )


def _has_direct_page_content(path: Path) -> bool:
    return bool(list_image_files(path) or list_archive_files(path))


def _has_chapter_subdirs(path: Path) -> bool:
    return any(_has_direct_page_content(child) for child in _first_level_subdirs(path))


def classify_import_root(root_path: Path) -> ImportMode:
    """Decide whether the selected folder is one series or a library of series."""
    children = _first_level_subdirs(root_path)
    if not children:
        return "series"

    nested_series_dirs = [
        child
        for child in children
        if _has_chapter_subdirs(child) and not _has_direct_page_content(child)
    ]
    leaf_chapter_dirs = [
        child
        for child in children
        if _has_direct_page_content(child) and not _has_chapter_subdirs(child)
    ]

    if nested_series_dirs and not leaf_chapter_dirs:
        return "library"

    if leaf_chapter_dirs and len(leaf_chapter_dirs) == len(children):
        if all(list_image_files(child) for child in children):
            return "series"
        if all(
            not list_image_files(child) and list_archive_files(child) for child in children
        ):
            return "library"
        return "series"

    if nested_series_dirs:
        return "library"

    return "series"


def _scan_image_directory(directory: Path, title: str) -> ScannedChapter | None:
    images = list_image_files(directory)
    if not images:
        return None
    pages = [
        ScannedPage(number=index, file_path=str(image.resolve()))
        for index, image in enumerate(images, start=1)
    ]
    return ScannedChapter(
        title=title,
        number=_extract_chapter_number(title),
        folder_path=str(directory.resolve()),
        archive_path=None,
        pages=pages,
    )


def _scan_archive_file(archive: Path) -> ScannedChapter | None:
    members: list[str] = []
    with zipfile.ZipFile(archive, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            member_path = Path(name)
            if member_path.suffix.lower() in IMAGE_EXTENSIONS:
                members.append(name)
    if not members:
        return None
    members.sort(key=natural_sort_key)
    pages = [
        ScannedPage(
            number=index,
            file_path=str(archive.resolve()),
            archive_path=str(archive.resolve()),
            archive_member=member,
        )
        for index, member in enumerate(members, start=1)
    ]
    return ScannedChapter(
        title=archive.stem,
        number=_extract_chapter_number(archive.stem),
        folder_path=None,
        archive_path=str(archive.resolve()),
        pages=pages,
    )


def _sort_chapters(chapters: list[ScannedChapter]) -> list[ScannedChapter]:
    return sorted(
        chapters,
        key=lambda chapter: (
            chapter.number if chapter.number is not None else float("inf"),
            natural_sort_key(chapter.title),
        ),
    )


def _scan_series_directory(series_dir: Path) -> ScannedSeries:
    chapters: list[ScannedChapter] = []

    for entry in sorted(series_dir.iterdir(), key=lambda item: natural_sort_key(item.name)):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            chapter = _scan_image_directory(entry, entry.name)
            if chapter:
                chapters.append(chapter)
        elif is_archive_file(entry):
            chapter = _scan_archive_file(entry)
            if chapter:
                chapters.append(chapter)

    direct_images = list_image_files(series_dir)
    if direct_images and not chapters:
        pages = [
            ScannedPage(number=index, file_path=str(image.resolve()))
            for index, image in enumerate(direct_images, start=1)
        ]
        chapters.append(
            ScannedChapter(
                title="Chapter 1",
                number=1,
                folder_path=str(series_dir.resolve()),
                archive_path=None,
                pages=pages,
            )
        )

    archives = list_archive_files(series_dir)
    if not chapters and archives:
        for archive in archives:
            chapter = _scan_archive_file(archive)
            if chapter:
                chapters.append(chapter)

    return ScannedSeries(
        title=series_dir.name,
        folder_path=str(series_dir.resolve()),
        chapters=_sort_chapters(chapters),
    )


def scan_library_root(root_path: Path) -> ScanResult:
    result = ScanResult()
    if not root_path.is_dir():
        return result

    mode = classify_import_root(root_path)

    if mode == "series":
        series = _scan_series_directory(root_path)
        if series.chapters:
            result.series = [series]
    else:
        for entry in sorted(root_path.iterdir(), key=lambda item: natural_sort_key(item.name)):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                series = _scan_series_directory(entry)
                if series.chapters:
                    result.series.append(series)
            elif is_archive_file(entry):
                chapter = _scan_archive_file(entry)
                if chapter:
                    result.series.append(
                        ScannedSeries(
                            title=entry.stem,
                            folder_path=str(root_path.resolve()),
                            chapters=[chapter],
                        )
                    )

    result.series_count = len(result.series)
    result.chapter_count = sum(len(series.chapters) for series in result.series)
    result.page_count = sum(
        len(chapter.pages)
        for series in result.series
        for chapter in series.chapters
    )
    return result
