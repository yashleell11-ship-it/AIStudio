"""Tests for the manhwa18.cc connector.

Every fixture under ``tests/fixtures/manhwa18/`` was captured from the
production VPS (``manhwamaniacs-backend`` container, OVH egress) so the parse
tests exercise exactly the bytes production receives.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.manhwa18.connector import Manhwa18Connector
from connectors.manhwa18.mappers import (
    PAGE_SIZE,
    page_id_chapter_key,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
)

FIXTURES = Path(__file__).parent / "fixtures" / "manhwa18"

SERIES_KEY = "return-of-the-frozen-player"
DECIMAL_SERIES_KEY = "keep-it-a-secret-from-your-mother-01"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def connector() -> Manhwa18Connector:
    return Manhwa18Connector()


# --------------------------------------------------------------------------
# Connector identity / 18+ gating
# --------------------------------------------------------------------------


def test_connector_is_marked_mature(connector: Manhwa18Connector) -> None:
    """manhwa18.cc is an adult source: the 18+ gate must hide it for profiles
    with mature content disabled. ``MATURE = True`` is what both
    ``SourceConnector.is_mature`` and the registry descriptor read."""
    assert connector.MATURE is True
    assert connector.is_mature is True


def test_connector_identity(connector: Manhwa18Connector) -> None:
    assert connector.source_type == "manhwa18"
    assert connector.display_name == "Manhwa18"
    assert connector.content_kind == "manga"
    assert connector.is_browsable is True


def test_image_host_allowlist_covers_cdn_subdomains(connector: Manhwa18Connector) -> None:
    """Page images come from ``img<NN>.manhwa18.cc`` (img01/img02/img11/img33
    seen from the VPS) and covers from ``manhwa18.cc`` itself. The proxy
    allowlist matches subdomains, so the single apex entry covers both — and
    must NOT be so loose that a lookalike domain passes."""
    from connectors.http.redirect_policy import host_matches_allowlist

    hosts = connector.allowed_image_hosts
    assert host_matches_allowlist("manhwa18.cc", hosts)
    assert host_matches_allowlist("img01.manhwa18.cc", hosts)
    assert host_matches_allowlist("img33.manhwa18.cc", hosts)
    assert not host_matches_allowlist("notmanhwa18.cc", hosts)
    assert not host_matches_allowlist("manhwa18.cc.evil.test", hosts)


# --------------------------------------------------------------------------
# Listing / search / genre parsing
# --------------------------------------------------------------------------


def test_parse_series_list_from_fixture() -> None:
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    assert len(listing.items) == PAGE_SIZE
    first = listing.items[0]
    assert first.id == "i-love-you-very-much-raw"
    assert first.title == "I Love You Very Much Raw"
    assert first.cover_url == "https://manhwa18.cc/manga/i-love-you-very-much-rawm.jpg"
    assert first.canonical_path == "/webtoon/i-love-you-very-much-raw"
    assert first.latest_chapter == "Chapter 7"
    assert listing.has_more is True


def test_listing_ids_are_slugs_not_paths() -> None:
    """``series_key`` is the opaque slug the site uses; nothing may prepend
    ``/webtoon/`` to it or the key stops round-tripping."""
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    assert all("/" not in item.id for item in listing.items)
    assert len({item.id for item in listing.items}) == len(listing.items)


def test_browse_page_2_differs_from_page_1() -> None:
    page1 = parse_series_list(_load("browse_page1.html"), page=1)
    page2 = parse_series_list(_load("browse_page2.html"), page=2)
    assert page1.items[0].id != page2.items[0].id
    assert page2.total == PAGE_SIZE + len(page2.items)


def test_trending_order_returns_a_different_first_card() -> None:
    """Regression guard for the sort bug this project has hit before: a mode
    that silently falls back to the default listing is worse than no mode."""
    latest = parse_series_list(_load("browse_page1.html"), page=1)
    trending = parse_series_list(_load("browse_order_trending.html"), page=1)
    assert latest.items[0].id != trending.items[0].id


def test_search_results_parse() -> None:
    listing = parse_search_results(_load("search_love.html"), page=1)
    assert len(listing.items) == PAGE_SIZE
    assert listing.items[0].id == "urami-koi-koi-urami-koi"
    assert listing.items[0].title == "Urami Koi, Koi, Urami Koi."
    assert listing.has_more is True


def test_empty_search_yields_no_items_and_no_next_page() -> None:
    listing = parse_search_results(_load("search_empty.html"), page=1)
    assert listing.items == []
    assert listing.has_more is False
    assert listing.total == 0


def test_genre_listing_parses_the_same_card_shape() -> None:
    listing = parse_series_list(_load("genre_romance.html"), page=1)
    assert len(listing.items) == PAGE_SIZE
    assert listing.items[0].id == "magical-girl-wife"
    assert all(item.cover_url for item in listing.items)


# --------------------------------------------------------------------------
# Series detail parsing
# --------------------------------------------------------------------------


def test_parse_series_detail_from_fixture() -> None:
    series = parse_series_detail(_load("series_detail.html"), SERIES_KEY)
    assert series is not None
    # The <h1> carries an "18+" badge span before the title; it must be gone.
    assert series.title == "Return of the Frozen Player"
    assert series.status == "OnGoing"
    assert series.genres == ("Action", "Adventure", "Fantasy")
    assert series.cover_url == (
        "https://manhwa18.cc/manga/return-of-the-frozen-playerczv.jpg"
    )
    assert series.description is not None
    assert "Frost Queen" in series.description
    assert "<" not in series.description  # tags stripped
    assert "&quot;" not in series.description  # entities decoded


def test_parse_series_detail_reads_author_and_artist() -> None:
    series = parse_series_detail(_load("series_decimal_chapters.html"), DECIMAL_SERIES_KEY)
    assert series is not None
    assert series.title == "Keep it a secret from your mother!"
    assert series.author == "Noah"
    assert series.artist == "Noah"


def test_updating_placeholder_becomes_none() -> None:
    """The site prints "Updating" where it has no author/artist. That is not a
    person's name and must not be shown as one."""
    series = parse_series_detail(_load("series_detail.html"), SERIES_KEY)
    assert series is not None
    assert series.author is None
    assert series.artist is None


