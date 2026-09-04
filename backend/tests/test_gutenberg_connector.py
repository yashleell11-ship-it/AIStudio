"""Offline tests for the Project Gutenberg novel connector.

Fixtures under ``tests/fixtures/gutenberg/`` are live responses captured
2026-09-05 FROM THE VPS (production's exact egress and TLS stack — the probe
methodology in the novels spec §4). Nothing here touches the network; the
connector runs against those captures with ``self._http`` patched.

What the captures are, and why each one is here:

* ``pg_catalog_sample.csv.gz`` — the real ``pg_catalog.csv.gz`` header plus 32
  real rows of it, re-gzipped. The rows are chosen to exercise the filter
  rather than to be a sample of the library: 19 English texts, four Datasets,
  two StillImages, a MovingImage, and Spanish and French texts. The full feed
  is 5.6 MB / 79,288 rows, which is not a thing to keep in git.
* ``top1000.html`` — the download leaderboard, whole and unedited. It is big
  because every board on it is load-bearing: the parser has to pick
  ``books-last30`` out of five other boards that look exactly like it.
* ``ebook_84.html`` / ``ebook_1342.html`` — book pages that must be served.
* ``ebook_french_796.html``, ``ebook_audio_3002.html``,
  ``ebook_copyrighted_8760.html`` — real records that must be REFUSED, one per
  reason the bibrec gate exists: not English, not a text, not public domain.
* ``pg11.epub`` / ``pg1342.epub`` — two REAL Gutenberg EPUBs in the
  ``.epub.noimages`` build this connector requests. They are here because
  they are the two halves of the honest story about chapter boundaries:
  Alice splits one spine document per chapter, Pride and Prejudice groups
  several chapters into each document. Both are public-domain texts, and
  they are used only as parser input — the assertions below check structure
  (counts, keys, ordering, budgets), never prose.
"""

from __future__ import annotations

import gzip
import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.archiveorg.epub import EpubChapter, parse_epub
from connectors.gutenberg.connector import (
    CATALOG_TTL_SECONDS,
    GENRE_SHELVES,
    HTTP_TIMEOUT_SECONDS,
    MAX_CACHED_BOOKS,
    MAX_EPUB_BYTES,
    GutenbergConnector,
    _BookCache,
    _ParsedBook,
)
from connectors.gutenberg.mappers import (
    CATALOG_PATH,
    MAX_CATALOG_GZIP_BYTES,
    PAGE_SIZE,
    POPULAR_PATH,
    _author_name,
    chapters_from_epub,
    cover_url,
    decompress_catalog,
    detail_path,
    download_path,
    genre_entries,
    normalize_chapter_key,
    normalize_series_key,
    paginate,
    parse_book_page,
    parse_catalog,
    parse_popular_ids,
    popular_entries,
    search_entries,
)
from connectors.http.client import ConnectorHttpError
from connectors.models import Series

FIXTURES = Path(__file__).parent / "fixtures" / "gutenberg"

ALICE = "11"  # one spine document per chapter
PRIDE = "1342"  # several chapters grouped into each spine document
FRANKENSTEIN = "84"

ALICE_CHAPTERS = 13
PRIDE_CHAPTERS = 15

