"""Flame Comics connector tests.

Every fixture under ``tests/fixtures/flamecomics/`` was captured FROM THE VPS
(production egress + TLS, 2026-09-04) against the live site, and the parse
tests below were each watched to FAIL first against a deliberately broken
selector before being kept.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.flamecomics.connector import FlameComicsConnector
from connectors.flamecomics.mappers import (
    CDN_BASE,
    make_chapter_key,
    page_id_chapter_key,
    parse_build_id,
    parse_catalog,
    parse_catalog_rankings,
    parse_chapter_pages,
    parse_chapters,
    parse_latest_feed,
    parse_series_detail,
    split_chapter_key,
)
from connectors.http.client import ConnectorHttpError

FIXTURES = Path(__file__).parent / "fixtures" / "flamecomics"

#: The chapter fixture's own coordinates, used to assert real CDN URLs.
CHAPTER_SERIES = "165"
CHAPTER_TOKEN = "ef45b23357dfef68"
CHAPTER_KEY = f"{CHAPTER_SERIES}/{CHAPTER_TOKEN}"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _json(name: str) -> dict:
    return json.loads(_text(name))


@pytest.fixture
def connector() -> FlameComicsConnector:
    return FlameComicsConnector()


@pytest.fixture
def wired(connector: FlameComicsConnector):
    """Drive the connector off the captured payloads, counting requests.

    Routes by path exactly as the live site does, so the tests exercise the
    real path-building code rather than a stub that accepts anything.
    """
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        if path == "/info/about":
            return _text("info_about.html")
        raise ConnectorHttpError(f"Client error '404 Not Found' for url '{path}'")

    def fake_get_json(path: str, *, params=None) -> dict:
        calls.append(path)
        if path.endswith("/browse.json"):
            return _json("browse.json")
        if path.endswith("/latest.json"):
            return _json("latest.json")
        if path.endswith(f"/series/{CHAPTER_SERIES}/{CHAPTER_TOKEN}.json"):
            return _json(f"chapter_{CHAPTER_SERIES}_{CHAPTER_TOKEN}.json")
        if path.endswith("/series/165.json"):
            return _json("series_165.json")
        if path.endswith("/series/127.json"):
            return _json("series_127.json")
        raise ConnectorHttpError(f"Client error '404 Not Found' for url '{path}'")

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "get_json", side_effect=fake_get_json),
    ):
        yield connector, calls


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def test_registry_lists_flamecomics_once_wired():
    """Registration lives in registry.py, which this connector does not own.

    Skips until the integrator adds the import/builtins/_CONFIGLESS entries,
    then guards them for real.
    """
    from connectors.registry import list_installed_connectors

    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    if "flamecomics" not in browsable:
        pytest.skip("flamecomics not yet wired into registry.py (owned by the integrator)")
    assert "flamecomics" in browsable


def test_connector_satisfies_the_configless_registry_contract():
    """It takes no config, so it belongs in `_CONFIGLESS_CONNECTORS` and must
    be constructible with no arguments (the registry caches one instance)."""
    assert FlameComicsConnector() is not None
    assert FlameComicsConnector.SOURCE_TYPE == "flamecomics"


def test_source_type_is_distinct_from_flamescans(connector: FlameComicsConnector):
    """flamecomics.xyz and the pre-existing `flamescans` connector are
    different sites; the keys must not collide."""
    assert connector.source_type == "flamecomics"
    assert connector.display_name == "Flame Comics"


# ---------------------------------------------------------------------------
# build id
# ---------------------------------------------------------------------------


def test_parse_build_id_from_captured_page():
    assert parse_build_id(_text("info_about.html")) == "B_GElpRjUCmSg9QJX9Gb1"


def test_parse_build_id_rejects_a_page_without_one():
    assert parse_build_id("<html><body>no next data here</body></html>") is None


def test_parse_build_id_rejects_a_value_that_would_escape_the_route():
    assert parse_build_id('{"buildId":"../../etc/passwd"}') is None


# ---------------------------------------------------------------------------
# catalog / browse / search
# ---------------------------------------------------------------------------


def test_parse_catalog_reads_every_comic_series():
    catalog = parse_catalog(_json("browse.json"))
    # 166 catalog entries at capture time, 13 of them novels.
    assert len(catalog) == 153
    by_id = {series.id: series for series in catalog}
    entry = by_id["165"]
    assert entry.title == "30 Years Have Passed Since the Prologue"
    assert entry.author == "Markellaha"
    assert entry.artist == "Studio GreenKirin"
    assert entry.status == "Ongoing"
    assert "Academy" in entry.genres and "Fantasy" in entry.genres
    assert entry.canonical_path == "https://flamecomics.xyz/series/165"


def test_catalog_drops_novels_that_share_the_browse_payload():
    """Novels live in the same catalog under `novel_id` and are served from
    /novel/<id>, a route this manga connector never builds — including them
    would produce series whose every subsequent request 404s."""
    payload = _json("browse.json")
    entries = payload["pageProps"]["series"]
    novels = [item for item in entries if "novel_id" in item]
    assert novels, "fixture must contain novels for this test to mean anything"

    catalog = parse_catalog(payload)
    assert len(catalog) == len(entries) - len(novels)

    # Only `series_id` can discriminate. Titles cannot: Flame Comics carries
    # both a novel and its comic adaptation under the same name (novel 1 and
    # series 20 are both "I Killed The Immortal"). Ids cannot be compared
    # across the two either — novel_id and series_id are separate numeric
    # namespaces that overlap. So: the catalog must be exactly the entries
    # that had a series_id.
    assert {series.id for series in catalog} == {
        str(item["series_id"]) for item in entries if item.get("series_id") is not None
    }
    assert all(series.id.isdigit() for series in catalog)


def test_catalog_cover_urls_point_at_the_cdn_with_a_cache_buster():
    catalog = parse_catalog(_json("browse.json"))
    entry = next(series for series in catalog if series.id == "165")
    assert entry.cover_url == (
        f"{CDN_BASE}/uploads/images/series/165/thumbnail.webp?1786358505"
    )


def test_series_descriptions_are_stripped_of_mantine_markup():
    """The DETAIL payload stores the description as Mantine-classed HTML
    paragraphs (the browse payload is already plain text — pointing this test
    at browse.json would prove nothing, which is how it was caught)."""
    raw = _json("series_165.json")["pageProps"]["series"]["description"]
    assert '<p class="mantine' in raw, "fixture must be HTML for this test to discriminate"

    series = parse_series_detail(_json("series_165.json"), "165")
    assert series.description is not None
    assert "<" not in series.description and "mantine" not in series.description
    assert series.description.startswith("I 'transmigrated' into a world I've never seen.")
    # Paragraph boundaries must not glue sentences together.
    assert "seen.I spent" not in series.description
    assert "I spent 30 years" in series.description


def test_catalog_descriptions_survive_as_plain_text():
    catalog = parse_catalog(_json("browse.json"))
    entry = next(series for series in catalog if series.id == "165")
    assert entry.description is not None
    assert entry.description.startswith("I 'transmigrated' into a world I've never seen.")


def test_popular_ordering_follows_the_sites_popularity_rank():
    payload = _json("browse.json")
    catalog = parse_catalog(payload)
    ranks, _added = parse_catalog_rankings(payload)
    assert ranks["2"] == 1

    from connectors.flamecomics.mappers import order_catalog

    ordered = order_catalog(catalog, ranks, {}, "popular")
    assert [series.id for series in ordered[:3]] == ["2", "23", "104"]
    assert ordered[0].title == "Omniscient Reader's Viewpoint"


def test_browse_modes_produce_genuinely_different_orderings(wired):
    connector, _calls = wired
    popular = connector.get_series_list(1, sort="popular")
    alphabetical = connector.get_series_list(1, sort="alphabetical")
    newest = connector.get_series_list(1, sort="new")
    latest = connector.get_series_list(1, sort="default")

    heads = {
        "popular": popular.items[0].id,
        "alphabetical": alphabetical.items[0].id,
        "new": newest.items[0].id,
        "latest": latest.items[0].id,
    }
    assert len(set(heads.values())) >= 3, heads
    assert alphabetical.items[0].title.startswith("30 Years")


def test_parse_latest_feed_is_sorted_by_newest_chapter():
    feed = parse_latest_feed(_json("latest.json"))
    assert len(feed) == 153
    assert feed[0].id == "164"
    assert feed[0].latest_chapter == "Chapter 12 - Test of Courage"
    # The upstream feed is only approximately ordered; ours must be exact.
    payload = _json("latest.json")
    newest = {
        str(item["series_id"]): max(
            (chapter["release_date"] for chapter in item.get("chapters") or []),
            default=0,
        )
        for item in payload["pageProps"]["allSeries"]
        if "series_id" in item
    }
    stamps = [newest[series.id] for series in feed]
    assert stamps == sorted(stamps, reverse=True)


def test_pagination_slices_the_single_catalog_payload(wired):
    connector, _calls = wired
    first = connector.get_series_list(1, sort="alphabetical")
    second = connector.get_series_list(2, sort="alphabetical")
    assert first.total == second.total == 153
    assert len(first.items) == 30
    assert first.has_more is True
    assert first.items[0].id != second.items[0].id
    assert not ({s.id for s in first.items} & {s.id for s in second.items})


def test_search_matches_title_author_and_genre(wired):
    connector, _calls = wired
    assert [s.title for s in connector.search_series("regressor", 1).items] == [
        "A Regressor's Tale of Cultivation"
    ]
    by_author = connector.search_series("Sing-Shong", 1)
    assert "Omniscient Reader's Viewpoint" in {s.title for s in by_author.items}


def test_search_ranks_title_matches_above_incidental_matches(wired):
    connector, _calls = wired
    results = connector.search_series("tower", 1)
    assert results.items, "expected at least one hit"
    assert "tower" in results.items[0].title.lower()


# ---------------------------------------------------------------------------
# series detail + chapters
# ---------------------------------------------------------------------------


def test_parse_series_detail_from_captured_payload():
    series = parse_series_detail(_json("series_165.json"), "165")
    assert series is not None
    assert series.id == "165"
    assert series.title == "30 Years Have Passed Since the Prologue"
    assert series.status == "Ongoing"
    assert series.author == "Markellaha"
    assert series.chapter_count == 14
    assert series.latest_chapter == "Chapter 14 - The Saintess and the Lumberjack (2)"
    assert "Academy" in series.genres


def test_parse_chapters_is_ascending_and_keys_carry_the_token():
    chapters = parse_chapters(_json("series_165.json"), "165")
    assert len(chapters) == 14
    numbers = [chapter.number for chapter in chapters]
    assert numbers == sorted(numbers)
    assert numbers[0] == 1.0 and numbers[-1] == 14.0
    assert chapters[-1].id == CHAPTER_KEY
    assert chapters[-1].series_id == "165"
    assert chapters[-1].title == "Chapter 14 - The Saintess and the Lumberjack (2)"
    assert chapters[-1].release_date == "1788408688"
    assert all(chapter.id.startswith("165/") for chapter in chapters)


def test_parse_chapters_handles_a_long_series():
    chapters = parse_chapters(_json("series_127.json"), "127")
    assert len(chapters) == 152
    assert chapters[0].number == 1.0
    assert chapters[-1].number == 152.0
    assert len({chapter.id for chapter in chapters}) == len(chapters)


def test_series_detail_and_chapter_list_share_one_request(wired):
    """The anti-pattern this guards against: fetching the series payload once
    for the detail and again for the chapter list. Opening a series calls both,
    so the second must be served from the shared cache entry."""
    connector, calls = wired
    connector.get_series("165")
    after_detail = [call for call in calls if call.endswith("/series/165.json")]
    connector.get_chapters("165")
    after_chapters = [call for call in calls if call.endswith("/series/165.json")]

    assert len(after_detail) == 1
    assert len(after_chapters) == 1, "get_chapters refetched the series payload"


def test_search_after_browse_costs_no_extra_request(wired):
    connector, calls = wired
    connector.get_series_list(1, sort="popular")
    before = len(calls)
    connector.search_series("regressor", 1)
    connector.search_series("tower", 1)
    connector.list_genres()
    connector.browse_by_genre("Action", 1)
    assert len(calls) == before, calls[before:]


def test_missing_series_returns_none_without_masking_real_errors(wired):
    connector, _calls = wired
    assert connector.get_series("999999") is None
    assert connector.get_chapters("999999") == []


def test_transport_failure_propagates_rather_than_looking_empty(
    connector: FlameComicsConnector,
):
    """A 503 is not "this series has no chapters" — the caller must be able to
    tell an upstream outage from a genuinely missing series."""

    def fake_get_text(path: str, *, params=None) -> str:
        return _text("info_about.html")

    def fake_get_json(path: str, *, params=None) -> dict:
        raise ConnectorHttpError("Retryable HTTP 503", status_code=503)

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "get_json", side_effect=fake_get_json),
        pytest.raises(ConnectorHttpError),
    ):
        connector.get_series("165")


# ---------------------------------------------------------------------------
# chapter pages
# ---------------------------------------------------------------------------


def test_parse_chapter_pages_builds_every_cdn_url_from_one_manifest():
    pages = parse_chapter_pages(
        _json(f"chapter_{CHAPTER_SERIES}_{CHAPTER_TOKEN}.json"), CHAPTER_KEY
    )
    assert len(pages) == 22
    assert [page.number for page in pages] == list(range(1, 23))
    # Verified fetchable from the VPS: 200, image/jpeg, 806798 bytes.
    assert pages[0].remote_url == (
        f"{CDN_BASE}/uploads/images/series/165/{CHAPTER_TOKEN}/00.jpg?1788409125"
    )
    assert pages[1].remote_url == (
        f"{CDN_BASE}/uploads/images/series/165/{CHAPTER_TOKEN}"
        "/30YRS-14-01.jpg?1788409125"
    )
    assert pages[0].width == 1778 and pages[0].height == 1000
    assert pages[1].width == 690 and pages[1].height == 9350
    assert all(page.chapter_id == CHAPTER_KEY for page in pages)


def test_chapter_pages_use_the_token_not_the_chapter_id():
    """The reader bundle builds /series/<series_id>/<TOKEN>/<name>; using the
    numeric chapter_id (12173) instead yields a 404 from the CDN — checked
    against the live CDN from the VPS."""
    payload = _json(f"chapter_{CHAPTER_SERIES}_{CHAPTER_TOKEN}.json")
    assert payload["pageProps"]["chapter"]["chapter_id"] == 12173
    pages = parse_chapter_pages(payload, CHAPTER_KEY)
    assert "/12173/" not in pages[0].remote_url
    assert f"/{CHAPTER_TOKEN}/" in pages[0].remote_url


def test_chapter_pages_are_ordered_numerically_not_lexicographically():
    """`images` is keyed by stringified index, where "10" sorts before "2".
    Ordering by string would scramble the read order of any chapter with more
    than nine pages — this one has 22."""
    payload = _json(f"chapter_{CHAPTER_SERIES}_{CHAPTER_TOKEN}.json")
    images = payload["pageProps"]["chapter"]["images"]
    expected = [images[key]["name"] for key in sorted(images, key=int)]
    pages = parse_chapter_pages(payload, CHAPTER_KEY)
    assert [page.remote_url.rsplit("/", 1)[1].split("?")[0] for page in pages] == expected
    assert expected != [images[key]["name"] for key in sorted(images)], (
        "fixture must have >9 pages for this test to discriminate"
    )


def test_chapter_pages_skip_decoy_entries():
    """The site's own reader filters `decoy` images and nameless entries. No
    live chapter carried one when sampled from the VPS, so this exercises the
    guard against the site switching the feature on."""
    payload = deepcopy(_json(f"chapter_{CHAPTER_SERIES}_{CHAPTER_TOKEN}.json"))
    images = payload["pageProps"]["chapter"]["images"]
    baseline = len(parse_chapter_pages(payload, CHAPTER_KEY))
    images["3"]["decoy"] = True
    images["5"]["name"] = ""

    pages = parse_chapter_pages(payload, CHAPTER_KEY)
    assert len(pages) == baseline - 2
    assert [page.number for page in pages] == list(range(1, baseline - 1))
    assert all("decoy" not in (page.remote_url or "") for page in pages)


def test_find_page_resolves_from_the_page_id_alone(wired):
    connector, calls = wired
    pages = connector.get_chapter_pages(CHAPTER_KEY)
    before = len(calls)
    found = connector.find_page(pages[7].id)
    assert found is not None
    assert found.id == pages[7].id
    assert found.remote_url == pages[7].remote_url
    assert len(calls) == before, "find_page must not refetch a cached chapter"


def test_find_page_does_not_walk_the_catalog(connector: FlameComicsConnector):
    """find_page must resolve via the chapter key embedded in the page id.
    A traversal of every series would be O(catalog) upstream requests per
    proxied image."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        return _text("info_about.html")

    def fake_get_json(path: str, *, params=None) -> dict:
        calls.append(path)
        if path.endswith(f"/series/{CHAPTER_SERIES}/{CHAPTER_TOKEN}.json"):
            return _json(f"chapter_{CHAPTER_SERIES}_{CHAPTER_TOKEN}.json")
        raise AssertionError(f"find_page fetched an unrelated path: {path}")

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "get_json", side_effect=fake_get_json),
    ):
        page = connector.find_page(f"{CHAPTER_KEY}:3")

    assert page is not None and page.number == 3
    assert sum(1 for call in calls if "/series/" in call) == 1


