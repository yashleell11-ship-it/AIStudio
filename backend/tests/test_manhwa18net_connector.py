"""Offline tests for the Manhwa18.net connector.

Fixtures under ``tests/fixtures/manhwa18net/`` were captured live 2026-09-05
FROM THE VPS (inside ``manhwamaniacs-backend``, so through production's exact
egress IP and TLS stack). The connector is exercised entirely against those
captures by patching ``self._http.get_text``; no test touches the network.

Every parse assertion here was watched to FAIL against a deliberately broken
selector before being kept -- a test that still passes on broken parsing
proves nothing.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest

from connectors.base import SourceConnector
from connectors.http.client import ConnectorHttpError
from connectors.manhwa18net.connector import Manhwa18NetConnector, _sniff_image_media_type
from connectors.manhwa18net.mappers import (
    BROWSE_PATH,
    SEARCH_PATH,
    browse_params,
    chapter_path,
    genre_path,
    inertia_props,
    make_chapter_key,
    make_page_id,
    normalize_series_key,
    page_id_chapter_key,
    parse_chapter_number,
    parse_chapter_pages,
    parse_chapters,
    parse_series_detail,
    parse_series_list,
    search_params,
    series_path,
)
from tests.connector_validation import ConnectorContractCase, validate_connector_contract

FIXTURES = Path(__file__).parent / "fixtures" / "manhwa18net"

SERIES_KEY = "the-seed-of-destiny"
CHAPTER_KEY = "the-seed-of-destiny/chapter-0-prologue"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def connector() -> Manhwa18NetConnector:
    return Manhwa18NetConnector()


@contextmanager
def _mock_manhwa18net(connector: SourceConnector) -> Iterator[None]:
    browse_page1 = _load("browse_page1.html")
    browse_page2 = _load("browse_page2.html")
    browse_top = _load("browse_top.html")
    search_secret = _load("search_secret.html")
    genre_manhwa = _load("genre_manhwa.html")
    series_detail = _load("series_detail.html")
    chapter_reader = _load("chapter_reader.html")

    def fake_get_text(path: str, *, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        if path == BROWSE_PATH:
            if params.get("sort") == "top":
                return browse_top
            if int(params.get("page", 1)) == 2:
                return browse_page2
            return browse_page1
        if path == SEARCH_PATH:
            return search_secret
        if path == genre_path("manhwa"):
            return genre_manhwa
        if path == series_path(SERIES_KEY):
            return series_detail
        if path == chapter_path(CHAPTER_KEY):
            return chapter_reader
        raise ConnectorHttpError(
            f"Client error '404 Not Found' for url '{path}'", status_code=None
        )

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        yield


# --- identity ---------------------------------------------------------------


def test_series_key_round_trips_through_every_inbound_shape():
    """House law: keys are the site's own slugs and pass through raw."""
    assert normalize_series_key(SERIES_KEY) == SERIES_KEY
    assert normalize_series_key(f"manga/{SERIES_KEY}") == SERIES_KEY
    assert normalize_series_key(f"/manga/{SERIES_KEY}/") == SERIES_KEY
    assert normalize_series_key(f"https://manhwa18.net/manga/{SERIES_KEY}") == SERIES_KEY
    assert series_path(SERIES_KEY) == f"/manga/{SERIES_KEY}"


def test_chapter_key_carries_both_slugs_because_chapter_slugs_repeat():
    """``chapter-1`` exists under every series, so the key must be qualified."""
    assert make_chapter_key(SERIES_KEY, "chapter-49") == f"{SERIES_KEY}/chapter-49"
    assert "/" in CHAPTER_KEY
    assert chapter_path(CHAPTER_KEY) == f"/manga/{CHAPTER_KEY}"
    assert chapter_path(f"https://manhwa18.net/manga/{CHAPTER_KEY}") == f"/manga/{CHAPTER_KEY}"


