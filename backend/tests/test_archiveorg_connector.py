"""Offline tests for the Internet Archive (archive.org) novel connector.

Fixtures under ``tests/fixtures/archiveorg/`` are live responses captured
2026-09-04 FROM THE VPS (production's exact egress/TLS -- the probe
methodology in the novels spec §4). Nothing here touches the network; the
connector runs against those captures with ``self._http.get_json`` /
``get_bytes`` patched.

What the captures are, and why each one is here:

* ``search_browse.json`` -- the default browse view (scope + ``downloads
  desc``), captured at **page 3**; the page number matters because the
  pagination assertions below pin ``start=40``.
* ``search_sherlock.json`` -- the same scope narrowed by search terms.
* ``search_deep_paging_error.json`` -- archive.org's ``200 {"error":
  "[DEEP_PAGING] ..."}`` past 10,000 results. There is no error status to
  match on; the body IS the error.
* ``metadata_missing.json`` -- ``200 {}``, how a nonexistent identifier
  answers. Also not a 404.
* ``metadata_thewonderfulwiza43936gut.json`` -- an item shipping BOTH
  ``pg43936.epub`` (105 KB) and ``pg43936-images.epub`` (9.9 MB) of the
  same book, which is what the EPUB-choice rule exists for.
* ``metadata_mobywordlists03201gut.json`` -- a real Gutenberg item with no
  EPUB at all (Text/ZIP/XML only): the skip path.
* ``pg1661.epub`` / ``bram-stoker_dracula.epub`` -- the two book dialects
  the connector must handle: EPUB 2 + NCX with Project Gutenberg licence
  wrappers, and EPUB 3 + nav with Standard Ebooks apparatus.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.archiveorg.connector import (
    MAX_CACHED_BOOKS,
    MAX_EPUB_BYTES,
    ArchiveOrgConnector,
    _BookCache,
)
from connectors.archiveorg.epub import (
    BOILERPLATE_EPUB_TYPES,
    MIN_CHAPTER_WORDS,
    _resolve,
    parse_epub,
)
from connectors.archiveorg.mappers import (
    DEEP_PAGING_LIMIT,
    MAX_PAGE,
    PAGE_SIZE,
    PUBLIC_DOMAIN_SCOPE,
    epub_filename,
    parse_search,
    safe_terms,
    scoped_query,
    search_params,
    series_from_metadata,
)
from connectors.http.client import ConnectorHttpError

FIXTURES = Path(__file__).parent / "fixtures" / "archiveorg"

SHERLOCK = "theadventuresofs01661gut"  # Project Gutenberg, EPUB 2 + NCX
DRACULA = "bram-stoker_dracula"  # Standard Ebooks, EPUB 3 + nav
OZ = "thewonderfulwiza43936gut"  # two EPUBs, one of them illustrated
WORDLISTS = "mobywordlists03201gut"  # a real Gutenberg item with no EPUB


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _epub(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# --- scope: the whole point of this connector's query ------------------------


def test_scope_targets_curated_public_domain_collections_only():
    """The scope must stay pinned to collections that are public domain by
    curation. Widening it to the opensource/community upload space is the
    documented failure mode this assertion guards."""
    assert "collection:(gutenberg OR standardebooks)" in PUBLIC_DOMAIN_SCOPE
    assert "format:EPUB" in PUBLIC_DOMAIN_SCOPE
    # English is filtered upstream, not client-side, and all three spellings
    # are live values in this corpus.
    assert "language:(eng OR en OR English)" in PUBLIC_DOMAIN_SCOPE
    assert "opensource" not in PUBLIC_DOMAIN_SCOPE
    assert "community" not in PUBLIC_DOMAIN_SCOPE


@pytest.mark.parametrize(
    "hostile",
    [
        ") OR collection:opensource AND (",
        "dracula) OR (mediatype:texts",
        'foo" OR collection:community OR "',
        "x AND NOT collection:gutenberg",
        "*:*",
    ],
)
def test_search_terms_cannot_break_out_of_the_scope_clause(hostile):
    """The scope is a Lucene query STRING, so an unescaped bracket in a user
    term would close the collection clause and browse all 52M items. Terms
    are reduced to bare words, which can only ever narrow the search."""
    query = scoped_query(hostile)
    assert query.startswith(PUBLIC_DOMAIN_SCOPE)
    # Whatever survives is either nothing at all (the bare scope) or one
    # trailing AND clause of inert words.
    tail = query[len(PUBLIC_DOMAIN_SCOPE) :]
    if not tail:
        return
    assert tail.startswith(" AND (") and tail.endswith(")")
    injected = tail[len(" AND (") : -1]
    for forbidden in ("(", ")", ":", '"', "*"):
        assert forbidden not in injected
    for operator in (" OR ", " AND ", " NOT "):
        assert operator not in f" {injected} "


def test_safe_terms_keeps_real_words_and_drops_lucene_grammar():
    assert safe_terms("The Hound of the Baskervilles") == "The Hound of the Baskervilles"
    assert safe_terms("Twenty-One Balloons") == "Twenty-One Balloons"  # hyphen kept
    assert safe_terms("-excluded") == "excluded"  # leading NOT stripped
    assert safe_terms("a AND b OR c") == "a b c"
    assert safe_terms("!!! ???") == ""


def test_empty_query_searches_the_bare_scope():
    assert scoped_query("") == PUBLIC_DOMAIN_SCOPE
    assert scoped_query(None) == PUBLIC_DOMAIN_SCOPE


def test_search_params_ask_for_the_fields_the_listing_maps():
    params = search_params("sherlock holmes", 2, sort="recent")
    assert params["q"].endswith("AND (sherlock holmes)")
    assert params["rows"] == PAGE_SIZE
    assert params["page"] == 2
    assert params["sort[]"] == "addeddate desc"
    assert "identifier" in params["fl[]"] and "creator" in params["fl[]"]


# --- listings ----------------------------------------------------------------


def test_parse_browse_listing():
    listing = parse_search(_load("search_browse.json"), page=3)
    assert len(listing.items) == PAGE_SIZE
    assert listing.total == 29613
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == "davidcopperfield00766gut"
    assert first.title == "David Copperfield"
    assert first.author == "Dickens, Charles, 1812-1870"
    assert first.cover_url == (
        "https://archive.org/services/img/davidcopperfield00766gut"
    )
    # Library subject headings ("Boys -- Fiction") keep only the facet.
    assert "Boys" in first.genres
    assert not any(" -- " in genre for genre in first.genres)
    # A published book is finished, and a listing costs no book fetch, so it
    # cannot know the chapter count.
    assert first.status == "completed"
    assert first.chapter_count == 0


def test_parse_search_listing_finds_the_target():
    listing = parse_search(_load("search_sherlock.json"), page=1)
    assert listing.items
    assert any("Sherlock" in item.title for item in listing.items)
    assert all(item.cover_url and item.id for item in listing.items)


def test_deep_paging_error_body_is_an_empty_page_not_a_crash(caplog):
    """archive.org answers HTTP 200 with an ``error`` body past 10,000
    results. There is no status code to notice, so the mapper must -- and it
    must say so: an error body and an empty result set look identical to a
    reader, but only one of them means this connector asked a bad question."""
    payload = _load("search_deep_paging_error.json")
    assert "DEEP_PAGING" in payload["error"]  # the capture really is the error

    with caplog.at_level(logging.WARNING, logger="connectors.archiveorg.mappers"):
        listing = parse_search(payload, page=900)
    assert listing.items == []
    assert listing.has_more is False
    assert any("DEEP_PAGING" in record.getMessage() for record in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="connectors.archiveorg.mappers"):
        parse_search(_load("search_no_results.json"), page=1)
    assert caplog.records == []  # a genuinely empty page is not a warning


def test_has_more_is_clamped_at_the_deep_paging_wall():
    """29,613 results exist but only 10,000 are reachable; promising a page
    the API will refuse just makes the client fetch an error."""
    payload = _load("search_browse.json")
    last = parse_search(payload, page=MAX_PAGE)
    assert last.has_more is False
    assert MAX_PAGE * PAGE_SIZE == DEEP_PAGING_LIMIT
    assert parse_search(payload, page=MAX_PAGE - 1).has_more is True


def test_empty_result_set_is_an_empty_page():
    listing = parse_search(_load("search_no_results.json"), page=1)
    assert listing.items == []
    assert listing.has_more is False


# --- picking the one EPUB to download ----------------------------------------


def test_epub_choice_prefers_text_only_over_the_illustrated_twin():
    """The Wizard of Oz item ships pg43936.epub (105 KB) and
    pg43936-images.epub (9.9 MB): same prose, 94x the bytes. The illustrated
    twin is listed FIRST, so a "take whatever comes first" rule would pick
    it; raising the byte ceiling past both proves the preference itself is
    doing the work and not the size cap."""
    payload = _load(f"metadata_{OZ}.json")
    epubs = [f["name"] for f in payload["files"] if f.get("format") == "EPUB"]
    assert epubs == ["pg43936-images.epub", "pg43936.epub"]  # worst one first
    assert epub_filename(payload, max_bytes=MAX_EPUB_BYTES) == "pg43936.epub"
    assert epub_filename(payload, max_bytes=50_000_000) == "pg43936.epub"


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 0, 2)])
def test_epub_choice_is_independent_of_the_order_files_are_listed(order):
    files = [
        {"name": "big.epub", "format": "EPUB", "size": "900000"},
        {"name": "book-images.epub", "format": "EPUB", "size": "120000"},
        {"name": "book.epub", "format": "EPUB", "size": "300000"},
    ]
    payload = {"files": [files[i] for i in order]}
    # Smallest overall is the illustrated one; the text-only edition still
    # wins, and among text-only editions the smaller does.
    assert epub_filename(payload, max_bytes=MAX_EPUB_BYTES) == "book.epub"


def test_epub_choice_on_a_single_epub_item():
    assert (
        epub_filename(_load(f"metadata_{SHERLOCK}.json"), max_bytes=MAX_EPUB_BYTES)
        == "pg1661.epub"
    )


def test_item_with_no_epub_is_skipped():
    """A real Gutenberg item that only ships Text/ZIP/XML. Its DjVuTXT-class
    text is OCR of scanned pages and cannot be split into chapters, so the
    item is skipped rather than served as damaged prose."""
    payload = _load(f"metadata_{WORDLISTS}.json")
    formats = {f.get("format") for f in payload["files"]}
    assert "EPUB" not in formats  # the capture really has no EPUB
    assert epub_filename(payload, max_bytes=MAX_EPUB_BYTES) is None


def test_oversized_epub_is_refused_before_it_is_downloaded():
    payload = _load(f"metadata_{OZ}.json")
    assert epub_filename(payload, max_bytes=50_000) is None
    assert epub_filename(payload, max_bytes=200_000) == "pg43936.epub"


def test_missing_item_metadata_is_the_empty_object_not_a_404():
    payload = _load("metadata_missing.json")
    assert payload == {}  # this is genuinely what archive.org returns
    assert series_from_metadata(payload, "whatever") is None
    assert epub_filename(payload, max_bytes=MAX_EPUB_BYTES) is None


# --- EPUB 2 (Project Gutenberg): spine -> chapters ---------------------------


def test_gutenberg_epub_becomes_ordered_chapters():
    book = parse_epub(_epub("pg1661.epub"))
    assert book is not None
    assert book.title == "The Adventures of Sherlock Holmes"
    assert book.author == "Sir Arthur Conan Doyle"
    assert len(book.chapters) == 11
    # Numbers are the position in the READABLE spine: contiguous from 1, so
    # the reader's furthest-wins progress merge behaves.
    assert [c.number for c in book.chapters] == [float(n) for n in range(1, 12)]
    # Titles come from the book's own NCX navMap.
    assert book.chapters[1].title == "ADVENTURE II. THE RED-HEADED LEAGUE"
    assert book.chapters[-1].title == "XII. THE ADVENTURE OF THE COPPER BEECHES"
    # Keys are the spine hrefs, which live inside the book file itself.
    assert all(c.key.endswith(".html") for c in book.chapters)
    assert len({c.key for c in book.chapters}) == 11


def test_gutenberg_licence_wrapper_never_reaches_the_reader():
    """pg1661's spine holds the PG header document and the full licence
    document. Neither is the book; both must be gone."""
    raw = _epub("pg1661.epub")
    inside = zipfile.ZipFile(io.BytesIO(raw))
    all_text = " ".join(
        inside.read(n).decode("utf-8", "replace")
        for n in inside.namelist()
        if n.endswith(".html")
    )
    assert "START OF THIS PROJECT GUTENBERG EBOOK" in all_text  # it IS in there
    assert "THE FULL PROJECT GUTENBERG LICENSE" in all_text

    book = parse_epub(raw)
    served = "\n".join(p for c in book.chapters for p in c.paragraphs)
    assert "PROJECT GUTENBERG EBOOK" not in served.upper()
    assert "FULL LICENSE" not in served.upper()
    assert "gutenberg-tm" not in served.lower()


def test_chapter_paragraphs_are_clean_plain_text():
    book = parse_epub(_epub("pg1661.epub"))
    chapter = book.chapters[1]
    joined = "\n".join(chapter.paragraphs)
    assert "Sherlock Holmes" in joined  # the story survived
    assert chapter.word_count > 5000
    assert "<" not in joined  # no markup
    assert "\n\n" not in joined  # paragraphs are single blocks
    assert all(p == p.strip() and p for p in chapter.paragraphs)


# --- EPUB 3 (Standard Ebooks): the other dialect -----------------------------


def test_standard_ebooks_epub3_nav_and_apparatus():
    book = parse_epub(_epub("bram-stoker_dracula.epub"))
    assert book is not None
    assert book.title == "Dracula"
    assert book.author == "Bram Stoker"
    # 27 numbered chapters + the Preface + the closing "Note".
    assert len(book.chapters) == 29
    assert book.chapters[0].title == "Preface"
    assert book.chapters[1].title == "I"
    assert book.chapters[-1].title == "Note"
    assert book.chapters[1].key == "text/chapter-1.xhtml"


def test_epub3_apparatus_is_dropped_by_its_own_semantics():
    """Standard Ebooks tags apparatus with ``epub:type``; the connector reads
    that rather than guessing from filenames. Titlepage/imprint/colophon/
    uncopyright go, and a 76-word Preface tagged ``frontmatter`` stays --
    which is why the coarse frontmatter/backmatter values are NOT filtered."""
    # The coarse structural values must stay OUT of the filter set.
    assert {"imprint", "colophon", "copyright-page", "titlepage"} <= BOILERPLATE_EPUB_TYPES
    assert not {"frontmatter", "backmatter", "bodymatter"} & BOILERPLATE_EPUB_TYPES

    raw = _epub("bram-stoker_dracula.epub")
    inside = zipfile.ZipFile(io.BytesIO(raw))
    assert b"colophon" in inside.read("epub/text/colophon.xhtml")  # it IS shipped

    keys = {c.key for c in parse_epub(raw).chapters}
    for apparatus in (
        "text/titlepage.xhtml",
        "text/imprint.xhtml",
        "text/halftitlepage.xhtml",
        "text/colophon.xhtml",
        "text/uncopyright.xhtml",
        "text/dedication.xhtml",
    ):
        assert apparatus not in keys
    assert "text/preface.xhtml" in keys  # frontmatter, but real content
    assert "text/epilogue.xhtml" in keys  # backmatter, but real content


def test_short_apparatus_is_dropped_by_the_word_floor():
    book = parse_epub(_epub("bram-stoker_dracula.epub"))
    assert all(c.word_count >= MIN_CHAPTER_WORDS for c in book.chapters)


# --- untrusted-archive handling ----------------------------------------------


def test_unparseable_book_is_none_not_an_exception():
    assert parse_epub(b"not a zip at all") is None
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
    assert parse_epub(empty.getvalue()) is None  # a ZIP, but no OPF


def test_resolve_rejects_hrefs_that_escape_the_archive_root():
    """Nothing is ever written to disk, so this is defence in depth -- but a
    href must not be able to address anything outside the book."""
    assert _resolve("OEBPS", "text/chapter-1.xhtml") == "OEBPS/text/chapter-1.xhtml"
    assert _resolve("", "chapter-1.xhtml") == "chapter-1.xhtml"
    assert _resolve("OEBPS", "../images/../text/c1.xhtml") == "text/c1.xhtml"
    for hostile in ("../../../etc/passwd", "../../secret.xhtml", "/../../x"):
        assert _resolve("OEBPS", hostile) is None
    # Absolute and remote references are not book members at all.
    assert _resolve("OEBPS", "https://example.com/evil.xhtml") is None
    assert _resolve("OEBPS", "") is None


def _make_epub(spine_items: list[tuple[str, str, str]], *, base: str = "OEBPS") -> bytes:
    """Build a minimal but valid EPUB. Items are (id, href, extra itemref attrs)."""
    buffer = io.BytesIO()
    prefix = f"{base}/" if base else ""
    opf_path = f"{prefix}content.opf"
    manifest = "".join(
        f'<item id="{i}" href="{h}" media-type="application/xhtml+xml"/>'
        for i, h, _ in spine_items
    )
    spine = "".join(f'<itemref idref="{i}" {extra}/>' for i, _, extra in spine_items)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            f'<container><rootfiles><rootfile full-path="{opf_path}"/>'
            "</rootfiles></container>",
        )
        zf.writestr(
            opf_path,
            "<package><metadata><dc:title>T</dc:title></metadata>"
            f"<manifest>{manifest}</manifest><spine>{spine}</spine></package>",
        )
        for _i, href, _extra in spine_items:
            zf.writestr(
                f"{prefix}{href}",
                "<html><body><h1>H</h1><p>" + ("word " * 400) + "</p></body></html>",
            )
    return buffer.getvalue()


def test_non_linear_spine_items_are_not_chapters():
    """``linear="no"`` marks material outside the reading order -- cover
    wrappers, and pop-up footnote pages, which are long enough to clear the
    word floor and would otherwise land in the middle of the book."""
    blob = _make_epub(
        [
            ("cover", "cover.xhtml", 'linear="no"'),
            ("c1", "chapter-1.xhtml", 'linear="yes"'),
            ("notes", "endnotes.xhtml", 'linear="no"'),
        ]
    )
    book = parse_epub(blob)
    assert [c.key for c in book.chapters] == ["chapter-1.xhtml"]


def test_traversal_href_cannot_pull_in_a_member_outside_the_opf_root():
    buffer = io.BytesIO()
    story = "<html><body><p>" + ("word " * 400) + "</p></body></html>"
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="a/b/content.opf"/>'
            "</rootfiles></container>",
        )
        zf.writestr(
            "a/b/content.opf",
            "<package><metadata><dc:title>T</dc:title></metadata><manifest>"
            '<item id="x" href="../../../secret.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="b" href="ok.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="x"/><itemref idref="b"/></spine></package>',
        )
        zf.writestr("secret.xhtml", story)
        zf.writestr("a/b/ok.xhtml", story)
    book = parse_epub(buffer.getvalue())
    assert [c.key for c in book.chapters] == ["ok.xhtml"]


def test_declared_zip_bomb_member_is_refused_without_expanding_it():
    """The payload here is ordinary prose, not a run of one letter: it would
    parse into a perfectly good chapter if the size guard did not stop it,
    so the test fails if the guard goes away rather than being caught by the
    word floor on the way past."""
    from connectors.archiveorg import epub as epub_module

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>',
        )
        zf.writestr(
            "content.opf",
            "<package><manifest>"
            '<item id="a" href="bomb.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="a"/></spine></package>',
        )
        zf.writestr(
            "bomb.xhtml",
            "<html><body><p>" + ("word " * 400_000) + "</p></body></html>",
        )
    blob = buffer.getvalue()
    assert len(blob) < 100_000  # highly compressible, like a real bomb
    assert zipfile.ZipFile(io.BytesIO(blob)).getinfo("bomb.xhtml").file_size > 1_000_000

    # Without the guard this is a 400,000-word chapter.
    assert parse_epub(blob) is not None
    with patch.object(epub_module, "MAX_MEMBER_BYTES", 100_000):
        assert parse_epub(blob) is None


# --- connector plumbing -------------------------------------------------------


@pytest.fixture
def connector() -> ArchiveOrgConnector:
    return ArchiveOrgConnector()


def _wire(connector, metadata_name: str, epub_name: str | None, calls: list):
    """Patch the connector's two HTTP verbs and record every call."""

    def fake_json(path, *, params=None):
        calls.append(path)
        return _load(metadata_name)

    def fake_bytes(path):
        calls.append(path)
        if epub_name is None:
            raise ConnectorHttpError(
                f"Client error '404 Not Found' for url 'https://archive.org{path}'"
            )
        return "application/epub+zip", _epub(epub_name)

    return patch.object(connector._http, "get_json", side_effect=fake_json), patch.object(
        connector._http, "get_bytes", side_effect=fake_bytes
    )


