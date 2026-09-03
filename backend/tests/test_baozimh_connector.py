from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.baozimh.connector import BaoZiMHConnector
from connectors.baozimh.mappers import COVER_BASE, PAGE_SIZE


FIXTURES = Path(__file__).parent / "fixtures" / "baozimh"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def baozimh_connector() -> BaoZiMHConnector:
    return BaoZiMHConnector()


def test_list_series_uses_amp_comic_list_api(baozimh_connector: BaoZiMHConnector):
    payload = _load_json("comic_list.json")

    with patch.object(baozimh_connector._http, "get_json", return_value=payload) as mock_get:
        listing = baozimh_connector.get_series_list(1, sort="latest")

    mock_get.assert_called_once_with(
        "/api/bzmhq/amp_comic_list",
        params={
            "type": "all",
            "region": "all",
            "state": "all",
            "filter": "*",
            "page": 1,
            "limit": PAGE_SIZE,
            "language": "tw",
        },
    )
    assert len(listing.items) == 2
    assert listing.items[0].id == "wuliandianfeng-pikapi"
    assert listing.items[0].title == "武煉巔峰"
    assert listing.items[0].cover_url == f"{COVER_BASE}/wuliandianfeng-pikapi.jpg"
    assert listing.has_more is True


def test_browse_ongoing_and_genre_filters(baozimh_connector: BaoZiMHConnector):
    payload = _load_json("comic_list.json")

    with patch.object(baozimh_connector._http, "get_json", return_value=payload) as mock_get:
        baozimh_connector.get_series_list(2, sort="serial")
        baozimh_connector.browse_by_genre("lianai", 1, sort="completed")

    assert mock_get.call_args_list[0].kwargs["params"]["state"] == "serial"
    assert mock_get.call_args_list[0].kwargs["params"]["page"] == 2
    assert mock_get.call_args_list[1].kwargs["params"]["type"] == "lianai"
    assert mock_get.call_args_list[1].kwargs["params"]["state"] == "pub"


def test_search_series_parses_html_cards(baozimh_connector: BaoZiMHConnector):
    html = _load_html("search_listing.html")

    with patch.object(baozimh_connector._http, "get_text", return_value=html) as mock_get:
        listing = baozimh_connector.search_series("妖", 1)

    mock_get.assert_called_once_with("/search", params={"q": "妖"})
    assert len(listing.items) == 3
    assert listing.items[0].id == "yaolinushen-liudaoshenshi"
    assert listing.items[0].title == "妖力女神"
    assert listing.has_more is False


def test_get_series_and_chapters(baozimh_connector: BaoZiMHConnector):
    html = _load_html("comic_detail.html")
    comic_id = "yaoshenji-taxuedongman"

    with patch.object(baozimh_connector._http, "get_text", return_value=html):
        series = baozimh_connector.get_series(comic_id)
        chapters = baozimh_connector.get_chapters(comic_id)

    assert series is not None
    assert series.title == "妖神記"
    assert series.author == "踏雪動漫"
    assert series.status == "ongoing"
    assert "熱血" in series.genres
    assert series.chapter_count == 4
    assert len(chapters) == 4
    assert chapters[0].id == f"{comic_id}/0_968"
    assert chapters[0].title == "第522話 噬魂泥（下）"
    assert chapters[-1].id == f"{comic_id}/0_0"


def test_chapter_pages(baozimh_connector: BaoZiMHConnector):
    html = _load_html("chapter_pages.html")
    chapter_id = "yaoshenji-taxuedongman/0_0"

    with patch.object(baozimh_connector._http, "get_text", return_value=html) as mock_get:
        pages = baozimh_connector.get_chapter_pages(chapter_id)

    mock_get.assert_called_once_with(
        "/user/page_direct?comic_id=yaoshenji-taxuedongman&section_slot=0&chapter_slot=0"
    )
    assert len(pages) == 5
    assert pages[0].number == 1
    assert pages[0].remote_url.endswith("/1.jpg")
    assert baozimh_connector.find_page(pages[0].id) == pages[0]


def test_chapter_pages_rehosted_off_dead_bzcdn(baozimh_connector: BaoZiMHConnector):
    """Regression: s<N>.bzcdn.net refuses connections; rehost onto static-tw.

    The reader markup still emits bzcdn.net page URLs (the fixture is real
    markup and proves it), but that CDN rejects TCP on :443, so every page
    parsed straight out of the HTML was unfetchable. Pages must come back
    pointing at the operator's static host, with the path untouched.
    """
    html = _load_html("chapter_pages.html")
    assert "https://s1.bzcdn.net/" in html  # upstream really still serves this

    with patch.object(baozimh_connector._http, "get_text", return_value=html):
        pages = baozimh_connector.get_chapter_pages("yaoshenji-taxuedongman/0_0")

    assert pages
    assert all(
        (p.remote_url or "").startswith("https://static-tw.baozimh.com/") for p in pages
    )
    assert not any("bzcdn.net" in (p.remote_url or "") for p in pages)
    # the path after the host must survive the rewrite verbatim
    assert pages[0].remote_url.endswith("/1.jpg")
    original_path = re.search(r"https://s1\.bzcdn\.net(/\S+?/1\.jpg)", html).group(1)
    assert pages[0].remote_url == f"https://static-tw.baozimh.com{original_path}"


def test_reader_redirect_to_twmanga_is_permitted(baozimh_connector: BaoZiMHConnector):
    """Regression: chapter URLs 302 to the twmanga.com reader.

    The SSRF redirect guard allows only the source's own domain by default,
    which aborted every chapter fetch ("Redirect blocked") and left the source
    listing thousands of chapters it could not open. twmanga.com is declared
    explicitly; anything else must still be refused.
    """
    from connectors.http.redirect_policy import redirect_rejection_reason

    allowed = baozimh_connector._http._redirect_hosts

    assert redirect_rejection_reason("https://www.twmanga.com/comic/chapter/x", allowed) is None
    assert redirect_rejection_reason("https://baozimh.com/comic/x", allowed) is None
    assert redirect_rejection_reason("https://evil.example.com/x", allowed) is not None
    # a lookalike must not slip through on a suffix match
    assert redirect_rejection_reason("https://nottwmanga.com/x", allowed) is not None


def test_allowed_image_hosts(baozimh_connector: BaoZiMHConnector):
    hosts = baozimh_connector.allowed_image_hosts
    assert "bzcdn.net" in hosts
    assert "static-tw.baozimh.com" in hosts
    assert baozimh_connector.image_fetch_headers()["Referer"] == "https://www.twmanga.com/"
