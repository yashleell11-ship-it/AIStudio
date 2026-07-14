from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.comicasura.connector import ComicAsuraConnector
from connectors.comicasura.mappers import (
    chapter_number_from_slug,
    listing_path,
    parse_chapter_id,
)


FIXTURES = Path(__file__).parent / "fixtures" / "comicasura"


@pytest.fixture
def comicasura_connector() -> ComicAsuraConnector:
    return ComicAsuraConnector()


def test_mature_flag(comicasura_connector: ComicAsuraConnector):
    assert comicasura_connector.is_mature is True
    assert comicasura_connector.source_type == "comicasura"
    assert comicasura_connector.display_name == "ComicAsura"


def test_allowed_image_hosts(comicasura_connector: ComicAsuraConnector):
    hosts = comicasura_connector.allowed_image_hosts
    assert "2xstorage.com" in hosts
    assert "waitst.com" in hosts


def test_listing_path_encodes_search_and_sort():
    assert listing_path(1) == "/advanced-search"
    assert listing_path(2) == "/advanced-search?page=2"
    assert listing_path(1, search="infinite mage") == "/advanced-search?name=infinite%20mage"
    assert listing_path(1, sort="rating") == "/advanced-search?sort=rating"
    assert "sort=latest" in listing_path(3, sort="latest")


def test_chapter_id_helpers():
    assert parse_chapter_id("infinite-mage/chapter-176") == ("infinite-mage", "chapter-176")
    assert parse_chapter_id("manga/infinite-mage/chapter-0-1") == ("infinite-mage", "chapter-0-1")
    assert parse_chapter_id("bad") is None
    assert chapter_number_from_slug("chapter-176") == 176.0
    assert chapter_number_from_slug("chapter-0-1") == 0.1


def test_list_series_from_fixture(comicasura_connector: ComicAsuraConnector):
    html = (FIXTURES / "listing.html").read_text(encoding="utf-8")

    with patch.object(comicasura_connector._http, "get_text", return_value=html) as mock_get:
        listing = comicasura_connector.get_series_list(1, sort="latest")

    mock_get.assert_called_once_with("/advanced-search?sort=latest")
    assert len(listing.items) == 3
    assert listing.items[0].id == "kids-being-kids"
    assert listing.items[0].cover_url.endswith("kids-being-kids.webp")
    assert listing.items[1].title == "Infinite Mage"
    assert listing.has_more is True


def test_search_series_uses_name_param(comicasura_connector: ComicAsuraConnector):
    html = (FIXTURES / "listing.html").read_text(encoding="utf-8")

    with patch.object(comicasura_connector._http, "get_text", return_value=html) as mock_get:
        listing = comicasura_connector.search_series("mage", 1)

    mock_get.assert_called_once_with("/advanced-search?name=mage")
    assert len(listing.items) == 3


def test_get_series_and_chapters(comicasura_connector: ComicAsuraConnector):
    html = (FIXTURES / "series_detail.html").read_text(encoding="utf-8")

    with patch.object(comicasura_connector._http, "get_text", return_value=html):
        series = comicasura_connector.get_series("infinite-mage")
        chapters = comicasura_connector.get_chapters("infinite-mage")

    assert series is not None
    assert series.title == "Infinite Mage"
    assert series.status == "Ongoing"
    assert "Action" in series.genres
    assert series.cover_url == "https://storage4.waitst.com/thumb/infinite-mage.webp"
    assert series.chapter_count == 4
    assert len(chapters) == 4
    assert chapters[0].id == "infinite-mage/chapter-0-1"
    assert chapters[0].number == 0.1
    assert chapters[-1].id == "infinite-mage/chapter-176"
    assert chapters[-1].number == 176.0


def test_chapter_pages(comicasura_connector: ComicAsuraConnector):
    html = (FIXTURES / "chapter_pages.html").read_text(encoding="utf-8")
    chapter_id = "infinite-mage/chapter-176"

    with patch.object(comicasura_connector._http, "get_text", return_value=html) as mock_get:
        pages = comicasura_connector.get_chapter_pages(chapter_id)

    mock_get.assert_called_once_with("/manga/infinite-mage/chapter-176")
    assert len(pages) == 3
    assert pages[0].number == 1
    assert pages[0].remote_url.endswith("/176/0.webp")
    assert pages[2].remote_url.endswith("/176/2.webp")
    assert comicasura_connector.find_page(pages[0].id) == pages[0]
