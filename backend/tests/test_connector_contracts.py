from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.base import SourceConnector
from tests.connector_validation import ConnectorContractCase, validate_connector_contract


ROOT = Path(__file__).parent / "fixtures"


@contextmanager
def _mock_asurascans(connector: SourceConnector):
    fixtures = ROOT / "asurascans"
    series_list = (fixtures / "series_list.json").read_text(encoding="utf-8")
    series_search = (fixtures / "series_search.json").read_text(encoding="utf-8")
    series_detail = (fixtures / "series_detail.json").read_text(encoding="utf-8")
    chapter_list = (fixtures / "chapter_list.json").read_text(encoding="utf-8")
    chapter_pages = (fixtures / "chapter_pages.json").read_text(encoding="utf-8")

    import json

    series_list_payload = json.loads(series_list)
    series_search_payload = json.loads(series_search)
    series_detail_payload = json.loads(series_detail)
    chapter_list_payload = json.loads(chapter_list)
    chapter_pages_payload = json.loads(chapter_pages)

    series_id = "return-of-the-mount-hua-sect-30e93729"

    def fake_get_json(path: str, *, params=None):
        if path == "/api/series":
            if params and params.get("search"):
                return series_search_payload
            return series_list_payload
        if path == f"/api/series/{series_id}":
            return series_detail_payload
        if path == f"/api/series/{series_id}/chapters":
            return chapter_list_payload
        if path == "/api/series/breakers-30e93729/chapters/91":
            return chapter_pages_payload
        raise AssertionError(f"Unexpected path: {path}")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        yield


@contextmanager
def _mock_mangadex(connector: SourceConnector):
    fixtures = ROOT / "mangadex"
    import json

    manga_list_payload = json.loads((fixtures / "manga_list.json").read_text(encoding="utf-8"))
    manga_search_payload = json.loads((fixtures / "manga_search.json").read_text(encoding="utf-8"))
    manga_detail_payload = json.loads((fixtures / "manga_detail.json").read_text(encoding="utf-8"))
    feed_payload = json.loads((fixtures / "chapter_feed_decimal.json").read_text(encoding="utf-8"))
    at_home_payload = json.loads((fixtures / "at_home.json").read_text(encoding="utf-8"))

    series_id = "32dce569-8fcc-46b6-853c-f956e16ee0bc"

    def fake_get_json(path: str, *, params=None):
        if path == "/manga":
            if params and params.get("title"):
                return manga_search_payload
            return manga_list_payload
        if path == f"/manga/{series_id}":
            return manga_detail_payload
        if path.endswith("/feed"):
            return feed_payload
        if path.startswith("/at-home/server/"):
            return at_home_payload
        raise AssertionError(f"Unexpected path: {path}")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        yield


@contextmanager
def _mock_mangakatana(connector: SourceConnector):
    fixtures = ROOT / "mangakatana"

    browse_page1 = (fixtures / "browse_page1.html").read_text(encoding="utf-8")
    browse_page2 = (fixtures / "browse_page2.html").read_text(encoding="utf-8")
    browse_order_latest = (fixtures / "browse_order_latest.html").read_text(encoding="utf-8")
    browse_order_numc = (fixtures / "browse_order_numc.html").read_text(encoding="utf-8")
    search = (fixtures / "search_solo.html").read_text(encoding="utf-8")
    series_detail = (fixtures / "series_detail.html").read_text(encoding="utf-8")
    chapter_reader = (fixtures / "chapter_reader.html").read_text(encoding="utf-8")

    series_id = "aishiteru-uso-dakedo.10797"
    chapter_id = f"{series_id}/c1"

    def fake_get_text(path: str, *, params=None):
        if path.endswith("/page/2"):
            return browse_page2
        if path == "/":
            return search
        if path.startswith("/manga/page/"):
            # Contract calls default + popular; popular should differ.
            if params and params.get("order") == "numc":
                return browse_order_numc
            if params and params.get("order") == "latest":
                return browse_order_latest
            return browse_page1
        if path == f"/manga/{series_id}":
            return series_detail
        if path == f"/manga/{chapter_id}":
            return chapter_reader
        return browse_page1

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        yield


@contextmanager
def _mock_toonily(connector: SourceConnector):
    fixtures = ROOT / "toonily"

    browse_latest = (fixtures / "browse_latest.html").read_text(encoding="utf-8")
    browse_popular = (fixtures / "browse_popular.html").read_text(encoding="utf-8")
    browse_page2 = (fixtures / "browse_page2.html").read_text(encoding="utf-8")
    search = (fixtures / "search_solo.html").read_text(encoding="utf-8")
    series_detail = (fixtures / "series_detail.html").read_text(encoding="utf-8")
    chapter_reader = (fixtures / "chapter_reader.html").read_text(encoding="utf-8")

    series_id = "the-beginning-after-the-end-7b1d8c89"
    chapter_id = f"{series_id}/chapter-240"

    def fake_get_text(path: str, *, params=None):
        if path.endswith("/page/2/"):
            return browse_page2
        if path == "/":
            return search
        if path.startswith("/webtoons/"):
            if params and params.get("m_orderby") == "views":
                return browse_popular
            return browse_latest
        if path == f"/serie/{series_id}/":
            return series_detail
        if path == f"/serie/{chapter_id}/":
            return chapter_reader
        return browse_latest

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        yield


