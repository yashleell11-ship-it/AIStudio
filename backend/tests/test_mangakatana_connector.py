from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.mangakatana.connector import MangaKatanaConnector
from connectors.mangakatana.mappers import parse_chapter_pages, parse_chapters, parse_series_list
from connectors.registry import create_connector, list_installed_connectors

FIXTURES = Path(__file__).parent / "fixtures" / "mangakatana"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def mangakatana_connector() -> MangaKatanaConnector:
    return MangaKatanaConnector()


def test_registry_lists_mangakatana():
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    assert "mangakatana" in browsable


def test_parse_series_list_from_fixture():
    html = _load("browse_page1.html")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) >= 10
    assert listing.has_more is True
    assert listing.items[0].id
    assert listing.items[0].cover_url


def test_browse_page_2_differs_from_page_1(mangakatana_connector: MangaKatanaConnector):
    page1 = _load("browse_page1.html")
    page2 = _load("browse_page2.html")

    def fake_get_text(path: str, *, params=None):
        if path.endswith("/page/2"):
            return page2
        return page1

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        first = mangakatana_connector.get_series_list(1)
        second = mangakatana_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id
    assert first.has_more is True


def test_browse_uses_page_path_and_filter(mangakatana_connector: MangaKatanaConnector):
    html = _load("browse_page1.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        mangakatana_connector.get_series_list(1)
        mangakatana_connector.get_series_list(2, sort="popular")

    assert captured[0][0] == "/manga/page/1"
    assert captured[0][1] == {"filter": 1, "order": "latest"}
    assert captured[1][0] == "/manga/page/2"
    assert captured[1][1] == {"filter": 1, "order": "numc"}


def test_each_browse_mode_requests_a_distinct_order_value(
    mangakatana_connector: MangaKatanaConnector,
):
    """Regression test for the sort bug: MangaKatana silently ignores `order`
    unless `filter=1` is also present, so every mode fell back to the same
    default listing. Each of the four exposed modes must now request a
    genuinely distinct `order` value, always alongside `filter=1`."""
    html = _load("browse_page1.html")
    captured: list[dict | None] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return html

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        mangakatana_connector.get_series_list(1, sort="default")
        mangakatana_connector.get_series_list(1, sort="latest")
        mangakatana_connector.get_series_list(1, sort="popular")
        mangakatana_connector.get_series_list(1, sort="rating")

    assert all(params is not None and params.get("filter") == 1 for params in captured)
    order_values = [params["order"] for params in captured]
    assert order_values == ["latest", "new", "numc", "az"]
    # All four must be distinct -- this is the exact condition that was
    # broken (every mode used to collapse onto the same request).
    assert len(set(order_values)) == 4


def test_browse_modes_parse_into_different_series_lists():
    """End-to-end regression test using real captured HTML: two distinct
    `order` values must yield different first-page series lists, not just
    different request params. This is what actually caught the original bug
    -- the old code sent different `filter` values that the site silently
    ignored, so every mode parsed to the same series list."""
    latest_html = _load("browse_order_latest.html")
    numc_html = _load("browse_order_numc.html")

    latest_listing = parse_series_list(latest_html, page=1)
    numc_listing = parse_series_list(numc_html, page=1)

    latest_ids = [item.id for item in latest_listing.items]
    numc_ids = [item.id for item in numc_listing.items]

    assert latest_ids
    assert numc_ids
    assert latest_ids[0] != numc_ids[0]
    assert set(latest_ids[:5]).isdisjoint(set(numc_ids[:5]))


def test_search_finds_titles_not_on_browse_page_1(mangakatana_connector: MangaKatanaConnector):
    browse_html = _load("browse_page1.html")
    search_html = _load("search_solo.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search_html
        return browse_html

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        browse = mangakatana_connector.get_series_list(1)
        search = mangakatana_connector.search_series("solo leveling", 1)

    browse_ids = {item.id for item in browse.items}
    assert search.items
    assert any("solo" in item.title.casefold() for item in search.items)
    assert any(item.id not in browse_ids for item in search.items)


def test_get_series_chapters_and_pages(mangakatana_connector: MangaKatanaConnector):
    series_id = "aishiteru-uso-dakedo.10797"
    chapter_id = f"{series_id}/c1"
    detail_html = _load("series_detail.html")
    chapter_html = _load("chapter_reader.html")

    def fake_get_text(path: str, *, params=None):
        if path == f"/manga/{series_id}":
            return detail_html
        if path == f"/manga/{chapter_id}":
            return chapter_html
        raise AssertionError(path)

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        series = mangakatana_connector.get_series(series_id)
        chapters_before = mangakatana_connector.get_chapters(series_id)
        pages = mangakatana_connector.get_chapter_pages(chapter_id)
        chapters_after = mangakatana_connector.get_chapters(series_id)

    assert series is not None
    assert series.id == series_id
    assert len(chapters_before) >= 1
    assert chapters_before[0].id.startswith(series_id + "/")
    assert all(chapter.page_count == 0 for chapter in chapters_before)
    assert len(pages) >= 2
    assert pages[0].remote_url is not None
    assert mangakatana_connector.find_page(pages[0].id) == pages[0]

    chapter_one = next(chapter for chapter in chapters_after if chapter.id == chapter_id)
    assert chapter_one.page_count == len(pages)
    assert chapter_one.page_count >= 2


def test_parse_chapter_pages_extracts_script_urls():
    html = _load("chapter_reader.html")
    pages = parse_chapter_pages(html, "aishiteru-uso-dakedo.10797/c1")
    assert len(pages) >= 2
    assert all(page.remote_url and "mangakatana.com" in page.remote_url for page in pages)


def test_parse_chapters_filters_by_series():
    html = _load("series_detail.html")
    chapters = parse_chapters(html, "aishiteru-uso-dakedo.10797")
    assert len(chapters) == 2
    assert chapters[0].series_id == "aishiteru-uso-dakedo.10797"


def test_create_mangakatana_connector():
    connector = create_connector("mangakatana")
    assert connector.source_type == "mangakatana"


def test_list_browse_modes(mangakatana_connector: MangaKatanaConnector):
    modes = mangakatana_connector.list_browse_modes()
    mode_ids = {mode.id for mode in modes}
    assert "popular" in mode_ids
    assert "latest" in mode_ids
