"""Map the gutendex API and Project Gutenberg EPUBs to connector models.

Project Gutenberg is ~75,000 public-domain books. This connector reads its
**catalogue** from gutendex (https://gutendex.com), a clean read-only JSON API
over Gutenberg's own metadata, and its **text** from gutenberg.org's generated
EPUBs. Probed FROM THE VPS (production egress/TLS, 2026-09-04): both hosts
answer 200 with plain httpx.

robots.txt, checked for every path this connector touches:

* ``gutendex.com/robots.txt`` -> ``User-agent: * / Allow: /``. The whole
  catalogue layer is allowed.
* ``www.gutenberg.org/robots.txt`` is two lines: ``User-agent: *`` /
  ``Disallow: /ebooks/search``. That single disallowed path is exactly the
  HTML search this connector does NOT use — going through gutendex is both
  the cleaner and the robots-correct way to search. The download path used
  here, ``/ebooks/<id>.epub.noimages``, is allowed, as is the
  ``/cache/epub/<id>/pg<id>.epub`` it redirects to.

**Which EPUB, and why it matters.** gutendex advertises
``application/epub+zip`` as ``/ebooks/<id>.epub3.images`` — the EPUB 3
build. This connector deliberately requests ``/ebooks/<id>.epub.noimages``
instead, which is strictly better on both axes that matter here (measured
from the VPS against the same books):

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

import re
from typing import Any

from connectors.archiveorg.epub import EpubChapter
from connectors.ids import fully_unquote
from connectors.models import Chapter, PaginatedSeriesList, Series

API_BASE = "https://gutendex.com"
FILES_BASE = "https://www.gutenberg.org"

#: gutendex returns a fixed 32 records per page.
PAGE_SIZE = 32

#: Only ask for books that actually ship an EPUB — the connector cannot serve
#: anything else, and filtering upstream keeps unusable rows out of listings
#: instead of having them 404 when opened.
EPUB_MIME = "application/epub+zip"

#: gutendex's whole ``sort`` vocabulary, mapped from our browse-mode ids. An
#: unknown value is silently ignored upstream (it answers 200 with the default
#: ordering), so this dict is the allowlist that keeps browse modes honest.
BROWSE_SORTS: dict[str, str] = {
    "": "popular",
    "default": "popular",
    "popular": "popular",
    "newest": "descending",
    "oldest": "ascending",
}

#: Language filter. Every novel source in this repo serves English.
LANGUAGE = "en"

#: Subjects/bookshelves kept per book, so a listing row stays small.
MAX_GENRES = 8


def download_path(book_id: str) -> str:
    """The EPUB path for a book id. See the module docstring for the variant."""
    return f"/ebooks/{book_id}.epub.noimages"


def normalize_series_key(value: str) -> str:
    """``84``, ``ebooks/84``, or a gutenberg/gutendex URL -> ``"84"``.

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


def series_detail_path(book_id: str) -> str:
    return f"/books/{book_id}"


def browse_params(query: str | None, page: int, sort: str | None) -> dict[str, Any]:
    """Query string for ``GET /books``.

    ``mime_type`` is always pinned so listings only contain books this
    connector can actually open; ``search`` is added only for a real query,
    and gutendex orders search results by relevance on its own.
    """
    params: dict[str, Any] = {
        "languages": LANGUAGE,
        "mime_type": EPUB_MIME,
        "page": max(1, page),
    }
    normalized = (query or "").strip()
    if normalized:
        params["search"] = normalized
    else:
        params["sort"] = BROWSE_SORTS.get((sort or "").strip().lower(), "popular")
    return params


def topic_params(topic: str, page: int, sort: str | None) -> dict[str, Any]:
    """Genre browse: gutendex's ``topic`` matches subjects and bookshelves."""
    params = browse_params(None, page, sort)
    params["topic"] = topic.strip()
    return params


# --- helpers ----------------------------------------------------------------


def _author_name(raw: str) -> str:
    """``"Austen, Jane"`` -> ``"Jane Austen"``.

    Gutenberg stores names surname-first for sorting. Only a single, simple
    comma is flipped — names carrying a suffix or a second comma
    ("Dumas, Alexandre, 1802-1870") are left exactly as they are rather than
    scrambled.
    """
    name = re.sub(r"\s+", " ", raw or "").strip()
    if name.count(",") != 1:
        return name
    surname, given = (part.strip() for part in name.split(","))
    if not surname or not given:
        return name
    return f"{given} {surname}"