def test_connector_declares_the_novel_contract(connector):
    assert connector.CONTENT_KIND == "novel"
    assert connector.content_kind == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.MATURE is False
    assert connector.get_chapter_pages("anything") == []
    assert connector.find_page("anything") is None
    # Covers redirect to per-item storage nodes (dn790006.ca.archive.org);
    # the suffix match covers them without allowlisting the internet.
    assert connector.allowed_image_hosts == frozenset({"archive.org"})


def test_a_whole_book_costs_exactly_two_requests(connector):
    """The cost constraint this connector exists to satisfy: metadata + one
    EPUB, then every chapter of that book is free while the parse is cached.
    Fetching an EPUB per chapter request would be unacceptable."""
    calls: list[str] = []
    json_patch, bytes_patch = _wire(connector, f"metadata_{SHERLOCK}.json", "pg1661.epub", calls)
    with json_patch, bytes_patch:
        series = connector.get_series(SHERLOCK)
        chapters = connector.get_chapters(SHERLOCK)
        for chapter in chapters:
            assert connector.chapter_text(SHERLOCK, chapter.id) is not None

    assert series is not None and series.chapter_count == 11
    assert len(chapters) == 11
    assert calls == [
        f"/metadata/{SHERLOCK}",
        f"/download/{SHERLOCK}/pg1661.epub",
    ]


