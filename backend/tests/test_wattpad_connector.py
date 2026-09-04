"""Offline tests for the Wattpad novel connector.

Fixtures under ``tests/fixtures/wattpad/`` were captured live 2026-09-04 FROM
THE VPS (through production's exact egress and TLS stack — the probe
methodology in the novels spec §4). The connector is exercised entirely
against those captures by patching ``self._http.get_json`` /
``self._http.get_text``; no network.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.wattpad.connector import WattpadConnector
from connectors.wattpad.mappers import (
    PAGE_SIZE,
    is_servable,
    list_params,
    normalize_chapter_key,
    normalize_series_key,
    parse_story_detail,
    parse_story_list,
    parse_story_text,
    story_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "wattpad"

SERIES_KEY = "26327373"
CHAPTER_KEY = "80847228"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _json(name: str) -> dict:
    return json.loads(_load(name))


# --- identity ---------------------------------------------------------------


def test_keys_are_bare_ids_and_round_trip():
    """Unlike the other novel sources, Wattpad keys carry NO slash — nothing
    may assume novel keys are path-shaped."""
    assert "/" not in SERIES_KEY and "/" not in CHAPTER_KEY
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert story_path(SERIES_KEY) == f"/api/v3/stories/{SERIES_KEY}"
    assert normalize_chapter_key(CHAPTER_KEY) == CHAPTER_KEY


def test_pasted_urls_reduce_to_ids():
    """Wattpad's own URLs append a slug to the id; only the id is stable."""
    assert (
        normalize_series_key(
            "https://www.wattpad.com/story/26327373-the-dragon-and-the-princess"
        )
        == SERIES_KEY
    )
    assert normalize_series_key("/story/26327373-the-dragon") == SERIES_KEY
    assert normalize_chapter_key("/80847228-chapter-1") == CHAPTER_KEY
    assert (
        normalize_chapter_key("https://www.wattpad.com/80847228-chapter-1")
        == CHAPTER_KEY
    )


def test_list_params_page_to_offset_and_mode():
    assert list_params(1)["offset"] == 0
    assert list_params(3)["offset"] == 2 * PAGE_SIZE
    assert list_params(1, sort="new")["filter"] == "new"
    assert list_params(1, sort="featured")["filter"] == "featured"
    # Unknown modes fall back to the default view, never to an API error.
    assert list_params(1, sort="nonsense")["filter"] == "hot"
    # A search request is a query, not a filter — sending both would make
    # Wattpad ignore the query.
    search = list_params(2, query="dragon")
    assert search["query"] == "dragon"
    assert "filter" not in search


# --- browse / search --------------------------------------------------------


def test_parse_search_results():
    payload = _json("search_dragon.json")
    listing = parse_story_list(payload, page=1)
    assert len(listing.items) == 20
    assert listing.total == 228550
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == SERIES_KEY
    assert first.title == "The Dragon and the Princess"
    assert first.author == "Dragon"
    assert first.status == "completed"
    assert first.chapter_count == 34
    assert first.cover_url == "https://img.wattpad.com/cover/26327373-256-k228682.jpg"
    assert "dragon" in first.genres


def test_mature_stories_are_dropped_from_listings():
    """The connector is NOT marked mature, so stories Wattpad flags mature are
    not part of its catalog. The captured "featured" page carries four of
    them — a filter regression shows up here, not in production."""
    payload = _json("browse_featured.json")
    raw = payload["stories"]
    assert sum(1 for story in raw if story.get("mature")) == 4

    listing = parse_story_list(payload, page=1)
    assert len(listing.items) == len(raw) - 4
    served = {item.id for item in listing.items}
    assert served
    assert all(
        str(story["id"]) not in served for story in raw if story.get("mature")
    )


def test_has_more_follows_next_url_not_a_full_page_check():
    """Wattpad silently drops deleted stories from a window: the captured
    ``filter=hot`` page holds 17 of the 20 requested. Ending a listing on a
    short page would cut browsing off three items into a 1,500-story view."""
    payload = _json("browse_hot.json")
    assert len(payload["stories"]) == 17 < PAGE_SIZE
    listing = parse_story_list(payload, page=1)
    assert len(listing.items) == 17
    assert listing.has_more is True


