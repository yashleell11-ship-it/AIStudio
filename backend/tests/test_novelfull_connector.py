"""Offline tests for the NovelFull novel connector.

Fixtures under ``tests/fixtures/novelfull/`` were captured FROM THE VPS
2026-09-04 (production's exact egress and TLS stack — the probe methodology
in the novels spec §4). The connector is exercised entirely against those
captures by patching ``self._http``; no network.

Two fixture notes:

* ``ajax_chapters.html`` is a head+tail trim of the live
  ``/ajax-chapter-option?novelId=237`` response, which carries all 3956
  options in one shot. The capture keeps options 1-60 and the last 10
  (chapters 3947-3954 plus the two after-stories), so it exercises the same
  parse over a fraction of the bytes. Positions here are therefore 1..70.
* ``chapter_sword_god_1.html`` is the real first chapter (its body repeats
  the title with different punctuation than the header — the dedupe case),
  and ``chapter_sword_god_after_story_2.html`` is the last chapter, whose
  title carries no number at all.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.models import Chapter
from connectors.novelfull.connector import NovelFullConnector, _is_not_found
from connectors.novelfull.mappers import (
    SITE_BASE,
    browse_path,
    chapter_number_from_title,
    chapter_path,
    is_site_junk_line,
    normalize_chapter_key,
    normalize_series_key,
    parse_chapter_options,
    parse_chapter_page,
    parse_novel_id,
    parse_novel_list,
    parse_novel_page,
    series_path,
)

FIXTURES = Path(__file__).parent / "fixtures" / "novelfull"

SERIES_KEY = "reincarnation-of-the-strongest-sword-god"
CHAPTER_KEY = "chapter-1-starting-over.html"
NOVEL_ID = "237"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- identity ---------------------------------------------------------------


def test_series_key_round_trips():
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(f"/{SERIES_KEY}.html") == SERIES_KEY
    assert normalize_series_key(f"{SERIES_KEY}.html") == SERIES_KEY
    assert normalize_series_key(f"https://novelfull.com/{SERIES_KEY}.html") == SERIES_KEY
    # A chapter URL narrows to the series it belongs to.
    assert normalize_series_key(f"/{SERIES_KEY}/{CHAPTER_KEY}") == SERIES_KEY
    assert series_path(SERIES_KEY) == f"/{SERIES_KEY}.html"


def test_chapter_key_round_trips():
    # The key keeps the ".html" the site's own option values carry.
    assert normalize_chapter_key(CHAPTER_KEY) == CHAPTER_KEY
    assert normalize_chapter_key(f"/{SERIES_KEY}/{CHAPTER_KEY}") == CHAPTER_KEY
    assert (
        normalize_chapter_key(f"https://novelfull.com/{SERIES_KEY}/{CHAPTER_KEY}")
        == CHAPTER_KEY
    )
    assert chapter_path(SERIES_KEY, CHAPTER_KEY) == f"/{SERIES_KEY}/{CHAPTER_KEY}"
    # Full URLs on both halves normalize down to the same path.
    assert (
        chapter_path(
            f"https://novelfull.com/{SERIES_KEY}.html",
            f"https://novelfull.com/{SERIES_KEY}/{CHAPTER_KEY}",
        )
        == f"/{SERIES_KEY}/{CHAPTER_KEY}"
    )


def test_browse_paths_match_the_site_nav():
    assert browse_path(None) == "/most-popular"
    assert browse_path("default") == "/most-popular"
    assert browse_path("popular") == "/most-popular"
    assert browse_path("latest") == "/latest-release-novel"
    assert browse_path("garbage") == "/most-popular"
    # "/completed" is a live 404 — the site's nav links "/completed-novel".
    assert browse_path("completed") == "/completed-novel"


def test_chapter_number_from_title_handles_the_separators_the_site_serves():
    assert chapter_number_from_title("Chapter 1 - Starting Over") == 1.0
    assert chapter_number_from_title("Chapter 1979 - Visiting the Tower") == 1979.0
    assert chapter_number_from_title("Chapter 10.5 - Interlude") == 10.5
    # An en dash after "Chapter" (Versatile Mage) and a zero-width space
    # inside it (War Sovereign) both appear live.
    assert chapter_number_from_title("Chapter – 1659 - Are You Out of Your Mind!?") == 1659.0
    assert chapter_number_from_title("Chapter​ 2528 - Du Wei's Trump Card") == 2528.0
    # Doubly-numbered titles take the leading number.
    assert chapter_number_from_title("Chapter 3947 - Chapter 1021 - Five Absolutes") == 3947.0
    # Side stories and afterwords carry no number at all.
    assert chapter_number_from_title("Gentle Snow After Story 2") is None


# --- browse -----------------------------------------------------------------


def test_parse_browse_popular_page_one():
    listing = parse_novel_list(_load("browse_popular.html"), page=1)
    assert len(listing.items) == 20
    assert listing.has_more is True
    assert listing.page == 1
    first = listing.items[0]
    assert first.id == SERIES_KEY
    assert first.title == "Reincarnation Of The Strongest Sword God"
    assert first.author == "Lucky Old Cat"
    assert first.cover_url == (
        f"{SITE_BASE}/uploads/webp/novel/"
        "reincarnation-of-the-strongest-s-4064914555.webp"
    )
    assert first.latest_chapter == "Gentle Snow After Story 2"
    # Every card resolved its own slug, title, cover and author — the row
    # split must not drop or mis-pair any of them.
    assert all(r.id and r.title and r.cover_url and r.author for r in listing.items)


def test_parse_browse_popular_page_two_is_distinct():
    p1 = parse_novel_list(_load("browse_popular.html"), page=1)
    p2 = parse_novel_list(_load("browse_popular_p2.html"), page=2)
    assert len(p2.items) == 20
    assert p2.has_more is True
    assert p2.page == 2
    assert p2.items[0].id == "reverend-insanity"
    assert p2.items[0].author == "Gu Zhen Ren"
    assert not ({r.id for r in p1.items} & {r.id for r in p2.items})


def test_parse_browse_latest():
    listing = parse_novel_list(_load("browse_latest.html"), page=1)
    assert len(listing.items) == 20
    assert listing.has_more is True
    assert listing.items[0].id == "the-mirror-legacy"
    assert listing.items[0].title == "The Mirror Legacy"
    assert listing.items[0].latest_chapter == "Chapter 1716: The Riddle Of Mansion Water (II)"


def test_browse_last_page_reports_no_more():
    """Real pager shape from page 86 of /most-popular (the last page): only
    earlier pages and a "last" link back to 86 — nothing beyond it."""
    html = (
        '<div class="row"><div><img src="/uploads/x.webp" class="cover"></div>'
        '<h3 class="truyen-title"><a href="/some-novel.html" title="Some Novel">'
        "Some Novel</a></h3></div>"
        '<ul class="pagination"><li class=""><a href="/most-popular?page=85">85</a></li>'
        '<li class="active"><a href="/most-popular?page=86">86</a></li>'
        '<li class="next disabled"><span>&gt;</span></li>'
        '<li class="last"><a href="/most-popular?page=86">Last &raquo;</a></li></ul>'
    )
    listing = parse_novel_list(html, page=86)
    assert len(listing.items) == 1
    assert listing.has_more is False


def test_has_more_from_a_next_link_alone():
    """Belt-and-braces alongside the page-number comparison: a live "next"
    li means another page even if no ?page= link is there to compare."""
    html = (
        '<div class="row"><div><img src="/uploads/x.webp" class="cover"></div>'
        '<h3 class="truyen-title"><a href="/some-novel.html" title="Some Novel">'
        "Some Novel</a></h3></div>"
        '<ul class="pagination"><li class="next"><a href="/most-popular/2">&gt;</a>'
        "</li></ul>"
    )
    assert parse_novel_list(html, page=1).has_more is True


def test_browse_drops_broken_rows_without_disturbing_the_others():
    """A card whose link is malformed is dropped; the cards around it keep
    their OWN cover. (Pairing two document-wide sweeps instead would strip
    every cover on the page as soon as the counts stopped matching.)"""
    good = (
        '<div class="row"><div><img src="/uploads/a.webp" class="cover"></div>'
        '<h3 class="truyen-title"><a href="/novel-a.html" title="Novel A">A</a></h3>'
        '<span class="author"><span class="glyphicon glyphicon-pencil"></span> '
        "Writer A</span>"
        '<span class="chapter-text">Chapter 9</span></div>'
    )
    broken = (
        '<div class="row"><div><img src="/uploads/broken.webp" class="cover"></div>'
        '<h3 class="truyen-title"><a href="/genre/Action">no .html href</a></h3>'
        "</div>"
    )
    tail = (
        '<div class="row"><div><img src="/uploads/c.webp" class="cover"></div>'
        '<h3 class="truyen-title"><a href="/novel-c.html" title="Novel C">C</a></h3>'
        "</div>"
    )
    listing = parse_novel_list(good + broken + tail, page=1)
    assert [r.id for r in listing.items] == ["novel-a", "novel-c"]
    assert listing.items[0].cover_url == f"{SITE_BASE}/uploads/a.webp"
    assert listing.items[0].author == "Writer A"
    assert listing.items[0].latest_chapter == "Chapter 9"
    assert listing.items[1].cover_url == f"{SITE_BASE}/uploads/c.webp"
    # The dropped row's cover never leaks onto a surviving card.
    assert all("broken" not in (r.cover_url or "") for r in listing.items)


def test_browse_ignores_non_listing_rows():
    """The header's genre dropdown uses the same <div class="row"> wrapper."""
    html = (
        '<div class="row"><ul class="dropdown-menu">'
        '<li><a href="/genre/Harem" title="Harem">Harem</a></li></ul></div>'
    )
    assert parse_novel_list(html, page=1).items == []