def test_find_page_rejects_malformed_ids_without_touching_the_network(
    connector: FlameComicsConnector,
):
    """A malformed page id must be rejected by shape alone. The original
    version of this test asserted only `is None` and passed even with the
    digit guard removed — because the connector then went to the *network*
    and got nothing back. Counting requests is what makes it discriminate."""
    calls: list[str] = []

    def boom(path: str, *, params=None):
        calls.append(path)
        raise AssertionError(f"malformed page id caused a request: {path}")

    with (
        patch.object(connector._http, "get_text", side_effect=boom),
        patch.object(connector._http, "get_json", side_effect=boom),
    ):
        assert connector.find_page("") is None
        assert connector.find_page("no-separator") is None
        assert connector.find_page("165/token:notanumber") is None
        assert connector.find_page(":5") is None

    assert calls == []


# ---------------------------------------------------------------------------
# identity keys
# ---------------------------------------------------------------------------


def test_chapter_keys_round_trip_through_page_ids():
    key = make_chapter_key("165", CHAPTER_TOKEN)
    assert key == CHAPTER_KEY
    assert split_chapter_key(key) == ("165", CHAPTER_TOKEN)
    assert page_id_chapter_key(f"{key}:12") == key


def test_series_keys_accept_paths_and_urls():
    from connectors.flamecomics.mappers import normalize_series_key

    assert normalize_series_key("165") == "165"
    assert normalize_series_key("/series/165") == "165"
    assert normalize_series_key("https://flamecomics.xyz/series/165") == "165"


