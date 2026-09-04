"""Offline tests for the Royal Road novel connector.

Fixtures under ``tests/fixtures/royalroad/`` were captured live 2026-09-04
FROM THE VPS (through production's exact egress and TLS stack — the probe
methodology in the novels spec §4). The connector is exercised entirely
against those captures by patching ``self._http.get_text``; no network.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.novel_text import hidden_classes_from_styles
from connectors.royalroad.connector import RoyalRoadConnector
from connectors.royalroad.mappers import (
    chapter_path,
    normalize_chapter_key,
    normalize_series_key,
    parse_chapter_page,
    parse_fiction_list,
    parse_fiction_page,
    series_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "royalroad"

SERIES_KEY = "21220/mother-of-learning"
CHAPTER_KEY = "301778/1-good-morning-brother"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- identity ---------------------------------------------------------------


def test_series_key_contains_a_slash_and_round_trips():
    """House law: keys are opaque and may contain slashes, passed through raw."""
    assert "/" in SERIES_KEY
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(f"fiction/{SERIES_KEY}") == SERIES_KEY
    assert (
        normalize_series_key(f"https://www.royalroad.com/fiction/{SERIES_KEY}")
        == SERIES_KEY
    )
    assert series_path(SERIES_KEY) == f"/fiction/{SERIES_KEY}"


def test_chapter_key_round_trips():
    assert normalize_chapter_key(CHAPTER_KEY) == CHAPTER_KEY
    assert (
        chapter_path(SERIES_KEY, CHAPTER_KEY)
        == f"/fiction/{SERIES_KEY}/chapter/{CHAPTER_KEY}"
    )
    # A full chapter URL normalizes down to the same key.
    assert (
        normalize_chapter_key(
            f"https://www.royalroad.com/fiction/{SERIES_KEY}/chapter/{CHAPTER_KEY}"
        )
        == CHAPTER_KEY
    )


# --- browse / search --------------------------------------------------------


def test_parse_browse_page():
    listing = parse_fiction_list(_load("browse_best_rated.html"), page=1)
    assert len(listing.items) == 20
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == SERIES_KEY
    assert first.title == "Mother of Learning"
    assert first.cover_url and first.cover_url.startswith("https://")
    assert first.genres  # tags parsed
    assert first.chapter_count > 100


def test_parse_latest_updates_page():
    listing = parse_fiction_list(_load("browse_latest.html"), page=1)
    assert len(listing.items) >= 10
    assert all(item.id and item.title for item in listing.items)


def test_parse_trending_page_is_unpaginated():
    """Trending is Royal Road's one unpaginated view: 50 cards, no Next link.
    ``has_more`` must come back False so clients stop instead of looping on
    an identical page 2. (Captured from the VPS 2026-09-04, like the rest.)"""
    listing = parse_fiction_list(_load("browse_trending.html"), page=1)
    assert len(listing.items) == 50
    assert listing.has_more is False
    assert all(item.id and item.title and item.chapter_count for item in listing.items)


def test_listing_drops_obviously_broken_rows():
    """House law: a card with no readable chapter count (markup drift) or a
    zero-chapter stub never reaches clients."""
    good = (
        '<div class="fiction-list-item row">'
        '<img src="https://www.royalroadcdn.com/covers/x.jpg">'
        '<h2 class="fiction-title"><a href="/fiction/1/good-story">Good Story</a></h2>'
        "<span>12 Chapters</span></div>"
    )
    zero = (
        '<div class="fiction-list-item row">'
        '<h2 class="fiction-title"><a href="/fiction/2/empty-stub">Empty Stub</a></h2>'
        "<span>0 Chapters</span></div>"
    )
    countless = (
        '<div class="fiction-list-item row">'
        '<h2 class="fiction-title"><a href="/fiction/3/driftwood">Driftwood</a></h2>'
        "</div>"
    )
    # Latest Updates cards have no "N Chapters" total, only recent chapter
    # links — evidence enough of a readable fiction.
    latest_style = (
        '<div class="fiction-list-item row">'
        '<h2 class="fiction-title"><a href="/fiction/4/fresh-serial">Fresh Serial</a></h2>'
        '<a href="/fiction/4/fresh-serial/chapter/900/ch-1">Ch 1</a>'
        "</div>"
    )
    listing = parse_fiction_list(good + zero + countless + latest_style, page=1)
    assert [item.id for item in listing.items] == ["1/good-story", "4/fresh-serial"]
    assert listing.items[0].chapter_count == 12
    assert listing.items[1].chapter_count == 1


def test_parse_search_results_find_target():
    listing = parse_fiction_list(_load("search_mother.html"), page=1)
    assert listing.items
    assert any(
        "mother of learning" in item.title.casefold() for item in listing.items
    )


# --- detail + chapters (one page carries both) ------------------------------


def test_parse_fiction_page_metadata():
    series, chapters = parse_fiction_page(_load("fiction_mol.html"), SERIES_KEY)
    assert series is not None
    assert series.title == "Mother of Learning"
    assert series.author == "nobody103"
    assert series.status == "completed"
    assert series.cover_url and "royalroadcdn.com" in series.cover_url
    assert series.description and "Zorian" in series.description
    # Description is plain text — no markup survives.
    assert "<" not in series.description
    assert series.chapter_count == len(chapters)


def test_parse_fiction_page_chapter_list_ordered_with_slash_keys():
    _, chapters = parse_fiction_page(_load("fiction_mol.html"), SERIES_KEY)
    assert len(chapters) >= 100
    assert chapters[0].id == CHAPTER_KEY
    assert chapters[0].title == "1. Good Morning Brother"
    assert chapters[0].number == 1.0
    assert all("/" in c.id for c in chapters)
    assert all(c.series_id == SERIES_KEY for c in chapters)
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers)
    assert all(c.release_date for c in chapters)


# --- chapter text -----------------------------------------------------------


def test_parse_chapter_page_paragraphs_are_plain_text():
    text = parse_chapter_page(_load("chapter_mol_1.html"))
    assert text is not None
    assert text.title == "1. Good Morning Brother"
    assert len(text.paragraphs) > 50
    assert text.word_count > 2000
    joined = "\n".join(text.paragraphs)
    # Real story text present.
    assert "Zorian" in joined
    # No markup or script content reaches the paragraphs. ("function" alone
    # would be wrong to assert on — it appears in the story's own prose.)
    assert "<" not in joined
    assert "javascript" not in joined.casefold()
    assert "window." not in joined


def test_chapter_page_watermark_and_ads_are_stripped():
    """The live capture carries BOTH defenses' targets: a hidden anti-theft
    sentence (randomized class + display:none style) and inline ad portlets.
    A broken sanitizer leaks them into the reader AND the TTS pipeline."""
    html = _load("chapter_mol_1.html")
    # Prove the fixture actually contains the watermark + ads (otherwise this
    # test would pass vacuously against a re-captured page).
    assert "know that it has been stolen" in html
    assert "Advertisement" in html
    assert hidden_classes_from_styles(html)

    text = parse_chapter_page(html)
    joined = " ".join(text.paragraphs)
    assert "stolen" not in joined.casefold()
    assert "amazon" not in joined.casefold()
    assert "report the violation" not in joined.casefold()
    assert "advertisement" not in joined.casefold()


def test_hidden_class_stripping_works_without_the_promo_blacklist():
    """Pin the STRUCTURAL defense on its own. The live fixture's watermark is
    also caught by the promo blacklist (defense in depth), so this synthetic
    page hides a sentence that reads as ordinary prose — only the
    hidden-classes-from-<style> mechanism can drop it. Breaks if
    ``parse_chapter_page`` stops wiring ``hidden_classes_from_styles`` into
    ``extract_paragraphs``."""
    page = (
        "<html><head><style>.abQ3xRandom { display: none; }</style></head>"
        '<body><h1>7. A Chapter</h1>'
        '<div class="chapter-inner chapter-content">'
        "<p>Zorian opened the window.</p>"
        '<p class="abQ3xRandom">He quietly counted the seventeen marbles.</p>'
        "<p>Then he went back to sleep.</p>"
        "</div></body></html>"
    )
    text = parse_chapter_page(page)
    assert text is not None
    assert "Zorian opened the window." in text.paragraphs
    assert "Then he went back to sleep." in text.paragraphs
    assert all("marbles" not in p for p in text.paragraphs)


# --- connector plumbing -----------------------------------------------------


@pytest.fixture
def connector() -> RoyalRoadConnector:
    return RoyalRoadConnector()


def test_connector_declares_novel_contract(connector):
    assert connector.CONTENT_KIND == "novel"
    assert connector.content_kind == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.get_chapter_pages("anything") == []
    assert connector.find_page("anything") is None


def test_connector_series_and_chapters_share_one_fetch(connector):
    calls: list[str] = []

    def fake_get_text(path, *, params=None):
        calls.append(path)
        return _load("fiction_mol.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)

    assert series is not None and series.title == "Mother of Learning"
    assert len(chapters) >= 100
    assert calls == [f"/fiction/{SERIES_KEY}"]


def test_connector_chapter_text_backfills_number_from_key(connector):
    def fake_get_text(path, *, params=None):
        assert path == chapter_path(SERIES_KEY, CHAPTER_KEY)
        return _load("chapter_mol_1.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        text = connector.chapter_text(SERIES_KEY, CHAPTER_KEY)

    assert text is not None
    assert text.chapter_number == 1.0
    assert text.paragraphs


def test_connector_browse_hits_the_selected_view(connector):
    seen: dict[str, object] = {}

    def fake_get_text(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return _load("browse_best_rated.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        listing = connector.get_series_list(1, sort="latest")

    assert seen["path"] == "/fictions/latest-updates"
    assert seen["params"] == {"page": 1}
    assert listing.items
