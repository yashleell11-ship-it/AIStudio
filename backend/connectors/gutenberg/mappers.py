"""Map Project Gutenberg's own published feeds and EPUBs to connector models.

Project Gutenberg is ~79,000 books, ~61,600 of them English prose. Everything
this connector reads comes from **www.gutenberg.org itself** — the machine-
readable catalogue feed, the top-downloads board, the bibliographic record on
a book's page, and the generated EPUB. There is no third-party service in the
path any more; see ``connector`` for why the gutendex mirror was removed.

Measured FROM THE VPS (production egress/TLS, 2026-09-05), cold:

=========================================  ==========  ==========
path                                       time        bytes
=========================================  ==========  ==========
``/cache/epub/feeds/pg_catalog.csv.gz``     0.25 s      5.6 MB
``/browse/scores/top1000.php``              0.15 s      517 KB
``/ebooks/84``                              0.11 s      25 KB
``/ebooks/1342.epub.noimages``              0.19 s      558 KB
=========================================  ==========  ==========

robots.txt, checked for every path used here, is two lines:
``User-agent: *`` / ``Disallow: /ebooks/search``. That one disallowed path is
the site's HTML search — which is exactly why this connector carries its own
catalogue index instead: searching Gutenberg politely means not asking
``/ebooks/search`` at all.

**The catalogue feed.** ``pg_catalog.csv`` is the whole bibliography as one
CSV: ``Text#, Type, Issued, Title, Language, Authors, Subjects, LoCC,
Bookshelves``. Filtered to ``Type=Text`` and ``Language=en`` it is 61,606
rows, and it is the single index behind browse, search and genre — so a
listing page costs ZERO upstream requests once the feed is in hand.

**Which EPUB, and why it matters.** The site advertises
``.epub3.images`` for a book; this connector requests
``/ebooks/<id>.epub.noimages`` instead, which is strictly better on both axes
that matter here (measured from the VPS against the same books):

===================  ====================  ===================
book                 ``.epub3.images``     ``.epub.noimages``
===================  ====================  ===================
Pride and Prejudice  24.8 MB / 6 spine     558 KB / 15 spine
Moby-Dick            812 KB / 10 spine     727 KB / 27 spine
Huckleberry Finn     16.0 MB / 46 spine    346 KB / 46 spine
===================  ====================  ===================

— up to ~45x less to download on a bandwidth-budgeted VPS, and a *finer*
chapter split, because the EPUB 2 build breaks the book into more spine
documents than the EPUB 3 one does.

**Honesty about chapter boundaries.** Chapters here are the book's own spine
documents — a real, authored file structure, never a heuristic split of
running text. For most Gutenberg conversions that is exactly one document per
chapter (Frankenstein 29, Alice 13, Dracula 30, Sherlock 13, Huckleberry Finn
46). For some older conversions the generator grouped several chapters into
one document, so the reader sees fewer, longer chapters whose titles name the
first chapter in each group (Moby-Dick's 135 chapters arrive as 27 documents).
That is coarse, but it is the boundary the book itself declares; no chapter
boundary is ever invented, and no text is lost or reordered.

Identity (house law: opaque, stored raw, never parsed by callers):

* ``series_key``  = the Gutenberg ebook id, e.g. ``"84"``.
* ``chapter_key`` = the EPUB manifest href of that spine document relative to
  the OPF, e.g. ``"8410.htm"`` — it lives inside the book file, so re-parsing
  the same EPUB always yields the same key (identical to how ``archiveorg``
  keys its chapters).
"""

from __future__ import annotations

import csv
import gzip
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from html import unescape

from connectors.archiveorg.epub import EpubChapter
from connectors.ids import fully_unquote
from connectors.models import Chapter, PaginatedSeriesList, Series
from connectors.novel_text import slice_element

SITE_BASE = "https://www.gutenberg.org"

#: The whole bibliography as one gzipped CSV, regenerated daily by Gutenberg.
CATALOG_PATH = "/cache/epub/feeds/pg_catalog.csv.gz"

#: The download leaderboard. Its ``books-last30`` section is 1,000 ebook ids
#: in descending 30-day download order — the only popularity signal Gutenberg
#: publishes outside the disallowed search endpoint.
POPULAR_PATH = "/browse/scores/top1000.php"

