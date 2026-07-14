from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.hentaiera import HentaiEraConnector
from connectors.registry import create_connector, list_installed_connectors


FIXTURES = Path(__file__).parent / "fixtures" / "hentaiera"


@pytest.fixture
def hentaiera_connector() -> HentaiEraConnector:
    return HentaiEraConnector()


def test_registry_lists_hentaiera_as_mature():
    descriptors = {item.source_type: item for item in list_installed_connectors(include_mature=True)}
    assert "hentaiera" in descriptors
    assert descriptors["hentaiera"].mature is True
    assert descriptors["hentaiera"].name == "HentaiEra"


def test_list_series_from_home_fixture(hentaiera_connector: HentaiEraConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(hentaiera_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = hentaiera_connector.get_series_list(1)

    mock_fetch.assert_called_once_with("/")
    assert len(listing.items) >= 10
    assert listing.items[0].id == "1687423"
    assert listing.items[0].title
    assert listing.has_more is True


def test_get_chapters_and_pages(hentaiera_connector: HentaiEraConnector):
    detail = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    gallery_id = "1687423"

    with patch.object(hentaiera_connector, "_fetch_html", return_value=detail):
        series = hentaiera_connector.get_series(gallery_id)
        chapters = hentaiera_connector.get_chapters(gallery_id)
        pages = hentaiera_connector.get_chapter_pages(gallery_id)

    assert series is not None
    assert "Cool Rock" in series.title
    assert len(chapters) == 1
    assert chapters[0].page_count == 11
    assert len(pages) == 11
    assert pages[0].remote_url.endswith("/1.webp")


def test_create_hentaiera_connector():
    connector = create_connector("hentaiera")
    assert isinstance(connector, HentaiEraConnector)
