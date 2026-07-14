from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.comicland.connector import ComicLandConnector


FIXTURES = Path(__file__).parent / "fixtures" / "comicland"


def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def comicland_connector() -> ComicLandConnector:
    return ComicLandConnector()


def test_connector_metadata(comicland_connector: ComicLandConnector):
    assert comicland_connector.source_type == "comicland"
    assert comicland_connector.display_name == "ComicLand"
    assert comicland_connector.is_mature is True
    assert comicland_connector.is_browsable is True
    assert "cdn.comicland.org" in comicland_connector.allowed_image_hosts
    modes = {mode.id for mode in comicland_connector.list_browse_modes()}
    assert modes == {"latest", "popular", "ongoing", "official", "uncensored"}


def test_list_series_latest(comicland_connector: ComicLandConnector):
    payload = _load("comics_list.json")

    with patch.object(comicland_connector._http, "get_json", return_value=payload) as mock_get:
        listing = comicland_connector.get_series_list(1, sort="latest")

    mock_get.assert_called_once_with(
        "/comics",
        params={"offset": 0, "limit": 20},
    )
    assert len(listing.items) == 2
    assert listing.items[0].id == "my-kingdom-silent-war"
    assert listing.items[0].title == "My Kingdom (Silent War)"
    assert listing.items[0].cover_url.endswith("/cover.jpg")
    assert listing.has_more is False


def test_list_series_popular_slices(comicland_connector: ComicLandConnector):
    payload = _load("popular.json")

    with patch.object(comicland_connector._http, "get_json", return_value=payload) as mock_get:
        page1 = comicland_connector.get_series_list(1, sort="popular")
        page2 = comicland_connector.get_series_list(2, sort="popular")

    mock_get.assert_called_once_with("/comics/popular", params=None)
    assert len(page1.items) == 2
    assert page1.has_more is False
    assert page2.items == []


def test_search_series(comicland_connector: ComicLandConnector):
    payload = _load("search.json")

    with patch.object(comicland_connector._http, "get_json", return_value=payload) as mock_get:
        listing = comicland_connector.search_series("secret", 1)

    mock_get.assert_called_once_with(
        "/comic/search",
        params={"offset": 0, "limit": 20, "q": "secret"},
    )
    assert len(listing.items) == 2
    assert listing.has_more is True
    assert listing.total == 60


def test_get_series_and_chapters(comicland_connector: ComicLandConnector):
    detail = _load("comic_detail.json")

    with patch.object(comicland_connector._http, "get_json", return_value=detail):
        series = comicland_connector.get_series("my-kingdom-silent-war")
        chapters = comicland_connector.get_chapters("my-kingdom-silent-war")

    assert series is not None
    assert series.title == "My Kingdom (Silent War)"
    assert series.chapter_count == 3
    assert len(chapters) == 3
    assert chapters[0].id == "my-kingdom-silent-war/chapters/3"
    assert chapters[0].number == 3.0
    assert chapters[-1].id == "my-kingdom-silent-war/chapters/1"


def test_chapter_pages(comicland_connector: ComicLandConnector):
    pages_payload = _load("chapter_pages.json")
    chapter_id = "my-kingdom-silent-war/chapters/1"

    with patch.object(comicland_connector._http, "get_json", return_value=pages_payload) as mock_get:
        pages = comicland_connector.get_chapter_pages(chapter_id)

    mock_get.assert_called_once_with(
        "/chapter/pages_by_index",
        params={"slug": "my-kingdom-silent-war", "index": 1},
    )
    assert len(pages) == 3
    assert pages[0].number == 1
    assert pages[0].remote_url.endswith("/001.jpg")
    assert pages[0].id == f"{chapter_id}:1"
    found = comicland_connector.find_page(f"{chapter_id}:2")
    assert found is not None
    assert found.number == 2


def test_browse_by_genre(comicland_connector: ComicLandConnector):
    payload = _load("comics_list.json")

    with patch.object(comicland_connector._http, "get_json", return_value=payload) as mock_get:
        listing = comicland_connector.browse_by_genre("romance", 2)

    mock_get.assert_called_once_with(
        "/comics_by_genre",
        params={"offset": 20, "limit": 20, "name": "romance"},
    )
    assert len(listing.items) == 2
