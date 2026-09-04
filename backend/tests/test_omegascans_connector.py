"""Omega Scans connector tests.

Fixtures under ``tests/fixtures/omegascans/`` were captured from INSIDE the
production ``manhwamaniacs-backend`` container on the OVH VPS (httpx 0.28.1,
production TLS stack), so they are byte-for-byte what production sees. The
``who_bought`` arrays the API embeds in chapter responses -- third-party user
ids -- were stripped before the fixtures were committed.

Every parse assertion here was watched to FAIL first against a deliberately
broken mapper (wrong JSON keys, dropped price filter, dropped sort table)
before the real mapper was restored; see the connector report.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.http.redirect_policy import host_matches_allowlist
from connectors.omegascans.connector import OmegaScansConnector, _is_not_found
from connectors.omegascans.mappers import (
    PAGE_SIZE,
    SITE_BASE,
    listing_params,
    make_page_id,
    page_id_chapter_id,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    parse_tags,
)

FIXTURES = Path(__file__).parent / "fixtures" / "omegascans"


def _load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def connector() -> OmegaScansConnector:
    return OmegaScansConnector()


class Recorder:
    """Stand-in for ``SyncConnectorHttpClient.get_json`` that counts calls."""

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, path: str, *, params: dict | None = None):
        self.calls.append((path, params))
        for prefix, payload in self.routes.items():
            if path == prefix or path.startswith(prefix):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unexpected request: {path} {params}")

    @property
    def paths(self) -> list[str]:
        return [path for path, _params in self.calls]


# ---------------------------------------------------------------------------
# connector identity
# ---------------------------------------------------------------------------


def test_connector_identity_and_mature_flag(connector: OmegaScansConnector):
    assert connector.source_type == "omegascans"
    assert connector.display_name == "Omega Scans"
    assert connector.content_kind == "manga"
    # Omega Scans' whole catalog is 18+; mis-flagging it would leak adult
    # covers into the default Sources browser.
    assert connector.is_mature is True


def test_allowed_image_hosts_cover_the_cdn_but_not_lookalikes(connector: OmegaScansConnector):
    hosts = connector.allowed_image_hosts
    assert host_matches_allowlist("media.omegascans.org", hosts)
    assert host_matches_allowlist("omegascans.org", hosts)
    # The SSRF allowlist must not be satisfied by a domain that merely ends
    # with the same letters.
    assert not host_matches_allowlist("notomegascans.org", hosts)
    assert not host_matches_allowlist("omegascans.org.evil.com", hosts)


def test_image_fetch_headers_send_site_referer(connector: OmegaScansConnector):
    assert connector.image_fetch_headers()["Referer"] == f"{SITE_BASE}/"


# ---------------------------------------------------------------------------
# listing / browse
# ---------------------------------------------------------------------------


def test_parse_series_list_from_fixture():
    listing = parse_series_list(_load("browse_page1"), page=1)
    assert len(listing.items) == 24
    assert listing.total == 284
    assert listing.has_more is True

    first = listing.items[0]
    assert first.id == "sex-stopwatch"
    assert first.title == "Sex Stopwatch"
    assert first.cover_url == (
        "https://media.omegascans.org/file/zFSsXt/vzq49pwb62fcuxfgmllu3cr1.webp"
    )
    assert first.canonical_path == "/series/sex-stopwatch"
    assert first.status == "Completed"
    assert first.chapter_count == 156
    # The listing's truncated free_chapters gives the card its latest label
    # without a second request.
    assert first.latest_chapter == "Chapter 155"
    # Descriptions arrive as HTML with entities; nothing tag-shaped may survive.
    assert first.description and "<p>" not in first.description
    assert "&ldquo;" not in first.description


def test_browse_page_two_returns_different_series(connector: OmegaScansConnector):
    recorder = Recorder({"/query": None})

    def route(path: str, *, params: dict | None = None):
        recorder.calls.append((path, params))
        return _load("browse_page2") if params and params["page"] == 2 else _load("browse_page1")

    with patch.object(connector._http, "get_json", side_effect=route):
        first = connector.get_series_list(1)
        second = connector.get_series_list(2)

    assert first.items[0].id == "sex-stopwatch"
    assert second.items[0].id == "intern-haenyeo"
    assert {s.id for s in first.items}.isdisjoint({s.id for s in second.items})


def test_last_catalog_page_reports_no_more():
    payload = _load("browse_page1")
    payload["meta"] = dict(payload["meta"], current_page=12, last_page=12)
    assert parse_series_list(payload, page=12).has_more is False


def test_every_browse_mode_requests_a_distinct_order_pair(connector: OmegaScansConnector):
    """Sort must actually reach the API.

    Omega Scans orders on ``orderBy`` + ``order``; a mode table that collapsed
    to one value would make all five exposed views identical while still
    looking fine in the UI.
    """
    seen: set[tuple[str, str]] = set()
    for mode in connector.list_browse_modes():
        params = listing_params(page=1, sort=mode.id)
        seen.add((params["orderBy"], params["order"]))
    assert len(seen) == len(connector.list_browse_modes())
    assert ("latest", "desc") in seen
    assert ("total_views", "desc") in seen
    assert ("title", "asc") in seen


def test_unknown_sort_falls_back_to_the_default_view():
    assert listing_params(page=1, sort="not-a-mode")["orderBy"] == "latest"


def test_listing_always_pins_series_type_comic():
    """Regression guard on an 11x payload difference measured from the VPS.

    Without ``series_type=Comic`` the API inlines every chapter of every
    series into each listing item: the same 12-item page weighed 275 KB
    without it and 25 KB with it. It also keeps the catalog's two Novel
    entries out of a manga source.
    """
    for sort in (None, "popular", "alphabetical"):
        assert listing_params(page=1, sort=sort)["series_type"] == "Comic"
    assert listing_params(page=1, query="x")["series_type"] == "Comic"


def test_browse_requests_the_query_endpoint_once_per_page(connector: OmegaScansConnector):
    recorder = Recorder({"/query": _load("browse_page1")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.get_series_list(3, sort="popular")
    assert recorder.paths == ["/query"]
    assert recorder.calls[0][1]["page"] == 3
    assert recorder.calls[0][1]["perPage"] == PAGE_SIZE


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_sends_query_string_and_parses_hits(connector: OmegaScansConnector):
    recorder = Recorder({"/query": _load("search_stopwatch")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        listing = connector.search_series("stopwatch", 1)

    assert recorder.calls[0][1]["query_string"] == "stopwatch"
    assert [s.id for s in listing.items] == ["sex-stopwatch"]
    assert listing.total == 1
    assert listing.has_more is False


def test_search_with_no_hits_is_empty_not_an_error(connector: OmegaScansConnector):
    recorder = Recorder({"/query": _load("search_empty")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        listing = connector.search_series("zzzznotarealtitle", 1)
    assert listing.items == []
    assert listing.has_more is False


def test_blank_search_falls_back_to_browse(connector: OmegaScansConnector):
    recorder = Recorder({"/query": _load("browse_page1")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        listing = connector.search_series("   ", 1)
    assert recorder.calls[0][1]["query_string"] == ""
    assert len(listing.items) == 24


# ---------------------------------------------------------------------------
# series detail
# ---------------------------------------------------------------------------


def test_parse_series_detail_from_fixture():
    series, numeric_id = parse_series_detail(_load("series_detail"), "sex-stopwatch")
    assert numeric_id == 7
    assert series is not None
    assert series.title == "Sex Stopwatch"
    assert series.author == "Serious"
    assert series.artist == "Toptoon"
    assert series.status == "Completed"
    assert series.genres == ("Fantasy",)
    # chapters_count comes free on the detail payload, so the chapter list is
    # never fetched just to show a count.
    assert series.chapter_count == 156
    assert series.description and "<p>" not in series.description


def test_get_series_does_not_fetch_the_chapter_list(connector: OmegaScansConnector):
    """The royalroad anti-pattern, guarded.

    Opening a series page must cost ONE request. If ``get_series`` ever calls
    ``get_chapters`` to fill ``chapter_count`` or ``latest_chapter``, this
    fails on the extra ``/chapter/query``.
    """
    recorder = Recorder({"/series/": _load("series_detail")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        series = connector.get_series("sex-stopwatch")
    assert series is not None
    assert recorder.paths == ["/series/sex-stopwatch"]


def test_series_detail_is_cached_across_calls(connector: OmegaScansConnector):
    recorder = Recorder({"/series/": _load("series_detail")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.get_series("sex-stopwatch")
        connector.get_series("sex-stopwatch")
    assert len(recorder.paths) == 1


def test_series_canonical_path_is_accepted_as_a_key(connector: OmegaScansConnector):
    recorder = Recorder({"/series/": _load("series_detail")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        series = connector.get_series("/series/sex-stopwatch")
    assert series is not None and series.id == "sex-stopwatch"
    assert recorder.paths == ["/series/sex-stopwatch"]


# ---------------------------------------------------------------------------
# the 404 trap
# ---------------------------------------------------------------------------


def test_not_found_matches_both_error_shapes():
    """``SyncConnectorHttpClient`` does not always attach ``status_code``.

    A bare ``exc.status_code == 404`` check is dead code for a non-retryable
    status, so the helper must also recognise httpx's raise_for_status text.
    """
    assert _is_not_found(ConnectorHttpError("boom", status_code=404)) is True
    assert _is_not_found(
        ConnectorHttpError("Client error '404 Not Found' for url 'https://api.omegascans.org/series/x'")
    ) is True
    assert _is_not_found(ConnectorHttpError("Retryable HTTP 503", status_code=503)) is False


def test_missing_series_returns_none(connector: OmegaScansConnector):
    error = ConnectorHttpError("Client error '404 Not Found' for url 'https://x/series/nope'")
    with patch.object(connector._http, "get_json", side_effect=error):
        assert connector.get_series("no-such-series-xyz") is None


def test_missing_chapter_returns_no_pages(connector: OmegaScansConnector):
    error = ConnectorHttpError("Client error '404 Not Found' for url 'https://x/chapter/a/b'")
    with patch.object(connector._http, "get_json", side_effect=error):
        assert connector.get_chapter_pages("sex-stopwatch/chapter-99999") == []


# ---------------------------------------------------------------------------
# chapters
# ---------------------------------------------------------------------------


def test_parse_chapters_from_fixture():
    chapters = parse_chapters([_load("chapters")], "sex-stopwatch")
    assert len(chapters) == 156
    # Ascending by the site's own numbering, oldest first.
    assert chapters[0].number == 1.0
    assert chapters[-1].number == 155.0
    assert [c.number for c in chapters] == sorted(c.number for c in chapters)

    first = chapters[0]
    assert first.id == "sex-stopwatch/chapter-1"
    assert first.series_id == "sex-stopwatch"
    assert first.title == "Chapter 1"
    assert first.release_date is not None

    last = chapters[-1]
    assert last.id == "sex-stopwatch/chapter-155"
    # chapter_title is appended when the site supplies one.
    assert last.title == "Chapter 155 - END"


def test_chapter_keys_are_unique_and_slash_shaped():
    chapters = parse_chapters([_load("chapters_alt")], "glory-hole-shop")
    assert len(chapters) == 162
    keys = [c.id for c in chapters]
    assert len(set(keys)) == len(keys)
    assert all(k.startswith("glory-hole-shop/") for k in keys)


def test_paywalled_chapters_are_excluded_from_the_list():
    """A ``price > 0`` chapter answers ``{"paywall": true}`` with no images.

    Listing it would put an entry in the chapter list that can never open.
    """
    payload = _load("chapters_paid")
    raw = payload["data"]
    assert any(c["price"] > 0 for c in raw), "fixture must contain a paid chapter"

    chapters = parse_chapters([payload], "regressed-warriors-female-dominance-diary")
    assert len(chapters) == len(raw) - 1
    paid_slugs = {c["chapter_slug"] for c in raw if c["price"] > 0}
    assert paid_slugs == {"chapter-98"}
    assert all(not c.id.endswith("/chapter-98") for c in chapters)


@pytest.mark.parametrize(
    ("name", "slug", "expected"),
    [
        ("Chapter 1", "chapter-1", 1.0),
        ("Chapter 155", "chapter-155", 155.0),
        ("Chapter 27.5", "chapter-27-5", 27.5),
        ("Chapter 102.5", "chapter-102-5", 102.5),
        ("", "chapter-42", 42.0),
        ("", "chapter-7-5", 7.5),
        ("Prologue", "prologue", None),
    ],
)
def test_chapter_number_parsing(name, slug, expected):
    assert parse_chapter_number(name, slug) == expected


def test_whole_chapter_list_arrives_in_one_request(connector: OmegaScansConnector):
    """156 chapters, one round trip.

    ``perPage=500`` covers the largest series in the catalog (270 chapters),
    so ``last_page`` is 1 and the defensive paging loop never engages.
    """
    recorder = Recorder({"/chapter/query": _load("chapters"), "/series/": _load("series_detail")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        chapters = connector.get_chapters("sex-stopwatch")

    assert len(chapters) == 156
    assert recorder.paths.count("/chapter/query") == 1
    assert recorder.calls[-1][1]["series_id"] == 7
    assert recorder.calls[-1][1]["perPage"] == 500


def test_get_chapters_reuses_a_series_id_learned_from_browsing(connector: OmegaScansConnector):
    """Opening a series reached from the catalog must not re-fetch its detail.

    ``/chapter/query`` needs the numeric series id (passing the slug answers
    HTTP 500), and every listing item already carries it.
    """
    recorder = Recorder({"/query": _load("browse_page1"), "/chapter/query": _load("chapters")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.get_series_list(1)
        chapters = connector.get_chapters("sex-stopwatch")

    assert len(chapters) == 156
    assert recorder.paths == ["/query", "/chapter/query"]
    assert not any(p.startswith("/series/") for p in recorder.paths)
    # ...and the id it reused is the real one from the listing, not a
    # placeholder that would silently query the wrong series.
    assert recorder.calls[-1][1]["series_id"] == 7


def test_chapter_list_is_cached(connector: OmegaScansConnector):
    recorder = Recorder({"/query": _load("browse_page1"), "/chapter/query": _load("chapters")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.get_series_list(1)
        connector.get_chapters("sex-stopwatch")
        connector.get_chapters("sex-stopwatch")
    assert recorder.paths.count("/chapter/query") == 1


def test_chapter_list_pages_when_the_api_says_there_is_more(connector: OmegaScansConnector):
    """The defensive loop only engages when ``last_page > 1``.

    ``perPage=500`` means it never fires against today's catalog, so it is
    driven here with a doctored ``last_page`` to prove a second page would be
    fetched and merged rather than silently dropped.
    """
    first = json.loads(json.dumps(_load("chapters")))
    first["meta"] = dict(first["meta"], last_page=2)
    second = json.loads(json.dumps(_load("chapters_alt")))
    second["meta"] = dict(second["meta"], last_page=2)
    pages = [first, second]
    requested: list[int] = []

    def route(path: str, *, params: dict | None = None):
        if path == "/series/sex-stopwatch":
            return _load("series_detail")
        page = (params or {}).get("page", 1)
        requested.append(page)
        return pages[page - 1]

    with patch.object(connector._http, "get_json", side_effect=route):
        chapters = connector.get_chapters("sex-stopwatch")

    assert requested == [1, 2]
    keys = {c.id for c in chapters}
    # A chapter that exists ONLY in the second page made it into the list...
    assert "sex-stopwatch/chapter-103-5" in keys
    # ...while slugs present in both pages were merged, not duplicated.
    assert len(keys) == len(chapters) == 166
    assert all(c.series_id == "sex-stopwatch" for c in chapters)


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------


def test_parse_chapter_pages_from_fixture():
    pages = parse_chapter_pages(_load("chapter_pages"), "sex-stopwatch/chapter-1")
    assert len(pages) == 11
    assert [p.number for p in pages] == list(range(1, 12))
    assert pages[0].id == "sex-stopwatch/chapter-1:1"
    assert pages[0].chapter_id == "sex-stopwatch/chapter-1"
    assert pages[0].remote_url.startswith("https://media.omegascans.org/")
    assert pages[0].remote_url.endswith("/01.jpg")
    assert len({p.remote_url for p in pages}) == 11


def test_parse_chapter_pages_refuses_a_paywalled_payload():
    """Defense in depth, exercised directly.

    The real paywalled response also omits ``chapter_data`` entirely, so it
    would parse to [] even without the flag check -- which means only a
    payload carrying BOTH the flag and images proves the guard is live. If
    the API ever starts returning teaser images alongside ``paywall: true``,
    this is what stops them reaching the reader.
    """
    teaser = json.loads(json.dumps(_load("chapter_pages")))
    teaser["paywall"] = True
    assert teaser["chapter"]["chapter_data"]["images"], "fixture must carry images"

    assert parse_chapter_pages(teaser, "sex-stopwatch/chapter-1") == []


def test_page_images_cost_exactly_one_request(connector: OmegaScansConnector):
    """13 images, one round trip -- there is no per-page resolution step."""
    recorder = Recorder({"/chapter/": _load("chapter_pages_last")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        pages = connector.get_chapter_pages("sex-stopwatch/chapter-155")

    assert len(pages) == 13
    assert recorder.paths == ["/chapter/sex-stopwatch/chapter-155"]


def test_paywalled_chapter_yields_no_pages(connector: OmegaScansConnector):
    payload = _load("chapter_paywalled")
    assert payload["paywall"] is True
    recorder = Recorder({"/chapter/": payload})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        pages = connector.get_chapter_pages(
            "regressed-warriors-female-dominance-diary/chapter-98"
        )
    assert pages == []


def test_chapter_pages_are_cached(connector: OmegaScansConnector):
    recorder = Recorder({"/chapter/": _load("chapter_pages")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.get_chapter_pages("sex-stopwatch/chapter-1")
        connector.get_chapter_pages("sex-stopwatch/chapter-1")
    assert len(recorder.paths) == 1


def test_opened_chapter_backfills_page_count_in_the_chapter_list(connector: OmegaScansConnector):
    recorder = Recorder(
        {
            "/query": _load("browse_page1"),
            "/chapter/query": _load("chapters"),
            "/chapter/": _load("chapter_pages"),
        }
    )
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.get_series_list(1)
        connector.get_chapter_pages("sex-stopwatch/chapter-1")
        connector._chapter_list_cache.clear()
        chapters = connector.get_chapters("sex-stopwatch")

    opened = next(c for c in chapters if c.id == "sex-stopwatch/chapter-1")
    assert opened.page_count == 11


# ---------------------------------------------------------------------------
# page identity
# ---------------------------------------------------------------------------


def test_page_id_round_trips_through_a_slash_bearing_chapter_key():
    chapter_key = "sex-stopwatch/chapter-155"
    page_id = make_page_id(chapter_key, 7)
    assert page_id == "sex-stopwatch/chapter-155:7"
    assert page_id_chapter_id(page_id) == chapter_key


def test_page_id_splits_on_the_last_colon_not_the_first():
    """Chapter keys are OPAQUE and may themselves contain a colon.

    Only the final colon is the separator this module wrote, so splitting on
    the first one would hand back a truncated chapter key and every image in
    such a chapter would 404. One colon cannot tell the two apart -- this
    needs a key that carries its own.
    """
    chapter_key = "odd-series/chapter-3:extra"
    page_id = make_page_id(chapter_key, 12)
    assert page_id == "odd-series/chapter-3:extra:12"
    assert page_id_chapter_id(page_id) == chapter_key


def test_page_id_without_a_separator_is_rejected():
    assert page_id_chapter_id("sex-stopwatch/chapter-1") is None


def test_find_page_returns_the_right_page_and_reuses_the_cache(connector: OmegaScansConnector):
    recorder = Recorder({"/chapter/": _load("chapter_pages")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.get_chapter_pages("sex-stopwatch/chapter-1")
        page = connector.find_page("sex-stopwatch/chapter-1:4")

    assert page is not None
    assert page.number == 4
    assert page.remote_url.endswith("/04.jpg")
    # find_page must not be an extra network call for an already-open chapter.
    assert len(recorder.paths) == 1


def test_find_page_on_a_malformed_id_is_none(connector: OmegaScansConnector):
    assert connector.find_page("nonsense") is None


# ---------------------------------------------------------------------------
# genres
# ---------------------------------------------------------------------------


def test_parse_tags_into_genre_modes():
    modes = parse_tags(_load("tags"))
    assert [m.label for m in modes] == ["Drama", "Fantasy", "Harem", "MILF", "Romance"]
    assert {m.id for m in modes} == {"1", "2", "3", "8", "16"}


def test_browse_by_genre_sends_the_tag_id(connector: OmegaScansConnector):
    recorder = Recorder({"/query": _load("browse_page1")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.browse_by_genre("3", 1)
    assert recorder.calls[0][1]["tags_ids"] == "[3]"


def test_browse_by_genre_ignores_a_non_numeric_tag(connector: OmegaScansConnector):
    """Tag ids are interpolated into the API's ``tags_ids`` array literal."""
    recorder = Recorder({"/query": _load("browse_page1")})
    with patch.object(connector._http, "get_json", side_effect=recorder):
        connector.browse_by_genre("1] or 1=1 --", 1)
    assert recorder.calls[0][1]["tags_ids"] == "[]"


def test_genres_are_fetched_once(connector: OmegaScansConnector):
    calls: list[str] = []

    def route(path: str, *, params: dict | None = None):
        calls.append(path)
        return _load("tags")

    with patch.object(connector._http, "get_json_value", side_effect=route):
        connector.list_genres()
        connector.list_genres()
    assert calls == ["/tags"]
