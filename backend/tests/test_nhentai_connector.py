from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.nhentai.connector import NHentaiConnector
from connectors.registry import create_connector, list_installed_connectors


FIXTURES = Path(__file__).parent / "fixtures" / "nhentai"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def nhentai_connector() -> NHentaiConnector:
    return NHentaiConnector()


def test_registry_lists_nhentai_as_mature():
    descriptors = {item.source_type: item for item in list_installed_connectors(include_mature=True)}
    assert "nhentai" in descriptors
    assert descriptors["nhentai"].mature is True


def test_list_series_uses_nhentai_api(nhentai_connector: NHentaiConnector):
    config_payload = _load("config.json")
    listing_payload = _load("galleries_list.json")

    def fake_json(path: str, *, params=None):
        if path == "/api/v2/config":
            return config_payload
        raise AssertionError(f"Unexpected get_json path: {path}")

    def fake_json_value(path: str, *, params=None):
        if path == "/api/v2/galleries":
            return listing_payload
        raise AssertionError(f"Unexpected get_json_value path: {path}")

    with (
        patch.object(nhentai_connector._http, "get_json", side_effect=fake_json),
        patch.object(nhentai_connector._http, "get_json_value", side_effect=fake_json_value),
    ):
        listing = nhentai_connector.get_series_list(1)

    assert listing.total == 2
    assert len(listing.items) == 2
    assert listing.items[0].title.endswith("[English]")
    assert listing.items[0].cover_url == "https://t3.nhentai.net/galleries/4042966/thumb.webp"


def test_search_series_uses_query_param(nhentai_connector: NHentaiConnector):
    config_payload = _load("config.json")
    search_payload = _load("search.json")

    def fake_json(path: str, *, params=None):
        if path == "/api/v2/config":
            return config_payload
        if path == "/api/v2/search":
            assert params == {"query": "sample", "page": 1}
            return search_payload
        raise AssertionError(f"Unexpected get_json path: {path}")

    with patch.object(nhentai_connector._http, "get_json", side_effect=fake_json):
        listing = nhentai_connector.search_series("sample", 1)

    assert listing.total == 1
    assert listing.items[0].id == "663284"


def test_get_chapters_and_pages(nhentai_connector: NHentaiConnector):
    config_payload = _load("config.json")
    gallery_payload = _load("gallery_detail.json")
    gallery_id = "663284"
    gallery_calls = {"count": 0}

    def fake_json(path: str, *, params=None):
        if path == "/api/v2/config":
            return config_payload
        if path == f"/api/v2/galleries/{gallery_id}":
            gallery_calls["count"] += 1
            return gallery_payload
        raise AssertionError(f"Unexpected get_json path: {path}")

    with patch.object(nhentai_connector._http, "get_json", side_effect=fake_json):
        series = nhentai_connector.get_series(gallery_id)
        chapters = nhentai_connector.get_chapters(gallery_id)
        pages = nhentai_connector.get_chapter_pages(gallery_id)

    assert gallery_calls["count"] == 1
    assert series is not None
    assert series.author == "Ciel"
    assert "doujinshi" in series.genres
    assert len(chapters) == 1
    assert chapters[0].page_count == 2
    assert len(pages) == 2
    assert pages[0].remote_url == "https://i3.nhentai.net/galleries/4042966/1.webp"
    assert nhentai_connector.find_page(pages[0].id) == pages[0]


def test_create_nhentai_connector():
    connector = create_connector("nhentai")
    assert connector.source_type == "nhentai"
    assert connector.is_mature is True


def test_english_browse_mode_uses_language_filter(nhentai_connector: NHentaiConnector):
    config_payload = _load("config.json")
    search_payload = _load("search.json")

    def fake_json(path: str, *, params=None):
        if path == "/api/v2/config":
            return config_payload
        if path == "/api/v2/search":
            assert params == {"query": "language:english", "page": 1}
            return search_payload
        raise AssertionError(f"Unexpected get_json path: {path}")

    with patch.object(nhentai_connector._http, "get_json", side_effect=fake_json):
        listing = nhentai_connector.get_series_list(1, sort="english")

    assert listing.total == 1
    assert listing.items[0].id == "663284"


def test_english_search_combines_user_query(nhentai_connector: NHentaiConnector):
    config_payload = _load("config.json")
    search_payload = _load("search.json")

    def fake_json(path: str, *, params=None):
        if path == "/api/v2/config":
            return config_payload
        if path == "/api/v2/search":
            assert params == {"query": "language:english elf", "page": 1}
            return search_payload
        raise AssertionError(f"Unexpected get_json path: {path}")

    with patch.object(nhentai_connector._http, "get_json", side_effect=fake_json):
        listing = nhentai_connector.search_series("elf", 1, sort="english")

    assert listing.total == 1
