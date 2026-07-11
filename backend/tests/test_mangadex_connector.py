from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.mangadex.connector import MangaDexConnector
from connectors.registry import create_connector, list_installed_connectors


FIXTURES = Path(__file__).parent / "fixtures" / "mangadex"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def mangadex_connector() -> MangaDexConnector:
    return MangaDexConnector()


def test_registry_lists_mangadex():
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    assert "mangadex" in browsable
    assert "asurascans" in browsable
    assert "demo" not in browsable


def test_list_series_uses_mangadex_api(mangadex_connector: MangaDexConnector):
    listing_payload = _load("manga_list.json")

    with patch.object(mangadex_connector._http, "get_json", return_value=listing_payload):
        listing = mangadex_connector.get_series_list(1)

    assert listing.total == 2
    assert len(listing.items) == 2
    assert listing.items[0].title == "Solo Leveling"
    assert listing.items[0].cover_url == (
        "https://uploads.mangadex.org/covers/32dce569-8fcc-46b6-853c-f956e16ee0bc/cover.jpg"
    )


def test_embedded_cover_art_attributes_without_included(mangadex_connector: MangaDexConnector):
    """MangaDex may embed cover_art attributes on relationships with empty included."""
    payload = {
        "result": "ok",
        "response": "collection",
        "data": [
            {
                "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "type": "manga",
                "attributes": {"title": {"en": "Embedded Cover Manga"}, "status": "ongoing"},
                "relationships": [
                    {
                        "id": "cover-1",
                        "type": "cover_art",
                        "attributes": {"fileName": "embedded.jpg"},
                    }
                ],
            }
        ],
        "limit": 1,
        "offset": 0,
        "total": 1,
        "included": [],
    }
    with patch.object(mangadex_connector._http, "get_json", return_value=payload):
        listing = mangadex_connector.get_series_list(1)
    assert listing.items[0].cover_url == (
        "https://uploads.mangadex.org/covers/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/embedded.jpg"
    )


def test_search_series_uses_title_param(mangadex_connector: MangaDexConnector):
    listing_payload = _load("manga_search.json")

    with patch.object(mangadex_connector._http, "get_json", return_value=listing_payload) as mock_get:
        listing = mangadex_connector.search_series("Solo Leveling", 1)

    assert mock_get.call_args.kwargs["params"]["title"] == "Solo Leveling"
    assert listing.total == 1
    assert listing.items[0].title == "Solo Leveling"


def test_get_chapters_and_pages(mangadex_connector: MangaDexConnector):
    feed_payload = _load("chapter_feed.json")
    at_home_payload = _load("at_home.json")
    series_id = "32dce569-8fcc-46b6-853c-f956e16ee0bc"
    chapter_id = "00000000-0000-0000-0000-000000000001"

    def fake_get_json(path: str, *, params=None):
        if path.endswith("/feed"):
            return feed_payload
        if path.startswith("/at-home/server/"):
            return at_home_payload
        raise AssertionError(f"Unexpected path: {path}")

    with patch.object(mangadex_connector._http, "get_json", side_effect=fake_get_json):
        chapters = mangadex_connector.get_chapters(series_id)
        pages = mangadex_connector.get_chapter_pages(chapter_id)

    assert len(chapters) == 1
    assert chapters[0].id == chapter_id
    assert len(pages) == 2
    assert pages[0].remote_url is not None
    assert mangadex_connector.find_page(pages[0].id) == pages[0]


def test_create_mangadex_connector():
    connector = create_connector("mangadex")
    assert connector.source_type == "mangadex"
