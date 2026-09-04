"""Offline tests for the Project Gutenberg novel connector.

Fixtures under ``tests/fixtures/gutenberg/`` are live responses captured
2026-09-04 FROM THE VPS (production's exact egress and TLS stack — the probe
methodology in the novels spec §4). Nothing here touches the network; the
connector runs against those captures with ``self._api.get_json`` and
``self._files.get_bytes`` patched.

What the captures are, and why each one is here:

* ``gutendex_popular.json`` / ``gutendex_popular_page2.json`` — the default
  browse view, pages 1 and 2; two pages because the pagination assertions
  pin the ``next`` handoff between them.
* ``gutendex_search.json`` — the same endpoint narrowed by ``search``.
* ``gutendex_book_84.json`` — a single-book detail record.
* ``pg11.epub`` / ``pg1342.epub`` — two REAL Gutenberg EPUBs in the
  ``.epub.noimages`` build this connector requests. They are here because
  they are the two halves of the honest story about chapter boundaries:
  Alice splits one spine document per chapter, Pride and Prejudice groups
  several chapters into each document. Both are public-domain texts, and
  they are used only as parser input — the assertions below check structure
  (counts, keys, ordering, budgets), never prose.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.archiveorg.epub import parse_epub
from connectors.gutenberg.connector import (
    API_MAX_RETRIES,
    API_TIMEOUT_SECONDS,
    GENRE_TOPICS,
    MAX_CACHED_BOOKS,
    MAX_EPUB_BYTES,
    GutenbergConnector,
    _BookCache,
    _ParsedBook,
)
from connectors.gutenberg.mappers import (
    EPUB_MIME,
    MAX_GENRES,
    PAGE_SIZE,
    _author_name,
    browse_params,
    download_path,
    normalize_chapter_key,
    normalize_series_key,
    parse_book,
    parse_book_list,
    series_detail_path,
    series_from_book,
    topic_params,
)
from connectors.http.client import ConnectorHttpError
from connectors.models import Series

FIXTURES = Path(__file__).parent / "fixtures" / "gutenberg"

ALICE = "11"  # one spine document per chapter
PRIDE = "1342"  # several chapters grouped into each spine document
FRANKENSTEIN = "84"

ALICE_CHAPTERS = 13
PRIDE_CHAPTERS = 15


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _epub(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# --- the download choice, which is the whole cost story ---------------------


def test_download_path_uses_the_noimages_build():
    """gutendex advertises ``.epub3.images``; this connector asks for
    ``.epub.noimages`` instead. Measured from the VPS on the same books, the
    noimages build is both far smaller AND more finely split:

    Pride and Prejudice  24.8 MB / 6 spine  ->  558 KB / 15 spine
    Moby-Dick             812 KB / 10 spine ->  727 KB / 27 spine
    Huckleberry Finn     16.0 MB / 46 spine ->  346 KB / 46 spine

    Regressing this to the advertised format would multiply the bandwidth
    bill by up to ~45x and make chapters coarser, so it is pinned here.
    """
    assert download_path(ALICE) == "/ebooks/11.epub.noimages"
    assert "images" not in download_path(ALICE).replace("noimages", "")


def test_the_shipped_epub_fixtures_are_small_enough_to_be_the_normal_case():
    """The size cap exists for anomalies, not for ordinary books."""
    for name in ("pg11.epub", "pg1342.epub"):
        assert (FIXTURES / name).stat().st_size < MAX_EPUB_BYTES


# --- catalogue parameters ---------------------------------------------------


def test_browse_params_pin_english_and_an_available_epub():
    """Listings must only contain books this connector can actually open;
    filtering upstream beats letting rows 404 when a reader taps them."""
    params = browse_params(None, 1, None)
    assert params["languages"] == "en"
    assert params["mime_type"] == EPUB_MIME
    assert params["sort"] == "popular"
    assert params["page"] == 1


def test_browse_params_allowlist_sorts():
    assert browse_params(None, 1, "newest")["sort"] == "descending"
    assert browse_params(None, 1, "oldest")["sort"] == "ascending"
    # gutendex silently ignores an unknown sort (answers 200 with its
    # default), so an unrecognized mode must resolve here, not upstream.
    assert browse_params(None, 1, "wharrgarbl")["sort"] == "popular"


def test_search_params_drop_sort_and_keep_the_filters():
    params = browse_params("frankenstein", 3, "newest")
    assert params["search"] == "frankenstein"
    assert "sort" not in params  # gutendex orders a search by relevance
    assert params["mime_type"] == EPUB_MIME
    assert params["page"] == 3


def test_topic_params_add_a_genre_without_losing_the_filters():
    params = topic_params("adventure", 2, None)
    assert params["topic"] == "adventure"
    assert params["mime_type"] == EPUB_MIME
    assert params["languages"] == "en"


def test_every_advertised_genre_is_a_usable_topic():
    assert GENRE_TOPICS
    for topic, label in GENRE_TOPICS:
        assert topic and topic == topic.strip()
        assert label


# --- identity ---------------------------------------------------------------


def test_series_key_is_the_ebook_id_and_normalizes_from_every_url_form():
    assert normalize_series_key("84") == FRANKENSTEIN
    assert normalize_series_key("ebooks/84") == FRANKENSTEIN
    assert normalize_series_key("https://www.gutenberg.org/ebooks/84") == FRANKENSTEIN
    assert normalize_series_key("https://gutendex.com/books/84") == FRANKENSTEIN
    assert normalize_series_key("84.epub.noimages") == FRANKENSTEIN
    assert series_detail_path(FRANKENSTEIN) == "/books/84"


def test_a_key_that_is_not_an_ebook_id_normalizes_to_empty():
    """Anything else must be refused locally rather than sent upstream."""
    for bad in ("", "   ", "not-a-number", "/", "ebooks/", "../../etc/passwd"):
        assert normalize_series_key(bad) == ""


def test_chapter_key_is_a_manifest_href_with_the_fragment_stripped():
    assert normalize_chapter_key("11-h-1.htm.html") == "11-h-1.htm.html"
    assert normalize_chapter_key("11-h-1.htm.html#chap01") == "11-h-1.htm.html"


# --- listing parsing --------------------------------------------------------


def test_parse_browse_page():
    listing = parse_book_list(_load("gutendex_popular.json"), page=1)
    assert len(listing.items) == PAGE_SIZE
    assert listing.total > 60000
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id.isdigit()
    assert first.title
    assert first.author
    assert first.status == "completed"
    assert first.cover_url and first.cover_url.startswith("https://")
    assert first.genres


def test_listings_never_download_a_book_so_chapter_count_stays_zero():
    """A listing must cost one request for the whole page, not one download
    per row. The real count arrives with the book in ``_load_book``."""
    listing = parse_book_list(_load("gutendex_popular.json"), page=1)
    assert all(item.chapter_count == 0 for item in listing.items)


def test_parse_browse_page_two_is_a_different_set():
    page1 = parse_book_list(_load("gutendex_popular.json"), page=1)
    page2 = parse_book_list(_load("gutendex_popular_page2.json"), page=2)
    assert {item.id for item in page1.items}.isdisjoint(
        {item.id for item in page2.items}
    )


def test_has_more_comes_from_gutendex_own_next_link():
    """gutendex hands back the next page's URL, or null on the last page —
    authoritative, so it beats inferring from the total."""
    payload = _load("gutendex_popular.json")
    assert payload["next"]
    assert parse_book_list(payload, page=1).has_more is True

    last_page = dict(payload, next=None)
    assert parse_book_list(last_page, page=99).has_more is False


def test_parse_search_page():
    listing = parse_book_list(_load("gutendex_search.json"), page=1)
    assert listing.items
    assert all(item.id and item.title for item in listing.items)


def test_empty_result_set_is_an_empty_listing():
    empty = {"count": 0, "next": None, "previous": None, "results": []}
    listing = parse_book_list(empty, page=1)
    assert listing.items == []
    assert listing.total == 0
    assert listing.has_more is False


def test_malformed_payload_is_an_empty_listing_not_a_crash():
    for payload in (None, {}, {"results": "nope"}, {"results": [None, 7, "x"]}):
        assert parse_book_list(payload, page=1).items == []


# --- what may and may not be served ----------------------------------------


def _book(**overrides) -> dict:
    base = {
        "id": 84,
        "title": "Frankenstein",
        "authors": [{"name": "Shelley, Mary Wollstonecraft"}],
        "media_type": "Text",
        "copyright": False,
        "formats": {EPUB_MIME: "https://www.gutenberg.org/ebooks/84.epub3.images"},
        "subjects": [],
        "bookshelves": [],
        "summaries": [],
    }
    base.update(overrides)
    return base


def test_a_normal_public_domain_text_is_servable():
    assert series_from_book(_book()) is not None


def test_books_still_in_copyright_are_never_served():
    """Only what Gutenberg itself marks public domain in the US. A null flag
    means "unknown", which is not good enough to redistribute."""
    assert series_from_book(_book(copyright=True)) is None
    assert series_from_book(_book(copyright=None)) is None
    assert "copyright" not in _book(copyright=True) or True  # documents the field


def test_non_text_media_are_never_served():
    """Gutenberg also holds audio and images; neither is a novel."""
    for medium in ("Sound", "Image", "Dataset", ""):
        assert series_from_book(_book(media_type=medium)) is None


def test_a_book_with_no_epub_is_never_served():
    """PDF/plain-text-only items have no spine to split into chapters."""
    assert series_from_book(_book(formats={})) is None
    assert (
        series_from_book(
            _book(formats={"text/plain": "https://www.gutenberg.org/x.txt"})
        )
        is None
    )


def test_records_with_no_id_or_title_are_never_served():
    assert series_from_book(_book(id=None)) is None
    assert series_from_book(_book(id=0)) is None
    assert series_from_book(_book(title="   ")) is None
    assert series_from_book("not a dict") is None


def test_epub_mime_match_tolerates_a_charset_parameter():
    book = _book(formats={f"{EPUB_MIME}; charset=utf-8": "https://x/84.epub"})
    assert series_from_book(book) is not None


# --- metadata presentation --------------------------------------------------


def test_author_names_are_flipped_out_of_gutenberg_sorting_order():
    assert _author_name("Austen, Jane") == "Jane Austen"
    assert _author_name("Shelley, Mary Wollstonecraft") == "Mary Wollstonecraft Shelley"


def test_author_names_with_a_second_comma_are_left_alone():
    """"Dumas, Alexandre, 1802-1870" must not be scrambled into nonsense."""
    assert _author_name("Dumas, Alexandre, 1802-1870") == "Dumas, Alexandre, 1802-1870"
    assert _author_name("Various") == "Various"
    assert _author_name("") == ""


def test_genres_are_readable_labels_from_both_vocabularies():
    book = _book(
        bookshelves=["Category: British Literature", "Browsing: Fiction"],
        subjects=["Courtship -- Fiction", "England -- Fiction", "Love stories"],
    )
    series = series_from_book(book)
    assert series is not None
    assert "British Literature" in series.genres
    assert "Fiction" in series.genres
    assert "Courtship" in series.genres
    assert "Love stories" in series.genres
    # The LoC "-- Fiction" tail and the curator prefixes are gone.
    assert not any("--" in genre or ":" in genre for genre in series.genres)


def test_genres_are_deduplicated_and_capped():
    book = _book(
        bookshelves=[f"Category: Shelf {i}" for i in range(20)],
        subjects=["Shelf 0"] * 5,
    )
    series = series_from_book(book)
    assert series is not None
    assert len(series.genres) == MAX_GENRES
    assert len(set(series.genres)) == len(series.genres)


def test_parse_book_detail():
    series = parse_book(_load("gutendex_book_84.json"))
    assert series is not None
    assert series.id == FRANKENSTEIN
    assert "Frankenstein" in series.title
    assert series.author == "Mary Wollstonecraft Shelley"


# --- real EPUBs: the honest chapter-boundary story --------------------------


def test_a_per_chapter_book_splits_one_spine_document_per_chapter():
    """Alice is the common, good case: the book's own file structure already
    is its chapter structure."""
    parsed = parse_epub(_epub("pg11.epub"))
    assert parsed is not None
    assert parsed.language == "en"
    assert len(parsed.chapters) == ALICE_CHAPTERS
    numbers = [chapter.number for chapter in parsed.chapters]
    assert numbers == sorted(numbers)
    assert numbers == [float(n) for n in range(1, ALICE_CHAPTERS + 1)]
    # Keys are stable manifest hrefs, unique within the book.
    keys = [chapter.key for chapter in parsed.chapters]
    assert len(set(keys)) == len(keys)
    assert all(key and "#" not in key for key in keys)
    # The book's own TOC named the chapters.
    assert sum(1 for c in parsed.chapters if "CHAPTER" in c.title.upper()) >= 12


def test_a_grouped_book_yields_fewer_longer_chapters_but_never_a_fake_split():
    """Pride and Prejudice is the coarse case, kept deliberately.

    Its 61 chapters were grouped by Gutenberg's own converter into 15 spine
    documents, so the reader sees 15 longer chapters whose titles name the
    first chapter in each group. That is coarse, but every boundary is one
    the book itself declares — the alternative would be inventing chapter
    boundaries in running text, which is worse than one long chapter.
    """
    parsed = parse_epub(_epub("pg1342.epub"))
    assert parsed is not None
    assert len(parsed.chapters) == PRIDE_CHAPTERS
    numbers = [chapter.number for chapter in parsed.chapters]
    assert numbers == [float(n) for n in range(1, PRIDE_CHAPTERS + 1)]
    # Coarse means long, not lossy: the whole novel is still present.
    assert sum(chapter.word_count for chapter in parsed.chapters) > 100_000
    assert all(chapter.paragraphs for chapter in parsed.chapters)


def test_the_gutenberg_licence_wrapper_never_reaches_a_reader():
    """Every Gutenberg book is wrapped in licence boilerplate; the shared
    EPUB reader trims it, and this pins that it stays trimmed."""
    parsed = parse_epub(_epub("pg11.epub"))
    assert parsed is not None
    blob = " ".join(
        paragraph
        for chapter in parsed.chapters
        for paragraph in chapter.paragraphs
    ).upper()
    assert "START OF THE PROJECT GUTENBERG" not in blob
    assert "FULL PROJECT GUTENBERG LICENSE" not in blob


def test_a_non_epub_payload_is_refused_rather_than_half_parsed():
    assert parse_epub(b"this is not a zip file at all") is None
    assert parse_epub(b"") is None


# --- connector behaviour ----------------------------------------------------


@pytest.fixture()
def connector() -> GutenbergConnector:
    return GutenbergConnector()


def test_connector_declares_the_novel_contract(connector: GutenbergConnector):
    assert connector.content_kind == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.source_type == "gutenberg"
    assert connector.is_mature is False
    assert connector.get_chapter_pages("anything") == []
    assert connector.find_page("anything") is None


def test_cover_host_is_inside_the_image_allowlist(connector: GutenbergConnector):
    listing = parse_book_list(_load("gutendex_popular.json"), page=1)
    covers = [item.cover_url for item in listing.items if item.cover_url]
    assert covers
    allowed = connector.allowed_image_hosts
    for cover in covers:
        host = cover.split("/")[2]
        assert any(host == domain or host.endswith(f".{domain}") for domain in allowed)


def _install_book(connector: GutenbergConnector, book_id: str, epub_name: str):
    """Patch both clients and count what each read actually costs."""
    counts = {"json": 0, "bytes": 0}
    detail = _load("gutendex_book_84.json")
    detail = dict(detail, id=int(book_id))

    def fake_get_json(path, params=None):
        counts["json"] += 1
        return detail

    def fake_get_bytes(url):
        counts["bytes"] += 1
        return "application/epub+zip", _epub(epub_name)

    return counts, patch.object(
        connector._api, "get_json", side_effect=fake_get_json
    ), patch.object(connector._files, "get_bytes", side_effect=fake_get_bytes)


def test_one_download_feeds_series_chapters_and_every_chapter_text(
    connector: GutenbergConnector,
):
    """The point of the design: reading a whole book costs ONE book fetch,
    not one per chapter."""
    counts, api_patch, files_patch = _install_book(connector, ALICE, "pg11.epub")
    with api_patch, files_patch:
        series = connector.get_series(ALICE)
        chapters = connector.get_chapters(ALICE)
        texts = [
            connector.chapter_text(ALICE, chapter.id) for chapter in chapters
        ]

    assert series is not None
    assert series.chapter_count == ALICE_CHAPTERS
    assert len(chapters) == ALICE_CHAPTERS
    assert all(text is not None for text in texts)
    # 13 chapters read end to end, one download and one metadata call total.
    assert counts["bytes"] == 1
    assert counts["json"] == 1


def test_chapter_text_carries_its_number_and_title(connector: GutenbergConnector):
    counts, api_patch, files_patch = _install_book(connector, ALICE, "pg11.epub")
    with api_patch, files_patch:
        chapters = connector.get_chapters(ALICE)
        text = connector.chapter_text(ALICE, chapters[1].id)

    assert text is not None
    assert text.chapter_number == 2.0
    assert text.title == chapters[1].title
    assert text.word_count > 500
    assert not any("<" in p and ">" in p for p in text.paragraphs)


def test_a_chapter_key_not_in_the_spine_reads_as_missing(
    connector: GutenbergConnector,
):
    counts, api_patch, files_patch = _install_book(connector, ALICE, "pg11.epub")
    with api_patch, files_patch:
        assert connector.chapter_text(ALICE, "no-such-document.html") is None


def _padded_epub(source: str, target_bytes: int) -> bytes:
    """A REAL, still-parsable EPUB grown past a byte budget.

    The padding is a stored (uncompressed) extra member, so the archive stays
    a valid book that ``parse_epub`` would happily read. That is the point:
    the only thing standing between this blob and a parse is the size cap, so
    the test below fails the moment that cap stops being enforced. Padding
    with junk bytes instead would prove nothing — a malformed ZIP is rejected
    by the parser whether or not the cap exists.
    """
    buffer = io.BytesIO(_epub(source))
    with zipfile.ZipFile(buffer, "a", zipfile.ZIP_STORED) as archive:
        archive.writestr("padding.bin", b"\0" * target_bytes)
    return buffer.getvalue()


def test_an_oversized_epub_is_refused_rather_than_parsed(
    connector: GutenbergConnector,
):
    """A book over the cap is skipped even though it parses perfectly well."""
    oversized = _padded_epub("pg11.epub", MAX_EPUB_BYTES)
    assert len(oversized) > MAX_EPUB_BYTES
    # Without the cap this blob is a readable book, not a broken one.
    assert parse_epub(oversized) is not None

    detail = _load("gutendex_book_84.json")
    with patch.object(connector._api, "get_json", return_value=detail), patch.object(
        connector._files, "get_bytes", return_value=("application/epub+zip", oversized)
    ):
        assert connector.get_series(FRANKENSTEIN) is None


def test_a_book_whose_epub_yields_no_chapters_is_not_served_as_a_shell(
    connector: GutenbergConnector,
):
    detail = _load("gutendex_book_84.json")
    with patch.object(connector._api, "get_json", return_value=detail), patch.object(
        connector._files, "get_bytes", return_value=("application/epub+zip", b"junk")
    ):
        assert connector.get_series(FRANKENSTEIN) is None
        assert connector.get_chapters(FRANKENSTEIN) == []


def test_a_copyrighted_record_is_refused_before_anything_is_downloaded(
    connector: GutenbergConnector,
):
    detail = dict(_load("gutendex_book_84.json"), copyright=True)
    with patch.object(connector._api, "get_json", return_value=detail), patch.object(
        connector._files, "get_bytes"
    ) as get_bytes:
        assert connector.get_series(FRANKENSTEIN) is None
    get_bytes.assert_not_called()


def test_non_english_chapters_are_refused(connector: GutenbergConnector):
    counts, api_patch, files_patch = _install_book(connector, ALICE, "pg11.epub")
    with api_patch, files_patch:
        chapters = connector.get_chapters(ALICE)
        key = chapters[1].id
        book = connector._books.get(ALICE)
        assert book is not None
        from connectors.archiveorg.epub import EpubChapter

        book.texts[key] = EpubChapter(
            key=key,
            title="Raw",
            number=2.0,
            paragraphs=("这是一段中文小说的正文内容。" * 12,),
        )
        assert connector.chapter_text(ALICE, key) is None


# --- upstream failure modes -------------------------------------------------


NOT_FOUND = "Client error '404 Not Found' for url 'https://gutendex.com/books/1'"


def test_a_404_reads_as_a_missing_series_not_a_network_failure(
    connector: GutenbergConnector,
):
    """The shared client leaves ``status_code`` None for a plain 404 (and
    ``get_bytes`` re-raises with no status at all), so the check must match
    the message too — a bare ``status_code == 404`` is dead code here."""
    error = ConnectorHttpError(NOT_FOUND)
    assert error.status_code is None  # the trap this guards

    with patch.object(connector._api, "get_json", side_effect=error):
        assert connector.get_series(FRANKENSTEIN) is None
        assert connector.get_chapters(FRANKENSTEIN) == []
        assert connector.chapter_text(FRANKENSTEIN, "x.html") is None


def test_a_404_on_the_download_also_reads_as_missing(connector: GutenbergConnector):
    detail = _load("gutendex_book_84.json")
    with patch.object(connector._api, "get_json", return_value=detail), patch.object(
        connector._files, "get_bytes", side_effect=ConnectorHttpError(NOT_FOUND)
    ):
        assert connector.get_series(FRANKENSTEIN) is None


def test_a_listing_page_past_the_end_is_empty_not_an_error(
    connector: GutenbergConnector,
):
    with patch.object(
        connector._api, "get_json", side_effect=ConnectorHttpError(NOT_FOUND)
    ):
        listing = connector.get_series_list(9999)
    assert listing.items == []
    assert listing.has_more is False


def test_a_real_network_failure_propagates(connector: GutenbergConnector):
    """The novel service serves its cache stale on ConnectorHttpError, so a
    503 must NOT be flattened into "this book no longer exists"."""
    error = ConnectorHttpError("Retryable HTTP 503", status_code=503)
    with patch.object(connector._api, "get_json", side_effect=error):
        with pytest.raises(ConnectorHttpError):
            connector.get_series(FRANKENSTEIN)
        with pytest.raises(ConnectorHttpError):
            connector.get_series_list(1)


def test_an_unusable_key_never_reaches_the_network(connector: GutenbergConnector):
    with patch.object(connector._api, "get_json") as get_json:
        assert connector.get_series("not-a-number") is None
        assert connector.get_chapters("") == []
        assert connector.chapter_text("   ", "x.html") is None
    get_json.assert_not_called()


def test_search_falls_back_to_browse_for_a_blank_query(connector: GutenbergConnector):
    seen: list[dict] = []

    def fake_get_json(path, params=None):
        seen.append(params or {})
        return _load("gutendex_popular.json")

    with patch.object(connector._api, "get_json", side_effect=fake_get_json):
        listing = connector.search_series("   ", 1)

    assert len(listing.items) == PAGE_SIZE
    assert "search" not in seen[0]
    assert seen[0]["sort"] == "popular"


def test_genre_browse_sends_the_topic(connector: GutenbergConnector):
    seen: list[dict] = []

    def fake_get_json(path, params=None):
        seen.append(params or {})
        return _load("gutendex_popular.json")

    with patch.object(connector._api, "get_json", side_effect=fake_get_json):
        connector.browse_by_genre("adventure", 1)

    assert seen[0]["topic"] == "adventure"
    assert seen[0]["mime_type"] == EPUB_MIME


# --- the book cache ---------------------------------------------------------


def _stub_book(name: str) -> _ParsedBook:
    return _ParsedBook(
        series=Series(id=name, title=name, chapter_count=1),
        chapters=[],
        texts={},
    )


def test_book_cache_evicts_least_recently_used_beyond_its_ceiling():
    """Unbounded caching would let a crawler walk 62,000 titles straight
    into the VPS's RAM; the ceiling is the guard."""
    cache = _BookCache(ttl_seconds=900.0, max_entries=2)
    cache.set("a", _stub_book("a"))
    cache.set("b", _stub_book("b"))
    # Touch "a" so "b" becomes the least recently used.
    assert cache.get("a") is not None
    cache.set("c", _stub_book("c"))

    assert cache.get("a") is not None
    assert cache.get("c") is not None
    assert cache.get("b") is None


def test_connector_cache_ceiling_is_small_enough_for_the_vps():
    assert 1 <= MAX_CACHED_BOOKS <= 8


def test_the_api_client_is_sized_for_gutendex_measured_latency(
    connector: GutenbergConnector,
):
    """Measured from the VPS on guaranteed-cold queries: 63-112s cold, ~0s
    warm, plus intermittent 503s. The 30s default cannot clear a cold query,
    so the timeout has real headroom — and because each attempt can cost the
    full timeout, the retry count is trimmed to bound the worst case.
    """
    assert API_TIMEOUT_SECONDS >= 60.0
    assert API_MAX_RETRIES >= 2  # a retry is what catches the now-warm cache
    # Worst case must stay bounded rather than stacking three long attempts.
    assert API_TIMEOUT_SECONDS * API_MAX_RETRIES <= 200.0
