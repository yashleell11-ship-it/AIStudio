"""Rawkuma connector tests.

Every fixture under ``tests/fixtures/rawkuma/`` was captured FROM THE VPS
(``docker exec manhwamaniacs-backend``), which is the only egress whose TLS
stack and IP reputation match production.

Each parse assertion below was watched to FAIL first against a deliberately
broken selector before being accepted -- see the ``BROKEN SELECTOR`` notes on
the individual tests for which selector was sabotaged to prove it.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.http.redirect_policy import host_matches_allowlist
from connectors.rawkuma.connector import RawkumaConnector, _is_not_found
from connectors.rawkuma.mappers import (
    is_page_image_url,
    listing_params,
    page_id_chapter_id,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list_json,
    rerank_by_title,
    title_relevance_rank,
)
from connectors.registry import list_installed_connectors

FIXTURES = Path(__file__).parent / "fixtures" / "rawkuma"

SERIES_KEY = "kage-no-jitsuryokusha-ni-naritakute"
CHAPTER_KEY = f"{SERIES_KEY}/chapter-84.379864"
RCDN_CHAPTER_KEY = "ottava-chiisana-te-no-pianist/chapter-3.299952"


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _json(name: str):
    return json.loads(_text(name))


@pytest.fixture
def connector() -> RawkumaConnector:
    return RawkumaConnector()


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def test_registry_lists_rawkuma_once_wired():
    """Green after the integrator applies the registration snippet.

    Skipped (not failed) beforehand so this file stays honest in a tree where
    registry.py has not been touched yet -- this connector is forbidden from
    editing it.
    """
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    if "rawkuma" not in browsable:
        pytest.skip("rawkuma not yet registered in connectors/registry.py")
    assert "rawkuma" in browsable


def test_connector_declares_its_contract(connector: RawkumaConnector):
    assert connector.source_type == "rawkuma"
    assert connector.display_name == "Rawkuma"
    assert connector.is_browsable is True
    assert connector.content_kind == "manga"
    assert connector.is_mature is False


# ---------------------------------------------------------------------------
# browse / catalog parsing
# ---------------------------------------------------------------------------


def test_parse_browse_page_yields_full_cards():
    """BROKEN SELECTOR proof: changing the cover lookup in ``series_from_rest``
    from ``inner.get("thumbnail")`` to ``inner.get("thumbnails")`` fails the
    cover assertion; renaming the ``"genre"`` taxonomy match in ``_tax_names``
    fails the genre assertion."""
    listing = parse_series_list_json(_json("browse_page1.json"), page=1)

    assert len(listing.items) == 24
    assert listing.has_more is True

    first = listing.items[0]
    assert first.id == "seijo-no-isan"
    assert first.title == "Seijo no, Isan"
    assert first.cover_url == "https://rawkuma.net/wp-content/uploads/2026/08/i524902.jpg"
    assert first.canonical_path == "/manga/seijo-no-isan/"
    assert first.author == "MUTSUHANA Eiko"
    assert first.genres == ("Fantasy", "Romance", "Shoujo")

    # A catalog card must arrive complete: the whole point of using the REST
    # collection is that no per-title follow-up request is needed to render it.
    assert all(item.cover_url for item in listing.items)
    assert all(item.title and item.id for item in listing.items)
    assert sum(1 for item in listing.items if item.genres) >= 20
    assert sum(1 for item in listing.items if item.status) >= 20


def test_browse_pages_hold_different_series():
    page1 = parse_series_list_json(_json("browse_page1.json"), page=1)
    page2 = parse_series_list_json(_json("browse_page2.json"), page=2)

    ids1 = [item.id for item in page1.items]
    ids2 = [item.id for item in page2.items]
    assert ids1 and ids2
    assert set(ids1).isdisjoint(set(ids2))
    assert page2.page == 2


def test_title_sort_returns_a_genuinely_different_ordering():
    """The three browse modes must not collapse onto one listing -- the exact
    failure mode a sibling connector shipped (every sort hitting the same
    default page). Compares real captured responses, not just request params."""
    latest = parse_series_list_json(_json("browse_page1.json"), page=1)
    alphabetical = parse_series_list_json(_json("browse_title_az.json"), page=1)

    assert latest.items[0].id != alphabetical.items[0].id
    assert set(i.id for i in latest.items[:5]).isdisjoint(
        set(i.id for i in alphabetical.items[:5])
    )


def test_each_browse_mode_requests_a_distinct_rest_ordering():
    orderings = [
        (listing_params(1, sort=mode)["orderby"], listing_params(1, sort=mode).get("order"))
        for mode in ("default", "latest", "title")
    ]
    assert orderings == [("modified", "desc"), ("date", "desc"), ("title", "asc")]
    assert len(set(orderings)) == 3


def test_unknown_sort_falls_back_to_default_rather_than_leaking_upstream():
    assert listing_params(1, sort="popular")["orderby"] == "modified"
    assert listing_params(1, sort=None)["orderby"] == "modified"


def test_genre_browse_filters_by_wordpress_term_id():
    """WP REST filters the genre taxonomy by term ID, not slug; sending the
    slug silently returns the unfiltered catalog."""
    params = listing_params(1, genre="action")
    assert params["genre"] == 2

    listing = parse_series_list_json(_json("browse_genre_action.json"), page=1)
    assert len(listing.items) == 24
    assert all("Action" in item.genres for item in listing.items)


def test_unknown_genre_is_dropped_instead_of_sent_upstream():
    assert "genre" not in listing_params(1, genre="not-a-real-genre")


# ---------------------------------------------------------------------------
# series detail
# ---------------------------------------------------------------------------


def test_parse_series_detail_from_json_ld():
    """BROKEN SELECTOR proof: matching ``"ComicSeriez"`` instead of
    ``"ComicSeries"`` in ``_comic_series_ld`` makes this return None."""
    series = parse_series_detail(_text("series_detail.html"), SERIES_KEY)

    assert series is not None
    assert series.id == SERIES_KEY
    assert series.title == "Kage no Jitsuryokusha ni Naritakute"
    assert series.author == "AIZAWA Daisuke"
    assert series.artist == "SAKANO Anri"
    assert series.status == "Ongoing"
    assert series.cover_url == "https://rawkuma.net/wp-content/uploads/2025/09/i492337.jpg"
    assert "Action" in series.genres and "Shounen" in series.genres
    assert len(series.genres) == 9


def test_series_description_prefers_the_full_body_over_the_clamped_teaser():
    """The page renders the synopsis twice: a clamped teaser that ends in an
    ellipsis, and the full text. Taking the first match gets the teaser."""
    series = parse_series_detail(_text("series_detail.html"), SERIES_KEY)

    assert series is not None
    assert series.description
    assert "Cid Kagenou has a dream" in series.description
    # Text that exists ONLY past the teaser's cut-off point. The teaser stops
    # mid-synopsis and terminates with the escaped ellipsis; picking the first
    # `itemprop="description"` in the document gets that shortened copy.
    assert "he alone is left in the dark" in series.description
    assert not series.description.rstrip().endswith("[…]")
    assert "…" not in series.description
    assert "<p>" not in series.description and "<br" not in series.description


def test_parse_series_detail_returns_none_on_a_non_series_document():
    assert parse_series_detail("<html><body>nothing here</body></html>", SERIES_KEY) is None


# ---------------------------------------------------------------------------
# chapters
# ---------------------------------------------------------------------------


def test_parse_chapters_reads_the_whole_server_rendered_list():
    """BROKEN SELECTOR proof: changing ``CHAPTER_LIST_RE`` to look for
    ``id="chapter-listing"`` returns an empty list and fails every assertion
    here. The count is pinned to the site's own "Chapters (94)" heading."""
    chapters = parse_chapters(_text("series_detail.html"), SERIES_KEY)

    assert len(chapters) == 94
    assert chapters[0].id == f"{SERIES_KEY}/chapter-1.37696"
    assert chapters[0].number == 1.0
    assert chapters[0].title == "Chapter 1"
    assert chapters[-1].id == CHAPTER_KEY
    assert chapters[-1].number == 84.0
    assert chapters[-1].release_date == "2026-08-25T15:44:20Z"
    assert all(chapter.series_id == SERIES_KEY for chapter in chapters)


