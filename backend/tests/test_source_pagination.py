from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.asurascans.connector import AsuraScansConnector
from connectors.models import PaginatedSeriesList, Series
from connectors.mangadex.connector import MangaDexConnector

ASURA_FIXTURES = Path(__file__).parent / "fixtures" / "asurascans"
MANGA_FIXTURES = Path(__file__).parent / "fixtures" / "mangadex"


def _load_asura(name: str) -> dict:
    return json.loads((ASURA_FIXTURES / name).read_text(encoding="utf-8"))


def _load_manga(name: str) -> dict:
    return json.loads((MANGA_FIXTURES / name).read_text(encoding="utf-8"))


def test_paginated_series_list_has_more_uses_consumed_count() -> None:
    items = [Series(id=str(index), title=f"Series {index}") for index in range(13)]
    listing = PaginatedSeriesList(items=items, page=17, page_size=20, total=333)
    assert listing.has_more is False

    full_page = PaginatedSeriesList(
        items=[Series(id=str(index), title=f"Series {index}") for index in range(20)],
        page=16,
        page_size=20,
        total=333,
    )
    assert full_page.has_more is True


def test_asurascans_browse_page_2_returns_different_items() -> None:
    full = _load_asura("series_list.json")
    page1_payload = {
        "data": full["data"][:20],
        "meta": {"total": 333, "per_page": 20, "has_more": True},
    }
    page2_item = dict(full["data"][0])
    page2_item.update(
        {
            "id": 9999,
            "slug": "second-page-series",
            "title": "Second Page Series",
            "public_url": "/comics/second-page-series-abc123",
        }
    )
    page2_payload = {
        "data": [page2_item],
        "meta": {"total": 333, "per_page": 20, "has_more": True},
    }
    connector = AsuraScansConnector()

    def fake_get_json(path: str, *, params=None):
        assert path == "/api/series"
        offset = int((params or {}).get("offset", 0))
        return page1_payload if offset == 0 else page2_payload

    try:
        with patch.object(connector._http, "get_json", side_effect=fake_get_json):
            page1 = connector.get_series_list(1)
            page2 = connector.get_series_list(2)
    finally:
        connector._http.close()

    assert page1.has_more is True
    assert page2.has_more is True
    assert page1.items[0].id != page2.items[0].id
    assert len(page1.items) == 20
    assert len(page2.items) == 1


def test_asurascans_search_finds_titles_not_on_page_1() -> None:
    browse_payload = _load_asura("series_list.json")
    search_payload = _load_asura("series_search.json")
    connector = AsuraScansConnector()

    def fake_get_json(path: str, *, params=None):
        assert path == "/api/series"
        if params and params.get("search"):
            return search_payload
        return browse_payload

    try:
        with patch.object(connector._http, "get_json", side_effect=fake_get_json):
            browse = connector.get_series_list(1)
            search = connector.search_series("solo", 1)
    finally:
        connector._http.close()

    browse_ids = {item.id for item in browse.items}
    assert search.items
    assert any(item.id not in browse_ids for item in search.items)


def test_mangadex_browse_page_2_requests_offset() -> None:
    page1_payload = {**_load_manga("manga_list.json"), "total": 50}
    page2_payload = {
        **page1_payload,
        "data": [
            {
                "id": "page-2-series",
                "type": "manga",
                "attributes": {"title": {"en": "Second Page Title"}, "status": "ongoing"},
                "relationships": [],
            }
        ],
        "total": 50,
    }
    connector = MangaDexConnector()
    captured_offsets: list[int] = []

    def fake_get_json(path: str, *, params=None):
        assert path == "/manga"
        captured_offsets.append(int((params or {}).get("offset", 0)))
        page = int((params or {}).get("offset", 0)) // 24 + 1
        return page1_payload if page == 1 else page2_payload

    try:
        with patch.object(connector._http, "get_json", side_effect=fake_get_json):
            page1 = connector.get_series_list(1)
            page2 = connector.get_series_list(2)
    finally:
        connector._http.close()

    assert captured_offsets == [0, 24]
    assert page1.items[0].id != page2.items[0].id
    assert page1.has_more is True
