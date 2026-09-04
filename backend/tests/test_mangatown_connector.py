"""MangaTown connector tests.

Every fixture in ``tests/fixtures/mangatown/`` was captured from the OVH VPS
(inside the ``manhwamaniacs-backend`` container), never from a laptop, so the
parsers here are exercised against exactly the bytes production receives.
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.base import SourceConnector
from connectors.mangatown.connector import MangaTownConnector
from connectors.mangatown.mappers import (
    build_pages,
    chapter_id_to_path,
    genre_path,
    listing_path,
    make_page_id,
    page_id_chapter_id,
    page_id_number,
    parse_chapter_meta,
    parse_chapters,
    parse_image_batch,
    parse_inline_image,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    parse_total_pages,
    series_id_to_path,
    unpack_packed_js,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mangatown"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def connector() -> MangaTownConnector:
    return MangaTownConnector()


# ---------------------------------------------------------------------------
# listing pages
# ---------------------------------------------------------------------------


def test_parse_series_list_reads_every_card_on_the_directory_page():
    listing = parse_series_list(_load("directory_p1.html"), page=1)

    assert len(listing.items) == 30
    first = listing.items[0]
    assert first.id == "tales_of_demons_and_gods"
    assert first.title == "Tales of Demons and Gods"
    assert first.cover_url.startswith("https://fmcdn.mangahere.com/")
    assert first.canonical_path == "/manga/tales_of_demons_and_gods/"
    # Every card must carry a usable identity and cover, not just the first.
    assert all(item.id and item.title and item.cover_url for item in listing.items)


def test_listing_cards_carry_author_status_genres_and_latest_chapter():
    items = parse_series_list(_load("directory_p1.html"), page=1).items
    first = items[0]

    assert first.author == "Mad Snail"
    assert first.status == "Ongoing"
    assert first.genres == ("Action", "Adventure")
    assert first.latest_chapter == "Tales of Demons and Gods 528.5"


def test_total_pages_comes_from_the_paginator_labels_not_the_sliding_window():
    """The visible page links are a window (1..8, then 334); only the
    ``<option>`` labels ("3/334") state the real total, so a parser that
    counted links would under-report on every page but the last."""
    html = _load("directory_p1.html")
    assert parse_total_pages(html) == 334

    listing = parse_series_list(html, page=1)
    assert listing.has_more is True
    assert listing.total == 334 * 30


def test_last_page_of_a_listing_reports_no_more():
    listing = parse_series_list(_load("directory_p1.html"), page=334)
    assert listing.has_more is False


def test_parse_search_results_uses_the_search_page_size():
    listing = parse_search_results(_load("search_naruto.html"), page=1)

    assert len(listing.items) == 20
    assert parse_total_pages(_load("search_naruto.html")) == 2
    assert listing.has_more is True
    assert "naruto" in listing.items[0].id


# ---------------------------------------------------------------------------
# series detail + chapters
# ---------------------------------------------------------------------------


def test_parse_series_detail_reads_every_metadata_field():
    series = parse_series_detail(_load("series_naruto.html"), "naruto")

    assert series is not None
    assert series.title == "Naruto"
    assert series.author == "KISHIMOTO Masashi"
    assert series.artist == "KISHIMOTO Masashi"
    assert series.cover_url.startswith("https://fmcdn.mangahere.com/")
    assert "Nine-tailed Demon Fox" in series.description


def test_status_survives_the_plural_label_suffix():
    """Regression: the site labels this field ``Status(s):``. Normalising the
    label with ``rstrip("(s)")`` is character-wise and yields "statu", which
    silently dropped status on every series."""
    series = parse_series_detail(_load("series_naruto.html"), "naruto")
    assert series.status == "Completed"


STATUS_WITH_BLURB_HTML = """
<h1 class="title-top">One Piece Green</h1>
<div class="detail_info clearfix"><img src="//example.test/c.jpg" />
<ul>
<li><b>Status(s):</b>Ongoing &nbsp;<a href="/manga/x/c002">One Piece Green 2</a> will coming soon</li>
</ul></div>
"""


def test_status_stops_at_the_promo_blurb_the_site_appends():
    """MangaTown packs a marketing line into the same <li> as the status, so
    flattening the whole element yields 'Ongoing One Piece Green 2 will coming
    soon' as the status string shown in the UI."""
    series = parse_series_detail(STATUS_WITH_BLURB_HTML, "one_piece_green")
    assert series.status == "Ongoing"