def test_chapters_are_ordered_by_the_sites_own_numbering():
    chapters = parse_chapters(_text("series_detail.html"), SERIES_KEY)
    numbers = [chapter.number for chapter in chapters]
    # Pinned: an empty parse would satisfy `numbers == sorted(numbers)`.
    assert len(numbers) == 94
    assert numbers == sorted(numbers)


def test_split_chapters_keep_their_decimal_numbering():
    """Rawkuma splits chapters as 82.1 / 82.2. Truncating those to int would
    collapse them onto one another and lose a chapter from the reader."""
    chapters = parse_chapters(_text("series_detail.html"), SERIES_KEY)
    decimals = {c.number: c.title for c in chapters if c.number and 82 <= c.number < 83}
    assert decimals == {82.1: "Chapter 82.1", 82.2: "Chapter 82.2"}


def test_chapter_labels_are_not_polluted_by_trailing_share_markup():
    """The oldest row carries an extra ``<span>Share now</span>``; a loose
    span match picks it up as the chapter title."""
    chapters = parse_chapters(_text("series_detail.html"), SERIES_KEY)
    assert len(chapters) == 94  # an empty parse would pass the `all(...)` below
    assert all(chapter.title.startswith("Chapter ") for chapter in chapters)
    assert "Share now" not in {chapter.title for chapter in chapters}


