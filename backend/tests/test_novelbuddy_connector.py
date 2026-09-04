"""Offline tests for the NovelBuddy novel connector.

Fixtures under ``tests/fixtures/novelbuddy/`` are live responses captured
2026-09-04 FROM THE VPS (production's exact egress and TLS stack — the probe
methodology in the novels spec §4). Nothing here touches the network; the
connector runs against those captures with ``self._http.get_json`` patched.

What the captures are, and why each one is here:

* ``browse_views.json`` / ``browse_views_page2.json`` — the default browse
  view (``sort=views``), pages 1 and 2. Two pages because the pagination
  assertions pin ``has_next`` handoff across them.
* ``search_sword.json`` — the same endpoint narrowed by ``q``.
* ``search_no_results.json`` — a real zero-hit search: ``200`` with an empty
  ``items`` array and ``has_next: false``. There is no error status to match
  on; the envelope IS the answer.
* ``title.json`` — ``/titles/<hsid>``, whose embedded ``chapters`` array is
  TRUNCATED to 50 of the title's 268. That truncation is the whole reason
  ``get_chapters`` uses the dedicated endpoint instead.
* ``chapters.json`` — ``/titles/<hsid>/chapters?limit=500``, all 268
  chapters in one response, newest-first.
* ``chapter.json`` — one chapter, whose ``content`` opens by repeating its
  own title and closes with an empty ad-slot ``<div>``.
* ``title_bad_sqid.json`` — the ``400`` body the API returns for an
  identifier that is not a Sqid.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.models import PaginatedSeriesList
from connectors.novelbuddy.connector import NovelBuddyConnector
from connectors.novelbuddy.mappers import (
    CHAPTER_LIMIT,
    browse_params,
    chapter_path,
    chapters_path,
    is_site_promo_line,
    normalize_chapter_key,
    normalize_series_key,
    parse_chapter,
    parse_chapters,
    parse_title,
    parse_title_list,
    series_hsid,
    series_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "novelbuddy"

SERIES_KEY = "LDgamG8v/world-evolution-apocalypse-i-possess-the-extraction-ability"
CHAPTER_KEY = "2Wz6RLKD/chapter-1-unlucky-day"
SERIES_CHAPTER_TOTAL = 268


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- identity ---------------------------------------------------------------


def test_series_key_contains_a_slash_and_round_trips():
    """House law: keys are opaque, may contain slashes, and pass through raw."""
    assert "/" in SERIES_KEY
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert (
        normalize_series_key(f"https://novelbuddy.me/{SERIES_KEY}") == SERIES_KEY
    )
    assert normalize_series_key(f"  /{SERIES_KEY}/  ") == SERIES_KEY


def test_series_key_addresses_the_api_by_its_hsid_half_only():
    """The API validates the path segment as a Sqid; the slug half is ours."""
    assert series_hsid(SERIES_KEY) == "LDgamG8v"
    assert series_path(SERIES_KEY) == "/titles/LDgamG8v"
    assert chapters_path(SERIES_KEY) == "/titles/LDgamG8v/chapters"
    assert chapter_path(SERIES_KEY, CHAPTER_KEY) == (
        "/titles/LDgamG8v/chapters/2Wz6RLKD"
    )


def test_chapter_key_round_trips_and_drops_the_series_half_of_a_url():
    assert normalize_chapter_key(CHAPTER_KEY) == CHAPTER_KEY
    # A site chapter URL is /<series slug>/<chapter slug>: the series half is
    # not part of a chapter key.
    assert (
        normalize_chapter_key(
            "https://novelbuddy.me/world-evolution-apocalypse/chapter-1-unlucky-day"
        )
        == "chapter-1-unlucky-day"
    )


# --- browse / search --------------------------------------------------------


def test_browse_params_omit_an_empty_query_entirely():
    """An empty ``q`` is a 400 upstream ("must be between 1 and 200
    characters"), so a browse must omit the parameter rather than blank it."""
    params = browse_params(None, 1, None)
    assert "q" not in params
    assert params["sort"] == "views"
    assert params["page"] == 1


def test_browse_params_allowlist_sorts_and_clip_long_queries():
    assert browse_params(None, 2, "trending")["sort"] == "views_7days"
    assert browse_params(None, 1, "latest")["sort"] == "latest"
    # An unknown sort is a 400 upstream, so it must never be forwarded.
    assert browse_params(None, 1, "wharrgarbl")["sort"] == "views"
    # A search is relevance-ordered; sort is not sent with a query.
    long_query = "x" * 500
    searched = browse_params(long_query, 1, "views")
    assert "sort" not in searched
    assert len(searched["q"]) == 200


def test_parse_browse_page():
    listing = parse_title_list(_load("browse_views.json"), page=1)
    assert len(listing.items) == 20
    assert listing.page_size == 20
    assert listing.total > 1000
    assert listing.has_more is True
    first = listing.items[0]
    assert "/" in first.id
    assert first.title
    assert first.chapter_count > 0
    assert first.cover_url and first.cover_url.startswith("https://")
    assert first.genres


def test_parse_browse_page_two_is_a_different_set():
    page1 = parse_title_list(_load("browse_views.json"), page=1)
    page2 = parse_title_list(_load("browse_views_page2.json"), page=2)
    assert page2.page == 2
    assert page2.has_more is True
    assert {item.id for item in page1.items}.isdisjoint(
        {item.id for item in page2.items}
    )


def test_parse_search_page():
    listing = parse_title_list(_load("search_sword.json"), page=1)
    assert len(listing.items) == 20
    assert all(item.id and item.title for item in listing.items)
    # Summaries arrive as HTML and must be stored as the same plain text
    # chapters are — no markup ever reaches a client.
    described = [item for item in listing.items if item.description]
    assert described
    assert not any("<p>" in (item.description or "") for item in described)


def test_zero_hit_search_is_an_empty_listing_not_an_error():
    listing = parse_title_list(_load("search_no_results.json"), page=1)
    assert listing.items == []
    assert listing.total == 0
    assert listing.has_more is False


def test_listing_drops_obviously_broken_rows():
    """House law: a row with no id, no title, or no readable chapter at all
    never reaches clients."""
    payload = {
        "data": {
            "items": [
                {
                    "id": "aaa",
                    "slug": "good-one",
                    "name": "Good One",
                    "stats": {"chapters_count": 12},
                },
                {"id": "", "slug": "no-id", "name": "No Id",
                 "stats": {"chapters_count": 5}},
                {"id": "bbb", "slug": "no-title", "name": "  ",
                 "stats": {"chapters_count": 5}},
                {"id": "ccc", "slug": "empty-stub", "name": "Empty Stub",
                 "stats": {"chapters_count": 0}},
            ],
            "pagination": {"limit": 20, "page": 1, "total": 4, "has_next": False},
        }
    }
    listing = parse_title_list(payload, page=1)
    assert [item.id for item in listing.items] == ["aaa/good-one"]


def test_listing_counts_teaser_chapters_when_the_stats_block_is_missing():
    """Some rows carry no ``chapters_count`` but do carry recent-chapter
    teasers — evidence enough that there is something to read."""
    payload = {
        "data": {
            "items": [
                {
                    "id": "ddd",
                    "slug": "teasers-only",
                    "name": "Teasers Only",
                    "latest_chapters": [{"name": "Chapter 3"}, {"name": "Chapter 2"}],
                }
            ]
        }
    }
    listing = parse_title_list(payload, page=1)
    assert len(listing.items) == 1
    assert listing.items[0].chapter_count == 2
    assert listing.items[0].latest_chapter == "Chapter 3"


def test_malformed_payload_is_an_empty_listing_not_a_crash():
    for payload in ({}, {"data": None}, {"data": {}}, {"data": {"items": "nope"}}):
        assert parse_title_list(payload, page=1).items == []


# --- detail -----------------------------------------------------------------


def test_parse_title_detail():
    series = parse_title(_load("title.json"), SERIES_KEY)
    assert series is not None
    assert series.title.startswith("World Evolution Apocalypse")
    assert series.author == "FrozenShiva_01"
    assert series.chapter_count == SERIES_CHAPTER_TOTAL
    assert series.status
    assert series.genres
    assert series.description and "<" not in series.description


def test_detail_keeps_the_key_the_caller_already_holds():
    """Upstream records can carry a ``redirect_slug``; adopting it would
    silently rename a series the reader has already bookmarked."""
    series = parse_title(_load("title.json"), SERIES_KEY)
    assert series is not None
    assert series.id == SERIES_KEY


def test_detail_chapter_array_is_truncated_which_is_why_it_is_not_used():
    """Pins the reason ``get_chapters`` hits the dedicated endpoint: the
    detail payload's own ``chapters`` array stops well short of the total."""
    raw = _load("title.json")["data"]["title"]
    assert len(raw["chapters"]) == 50
    assert raw["stats"]["chapters_count"] == SERIES_CHAPTER_TOTAL
    assert len(raw["chapters"]) < raw["stats"]["chapters_count"]


# --- chapters ---------------------------------------------------------------


def test_parse_chapter_list_is_complete_and_ascending():
    chapters = parse_chapters(_load("chapters.json"), SERIES_KEY)
    assert len(chapters) == SERIES_CHAPTER_TOTAL
    numbers = [chapter.number for chapter in chapters]
    assert numbers == sorted(numbers)
    assert numbers[0] == 1.0
    assert numbers[-1] == float(SERIES_CHAPTER_TOTAL)
    assert chapters[0].id == CHAPTER_KEY
    assert all("/" in chapter.id for chapter in chapters)
    assert all(chapter.series_id == SERIES_KEY for chapter in chapters)


def test_chapter_rows_without_an_id_or_title_are_dropped():
    payload = {
        "data": {
            "chapters": [
                {"id": "c2", "slug": "two", "name": "Chapter 2", "number": 2},
                {"id": "", "slug": "nope", "name": "Chapter X", "number": 9},
                {"id": "c1", "slug": "one", "name": "Chapter 1", "number": 1},
                {"id": "c3", "slug": "three", "name": "   ", "number": 3},
            ]
        }
    }
    chapters = parse_chapters(payload, SERIES_KEY)
    assert [chapter.id for chapter in chapters] == ["c1/one", "c2/two"]


def test_chapters_with_no_number_sort_to_the_end_rather_than_crashing():
    payload = {
        "data": {
            "chapters": [
                {"id": "cx", "slug": "extra", "name": "Side Story", "number": None},
                {"id": "c1", "slug": "one", "name": "Chapter 1", "number": 1},
            ]
        }
    }
    chapters = parse_chapters(payload, SERIES_KEY)
    assert [chapter.id for chapter in chapters] == ["c1/one", "cx/extra"]


# --- chapter text and the aggregator-junk strip -----------------------------


def test_parse_chapter_text():
    text = parse_chapter(_load("chapter.json"))
    assert text is not None
    assert text.title == "Chapter 1: Unlucky Day"
    assert text.chapter_number == 1.0
    assert len(text.paragraphs) > 50
    assert text.word_count > 500
    assert all(isinstance(p, str) and p.strip() for p in text.paragraphs)
    # No markup survives into storage.
    assert not any("<" in p and ">" in p for p in text.paragraphs)


def test_chapter_body_does_not_repeat_its_own_title():
    """Every NovelBuddy body opens by repeating the chapter title inside the
    content div. The reader already renders the title above the text, so
    leaving it would show it twice — and read it twice aloud."""
    text = parse_chapter(_load("chapter.json"))
    assert text is not None
    assert text.paragraphs[0] != text.title
    assert not text.paragraphs[0].startswith("Chapter 1: Unlucky Day")
    # The real first line of the story survives.
    assert "Ugh" in text.paragraphs[0]


def test_repeated_heading_drop_only_fires_on_an_exact_match():
    """A chapter whose opening sentence merely resembles its title keeps it —
    the drop is exact against the normalized title, first paragraph only."""
    payload = {
        "data": {
            "chapter": {
                "name": "Chapter 7: The Long Road",
                "number": 7,
                "content": (
                    "<div><p>The long road stretched on for miles.</p>"
                    "<p>He walked it anyway.</p></div>"
                ),
            }
        }
    }
    text = parse_chapter(payload)
    assert text is not None
    assert text.paragraphs[0] == "The long road stretched on for miles."
    assert len(text.paragraphs) == 2


def test_site_promo_lines_are_stripped_from_chapter_bodies():
    """Aggregator watermark lines injected as visible body text."""
    payload = {
        "data": {
            "chapter": {
                "name": "Chapter 5",
                "number": 5,
                "content": (
                    "<div>"
                    "<p>Chapter 5</p>"
                    "<p>The gate groaned open.</p>"
                    "<p>Read the latest chapters at novelbuddy.me</p>"
                    "<p>Visit our website for more chapters.</p>"
                    "<p>https://novelbuddy.com/some-novel</p>"
                    "<p>www.novelbuddy.me</p>"
                    "<p>Updated by freewebnovel.com</p>"
                    "<p>She stepped through without looking back.</p>"
                    "</div>"
                ),
            }
        }
    }
    text = parse_chapter(payload)
    assert text is not None
    assert text.paragraphs == (
        "The gate groaned open.",
        "She stepped through without looking back.",
    )


def test_promo_matcher_never_fires_on_ordinary_prose():
    """Every pattern must be specific enough to be safe on narrative text."""
    prose = [
        "He read the latest report from the front.",
        "The buddy system had saved them more than once.",
        "She would visit the old temple at dawn.",
        "Three more chapters of the ledger remained unread.",
        "Support arrived on the fourth day.",
        "A novel idea, he thought, and a dangerous one.",
    ]
    assert not any(is_site_promo_line(line) for line in prose)


def test_promo_matcher_sees_through_confusable_obfuscation():
    """The shared normalizer folds homoglyphs before matching, so spelling
    the site name with Cyrillic lookalikes does not slip through."""
    assert is_site_promo_line("read more at nоvelbuddy.me")  # Cyrillic 'о'


def test_ad_slots_and_hidden_elements_never_reach_storage():
    payload = {
        "data": {
            "chapter": {
                "name": "Chapter 9",
                "number": 9,
                "content": (
                    "<style>.wm7 { display: none; }</style>"
                    "<div>"
                    "<p>Real opening line.</p>"
                    '<div class="ads"><p>Buy something now.</p></div>'
                    '<p class="wm7">Stolen from somewhere.</p>'
                    '<p style="display:none">Also hidden.</p>'
                    "<script>var x = 'not text';</script>"
                    "<p>Real closing line.</p>"
                    '<div style="margin-top:10px;text-align:center"><div></div></div>'
                    "</div>"
                ),
            }
        }
    }
    text = parse_chapter(payload)
    assert text is not None
    assert text.paragraphs == ("Real opening line.", "Real closing line.")


def test_chapter_with_no_content_does_not_parse():
    for content in (None, "", "   ", "<div></div>"):
        payload = {"data": {"chapter": {"name": "C", "number": 1, "content": content}}}
        assert parse_chapter(payload) is None


def test_chapter_that_is_only_promo_does_not_parse():
    """A body with nothing left after the strip is a dead chapter, not an
    empty one — the service must fall back to cache rather than store it."""
    payload = {
        "data": {
            "chapter": {
                "name": "Chapter 3",
                "number": 3,
                "content": "<div><p>Chapter 3</p><p>Read more at novelbuddy.me</p></div>",
            }
        }
    }
    assert parse_chapter(payload) is None


def test_malformed_chapter_payloads_do_not_crash():
    for payload in ({}, {"data": None}, {"data": {}}, {"data": {"chapter": "nope"}}):
        assert parse_chapter(payload) is None


# --- connector behaviour ----------------------------------------------------


@pytest.fixture()
def connector() -> NovelBuddyConnector:
    return NovelBuddyConnector()


def test_connector_declares_the_novel_contract(connector: NovelBuddyConnector):
    assert connector.content_kind == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.source_type == "novelbuddy"
    assert connector.is_mature is False
    # Novels have no page images.
    assert connector.get_chapter_pages("anything") == []
    assert connector.find_page("anything") is None


def test_cover_cdn_is_inside_the_image_allowlist(connector: NovelBuddyConnector):
    """Covers are served from rs.novelbuddy.me; the proxy allowlist is a
    domain-suffix match, so the site domain must cover the CDN subdomain."""
    listing = parse_title_list(_load("browse_views.json"), page=1)
    covers = [item.cover_url for item in listing.items if item.cover_url]
    assert covers
    allowed = connector.allowed_image_hosts
    for cover in covers:
        host = cover.split("/")[2]
        assert any(host == domain or host.endswith(f".{domain}") for domain in allowed)


def test_chapter_list_costs_exactly_one_request(connector: NovelBuddyConnector):
    """However long the series. Verified upstream against a 1,230-chapter
    title: the endpoint returns the whole list and ``pagination`` is null."""
    calls: list[tuple] = []

    def fake_get_json(path, params=None):
        calls.append((path, params))
        return _load("chapters.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        chapters = connector.get_chapters(SERIES_KEY)

    assert len(chapters) == SERIES_CHAPTER_TOTAL
    assert len(calls) == 1
    assert calls[0][0] == "/titles/LDgamG8v/chapters"
    assert calls[0][1] == {"limit": CHAPTER_LIMIT}


def test_repeat_reads_are_served_from_cache(connector: NovelBuddyConnector):
    calls: list[str] = []

    def fake_get_json(path, params=None):
        calls.append(path)
        return _load("chapters.json") if path.endswith("/chapters") else _load("title.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        assert connector.get_series(SERIES_KEY) is not None
        assert connector.get_series(SERIES_KEY) is not None
        assert connector.get_chapters(SERIES_KEY)
        assert connector.get_chapters(SERIES_KEY)

    # One request each, not four.
    assert sorted(calls) == ["/titles/LDgamG8v", "/titles/LDgamG8v/chapters"]


def test_chapter_text_end_to_end(connector: NovelBuddyConnector):
    with patch.object(connector._http, "get_json", return_value=_load("chapter.json")):
        text = connector.chapter_text(SERIES_KEY, CHAPTER_KEY)
    assert text is not None
    assert text.chapter_number == 1.0
    assert text.word_count > 500


def test_non_english_chapter_is_refused(connector: NovelBuddyConnector):
    """Aggregators occasionally leak an untranslated raw; caching one would
    pin garbage in novel_chapter_cache for a week."""
    payload = {
        "data": {
            "chapter": {
                "name": "第一章",
                "number": 1,
                "content": "<div><p>" + ("这是一段中文小说的正文内容。" * 12) + "</p></div>",
            }
        }
    }
    with patch.object(connector._http, "get_json", return_value=payload):
        assert connector.chapter_text(SERIES_KEY, CHAPTER_KEY) is None


# --- upstream failure modes -------------------------------------------------


def _http_error(message: str, status: int | None = None) -> ConnectorHttpError:
    return ConnectorHttpError(message, status_code=status)


NOT_FOUND = "Client error '404 Not Found' for url 'https://api.novelbuddy.me/x'"
BAD_REQUEST = "Client error '400 Bad Request' for url 'https://api.novelbuddy.me/x'"


def test_a_404_reads_as_a_missing_series_not_a_network_failure(
    connector: NovelBuddyConnector,
):
    """The shared client leaves ``status_code`` None for a plain 404, so the
    check must match the message too — a bare ``status_code == 404`` is dead
    code against this client."""
    error = _http_error(NOT_FOUND)
    assert error.status_code is None  # the trap this guards

    with patch.object(connector._http, "get_json", side_effect=error):
        assert connector.get_series(SERIES_KEY) is None
        assert connector.get_chapters(SERIES_KEY) == []
        assert connector.chapter_text(SERIES_KEY, CHAPTER_KEY) is None


def test_a_rejected_identifier_reads_as_a_missing_series(
    connector: NovelBuddyConnector,
):
    """``/titles/<id>`` validates its path segment as a Sqid and answers 400
    for a stale or hand-edited key. To a reader that is a missing series, not
    an outage — raising would make the service serve stale cache forever."""
    body = _load("title_bad_sqid.json")
    assert body["success"] is False
    # The rejection is about the identifier itself, not about the resource.
    assert "title_sqid" in json.dumps(body)

    with patch.object(connector._http, "get_json", side_effect=_http_error(BAD_REQUEST)):
        assert connector.get_series("not-a-sqid-at-all") is None
        assert connector.get_chapters("not-a-sqid-at-all") == []


def test_a_real_network_failure_propagates(connector: NovelBuddyConnector):
    """The novel service serves its cache stale on ConnectorHttpError, so a
    500 must NOT be flattened into "this series no longer exists"."""
    error = _http_error("Retryable HTTP 503", status=503)
    with patch.object(connector._http, "get_json", side_effect=error):
        with pytest.raises(ConnectorHttpError):
            connector.get_series(SERIES_KEY)
        with pytest.raises(ConnectorHttpError):
            connector.get_chapters(SERIES_KEY)
        with pytest.raises(ConnectorHttpError):
            connector.chapter_text(SERIES_KEY, CHAPTER_KEY)


def test_an_empty_key_never_reaches_the_network(connector: NovelBuddyConnector):
    with patch.object(connector._http, "get_json") as get_json:
        assert connector.get_series("   ") is None
        assert connector.get_chapters("") == []
    get_json.assert_not_called()


def test_search_falls_back_to_browse_for_a_blank_query(connector: NovelBuddyConnector):
    seen: list[dict] = []

    def fake_get_json(path, params=None):
        seen.append(params or {})
        return _load("browse_views.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        listing = connector.search_series("   ", 1)

    assert isinstance(listing, PaginatedSeriesList)
    assert len(listing.items) == 20
    assert "q" not in seen[0]
