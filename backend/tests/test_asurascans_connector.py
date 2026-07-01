from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.asurascans.connector import AsuraScansConnector
from connectors.registry import create_connector, list_installed_connectors


FIXTURES = Path(__file__).parent / "fixtures" / "asurascans"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def asurascans_connector() -> AsuraScansConnector:
    return AsuraScansConnector()


def test_registry_lists_asurascans():
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    assert "asurascans" in browsable
    assert "mangadex" in browsable


def test_list_series_uses_asurascans_api(asurascans_connector: AsuraScansConnector):
    listing_payload = _load("series_list.json")

    with patch.object(asurascans_connector._http, "get_json", return_value=listing_payload):
        listing = asurascans_connector.get_series_list(1)

    assert listing.total == 333
    assert len(listing.items) == 20
    assert listing.items[0].id == "return-of-the-mount-hua-sect-30e93729"
    assert listing.items[0].title == "Return of the Mount Hua Sect"


def test_search_series_uses_search_param(asurascans_connector: AsuraScansConnector):
    listing_payload = _load("series_search.json")

    with patch.object(asurascans_connector._http, "get_json", return_value=listing_payload) as mock_get:
        listing = asurascans_connector.search_series("solo", 1)

    params = mock_get.call_args.kwargs["params"]
    assert params["search"] == "solo"
    assert params["offset"] == 0
    assert params["limit"] == 20
    assert listing.total >= 1
    assert any("solo" in item.title.casefold() for item in listing.items)


def test_list_series_page_2_uses_offset(asurascans_connector: AsuraScansConnector):
    listing_payload = _load("series_list.json")
    captured: list[dict] = []

    def fake_get_json(path: str, *, params=None):
        captured.append(dict(params or {}))
        return listing_payload

    with patch.object(asurascans_connector._http, "get_json", side_effect=fake_get_json):
        asurascans_connector.get_series_list(1)
        asurascans_connector.get_series_list(2, sort="popular")

    assert captured[0]["offset"] == 0
    assert captured[1]["offset"] == 20
    assert captured[1]["sort"] == "popular"


def test_get_series_chapters_and_pages(asurascans_connector: AsuraScansConnector):
    listing_payload = _load("series_list.json")
    detail_payload = _load("series_detail.json")
    chapter_payload = _load("chapter_list.json")
    pages_payload = _load("chapter_pages.json")
    series_id = "return-of-the-mount-hua-sect-30e93729"
    chapter_id = "breakers-30e93729:91"

    def fake_get_json(path: str, *, params=None):
        if path == "/api/series":
            return listing_payload
        if path == f"/api/series/{series_id}":
            return detail_payload
        if path == f"/api/series/{series_id}/chapters":
            return chapter_payload
        if path == "/api/series/breakers-30e93729/chapters/91":
            return pages_payload
        raise AssertionError(f"Unexpected path: {path}")

    with patch.object(asurascans_connector._http, "get_json", side_effect=fake_get_json):
        listing = asurascans_connector.get_series_list(1)
        series = asurascans_connector.get_series(listing.items[0].id)
        chapters = asurascans_connector.get_chapters(series_id)
        pages = asurascans_connector.get_chapter_pages(chapter_id)

    assert listing.items[0].id == series_id
    assert series is not None
    assert series.id == series_id
    assert series.title == "Return of the Mount Hua Sect"
    assert len(chapters) == 175
    assert chapters[-1].id == f"{series_id}:169"
    assert len(pages) == 14
    assert pages[0].remote_url is not None
    assert asurascans_connector.find_page(pages[0].id) == pages[0]


@pytest.mark.integration
def test_asurascans_sequential_live_requests():
    connector = AsuraScansConnector()
    try:
        listing = connector.get_series_list(1)
        assert listing.items
        for series_id in [item.id for item in listing.items[:5]]:
            series = connector.get_series(series_id)
            chapters = connector.get_chapters(series_id)
            assert series is not None, series_id
            assert series.id == series_id
            assert chapters, series_id
    finally:
        connector._http.close()


def test_create_asurascans_connector():
    connector = create_connector("asurascans")
    assert connector.source_type == "asurascans"
