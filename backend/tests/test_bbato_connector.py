from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.bbato.connector import BbatoConnector
from connectors.bbato.mappers import (
    listing_path,
    parse_chapter_pages,
    parse_chapters_from_reader,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_path,
)


FIXTURES = Path(__file__).parent / "fixtures" / "bbato"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def bbato_connector() -> BbatoConnector:
    return BbatoConnector()


def test_bbato_is_mature(bbato_connector: BbatoConnector):
    assert bbato_connector.source_type == "bbato"
    assert bbato_connector.display_name == "Bbato"
    assert bbato_connector.is_mature is True
    assert "merrypsycho.xyz" in bbato_connector.allowed_image_hosts
    assert bbato_connector.image_fetch_headers().get("Referer", "").startswith("https://bbato.com")


def test_listing_paths():
    assert listing_path(1) == "/type/manga"
    assert listing_path(2) == "/type/manga/page/2"
    assert listing_path(1, sort="manhwa") == "/type/manhwa"
    assert search_path("love", 1) == "/filter?keyword=love"
    assert search_path("love", 2) == "/filter?keyword=love&page=2"


def test_parse_series_list_from_fixture():
    html = _load("listing_page1.html")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) == 30
    assert listing.items[0].id == "bound-to-your-ruin"
    assert listing.items[0].title == "Bound to Your Ruin"
    assert listing.items[0].cover_url.startswith("https://cdn2.merrypsycho.xyz/")
    assert listing.has_more is True


def test_browse_page_2_differs(bbato_connector: BbatoConnector):
    page1 = _load("listing_page1.html")
    page2 = _load("listing_page2.html")

    def fake_fetch(path: str) -> str:
        if path.endswith("/page/2"):
            return page2
        return page1

    with patch.object(bbato_connector, "_fetch_html", side_effect=fake_fetch):
        first = bbato_connector.get_series_list(1)
        second = bbato_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id
    assert first.has_more is True


def test_search_series(bbato_connector: BbatoConnector):
    html = _load("search_love.html")
    with patch.object(bbato_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = bbato_connector.search_series("love", 1)

    mock_fetch.assert_called_once_with("/filter?keyword=love")
    assert len(listing.items) >= 1
    assert any("love" in item.id or "love" in item.title.lower() for item in listing.items)


def test_parse_search_results_has_more():
    html = _load("search_love.html")
    listing = parse_search_results(html, page=1)
    assert len(listing.items) == 30
    assert listing.has_more is True


def test_get_series_and_chapters(bbato_connector: BbatoConnector):
    series_html = _load("series_dungeon.html")
    reader_html = _load("reader_ch160.html")

    def fake_fetch(path: str) -> str:
        if path.startswith("/read/"):
            return reader_html
        return series_html

    with patch.object(bbato_connector, "_fetch_html", side_effect=fake_fetch):
        series = bbato_connector.get_series("dungeon-odyssey")
        chapters = bbato_connector.get_chapters("dungeon-odyssey")

    assert series is not None
    assert series.title == "Dungeon Odyssey"
    assert series.cover_url and "dungeon-odyssey" in series.cover_url
    assert series.status == "ongoing"
    assert "Action" in series.genres
    assert "Glumph" in (series.author or "")
    assert len(chapters) == 160
    assert chapters[0].id == "dungeon-odyssey/chapter-1"
    assert chapters[-1].id == "dungeon-odyssey/chapter-160"
    assert series.chapter_count == 160


def test_parse_series_detail_without_reader():
    series = parse_series_detail(_load("series_dungeon.html"), "dungeon-odyssey")
    assert series is not None
    assert series.title == "Dungeon Odyssey"
    assert series.chapter_count == 160


def test_get_chapter_pages(bbato_connector: BbatoConnector):
    html = _load("reader_ch160.html")
    chapter_id = "dungeon-odyssey/chapter-160"

    with patch.object(bbato_connector, "_fetch_html", return_value=html):
        pages = bbato_connector.get_chapter_pages(chapter_id)

    assert len(pages) >= 10
    assert pages[0].number == 1
    assert pages[0].remote_url == "https://cdn2.merrypsycho.xyz/dungeon-odyssey/160/0.webp"
    assert pages[0].id == f"{chapter_id}:1"
    assert bbato_connector.find_page(pages[0].id) == pages[0]


def test_parse_chapter_pages_direct():
    pages = parse_chapter_pages(_load("reader_ch160.html"), "dungeon-odyssey/chapter-160")
    assert len(pages) >= 10
    assert all("merrypsycho.xyz" in (p.remote_url or "") for p in pages)


def test_parse_chapters_from_reader_full_list():
    chapters = parse_chapters_from_reader(
        _load("reader_ch160.html"),
        "dungeon-odyssey",
    )
    assert len(chapters) == 160
    assert chapters[0].number == 1.0
    assert chapters[-1].number == 160.0


def test_browse_by_genre(bbato_connector: BbatoConnector):
    html = _load("genre_action.html")
    with patch.object(bbato_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = bbato_connector.browse_by_genre("action", 1)

    mock_fetch.assert_called_once_with("/genre/action")
    assert len(listing.items) == 30
    assert listing.has_more is True


def test_manhwa_browse_mode_path(bbato_connector: BbatoConnector):
    html = _load("listing_page1.html")
    with patch.object(bbato_connector, "_fetch_html", return_value=html) as mock_fetch:
        bbato_connector.get_series_list(1, sort="manhwa")
    mock_fetch.assert_called_once_with("/type/manhwa")


def test_registry_bbato_when_registered():
    from connectors.registry import create_connector, list_installed_connectors

    descriptors = {
        item.source_type: item for item in list_installed_connectors(include_mature=True)
    }
    if "bbato" not in descriptors:
        pytest.skip("bbato not registered yet — apply registration instructions")
    assert descriptors["bbato"].mature is True
    assert descriptors["bbato"].name == "Bbato"
    connector = create_connector("bbato")
    assert connector.source_type == "bbato"
    assert connector.is_mature is True
