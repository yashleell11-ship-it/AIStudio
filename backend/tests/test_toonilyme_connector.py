"""Tests for the toonily.me (ToonTop) connector.

Every fixture in ``tests/fixtures/toonilyme`` was captured from the production
VPS against ``https://api.toontop.io`` (see the connector docstring). Network
is never touched here: ``self._http.get_json`` is patched.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.toonilyme.connector import ToonilyMeConnector
from connectors.toonilyme.mappers import (
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    search_query_variant,
)
from services.outbound_security import host_matches_allowlist

FIXTURES = Path(__file__).parent / "fixtures" / "toonilyme"

LOOKISM_HSID = "08AdJW2p"
SOLO_HSID = "EQDwe08V"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def connector() -> ToonilyMeConnector:
    return ToonilyMeConnector()


@contextmanager
def routed(connector: ToonilyMeConnector, routes: dict[str, str]):
    """Patch get_json, dispatching on path, and record every call.

    ``routes`` maps an exact request path to a fixture filename. Any path not
    in the map raises, so a test that silently makes an unexpected request
    fails loudly instead of passing on stale cache.
    """
    calls: list[tuple[str, dict | None]] = []

    def fake_get_json(path: str, *, params=None):
        calls.append((path, params))
        if path not in routes:
            raise AssertionError(f"unexpected request: {path} params={params}")
        return _load(routes[path])

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        yield calls


# ---------------------------------------------------------------------------
# Browse / search
# ---------------------------------------------------------------------------

def test_parse_series_list_from_fixture():
    listing = parse_series_list(_load("browse_latest.json"), page=1)
    assert len(listing.items) == 24
    assert listing.total == 8704
    assert listing.page_size == 24
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "i-report-regarding-gender-raw"
    assert first.title == "I Report Regarding Gender Raw"
    assert first.cover_url and first.cover_url.startswith("https://rx.toontop.io/covers/")
    assert first.chapter_count == 49
    assert first.genres


def test_browse_popular_differs_from_latest(connector: ToonilyMeConnector):
    latest = parse_series_list(_load("browse_latest.json"), page=1)
    popular = parse_series_list(_load("browse_popular.json"), page=1)
    assert latest.items[0].id != popular.items[0].id
    assert popular.items[0].id == "secret-class"


def test_browse_page2_is_a_different_page(connector: ToonilyMeConnector):
    page2 = parse_series_list(_load("browse_latest_page2.json"), page=2)
    page1 = parse_series_list(_load("browse_latest.json"), page=1)
    assert page2.page == 2
    assert page2.has_more is True
    assert {i.id for i in page1.items}.isdisjoint({i.id for i in page2.items})


def test_browse_sends_mapped_sort_and_paging(connector: ToonilyMeConnector):
    with routed(connector, {"/titles/search": "browse_latest.json"}) as calls:
        connector.get_series_list(1)
        connector.get_series_list(3, sort="popular")
        connector.get_series_list(1, sort="trending")
        connector.get_series_list(1, sort="nonsense-mode")

    assert calls[0][1] == {"page": 1, "limit": 24, "sort": "latest"}
    assert calls[1][1] == {"page": 3, "limit": 24, "sort": "popular"}
    assert calls[2][1] == {"page": 1, "limit": 24, "sort": "views_7days"}
    # An unknown sort must fall back to a sort the API accepts, never be
    # forwarded raw (upstream answers 400 for an unrecognized sort field).
    assert calls[3][1] == {"page": 1, "limit": 24, "sort": "latest"}


def test_search_sends_query_and_parses_results(connector: ToonilyMeConnector):
    with routed(connector, {"/titles/search": "search_lookism.json"}) as calls:
        listing = connector.search_series("lookism", 1)

    assert calls[0][0] == "/titles/search"
    assert calls[0][1]["q"] == "lookism"
    assert "lookism" in {item.id for item in listing.items}
    assert listing.items[0].title == "Lookism"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("lookism", "lookism"),
        ("solo leveling", "solo-leveling"),
        ("  tower  of   god ", "tower-of-god"),
        ("one piece", "one-piece"),
        ("", ""),
    ],
)
def test_search_query_variant(query: str, expected: str):
    assert search_query_variant(query) == expected


def test_multiword_search_uses_the_hyphenated_form(connector: ToonilyMeConnector):
    """Upstream ranks the plain phrase so badly it misses the title entirely;
    the slug-shaped form is the one that resolves."""
    with routed(connector, {"/titles/search": "search_lookism.json"}) as calls:
        connector.search_series("tower of god", 1)
    assert len(calls) == 1, "the precise form must cost only one request"
    assert calls[0][1]["q"] == "tower-of-god"


def test_multiword_search_falls_back_to_the_raw_phrase_when_empty(
    connector: ToonilyMeConnector,
):
    calls: list[dict] = []

    def fake_get_json(path: str, *, params=None):
        calls.append(params)
        if params["q"] == "no-such-title-here":
            return {"success": True, "data": {"items": [], "pagination": {"total": 0}}}
        return _load("search_lookism.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        listing = connector.search_series("no such title here", 1)

    assert [c["q"] for c in calls] == ["no-such-title-here", "no such title here"]
    assert listing.items, "fallback must preserve recall"


def test_single_word_search_never_makes_a_second_request(connector: ToonilyMeConnector):
    def fake_get_json(path: str, *, params=None):
        return {"success": True, "data": {"items": [], "pagination": {"total": 0}}}

    with patch.object(connector._http, "get_json", side_effect=fake_get_json) as m:
        connector.search_series("zzzznotfound", 1)
    assert m.call_count == 1


def test_blank_search_falls_back_to_browse(connector: ToonilyMeConnector):
    with routed(connector, {"/titles/search": "browse_latest.json"}) as calls:
        connector.search_series("   ", 1)
    assert "q" not in (calls[0][1] or {})


def test_genre_browse_sends_genre_filter(connector: ToonilyMeConnector):
    with routed(connector, {"/titles/search": "browse_latest.json"}) as calls:
        connector.browse_by_genre("action", 2, sort="popular")
    assert calls[0][1] == {"page": 2, "limit": 24, "sort": "popular", "genres": "action"}


# ---------------------------------------------------------------------------
# Series detail
# ---------------------------------------------------------------------------

def test_parse_series_detail_from_fixture():
    series = parse_series_detail(_load("series_lookism.json"), "lookism")
    assert series is not None
    assert series.id == "lookism"
    assert series.title == "Lookism"
    assert series.chapter_count == 631
    assert series.status == "Ongoing"
    assert series.author == "Park Tae Joon"
    assert series.artist == "Park Tae Joon"
    assert series.cover_url == "https://rx.toontop.io/covers/248c4e5f8aef.webp"
    assert "Park Hyung Suk" in (series.description or "")
    assert "Action" in series.genres
    assert series.latest_chapter == "Chapter 623"


def test_get_series_uses_by_slug_detail_endpoint(connector: ToonilyMeConnector):
    with routed(connector, {"/titles/by-slug/lookism": "series_lookism.json"}) as calls:
        series = connector.get_series("lookism")
    assert series is not None and series.title == "Lookism"
    assert calls == [("/titles/by-slug/lookism", {"include": "details"})]


def test_series_key_accepts_url_and_path_forms(connector: ToonilyMeConnector):
    with routed(connector, {"/titles/by-slug/lookism": "series_lookism.json"}):
        assert connector.get_series("https://toontop.io/lookism") is not None
        assert connector.get_series("/lookism/") is not None


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------

def test_parse_chapters_ascending_with_decimals():
    chapters = parse_chapters(_load("chapters_solo_leveling.json"), "solo-leveling")
    assert len(chapters) == 227
    numbers = [c.number for c in chapters]
    assert all(n is not None for n in numbers)
    assert numbers == sorted(numbers), "chapters must be ascending (last == newest)"
    assert chapters[-1].title == "Chapter 200.5"
    by_id = {c.id: c for c in chapters}
    decimal = by_id["solo-leveling/chapter-200-5"]
    assert decimal.number == 200.5
    assert by_id["solo-leveling/chapter-179-6"].number == 179.6
    # Keys are the site's own path shape, and carry the series slug.
    assert all(c.id.startswith("solo-leveling/") for c in chapters)
    assert all(c.series_id == "solo-leveling" for c in chapters)
    assert chapters[0].release_date


def test_short_series_chapter_list_costs_no_extra_request(connector: ToonilyMeConnector):
    """declared count fits the embedded window -> zero follow-up requests."""
    with routed(
        connector, {"/titles/by-slug/the-myth-of-achilles": "series_short.json"}
    ) as calls:
        chapters = connector.get_chapters("the-myth-of-achilles")

    assert len(chapters) == 5
    assert [c.number for c in chapters] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert len(calls) == 1, f"expected a single request, got {calls}"


def test_long_series_fetches_the_bulk_chapter_list(connector: ToonilyMeConnector):
    """631 declared > 50 embedded -> one bulk call, keyed by the series hsid."""
    with routed(
        connector,
        {
            "/titles/by-slug/lookism": "series_lookism.json",
            f"/titles/{LOOKISM_HSID}/chapters": "chapters_solo_leveling.json",
        },
    ) as calls:
        chapters = connector.get_chapters("lookism")

    assert [path for path, _ in calls] == [
        "/titles/by-slug/lookism",
        f"/titles/{LOOKISM_HSID}/chapters",
    ]
    assert len(chapters) == 227  # from the bulk fixture, not the 50 embedded


def test_bulk_chapter_failure_falls_back_to_embedded_window(connector: ToonilyMeConnector):
    def fake_get_json(path: str, *, params=None):
        if path == "/titles/by-slug/lookism":
            return _load("series_lookism.json")
        raise ConnectorHttpError("Retryable HTTP 503", status_code=503)

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        chapters = connector.get_chapters("lookism")

    # Degrades to the newest 50 rather than losing the series entirely.
    assert len(chapters) == 50
    assert chapters[-1].title == "Chapter 623"


def test_series_and_chapters_share_a_single_detail_fetch(connector: ToonilyMeConnector):
    """The anti-pattern guard: opening a series must not fetch detail twice."""
    with routed(
        connector, {"/titles/by-slug/the-myth-of-achilles": "series_short.json"}
    ) as calls:
        series = connector.get_series("the-myth-of-achilles")
        chapters = connector.get_chapters("the-myth-of-achilles")

    assert series is not None and chapters
    detail_calls = [p for p, _ in calls if p == "/titles/by-slug/the-myth-of-achilles"]
    assert len(detail_calls) == 1, f"detail fetched {len(detail_calls)}x: {calls}"


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

def test_parse_chapter_pages_from_fixture():
    pages = parse_chapter_pages(_load("chapter_lookism_623.json"), "lookism/chapter-623")
    assert len(pages) == 17
    assert pages[0].number == 1
    assert pages[0].id == "lookism/chapter-623:1"
    assert pages[0].chapter_id == "lookism/chapter-623"
    assert pages[0].remote_url == "https://rx.toontop.io/r/p/1221027a/ecdd3de0/c03d35981b17.webp"
    assert [p.number for p in pages] == list(range(1, 18))


def test_chapter_pages_resolve_in_one_request(connector: ToonilyMeConnector):
    """Page images must not cost a request per page."""
    with routed(
        connector,
        {"/titles/by-slug/lookism/chapters/chapter-623": "chapter_lookism_623.json"},
    ) as calls:
        pages = connector.get_chapter_pages("lookism/chapter-623")

    assert len(pages) == 17
    assert len(calls) == 1, f"expected one request for all pages, got {len(calls)}"
    assert calls[0][1] == {"include": "details"}


def test_decimal_chapter_pages_resolve(connector: ToonilyMeConnector):
    with routed(
        connector,
        {
            "/titles/by-slug/solo-leveling/chapters/chapter-200-5":
                "chapter_solo_leveling_200_5.json"
        },
    ):
        pages = connector.get_chapter_pages("solo-leveling/chapter-200-5")
    assert pages
    assert pages[0].remote_url.startswith("https://rx.toontop.io/")


def test_page_urls_are_https_and_inside_the_ssrf_allowlist(connector: ToonilyMeConnector):
    pages = parse_chapter_pages(_load("chapter_lookism_623.json"), "lookism/chapter-623")
    for page in pages:
        parsed = urlparse(page.remote_url or "")
        assert parsed.scheme == "https"
        assert parsed.hostname
        assert host_matches_allowlist(parsed.hostname, connector.allowed_image_hosts)


def test_find_page_round_trips_without_refetching(connector: ToonilyMeConnector):
    with routed(
        connector,
        {"/titles/by-slug/lookism/chapters/chapter-623": "chapter_lookism_623.json"},
    ) as calls:
        pages = connector.get_chapter_pages("lookism/chapter-623")
        found = connector.find_page(pages[5].id)
        missing = connector.find_page("lookism/chapter-623:999")

    assert found == pages[5]
    assert missing is None
    assert len(calls) == 1, "find_page must reuse the cached page list"


def test_find_page_rejects_a_malformed_id(connector: ToonilyMeConnector):
    assert connector.find_page("no-colon-here") is None
    assert connector.find_page("") is None


def test_chapter_page_count_backfills_into_the_chapter_list(connector: ToonilyMeConnector):
    with routed(
        connector,
        {
            "/titles/by-slug/lookism/chapters/chapter-623": "chapter_lookism_623.json",
            "/titles/by-slug/lookism": "series_lookism.json",
            f"/titles/{LOOKISM_HSID}/chapters": "chapters_solo_leveling.json",
        },
    ):
        connector.get_chapter_pages("lookism/chapter-623")
        connector.get_chapters("lookism")
        # chapters_solo_leveling has no lookism/chapter-623 id, so probe the
        # cache through a chapter that IS in the bulk fixture instead.
        connector._page_count_cache.set("solo-leveling/chapter-1", 42)
        chapters = parse_chapters(_load("chapters_solo_leveling.json"), "solo-leveling")
        enriched = connector._enrich(chapters)

    by_id = {c.id: c for c in enriched}
    assert by_id["solo-leveling/chapter-1"].page_count == 42
    assert by_id["solo-leveling/chapter-2"].page_count == 0


# ---------------------------------------------------------------------------
# Failure handling -- the known ConnectorHttpError trap
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "error",
    [
        # The shared client attaches status_code only for RETRYABLE_STATUS, so
        # a 404 usually arrives ONLY as httpx's message text. Both forms must
        # be recognised, or the message-only form is unhandled.
        ConnectorHttpError("Client error '404 Not Found' for url 'https://x'"),
        ConnectorHttpError("Not found", status_code=404),
    ],
    ids=["message-only", "status-code"],
)
def test_missing_series_returns_none_for_both_404_shapes(
    connector: ToonilyMeConnector, error: ConnectorHttpError
):
    with patch.object(connector._http, "get_json", side_effect=error):
        assert connector.get_series("no-such-series") is None
        assert connector.get_chapters("no-such-series") == []


@pytest.mark.parametrize(
    "error",
    [
        ConnectorHttpError("Client error '404 Not Found' for url 'https://x'"),
        ConnectorHttpError("Not found", status_code=404),
    ],
    ids=["message-only", "status-code"],
)
def test_missing_chapter_returns_empty_for_both_404_shapes(
    connector: ToonilyMeConnector, error: ConnectorHttpError
):
    with patch.object(connector._http, "get_json", side_effect=error):
        assert connector.get_chapter_pages("no-such-series/chapter-1") == []


def test_server_error_on_detail_propagates(connector: ToonilyMeConnector):
    """A 503 is not a missing series -- it must not be reported as 'gone'."""
    with patch.object(
        connector._http,
        "get_json",
        side_effect=ConnectorHttpError("Retryable HTTP 503", status_code=503),
    ):
        with pytest.raises(ConnectorHttpError):
            connector.get_series("lookism")


def test_malformed_chapter_key_makes_no_request(connector: ToonilyMeConnector):
    with routed(connector, {}) as calls:
        assert connector.get_chapter_pages("lookism") == []
        assert connector.get_chapter_pages("") == []
    assert calls == []


# ---------------------------------------------------------------------------
# Chapter numbering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,slug,expected",
    [
        ("Chapter 623", "chapter-623", 623.0),
        ("Chapter 200.5", "chapter-200-5", 200.5),
        # The six real deviations found across 27,927 upstream chapter names.
        ("Chapter 11 - Revised", "chapter-11-revised", 11.0),
        ("Chapter 3 - Fixed", "chapter-3-fixed", 3.0),
        ("132 - Ahn Somi, the voyeur", "132-ahn-somi-the-voyeur", 132.0),
        ("Chapter 0 - Prologue", "chapter-0-prologue", 0.0),
        ("Chapter 84.5 - Hiatus", "chapter-84-5-hiatus", 84.5),
        # Name missing entirely -> slug fallback.
        ("", "chapter-5-1", 5.1),
        ("", "chapter-7", 7.0),
        ("", "extras", None),
    ],
)
def test_chapter_number_parsing(name: str, slug: str, expected):
    assert parse_chapter_number(name, slug) == expected


def test_chapter_number_ignores_the_internal_sequence_field():
    """Lookism's 'Chapter 623' carries number: 634 upstream -- an internal
    ordering sequence, not the published number. Using it would renumber the
    series."""
    payload = _load("series_lookism.json")
    raw = payload["data"]["title"]["chapters"][0]
    assert raw["name"] == "Chapter 623" and raw["number"] == 634
    chapters = parse_chapters({"data": {"chapters": [raw]}}, "lookism")
    assert chapters[0].number == 623.0


# ---------------------------------------------------------------------------
# Source metadata
# ---------------------------------------------------------------------------

def test_source_identity_and_mature_flag(connector: ToonilyMeConnector):
    assert connector.source_type == "toonilyme"
    assert connector.display_name == "Toonily.me"
    assert connector.is_browsable is True
    assert connector.content_kind == "manga"
    # Adult-leaning catalog; the upstream per-title is_adult flag under-reports.
    assert connector.is_mature is True


def test_image_fetch_headers_carry_the_site_referer(connector: ToonilyMeConnector):
    headers = connector.image_fetch_headers()
    # rx.toontop.io answers 403 to an image GET with no Referer (verified on VPS).
    assert headers["Referer"] == "https://toontop.io/"
    assert "Mozilla/5.0" in headers["User-Agent"]


def test_allowlist_covers_the_cdn_but_not_the_open_internet(connector: ToonilyMeConnector):
    allowed = connector.allowed_image_hosts
    assert host_matches_allowlist("rx.toontop.io", allowed)
    assert host_matches_allowlist("toontop.io", allowed)
    assert not host_matches_allowlist("evil.example.com", allowed)
    assert not host_matches_allowlist("toontop.io.evil.com", allowed)


def test_browse_modes_and_genres_are_offered(connector: ToonilyMeConnector):
    modes = {m.id for m in connector.list_browse_modes()}
    assert {"default", "popular", "trending", "rating", "new"} <= modes
    genres = connector.list_genres()
    assert len(genres) == 71
    assert "action" in {g.id for g in genres}
