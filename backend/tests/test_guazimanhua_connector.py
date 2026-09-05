"""Offline tests for the GuaziManhua (瓜子漫画) connector.

Fixtures under ``tests/fixtures/guazimanhua/`` were captured live 2026-09-05
FROM THE VPS (inside ``manhwamaniacs-backend``, so through production's exact
egress IP and TLS stack). The connector is exercised entirely against those
captures by patching ``self._http.get_text``; no test touches the network.

Every parse assertion here was watched to FAIL against a deliberately broken
selector before being kept -- a test that still passes on broken parsing
proves nothing.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest

from connectors.base import SourceConnector
from connectors.guazimanhua.connector import GuaziManhuaConnector
from connectors.guazimanhua.mappers import (
    CATEGORY_PATH,
    CHAPTER_PATH,
    PAGE_SIZE,
    SERIES_PATH,
    browse_params,
    canonical_path,
    genre_params,
    make_page_id,
    normalize_series_key,
    page_id_chapter_key,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_last_page,
    parse_series_detail,
    parse_series_list,
    search_params,
)
from connectors.http.client import ConnectorHttpError
from tests.connector_validation import ConnectorContractCase, validate_connector_contract

FIXTURES = Path(__file__).parent / "fixtures" / "guazimanhua"

SERIES_KEY = "18109"
CHAPTER_KEY = "2491382"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def connector() -> GuaziManhuaConnector:
    return GuaziManhuaConnector()


@contextmanager
def _mock_guazimanhua(connector: SourceConnector) -> Iterator[None]:
    browse_page1 = _load("browse_page1.html")
    browse_page2 = _load("browse_page2.html")
    browse_daily = _load("browse_daily.html")
    search = _load("search.html")
    genre = _load("genre.html")
    series_detail = _load("series_detail.html")
    chapter_reader = _load("chapter_reader.html")

    def fake_get_text(path: str, *, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        if path == CATEGORY_PATH:
            if params.get("keyword"):
                return search
            if params.get("cid"):
                return genre
            if params.get("sort") == "daily":
                return browse_daily
            if int(params.get("page", 1)) == 2:
                return browse_page2
            return browse_page1
        if path == SERIES_PATH:
            if str(params.get("id")) == SERIES_KEY:
                return series_detail
            raise ConnectorHttpError(
                f"Client error '404 Not Found' for url '{path}'", status_code=None
            )
        if path == CHAPTER_PATH and str(params.get("id")) == CHAPTER_KEY:
            return chapter_reader
        raise AssertionError(f"Unexpected path: {path} params={params}")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        yield


# --- identity ---------------------------------------------------------------


def test_series_key_is_the_sites_integer_id_from_any_inbound_shape():
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key("/comic.php?id=18109") == SERIES_KEY
    assert normalize_series_key("https://www.guazimanhua.com/comic.php?id=18109") == SERIES_KEY
    assert canonical_path(SERIES_KEY) == "/comic.php?id=18109"


def test_page_id_round_trips():
    page_id = make_page_id(CHAPTER_KEY, 12)
    assert page_id == f"{CHAPTER_KEY}:12"
    assert page_id_chapter_key(page_id) == CHAPTER_KEY
    assert page_id_chapter_key("no-separator-here") is None


def test_chapter_number_reads_the_chinese_label():
    assert parse_chapter_number("第1190话 众盼其死之人") == 1190.0
    assert parse_chapter_number("第1话ROMANCE DAWN") == 1.0
    # Side stories carry no digits; they still have to be orderable.
    assert parse_chapter_number("番外篇", fallback=7.0) == 7.0


# --- browse / search params -------------------------------------------------


def test_browse_params_match_the_sites_own_filter_chips():
    """The "全部" chip is a bare /category.php, so page 1 sends nothing."""
    assert browse_params(None, 1) == {}
    assert browse_params(None, 3) == {"page": 3}
    assert browse_params("hits", 2) == {"sort": "hits", "page": 2}
    assert browse_params("not-a-mode", 1) == {}
    assert search_params("玄幻", 1) == {"keyword": "玄幻"}


def test_genre_params_send_the_numeric_cid_and_reject_unknown_keys():
    assert genre_params("xuanhuan", 2) == {"page": 2, "cid": 25}
    assert genre_params("not-a-genre", 1) is None


# --- catalog parsing --------------------------------------------------------


def test_parse_browse_page_reads_every_card():
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    assert len(listing.items) == PAGE_SIZE
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "14109"
    assert first.title == "从姑获鸟开始"
    assert first.cover_url == "https://img.guazicdn.com/th/comics/cover/2345/260424/cover.webp"
    assert first.canonical_path == "/comic.php?id=14109"
    assert first.author == "之画文化"
    assert first.genres == ("穿越", "冒险")
    assert first.status == "连载"


def test_pager_gives_the_only_total_the_site_publishes():
    """No result count exists anywhere; the pager's last page is the source."""
    assert parse_last_page(_load("browse_page1.html")) == 631
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    assert listing.total == 631 * PAGE_SIZE


def test_genre_pager_survives_html_escaped_ampersands():
    """A filtered pager renders "?cid=25&amp;page=2"; a bare [?&] misses it."""
    assert parse_last_page(_load("genre.html")) == 20
    listing = parse_series_list(_load("genre.html"), page=1)
    assert listing.has_more is True