def test_parse_series_detail_returns_none_on_a_page_without_a_title() -> None:
    assert parse_series_detail("<html><body>nope</body></html>", SERIES_KEY) is None


# --------------------------------------------------------------------------
# Chapter list parsing
# --------------------------------------------------------------------------


def test_parse_chapters_reads_the_whole_inline_list() -> None:
    """The series page carries the COMPLETE chapter list inline — 227 rows for
    this series. Anything less means the list block was mis-scoped."""
    chapters = parse_chapters(_load("series_detail.html"), SERIES_KEY)
    assert len(chapters) == 227
    assert chapters[0].id == f"{SERIES_KEY}/chapter-0"
    assert chapters[0].number == 0.0
    assert chapters[-1].id == f"{SERIES_KEY}/chapter-226"
    assert chapters[-1].number == 226.0
    assert chapters[0].title == "Chapter 0"
    assert chapters[0].series_id == SERIES_KEY


def test_chapters_are_sorted_oldest_first() -> None:
    chapters = parse_chapters(_load("series_detail.html"), SERIES_KEY)
    numbers = [chapter.number for chapter in chapters]
    assert numbers == sorted(numbers)


def test_chapter_keys_keep_their_slash_and_are_unique() -> None:
    """``chapter_key`` is opaque and contains a slash; it is stored raw."""
    chapters = parse_chapters(_load("series_detail.html"), SERIES_KEY)
    assert all(chapter.id.startswith(f"{SERIES_KEY}/") for chapter in chapters)
    assert len({chapter.id for chapter in chapters}) == len(chapters)


def test_decimal_chapter_numbers_come_from_the_site_numbering() -> None:
    """The site spells half-chapters ``chapter-100-5`` in the URL and
    "Chapter 100.5" in the label. Reading the dash as the number would give
    1005 and wreck reading order."""
    chapters = parse_chapters(_load("series_decimal_chapters.html"), DECIMAL_SERIES_KEY)
    by_key = {chapter.id: chapter for chapter in chapters}
    half = by_key[f"{DECIMAL_SERIES_KEY}/chapter-100-5"]
    assert half.number == 100.5
    assert half.title == "Chapter 100.5"
    whole = by_key[f"{DECIMAL_SERIES_KEY}/chapter-100"]
    assert whole.number == 100.0
    assert whole.number < half.number


def test_chapter_release_dates_are_read_when_present() -> None:
    chapters = parse_chapters(_load("series_detail.html"), SERIES_KEY)
    dated = [chapter for chapter in chapters if chapter.release_date]
    assert len(dated) > 200
    assert chapters[0].release_date == "18 Mar 2021"


def test_chapter_rows_for_other_series_are_ignored() -> None:
    """The chapter list block sits under a heading that reads "Latest Manga
    Releases". Should the site ever fold another series' rows into it, they
    must not be attributed to this series -- a foreign chapter_key would 404
    the reader."""
    block = (
        '<ul class="row-content-chapter wleft">'
        '<li class="a-h wleft">'
        f'<a class="chapter-name text-nowrap" href="/webtoon/{SERIES_KEY}/chapter-5"'
        ' title="x">Chapter 5</a>'
        '<span class="chapter-time text-nowrap">01 Jan 2024</span></li>'
        '<li class="a-h wleft">'
        '<a class="chapter-name text-nowrap" href="/webtoon/some-other-series/chapter-9"'
        ' title="y">Chapter 9</a></li>'
        "</ul>"
    )
    chapters = parse_chapters(block, SERIES_KEY)
    assert [chapter.id for chapter in chapters] == [f"{SERIES_KEY}/chapter-5"]


