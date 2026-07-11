from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.registry import create_connector, list_installed_connectors
from connectors.threehentai.connector import ThreeHentaiConnector


FIXTURES = Path(__file__).parent / "fixtures" / "threehentai"


@pytest.fixture
def threehentai_connector() -> ThreeHentaiConnector:
    return ThreeHentaiConnector()


def test_registry_lists_3hentai_as_mature():
    descriptors = {item.source_type: item for item in list_installed_connectors(include_mature=True)}
    assert "3hentai" in descriptors
    assert descriptors["3hentai"].mature is True
    assert descriptors["3hentai"].name == "3Hentai"


def test_list_series_from_home_fixture(threehentai_connector: ThreeHentaiConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(threehentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = threehentai_connector.get_series_list(1)

    mock_fetch.assert_called_once_with("/")
    assert len(listing.items) >= 1
    assert listing.items[0].id.isdigit()
    assert listing.items[0].cover_url is not None
    assert listing.has_more is True


def test_search_series_uses_search_path(threehentai_connector: ThreeHentaiConnector):
    html = (FIXTURES / "search_listing.html").read_text(encoding="utf-8")

    with patch.object(threehentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = threehentai_connector.search_series("elf", 1)

    mock_fetch.assert_called_once_with("/search?q=elf")
    assert len(listing.items) >= 1


def test_get_chapters_and_pages(threehentai_connector: ThreeHentaiConnector):
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    gallery_id = "699891"

    with patch.object(threehentai_connector, "_fetch_html", return_value=html):
        series = threehentai_connector.get_series(gallery_id)
        chapters = threehentai_connector.get_chapters(gallery_id)
        pages = threehentai_connector.get_chapter_pages(gallery_id)

    assert series is not None
    assert "Rinko" in series.title
    assert "doujinshi" in series.genres
    assert len(chapters) == 1
    assert chapters[0].page_count > 0
    assert len(pages) == chapters[0].page_count
    assert pages[0].remote_url.endswith("/1.jpg")
    assert threehentai_connector.find_page(pages[0].id) == pages[0]


def test_english_browse_mode_uses_language_query(threehentai_connector: ThreeHentaiConnector):
    html = (FIXTURES / "search_listing.html").read_text(encoding="utf-8")

    with patch.object(threehentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        threehentai_connector.get_series_list(1, sort="english")

    mock_fetch.assert_called_once_with("/search?q=language%3Aenglish")


def test_create_3hentai_connector():
    connector = create_connector("3hentai")
    assert connector.source_type == "3hentai"
    assert connector.is_mature is True
