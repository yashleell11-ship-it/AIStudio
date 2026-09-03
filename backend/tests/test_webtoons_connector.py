from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.webtoons.connector import WebtoonsConnector
from connectors.webtoons.mappers import (
    IMAGE_HOSTS,
    make_chapter_id,
    make_page_id,
    page_id_chapter_id,
    parse_chapter_id,
    parse_chapter_pages,
    parse_episodes,
    parse_search_results,
    parse_series_cards,
    parse_series_detail,
)
from services.outbound_security import host_matches_allowlist

FIXTURES = Path(__file__).parent / "fixtures" / "webtoons"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def webtoons_connector() -> WebtoonsConnector:
    return WebtoonsConnector()


# -- Pure parser tests ------------------------------------------------------

def test_parse_series_cards_from_browse_fixture():
    cards = parse_series_cards(_load("browse.html"))
    assert len(cards) >= 10
    first = cards[0]
    assert first.id.isdigit()  # series_id is the integer title_no
    assert first.title
    assert first.cover_url
    # Every card's cover must be on an allowlisted CDN host.
    for card in cards:
        host = card.cover_url.split("/")[2]
        assert host_matches_allowlist(host, IMAGE_HOSTS)


def test_parse_search_results_finds_title():
    listing = parse_search_results(_load("search.html"), page=1)
    assert listing.items
    assert any("unordinary" in item.title.casefold() for item in listing.items)
    assert all(item.id.isdigit() for item in listing.items)


def test_parse_series_detail_extracts_metadata():
    series = parse_series_detail(_load("detail.html"), "679")
    assert series is not None
    assert series.title == "unOrdinary"
    assert series.author
    assert series.genres  # e.g. ("Superhero",)
    assert series.status == "Ongoing"
    assert series.cover_url and host_matches_allowlist(series.cover_url.split("/")[2], IMAGE_HOSTS)
    assert series.description


def test_parse_episodes_builds_roundtrippable_chapter_ids():
    episodes = parse_episodes(_load("detail.html"), "679")
    assert len(episodes) >= 5
    for ch in episodes:
        assert ch.series_id == "679"
        parsed = parse_chapter_id(ch.id)
        assert parsed is not None
        title_no, episode_no, genre, slug = parsed
        assert title_no == "679"
        assert genre == "super-hero"
        assert slug == "unordinary"
        assert episode_no.isdigit()


def test_parse_chapter_pages_extracts_data_urls():
    chapter_id = make_chapter_id("679", 1, "super-hero", "unordinary")
    pages = parse_chapter_pages(_load("viewer.html"), chapter_id)
    assert len(pages) >= 10
    for i, page in enumerate(pages, start=1):
        assert page.number == i
        assert page.chapter_id == chapter_id
        assert page.remote_url and page.remote_url.startswith("https://")
        # The real image URL (data-url), never the transparent placeholder src.
        assert "bg_transparency" not in page.remote_url
        assert host_matches_allowlist(page.remote_url.split("/")[2], IMAGE_HOSTS)


def test_page_id_roundtrips_chapter_id():
    chapter_id = make_chapter_id("679", 200, "super-hero", "unordinary")
    page_id = make_page_id(chapter_id, 7)
    assert page_id_chapter_id(page_id) == chapter_id
    # chapter_id survives even though it itself contains colons.
    assert parse_chapter_id(page_id_chapter_id(page_id)) is not None


# -- Connector behaviour (offline, mocked HTTP) -----------------------------

def test_get_series_list_paginates_client_side(webtoons_connector: WebtoonsConnector):
    browse = _load("browse.html")
    with patch.object(webtoons_connector._http, "get_text", return_value=browse):
        page1 = webtoons_connector.get_series_list(1)
        page2 = webtoons_connector.get_series_list(2)
    assert len(page1.items) == 30
    assert page1.has_more is True
    assert page1.items[0].id != page2.items[0].id
    # Same underlying catalog, disjoint slices.
    assert {i.id for i in page1.items}.isdisjoint({i.id for i in page2.items})


def test_search_series_uses_search_endpoint(webtoons_connector: WebtoonsConnector):
    search = _load("search.html")
    captured: list[tuple[str, dict | None]] = []

    def fake(path: str, *, params=None):
        captured.append((path, params))
        return search

    with patch.object(webtoons_connector._http, "get_text", side_effect=fake):
        listing = webtoons_connector.search_series("unordinary", 1)

    assert captured[0][0] == "/en/search"
    assert captured[0][1] == {"keyword": "unordinary"}
    assert any("unordinary" in i.title.casefold() for i in listing.items)


def test_get_chapters_paginates_via_canonical_path(webtoons_connector: WebtoonsConnector):
    """Regression test: the placeholder ``/en/_/_/list`` path 301-redirects and
    drops ``&page=N``, so deeper episode pages MUST be requested against the
    canonical ``/<genre>/<slug>/list`` path. Page 1 goes through the
    placeholder; every subsequent page must carry the real genre/slug."""
    detail = _load("detail.html")
    captured: list[str] = []

    def fake(path: str, *, params=None):
        captured.append(path)
        return detail

    with patch.object(webtoons_connector._http, "get_text", side_effect=fake):
        chapters = webtoons_connector.get_chapters("679")

    assert chapters  # >= 1 chapter
    # Sorted ascending by episode number.
    numbers = [c.number for c in chapters if c.number is not None]
    assert numbers == sorted(numbers)
    # Page 1 used the placeholder path...
    assert captured[0] == "/en/_/_/list?title_no=679"
    # ...and page 2 used the canonical genre/slug path WITH the page param.
    assert any(
        "/en/super-hero/unordinary/list?title_no=679&page=2" == p for p in captured
    ), captured


