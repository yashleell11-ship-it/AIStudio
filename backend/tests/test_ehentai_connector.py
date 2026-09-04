from __future__ import annotations

import threading
import time

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.ehentai.connector import EHentaiConnector
from connectors.ehentai.mappers import (
    is_viewer_url,
    listing_path,
    parse_reader_image_url,
    parse_series_list,
)


FIXTURES = Path(__file__).parent / "fixtures" / "ehentai"


@pytest.fixture
def ehentai_connector() -> EHentaiConnector:
    return EHentaiConnector()


def test_list_series_from_home_fixture(ehentai_connector: EHentaiConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(ehentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = ehentai_connector.get_series_list(1)

    mock_fetch.assert_called_once_with("/")
    assert len(listing.items) == 25
    assert listing.items[0].id == "4044868/c3ce5e14a2"
    assert "水越沙耶香" in listing.items[0].title or "G-taste" in listing.items[0].title
    assert listing.items[0].cover_url is not None
    assert listing.items[0].cover_url.startswith("https://ehgt.org/")
    assert listing.has_more is True


def test_search_series_uses_search_path(ehentai_connector: EHentaiConnector):
    html = (FIXTURES / "search_listing.html").read_text(encoding="utf-8")

    with patch.object(ehentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        listing = ehentai_connector.search_series("elf", 1)

    mock_fetch.assert_called_once_with("/?f_search=elf")
    assert len(listing.items) >= 1
    assert "/" in listing.items[0].id


def test_english_browse_mode_uses_language_query(ehentai_connector: EHentaiConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(ehentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        ehentai_connector.get_series_list(1, sort="english")

    mock_fetch.assert_called_once_with("/?f_search=language%3Aenglish")


def test_popular_browse_mode_uses_popular_path(ehentai_connector: EHentaiConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(ehentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        ehentai_connector.get_series_list(1, sort="popular")

    mock_fetch.assert_called_once_with("/popular")


def test_page_two_uses_cached_next_cursor(ehentai_connector: EHentaiConnector):
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")

    with patch.object(ehentai_connector, "_fetch_html", return_value=html) as mock_fetch:
        ehentai_connector.get_series_list(1)
        ehentai_connector.get_series_list(2)

    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[1].args[0] == "/?next=4044842"


def test_get_chapters_and_pages(ehentai_connector: EHentaiConnector):
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    gallery_id = "2824036/518ad4908e"

    with patch.object(ehentai_connector, "_fetch_html", return_value=html):
        series = ehentai_connector.get_series(gallery_id)
        chapters = ehentai_connector.get_chapters(gallery_id)
        pages = ehentai_connector.get_chapter_pages(gallery_id)

    assert series is not None
    assert "Half-succubus" in series.title
    assert "Artist CG" in series.genres
    assert "english" in {g.casefold() for g in series.genres} or any(
        "christmas" in g.casefold() for g in series.genres
    )
    assert series.cover_url and series.cover_url.startswith("https://ehgt.org/")
    assert len(chapters) == 1
    assert chapters[0].page_count == 4
    assert len(pages) == 4
    assert pages[0].remote_url == "https://e-hentai.org/s/1c9b46c429/2824036-1"
    assert is_viewer_url(pages[0].remote_url)
    assert ehentai_connector.find_page(pages[0].id) == pages[0]


def test_fetch_proxied_image_resolves_viewer_page(ehentai_connector: EHentaiConnector):
    reader_html = (FIXTURES / "reader_page.html").read_text(encoding="utf-8")
    image_url = parse_reader_image_url(reader_html)
    assert image_url is not None

    viewer = "https://e-hentai.org/s/1c9b46c429/2824036-1"
    with (
        patch.object(ehentai_connector._http, "get_text", return_value=reader_html) as mock_html,
        patch.object(
            ehentai_connector._http,
            "get_bytes",
            return_value=("image/webp", b"webp-bytes"),
        ) as mock_bytes,
    ):
        media_type, body = ehentai_connector.fetch_proxied_image(viewer)

    mock_html.assert_called_once_with(viewer)
    mock_bytes.assert_called_once()
    assert mock_bytes.call_args.args[0] == image_url
    assert media_type == "image/webp"
    assert body == b"webp-bytes"


def test_allowed_image_hosts(ehentai_connector: EHentaiConnector):
    hosts = ehentai_connector.allowed_image_hosts
    assert "e-hentai.org" in hosts
    assert "ehgt.org" in hosts
    assert "hath.network" in hosts


def test_listing_path_helpers():
    assert listing_path() == "/"
    assert listing_path(sort="popular") == "/popular"
    assert listing_path(query="elf", cursor="123") == "/?f_search=elf&next=123"


def test_parse_series_list_has_more_from_next_link():
    html = (FIXTURES / "home_listing.html").read_text(encoding="utf-8")
    listing = parse_series_list(html, page=1)
    assert listing.has_more is True
    assert listing.items[0].id.count("/") == 1


def test_opening_a_gallery_fetches_its_landing_page_once(
    ehentai_connector: EHentaiConnector,
):
    """get_series, get_chapters and get_chapter_pages read the same document.

    The reader calls all three back to back when a gallery is opened, and each
    used to fetch ``/g/<id>/`` for itself -- three identical requests to a site
    that rate-limits hard.
    """
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    gallery_id = "2824036/518ad4908e"

    with patch.object(
        ehentai_connector, "_fetch_html", return_value=html
    ) as mock_fetch:
        ehentai_connector.get_series(gallery_id)
        ehentai_connector.get_chapters(gallery_id)
        ehentai_connector.get_chapter_pages(gallery_id)

    landing = [
        call for call in mock_fetch.call_args_list
        if "?p=" not in call.args[0]
    ]
    assert len(landing) == 1, mock_fetch.call_args_list


def test_thumbnail_pages_are_fetched_in_parallel_batches(
    ehentai_connector: EHentaiConnector,
):
    """A big gallery must not cost one serial round trip per 20 images.

    Measured from the VPS, a 460-image gallery spent 23.1s in the pages stage
    walking its thumbnail pages one at a time -- the slowest single stage in
    the connector audit.
    """
    html = (FIXTURES / "gallery_detail.html").read_text(encoding="utf-8")
    gallery_id = "2824036/518ad4908e"
    requested: list[str] = []
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def fake_fetch(path: str) -> str:
        nonlocal in_flight, max_in_flight
        with lock:
            requested.append(path)
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return html

    # 100 images over 20-per-thumbnail-page => 5 thumbnail pages (0..4).
    with patch.object(ehentai_connector, "_fetch_html", side_effect=fake_fetch):
        with patch(
            "connectors.ehentai.connector.parse_page_count", return_value=100
        ):
            with patch(
                "connectors.ehentai.connector.parse_page_tokens",
                side_effect=lambda doc, gid: {str(len(requested)): "tok"},
            ):
                ehentai_connector.get_chapter_pages(gallery_id)

    thumb_paths = [p for p in requested if "?p=" in p]
    assert sorted(thumb_paths) == sorted(
        [f"/g/{gallery_id}/?p={n}" for n in range(1, 5)]
    ), requested
    # Serial would peak at one concurrent request; batching overlaps them.
    assert max_in_flight > 1
