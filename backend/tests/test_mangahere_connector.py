"""MangaHere connector tests.

Every fixture under ``tests/fixtures/mangahere/`` was captured from the
production VPS with the project's own User-Agent, so these exercise the exact
bytes production parses. Network is never touched: ``self._http.get_text`` is
patched throughout.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.mangahere.connector import _is_not_found, MangaHereConnector
from connectors.mangahere.mappers import (
    drop_last_advert,
    extract_chapterfun_context,
    extract_inline_page_urls,
    is_removed,
    listing_path,
    make_page_id,
    page_id_chapter_key,
    parse_chapter_number,
    parse_chapterfun_response,
    parse_chapters,
    parse_image_info,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_path,
    unpack_packed_script,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mangahere"

#: The classic-manga chapter the chapterfun fixtures were captured for.
ASHX_CHAPTER = "pluto/v01/c001"
ASHX_IMAGE_COUNT = 41


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def connector() -> MangaHereConnector:
    return MangaHereConnector()


def _fixture_http(record: list[tuple[str, dict | None]] | None = None):
    """Return a ``get_text`` stand-in that serves the captured documents."""

    def get_text(path: str, *, params: dict | None = None) -> str:
        if record is not None:
            record.append((path, params))
        if path.startswith(f"/manga/{ASHX_CHAPTER}/chapterfun.ashx"):
            assert params is not None
            return _load(f"chapterfun/page_{params['page']}.js")
        if path.startswith(f"/manga/{ASHX_CHAPTER}/"):
            return _load("chapter_ashx.html")
        if path.startswith("/manga/solo_leveling/c202"):
            return _load("chapter_inline.html")
        if path.startswith("/manga/onepunch_man/"):
            return _load("chapter_removed.html")
        if path == "/manga/solo_leveling/":
            return _load("series_detail.html")
        if path == "/manga/pluto/":
            return _load("series_detail_volumes.html")
        if path.startswith("/search"):
            return _load("search_solo.html")
        if path == "/directory/2.htm?rating":
            return _load("browse_rating.html")
        if path == "/directory/2.htm":
            return _load("browse_page2.html")
        if path == "/action/2.htm":
            return _load("genre_action_page2.html")
        return _load("browse_page1.html")

    return get_text


# --- browse listings --------------------------------------------------------


def test_parse_browse_listing_from_fixture():
    listing = parse_series_list(_load("browse_page1.html"), page=1)

    assert len(listing.items) == 70
    first = listing.items[0]
    assert first.id == "onepunch_man"
    assert first.title == "Onepunch-Man"
    assert first.canonical_path == "/manga/onepunch_man/"
    assert first.cover_url is not None and first.cover_url.startswith("https://")
    assert first.latest_chapter
    # The pager's last link is page 143, so the listing must report the real
    # catalog size rather than "one page of results".
    assert listing.total == 143 * 70
    assert listing.has_more is True


def test_browse_page_two_is_a_different_listing(connector: MangaHereConnector):
    with patch.object(connector._http, "get_text", side_effect=_fixture_http()):
        page1 = connector.get_series_list(1)
        page2 = connector.get_series_list(2)

    assert page1.items and page2.items
    assert page1.items[0].id != page2.items[0].id
    assert {item.id for item in page1.items[:10]}.isdisjoint(
        {item.id for item in page2.items[:10]}
    )


def test_every_browse_mode_requests_a_distinct_path(connector: MangaHereConnector):
    """MangaHere's sort flag is a BARE query key.

    ``/directory/2.htm?rating`` re-sorts the catalog; ``?rating=`` is silently
    ignored and the site serves its default popularity order (verified from
    the VPS -- the first three slugs were identical to the unsorted page).
    Passing the flag through ``params`` would render it with the ``=``, so
    this pins both that each mode is a genuinely different request AND that
    the flag never grows a value.
    """
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        for mode in connector.list_browse_modes():
            connector.get_series_list(2, sort=mode.id)

    paths = [path for path, _params in record]
    assert len(set(paths)) == len(paths), f"modes collapsed onto one request: {paths}"
    assert all(params is None for _path, params in record)
    for path in paths:
        _base, _sep, query = path.partition("?")
        assert "=" not in query, f"sort flag must stay valueless, got {path!r}"


def test_rating_mode_parses_a_different_catalog_than_default(
    connector: MangaHereConnector,
):
    """The end-to-end half of the sort check, on real captured HTML.

    Asserting only on request shape would not have caught the ``?rating=``
    bug -- the request looked fine and the site quietly returned the default
    listing. These two fixtures are ``/directory/2.htm`` and
    ``/directory/2.htm?rating`` as the VPS served them.
    """
    with patch.object(connector._http, "get_text", side_effect=_fixture_http()):
        default = connector.get_series_list(2)
        rated = connector.get_series_list(2, sort="rating")

    assert default.items[0].id != rated.items[0].id
    assert {item.id for item in default.items[:5]}.isdisjoint(
        {item.id for item in rated.items[:5]}
    )


def test_genre_browse_uses_the_genre_path(connector: MangaHereConnector):
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        listing = connector.browse_by_genre("action", 2)

    assert record[0][0] == "/action/2.htm"
    assert len(listing.items) == 70
    assert all(item.id for item in listing.items)


def test_genre_browse_rejects_an_unknown_genre(connector: MangaHereConnector):
    with pytest.raises(NotImplementedError):
        connector.browse_by_genre("not-a-real-genre", 1)


def test_listing_path_shapes():
    assert listing_path(1) == "/directory/"
    assert listing_path(3) == "/directory/3.htm"
    assert listing_path(2, sort="rating") == "/directory/2.htm?rating"
    assert listing_path(1, sort="latest") == "/new/"
    assert listing_path(4, genre="romance") == "/romance/4.htm"


# --- search -----------------------------------------------------------------


def test_search_cards_carry_the_metadata_the_site_shows():
    listing = parse_search_results(_load("search_solo.html"), page=1)

    assert len(listing.items) == 12
    first = listing.items[0]
    assert first.id == "solo_leveling"
    assert first.title == "Solo Leveling"
    assert first.status == "Completed"
    assert first.author == "Jang Sung-Lak"
    assert first.latest_chapter == "Ch.202"
    assert first.description and "Gate" in first.description
    assert first.cover_url and first.cover_url.startswith("https://")
    assert listing.has_more is True


def test_search_never_uses_the_robots_disallowed_endpoint():
    """robots.txt allows everything except ``/bookmark/`` and ``/search.php``.

    The legacy ``/search.php?name=`` endpoint still answers 200, so nothing
    but this test stops a future edit from reaching for it.
    """
    path = search_path("solo leveling", 2)
    assert path.startswith("/search?")
    assert "search.php" not in path
    assert "bookmark" not in path
    assert "page=2" in path


def test_blank_search_falls_back_to_browse(connector: MangaHereConnector):
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        listing = connector.search_series("   ", 1)

    assert record[0][0] == "/directory/"
    assert listing.items


# --- series detail and chapters --------------------------------------------


def test_series_detail_parses_full_metadata():
    series = parse_series_detail(_load("series_detail.html"), "solo_leveling")

    assert series is not None
    assert series.title == "Solo Leveling"
    assert series.status == "Completed"
    assert series.author == "Jang Sung-Lak"
    assert series.genres == ("Action", "Adventure", "Shounen")
    # The site truncates the visible blurb and hides the full one in a
    # .fullcontent paragraph -- the full text is what must be stored.
    assert series.description is not None
    assert "Sung Jin-Woo" in series.description
    assert series.cover_url is not None
    assert series.cover_url.startswith("https://fmcdn.mangahere.com/")


def test_series_detail_rejects_a_taken_down_page():
    assert is_removed(_load("chapter_removed.html")) is True
    assert parse_series_detail(_load("chapter_removed.html"), "onepunch_man") is None


def test_chapters_parse_ascending_with_decimal_numbers():
    chapters = parse_chapters(_load("series_detail.html"), "solo_leveling")

    assert len(chapters) == 212
    numbers = [chapter.number for chapter in chapters]
    assert numbers == sorted(numbers), "chapters must come back ascending"
    assert chapters[0].id == "solo_leveling/c001"
    assert chapters[-1].id == "solo_leveling/c202"
    assert chapters[-1].number == 202.0
    by_id = {chapter.id: chapter for chapter in chapters}
    assert by_id["solo_leveling/c200.5"].number == 200.5
    assert all(chapter.series_id == "solo_leveling" for chapter in chapters)
    assert by_id["solo_leveling/c202"].release_date == "Jan 09,2025"


def test_volume_chapter_keys_survive_intact():
    """Identity keys are opaque strings that may contain slashes.

    MangaHere's volume-organised titles address chapters as
    ``pluto/v08/c065``; the number still has to come off the ``cNNN`` tail.
    """
    chapters = parse_chapters(_load("series_detail_volumes.html"), "pluto")

    assert len(chapters) == 65
    assert chapters[0].id == "pluto/v01/c001"
    assert chapters[-1].id == "pluto/v08/c065"
    assert chapters[-1].number == 65.0
    assert "The World's Strongest Robot" in chapters[-1].title
    assert [chapter.number for chapter in chapters] == sorted(
        chapter.number for chapter in chapters
    )


def test_parse_chapter_number_handles_every_key_shape():
    assert parse_chapter_number("solo_leveling/c202") == 202.0
    assert parse_chapter_number("solo_leveling/c200.5") == 200.5
    assert parse_chapter_number("pluto/v08/c065") == 65.0
    assert parse_chapter_number("/manga/pluto/v08/c065/1.html") == 65.0
    assert parse_chapter_number("weird/slug-with-no-number") is None


def test_series_and_chapters_share_a_single_fetch(connector: MangaHereConnector):
    """Opening a series must not download its 120KB detail page twice.

    MangaHere renders the whole chapter list inside the detail document, so
    the detail read and the chapter-list read are the SAME request. Fetching
    it once per call is the exact anti-pattern this project has already had
    to fix elsewhere.
    """
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        series = connector.get_series("solo_leveling")
        chapters = connector.get_chapters("solo_leveling")
        connector.get_chapters("solo_leveling")

    assert series is not None
    assert series.chapter_count == 212
    assert len(chapters) == 212
    assert len(record) == 1, f"expected one HTTP fetch, got {record}"


def test_chapters_then_series_still_costs_one_fetch(connector: MangaHereConnector):
    """The reverse order the reader actually uses.

    A reader that opens the chapter list first and then asks for series
    metadata must not trigger a second download of the same document -- this
    is the direction that only the raw-HTML cache covers, since nothing has
    populated the parsed-``Series`` cache yet.
    """
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        chapters = connector.get_chapters("solo_leveling")
        series = connector.get_series("solo_leveling")

    assert len(chapters) == 212
    assert series is not None and series.title == "Solo Leveling"
    assert len(record) == 1, f"expected one HTTP fetch, got {record}"


def test_get_series_returns_none_for_a_missing_slug(connector: MangaHereConnector):
    """An unknown slug 302s onto the search page, which parses to nothing."""
    with patch.object(
        connector._http, "get_text", side_effect=lambda *a, **k: _load("search_solo.html")
    ):
        assert connector.get_series("no_such_series_zzz") is None


# --- chapter pages: the inline (long-strip) path ---------------------------


def test_inline_chapter_resolves_every_page_in_one_request(
    connector: MangaHereConnector,
):
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        pages = connector.get_chapter_pages("solo_leveling/c202")

    assert len(record) == 1, "a long-strip chapter must cost exactly one request"
    assert record[0][0] == "/manga/solo_leveling/c202/1.html"
    assert len(pages) == 12
    assert [page.number for page in pages] == list(range(1, 13))
    assert all(page.chapter_id == "solo_leveling/c202" for page in pages)
    for page in pages:
        assert page.remote_url is not None
        assert page.remote_url.startswith("https://zjcdn.mangahere.org/")


def test_inline_chapter_drops_the_sites_trailing_adverts():
    """The reader must not be handed MangaHere's own promo images as pages.

    The captured chapter carries 14 images; the last two are flagged
    ``"d": 2`` in the site's own ``_tpimagearr`` and are (verified by
    fetching them) a scanlator banner and MangaHere's app advert.
    """
    html = _load("chapter_inline.html")
    info = parse_image_info(html)

    assert len(info) == 14
    assert [entry["d"] for entry in info[-2:]] == [2, 2]
    assert [entry["d"] for entry in info[:-2]] == [1] * 12

    urls = extract_inline_page_urls(html)
    assert len(urls) == 12
    assert not any("9013-" in url for url in urls)


def test_inline_pages_carry_the_sites_own_dimensions(connector: MangaHereConnector):
    """``_tpimagearr`` gives real pixel sizes for free -- pass them through."""
    with patch.object(connector._http, "get_text", side_effect=_fixture_http()):
        pages = connector.get_chapter_pages("solo_leveling/c202")

    assert pages[0].width == 760
    assert pages[0].height == 13820
    assert all(page.width and page.height for page in pages)


# --- chapter pages: the chapterfun (classic manga) path --------------------


def test_chapterfun_context_is_recovered_from_the_packed_script():
    """The key is assembled character by character so it never appears
    literally in the document; nothing works without decoding the packer."""
    context = extract_chapterfun_context(_load("chapter_ashx.html"))

    assert context is not None
    chapter_numeric_id, guidkey, image_count = context
    assert chapter_numeric_id == "47536"
    assert image_count == ASHX_IMAGE_COUNT
    assert len(guidkey) == 16
    assert guidkey not in _load("chapter_ashx.html")


def test_chapterfun_chapter_resolves_every_image(connector: MangaHereConnector):
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        pages = connector.get_chapter_pages(ASHX_CHAPTER)

    # 41 images upstream, minus the single advert the site appends.
    assert len(pages) == ASHX_IMAGE_COUNT - 1
    assert [page.number for page in pages] == list(range(1, ASHX_IMAGE_COUNT))
    urls = [page.remote_url for page in pages]
    assert len(set(urls)) == len(urls), "every page must be a distinct image"
    assert all(url and url.startswith("https://zjcdn.mangahere.org/") for url in urls)


def test_chapterfun_is_asked_for_half_the_pages_not_all_of_them(
    connector: MangaHereConnector,
):
    """One chapterfun reply covers the requested page AND the next one.

    Asking per page would double the request count of the slow path -- the
    "a request per page image" anti-pattern this project has already paid
    for once.
    """
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        connector.get_chapter_pages(ASHX_CHAPTER)

    chapterfun_calls = [
        params for path, params in record if "chapterfun.ashx" in path
    ]
    expected = (ASHX_IMAGE_COUNT + 1) // 2
    assert len(chapterfun_calls) == expected == 21
    assert len(record) == expected + 1, "one reader page plus the chapterfun fan-out"
    requested = sorted(int(params["page"]) for params in chapterfun_calls)
    assert requested == list(range(1, ASHX_IMAGE_COUNT + 1, 2))
    assert all(params["cid"] == "47536" for params in chapterfun_calls)


def test_chapterfun_response_decodes_to_absolute_image_urls():
    urls = parse_chapterfun_response(_load("chapterfun/page_1.js"))

    assert urls == [
        "https://zjcdn.mangahere.org/store/manga/2444/01-001.0/compressed/ms_tag.jpg",
        "https://zjcdn.mangahere.org/store/manga/2444/01-001.0/compressed/"
        "pluto_v01_cover_deluxe1.jpg",
    ]


def test_last_chapterfun_reply_is_the_advert_and_is_dropped():
    """The final image of a classic chapter is MangaHere's own advert.

    Verified from the VPS across seven chapters of seven different series:
    the last image was the same 206523-byte PNG every time.
    """
    tail = parse_chapterfun_response(_load(f"chapterfun/page_{ASHX_IMAGE_COUNT}.js"))

    assert len(tail) == 1, "the last page number returns a single image"
    assert drop_last_advert(tail * 3) == (tail * 3)[:-1]
    # Never trim a chapter down to nothing.
    assert drop_last_advert(tail) == tail
    assert drop_last_advert([]) == []


# --- taken-down content -----------------------------------------------------


def test_removed_chapter_serves_no_pages_rather_than_a_warning_graphic(
    connector: MangaHereConnector,
):
    """MangaHere leaves taken-down titles in the catalog.

    The chapter page still ships a ``chapterid`` and an ``imagecount``, and
    ``chapterfun.ashx`` answers with ``images/war.jpg``. Serving that would
    show the reader a warning placeholder as if it were page one.
    """
    html = _load("chapter_removed.html")
    assert is_removed(html) is True
    assert extract_inline_page_urls(html) == []

    with patch.object(connector._http, "get_text", side_effect=_fixture_http()):
        assert connector.get_chapter_pages("onepunch_man/c237") == []


def test_placeholder_image_url_is_never_served():
    """Defence in depth behind the takedown notice.

    ``chapterfun/removed_war.js`` is the real reply the VPS got for a
    taken-down Onepunch-Man chapter: a single ``images/war.jpg``. Even if
    the notice wording on the reader page ever changes, that placeholder
    must not reach the reader dressed up as page one.
    """
    script = _load("chapterfun/removed_war.js")

    assert "war" in script, "fixture must still be the placeholder reply"
    assert unpack_packed_script(script) is not None
    assert parse_chapterfun_response(script) == []


# --- packer -----------------------------------------------------------------


def test_packed_script_decodes_identity_tokens():
    """A packer dictionary entry that is EMPTY means "decodes to itself".

    Getting this wrong is silent and destructive: the chapter directory
    ``202.0`` would come out as ``202.`` and every image URL in the chapter
    would 404.
    """
    inline = extract_inline_page_urls(_load("chapter_inline.html"))

    assert inline, "expected the inline path to resolve"
    assert "/202.0/" in inline[0], inline[0]
    assert ".0/compressed/" in inline[0]


def test_unpack_rejects_a_non_packed_script():
    assert unpack_packed_script("var x = 1;") is None
    assert unpack_packed_script("") is None


# --- identity keys, caching, proxying --------------------------------------


def test_page_ids_round_trip_through_slashed_chapter_keys():
    page_id = make_page_id("pluto/v08/c065", 7)

    assert page_id == "pluto/v08/c065:7"
    assert page_id_chapter_key(page_id) == "pluto/v08/c065"
    assert page_id_chapter_key("no-colon-here") is None


def test_find_page_resolves_through_one_chapter_lookup(connector: MangaHereConnector):
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        connector.get_chapter_pages(ASHX_CHAPTER)
        before = len(record)
        page = connector.find_page(f"{ASHX_CHAPTER}:5")

    assert page is not None
    assert page.number == 5
    assert page.chapter_id == ASHX_CHAPTER
    # The chapter is already cached, so locating a page costs no new request.
    assert len(record) == before


def test_chapter_pages_are_cached(connector: MangaHereConnector):
    record: list[tuple[str, dict | None]] = []
    with patch.object(connector._http, "get_text", side_effect=_fixture_http(record)):
        first = connector.get_chapter_pages("solo_leveling/c202")
        after_first = len(record)
        second = connector.get_chapter_pages("solo_leveling/c202")

    assert first == second
    assert len(record) == after_first


def test_resolved_hosts_are_on_the_proxy_allowlist(connector: MangaHereConnector):
    from urllib.parse import urlparse

    from services.outbound_security import host_matches_allowlist

    with patch.object(connector._http, "get_text", side_effect=_fixture_http()):
        pages = connector.get_chapter_pages(ASHX_CHAPTER)
        series = connector.get_series("solo_leveling")

    assert series is not None and series.cover_url
    for url in [pages[0].remote_url, series.cover_url]:
        parsed = urlparse(url or "")
        assert parsed.scheme == "https"
        assert parsed.hostname
        assert host_matches_allowlist(parsed.hostname, connector.allowed_image_hosts)


def test_image_requests_carry_the_referer_the_cdn_demands(
    connector: MangaHereConnector,
):
    """Both MangaHere CDNs answer 403 with an HTML body when no ``Referer``
    is sent (verified from the VPS for the cover host and the page-image
    host). Without this header every cover and every page is a broken image.
    """
    headers = connector.image_fetch_headers()

    assert headers["Referer"] == "https://www.mangahere.cc/"


def test_not_found_detection_matches_both_error_shapes():
    """The shared client only sets ``status_code`` for RETRYABLE_STATUS, so a
    404 arrives as message text. Checking only the attribute is dead code."""
    assert _is_not_found(ConnectorHttpError("boom", status_code=404)) is True
    assert (
        _is_not_found(
            ConnectorHttpError("Client error '404 Not Found' for url 'https://x'")
        )
        is True
    )
    assert _is_not_found(ConnectorHttpError("Retryable HTTP 503", status_code=503)) is False


def test_connector_descriptors():
    connector = MangaHereConnector()

    assert connector.source_type == "mangahere"
    assert connector.display_name == "MangaHere"
    assert connector.is_browsable is True
    assert connector.is_mature is False
    assert connector.content_kind == "manga"
    assert len(connector.list_browse_modes()) == 7
    assert {mode.id for mode in connector.list_genres()} >= {"action", "romance"}
