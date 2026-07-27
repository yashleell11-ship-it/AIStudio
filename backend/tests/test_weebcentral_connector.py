"""Offline tests for the Weeb Central connector.

Fixtures under ``tests/fixtures/weebcentral/`` were captured live from
weebcentral.com's HTMX partials. The connector is exercised entirely against
those fixtures by patching ``self._http.get_text`` -- no network access.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.weebcentral.connector import WeebCentralConnector
from connectors.weebcentral.mappers import (
    make_page_id,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_data_params,
)
from services.outbound_security import host_matches_allowlist

FIXTURES = Path(__file__).parent / "fixtures" / "weebcentral"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def weebcentral_connector() -> WeebCentralConnector:
    return WeebCentralConnector()


# --- Parsing ----------------------------------------------------------------


def test_parse_series_list_from_fixture():
    listing = parse_series_list(_load("browse_search_data.html"), page=1)
    assert len(listing.items) >= 10
    assert listing.has_more is True
    assert listing.items[0].id
    assert listing.items[0].title
    assert listing.items[0].cover_url and listing.items[0].cover_url.startswith("https://")


def test_search_results_parse_target_title():
    listing = parse_search_results(_load("search_solo.html"), page=1, query="solo leveling")
    assert listing.items
    assert any("solo leveling" in item.title.casefold() for item in listing.items)


def test_parse_chapters_ascending_and_scoped():
    chapters = parse_chapters(_load("full_chapter_list.html"), "01J76XYCPSY3C4BNPBRY8JMCBE")
    assert len(chapters) >= 5
    assert all(c.series_id == "01J76XYCPSY3C4BNPBRY8JMCBE" for c in chapters)
    assert all(c.release_date for c in chapters)
    numbers = [c.number for c in chapters if c.number is not None]
    # Weeb Central lists newest-first; the connector must present oldest-first.
    assert numbers == sorted(numbers)


def test_parse_chapter_pages_real_images_with_dimensions():
    pages = parse_chapter_pages(_load("chapter_images.html"), "01J76XZ666GREP4DQDKEP1YDZG")
    assert len(pages) >= 1
    assert all(p.remote_url and p.remote_url.startswith("https://") for p in pages)
    assert all("broken_image" not in (p.remote_url or "") for p in pages)
    # Page numbers are contiguous starting at 1.
    assert [p.number for p in pages] == list(range(1, len(pages) + 1))
    assert pages[0].width and pages[0].height


def test_parse_series_detail_metadata():
    series = parse_series_detail(_load("series_detail.html"), "01J76XYCPSY3C4BNPBRY8JMCBE")
    assert series is not None
    assert series.title == "Solo Leveling"
    assert series.status == "Complete"
    assert series.author and "GEE So-Lyung" in series.author
    assert "Action" in series.genres
    assert series.description and "hunter" in series.description.casefold()
    assert series.cover_url and "01J76XYCPSY3C4BNPBRY8JMCBE" in series.cover_url


# --- Request shaping --------------------------------------------------------


def test_browse_uses_search_data_with_limit_offset(weebcentral_connector: WeebCentralConnector):
    html = _load("browse_search_data.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(weebcentral_connector._http, "get_text", side_effect=fake_get_text):
        weebcentral_connector.get_series_list(1)
        weebcentral_connector.get_series_list(3, sort="popular")

    assert captured[0][0] == "/search/data"
    assert captured[0][1]["text"] == ""
    assert captured[0][1]["sort"] == "Latest Updates"
    assert captured[0][1]["offset"] == 0
    assert captured[0][1]["adult"] == "False"  # non-mature connector
    assert captured[1][1]["sort"] == "Popularity"
    assert captured[1][1]["offset"] == 64  # (page 3 - 1) * page_size(32)


def test_each_browse_mode_requests_a_distinct_sort(weebcentral_connector: WeebCentralConnector):
    html = _load("browse_search_data.html")
    captured: list[dict | None] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return html

    with patch.object(weebcentral_connector._http, "get_text", side_effect=fake_get_text):
        for mode in ("default", "popular", "added", "alphabetical"):
            weebcentral_connector.get_series_list(1, sort=mode)

    sorts = [params["sort"] for params in captured]
    assert sorts == ["Latest Updates", "Popularity", "Recently Added", "Alphabet"]
    assert len(set(sorts)) == 4


def test_search_uses_best_match_and_query():
    params = search_data_params("solo leveling", page=1)
    assert params["text"] == "solo leveling"
    assert params["sort"] == "Best Match"
    # Empty query falls back to a browse sort, not Best Match.
    assert search_data_params("", page=1, sort="popular")["sort"] == "Popularity"


def test_browse_page_2_differs_from_page_1(weebcentral_connector: WeebCentralConnector):
    page1 = _load("browse_search_data.html")
    page2 = _load("browse_page2.html")

    def fake_get_text(path: str, *, params=None):
        return page2 if (params or {}).get("offset") else page1

    with patch.object(weebcentral_connector._http, "get_text", side_effect=fake_get_text):
        first = weebcentral_connector.get_series_list(1)
        second = weebcentral_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id


def test_get_chapter_pages_requests_long_strip(weebcentral_connector: WeebCentralConnector):
    html = _load("chapter_images.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(weebcentral_connector._http, "get_text", side_effect=fake_get_text):
        pages = weebcentral_connector.get_chapter_pages("01J76XZ666GREP4DQDKEP1YDZG")

    assert pages
    path, params = captured[0]
    assert path == "/chapters/01J76XZ666GREP4DQDKEP1YDZG/images"
    # reading_style=long_strip is mandatory; without it the endpoint returns no images.
    assert params["reading_style"] == "long_strip"


# --- find_page round-trip ---------------------------------------------------


def test_find_page_round_trips_via_chapter(weebcentral_connector: WeebCentralConnector):
    html = _load("chapter_images.html")

    with patch.object(weebcentral_connector._http, "get_text", return_value=html):
        page_id = make_page_id("01J76XZ666GREP4DQDKEP1YDZG", 2)
        found = weebcentral_connector.find_page(page_id)

    assert found is not None
    assert found.id == page_id
    assert found.chapter_id == "01J76XZ666GREP4DQDKEP1YDZG"
    assert found.remote_url and found.remote_url.startswith("https://")


def test_find_page_rejects_malformed_id(weebcentral_connector: WeebCentralConnector):
    assert weebcentral_connector.find_page("no-colon-here") is None


# --- ID normalization -------------------------------------------------------


def test_id_normalization_accepts_full_refs(weebcentral_connector: WeebCentralConnector):
    assert weebcentral_connector._normalize_id("series/01ABC/Some-Slug") == "01ABC"
    assert weebcentral_connector._normalize_id("chapters/01XYZ") == "01XYZ"
    assert weebcentral_connector._normalize_id("/01BARE/") == "01BARE"


# --- Image proxy allowlist --------------------------------------------------


def test_allowed_image_hosts_cover_real_cdns(weebcentral_connector: WeebCentralConnector):
    allowed = weebcentral_connector.allowed_image_hosts
    # Hosts observed live: covers + rotating page-image CDNs.
    real_hosts = [
        "temp.compsci88.com",
        "hot.planeptune.us",
        "scans-hot.planeptune.us",
        "scans.lastation.us",
        "official.lowee.us",
    ]
    for host in real_hosts:
        assert host_matches_allowlist(host, allowed), host
    # An unrelated host must not match.
    assert not host_matches_allowlist("evil.example.com", allowed)


def test_image_fetch_headers_send_referer(weebcentral_connector: WeebCentralConnector):
    headers = weebcentral_connector.image_fetch_headers()
    assert headers.get("Referer") == "https://weebcentral.com/"


def test_metadata_flags(weebcentral_connector: WeebCentralConnector):
    assert weebcentral_connector.source_type == "weebcentral"
    assert weebcentral_connector.display_name == "Weeb Central"
    assert weebcentral_connector.is_browsable is True
    assert weebcentral_connector.is_mature is False
    mode_ids = {mode.id for mode in weebcentral_connector.list_browse_modes()}
    assert {"default", "popular"} <= mode_ids