#: English texts in ``pg_catalog_sample.csv.gz``; the other 13 rows are the
#: media types and languages the filter has to drop.
SAMPLE_ENGLISH_TEXTS = 19


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _epub(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture(scope="module")
def catalog():
    """The sample feed, parsed once — every listing test reads the same index."""
    return parse_catalog(decompress_catalog(_epub("pg_catalog_sample.csv.gz")))


# --- the download choice, which is the whole cost story ---------------------


def test_download_path_uses_the_noimages_build():
    """The site advertises ``.epub3.images``; this connector asks for
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


def test_no_path_this_connector_reads_is_the_disallowed_search_endpoint():
    """robots.txt disallows exactly one path, ``/ebooks/search`` — which is
    why the catalogue index exists. A search that started asking the site
    would be a robots violation, not just a slow query."""
    paths = [CATALOG_PATH, POPULAR_PATH, detail_path("84"), download_path("84")]
    assert all(not path.startswith("/ebooks/search") for path in paths)


# --- identity ---------------------------------------------------------------


def test_series_key_is_the_ebook_id_and_normalizes_from_every_url_form():
    assert normalize_series_key("84") == FRANKENSTEIN
    assert normalize_series_key("ebooks/84") == FRANKENSTEIN
    assert normalize_series_key("https://www.gutenberg.org/ebooks/84") == FRANKENSTEIN
    assert normalize_series_key("84.epub.noimages") == FRANKENSTEIN
    assert detail_path(FRANKENSTEIN) == "/ebooks/84"


def test_a_key_that_is_not_an_ebook_id_normalizes_to_empty():
    """Anything else must be refused locally rather than sent upstream."""
    for bad in ("", "   ", "not-a-number", "/", "ebooks/", "../../etc/passwd"):
        assert normalize_series_key(bad) == ""


def test_chapter_key_is_a_manifest_href_with_the_fragment_stripped():
    assert normalize_chapter_key("11-h-1.htm.html") == "11-h-1.htm.html"
    assert normalize_chapter_key("11-h-1.htm.html#chap01") == "11-h-1.htm.html"


def test_cover_url_is_derived_from_the_id_so_a_listing_costs_no_lookups():
    assert cover_url("84").endswith("/cache/epub/84/pg84.cover.medium.jpg")


# --- the catalogue feed -----------------------------------------------------


def test_the_feed_is_filtered_to_english_texts(catalog):
    """The feed is the whole library — audio, images, datasets and 40 other
    languages included. Only what this connector can open may reach a shelf."""
    assert len(catalog) == SAMPLE_ENGLISH_TEXTS
    assert catalog.get("2701") is not None  # Moby-Dick, en Text
    assert catalog.get("50") is None  # "Pi", a Dataset
    assert catalog.get("114") is None  # a StillImage
    assert catalog.get("2000") is None  # Don Quijote, es
    assert catalog.get("796") is None  # La Chartreuse De Parme, fr


def test_columns_are_located_by_name_not_by_position():
    """The feed has gained columns before. A parser that counted commas would
    start serving subjects as titles the day it gains another."""
    rows = decompress_catalog(_epub("pg_catalog_sample.csv.gz")).splitlines()
    header, first = rows[0].split(","), rows[1]
    widened = ",".join(["Nonsense"] + header) + "\n" + "x," + first + "\n"
    parsed = parse_catalog(widened)
    assert len(parsed) == 1
    assert parsed.oldest[0].title


def test_a_feed_without_the_expected_columns_is_empty_not_garbage():
    assert len(parse_catalog("a,b,c\n1,2,3\n")) == 0
    assert len(parse_catalog("")) == 0


def test_the_two_orderings_share_their_entries(catalog):
    """``newest`` is the feed reversed, not a second copy of 61,606 rows."""
    assert catalog.newest[0] is catalog.oldest[-1]
    assert catalog.oldest[0].book_id == "1"


def test_a_catalogue_row_is_a_listing_card_that_cost_no_download(catalog):
    listing = paginate(catalog.oldest, 1)
    for item in listing.items:
        # The real count needs the book itself; the detail view fills it in.
        assert item.chapter_count == 0
        assert item.status == "completed"
        assert item.cover_url and item.cover_url.startswith("https://")
    frankenstein = catalog.get(FRANKENSTEIN)
    assert frankenstein.title == "Frankenstein; or, the modern prometheus"
    assert frankenstein.author == "Mary Wollstonecraft Shelley"
    assert "Novels" in frankenstein.genres


def test_genre_labels_are_pooled_across_rows(catalog):
    """A few thousand labels are repeated across 61,606 rows; pooling is what
    keeps that from being 370,000 near-duplicate strings in the VPS's RAM."""
    shared = [
        label
        for entry in catalog.oldest
        for label in entry.genres
        if label == "Novels"
    ]
    assert len(shared) > 1
    assert all(label is shared[0] for label in shared)


def test_a_feed_that_expands_without_bound_is_refused():
    """The ceiling is read one byte past, so a hostile feed is refused rather
    than materialized first (the same reasoning as the EPUB zip-bomb cap)."""
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as stream:
        stream.write(b"a" * 200_000_000)
    assert decompress_catalog(buffer.getvalue()) is None


def test_a_response_that_is_not_a_feed_is_refused_not_parsed():
    assert decompress_catalog(b"") is None
    assert decompress_catalog(b"<html>error</html>") is None
    assert decompress_catalog(b"\x00" * (MAX_CATALOG_GZIP_BYTES + 1)) is None


# --- the popularity board ---------------------------------------------------


def test_popular_ids_come_from_the_thirty_day_board_only():
    """The page carries six boards. Three are author boards whose links are
    ``/ebooks/author/...``, and the other two are yesterday's and last week's
    books — anchoring on the heading id is what keeps them out."""
    ids = parse_popular_ids(_text("top1000.html"))
    assert len(ids) == 1000
    assert len(set(ids)) == 1000
    assert all(book_id.isdigit() for book_id in ids)
    assert ids[0] == "2701"
    # The boards share their head but not their tail; last-1 ends 2814 and
    # last-7 ends 48895, so this pins which one was read.
    assert ids[-1] == "22553"


def test_a_board_that_stops_parsing_yields_nothing_rather_than_nonsense():
    assert parse_popular_ids("<html><ol><li><a href='/ebooks/1'>x</a></ol>") == ()
    assert parse_popular_ids("") == ()


def test_popular_order_is_kept_and_unservable_ids_are_dropped(catalog):
    """Roughly 150 of the board's 1,000 rows are audio or another language.
    Dropping them beats listing a book that 404s when a reader taps it."""
    ids = parse_popular_ids(_text("top1000.html"))
    ordered = popular_entries(catalog, ids)
    assert [entry.book_id for entry in ordered][:4] == ["2701", "1342", "1661", "11"]
    assert len(ordered) < len(ids)
    assert all(catalog.get(entry.book_id) is not None for entry in ordered)


def test_a_repeated_id_on_the_board_is_listed_once(catalog):
    assert [e.book_id for e in popular_entries(catalog, ("84", "84", "11"))] == [
        "84",
        "11",
    ]


# --- search and genre over the local index ----------------------------------


def test_search_ranks_titles_above_authors(catalog):
    """The index is ordered by ebook number, so unranked, "austen" would
    answer with whichever Austen novel Gutenberg digitized first."""
    hits = search_entries(catalog, "pride and prejudice")
    assert hits[0].book_id == PRIDE
    by_author = search_entries(catalog, "austen")
    assert {entry.book_id for entry in by_author} == {"158", PRIDE}
    mixed = search_entries(catalog, "dracula")
    assert [entry.book_id for entry in mixed] == ["345"]


def test_search_is_case_and_whitespace_insensitive(catalog):
    assert search_entries(catalog, "  ALICE  ")[0].book_id == ALICE


def test_a_blank_search_matches_nothing_rather_than_everything(catalog):
    assert search_entries(catalog, "   ") == []


def test_genre_matches_the_label_a_card_displays_not_a_substring(catalog):
    """Equality, not substring: a substring match on "Novels" would also pull
    in "Historical Novels", and a reader filtering on one would get the other."""
    novels = genre_entries(catalog, "Novels")
    assert novels
    assert all("Novels" in entry.genres for entry in novels)
    assert genre_entries(catalog, "Novel") == []
    assert genre_entries(catalog, "  novels ")  # case/space insensitive


def test_every_advertised_genre_is_a_label_the_parser_can_produce():
    """An advertised genre that matches nothing is a dead end. The parser
    strips Gutenberg's ``Category:``/``Browsing:`` prefixes, so a shelf id
    carrying one could never match a parsed label."""
    assert GENRE_SHELVES
    for shelf, label in GENRE_SHELVES:
        assert shelf and shelf == shelf.strip()
        assert not shelf.startswith(("Category:", "Browsing:"))
        assert label


def test_the_sample_feed_populates_the_shelves_it_carries(catalog):
    for shelf in ("Novels", "Romance", "Science-Fiction & Fantasy"):
        assert genre_entries(catalog, shelf), shelf


# --- pagination -------------------------------------------------------------


def test_pagination_slices_the_index(catalog):
    entries = list(catalog.oldest) * 4  # 76 rows, so page 3 is a partial page
    page1 = paginate(entries, 1)
    page2 = paginate(entries, 2)
    assert len(page1.items) == PAGE_SIZE
    assert page1.total == len(entries)
    assert page1.has_more is True
    assert page1.items[0].id != page2.items[0].id
    assert len(paginate(entries, 3).items) == len(entries) - 2 * PAGE_SIZE


def test_a_page_past_the_end_is_empty_not_an_error(catalog):
    listing = paginate(catalog.oldest, 9999)
    assert listing.items == []
    assert listing.has_more is False


def test_page_zero_reads_as_page_one(catalog):
    assert paginate(catalog.oldest, 0).page == 1


# --- a book's own page ------------------------------------------------------


def test_a_public_domain_english_text_is_served():
    series = parse_book_page(_text("ebook_84.html"), FRANKENSTEIN)
    assert series is not None
    assert series.title == "Frankenstein; or, the modern prometheus"
    assert series.author == "Mary Wollstonecraft Shelley"
    assert series.genres[0] == "Science fiction"
    assert series.description and "Frankenstein" in series.description
    assert series.cover_url == cover_url(FRANKENSTEIN)


def test_the_summary_includes_the_half_folded_behind_read_more():
    """The container holds the whole blurb; the site merely folds its tail
    into a span a checkbox reveals. Serving the teaser would cut a sentence
    off mid-word."""
    series = parse_book_page(_text("ebook_1342.html"), PRIDE)
    assert series is not None and series.description
    assert "Read more" not in series.description
    assert len(series.description) > 400


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("ebook_french_796.html", "not English"),
        ("ebook_audio_3002.html", "not a text"),
        ("ebook_copyrighted_8760.html", "not public domain"),
    ],
)
def test_a_record_the_bibrec_does_not_vouch_for_is_refused(name: str, why: str):
    """The three facts a catalogue row cannot carry. A missing rights row
    means "unknown", which is not good enough to redistribute."""
    assert parse_book_page(_text(name), "1") is None, why


