"""Offline tests for the Standard Ebooks novel connector.

Fixtures under ``tests/fixtures/standardebooks/`` were captured live
2026-09-04 FROM THE VPS (through production's exact egress and TLS stack —
the probe methodology in the novels spec §4). The connector is exercised
entirely against those captures by patching ``self._http.get_text``; no
network.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.standardebooks.connector import StandardEbooksConnector
from connectors.standardebooks.mappers import (
    NON_READING_SLUGS,
    browse_params,
    chapter_path,
    normalize_chapter_key,
    normalize_series_key,
    parse_book,
    parse_chapter_page,
    parse_ebook_list,
    parse_toc,
    series_path,
    toc_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "standardebooks"

SERIES_KEY = "mary-shelley/frankenstein"
CHAPTER_KEY = "chapter-1"
CAROL_KEY = "charles-dickens/a-christmas-carol"
#: A translated work: author/title/translator. Three segments are routine.
TRANSLATED_KEY = "confucius/analects/james-legge"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- identity ---------------------------------------------------------------


def test_series_key_contains_a_slash_and_round_trips():
    """House law: keys are opaque and may contain slashes, passed through raw."""
    assert "/" in SERIES_KEY
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(f"ebooks/{SERIES_KEY}") == SERIES_KEY
    assert (
        normalize_series_key(f"https://standardebooks.org/ebooks/{SERIES_KEY}")
        == SERIES_KEY
    )
    assert series_path(SERIES_KEY) == f"/ebooks/{SERIES_KEY}"
    assert toc_path(SERIES_KEY) == f"/ebooks/{SERIES_KEY}/text"


def test_three_segment_translated_key_survives_normalization():
    """A translated work's key is author/title/translator — nothing may
    assume two segments (``confucius/analects/james-legge`` is on browse page
    2 of the live capture)."""
    assert TRANSLATED_KEY.count("/") == 2
    assert normalize_series_key(TRANSLATED_KEY) == TRANSLATED_KEY
    assert (
        normalize_series_key(f"/ebooks/{TRANSLATED_KEY}/text/chapter-3")
        == TRANSLATED_KEY
    )
    assert series_path(TRANSLATED_KEY) == f"/ebooks/{TRANSLATED_KEY}"


def test_chapter_key_round_trips():
    assert normalize_chapter_key(CHAPTER_KEY) == CHAPTER_KEY
    assert normalize_chapter_key(f"text/{CHAPTER_KEY}") == CHAPTER_KEY
    assert (
        normalize_chapter_key(
            f"https://standardebooks.org/ebooks/{SERIES_KEY}/text/{CHAPTER_KEY}"
        )
        == CHAPTER_KEY
    )
    assert (
        chapter_path(SERIES_KEY, CHAPTER_KEY)
        == f"/ebooks/{SERIES_KEY}/text/{CHAPTER_KEY}"
    )


def test_browse_params_map_sort_modes():
    assert browse_params(2) == {"page": 2, "per-page": 48}
    assert browse_params(1, sort="popularity") == {
        "page": 1,
        "per-page": 48,
        "sort": "popularity",
    }
    # The site default sends no sort param at all.
    assert "sort" not in browse_params(1, sort="default")
    assert "sort" not in browse_params(1, sort="nonsense-mode")
    assert browse_params(1, query="dickens")["query"] == "dickens"


# --- browse / search --------------------------------------------------------


def test_parse_browse_page():
    listing = parse_ebook_list(_load("browse_p1.html"), page=1)
    assert len(listing.items) == 48
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "arthur-conan-doyle/brigadier-gerard-stories"
    assert first.title == "Brigadier Gerard Stories"
    assert first.author == "Arthur Conan Doyle"
    assert first.cover_url == (
        "https://standardebooks.org/images/covers/"
        "arthur-conan-doyle_brigadier-gerard-stories/"
        "e2107a97c06b430333019e509b9ff3b5c69ca03a/cover@2x.jpg"
    )
    assert first.status == "completed"


def test_parse_browse_page_two_carries_three_segment_keys():
    listing = parse_ebook_list(_load("browse_p2.html"), page=2)
    assert len(listing.items) == 48
    deep = [item for item in listing.items if item.id.count("/") == 2]
    assert deep, "page 2 of the capture contains translated works"
    assert any(item.id == TRANSLATED_KEY for item in deep)
    assert all(item.title for item in deep)


def test_last_page_reports_no_more_pages():
    """The site CLAMPS an over-large page number to the last page instead of
    erroring, so ``has_more`` can only come from the pagination nav's
    rel="next" link — a count-based guess would loop clients forever on the
    final page. (Capture: ``/ebooks?page=99999&per-page=48``.)"""
    listing = parse_ebook_list(_load("browse_last.html"), page=32)
    assert listing.items
    assert len(listing.items) < 48
    assert listing.has_more is False


def test_parse_search_results_find_target():
    listing = parse_ebook_list(_load("search_dickens.html"), page=1)
    assert len(listing.items) == 12
    assert all(item.id.startswith("charles-dickens/") for item in listing.items)
    assert any("Edwin Drood" in item.title for item in listing.items)
    assert listing.items[0].author == "Charles Dickens"


def test_listing_drops_obviously_broken_rows():
    """House law: a card with no readable title (markup drift) never reaches
    clients, and a card with no cover still does."""
    good = (
        '<li typeof="schema:Book" about="/ebooks/a-writer/a-book">'
        '<img src="/images/covers/a-writer_a-book/deadbeef/cover@2x.jpg">'
        '<p><a href="/ebooks/a-writer/a-book"><span property="schema:name">A Book</span></a></p>'
        '<p class="author"><a><span property="schema:name">A Writer</span></a></p>'
        "</li>"
    )
    titleless = (
        '<li typeof="schema:Book" about="/ebooks/b-writer/b-book">'
        '<p><a href="/ebooks/b-writer/b-book">B Book</a></p>'
        "</li>"
    )
    coverless = (
        '<li typeof="schema:Book" about="/ebooks/c-writer/c-book">'
        '<p><a><span property="schema:name">C Book</span></a></p>'
        "</li>"
    )
    listing = parse_ebook_list(good + titleless + coverless, page=1)
    assert [item.id for item in listing.items] == [
        "a-writer/a-book",
        "c-writer/c-book",
    ]
    assert listing.items[0].cover_url.startswith("https://standardebooks.org/images/")
    assert listing.items[1].cover_url is None
    assert listing.has_more is False


def test_card_with_two_authors_joins_both():
    card = (
        '<li typeof="schema:Book" about="/ebooks/ring-lardner_george-s-kaufman/june-moon">'
        '<p><a><span property="schema:name">June Moon</span></a></p>'
        '<p class="author"><a><span property="schema:name">Ring Lardner</span></a></p>'
        '<p class="author"><a><span property="schema:name">George S. Kaufman</span></a></p>'
        "</li>"
    )
    listing = parse_ebook_list(card, page=1)
    assert listing.items[0].title == "June Moon"
    assert listing.items[0].author == "Ring Lardner, George S. Kaufman"


# --- detail + chapters ------------------------------------------------------


def test_parse_book_metadata():
    series, chapters = parse_book(
        _load("book_frankenstein.html"), _load("toc_frankenstein.xhtml"), SERIES_KEY
    )
    assert series is not None
    assert series.title == "Frankenstein"
    assert series.author == "Mary Shelley"
    assert series.status == "completed"
    assert series.cover_url == (
        "https://standardebooks.org/ebooks/mary-shelley/frankenstein/downloads/cover.jpg"
    )
    assert series.genres == ("Horror", "Science Fiction")
    assert series.description and "Victor Frankenstein" in series.description
    # Description is plain text — no markup survives.
    assert "<" not in series.description
    assert series.chapter_count == len(chapters)


def test_description_excludes_the_sites_donation_appeal():
    """The book page's description SECTION wraps the description itself in an
    <aside> fundraising appeal that the site renders conditionally (it is
    absent from the capture, present on the live page). Slicing the narrow
    ``schema:description`` div rather than the section is what keeps "We rely
    on your support" out of every book blurb."""
    page = (
        '<html><body><main><article class="ebook">'
        '<h1 property="schema:name">A Book</h1>'
        '<section id="description"><h2>Description</h2>'
        '<aside class="donation"><p>We rely on your support to help us keep '
        "producing beautiful, free ebooks.</p></aside>"
        '<div property="schema:description">'
        "<p>A quiet novel about a long winter.</p>"
        "</div></section></article></main></body></html>"
    )
    series, _ = parse_book(page, "", "a-writer/a-book")
    assert series is not None
    assert series.description == "A quiet novel about a long winter."
    assert "rely on your support" not in series.description


