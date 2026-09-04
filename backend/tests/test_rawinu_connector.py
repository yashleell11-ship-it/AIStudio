"""Tests for the RawINU connector.

Every fixture in ``tests/fixtures/rawinu/`` was captured FROM THE VPS
(135.148.43.147) through the production container's own
``SyncConnectorHttpClient``, so the bytes exercised here are the bytes
production sees, TLS stack included.

Each parse assertion below was watched to FAIL against a deliberately broken
selector before being accepted — a test that still passes when the parser is
broken is worse than no test at all.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.rawinu.connector import RawInuConnector
from connectors.rawinu.mappers import (
    CHAPTER_LIST_PATH,
    LIST_PATH,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_genres,
    parse_series_detail,
    parse_series_list,
)

FIXTURES = Path(__file__).parent / "fixtures" / "rawinu"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def rawinu() -> RawInuConnector:
    return RawInuConnector()


# ---------------------------------------------------------------------------
# descriptor / registration
# ---------------------------------------------------------------------------


def test_source_descriptor_contract(rawinu: RawInuConnector):
    assert rawinu.source_type == "rawinu"
    assert rawinu.display_name == "RawINU"
    assert rawinu.is_browsable is True
    assert rawinu.supports_import is False
    # RAW manga, not adult content.
    assert rawinu.is_mature is False
    assert rawinu.content_kind == "manga"


def test_allowed_image_hosts_covers_the_cdn(rawinu: RawInuConnector):
    """Covers and page images both live on *.ihlv1.xyz; the proxy allowlist
    must admit it or every image 403s at the proxy."""
    assert "ihlv1.xyz" in rawinu.allowed_image_hosts
    # The allowlist must not be wide open.
    assert "rawinu.com" not in rawinu.allowed_image_hosts


def test_registry_lists_rawinu_once_wired():
    """Passes once the serial integrator adds the registration snippet.

    This connector ships unregistered by design (registry.py is owned by the
    integrator, not by this connector), so before wiring this is a skip
    rather than a failure.
    """
    from connectors.registry import list_installed_connectors

    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    if "rawinu" not in browsable:
        pytest.skip("rawinu not yet added to registry.py builtins by the integrator")
    assert "rawinu" in browsable


# ---------------------------------------------------------------------------
# listing / search / genre  (one endpoint, three query shapes)
# ---------------------------------------------------------------------------


def test_parse_series_list_from_fixture():
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    assert len(listing.items) == 20
    assert listing.has_more is True
    # 408 pagination pages x 20 cards.
    assert listing.total == 8160
    first = listing.items[0]
    assert first.id == "seijo-no-isan"
    assert first.title == "SEIJO NO, ISAN"
    assert first.cover_url == (
        "https://s4.ihlv1.xyz/images4/20260807/seijo-no-isan_6a757e9c81f66.jpg"
    )
    assert first.canonical_path == "/manga-seijo-no-isan.html"
    assert first.latest_chapter == "Last chapter: 2.2"


def test_every_listing_card_yields_id_title_and_cover():
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    assert all(item.id and item.title for item in listing.items)
    assert all(item.cover_url and item.cover_url.startswith("https://") for item in listing.items)


def test_listing_ignores_non_series_manga_links():
    """The listing page also links manga-list-genre-*.html, manga-author-*.html,
    manga-list-magazine-*.html and manga-on-going.html. A naive
    `manga-([^"]+)\\.html` scrape pulls all of them in as fake series; card-scoped
    parsing must not."""
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    ids = [item.id for item in listing.items]
    assert not any(i.startswith(("list-genre", "author-", "list-magazine", "on-going")) for i in ids)
    assert "list" not in ids


def test_browse_page_2_differs_from_page_1():
    page1 = parse_series_list(_load("browse_page1.html"), page=1)
    page2 = parse_series_list(_load("browse_page2.html"), page=2)
    assert page1.items[0].id != page2.items[0].id
    assert not set(i.id for i in page1.items) & set(i.id for i in page2.items)


def test_search_results_parse_and_paginate():
    listing = parse_series_list(_load("search_isekai.html"), page=1)
    assert len(listing.items) == 20
    # 36 pages of "isekai" matches.
    assert listing.total == 720
    assert listing.has_more is True
    assert any("ISEKAI" in item.title.upper() for item in listing.items)


def test_search_with_no_matches_is_empty_and_terminal():
    listing = parse_series_list(_load("search_empty.html"), page=1)
    assert listing.items == []
    assert listing.has_more is False
    assert listing.total == 0


def test_genre_listing_parses(rawinu: RawInuConnector):
    listing = parse_series_list(_load("browse_genre_comedy.html"), page=1)
    assert len(listing.items) == 20
    assert listing.total == 3200
    assert listing.items[0].id == "lucifer-san-no-daraku-gohan"


def test_browse_requests_the_listing_endpoint_with_expected_params(rawinu: RawInuConnector):
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return _load("browse_page1.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        rawinu.get_series_list(2)

    assert captured[0][0] == LIST_PATH
    assert captured[0][1]["page"] == 2
    assert captured[0][1]["sort"] == "last_update"
    assert captured[0][1]["sort_type"] == "DESC"


def test_each_browse_mode_requests_a_distinct_sort(rawinu: RawInuConnector):
    """Three exposed modes must map to three genuinely different site sorts.
    Verified from the VPS that these return different first pages
    (last_update -> newest upload, views -> One Piece, name -> A-Z)."""
    captured: list[dict] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return _load("browse_page1.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        for mode in rawinu.list_browse_modes():
            rawinu.get_series_list(1, sort=mode.id)

    pairs = [(p["sort"], p["sort_type"]) for p in captured]
    assert len(set(pairs)) == len(pairs) == 3
    assert ("last_update", "DESC") in pairs
    assert ("views", "DESC") in pairs
    assert ("name", "ASC") in pairs


def test_search_uses_the_name_param_never_s_or_search(rawinu: RawInuConnector):
    """robots.txt on rawinu.com allows `/` but disallows `/*?s=` and
    `/*?search=`. The site's own form searches by `name`, which is outside
    those two rules — so search MUST spell the parameter `name`. This test is
    a crawl-policy guard, not a cosmetic one."""
    captured: list[dict] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return _load("search_isekai.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        rawinu.search_series("isekai", 1)

    params = captured[0]
    assert params["name"] == "isekai"
    assert "s" not in params
    assert "search" not in params


def test_blank_search_falls_back_to_browse(rawinu: RawInuConnector):
    captured: list[dict] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return _load("browse_page1.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        listing = rawinu.search_series("   ", 1)

    assert captured[0]["name"] == ""
    assert len(listing.items) == 20


def test_genre_browse_sends_the_genre_param(rawinu: RawInuConnector):
    captured: list[dict] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return _load("browse_genre_comedy.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        rawinu.browse_by_genre("comedy", 1)

    assert captured[0]["genre"] == "comedy"


def test_genres_are_harvested_from_a_listing_already_fetched(rawinu: RawInuConnector):
    """The genre vocabulary ships on every listing page. Browsing once must
    populate it, so list_genres() costs zero additional requests."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return _load("browse_page1.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        rawinu.get_series_list(1)
        assert len(calls) == 1
        genres = rawinu.list_genres()

    assert len(calls) == 1, "list_genres() must not issue its own request"
    labels = {g.label for g in genres}
    ids = {g.id for g in genres}
    assert "Comedy" in labels and "comedy" in ids
    assert len(genres) > 100


