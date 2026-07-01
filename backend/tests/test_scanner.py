from __future__ import annotations

from pathlib import Path

from connectors.local_filesystem.scanner import _extract_chapter_number
from utils.scanner import classify_import_root, scan_library_root


def test_single_series_folder_with_episode_chapters(tmp_path: Path):
    series_dir = tmp_path / "Solo Leveling"
    for episode in ["Episode 0", "Episode 1", "Episode 2", "Episode 3"]:
        chapter_dir = series_dir / episode
        chapter_dir.mkdir(parents=True)
        (chapter_dir / "001.jpg").write_bytes(b"page-1")
        (chapter_dir / "002.jpg").write_bytes(b"page-2")

    assert classify_import_root(series_dir) == "series"
    result = scan_library_root(series_dir)
    assert result.series_count == 1
    assert result.chapter_count == 4
    assert result.page_count == 8
    assert result.series[0].title == "Solo Leveling"
    assert [chapter.title for chapter in result.series[0].chapters] == [
        "Episode 0",
        "Episode 1",
        "Episode 2",
        "Episode 3",
    ]


def test_library_root_with_nested_series(tmp_path: Path):
    library_root = tmp_path / "Library"
    series_dir = library_root / "Solo Leveling"
    chapter_dir = series_dir / "Chapter 001"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"page-1")
    (chapter_dir / "002.jpg").write_bytes(b"page-2")

    assert classify_import_root(library_root) == "library"
    result = scan_library_root(library_root)
    assert result.series_count == 1
    assert result.series[0].title == "Solo Leveling"
    assert result.chapter_count == 1
    assert len(result.series[0].chapters[0].pages) == 2


def test_library_root_with_multiple_series(tmp_path: Path):
    library_root = tmp_path / "Library"
    for name in ["Series A", "Series B"]:
        chapter_dir = library_root / name / "Chapter 1"
        chapter_dir.mkdir(parents=True)
        (chapter_dir / "1.jpg").write_bytes(b"page")

    assert classify_import_root(library_root) == "library"
    result = scan_library_root(library_root)
    assert result.series_count == 2
    assert {series.title for series in result.series} == {"Series A", "Series B"}


def test_extract_chapter_number_supports_decimals():
    assert _extract_chapter_number("Chapter 13.5") == 13.5
    assert _extract_chapter_number("120.1 - Omake") == 120.1
    assert _extract_chapter_number("Chapter 42") == 42.0
    assert _extract_chapter_number("no digits here") is None


def test_scan_preserves_decimal_chapter_number(tmp_path: Path):
    series_dir = tmp_path / "Solo Leveling"
    chapter_dir = series_dir / "Chapter 13.5"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"page-1")

    result = scan_library_root(series_dir)
    assert result.series[0].chapters[0].number == 13.5