def test_listings_never_fetch_a_book(connector):
    calls: list[str] = []

    def fake_json(path, *, params=None):
        calls.append(path)
        return _load("search_browse.json")

    def fake_bytes(path):  # pragma: no cover - must never run
        raise AssertionError(f"a listing must not download {path}")

    with patch.object(connector._http, "get_json", side_effect=fake_json), patch.object(
        connector._http, "get_bytes", side_effect=fake_bytes
    ):
        connector.get_series_list(1)
        connector.search_series("dracula", 1)
    assert calls == ["/advancedsearch.php", "/advancedsearch.php"]


def test_connector_serves_series_metadata_over_the_epubs_own(connector):
    """The catalogue record wins: search matched 'Dracula by Bram Stoker',
    and a detail page that renamed itself to the OPF's 'Dracula' would look
    like a different book."""
    calls: list[str] = []
    json_patch, bytes_patch = _wire(
        connector, f"metadata_{DRACULA}.json", "bram-stoker_dracula.epub", calls
    )
    with json_patch, bytes_patch:
        series = connector.get_series(DRACULA)
        text = connector.chapter_text(DRACULA, "text/chapter-1.xhtml")

    assert series.title == "Dracula by Bram Stoker"
    assert series.chapter_count == 29
    assert series.status == "completed"
    assert text is not None
    assert text.title == "I"
    assert text.chapter_number == 2.0
    assert text.word_count > 5000