def _authors(entries: Any) -> tuple[str, ...]:
    if not isinstance(entries, list):
        return ()
    names = []
    for entry in entries:
        if isinstance(entry, dict):
            name = _author_name(str(entry.get("name") or ""))
            if name:
                names.append(name)
    return tuple(dict.fromkeys(names))


def _genres(book: dict[str, Any]) -> tuple[str, ...]:
    """Readable topic labels from Gutenberg's subjects and bookshelves.

    Subjects are Library-of-Congress style ("Courtship -- Fiction") and
    bookshelves are curator-style ("Category: British Literature"); both are
    reduced to their leading human-readable segment and de-duplicated.
    """
    labels: list[str] = []
    for field in ("bookshelves", "subjects"):
        values = book.get(field)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            label = value.split(" -- ")[0].strip()
            label = re.sub(r"^(?:Category|Browsing)\s*:\s*", "", label).strip()
            if label:
                labels.append(label)
    return tuple(dict.fromkeys(labels))[:MAX_GENRES]


def _summary(book: dict[str, Any]) -> str | None:
    summaries = book.get("summaries")
    if isinstance(summaries, list):
        for entry in summaries:
            if isinstance(entry, str) and entry.strip():
                return re.sub(r"\s+", " ", entry).strip()
    return None


def _cover_url(book: dict[str, Any]) -> str | None:
    formats = book.get("formats")
    if not isinstance(formats, dict):
        return None
    for key, value in formats.items():
        if isinstance(key, str) and key.startswith("image/") and isinstance(value, str):
            return value
    return None


def _has_epub(book: dict[str, Any]) -> bool:
    formats = book.get("formats")
    if not isinstance(formats, dict):
        return False
    return any(
        isinstance(key, str) and key.split(";")[0].strip() == EPUB_MIME
        for key in formats
    )


def series_from_book(
    book: Any, *, chapter_count: int = 0, title: str | None = None
) -> Series | None:
    """One gutendex record -> ``Series``, or None when it cannot be served.

    Rejected here rather than at read time: a record with no id or title, a
    non-text medium (Gutenberg also holds audio and images), anything still
    in copyright, or a book with no EPUB to split into chapters.
    """
    if not isinstance(book, dict):
        return None
    book_id = book.get("id")
    if not isinstance(book_id, int) or book_id <= 0:
        return None
    name = re.sub(r"\s+", " ", str(title or book.get("title") or "")).strip()
    if not name:
        return None
    if str(book.get("media_type") or "").strip().lower() != "text":
        return None
    # Serve only what Gutenberg itself marks public domain in the US. A null
    # copyright flag means "unknown", which is not good enough to redistribute.
    if book.get("copyright") is not False:
        return None
    if not _has_epub(book):
        return None

    authors = _authors(book.get("authors"))
    return Series(
        id=str(book_id),
        title=name,
        # Listings leave this 0 ON PURPOSE: the real count needs the book
        # itself, and a listing must never cost one download per row.
        chapter_count=chapter_count,
        description=_summary(book),
        cover_url=_cover_url(book),
        author=authors[0] if authors else None,
        # Every book here is a finished, published work.
        status="completed",
        genres=_genres(book),
    )


def parse_book_list(payload: Any, *, page: int) -> PaginatedSeriesList:
    """``GET /books`` -> a paginated listing."""
    if not isinstance(payload, dict):
        return PaginatedSeriesList(items=[], page=page, page_size=PAGE_SIZE, total=0)
    results = payload.get("results")
    items: list[Series] = []
    if isinstance(results, list):
        for entry in results:
            series = series_from_book(entry)
            if series is not None:
                items.append(series)
    total = payload.get("count")
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=int(total) if isinstance(total, int) and total > 0 else 0,
        # gutendex hands back the next page's URL, or null on the last page —
        # authoritative, so it beats inferring from the total.
        api_has_more=bool(payload.get("next")),
    )


def parse_book(payload: Any) -> Series | None:
    """``GET /books/<id>`` -> ``Series``."""
    return series_from_book(payload)


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
