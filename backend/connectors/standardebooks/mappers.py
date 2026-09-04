"""Map Standard Ebooks HTML/XHTML to normalized connector models.

Standard Ebooks (https://standardebooks.org) hand-produces public-domain
ebooks: ~1,500 titles, every one proofread, typographically corrected and
released CC0. Probed FROM THE VPS on 2026-09-04 through production's exact
egress and TLS stack (the methodology in the novels spec §4): browse, search,
book pages, tables of contents and chapter documents all answer 200 with
plain httpx. No Cloudflare, no interstitial, no rate-limit banner.

Views used:

* Browse   -> ``GET /ebooks?page=N&per-page=48[&sort=...]``. Cards are RDFa
  ``<li typeof="schema:Book" about="/ebooks/<key>">`` blocks — the key is an
  attribute, not something to reconstruct from a URL.
* Search   -> ``GET /ebooks?query=<q>&page=N&per-page=48`` (same card markup).
* Book     -> ``GET /ebooks/<key>``: title, author(s), cover, description,
  subjects.
* Contents -> ``GET /ebooks/<key>/text``: the ebook's own EPUB nav document,
  ``<nav id="toc">`` holding ``<a href="text/<slug>">`` links in reading
  order. This is the chapter list; nothing has to be inferred from prose.
* Chapter  -> ``GET /ebooks/<key>/text/<slug>``: a standalone XHTML document
  whose ``<main>`` contains ONLY the chapter. Site chrome lives in sibling
  ``<header>``/``<footer>`` elements, so slicing ``<main>`` is the whole
  sanitizing job — there is no ad markup and no watermark text on this site.

**The honeypot.** Every Standard Ebooks page opens its ``<header>`` with
``<a href="/honeypot" hidden="hidden">Following this link will ban your IP
for 24 hours</a>``. It sits OUTSIDE ``<main>``, so slicing ``<main>`` drops
it structurally, and nothing here ever follows a link out of a page. Both
properties are pinned by tests: a parser change that widens the slice past
``<main>`` would put that sentence into chapter text (and into TTS), and a
crawler-style change that followed page links would get the VPS banned.

Identity (house law: opaque, stored raw, never parsed):

* ``series_key``  = ``"<author>/<book>"`` or ``"<author>/<book>/<translator>"``
  (e.g. ``mary-shelley/frankenstein``, ``confucius/analects/james-legge``) —
  exactly the tail of the site's own URL, so a key round-trips as
  ``/ebooks/{series_key}``. THREE segments are routine (translated works), so
  nothing may assume a two-segment key.
* ``chapter_key`` = the ToC slug (e.g. ``chapter-1``, ``letter-4``,
  ``preface``), so a chapter is ``/ebooks/{series_key}/text/{chapter_key}``.
"""

from __future__ import annotations

import html as html_lib
import re

from connectors.ids import fully_unquote
from connectors.models import Chapter, NovelChapterText, PaginatedSeriesList, Series
from connectors.novel_text import extract_paragraphs, slice_element

SITE_BASE = "https://standardebooks.org"

#: The largest per-page the site's own form offers.
PAGE_SIZE = 48

#: Browse sorts exposed as modes. ``None`` means "send no sort param", which
#: is the site default (S.E. release date, newest first).
BROWSE_SORTS: dict[str, str | None] = {
    "": None,
    "default": None,
    "newest": None,
    "popularity": "popularity",
    "popular": "popularity",
    "reading-ease": "reading-ease",
    "easiest": "reading-ease",
    "length": "length",
    "shortest": "length",
    "author": "author-alpha",
    "author-alpha": "author-alpha",
}

# ---------------------------------------------------------------------------
# Structural boilerplate in every Standard Ebooks table of contents. These are
# real documents, but they are production furniture (the title page, the CC0
# dedication, the list of contributors), not chapters — serving them as
# chapters would put "Uncopyright" between the last chapter and the end of the
# book. Front matter that IS part of the work (introduction, preface,
# dedication, epigraph, endnotes) is deliberately NOT in this set.
# ---------------------------------------------------------------------------
NON_READING_SLUGS = frozenset(
    {"titlepage", "imprint", "halftitlepage", "colophon", "uncopyright"}
)

_BOOK_CARD_RE = re.compile(r'<li typeof="schema:Book" about="/ebooks/([^"]+)"')
_SCHEMA_NAME_RE = re.compile(r'<span property="schema:name">([^<]*)</span>')
_AUTHOR_BLOCK_RE = re.compile(r'<p class="author"[^>]*>(.*?)</p>', re.DOTALL)
_CARD_COVER_RE = re.compile(r'<img src="(/images/covers/[^"]+)"')
_NEXT_PAGE_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*rel="next"')

