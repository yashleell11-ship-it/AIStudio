from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.firstkissmanga.connector import FirstKissMangaConnector
from connectors.firstkissmanga.http import is_fingerprint_gate, is_parking_page
from connectors.firstkissmanga.mappers import (
    parse_chapter_pages,
    parse_chapters,
    parse_series_list,
)
from connectors.registry import create_connector, list_installed_connectors


FIXTURES = Path(__file__).parent / "fixtures" / "firstkissmanga"
SERIES_ID = "doupo-cangqiong"
CHAPTER_ID = f"{SERIES_ID}/chapter-370"


@pytest.fixture
def firstkiss_connector() -> FirstKissMangaConnector:
    return FirstKissMangaConnector()


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_registry_lists_1stkissmanga():
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    assert "1stkissmanga" in browsable


def test_fingerprint_gate_detection():
    gate_html = """
    <script src="fingerprintjs"></script>
    <script>var redirect_link = 'https://1stkissmanga.io/manga/';</script>
    """
    catalog_html = _load("browse_latest.html")
    assert is_fingerprint_gate(gate_html)
    assert not is_fingerprint_gate(catalog_html)


def test_parking_page_detection():
    assert is_parking_page("<title>parklogic.com</title>", url="https://ww16.1stkissmanga.io/")
    assert not is_parking_page(_load("browse_latest.html"), url="https://1stkissmanga.io/manga/")


def test_parse_series_list_from_fixture():
    listing = parse_series_list(_load("browse_latest.html"), page=1)
    assert len(listing.items) == 6
    assert listing.items[0].id == "kill-the-dragon"
    assert listing.items[0].title == "Kill the Dragon"
    assert listing.items[0].cover_url is not None


def test_browse_page_2_differs_from_page_1(firstkiss_connector: FirstKissMangaConnector):
    page1 = _load("browse_latest.html")
    page2 = _load("browse_page2.html")

    def fake_get_text(path: str, *, params=None):
        if path.endswith("/page/2/"):
            return page2
        return page1

    with patch.object(firstkiss_connector._http, "get_text", side_effect=fake_get_text):
        first = firstkiss_connector.get_series_list(1)
        second = firstkiss_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id
    assert first.has_more is True


def test_browse_uses_manga_path_and_sort(firstkiss_connector: FirstKissMangaConnector):
    html = _load("browse_latest.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(firstkiss_connector._http, "get_text", side_effect=fake_get_text):
        firstkiss_connector.get_series_list(1)
        firstkiss_connector.get_series_list(2, sort="popular")

    assert captured[0][0] == "/manga/"
    assert captured[0][1] == {}
    assert captured[1][0] == "/manga/page/2/"
    assert captured[1][1] == {"m_orderby": "views"}


def test_get_chapters_and_pages(firstkiss_connector: FirstKissMangaConnector):
    series_html = _load("series_detail.html")
    chapter_html = _load("chapter_reader.html")

    def fake_get_text(path: str, *, params=None):
        if path == f"/manga/{SERIES_ID}/":
            return series_html
        if path == f"/manga/{CHAPTER_ID}/":
            return chapter_html
        raise AssertionError(path)

    with patch.object(firstkiss_connector._http, "get_text", side_effect=fake_get_text):
        series = firstkiss_connector.get_series(SERIES_ID)
        chapters = firstkiss_connector.get_chapters(SERIES_ID)
        pages = firstkiss_connector.get_chapter_pages(CHAPTER_ID)

    assert series is not None
    assert series.title == "Doupo Cangqiong"
    assert len(chapters) >= 10
    assert chapters[-1].number == 370.0
    assert len(pages) == 3
    assert pages[0].remote_url.endswith(".jpg")
    assert "1stkmgv2.com" in pages[0].remote_url
    assert firstkiss_connector.find_page(pages[0].id) == pages[0]


def test_parse_chapter_pages_extracts_lazy_src():
    pages = parse_chapter_pages(_load("chapter_reader.html"), CHAPTER_ID)
    assert len(pages) == 3
    assert pages[0].remote_url.endswith(".jpg")
    assert pages[1].remote_url.endswith(".webp")
    assert "data:image" not in pages[1].remote_url


def test_parse_chapters_filters_by_series():
    chapters = parse_chapters(_load("series_detail.html"), SERIES_ID)
    assert chapters
    assert all(chapter.series_id == SERIES_ID for chapter in chapters)


def test_create_1stkissmanga_connector():
    connector = create_connector("1stkissmanga")
    assert connector.source_type == "1stkissmanga"
    assert connector.is_mature is False


def test_allowed_image_hosts(firstkiss_connector: FirstKissMangaConnector):
    hosts = firstkiss_connector.allowed_image_hosts
    assert "1stkissmanga.io" in hosts
    assert "1stkmgv2.com" in hosts
