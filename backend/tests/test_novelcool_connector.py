"""Tests for the Novel Cool manga connector.

Every fixture under ``tests/fixtures/novelcool/`` was captured from the OVH
VPS inside ``manhwamaniacs-backend``, so these tests pin the markup production
actually receives rather than whatever this laptop's egress IP is served.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.novelcool import mappers
from connectors.novelcool.connector import NovelCoolConnector
from connectors.novelcool.mappers import (
    IMAGES_PER_VIEW,
    SEARCH_PAGES_PER_REQUEST,
    is_listing_page,
    make_page_id,
    page_id_chapter_id,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_cards,
    parse_series_detail,
    parse_series_list,
    parse_total_pages,
)

FIXTURES = Path(__file__).parent / "fixtures" / "novelcool"

#: The chapter used throughout: Nano Machine Ch.272, 13 images across 2 views.
CHAPTER_KEY = "Ch-272/13661864"
SERIES_KEY = "Nano-Machine"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def connector() -> NovelCoolConnector:
    return NovelCoolConnector()


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------


def test_parse_series_list_reads_cards_and_page_count():
    listing = parse_series_list(_load("browse_index_page1.html"), page=1)

    assert len(listing.items) >= 15
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "13-Nights-Of-Vengeful-Spirits"
    assert first.title == "13 Nights Of Vengeful Spirits"
    assert first.cover_url is not None
    assert first.cover_url.startswith("https://img.novelcool.com/")
    assert first.canonical_path == "/novel/13-Nights-Of-Vengeful-Spirits.html"
    assert "Horror" in first.genres


def test_directory_reports_its_own_total_page_count():
    # The site states "1/1355" in its pager; nothing else on the page says how
    # deep the directory goes, so has_more depends entirely on reading it.
    assert parse_total_pages(_load("browse_index_page1.html")) == 1355


def test_each_page_count_selector_works_on_its_own():
    """The page total is stated twice — in the pager's "1/1355" readout and in
    the page-go script's ``all_pages`` — and the mapper reads both.

    Asserting only on the intact page cannot tell the two apart: breaking
    either selector alone still passes because the other covers it. These
    inputs delete one marker at a time so each selector is pinned separately.
    """
    html = _load("browse_index_page1.html")
    assert "page-nav-center-num" in html and "all_pages" in html

    without_script = html.replace("all_pages", "all_pages_REMOVED")
    without_pager = html.replace("page-nav-center-num", "page-nav-REMOVED")

    assert parse_total_pages(without_script) == 1355, "pager readout selector"
    assert parse_total_pages(without_pager) == 1355, "all_pages selector"
    assert parse_total_pages(html.replace("all_pages", "x").replace("page-nav-center-num", "y")) is None


def test_listing_keeps_manga_and_drops_novels():
    """Novel Cool mixes prose novels into every listing.

    The manga reader cannot render a novel, so a card without the
    ``book-type-manga`` badge must never reach it.
    """
    html = _load("browse_index_page1.html")
    assert html.count('class="book-type book-type-novel"') >= 10, "fixture has novels"

    kept = {series.id for series in parse_series_cards(html)}
    everything = {series.id for series in parse_series_cards(html, manga_only=False)}

    assert kept, "at least some manga survive the filter"
    assert kept < everything, "the filter actually drops the novel cards"
    assert len(everything) - len(kept) >= 10


def test_browse_page_2_returns_different_series_than_page_1():
    page1 = parse_series_list(_load("browse_index_page1.html"), page=1)
    page2 = parse_series_list(_load("browse_index_page2.html"), page=2)

    assert page2.items
    assert not ({s.id for s in page1.items} & {s.id for s in page2.items})


def test_genre_listing_parses():
    listing = parse_series_list(_load("browse_genre_action.html"), page=1)
    assert len(listing.items) >= 10
    assert listing.has_more is True


def test_single_page_listing_never_claims_a_second_page():
    """``/category/latest.html`` has no page 2 upstream; saying otherwise sends
    the reader to ``latest_2.html``, which silently serves the generic
    directory instead of more latest releases."""
    listing = parse_series_list(_load("browse_latest.html"), page=1, single_page=True)

    assert len(listing.items) >= 50
    assert listing.has_more is False


def test_popular_page_is_almost_entirely_novels():
    """Why "popular" is not an exposed browse mode. If this ever flips, the
    mode is worth adding back."""
    html = _load("browse_popular.html")
    manga = parse_series_cards(html)
    everything = parse_series_cards(html, manga_only=False)

    assert len(everything) >= 40
    assert len(manga) <= 3, "popular.html is Novel Cool's novel chart"
    assert "popular" not in {mode for mode, _label in mappers.BROWSE_MODES}


# ---------------------------------------------------------------------------
# The soft 404 -- novelcool never returns a 404 status
# ---------------------------------------------------------------------------


def test_missing_series_page_is_the_homepage_not_a_404():
    """Guards the trap this whole connector is shaped around.

    ``missing_series.html`` is the real response for a slug that does not
    exist: HTTP 200 carrying the homepage, complete with 100+ valid
    ``book-item`` cards. Anything that parses it as a listing shows the reader
    100 unrelated series; anything that parses it as a series invents one.
    """
    html = _load("missing_series.html")

    assert html.count('<div class="book-item"') > 50, "fixture really does carry cards"
    assert is_listing_page(html) is False
    assert parse_series_detail(html, "No-Such-Series") is None
    assert parse_chapters(html, "No-Such-Series") == []

    listing = parse_series_list(html, page=9999)
    assert listing.items == []
    assert listing.has_more is False


def test_real_listing_pages_are_recognised_as_listings():
    for name in (
        "browse_index_page1.html",
        "browse_latest.html",
        "browse_genre_action.html",
        "search_sword_p1.html",
    ):
        assert is_listing_page(_load(name)) is True, name


# ---------------------------------------------------------------------------
# Series detail
# ---------------------------------------------------------------------------


def test_parse_series_detail_reads_every_metadata_field():
    series = parse_series_detail(_load("series_nano_machine.html"), SERIES_KEY)

    assert series is not None
    assert series.title == "Nano Machine"
    assert series.author == "Hanzhung Wulya"
    assert series.status == "Ongoing"
    assert series.cover_url == (
        "https://img.novelcool.com/logo/202505/e7/Nano_Machine9858.jpg"
    )
    assert series.canonical_path == "/novel/Nano-Machine.html"
    assert series.description


def test_detail_genres_survive_the_double_space_in_the_markup():
    """The page emits ``<span  itemprop="keywords">`` with TWO spaces.

    A single-space pattern silently matches nothing and every series comes
    back with no genres — which is exactly what the first draft of the mapper
    did, and it looked like the site simply had no genre data.
    """
    series = parse_series_detail(_load("series_nano_machine.html"), SERIES_KEY)

    assert series is not None
    assert series.genres == ("Action", "Adventure", "Fantasy")


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------


def test_parse_chapters_reads_the_inline_list():
    chapters = parse_chapters(_load("series_nano_machine.html"), SERIES_KEY)

    assert len(chapters) == 276
    assert all(chapter.series_id == SERIES_KEY for chapter in chapters)
    assert any(chapter.release_date for chapter in chapters)
    # Chapter keys are opaque and DO contain a slash.
    assert all("/" in chapter.id for chapter in chapters)
    assert CHAPTER_KEY in {chapter.id for chapter in chapters}


def test_chapters_come_back_oldest_first_by_the_sites_own_numbering():
    chapters = parse_chapters(_load("series_nano_machine.html"), SERIES_KEY)
    numbers = [chapter.number for chapter in chapters if chapter.number is not None]

    assert numbers == sorted(numbers)
    assert numbers[0] == 1
    assert numbers[-1] == 272
    # Unnumbered oddments sort after the numbered run, never in the middle.
    unnumbered = [i for i, c in enumerate(chapters) if c.number is None]
    assert all(i >= len(numbers) for i in unnumbered)


def test_chapters_sharing_a_number_keep_the_oldest_first():
    """``parse_chapters`` reverses the upstream list before its stable sort.

    Upstream is newest-first, and duplicate chapter numbers are real: One Piece
    carries two "Chapter 1.2" entries, one from 2020 and one posted an hour
    ago. Sorting a newest-first list by number leaves the pair newest-first
    too, so the reader would meet the re-upload before the original. The
    reverse is what puts them in reading order — and the sort alone cannot
    show that, which is why this test builds the tie explicitly.

    The two rows below are lifted verbatim out of the captured fixture (only
    the duplicated title differs), so the markup being parsed is the site's
    own; no small captured series happens to contain a tie.
    """
    fixture = _load("series_nano_machine.html")
    rows = re.findall(r'<div class="chp-item">.*?</div>\s*</a>\s*</div>', fixture, re.S)
    assert len(rows) > 2, "fixture supplies the real row markup"

    newer, older = rows[0], rows[1]
    # Give the older row the newer one's number, leaving everything else real.
    older_tied = older.replace('title="Ch.271"', 'title="Ch.272"').replace(
        "> Ch.271<", "> Ch.272<"
    )
    upstream_order = newer + older_tied  # the site emits newest first

    chapters = parse_chapters(upstream_order, SERIES_KEY)

    assert [chapter.number for chapter in chapters] == [272, 272]
    assert chapters[0].release_date == "Jul 30, 2025", "older release comes first"
    assert chapters[1].release_date == "Aug 06, 2025"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Ch.272", 272),
        ("Chapter 260", 260),
        ("Ch. 1", 1),
        ("ch.994", 994),
        ("Ch. 16 This Bastard, He was Fooling Everyone <3>", 16),
        ("Vol.TBE Ch.1165", 1165),
        ("Chapter 0.5", 0.5),
        ("Chapter 28-5", 28.5),
        ("136.5 {NOTICE}", 136.5),
        ("TAL 0", 0),
        ("Chapter", None),
    ],
)
def test_parse_chapter_number(title: str, expected: float | None):
    assert parse_chapter_number(title) == expected


# ---------------------------------------------------------------------------
# Chapter pages
# ---------------------------------------------------------------------------


def test_first_reader_view_reports_the_whole_chapter_shape():
    """View 1 must yield the total image count and the view count, because
    that is what lets the connector fetch the rest in one parallel batch
    instead of walking views until one comes back empty."""
    pages, total_pages, total_views = parse_chapter_pages(
        _load("chapter_pages_1.html"), CHAPTER_KEY
    )

    assert len(pages) == IMAGES_PER_VIEW == 10
    assert total_pages == 13
    assert total_views == 2
    assert [page.number for page in pages] == list(range(1, 11))
    assert all(page.chapter_id == CHAPTER_KEY for page in pages)
    assert all(page.remote_url.startswith("https://") for page in pages)
    assert all(".movietop.cc/" in page.remote_url for page in pages)


def test_second_view_continues_the_global_numbering():
    """The ``i="1"`` attribute on each <img> restarts at 1 on every view, so
    numbering from it would produce pages 1-10 followed by another 1-3. The
    "<n>/<total>" label carries the global number and is what must be read."""
    pages, total_pages, _views = parse_chapter_pages(
        _load("chapter_pages_2.html"), CHAPTER_KEY
    )

    assert [page.number for page in pages] == [11, 12, 13]
    assert total_pages == 13


def test_page_ids_round_trip_through_slash_bearing_chapter_keys():
    page_id = make_page_id(CHAPTER_KEY, 11)

    assert page_id == "Ch-272/13661864:11"
    assert page_id_chapter_id(page_id) == CHAPTER_KEY
    assert page_id_chapter_id("no-colon-here") is None


def test_chapter_path_uses_the_ten_image_reader_view():
    # 10 is the largest the site honours; see mappers module docstring.
    assert (
        mappers.chapter_id_to_path(CHAPTER_KEY, 1)
        == "/chapter/Ch-272/13661864-10-1.html"
    )
    assert (
        mappers.chapter_id_to_path(CHAPTER_KEY, 2)
        == "/chapter/Ch-272/13661864-10-2.html"
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_results_parse():
    listing = parse_search_results(_load("search_sword_p3.html"), page=3)
    assert len(listing.items) >= 10
    assert all(series.canonical_path for series in listing.items)


def test_upstream_search_buries_manga_behind_novels():
    """The reason search coalesces several upstream pages.

    Novel Cool orders search results novels-first: upstream page 1 for "sword"
    contains NO manga at all. A connector that served page 1 alone would report
    that the site has no sword manga.
    """
    counts = [
        len(parse_series_cards(_load(f"search_sword_p{page}.html")))
        for page in (1, 2, 3)
    ]

    assert counts[0] == 0, "page 1 is all novels"
    assert sum(counts) >= 15, "the manga are there, further in"


# ---------------------------------------------------------------------------
# Connector request behaviour
# ---------------------------------------------------------------------------


def test_series_detail_and_chapter_list_share_a_single_fetch(
    connector: NovelCoolConnector,
):
    """The chapter rows are inline on the detail document. Fetching it twice
    would download ~300KB twice on every series open."""
    detail = _load("series_nano_machine.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        return detail

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)

    assert series is not None
    assert len(chapters) == 276
    assert calls == ["/novel/Nano-Machine.html"], "one fetch serves both stages"


def test_series_advertises_the_highest_numbered_chapter_as_latest(
    connector: NovelCoolConnector,
):
    """Nano Machine's list ends with an unnumbered "{NOTICE}" entry, so taking
    chapters[-1] blindly advertised that as the latest chapter of a series
    whose real head is Ch.272."""
    detail = _load("series_nano_machine.html")

    with patch.object(connector._http, "get_text", side_effect=lambda p, *, params=None: detail):
        series = connector.get_series(SERIES_KEY)

    assert series is not None
    assert series.latest_chapter == "Ch.272"
    assert series.chapter_count == 276


def test_chapter_pages_merge_every_view_in_order(connector: NovelCoolConnector):
    views = {
        "/chapter/Ch-272/13661864-10-1.html": _load("chapter_pages_1.html"),
        "/chapter/Ch-272/13661864-10-2.html": _load("chapter_pages_2.html"),
    }
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        return views[path]

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages(CHAPTER_KEY)

    assert [page.number for page in pages] == list(range(1, 14))
    assert len(set(page.remote_url for page in pages)) == 13
    assert sorted(calls) == sorted(views), "13 images cost 2 fetches, not 13"


def test_chapter_pages_are_cached_and_backfill_the_chapter_page_count(
    connector: NovelCoolConnector,
):
    detail = _load("series_nano_machine.html")
    views = {
        "/chapter/Ch-272/13661864-10-1.html": _load("chapter_pages_1.html"),
        "/chapter/Ch-272/13661864-10-2.html": _load("chapter_pages_2.html"),
    }
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        return views.get(path, detail)

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.get_chapter_pages(CHAPTER_KEY)
        before = len(calls)
        again = connector.get_chapter_pages(CHAPTER_KEY)
        chapters = connector.get_chapters(SERIES_KEY)

    assert len(again) == 13
    assert len(calls) == before + 1, "second read is cached; only the detail is fetched"
    target = next(chapter for chapter in chapters if chapter.id == CHAPTER_KEY)
    assert target.page_count == 13


def test_find_page_resolves_a_page_from_a_later_view(connector: NovelCoolConnector):
    views = {
        "/chapter/Ch-272/13661864-10-1.html": _load("chapter_pages_1.html"),
        "/chapter/Ch-272/13661864-10-2.html": _load("chapter_pages_2.html"),
    }

    with patch.object(
        connector._http, "get_text", side_effect=lambda p, *, params=None: views[p]
    ):
        page = connector.find_page(make_page_id(CHAPTER_KEY, 12))
        missing = connector.find_page(make_page_id(CHAPTER_KEY, 999))

    assert page is not None
    assert page.number == 12
    assert ".movietop.cc/" in page.remote_url
    assert missing is None


def test_browse_requests_a_distinct_path_per_mode(connector: NovelCoolConnector):
    html = _load("browse_index_page1.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        for mode, _label in mappers.BROWSE_MODES:
            connector.get_series_list(1, sort=mode)

    assert calls == [
        "/category/index_1.html",
        "/category/latest.html",
        "/category/new_list.html",
        "/category/updated_1.html",
        "/category/completed_1.html",
    ]
    assert len(set(calls)) == len(calls), "every mode is a genuinely different view"


def test_paged_mode_advances_the_path(connector: NovelCoolConnector):
    calls: list[str] = []

    with patch.object(
        connector._http,
        "get_text",
        side_effect=lambda p, *, params=None: (
            calls.append(p), _load("browse_index_page2.html")
        )[1],
    ):
        connector.get_series_list(2)

    assert calls == ["/category/index_2.html"]


def test_single_page_mode_answers_page_2_without_a_request(
    connector: NovelCoolConnector,
):
    """``latest_2.html`` does not 404 and does not continue the list — it
    serves the generic directory. The request must not be made at all."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        return _load("browse_latest.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        listing = connector.get_series_list(2, sort="latest")

    assert listing.items == []
    assert listing.has_more is False
    assert calls == [], "no request is made for a page that cannot exist"


