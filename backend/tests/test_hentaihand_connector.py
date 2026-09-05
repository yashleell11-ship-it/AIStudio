"""Offline tests for the HentaiHand connector.

Fixtures under ``tests/fixtures/hentaihand/`` were captured live 2026-09-05
FROM THE VPS (inside ``manhwamaniacs-backend``, so through production's exact
egress IP and TLS stack). The connector is exercised entirely against those
captures by patching ``self._http.get_json``; no test touches the network.

Every parse assertion here was watched to FAIL against a deliberately broken
selector before being kept -- a test that still passes on broken parsing
proves nothing.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest

from connectors.base import SourceConnector
from connectors.hentaihand.connector import HentaiHandConnector
from connectors.hentaihand.mappers import (
    COMICS_PATH,
    PAGE_SIZE,
    browse_params,
    comic_to_chapter,
    comic_to_series,
    genre_params,
    images_path,
    make_page_id,
    normalize_series_key,
    page_id_series_key,
    parse_images,
    parse_series_list,
    search_params,
    series_path,
)
from connectors.http.client import ConnectorHttpError
from tests.connector_validation import ConnectorContractCase, validate_connector_contract

FIXTURES = Path(__file__).parent / "fixtures" / "hentaihand"

SERIES_KEY = "x-817b34d20c"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture()
def connector() -> HentaiHandConnector:
    return HentaiHandConnector()


@contextmanager
def _mock_hentaihand(connector: SourceConnector) -> Iterator[None]:
    browse_page1 = _load("browse_page1.json")
    browse_page2 = _load("browse_page2.json")
    browse_popularity = _load("browse_popularity.json")
    search_naruto = _load("search_naruto.json")
    genre_full_color = _load("genre_full_color.json")
    series_detail = _load("series_detail.json")
    chapter_images = _load("chapter_images.json")

    def fake_get_json(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path == COMICS_PATH:
            params = params or {}
            if params.get("q"):
                return search_naruto
            if params.get("tags[]"):
                return genre_full_color
            if params.get("sort") == "popularity":
                return browse_popularity
            if int(params.get("page", 1)) == 2:
                return browse_page2
            return browse_page1
        if path == series_path(SERIES_KEY):
            return series_detail
        if path == images_path(SERIES_KEY):
            return chapter_images
        raise AssertionError(f"Unexpected path: {path} params={params}")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        yield


# --- identity ---------------------------------------------------------------


def test_series_key_round_trips_through_every_inbound_shape():
    """House law: keys are the site's own slugs and pass through raw."""
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(f"/{SERIES_KEY}/") == SERIES_KEY
    assert normalize_series_key(f"https://hentaihand.com/comic/{SERIES_KEY}") == SERIES_KEY
    assert normalize_series_key(f"https://hentaihand.com/api/comics/{SERIES_KEY}") == SERIES_KEY
    assert series_path(SERIES_KEY) == f"/api/comics/{SERIES_KEY}"
    assert images_path(SERIES_KEY) == f"/api/comics/{SERIES_KEY}/images"


def test_page_id_round_trips():
    page_id = make_page_id(SERIES_KEY, 7)
    assert page_id == f"{SERIES_KEY}:7"
    assert page_id_series_key(page_id) == SERIES_KEY
    assert page_id_series_key("no-separator-here") is None


# --- browse / search params -------------------------------------------------


def test_default_browse_pins_uploaded_at_not_the_apis_own_order():
    """No ``sort`` means id-ascending upstream, i.e. 2016 uploads first."""
    assert browse_params(None, 1) == {"page": 1, "sort": "uploaded_at"}
    assert browse_params("popularity", 3) == {"page": 3, "sort": "popularity"}
    assert browse_params("not-a-mode", 1)["sort"] == "uploaded_at"
    assert search_params("naruto", 2) == {"page": 2, "sort": "uploaded_at", "q": "naruto"}


def test_genre_params_send_the_numeric_tag_id_and_reject_unknown_slugs():
    """``tags[]=<slug>`` answers total 0 upstream, so ids are mandatory."""
    assert genre_params("full-color", 1) == {"page": 1, "sort": "uploaded_at", "tags[]": 32}
    assert genre_params("not-a-tag", 1) is None


# --- catalog parsing --------------------------------------------------------


def test_parse_browse_page_reads_the_whole_paginator_envelope():
    listing = parse_series_list(_load("browse_page1.json"), page=1)
    assert len(listing.items) == PAGE_SIZE
    assert listing.page_size == PAGE_SIZE
    # ``total``/``last_page`` are published, so has_more is exact rather than
    # the "did a card come back?" guess an HTML source forces.
    assert listing.total == 655080
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "iwao-1-2-3-4-5-6-7-8-9-10-11-12"
    assert first.cover_url == "https://cdn.hentaihand.com/nhentai/storage/comics/thumbs/705460.webp"
    assert first.canonical_path == f"/comic/{first.id}"
    # A gallery is a finished work; category and language ride along as chips
    # the way the registered nhentai source surfaces them.
    assert first.status == "completed"
    assert first.latest_chapter == "10 pages"
    assert first.genres[:2] == ("Doujinshi", "Japanese")
    assert "Sole Female" in first.genres