# --- search -----------------------------------------------------------------


def test_parse_search_results():
    listing = parse_novel_list(_load("search_sword_god.html"), page=1)
    assert len(listing.items) == 6
    # Six hits, no pager on the page -> no second page to ask for.
    assert listing.has_more is False
    assert [r.id for r in listing.items[:3]] == [
        SERIES_KEY,
        "chaotic-sword-god",
        "limitless-sword-god",
    ]
    assert listing.items[1].title == "Chaotic Sword God"
    assert listing.items[1].author == "Xin Xing Xiao Yao"
    assert all(r.cover_url for r in listing.items)


# --- novel detail -----------------------------------------------------------


def test_parse_novel_page_metadata():
    series = parse_novel_page(_load("novel_sword_god.html"), SERIES_KEY)
    assert series is not None
    assert series.id == SERIES_KEY
    assert series.title == "Reincarnation Of The Strongest Sword God"
    assert series.author == "Lucky Old Cat"
    assert series.status == "completed"
    assert series.cover_url == (
        f"{SITE_BASE}/uploads/webp/novel/"
        "reincarnation-of-the-strongest-s-4064914555.webp"
    )
    assert series.description and "living game" in series.description
    assert "<" not in series.description  # sanitized plain text


def test_parse_novel_page_takes_only_the_novels_own_genres():
    """The header nav links all ~36 site-wide genres on every page; the
    novel's own five live in the info block's "Genre:" row."""
    series = parse_novel_page(_load("novel_sword_god.html"), SERIES_KEY)
    assert series.genres == ("Action", "Adventure", "Fantasy", "Martial Arts", "Xuanhuan")
    for nav_only in ("Yaoi", "Lolicon", "Smut", "Mecha", "Josei"):
        assert nav_only not in series.genres