def test_detail_genres_include_the_demographic_and_are_deduped():
    series = parse_series_detail(_load("series_naruto.html"), "naruto")
    assert series.genres == ("Shounen", "Action", "Adventure", "Comedy", "Drama", "Fantasy")
    assert len(set(series.genres)) == len(series.genres)


def test_missing_series_is_detected_structurally_not_by_status_code():
    """MangaTown 302s an unknown slug to ``/search?stype=1&name=...`` and
    serves it with HTTP 200, so the absence of detail markup is the only
    honest not-found signal."""
    assert parse_series_detail(_load("series_missing.html"), "zzz_no_such_series_xyz") is None


def test_parse_chapters_returns_the_whole_list_oldest_first():
    chapters = parse_chapters(_load("series_naruto.html"), "naruto")

    assert len(chapters) == 752
    assert chapters[0].id == "naruto/v01/c000"
    assert chapters[-1].id == "naruto/v72/c700.6"
    numbers = [c.number for c in chapters]
    assert all(a <= b for a, b in zip(numbers, numbers[1:]))


UNNUMBERED_CHAPTER_HTML = """
<ul class="chapter_list">
    <li><a href="/manga/demo/omake-c/" name="">Demo Omake C</a><span class="time">Mar 03,2020</span></li>
    <li><a href="/manga/demo/omake-b/" name="">Demo Omake B</a><span class="time">Feb 02,2020</span></li>
    <li><a href="/manga/demo/omake-a/" name="">Demo Omake A</a><span class="time">Jan 01,2020</span></li>
</ul>
"""


def test_unnumbered_chapters_still_come_back_oldest_first():
    """MangaTown lists newest-first. Numbered chapters are re-sorted onto the
    site's own numbering, but rows it never numbered have only document order
    to go on -- those must still be flipped, or the reader opens a series at
    its newest extra and 'next chapter' walks backwards through time."""
    chapters = parse_chapters(UNNUMBERED_CHAPTER_HTML, "demo")

    assert [c.id for c in chapters] == [
        "demo/omake-a",
        "demo/omake-b",
        "demo/omake-c",
    ]
    assert all(c.number is None for c in chapters)


def test_chapter_numbers_come_from_the_sites_own_name_attribute():
    chapters = parse_chapters(_load("series_naruto.html"), "naruto")
    by_id = {c.id: c for c in chapters}

    assert by_id["naruto/v72/c700.6"].number == pytest.approx(700.6)
    assert by_id["naruto/v01/c001"].number == pytest.approx(1.0)
    assert all(isinstance(c.number, float) for c in chapters)


def test_chapter_keys_are_opaque_and_keep_their_slashes():
    chapters = parse_chapters(_load("series_naruto.html"), "naruto")
    volume_keys = [c.id for c in chapters if "/v" in c.id]

    assert volume_keys, "expected volume-scoped chapter keys"
    assert all(key.startswith("naruto/") for key in volume_keys)
    assert chapter_id_to_path("naruto/v01/c001") == "/manga/naruto/v01/c001/"


def test_chapters_carry_titles_and_release_dates():
    chapters = parse_chapters(_load("series_naruto.html"), "naruto")
    latest = chapters[-1]

    assert "700.6" in latest.title
    assert latest.release_date == "Apr 22,2016"
    assert all(c.title for c in chapters)


# ---------------------------------------------------------------------------
# chapter pages / packed image batch
# ---------------------------------------------------------------------------


def test_parse_chapter_meta_reads_total_pages_and_the_batch_id():
    """Both numbers drive the fast path: the reader never walks the chapter to
    learn its length, and ``chapter_id`` is the ``cid`` chapterfun.ashx wants."""
    assert parse_chapter_meta(_load("chapter_naruto_c001.html")) == (53, 15584)