def test_chapter_keys_stay_opaque_and_belong_to_their_series():
    chapters = parse_chapters(_text("series_detail.html"), SERIES_KEY)
    assert len(chapters) == 94  # an empty parse would pass every `all(...)` below
    assert all(chapter.id.startswith(f"{SERIES_KEY}/chapter-") for chapter in chapters)
    # Keys are stored raw, slashes and all -- never re-encoded or split.
    assert all("/" in chapter.id and "%" not in chapter.id for chapter in chapters)
    assert len({chapter.id for chapter in chapters}) == len(chapters)


# ---------------------------------------------------------------------------
# chapter pages
# ---------------------------------------------------------------------------


def test_parse_chapter_pages_reads_every_image_from_one_document():
    """BROKEN SELECTOR proof: changing ``PAGE_SECTION_RE`` to look for
    ``data-image-datum`` returns zero pages."""
    pages = parse_chapter_pages(_text("chapter_pages.html"), CHAPTER_KEY)

    assert len(pages) == 30
    assert [page.number for page in pages] == list(range(1, 31))
    assert all(page.chapter_id == CHAPTER_KEY for page in pages)
    assert pages[0].remote_url == (
        "https://kuma.kyut.dev/wp-content/scr/k/"
        "kage-no-jitsuryokusha-ni-naritakute-raw/84/1.jpg"
    )
    assert len({page.remote_url for page in pages}) == 30


def test_parse_chapter_pages_handles_the_second_cdn_host():
    """Rawkuma serves page images from two hosts across the catalog; a parser
    pinned to the first one silently returns no pages for the other."""
    pages = parse_chapter_pages(_text("chapter_pages_rcdn.html"), RCDN_CHAPTER_KEY)

    assert len(pages) == 45
    assert pages[0].remote_url.startswith("https://rcdn.kyut.dev/")
    assert pages[-1].number == 45


def test_every_page_host_is_inside_the_image_proxy_allowlist(connector: RawkumaConnector):
    """The image proxy rejects any host outside ``allowed_image_hosts`` before
    it makes a request, so a CDN missing from that set means blank pages."""
    from urllib.parse import urlparse

    allowed = connector.allowed_image_hosts
    urls = [
        page.remote_url
        for name, key in (
            ("chapter_pages.html", CHAPTER_KEY),
            ("chapter_pages_rcdn.html", RCDN_CHAPTER_KEY),
        )
        for page in parse_chapter_pages(_text(name), key)
    ]
    covers = [
        item.cover_url for item in parse_series_list_json(_json("browse_page1.json"), page=1).items
    ]
    assert len(urls) == 75 and len(covers) == 24
    for url in [*urls, *covers]:
        host = urlparse(url).hostname or ""
        assert host_matches_allowlist(host, allowed), host


def test_non_cdn_images_inside_the_reader_are_not_counted_as_pages():
    """Only images from Rawkuma's page CDN are pages.

    A banner or house ad dropped into the reader section would otherwise be
    served as page 1, shifting every real page number by one. Built by
    injecting chrome into the REAL captured document rather than a hand-rolled
    stub, so the surrounding markup is exactly what the site ships.
    """
    html = _text("chapter_pages.html")
    marker = '<img src="https://kuma.kyut.dev'
    assert marker in html
    polluted = html.replace(
        marker,
        '<img src="https://ads.example.com/banner.gif" alt="" />'
        '<img src="https://rawkuma.net/wp-content/themes/rawkuma/static/spacer.png" alt="" />'
        + marker,
        1,
    )

    pages = parse_chapter_pages(polluted, CHAPTER_KEY)
    assert len(pages) == 30
    assert pages[0].number == 1
    assert pages[0].remote_url.startswith("https://kuma.kyut.dev/")
    assert all(is_page_image_url(page.remote_url) for page in pages)