def test_get_series_falls_back_to_canvas_path_on_originals_404(
    webtoons_connector: WebtoonsConnector,
):
    """Regression test: every Canvas title 404'd in production because the
    cold-cache placeholder guess (``/en/_/_/list``) is Originals-shaped and
    WEBTOON does not redirect it for Canvas titles the way it does for
    Originals. ``get_series`` must retry with the Canvas-shaped placeholder
    (``/en/canvas/_/list``) and succeed."""
    canvas_detail = _load("detail_canvas.html")
    captured: list[str] = []

    def fake(path: str, *, params=None):
        captured.append(path)
        if path == "/en/_/_/list?title_no=843210":
            raise ConnectorHttpError("Not Found", status_code=404)
        return canvas_detail

    with patch.object(webtoons_connector._http, "get_text", side_effect=fake):
        series = webtoons_connector.get_series("843210")

    assert captured == [
        "/en/_/_/list?title_no=843210",
        "/en/canvas/_/list?title_no=843210",
    ]
    assert series is not None
    assert series.title == "Late Bloomer"
    assert series.canonical_path == "/en/canvas/late-bloomer/list?title_no=843210"
    # The real genre/slug learned from the successful fallback must be
    # cached, so subsequent calls go straight to the canonical path.
    assert webtoons_connector._slug_cache.get("843210") == ("canvas", "late-bloomer")


def test_get_chapters_falls_back_to_canvas_path_then_paginates_canonically(
    webtoons_connector: WebtoonsConnector,
):
    """Same fallback, exercised through get_chapters: page 1 needs the
    Canvas-shaped retry, and once the real slug is learned, page 2 (empty,
    ending pagination) must be requested against the canonical Canvas path —
    never the Originals placeholder again."""
    canvas_detail = _load("detail_canvas.html")
    captured: list[str] = []

    def fake(path: str, *, params=None):
        captured.append(path)
        if path == "/en/_/_/list?title_no=843210":
            raise ConnectorHttpError("Not Found", status_code=404)
        if path == "/en/canvas/_/list?title_no=843210":
            return canvas_detail
        return "<html><body>no more episodes here</body></html>"

    with patch.object(webtoons_connector._http, "get_text", side_effect=fake):
        chapters = webtoons_connector.get_chapters("843210")

    assert len(chapters) == 2
    assert all(parse_chapter_id(c.id)[2] == "canvas" for c in chapters)
    assert captured == [
        "/en/_/_/list?title_no=843210",
        "/en/canvas/_/list?title_no=843210",
        "/en/canvas/late-bloomer/list?title_no=843210&page=2",
    ]


def test_get_chapter_pages_requests_viewer_and_parses(webtoons_connector: WebtoonsConnector):
    viewer = _load("viewer.html")
    captured: list[str] = []

    def fake(path: str, *, params=None):
        captured.append(path)
        return viewer

    chapter_id = make_chapter_id("679", 1, "super-hero", "unordinary")
    with patch.object(webtoons_connector._http, "get_text", side_effect=fake):
        pages = webtoons_connector.get_chapter_pages(chapter_id)

    assert len(pages) >= 10
    # Viewer URL carries the real genre/slug and episode_no.
    assert captured[0] == "/en/super-hero/unordinary/ep/viewer?title_no=679&episode_no=1"
    assert all(host_matches_allowlist(p.remote_url.split("/")[2], IMAGE_HOSTS) for p in pages)


def test_find_page_roundtrips_from_viewer(webtoons_connector: WebtoonsConnector):
    viewer = _load("viewer.html")
    chapter_id = make_chapter_id("679", 1, "super-hero", "unordinary")
    page_id = make_page_id(chapter_id, 3)
    with patch.object(webtoons_connector._http, "get_text", return_value=viewer):
        page = webtoons_connector.find_page(page_id)
    assert page is not None
    assert page.id == page_id
    assert page.number == 3
    assert page.remote_url.startswith("https://")


def test_find_page_rejects_malformed_id(webtoons_connector: WebtoonsConnector):
    assert webtoons_connector.find_page("not-a-valid-page-id") is None


# -- Descriptors / contract -------------------------------------------------

def test_connector_descriptors(webtoons_connector: WebtoonsConnector):
    assert webtoons_connector.source_type == "webtoons"
    assert webtoons_connector.display_name == "WEBTOON"
    assert webtoons_connector.is_browsable is True
    assert webtoons_connector.is_mature is False


def test_allowed_image_hosts_and_referer(webtoons_connector: WebtoonsConnector):
    hosts = webtoons_connector.allowed_image_hosts
    assert "webtoon-phinf.pstatic.net" in hosts
    assert "swebtoon-phinf.pstatic.net" in hosts
    # Hotlink protection requires a webtoons.com Referer on image GETs.
    assert webtoons_connector.image_fetch_headers().get("Referer") == "https://www.webtoons.com"


def test_list_genres_populated(webtoons_connector: WebtoonsConnector):
    genres = webtoons_connector.list_genres()
    ids = {g.id for g in genres}
    assert "romance" in ids
    assert "fantasy" in ids
