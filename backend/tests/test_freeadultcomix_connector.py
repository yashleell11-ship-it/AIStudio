from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from connectors.freeadultcomix.connector import FreeAdultComixConnector
from connectors.freeadultcomix.http import FacSyncHttpClient
from connectors.freeadultcomix.mappers import (
    listing_path,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    search_listing_path,
    tag_listing_path,
)


FIXTURES = Path(__file__).parent / "fixtures" / "freeadultcomix"


@pytest.fixture
def freeadultcomix_connector() -> FreeAdultComixConnector:
    # Avoid live DoH during unit tests.
    http = MagicMock(spec=FacSyncHttpClient)
    return FreeAdultComixConnector(http_client=http)


def test_listing_and_search_paths():
    assert listing_path(1) == "/"
    assert listing_path(2) == "/page/2/"
    assert search_listing_path("jab comix", 1) == "/?s=jab%20comix"
    assert search_listing_path("jab", 3) == "/page/3/?s=jab"
    assert tag_listing_path("big-ass", 1) == "/tag/big-ass/"
    assert tag_listing_path("big-ass", 2) == "/tag/big-ass/page/2/"


def test_parse_home_listing_fixture():
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) == 24
    assert listing.items[0].id == "pegasus-smith-au-naturel-29"
    assert "Au Naturel 29" in listing.items[0].title
    assert listing.items[0].cover_url and "wp-content/uploads" in listing.items[0].cover_url
    assert listing.has_more is True


def test_parse_page2_listing_fixture():
    html = (FIXTURES / "page2_listing.html").read_text(encoding="utf-8")
    listing = parse_series_list(html, page=2)
    assert len(listing.items) >= 20
    assert listing.has_more is True


def test_parse_search_listing_fixture():
    html = (FIXTURES / "search_listing.html").read_text(encoding="utf-8")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) >= 1
    assert any("jab" in item.id or "jab" in item.title.lower() for item in listing.items)


def test_parse_gallery_detail_fixture():
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    series = parse_series_detail(html, "pegasus-smith-au-naturel-29")
    assert series is not None
    assert "Au Naturel 29" in series.title
    assert series.cover_url
    assert len(series.genres) >= 1

    chapters = parse_chapters(html, "pegasus-smith-au-naturel-29")
    pages = parse_chapter_pages(html, "pegasus-smith-au-naturel-29")
    assert len(chapters) == 1
    assert chapters[0].page_count == len(pages)
    assert len(pages) >= 100
    assert pages[0].remote_url.endswith("Au-Naturel-29-0.jpg")
    assert "/wp-content/uploads/" in pages[0].remote_url


def test_list_series_uses_home_path(freeadultcomix_connector: FreeAdultComixConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")
    with patch.object(freeadultcomix_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = freeadultcomix_connector.get_series_list(1)
    mock_fetch.assert_called_once_with("/")
    assert len(listing.items) == 24


def test_search_series_uses_search_path(freeadultcomix_connector: FreeAdultComixConnector):
    html = (FIXTURES / "search_listing.html").read_text(encoding="utf-8")
    with patch.object(freeadultcomix_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = freeadultcomix_connector.search_series("jab", 1)
    mock_fetch.assert_called_once_with("/?s=jab")
    assert len(listing.items) >= 1


def test_browse_by_genre_uses_tag_path(freeadultcomix_connector: FreeAdultComixConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")
    with patch.object(freeadultcomix_connector, "_fetch_html", return_value=html) as mock_fetch:
        freeadultcomix_connector.browse_by_genre("big-ass", 1)
    mock_fetch.assert_called_once_with("/tag/big-ass/")


def test_get_chapters_and_pages(freeadultcomix_connector: FreeAdultComixConnector):
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    series_id = "pegasus-smith-au-naturel-29"
    with patch.object(freeadultcomix_connector, "_fetch_html", return_value=html):
        series = freeadultcomix_connector.get_series(series_id)
        chapters = freeadultcomix_connector.get_chapters(series_id)
        pages = freeadultcomix_connector.get_chapter_pages(series_id)

    assert series is not None
    assert "Au Naturel" in series.title
    assert len(chapters) == 1
    assert chapters[0].page_count == len(pages)
    assert pages[0].remote_url.endswith(".jpg")
    assert freeadultcomix_connector.find_page(pages[0].id) == pages[0]


def test_connector_metadata(freeadultcomix_connector: FreeAdultComixConnector):
    assert freeadultcomix_connector.source_type == "freeadultcomix"
    assert freeadultcomix_connector.display_name == "FreeAdultComix"
    assert freeadultcomix_connector.is_mature is True
    assert "freeadultcomix.com" in freeadultcomix_connector.allowed_image_hosts
