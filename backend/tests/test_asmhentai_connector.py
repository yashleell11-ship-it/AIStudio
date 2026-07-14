from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.asmhentai.connector import AsmHentaiConnector
from connectors.registry import create_connector, list_installed_connectors


FIXTURES = Path(__file__).parent / "fixtures" / "asmhentai"


@pytest.fixture
def asmhentai_connector() -> AsmHentaiConnector:
    return AsmHentaiConnector()


def test_registry_lists_asmhentai_as_mature():
    descriptors = {item.source_type: item for item in list_installed_connectors(include_mature=True)}
    assert "asmhentai" in descriptors
    assert descriptors["asmhentai"].mature is True
    assert descriptors["asmhentai"].name == "AsmHentai"


def test_list_series_from_home_fixture(asmhentai_connector: AsmHentaiConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(asmhentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = asmhentai_connector.get_series_list(1)

    mock_fetch.assert_called_once_with("/")
    assert len(listing.items) >= 19
    assert listing.items[0].id == "659418"
    assert listing.items[0].title == "ERZA X NATSU"
    assert listing.items[0].cover_url.startswith("https://images.asmhentai.com/")
    assert listing.has_more is True


def test_search_series_uses_search_path(asmhentai_connector: AsmHentaiConnector):
    html = (FIXTURES / "search_listing.html").read_text(encoding="utf-8")

    with patch.object(asmhentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = asmhentai_connector.search_series("erza", 1)

    mock_fetch.assert_called_once_with("/search/?q=erza")
    assert len(listing.items) >= 1
    assert listing.items[0].id == "659418"


def test_get_chapters_and_pages(asmhentai_connector: AsmHentaiConnector):
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    gallery_id = "659418"

    with patch.object(asmhentai_connector, "_fetch_html", return_value=html):
        series = asmhentai_connector.get_series(gallery_id)
        chapters = asmhentai_connector.get_chapters(gallery_id)
        pages = asmhentai_connector.get_chapter_pages(gallery_id)

    assert series is not None
    assert "ERZA X NATSU" in series.title
    assert "fairy tail" in series.genres
    assert len(chapters) == 1
    assert chapters[0].page_count == 3
    assert len(pages) == 3
    assert pages[0].remote_url == "https://images.asmhentai.com/018/659418/1.jpg"
    assert asmhentai_connector.find_page(pages[0].id) == pages[0]


def test_popular_browse_mode_uses_sort_query(asmhentai_connector: AsmHentaiConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(asmhentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        asmhentai_connector.get_series_list(1, sort="popular")

    mock_fetch.assert_called_once_with("/?sort=popular")


def test_create_asmhentai_connector():
    connector = create_connector("asmhentai")
    assert connector.source_type == "asmhentai"
    assert connector.is_mature is True
