from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.elftoon.connector import ElfToonConnector
from connectors.elftoon.mappers import (
    SEARCH_PAGE_SIZE,
    chapter_id_to_path,
    listing_params,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_params,
    search_path,
)
from connectors.http.client import ConnectorHttpError

FIXTURES = Path(__file__).parent / "fixtures" / "elftoon"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def elftoon_connector() -> ElfToonConnector:
    return ElfToonConnector()


def test_listing_params_use_themesia_order():
    assert listing_params(page=1, sort="default") == {"order": "update"}
    assert listing_params(page=2, sort="popular") == {"order": "popular", "page": 2}
    assert listing_params(page=1, sort="latest") == {"order": "latest"}


def test_parse_series_list_from_fixture():
    html = _load("browse_update.html")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) >= 15
    assert listing.items[0].id
    assert listing.items[0].title
    assert listing.items[0].cover_url
    assert listing.has_more is True


def test_browse_sort_orders_differ():
    update = parse_series_list(_load("browse_update.html"), page=1)
    popular = parse_series_list(_load("browse_popular.html"), page=1)
    assert update.items[0].id != popular.items[0].id


def test_browse_page_2_differs(elftoon_connector: ElfToonConnector):
    page1 = _load("browse_update.html")
    page2 = _load("browse_page2.html")

    def fake_get_text(path: str, *, params=None):
        if params and str(params.get("page")) == "2":
            return page2
        return page1

    with patch.object(elftoon_connector._http, "get_text", side_effect=fake_get_text):
        first = elftoon_connector.get_series_list(1, sort="default")
        second = elftoon_connector.get_series_list(2, sort="default")

    assert first.items[0].id != second.items[0].id
    assert first.has_more is True