def test_parse_genres_reads_slug_and_label():
    genres = parse_genres(_load("browse_page1.html"))
    assert ("comedy", "Comedy") in genres
    assert ("action", "Action") in genres
    assert len(genres) == len({slug for slug, _ in genres}), "slugs must be unique"


# ---------------------------------------------------------------------------
# series detail
# ---------------------------------------------------------------------------


def test_parse_series_detail_fields():
    series = parse_series_detail(_load("series_detail.html"), "mechanical-buddy-universe")
    assert series is not None
    assert series.title == "MECHANICAL BUDDY UNIVERSE"
    assert series.author == "KATOU Takuji"
    assert series.status == "On going"
    assert series.genres == ("Comedy", "Sci-fi")
    assert series.cover_url == (
        "https://s4.ihlv1.xyz/images2/20230425/6446fa8a46746_6446fa8ae74a6.jpg"
    )
    assert series.canonical_path == "/manga-mechanical-buddy-universe.html"
    assert "android" in (series.description or "")


def test_series_title_is_base64_decoded_from_data_enc():
    """RawINU emits the title only as <h3 data-enc="BASE64"> with no text
    node. Reading the attribute raw yields the base64 blob as the title.

    The breadcrumb is stripped out first on purpose. With it present the
    fallback path also produces the right answer, so the assertion would pass
    even with the base64 reader completely broken — this isolates the decode.
    """
    html = _load("series_detail.html")
    assert 'data-enc="TUVDSEFOSUNBTCBCVUREWSBVTklWRVJTRQ=="' in html
    without_breadcrumb = re.sub(
        r'<li class="breadcrumb-item active"[^>]*>[^<]*</li>', "", html
    )
    assert 'aria-current="page"' not in without_breadcrumb

    series = parse_series_detail(without_breadcrumb, "mbu")
    assert series is not None
    assert series.title == "MECHANICAL BUDDY UNIVERSE"
    assert "TUVDSEFOSUNBTA" not in series.title


