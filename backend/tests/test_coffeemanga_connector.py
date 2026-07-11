"""Offline unit tests for the CoffeeManga (Madara) connector.

These load the committed fixtures and monkeypatch the HTTP client, so no
network is touched. The shared end-to-end contract lives in
``tests/test_connector_contracts.py``; this file adds focused coverage of the
coffeemanga-specific parsing quirks.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from connectors.coffeemanga import mappers
from connectors.coffeemanga.connector import CoffeeMangaConnector
from connectors.registry import create_connector, list_installed_connectors

FIXTURES = Path(__file__).parent / "fixtures" / "coffeemanga"
SERIES_ID = "the-abandoned-princes-ghost-bride"
CHAPTER_ID = f"{SERIES_ID}/chapter-1"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@contextmanager
def _mock_http(connector: CoffeeMangaConnector):
    browse_latest = _fixture("browse_latest.html")
    browse_popular = _fixture("browse_popular.html")
    browse_page2 = _fixture("browse_page2.html")
    search_html = _fixture("search.html")
    series_detail = _fixture("series_detail.html")
    chapter_reader = _fixture("chapter_reader.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search_html
        if path == f"/manga/{SERIES_ID}/":
            return series_detail
        if path == f"/manga/{CHAPTER_ID}/":
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


# --- Focused parser-level tests (no connector/HTTP) ---------------------------


def test_reader_images_strip_leading_space_and_include_eager_and_lazy():
    pages = mappers.parse_chapter_pages(_fixture("chapter_reader.html"), CHAPTER_ID)
    # 2 eager (jpg) + 3 lazy (webp) = 5; the leading-space quirk must not drop
    # the eager pages, and data: placeholders must be ignored.
    assert len(pages) == 5
    assert [p.number for p in pages] == [1, 2, 3, 4, 5]
    for page in pages:
        assert page.remote_url is not None
        assert not page.remote_url.startswith(" "), "leading space not stripped"
        assert page.remote_url.startswith("https://coffeemanga.ink/")
        assert "data:image" not in page.remote_url
    assert pages[0].remote_url.endswith("1_result.jpg")  # eager
    assert pages[2].remote_url.endswith("3_result.webp")  # lazy


def test_search_returns_series_not_chapter_links():
    listing = mappers.parse_search_results(_fixture("search.html"), page=1, query="abandoned")
    ids = [s.id for s in listing.items]
    assert SERIES_ID in ids
    # A chapter link (…/chapter-22/) lives in the same result block; it must not
    # leak in as a series id.
    assert all("chapter-" not in sid for sid in ids)
    assert all(item.title and item.cover_url for item in listing.items)


def test_series_detail_metadata_parsed():
    series = mappers.parse_series_detail(_fixture("series_detail.html"), SERIES_ID)
    assert series is not None
    assert "Abandoned Prince" in series.title
    assert series.author == "HYEONSOL"
    assert series.artist == "HYEONSOL"
    assert series.status == "OnGoing"
    assert series.genres == ("Drama", "Fantasy", "Romance")
    assert series.cover_url and series.cover_url.startswith("https://coffeemanga.ink/")
    assert series.description and "abandoned prince" in series.description.lower()


def test_chapters_ascending_with_decimal_side_chapter():
    chapters = mappers.parse_chapters(_fixture("series_detail.html"), SERIES_ID)
    numbers = [c.number for c in chapters]
    assert numbers == sorted(numbers)
    by_seg = {c.id.split("/")[-1]: c for c in chapters}
    assert by_seg["chapter-10-5"].number == 10.5
    # decimal sorts between 10 and 11
    order = [c.id.split("/")[-1] for c in chapters]
    assert order.index("chapter-10") < order.index("chapter-10-5") < order.index("chapter-11")


# --- Connector end-to-end (mocked HTTP) ---------------------------------------


def test_connector_browse_search_read_flow():
    connector = CoffeeMangaConnector()
    with _mock_http(connector):
        latest = connector.get_series_list(1, sort="default")
        assert latest.items and latest.items[0].id == SERIES_ID
        popular = connector.get_series_list(1, sort="popular")
        assert popular.items[0].id != latest.items[0].id

        search = connector.search_series("abandoned", 1)
        assert any(s.id == SERIES_ID for s in search.items)

        series = connector.get_series(SERIES_ID)
        assert series is not None and series.chapter_count == 13
        assert series.latest_chapter  # populated from last chapter

        chapters = connector.get_chapters(SERIES_ID)
        assert len(chapters) == 13

        pages = connector.get_chapter_pages(CHAPTER_ID)
        assert len(pages) == 5
        assert connector.find_page(pages[0].id) == pages[0]


def test_registry_lists_coffeemanga():
    connector = create_connector("coffeemanga")
    assert isinstance(connector, CoffeeMangaConnector)
    assert connector.is_mature is False
    names = {d.source_type for d in list_installed_connectors(browsable_only=True)}
    assert "coffeemanga" in names


# --- Regression guards for the review hardening -------------------------------


def test_card_cover_prefers_data_src_for_lazy_thumbnails():
    # A lazy-loaded card: real URL in data-src, src is a data: placeholder. The
    # cover must resolve to the real URL, not the placeholder (which the image
    # proxy would reject as a non-https scheme).
    html = (
        '<div class="page-item-detail manga"><div class="item-thumb">'
        '<a href="https://coffeemanga.ink/manga/lazy-series/" title="Lazy Series">'
        '<img src="data:image/gif;base64,PLACEHOLDER" '
        'data-src=" https://coffeemanga.ink/covers/lazy.webp"></a></div></div>'
    )
    cards = mappers.parse_series_cards(html)
    assert len(cards) == 1
    assert cards[0].id == "lazy-series"
    assert cards[0].cover_url == "https://coffeemanga.ink/covers/lazy.webp"


def test_coverless_card_does_not_borrow_next_cards_cover():
    # Two cards; the first has no <img>. It must not steal the second card's
    # cover, and the second card must still appear.
    html = (
        '<div class="page-item-detail"><div class="item-thumb">'
        '<a href="https://coffeemanga.ink/manga/no-cover/" title="No Cover"></a></div></div>'
        '<div class="page-item-detail"><div class="item-thumb">'
        '<a href="https://coffeemanga.ink/manga/has-cover/" title="Has Cover">'
        '<img src="https://coffeemanga.ink/covers/has.jpg"></a></div></div>'
    )
    cards = mappers.parse_series_cards(html)
    covers = {c.id: c.cover_url for c in cards}
    assert [c.id for c in cards] == ["no-cover", "has-cover"]
    assert covers["no-cover"] is None
    assert covers["has-cover"] == "https://coffeemanga.ink/covers/has.jpg"


def test_detail_title_ignores_badge_only_h1_and_falls_back_to_og_title():
    html = (
        '<meta property="og:title" content="Real Title" />'
        '<meta property="og:image" content="https://coffeemanga.ink/covers/x.webp" />'
        '<div class="post-title"><h1><span class="badge">Hot</span></h1></div>'
    )
    series = mappers.parse_series_detail(html, "real-title")
    assert series is not None
    assert series.title == "Real Title"


def test_detail_title_captures_leading_text_before_nested_span():
    html = (
        '<meta property="og:image" content="https://coffeemanga.ink/covers/x.webp" />'
        '<div class="post-title"><h1>Actual Title <span class="alt">altname</span></h1></div>'
    )
    series = mappers.parse_series_detail(html, "actual-title")
    assert series is not None
    assert series.title == "Actual Title"