def test_chapter_keys_survive_url_encoding(connector):
    """Keys are spine hrefs and contain slashes; they arrive percent-encoded
    from the client and are normalized back before lookup."""
    calls: list[str] = []
    json_patch, bytes_patch = _wire(
        connector, f"metadata_{DRACULA}.json", "bram-stoker_dracula.epub", calls
    )
    with json_patch, bytes_patch:
        assert connector.chapter_text(DRACULA, "text%2Fchapter-1.xhtml") is not None
        assert connector.chapter_text(DRACULA, "/text/chapter-1.xhtml/") is not None


def test_unknown_chapter_key_returns_none(connector):
    calls: list[str] = []
    json_patch, bytes_patch = _wire(connector, f"metadata_{SHERLOCK}.json", "pg1661.epub", calls)
    with json_patch, bytes_patch:
        assert connector.chapter_text(SHERLOCK, "text/no-such-chapter.xhtml") is None


def test_missing_item_is_none_and_downloads_nothing(connector):
    calls: list[str] = []

    def fake_json(path, *, params=None):
        calls.append(path)
        return _load("metadata_missing.json")

    def fake_bytes(path):  # pragma: no cover - must never run
        raise AssertionError("a nonexistent item must not be downloaded")

    with patch.object(connector._http, "get_json", side_effect=fake_json), patch.object(
        connector._http, "get_bytes", side_effect=fake_bytes
    ):
        assert connector.get_series("no-such-item") is None
        assert connector.get_chapters("no-such-item") == []
        assert connector.chapter_text("no-such-item", "x") is None


