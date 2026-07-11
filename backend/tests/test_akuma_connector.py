from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.akuma.connector import AkumaConnector
from connectors.akuma.mappers import (
    build_gallery_pages,
    extract_media_base,
    extract_next_cursor,
    parse_chapters,
    parse_image_filenames,
    parse_series_detail,
    parse_series_list,
)
from connectors.http.ddg_client import is_ddos_guard_challenge
from connectors.registry import create_connector, list_installed_connectors

FIXTURES = Path(__file__).parent / "fixtures" / "akuma"
GALLERY_ID = "tnfns98p"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def akuma_connector() -> AkumaConnector:
    return AkumaConnector()


def test_registry_lists_akuma_as_mature():
    descriptors = {item.source_type: item for item in list_installed_connectors(include_mature=True)}
    assert "akuma" in descriptors
    assert descriptors["akuma"].mature is True
    assert create_connector("akuma").source_type == "akuma"


def test_ddos_guard_challenge_detection():
    assert is_ddos_guard_challenge("<title>DDoS-Guard</title><p>Checking your browser")
    assert not is_ddos_guard_challenge('<ul class="post-loop mb-3 minimal">')
    assert not is_ddos_guard_challenge('<div class="entry-content">')


def test_parse_series_list_from_fixture():
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    assert len(listing.items) == 60
    assert listing.has_more is True
    assert listing.items[0].id == "ffsrkvpa"
    assert listing.items[0].title == "COMIC ExE 72 [Digital]"


def test_browse_page_2_differs_from_page_1(akuma_connector: AkumaConnector):
    page1 = _load("browse_page1.html")
    page2 = _load("browse_page2.html")
    cursor = extract_next_cursor(page1)

    def fake_get_text(path: str, *, params=None):
        del params
        if cursor and cursor in path:
            return page2
        if path == "/":
            return page1
        raise AssertionError(f"Unexpected path: {path}")

    with patch.object(akuma_connector._http, "get_text", side_effect=fake_get_text):
        first = akuma_connector.get_series_list(1)
        second = akuma_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id
    assert second.items[0].id == "vol800ep"


def test_search_series_uses_query_param(akuma_connector: AkumaConnector):
    search_html = _load("search.html")

    def fake_get_text(path: str, *, params=None):
        del params
        assert path == "/?q=solo"
        return search_html

    with patch.object(akuma_connector._http, "get_text", side_effect=fake_get_text):
        listing = akuma_connector.search_series("solo", 1)

    assert len(listing.items) == 60


def test_get_series_detail(akuma_connector: AkumaConnector):
    detail_html = _load("gallery_detail.html")

    with patch.object(akuma_connector._http, "get_text", return_value=detail_html):
        series = akuma_connector.get_series(GALLERY_ID)

    assert series is not None
    assert series.id == GALLERY_ID
    assert series.chapter_count == 1
    assert "pages" in (series.latest_chapter or "")
    assert series.cover_url and "akuma.moe" in series.cover_url


def test_get_chapters_and_pages(akuma_connector: AkumaConnector):
    detail_html = _load("gallery_detail.html")
    reader_html = _load("reader_page1.html")
    image_list = _load("image_list.json")
    post_calls = {"count": 0}

    def fake_get_text(path: str, *, params=None):
        del params
        if path == f"/g/{GALLERY_ID}":
            return detail_html
        if path == f"/g/{GALLERY_ID}/1":
            return reader_html
        raise AssertionError(f"Unexpected get_text path: {path}")

    def fake_post_text(path: str, *, data=None, extra_headers=None):
        del data
        post_calls["count"] += 1
        assert path == f"/g/{GALLERY_ID}"
        assert extra_headers and extra_headers.get("X-CSRF-TOKEN")
        return image_list

    with (
        patch.object(akuma_connector._http, "get_text", side_effect=fake_get_text),
        patch.object(akuma_connector._http, "post_text", side_effect=fake_post_text),
    ):
        chapters = akuma_connector.get_chapters(GALLERY_ID)
        pages = akuma_connector.get_chapter_pages(GALLERY_ID)

    assert post_calls["count"] == 1
    assert len(chapters) == 1
    assert chapters[0].page_count == 38
    assert len(pages) == 38
    assert pages[0].number == 1
    assert pages[0].remote_url.startswith("https://s")
    assert pages[0].remote_url.endswith(".jpg")
    assert akuma_connector.find_page(pages[1].id) == pages[1]


def test_mapper_unit_helpers():
    detail = _load("gallery_detail.html")
    reader = _load("reader_page1.html")
    chapter = parse_chapters(detail, gallery_id=GALLERY_ID)
    assert len(chapter) == 1
    assert chapter[0].page_count == 38

    media_base = extract_media_base(reader)
    assert media_base and media_base.startswith("https://s2.akuma.moe/")

    filenames = parse_image_filenames(_load("image_list.json"))
    pages = build_gallery_pages(
        gallery_id=GALLERY_ID,
        media_base=media_base,
        filenames=filenames,
    )
    assert len(pages) == 38
    assert pages[-1].id == f"{GALLERY_ID}:38"

    series = parse_series_detail(detail, gallery_id=GALLERY_ID)
    assert series is not None
    assert series.title


def test_fetch_proxied_image_uses_ddg_client(akuma_connector: AkumaConnector):
    image_bytes = b"\x89PNG\r\n"

    with patch.object(
        akuma_connector._http,
        "get_bytes",
        return_value=("image/png", image_bytes),
    ) as mock_get_bytes:
        media_type, data = akuma_connector.fetch_proxied_image(
            "https://s2.akuma.moe/4045018/page.png"
        )

    assert media_type == "image/png"
    assert data == image_bytes
    mock_get_bytes.assert_called_once()