def test_page_two_reports_its_own_page_number_from_the_envelope():
    listing = parse_series_list(_load("browse_page2.json"), page=2)
    assert listing.page == 2
    assert listing.items[0].id != parse_series_list(_load("browse_page1.json"), page=1).items[0].id


def test_popularity_is_a_short_trending_window_not_the_whole_catalog():
    """``sort=popularity`` really does change the query, not just the order."""
    listing = parse_series_list(_load("browse_popularity.json"), page=1)
    assert listing.total == 740
    assert listing.items[0].id != parse_series_list(_load("browse_page1.json"), page=1).items[0].id


def test_search_results_actually_match_the_query():
    listing = parse_series_list(_load("search_naruto.json"), page=1)
    assert listing.total == 2253
    assert any("naruto" in item.title.casefold() for item in listing.items)


def test_listing_with_no_data_key_is_an_empty_page_not_a_crash():
    listing = parse_series_list({"current_page": 1}, page=1)
    assert listing.items == []
    assert listing.has_more is False


# --- detail / reader --------------------------------------------------------


def test_detail_fills_in_the_fields_a_listing_card_omits():
    payload = _load("series_detail.json")
    series = comic_to_series(payload)
    assert series is not None
    assert series.id == SERIES_KEY
    assert "寝取られ" in series.title
    assert series.artist == "Netorare No Tami"
    # 14 tags plus the category, language and parody the listing card omits.
    assert len(series.genres) == 17
    assert "Original" in series.genres


def test_a_gallery_is_exactly_one_chapter():
    """``chapters_count`` was 0 on every comic sampled; one chapter, not none."""
    chapter = comic_to_chapter(_load("series_detail.json"))
    assert chapter is not None
    assert chapter.id == SERIES_KEY
    assert chapter.series_id == SERIES_KEY
    assert chapter.number == 1.0
    assert chapter.page_count == 294
    assert chapter.release_date == "2026-09-05"


def test_pages_are_numbered_from_one_and_carry_cdn_urls():
    pages = parse_images(_load("chapter_images.json"), SERIES_KEY)
    assert len(pages) == 295
    assert pages[0].id == f"{SERIES_KEY}:1"
    assert pages[0].number == 1
    assert pages[0].remote_url == "https://cdn.hentaihand.com/nhentai/storage/images/705459/1.webp"
    assert [page.number for page in pages] == list(range(1, len(pages) + 1))


def test_pages_are_ordered_by_the_apis_page_field_not_response_order():
    shuffled = {
        "images": [
            {"page": 3, "source_url": "https://cdn.hentaihand.com/a/3.jpg"},
            {"page": 1, "source_url": "https://cdn.hentaihand.com/a/1.jpg"},
            {"page": 2, "source_url": "https://cdn.hentaihand.com/a/2.jpg"},
        ]
    }
    urls = [page.remote_url for page in parse_images(shuffled, SERIES_KEY)]
    assert urls == [
        "https://cdn.hentaihand.com/a/1.jpg",
        "https://cdn.hentaihand.com/a/2.jpg",
        "https://cdn.hentaihand.com/a/3.jpg",
    ]


# --- connector wiring -------------------------------------------------------


def test_image_host_allowlist_covers_the_cdn_subdomain(connector: HentaiHandConnector):
    from services.outbound_security import host_matches_allowlist

    assert host_matches_allowlist("cdn.hentaihand.com", connector.allowed_image_hosts)
    assert not host_matches_allowlist("nothentaihand.com", connector.allowed_image_hosts)


def test_source_is_registered_as_mature(connector: HentaiHandConnector):
    assert connector.is_mature is True


def test_detail_and_chapters_share_one_upstream_fetch(connector: HentaiHandConnector):
    with _mock_hentaihand(connector) as _mock:
        with patch.object(
            connector._http, "get_json", wraps=connector._http.get_json
        ) as spy:
            connector.get_series(SERIES_KEY)
            connector.get_chapters(SERIES_KEY)
        assert spy.call_count == 1


def test_unknown_genre_answers_empty_without_a_request(connector: HentaiHandConnector):
    with patch.object(connector._http, "get_json", side_effect=AssertionError("no request")):
        listing = connector.browse_by_genre("not-a-tag", 1)
    assert listing.items == []
    assert listing.has_more is False


def test_missing_series_is_none_rather_than_an_error(connector: HentaiHandConnector):
    """An unknown slug 404s with an HTML body, which get_json cannot parse."""
    not_found = ConnectorHttpError(
        "Client error '404 Not Found' for url 'https://hentaihand.com/api/comics/nope'"
    )
    with patch.object(connector._http, "get_json", side_effect=not_found):
        assert connector.get_series("definitely-not-a-real-slug-xyz") is None
        assert connector.get_chapters("definitely-not-a-real-slug-xyz") == []
        assert connector.get_chapter_pages("definitely-not-a-real-slug-xyz") == []


def test_connector_contract():
    validate_connector_contract(
        ConnectorContractCase(
            source_type="hentaihand",
            fixtures_dir=FIXTURES,
            search_query="naruto",
            series_id=SERIES_KEY,
            reader_chapter_id=SERIES_KEY,
            expected_title_substring="寝取られ",
            expected_image_host_substring="cdn.hentaihand.com",
            mock=_mock_hentaihand,
        )
    )