def test_metadata_without_a_metadata_block_is_not_an_item(connector):
    """The existence check reads ``metadata``, not ``files``. A payload that
    lists an EPUB but carries no catalogue record is not a servable item, and
    downloading its book to discover that would waste a megabyte."""

    def fake_json(path, *, params=None):
        return {"files": [{"name": "book.epub", "format": "EPUB", "size": "200000"}]}

    def fake_bytes(path):  # pragma: no cover - must never run
        raise AssertionError("an item with no catalogue record must not be downloaded")

    with patch.object(connector._http, "get_json", side_effect=fake_json), patch.object(
        connector._http, "get_bytes", side_effect=fake_bytes
    ):
        assert connector.get_series("headless-item") is None
        assert connector.get_chapters("headless-item") == []


def test_item_without_an_epub_is_none_and_downloads_nothing(connector):
    def fake_json(path, *, params=None):
        return _load(f"metadata_{WORDLISTS}.json")

    def fake_bytes(path):  # pragma: no cover - must never run
        raise AssertionError("an item with no EPUB must not be downloaded")

    with patch.object(connector._http, "get_json", side_effect=fake_json), patch.object(
        connector._http, "get_bytes", side_effect=fake_bytes
    ):
        assert connector.get_series(WORDLISTS) is None
        assert connector.get_chapters(WORDLISTS) == []