def test_page_id_chapter_key_requires_the_colon_separator() -> None:
    """A page id is ``<chapter_key>:<n>`` and the chapter key itself contains
    slashes but never a colon. Without the colon there is no page id, and
    treating the whole string as a chapter key would send the reader off to
    fetch a nonsense URL."""
    assert page_id_chapter_key(f"{SERIES_KEY}/chapter-1:7") == f"{SERIES_KEY}/chapter-1"
    assert page_id_chapter_key(f"{SERIES_KEY}/chapter-1") is None
    assert page_id_chapter_key("") is None
    assert page_id_chapter_key(":3") is None


def test_parse_chapter_number_falls_back_to_the_url_ref() -> None:
    assert parse_chapter_number("Chapter 12.5", "chapter-12-5") == 12.5
    assert parse_chapter_number("", "chapter-12-5") == 12.5
    assert parse_chapter_number("", "chapter-7") == 7.0
    assert parse_chapter_number("Prologue", "prologue") is None


# --------------------------------------------------------------------------
# Chapter page (image) parsing
# --------------------------------------------------------------------------


def test_parse_chapter_pages_from_fixture() -> None:
    chapter_key = f"{SERIES_KEY}/chapter-1"
    pages = parse_chapter_pages(_load("chapter_reader.html"), chapter_key)
    assert len(pages) == 13
    assert pages[0].id == f"{chapter_key}:1"
    assert pages[0].number == 1
    assert pages[0].chapter_id == chapter_key
    assert pages[0].remote_url == "https://img01.manhwa18.cc/uploads/1838/1/1-774.jpg"
    assert pages[-1].number == 13
    assert [page.number for page in pages] == list(range(1, 14))
    assert all(page.remote_url and page.remote_url.startswith("https://") for page in pages)


def test_chapter_pages_are_scoped_to_the_reader_block() -> None:
    """The reader page is full of ad/thumbnail images. Only the ones inside
    ``.read-content`` are chapter pages."""
    html_text = _load("chapter_reader.html")
    all_data_src = html_text.count('data-src="')
    pages = parse_chapter_pages(html_text, f"{SERIES_KEY}/chapter-1")
    assert all_data_src > len(pages)
    assert all("manhwa18.cc" in (page.remote_url or "") for page in pages)


def test_parse_chapter_pages_returns_empty_without_a_reader_block() -> None:
    assert parse_chapter_pages("<html><body>no reader</body></html>", "x/chapter-1") == []


# --------------------------------------------------------------------------
# Request shapes (what the connector actually asks the site for)
# --------------------------------------------------------------------------