def test_page_id_round_trips_through_a_key_holding_slashes_and_dashes():
    page_id = make_page_id(CHAPTER_KEY, 4)
    assert page_id == f"{CHAPTER_KEY}:4"
    assert page_id_chapter_key(page_id) == CHAPTER_KEY
    assert page_id_chapter_key("no-separator-here") is None


def test_chapter_number_reads_the_label_and_falls_back_to_order():
    assert parse_chapter_number("Chapter 49") == 49.0
    assert parse_chapter_number("Chapter 28.2") == 28.2
    assert parse_chapter_number("Chapter 0 - Prologue") == 0.0
    # A label with no digits still has to be orderable, or the reader cannot
    # sequence the series at all.
    assert parse_chapter_number("Epilogue", fallback=53.0) == 53.0


# --- browse / search params -------------------------------------------------


def test_browse_params_omit_sort_for_the_sites_own_default():
    assert browse_params(None, 1) == {"page": 1}
    assert browse_params("top", 2) == {"page": 2, "sort": "top"}
    assert browse_params("not-a-mode", 1) == {"page": 1}
    assert search_params("secret", 3) == {"page": 3, "q": "secret"}
    assert genre_path("manhwa") == "/genre/manhwa"


# --- payload ----------------------------------------------------------------


def test_inertia_payload_is_read_as_json_not_scraped():
    props = inertia_props(_load("series_detail.html"))
    assert props is not None
    assert set(props) >= {"manga", "chapters", "seo"}


def test_a_page_without_the_inertia_attribute_parses_to_nothing():
    assert inertia_props("<html><body>no payload</body></html>") is None


# --- catalog parsing --------------------------------------------------------


def test_parse_browse_page_reads_the_laravel_paginator():
    listing = parse_series_list(_load("browse_page1.html"), page=1)
    assert len(listing.items) == 24
    assert listing.page_size == 24
    assert listing.total == 2277
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "your-mom-is-the-best"
    assert first.title == "Your Mom Is the Best"
    assert first.canonical_path == "/manga/your-mom-is-the-best"
    assert first.cover_url is not None and first.cover_url.startswith("https://min.manhwa18.net/")
    assert first.latest_chapter == "Chapter 7"
    assert "Manhwa" in first.genres


def test_page_two_is_a_different_slice_and_says_so():
    page1 = parse_series_list(_load("browse_page1.html"), page=1)
    page2 = parse_series_list(_load("browse_page2.html"), page=2)
    assert page2.page == 2
    assert page2.items[0].id == "i-became-an-apartment-security-manager"
    assert {item.id for item in page1.items}.isdisjoint({item.id for item in page2.items})


def test_top_sort_really_reorders_the_catalog():
    top = parse_series_list(_load("browse_top.html"), page=1)
    assert top.items[0].id == "secret-class"
    assert top.items[0].id != parse_series_list(_load("browse_page1.html"), page=1).items[0].id


def test_search_reads_the_mangas_key_the_search_route_uses_instead_of_paginate():
    """``/tim-kiem`` publishes the same envelope under a different prop name."""
    listing = parse_series_list(_load("search_secret.html"), page=1)
    assert listing.total == 74
    assert listing.page_size == 18
    assert any("secret" in item.title.casefold() for item in listing.items)


def test_genre_page_paginates_over_its_own_smaller_total():
    listing = parse_series_list(_load("genre_manhwa.html"), page=1)
    assert listing.total == 1771
    assert listing.has_more is True


def test_a_404_page_carries_no_payload_and_parses_to_none():
    assert parse_series_detail(_load("missing_series.html"), SERIES_KEY) is None


# --- detail / chapters / reader ---------------------------------------------


def test_detail_reads_metadata_out_of_the_payload():
    series = parse_series_detail(_load("series_detail.html"), SERIES_KEY)
    assert series is not None
    assert series.id == SERIES_KEY
    assert series.title == "The Seed of Destiny"
    assert series.description is not None
    assert "elf princess" in series.description
    # The synopsis field ships an inline <script> player bootstrap; none of it
    # may survive into the description shown in the app.
    assert "<script" not in series.description
    assert "PlayerjsAsync" not in series.description
    assert "Explicit Sex" in series.genres