def test_parse_novel_id():
    assert parse_novel_id(_load("novel_sword_god.html")) == NOVEL_ID
    assert parse_novel_id("<html>no id here</html>") is None


def test_parse_novel_page_without_title_is_none():
    assert parse_novel_page("<html><body>404</body></html>", SERIES_KEY) is None


# --- chapter list (the one-shot ajax endpoint) -------------------------------


def test_parse_chapter_options_reads_the_whole_select():
    chapters = parse_chapter_options(_load("ajax_chapters.html"), SERIES_KEY)
    assert len(chapters) == _load("ajax_chapters.html").count("<option")
    assert len(chapters) == 70
    assert chapters[0].id == CHAPTER_KEY
    assert chapters[0].title == "Chapter 1 - Starting Over"
    assert chapters[0].series_id == SERIES_KEY
    assert chapters[0].page_count == 0
    # HTML entities in titles are decoded, not passed through.
    assert chapters[13].title == "Chapter 14 - Extraordinary Player's Physique"
    # The capture's tail is the real end of the novel.
    assert chapters[-1].id == "gentle-snow-after-story-2.html"
    assert chapters[-1].title == "Gentle Snow After Story 2"
    assert all(c.series_id == SERIES_KEY for c in chapters)


def test_chapter_numbers_are_list_positions_and_stay_ordered():
    chapters = parse_chapter_options(_load("ajax_chapters.html"), SERIES_KEY)
    numbers = [c.number for c in chapters]
    assert numbers == [float(i) for i in range(1, len(chapters) + 1)]
    assert len(set(numbers)) == len(numbers)
    assert all(b > a for a, b in zip(numbers, numbers[1:]))


