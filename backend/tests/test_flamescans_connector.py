from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.flamescans.connector import FlameScansConnector
from connectors.flamescans.mappers import (
    chapter_pages_to_pages,
    make_chapter_id,
    parse_chapter_id,
    parse_next_data,
    series_list_item_to_series,
)


FIXTURES = Path(__file__).parent / "fixtures" / "flamescans"


def _load_json(name: str) -> list | dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def flamescans_connector() -> FlameScansConnector:
    return FlameScansConnector()


def test_parse_chapter_id_roundtrip():
    chapter_id = make_chapter_id("138", "d52a1478c5459405")
    assert chapter_id == "138/d52a1478c5459405"
    assert parse_chapter_id(chapter_id) == ("138", "d52a1478c5459405")
    assert parse_chapter_id("bad") is None


def test_series_list_item_maps_cover():
    item = _load_json("series_list.json")[0]
    series = series_list_item_to_series(item)
    assert series is not None
    assert series.id == "138"
    assert series.title == "Surviving the Apocalypse"
    assert series.chapter_count == 91
    assert series.cover_url == (
        "https://cdn.flamecomics.xyz/uploads/images/series/138/thumbnail.webp"
    )


def test_list_series_paginates_api_catalog(flamescans_connector: FlameScansConnector):
    catalog = _load_json("series_list.json")

    with patch.object(flamescans_connector._http, "get_json_value", return_value=catalog) as mock_get:
        listing = flamescans_connector.get_series_list(1, sort="latest")

    mock_get.assert_called_once_with("/api/series")
    assert listing.total == 3
    assert len(listing.items) == 3
    assert listing.items[0].id == "138"
    assert listing.has_more is False


def test_search_filters_titles(flamescans_connector: FlameScansConnector):
    catalog = _load_json("series_list.json")

    with patch.object(flamescans_connector._http, "get_json_value", return_value=catalog):
        listing = flamescans_connector.search_series("ancient", 1)

    assert len(listing.items) == 1
    assert listing.items[0].title == "The Ancient Sovereign of Eternity"


def test_popular_sort_orders_by_chapter_count(flamescans_connector: FlameScansConnector):
    catalog = _load_json("series_list.json")

    with patch.object(flamescans_connector._http, "get_json_value", return_value=catalog):
        listing = flamescans_connector.get_series_list(1, sort="popular")

    assert listing.items[0].id == "23"
    assert listing.items[0].chapter_count == 495


def test_get_series_and_chapters(flamescans_connector: FlameScansConnector):
    html = _load_text("series_detail.html")

    with patch.object(flamescans_connector._http, "get_text", return_value=html) as mock_get:
        series = flamescans_connector.get_series("138")
        chapters = flamescans_connector.get_chapters("138")

    mock_get.assert_called_with("/series/138")
    assert series is not None
    assert series.title == "Surviving the Apocalypse"
    assert series.chapter_count == 2
    assert series.author == "Song"
    assert "Action" in series.genres
    assert len(chapters) == 2
    assert chapters[0].id == "138/e7dde88aab33c49b"
    assert chapters[0].number == 1.0
    assert chapters[-1].id == "138/d52a1478c5459405"
    assert chapters[-1].number == 90.0


def test_chapter_pages(flamescans_connector: FlameScansConnector):
    html = _load_text("chapter_pages.html")
    chapter_id = "138/d52a1478c5459405"

    with patch.object(flamescans_connector._http, "get_text", return_value=html) as mock_get:
        pages = flamescans_connector.get_chapter_pages(chapter_id)

    mock_get.assert_called_once_with("/series/138/d52a1478c5459405")
    assert len(pages) == 2
    assert pages[0].number == 1
    assert pages[0].remote_url.startswith(
        "https://cdn.flamecomics.xyz/uploads/images/series/138/d52a1478c5459405/SA-90-00.jpg"
    )
    assert pages[1].number == 2
    assert pages[1].id == f"{chapter_id}:2"


def test_parse_next_data_and_pages_mapper():
    props = parse_next_data(_load_text("chapter_pages.html"))
    assert props is not None
    pages = chapter_pages_to_pages("138/d52a1478c5459405", props)
    assert len(pages) == 2
    assert pages[0].width == 1778