#: Listing page size. Chosen, not imposed: pagination is ours now that pages
#: are sliced out of a local index.
PAGE_SIZE = 32

#: Catalogue rows this connector can serve. Everything else in the feed is
#: audio, images, or another language.
CATALOG_MEDIA_TYPE = "Text"
CATALOG_LANGUAGE = "en"

#: Subjects/bookshelves kept per book, so a listing row stays small.
MAX_GENRES = 8

#: Refuse a catalogue feed bigger than this. The real one is 5.6 MB gzipped /
#: 21 MB expanded; the ceilings exist so a corrupt or hostile response cannot
#: expand into the VPS's memory (the same reasoning as the EPUB zip-bomb
#: refusal in ``archiveorg.epub``).
MAX_CATALOG_GZIP_BYTES = 32_000_000
MAX_CATALOG_TEXT_BYTES = 128_000_000

#: Browse-mode ids -> how the local index is ordered. Unlike a query
#: parameter, an unknown value here cannot be "silently ignored upstream", so
#: this dict is both the allowlist and the whole ordering vocabulary.
BROWSE_SORTS: dict[str, str] = {
    "": "popular",
    "default": "popular",
    "popular": "popular",
    "newest": "newest",
    "oldest": "oldest",
}


def download_path(book_id: str) -> str:
    """The EPUB path for a book id. See the module docstring for the variant."""
    return f"/ebooks/{book_id}.epub.noimages"


def detail_path(book_id: str) -> str:
    """The book's page, which carries its bibliographic record."""
    return f"/ebooks/{book_id}"


def cover_url(book_id: str) -> str:
    """Gutenberg's generated cover for a book.

    Derived, never looked up: the path is a pure function of the id, so a
    listing of 32 rows costs 32 cover URLs and zero requests. Sampled from the
    VPS 2026-09-05, 30/30 random English texts and 20/20 of the most-
    downloaded ones answered 200 here.
    """
    return f"{SITE_BASE}/cache/epub/{book_id}/pg{book_id}.cover.medium.jpg"


def normalize_series_key(value: str) -> str:
    """``84``, ``ebooks/84``, or a gutenberg.org URL -> ``"84"``.

    Returns ``""`` for anything that is not a plain ebook id, which the
    connector treats as a missing series rather than sending it upstream.
    """
    cleaned = fully_unquote(value).strip().strip("/")
    if not cleaned:
        return ""
    if cleaned.startswith("http"):
        cleaned = re.sub(r"^https?://[^/]+/", "", cleaned).strip("/")
    if cleaned.startswith("ebooks/"):
        cleaned = cleaned[len("ebooks/") :]
    if cleaned.startswith("books/"):
        cleaned = cleaned[len("books/") :]
    # Trim a trailing format suffix ("84.epub.noimages") or slug tail.
    cleaned = cleaned.split("/", 1)[0]
    match = re.match(r"^(\d+)", cleaned)
    return match.group(1) if match else ""


def normalize_chapter_key(value: str) -> str:
    """Chapter keys are EPUB manifest hrefs; only the fragment is stripped."""
    return fully_unquote(value).strip().split("#", 1)[0].strip("/")