def test_last_page_reports_no_more_pages():
    """Deep page of ``filter=new`` (offset 1480 of 1500): full window, but the
    API returns no ``nextUrl``."""
    payload = _json("browse_new_offset.json")
    assert payload.get("nextUrl") is None
    listing = parse_story_list(payload, page=75)
    assert len(listing.items) == 20
    assert listing.has_more is False


def test_listing_drops_obviously_broken_and_foreign_rows():
    """House law: rows with no title/id never reach clients. A story whose
    language is not English is dropped too — the connector declares
    LANGUAGE = "en"."""
    payload = {
        "total": 4,
        "nextUrl": None,
        "stories": [
            {"id": "1", "title": "Kept", "language": {"name": "English"}},
            {"id": "2", "title": "", "language": {"name": "English"}},
            {"id": "", "title": "No Id", "language": {"name": "English"}},
            {"id": "4", "title": "Otra Historia", "language": {"name": "Spanish"}},
            # No language field at all: absent data is not evidence of a
            # foreign language, so this one is kept.
            {"id": "5", "title": "Unlabelled"},
        ],
    }
    listing = parse_story_list(payload, page=1)
    assert [item.id for item in listing.items] == ["1", "5"]
    assert listing.has_more is False


def test_empty_or_malformed_payload_is_an_empty_page():
    assert parse_story_list({}, page=1).items == []
    assert parse_story_list({"stories": None}, page=1).items == []
    assert parse_story_list({"stories": ["not-a-dict"]}, page=1).items == []


def test_is_servable_rejects_mature_and_foreign_stories():
    assert is_servable({"id": "1", "title": "T"}) is True
    assert is_servable({"id": "1", "title": "T", "mature": True}) is False
    assert is_servable({"id": "1", "title": "T", "language": {"name": "Filipino"}}) is False
    assert is_servable({"id": "1", "title": "T", "language": {"name": "english"}}) is True


# --- detail + chapters (one response carries both) --------------------------


def test_parse_story_detail_metadata():
    series, chapters = parse_story_detail(_json("story_dragon_princess.json"), SERIES_KEY)
    assert series is not None
    assert series.title == "The Dragon and the Princess"
    assert series.author == "Dragon"
    assert series.status == "completed"
    assert series.cover_url and series.cover_url.startswith("https://img.wattpad.com/")
    assert series.description and "princess named Lydia" in series.description
    # Blurbs are plain text: no markup, and the hard line breaks Wattpad
    # stores become paragraph breaks rather than ragged single lines.
    assert "<" not in series.description
    assert "\n \n" not in series.description
    assert series.chapter_count == len(chapters)


def test_parse_story_detail_part_list_is_ordered_and_numbered():
    _, chapters = parse_story_detail(_json("story_dragon_princess.json"), SERIES_KEY)
    assert len(chapters) == 34
    assert chapters[1].id == CHAPTER_KEY
    assert chapters[1].title == "Chapter 1"
    # Wattpad numbers nothing itself: position in the part list IS the number.
    assert [chapter.number for chapter in chapters] == [
        float(n) for n in range(1, 35)
    ]
    assert all(chapter.series_id == SERIES_KEY for chapter in chapters)
    assert all(chapter.release_date for chapter in chapters)
    assert all(chapter.page_count == 0 for chapter in chapters)


def test_part_zero_is_the_authors_note_not_chapter_one():
    """The first part of this story is a "Declaration" author's note. It is a
    real part and must keep position 1 — renumbering to make "Chapter 1" the
    first chapter would desync every saved reading position."""
    _, chapters = parse_story_detail(_json("story_dragon_princess.json"), SERIES_KEY)
    assert chapters[0].title == "Declaration"
    assert chapters[0].number == 1.0
    assert chapters[1].title == "Chapter 1"


def test_detail_of_a_mature_story_is_not_served():
    """A catalog that hides a story from listings but still serves it on a
    guessed key is not a filter."""
    payload = {
        "id": "99",
        "title": "Adults Only",
        "mature": True,
        "language": {"name": "English"},
        "parts": [{"id": "1", "title": "One"}],
    }
    series, chapters = parse_story_detail(payload, "99")
    assert series is None
    assert chapters == []


