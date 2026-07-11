from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.cf_client import is_cloudflare_challenge
from connectors.registry import create_connector, list_installed_connectors
from connectors.toonily.connector import ToonilyConnector
from connectors.toonily.mappers import (
    chapter_id_sort_key,
    parse_chapter_pages,
    parse_chapter_segment,
    parse_chapters,
    parse_series_list,
)

FIXTURES = Path(__file__).parent / "fixtures" / "toonily"
SERIES_ID = "the-beginning-after-the-end-7b1d8c89"
MADARA_SUBCHAPTER_SEGMENTS = (
    "chapter-175-8",
    "chapter-175-8_1",
    "chapter-175-8_2",
    "chapter-175-8_11",
    "chapter-175-9",
)


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def toonily_connector() -> ToonilyConnector:
    return ToonilyConnector()


def test_registry_lists_toonily():
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    assert "toonily" in browsable


def test_cloudflare_challenge_detection():
    assert is_cloudflare_challenge("<title>Just a moment...</title>")
    assert not is_cloudflare_challenge('<div class="page-item-detail">')
    assert not is_cloudflare_challenge(
        '<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1"></script>'
        '<div class="page-item-detail"></div>'
    )


def test_parse_series_list_from_fixture():
    html = _load("browse_latest.html")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) >= 10
    assert listing.has_more is True
    assert listing.items[0].id == "the-beginning-after-the-end-7b1d8c89"
    assert listing.items[0].cover_url


def test_browse_page_2_differs_from_page_1(toonily_connector: ToonilyConnector):
    page1 = _load("browse_latest.html")
    page2 = _load("browse_page2.html")

    def fake_get_text(path: str, *, params=None):
        if path.endswith("/page/2/"):
            return page2
        return page1

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        first = toonily_connector.get_series_list(1)
        second = toonily_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id
    assert first.has_more is True