def test_unnumbered_entries_never_collide_with_numbered_ones():
    """Emperor's Domination (live, 2026-09-04) opens its chapter list with
    seven "Side Story N" entries ahead of Chapter 1. Numbering from the
    title with a position fallback gave both runs 1..7 — seven duplicate
    chapter numbers on one novel."""
    options = "".join(
        f'<option value="/emperors-domination/side-story-{i}.html">'
        f"Side Story {i}</option>"
        for i in range(1, 8)
    ) + "".join(
        f'<option value="/emperors-domination/chapter-{i}.html">'
        f"Chapter {i} : Three Demon Master ({i})</option>"
        for i in range(1, 8)
    )
    chapters = parse_chapter_options(f"<select>{options}</select>", "emperors-domination")
    assert len(chapters) == 14
    numbers = [c.number for c in chapters]
    assert len(set(numbers)) == 14
    assert numbers == [float(i) for i in range(1, 15)]
    assert chapters[0].title == "Side Story 1"
    assert chapters[7].title == "Chapter 1 : Three Demon Master (1)"


def test_parse_chapter_options_drops_malformed_options():
    html = (
        "<select>"
        '<option value="/slug/real-chapter.html">Chapter 1 - Real</option>'
        '<option value="">Chapter 2 - No value</option>'
        '<option value="/only-one-segment">Chapter 3 - Not a chapter path</option>'
        '<option value="/slug/other.html">Chapter 4 - Also Real</option>'
        "</select>"
    )
    chapters = parse_chapter_options(html, SERIES_KEY)
    assert [c.id for c in chapters] == ["real-chapter.html", "other.html"]
    # Positions renumber over the survivors — no gaps, no duplicates.
    assert [c.number for c in chapters] == [1.0, 2.0]


def test_parse_chapter_options_on_an_empty_select():
    assert parse_chapter_options("<select></select>", SERIES_KEY) == []


# --- chapter text -----------------------------------------------------------


def test_parse_chapter_page():
    text = parse_chapter_page(_load("chapter_sword_god_1.html"))
    assert text is not None
    assert text.title == "Chapter 1 - Starting Over"
    assert text.chapter_number == 1.0
    assert len(text.paragraphs) == 89
    assert text.word_count == 2979
    assert text.paragraphs[-1] == '"God\'s Domain, here I come."'


def test_chapter_body_title_duplicate_is_dropped_despite_punctuation():
    """The <h2> says "Chapter 1 - Starting Over"; the body repeats it as
    "Chapter 1: Starting Over". Only the punctuation differs, so an exact
    string compare leaves the heading sitting in the prose."""
    text = parse_chapter_page(_load("chapter_sword_god_1.html"))
    assert text.paragraphs[0] == "Translator:Hellscythe_"
    joined = " ".join(text.paragraphs)
    assert "Chapter 1: Starting Over" not in joined
    assert "Chapter 1 - Starting Over" not in joined


