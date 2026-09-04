"""Map archive.org's search + metadata JSON to normalized connector models.

Endpoints, all probed and fixture-captured FROM THE VPS on 2026-09-04
(production egress/TLS -- the methodology in the novels spec §4). Plain
httpx, no Cloudflare anywhere on archive.org:

* Search   -> ``GET /advancedsearch.php?q=&rows=&page=&sort[]=&fl[]=&output=json``
  -> ``{responseHeader: {...}, response: {numFound, start, docs: [...]}}``.
* Metadata -> ``GET /metadata/<identifier>``
  -> ``{metadata: {...}, files: [{name, format, size}], ...}``.
* Download -> ``GET /download/<identifier>/<filename>``, which 302s to the
  item's storage node (``ia800509.us.archive.org``) -- a subdomain of
  ``archive.org``, so the shared client's redirect guard follows it.
* Cover    -> ``GET /services/img/<identifier>``.

Two response shapes have no HTTP status to match on, and both are handled
here rather than by the connector's error path:

* a missing identifier answers ``200 {}`` from ``/metadata`` -- an empty
  object, NOT a 404;
* ``/advancedsearch.php`` answers ``200 {"error": "[DEEP_PAGING] ..."}``
  once ``page * rows`` passes 10,000 results.
"""

from __future__ import annotations

import re
from typing import Any

from connectors.ids import fully_unquote
from connectors.models import Chapter, PaginatedSeriesList, Series

SITE_BASE = "https://archive.org"
PAGE_SIZE = 20

# archive.org refuses to page past 10,000 results (it points deep callers at
# its Scraping API instead), so the last servable page is 10000 / PAGE_SIZE.
DEEP_PAGING_LIMIT = 10_000
MAX_PAGE = DEEP_PAGING_LIMIT // PAGE_SIZE

# ---------------------------------------------------------------------------
# SCOPE -- do not widen this without reading why it is narrow.
#
# archive.org holds ~52M text items, and ~6.7M of those carry an EPUB. The
# overwhelming majority of that EPUB mass sits in the user-upload space
# (``collection:opensource`` / ``community``), which is full of in-copyright
# commercial books re-uploaded under false public-domain marks. Those items
# are removed on legal request, so a connector aimed at them serves other
# people's books until it 404s -- unpredictably, item by item.
#
# So this connector is scoped to collections that are public domain BY
# CURATION, not by an uploader's checkbox:
#
#   * ``gutenberg``      -- the Project Gutenberg mirror. PG clears rights
#                           before publishing; ~29.6k English EPUB items.
#   * ``standardebooks`` -- Standard Ebooks, PD sources released CC0.
#
# ``format:EPUB`` is part of the scope, not a preference: an item without an
# EPUB has no dependable chapter structure (see ``epub.py``), so it must
# never reach a listing in the first place.
#
# ``language`` is filtered UPSTREAM rather than client-side because the
# archive is multilingual and client-side filtering would empty whole pages.
# The three spellings are all real values in this collection: the same
# corpus carries ``eng`` (MARC), ``en`` (BCP-47) and ``English``.
# ---------------------------------------------------------------------------
PUBLIC_DOMAIN_SCOPE = (
    "collection:(gutenberg OR standardebooks) "
    "AND format:EPUB "
    "AND language:(eng OR en OR English)"
)

#: Fields asked of the search API. Anything not listed here is absent from
#: ``docs``, which is why listings carry no chapter count -- that costs a
#: book fetch and is filled in by ``get_series``.
SEARCH_FIELDS = (
    "identifier",
    "title",
    "creator",
    "description",
    "subject",
    "year",
    "downloads",
    "language",
)

#: Browse views; ids are this connector's, values are the API's sort strings.
BROWSE_SORTS: dict[str, str] = {
    "": "downloads desc",
    "default": "downloads desc",
    "popular": "downloads desc",
    "trending": "week desc",
    "recent": "addeddate desc",
    "latest": "addeddate desc",
    "title": "titleSorter asc",
}