def test_chapters_come_back_oldest_first_with_usable_numbers():
    chapters = parse_chapters(_load("series_detail.html"), SERIES_KEY)
    assert len(chapters) == 52
    assert chapters[0].id == f"{SERIES_KEY}/chapter-0-prologue"
    assert chapters[0].number == 0.0
    assert chapters[-1].id == f"{SERIES_KEY}/chapter-49"
    assert chapters[-1].number == 49.0
    numbers = [chapter.number for chapter in chapters]
    assert numbers == sorted(numbers)
    assert all(chapter.series_id == SERIES_KEY for chapter in chapters)


def test_reader_pages_come_from_the_payload_not_from_img_tags():
    pages = parse_chapter_pages(_load("chapter_reader.html"), CHAPTER_KEY)
    assert len(pages) == 6
    assert pages[0].id == f"{CHAPTER_KEY}:1"
    assert pages[0].chapter_id == CHAPTER_KEY
    assert pages[0].remote_url.startswith("https://min.manhwa18.net/")
    assert [page.number for page in pages] == [1, 2, 3, 4, 5, 6]


# --- image labelling --------------------------------------------------------


def test_page_images_are_relabelled_from_their_magic_number():
    """min.manhwa18.net serves every page image as binary/octet-stream.

    Without this the proxy clamps them to application/octet-stream and the
    reader shows an undisplayable download instead of a page.
    """
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    assert _sniff_image_media_type(png, "binary/octet-stream") == "image/png"
    assert _sniff_image_media_type(b"\xff\xd8\xff\xe0", "binary/octet-stream") == "image/jpeg"
    assert _sniff_image_media_type(b"RIFF____WEBPVP8 ", "binary/octet-stream") == "image/webp"


def test_a_truthful_upstream_label_is_never_overridden():
    assert _sniff_image_media_type(b"not-an-image", "image/jpeg") == "image/jpeg"


# --- connector wiring -------------------------------------------------------


def test_image_host_allowlist_covers_the_cdn_subdomain(connector: Manhwa18NetConnector):
    from services.outbound_security import host_matches_allowlist

    assert host_matches_allowlist("min.manhwa18.net", connector.allowed_image_hosts)
    assert not host_matches_allowlist("notmanhwa18.net", connector.allowed_image_hosts)


def test_source_id_does_not_collide_with_the_registered_manhwa18_cc_source(
    connector: Manhwa18NetConnector,
):
    """manhwa18.cc is already registered as ``manhwa18``; this is a different site."""
    from connectors.registry import create_connector

    assert connector.source_type == "manhwa18net"
    assert create_connector("manhwa18").source_type == "manhwa18"
    assert connector.is_mature is True


def test_detail_and_chapters_share_one_upstream_fetch(connector: Manhwa18NetConnector):
    with _mock_manhwa18net(connector):
        with patch.object(connector._http, "get_text", wraps=connector._http.get_text) as spy:
            connector.get_series(SERIES_KEY)
            connector.get_chapters(SERIES_KEY)
        assert spy.call_count == 1


def test_missing_series_is_none_rather_than_an_error(connector: Manhwa18NetConnector):
    with _mock_manhwa18net(connector):
        assert connector.get_series("definitely-not-a-real-series-xyz") is None
        assert connector.get_chapters("definitely-not-a-real-series-xyz") == []


def test_connector_contract():
    validate_connector_contract(
        ConnectorContractCase(
            source_type="manhwa18net",
            fixtures_dir=FIXTURES,
            search_query="secret",
            series_id=SERIES_KEY,
            reader_chapter_id=CHAPTER_KEY,
            expected_title_substring="Seed of Destiny",
            expected_image_host_substring="min.manhwa18.net",
            expected_latest_first_id="your-mom-is-the-best",
            expected_page2_first_id="i-became-an-apartment-security-manager",
            mock=_mock_manhwa18net,
        )
    )
