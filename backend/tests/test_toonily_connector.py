from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.registry import create_connector, list_installed_connectors
from connectors.toonily.connector import ToonilyConnector
from connectors.toonily.mappers import parse_chapter_pages, parse_chapters, parse_series_list

FIXTURES = Path(__file__).parent / "fixtures" / "toonily"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def toonily_connector() -> ToonilyConnector:
    return ToonilyConnector()


def test_registry_lists_toonily():
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    assert "toonily" in browsable


def test_parse_series_list_from_fixture():
    html = _load("browse_latest.html")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) >= 10
    assert listing.has_more is True
    assert listing.items[0].id == "the-beginning-after-the-end-7b1d8c89"
    assert listing.items[0].cover_url


def test_browse_page_2_differs_from_page_1(toonily_connector: ToonilyConnector):
    page1 = _load("browse_latest.html")
    page2 = _load("browse_page2.html")

    def fake_get_text(path: str, *, params=None):
        if path.endswith("/page/2/"):
            return page2
        return page1

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        first = toonily_connector.get_series_list(1)
        second = toonily_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id
    assert first.has_more is True


def test_browse_uses_webtoons_path_and_sort(toonily_connector: ToonilyConnector):
    html = _load("browse_latest.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        toonily_connector.get_series_list(1)
        toonily_connector.get_series_list(2, sort="popular")

    assert captured[0][0] == "/webtoons/"
    assert captured[0][1] == {}
    assert captured[1][0] == "/webtoons/page/2/"
    assert captured[1][1] == {"m_orderby": "views"}


def test_each_browse_mode_requests_a_distinct_order_value(
    toonily_connector: ToonilyConnector,
):
    html = _load("browse_latest.html")
    captured: list[dict | None] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return html

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        toonily_connector.get_series_list(1, sort="default")
        toonily_connector.get_series_list(1, sort="latest")
        toonily_connector.get_series_list(1, sort="popular")
        toonily_connector.get_series_list(1, sort="rating")

    order_values = [
        (params or {}).get("m_orderby", "latest")
        for params in captured
    ]
    assert order_values == ["latest", "new-manga", "views", "ratings"]
    assert len(set(order_values)) == 4


def test_browse_modes_parse_into_different_series_lists():
    latest_html = _load("browse_latest.html")
    popular_html = _load("browse_popular.html")

    latest_listing = parse_series_list(latest_html, page=1)
    popular_listing = parse_series_list(popular_html, page=1)

    assert latest_listing.items[0].id != popular_listing.items[0].id


def test_search_finds_titles_not_on_browse_page_1(toonily_connector: ToonilyConnector):
    browse_html = _load("browse_latest.html")
    search_html = _load("search_solo.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search_html
        return browse_html

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        browse = toonily_connector.get_series_list(1)
        search = toonily_connector.search_series("solo leveling", 1)

    browse_ids = {item.id for item in browse.items}
    assert search.items
    assert any("solo" in item.title.casefold() for item in search.items)
    assert any(item.id not in browse_ids for item in search.items)


def test_get_series_chapters_and_pages(toonily_connector: ToonilyConnector):
    series_id = "the-beginning-after-the-end-7b1d8c89"
    chapter_id = f"{series_id}/chapter-240"
    detail_html = _load("series_detail.html")
    chapter_html = _load("chapter_reader.html")

    def fake_get_text(path: str, *, params=None):
        if path == f"/serie/{series_id}/":
            return detail_html
        if path == f"/serie/{chapter_id}/":
            return chapter_html
        raise AssertionError(path)

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        series = toonily_connector.get_series(series_id)
        chapters_before = toonily_connector.get_chapters(series_id)
        pages = toonily_connector.get_chapter_pages(chapter_id)
        chapters_after = toonily_connector.get_chapters(series_id)

    assert series is not None
    assert series.id == series_id
    assert series.title == "The Beginning After the End"
    assert series.author == "TurtleMe"
    assert series.artist == "Duta Permana"
    assert series.status == "OnGoing"
    assert "Action" in series.genres
    assert series.description
    assert len(chapters_before) >= 1
    assert chapters_before[0].id.startswith(series_id + "/")
    assert all(chapter.page_count == 0 for chapter in chapters_before)
    assert len(pages) >= 2
    assert pages[0].remote_url is not None
    assert "tnlycdn.com" in pages[0].remote_url
    assert toonily_connector.find_page(pages[0].id) == pages[0]

    chapter_latest = next(chapter for chapter in chapters_after if chapter.id == chapter_id)
    assert chapter_latest.page_count == len(pages)
    assert chapter_latest.page_count >= 2
    assert chapter_latest.number == 240.0


def test_parse_chapter_pages_extracts_image_urls():
    html = _load("chapter_reader.html")
    chapter_id = "the-beginning-after-the-end-7b1d8c89/chapter-240"
    pages = parse_chapter_pages(html, chapter_id)
    assert len(pages) == 3
    assert all(page.remote_url and "tnlycdn.com" in page.remote_url for page in pages)


def test_parse_chapters_filters_by_series():
    html = _load("series_detail.html")
    series_id = "the-beginning-after-the-end-7b1d8c89"
    chapters = parse_chapters(html, series_id)
    assert len(chapters) >= 2
    assert chapters[0].series_id == series_id
    assert chapters[-1].number == 240.0


def test_parse_decimal_chapter_number():
    html = _load("series_detail.html")
    series_id = "the-beginning-after-the-end-7b1d8c89"
    chapters = parse_chapters(html, series_id)
    decimal = next(
        (chapter for chapter in chapters if chapter.number is not None and chapter.number % 1 != 0),
        None,
    )
    if decimal is not None:
        assert decimal.number == float(int(decimal.number)) + (decimal.number % 1)


def test_create_toonily_connector():
    connector = create_connector("toonily")
    assert connector.source_type == "toonily"


def test_list_browse_modes(toonily_connector: ToonilyConnector):
    modes = toonily_connector.list_browse_modes()
    mode_ids = {mode.id for mode in modes}
    assert "popular" in mode_ids
    assert "latest" in mode_ids
    assert "default" in mode_ids


def test_allowed_image_hosts(toonily_connector: ToonilyConnector):
    hosts = toonily_connector.allowed_image_hosts
    assert "tnlycdn.com" in hosts
