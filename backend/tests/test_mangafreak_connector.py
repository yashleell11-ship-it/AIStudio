"""Tests for the MangaFreak connector.

Fixtures under ``tests/fixtures/mangafreak/`` were captured from the
production container on the VPS, so they carry the exact markup (and the
exact quirks) the connector meets in production.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.mangafreak.connector import MangaFreakConnector
from connectors.mangafreak.mappers import (
    is_series_document,
    make_page_id,
    page_id_chapter_key,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_genre_list,
    parse_latest_releases,
    parse_mangalist,
    parse_ranking,
    parse_search_results,
    parse_series_detail,
)
from connectors.registry import list_installed_connectors

FIXTURES = Path(__file__).parent / "fixtures" / "mangafreak"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def connector() -> MangaFreakConnector:
    return MangaFreakConnector()


def _registered() -> bool:
    return "mangafreak" in {c.source_type for c in list_installed_connectors()}


# --------------------------------------------------------------------------
# listing parsers
# --------------------------------------------------------------------------


def test_parse_mangalist_reads_every_card():
    listing = parse_mangalist(_load("mangalist_page1.html"), page=1)

    assert len(listing.items) == 18
    first = listing.items[0]
    assert first.id.startswith("Honyaku_No_Sainou")
    assert first.title.startswith('"Honyaku" no Sainou')
    assert first.canonical_path == f"/Manga/{first.id}"
    assert first.cover_url == (
        "https://images.mangafreak.me/mini_images/"
        "honyaku_no_sainou_de_ore_dake_ga_sekai_wo_kaihen_dekiru_ken_hazure_"
        "sainou_honyaku_de_kizukeba_sekai_saikyou_ni_nattemashita/100x140"
    )
    assert first.status == "Ongoing"
    assert first.chapter_count == 23
    # Directory runs to 402 pages, so page 1 must offer more.
    assert listing.has_more is True
    assert listing.page_size == 18


def test_mangalist_page_2_holds_different_series():
    page1 = parse_mangalist(_load("mangalist_page1.html"), page=1)
    page2 = parse_mangalist(_load("mangalist_page2.html"), page=2)

    assert {s.id for s in page1.items}.isdisjoint({s.id for s in page2.items})


def test_parse_latest_releases_reads_series_and_latest_chapter():
    listing = parse_latest_releases(_load("latest_page1.html"), page=1)

    assert len(listing.items) == 30
    first = listing.items[0]
    assert first.id == (
        "Tensei_Shite_High_Elf_Ni_Narimashitaga_Slow_Life_Wa_120_Nen_De_Akimashita"
    )
    assert first.title.startswith("Tensei Shite High Elf")
    assert first.cover_url.endswith("/55x85")
    assert first.latest_chapter is not None and first.latest_chapter.endswith("53")
    assert listing.page_size == 30


def test_parse_ranking_reads_genre_page():
    listing = parse_ranking(_load("genre_action_page1.html"), page=1)

    assert len(listing.items) == 15
    first = listing.items[0]
    assert first.id == "One_Piece"
    assert first.title == "One Piece"
    assert first.author == "Oda, Eiichiro"
    assert first.status == "Ongoing"
    assert first.chapter_count == 1190
    assert first.cover_url.endswith("/manga_images/one_piece.jpg")
    assert listing.page_size == 15


def test_parse_search_results_reads_items_and_genres():
    listing = parse_search_results(_load("search_study.html"), page=1)

    assert len(listing.items) == 7
    first = listing.items[0]
    assert first.id == "A_Simple_Thinking_About_Blood_Types"
    assert first.title == "A Simple Thinking About Blood Types"
    assert first.chapter_count == 16
    assert first.status == "Ongoing"
    assert first.genres == ("Comedy", "Psychological", "Slice Of Life")
    # This query fits on one page, so the paginator must not invent more.
    assert listing.has_more is False


def test_pagination_totals_come_from_the_last_page_link():
    mangalist = parse_mangalist(_load("mangalist_page1.html"), page=1)
    genre = parse_ranking(_load("genre_action_page1.html"), page=1)

    # 402 pages x 18 per page, 62 x 15 -- read off the "»" link.
    assert mangalist.total == 402 * 18
    assert genre.total == 62 * 15


def test_parse_genre_list_returns_real_genres():
    genres = dict(parse_genre_list(_load("genre_action_page1.html")))

    assert "Action" in genres
    assert genres["Web_Comic"] == "Web Comic"
    # "All" is the unfiltered view, not a genre.
    assert "All" not in genres


# --------------------------------------------------------------------------
# series detail + chapters
# --------------------------------------------------------------------------


def test_parse_series_detail_reads_metadata():
    series = parse_series_detail(_load("series_study_group.html"), "Study_Group")

    assert series is not None
    assert series.title == "Study Group"
    assert series.author == "Hyungwook Shin"
    assert series.artist == "Seungyeon Ryu"
    assert series.status == "Ongoing"
    assert series.genres == (
        "Action",
        "Comedy",
        "Martial Arts",
        "School Life",
        "Shounen",
    )
    assert series.cover_url == (
        "https://images.mangafreak.me/manga_images/study_group.jpg"
    )
    assert series.description is not None
    assert "Gamin Yoon" in series.description


def test_parse_chapters_reads_the_whole_table_in_order():
    chapters = parse_chapters(_load("series_study_group.html"), "Study_Group")

    assert len(chapters) == 343
    assert len({c.id for c in chapters}) == 343
    assert chapters[0].id == "Read1_Study_Group_1"
    assert chapters[0].number == 1.0
    assert chapters[0].release_date == "2019/07/13"
    assert chapters[-1].id == "Read1_Study_Group_341"
    assert chapters[-1].number == 341.0
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers)
    assert all(c.series_id == "Study_Group" for c in chapters)


def test_split_chapters_sort_after_their_base_without_colliding():
    """MangaFreak marks split releases with a letter suffix (234e, 234i).

    They must stay distinct from chapter 234 and from each other, and must sit
    between 234 and 235 -- otherwise the reader's "next chapter" walks the
    series in the wrong order.
    """
    chapters = parse_chapters(_load("series_study_group.html"), "Study_Group")
    by_id = {c.id: c.number for c in chapters}

    assert by_id["Read1_Study_Group_234"] == 234.0
    assert by_id["Read1_Study_Group_234e"] == pytest.approx(234.05)
    assert by_id["Read1_Study_Group_234i"] == pytest.approx(234.09)
    assert (
        by_id["Read1_Study_Group_234"]
        < by_id["Read1_Study_Group_234e"]
        < by_id["Read1_Study_Group_234i"]
        < by_id["Read1_Study_Group_235"]
    )
    assert len({n for n in by_id.values()}) == len(by_id)


@pytest.mark.parametrize(
    ("chapter_key", "expected"),
    [
        ("Read1_One_Piece_1053", 1053.0),
        ("Read1_One_Piece_1053a", 1053.01),
        ("Read1_One_Piece_1053b", 1053.02),
        ("Read1_My_Hero_Academia_430f", 430.06),
    ],
)
def test_parse_chapter_number_handles_suffixes(chapter_key: str, expected: float):
    assert parse_chapter_number(chapter_key) == pytest.approx(expected)


# --------------------------------------------------------------------------
# the homepage-instead-of-404 trap
# --------------------------------------------------------------------------


def test_is_series_document_separates_a_real_series_from_the_homepage():
    """The structural guard itself, tested directly.

    Everything else about a missing series looks fine -- HTTP 200, a full
    HTML document -- so this marker check is the ONLY thing standing between
    the reader and a homepage parsed as a series. Asserting it here means a
    regression in the markers fails loudly instead of being masked by some
    incidental difference between the two documents.
    """
    assert is_series_document(_load("series_study_group.html")) is True
    assert is_series_document(_load("missing_series_homepage.html")) is False


def test_missing_series_is_rejected_although_it_answers_http_200():
    """MangaFreak serves the FULL HOMEPAGE (HTTP 200) for an unknown series.

    Nothing about the response says "not found", so a parser that trusts the
    status code would happily return a homepage-shaped series. Both the detail
    and chapter parsers must reject it on structure.
    """
    homepage = _load("missing_series_homepage.html")

    assert parse_series_detail(homepage, "Nope_Not_Real_Zzz") is None
    assert parse_chapters(homepage, "Nope_Not_Real_Zzz") == []


def test_connector_returns_none_for_a_series_that_answers_with_the_homepage(
    connector: MangaFreakConnector,
):
    homepage = _load("missing_series_homepage.html")

    with patch.object(connector._http, "get_text", return_value=homepage):
        assert connector.get_series("Nope_Not_Real_Zzz") is None
        assert connector.get_chapters("Nope_Not_Real_Zzz") == []


# --------------------------------------------------------------------------
# chapter pages
# --------------------------------------------------------------------------


def test_parse_chapter_pages_reads_every_image_in_order():
    pages = parse_chapter_pages(
        _load("chapter_study_group_341.html"), "Read1_Study_Group_341"
    )

    assert len(pages) == 40
    assert [p.number for p in pages] == list(range(1, 41))
    assert pages[0].remote_url == (
        "https://images.mangafreak.me/mangas/study_group/study_group_341/"
        "study_group_341_1.jpg"
    )
    assert pages[-1].remote_url.endswith("study_group_341_40.jpg")
    assert all(p.chapter_id == "Read1_Study_Group_341" for p in pages)
    assert pages[0].id == "Read1_Study_Group_341:1"


def test_chapter_pages_exclude_the_social_share_icons():
    """The reader document also carries six /share/*.webp icons.

    They sit in exactly the same <img src=...> shape as the page images, so a
    naive image scrape ships them as readable pages.
    """
    pages = parse_chapter_pages(
        _load("chapter_study_group_341.html"), "Read1_Study_Group_341"
    )

    assert all("/mangas/" in p.remote_url for p in pages)
    assert not any("/share/" in p.remote_url for p in pages)


def test_page_id_round_trips_through_the_chapter_key():
    """Chapter keys contain underscores, so the separator must not be one."""
    page_id = make_page_id("Read1_Study_Group_341", 7)

    assert page_id == "Read1_Study_Group_341:7"
    assert page_id_chapter_key(page_id) == "Read1_Study_Group_341"


# --------------------------------------------------------------------------
# connector behaviour: request shape and caching (the speed contract)
# --------------------------------------------------------------------------


def test_series_and_chapters_share_a_single_fetch(connector: MangaFreakConnector):
    """Opening a series then listing its chapters must cost ONE request.

    The detail document already contains the whole chapter table; fetching it
    twice doubles the cost of the app's most common interaction.
    """
    detail = _load("series_study_group.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return detail

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        series = connector.get_series("Study_Group")
        chapters = connector.get_chapters("Study_Group")

    assert calls == ["/Manga/Study_Group"]
    assert series is not None
    assert series.chapter_count == 343
    assert series.latest_chapter == "Chapter 341"
    assert len(chapters) == 343


def test_chapters_first_also_primes_the_series_cache(connector: MangaFreakConnector):
    """The saving must hold whichever entry point the client hits first."""
    detail = _load("series_study_group.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return detail

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.get_chapters("Study_Group")
        series = connector.get_series("Study_Group")

    assert calls == ["/Manga/Study_Group"]
    assert series is not None and series.title == "Study Group"


def test_whole_chapter_costs_one_request_and_find_page_reuses_it(
    connector: MangaFreakConnector,
):
    """Page images resolve from one reader fetch, never one request per page."""
    chapter = _load("chapter_study_group_341.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return chapter

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages("Read1_Study_Group_341")
        again = connector.get_chapter_pages("Read1_Study_Group_341")
        found = connector.find_page("Read1_Study_Group_341:7")

    assert calls == ["/Read1_Study_Group_341"]
    assert len(pages) == 40 and len(again) == 40
    assert found is not None
    assert found.number == 7
    assert found.remote_url.endswith("study_group_341_7.jpg")


def test_reading_a_chapter_backfills_its_page_count_on_the_chapter_list(
    connector: MangaFreakConnector,
):
    detail = _load("series_study_group.html")
    chapter = _load("chapter_study_group_341.html")

    def fake_get_text(path: str, *, params=None):
        return chapter if path.startswith("/Read1_") else detail

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        assert all(c.page_count == 0 for c in connector.get_chapters("Study_Group"))
        connector.get_chapter_pages("Read1_Study_Group_341")
        chapters = connector.get_chapters("Study_Group")

    by_id = {c.id: c.page_count for c in chapters}
    assert by_id["Read1_Study_Group_341"] == 40
    assert by_id["Read1_Study_Group_340"] == 0


def test_search_paginates_with_a_query_param_not_a_path_segment(
    connector: MangaFreakConnector,
):
    """`/Find/<q>/2` answers HTTP 200 with ZERO results on this site.

    Using the path form would silently report "no results" for every page
    after the first instead of failing loudly, so the query-param form is
    part of the contract.
    """
    html = _load("search_study.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.search_series("Study", 1)
        connector.search_series("Study", 2)

    assert calls == ["/Find/study", "/Find/study?page=2"]


def test_browse_modes_map_to_distinct_endpoints(connector: MangaFreakConnector):
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        if path.startswith("/Latest_Releases"):
            return _load("latest_page1.html")
        if path.startswith("/Mangalist"):
            return _load("mangalist_page1.html")
        return _load("genre_action_page1.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        for mode in (m.id for m in connector.list_browse_modes()):
            connector.get_series_list(1, sort=mode)
        connector.browse_by_genre("Action", 2)

    assert calls == [
        "/Latest_Releases/1",
        "/Genre/All/1",
        "/Mangalist/All/1",
        "/Genre/Action/2",
    ]
    assert len(set(calls)) == len(calls)


def test_series_id_accepts_a_full_path(connector: MangaFreakConnector):
    """Identity keys are opaque, but a stored canonical_path must still work."""
    detail = _load("series_study_group.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return detail

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        assert connector.get_series("/Manga/Study_Group") is not None

    assert calls == ["/Manga/Study_Group"]


def test_image_proxy_allowlist_covers_the_cdn(connector: MangaFreakConnector):
    hosts = connector.allowed_image_hosts

    assert "mangafreak.me" in hosts
    page = parse_chapter_pages(
        _load("chapter_study_group_341.html"), "Read1_Study_Group_341"
    )[0]
    assert page.remote_url.startswith("https://images.mangafreak.me/")


@pytest.mark.skipif(
    not _registered(), reason="registry wiring is done by the integrator"
)
def test_registry_lists_mangafreak():
    browsable = [c.source_type for c in list_installed_connectors(browsable_only=True)]
    assert "mangafreak" in browsable