def test_browse_requests_page_path_and_orderby(connector: Manhwa18Connector) -> None:
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return _load("browse_page1.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.get_series_list(1)
        connector.get_series_list(3, sort="trending")
        connector.get_series_list(1, sort="raw")

    assert captured[0] == ("/webtoons/1", {"orderby": "latest"})
    assert captured[1] == ("/webtoons/3", {"orderby": "trending"})
    # /raw is its own listing and ignores orderby -- do not send a no-op param.
    assert captured[2] == ("/raw/1", None)


def test_every_browse_mode_maps_to_a_distinct_request(connector: Manhwa18Connector) -> None:
    """Six modes must produce six genuinely different requests. A mode that
    quietly resolves to the same URL as another is a broken mode."""
    captured: list[tuple[str, tuple[tuple[str, str], ...]]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, tuple(sorted((params or {}).items()))))
        return _load("browse_page1.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        for mode in connector.list_browse_modes():
            connector.get_series_list(1, sort=mode.id)

    assert len(captured) == len(connector.list_browse_modes()) == 6
    assert len(set(captured)) == len(captured)


def test_search_requests_the_search_endpoint(connector: Manhwa18Connector) -> None:
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return _load("search_love.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.search_series("  love  ", 2)

    assert captured == [("/search", {"q": "love", "page": "2"})]


def test_genre_browse_requests_the_genre_path(connector: Manhwa18Connector) -> None:
    captured: list[str] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(path)
        return _load("genre_romance.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.browse_by_genre("romance", 2)

    assert captured == ["/webtoon-genre/romance/2"]


def test_unknown_genre_is_rejected_without_a_request(connector: Manhwa18Connector) -> None:
    with patch.object(connector._http, "get_text", side_effect=AssertionError("no request")):
        with pytest.raises(ValueError):
            connector.browse_by_genre("../../etc/passwd", 1)


def test_list_genres_costs_no_request(connector: Manhwa18Connector) -> None:
    with patch.object(connector._http, "get_text", side_effect=AssertionError("no request")):
        genres = connector.list_genres()
    assert len(genres) == 40
    assert any(mode.id == "romance" for mode in genres)


# --------------------------------------------------------------------------
# Speed: request-count guarantees
# --------------------------------------------------------------------------


def test_detail_and_chapter_list_share_one_fetch(connector: Manhwa18Connector) -> None:
    """The series page is ~190KB and carries BOTH the metadata and the full
    chapter list. Fetching it once for get_series and again for get_chapters
    is the exact anti-pattern this project has already fixed elsewhere."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return _load("series_detail.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)
        connector.get_series(SERIES_KEY)
        connector.get_chapters(SERIES_KEY)

    assert calls == [f"/webtoon/{SERIES_KEY}"]
    assert series is not None
    assert series.chapter_count == 227
    assert series.latest_chapter == "Chapter 226"
    assert len(chapters) == 227


def test_chapter_pages_cost_one_request_for_every_page(connector: Manhwa18Connector) -> None:
    """All page-image URLs come from one chapter document. A request per page
    would be catastrophic on a 62-page chapter."""
    chapter_key = f"{SERIES_KEY}/chapter-1"
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return _load("chapter_reader.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages(chapter_key)
        connector.get_chapter_pages(chapter_key)

    assert calls == [f"/webtoon/{chapter_key}"]
    assert len(pages) == 13


def test_find_page_resolves_from_the_page_id_alone(connector: Manhwa18Connector) -> None:
    """The image proxy calls find_page once per image. It must resolve the
    chapter from the id — never traverse series -> chapters -> pages."""
    chapter_key = f"{SERIES_KEY}/chapter-1"
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return _load("chapter_reader.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        first = connector.find_page(f"{chapter_key}:5")
        second = connector.find_page(f"{chapter_key}:9")

    assert calls == [f"/webtoon/{chapter_key}"]
    assert first is not None and first.number == 5
    assert second is not None and second.number == 9


def test_find_page_returns_none_for_a_malformed_id(connector: Manhwa18Connector) -> None:
    with patch.object(connector._http, "get_text", side_effect=AssertionError("no request")):
        assert connector.find_page("no-colon-here") is None


def test_chapter_page_count_backfills_into_the_chapter_list(
    connector: Manhwa18Connector,
) -> None:
    chapter_key = f"{SERIES_KEY}/chapter-1"

    def fake_get_text(path: str, *, params=None):
        if path == f"/webtoon/{SERIES_KEY}":
            return _load("series_detail.html")
        return _load("chapter_reader.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        before = {c.id: c.page_count for c in connector.get_chapters(SERIES_KEY)}
        connector.get_chapter_pages(chapter_key)
        after = {c.id: c.page_count for c in connector.get_chapters(SERIES_KEY)}

    assert before[chapter_key] == 0
    assert after[chapter_key] == 13


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------


def test_missing_series_returns_none_not_an_exception(connector: Manhwa18Connector) -> None:
    """A missing slug answers a real 404 from the VPS. The shared client only
    attaches ``status_code`` for RETRYABLE_STATUS, so the 404 arrives only as
    httpx's message text -- the both-forms check must catch it."""
    from connectors.http.client import ConnectorHttpError

    message = (
        "Client error '404 Not Found' for url "
        "'https://manhwa18.cc/webtoon/this-series-does-not-exist-zzz'"
    )
    with patch.object(
        connector._http, "get_text", side_effect=ConnectorHttpError(message)
    ):
        assert connector.get_series("this-series-does-not-exist-zzz") is None
        assert connector.get_chapters("this-series-does-not-exist-zzz") == []


def test_non_404_detail_failure_propagates(connector: Manhwa18Connector) -> None:
    """A 503 is not "this series does not exist" -- swallowing it would cache
    an empty library page over a transient upstream blip."""
    from connectors.http.client import ConnectorHttpError

    with patch.object(
        connector._http,
        "get_text",
        side_effect=ConnectorHttpError("Server error '503'", status_code=503),
    ):
        with pytest.raises(ConnectorHttpError):
            connector.get_series(SERIES_KEY)


def test_series_and_chapter_keys_round_trip_through_normalization(
    connector: Manhwa18Connector,
) -> None:
    """Keys may arrive percent-encoded or with the site path prefix; both must
    normalize back to the raw opaque key."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return _load("series_detail.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.get_series(f"/webtoon/{SERIES_KEY}")
        connector.get_series(SERIES_KEY)

    assert calls == [f"/webtoon/{SERIES_KEY}"]