def test_chapter_without_a_number_in_its_title():
    text = parse_chapter_page(_load("chapter_sword_god_after_story_2.html"))
    assert text.title == "Gentle Snow After Story 2"
    assert text.chapter_number is None  # the service backfills from the list
    assert len(text.paragraphs) == 48
    assert text.paragraphs[0].startswith("Just as Blazing Soul")


@pytest.mark.parametrize(
    "fixture",
    ["chapter_sword_god_1.html", "chapter_sword_god_after_story_2.html"],
)
def test_chapter_paragraphs_are_sanitized_plain_text(fixture):
    text = parse_chapter_page(_load(fixture))
    joined = " ".join(text.paragraphs).lower()
    for junk in (
        "if you find any errors",  # NovelFull's own report-chapter footer
        "report chapter",
        "novelfull",
        "advertisement",
        "freegames.click",
        "adsbygoogle",
        "<div",
        "<p",
        "<script",
        "<iframe",
        "http",
    ):
        assert junk not in joined, junk


def test_site_junk_footer_is_stripped():
    """NovelFull appends this line INSIDE #chapter-content, so the shared
    structural strip and promo blacklist both pass it through."""
    footer = (
        "If you find any errors ( Ads popup, ads redirect, broken links, "
        "non-standard content, etc.. ), Please let us know < report chapter > "
        "so we can fix it as soon as possible."
    )
    assert is_site_junk_line(footer) is True
    assert is_site_junk_line("He found any errors in the ledger and reported them.") is False

    html = (
        '<h2><a class="chapter-title" href="/x/chapter-9.html" '
        'title="Chapter 9 - The Test"><span class="chapter-text">'
        "Chapter 9 - The Test</span></a></h2>"
        '<div id="chapter-content" class="chapter-c">'
        '<div align="center"><iframe src="//ad.a-ads.com/1?size=300x250"></iframe></div>'
        "<p></p><p> Chapter 9: The Test</p>"
        "<p>Shi Feng drew his blade.</p>"
        "<script>evil();</script>"
        '<div class="ad-slot"><ins class="adsbygoogle"></ins>BUY GOLD</div>'
        "<p>The blade answered.</p>"
        f'<div align="left">{footer}</div>'
        "</div>"
    )
    text = parse_chapter_page(html)
    assert text is not None
    assert text.title == "Chapter 9 - The Test"
    assert text.chapter_number == 9.0
    assert text.paragraphs == ("Shi Feng drew his blade.", "The blade answered.")


def test_chapter_content_slice_survives_nested_divs():
    """Ad slots are <div>s nested inside #chapter-content; a naive slice to
    the first </div> would cut the chapter off at the first ad."""
    html = (
        '<div id="chapter-content">'
        "<p>Before the ad.</p>"
        '<div class="banner"><div>junk</div></div>'
        "<p>After the ad.</p>"
        "</div>"
        "<p>Outside the body entirely.</p>"
    )
    text = parse_chapter_page(html)
    assert text.paragraphs == ("Before the ad.", "After the ad.")


def test_chapter_without_content_div_is_none():
    assert parse_chapter_page("<html><body>404 page</body></html>") is None


def test_chapter_with_only_junk_is_none():
    html = (
        '<div id="chapter-content"><div align="left">If you find any errors '
        "( Ads popup, ads redirect ), Please let us know &lt; report chapter "
        "&gt;.</div></div>"
    )
    assert parse_chapter_page(html) is None


# --- connector behavior (patched HTTP) --------------------------------------


@pytest.fixture()
def connector() -> NovelFullConnector:
    return NovelFullConnector()


def test_connector_declares_novel_kind(connector):
    assert connector.source_type == "novelfull"
    assert connector.content_kind == "novel"
    assert connector.CONTENT_KIND == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.is_mature is False
    assert connector.is_browsable is True
    assert "novelfull.com" in connector.allowed_image_hosts