@contextmanager
def _mock_demonicscans(connector: SourceConnector):
    fixtures = ROOT / "demonicscans"

    latest = (fixtures / "browse_latest.html").read_text(encoding="utf-8")
    latest_page2 = (fixtures / "browse_page2.html").read_text(encoding="utf-8")
    popular = (fixtures / "browse_popular.html").read_text(encoding="utf-8")
    advanced = (fixtures / "search_advanced.html").read_text(encoding="utf-8")
    # Real /search.php?manga=demons response. search_series stopped scanning
    # /advanced.php and now asks the site's own search endpoint.
    search = (fixtures / "search_demons.html").read_text(encoding="utf-8")
    series_detail = (fixtures / "series_detail.html").read_text(encoding="utf-8")
    chapter_reader = (fixtures / "chapter_reader.html").read_text(encoding="utf-8")

    def fake_get_text(path: str, *, params=None):
        if path == "/search.php":
            return search
        if path == "/lastupdates.php?list=2":
            return latest
        if path == "/lastupdates.php?list=3":
            return latest_page2
        if path == "/":
            return popular
        if path == "/advanced.php?list=2":
            return advanced
        if path.startswith("/manga/"):
            return series_detail
        if path.startswith("/title/"):
            return chapter_reader
        return latest

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        yield


@contextmanager
def _mock_coffeemanga(connector: SourceConnector):
    fixtures = ROOT / "coffeemanga"

    browse_latest = (fixtures / "browse_latest.html").read_text(encoding="utf-8")
    browse_popular = (fixtures / "browse_popular.html").read_text(encoding="utf-8")
    browse_page2 = (fixtures / "browse_page2.html").read_text(encoding="utf-8")
    search = (fixtures / "search.html").read_text(encoding="utf-8")
    series_detail = (fixtures / "series_detail.html").read_text(encoding="utf-8")
    chapter_reader = (fixtures / "chapter_reader.html").read_text(encoding="utf-8")

    series_id = "the-abandoned-princes-ghost-bride"
    chapter_id = f"{series_id}/chapter-1"

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search
        if path == f"/manga/{series_id}/":
            return series_detail
        if path == f"/manga/{chapter_id}/":
            return chapter_reader
        if path.startswith("/manga/page/2"):
            return browse_page2
        if path.startswith("/manga"):
            if params and params.get("m_orderby") == "views":
                return browse_popular
            return browse_latest
        return browse_latest

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        yield