# --- the catalogue index ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One servable book, as the catalogue feed describes it.

    Deliberately four fields. At 61,606 rows every attribute is paid 61,606
    times, and the fifth field nobody reads is a megabyte of the VPS's RAM.
    """

    book_id: str
    title: str
    author: str | None
    genres: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Catalog:
    """The parsed feed, held once and paged from without touching the network.

    ``oldest`` is the feed's own order (ascending ebook number, which is also
    the order Gutenberg published them in) and ``newest`` is its reverse. Both
    are tuples of the SAME entry objects, so the second ordering costs a
    pointer each, not a copy.
    """

    oldest: tuple[CatalogEntry, ...] = ()
    newest: tuple[CatalogEntry, ...] = ()
    by_id: dict[str, CatalogEntry] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.oldest)

    def get(self, book_id: str) -> CatalogEntry | None:
        return self.by_id.get(book_id)


def decompress_catalog(blob: bytes) -> str | None:
    """The gzipped feed -> its CSV text, or None when it is not plausible.

    Reads one byte past the ceiling rather than the whole stream, so a feed
    that expands without bound is refused instead of being materialized first.
    """
    if not blob or len(blob) > MAX_CATALOG_GZIP_BYTES:
        return None
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
            raw = stream.read(MAX_CATALOG_TEXT_BYTES + 1)
    except (OSError, EOFError):
        return None
    if not raw or len(raw) > MAX_CATALOG_TEXT_BYTES:
        return None
    # utf-8-sig: the feed is served with a BOM.
    return raw.decode("utf-8-sig", "replace")


_CATALOG_COLUMNS = (
    "Text#",
    "Type",
    "Title",
    "Language",
    "Authors",
    "Subjects",
    "Bookshelves",
)


def parse_catalog(text: str) -> Catalog:
    """``pg_catalog.csv`` -> the index every listing is sliced out of.

    Columns are located by NAME, never by position: the feed has gained
    columns before, and a connector that counted commas would start serving
    subjects as titles the day it gains another.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return Catalog()
    columns = {name.strip(): position for position, name in enumerate(header)}
    if any(name not in columns for name in _CATALOG_COLUMNS):
        return Catalog()

    id_at = columns["Text#"]
    type_at = columns["Type"]
    title_at = columns["Title"]
    language_at = columns["Language"]
    authors_at = columns["Authors"]
    subjects_at = columns["Subjects"]
    shelves_at = columns["Bookshelves"]
    width = max(columns[name] for name in _CATALOG_COLUMNS)

    # Genre labels come from a vocabulary of a few thousand, repeated across
    # 61,606 rows. Pooling them makes the tuples share one string each
    # instead of holding 370,000 near-duplicates.
    pool: dict[str, str] = {}
    entries: list[CatalogEntry] = []
    by_id: dict[str, CatalogEntry] = {}
    for row in reader:
        if len(row) <= width:
            continue
        if row[type_at] != CATALOG_MEDIA_TYPE or row[language_at] != CATALOG_LANGUAGE:
            continue
        book_id = row[id_at].strip()
        if not book_id.isdigit():
            continue
        title = _collapse(row[title_at])
        if not title:
            continue
        entry = CatalogEntry(
            book_id=book_id,
            title=title,
            author=_author_name(row[authors_at]) or None,
            genres=_catalog_genres(row[shelves_at], row[subjects_at], pool),
        )
        entries.append(entry)
        by_id[book_id] = entry
    ordered = tuple(entries)
    return Catalog(oldest=ordered, newest=ordered[::-1], by_id=by_id)


_POPULAR_ID = re.compile(r'<li><a href="/ebooks/(\d+)"')

#: Anchored on the heading's stable ``id``, not its wording, and stopped at
#: the end of its own list so the next board cannot bleed in.
_POPULAR_SECTION = re.compile(
    r'id="books-last30".*?<ol>(.*?)</ol>', re.DOTALL | re.IGNORECASE
)


def parse_popular_ids(html: str) -> tuple[str, ...]:
    """The leaderboard -> ebook ids in descending 30-day download order.

    Only the ``books-last30`` section is read. The page also carries
    yesterday's and last week's boards, which are noisier, and three author
    boards, whose links are ``/ebooks/author/...`` and would otherwise be
    mistaken for books.
    """
    section = _POPULAR_SECTION.search(html)
    if section is None:
        return ()
    return tuple(dict.fromkeys(_POPULAR_ID.findall(section.group(1))))


# --- listings ---------------------------------------------------------------


def series_from_entry(entry: CatalogEntry) -> Series:
    """One catalogue row -> a listing card.

    ``chapter_count`` stays 0 ON PURPOSE: the real count needs the book
    itself, and a listing must never cost one download per row. The detail
    view fills it in.
    """
    return Series(
        id=entry.book_id,
        title=entry.title,
        chapter_count=0,
        cover_url=cover_url(entry.book_id),
        author=entry.author,
        # Every book here is a finished, published work.
        status="completed",
        genres=entry.genres,
    )


def paginate(entries: Sequence[CatalogEntry], page: int) -> PaginatedSeriesList:
    """Slice one page out of an ordering of the index."""
    page = max(1, page)
    start = (page - 1) * PAGE_SIZE
    window = entries[start : start + PAGE_SIZE]
    return PaginatedSeriesList(
        items=[series_from_entry(entry) for entry in window],
        page=page,
        page_size=PAGE_SIZE,
        total=len(entries),
    )