def test_genre_browse_builds_the_paged_genre_path(connector: NovelCoolConnector):
    calls: list[str] = []

    with patch.object(
        connector._http,
        "get_text",
        side_effect=lambda p, *, params=None: (
            calls.append(p), _load("browse_genre_action.html")
        )[1],
    ):
        listing = connector.browse_by_genre("Action", 2)

    assert calls == ["/category/Action_2.html"]
    assert listing.items
    assert mappers.genre_path("Slice Of Life", 1) == "/category/Slice+Of+Life_1.html"


def test_search_coalesces_upstream_pages_to_get_past_the_novels(
    connector: NovelCoolConnector,
):
    """Upstream page 1 for "sword" has zero manga. One app search page must
    cover enough upstream pages to reach them."""
    pages = {
        1: _load("search_sword_p1.html"),
        2: _load("search_sword_p2.html"),
        3: _load("search_sword_p3.html"),
    }
    requested: list[int] = []

    def fake_get_text(path: str, *, params=None) -> str:
        assert path == "/search/"
        assert params is not None and params["name"] == "sword"
        page = int(params["page"])
        requested.append(page)
        return pages[page]

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        listing = connector.search_series("sword", 1)

    assert sorted(requested) == [1, 2, 3]
    assert len(requested) == SEARCH_PAGES_PER_REQUEST
    assert len(listing.items) >= 15, "the manga behind the novel prefix are reached"
    assert len({series.id for series in listing.items}) == len(listing.items)
    assert listing.has_more is True


