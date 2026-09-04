"""Internet Archive novel source connector (spec 2026-09-04-novels-design §4).

Every other source in this repo serves one chapter per URL. archive.org
serves whole books, so this connector is an **EPUB importer wearing the
connector interface**: it fetches a book once, parses its OPF spine into
chapters (``epub.py``), and answers ``get_series`` / ``get_chapters`` /
``chapter_text`` from that single parse.

Request budget -- the point of the design:

* browse / search: **1 request**, no book is touched. Listings come entirely
  from ``advancedsearch.php``.
* first touch of a book (whichever of ``get_series`` / ``get_chapters`` /
  ``chapter_text`` arrives first): **2 requests** -- ``/metadata/<id>`` to
  find the smallest EPUB, then that one file. Both are needed: EPUB
  filenames are per-item (``pg1661.epub``, ``bram-stoker_dracula.epub``) and
  cannot be guessed.
* every subsequent chapter of that book while the parse is cached: **0
  requests**. Reading a 29-chapter novel end to end therefore costs 2 HTTP
  requests, not 29 -- and because ``novel_chapter_cache`` persists each
  chapter's text server-side, it costs 2 for every reader, not 2 per reader.

The book is never written to disk. It is read into memory, parsed, and the
compressed bytes are dropped; only the extracted paragraphs are retained,
under the bounded cache below. That keeps the connector inside the VPS's
~20GB budget by construction rather than by cleanup.

Scope: Project Gutenberg + Standard Ebooks only, deliberately -- see the
``PUBLIC_DOMAIN_SCOPE`` comment in ``mappers.py`` before widening it.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass

from connectors.archiveorg.epub import EpubChapter, parse_epub
from connectors.archiveorg.mappers import (
    MAX_PAGE,
    PAGE_SIZE,
    SITE_BASE,
    chapters_from_epub,
    download_path,
    epub_filename,
    normalize_chapter_key,
    normalize_series_key,
    parse_search,
    search_params,
    series_from_metadata,
)
from connectors.base import SourceConnector
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

#: Largest EPUB this connector will download, checked against the size the
#: metadata API declares BEFORE the request is made. Illustrated Gutenberg
#: variants reach 35 MB; the text-only edition of the same book is a few
#: hundred KB, and ``epub_filename`` prefers it.
MAX_EPUB_BYTES = 5_000_000

#: Parsed books held in memory. Bounded on purpose: a parse is roughly a
#: megabyte of paragraph text, and the shared ``TTLCache`` has no size
#: ceiling of its own, so an unbounded one would let a crawler walk the
#: catalogue straight into the VPS's RAM.
MAX_CACHED_BOOKS = 4
BOOK_CACHE_TTL_SECONDS = 900.0


@dataclass(frozen=True, slots=True)
class _ParsedBook:
    """One fetched-and-parsed book: everything the three reads need."""

    series: Series
    chapters: list[Chapter]
    texts: dict[str, EpubChapter]


class _BookCache:
    """TTL cache with an LRU ceiling on how many books it may hold.

    Wraps the shared ``TTLCache`` (it owns expiry) and keeps its own key
    order so the oldest-used book can be evicted once ``max_entries`` is
    reached. Connectors are shared singletons across request threads, so the
    ordering is lock-guarded.
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


def _is_not_found(exc: ConnectorHttpError) -> bool:
    """True when the failure was an upstream HTTP 404.

    The shared client only attaches ``status_code`` for RETRYABLE_STATUS
    responses, and ``get_bytes`` re-raises with no status at all, so a 404
    arrives as ``status_code=None`` carrying httpx's ``raise_for_status``
    text ("Client error '404 Not Found' for url ..."). A bare
    ``exc.status_code == 404`` check is dead code against this client --
    match both forms, as royalroad/freewebnovel do.
    """
    return exc.status_code == 404 or "404 Not Found" in str(exc)


