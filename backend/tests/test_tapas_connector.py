from __future__ import annotations

from unittest.mock import patch

import pytest

from connectors.tapas.connector import TapasConnector
from connectors.tapas.mappers import (
    episode_html_to_pages,
    episode_to_chapter,
    landing_item_to_series,
    make_chapter_id,
    parse_chapter_id,
    parse_search_html,
)


def test_landing_item_to_series():
    item = {
        "seriesId": 202473,
        "title": "Solo Leveling",
        "description": "A hunter story",
        "authorList": ["Chugong"],
        "mainGenre": {"key": "AF", "value": "Action Fantasy"},
        "assetProperty": {
            "thumbnailImage": {"path": "https://story-a.tapas.io/prod/story/thumb.jpg"},
        },
    }
    series = landing_item_to_series(item, slug="solo-leveling-comic")
    assert series is not None
    assert series.id == "solo-leveling-comic"
    assert series.title == "Solo Leveling"
    assert series.author == "Chugong"


def test_episode_to_chapter_and_pages():
    chapter = episode_to_chapter(
        {"id": 2099900, "title": "Episode 1", "scene": 1, "publish_date": "2021-04-06T00:00:00Z"},
        series_slug="solo-leveling-comic",
    )
    assert chapter is not None
    assert chapter.id == "solo-leveling-comic:2099900"
    assert parse_chapter_id(chapter.id) == ("solo-leveling-comic", "2099900")

    latest = episode_to_chapter(
        {"id": 999, "title": "Episode 104", "scene": 0},
        series_slug="262684",
    )
    assert latest is not None
    assert latest.number == 104.0

    html = (
        '<img class="content__img js-lazy" '
        'data-src="https://us-a.tapas.io/pc/5d/page-1.jpg?token=abc" />'
        '<img class="content__img js-lazy" '
        'data-src="https://us-a.tapas.io/pc/5d/page-2.jpg?token=def" />'
    )
    pages = episode_html_to_pages(make_chapter_id("solo-leveling-comic", 2099900), html)
    assert len(pages) == 2
    assert pages[0].number == 1
    assert "tapas.io" in (pages[0].remote_url or "")


def test_parse_search_html_strips_highlight_markup():
    html = (
        '<a data-series-id="202473" href="/series/solo-leveling-comic" '
        'data-series-title="#_h_i_g_h_L_i_g_h_t_#Solo#/_h_i_g_h_L_i_g_h_t_# Leveling">'
        "</a>"
    )
    listing = parse_search_html(html, page=1)
    assert listing.items
    assert listing.items[0].id == "solo-leveling-comic"
    assert listing.items[0].title == "Solo Leveling"


@pytest.fixture
def tapas_connector() -> TapasConnector:
    return TapasConnector()


def test_tapas_registry_metadata(tapas_connector: TapasConnector):
    assert tapas_connector.source_type == "tapas"
    assert tapas_connector.display_name == "Tapas"
    assert "us-a.tapas.io" in tapas_connector.allowed_image_hosts


def test_tapas_browse_with_mock(tapas_connector: TapasConnector):
    payload = {
        "data": {
            "items": [
                {
                    "seriesId": 331138,
                    "title": "In Bed With the Male Lead",
                    "description": "Sample",
                    "authorList": ["Author"],
                    "mainGenre": {"key": "BL", "value": "BL"},
                    "assetProperty": {"thumbnailImage": {"path": "https://story-a.tapas.io/thumb.jpg"}},
                }
            ]
        }
    }

    with patch.object(tapas_connector._story_api, "get_json", return_value=payload):
        listing = tapas_connector.get_series_list(1)
    assert len(listing.items) == 1
    assert listing.items[0].id == "331138"