def test_page_cdn_check_matches_on_host_not_substring():
    """A substring test over the whole URL would accept anything that merely
    mentions the CDN domain in a query string."""
    assert is_page_image_url("https://kuma.kyut.dev/wp-content/scr/a/b/1.jpg") is True
    assert is_page_image_url("https://rcdn.kyut.dev/images/o/x/3/1.jpg") is True
    assert is_page_image_url("https://ads.example.com/track?ref=kyut.dev") is False
    assert is_page_image_url("https://notkyut.dev/1.jpg") is False


def test_page_id_round_trips_to_its_chapter_key():
    pages = parse_chapter_pages(_text("chapter_pages.html"), CHAPTER_KEY)
    assert pages[0].id == f"{CHAPTER_KEY}:1"
    assert page_id_chapter_id(pages[0].id) == CHAPTER_KEY
    assert page_id_chapter_id(pages[-1].id) == CHAPTER_KEY
    assert page_id_chapter_id("no-separator-here") is None


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_reranks_verbatim_title_matches_to_the_front():
    """BROKEN SELECTOR proof: making ``title_relevance_rank`` return a constant
    leaves the upstream order untouched and fails this.

    WordPress ranks relevance over the whole post body, so searching "slime"
    returns titles that merely mention it in the synopsis ahead of the ones
    that are actually called Slime-something.
    """
    listing = parse_series_list_json(_json("search_rest_slime.json"), page=1)
    assert not listing.items[0].title.lower().startswith("slime")

    reranked = rerank_by_title(listing, "slime")
    assert reranked.items[0].title.lower().startswith("slime")
    assert {i.id for i in reranked.items} == {i.id for i in listing.items}
    assert reranked.page == listing.page
    assert reranked.api_has_more == listing.api_has_more


def test_search_rerank_keeps_an_exact_title_first():
    listing = parse_series_list_json(_json("search_rest_one_piece.json"), page=1)
    reranked = rerank_by_title(listing, "one piece")
    assert reranked.items[0].title == "One Piece"
    assert title_relevance_rank("One Piece", "one piece") == 0
    assert title_relevance_rank("Slime Seijo", "slime") == 1
    assert title_relevance_rank("Green Slime ni Tensei shita Ore wa", "slime") == 2
    assert title_relevance_rank("Dokudami no Hana Saku Koro", "slime") == 3


def test_search_rerank_is_stable_inside_a_tier():
    """Re-ordering must only lift matching tiers; upstream relevance still
    decides within a tier, so paging stays coherent."""
    listing = parse_series_list_json(_json("search_rest_slime.json"), page=1)
    reranked = rerank_by_title(listing, "slime")
    for tier in range(4):
        original = [i.id for i in listing.items if title_relevance_rank(i.title, "slime") == tier]
        after = [i.id for i in reranked.items if title_relevance_rank(i.title, "slime") == tier]
        assert original == after


# ---------------------------------------------------------------------------
# request efficiency
# ---------------------------------------------------------------------------


def test_series_detail_and_chapter_list_share_a_single_fetch(connector: RawkumaConnector):
    """The whole reason the series page is parsed twice from one document.

    Fetching it again for the chapter list is the anti-pattern this repo has
    already had to fix elsewhere: a second half-megabyte GET on every series
    open.
    """
    calls: list[str] = []
    html = _text("series_detail.html")

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        series = connector.get_series(SERIES_KEY)
        chapters = connector.get_chapters(SERIES_KEY)
        connector.get_series(SERIES_KEY)
        connector.get_chapters(SERIES_KEY)

    assert calls == [f"/manga/{SERIES_KEY}/"]
    assert series is not None
    assert series.chapter_count == 94
    assert series.latest_chapter == "Chapter 84"
    assert len(chapters) == 94


