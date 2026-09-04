"""Offline tests for the MangaBuddy (comizy.io) connector.

Fixtures under ``tests/fixtures/mangabuddy/`` were captured live 2026-09-04
FROM THE VPS (through production's exact egress and TLS stack). The connector
is exercised entirely against those captures by patching ``self._http.get_json``;
no network.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.mangabuddy.connector import MangaBuddyConnector, _is_not_found
from connectors.mangabuddy.mappers import (
    PAGE_SIZE,
    declared_chapter_count,
    explicit_sort,
    is_api_id,
    make_chapter_key,
    make_page_id,
    normalize_genre,
    normalize_series_key,
    normalize_sort,
    page_id_chapter_key,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_embedded_chapters,
    parse_series_detail,
    parse_series_list,
    search_params,
    split_chapter_key,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mangabuddy"

SERIES_KEY = "A5LeWJj1"  # Stay Alive
CHAPTER_HSID = "MjPw7z45"  # its Chapter 1
CHAPTER_KEY = f"{SERIES_KEY}/{CHAPTER_HSID}"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- identity ---------------------------------------------------------------


def test_chapter_key_contains_a_slash_and_round_trips():
    """House law: keys are opaque and may contain slashes, passed through raw."""
    assert "/" in CHAPTER_KEY
    assert make_chapter_key(SERIES_KEY, CHAPTER_HSID) == CHAPTER_KEY
    assert split_chapter_key(CHAPTER_KEY) == (SERIES_KEY, CHAPTER_HSID)
    # Stray slashes and a leading slash normalize to the same key.
    assert split_chapter_key(f"/{CHAPTER_KEY}/") == (SERIES_KEY, CHAPTER_HSID)
    # A bare series key is not a chapter key.
    assert split_chapter_key(SERIES_KEY) is None
    assert split_chapter_key("") is None


def test_series_key_survives_being_asked_with_a_chapter_key():
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(CHAPTER_KEY) == SERIES_KEY
    assert normalize_series_key(f"/{SERIES_KEY}/") == SERIES_KEY


def test_page_id_round_trips_through_a_slash_bearing_chapter_key():
    page_id = make_page_id(CHAPTER_KEY, 7)
    assert page_id == f"{CHAPTER_KEY}:7"
    assert page_id_chapter_key(page_id) == CHAPTER_KEY
    assert page_id_chapter_key("no-colon-here") is None


def test_is_api_id_screens_slugs_the_api_rejects():
    """``GET /titles/martial-peak`` answers 400, not 404 -- screen it first."""
    assert is_api_id(SERIES_KEY)
    assert is_api_id(CHAPTER_HSID)
    assert not is_api_id("martial-peak")
    assert not is_api_id("")


# --- params -----------------------------------------------------------------


def test_normalize_sort_maps_browse_modes_and_rejects_unknowns():
    assert normalize_sort(None) == "latest"
    assert normalize_sort("default") == "latest"
    assert normalize_sort("popular") == "popular"
    assert normalize_sort("views_7days") == "views_7days"
    # Verified broken upstream (200 with zero items) -- must not be emitted.
    assert normalize_sort("alphabetical") == "latest"
    assert normalize_sort("nonsense") == "latest"


def test_normalize_genre_accepts_known_slugs_only():
    assert normalize_genre("action") == "action"
    assert normalize_genre("Action") == "action"
    assert normalize_genre("not-a-genre") is None


def test_search_params_shape():
    params = search_params("solo leveling", page=2, sort="views")
    assert params == {"page": 2, "limit": PAGE_SIZE, "sort": "views", "q": "solo leveling"}
    # A blank query drops ``q`` entirely (browse, not search).
    assert "q" not in search_params("  ", page=1, sort=None)
    assert search_params("", page=1, sort=None, genre="action")["genres"] == "action"


def test_a_keyword_search_omits_sort_so_the_api_ranks_by_relevance():
    """Sending the browse default on a search buries the obvious hit.

    Verified live from the VPS: ``q=solo+leveling&sort=latest`` returns
    "Leveling Up With Skills" first, while omitting ``sort`` returns
    "Solo Leveling". ``sort=best_match`` -- what the site's own UI calls this
    mode -- is not a real API sort and answers 400.
    """
    params = search_params("solo leveling", page=1, sort=None)
    assert "sort" not in params
    assert params["q"] == "solo leveling"
    # An explicitly chosen sort still wins over relevance.
    assert search_params("solo leveling", page=1, sort="views")["sort"] == "views"
    # Browsing (no query) always carries a sort.
    assert search_params("", page=1, sort=None)["sort"] == "latest"
    assert search_params("", page=1, sort="default")["sort"] == "latest"
    # Neither pseudo-sort may ever reach the API.
    assert "sort" not in search_params("solo", page=1, sort="best_match")
    assert "sort" not in search_params("solo", page=1, sort="alphabetical")


def test_explicit_sort_distinguishes_chosen_from_defaulted():
    assert explicit_sort(None) is None
    assert explicit_sort("default") is None
    assert explicit_sort("best_match") is None
    assert explicit_sort("alphabetical") is None
    assert explicit_sort("views") == "views"


# --- listing ----------------------------------------------------------------


def test_parse_browse_listing():
    listing = parse_series_list(_load("browse_latest.json"), page=1)
    assert len(listing.items) == 24
    assert listing.page == 1
    assert listing.page_size == 24
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "kNxX4KNE"
    assert first.title == "Magical Girl Wife"
    assert first.cover_url == "https://rx.comizy.io/covers/3ee3277dc067.webp"
    assert first.canonical_path == "/magical-girl-wife"
    assert first.chapter_count == 24
    assert first.status == "Ongoing"
    assert "Fantasy" in first.genres
    assert first.latest_chapter == "Chapter 24"
    assert first.description and "magical girl" in first.description.lower()


def test_parse_listing_page_two_reports_its_own_page():
    listing = parse_series_list(_load("browse_popular_page2.json"), page=2)
    assert listing.page == 2
    assert len(listing.items) == 24
    assert listing.has_more is True
    assert all(item.id and item.title for item in listing.items)


def test_has_more_comes_from_the_api_not_the_saturated_total():
    """``total`` saturates at 10000 (``total_relation: "gte"``)."""
    listing = parse_series_list(_load("browse_latest.json"), page=1)
    assert listing.total == 10000
    assert listing.api_has_more is True


def test_parse_search_results():
    listing = parse_series_list(_load("search_solo_leveling.json"), page=1)
    assert len(listing.items) == 24
    titles = [item.title for item in listing.items]
    assert "Solo Leveling" in titles
    top = listing.items[0]
    assert top.title == "Solo Leveling"
    assert top.id == "4N90moOv"


def test_parse_genre_listing():
    listing = parse_series_list(_load("genre_action.json"), page=1)
    assert len(listing.items) == 24
    assert all(item.id and item.title for item in listing.items)


def test_listing_skips_records_missing_an_id_or_title():
    payload = {
        "data": {
            "items": [
                {"id": "", "name": "No id"},
                {"id": "abc123", "name": ""},
                {"id": "ok12345", "name": "Kept"},
                "not-a-dict",
            ],
            "pagination": {"page": 1, "limit": 24, "total": 3, "has_next": False},
        }
    }
    listing = parse_series_list(payload, page=1)
    assert [item.title for item in listing.items] == ["Kept"]
    assert listing.has_more is False


# --- series detail ----------------------------------------------------------


def test_parse_series_detail():
    series = parse_series_detail(_load("series_stay_alive.json"), SERIES_KEY)
    assert series is not None
    assert series.id == SERIES_KEY
    assert series.title == "Stay Alive"
    assert series.chapter_count == 61
    assert series.status == "Ongoing"
    assert series.cover_url == "https://rx.comizy.io/covers/2fecb9de0ae0.webp"
    assert series.canonical_path == "/stay-alive"
    assert series.author is not None and "Gonu" in series.author
    assert series.artist == "Foxy"
    assert "Action" in series.genres
    assert series.description and "zombie" in series.description.lower()


def test_series_detail_embeds_only_the_newest_fifty_chapters():
    """The detail route truncates at 50 -- the connector must notice."""
    payload = _load("series_stay_alive.json")
    embedded = parse_embedded_chapters(payload, SERIES_KEY)
    assert len(embedded) == 50
    assert declared_chapter_count(payload) == 61
    assert len(embedded) < declared_chapter_count(payload)


def test_parse_series_detail_rejects_a_payload_with_no_title():
    assert parse_series_detail({"data": {}}, SERIES_KEY) is None
    assert parse_series_detail({}, SERIES_KEY) is None


# --- chapters ---------------------------------------------------------------


def test_parse_full_chapter_list():
    chapters = parse_chapters(_load("chapters_stay_alive.json"), SERIES_KEY)
    assert len(chapters) == 61
    # Oldest first, so the reader starts at the beginning.
    assert chapters[0].title == "Chapter 0"
    assert chapters[0].number == 0
    assert chapters[-1].title == "Chapter 60"
    assert chapters[-1].number == 60
    assert all(c.series_id == SERIES_KEY for c in chapters)
    assert all(c.id.startswith(f"{SERIES_KEY}/") for c in chapters)
    assert chapters[-1].id == "A5LeWJj1/Y5l0zKZ5"
    assert chapters[-1].release_date == "2026-09-04T18:00:03.000Z"


def test_chapter_numbers_are_strictly_increasing():
    chapters = parse_chapters(_load("chapters_stay_alive.json"), SERIES_KEY)
    numbers = [c.number for c in chapters]
    assert all(n is not None for n in numbers)
    assert numbers == sorted(numbers)
    assert numbers == list(range(0, 61))


def test_chapter_number_ignores_the_api_ordinal_field():
    """The API's ``number`` is a 1-based ordinal, not the chapter number.

    On Stay Alive its ``chapter-0`` is ``number: 1`` and ``chapter-60`` is
    ``number: 61``; trusting it would shift every chapter by one.
    """
    raw = _load("chapters_stay_alive.json")["data"]["chapters"]
    oldest = raw[-1]
    assert oldest["slug"] == "chapter-0"
    assert oldest["number"] == 1  # the ordinal, and NOT what we parse
    chapters = parse_chapters(_load("chapters_stay_alive.json"), SERIES_KEY)
    assert chapters[0].number == 0


def test_parse_chapter_number_prefers_the_sites_own_labelling():
    assert parse_chapter_number("Chapter 60", "chapter-60") == 60
    assert parse_chapter_number("Chapter 10.5", "chapter-10-5") == 10.5
    assert parse_chapter_number("", "chapter-7") == 7
    assert parse_chapter_number("Prologue", "prologue") is None


def test_chapters_skip_records_with_no_id():
    payload = {"data": {"chapters": [{"name": "Chapter 1"}, {"id": "ok1", "name": "Chapter 2"}]}}
    chapters = parse_chapters(payload, SERIES_KEY)
    assert len(chapters) == 1
    assert chapters[0].id == f"{SERIES_KEY}/ok1"


# --- pages ------------------------------------------------------------------


def test_parse_chapter_pages_returns_every_image_with_dimensions():
    pages = parse_chapter_pages(_load("chapter_detail.json"), CHAPTER_KEY)
    assert len(pages) == 85
    assert [p.number for p in pages] == list(range(1, 86))
    assert all(p.chapter_id == CHAPTER_KEY for p in pages)
    assert pages[0].id == f"{CHAPTER_KEY}:1"
    assert pages[0].remote_url.startswith("https://x1.cmzcdn.org/")
    assert pages[0].width == 720 and pages[0].height == 1200
    # The last page is a different height -- proof we read per-page dimensions
    # rather than stamping the first one across the chapter.
    assert pages[-1].height == 1271


def test_every_page_url_is_on_an_allowlisted_cdn_host():
    connector = MangaBuddyConnector()
    allowed = connector.allowed_image_hosts
    pages = parse_chapter_pages(_load("chapter_detail.json"), CHAPTER_KEY)
    for page in pages:
        host = page.remote_url.split("/")[2]
        assert any(host == d or host.endswith("." + d) for d in allowed), host


def test_the_images_route_is_a_three_item_teaser_we_must_not_use():
    """Why ``get_chapter_pages`` calls the chapter DETAIL route.

    ``/titles/<t>/chapters/<c>/images`` answers 200 with exactly 3 URLs no
    matter how long the chapter is (verified from the VPS on three chapters of
    85, 13 and 12 pages; it ignores limit/page/all). Building on it would
    silently drop every page past the third.
    """
    teaser = _load("chapter_images_truncated.json")
    assert len(teaser["data"]["images"]) == 3
    detail = _load("chapter_detail.json")
    assert len(detail["data"]["chapter"]["images"]) == 85


def test_parse_chapter_pages_falls_back_to_the_plain_image_list():
    payload = {"data": {"chapter": {"images": ["https://x1.cmzcdn.org/a.webp"]}}}
    pages = parse_chapter_pages(payload, CHAPTER_KEY)
    assert len(pages) == 1
    assert pages[0].remote_url == "https://x1.cmzcdn.org/a.webp"
    assert pages[0].width is None


def test_parse_chapter_pages_on_a_payload_with_no_chapter():
    assert parse_chapter_pages({"data": {}}, CHAPTER_KEY) == []


# --- connector wiring -------------------------------------------------------


def _connector_with(responses: dict[str, object]) -> tuple[MangaBuddyConnector, list[str]]:
    """A connector whose HTTP layer answers from ``responses`` by path."""
    connector = MangaBuddyConnector()
    calls: list[str] = []

    def fake_get_json(path: str, *, params=None):
        calls.append(path)
        value = responses.get(path)
        if value is None:
            raise ConnectorHttpError(f"Client error '404 Not Found' for url {path}")
        if isinstance(value, Exception):
            raise value
        return value

    patcher = patch.object(connector._http, "get_json", side_effect=fake_get_json)
    patcher.start()
    return connector, calls


def test_opening_a_short_series_costs_one_request_for_detail_and_chapters():
    """The known anti-pattern: fetching the series page twice.

    A series whose chapter list already arrived complete inside the detail
    payload must not spend a second request to list its chapters.
    """
    detail = _load("series_stay_alive.json")
    # Trim the declared count so the embedded 50 ARE the whole series.
    detail["data"]["title"]["stats"]["chapters_count"] = 50
    connector, calls = _connector_with({f"/titles/{SERIES_KEY}": detail})

    series = connector.get_series(SERIES_KEY)
    chapters = connector.get_chapters(SERIES_KEY)

    assert series is not None and series.title == "Stay Alive"
    assert len(chapters) == 50
    assert calls == [f"/titles/{SERIES_KEY}"], calls


def test_opening_a_long_series_costs_exactly_two_requests():
    connector, calls = _connector_with(
        {
            f"/titles/{SERIES_KEY}": _load("series_stay_alive.json"),
            f"/titles/{SERIES_KEY}/chapters": _load("chapters_stay_alive.json"),
        }
    )
    series = connector.get_series(SERIES_KEY)
    chapters = connector.get_chapters(SERIES_KEY)

    assert series is not None
    assert len(chapters) == 61
    assert calls == [f"/titles/{SERIES_KEY}", f"/titles/{SERIES_KEY}/chapters"], calls


def test_repeat_reads_are_served_from_cache():
    connector, calls = _connector_with(
        {
            f"/titles/{SERIES_KEY}": _load("series_stay_alive.json"),
            f"/titles/{SERIES_KEY}/chapters": _load("chapters_stay_alive.json"),
        }
    )
    for _ in range(3):
        connector.get_series(SERIES_KEY)
        connector.get_chapters(SERIES_KEY)
    assert len(calls) == 2, calls


def test_chapter_pages_cost_one_request_and_find_page_costs_none():
    """A page-image resolution that costs a request per page is the trap."""
    connector, calls = _connector_with(
        {f"/titles/{SERIES_KEY}/chapters/{CHAPTER_HSID}": _load("chapter_detail.json")}
    )
    pages = connector.get_chapter_pages(CHAPTER_KEY)
    assert len(pages) == 85
    assert len(calls) == 1

    for page in pages:
        found = connector.find_page(page.id)
        assert found is not None and found.remote_url == page.remote_url
    # 85 image lookups, still one upstream request in total.
    assert len(calls) == 1, calls


def test_get_chapters_reports_page_counts_learned_from_opening_a_chapter():
    connector, _calls = _connector_with(
        {
            f"/titles/{SERIES_KEY}": _load("series_stay_alive.json"),
            f"/titles/{SERIES_KEY}/chapters": _load("chapters_stay_alive.json"),
            f"/titles/{SERIES_KEY}/chapters/{CHAPTER_HSID}": _load("chapter_detail.json"),
        }
    )
    connector.get_chapter_pages(CHAPTER_KEY)
    chapters = connector.get_chapters(SERIES_KEY)
    opened = [c for c in chapters if c.id == CHAPTER_KEY]
    assert opened and opened[0].page_count == 85


def test_browse_and_search_each_cost_one_request():
    connector, calls = _connector_with({"/titles/search": _load("browse_latest.json")})
    listing = connector.get_series_list(1)
    assert len(listing.items) == 24
    assert calls == ["/titles/search"]

    results = connector.search_series("solo leveling", 1)
    assert len(results.items) == 24
    assert len(calls) == 2


def test_blank_search_falls_back_to_browsing():
    connector, calls = _connector_with({"/titles/search": _load("browse_latest.json")})
    listing = connector.search_series("   ", 1)
    assert len(listing.items) == 24
    assert len(calls) == 1


def test_genre_browse_sends_the_genre_filter():
    connector = MangaBuddyConnector()
    seen: dict[str, object] = {}

    def fake_get_json(path: str, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return _load("genre_action.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        listing = connector.browse_by_genre("action", 1, sort="views")
    assert listing.items
    assert seen["path"] == "/titles/search"
    assert seen["params"]["genres"] == "action"
    assert seen["params"]["sort"] == "views"


# --- failure handling -------------------------------------------------------


def test_is_not_found_matches_both_error_shapes():
    """The shared client only sets status_code for RETRYABLE_STATUS."""
    assert _is_not_found(ConnectorHttpError("boom", status_code=404))
    assert _is_not_found(
        ConnectorHttpError("Client error '404 Not Found' for url https://x/y")
    )
    assert not _is_not_found(ConnectorHttpError("Retryable HTTP 503", status_code=503))


def test_missing_series_returns_none_and_missing_chapters_returns_empty():
    connector, _calls = _connector_with({})
    assert connector.get_series("ZZZZZZZZ") is None
    assert connector.get_chapters("ZZZZZZZZ") == []
    assert connector.get_chapter_pages("ZZZZZZZZ/YYYYYYYY") == []


def test_slug_shaped_keys_are_refused_without_a_request():
    """The API answers 400 for a slug; never spend a request learning that."""
    connector, calls = _connector_with({})
    assert connector.get_series("martial-peak") is None
    assert connector.get_chapters("martial-peak") == []
    assert connector.get_chapter_pages("martial-peak/chapter-1") == []
    assert calls == []


def test_chapter_list_failure_degrades_to_the_embedded_chapters():
    connector, _calls = _connector_with(
        {f"/titles/{SERIES_KEY}": _load("series_stay_alive.json")}
    )
    chapters = connector.get_chapters(SERIES_KEY)
    # The dedicated route 404s in this fixture set; we still show the newest 50
    # rather than an empty series.
    assert len(chapters) == 50


def test_browse_propagates_transport_errors():
    connector = MangaBuddyConnector()
    with patch.object(
        connector._http,
        "get_json",
        side_effect=ConnectorHttpError("Retryable HTTP 503", status_code=503),
    ):
        with pytest.raises(ConnectorHttpError):
            connector.get_series_list(1)


def test_find_page_on_a_malformed_id():
    connector, calls = _connector_with({})
    assert connector.find_page("no-colon") is None
    assert calls == []


# --- descriptor -------------------------------------------------------------


def test_connector_descriptor():
    connector = MangaBuddyConnector()
    assert connector.source_type == "mangabuddy"
    assert connector.display_name == "MangaBuddy"
    assert connector.is_browsable is True
    assert connector.is_mature is False
    assert connector.content_kind == "manga"
    assert connector.allowed_image_hosts == frozenset({"cmzcdn.org", "comizy.io"})
    # cmzcdn.org 403s without a site Referer.
    assert connector.image_fetch_headers()["Referer"] == "https://comizy.io/"
    mode_ids = [m.id for m in connector.list_browse_modes()]
    assert mode_ids[0] == "default"
    assert "popular" in mode_ids
    assert "alphabetical" not in mode_ids  # broken upstream
    assert len(connector.list_genres()) == 71