def test_parse_toc_is_reading_order_and_skips_production_boilerplate():
    chapters = parse_toc(_load("toc_frankenstein.xhtml"), SERIES_KEY)
    assert len(chapters) == 33
    slugs = [chapter.id for chapter in chapters]
    # Real front matter is kept; Standard Ebooks' own production furniture
    # is not — "Uncopyright" must never sit after the last chapter.
    assert slugs[0] == "introduction"
    assert "preface" in slugs
    assert not NON_READING_SLUGS.intersection(slugs)
    assert "titlepage" not in slugs and "colophon" not in slugs
    # Numbering is ToC POSITION, contiguous from 1, in document order.
    assert [chapter.number for chapter in chapters] == [
        float(n) for n in range(1, 34)
    ]
    assert all(chapter.series_id == SERIES_KEY for chapter in chapters)
    assert all(chapter.page_count == 0 for chapter in chapters)


def test_parse_toc_ignores_the_landmarks_nav():
    """The contents document carries a SECOND <nav> ("landmarks") that
    re-links the first chapter. Parsing the whole page instead of
    ``<nav id="toc">`` would emit that chapter twice."""
    chapters = parse_toc(_load("toc_christmas_carol.xhtml"), CAROL_KEY)
    slugs = [chapter.id for chapter in chapters]
    assert slugs == [
        "preface",
        "chapter-1",
        "chapter-2",
        "chapter-3",
        "chapter-4",
        "chapter-5",
    ]
    assert slugs.count("chapter-1") == 1
    assert 'id="landmarks"' in _load("toc_christmas_carol.xhtml")