#: Lucene syntax a user query must never smuggle in. The scope above is a
#: query STRING, so an unescaped ``)`` in a search term would close the
#: collection clause and let the rest of the query browse all 52M items --
#: exactly the user-upload space the scope exists to exclude. Search terms
#: are therefore reduced to bare words before they are concatenated.
_TERM_RE = re.compile(r"[^0-9A-Za-z'’\s-]+")
_LUCENE_OPERATORS = frozenset({"and", "or", "not", "to"})

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize_series_key(value: str) -> str:
    """A series key is the archive.org identifier, stored raw."""
    return fully_unquote(value).strip().strip("/")


def normalize_chapter_key(value: str) -> str:
    """A chapter key is a spine href; it may legitimately contain slashes."""
    return fully_unquote(value).strip().strip("/")


def sort_param(sort: str | None) -> str:
    return BROWSE_SORTS.get((sort or "").strip().lower(), "downloads desc")


def safe_terms(query: str) -> str:
    """User text -> Lucene-inert bare words (see ``_TERM_RE``).

    Punctuation goes, and the bare boolean operators go with it, so a query
    can only ever narrow the scoped search -- never restructure it.
    """
    cleaned = _TERM_RE.sub(" ", query)
    words = [
        stripped
        for word in cleaned.split()
        # A leading "-" is Lucene's NOT; strip it so hyphenated words survive
        # ("Twenty-One") without a term ever becoming an exclusion.
        if (stripped := word.strip("-")) and stripped.lower() not in _LUCENE_OPERATORS
    ]
    return " ".join(words[:16])


def scoped_query(query: str | None = None) -> str:
    """The public-domain scope, optionally narrowed by user search terms."""
    terms = safe_terms(query or "")
    return f"{PUBLIC_DOMAIN_SCOPE} AND ({terms})" if terms else PUBLIC_DOMAIN_SCOPE


def search_params(
    query: str | None, page: int, *, sort: str | None = None
) -> dict[str, Any]:
    return {
        "q": scoped_query(query),
        "rows": PAGE_SIZE,
        "page": max(1, page),
        "output": "json",
        "sort[]": sort_param(sort),
        "fl[]": list(SEARCH_FIELDS),
    }


def cover_url(identifier: str) -> str:
    """The item's thumbnail service.

    Always answers 200: the real cover when the item has one, a generic
    archive.org placeholder when it does not (most Project Gutenberg items
    have no thumbnail). A placeholder beats a broken image in the grid.
    """
    return f"{SITE_BASE}/services/img/{identifier}"


def download_path(identifier: str, filename: str) -> str:
    return f"/download/{identifier}/{filename}"


