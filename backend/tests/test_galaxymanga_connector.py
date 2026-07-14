from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.galaxymanga.connector import GalaxyMangaConnector
from connectors.galaxymanga.mappers import (
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
)

FIXTURES = Path(__file__).parent / "fixtures" / "galaxymanga"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def galaxymanga_connector() -> GalaxyMangaConnector:
    return GalaxyMangaConnector()


def test_connector_is_mature():
    connector = GalaxyMangaConnector()
    assert connector.source_type == "galaxymanga"
    assert connector.display_name == "GalaxyManga"
    assert connector.is_mature is True
    assert "galaxymanga.io" in connector.allowed_image_hosts
    assert "dl.galaxymanga.io" in connector.allowed_image_hosts


def test_parse_series_list_from_fixture():
    html = _load("browse_page1.html")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) == 24
    assert listing.has_more is True
    assert listing.items[0].id == "my-younger-sister-chooses-me-tonight"
    assert listing.items[0].title
    assert listing.items[0].cover_url and "galaxymanga.io" in listing.items[0].cover_url


def test_browse_page_2_differs_from_page_1(galaxymanga_connector: GalaxyMangaConnector):
    page1 = _load("browse_page1.html")
    page2 = _load("browse_page2.html")

    def fake_get_text(path: str, *, params=None):
        if params and params.get("page") == 2:
            return page2
        return page1

    with patch.object(galaxymanga_connector._http, "get_text", side_effect=fake_get_text):
        first = galaxymanga_connector.get_series_list(1)
        second = galaxymanga_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id
    assert first.has_more is True
    assert second.has_more is True


def test_browse_uses_order_params(galaxymanga_connector: GalaxyMangaConnector):
    html = _load("browse_page1.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(galaxymanga_connector._http, "get_text", side_effect=fake_get_text):
        galaxymanga_connector.get_series_list(1)
        galaxymanga_connector.get_series_list(2, sort="popular")
        galaxymanga_connector.get_series_list(1, sort="latest")
        galaxymanga_connector.get_series_list(1, sort="rating")

    assert captured[0] == ("/manga/", {"order": "update"})
    assert captured[1] == ("/manga/", {"order": "popular", "page": 2})
    assert captured[2] == ("/manga/", {"order": "latest"})
    assert captured[3] == ("/manga/", {"order": "title"})


def test_popular_listing_differs_from_update():
    update = parse_series_list(_load("browse_page1.html"), page=1)
    popular = parse_series_list(_load("browse_popular.html"), page=1)
    assert update.items[0].id != popular.items[0].id
    assert popular.items[0].id == "tears-on-a-withered-flower"


def test_search_series(galaxymanga_connector: GalaxyMangaConnector):
    html = _load("search_predatory.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(galaxymanga_connector._http, "get_text", side_effect=fake_get_text):
        listing = galaxymanga_connector.search_series("predatory", 1)

    assert captured == [("/", {"s": "predatory"})]
    assert listing.items[0].id == "predatory-marriage"
    assert listing.has_more is False

    search_listing = parse_search_results(html, page=1)
    assert any(item.id == "predatory-marriage" for item in search_listing.items)


def test_search_page_2_path(galaxymanga_connector: GalaxyMangaConnector):
    html = _load("search_predatory.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(galaxymanga_connector._http, "get_text", side_effect=fake_get_text):
        galaxymanga_connector.search_series("love", 2)

    assert captured == [("/page/2/", {"s": "love"})]


def test_series_chapters_and_pages(galaxymanga_connector: GalaxyMangaConnector):
    series_html = _load("series_predatory.html")
    chapter_html = _load("chapter_1.html")
    series_id = "predatory-marriage"

    def fake_get_text(path: str, *, params=None):
        if path.startswith("/manga/"):
            return series_html
        if "chapter-1" in path:
            return chapter_html
        raise AssertionError(f"unexpected path {path}")

    with patch.object(galaxymanga_connector._http, "get_text", side_effect=fake_get_text):
        series = galaxymanga_connector.get_series(series_id)
        chapters = galaxymanga_connector.get_chapters(series_id)
        pages = galaxymanga_connector.get_chapter_pages("predatory-marriage-chapter-1")

    assert series is not None
    assert series.title == "Predatory Marriage"
    assert series.status == "Ongoing"
    assert "Romance" in series.genres
    assert series.cover_url and "galaxymanga.io" in series.cover_url
    assert series.chapter_count == len(chapters) == 81
    assert chapters[0].id == "predatory-marriage-chapter-0-1"
    assert chapters[0].number == 0.1
    assert chapters[-1].id == "predatory-marriage-chapter-80"
    assert chapters[-1].number == 80
    assert len(pages) == 19
    assert pages[0].remote_url.startswith("https://dl.galaxymanga.io/")
    assert galaxymanga_connector.find_page(pages[0].id) == pages[0]


def test_parse_helpers_directly():
    series = parse_series_detail(_load("series_predatory.html"), "predatory-marriage")
    assert series is not None
    assert series.title == "Predatory Marriage"

    chapters = parse_chapters(_load("series_predatory.html"), "predatory-marriage")
    assert len(chapters) == 81

    pages = parse_chapter_pages(_load("chapter_1.html"), "predatory-marriage-chapter-1")
    assert len(pages) == 19
    assert pages[0].id == "predatory-marriage-chapter-1:1"