def test_page_two_is_a_different_slice():
    page1 = parse_series_list(_load("browse_page1.html"), page=1)
    page2 = parse_series_list(_load("browse_page2.html"), page=2)
    assert page2.items[0].id == "25018"
    assert {item.id for item in page1.items}.isdisjoint({item.id for item in page2.items})


def test_daily_sort_really_reorders_the_catalog():
    daily = parse_series_list(_load("browse_daily.html"), page=1)
    assert daily.items[0].id == "26470"
    assert daily.items[0].id != parse_series_list(_load("browse_page1.html"), page=1).items[0].id


def test_search_is_a_single_unpaginated_page():
    """``?keyword=&page=2`` comes back with zero cards, so has_more must be False."""
    listing = parse_series_list(_load("search.html"), page=1)
    assert len(listing.items) == 8
    assert listing.has_more is False
    assert any("玄幻" in item.title for item in listing.items)


# --- detail / chapters / reader ---------------------------------------------


def test_detail_prefers_the_pages_json_ld_over_its_rendered_chrome():
    series = parse_series_detail(_load("series_detail.html"), SERIES_KEY)
    assert series is not None
    assert series.id == SERIES_KEY
    assert series.title == "航海王"
    # The visible chrome shows author and genres as one "·"-joined string;
    # JSON-LD publishes them already split.
    assert series.author == "尾田荣一郎"
    assert series.genres == ("热血", "冒险", "奇幻", "爆笑")
    assert series.status == "连载"
    assert series.cover_url is not None and series.cover_url.startswith("https://img.guazicdn.com/")


def test_chapters_read_the_mobile_grid_which_is_the_only_complete_list():
    """The page's JSON-LD ItemList truncates at 50; the grid carries all 1,187."""
    chapters = parse_chapters(_load("series_detail.html"), SERIES_KEY)
    assert len(chapters) == 1187
    assert chapters[0].id == "906323"
    assert chapters[0].number == 1.0
    assert chapters[-1].number == 1190.0
    numbers = [chapter.number for chapter in chapters]
    assert numbers == sorted(numbers)
    assert all(chapter.series_id == SERIES_KEY for chapter in chapters)


def test_chapters_are_not_doubled_by_the_desktop_copy_of_the_same_list():
    """The document renders the chapter list twice; only one may be parsed."""
    html = _load("series_detail.html")
    assert html.count('href="/chapter.php?id=') > 2 * 1187 - 10
    assert len(parse_chapters(html, SERIES_KEY)) == 1187


def test_a_404_detail_page_parses_to_none():
    assert parse_series_detail(_load("missing_series.html"), SERIES_KEY) is None


def test_reader_pages_are_plain_img_tags_in_server_rendered_markup():
    pages = parse_chapter_pages(_load("chapter_reader.html"), CHAPTER_KEY)
    assert len(pages) == 18
    assert pages[0].id == f"{CHAPTER_KEY}:1"
    assert pages[0].remote_url == "https://img.guazicdn.com/th/comics/chapters/2508/260810/1191_1.webp"
    assert [page.number for page in pages] == list(range(1, 19))


# --- connector wiring -------------------------------------------------------


def test_image_host_allowlist_covers_the_separate_cdn_domain(
    connector: GuaziManhuaConnector,
):
    from services.outbound_security import host_matches_allowlist

    assert host_matches_allowlist("img.guazicdn.com", connector.allowed_image_hosts)
    assert not host_matches_allowlist("guazimanhua.com", connector.allowed_image_hosts)


def test_source_is_general_audience(connector: GuaziManhuaConnector):
    """The site publishes no adult section; its whole tag set is mainstream."""
    assert connector.is_mature is False


def test_the_cdn_needs_no_referer(connector: GuaziManhuaConnector):
    """Measured from the VPS: covers and page images answer 200 either way."""
    assert connector.image_fetch_headers() == {}


def test_detail_and_chapters_share_one_upstream_fetch(connector: GuaziManhuaConnector):
    with _mock_guazimanhua(connector):
        with patch.object(connector._http, "get_text", wraps=connector._http.get_text) as spy:
            connector.get_series(SERIES_KEY)
            connector.get_chapters(SERIES_KEY)
        assert spy.call_count == 1


def test_missing_series_is_none_rather_than_an_error(connector: GuaziManhuaConnector):
    with _mock_guazimanhua(connector):
        assert connector.get_series("99999999") is None
        assert connector.get_chapters("99999999") == []


def test_unknown_genre_answers_empty_without_a_request(connector: GuaziManhuaConnector):
    with patch.object(connector._http, "get_text", side_effect=AssertionError("no request")):
        listing = connector.browse_by_genre("not-a-genre", 1)
    assert listing.items == []
    assert listing.has_more is False


def test_connector_contract():
    validate_connector_contract(
        ConnectorContractCase(
            source_type="guazimanhua",
            fixtures_dir=FIXTURES,
            search_query="玄幻",
            series_id=SERIES_KEY,
            reader_chapter_id=CHAPTER_KEY,
            expected_title_substring="航海王",
            expected_image_host_substring="img.guazicdn.com",
            expected_latest_first_id="14109",
            expected_page2_first_id="25018",
            mock=_mock_guazimanhua,
        )
    )