def test_download_404_without_a_status_code_is_still_recognised(connector):
    """The shared client only attaches ``status_code`` for RETRYABLE_STATUS,
    and ``get_bytes`` re-raises with no status at all -- so a real 404 has
    ``status_code is None`` and only httpx's message to go on. A bare
    ``exc.status_code == 404`` check would be dead code here."""
    calls: list[str] = []
    json_patch, bytes_patch = _wire(connector, f"metadata_{SHERLOCK}.json", None, calls)
    with json_patch, bytes_patch:
        assert connector.get_series(SHERLOCK) is None
        assert connector.chapter_text(SHERLOCK, "anything") is None


def test_network_failure_raises_so_the_service_can_serve_stale(connector):
    def fake_json(path, *, params=None):
        raise ConnectorHttpError("Retryable HTTP 503", status_code=503)

    with patch.object(connector._http, "get_json", side_effect=fake_json):
        with pytest.raises(ConnectorHttpError):
            connector.chapter_text(SHERLOCK, "anything")
        with pytest.raises(ConnectorHttpError):
            connector.get_series(SHERLOCK)


def test_download_failure_raises_rather_than_reporting_no_such_book(connector):
    def fake_json(path, *, params=None):
        return _load(f"metadata_{SHERLOCK}.json")

    def fake_bytes(path):
        raise ConnectorHttpError("Retryable HTTP 502", status_code=502)

    with patch.object(connector._http, "get_json", side_effect=fake_json), patch.object(
        connector._http, "get_bytes", side_effect=fake_bytes
    ):
        with pytest.raises(ConnectorHttpError):
            connector.get_series(SHERLOCK)


