"""Project Gutenberg novel source connector (spec 2026-09-04-novels-design §4).

Like ``archiveorg``, and unlike every per-chapter-URL source in this repo,
Gutenberg serves whole books — so this connector is an **EPUB importer
wearing the connector interface**: the catalogue comes from the gutendex JSON
API, and a book is fetched exactly once and split along its own OPF spine.

It deliberately reuses ``connectors.archiveorg.epub.parse_epub`` rather than
growing a second EPUB reader. That module is the house's hardened container
parser — zip-bomb refusal from the ZIP directory, href-traversal rejection,
spine/char budgets, Project Gutenberg licence-banner trimming — and a book
here is the *same kind of file* archive.org serves (many archive.org items
literally are Gutenberg EPUBs). Duplicating 450 lines of security-relevant
parsing to avoid one import would be strictly worse.

What this source adds over reaching Gutenberg through ``archiveorg``:

* the whole catalogue (~62,000 English EPUB titles) rather than the subset
  archive.org mirrors, with real search, topic browse and popularity order;
* one fewer indirection, and a smaller download — see ``mappers`` for the
  ``.epub.noimages`` measurements and the robots verdict for both hosts.

Request budget — the point of the design:

* browse / search: **1 request**, no book is touched.
* first touch of a book (whichever of ``get_series`` / ``get_chapters`` /
  ``chapter_text`` arrives first): **1 request** — the EPUB URL is derived
  from the book id, so unlike archive.org there is no metadata call to find
  the filename.
* every subsequent chapter of that book while the parse is cached: **0
  requests**. Reading a 46-chapter novel end to end costs 1 HTTP request,
  and ``novel_chapter_cache`` then keeps each chapter server-side for every
  other reader too.

The book is never written to disk: it is read into memory, parsed, and the
compressed bytes dropped — only the extracted paragraphs are retained, under
the bounded cache below. That keeps the connector inside the VPS's ~20 GB
budget by construction rather than by cleanup.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass

from connectors.archiveorg.epub import EpubChapter, parse_epub
from connectors.base import SourceConnector
from connectors.gutenberg.mappers import (
    API_BASE,
    FILES_BASE,
    PAGE_SIZE,
    browse_params,
    chapters_from_epub,
    download_path,
    normalize_chapter_key,
    normalize_series_key,
    parse_book,
    parse_book_list,
    series_detail_path,
    topic_params,
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

#: gutendex is a small community-run service with a very wide latency spread,
#: measured from the VPS 2026-09-04 on guaranteed-cold queries (distinct deep
#: page numbers, so no cache entry could already exist):
#:
#:     cold  63-112 s   |   warm  ~0.0 s   |   plus intermittent 503s
#:
#: The spread is a property of the service, not of the query — browse, search
#: and topic all behave the same, with and without the ``mime_type`` filter.
#: An immediately repeated query is served from their cache in milliseconds,
#: so the pragmatic shape is one generous attempt plus one retry: the first
#: attempt warms gutendex even if it times out on our side, and the repeat
#: then lands instantly. Both failure modes are already retryable in the
#: shared client (503 by status, a timeout as a transport error).
API_TIMEOUT_SECONDS = 90.0
API_MAX_RETRIES = 2

#: Refuse to parse a book larger than this. The ``.epub.noimages`` build is a
#: few hundred KB for a normal novel (Alice 137 KB, Pride and Prejudice
#: 558 KB, Moby-Dick 727 KB), so this only ever fires on an anomaly — the
#: illustrated builds this connector does NOT request are the 16-25 MB ones.
MAX_EPUB_BYTES = 5_000_000

#: Parsed books held in memory. Bounded on purpose: a parse is roughly a
#: megabyte of paragraph text and the shared ``TTLCache`` has no size ceiling
#: of its own, so an unbounded one would let a crawler walk 62,000 titles
#: straight into the VPS's RAM.
MAX_CACHED_BOOKS = 4
BOOK_CACHE_TTL_SECONDS = 900.0

#: Topic browse. gutendex's ``topic`` matches subjects AND bookshelves, so
#: these are single words chosen to hit both vocabularies.
GENRE_TOPICS: tuple[tuple[str, str], ...] = (
    ("adventure", "Adventure"),
    ("fantasy", "Fantasy"),
    ("science fiction", "Science Fiction"),
    ("detective", "Mystery & Detective"),
    ("horror", "Horror"),
    ("romance", "Romance"),
    ("historical fiction", "Historical Fiction"),
    ("children", "Children's Literature"),
    ("poetry", "Poetry"),
    ("humor", "Humour"),
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
        # Two hosts, two clients: the catalogue API and the file host are
        # different origins, and the client's redirect guard is anchored to
        # its own base URL (an EPUB 302s within gutenberg.org only).
        self._api = SyncConnectorHttpClient(
            API_BASE,
            timeout=API_TIMEOUT_SECONDS,
            # Retrying a cold query is what actually pays off here (the first
            # attempt warms gutendex's cache even when we hang up on it), but
            # each attempt can cost the full timeout, so the count is trimmed
            # to bound the worst case instead of the default 3.
            max_retries=API_MAX_RETRIES,
            user_agent=BROWSER_USER_AGENT,
            headers={"Accept": "application/json"},
        )
        self._files = SyncConnectorHttpClient(
            FILES_BASE,
            # A whole book on one connection; the default 30s is tight when
            # gutenberg.org has to generate the file.
            timeout=60.0,
            user_agent=BROWSER_USER_AGENT,
            headers={"Accept": "application/epub+zip,*/*"},
        )
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
        return {"Referer": f"{FILES_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Most Downloaded"),
            BrowseMode(id="newest", label="Recently Added"),
            BrowseMode(id="oldest", label="Earliest Catalogued"),
        ]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id=topic, label=label) for topic, label in GENRE_TOPICS]

    # --- listings (1 request, no book is fetched) --------------------------

    def _listing(
        self, query: str | None, page: int, sort: str | None, topic: str | None = None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        params = (
            topic_params(topic, page, sort)
            if topic
            else browse_params(query, page, sort)
        )
        try:
            payload = self._api.get_json("/books", params=params)
        except ConnectorHttpError as exc:
            # gutendex answers 404 for a page past the end of a result set.
            if _is_not_found(exc):
                logger.info("Gutenberg listing page %d is past the end", page)
                return PaginatedSeriesList(
                    items=[], page=page, page_size=PAGE_SIZE, total=0
                )
            raise
        listing = parse_book_list(payload, page=page)
        logger.info(
            "Gutenberg listing q=%r topic=%s page=%d sort=%s count=%d has_more=%s",
            query or "",
            topic or "-",
            page,
            sort or "default",
            len(listing.items),
            listing.has_more,
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._listing(None, page, sort)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing(normalized, page, sort)

    def browse_by_genre(
        self, genre: str, page: int, *, sort: str | None = None
    ) -> PaginatedSeriesList:
        normalized = (genre or "").strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._listing(None, page, sort, topic=normalized)

    # --- one book, one fetch ----------------------------------------------

    def _load_book(self, series_key: str) -> _ParsedBook | None:
        """Fetch and parse a book once; serve every later read from the cache.

        Returns None when the id is not a Gutenberg ebook id, the book does
        not exist, it is not a public-domain text, or its EPUB yields no
        readable chapters — all of which mean the same thing to a reader:
        this is not a series we can serve.
        """
        book_id = normalize_series_key(series_key)
        if not book_id:
            return None
        cached = self._books.get(book_id)
        if cached is not None:
            return cached

        try:
            metadata = self._api.get_json(series_detail_path(book_id))
        except ConnectorHttpError as exc:
            logger.warning("Gutenberg metadata %s failed: %s", book_id, exc)
            if _is_not_found(exc):
                return None
            raise
        series = parse_book(metadata)
        if series is None:
            # Not a public-domain text with an EPUB — see series_from_book.
            logger.info("Gutenberg book %s is not servable; skipping", book_id)
            return None

        path = download_path(book_id)
        try:
            _content_type, blob = self._files.get_bytes(path)
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
            # Prefer the catalogue's title; fall back to the book's own.
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
