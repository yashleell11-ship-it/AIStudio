"""MangaPanda connector tests.

Fixtures under ``tests/fixtures/mangapanda/`` were captured from the
production VPS (the OVH egress IP), not from a developer laptop, so they are
the exact bytes the deployed backend is served.

Every parse assertion in this file was watched to FAIL against a deliberately
broken selector before being accepted — see the connector report for the
recorded evidence.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.mangapanda.connector import (
    MangaPandaConnector,
    _sniff_image_media_type,
)
from connectors.mangapanda.mappers import (
    listing_path,
    genre_path,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_search_results,
    parse_series_detail,
    parse_series_list,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mangapanda"

SERIES_ID = "naruto-gaiden-the-seventh-hokage_113"
CHAPTER_ID = f"{SERIES_ID}/chapter-10"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def connector() -> MangaPandaConnector:
    return MangaPandaConnector()


# --------------------------------------------------------------------------
# Listings
# --------------------------------------------------------------------------


def test_parse_popular_listing_reads_full_cards():
    listing = parse_series_list(_load("browse_popular_page1.html"), page=1)

    assert len(listing.items) == 30
    assert listing.has_more is True

    first = listing.items[0]
    assert first.id == "one-piece_122"
    assert first.title == "One Piece"
    assert first.cover_url is not None
    assert "mghcdn.com" in first.cover_url
    assert first.author is not None and "Oda" in first.author
    assert first.status == "Ongoing"
    assert "Action" in first.genres

    # Every card must carry an id and a title, or the browse grid renders
    # blank tiles that cannot be opened.
    assert all(item.id and item.title for item in listing.items)


def test_listing_card_titles_are_not_slugs():
    """The heading anchor text, not the URL slug, is the display title."""
    listing = parse_series_list(_load("browse_popular_page1.html"), page=1)
    titles = {item.id: item.title for item in listing.items}
    assert titles["one-piece_122"] == "One Piece"
    assert titles["kimetsu-no-yaiba_106"] == "Kimetsu no Yaiba"
    # A slug leaking through as the title is the specific failure this guards.
    assert not any(item.title == item.id for item in listing.items)


def test_completed_series_status_is_read_from_the_card():
    listing = parse_series_list(_load("browse_popular_page1.html"), page=1)
    by_id = {item.id: item for item in listing.items}
    assert by_id["kimetsu-no-yaiba_106"].status == "Completed"
    assert by_id["one-piece_122"].status == "Ongoing"


def test_listing_pages_differ_and_report_has_more():
    page1 = parse_series_list(_load("browse_popular_page1.html"), page=1)
    page3 = parse_series_list(_load("browse_popular_page3.html"), page=3)

    assert page3.items[0].id == "world-trigger_121"
    assert page1.items[0].id != page3.items[0].id
    # Disjoint content proves pagination is really being followed rather than
    # the same first page being re-parsed under a different page number.
    assert set(i.id for i in page1.items).isdisjoint(i.id for i in page3.items)
    assert page3.page == 3
    assert page3.has_more is True


def test_updates_and_genre_listings_parse():
    updates = parse_series_list(_load("browse_updates_page1.html"), page=1)
    genre = parse_series_list(_load("genre_action_page1.html"), page=1)

    assert len(updates.items) == 30
    assert len(genre.items) == 30
    assert updates.items[0].id == "lost-man"
    assert genre.items[0].id == "onepunch-man_119"
    # Different views must not collapse onto the same list.
    assert updates.items[0].id != genre.items[0].id


def test_browse_modes_map_to_distinct_site_paths():
    paths = [listing_path(1, sort=mode) for mode in
             ("default", "popular", "added", "completed", "alphabetical")]
    assert paths == ["/updates", "/popular", "/new", "/completed", "/search"]
    assert len(set(paths)) == 5
    # Page 2+ uses the site's /page/N form, never a ?page= query (which the
    # site silently ignores, serving page 1 again).
    assert listing_path(2, sort="popular") == "/popular/page/2"
    assert listing_path(3, sort="default") == "/updates/page/3"
    assert genre_path("action", 2) == "/genre/action/page/2"
    assert genre_path("action", 1) == "/genre/action"


def test_connector_requests_the_paged_path(connector: MangaPandaConnector):
    html = _load("browse_popular_page1.html")
    seen: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        seen.append((path, params))
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        connector.get_series_list(1, sort="popular")
        connector.get_series_list(2, sort="popular")

    assert seen == [("/popular", None), ("/popular/page/2", None)]


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------


def test_search_parses_matching_series():
    listing = parse_search_results(_load("search_naruto.html"), page=1)
    ids = [item.id for item in listing.items]

    assert ids == [
        "naruto_113",
        "boruto-naruto-next-generations_115",
        "naruto-gaiden-the-seventh-hokage_113",
        "road-to-naruto-the-movie_111",
    ]
    # Search answers on one page; claiming otherwise makes the UI request a
    # page 2 that comes back identical.
    assert listing.has_more is False


def test_search_with_no_matches_is_empty_not_a_carousel():
    """The no-results page still renders promo carousels of other series.

    Those carousels are not ``media-manga`` cards, so an empty result must
    stay empty rather than filling with unrelated popular titles.
    """
    listing = parse_search_results(_load("search_empty.html"), page=1)
    assert listing.items == []
    assert listing.total == 0
    assert listing.has_more is False


def test_search_sends_the_query_parameter(connector: MangaPandaConnector):
    html = _load("search_naruto.html")
    seen: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        seen.append((path, params))
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        listing = connector.search_series("naruto", 1)

    assert seen == [("/search", {"q": "naruto"})]
    assert listing.items[0].id == "naruto_113"


# --------------------------------------------------------------------------
# Series detail
# --------------------------------------------------------------------------


def test_parse_series_detail_metadata():
    series = parse_series_detail(_load("series_naruto_gaiden.html"), SERIES_ID)

    assert series is not None
    assert series.title == "Naruto Gaiden: The Seventh Hokage"
    assert series.author == "Kishimoto Masashi"
    assert series.artist == "Kishimoto Masashi"
    assert series.status == "Ongoing"
    assert series.cover_url == (
        "https://thumb.mghcdn.com/mr/naruto-gaiden-the-seventh-hokage.jpg"
    )
    assert series.description is not None
    assert "spin-off sequel" in series.description
    assert series.canonical_path == f"/manga/{SERIES_ID}"


def test_series_title_excludes_alternative_titles():
    """The <h1> nests alternative titles in a <small> and a "Hot" badge in an
    <a>. Both must be stripped, or the title becomes a run-on of every
    alternate romanization the series has ever had."""
    series = parse_series_detail(_load("series_naruto_gaiden.html"), SERIES_ID)
    assert series is not None
    assert series.title == "Naruto Gaiden: The Seventh Hokage"
    assert "Nanadaime" not in series.title
    assert "Scarlet Spring" not in series.title
    assert "Hot" not in series.title


def test_series_genres_come_from_the_header_not_the_page_footer():
    """Every series page ends with a "Popular Manga Updates" carousel whose
    cards carry their own genre chips. Reading genres document-wide pulls
    those in, so the header slice is what keeps them out."""
    series = parse_series_detail(_load("series_naruto_gaiden.html"), SERIES_ID)
    assert series is not None
    assert series.genres == (
        "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Shounen",
    )
    # The carousel below carries genres this series does not have.
    assert "Sci-fi" not in series.genres


# --------------------------------------------------------------------------
# Chapters
# --------------------------------------------------------------------------


def test_parse_chapters_from_the_series_page():
    chapters = parse_chapters(_load("series_naruto_gaiden.html"), SERIES_ID)

    assert len(chapters) == 21
    assert all(chapter.series_id == SERIES_ID for chapter in chapters)
    assert chapters[0].id == f"{SERIES_ID}/chapter-1"
    assert chapters[0].number == 1
    assert chapters[0].title == "Uchiha Sarada"
    assert chapters[-1].id == f"{SERIES_ID}/chapter-10.5"
    assert chapters[-1].number == 10.5


def test_chapters_are_ordered_ascending_and_keep_decimals():
    chapters = parse_chapters(_load("series_naruto_gaiden.html"), SERIES_ID)
    numbers = [chapter.number for chapter in chapters]

    assert numbers == sorted(numbers)
    # Site numbering includes .1 full-colour releases and a 10.5 special;
    # truncating those to ints collapses distinct chapters onto each other.
    assert 1.1 in numbers
    assert 10.5 in numbers
    assert len(set(numbers)) == len(numbers)


def test_chapter_rows_do_not_leak_other_series():
    """The series page also lists other series' newest chapters in its
    sidebar and carousel; those rows must not become chapters of this series."""
    chapters = parse_chapters(_load("series_naruto_gaiden.html"), SERIES_ID)
    assert chapters
    assert all(chapter.id.startswith(f"{SERIES_ID}/") for chapter in chapters)
    assert not any("one-piece" in chapter.id for chapter in chapters)


def test_alternate_edition_row_stores_the_canonical_key():
    """Rows that also have a full-colour edition render two anchors under one
    displayed number, and the alternate's href carries an unrelated internal
    id (chapter-121113.5 under a "#9.1" heading). Storing that id would send
    the reader to a different chapter than the number promises."""
    chapters = parse_chapters(_load("series_naruto_gaiden.html"), SERIES_ID)
    by_number = {chapter.number: chapter.id for chapter in chapters}

    assert by_number[9.1] == f"{SERIES_ID}/chapter-9.1"
    assert not any("121113" in chapter.id for chapter in chapters)


def test_chapters_carry_release_dates():
    chapters = parse_chapters(_load("series_naruto_gaiden.html"), SERIES_ID)
    dated = [chapter for chapter in chapters if chapter.release_date]
    assert len(dated) == len(chapters)
    assert chapters[-1].release_date == "02-28-2026"


# --------------------------------------------------------------------------
# Chapter pages
# --------------------------------------------------------------------------


def test_parse_chapter_pages():
    pages = parse_chapter_pages(_load("chapter_naruto_gaiden_10.html"), CHAPTER_ID)

    assert len(pages) == 6
    assert [page.number for page in pages] == [1, 2, 3, 4, 5, 6]
    assert all(page.chapter_id == CHAPTER_ID for page in pages)
    assert pages[0].remote_url == (
        "https://imgx.mghcdn.com/naruto-gaiden-the-seventh-hokage/10/1.jpg"
    )
    assert all("imgx.mghcdn.com" in (page.remote_url or "") for page in pages)


def test_chapter_pages_exclude_carousel_thumbnails():
    """The reader page ends with cover-art carousels on the same CDN. Page
    images end in a numeric filename (.../10/3.jpg); covers end in a title
    slug (.../mr/kingdom.jpg), which is what separates them."""
    pages = parse_chapter_pages(_load("chapter_naruto_gaiden_10.html"), CHAPTER_ID)
    assert all("thumb.mghcdn.com" not in (page.remote_url or "") for page in pages)
    assert all("/mr/" not in (page.remote_url or "") for page in pages)


def test_page_ids_round_trip_through_the_chapter_key():
    """Chapter keys contain slashes and dots, so page ids must still split
    back cleanly — find_page depends on it."""
    pages = parse_chapter_pages(_load("chapter_naruto_gaiden_10.html"), CHAPTER_ID)
    for page in pages:
        assert page_id_chapter_id(page.id) == CHAPTER_ID
    assert page_id_chapter_id("no-colon-here") is None


def test_find_page_resolves_a_single_page(connector: MangaPandaConnector):
    html = _load("chapter_naruto_gaiden_10.html")

    with patch.object(connector._http, "get_text", return_value=html):
        page = connector.find_page(f"{CHAPTER_ID}:4")

    assert page is not None
    assert page.number == 4
    assert page.remote_url.endswith("/10/4.jpg")


# --------------------------------------------------------------------------
# Efficiency: the behaviour that makes this source fast
# --------------------------------------------------------------------------


def test_series_detail_and_chapters_share_one_fetch(connector: MangaPandaConnector):
    """Opening a series must cost ONE request.

    The metadata and the complete chapter list live in the same document, and
    it is the largest one this source serves (~650KB for a long series).
    Fetching it once per stage would download that twice on every series open
    — the exact anti-pattern already fixed on other connectors here.
    """
    html = _load("series_naruto_gaiden.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        series = connector.get_series(SERIES_ID)
        chapters = connector.get_chapters(SERIES_ID)

    assert series is not None
    assert len(chapters) == 21
    assert calls == [f"/manga/{SERIES_ID}"], f"expected 1 fetch, got {calls}"


def test_chapters_first_also_costs_one_fetch(connector: MangaPandaConnector):
    """The reverse order must be just as cheap — the reader calls
    get_chapters before get_series."""
    html = _load("series_naruto_gaiden.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        chapters = connector.get_chapters(SERIES_ID)
        series = connector.get_series(SERIES_ID)

    assert len(chapters) == 21
    assert series is not None
    assert calls == [f"/manga/{SERIES_ID}"]


def test_series_carries_chapter_count_and_latest(connector: MangaPandaConnector):
    html = _load("series_naruto_gaiden.html")
    with patch.object(connector._http, "get_text", return_value=html):
        series = connector.get_series(SERIES_ID)

    assert series is not None
    assert series.chapter_count == 21
    assert series.latest_chapter == "Chapter 10.5"


def test_chapter_pages_are_cached(connector: MangaPandaConnector):
    html = _load("chapter_naruto_gaiden_10.html")
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None):
        calls.append(path)
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        first = connector.get_chapter_pages(CHAPTER_ID)
        second = connector.get_chapter_pages(CHAPTER_ID)

    assert first == second
    assert calls == [f"/chapter/{CHAPTER_ID}"]


def test_page_count_is_backfilled_into_the_chapter_list(connector: MangaPandaConnector):
    """The series page has no per-chapter page counts, so chapters start at
    0. Once a chapter has been read its real count must show up in the list
    rather than the reader re-deriving it."""
    series_html = _load("series_naruto_gaiden.html")
    chapter_html = _load("chapter_naruto_gaiden_10.html")

    def fake_get_text(path: str, *, params=None):
        return chapter_html if path.startswith("/chapter/") else series_html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        before = {c.id: c.page_count for c in connector.get_chapters(SERIES_ID)}
        connector.get_chapter_pages(CHAPTER_ID)
        after = {c.id: c.page_count for c in connector.get_chapters(SERIES_ID)}

    assert before[CHAPTER_ID] == 0
    assert after[CHAPTER_ID] == 6


# --------------------------------------------------------------------------
# Image proxying
# --------------------------------------------------------------------------


def test_image_media_type_is_sniffed_from_the_bytes():
    """imgx.mghcdn.com serves real JPEG bytes for every .png page URL and
    labels them image/png. That is a valid image type, so the proxy passes it
    through unchanged and a strict client is handed a JPEG asserted to be a
    PNG under nosniff. The magic number must win."""
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32
    assert _sniff_image_media_type(jpeg, "image/png") == "image/jpeg"

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    assert _sniff_image_media_type(png, "image/png") == "image/png"

    webp = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 16
    assert _sniff_image_media_type(webp, "application/octet-stream") == "image/webp"

    # Unrecognisable bytes fall back to a declared image type, else to a type
    # the proxy will refuse to serve as an image.
    assert _sniff_image_media_type(b"\x00" * 16, "image/webp") == "image/webp"
    assert _sniff_image_media_type(b"\x00" * 16, "text/html") == "application/octet-stream"


def test_fetch_proxied_image_relabels_the_response(connector: MangaPandaConnector):
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32
    with patch.object(connector._http, "get_bytes", return_value=("image/png", jpeg)):
        media_type, body = connector.fetch_proxied_image(
            "https://imgx.mghcdn.com/kingdom/886/1.png"
        )
    assert media_type == "image/jpeg"
    assert body == jpeg


def test_allowed_image_hosts_cover_both_cdns_and_reject_lookalikes(
    connector: MangaPandaConnector,
):
    from connectors.http.redirect_policy import host_matches_allowlist

    allowed = connector.allowed_image_hosts
    assert host_matches_allowlist("imgx.mghcdn.com", allowed)
    assert host_matches_allowlist("thumb.mghcdn.com", allowed)
    # The dot boundary matters: a lookalike domain must not pass.
    assert not host_matches_allowlist("evilmghcdn.com", allowed)
    assert not host_matches_allowlist("mghcdn.com.evil.test", allowed)


def test_connector_identity(connector: MangaPandaConnector):
    assert connector.source_type == "mangapanda"
    assert connector.display_name == "MangaPanda"
    assert connector.is_browsable is True
    assert connector.is_mature is False
    assert connector.content_kind == "manga"
    assert len(connector.list_genres()) == 60
