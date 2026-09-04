"""Offline tests for the Manga Fox (fanfox.net) connector.

Fixtures under ``tests/fixtures/fanfox/`` were captured live 2026-09-04 FROM
THE VPS — production's exact egress and TLS stack. Every stage is exercised
against those captures by patching ``self._http.get_text``; no network.

Two chapter shapes are covered because fanfox serves both: ``chapter_c001_p1``
embeds the whole chapter in a packed ``newImgs`` array, while
``chapter_mode_b_p1`` ships only a ``guidkey`` and makes the reader call
``chapterfun.ashx`` (``chapterfun_p1.js``).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.fanfox.connector import FanFoxConnector
from connectors.fanfox.mappers import (
    chapter_path,
    chapterfun_path,
    listing_path,
    make_page_id,
    normalize_chapter_key,
    normalize_series_key,
    page_id_chapter_key,
    parse_chapter_ident,
    parse_chapter_number,
    parse_chapterfun,
    parse_chapters,
    parse_embedded_image_urls,
    parse_guidkey,
    parse_image_count,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
    search_params,
    series_path,
)
from connectors.http.client import ConnectorHttpError

FIXTURES = Path(__file__).parent / "fixtures" / "fanfox"

SERIES_KEY = "solo_leveling"
MODE_A_CHAPTER = "solo_leveling/c001"
MODE_B_CHAPTER = "one_piece/c1100"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def directory_html() -> str:
    return _load("directory_p1.html")


@pytest.fixture(scope="module")
def search_html() -> str:
    return _load("search.html")


@pytest.fixture(scope="module")
def series_html() -> str:
    return _load("series_solo_leveling.html")


@pytest.fixture(scope="module")
def missing_html() -> str:
    return _load("series_missing.html")


@pytest.fixture(scope="module")
def chapter_a_html() -> str:
    return _load("chapter_c001_p1.html")


@pytest.fixture(scope="module")
def chapter_b_html() -> str:
    return _load("chapter_mode_b_p1.html")


@pytest.fixture(scope="module")
def chapterfun_js() -> str:
    return _load("chapterfun_p1.js")


# --- identity ---------------------------------------------------------------


def test_chapter_key_may_contain_slashes_and_round_trips():
    """House law: identity keys are opaque strings, passed through raw."""
    volume_key = "one_piece/vTBE/c1100"
    assert "/" in volume_key
    assert normalize_chapter_key(volume_key) == volume_key
    # Every reference shape reduces to the same opaque key.
    assert normalize_chapter_key(f"/manga/{volume_key}/1.html") == volume_key
    assert normalize_chapter_key(f"https://fanfox.net/manga/{volume_key}/7.html") == volume_key
    assert chapter_path(volume_key) == f"/manga/{volume_key}/1.html"
    assert chapterfun_path(volume_key) == f"/manga/{volume_key}/chapterfun.ashx"


def test_series_key_round_trips():
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key("/manga/solo_leveling/") == SERIES_KEY
    assert normalize_series_key("https://fanfox.net/manga/solo_leveling/") == SERIES_KEY
    assert series_path(SERIES_KEY) == "/manga/solo_leveling/"


def test_page_id_recovers_chapter_key_without_parsing_it():
    page_id = make_page_id(MODE_B_CHAPTER, 7)
    assert page_id == "one_piece/c1100:7"
    assert page_id_chapter_key(page_id) == MODE_B_CHAPTER
    assert page_id_chapter_key("no-colon") is None


def test_listing_and_search_paths():
    assert listing_path(1) == "/directory/"
    assert listing_path(3) == "/directory/3.html"
    assert listing_path(1, sort="rating") == "/directory/?rating"
    assert listing_path(2, genre="action", sort="latest") == "/directory/action/2.html?latest"
    assert search_params("solo leveling", 1) == {"title": "solo leveling"}
    assert search_params("solo leveling", 3) == {"title": "solo leveling", "page": 3}


@pytest.mark.parametrize(
    ("label", "expected"),
    [("Ch.202", 202), ("Ch.200.5", 200.5), ("Ch.000 - Prologue", 0), ("Vol.01 Ch.131", 131)],
)
def test_parse_chapter_number_uses_the_sites_own_numbering(label, expected):
    assert parse_chapter_number(label) == expected


# --- listing ----------------------------------------------------------------


def test_parse_series_list_reads_every_card(directory_html):
    listing = parse_series_list(directory_html, page=1)
    assert len(listing.items) == 70
    first = listing.items[0]
    assert first.id == (
        "a_story_about_treating_a_female_knight_who_has_never_been_treated_as_a_woman_as_a_woman"
    )
    # The visible anchor text is ellipsised; the full name comes from @title.
    assert first.title == (
        "A Story About Treating a Female Knight Who Has Never Been Treated as a Woman as a Woman"
    )
    assert first.cover_url.startswith("https://fmcdn.mfcdn.net/store/manga/")
    assert first.latest_chapter == "Vol.01 Ch.131"
    assert first.canonical_path == f"/manga/{first.id}/"
    assert any(item.id == "one_piece" for item in listing.items)


def test_parse_series_list_reports_pagination(directory_html):
    listing = parse_series_list(directory_html, page=1)
    assert listing.total_pages == 143
    assert listing.has_more is True


# --- search -----------------------------------------------------------------


def test_parse_search_results_carries_rich_metadata(search_html):
    listing = parse_search_results(search_html, page=1)
    assert len(listing.items) == 12
    top = listing.items[0]
    assert top.id == SERIES_KEY
    assert top.title == "Solo Leveling"
    assert top.status == "Completed"
    # The " [Add]" pseudo-link is a UI affordance, not a credit.
    assert top.author == "Jang Sung-Lak"
    assert top.latest_chapter == "Ch.202"
    assert top.description and "the Gate" in top.description
    assert listing.has_more is True


# --- series detail ----------------------------------------------------------


def test_parse_series_detail(series_html):
    series = parse_series_detail(series_html, SERIES_KEY)
    assert series is not None
    assert series.title == "Solo Leveling"
    assert series.status == "Completed"
    assert series.author == "Jang Sung-Lak"
    assert series.genres == ("Action", "Adventure", "Fantasy", "Shounen", "Webtoons")
    assert series.cover_url.startswith("https://fmcdn.mfcdn.net/")
    # The full blurb, not the truncated teaser with its "more" toggle.
    assert series.description and len(series.description) > 400
    assert "E-rank Hunter" in series.description
    assert not series.description.endswith("more")


def test_unknown_slug_is_rejected_despite_http_200(missing_html):
    """Fanfox serves its SEARCH page for an unknown slug, under HTTP 200.

    Trusting the status would publish an empty series named after the search
    box, so the parser must refuse a document with no detail header.
    """
    assert parse_series_detail(missing_html, "definitely_not_a_real_series_xyz") is None


# --- chapter list -----------------------------------------------------------


def test_parse_chapters_reads_the_inline_table(series_html):
    chapters = parse_chapters(series_html, SERIES_KEY)
    assert len(chapters) == 215
    # Returned oldest-first even though the page renders newest-first.
    assert chapters[0].id == "solo_leveling/c000"
    assert chapters[0].number == 0
    assert chapters[0].title == "Ch.000 - Prologue"
    assert chapters[0].release_date == "Nov 05,2018"
    assert chapters[-1].id == "solo_leveling/c202"
    assert chapters[-1].number == 202
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers)
    # Decimal chapters keep the site's own numbering.
    assert 200.5 in numbers
    assert all(c.series_id == SERIES_KEY for c in chapters)


# --- reader: mode A (embedded) ----------------------------------------------


def test_mode_a_chapter_embeds_every_image_url(chapter_a_html):
    assert parse_image_count(chapter_a_html) == 16
    urls = parse_embedded_image_urls(chapter_a_html)
    assert len(urls) == 16
    assert all(u.startswith("https://zjcdn.mangafox.me/store/manga/29037/001.0/") for u in urls)
    assert all("token=" in u and "ttl=" in u for u in urls)
    # Distinct images, not the same URL repeated.
    assert len(set(urls)) == 16


# --- reader: mode B (guidkey -> chapterfun.ashx) ----------------------------


def test_mode_b_chapter_ships_a_guidkey_instead_of_urls(chapter_b_html):
    assert parse_image_count(chapter_b_html) == 19
    assert parse_embedded_image_urls(chapter_b_html) == []
    # Emitted as ''+'c'+'9'+... purely to defeat naive scraping.
    assert parse_guidkey(chapter_b_html) == "c909668712873f23"
    assert parse_chapter_ident(chapter_b_html) == ("1389352", "106")


def test_parse_chapterfun_expands_pix_and_pvalue(chapterfun_js):
    urls = parse_chapterfun(chapterfun_js)
    assert len(urls) == 2
    assert urls[0].endswith("o000.jpg?token=a79b522249410f0d6ae0f7b6d90c0222ed604b5a&ttl=1788624000")
    assert urls[1].endswith("o001.jpg?token=664e37b738ee55f8075ae2b0a28101fd8ab56da6&ttl=1788624000")
    assert all(u.startswith("https://zjcdn.mangafox.me/store/manga/106/TBE-1100.0/compressed/") for u in urls)


# --- connector wiring -------------------------------------------------------


def _connector() -> FanFoxConnector:
    return FanFoxConnector()


def test_get_series_and_get_chapters_share_one_fetch(series_html):
    """Speed contract: the chapter table is inline, so one GET serves both."""
    connector = _connector()
    with patch.object(connector._http, "get_text", return_value=series_html) as get_text:
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)
    assert get_text.call_count == 1
    assert series is not None
    assert series.title == "Solo Leveling"
    assert series.chapter_count == 215
    assert series.latest_chapter == "Ch.202"
    assert len(chapters) == 215


def test_get_series_returns_none_for_unknown_slug(missing_html):
    connector = _connector()
    with patch.object(connector._http, "get_text", return_value=missing_html):
        assert connector.get_series("definitely_not_a_real_series_xyz") is None


def test_get_chapter_pages_mode_a_costs_exactly_one_request(chapter_a_html):
    connector = _connector()
    with patch.object(connector._http, "get_text", return_value=chapter_a_html) as get_text:
        pages = connector.get_chapter_pages(MODE_A_CHAPTER)
    assert get_text.call_count == 1
    assert len(pages) == 16
    assert pages[0].id == f"{MODE_A_CHAPTER}:1"
    assert pages[0].number == 1
    assert pages[0].chapter_id == MODE_A_CHAPTER
    assert pages[0].remote_url.endswith("n20181105_144325_926.jpg?token=74f699c05804b8d959b3eea72709a85dc22fd79f&ttl=1788624000")
    assert [p.number for p in pages] == list(range(1, 17))


def test_get_chapter_pages_mode_b_fans_out_two_pages_per_call(chapter_b_html):
    """19 pages must cost 1 chapter GET + ceil(19/2) chapterfun calls."""
    connector = _connector()
    calls: list[str] = []

    def fake_get_text(path, *, params=None):
        calls.append(path)
        if path.endswith("chapterfun.ashx"):
            start = int(params["page"])
            assert params["cid"] == "1389352"
            assert params["key"] == "c909668712873f23"
            body = "//zjcdn.mangafox.me/store/manga/106/TBE-1100.0/compressed"
            return _packed_chapterfun(body, start)
        return chapter_b_html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages(MODE_B_CHAPTER)

    assert len(pages) == 19
    assert [p.number for p in pages] == list(range(1, 20))
    assert calls.count(chapterfun_path(MODE_B_CHAPTER)) == 10  # ceil(19 / 2)
    assert len(calls) == 11
    assert pages[0].remote_url.endswith("/o001.jpg?token=t1")
    assert pages[18].remote_url.endswith("/o019.jpg?token=t19")


def _packed_chapterfun(pix: str, start: int) -> str:
    """A chapterfun response in the site's own shape, already unpacked.

    Written as plain JS so this test exercises the pix+pvalue assembly and the
    fan-out arithmetic rather than re-testing the unpacker — the real packed
    wire format is covered against a live capture by
    ``test_parse_chapterfun_expands_pix_and_pvalue``.
    """
    values = ",".join(f'"/o{n:03d}.jpg?token=t{n}"' for n in (start, start + 1))
    return f'var pix="{pix}";var pvalue=[{values}];'


def test_mode_b_stops_at_a_gap_rather_than_serving_a_hole(chapter_b_html):
    """A failed chapterfun call must truncate, never silently skip a page."""
    connector = _connector()

    def fake_get_text(path, *, params=None):
        if path.endswith("chapterfun.ashx"):
            start = int(params["page"])
            if start == 7:
                raise ConnectorHttpError("Retryable HTTP 503", status_code=503)
            return _packed_chapterfun("//zjcdn.mangafox.me/x", start)
        return chapter_b_html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages(MODE_B_CHAPTER)

    # Pages 7 and 8 were lost, so the chapter stops at 6.
    assert [p.number for p in pages] == [1, 2, 3, 4, 5, 6]


def test_chapter_pages_are_cached_so_find_page_costs_nothing_extra(chapter_a_html):
    connector = _connector()
    with patch.object(connector._http, "get_text", return_value=chapter_a_html) as get_text:
        pages = connector.get_chapter_pages(MODE_A_CHAPTER)
        found = connector.find_page(make_page_id(MODE_A_CHAPTER, 5))
        again = connector.get_chapter_pages(MODE_A_CHAPTER)
    assert get_text.call_count == 1
    assert found is not None
    assert found.number == 5
    assert found.remote_url == pages[4].remote_url
    assert again == pages


def test_find_page_rejects_a_foreign_page_id(chapter_a_html):
    connector = _connector()
    with patch.object(connector._http, "get_text", return_value=chapter_a_html):
        assert connector.find_page("solo_leveling/c001:999") is None
    assert connector.find_page("malformed") is None


def test_missing_chapter_404_yields_no_pages():
    connector = _connector()
    # The shared client only attaches status_code for RETRYABLE_STATUS, so a
    # real 404 arrives as httpx's raise_for_status text — both forms must work.
    error = ConnectorHttpError("Client error '404 Not Found' for url ...")
    with patch.object(connector._http, "get_text", side_effect=error):
        assert connector.get_chapter_pages(MODE_A_CHAPTER) == []


def test_page_count_is_remembered_for_the_chapter_list(series_html, chapter_a_html):
    connector = _connector()
    with patch.object(connector._http, "get_text", return_value=chapter_a_html):
        connector.get_chapter_pages(MODE_A_CHAPTER)
    with patch.object(connector._http, "get_text", return_value=series_html):
        chapters = connector.get_chapters(SERIES_KEY)
    read = [c for c in chapters if c.id == MODE_A_CHAPTER]
    assert read and read[0].page_count == 16


def test_image_proxy_contract():
    """The CDN 403s a request with no Referer; the proxy must send one."""
    connector = _connector()
    assert connector.image_fetch_headers() == {"Referer": "https://fanfox.net/"}
    hosts = connector.allowed_image_hosts
    assert "mangafox.me" in hosts and "mfcdn.net" in hosts
    assert connector.source_type == "fanfox"
    assert connector.is_mature is False
    assert connector.content_kind == "manga"


def test_request_headers_carry_the_referer_chapterfun_requires():
    """chapterfun.ashx answers 200 with an EMPTY body if the referer is absent.

    Once the client holds fanfox's session cookies, a referer-less call to the
    reader endpoint is not an error — it is a silent empty response, which
    would surface as a chapter with zero pages. Losing this header is a
    plausible "harmless cleanup", so it is pinned here.
    """
    connector = _connector()
    assert connector._http._client.headers["Referer"] == "https://fanfox.net/"


def test_age_gate_cookie_is_set():
    """Fanfox truncates ecchi-tagged titles to ZERO chapters without this.

    The affected series are listed in the ordinary catalog, so losing the
    cookie does not fail loudly — it silently serves unopenable series.
    """
    connector = _connector()
    assert connector._http._client.cookies.get("isAdult", domain=".fanfox.net") == "1"


def test_browse_and_genre_paths_are_requested(directory_html):
    connector = _connector()
    with patch.object(connector._http, "get_text", return_value=directory_html) as get_text:
        connector.get_series_list(2, sort="rating")
        connector.browse_by_genre("action", 1)
    assert get_text.call_args_list[0].args[0] == "/directory/2.html?rating"
    assert get_text.call_args_list[1].args[0] == "/directory/action/"


def test_search_requests_the_allowed_endpoint(search_html):
    """robots.txt disallows /search.php but allows /search."""
    connector = _connector()
    with patch.object(connector._http, "get_text", return_value=search_html) as get_text:
        listing = connector.search_series("solo leveling", 1)
    path = get_text.call_args.args[0]
    assert path == "/search"
    assert not path.endswith(".php")
    assert get_text.call_args.kwargs["params"] == {"title": "solo leveling"}
    assert listing.items[0].id == SERIES_KEY