def test_search_app_page_2_reads_the_next_span_of_upstream_pages(
    connector: NovelCoolConnector,
):
    """Paging must not re-serve upstream pages the reader already saw."""
    requested: list[int] = []

    def fake_get_text(path: str, *, params=None) -> str:
        requested.append(int(params["page"]))
        return _load("search_sword_p3.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.search_series("sword", 2)

    assert sorted(requested) == [4, 5, 6]


def test_search_does_not_fetch_pages_past_the_last_one(connector: NovelCoolConnector):
    """A one-page result set must cost exactly one request, not three.

    "nano machine" really does return a single page of three results upstream
    (captured from the VPS): the site renders the pager container but states no
    page total, which is how a one-page result set announces itself.
    """
    requested: list[int] = []

    def fake_get_text(path: str, *, params=None) -> str:
        requested.append(int(params["page"]))
        return _load("search_nano_machine.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        listing = connector.search_series("nano machine", 1)

    assert requested == [1], "a single-page result set costs a single request"
    assert listing.has_more is False
    assert listing.items


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_image_hosts_cover_every_cdn_shard(connector: NovelCoolConnector):
    """Page images round-robin across en2..en10.movietop.cc; the SSRF
    allowlist matches by domain suffix, so the registrable domain covers them
    all. Covers come from img.novelcool.com."""
    hosts = connector.allowed_image_hosts

    assert "movietop.cc" in hosts
    assert "novelcool.com" in hosts

    pages, _total, _views = parse_chapter_pages(
        _load("chapter_pages_1.html"), CHAPTER_KEY
    )
    for page in pages:
        host = page.remote_url.split("/")[2]
        assert any(
            host == allowed or host.endswith(f".{allowed}") for allowed in hosts
        ), host


def test_connector_identity_and_kind(connector: NovelCoolConnector):
    assert connector.source_type == "novelcool"
    assert connector.display_name == "Novel Cool"
    assert connector.content_kind == "manga"
    assert connector.is_mature is False
    assert connector.is_browsable is True
    assert connector.list_genres()


def test_connector_satisfies_the_configless_registry_contract():
    """Configless connectors are constructed with no arguments by the registry."""
    assert NovelCoolConnector().source_type == "novelcool"


def test_registry_lists_novelcool_once_wired():
    """Registration lives in registry.py, which this connector does not own.

    The integrator wires it; until then this skips rather than failing.
    """
    from connectors.registry import list_installed_connectors

    browsable = {item.source_type for item in list_installed_connectors(browsable_only=True)}
    if "novelcool" not in browsable:
        pytest.skip("novelcool not yet wired into registry.py (owned by the integrator)")
    assert "novelcool" in browsable