def test_a_page_without_a_bibrec_table_is_refused():
    assert parse_book_page("<html><body>nope</body></html>", "1") is None


def test_author_names_are_flipped_and_stripped_of_their_life_dates():
    assert _author_name("Austen, Jane, 1775-1817") == "Jane Austen"
    assert _author_name("Baum, L. Frank (Lyman Frank), 1856-1919; Norris, William") == (
        "L. Frank (Lyman Frank) Baum"
    )
    assert _author_name("Aristotle, 384 BCE-322 BCE") == "Aristotle"
    assert _author_name("Various") == "Various"
    # A name still carrying a second comma is left alone rather than scrambled.
    assert _author_name("Ward, Humphry, Mrs.") == "Ward, Humphry, Mrs."
    assert _author_name("  ") == ""


# --- EPUB structure ---------------------------------------------------------


def test_chapters_are_the_books_own_spine_documents():
    """Never a heuristic split of running text: Alice is one document per
    chapter, Pride and Prejudice groups several chapters into each."""
    alice = parse_epub(_epub("pg11.epub"))
    pride = parse_epub(_epub("pg1342.epub"))
    assert len(alice.chapters) == ALICE_CHAPTERS
    assert len(pride.chapters) == PRIDE_CHAPTERS

    chapters = chapters_from_epub(ALICE, alice.chapters)
    assert [chapter.id for chapter in chapters] == [c.key for c in alice.chapters]
    assert all(chapter.series_id == ALICE for chapter in chapters)
    assert all(chapter.page_count == 0 for chapter in chapters)
    assert [c.number for c in chapters] == sorted(c.number for c in chapters)


