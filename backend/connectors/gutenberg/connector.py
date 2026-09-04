"""Project Gutenberg novel source connector (spec 2026-09-04-novels-design §4).

Like ``archiveorg``, and unlike every per-chapter-URL source in this repo,
Gutenberg serves whole books — so this connector is an **EPUB importer
wearing the connector interface**: the catalogue is Gutenberg's own published
feed, and a book is fetched exactly once and split along its own OPF spine.

It deliberately reuses ``connectors.archiveorg.epub.parse_epub`` rather than
growing a second EPUB reader. That module is the house's hardened container
parser — zip-bomb refusal from the ZIP directory, href-traversal rejection,
spine/char budgets, Project Gutenberg licence-banner trimming — and a book
here is the *same kind of file* archive.org serves (many archive.org items
literally are Gutenberg EPUBs). Duplicating 450 lines of security-relevant
parsing to avoid one import would be strictly worse.

**Why the gutendex mirror is gone.** This connector used to read its
catalogue from gutendex.com, a community JSON mirror of Gutenberg's metadata.
Measured from the VPS on guaranteed-cold queries (2026-09-05), gutendex
answers in **66-141 seconds** — for browse, for search, with and without
filters, on every query shape tried. With one retry behind it, a browse page
cost 194 s and 147 round trips, and detail and chapters never ran at all
before the probe's budget expired. Gutenberg's own site, over the same TLS
stack from the same box, answers every path below in **under 0.3 s**. The
mirror was the entire cost; removing it removes it.

Request budget — the point of the design:

* **browse / search / genre: 0 requests** once the catalogue is in hand. The
  first listing after a cold start (or after the 6-hour TTL) pays 1 request
  for the 5.6 MB catalogue feed, plus 1 more for the download leaderboard on
  the popularity ordering. Measured by the e2e probe from the VPS: 2.7 s cold
  over 2 round trips, ~0 s warm, against 194 s over 147 before.
* first touch of a book (whichever of ``get_series`` / ``get_chapters`` /
  ``chapter_text`` arrives first): **2 requests** — the bibliographic record,
  which is what vouches that the book is an English public-domain *text*, and
  the EPUB itself, whose URL is derived from the id. The probe reports three
  round trips for it: ``/ebooks/<id>.epub.noimages`` 302s to the generated
  file under ``/cache/epub/``, and a redirect hop is a round trip.
* every subsequent chapter of that book while the parse is cached: **0
  requests**. Reading a 46-chapter novel end to end costs 2 HTTP requests,
  and ``novel_chapter_cache`` then keeps each chapter server-side for every
  other reader too.

Neither the catalogue nor a book is ever written to disk: both are read into
memory, parsed, and the compressed bytes dropped — only the extracted rows
and paragraphs are retained, under the bounded caches below. That keeps the
connector inside the VPS's ~20 GB budget by construction rather than by
cleanup. The catalogue's own resident cost was measured in the production
container at ~25 MB for 61,606 books; see ``CATALOG_TTL_SECONDS``.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass

from connectors.archiveorg.epub import EpubChapter, parse_epub
from connectors.base import SourceConnector
from connectors.gutenberg.mappers import (
    BROWSE_SORTS,
    CATALOG_PATH,
    POPULAR_PATH,
    SITE_BASE,
    Catalog,
    CatalogEntry,
    chapters_from_epub,
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
from connectors.http.cache import TTLCache
from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.models import (
    BrowseMode,
    Chapter,
    NovelChapterText,
    Page,
    PaginatedSeriesList,
    Series,
)
from connectors.novel_text import looks_english

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

#: Every path this connector touches lives on one host and answered in under
#: 0.3 s from the VPS, so the client needs no special latency allowance — the
#: headroom here is for the EPUB, which gutenberg.org sometimes generates on
#: demand.
HTTP_TIMEOUT_SECONDS = 60.0

#: Refuse to parse a book larger than this. The ``.epub.noimages`` build is a
#: few hundred KB for a normal novel (Alice 137 KB, Pride and Prejudice
#: 558 KB, Moby-Dick 727 KB), so this only ever fires on an anomaly — the
#: illustrated builds this connector does NOT request are the 16-25 MB ones.
MAX_EPUB_BYTES = 5_000_000

#: How long the catalogue index is held. Gutenberg regenerates the feed once
#: a day, so a shorter TTL would re-download the same bytes; a longer one
#: would hold ~25 MB of the VPS's 3.8 GB indefinitely for a source nobody is
#: reading. Six hours refreshes twice a day and lets an idle source let go.
CATALOG_TTL_SECONDS = 21_600.0
CATALOG_KEY = "catalog"

#: The download leaderboard moves daily and is cheap; it is cached only so a
#: page-2 browse does not re-fetch it.
POPULAR_TTL_SECONDS = 3600.0
POPULAR_KEY = "popular"

#: Parsed books held in memory. Bounded on purpose: a parse is roughly a
#: megabyte of paragraph text and the shared ``TTLCache`` has no size ceiling
#: of its own, so an unbounded one would let a crawler walk 61,000 titles
#: straight into the VPS's RAM.
MAX_CACHED_BOOKS = 4
BOOK_CACHE_TTL_SECONDS = 900.0

#: Genre browse. These are Gutenberg's OWN bookshelf labels, matched exactly
#: against what a listing card displays, with the row count each carried in
#: the feed on 2026-09-05 — an advertised genre that matches nothing is a
#: dead end, so every one of these is verified populated.
GENRE_SHELVES: tuple[tuple[str, str], ...] = (
    ("Novels", "Novels"),  # 18,500
    ("Adventure", "Adventure"),  # 7,440
    ("Children & Young Adult Reading", "Children & Young Adult"),  # 6,346
    ("Humour", "Humour"),  # 4,028
    ("Science-Fiction & Fantasy", "Science Fiction & Fantasy"),  # 3,952
    ("Historical Novels", "Historical Novels"),  # 3,908
    ("Poetry", "Poetry"),  # 3,687
    ("Short Stories", "Short Stories"),  # 3,647
    ("Travel Writing", "Travel Writing"),  # 3,046
    ("Mythology, Legends & Folklore", "Myths & Folklore"),  # 2,449
    ("Romance", "Romance"),  # 2,253
    ("Crime, Thrillers and Mystery", "Crime & Mystery"),  # 1,987
)


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses, and ``get_bytes`` re-raises with no status at all, so a 404
    arrives as ``status_code=None`` carrying httpx's ``raise_for_status``
    text ("Client error '404 Not Found' for url ..."). A bare
    ``exc.status_code == 404`` check is dead code against this client —
    match both forms, as royalroad/freewebnovel/archiveorg do.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


@dataclass(frozen=True, slots=True)
class _ParsedBook:
    """One fetched-and-parsed book: everything the three reads need."""

    series: Series
    chapters: list[Chapter]
    texts: dict[str, EpubChapter]


class _BookCache:
    """TTL cache with an LRU ceiling on how many books it may hold.

    Wraps the shared ``TTLCache`` (which owns expiry) and keeps its own key
    order so the least-recently-used book can be evicted once ``max_entries``
    is reached. Connectors are shared singletons across request threads, so
    the ordering is lock-guarded.
    """

    def __init__(self, *, ttl_seconds: float, max_entries: int) -> None:
        self._cache: TTLCache[_ParsedBook] = TTLCache(ttl_seconds=ttl_seconds)
        self._order: OrderedDict[str, None] = OrderedDict()
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def get(self, key: str) -> _ParsedBook | None:
        value = self._cache.get(key)
        with self._lock:
            if value is None:
                self._order.pop(key, None)
            else:
                self._order.move_to_end(key)
        return value

    def set(self, key: str, value: _ParsedBook) -> None:
        self._cache.set(key, value)
        with self._lock:
            self._order[key] = None
            self._order.move_to_end(key)
            while len(self._order) > self._max_entries:
                evicted, _ = self._order.popitem(last=False)
                self._cache.pop(evicted)

    def clear(self) -> None:
        self._cache.clear()
        with self._lock:
            self._order.clear()


class GutenbergConnector(SourceConnector):
    """Read public-domain books from Project Gutenberg as novels."""

    SOURCE_TYPE = "gutenberg"
    DISPLAY_NAME = "Project Gutenberg"
    DESCRIPTION = (
        "Read the Project Gutenberg library — tens of thousands of "
        "public-domain books, searchable by title, author and topic. Each "
        "book's EPUB is split along its own chapter structure and served as "
        "clean plain-text paragraphs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False
    CONTENT_KIND = "novel"
    LANGUAGE = "en"

    def __init__(self) -> None:
        # One host, one client: catalogue, leaderboard, book pages and EPUBs
        # are all gutenberg.org, and an EPUB's 302 lands inside it.
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            timeout=HTTP_TIMEOUT_SECONDS,
            user_agent=BROWSER_USER_AGENT,
            headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        )
        self._catalog: TTLCache[Catalog] = TTLCache(ttl_seconds=CATALOG_TTL_SECONDS)
        self._popular: TTLCache[tuple[str, ...]] = TTLCache(
            ttl_seconds=POPULAR_TTL_SECONDS
        )
        # Building the index costs a download and ~1 s of parsing. Without
        # this, a cold source hit by several readers at once would do that
        # work — and hold that memory — once per thread.
        self._index_lock = threading.Lock()
        # One fetch+parse per book feeds get_series, get_chapters AND every
        # chapter_text for that book (see the module docstring's budget).
        self._books = _BookCache(
            ttl_seconds=BOOK_CACHE_TTL_SECONDS, max_entries=MAX_CACHED_BOOKS
        )

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    @property
    def allowed_image_hosts(self) -> frozenset[str]:
        # Covers are /cache/epub/<id>/pg<id>.cover.medium.jpg on the site itself.
        return frozenset({"gutenberg.org"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Most Downloaded"),
            BrowseMode(id="newest", label="Recently Added"),
            BrowseMode(id="oldest", label="Earliest Catalogued"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=shelf, label=label) for shelf, label in GENRE_SHELVES]

    # --- the local index --------------------------------------------------

    def _catalogue(self) -> Catalog:
        """Gutenberg's catalogue feed, parsed once and paged from thereafter."""
        cached = self._catalog.get(CATALOG_KEY)
        if cached is not None:
            return cached
        with self._index_lock:
            # A thread that queued on the lock while another built the index
            # must use that one rather than downloading 5.6 MB again.
            cached = self._catalog.get(CATALOG_KEY)
            if cached is not None:
                return cached
            _content_type, blob = self._http.get_bytes(CATALOG_PATH)
            text = decompress_catalog(blob)
            del blob
            if text is None:
                raise ConnectorHttpError("Gutenberg catalogue feed was unreadable")
            catalog = parse_catalog(text)
            # The 21 MB of CSV goes out of scope here; only the index is kept.
            del text
            if not len(catalog):
                raise ConnectorHttpError("Gutenberg catalogue feed held no books")
            self._catalog.set(CATALOG_KEY, catalog)
            logger.info("Gutenberg catalogue loaded: books=%d", len(catalog))
            return catalog

    def _popular_ids(self) -> tuple[str, ...]:
        cached = self._popular.get(POPULAR_KEY)
        if cached is not None:
            return cached
        html = self._http.get_text(POPULAR_PATH)
        ids = parse_popular_ids(html)
        if ids:
            self._popular.set(POPULAR_KEY, ids)
        return ids

    def _ordering(self, sort: str | None) -> list[CatalogEntry]:
        catalog = self._catalogue()
        mode = BROWSE_SORTS.get((sort or "").strip().lower(), "popular")
        if mode == "newest":
            return list(catalog.newest)
        if mode == "oldest":
            return list(catalog.oldest)
        ordered = popular_entries(catalog, self._popular_ids())
        # The leaderboard is the only popularity signal Gutenberg publishes;
        # if it ever stops parsing, fall back to the newest books rather than
        # handing the reader an empty shelf.
        return ordered or list(catalog.newest)

    # --- listings (0 requests once the index is warm) ----------------------

    def get_series_list(
        self, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        listing = paginate(self._ordering(sort), page)
        logger.info(
            "Gutenberg browse page=%d sort=%s count=%d total=%d",
            listing.page,
            sort or "default",
            len(listing.items),
            listing.total,
        )
        return listing

    def search_series(
        self, query: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        listing = paginate(search_entries(self._catalogue(), normalized), page)
        logger.info(
            "Gutenberg search %r page=%d count=%d total=%d",
            normalized,
            listing.page,
            len(listing.items),
            listing.total,
        )
        return listing

    def browse_by_genre(
        self, genre: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        normalized = (genre or "").strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        listing = paginate(genre_entries(self._catalogue(), normalized), page)
        logger.info(
            "Gutenberg genre %r page=%d count=%d total=%d",
            normalized,
            listing.page,
            len(listing.items),
            listing.total,
        )
        return listing

    # --- one book, two requests -------------------------------------------

    def _load_book(self, series_key: str) -> _ParsedBook | None:
        """Fetch and parse a book once; serve every later read from the cache.

        Returns None when the id is not a Gutenberg ebook id, the book does
        not exist, it is not an English public-domain text, or its EPUB
        yields no readable chapters — all of which mean the same thing to a
        reader: this is not a series we can serve.
        """
        book_id = normalize_series_key(series_key)
        if not book_id:
            return None
        cached = self._books.get(book_id)
        if cached is not None:
            return cached

        try:
            page = self._http.get_text(detail_path(book_id))
        except ConnectorHttpError as exc:
            logger.warning("Gutenberg book page %s failed: %s", book_id, exc)
            if _is_not_found(exc):
                return None
            raise
        series = parse_book_page(page, book_id)
        if series is None:
            # Not an English public-domain text — see parse_book_page.
            logger.info("Gutenberg book %s is not servable; skipping", book_id)
            return None

        path = download_path(book_id)
        try:
            _content_type, blob = self._http.get_bytes(path)
        except ConnectorHttpError as exc:
            logger.warning("Gutenberg download %s failed: %s", path, exc)
            if _is_not_found(exc):
                return None
            raise
        if len(blob) > MAX_EPUB_BYTES:
            logger.warning(
                "Gutenberg EPUB %s is %d bytes, over the %d cap; skipping",
                path,
                len(blob),
                MAX_EPUB_BYTES,
            )
            return None

        parsed = parse_epub(blob)
        # The compressed book goes out of scope here; only paragraphs are kept.
        del blob
        if parsed is None or not parsed.chapters:
            logger.warning("Gutenberg EPUB %s yielded no chapters", path)
            return None

        series = Series(
            id=book_id,
            # Prefer the bibliographic record's title; fall back to the EPUB's.
            title=series.title or (parsed.title or ""),
            chapter_count=len(parsed.chapters),
            description=series.description,
            cover_url=series.cover_url,
            author=series.author or parsed.author,
            status=series.status,
            genres=series.genres,
            latest_chapter=parsed.chapters[-1].title,
        )
        if not series.title:
            return None

        book = _ParsedBook(
            series=series,
            chapters=chapters_from_epub(book_id, parsed.chapters),
            texts={chapter.key: chapter for chapter in parsed.chapters},
        )
        self._books.set(book_id, book)
        logger.info(
            "Gutenberg book %s parsed: chapters=%d words=%d",
            book_id,
            len(parsed.chapters),
            sum(chapter.word_count for chapter in parsed.chapters),
        )
        return book

    def get_series(self, series_id: str) -> Series | None:
        book = self._load_book(series_id)
        return book.series if book is not None else None

    def get_chapters(self, series_id: str) -> list[Chapter]:
        book = self._load_book(series_id)
        return list(book.chapters) if book is not None else []

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        # Novels have no page images; reading goes through /novels/chapter.
        return []

    def find_page(self, page_id: str) -> Page | None:
        return None

    # --- chapter text (0 further requests while the book is cached) --------

    def chapter_text(self, series_key: str, chapter_key: str) -> NovelChapterText | None:
        book = self._load_book(series_key)
        if book is None:
            return None
        key = normalize_chapter_key(chapter_key)
        chapter = book.texts.get(key)
        if chapter is None:
            logger.warning(
                "Gutenberg chapter %s not in book %s spine", key, series_key
            )
            return None
        if not looks_english(chapter.paragraphs):
            logger.warning(
                "Gutenberg chapter %s of %s failed the English check", key, series_key
            )
            return None
        logger.info(
            "Gutenberg chapter %s of %s paragraphs=%d words=%d",
            key,
            series_key,
            len(chapter.paragraphs),
            chapter.word_count,
        )
        return NovelChapterText(
            title=chapter.title,
            paragraphs=chapter.paragraphs,
            chapter_number=chapter.number,
        )