def test_browse_uses_webtoons_path_and_sort(toonily_connector: ToonilyConnector):
    html = _load("browse_latest.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        toonily_connector.get_series_list(1)
        toonily_connector.get_series_list(2, sort="popular")

    assert captured[0][0] == "/webtoons/"
    assert captured[0][1] == {}
    assert captured[1][0] == "/webtoons/page/2/"
    assert captured[1][1] == {"m_orderby": "views"}


def test_each_browse_mode_requests_a_distinct_order_value(
    toonily_connector: ToonilyConnector,
):
    html = _load("browse_latest.html")
    captured: list[dict | None] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return html

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        toonily_connector.get_series_list(1, sort="default")
        toonily_connector.get_series_list(1, sort="latest")
        toonily_connector.get_series_list(1, sort="popular")
        toonily_connector.get_series_list(1, sort="rating")

    order_values = [
        (params or {}).get("m_orderby", "latest")
        for params in captured
    ]
    assert order_values == ["latest", "new-manga", "views", "ratings"]
    assert len(set(order_values)) == 4


def test_browse_modes_parse_into_different_series_lists():
    latest_html = _load("browse_latest.html")
    popular_html = _load("browse_popular.html")

    latest_listing = parse_series_list(latest_html, page=1)
    popular_listing = parse_series_list(popular_html, page=1)

    assert latest_listing.items[0].id != popular_listing.items[0].id


def test_search_finds_titles_not_on_browse_page_1(toonily_connector: ToonilyConnector):
    browse_html = _load("browse_latest.html")
    search_html = _load("search_solo.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search_html
        return browse_html

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        browse = toonily_connector.get_series_list(1)
        search = toonily_connector.search_series("solo leveling", 1)

    browse_ids = {item.id for item in browse.items}
    assert search.items
    assert any("solo" in item.title.casefold() for item in search.items)
    assert any(item.id not in browse_ids for item in search.items)


def test_parse_chapter_pages_extracts_image_urls():
    html = _load("chapter_reader.html")
    chapter_id = "the-beginning-after-the-end-7b1d8c89/chapter-240"
    pages = parse_chapter_pages(html, chapter_id)
    assert len(pages) == 3
    assert all(page.remote_url and "tnlycdn.com" in page.remote_url for page in pages)


def _chapter_id(series_id: str, segment: str) -> str:
    return f"{series_id}/{segment}"


def _adjacent_chapter_ids(chapters, chapter_id: str) -> tuple[str | None, str | None]:
    chapter_index = next(index for index, chapter in enumerate(chapters) if chapter.id == chapter_id)
    previous_id = chapters[chapter_index - 1].id if chapter_index > 0 else None
    next_id = chapters[chapter_index + 1].id if chapter_index < len(chapters) - 1 else None
    return previous_id, next_id


def test_madara_subchapter_segments_parse_display_number():
    assert parse_chapter_segment("chapter-175-8") == 175.8
    assert parse_chapter_segment("chapter-175-8_1") == 175.8
    assert parse_chapter_segment("chapter-175-8_2") == 175.8
    assert parse_chapter_segment("chapter-175-8_11") == 175.8
    assert parse_chapter_segment("chapter-175-9") == 175.9


def test_madara_subchapter_segments_have_distinct_sort_keys():
    keys = [chapter_id_sort_key(_chapter_id(SERIES_ID, segment)) for segment in MADARA_SUBCHAPTER_SEGMENTS]
    assert keys == [
        (175, 8, 0),
        (175, 8, 1),
        (175, 8, 2),
        (175, 8, 11),
        (175, 9, 0),
    ]
    assert len(set(keys)) == len(keys)


def test_madara_subchapters_ordered_from_real_fixture():
    html = _load("chapters_175_8_madara.html")
    chapters = parse_chapters(html, SERIES_ID)
    ordered_segments = [chapter.id.rsplit("/", 1)[-1] for chapter in chapters]

    for left, right in zip(MADARA_SUBCHAPTER_SEGMENTS, MADARA_SUBCHAPTER_SEGMENTS[1:]):
        assert ordered_segments.index(left) < ordered_segments.index(right)

    assert ordered_segments.index("chapter-175-7") < ordered_segments.index("chapter-175-8")
    subchapter_segments = [
        segment for segment in ordered_segments if segment.startswith("chapter-175-8")
    ]
    assert subchapter_segments == sorted(
        subchapter_segments,
        key=lambda segment: chapter_id_sort_key(_chapter_id(SERIES_ID, segment)),
    )
    assert all(chapter.number == 175.8 for chapter in chapters if "chapter-175-8" in chapter.id)


def test_madara_subchapters_not_sorted_to_beginning():
    html = _load("chapters_175_8_madara.html")
    chapters = parse_chapters(html, SERIES_ID)
    first_segment = chapters[0].id.rsplit("/", 1)[-1]

    assert first_segment == "chapter-175-7"
    assert chapters[0].number == 175.7
    assert all(chapter.number is not None for chapter in chapters)


def test_madara_subchapter_adjacent_navigation_from_real_fixture():
    html = _load("chapters_175_8_madara.html")
    chapters = parse_chapters(html, SERIES_ID)

    teaser_id = _chapter_id(SERIES_ID, "chapter-175-8")
    part_one_id = _chapter_id(SERIES_ID, "chapter-175-8_1")
    part_two_id = _chapter_id(SERIES_ID, "chapter-175-8_2")
    part_eleven_id = _chapter_id(SERIES_ID, "chapter-175-8_11")
    next_main_id = _chapter_id(SERIES_ID, "chapter-175-9")

    assert _adjacent_chapter_ids(chapters, part_one_id) == (teaser_id, part_two_id)
    assert _adjacent_chapter_ids(chapters, part_eleven_id) == (
        _chapter_id(SERIES_ID, "chapter-175-8_9"),
        next_main_id,
    )
    assert _adjacent_chapter_ids(chapters, teaser_id)[0] == _chapter_id(SERIES_ID, "chapter-175-7")


def test_madara_subchapter_adjacent_navigation_via_connector(toonily_connector: ToonilyConnector):
    html = _load("chapters_175_8_madara.html")

    def fake_get_text(path: str, *, params=None):
        if path == f"/serie/{SERIES_ID}/":
            return html
        raise AssertionError(path)

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        chapters = toonily_connector.get_chapters(SERIES_ID)

    part_one_id = _chapter_id(SERIES_ID, "chapter-175-8_1")
    assert _adjacent_chapter_ids(chapters, part_one_id) == (
        _chapter_id(SERIES_ID, "chapter-175-8"),
        _chapter_id(SERIES_ID, "chapter-175-8_2"),
    )


def test_parse_chapters_filters_by_series():
    html = _load("series_detail.html")
    chapters = parse_chapters(html, SERIES_ID)
    assert len(chapters) >= 2
    assert chapters[0].series_id == SERIES_ID
    assert chapters[-1].number == 240.0
    part_eleven = next(
        chapter for chapter in chapters if chapter.id.endswith("chapter-175-8_11")
    )
    assert part_eleven.number == 175.8


def test_create_toonily_connector():
    connector = create_connector("toonily")
    assert connector.source_type == "toonily"


def test_list_browse_modes(toonily_connector: ToonilyConnector):
    modes = toonily_connector.list_browse_modes()
    mode_ids = {mode.id for mode in modes}
    assert "popular" in mode_ids
    assert "latest" in mode_ids
    assert "default" in mode_ids


def test_allowed_image_hosts(toonily_connector: ToonilyConnector):
    hosts = toonily_connector.allowed_image_hosts
    assert "tnlycdn.com" in hosts


def test_image_fetch_headers_include_toonily_referer(toonily_connector: ToonilyConnector):
    assert toonily_connector.image_fetch_headers()["Referer"] == "https://toonily.com/"


def test_pull_yourself_fixture_chapter_count():
    html = _load("pull_yourself_series_detail.html")
    chapters = parse_chapters(html, "pull-yourself-together-team-leader-04cfa291")
    assert len(chapters) == 17
    assert chapters[0].number == 1.0
    assert chapters[-1].number == 18.0


def test_get_chapters_pull_yourself_via_connector(toonily_connector: ToonilyConnector):
    html = _load("pull_yourself_series_detail.html")
    series_id = "pull-yourself-together-team-leader-04cfa291"

    def fake_get_text(path: str, *, params=None):
        if path == f"/serie/{series_id}/":
            return html
        raise AssertionError(path)

    with patch.object(toonily_connector._http, "get_text", side_effect=fake_get_text):
        chapters = toonily_connector.get_chapters(series_id)

    assert len(chapters) == 17
    assert chapters[0].title == "Chapter 1"