def test_connector_browse_modes_all_resolve_to_a_real_view(connector):
    modes = connector.list_browse_modes()
    assert [m.id for m in modes] == ["default", "latest", "completed"]
    # Every advertised mode maps to a path the site actually serves
    # (verified live from the VPS; "/completed" answered 404).
    assert [browse_path(m.id) for m in modes] == [
        "/most-popular",
        "/latest-release-novel",
        "/completed-novel",
    ]


def test_connector_browse_page_one_sends_no_page_param(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("browse_popular.html")
    ) as get_text:
        listing = connector.get_series_list(1)
    assert get_text.call_args.args[0] == "/most-popular"
    assert get_text.call_args.kwargs["params"] is None
    assert len(listing.items) == 20


def test_connector_browse_page_two(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("browse_popular_p2.html")
    ) as get_text:
        listing = connector.get_series_list(2, sort="latest")
    assert get_text.call_args.args[0] == "/latest-release-novel"
    assert get_text.call_args.kwargs["params"] == {"page": 2}
    assert listing.page == 2
    assert len(listing.items) == 20


def test_connector_search(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("search_sword_god.html")
    ) as get_text:
        listing = connector.search_series("  sword god  ", 1)
    assert get_text.call_args.args[0] == "/search"
    assert get_text.call_args.kwargs["params"] == {"keyword": "sword god"}
    assert len(listing.items) == 6


def test_connector_search_page_two_adds_the_page_param(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("search_sword_god.html")
    ) as get_text:
        connector.search_series("sword god", 3)
    assert get_text.call_args.kwargs["params"] == {"keyword": "sword god", "page": 3}


def test_connector_empty_search_falls_back_to_browse(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("browse_popular.html")
    ) as get_text:
        listing = connector.search_series("   ", 1)
    assert get_text.call_args.args[0] == "/most-popular"
    assert len(listing.items) == 20


def _detail_then_ajax(path: str, **kwargs):
    """Route the two GETs get_series makes to their fixtures."""
    if path == "/ajax-chapter-option":
        assert kwargs["params"] == {"novelId": NOVEL_ID}
        return _load("ajax_chapters.html")
    assert path == f"/{SERIES_KEY}.html"
    return _load("novel_sword_god.html")


def test_connector_get_series_folds_in_the_chapter_list(connector):
    with patch.object(connector._http, "get_text", side_effect=_detail_then_ajax) as get_text:
        series = connector.get_series(SERIES_KEY)
    assert get_text.call_count == 2  # detail once, ajax once
    assert series.title == "Reincarnation Of The Strongest Sword God"
    assert series.chapter_count == 70
    assert series.latest_chapter == "Gentle Snow After Story 2"
    assert series.genres == ("Action", "Adventure", "Fantasy", "Martial Arts", "Xuanhuan")


def test_connector_get_series_then_get_chapters_refetches_nothing(connector):
    with patch.object(connector._http, "get_text", side_effect=_detail_then_ajax) as get_text:
        connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)
    assert get_text.call_count == 2  # both served from the TTL caches
    assert len(chapters) == 70
    assert chapters[0].id == CHAPTER_KEY


def test_connector_get_chapters_alone_fetches_the_detail_page_for_the_novel_id(connector):
    with patch.object(connector._http, "get_text", side_effect=_detail_then_ajax) as get_text:
        chapters = connector.get_chapters(SERIES_KEY)
    assert [c.args[0] for c in get_text.call_args_list] == [
        f"/{SERIES_KEY}.html",
        "/ajax-chapter-option",
    ]
    assert len(chapters) == 70


def test_connector_chapter_text(connector):
    with patch.object(
        connector._http, "get_text", return_value=_load("chapter_sword_god_1.html")
    ) as get_text:
        text = connector.chapter_text(SERIES_KEY, CHAPTER_KEY)
    assert get_text.call_args.args[0] == f"/{SERIES_KEY}/{CHAPTER_KEY}"
    assert text.title == "Chapter 1 - Starting Over"
    assert text.chapter_number == 1.0
    assert len(text.paragraphs) == 89