class ArchiveOrgConnector(SourceConnector):
    """Read public-domain books from the Internet Archive as novels."""

    SOURCE_TYPE = "archiveorg"
    DISPLAY_NAME = "Internet Archive"
    DESCRIPTION = (
        "Read public-domain books from the Internet Archive's curated "
        "Project Gutenberg and Standard Ebooks collections. Each book's EPUB "
        "is split along its own chapter structure and served as clean "
        "plain-text paragraphs."
    )
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False
    CONTENT_KIND = "novel"
    LANGUAGE = "en"

    def __init__(self) -> None:
        self._http = SyncConnectorHttpClient(
            SITE_BASE,
            # A whole book on one connection; the default 30s is tight for a
            # multi-megabyte EPUB off a cold storage node.
            timeout=60.0,
            user_agent=BROWSER_USER_AGENT,
            headers={"Accept": "application/json"},
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
        # Covers come from /services/img/<id>, which redirects to the item's
        # storage node (dn790006.ca.archive.org); the subdomain match covers
        # every node without allowlisting the whole internet.
        return frozenset({"archive.org"})

    def image_fetch_headers(self) -> dict[str, str]:
        return {"Referer": f"{SITE_BASE}/", "User-Agent": BROWSER_USER_AGENT}

    def list_browse_modes(self) -> list[BrowseMode]:
        return [
            BrowseMode(id="default", label="Most Downloaded"),
            BrowseMode(id="trending", label="Trending This Week"),
            BrowseMode(id="recent", label="Recently Added"),
            BrowseMode(id="title", label="A-Z"),
        ]

    # --- listings (1 request, no book is fetched) --------------------------

    def _search(
        self, query: str | None, page: int, sort: str | None
    ) -> PaginatedSeriesList:
        if page < 1:
            page = 1
        if page > MAX_PAGE:
            # archive.org refuses to page past 10,000 results; answering
            # empty here saves a request that could only return its error.
            logger.info("ArchiveOrg page %d is past the deep-paging wall", page)
            return PaginatedSeriesList(items=[], page=page, page_size=PAGE_SIZE, total=0)
        payload = self._http.get_json(
            "/advancedsearch.php", params=search_params(query, page, sort=sort)
        )
        listing = parse_search(payload, page=page)
        logger.info(
            "ArchiveOrg search %r page=%d sort=%s count=%d has_more=%s",
            query or "",
            page,
            sort or "default",
            len(listing.items),
            listing.has_more,
        )
        return listing

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self._search(None, page, sort)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        normalized = query.strip()
        if not normalized:
            return self.get_series_list(page, sort=sort)
        return self._search(normalized, page, sort)

    # --- one book, one fetch ----------------------------------------------

    def _load_book(self, series_key: str) -> _ParsedBook | None:
        """Fetch and parse a book once; serve every later read from the cache.

        Returns None when the item does not exist, carries no usable EPUB, or
        the EPUB yields no readable chapters -- all of which mean the same
        thing to a reader: this is not a series we can serve.
        """
        series_key = normalize_series_key(series_key)
        if not series_key:
            return None
        cached = self._books.get(series_key)
        if cached is not None:
            return cached

        try:
            metadata = self._http.get_json(f"/metadata/{series_key}")
        except ConnectorHttpError as exc:
            logger.warning("ArchiveOrg metadata %s failed: %s", series_key, exc)
            if _is_not_found(exc):
                return None
            raise
        if not metadata.get("metadata"):
            # A nonexistent identifier answers 200 {} -- not a 404.
            logger.info("ArchiveOrg item %s does not exist", series_key)
            return None

        filename = epub_filename(metadata, max_bytes=MAX_EPUB_BYTES)
        if filename is None:
            # No EPUB (or only oversized ones). PDF/DjVuTXT are OCR of
            # scanned pages and cannot be split into chapters reliably, so
            # the item is skipped rather than served as damaged text.
            logger.info("ArchiveOrg item %s has no usable EPUB; skipping", series_key)
            return None

        path = download_path(series_key, filename)
        try:
            _content_type, blob = self._http.get_bytes(path)
        except ConnectorHttpError as exc:
            logger.warning("ArchiveOrg download %s failed: %s", path, exc)
            if _is_not_found(exc):
                return None
            raise

        parsed = parse_epub(blob)
        # The compressed book goes out of scope here; only paragraphs are kept.
        del blob
        if parsed is None or not parsed.chapters:
            logger.warning("ArchiveOrg EPUB %s yielded no chapters", path)
            return None

        series = series_from_metadata(
            metadata,
            series_key,
            title=parsed.title,
            author=parsed.author,
            chapter_count=len(parsed.chapters),
        )
        if series is None:
            return None

        book = _ParsedBook(
            series=series,
            chapters=chapters_from_epub(series_key, parsed.chapters),
            texts={chapter.key: chapter for chapter in parsed.chapters},
        )
        self._books.set(series_key, book)
        logger.info(
            "ArchiveOrg book %s parsed: file=%s chapters=%d words=%d",
            series_key,
            filename,
            len(parsed.chapters),
            sum(c.word_count for c in parsed.chapters),
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
                "ArchiveOrg chapter %s not in book %s spine", key, series_key
            )
            return None
        if not looks_english(chapter.paragraphs):
            logger.warning(
                "ArchiveOrg chapter %s of %s failed the English check", key, series_key
            )
            return None
        logger.info(
            "ArchiveOrg chapter %s of %s paragraphs=%d words=%d",
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
