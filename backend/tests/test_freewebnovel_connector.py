"""Offline tests for the FreeWebNovel novel connector.

Fixtures under ``tests/fixtures/freewebnovel/`` were captured live 2026-09-04
FROM THE VPS (through production's exact egress and TLS stack — the probe
methodology in the novels spec §4). The connector is exercised entirely
against those captures by patching ``self._http``; no network.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.freewebnovel.connector import FreeWebNovelConnector, _is_not_found
from connectors.freewebnovel.mappers import (
    browse_path,
    chapter_number_from_key,
    chapter_path,
    normalize_chapter_key,
    normalize_series_key,
    parse_browse_page,
    parse_chapter_page,
    parse_novel_page,
    parse_search_results,
    search_params,
    series_path,
)
from connectors.http.client import ConnectorHttpError

FIXTURES = Path(__file__).parent / "fixtures" / "freewebnovel"

SERIES_KEY = "shadow-slave"
CHAPTER_KEY = "chapter-1"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- identity ---------------------------------------------------------------


def test_series_key_round_trips():
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(f"novel/{SERIES_KEY}") == SERIES_KEY
    assert normalize_series_key(f"/novel/{SERIES_KEY}/") == SERIES_KEY
    assert (
        normalize_series_key(f"https://freewebnovel.com/novel/{SERIES_KEY}")
        == SERIES_KEY
    )
    assert series_path(SERIES_KEY) == f"/novel/{SERIES_KEY}"


def test_chapter_key_round_trips():
    assert normalize_chapter_key(CHAPTER_KEY) == CHAPTER_KEY
    assert (
        normalize_chapter_key(f"novel/{SERIES_KEY}/{CHAPTER_KEY}") == CHAPTER_KEY
    )
    assert (
        chapter_path(SERIES_KEY, CHAPTER_KEY)
        == f"/novel/{SERIES_KEY}/{CHAPTER_KEY}"
    )
    # Full chapter URL normalizes down to the same path.
    assert (
        chapter_path(
            f"https://freewebnovel.com/novel/{SERIES_KEY}",
            f"https://freewebnovel.com/novel/{SERIES_KEY}/{CHAPTER_KEY}",
        )
        == f"/novel/{SERIES_KEY}/{CHAPTER_KEY}"
    )


def test_chapter_number_from_key():
    assert chapter_number_from_key("chapter-1") == 1.0
    assert chapter_number_from_key("chapter-1287") == 1287.0
    assert chapter_number_from_key("chapter-10.5") == 10.5
    assert chapter_number_from_key("not-a-chapter") is None


def test_browse_paths():
    assert browse_path(None, 1) == "/sort/latest-release"
    assert browse_path("default", 1) == "/sort/latest-release"
    assert browse_path("popular", 3) == "/sort/most-popular/3"
    assert browse_path("most-popular", 1) == "/sort/most-popular"
    assert browse_path("garbage", 2) == "/sort/latest-release/2"


def test_search_params_paginate_via_query():
    assert search_params("martial", 1) == {"keyword": "martial"}
    assert search_params("martial", 3) == {"keyword": "martial", "page": "3"}


# --- browse -----------------------------------------------------------------


def test_parse_browse_latest():
    listing = parse_browse_page(_load("browse_latest.html"), page=1)
    assert len(listing.items) == 20
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "becoming-a-god-starts-with-acting"
    assert first.title == "Becoming a God Starts with Acting"
    assert first.cover_url and first.cover_url.startswith("https://freewebnovel.com/")
    assert "Fantasy" in first.genres
    assert first.latest_chapter == "chapter-580"
    # Every card parsed a slug id and a non-empty title.
    assert all(row.id and row.title for row in listing.items)


def test_parse_browse_popular_page_two():
    listing = parse_browse_page(_load("browse_popular_p2.html"), page=2)
    assert len(listing.items) == 20
    assert listing.has_more is True
    assert listing.page == 2
    assert listing.items[0].id == "the-sovereigns-ascension"


def test_browse_last_page_reports_no_more():
    # Minimal real-shaped pager: current page 3, only earlier pages linked.
    html = (
        '<div class="li-row"><h3 class="tit">'
        '<a href="/novel/some-novel" title="Some Novel">Some Novel</a></h3></div>'
        '<div class="pages"><a href="/sort/latest-release/2">2</a>'
        "<strong>3</strong></div>"
    )
    listing = parse_browse_page(html, page=3)
    assert len(listing.items) == 1
    assert listing.has_more is False


# --- search -----------------------------------------------------------------


def test_parse_search_page_one_has_more():
    listing = parse_search_results(_load("search_martial_p1.html"), page=1)
    assert len(listing.items) == 20
    # Query-style pager links (&page=N) must be seen by has_more.
    assert listing.has_more is True
    assert listing.items[0].id == "martial-dao-i-can-enhance-my-talents"
    assert listing.items[0].title == "Martial Dao: I Can Enhance My Talents"


def test_parse_search_page_two_is_distinct_and_paginated():
    p1 = parse_search_results(_load("search_martial_p1.html"), page=1)
    p2 = parse_search_results(_load("search_martial_p2.html"), page=2)
    assert len(p2.items) == 20
    assert p2.has_more is True
    assert p2.items[0].id == "martial-arts-master"
    assert not ({row.id for row in p1.items} & {row.id for row in p2.items})


def test_search_without_pager_reports_no_more():
    html = (
        '<div class="li-row"><h3 class="tit">'
        '<a href="/novel/only-hit" title="Only Hit">Only Hit</a></h3></div>'
    )
    listing = parse_search_results(html, page=1)
    assert len(listing.items) == 1
    assert listing.has_more is False


# --- novel detail -----------------------------------------------------------


def test_parse_novel_page_metadata():
    series, chapters = parse_novel_page(_load("novel_shadow_slave.html"), SERIES_KEY)
    assert series is not None
    assert series.id == SERIES_KEY
    assert series.title == "Shadow Slave"
    assert series.author == "Guiltythree"
    assert series.status == "ongoing"
    # Cover must be the og:image novel cover, never the site logo (the logo
    # is the first <img> on the page).
    assert series.cover_url == "https://freewebnovel.com/files/article/image/1/1991/1991s.jpg"
    assert "logo" not in series.cover_url
    # Genres come from the info block's own Genre row, NOT the header nav
    # that links all ~38 site genres.
    assert series.genres == ("Action", "Adventure", "Fantasy", "Romance")
    assert series.description and "Sunny" in series.description
    assert "<" not in series.description  # sanitized plain text
    assert series.chapter_count == len(chapters)


def test_parse_novel_page_synthesizes_full_chapter_list():
    _, chapters = parse_novel_page(_load("novel_shadow_slave.html"), SERIES_KEY)
    # The page shows the first 40 titles + the newest strip; URLs are
    # uniformly /novel/<slug>/chapter-<n>, so the list runs 1..newest.
    assert len(chapters) == 3173
    assert chapters[0].id == "chapter-1"
    assert chapters[0].title == "Chapter 1: Nightmare Begins"
    assert chapters[0].number == 1.0
    assert chapters[39].title == "Chapter 40: Weak Point"  # last real title
    assert chapters[40].title == "Chapter 41"  # synthesized filler
    assert chapters[-1].id == "chapter-3173"
    assert chapters[-1].title == "Chapter 3173 Life Goes On"  # newest strip
    assert [c.number for c in chapters[:3]] == [1.0, 2.0, 3.0]
    assert all(c.series_id == SERIES_KEY for c in chapters[:5])


def test_parse_novel_page_without_title_is_none():
    assert parse_novel_page("<html><body>nope</body></html>", SERIES_KEY) == (None, [])


# --- chapter text -----------------------------------------------------------


def test_parse_chapter_page():
    text = parse_chapter_page(_load("chapter_shadow_slave_1.html"), CHAPTER_KEY)
    assert text is not None
    assert text.title == "Chapter 1: Nightmare Begins"
    assert text.chapter_number == 1.0
    assert len(text.paragraphs) == 91
    assert text.word_count > 1500
    assert text.paragraphs[0].startswith("A frail-looking young man")
    # The article body's leading <h4> duplicate of the title is dropped.
    assert text.paragraphs[0] != text.title


def test_chapter_paragraphs_are_sanitized_plain_text():
    text = parse_chapter_page(_load("chapter_shadow_slave_1.html"), CHAPTER_KEY)
    joined = " ".join(text.paragraphs).lower()
    for junk in ("freewebnovel", "<div", "<p", "<script", "adsbygoogle", "http"):
        assert junk not in joined, junk


def test_chapter_junk_stripping():
    """FreeWebNovel-shaped junk: ad-slot divs between paragraphs, scripts,
    visible self-promo watermark lines (plain and homoglyph-obfuscated)."""
    html = (
        '<html><head><title>x</title></head><body><div id="article">'
        "<h4>Chapter 9: The Test</h4>"
        "<p>Sunny walked into the shadows.</p>"
        '<div class="ad-slot"><ins class="adsbygoogle"></ins>BUY GOLD</div>'
        "<script>evil();</script>"
        "<p>Read the latest chapters at FreeWebNovel.com only.</p>"
        "<p>This content is taken from freewebnovel&#46;com</p>"
        "<p>Updated by NovelBin.com</p>"
        "<p>Follow new novels on frᴇᴇwᴇbnovᴇl.cоm</p>"
        "<p>The shadows walked back.</p>"
        "</div></body></html>"
    )
    text = parse_chapter_page(html, "chapter-9")
    assert text is not None
    assert text.title == ""  # no <span class="chapter"> in the snippet
    assert text.paragraphs == (
        "Chapter 9: The Test",  # kept: no span title to dedupe against
        "Sunny walked into the shadows.",
        "The shadows walked back.",
    )


def test_chapter_leading_title_duplicate_dropped():
    html = (
        '<span class="chapter">Chapter 9: The Test</span>'
        '<div id="article"><h4>Chapter 9: The Test</h4>'
        "<p>Actual story text follows here.</p></div>"
    )
    text = parse_chapter_page(html, "chapter-9")
    assert text.title == "Chapter 9: The Test"
    assert text.paragraphs == ("Actual story text follows here.",)


def test_chapter_without_article_is_none():
    assert parse_chapter_page("<html><body>404</body></html>", CHAPTER_KEY) is None


def test_chapter_with_only_junk_is_none():
    html = '<div id="article"><p>Read the latest chapters at FreeWebNovel.com</p></div>'
    assert parse_chapter_page(html, CHAPTER_KEY) is None


# --- connector behavior (patched HTTP) --------------------------------------


@pytest.fixture()
def connector() -> FreeWebNovelConnector:
    return FreeWebNovelConnector()


def test_connector_declares_novel_kind(connector):
    assert connector.source_type == "freewebnovel"
    assert connector.content_kind == "novel"
    assert connector.CONTENT_KIND == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.is_mature is False
    assert "freewebnovel.com" in connector.allowed_image_hosts


def test_connector_series_and_chapters_share_one_fetch(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("novel_shadow_slave.html")
    ) as get_text:
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)
    assert get_text.call_count == 1  # detail page cached across both calls
    assert get_text.call_args.args[0] == f"/novel/{SERIES_KEY}"
    assert series.title == "Shadow Slave"
    assert len(chapters) == 3173


def test_connector_search_uses_get_with_page_param(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("search_martial_p2.html")
    ) as get_text:
        listing = connector.search_series("martial", 2)
    assert get_text.call_args.args[0] == "/search"
    assert get_text.call_args.kwargs["params"] == {"keyword": "martial", "page": "2"}
    assert len(listing.items) == 20


def test_connector_empty_search_falls_back_to_browse(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("browse_latest.html")
    ) as get_text:
        listing = connector.search_series("   ", 1)
    assert get_text.call_args.args[0] == "/sort/latest-release"
    assert len(listing.items) == 20


def test_connector_chapter_text(connector):
    with patch.object(
        connector._http,
        "get_text",
        return_value=_load("chapter_shadow_slave_1.html"),
    ) as get_text:
        text = connector.chapter_text(SERIES_KEY, CHAPTER_KEY)
    assert get_text.call_args.args[0] == f"/novel/{SERIES_KEY}/{CHAPTER_KEY}"
    assert text.title == "Chapter 1: Nightmare Begins"
    assert text.chapter_number == 1.0
    assert len(text.paragraphs) == 91


def test_connector_manga_surface_is_empty(connector):
    assert connector.get_chapter_pages("chapter-1") == []
    assert connector.find_page("anything") is None


# --- 404 vs network failure (verified live from the VPS) --------------------

# The shared client only sets status_code for RETRYABLE_STATUS; a 404
# surfaces as httpx's raise_for_status message. Both forms must count.
_NOT_FOUND = ConnectorHttpError(
    "Client error '404 Not Found' for url "
    "'https://freewebnovel.com/novel/shadow-slave/chapter-999999'\n"
    "For more information check: https://developer.mozilla.org/..."
)


def test_is_not_found_matches_both_forms():
    assert _is_not_found(_NOT_FOUND) is True
    assert _is_not_found(ConnectorHttpError("gone", status_code=404)) is True
    assert _is_not_found(ConnectorHttpError("Retryable HTTP 503", status_code=503)) is False
    assert _is_not_found(ConnectorHttpError("connection reset")) is False


def test_chapter_text_missing_chapter_is_none(connector):
    with patch.object(connector._http, "get_text", side_effect=_NOT_FOUND):
        assert connector.chapter_text(SERIES_KEY, "chapter-999999") is None


def test_chapter_text_network_failure_raises(connector):
    err = ConnectorHttpError("Retryable HTTP 503", status_code=503)
    with patch.object(connector._http, "get_text", side_effect=err):
        with pytest.raises(ConnectorHttpError):
            connector.chapter_text(SERIES_KEY, CHAPTER_KEY)


def test_missing_series_is_none(connector):
    with patch.object(connector._http, "get_text", side_effect=_NOT_FOUND):
        assert connector.get_series("zz-definitely-not-real-xyz") is None
        assert connector.get_chapters("zz-definitely-not-real-xyz") == []


def test_chapter_text_rejects_non_english(connector):
    cjk = "".join(chr(0x4E00 + i) for i in range(80))
    html = f'<div id="article"><p>{cjk}</p></div>'
    with patch.object(connector._http, "get_text", return_value=html):
        assert connector.chapter_text(SERIES_KEY, CHAPTER_KEY) is None