def popular_entries(catalog: Catalog, ids: Sequence[str]) -> list[CatalogEntry]:
    """The leaderboard's order, restricted to books this connector can serve.

    The board is language-agnostic and includes non-text items, so roughly
    150 of its 1,000 rows have no entry here; dropping them beats listing a
    book that 404s when a reader taps it.
    """
    seen: set[str] = set()
    ordered: list[CatalogEntry] = []
    for book_id in ids:
        if book_id in seen:
            continue
        seen.add(book_id)
        entry = catalog.get(book_id)
        if entry is not None:
            ordered.append(entry)
    return ordered


def search_entries(catalog: Catalog, query: str) -> list[CatalogEntry]:
    """Substring search over the local index, best matches first.

    Ranked rather than merely filtered, because the index is ordered by ebook
    number: unranked, "sherlock" would answer with whichever Holmes volume
    Gutenberg happened to digitize first. Title beats author, and a title that
    IS the query beats one that merely contains it.
    """
    needle = _collapse(query).lower()
    if not needle:
        return []
    ranked: list[tuple[int, int, CatalogEntry]] = []
    for position, entry in enumerate(catalog.oldest):
        title = entry.title.lower()
        if needle in title:
            if title == needle:
                score = 0
            elif title.startswith(needle):
                score = 1
            else:
                score = 2
        elif entry.author and needle in entry.author.lower():
            score = 3
        else:
            continue
        ranked.append((score, position, entry))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [entry for _score, _position, entry in ranked]


def genre_entries(catalog: Catalog, genre: str) -> list[CatalogEntry]:
    """Books carrying a genre label, matched against what the reader saw.

    Equality, not substring: the labels are Gutenberg's own bookshelf names,
    and a substring match on "History - Other" would also pull in "History -
    Ancient". The labels compared here are exactly the ones the listing card
    displays, so filtering by one can never hide a book that shows it.
    """
    needle = _collapse(genre).lower()
    if not needle:
        return []
    return [
        entry
        for entry in catalog.oldest
        if any(label.lower() == needle for label in entry.genres)
    ]


# --- a book's own page ------------------------------------------------------