def test_chapter_pages_cost_one_request_for_the_whole_chapter(connector: RawkumaConnector):
    """Resolving page images must not cost a request per page."""
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        return _text("chapter_pages.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages(CHAPTER_KEY)
        again = connector.get_chapter_pages(CHAPTER_KEY)
        found = connector.find_page(pages[17].id)

    assert len(pages) == 30
    assert len(calls) == 1
    assert again == pages
    assert found is not None and found.number == 18


def test_find_page_rejects_a_foreign_id_without_touching_the_network(
    connector: RawkumaConnector,
):
    with patch.object(connector._http, "get_text", side_effect=AssertionError("no request")):
        assert connector.find_page("garbage") is None


def test_page_count_is_backfilled_into_later_chapter_lists(connector: RawkumaConnector):
    """The series page carries no per-chapter page count; once a chapter has
    been opened the connector should stop reporting 0 for it."""

    def fake_get_text(path: str, *, params=None) -> str:
        return _text("chapter_pages.html") if "chapter-" in path else _text("series_detail.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        assert connector.get_chapters(SERIES_KEY)[-1].page_count == 0
        connector.get_chapter_pages(CHAPTER_KEY)
        assert connector.get_chapters(SERIES_KEY)[-1].page_count == 30


def test_search_issues_exactly_one_upstream_request(connector: RawkumaConnector):
    calls: list[dict] = []

    def fake_get_json_value(path: str, *, params=None):
        calls.append(params or {})
        return _json("search_rest_slime.json")

    with patch.object(connector._http, "get_json_value", side_effect=fake_get_json_value):
        listing = connector.search_series("slime", 1)

    assert len(calls) == 1
    assert calls[0]["search"] == "slime"
    assert calls[0]["orderby"] == "relevance"
    assert listing.items[0].title.lower().startswith("slime")


def test_blank_search_falls_back_to_the_catalog(connector: RawkumaConnector):
    with patch.object(
        connector._http, "get_json_value", side_effect=lambda p, params=None: _json("browse_page1.json")
    ):
        listing = connector.search_series("   ", 1)
    assert listing.items[0].id == "seijo-no-isan"


# ---------------------------------------------------------------------------
# failure handling
# ---------------------------------------------------------------------------


def test_not_found_detection_matches_both_error_shapes():
    """The known trap: ``SyncConnectorHttpClient`` only attaches
    ``status_code`` for RETRYABLE_STATUS, and 404 is not one of them, so a
    bare ``exc.status_code == 404`` check never fires."""
    bare = ConnectorHttpError(
        "Client error '404 Not Found' for url 'https://rawkuma.net/manga/x/'"
    )
    assert bare.status_code is None
    assert _is_not_found(bare) is True
    assert _is_not_found(ConnectorHttpError("boom", status_code=404)) is True
    assert _is_not_found(ConnectorHttpError("Retryable HTTP 503", status_code=503)) is False


def test_missing_series_returns_none_and_is_remembered(connector: RawkumaConnector):
    calls: list[str] = []

    def fake_get_text(path: str, *, params=None) -> str:
        calls.append(path)
        raise ConnectorHttpError(
            "Client error '404 Not Found' for url 'https://rawkuma.net/manga/nope/'"
        )

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        assert connector.get_series("nope") is None
        assert connector.get_chapters("nope") == []
        assert connector.get_series("nope") is None

    # A 404 is cached as "gone" so a missing series is not re-fetched on every
    # lookup; a deterministic 404 cannot answer differently.
    assert len(calls) == 1


def test_missing_chapter_returns_no_pages(connector: RawkumaConnector):
    with patch.object(
        connector._http,
        "get_text",
        side_effect=ConnectorHttpError("Client error '404 Not Found' for url '...'"),
    ):
        assert connector.get_chapter_pages("nope/chapter-1.1") == []


def test_browse_past_the_last_page_returns_an_empty_page_not_an_error(
    connector: RawkumaConnector,
):
    """WordPress answers 400 for a page beyond the collection; that is the end
    of the list, not a failure the reader should see."""
    with patch.object(
        connector._http,
        "get_json_value",
        side_effect=ConnectorHttpError("Client error '400 Bad Request' for url '...'"),
    ):
        listing = connector.get_series_list(9999)

    assert listing.items == []
    assert listing.has_more is False


def test_transport_failure_still_propagates(connector: RawkumaConnector):
    """Only 400 is swallowed. A 503 must not be reported as an empty catalog,
    or the browse UI silently shows nothing whenever the site wobbles."""
    with patch.object(
        connector._http,
        "get_json_value",
        side_effect=ConnectorHttpError("Retryable HTTP 503", status_code=503),
    ):
        with pytest.raises(ConnectorHttpError):
            connector.get_series_list(1)