def test_browse_requests_order_and_page(elftoon_connector: ElfToonConnector):
    html = _load("browse_update.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(elftoon_connector._http, "get_text", side_effect=fake_get_text):
        elftoon_connector.get_series_list(1)
        elftoon_connector.get_series_list(2, sort="popular")

    assert captured[0] == ("/manga/", {"order": "update"})
    assert captured[1] == ("/manga/", {"order": "popular", "page": 2})


def test_search_finds_titles(elftoon_connector: ElfToonConnector):
    search_html = _load("search_solo.html")

    with patch.object(elftoon_connector._http, "get_text", return_value=search_html) as mock_get:
        listing = elftoon_connector.search_series("solo", 1)

    mock_get.assert_called_once_with(
        "/",
        params={"s": "solo", "post_type": "wp-manga"},
    )
    assert listing.items
    assert any("infinite" in item.title.casefold() or "solo" in item.id for item in listing.items) or listing.items
    # A single page of hits: nothing to scroll to.
    assert listing.has_more is False


def test_search_paginates_by_path_not_query():
    """``?page=N`` is ignored by WordPress; the page number belongs in the path."""
    assert search_path(1) == "/"
    assert search_path(2) == "/page/2/"
    assert search_path(7) == "/page/7/"
    assert "page" not in search_params("demon")


def test_search_page_2_returns_different_series(elftoon_connector: ElfToonConnector):
    """The bug this guards: every page used to answer with page 1's ids."""
    page1 = _load("search_demon_page1.html")
    page2 = _load("search_demon_page2.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return page2 if path == "/page/2/" else page1

    with patch.object(elftoon_connector._http, "get_text", side_effect=fake_get_text):
        first = elftoon_connector.search_series("demon", 1)
        second = elftoon_connector.search_series("demon", 2)

    assert captured == [
        ("/", {"s": "demon", "post_type": "wp-manga"}),
        ("/page/2/", {"s": "demon", "post_type": "wp-manga"}),
    ]
    first_ids = [item.id for item in first.items]
    second_ids = [item.id for item in second.items]
    assert first_ids and second_ids
    assert not set(first_ids) & set(second_ids)
    assert first.has_more is True
    assert second.has_more is True
    assert first.page_size == SEARCH_PAGE_SIZE


def test_search_last_page_reports_no_more():
    """Page 3 of "demon" is the last: the paginator shows no Next link."""
    last = parse_search_results(_load("search_demon_page3.html"), page=3)
    assert last.items
    assert last.has_more is False
    assert last.total == 2 * SEARCH_PAGE_SIZE + len(last.items)


def test_search_past_last_page_is_empty_not_an_error(
    elftoon_connector: ElfToonConnector,
):
    """WordPress 404s past the end; infinite scroll must see an empty page."""
    not_found = ConnectorHttpError(
        "Client error '404 Not Found' for url 'https://elftoon.com/page/4/?s=demon'",
        status_code=404,
    )

    with patch.object(elftoon_connector._http, "get_text", side_effect=not_found):
        listing = elftoon_connector.search_series("demon", 4)

    assert listing.items == []
    assert listing.has_more is False
    assert listing.page == 4


def test_search_page_1_404_still_raises(elftoon_connector: ElfToonConnector):
    """``/?s=...`` answers 200 even with zero hits, so a 404 there is a fault."""
    not_found = ConnectorHttpError(
        "Client error '404 Not Found' for url 'https://elftoon.com/?s=demon'",
        status_code=404,
    )

    with patch.object(elftoon_connector._http, "get_text", side_effect=not_found):
        with pytest.raises(ConnectorHttpError):
            elftoon_connector.search_series("demon", 1)


def test_parse_series_detail():
    html = _load("series_detail.html")
    series = parse_series_detail(html, "10000-ways-to-eliminate-players")
    assert series is not None
    assert "Eliminate Players" in series.title
    assert series.cover_url
    assert series.status == "ongoing"
    assert series.description
    assert "Action" in series.genres


def test_parse_chapters_skips_locked():
    free_html = _load("series_detail.html")
    free = parse_chapters(free_html, "10000-ways-to-eliminate-players")
    assert len(free) >= 10
    assert free[0].number is not None
    assert free[0].number <= free[-1].number
    assert all("chapter-" in chapter.id for chapter in free)

    locked_html = _load("series_locked.html")
    chapters = parse_chapters(locked_html, "infinite-evolution-from-zero")
    assert chapters
    # Newest chapters on this series are coin-locked; free list must omit them.
    assert all(chapter.number is None or chapter.number < 105 for chapter in chapters)
    assert not any("chapter-107" in chapter.id for chapter in chapters)


def test_chapter_id_to_path():
    assert (
        chapter_id_to_path("10000-ways-to-eliminate-players/10000-ways-to-eliminate-players-chapter-1")
        == "/10000-ways-to-eliminate-players-chapter-1/"
    )


def test_parse_chapter_pages_from_ts_reader():
    html = _load("chapter_reader.html")
    chapter_id = "10000-ways-to-eliminate-players/10000-ways-to-eliminate-players-chapter-1"
    pages = parse_chapter_pages(html, chapter_id)
    assert len(pages) >= 2
    assert pages[0].number == 1
    assert pages[0].remote_url and pages[0].remote_url.startswith("http")
    assert "elftoon.com" in pages[0].remote_url or "wp.com" in pages[0].remote_url


def test_get_series_and_pages(elftoon_connector: ElfToonConnector):
    detail = _load("series_detail.html")
    reader = _load("chapter_reader.html")

    def fake_get_text(path: str, *, params=None):
        if path.startswith("/manga/"):
            return detail
        if "chapter-" in path:
            return reader
        return detail

    with patch.object(elftoon_connector._http, "get_text", side_effect=fake_get_text):
        series = elftoon_connector.get_series("10000-ways-to-eliminate-players")
        chapters = elftoon_connector.get_chapters("10000-ways-to-eliminate-players")
        pages = elftoon_connector.get_chapter_pages(chapters[0].id)

    assert series is not None
    assert series.chapter_count == len(chapters)
    assert len(pages) >= 2
