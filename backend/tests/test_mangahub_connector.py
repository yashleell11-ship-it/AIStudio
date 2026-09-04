"""Offline tests for the MangaHub GraphQL connector.

Fixtures under ``tests/fixtures/mangahub/`` were captured live 2026-09-04 FROM
THE VPS (production's exact egress and TLS stack) against
``https://api.mghcdn.com/graphql``. The connector is exercised entirely
against those captures by patching ``SyncConnectorHttpClient.get_json``; no
network. The class-level patch (rather than a per-instance one) is deliberate:
the gated ``chapter`` query runs on a second client the connector rebuilds when
its access nonce is spent, and the rotation path has to be covered too.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.mangahub.connector import TOKEN_CHAPTER_BUDGET, MangaHubConnector
from connectors.mangahub.mappers import (
    IMAGE_BASE,
    PAGE_SIZE,
    THUMB_BASE,
    chapter_query,
    format_chapter_number,
    genre_manga_query,
    graphql_errors,
    is_rate_limited,
    make_chapter_key,
    make_page_id,
    manga_query,
    normalize_series_key,
    normalize_sort,
    page_id_chapter_key,
    parse_chapter_pages,
    parse_chapters,
    parse_genre_series_list,
    parse_genres,
    parse_series_detail,
    parse_series_list,
    search_query,
    series_canonical_path,
    split_chapter_key,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mangahub"

SERIES_KEY = "solo-leveling_105"
VILLAIN_KEY = "i-d-rather-live-as-a-villain"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- identity ---------------------------------------------------------------


def test_series_key_round_trips_from_every_shape():
    """Keys are opaque: stored and passed raw, never reconstructed."""
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(f"manga/{SERIES_KEY}") == SERIES_KEY
    assert normalize_series_key(f"/manga/{SERIES_KEY}/") == SERIES_KEY
    assert normalize_series_key(f"https://mangahub.io/manga/{SERIES_KEY}") == SERIES_KEY
    assert series_canonical_path(SERIES_KEY) == f"/manga/{SERIES_KEY}"


def test_chapter_key_round_trips_including_decimals():
    assert make_chapter_key(SERIES_KEY, 1) == f"{SERIES_KEY}/1"
    assert make_chapter_key(SERIES_KEY, 1.0) == f"{SERIES_KEY}/1"
    assert make_chapter_key(SERIES_KEY, 200.5) == f"{SERIES_KEY}/200.5"
    assert split_chapter_key(f"{SERIES_KEY}/200.5") == (SERIES_KEY, 200.5)
    assert split_chapter_key(f"{SERIES_KEY}/0") == (SERIES_KEY, 0.0)


def test_split_chapter_key_keeps_slashes_inside_the_series_key():
    """rpartition, not split: a slug containing a slash must survive intact."""
    assert split_chapter_key("group/series-name/12") == ("group/series-name", 12.0)


def test_split_chapter_key_rejects_unusable_input():
    assert split_chapter_key("no-number-here") is None
    assert split_chapter_key(f"{SERIES_KEY}/not-a-number") is None


def test_page_id_round_trips():
    page_id = make_page_id(f"{SERIES_KEY}/200.5", 7)
    assert page_id == f"{SERIES_KEY}/200.5:7"
    assert page_id_chapter_key(page_id) == f"{SERIES_KEY}/200.5"
    assert page_id_chapter_key("no-colon") is None


def test_format_chapter_number_never_emits_a_trailing_zero():
    assert format_chapter_number(1) == "1"
    assert format_chapter_number(1.0) == "1"
    assert format_chapter_number(200.5) == "200.5"


# --- query builders ---------------------------------------------------------


def test_search_query_escapes_user_input():
    """A quote typed into the search box must not break out of the literal."""
    gql = search_query('a "b" \\ c', limit=24, offset=0, mod="POPULAR")
    assert 'q:"a \\"b\\" \\\\ c"' in gql
    assert "count:true" in gql


def test_query_builders_carry_the_site_source_and_paging():
    gql = search_query("", limit=PAGE_SIZE, offset=48, mod="LATEST")
    assert "x:m01" in gql and "mod:LATEST" in gql
    assert f"limit:{PAGE_SIZE}" in gql and "offset:48" in gql
    assert "hideNSFW:true" in gql and "hideYaoi:true" in gql
    assert "genre:\"action\"" in genre_manga_query(
        "action", limit=24, offset=0, mod="POPULAR"
    )
    assert f'slug:"{SERIES_KEY}"' in manga_query(SERIES_KEY)
    # The chapter list rides along on the detail query -- that is the whole
    # point of sharing one fetch.
    assert "chapters{" in manga_query(SERIES_KEY)


def test_chapter_query_number_is_a_bare_float():
    assert "number:1)" in chapter_query(SERIES_KEY, 1.0)
    assert "number:200.5)" in chapter_query(SERIES_KEY, 200.5)


def test_normalize_sort_maps_browse_modes():
    assert normalize_sort(None) == "POPULAR"
    assert normalize_sort("latest") == "LATEST"
    assert normalize_sort("alphabetical") == "ALPHABET"
    assert normalize_sort("completed") == "COMPLETED"
    assert normalize_sort("nonsense") == "POPULAR"


# --- listing parsing --------------------------------------------------------


def test_parse_browse_listing():
    listing = parse_series_list(_load("search_popular_p1.json"), page=1)
    assert len(listing.items) == 24
    assert listing.total == 67613
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "martial-peak"
    assert first.title == "Martial Peak"
    assert first.cover_url == f"{THUMB_BASE}rm/martial-peak.jpg"
    assert first.canonical_path == "/manga/martial-peak"
    assert first.status == "Ongoing"
    assert first.author and "Momo" in first.author
    assert "Action" in first.genres
    assert first.latest_chapter == "Chapter 3862"


def test_parse_second_page_keeps_paging_coherent():
    listing = parse_series_list(_load("search_popular_p2.json"), page=2)
    assert len(listing.items) == 24
    assert listing.page == 2
    assert listing.has_more is True
    first_page_ids = {s.id for s in parse_series_list(_load("search_popular_p1.json"), page=1).items}
    assert not (first_page_ids & {s.id for s in listing.items})


def test_parse_latest_listing():
    listing = parse_series_list(_load("search_latest_p1.json"), page=1)
    assert len(listing.items) == 24
    assert all(item.id and item.title for item in listing.items)


def test_parse_search_results():
    listing = parse_series_list(_load("search_query_solo.json"), page=1)
    assert listing.total == 9
    assert listing.has_more is False
    assert listing.items[0].id == SERIES_KEY
    assert listing.items[0].title == "Solo Leveling"


def test_parse_empty_search_is_not_an_error():
    listing = parse_series_list(_load("search_query_empty_result.json"), page=1)
    assert listing.items == []
    assert listing.total == 0
    assert listing.has_more is False


def test_parse_genre_listing():
    listing = parse_genre_series_list(_load("genre_manga_action.json"), page=1)
    assert len(listing.items) == 24
    assert listing.total > 1000
    assert all(item.cover_url and item.cover_url.startswith(THUMB_BASE) for item in listing.items)


def test_parse_genres():
    genres = parse_genres(_load("genres.json"))
    assert len(genres) == 132
    slugs = {mode.id for mode in genres}
    assert {"action", "adventure", "comedy", "drama"} <= slugs
    assert all(mode.label for mode in genres)


# --- detail / chapter parsing -----------------------------------------------


def test_parse_series_detail():
    series = parse_series_detail(_load("manga_solo_leveling.json"), SERIES_KEY)
    assert series is not None
    assert series.id == SERIES_KEY
    assert series.title == "Solo Leveling"
    assert series.chapter_count == 204
    assert series.status == "Completed"
    assert series.cover_url == f"{THUMB_BASE}mh/solo-leveling.jpg"
    assert series.author and "Chugong" in series.author
    assert series.artist and "REDICE" in series.artist
    assert series.description and "Hunters" in series.description
    assert "Action" in series.genres and len(series.genres) == 14
    assert series.latest_chapter == "Chapter 200.5 {NOTICE}"


def test_parse_series_detail_returns_none_for_a_missing_slug():
    """A missing series is HTTP 200 with data.manga = null -- no 404 exists."""
    payload = _load("manga_missing.json")
    assert graphql_errors(payload)
    assert parse_series_detail(payload, "definitely-not-real-zzz") is None
    assert parse_chapters(payload, "definitely-not-real-zzz") == []


def test_parse_chapters_from_the_same_detail_response():
    chapters = parse_chapters(_load("manga_solo_leveling.json"), SERIES_KEY)
    assert len(chapters) == 204
    numbers = [chapter.number for chapter in chapters]
    assert numbers == sorted(numbers)
    assert chapters[0].id == f"{SERIES_KEY}/0"
    assert chapters[-1].id == f"{SERIES_KEY}/200.5"
    assert chapters[-1].number == 200.5
    assert chapters[-1].title == "Chapter 200.5 {NOTICE}"
    assert chapters[-1].release_date == "2024-07-13T06:00:55.000Z"
    assert all(chapter.series_id == SERIES_KEY for chapter in chapters)


def test_chapters_with_a_blank_upstream_title_fall_back_to_the_number():
    """Old MangaHub rows carry title="" -- the site renders "Chapter N"."""
    chapters = parse_chapters(_load("manga_solo_leveling.json"), SERIES_KEY)
    by_number = {chapter.number: chapter for chapter in chapters}
    assert by_number[1.0].title == "Chapter 1"
    assert by_number[0.0].title == "Chapter 0"


def test_parse_villain_detail_and_chapters():
    payload = _load("manga_villain.json")
    series = parse_series_detail(payload, VILLAIN_KEY)
    assert series is not None
    assert series.chapter_count == 47
    assert series.status == "Ongoing"
    chapters = parse_chapters(payload, VILLAIN_KEY)
    assert chapters[-1].id == f"{VILLAIN_KEY}/46"
    assert chapters[-1].title == "Chapter 46"


# --- page parsing -----------------------------------------------------------


def test_parse_chapter_pages():
    key = f"{SERIES_KEY}/1"
    pages = parse_chapter_pages(_load("chapter_solo_1.json"), key)
    assert len(pages) == 22
    assert pages[0].id == f"{key}:1"
    assert pages[0].chapter_id == key
    assert pages[0].number == 1
    assert pages[0].remote_url == f"{IMAGE_BASE}solo-leveling/1/1.jpg"
    assert pages[-1].number == 22
    assert pages[-1].remote_url == f"{IMAGE_BASE}solo-leveling/1/22.jpg"


def test_parse_chapter_pages_uses_the_payload_directory_and_extension():
    """The 'p' prefix is authoritative: extensions vary and slugs are aliased."""
    key = f"{VILLAIN_KEY}/46"
    pages = parse_chapter_pages(_load("chapter_villain_46.json"), key)
    assert len(pages) == 33
    assert all(page.remote_url.endswith(".webp") for page in pages)
    assert pages[0].remote_url == f"{IMAGE_BASE}{VILLAIN_KEY}/46/1.webp"


def test_parse_chapter_pages_of_a_missing_chapter_is_empty():
    payload = _load("chapter_missing.json")
    assert graphql_errors(payload)
    assert parse_chapter_pages(payload, f"{SERIES_KEY}/99999") == []


def test_rate_limit_detection():
    limited = _load("chapter_rate_limited.json")
    assert is_rate_limited(limited) is True
    assert parse_chapter_pages(limited, f"{SERIES_KEY}/5") == []
    assert is_rate_limited(_load("chapter_solo_1.json")) is False
    assert is_rate_limited(_load("manga_missing.json")) is False


# --- connector wiring -------------------------------------------------------


class FakeApi:
    """Stands in for ``SyncConnectorHttpClient.get_json``, recording queries.

    Patched onto the class as a plain (non-function) attribute, so it is NOT
    bound as a method and receives no ``self`` -- which is what lets one fake
    serve both the metadata client and the rotating chapter client.
    """

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.queries: list[str] = []
        self.responses = responses or []
        self.default: dict[str, Any] = {"data": {}}
        self.routes: dict[str, dict[str, Any]] = {}

    def __call__(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        assert path == "/graphql"
        query = params["query"]
        self.queries.append(query)
        if self.responses:
            return self.responses.pop(0)
        for marker, payload in self.routes.items():
            if marker in query:
                return payload
        return self.default


def _connector_with(api: FakeApi) -> MangaHubConnector:
    return MangaHubConnector()


@pytest.fixture()
def api() -> FakeApi:
    return FakeApi()


def test_descriptor_and_image_allowlist():
    connector = MangaHubConnector()
    assert connector.source_type == "mangahub"
    assert connector.display_name == "MangaHub"
    assert connector.is_browsable is True
    assert connector.is_mature is False
    assert connector.content_kind == "manga"
    hosts = connector.allowed_image_hosts
    from connectors.http.redirect_policy import host_matches_allowlist

    assert host_matches_allowlist("imgx.mghcdn.com", hosts)
    assert host_matches_allowlist("thumb.mghcdn.com", hosts)
    # Suffix matching must respect the dot boundary.
    assert not host_matches_allowlist("evilmghcdn.com", hosts)
    assert not host_matches_allowlist("mghubcdn.com", hosts)


def test_browse_modes_and_offsets(api: FakeApi):
    api.default = _load("search_popular_p1.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        listing = connector.get_series_list(3, sort="latest")
    assert len(api.queries) == 1
    assert "mod:LATEST" in api.queries[0]
    assert f"offset:{2 * PAGE_SIZE}" in api.queries[0]
    assert listing.page == 3


def test_search_delegates_to_browse_when_the_query_is_blank(api: FakeApi):
    api.default = _load("search_popular_p1.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        connector.search_series("   ", 1)
    assert len(api.queries) == 1
    assert 'q:""' in api.queries[0]


def test_detail_and_chapter_list_share_a_single_request(api: FakeApi):
    """The anti-pattern this source avoids natively: one fetch, both answers."""
    api.default = _load("manga_solo_leveling.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)
        again = connector.get_series(SERIES_KEY)
    assert series is not None and again is not None
    assert series.chapter_count == 204
    assert len(chapters) == 204
    assert len(api.queries) == 1, "detail + chapter list must cost ONE request"


def test_missing_series_does_not_raise(api: FakeApi):
    api.default = _load("manga_missing.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        assert connector.get_series("definitely-not-real-zzz") is None
        assert connector.get_chapters("definitely-not-real-zzz") == []


def test_transport_failure_on_detail_is_swallowed():
    # A plain function patched onto the class IS bound, so it takes self.
    def boom(_client, _path, *, params):
        raise ConnectorHttpError("Client error '404 Not Found' for url ...")

    connector = MangaHubConnector()
    with patch.object(SyncConnectorHttpClient, "get_json", boom):
        assert connector.get_series(SERIES_KEY) is None
        assert connector.get_chapters(SERIES_KEY) == []
        assert connector.get_chapter_pages(f"{SERIES_KEY}/1") == []


def test_chapter_pages_cost_one_request_and_then_cache(api: FakeApi):
    api.default = _load("chapter_solo_1.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        pages = connector.get_chapter_pages(f"{SERIES_KEY}/1")
        cached = connector.get_chapter_pages(f"{SERIES_KEY}/1")
    assert len(pages) == 22
    assert cached == pages
    assert len(api.queries) == 1
    assert f'slug:"{SERIES_KEY}"' in api.queries[0] and "number:1)" in api.queries[0]


def test_find_page_resolves_without_refetching(api: FakeApi):
    api.default = _load("chapter_solo_1.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        pages = connector.get_chapter_pages(f"{SERIES_KEY}/1")
        found = connector.find_page(pages[4].id)
        missing = connector.find_page(f"{SERIES_KEY}/1:999")
    assert found is not None
    assert found.remote_url == f"{IMAGE_BASE}solo-leveling/1/5.jpg"
    assert missing is None
    assert len(api.queries) == 1


def test_find_page_rejects_a_key_without_a_page_marker(api: FakeApi):
    """A page id must carry the ``:N`` marker, and a miss must cost no request.

    The interesting input is a string that is a perfectly valid *chapter* key:
    if find_page treated it as one it would happily fetch the chapter and hand
    back page 1 for an id that names no page at all.
    """
    api.default = _load("chapter_solo_1.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        assert connector.find_page(f"{SERIES_KEY}/1") is None
        assert connector.find_page("no-colon-here") is None
    assert api.queries == [], "an unmarked page id must not reach the network"


def test_page_count_backfills_into_the_chapter_list(api: FakeApi):
    api.routes = {
        "manga(": _load("manga_solo_leveling.json"),
        "chapter(": _load("chapter_solo_1.json"),
    }
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        assert connector.get_chapters(SERIES_KEY)[1].page_count == 0
        connector.get_chapter_pages(f"{SERIES_KEY}/1")
        refreshed = connector.get_chapters(SERIES_KEY)
    by_number = {chapter.number: chapter for chapter in refreshed}
    assert by_number[1.0].page_count == 22


def test_a_spent_access_nonce_is_rotated_and_retried_once():
    """The API answers 200 for a refusal, so the retry is decided on the body."""
    api = FakeApi([_load("chapter_rate_limited.json"), _load("chapter_solo_1.json")])
    connector = MangaHubConnector()
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        pages = connector.get_chapter_pages(f"{SERIES_KEY}/1")
    assert len(pages) == 22
    assert len(api.queries) == 2, "exactly one retry with a fresh nonce"


def test_a_persistent_refusal_gives_up_instead_of_looping():
    api = FakeApi(
        [_load("chapter_rate_limited.json"), _load("chapter_rate_limited.json")]
    )
    connector = MangaHubConnector()
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        assert connector.get_chapter_pages(f"{SERIES_KEY}/1") == []
    assert len(api.queries) == 2


def test_the_nonce_budget_rotates_the_chapter_client_proactively(api: FakeApi):
    """Each nonce is spent to its measured four-call budget, then replaced."""
    api.default = _load("chapter_solo_1.json")
    connector = _connector_with(api)
    seen: list[str | None] = []
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        for number in range(1, TOKEN_CHAPTER_BUDGET * 2 + 1):
            connector.get_chapter_pages(f"{SERIES_KEY}/{number}")
            client = connector._chapter_http
            seen.append(None if client is None else client._client.headers.get("x-mhub-access"))
    assert len(api.queries) == TOKEN_CHAPTER_BUDGET * 2
    assert all(token for token in seen)
    # One nonce covers its budget, then a different one takes over.
    assert len(set(seen)) == 2
    assert seen[0] == seen[TOKEN_CHAPTER_BUDGET - 1]
    assert seen[TOKEN_CHAPTER_BUDGET] != seen[0]


def test_genres_are_cached_after_the_first_lookup(api: FakeApi):
    api.default = _load("genres.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        first = connector.list_genres()
        second = connector.list_genres()
    assert len(first) == 132
    assert second == first
    assert len(api.queries) == 1


def test_genre_browse_uses_the_genre_query(api: FakeApi):
    api.default = _load("genre_manga_action.json")
    connector = _connector_with(api)
    with patch.object(SyncConnectorHttpClient, "get_json", api):
        listing = connector.browse_by_genre("action", 2, sort="latest")
    assert "genreManga(" in api.queries[0]
    assert f"offset:{PAGE_SIZE}" in api.queries[0]
    assert len(listing.items) == 24
