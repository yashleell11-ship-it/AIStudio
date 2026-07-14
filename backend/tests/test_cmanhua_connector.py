from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.cmanhua.connector import CManhuaConnector
from connectors.cmanhua.mappers import (
    jump_page_form,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cmanhua"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def cmanhua_connector() -> CManhuaConnector:
    return CManhuaConnector()


def test_connector_is_mature():
    connector = CManhuaConnector()
    assert connector.source_type == "cmanhua"
    assert connector.display_name == "CManhua"
    assert connector.is_mature is True
    assert "manhua.5um.net" in connector.allowed_image_hosts
    assert "cmanhua.com" in connector.allowed_image_hosts


def test_parse_series_list_from_allcomics_fixture():
    html = _load("allcomics_p1.html")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) == 24
    assert listing.has_more is True
    assert listing.items[0].id == "guifeijintianyeyaoyishensidi"
    assert listing.items[0].title == "贵妃今天也要以身饲敌"
    assert listing.items[0].cover_url == (
        "https://cmanhua.com/pictures/guifeijintianyeyaoyishensidi/cover.webp"
    )
    assert listing.total >= 24 * 2


def test_allcomics_page_2_differs_from_page_1():
    page1 = parse_series_list(_load("allcomics_p1.html"), page=1)
    page2 = parse_series_list(_load("allcomics_p2.html"), page=2)
    assert page1.items[0].id != page2.items[0].id
    assert {item.id for item in page1.items}.isdisjoint({item.id for item in page2.items})


def test_browse_page_1_gets_allcomics(cmanhua_connector: CManhuaConnector):
    html = _load("allcomics_p1.html")
    with patch.object(cmanhua_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = cmanhua_connector.get_series_list(1)

    mock_fetch.assert_called_once_with("/AllComics")
    assert len(listing.items) == 24
    assert listing.has_more is True


def test_browse_page_2_uses_aspnet_jump(cmanhua_connector: CManhuaConnector):
    page1 = _load("allcomics_p1.html")
    page2 = _load("allcomics_p2.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get(path: str, *, params=None):
        del params
        assert path == "/AllComics"
        return page1

    def fake_post(path: str, *, data=None, extra_headers=None):
        del extra_headers
        captured.append((path, data))
        return page2

    with (
        patch.object(cmanhua_connector, "_fetch_html", side_effect=fake_get),
        patch.object(cmanhua_connector._http, "post_text", side_effect=fake_post),
    ):
        listing = cmanhua_connector.get_series_list(2)

    assert captured
    assert captured[0][0] == "/AllComics"
    form = captured[0][1] or {}
    assert form["ctl00$MainContent$txtJumpPage"] == "2"
    assert form["ctl00$MainContent$btnJumpPage"] == "跳转"
    assert form["__VIEWSTATE"]
    assert listing.items[0].id != "guifeijintianyeyaoyishensidi"


def test_jump_page_form_reads_viewstate():
    form = jump_page_form(_load("allcomics_p1.html"), 10)
    assert form["ctl00$MainContent$txtJumpPage"] == "10"
    assert len(form["__VIEWSTATE"]) > 100
    assert form["__VIEWSTATEGENERATOR"]


def test_latest_mode_uses_mangaupdate(cmanhua_connector: CManhuaConnector):
    html = _load("mangaupdate.html")
    with patch.object(cmanhua_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = cmanhua_connector.get_series_list(1, sort="latest")

    mock_fetch.assert_called_once_with("/MangaUpdate")
    assert len(listing.items) >= 10
    assert listing.has_more is False


def test_search_uses_handler(cmanhua_connector: CManhuaConnector):
    payload = json.loads(_load("search.json"))

    with patch.object(cmanhua_connector._http, "get_json_value", return_value=payload) as mock_json:
        listing = cmanhua_connector.search_series("放肆", 1)

    mock_json.assert_called_once_with(
        "/Modules/Search/SearchHandler.ashx",
        params={"q": "放肆"},
    )
    assert listing.items
    assert listing.items[0].id
    assert listing.items[0].cover_url and listing.items[0].cover_url.startswith("https://")


def test_parse_search_results_page_2_empty():
    payload = json.loads(_load("search.json"))
    listing = parse_search_results(payload, page=2)
    assert listing.items == []
    assert listing.has_more is False


def test_get_series_chapters_and_pages(cmanhua_connector: CManhuaConnector):
    detail = _load("series_detail.html")
    reader = _load("chapter_reader.html")
    series_id = "fangsi"

    def fake_get(path: str, *, params=None):
        del params
        if path.startswith("/comic/"):
            return detail
        if path.startswith("/ReadComic"):
            return reader
        raise AssertionError(path)

    with patch.object(cmanhua_connector, "_fetch_html", side_effect=fake_get):
        series = cmanhua_connector.get_series(series_id)
        chapters = cmanhua_connector.get_chapters(series_id)
        pages = cmanhua_connector.get_chapter_pages(chapters[0].id)

    assert series is not None
    assert series.title == "放肆"
    assert series.author and "玄笺" in series.author
    assert series.status == "Ongoing"
    assert series.cover_url and series.cover_url.endswith("/fangsi/cover.webp")
    assert len(chapters) == 31
    assert chapters[0].id == "69d4da0bf111574e5c5e5678"
    assert chapters[0].number == 1.0
    assert len(pages) == 43
    assert pages[0].remote_url and "manhua.5um.net" in pages[0].remote_url
    assert cmanhua_connector.find_page(pages[0].id) == pages[0]


def test_parse_helpers_round_trip():
    detail = _load("series_detail.html")
    series = parse_series_detail(detail, series_id="fangsi")
    chapters = parse_chapters(detail, series_id="fangsi")
    pages = parse_chapter_pages(_load("chapter_reader.html"), chapter_id=chapters[0].id)
    assert series is not None
    assert series.chapter_count == 31
    assert len(chapters) == 31
    assert pages[0].chapter_id == chapters[0].id
