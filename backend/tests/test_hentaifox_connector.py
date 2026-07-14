from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.hentaifox import HentaiFoxConnector
from connectors.registry import create_connector, list_installed_connectors


FIXTURES = Path(__file__).parent / "fixtures" / "hentaifox"


@pytest.fixture
def hentaifox_connector() -> HentaiFoxConnector:
    return HentaiFoxConnector()


def test_registry_lists_hentaifox_as_mature():
    descriptors = {item.source_type: item for item in list_installed_connectors(include_mature=True)}
    assert "hentaifox" in descriptors
    assert descriptors["hentaifox"].mature is True
    assert descriptors["hentaifox"].name == "HentaiFox"


def test_list_series_from_home_fixture(hentaifox_connector: HentaiFoxConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(hentaifox_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = hentaifox_connector.get_series_list(1)

    mock_fetch.assert_called_once_with("/")
    assert len(listing.items) >= 10
    assert listing.items[0].id == "167410"
    assert "Over Fifty" in listing.items[0].title
    assert listing.items[0].cover_url is not None
    assert listing.has_more is True


def test_get_chapters_and_pages(hentaifox_connector: HentaiFoxConnector):
    detail = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    reader = (FIXTURES / "reader_page.html").read_text(encoding="utf-8")
    gallery_id = "167410"

    def fake_fetch(path: str) -> str:
        if path == f"/gallery/{gallery_id}/":
            return detail
        if path == f"/g/{gallery_id}/47/":
            return reader
        raise AssertionError(f"unexpected path {path}")

    with patch.object(hentaifox_connector, "_fetch_html", side_effect=fake_fetch):
        series = hentaifox_connector.get_series(gallery_id)
        chapters = hentaifox_connector.get_chapters(gallery_id)
        pages = hentaifox_connector.get_chapter_pages(gallery_id)

    assert series is not None
    assert "Over Fifty" in series.title
    assert len(chapters) == 1
    assert chapters[0].page_count == 47
    assert len(pages) == 47
    assert pages[0].remote_url.endswith("/1.webp")
    assert pages[-1].remote_url.endswith("/47.png")
    assert hentaifox_connector.find_page(pages[0].id) == pages[0]


def test_create_hentaifox_connector():
    connector = create_connector("hentaifox")
    assert isinstance(connector, HentaiFoxConnector)