def test_toc_titles_are_tightened_around_inline_markup():
    """ToC labels wrap numerals in a <span> ("Stave <span>I</span>: Marley's
    Ghost"); stripping tags naively leaves "Stave I : Marley's Ghost"."""
    chapters = parse_toc(_load("toc_christmas_carol.xhtml"), CAROL_KEY)
    assert chapters[1].title == "Stave I: Marley’s Ghost"
    assert " :" not in chapters[1].title


def test_chapter_numbering_follows_the_toc_not_the_slug():
    """``letter-4`` and ``chapter-4`` are different documents in the same
    book: a number parsed out of the slug would collide. Position wins."""
    chapters = parse_toc(_load("toc_frankenstein.xhtml"), SERIES_KEY)
    by_slug = {chapter.id: chapter.number for chapter in chapters}
    assert by_slug["letter-4"] != by_slug["chapter-4"]
    assert by_slug["chapter-1"] > by_slug["letter-4"]


# --- chapter text -----------------------------------------------------------


def test_parse_chapter_page_paragraphs_are_plain_text():
    text = parse_chapter_page(_load("chapter_frankenstein_1.xhtml"))
    assert text is not None
    assert text.title == "Chapter I"
    assert len(text.paragraphs) > 5
    assert text.word_count > 1000
    joined = "\n".join(text.paragraphs)
    assert "I am by birth a Genevese" in joined
    assert "<" not in joined
    assert "stylesheet" not in joined
    # Left None on purpose — the ToC position is authoritative and the novel
    # service backfills it from the chapter list.
    assert text.chapter_number is None


def test_chapter_body_excludes_site_chrome_and_the_honeypot():
    """Standard Ebooks opens every page's <header> with a hidden link reading
    "Following this link will ban your IP for 24 hours", and closes with
    previous/next footer links. Both are siblings of <main>, so the slice
    drops them structurally — a parser widened past <main> would read that
    ban warning aloud in the middle of the book."""
    html = _load("chapter_frankenstein_1.xhtml")
    # Prove the capture really contains the chrome (otherwise this passes
    # vacuously against a re-captured page).
    assert "ban your IP for 24 hours" in html
    assert 'rel="next"' in html and "Table of contents" in html

    text = parse_chapter_page(html)
    joined = " ".join(text.paragraphs).lower()
    assert "ban your ip" not in joined
    assert "honeypot" not in joined
    assert "table of contents" not in joined
    assert "previous:" not in joined and "next:" not in joined


def test_chapter_body_drops_its_own_heading():
    """The document opens with its own title ("Chapter I"). Keeping it would
    make every chapter start by reading its own name aloud — and TTS is the
    reason this pipeline stores plain text at all."""
    text = parse_chapter_page(_load("chapter_frankenstein_1.xhtml"))
    assert text.paragraphs[0].startswith("I am by birth a Genevese")
    assert "Chapter I" not in text.paragraphs[:2]


def test_chapter_body_drops_an_hgroup_heading_with_a_subtitle():
    """A Christmas Carol's heading is an <hgroup> whose subtitle is a <p>, so
    "first heading" cannot be decided by looking for the first <p>."""
    html = _load("chapter_christmas_carol_1.xhtml")
    assert "<hgroup>" in html
    text = parse_chapter_page(html)
    assert text.title == "Stave I: Marley’s Ghost"
    assert text.paragraphs[0].startswith("Marley was dead, to begin with.")
    assert "Marley’s Ghost" not in text.paragraphs[0]
    assert text.word_count > 5000


def test_heading_inside_the_body_is_kept():
    """Only a heading that OPENS the chapter is its own title. A heading
    further in is part of the text (letters, section breaks, poem titles)."""
    page = (
        "<html><head><title>A Book - Chapter I</title></head><body>"
        "<header><a href='/honeypot' hidden='hidden'>Following this link will "
        "ban your IP for 24 hours</a></header>"
        '<main epub:type="bodymatter"><section id="chapter-1">'
        "<h2>Chapter I</h2>"
        "<p>The letter arrived on a Tuesday.</p>"
        "<h3>To My Dear Sister</h3>"
        "<p>I write to you from Archangel.</p>"
        "</section></main></body></html>"
    )
    text = parse_chapter_page(page)
    assert text is not None
    assert text.title == "Chapter I"
    assert text.paragraphs == (
        "The letter arrived on a Tuesday.",
        "To My Dear Sister",
        "I write to you from Archangel.",
    )