_H1_RE = re.compile(r'<h1[^>]*property="schema:name"[^>]*>(.*?)</h1>', re.DOTALL)
_PAGE_AUTHOR_RE = re.compile(
    r'<a property="schema:author"[^>]*>\s*<span property="schema:name">([^<]*)</span>',
    re.DOTALL,
)
_OG_IMAGE_RE = re.compile(r'<meta content="([^"]*)" property="og:image"\s*/?>')
_SUBJECT_RE = re.compile(r'<a href="/subjects/[^"]*">([^<]*)</a>')
_DESCRIPTION_OPEN = r'<div[^>]*property="schema:description"[^>]*>'

_TOC_NAV_OPEN = r'<nav[^>]*id="toc"[^>]*>'
_TOC_LINK_RE = re.compile(r'<a href="text/([^"#]+)"[^>]*>(.*?)</a>', re.DOTALL)

_MAIN_OPEN = r"<main\b[^>]*>"
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
# A chapter document opens with its own heading ("Chapter I", or an <hgroup>
# pairing the label with a subtitle). That text is already the chapter title;
# leaving it in the body would make every chapter start by reading its own
# name aloud.
_HEADING_BLOCK_RE = re.compile(
    r"<hgroup\b[^>]*>.*?</hgroup>|<h([1-6])\b[^>]*>.*?</h\1\s*>",
    re.DOTALL | re.IGNORECASE,
)


# Inline markup inside a label ("Stave <span>I</span>: Marley's Ghost") is
# replaced with a space so words never fuse, which then leaves a space in
# front of the punctuation that followed the tag ("Stave I : Marley's Ghost").
_LOOSE_PUNCTUATION_RE = re.compile(r"\s+([,;:.!?)\]])")


def _clean(text: str) -> str:
    stripped = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    return _LOOSE_PUNCTUATION_RE.sub(r"\1", html_lib.unescape(stripped)).strip()


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    return f"{SITE_BASE}{url}" if url.startswith("/") else f"{SITE_BASE}/{url}"


def normalize_series_key(value: str) -> str:
    """``/ebooks/a/b``, a full URL, or a chapter URL -> ``a/b``.

    Keys carry two OR three segments (a translated work names its
    translator), so this trims wrappers instead of counting parts.
    """
    cleaned = fully_unquote(value).strip().strip("/")
    if cleaned.startswith("http"):
        cleaned = cleaned.split("standardebooks.org/", 1)[-1].strip("/")
    if cleaned.startswith("ebooks/"):
        cleaned = cleaned[len("ebooks/") :]
    # "<key>/text" (contents) and "<key>/text/<slug>" (a chapter) both reduce
    # to the book they belong to.
    if "/text" in cleaned:
        cleaned = cleaned.split("/text", 1)[0]
    return cleaned.strip("/")


def normalize_chapter_key(value: str) -> str:
    """``text/chapter-1``, a chapter URL, or ``chapter-1`` -> ``chapter-1``."""
    cleaned = fully_unquote(value).strip().strip("/")
    if "/text/" in cleaned:
        cleaned = cleaned.split("/text/", 1)[1]
    elif cleaned.startswith("text/"):
        cleaned = cleaned[len("text/") :]
    return cleaned.strip("/")


def series_path(series_key: str) -> str:
    return f"/ebooks/{normalize_series_key(series_key)}"


def toc_path(series_key: str) -> str:
    return f"/ebooks/{normalize_series_key(series_key)}/text"


def chapter_path(series_key: str, chapter_key: str) -> str:
    return (
        f"/ebooks/{normalize_series_key(series_key)}"
        f"/text/{normalize_chapter_key(chapter_key)}"
    )


def browse_params(
    page: int, *, sort: str | None = None, query: str | None = None
) -> dict[str, str | int]:
    params: dict[str, str | int] = {"page": page, "per-page": PAGE_SIZE}
    sort_value = BROWSE_SORTS.get((sort or "").strip().lower())
    if sort_value:
        params["sort"] = sort_value
    if query:
        params["query"] = query
    return params


def parse_ebook_list(html_text: str, *, page: int) -> PaginatedSeriesList:
    """Parse a browse or search page's ``schema:Book`` cards."""
    matches = list(_BOOK_CARD_RE.finditer(html_text))
    items: list[Series] = []
    for index, match in enumerate(matches):
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(html_text)
        )
        block = html_text[match.end() : end]
        key = html_lib.unescape(match.group(1)).strip("/")
        names = [_clean(name) for name in _SCHEMA_NAME_RE.findall(block)]
        # Card order is title first, then one span per author. A card with no
        # title is markup drift — house law says it never reaches clients.
        title = names[0] if names else ""
        if not key or not title:
            continue
        authors = [
            _clean(name)
            for author_block in _AUTHOR_BLOCK_RE.findall(block)
            for name in _SCHEMA_NAME_RE.findall(author_block)
        ]
        cover = _CARD_COVER_RE.search(block)
        items.append(
            Series(
                id=key,
                title=title,
                # Listings carry no chapter count and fetching 48 tables of
                # contents to invent one would be absurd; the detail view
                # fills it in from the real ToC.
                chapter_count=0,
                cover_url=_absolute(cover.group(1)) if cover else None,
                author=", ".join(dict.fromkeys(authors)) or None,
                status="completed",
            )
        )
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=0,
        # The site clamps an over-large page number to the last page instead
        # of erroring, so "is there a next page" can only come from the
        # pagination nav's rel="next" link.
        api_has_more=bool(_NEXT_PAGE_RE.search(html_text)),
    )