def test_non_english_chapter_is_refused(connector):
    """archive.org is multilingual; the search scope filters upstream, but a
    mis-tagged book must still not be cached as English text."""
    calls: list[str] = []
    json_patch, bytes_patch = _wire(connector, f"metadata_{SHERLOCK}.json", "pg1661.epub", calls)
    with json_patch, bytes_patch:
        book = connector._load_book(SHERLOCK)
        key = book.chapters[0].id
        assert connector.chapter_text(SHERLOCK, key) is not None
        # Swap the cached chapter's text for Chinese and re-read.
        from connectors.archiveorg.epub import EpubChapter

        book.texts[key] = EpubChapter(
            key=key,
            title=book.texts[key].title,
            number=1.0,
            paragraphs=("重生之最强剑神是一部网络小说。" * 20,),
        )
        assert connector.chapter_text(SHERLOCK, key) is None


def test_beyond_the_deep_paging_wall_no_request_is_made(connector):
    def fake_json(path, *, params=None):  # pragma: no cover - must never run
        raise AssertionError("a page the API refuses must not be requested")

    with patch.object(connector._http, "get_json", side_effect=fake_json):
        listing = connector.get_series_list(MAX_PAGE + 1)
    assert listing.items == []
    assert listing.has_more is False


def test_book_cache_evicts_least_recently_used():
    """The shared TTLCache has no size ceiling; parsed books are ~1 MB of
    paragraph text each, so this connector puts an LRU bound on top of it --
    otherwise a crawler walking the catalogue walks into the VPS's RAM."""
    cache = _BookCache(ttl_seconds=600.0, max_entries=2)
    books = {name: object() for name in ("a", "b", "c")}
    cache.set("a", books["a"])
    cache.set("b", books["b"])
    assert cache.get("a") is books["a"]  # "a" is now the most recent use
    cache.set("c", books["c"])
    assert cache.get("b") is None  # least recently USED, not oldest inserted
    assert cache.get("a") is books["a"]
    assert cache.get("c") is books["c"]