def test_connector_manga_surface_is_empty(connector):
    assert connector.get_chapter_pages(CHAPTER_KEY) == []
    assert connector.find_page("anything") is None


def test_connector_chapter_text_rejects_non_english(connector):
    cjk = "".join(chr(0x4E00 + i) for i in range(80))
    html = f'<div id="chapter-content"><p>{cjk}</p></div>'
    with patch.object(connector._http, "get_text", return_value=html):
        assert connector.chapter_text(SERIES_KEY, CHAPTER_KEY) is None


def test_connector_chapter_text_unparseable_is_none(connector):
    with patch.object(connector._http, "get_text", return_value="<html>gone</html>"):
        assert connector.chapter_text(SERIES_KEY, CHAPTER_KEY) is None


# --- 404 vs network failure (both shapes verified live from the VPS) --------

# The shared client only sets status_code for RETRYABLE_STATUS, so a real
# 404 arrives carrying httpx's raise_for_status message and status_code
# None. A bare `exc.status_code == 404` test is dead code.
_NOT_FOUND = ConnectorHttpError(
    "Client error '404 Not Found' for url "
    f"'https://novelfull.com/{SERIES_KEY}/chapter-99999999-nope.html'\n"
    "For more information check: https://developer.mozilla.org/..."
)
_RETRYABLE = ConnectorHttpError("Retryable HTTP 503", status_code=503)


def test_is_not_found_matches_both_forms():
    assert _is_not_found(_NOT_FOUND) is True
    assert _is_not_found(ConnectorHttpError("gone", status_code=404)) is True
    assert _is_not_found(_RETRYABLE) is False
    assert _is_not_found(ConnectorHttpError("connection reset")) is False


def test_missing_series_is_none(connector):
    with patch.object(connector._http, "get_text", side_effect=_NOT_FOUND):
        assert connector.get_series("zz-definitely-not-real-xyz") is None
        assert connector.get_chapters("zz-definitely-not-real-xyz") == []


def test_missing_chapter_is_none(connector):
    with patch.object(connector._http, "get_text", side_effect=_NOT_FOUND):
        assert connector.chapter_text(SERIES_KEY, "chapter-99999999-nope.html") is None


def test_chapter_text_network_failure_raises(connector):
    with patch.object(connector._http, "get_text", side_effect=_RETRYABLE):
        with pytest.raises(ConnectorHttpError):
            connector.chapter_text(SERIES_KEY, CHAPTER_KEY)


def test_series_network_failure_raises(connector):
    with patch.object(connector._http, "get_text", side_effect=_RETRYABLE):
        with pytest.raises(ConnectorHttpError):
            connector.get_series(SERIES_KEY)


def test_chapter_list_network_failure_raises_rather_than_caching_emptiness(connector):
    """A transient failure on the ajax endpoint must not be recorded as
    "this novel has no chapters" — it has to reach the source cache so the
    previous list is served stale."""

    def _detail_ok_then_boom(path: str, **kwargs):
        if path == "/ajax-chapter-option":
            raise _RETRYABLE
        return _load("novel_sword_god.html")

    with patch.object(connector._http, "get_text", side_effect=_detail_ok_then_boom):
        with pytest.raises(ConnectorHttpError):
            connector.get_chapters(SERIES_KEY)


def test_chapter_list_404_is_an_empty_list(connector):
    def _detail_ok_then_404(path: str, **kwargs):
        if path == "/ajax-chapter-option":
            raise _NOT_FOUND
        return _load("novel_sword_god.html")

    with patch.object(connector._http, "get_text", side_effect=_detail_ok_then_404):
        assert connector.get_chapters(SERIES_KEY) == []


def test_chapters_are_the_declared_model(connector):
    chapters = parse_chapter_options(_load("ajax_chapters.html"), SERIES_KEY)
    assert all(isinstance(c, Chapter) for c in chapters)
