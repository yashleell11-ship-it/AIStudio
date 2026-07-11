from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.porncomic18.connector import PornComic18Connector
from connectors.registry import create_connector


FIXTURES = Path(__file__).parent / "fixtures" / "porncomic18"


@pytest.fixture
def porncomic18_connector() -> PornComic18Connector:
    return PornComic18Connector()


def test_list_series_from_fixture(porncomic18_connector: PornComic18Connector):
    html = (FIXTURES / "listing.html").read_text(encoding="utf-8")

    with patch.object(porncomic18_connector, "_fetch_html", return_value=html):
        listing = porncomic18_connector.get_series_list(1)

    assert len(listing.items) == 20
    assert listing.items[0].id == "hypnotizing-maomao-manga"
    assert listing.has_more is True


def test_get_chapters_and_pages(porncomic18_connector: PornComic18Connector):
    series_html = (FIXTURES / "series.html").read_text(encoding="utf-8")
    chapter_html = (FIXTURES / "chapter.html").read_text(encoding="utf-8")

    def fake_fetch(path: str) -> str:
        if path == "/comic/secret-class":
            return series_html
        if path == "/comic/secret-class/chapter-242":
            return chapter_html
        raise AssertionError(path)

    with patch.object(porncomic18_connector, "_fetch_html", side_effect=fake_fetch):
        series = porncomic18_connector.get_series("secret-class")
        chapters = porncomic18_connector.get_chapters("secret-class")
        pages = porncomic18_connector.get_chapter_pages("secret-class/chapter-242")

    assert series is not None
    assert series.title == "Secret Class"
    assert len(chapters) == 242
    assert len(pages) == 35
    assert pages[0].remote_url.endswith("/01.jpg")
    assert porncomic18_connector.find_page(pages[0].id) == pages[0]


def test_create_18porncomic_connector():
    connector = create_connector("18porncomic")
    assert connector.source_type == "18porncomic"
    assert connector.is_mature is True