def test_inline_image_is_taken_from_the_chapter_document():
    url = parse_inline_image(_load("chapter_naruto_c001.html"))
    assert url == (
        "https://zjcdn.mangahere.org/store/manga/8/01-001.0/compressed/naruto_v01.jpg"
    )


def test_unpack_packed_js_reverses_the_packer():
    script = unpack_packed_js(_load("chapterfun_p1.txt"))
    assert "pvalue" in script
    assert "zjcdn.mangahere.org" in script


def test_image_batch_yields_two_absolute_urls_per_call():
    """chapterfun.ashx answers with a look-ahead batch (the requested page and
    the next), which is what makes ceil(pages/2) calls enough for a chapter."""
    urls = parse_image_batch(_load("chapterfun_p1.txt"))

    assert urls == [
        "https://zjcdn.mangahere.org/store/manga/8/01-001.0/compressed/naruto_v01.jpg",
        "https://zjcdn.mangahere.org/store/manga/8/01-001.0/compressed/"
        "naruto_v01_ch001_005.jpg",
    ]


def test_image_batch_on_unknown_payload_is_empty_not_an_exception():
    assert parse_image_batch("not packed javascript") == []
    assert unpack_packed_js("not packed javascript") == ""


# ---------------------------------------------------------------------------
# identity keys
# ---------------------------------------------------------------------------


def test_page_id_round_trips_a_chapter_key_containing_slashes():
    page_id = make_page_id("naruto/v01/c001", 7)

    assert page_id == "naruto/v01/c001:7"
    assert page_id_chapter_id(page_id) == "naruto/v01/c001"
    assert page_id_number(page_id) == 7


def test_paths_are_built_from_opaque_keys():
    assert series_id_to_path("naruto") == "/manga/naruto/"
    assert listing_path(1) == "/directory/1.htm"
    assert listing_path(3, sort="rating") == "/directory/3.htm?rating.za"
    assert listing_path(2, sort="latest") == "/latest/2.htm"
    assert genre_path("action", 2) == "/directory/0-action-0-0-0-0/2.htm"


def test_build_pages_orders_by_page_number():
    pages = build_pages("naruto/v01/c001", {2: "b.jpg", 1: "a.jpg", 3: "c.jpg"})
    assert [p.number for p in pages] == [1, 2, 3]
    assert [p.remote_url for p in pages] == ["a.jpg", "b.jpg", "c.jpg"]
    assert pages[0].id == "naruto/v01/c001:1"


# ---------------------------------------------------------------------------
# connector wiring / efficiency
# ---------------------------------------------------------------------------


def test_connector_implements_the_full_contract(connector: MangaTownConnector):
    assert isinstance(connector, SourceConnector)
    assert connector.source_type == "mangatown"
    # find_page MUST be overridden -- the base traversal is O(n^3).
    assert type(connector).find_page is not SourceConnector.find_page


