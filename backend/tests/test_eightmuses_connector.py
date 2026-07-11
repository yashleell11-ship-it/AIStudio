from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.eightmuses.connector import EightMusesConnector
from connectors.eightmuses.mappers import parse_chapters, parse_chapter_pages, parse_publishers
from connectors.registry import create_connector


FIXTURES = Path(__file__).parent / "fixtures" / "eightmuses"


@pytest.fixture
def eightmuses_connector() -> EightMusesConnector:
    return EightMusesConnector()


def test_parse_publishers_from_fixture():
    html = (FIXTURES / "publishers.html").read_text(encoding="utf-8")
    publishers = parse_publishers(html)
    assert "JAB-Comics" in publishers
    assert "MilfToon-Comics" in publishers
    assert len(publishers) >= 60


def test_browse_lists_comics_for_first_publisher(eightmuses_connector: EightMusesConnector):
    publishers_html = (FIXTURES / "publishers.html").read_text(encoding="utf-8")
    jab_html = (FIXTURES / "jab_comics.html").read_text(encoding="utf-8")
    publishers = parse_publishers(publishers_html)
    jab_page = publishers.index("JAB-Comics") + 1

    def fake_fetch(path: str) -> str:
        if path == "/comics":
            return publishers_html
        if path == "/comics/album/JAB-Comics":
            return jab_html
        raise AssertionError(path)

    with patch.object(eightmuses_connector, "_fetch_html", side_effect=fake_fetch):
        listing = eightmuses_connector.get_series_list(jab_page)

    assert len(listing.items) >= 60
    assert listing.items[0].id == "JAB-Comics/Ay-Papi"
    assert listing.items[0].title == "Ay Papi"
    assert listing.has_more is True


def test_get_chapters_and_pages(eightmuses_connector: EightMusesConnector):
    series_html = (FIXTURES / "ay_papi.html").read_text(encoding="utf-8")
    chapter_html = (FIXTURES / "issue_1.html").read_text(encoding="utf-8")

    def fake_fetch(path: str) -> str:
        if path == "/comics/album/JAB-Comics/Ay-Papi":
            return series_html
        if path == "/comics/album/JAB-Comics/Ay-Papi/Issue-1":
            return chapter_html
        raise AssertionError(path)

    with patch.object(eightmuses_connector, "_fetch_html", side_effect=fake_fetch):
        series = eightmuses_connector.get_series("JAB-Comics/Ay-Papi")
        chapters = eightmuses_connector.get_chapters("JAB-Comics/Ay-Papi")
        pages = eightmuses_connector.get_chapter_pages("JAB-Comics/Ay-Papi/Issue-1")

    assert series is not None
    assert series.title == "Ay Papi"
    assert len(chapters) >= 19
    assert chapters[0].title == "Issue 1"
    assert len(pages) == 22
    assert pages[0].remote_url is not None
    assert "/image/fl/" in pages[0].remote_url
    assert eightmuses_connector.find_page(pages[0].id) == pages[0]


def test_search_series(eightmuses_connector: EightMusesConnector):
    search_html = (FIXTURES / "search_ay_papi.html").read_text(encoding="utf-8")

    with patch.object(eightmuses_connector, "_fetch_html", return_value=search_html):
        listing = eightmuses_connector.search_series("ay papi", 1)

    assert len(listing.items) == 2
    assert listing.items[0].id == "JAB-Comics/Ay-Papi"


def test_leaf_album_parses_single_complete_chapter():
    html = """
    <a class="c-tile t-hover" href="/comics/album/Example/One-Shot" title="One Shot"></a>
    <a href="/comics/picture/Example/One-Shot/1"></a>
    <a href="/comics/picture/Example/One-Shot/2"></a>
    """
    chapters = parse_chapters(html, series_id="Example/One-Shot")
    assert len(chapters) == 1
    assert chapters[0].id == "Example/One-Shot"
    assert chapters[0].page_count == 2


def test_create_8muses_connector():
    connector = create_connector("8muses")
    assert connector.source_type == "8muses"
    assert connector.is_mature is True