_BIBREC_ROW = re.compile(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_LABEL_BLOCK = re.compile(r"<label\b.*?</label>", re.DOTALL | re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")

#: The one rights wording Gutenberg uses for a text anyone may redistribute
#: ("Public domain in the USA."). Its catalogue also holds books that are
#: still in copyright and carried by permission; those keep an author's
#: licence this connector has no right to strip, and the EPUB reader strips
#: exactly that kind of banner, so they are refused before download.
PUBLIC_DOMAIN_PREFIX = "public domain"


def _collapse(value: str) -> str:
    return _WHITESPACE.sub(" ", value or "").strip()


def _text(fragment: str) -> str:
    """Visible text of an HTML fragment."""
    return _collapse(unescape(_TAG.sub(" ", _COMMENT.sub(" ", fragment))))


def parse_book_page(html: str, book_id: str) -> Series | None:
    """``/ebooks/<id>`` -> ``Series``, or None when it must not be served.

    The page's ``bibrec`` table is the authority for the three facts a
    catalogue row cannot carry: what the item IS (text, not audio), what
    language it is in, and its copyright status. Anything the table does not
    vouch for is refused rather than guessed — a missing rights row means
    "unknown", which is not good enough to redistribute.
    """
    table = slice_element(html, r'<table[^>]*\bclass="bibrec"[^>]*>')
    if table is None:
        return None
    rows: dict[str, list[str]] = {}
    for raw_label, raw_value in _BIBREC_ROW.findall(table):
        label = _text(raw_label).rstrip(":").lower()
        value = _text(raw_value)
        if label and value:
            rows.setdefault(label, []).append(value)

    category = rows.get("category", ())
    if not any(value.lower() == CATALOG_MEDIA_TYPE.lower() for value in category):
        return None
    language = rows.get("language", ())
    if not any(value.lower().startswith("english") for value in language):
        return None
    rights = rows.get("copyright", ())
    if not any(value.lower().startswith(PUBLIC_DOMAIN_PREFIX) for value in rights):
        return None

    title = _collapse(next(iter(rows.get("title", ())), ""))
    if not title:
        return None
    authors = rows.get("author", ()) or rows.get("editor", ())
    genres: list[str] = []
    for key in ("bookshelf", "bookshelves", "subject"):
        for value in rows.get(key, ()):
            label = value.split(" -- ")[0].strip()
            if label:
                genres.append(label)

    return Series(
        id=book_id,
        title=title,
        chapter_count=0,
        description=parse_summary(html),
        cover_url=cover_url(book_id),
        author=_author_name(next(iter(authors), "")) or None,
        status="completed",
        genres=tuple(dict.fromkeys(genres))[:MAX_GENRES],
    )


def parse_summary(html: str) -> str | None:
    """The book page's blurb, including the half hidden behind "Read more".

    The container holds the whole summary; the site merely folds its tail into
    a ``<span>`` a checkbox reveals. Only the toggle's own ``<label>`` is
    dropped, so the reader gets the complete text rather than the truncated
    teaser plus the words "Read more".
    """
    block = slice_element(html, r'<div[^>]*\bclass="summary-text-container"[^>]*>')
    if block is None:
        return None
    return _text(_LABEL_BLOCK.sub(" ", block)) or None


# --- names and labels -------------------------------------------------------

#: A trailing life-dates fragment in a Gutenberg author string: "1797-1851",
#: "1860-", "1858?-1920", "384 BCE-322 BCE", "active 8th century".
_LIFE_DATES = re.compile(
    r"^(?:active\b.*"
    r"|(?:b\.|d\.|fl\.|ca?\.)?\s*\d{1,4}\??\s*(?:BCE|BC|CE|AD)?"
    r"\s*[-–]\s*"
    r"(?:ca?\.)?\s*(?:\d{1,4}\??)?\s*(?:BCE|BC|CE|AD)?)$",
    re.IGNORECASE,
)
_ROLE_SUFFIX = re.compile(r"\s*\[[^\]]*\]\s*$")


def _author_name(raw: str) -> str:
    """``"Austen, Jane, 1775-1817"`` -> ``"Jane Austen"``.

    The catalogue credits everyone who touched a book, surname-first and with
    life dates, e.g. ``"Baum, L. Frank (Lyman Frank), 1856-1919; Norris,
    William [Contributor]"``. Only the first credit is kept — a card has room
    for one name — its role tag and dates are dropped, and the comma is
    flipped only when exactly one remains. A name still carrying a second
    comma after that ("Ward, Humphry, Mrs.") is left exactly as it is rather
    than scrambled into "Humphry Ward, Mrs.".
    """
    name = _collapse(raw)
    if not name:
        return ""
    name = _ROLE_SUFFIX.sub("", name.split(";")[0]).strip()
    parts = [part.strip() for part in name.split(",")]
    while len(parts) > 1 and _LIFE_DATES.match(parts[-1]):
        parts.pop()
    parts = [part for part in parts if part]
    if len(parts) == 2:
        return f"{parts[1]} {parts[0]}"
    return ", ".join(parts)


def _catalog_genres(
    bookshelves: str, subjects: str, pool: dict[str, str]
) -> tuple[str, ...]:
    """Readable topic labels from Gutenberg's bookshelves and subjects.

    Bookshelves are curator-style ("Category: British Literature") and
    subjects are Library-of-Congress style ("Courtship -- Fiction"); both are
    reduced to their leading human-readable segment and de-duplicated.
    Bookshelves come FIRST because they are the vocabulary genre browse
    advertises, and no book carries more than ten of them — so the cap below
    trims subjects, never a shelf a reader could have filtered on.
    """
    labels: list[str] = []
    for value in _split_labels(bookshelves) + _split_labels(subjects):
        label = value.split(" -- ")[0].strip()
        if label.startswith(("Category:", "Browsing:")):
            label = label.split(":", 1)[1].strip()
        if label:
            labels.append(pool.setdefault(label, label))
    return tuple(dict.fromkeys(labels))[:MAX_GENRES]


def _split_labels(field_value: str) -> list[str]:
    return [part for part in (field_value or "").split(";") if part.strip()]


def chapters_from_epub(
    series_key: str, chapters: tuple[EpubChapter, ...] | list[EpubChapter]
) -> list[Chapter]:
    """Parsed EPUB spine documents -> the chapter list the reader expects."""
    return [
        Chapter(
            id=chapter.key,
            series_id=series_key,
            title=chapter.title,
            number=chapter.number,
            page_count=0,
        )
        for chapter in chapters
    ]
