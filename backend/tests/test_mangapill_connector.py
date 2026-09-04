"""Offline tests for the MangaPill manga connector.

Fixtures under ``tests/fixtures/mangapill/`` were captured live 2026-09-04
FROM THE VPS (inside ``manhwamaniacs-backend``, so through production's exact
egress IP and TLS stack). The connector is exercised entirely against those
captures by patching ``self._http.get_text``; no test touches the network.

Every parse assertion here was watched to FAIL against a deliberately broken
selector before being kept -- a test that still passes on broken parsing
proves nothing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.mangapill.connector import MangaPillConnector
from connectors.mangapill.mappers import (
    PAGE_SIZE,
    browse_params,
    chapter_path,
    genre_params,
    make_page_id,
    normalize_chapter_key,
    normalize_series_key,
    page_id_chapter_key,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_latest_cards,
    parse_series_cards,
    parse_series_detail,
    parse_series_list,
    search_params,
    series_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mangapill"

SERIES_KEY = "8453/mahou-shoujo-dandelion"
CHAPTER_KEY = "2-11192000/one-piece-chapter-1192"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def connector() -> MangaPillConnector:
    return MangaPillConnector()


# --- identity ---------------------------------------------------------------


def test_series_key_contains_a_slash_and_round_trips():
    """House law: keys are opaque, may contain slashes, and pass through raw."""
    assert "/" in SERIES_KEY
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(f"manga/{SERIES_KEY}") == SERIES_KEY
    assert normalize_series_key(f"/manga/{SERIES_KEY}/") == SERIES_KEY
    assert normalize_series_key(f"https://mangapill.com/manga/{SERIES_KEY}") == SERIES_KEY
    assert series_path(SERIES_KEY) == f"/manga/{SERIES_KEY}"


def test_chapter_key_round_trips():
    assert "/" in CHAPTER_KEY
    assert normalize_chapter_key(CHAPTER_KEY) == CHAPTER_KEY
    assert normalize_chapter_key(f"chapters/{CHAPTER_KEY}") == CHAPTER_KEY
    assert (
        normalize_chapter_key(f"https://mangapill.com/chapters/{CHAPTER_KEY}")
        == CHAPTER_KEY
    )
    assert chapter_path(CHAPTER_KEY) == f"/chapters/{CHAPTER_KEY}"


def test_page_id_round_trips_through_a_key_holding_slashes_and_dashes():
    page_id = make_page_id(CHAPTER_KEY, 7)
    assert page_id == f"{CHAPTER_KEY}:7"
    assert page_id_chapter_key(page_id) == CHAPTER_KEY
    assert page_id_chapter_key("no-separator-here") is None


def test_chapter_number_comes_from_the_sites_own_label():
    assert parse_chapter_number("Chapter 1192") == 1192.0
    assert parse_chapter_number("Chapter 28.2") == 28.2
    assert parse_chapter_number("Oneshot") is None


# --- browse / search params -------------------------------------------------


def test_browse_params_always_send_the_three_filter_keys():
    """An all-blank /search renders zero results, so "All Manga" pins a type."""
    params = browse_params("all", 3)
    assert params == {"q": "", "type": "manga", "status": "", "page": 3}
    assert browse_params("completed", 1)["status"] == "finished"
    assert search_params("one piece", 2) == {
        "q": "one piece",
        "type": "",
        "status": "",
        "page": 2,
    }
    assert genre_params("Action", 4)["genre"] == "Action"


# --- catalog parsing --------------------------------------------------------


def test_parse_browse_page_reads_every_card():
    listing = parse_series_list(_load("browse_manga_page1.html"), page=1)
    assert len(listing.items) == PAGE_SIZE
    first = listing.items[0]
    assert first.id == "1/berserk"
    assert first.title == "Berserk"
    assert first.canonical_path == "/manga/1/berserk"
    assert first.cover_url and first.cover_url.startswith(
        "https://cdn.readdetectiveconan.com/"
    )
    # Titles must be real display text, never an empty string or a slug echo.
    # (One genuine title on this page IS "1/11", so a slash is not the test.)
    assert all(item.title for item in listing.items)
    assert all(item.title != item.id for item in listing.items)
    assert "1/11" in {item.title for item in listing.items}


def test_has_more_tracks_the_pagers_next_link_exactly():
    first = parse_series_list(_load("browse_manga_page1.html"), page=1)
    last = parse_series_list(_load("browse_manga_last.html"), page=20)
    assert first.has_more is True
    assert last.has_more is False
    # The last page is full (50 cards) yet still terminal -- proof that
    # has_more reads the pager rather than guessing from a short page.
    assert len(last.items) == PAGE_SIZE


def test_parse_search_results():
    listing = parse_series_list(_load("search_one_piece.html"), page=1)
    assert listing.items[0].id == "2/one-piece"
    assert listing.items[0].title == "One Piece"
    ids = {item.id for item in listing.items}
    assert "3258/one-piece-digital-colored-comics" in ids
    # Each card links twice (cover + title); dedup must collapse them.
    assert len(ids) == len(listing.items)


def test_repeated_cards_collapse_to_one_series():
    """Dedup is real, not decorative: MangaPill links a card from both its
    cover and its title, and ``/chapters`` lists several series twice (120
    chapters, 117 distinct series). A key must never be emitted twice."""
    page = _load("browse_manga_page1.html")
    once = parse_series_cards(page)
    twice = parse_series_cards(page + page)
    assert len(once) == PAGE_SIZE
    assert [s.id for s in twice] == [s.id for s in once]

    latest = _load("latest_chapters.html")
    series = parse_latest_cards(latest)
    ids = [s.id for s in series]
    assert len(ids) == len(set(ids))
    assert [s.id for s in parse_latest_cards(latest + latest)] == ids


def test_parse_latest_cards_carries_the_newest_chapter_label():
    series = parse_latest_cards(_load("latest_chapters.html"))
    assert len(series) == 117
    first = series[0]
    assert first.id == "4299/temple"
    assert first.title == "Temple"
    assert first.latest_chapter == "Chapter 141"
    assert first.cover_url and first.cover_url.startswith("https://")


# --- series detail ----------------------------------------------------------


def test_parse_series_detail():
    series = parse_series_detail(_load("series_dandelion.html"), SERIES_KEY)
    assert series is not None
    assert series.title == "Mahou Shoujo Dandelion"
    assert series.status == "publishing"
    assert series.genres == (
        "Action",
        "Comedy",
        "Drama",
        "Fantasy",
        "School",
        "Shoujo",
        "Slice of Life",
    )
    assert series.cover_url == (
        "https://cdn.readdetectiveconan.com/file/mangapill/i/8453.jpeg"
    )
    assert series.description and "phantoms" in series.description
    assert "<" not in series.description  # tags stripped, entities decoded


def test_parse_series_detail_returns_none_on_a_page_without_a_title():
    assert parse_series_detail("<html><body>nope</body></html>", SERIES_KEY) is None


def test_parse_chapters_orders_ascending_and_keeps_decimal_numbering():
    chapters = parse_chapters(_load("series_dandelion.html"), SERIES_KEY)
    assert len(chapters) == 40
    assert chapters[0].id == "8453-10001000/mahou-shoujo-dandelion-chapter-1"
    assert chapters[0].number == 1.0
    assert chapters[-1].id == "8453-10028200/mahou-shoujo-dandelion-chapter-28.2"
    assert chapters[-1].title == "Chapter 28.2"
    # The site lists newest-first; the app wants ascending, and point releases
    # must sort between their neighbours rather than after them.
    assert [c.number for c in chapters[-6:]] == [25.0, 26.0, 27.0, 27.1, 28.1, 28.2]
    assert all(c.series_id == SERIES_KEY for c in chapters)


# --- chapter pages ----------------------------------------------------------


def test_parse_chapter_pages_reads_every_image_with_its_dimensions():
    pages = parse_chapter_pages(_load("chapter_one_piece_1192.html"), CHAPTER_KEY)
    assert len(pages) == 14
    assert [p.number for p in pages] == list(range(1, 15))
    first = pages[0]
    assert first.id == f"{CHAPTER_KEY}:1"
    assert first.chapter_id == CHAPTER_KEY
    assert first.remote_url == (
        "https://cdn.readdetectiveconan.com/file/mangap/2026/36/2/11192000/"
        "01a06b5d-91d0-7e36-8f96-4051bd67700f/1.png"
    )
    # width/height ride along in the markup, so the reader reserves layout
    # space without a HEAD request or an image decode.
    assert (first.width, first.height) == (1100, 1606)
    assert all(p.width and p.height for p in pages)
    assert all(p.remote_url.startswith("https://") for p in pages)


# --- connector wiring -------------------------------------------------------


def test_detail_and_chapter_list_share_exactly_one_fetch(connector):
    """The known anti-pattern: fetching the series page twice. The chapter
    rows are already inside the detail document, so both calls -- and every
    repeat within the cache TTL -- must ride one GET."""
    with patch.object(
        connector._http, "get_text", return_value=_load("series_dandelion.html")
    ) as get_text:
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)
        connector.get_series(SERIES_KEY)

    assert get_text.call_count == 1
    assert get_text.call_args.args[0] == f"/manga/{SERIES_KEY}"
    assert series is not None
    assert series.chapter_count == 40
    assert series.latest_chapter == "Chapter 28.2"
    assert len(chapters) == 40


def test_latest_browse_pages_locally_from_one_fetch(connector):
    """``/chapters?page=2`` serves byte-identical HTML upstream, so paging it
    must come from slicing the single cached document, not a second GET."""
    with patch.object(
        connector._http, "get_text", return_value=_load("latest_chapters.html")
    ) as get_text:
        page1 = connector.get_series_list(1)
        page2 = connector.get_series_list(2)
        page3 = connector.get_series_list(3)

    assert get_text.call_count == 1
    assert get_text.call_args.args[0] == "/chapters"
    assert len(page1.items) == PAGE_SIZE
    assert len(page2.items) == PAGE_SIZE
    assert len(page3.items) == 17
    assert page1.has_more is True
    assert page3.has_more is False
    assert page1.total == 117
    # No series may appear on two pages.
    ids = [s.id for s in page1.items + page2.items + page3.items]
    assert len(ids) == len(set(ids)) == 117


def test_browse_mode_hits_search_with_the_modes_filter(connector):
    seen: dict[str, object] = {}

    def fake(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return _load("browse_manga_page1.html")

    with patch.object(connector._http, "get_text", side_effect=fake):
        listing = connector.get_series_list(2, sort="all")

    assert seen["path"] == "/search"
    assert seen["params"] == {"q": "", "type": "manga", "status": "", "page": 2}
    assert listing.items


def test_search_delegates_to_the_search_endpoint(connector):
    seen: dict[str, object] = {}

    def fake(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return _load("search_one_piece.html")

    with patch.object(connector._http, "get_text", side_effect=fake):
        listing = connector.search_series("one piece", 1)

    assert seen["path"] == "/search"
    assert seen["params"]["q"] == "one piece"
    assert listing.items[0].id == "2/one-piece"


def test_find_page_resolves_without_re_fetching_the_chapter(connector):
    with patch.object(
        connector._http,
        "get_text",
        return_value=_load("chapter_one_piece_1192.html"),
    ) as get_text:
        pages = connector.get_chapter_pages(CHAPTER_KEY)
        found = connector.find_page(pages[3].id)
        missing = connector.find_page(f"{CHAPTER_KEY}:999")

    assert get_text.call_count == 1
    assert found is not None
    assert found.number == 4
    assert found.remote_url == pages[3].remote_url
    assert missing is None


def test_find_page_rejects_a_malformed_id_without_any_request(connector):
    with patch.object(connector._http, "get_text") as get_text:
        assert connector.find_page("garbage") is None
    get_text.assert_not_called()


def test_chapter_page_count_backfills_into_a_later_chapter_list(connector):
    with patch.object(
        connector._http,
        "get_text",
        return_value=_load("chapter_one_piece_1192.html"),
    ):
        connector.get_chapter_pages(CHAPTER_KEY)

    with patch.object(
        connector._http, "get_text", return_value=_load("series_dandelion.html")
    ):
        chapters = connector.get_chapters(SERIES_KEY)

    # Nothing in the dandelion list was read, so every count stays 0 ...
    assert all(c.page_count == 0 for c in chapters)

    # ... but the chapter that WAS read reports its real page count.
    connector._detail_cache._entries.clear()
    with patch.object(
        connector._http,
        "get_text",
        return_value=_load("series_dandelion.html").replace(
            "8453-10001000/mahou-shoujo-dandelion-chapter-1", CHAPTER_KEY
        ),
    ):
        patched = connector.get_chapters(SERIES_KEY)
    assert any(c.id == CHAPTER_KEY and c.page_count == 14 for c in patched)


# --- image delivery ---------------------------------------------------------


def test_image_requests_carry_the_referer_the_cdn_demands(connector):
    """Measured from the VPS: the CDN answers 403 without a Referer and 200
    with one, for page images AND covers alike."""
    assert connector.image_fetch_headers() == {"Referer": "https://mangapill.com/"}


def test_the_image_cdn_is_allowlisted_for_the_proxy(connector):
    hosts = connector.allowed_image_hosts
    assert "readdetectiveconan.com" in hosts
    page_host = "cdn.readdetectiveconan.com"
    assert any(page_host == h or page_host.endswith(f".{h}") for h in hosts)


# --- failure handling -------------------------------------------------------


def test_404_is_a_clean_not_found_in_the_shared_clients_real_shape(connector):
    """The shared client only attaches ``status_code`` for RETRYABLE_STATUS, so
    a real 404 arrives with ``status_code=None`` and httpx's message text. The
    connector must recognise THAT shape (dead-check regression)."""
    real_shape = ConnectorHttpError(
        "Client error '404 Not Found' for url "
        "'https://mangapill.com/manga/99999999/nope'",
        status_code=None,
    )

    with patch.object(connector._http, "get_text", side_effect=real_shape):
        assert connector.get_series("99999999/nope") is None
        assert connector.get_chapters("99999999/nope") == []
        assert connector.get_chapter_pages("99999999-10001000/nope-chapter-1") == []


def test_non_404_errors_still_raise(connector):
    boom = ConnectorHttpError("Retryable HTTP 503", status_code=503)
    with patch.object(connector._http, "get_text", side_effect=boom):
        with pytest.raises(ConnectorHttpError):
            connector.get_series("2/one-piece")
        with pytest.raises(ConnectorHttpError):
            connector.get_chapter_pages(CHAPTER_KEY)
        with pytest.raises(ConnectorHttpError):
            connector.get_series_list(1, sort="all")