def test_detail_skips_malformed_parts():
    payload = {
        "id": "7",
        "title": "Ragged",
        "language": {"name": "English"},
        "parts": [
            {"id": "11", "title": "One"},
            "not-a-dict",
            {"title": "No Id"},
            {"id": "12", "title": "Two"},
        ],
    }
    series, chapters = parse_story_detail(payload, "7")
    assert [chapter.id for chapter in chapters] == ["11", "12"]
    assert [chapter.number for chapter in chapters] == [1.0, 2.0]
    assert series.chapter_count == 2


# --- chapter text -----------------------------------------------------------


def test_parse_story_text_paragraphs_are_plain_text():
    paragraphs = parse_story_text(_load("storytext_part1.html"))
    assert len(paragraphs) == 14
    joined = "\n".join(paragraphs)
    assert "Lydia had finally found peace to sleep" in joined
    assert "<" not in joined
    assert "data-p-id" not in joined
    assert sum(len(p.split()) for p in paragraphs) > 1000


def test_long_part_is_returned_whole_by_the_unpaginated_endpoint():
    """``/apiv2/storytext?id=`` with NO ``page`` parameter returns the entire
    part; adding ``page=1`` returns a ~4.5 KB slice (measured live: 36,080
    characters vs 4,661 on this exact part). This capture is the unpaginated
    response — it must parse to the whole ~5,000-word chapter, so a future
    "add pagination" change is caught here rather than by a reader hitting a
    chapter that stops mid-sentence."""
    paragraphs = parse_story_text(_load("storytext_long.html"))
    assert len(paragraphs) > 150
    assert sum(len(p.split()) for p in paragraphs) > 4500
    assert "<" not in "\n".join(paragraphs)


def test_inline_markup_and_media_are_stripped_from_chapter_text():
    fragment = (
        '<p data-p-id="a">She read the <b>letter</b> twice, then <i>burned</i> it.</p>'
        '<p data-p-id="b"><img src="https://img.wattpad.com/x.jpg"/></p>'
        '<script>window.tracking = 1;</script>'
        '<p data-p-id="c">Outside, the snow kept falling.</p>'
    )
    paragraphs = parse_story_text(fragment)
    assert paragraphs == (
        "She read the letter twice, then burned it.",
        "Outside, the snow kept falling.",
    )
    assert all("window." not in p for p in paragraphs)


def test_empty_fragment_does_not_parse():
    assert parse_story_text("") == ()
    assert parse_story_text("<p></p>") == ()


# --- connector plumbing -----------------------------------------------------


@pytest.fixture
def connector() -> WattpadConnector:
    return WattpadConnector()


def test_connector_declares_novel_contract(connector):
    assert connector.CONTENT_KIND == "novel"
    assert connector.content_kind == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.is_mature is False
    assert connector.get_chapter_pages("anything") == []
    assert connector.find_page("anything") is None
    assert connector.allowed_image_hosts == frozenset({"wattpad.com"})