def test_chapter_page_without_a_main_element_does_not_parse():
    assert parse_chapter_page("<html><body><p>orphaned</p></body></html>") is None
    assert parse_chapter_page("<html><body><main></main></body></html>") is None


# --- connector plumbing -----------------------------------------------------


@pytest.fixture
def connector() -> StandardEbooksConnector:
    return StandardEbooksConnector()


def test_connector_declares_novel_contract(connector):
    assert connector.CONTENT_KIND == "novel"
    assert connector.content_kind == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.is_mature is False
    assert connector.get_chapter_pages("anything") == []
    assert connector.find_page("anything") is None
    assert connector.allowed_image_hosts == frozenset({"standardebooks.org"})


def test_connector_series_and_chapters_share_one_pair_of_fetches(connector):
    calls: list[str] = []

    def fake_get_text(path, *, params=None):
        calls.append(path)
        return (
            _load("toc_frankenstein.xhtml")
            if path.endswith("/text")
            else _load("book_frankenstein.html")
        )

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)

    assert series is not None and series.title == "Frankenstein"
    assert len(chapters) == 33
    # The second call is served from the cache: a detail view costs the book
    # page plus the contents document ONCE, not once per accessor.
    assert calls == [f"/ebooks/{SERIES_KEY}", f"/ebooks/{SERIES_KEY}/text"]


def test_connector_chapter_text_reads_the_chapter_document(connector):
    seen: dict[str, object] = {}

    def fake_get_text(path, *, params=None):
        seen["path"] = path
        return _load("chapter_frankenstein_1.xhtml")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        text = connector.chapter_text(SERIES_KEY, CHAPTER_KEY)

    assert seen["path"] == f"/ebooks/{SERIES_KEY}/text/{CHAPTER_KEY}"
    assert text is not None
    assert text.title == "Chapter I"
    assert text.paragraphs


def test_connector_browse_sends_the_selected_sort(connector):
    seen: dict[str, object] = {}

    def fake_get_text(path, *, params=None):
        seen["path"] = path
        seen["params"] = params
        return _load("browse_p1.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        listing = connector.get_series_list(3, sort="popularity")

    assert seen["path"] == "/ebooks"
    assert seen["params"] == {"page": 3, "per-page": 48, "sort": "popularity"}
    assert listing.items


def test_connector_search_falls_back_to_browse_when_query_is_blank(connector):
    seen: dict[str, object] = {}

    def fake_get_text(path, *, params=None):
        seen["params"] = params
        return _load("browse_p1.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.search_series("   ", 1)

    assert "query" not in seen["params"]


def test_connector_chapter_text_rejects_a_non_english_page(connector):
    """The catalog is English, but a translated work's front matter can quote
    the original at length; caching that would pin garbage for a week."""
    page = (
        "<html><head><title>A Book - Chapter I</title></head>"
        '<body><main><section><h2>Chapter I</h2>'
        "<p>他們在月光下等待著那個人的消息。這是一個漫長而寒冷的夜晚，"
        "沒有人願意先開口說話，只有風聲在山谷之間不停地迴盪著。"
        "天亮之前，他們必須做出最後的決定。</p></section></main></body></html>"
    )
    with patch.object(connector._http, "get_text", return_value=page):
        assert connector.chapter_text(SERIES_KEY, CHAPTER_KEY) is None


def test_connector_404_is_clean_not_found_in_the_shared_clients_real_shape(connector):
    """The shared client re-raises a 404 with ``status_code=None`` and only
    httpx's message text — the connector must recognise THAT shape, not a
    ``status_code == 404`` that never occurs (dead-check regression)."""
    real_shape = ConnectorHttpError(
        "Client error '404 Not Found' for url "
        "'https://standardebooks.org/ebooks/nobody/no-such-book'",
        status_code=None,
    )

    with patch.object(connector._http, "get_text", side_effect=real_shape):
        assert connector.get_series("nobody/no-such-book") is None
        assert connector.get_chapters("nobody/no-such-book") == []
        assert connector.chapter_text("nobody/no-such-book", "chapter-1") is None


def test_connector_non_404_errors_still_raise(connector):
    boom = ConnectorHttpError("Retryable HTTP 503", status_code=503)
    with patch.object(connector._http, "get_text", side_effect=boom):
        with pytest.raises(ConnectorHttpError):
            connector.get_series(SERIES_KEY)
        with pytest.raises(ConnectorHttpError):
            connector.chapter_text(SERIES_KEY, CHAPTER_KEY)