def test_series_title_falls_back_to_the_breadcrumb_without_data_enc():
    """The other half of the pair: strip data-enc, keep the breadcrumb."""
    html = _load("series_detail.html").replace("<h3 data-enc=", "<h3 data-gone=")
    series = parse_series_detail(html, "mbu")
    assert series is not None
    assert series.title == "MECHANICAL BUDDY UNIVERSE"


def test_native_japanese_title_is_kept_in_the_description():
    """RAW source: the card title is romaji and the Japanese title only
    appears under "Other names". It must survive into the reader."""
    series = parse_series_detail(_load("series_detail.html"), "mbu")
    assert series is not None
    assert "Also known as:" in (series.description or "")
    assert "メカニカル" in (series.description or "")


@pytest.mark.parametrize(
    "fixture",
    [
        "not_found_series.html",
        "not_found_chapter.html",
        "browse_page1.html",
        "search_empty.html",
        "browse_genre_comedy.html",
    ],
)
def test_series_detail_rejects_pages_that_are_not_series(fixture: str):
    """RawINU NEVER answers 404 — an unknown slug returns HTTP 200 carrying
    the homepage (verified from the VPS). Structure is the only not-found
    signal, and listing pages must be rejected too: they carry an
    aria-current="page" breadcrumb reading "List manga" that a
    breadcrumb-only title parser would happily return as a series name."""
    assert parse_series_detail(_load(fixture), "whatever") is None


def test_get_series_returns_none_on_a_soft_404(rawinu: RawInuConnector):
    with patch.object(rawinu._http, "get_text", return_value=_load("not_found_series.html")):
        assert rawinu.get_series("no-such-series") is None


# ---------------------------------------------------------------------------
# chapters
# ---------------------------------------------------------------------------


def test_parse_chapters_from_the_one_shot_endpoint():
    chapters = parse_chapters(_load("chapter_list.html"), "mechanical-buddy-universe")
    assert len(chapters) == 61
    # Oldest first.
    assert chapters[0].number == 1.0
    assert chapters[-1].number == 61.0
    assert chapters[-1].id == "mechanical-buddy-universe-chapter-61"
    assert chapters[-1].title == "Chapter 61"
    assert chapters[-1].series_id == "mechanical-buddy-universe"
    assert chapters[-1].release_date == "1 weeks"


def test_parse_chapters_handles_decimal_numbering():
    chapters = parse_chapters(_load("chapter_list_decimal.html"), "ryoumin")
    assert len(chapters) == 91
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers), "chapters must come back in reading order"
    assert 75.1 in numbers and 75.2 in numbers
    assert chapters[-1].number == 76.1


def test_blank_chapter_name_recovers_its_number():
    """Chapter 20 of ryoumin-0-nin-start-... ships an empty <div
    class="chapter-name"></div> and an empty title attribute upstream. Its
    number is recoverable only from its own href."""
    chapters = parse_chapters(_load("chapter_list_decimal.html"), "ryoumin")
    twenty = [c for c in chapters if c.number == 20.0]
    assert len(twenty) == 1
    assert twenty[0].title == "Chapter 20"


def test_parse_chapter_number_prefers_name_then_href():
    assert parse_chapter_number("Chapter 12.5", "x-chapter-99") == 12.5
    assert parse_chapter_number("", "series-chapter-20") == 20.0
    assert parse_chapter_number("", "no-numbering-here") is None


def test_chapter_number_is_the_chapter_not_the_last_number_in_the_name():
    """Guards the "chapter N" reader specifically. A trailing-number-only
    parser answers 2 here (and 2024 for a dated title), silently renumbering
    the series."""
    assert parse_chapter_number("Chapter 7 - Part 2", "x") == 7.0
    assert parse_chapter_number("Chapter 5 (2024)", "x") == 5.0