def test_series_detail_and_chapters_share_a_single_fetch(connector: MangaTownConnector):
    """The chapter list ships inside the series page, so opening a series must
    cost ONE request even though two public methods are called."""
    html = _load("series_naruto.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        series = connector.get_series("naruto")
        chapters = connector.get_chapters("naruto")

    assert calls == ["/manga/naruto/"]
    assert series.title == "Naruto"
    assert series.chapter_count == 752
    assert len(chapters) == 752
    assert series.latest_chapter == chapters[-1].title


def test_unknown_series_returns_none_without_raising(connector: MangaTownConnector):
    with patch.object(connector._http, "get_text", return_value=_load("series_missing.html")):
        assert connector.get_series("zzz_no_such_series_xyz") is None
        assert connector.get_chapters("zzz_no_such_series_xyz") == []


def test_chapter_pages_use_the_batch_endpoint_not_one_fetch_per_page(
    connector: MangaTownConnector,
):
    """The naive reading of this site is one 173 KB page fetch per image (53
    for this chapter). The batch endpoint must resolve the whole chapter in
    ceil(pages/2) calls instead, page 1 coming free from the chapter document."""
    chapter_html = _load("chapter_naruto_c001.html")
    batch = _load("chapterfun_p1.txt")
    paths: list[str] = []
    params_seen: list[dict | None] = []

    def fake_get_text(path: str, *, params=None):
        paths.append(path)
        params_seen.append(params)
        if path.endswith("chapterfun.ashx"):
            return batch
        return chapter_html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages("naruto/v01/c001")

    assert len(pages) == 53
    assert [p.number for p in pages] == list(range(1, 54))
    assert all(p.remote_url and p.remote_url.startswith("https://") for p in pages)

    chapter_fetches = [p for p in paths if not p.endswith("chapterfun.ashx")]
    batch_fetches = [p for p in paths if p.endswith("chapterfun.ashx")]
    assert chapter_fetches == ["/manga/naruto/v01/c001/"]
    # Page 1 is served inline, so pages 2..53 need ceil(52/2) = 26 batches.
    assert len(batch_fetches) == math.ceil(52 / 2) == 26
    assert len(batch_fetches) < 53
    assert batch_fetches[0] == "/manga/naruto/v01/c001/chapterfun.ashx"
    cids = {p["cid"] for p in params_seen if p and "cid" in p}
    assert cids == {15584}


def test_chapter_pages_are_cached_so_find_page_costs_nothing_extra(
    connector: MangaTownConnector,
):
    chapter_html = _load("chapter_naruto_c001.html")
    batch = _load("chapterfun_p1.txt")

    def fake_get_text(path: str, *, params=None):
        return batch if path.endswith("chapterfun.ashx") else chapter_html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text) as mocked:
        connector.get_chapter_pages("naruto/v01/c001")
        first_call_count = mocked.call_count
        page = connector.find_page("naruto/v01/c001:5")
        assert mocked.call_count == first_call_count

    assert page is not None
    assert page.number == 5
    assert page.chapter_id == "naruto/v01/c001"


def test_find_page_rejects_an_id_without_a_page_suffix(connector: MangaTownConnector):
    assert connector.find_page("naruto/v01/c001") is None


def test_a_chapter_without_reader_metadata_falls_back_to_the_inline_image(
    connector: MangaTownConnector,
):
    stripped = _load("chapter_naruto_c001.html").replace("var total_pages", "var x_pages")
    with patch.object(connector._http, "get_text", return_value=stripped):
        pages = connector.get_chapter_pages("naruto/v01/c001")

    assert len(pages) == 1
    assert pages[0].number == 1
    assert pages[0].remote_url.endswith("naruto_v01.jpg")


def test_browse_modes_request_distinct_paths(connector: MangaTownConnector):
    html = _load("directory_p1.html")
    paths: list[str] = []

    def fake_get_text(path: str, *, params=None):
        paths.append(path)
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        for mode in connector.list_browse_modes():
            connector.get_series_list(1, sort=mode.id)

    assert len(set(paths)) == len(paths), f"browse modes collapsed onto one path: {paths}"
    assert "/directory/1.htm" in paths
    assert "/latest/1.htm" in paths
    assert "/hot/1.htm" in paths


def test_search_hits_the_search_endpoint_with_name_and_page(
    connector: MangaTownConnector,
):
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return _load("search_naruto.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        listing = connector.search_series("naruto", 2)

    assert captured == [("/search", {"name": "naruto", "page": 2})]
    assert len(listing.items) == 20


def test_genre_browse_uses_the_allowed_directory_form(connector: MangaTownConnector):
    """``/directory/0-<genre>-0-0-0-0/`` is the site's own genre link shape and
    is NOT one of the ``/directory/q*`` faceted paths robots.txt disallows."""
    captured: list[str] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(path)
        return _load("directory_p1.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.browse_by_genre("action", 2)

    assert captured == ["/directory/0-action-0-0-0-0/2.htm"]
    assert all(not path.startswith("/directory/q") for path in captured)

    with pytest.raises(NotImplementedError):
        connector.browse_by_genre("no_such_genre", 1)


def test_image_hosts_and_referer_cover_both_cdns(connector: MangaTownConnector):
    """Both CDNs answer 403 without a Referer (verified from the VPS)."""
    hosts = connector.allowed_image_hosts
    assert "mangahere.org" in hosts  # zjcdn.* page images
    assert "mangahere.com" in hosts  # fmcdn.* covers
    assert connector.image_fetch_headers()["Referer"] == "https://www.mangatown.com/"