# --- connector behaviour ----------------------------------------------------


@pytest.fixture()
def connector() -> GutenbergConnector:
    return GutenbergConnector()


class _FakeSite:
    """The four paths this connector reads, and a count of what each cost.

    Every book page answers with Frankenstein's record whatever id is asked
    for: these tests pin structure and request cost, and the id the connector
    serves back is its own argument, never anything the page carried.
    """

    def __init__(self, book_id: str = ALICE, epub_name: str = "pg11.epub") -> None:
        self.book_id = book_id
        self.epub_name = epub_name
        self.text_calls: list[str] = []
        self.byte_calls: list[str] = []

    def get_text(self, path: str, **_kwargs) -> str:
        self.text_calls.append(path)
        if path == POPULAR_PATH:
            return _text("top1000.html")
        return _text("ebook_84.html")

    def get_bytes(self, path: str, **_kwargs) -> tuple[str, bytes]:
        self.byte_calls.append(path)
        if path == CATALOG_PATH:
            return "application/gzip", _epub("pg_catalog_sample.csv.gz")
        return "application/epub+zip", _epub(self.epub_name)

    @property
    def requests(self) -> int:
        return len(self.text_calls) + len(self.byte_calls)


def _serving(connector: GutenbergConnector, site: _FakeSite):
    return patch.object(connector, "_http", site)


