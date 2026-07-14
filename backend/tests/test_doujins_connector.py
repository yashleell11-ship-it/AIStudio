from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.doujins.connector import DoujinsConnector
from connectors.doujins.mappers import (
    parse_folders_payload,
    parse_gallery_pages,
    parse_html_listing,
    parse_searchbox_payload,
    parse_series_detail,
)


FIXTURES = Path(__file__).parent / "fixtures" / "doujins"


@pytest.fixture
def doujins_connector() -> DoujinsConnector:
    return DoujinsConnector()


def test_connector_is_mature(doujins_connector: DoujinsConnector):
    assert doujins_connector.source_type == "doujins"
    assert doujins_connector.display_name == "Doujins"
    assert doujins_connector.is_mature is True
    assert "static.doujins.com" in doujins_connector.allowed_image_hosts


def test_parse_folders_day_fixture():
    payload = json.loads((FIXTURES / "folders_day.json").read_text(encoding="utf-8"))
    items = parse_folders_payload(payload)
    assert len(items) == 7
    assert items[0].id == "kurokos-basketball/last-ecstasy-matching-with-a-bad-girl-101402"
    assert items[0].title == "Matching With A Bad Girl"
    assert items[0].cover_url and items[0].cover_url.startswith("https://static.doujins.com/")
    assert items[0].artist


def test_list_series_latest_uses_folders_api(doujins_connector: DoujinsConnector):
    payload = json.loads((FIXTURES / "folders_day.json").read_text(encoding="utf-8"))

    with patch.object(doujins_connector, "_fetch_json", return_value=payload) as mock_json:
        listing = doujins_connector.get_series_list(1, sort="latest")

    assert mock_json.called
    assert len(listing.items) == 7
    assert listing.items[0].id.endswith("-101402")
    assert listing.has_more is False


def test_list_series_popular_uses_top_html(doujins_connector: DoujinsConnector):
    html = (FIXTURES / "top_listing.html").read_text(encoding="utf-8")

    with patch.object(doujins_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = doujins_connector.get_series_list(1, sort="popular")

    mock_fetch.assert_called_once_with("/top")
    assert len(listing.items) >= 5
    assert listing.items[0].id.startswith("original-doujins-series/")
    assert listing.items[0].cover_url.startswith("https://static.doujins.com/")


def test_parse_html_listing_top_fixture():
    html = (FIXTURES / "top_listing.html").read_text(encoding="utf-8")
    items = parse_html_listing(html)
    assert len(items) >= 5
    assert "100811" in items[0].id
    assert "Cosplay Sex" in items[0].title


def test_search_series_uses_searchbox(doujins_connector: DoujinsConnector):
    home = (FIXTURES / "home_csrf.html").read_text(encoding="utf-8")
    payload = (FIXTURES / "searchbox.json").read_text(encoding="utf-8")

    with (
        patch.object(doujins_connector, "_fetch_html", return_value=home),
        patch.object(doujins_connector._http, "post_text", return_value=payload) as mock_post,
    ):
        listing = doujins_connector.search_series("Trainee program", 1)

    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "/searchbox"
    assert len(listing.items) == 1
    assert listing.items[0].id.endswith("-80117")
    assert "Trainee program" in listing.items[0].title
    assert listing.has_more is False


def test_get_series_chapters_and_pages(doujins_connector: DoujinsConnector):
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    series_id = "genshin-impact/frozen-spider-lily-arlecchino-trainee-program-80117"

    with patch.object(doujins_connector, "_fetch_html", return_value=html) as mock_fetch:
        series = doujins_connector.get_series(series_id)
        chapters = doujins_connector.get_chapters(series_id)
        pages = doujins_connector.get_chapter_pages(series_id)

    mock_fetch.assert_called()
    assert series is not None
    assert "Trainee program" in series.title
    assert series.artist == "frozen spider lily"
    assert "arlecchino" in {g.casefold() for g in series.genres}
    assert len(chapters) == 1
    assert chapters[0].page_count == 36
    assert len(pages) == 36
    assert pages[0].remote_url.startswith("https://static.doujins.com/n-")
    assert "&amp;" not in (pages[0].remote_url or "")
    assert doujins_connector.find_page(pages[0].id) == pages[0]


def test_parse_series_detail_and_pages_directly():
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    series_id = "genshin-impact/frozen-spider-lily-arlecchino-trainee-program-80117"
    series = parse_series_detail(html, series_id=series_id)
    pages = parse_gallery_pages(html, series_id=series_id)
    assert series is not None
    assert series.id == series_id
    assert len(pages) == 36


def test_parse_searchbox_ignores_non_gallery_suggestions():
    payload = {
        "success": 1,
        "suggestions": [
            {"name": "loli", "link": "/searches?words=loli", "itemCount": 0},
            {
                "name": "Gallery",
                "link": "/foo/bar-gallery-123",
                "itemCount": 0,
            },
        ],
    }
    items = parse_searchbox_payload(payload)
    assert len(items) == 1
    assert items[0].id == "foo/bar-gallery-123"