def test_connector_series_and_chapters_share_one_fetch(connector):
    calls: list[str] = []

    def fake_get_json(path, *, params=None):
        calls.append(path)
        return _json("story_dragon_princess.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)

    assert series is not None and series.title == "The Dragon and the Princess"
    assert len(chapters) == 34
    assert calls == [f"/api/v3/stories/{SERIES_KEY}"]


def test_connector_browse_sends_the_selected_filter(connector):
    seen: dict[str, object] = {}

    def fake_get_json(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return _json("browse_hot.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        listing = connector.get_series_list(2, sort="new")

    assert seen["path"] == "/api/v3/stories"
    assert seen["params"]["filter"] == "new"
    assert seen["params"]["offset"] == PAGE_SIZE
    assert listing.items


def test_connector_search_falls_back_to_browse_when_query_is_blank(connector):
    seen: dict[str, object] = {}

    def fake_get_json(path, *, params=None):
        seen["params"] = params
        return _json("browse_hot.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        connector.search_series("   ", 1)

    assert "query" not in seen["params"]
    assert seen["params"]["filter"] == "hot"


def test_connector_chapter_text_never_sends_a_page_parameter(connector):
    """Sending ``page`` truncates the part to a ~4.5 KB slice."""
    seen: dict[str, object] = {}

    def fake_get_text(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return _load("storytext_long.html")

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "get_json", return_value=_json("story_dragon_princess.json")),
    ):
        text = connector.chapter_text(SERIES_KEY, CHAPTER_KEY)

    assert seen["path"] == "/apiv2/storytext"
    assert seen["params"] == {"id": CHAPTER_KEY}
    assert "page" not in seen["params"]
    assert text is not None and text.word_count > 4500


def test_connector_chapter_text_titles_the_part_from_the_story(connector):
    """The text endpoint returns prose and nothing else — the title and number
    come from the story's own part list."""
    with (
        patch.object(connector._http, "get_text", return_value=_load("storytext_part1.html")),
        patch.object(connector._http, "get_json", return_value=_json("story_dragon_princess.json")),
    ):
        text = connector.chapter_text(SERIES_KEY, CHAPTER_KEY)

    assert text is not None
    assert text.title == "Chapter 1"
    assert text.chapter_number == 2.0  # part 2 of 34: part 1 is the author's note
    assert text.paragraphs


def test_connector_serves_chapter_text_even_when_the_story_lookup_fails(connector):
    """Metadata enrichment is best effort: a story that has since been pulled
    must not cost the reader a chapter whose text still serves."""
    with (
        patch.object(connector._http, "get_text", return_value=_load("storytext_part1.html")),
        patch.object(
            connector._http,
            "get_json",
            side_effect=ConnectorHttpError("Retryable HTTP 503", status_code=503),
        ),
    ):
        text = connector.chapter_text(SERIES_KEY, CHAPTER_KEY)

    assert text is not None
    assert text.paragraphs
    assert text.title == ""
    assert text.chapter_number is None


def test_connector_chapter_text_rejects_a_non_english_part(connector):
    """A story the API labels English can still serve a non-English part —
    observed live on a story pulled straight from ``filter=hot``. Caching that
    would pin unreadable text for a week."""
    fragment = (
        '<p data-p-id="a">ထမင္းစားၿပီးဗိုက္ကေလးလာၿပီးမ်က္လံုးကလည္းစင္းလာတာမို႔</p>'
        '<p data-p-id="b">အိပ္ေပ်ာ္သြားသည္ ကိုငယ္တို႔သြားၿပီလားဆိုတာေတာင္မသိလိုက္</p>'
    )
    with (
        patch.object(connector._http, "get_text", return_value=fragment),
        patch.object(connector._http, "get_json", return_value=_json("story_dragon_princess.json")),
    ):
        assert connector.chapter_text(SERIES_KEY, CHAPTER_KEY) is None


def test_connector_400_is_clean_not_found_wattpads_real_shape(connector):
    """Wattpad answers a missing story or part with **400**, not 404, and 400
    is not retryable — so it reaches the connector with ``status_code=None``
    and only httpx's message text. A ``status_code == 404`` check would be
    dead code twice over."""
    real_shape = ConnectorHttpError(
        "Client error '400 Bad Request' for url "
        "'https://www.wattpad.com/api/v3/stories/999999999999'",
        status_code=None,
    )

    with (
        patch.object(connector._http, "get_json", side_effect=real_shape),
        patch.object(connector._http, "get_text", side_effect=real_shape),
    ):
        assert connector.get_series("999999999999") is None
        assert connector.get_chapters("999999999999") == []
        assert connector.chapter_text("999999999999", "999999999999") is None


def test_connector_404_is_also_treated_as_not_found(connector):
    real_shape = ConnectorHttpError(
        "Client error '404 Not Found' for url "
        "'https://www.wattpad.com/api/v3/stories/1'",
        status_code=None,
    )
    with patch.object(connector._http, "get_json", side_effect=real_shape):
        assert connector.get_series("1") is None


def test_connector_non_404_errors_still_raise(connector):
    boom = ConnectorHttpError("Retryable HTTP 503", status_code=503)
    with patch.object(connector._http, "get_json", side_effect=boom):
        with pytest.raises(ConnectorHttpError):
            connector.get_series(SERIES_KEY)
    with patch.object(connector._http, "get_text", side_effect=boom):
        with pytest.raises(ConnectorHttpError):
            connector.chapter_text(SERIES_KEY, CHAPTER_KEY)
