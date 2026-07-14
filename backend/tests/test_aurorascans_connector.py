from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.aurorascans.connector import AuroraScansConnector
from connectors.registry import create_connector, list_installed_connectors


FIXTURES = Path(__file__).parent / "fixtures" / "aurorascans"


def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def aurorascans_connector() -> AuroraScansConnector:
    return AuroraScansConnector()


def test_registry_lists_aurorascans():
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    assert "aurorascans" in browsable
    connector = create_connector("aurorascans")
    assert type(connector).__name__ == "AuroraScansConnector"


def test_list_series_uses_qimanga_api(aurorascans_connector: AuroraScansConnector):
    listing_payload = _load("series_list.json")

    with patch.object(aurorascans_connector._http, "get_json", return_value=listing_payload) as mock_get:
        listing = aurorascans_connector.get_series_list(1, sort="latest")

    mock_get.assert_called_once_with(
        "/series",
        params={"page": 1, "perPage": 20, "sort": "latest"},
    )
    assert listing.total == 818
    assert len(listing.items) == 2
    assert listing.items[0].id == "the-artist-who-paints-dungeon"
    assert listing.has_more is True


def test_search_series_uses_search_endpoint(aurorascans_connector: AuroraScansConnector):
    listing_payload = _load("series_list.json")

    with patch.object(aurorascans_connector._http, "get_json", return_value=listing_payload) as mock_get:
        listing = aurorascans_connector.search_series("dungeon", 1)

    mock_get.assert_called_once_with(
        "/series/search",
        params={"page": 1, "perPage": 20, "sort": "latest", "q": "dungeon"},
    )
    assert len(listing.items) == 2


def test_get_series_and_chapters(aurorascans_connector: AuroraScansConnector):
    detail_payload = _load("series_detail.json")
    chapter_payload = _load("chapter_list.json")

    with patch.object(
        aurorascans_connector._http,
        "get_json",
        side_effect=[detail_payload, chapter_payload],
    ):
        series = aurorascans_connector.get_series("the-artist-who-paints-dungeon")
        chapters = aurorascans_connector.get_chapters("the-artist-who-paints-dungeon")

    assert series is not None
    assert series.title == "The Artist Who Paints Dungeon"
    assert series.chapter_count == 8
    assert len(chapters) == 1
    assert chapters[0].id == "the-artist-who-paints-dungeon/chapters/chapter-10"
    assert chapters[0].title == "Chapter 10"


def test_chapter_pages(aurorascans_connector: AuroraScansConnector):
    pages_payload = _load("chapter_pages.json")
    chapter_id = "the-artist-who-paints-dungeon/chapters/chapter-10"

    with patch.object(aurorascans_connector._http, "get_json", return_value=pages_payload):
        pages = aurorascans_connector.get_chapter_pages(chapter_id)

    assert len(pages) == 2
    assert pages[0].number == 1
    assert pages[0].remote_url.endswith("00.webp")
    assert pages[1].number == 2