def _raises(error: Exception):
    """A read that fails the way the live client would fail."""

    def fail(*_args, **_kwargs):
        raise error

    return fail


def test_connector_declares_the_novel_contract(connector: GutenbergConnector):
    assert connector.content_kind == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.source_type == "gutenberg"
    assert connector.is_mature is False
    assert connector.get_chapter_pages("anything") == []
    assert connector.find_page("anything") is None


def test_cover_host_is_inside_the_image_allowlist(connector: GutenbergConnector):
    host = cover_url("84").split("/")[2]
    assert any(
        host == domain or host.endswith(f".{domain}")
        for domain in connector.allowed_image_hosts
    )


def test_a_browse_page_costs_two_requests_cold_and_none_warm(
    connector: GutenbergConnector,
):
    """The point of the rewrite. Against gutendex a browse page cost 194 s
    across 147 round trips and the reads behind it never ran at all; here the
    catalogue and the leaderboard are fetched once and every later listing is
    sliced out of memory."""
    site = _FakeSite()
    with _serving(connector, site):
        first = connector.get_series_list(1)
        assert site.byte_calls == [CATALOG_PATH]
        assert site.text_calls == [POPULAR_PATH]

        before = site.requests
        again = connector.get_series_list(1)
        connector.get_series_list(2)
        connector.search_series("alice", 1)
        connector.browse_by_genre("Novels", 1)
        connector.get_series_list(1, sort="newest")
        connector.get_series_list(1, sort="oldest")
        assert site.requests == before

    assert first.items
    assert [item.id for item in again.items] == [item.id for item in first.items]
    assert first.items[0].id == "2701"  # the leaderboard's order, not the feed's


def test_browse_falls_back_to_the_newest_books_when_the_board_stops_parsing(
    connector: GutenbergConnector,
):
    """The leaderboard is the only popularity signal Gutenberg publishes.
    Losing it must not hand the reader an empty shelf."""
    site = _FakeSite()
    site.get_text = lambda path, **_: ""  # type: ignore[assignment]
    with _serving(connector, site):
        listing = connector.get_series_list(1)
    assert listing.items
    assert listing.items[0].id == "16328"  # the newest row in the sample feed


