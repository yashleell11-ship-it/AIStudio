from __future__ import annotations

from pathlib import Path

import pytest

from connectors.adapters import build_scan_result
from connectors.local_filesystem.connector import LocalFilesystemConnector
from connectors.registry import create_connector, list_connector_types
from services.source_service import SourceService


def test_list_connector_types_includes_local_filesystem():
    assert "local_filesystem" in list_connector_types()


def test_local_filesystem_connector_series_list(tmp_path: Path):
    series_dir = tmp_path / "Solo Leveling"
    for episode in ["Episode 0", "Episode 1"]:
        chapter_dir = series_dir / episode
        chapter_dir.mkdir(parents=True)
        (chapter_dir / "001.jpg").write_bytes(b"page-1")

    connector = create_connector("local_filesystem", root_path=series_dir)
    listing = connector.get_series_list(1)

    assert listing.total == 1
    assert len(listing.items) == 1
    assert listing.items[0].title == "Solo Leveling"
    assert listing.items[0].chapter_count == 2


def test_local_filesystem_connector_chapters_and_pages(tmp_path: Path):
    series_dir = tmp_path / "Solo Leveling"
    chapter_dir = series_dir / "Episode 0"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"page-1")
    (chapter_dir / "002.jpg").write_bytes(b"page-2")

    connector = LocalFilesystemConnector(series_dir)
    series_list = connector.get_series_list(1)
    series = connector.get_series(series_list.items[0].id)
    chapters = connector.get_chapters(series_list.items[0].id)
    pages = connector.get_chapter_pages(chapters[0].id)

    assert series is not None
    assert series.title == "Solo Leveling"
    assert len(chapters) == 1
    assert chapters[0].title == "Episode 0"
    assert chapters[0].page_count == 2
    assert len(pages) == 2
    assert pages[0].number == 1
    assert pages[1].number == 2


def test_build_scan_result_matches_source_service(tmp_path: Path):
    series_dir = tmp_path / "Solo Leveling"
    for episode in ["Episode 0", "Episode 1"]:
        chapter_dir = series_dir / episode
        chapter_dir.mkdir(parents=True)
        (chapter_dir / "001.jpg").write_bytes(b"page-1")

    connector = LocalFilesystemConnector(series_dir)
    adapter_result = build_scan_result(connector)
    service_result = SourceService().discover_folder(str(series_dir))

    assert adapter_result.series_count == service_result.series_count == 1
    assert adapter_result.chapter_count == service_result.chapter_count == 2
    assert adapter_result.page_count == service_result.page_count == 2


def test_create_connector_rejects_unknown_type():
    with pytest.raises(ValueError, match="Unknown source type"):
        create_connector("unknown_source", root_path="/tmp")