def parse_toc(toc_html: str, series_key: str) -> list[Chapter]:
    """Reading-order chapter list from the ebook's own EPUB nav document.

    Only ``<nav id="toc">`` is read: the document carries a second
    ``<nav id="landmarks">`` that re-links the first chapter, and parsing the
    whole page would emit that chapter twice.
    """
    series_key = normalize_series_key(series_key)
    nav = slice_element(toc_html, _TOC_NAV_OPEN)
    if nav is None:
        return []
    chapters: list[Chapter] = []
    for slug, label in _TOC_LINK_RE.findall(nav):
        slug = html_lib.unescape(slug).strip("/")
        if not slug or slug in NON_READING_SLUGS:
            continue
        title = _clean(label)
        if not title:
            continue
        chapters.append(
            Chapter(
                id=slug,
                series_id=series_key,
                # Position in the table of contents IS the chapter number:
                # front matter shifts it, and the slug's own digits do not
                # (``letter-4`` and ``chapter-4`` are different documents).
                title=title,
                number=float(len(chapters) + 1),
                page_count=0,
            )
        )
    return chapters


def parse_book(
    book_html: str, toc_html: str, series_key: str
) -> tuple[Series | None, list[Chapter]]:
    """Series metadata (book page) + chapter list (contents page)."""
    series_key = normalize_series_key(series_key)
    title_match = _H1_RE.search(book_html)
    if title_match is None:
        return None, []
    title = _clean(title_match.group(1))
    if not title:
        return None, []

    chapters = parse_toc(toc_html, series_key)
    authors = [_clean(name) for name in _PAGE_AUTHOR_RE.findall(book_html)]
    cover = _OG_IMAGE_RE.search(book_html)
    genres = tuple(
        dict.fromkeys(_clean(subject) for subject in _SUBJECT_RE.findall(book_html))
    )

    description = None
    description_body = slice_element(book_html, _DESCRIPTION_OPEN)
    if description_body:
        description = "\n\n".join(extract_paragraphs(description_body)) or None

    series = Series(
        id=series_key,
        title=title,
        chapter_count=len(chapters),
        description=description,
        cover_url=_absolute(cover.group(1)) if cover else None,
        author=", ".join(dict.fromkeys(authors)) or None,
        # Standard Ebooks only publishes finished, proofread books; there is
        # no such thing as an ongoing title here.
        status="completed",
        genres=genres,
        latest_chapter=chapters[-1].title if chapters else None,
    )
    return series, chapters


def _strip_leading_heading(body: str) -> str:
    """Drop the chapter's own heading block when it opens the body."""
    match = _HEADING_BLOCK_RE.search(body)
    if match is None:
        return body
    first_paragraph = body.lower().find("<p")
    # An <hgroup> legitimately CONTAINS a <p> (the subtitle), so compare
    # against the heading's start, not its end.
    if first_paragraph != -1 and match.start() > first_paragraph:
        return body
    return body[: match.start()] + body[match.end() :]


def chapter_title_from_document(html_text: str) -> str:
    """``<title>Frankenstein - Chapter I</title>`` -> ``Chapter I``.

    Every chapter document titles itself "<book> - <chapter>"; the book half
    is already known to the caller, so only the chapter half is kept.
    """
    match = _TITLE_TAG_RE.search(html_text)
    if match is None:
        return ""
    full = _clean(match.group(1))
    return full.split(" - ", 1)[1].strip() if " - " in full else full


def parse_chapter_page(html_text: str) -> NovelChapterText | None:
    """Sanitized plain-text paragraphs for one chapter document.

    ``<main>`` is the entire chapter and nothing else — the site chrome (nav,
    the honeypot link, previous/next footer links) are siblings of ``<main>``,
    so the slice removes them structurally rather than by blacklist.
    """
    body = slice_element(html_text, _MAIN_OPEN)
    if body is None:
        return None
    paragraphs = extract_paragraphs(_strip_leading_heading(body))
    if not paragraphs:
        return None
    return NovelChapterText(
        title=chapter_title_from_document(html_text),
        paragraphs=tuple(paragraphs),
        # Left None on purpose: the authoritative number is the chapter's
        # position in the table of contents (which the novel service backfills
        # from ``get_chapters``), and the slug's digits disagree with it
        # whenever a book has front matter.
        chapter_number=None,
    )