def test_an_unreadable_feed_is_an_error_not_an_empty_library(
    connector: GutenbergConnector,
):
    """Serving zero books looks to every caller like "Gutenberg has nothing",
    which would poison the source-health signal and the reader's shelf alike."""
    site = _FakeSite()
    site.get_bytes = lambda path, **_: ("text/html", b"<html>nope</html>")  # type: ignore[assignment]
    with _serving(connector, site), pytest.raises(ConnectorHttpError):
        connector.get_series_list(1)


def test_the_catalogue_is_built_once_even_under_concurrent_readers(
    connector: GutenbergConnector,
):
    """Connectors are shared singletons across request threads; without the
    lock a cold source hit by several readers downloads 5.6 MB per thread."""
    import threading

    site = _FakeSite()
    with _serving(connector, site):
        threads = [
            threading.Thread(target=connector.get_series_list, args=(1,))
            for _ in range(6)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert site.byte_calls == [CATALOG_PATH]


def test_one_book_feeds_series_chapters_and_every_chapter_text(
    connector: GutenbergConnector,
):
    """Reading a whole book costs the record plus one download, not one
    request per chapter."""
    site = _FakeSite()
    with _serving(connector, site):
        series = connector.get_series(ALICE)
        chapters = connector.get_chapters(ALICE)
        texts = [connector.chapter_text(ALICE, chapter.id) for chapter in chapters]

    assert series is not None
    assert series.chapter_count == ALICE_CHAPTERS
    assert len(chapters) == ALICE_CHAPTERS
    assert all(text is not None for text in texts)
    assert site.text_calls == [detail_path(ALICE)]
    assert site.byte_calls == [download_path(ALICE)]


def test_chapter_text_carries_its_number_and_title(connector: GutenbergConnector):
    site = _FakeSite()
    with _serving(connector, site):
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
    with _serving(connector, _FakeSite()):
        assert connector.chapter_text(ALICE, "no-such-document.html") is None


def test_non_english_chapters_are_refused(connector: GutenbergConnector):
    """The source declares ``LANGUAGE = "en"``; a spine document that is not
    English must not reach a reader who chose an English source."""
    with _serving(connector, _FakeSite()):
        chapters = connector.get_chapters(ALICE)
        key = chapters[1].id
        book = connector._books.get(ALICE)
        assert book is not None
        book.texts[key] = EpubChapter(
            key=key,
            title="Raw",
            number=2.0,
            paragraphs=("这是一段中文小说的正文内容。" * 12,),
        )
        assert connector.chapter_text(ALICE, key) is None


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

    site = _FakeSite()
    site.get_bytes = lambda path, **_: ("application/epub+zip", oversized)  # type: ignore[assignment]
    with _serving(connector, site):
        assert connector.get_series(FRANKENSTEIN) is None


def test_a_book_whose_epub_yields_no_chapters_is_not_served_as_a_shell(
    connector: GutenbergConnector,
):
    site = _FakeSite()
    site.get_bytes = lambda path, **_: ("application/epub+zip", b"junk")  # type: ignore[assignment]
    with _serving(connector, site):
        assert connector.get_series(FRANKENSTEIN) is None
        assert connector.get_chapters(FRANKENSTEIN) == []


def test_a_copyrighted_record_is_refused_before_anything_is_downloaded(
    connector: GutenbergConnector,
):
    site = _FakeSite()
    site.get_text = lambda path, **_: _text("ebook_copyrighted_8760.html")  # type: ignore[assignment]
    with _serving(connector, site):
        assert connector.get_series("8760") is None
    assert site.byte_calls == []


# --- upstream failure modes -------------------------------------------------


NOT_FOUND = "Client error '404 Not Found' for url 'https://www.gutenberg.org/ebooks/1'"


def test_a_404_reads_as_a_missing_series_not_a_network_failure(
    connector: GutenbergConnector,
):
    """The shared client leaves ``status_code`` None for a plain 404 (and
    ``get_bytes`` re-raises with no status at all), so the check must match
    the message too — a bare ``status_code == 404`` is dead code here."""
    error = ConnectorHttpError(NOT_FOUND)
    assert error.status_code is None  # the trap this guards

    site = _FakeSite()
    site.get_text = _raises(error)
    with _serving(connector, site):
        assert connector.get_series(FRANKENSTEIN) is None
        assert connector.get_chapters(FRANKENSTEIN) == []
        assert connector.chapter_text(FRANKENSTEIN, "x.html") is None


def test_a_404_on_the_download_also_reads_as_missing(connector: GutenbergConnector):
    site = _FakeSite()
    site.get_bytes = _raises(ConnectorHttpError(NOT_FOUND))
    with _serving(connector, site):
        assert connector.get_series(FRANKENSTEIN) is None


def test_a_real_network_failure_propagates(connector: GutenbergConnector):
    """The novel service serves its cache stale on ConnectorHttpError, so a
    503 must NOT be flattened into "this book no longer exists"."""
    error = ConnectorHttpError("Retryable HTTP 503", status_code=503)
    site = _FakeSite()
    site.get_text = _raises(error)
    site.get_bytes = _raises(error)
    with _serving(connector, site):
        with pytest.raises(ConnectorHttpError):
            connector.get_series(FRANKENSTEIN)
        with pytest.raises(ConnectorHttpError):
            connector.get_series_list(1)


def test_an_unusable_key_never_reaches_the_network(connector: GutenbergConnector):
    site = _FakeSite()
    with _serving(connector, site):
        assert connector.get_series("not-a-number") is None
        assert connector.get_chapters("") == []
        assert connector.chapter_text("   ", "x.html") is None
    assert site.requests == 0


def test_a_blank_search_falls_back_to_browse(connector: GutenbergConnector):
    with _serving(connector, _FakeSite()):
        listing = connector.search_series("   ", 1)
    assert listing.items
    assert listing.items[0].id == "2701"  # the popularity ordering


# --- the caches -------------------------------------------------------------


def _stub_book(name: str) -> _ParsedBook:
    return _ParsedBook(
        series=Series(id=name, title=name, chapter_count=1),
        chapters=[],
        texts={},
    )


def test_book_cache_evicts_least_recently_used_beyond_its_ceiling():
    """Unbounded caching would let a crawler walk 61,000 titles straight
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


def test_clearing_the_book_cache_also_clears_its_lru_order():
    """A cleared cache that kept its key order would evict phantom entries and
    hold fewer books than its ceiling for the rest of the process."""
    cache = _BookCache(ttl_seconds=900.0, max_entries=2)
    cache.set("a", _stub_book("a"))
    cache.set("b", _stub_book("b"))
    cache.clear()
    cache.set("c", _stub_book("c"))
    cache.set("d", _stub_book("d"))
    assert cache.get("c") is not None
    assert cache.get("d") is not None


def test_connector_cache_ceiling_is_small_enough_for_the_vps():
    assert 1 <= MAX_CACHED_BOOKS <= 8


def test_the_catalogue_ttl_lets_an_idle_source_let_go():
    """Gutenberg regenerates the feed daily, so a shorter TTL re-downloads the
    same bytes; a longer one holds ~25 MB of a 3.8 GB box for a source nobody
    is reading."""
    assert 3_600.0 <= CATALOG_TTL_SECONDS <= 86_400.0


def test_the_client_timeout_is_sized_for_a_generated_epub():
    """Every catalogue path answered in under 0.3 s from the VPS; the headroom
    is for the EPUB, which gutenberg.org sometimes generates on demand."""
    assert HTTP_TIMEOUT_SECONDS >= 30.0