def _text(value: Any) -> str:
    """archive.org returns strings OR lists of strings for the same field."""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def _clean_description(value: Any) -> str | None:
    """Descriptions carry HTML (Standard Ebooks ships ``<div>`` blocks)."""
    text = _HTML_TAG_RE.sub(" ", _text(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _genres(value: Any) -> tuple[str, ...]:
    """``subject`` is a list, or one comma-separated string."""
    if isinstance(value, list):
        subjects = [str(v).strip() for v in value]
    else:
        subjects = [part.strip() for part in _text(value).split(",")]
    # Library subject headings are "Boys -- Fiction"; keep the leading facet.
    seen: list[str] = []
    for subject in subjects:
        head = subject.split(" -- ")[0].strip()
        if head and head not in seen:
            seen.append(head)
    return tuple(seen[:12])


def _series_from_doc(doc: dict[str, Any]) -> Series | None:
    identifier = _text(doc.get("identifier"))
    title = _text(doc.get("title"))
    if not identifier or not title:
        return None
    author = _text(doc.get("creator"))
    return Series(
        id=identifier,
        # chapter_count stays 0 in listings ON PURPOSE: the real count needs
        # the book's spine, and fetching 20 EPUBs to render one grid page is
        # exactly the cost this connector is designed to avoid.
        chapter_count=0,
        title=title,
        description=_clean_description(doc.get("description")),
        cover_url=cover_url(identifier),
        author=author or None,
        status="completed",  # A published book is never "ongoing".
        genres=_genres(doc.get("subject")),
    )


def parse_search(payload: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    """One search/browse page.

    An ``error`` payload (deep paging) and a result-less response both yield
    an empty page rather than an exception -- from a reader's point of view
    "there is nothing past here" and "you asked too deep" are the same thing.
    """
    if payload.get("error"):
        return PaginatedSeriesList(items=[], page=page, page_size=PAGE_SIZE, total=0)
    response = payload.get("response") or {}
    items: list[Series] = []
    for doc in response.get("docs") or []:
        if isinstance(doc, dict):
            series = _series_from_doc(doc)
            if series is not None:
                items.append(series)
    try:
        total = int(response.get("numFound") or 0)
    except (TypeError, ValueError):
        total = 0
    consumed = (page - 1) * PAGE_SIZE + len(items)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=total,
        # Clamped at the API's own deep-paging wall: claiming a page 501 the
        # API will refuse just makes the client fetch an empty page.
        api_has_more=bool(items) and consumed < min(total, DEEP_PAGING_LIMIT),
    )


def epub_filename(payload: dict[str, Any], *, max_bytes: int) -> str | None:
    """Pick the one EPUB to download for an item, or None if there is none.

    Items routinely ship several. Project Gutenberg publishes a text-only
    ``pg43936.epub`` (105 KB) beside an illustrated ``pg43936-images.epub``
    (9.9 MB) of the same book: identical prose, 94x the bytes. So illustrated
    variants are deprioritised and the smallest remaining EPUB within
    ``max_bytes`` wins -- deterministic (size comes from the metadata, no
    probing) and the cheapest for a 2-vCPU VPS.
    """
    candidates: list[tuple[int, int, str]] = []
    for entry in payload.get("files") or []:
        if not isinstance(entry, dict):
            continue
        name = _text(entry.get("name"))
        if _text(entry.get("format")).upper() != "EPUB" and not name.lower().endswith(".epub"):
            continue
        try:
            size = int(entry.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if not name or size <= 0 or size > max_bytes:
            continue
        illustrated = 1 if re.search(r"-(?:images|illustrated)\b", name, re.IGNORECASE) else 0
        candidates.append((illustrated, size, name))
    if not candidates:
        return None
    return min(candidates)[2]


def series_from_metadata(
    payload: dict[str, Any],
    identifier: str,
    *,
    title: str | None = None,
    author: str | None = None,
    chapter_count: int = 0,
) -> Series | None:
    """Item metadata (+ the parsed book's own title/author) -> ``Series``.

    ``/metadata`` answers ``200 {}`` for an identifier that does not exist,
    so an empty payload is the not-found signal here, not an HTTP error.
    """
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or not metadata:
        return None
    resolved_title = _text(metadata.get("title")) or (title or "").strip()
    if not resolved_title:
        return None
    # The catalogue record wins over the EPUB's own OPF metadata: Standard
    # Ebooks titles its OPF "Dracula" where the archive record reads
    # "Dracula by Bram Stoker", and the record is what search matched on.
    resolved_author = _text(metadata.get("creator")) or (author or "").strip()
    year = _text(metadata.get("year")) or _text(metadata.get("date"))[:4]
    return Series(
        id=normalize_series_key(identifier),
        title=resolved_title,
        chapter_count=chapter_count,
        description=_clean_description(metadata.get("description")),
        cover_url=cover_url(identifier),
        author=resolved_author or None,
        status="completed",
        genres=_genres(metadata.get("subject")),
        latest_chapter=year or None,
    )


def chapters_from_epub(series_key: str, chapters: Any) -> list[Chapter]:
    """``epub.EpubChapter`` list -> connector ``Chapter`` list."""
    series_key = normalize_series_key(series_key)
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