# ---------------------------------------------------------------------------
# stale build id
# ---------------------------------------------------------------------------


def test_stale_build_id_is_refreshed_and_the_request_retried(
    connector: FlameComicsConnector,
):
    """A site redeploy invalidates the cached buildId and every /_next/data
    route 404s. The connector must re-resolve the id and retry once rather
    than reporting the whole source as empty until its TTL expires."""
    connector._build_id_cache.set("browse", "STALE_BUILD")
    served: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        return _text("info_about.html")  # carries B_GElpRjUCmSg9QJX9Gb1

    def fake_get_json(path: str, *, params=None) -> dict:
        served.append(path)
        if "STALE_BUILD" in path:
            raise ConnectorHttpError(f"Client error '404 Not Found' for url '{path}'")
        return _json("series_165.json")

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "get_json", side_effect=fake_get_json),
    ):
        series = connector.get_series("165")

    assert series is not None and series.title.startswith("30 Years")
    assert len(served) == 2
    assert "STALE_BUILD" in served[0]
    assert "B_GElpRjUCmSg9QJX9Gb1" in served[1]


def test_genuine_404_is_not_retried_forever(connector: FlameComicsConnector):
    """When the build id comes back unchanged the 404 was real; the connector
    must stop rather than loop."""
    attempts: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        return _text("info_about.html")

    def fake_get_json(path: str, *, params=None) -> dict:
        attempts.append(path)
        raise ConnectorHttpError(f"Client error '404 Not Found' for url '{path}'")

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "get_json", side_effect=fake_get_json),
    ):
        assert connector.get_series("999999") is None

    assert len(attempts) == 1