def test_book_cache_bound_stays_small_enough_to_matter():
    """A regression guard on the number itself: at ~1 MB per parsed book,
    this ceiling is the connector's memory budget."""
    assert 1 <= MAX_CACHED_BOOKS <= 16


def test_evicted_book_is_refetched_rather_than_served_stale(connector):
    calls: list[str] = []
    json_patch, bytes_patch = _wire(connector, f"metadata_{SHERLOCK}.json", "pg1661.epub", calls)
    connector._books = _BookCache(ttl_seconds=600.0, max_entries=2)
    with json_patch, bytes_patch:
        connector._load_book("book-0")
        connector._load_book("book-1")
        connector._load_book("book-2")  # evicts book-0
        before = len(calls)
        connector._load_book("book-2")
        assert len(calls) == before  # still cached: no requests
        connector._load_book("book-0")
        assert len(calls) == before + 2  # evicted: metadata + EPUB again


def test_registered_and_gated_by_the_novels_flag(monkeypatch):
    """Novel sources must be invisible while MM_NOVELS_ENABLED is off --
    production stays a manhwa site (spec §2). Skipped until the serial
    integrator wires this connector into the registry."""
    import connectors.registry as registry
    from core.config import get_settings

    if "archiveorg" not in registry._REGISTRY:
        pytest.skip("archiveorg not yet wired into the registry by the integrator")

    monkeypatch.delenv("MM_NOVELS_ENABLED", raising=False)
    get_settings.cache_clear()
    assert "archiveorg" not in registry.list_connector_types()
    with pytest.raises(ValueError):
        registry.create_connector("archiveorg")

    monkeypatch.setenv("MM_NOVELS_ENABLED", "true")
    get_settings.cache_clear()
    descriptors = {d.source_type: d for d in registry.list_installed_connectors()}
    assert descriptors["archiveorg"].content_kind == "novel"
    assert descriptors["archiveorg"].language == "en"
    assert isinstance(registry.create_connector("archiveorg"), ArchiveOrgConnector)
    get_settings.cache_clear()