CASES: list[ConnectorContractCase] = [
    ConnectorContractCase(
        source_type="asurascans",
        fixtures_dir=ROOT / "asurascans",
        search_query="solo",
        series_id="return-of-the-mount-hua-sect-30e93729",
        reader_chapter_id="breakers-30e93729:91",
        expected_title_substring="Mount Hua",
        expected_image_host_substring="asura",
        ordering_probe_ids=("return-of-the-mount-hua-sect-30e93729:1", "return-of-the-mount-hua-sect-30e93729:2"),
        adjacent_pairs=(
            ("return-of-the-mount-hua-sect-30e93729:1", "return-of-the-mount-hua-sect-30e93729:2"),
        ),
        mock=_mock_asurascans,
    ),
    ConnectorContractCase(
        source_type="mangadex",
        fixtures_dir=ROOT / "mangadex",
        search_query="Solo",
        series_id="32dce569-8fcc-46b6-853c-f956e16ee0bc",
        reader_chapter_id="00000000-0000-0000-0000-000000000001",
        expected_title_substring="Solo Leveling",
        expected_image_host_substring="mangadex",
        decimal_chapter_ids=("00000000-0000-0000-0000-000000000002",),
        ordering_probe_ids=(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ),
        adjacent_pairs=(
            ("00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"),
        ),
        mock=_mock_mangadex,
    ),
    ConnectorContractCase(
        source_type="mangakatana",
        fixtures_dir=ROOT / "mangakatana",
        search_query="solo",
        series_id="aishiteru-uso-dakedo.10797",
        reader_chapter_id="aishiteru-uso-dakedo.10797/c1",
        expected_title_substring="Aishiteru",
        expected_image_host_substring="mangakatana.com",
        expected_latest_first_id="kuroneko-to-majo-no-kyoushitsu.26203",
        expected_popular_first_id="martial-peak.20405",
        expected_page2_first_id="kakegurui.1388",
        expected_search_ids=("solo-leveling.21708",),
        mock=_mock_mangakatana,
    ),
    ConnectorContractCase(
        source_type="toonily",
        fixtures_dir=ROOT / "toonily",
        search_query="solo",
        series_id="the-beginning-after-the-end-7b1d8c89",
        reader_chapter_id="the-beginning-after-the-end-7b1d8c89/chapter-240",
        expected_title_substring="Beginning After the End",
        expected_image_host_substring="tnlycdn.com",
        expected_latest_first_id="the-beginning-after-the-end-7b1d8c89",
        expected_popular_first_id="omniscient-reader-kk11",
        expected_page2_first_id="solo-leveling-ab12cd34",
        expected_search_ids=("solo-leveling-ab12cd34",),
        decimal_chapter_ids=(
            "the-beginning-after-the-end-7b1d8c89/chapter-175-8",
        ),
        ordering_probe_ids=(
            "the-beginning-after-the-end-7b1d8c89/chapter-175-8",
            "the-beginning-after-the-end-7b1d8c89/chapter-175-8_1",
            "the-beginning-after-the-end-7b1d8c89/chapter-175-8_2",
            "the-beginning-after-the-end-7b1d8c89/chapter-175-8_11",
            "the-beginning-after-the-end-7b1d8c89/chapter-175-9",
        ),
        adjacent_pairs=(
            (
                "the-beginning-after-the-end-7b1d8c89/chapter-175-8",
                "the-beginning-after-the-end-7b1d8c89/chapter-175-8_1",
            ),
            (
                "the-beginning-after-the-end-7b1d8c89/chapter-175-8_1",
                "the-beginning-after-the-end-7b1d8c89/chapter-175-8_2",
            ),
        ),
        mock=_mock_toonily,
    ),
    ConnectorContractCase(
        source_type="demonicscans",
        fixtures_dir=ROOT / "demonicscans",
        search_query="demons",
        series_id="Tales-of-Demons-and-Gods",
        reader_chapter_id="Tales-of-Demons-and-Gods:522.1",
        expected_title_substring="Tales of Demons and Gods",
        expected_image_host_substring="demoniclibs.com",
        expected_latest_first_id="Tales-of-Demons-and-Gods",
        expected_popular_first_id="Pick-Me-Up",
        expected_page2_first_id="Some-Other-Series",
        expected_search_ids=("Tales-of-Demons-and-Gods",),
        decimal_chapter_ids=("Tales-of-Demons-and-Gods:522.1",),
        ordering_probe_ids=("Tales-of-Demons-and-Gods:521.1", "Tales-of-Demons-and-Gods:521.6", "Tales-of-Demons-and-Gods:522.1"),
        adjacent_pairs=(("Tales-of-Demons-and-Gods:521.6", "Tales-of-Demons-and-Gods:522.1"),),
        mock=lambda c: _mock_demonicscans(c),
    ),
    ConnectorContractCase(
        source_type="coffeemanga",
        fixtures_dir=ROOT / "coffeemanga",
        search_query="abandoned",
        series_id="the-abandoned-princes-ghost-bride",
        reader_chapter_id="the-abandoned-princes-ghost-bride/chapter-1",
        expected_title_substring="Abandoned Prince",
        expected_image_host_substring="coffeemanga.ink",
        expected_latest_first_id="the-abandoned-princes-ghost-bride",
        expected_popular_first_id="solo-leveling-cf01",
        expected_page2_first_id="tower-of-god-cf02",
        expected_search_ids=("the-abandoned-princes-ghost-bride",),
        decimal_chapter_ids=("the-abandoned-princes-ghost-bride/chapter-10-5",),
        ordering_probe_ids=(
            "the-abandoned-princes-ghost-bride/chapter-10",
            "the-abandoned-princes-ghost-bride/chapter-10-5",
            "the-abandoned-princes-ghost-bride/chapter-11",
        ),
        adjacent_pairs=(
            (
                "the-abandoned-princes-ghost-bride/chapter-10",
                "the-abandoned-princes-ghost-bride/chapter-10-5",
            ),
            (
                "the-abandoned-princes-ghost-bride/chapter-10-5",
                "the-abandoned-princes-ghost-bride/chapter-11",
            ),
        ),
        mock=_mock_coffeemanga,
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[case.source_type for case in CASES])
def test_connector_contract(case: ConnectorContractCase) -> None:
    # The contract exercises the live registry, so a deregistered source has
    # nothing to instantiate. Its fixtures and parser tests stay put — this
    # skips only the registry-dependent half.
    from connectors.excluded import EXCLUDED_CONNECTORS

    if case.source_type in EXCLUDED_CONNECTORS:
        pytest.skip(f"{case.source_type} is deregistered (see connectors/excluded.py)")
    validate_connector_contract(case)