def test_not_found_detection_matches_both_error_shapes():
    """SyncConnectorHttpClient only sets status_code for RETRYABLE_STATUS, so a
    404 can arrive with status_code=None and only the httpx message. Checking
    status_code alone would be dead code."""
    from connectors.flamecomics.connector import _is_not_found

    assert _is_not_found(ConnectorHttpError("boom", status_code=404))
    assert _is_not_found(
        ConnectorHttpError("Client error '404 Not Found' for url 'https://x/y'")
    )
    assert not _is_not_found(ConnectorHttpError("Retryable HTTP 503", status_code=503))


# ---------------------------------------------------------------------------
# image proxy allowlist
# ---------------------------------------------------------------------------


def test_allowed_image_hosts_covers_the_cdn_actually_used(
    connector: FlameComicsConnector,
):
    """The image proxy rejects any host not on this list, so a mismatch here
    makes every cover and page image unreadable."""
    pages = parse_chapter_pages(
        _json(f"chapter_{CHAPTER_SERIES}_{CHAPTER_TOKEN}.json"), CHAPTER_KEY
    )
    catalog = parse_catalog(_json("browse.json"))
    hosts = {"cdn.flamecomics.xyz"}
    allowed = connector.allowed_image_hosts

    for url in [pages[0].remote_url, catalog[0].cover_url]:
        host = url.split("/")[2]
        hosts.add(host)
        assert any(
            host == suffix or host.endswith(f".{suffix}") for suffix in allowed
        ), f"{host} is not covered by {allowed}"
