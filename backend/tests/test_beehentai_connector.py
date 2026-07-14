from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.beehentai.connector import BeeHentaiConnector


FIXTURES = Path(__file__).parent / "fixtures" / "beehentai"


def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def beehentai_connector() -> BeeHentaiConnector:
    return BeeHentaiConnector()


def test_connector_metadata(beehentai_connector: BeeHentaiConnector):
    assert beehentai_connector.source_type == "beehentai"
    assert beehentai_connector.display_name == "BeeHentai"
    assert beehentai_connector.is_mature is True
    assert "rx.toondex.io" in beehentai_connector.allowed_image_hosts


def test_list_series_uses_toondex_search(beehentai_connector: BeeHentaiConnector):
    listing_payload = _load("series_list.json")

    with patch.object(beehentai_connector._http, "get_json", return_value=listing_payload) as mock_get:
        listing = beehentai_connector.get_series_list(1, sort="latest")

    mock_get.assert_called_once_with(
        "/titles/search",
        params={"page": 1, "limit": 24, "sort": "latest"},
    )
    assert listing.total == 3247
    assert len(listing.items) == 2
    assert listing.items[0].id == "onsaemiro"
    assert listing.has_more is True


def test_search_series_passes_query(beehentai_connector: BeeHentaiConnector):
    listing_payload = _load("series_list.json")

    with patch.object(beehentai_connector._http, "get_json", return_value=listing_payload) as mock_get:
        listing = beehentai_connector.search_series("solo", 1)

    mock_get.assert_called_once_with(
        "/titles/search",
        params={"page": 1, "limit": 24, "sort": "latest", "q": "solo"},
    )
    assert len(listing.items) == 2


def test_browse_by_genre_uses_genres_param(beehentai_connector: BeeHentaiConnector):
    listing_payload = _load("series_list.json")

    with patch.object(beehentai_connector._http, "get_json", return_value=listing_payload) as mock_get:
        listing = beehentai_connector.browse_by_genre("adult", 1, sort="popular")

    mock_get.assert_called_once_with(
        "/titles/search",
        params={"page": 1, "limit": 24, "sort": "popular", "genres": "adult"},
    )
    assert len(listing.items) == 2


def test_list_genres(beehentai_connector: BeeHentaiConnector):
    genres_payload = _load("genres.json")

    with patch.object(beehentai_connector._http, "get_json", return_value=genres_payload):
        genres = beehentai_connector.list_genres()

    assert genres[0].id == "action"
    assert genres[0].label == "Action"
    assert len(genres) == 3


def test_get_series_and_chapters(beehentai_connector: BeeHentaiConnector):
    detail_payload = _load("series_detail.json")
    chapter_payload = _load("chapter_list.json")

    with patch.object(
        beehentai_connector._http,
        "get_json",
        side_effect=[detail_payload, chapter_payload],
    ):
        series = beehentai_connector.get_series("sister-neighbors")
        chapters = beehentai_connector.get_chapters("sister-neighbors")

    assert series is not None
    assert series.title == "Sister Neighbors"
    assert series.chapter_count == 161
    assert series.author == "Tharchog"
    assert len(chapters) == 2
    # Fetched newest-first from API, returned oldest-first.
    assert chapters[0].id == "sister-neighbors/chapters/chapter-159"
    assert chapters[1].id == "sister-neighbors/chapters/chapter-160"
    assert chapters[1].title == "Chapter 160"


def test_chapter_pages(beehentai_connector: BeeHentaiConnector):
    pages_payload = _load("chapter_pages.json")
    chapter_id = "sister-neighbors/chapters/chapter-1"

    with patch.object(beehentai_connector._http, "get_json", return_value=pages_payload):
        pages = beehentai_connector.get_chapter_pages(chapter_id)

    assert len(pages) == 3
    assert pages[0].number == 1
    assert pages[0].remote_url.startswith("https://rx.toondex.io/")
    assert pages[2].number == 3
    assert pages[0].id == f"{chapter_id}:1"