def test_chapter_number_falls_back_to_a_bare_trailing_number():
    """Names carrying a number but not the word "chapter" still have to
    produce one — this is the only path that exercises that fallback."""
    assert parse_chapter_number("12.5", "x") == 12.5
    assert parse_chapter_number("Oneshot 3", "x") == 3.0


def test_empty_chapter_list_response_yields_no_chapters():
    assert parse_chapters(_load("chapter_list_empty.html"), "x") == []


def test_get_chapters_uses_the_one_shot_xhr_endpoint(rawinu: RawInuConnector):
    """The series HTML contains NO chapter rows — it ships an empty
    <div id="list-chapter"> filled by XHR. Scraping the series page for
    chapters returns nothing; the connector must call the XHR endpoint."""
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return _load("chapter_list.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        chapters = rawinu.get_chapters("mechanical-buddy-universe")

    assert len(captured) == 1
    assert captured[0][0] == CHAPTER_LIST_PATH
    assert captured[0][1] == {"slug": "mechanical-buddy-universe"}
    assert len(chapters) == 61


def test_get_series_seeds_the_chapter_cache_so_get_chapters_is_free(
    rawinu: RawInuConnector,
):
    """Speed regression guard. The reader opens a series and immediately asks
    for its chapters. get_series already pays for the chapter list, so the
    follow-up get_chapters must issue ZERO further requests."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        if path == CHAPTER_LIST_PATH:
            return _load("chapter_list.html")
        return _load("series_detail.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        series = rawinu.get_series("mechanical-buddy-universe")
        assert calls == ["/manga-mechanical-buddy-universe.html", CHAPTER_LIST_PATH]
        chapters = rawinu.get_chapters("mechanical-buddy-universe")

    assert len(calls) == 2, f"expected no refetch, got {calls}"
    assert len(chapters) == 61
    assert series is not None
    assert series.chapter_count == 61
    assert series.latest_chapter == "Chapter 61"


def test_get_series_is_cached_across_calls(rawinu: RawInuConnector):
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        if path == CHAPTER_LIST_PATH:
            return _load("chapter_list.html")
        return _load("series_detail.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        rawinu.get_series("mechanical-buddy-universe")
        rawinu.get_series("mechanical-buddy-universe")

    assert len(calls) == 2, f"second get_series must hit cache, got {calls}"


# ---------------------------------------------------------------------------
# chapter pages
# ---------------------------------------------------------------------------


def test_parse_chapter_pages_from_the_reader_html():
    pages = parse_chapter_pages(_load("chapter_pages.html"), "mechanical-buddy-universe-chapter-61")
    assert len(pages) == 21
    assert pages[0].number == 1
    assert pages[0].id == "mechanical-buddy-universe-chapter-61:1"
    assert pages[0].chapter_id == "mechanical-buddy-universe-chapter-61"
    assert pages[0].remote_url == (
        "https://s4.ihlv1.xyz/images4/20260825/165_6a8d051939ce6.jpg"
    )
    assert [p.number for p in pages] == list(range(1, 22))


def test_page_image_urls_are_stripped_of_upstream_whitespace():
    """RawINU pads every data-src value with trailing newlines. An unstripped
    URL is not fetchable."""
    pages = parse_chapter_pages(_load("chapter_pages.html"), "c")
    for page in pages:
        assert page.remote_url is not None
        assert page.remote_url == page.remote_url.strip()
        assert "\n" not in page.remote_url
        assert page.remote_url.startswith("https://")


def test_page_images_prefer_data_src_over_a_placeholder_src():
    """RawINU emits only data-src today, but the usual lazy-load shape is
    src="placeholder" + data-src="real". The image regex must be anchored to
    data-src so a future template change cannot silently serve every page as
    the loading spinner."""
    html = (
        '<div id="chapter-images">'
        '<img class="chapter-img" src="/uploads/lazy-loading.gif" '
        'data-src="https://s2.ihlv1.xyz/images4/x/real1.jpg">'
        '<img class="chapter-img" src="/uploads/lazy-loading.gif" '
        'data-src="https://s2.ihlv1.xyz/images4/x/real2.jpg">'
        "</div>"
    )
    pages = parse_chapter_pages(html, "c")
    assert [p.remote_url for p in pages] == [
        "https://s2.ihlv1.xyz/images4/x/real1.jpg",
        "https://s2.ihlv1.xyz/images4/x/real2.jpg",
    ]
    assert not any("lazy-loading" in (p.remote_url or "") for p in pages)


def test_chapter_pages_cost_exactly_one_request(rawinu: RawInuConnector):
    """Every page image URL is in the single reader response — resolving
    images must never cost a request per page."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return _load("chapter_pages.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        pages = rawinu.get_chapter_pages("mechanical-buddy-universe-chapter-61")

    assert len(calls) == 1
    assert calls[0] == "/unir-mechanical-buddy-universe-chapter-61.html"
    assert len(pages) == 21


def test_find_page_serves_from_the_chapter_cache(rawinu: RawInuConnector):
    """The image proxy calls find_page once per page image. After the chapter
    is warm every one of those must be free."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return _load("chapter_pages.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        rawinu.get_chapter_pages("mechanical-buddy-universe-chapter-61")
        found = [
            rawinu.find_page(f"mechanical-buddy-universe-chapter-61:{n}")
            for n in range(1, 22)
        ]

    assert len(calls) == 1, f"21 find_page calls must not refetch, got {len(calls)}"
    assert all(p is not None for p in found)
    assert found[0].number == 1
    assert found[-1].number == 21


def test_find_page_rejects_a_malformed_page_id(rawinu: RawInuConnector):
    assert rawinu.find_page("no-colon-here") is None


def test_chapter_page_count_backfills_into_the_chapter_list(rawinu: RawInuConnector):
    """Chapter list markup carries no page counts. Once a chapter has been
    read, its count should show without another fetch."""

    def fake_get_text(path: str, *, params=None):
        if path == CHAPTER_LIST_PATH:
            return _load("chapter_list.html")
        return _load("chapter_pages.html")

    with patch.object(rawinu._http, "get_text", side_effect=fake_get_text):
        rawinu.get_chapter_pages("mechanical-buddy-universe-chapter-61")
        chapters = rawinu.get_chapters("mechanical-buddy-universe")

    last = [c for c in chapters if c.id == "mechanical-buddy-universe-chapter-61"][0]
    assert last.page_count == 21


# ---------------------------------------------------------------------------
# image URL hygiene
# ---------------------------------------------------------------------------


def test_cover_urls_drop_the_imgmax_parameter():
    """Measured from the VPS: ?imgmax=100, ?imgmax=300 and no parameter all
    return byte-identical responses — the CDN ignores it. Dropping it puts
    the browse-card cover and the series-detail cover on ONE url so each
    cover is fetched and cached once instead of once per size spelling."""
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    detail = parse_series_detail(_load("series_detail.html"), "mbu")
    assert all("imgmax" not in (i.cover_url or "") for i in listing.items)
    assert "imgmax" not in (detail.cover_url or "")
    assert all("?" not in (i.cover_url or "") for i in listing.items)


def test_cover_url_survives_pagespeed_mangled_markup():
    """A few covers were rewritten by mod_pagespeed, which leaked unescaped
    attributes INSIDE the CSS url('...') value:
        url('https://host/img.png" data-pagespeed-url-hash="3060502731" onload="...?imgmax=100')
    Everything from the stray quote on is junk and must be cut, or the URL
    404s at the CDN."""
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    zam = [i for i in listing.items if i.id == "zamuzekuta"]
    assert zam, "fixture should contain the pagespeed-mangled card"
    assert zam[0].cover_url == (
        "https://s4.ihlv1.xyz/images3/20251003/image_68df5f2c6e42e.png"
    )
    for item in listing.items:
        assert '"' not in (item.cover_url or "")
        assert "pagespeed" not in (item.cover_url or "")


def test_all_image_hosts_are_inside_the_proxy_allowlist(rawinu: RawInuConnector):
    """Any cover or page image on a host outside allowed_image_hosts is
    rejected by the image proxy before a request is made."""
    urls = [i.cover_url for i in parse_series_list(_load("browse_page1.html"), page=1).items]
    urls += [p.remote_url for p in parse_chapter_pages(_load("chapter_pages.html"), "c")]
    urls.append(parse_series_detail(_load("series_detail.html"), "m").cover_url)
    allowed = rawinu.allowed_image_hosts
    for url in urls:
        host = url.split("://", 1)[1].split("/", 1)[0]
        assert any(host == a or host.endswith("." + a) for a in allowed), host
