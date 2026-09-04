"""Map NovelFull HTML to normalized connector models.

NovelFull (https://novelfull.com) is the classic full-catalogue archive of
English-TRANSLATED JP/KR/CN light novels — the owner's "all light novels"
ask. Chosen after the whole named light-novel ladder failed at the VPS
egress (probed 2026-09-04 through production's TLS stack: LightNovelWorld
and LightNovelPub Cloudflare-challenged even via curl_cffi impersonation,
NovelHall 403 CF, ranobes.top 403 CF); NovelFull answers 200 on every view
with plain httpx.

Views used:

* Browse  -> ``GET /most-popular?page=N`` / ``/latest-release-novel?page=N``
  / ``/completed-novel?page=N`` (``<div class="row">`` cards, 20 per page,
  bootstrap pagination).
* Search  -> ``GET /search?keyword=<q>&page=N`` (same row markup).
* Detail  -> ``GET /<slug>.html`` (title, author, genres, status, rating,
  description, and ``data-novel-id`` — the handle for the chapter index).
* Chapters-> ``GET /ajax-chapter-option?novelId=<id>``: the COMPLETE chapter
  list (thousands of real titles) as one ``<select>`` — a single request,
  unlike the site's 50-per-page HTML index.
* Chapter -> ``GET /<slug>/<chapter-slug>.html``; text in
  ``<div id="chapter-content">`` with iframe/script ad slots interleaved and
  a "if you find any errors ... report chapter" footer line appended INSIDE
  the content div on every chapter.

Identity: ``series_key`` = the novel slug (``reincarnation-of-the-strongest-
sword-god``), ``chapter_key`` = the chapter path segment incl. ``.html``
(``chapter-1-starting-over.html``) — both verbatim site URL parts.
"""

from __future__ import annotations

import html as html_lib
import re

from connectors.ids import fully_unquote
from connectors.models import Chapter, NovelChapterText, PaginatedSeriesList, Series
from connectors.novel_text import (
    extract_paragraphs,
    hidden_classes_from_styles,
    normalize_line,
    slice_element,
)

SITE_BASE = "https://novelfull.com"
PAGE_SIZE = 20

# Verified live from the VPS 2026-09-04: "/completed" is a 404 — the site's
# own nav links "/completed-novel".
BROWSE_SORTS: dict[str, str] = {
    "": "most-popular",
    "default": "most-popular",
    "popular": "most-popular",
    "most-popular": "most-popular",
    "latest": "latest-release-novel",
    "latest-release": "latest-release-novel",
    "latest-release-novel": "latest-release-novel",
    "completed": "completed-novel",
    "completed-novel": "completed-novel",
    "hot": "hot-novel",
    "hot-novel": "hot-novel",
}

# One listing card per ``<div class="row">``: cover, title, author and latest
# chapter all live inside it. Splitting per row (rather than pairing two
# document-wide regex sweeps) keeps a malformed card from shifting every
# other card's cover onto the wrong novel.
_ROW_SPLIT_RE = re.compile(r'<div class="row">')
_NOVEL_HREF_RE = re.compile(
    r'<h3 class="truyen-title">.*?href="/([^"/]+)\.html"\s+title="([^"]*)"',
    re.DOTALL,
)
_COVER_RE = re.compile(r'<img src="([^"]+)"[^>]*class="cover"')
_AUTHOR_ROW_RE = re.compile(r'glyphicon-pencil"></span>([^<]+)<')
_LATEST_CHAPTER_RE = re.compile(r'<span class="chapter-text">\s*([^<]+?)\s*</span>')
_NEXT_PAGE_RE = re.compile(r'<li class="[^"]*next[^"]*">\s*<a\b')
_LAST_PAGE_RE = re.compile(r'\?page=(\d+)[^"]*"')
_TITLE_H3_RE = re.compile(r'<h3 class="title"[^>]*>([^<]+)</h3>')
_NOVEL_ID_RE = re.compile(r'data-novel-id="(\d+)"')
_INFO_AUTHOR_RE = re.compile(r'href="/author/[^"]*"[^>]*>([^<]+)<')
# The novel's OWN genres, scoped to the info block's "Genre:" row. An
# unscoped /genre/ sweep picks up the header nav, which links all ~36
# site-wide genres on every page.
_GENRE_ROW_RE = re.compile(r"<h3>Genre:</h3>(.*?)</div>", re.DOTALL)
_GENRE_RE = re.compile(r'href="/genre/[^"]*"[^>]*>([^<]+)<')
_STATUS_RE = re.compile(r'<h3>Status:</h3>\s*(?:<a[^>]*>)?([^<]+)')
_DESC_RE = re.compile(r'<div class="desc-text"[^>]*>(.*?)</div>', re.DOTALL)
_OPTION_RE = re.compile(r'<option value="/[^"/]+/([^"]+)"[^>]*>([^<]*)</option>')
_CHAPTER_TITLE_RE = re.compile(
    r'class="chapter-title"[^>]*title="([^"]*)"'
)
_CHAPTER_TEXT_SPAN_RE = re.compile(r'<span class="chapter-text">\s*([^<]+?)\s*<')
_CONTENT_OPEN = r'<div[^>]*id="chapter-content"[^>]*>'
# Titles seen live carry the number after an ASCII hyphen, an en dash, a
# colon, or a zero-width space ("Chapter - 1659", "Chapter​ 2528");
# ``normalize_line`` strips the zero-width forms before this runs.
_DASHES = "\\-‐‑‒–—―"  # ASCII hyphen plus U+2010..U+2015
_LEADING_NUMBER_RE = re.compile(
    rf"chapter[\s{_DASHES}:.,#]*(\d+(?:\.\d+)?)", re.IGNORECASE
)
_PUNCT_RE = re.compile(r"[^a-z0-9]+")

# NovelFull appends its own housekeeping footer INSIDE ``#chapter-content``
# on every chapter, so it survives the structural strip and the shared
# promo blacklist. Verified live on multiple chapters from the VPS.
_SITE_JUNK_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bif you find any errors\b",
        r"\bplease let us know\b.{0,20}\breport chapter\b",
        r"\bads?\s*popup\b.{0,40}\bads?\s*redirect\b",
    )
)


def is_site_junk_line(paragraph: str) -> bool:
    """True for NovelFull's own footer boilerplate, never for story prose."""
    normalized = normalize_line(paragraph)
    return any(p.search(normalized) for p in _SITE_JUNK_PATTERNS)


def normalize_series_key(value: str) -> str:
    """``/slug.html`` / a full URL / ``slug`` -> ``slug``."""
    cleaned = fully_unquote(value).strip().strip("/")
    if cleaned.startswith("http"):
        cleaned = cleaned.split("novelfull.com/", 1)[-1].strip("/")
    cleaned = cleaned.split("/", 1)[0]
    if cleaned.endswith(".html"):
        cleaned = cleaned[: -len(".html")]
    return cleaned


def normalize_chapter_key(value: str) -> str:
    cleaned = fully_unquote(value).strip().strip("/")
    return cleaned.rsplit("/", 1)[-1]


def series_path(series_key: str) -> str:
    return f"/{normalize_series_key(series_key)}.html"


def chapter_path(series_key: str, chapter_key: str) -> str:
    return f"/{normalize_series_key(series_key)}/{normalize_chapter_key(chapter_key)}"


def browse_path(sort: str | None) -> str:
    view = BROWSE_SORTS.get((sort or "").strip().lower(), "most-popular")
    return f"/{view}"


def chapter_number_from_title(title: str) -> float | None:
    """The "Chapter N" number a chapter title leads with, if it has one."""
    match = _LEADING_NUMBER_RE.search(normalize_line(title))
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _clean(text: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def _absolute(url: str) -> str:
    return url if url.startswith("http") else f"{SITE_BASE}{url}"


def _title_key(text: str) -> str:
    """Punctuation-insensitive comparison key for chapter titles.

    The header says "Chapter 1 - Starting Over" while the body repeats it as
    "Chapter 1: Starting Over"; only the punctuation differs.
    """
    return _PUNCT_RE.sub(" ", normalize_line(text).casefold()).strip()


def parse_novel_list(html_text: str, *, page: int) -> PaginatedSeriesList:
    """Parse a browse or search page's listing cards.

    One card per ``<div class="row">``; rows without a ``truyen-title`` link
    (the header's genre dropdown uses the same wrapper) are dropped.
    """
    items: list[Series] = []
    for block in _ROW_SPLIT_RE.split(html_text)[1:]:
        href = _NOVEL_HREF_RE.search(block)
        if not href:
            continue
        author = _AUTHOR_ROW_RE.search(block)
        cover = _COVER_RE.search(block)
        latest = _LATEST_CHAPTER_RE.search(block)
        items.append(
            Series(
                id=href.group(1),
                title=_clean(href.group(2)),
                author=_clean(author.group(1)) if author else None,
                cover_url=_absolute(cover.group(1)) if cover else None,
                latest_chapter=_clean(latest.group(1)) if latest else None,
            )
        )
    has_more = bool(_NEXT_PAGE_RE.search(html_text)) or any(
        int(p) > page for p in _LAST_PAGE_RE.findall(html_text)
    )
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=0,
        api_has_more=has_more,
    )


def parse_novel_page(html_text: str, series_key: str) -> Series | None:
    """Series metadata (the chapter list is a separate ajax fetch)."""
    series_key = normalize_series_key(series_key)
    title = _TITLE_H3_RE.search(html_text)
    if title is None:
        return None
    author = _INFO_AUTHOR_RE.search(html_text)
    status = _STATUS_RE.search(html_text)
    genre_row = _GENRE_ROW_RE.search(html_text)
    genres = (
        tuple(dict.fromkeys(_clean(g) for g in _GENRE_RE.findall(genre_row.group(1))))
        if genre_row
        else ()
    )
    cover = _COVER_RE.search(html_text) or re.search(
        r'<div class="book">\s*<img src="([^"]+)"', html_text
    )
    cover_url = _absolute(cover.group(1)) if cover else None
    description = None
    desc_match = _DESC_RE.search(html_text)
    if desc_match:
        description = "\n\n".join(extract_paragraphs(desc_match.group(1))) or None
    return Series(
        id=series_key,
        title=_clean(title.group(1)),
        description=description,
        cover_url=cover_url,
        author=_clean(author.group(1)) if author else None,
        status=_clean(status.group(1)).lower() if status else None,
        genres=genres,
    )


def parse_novel_id(html_text: str) -> str | None:
    match = _NOVEL_ID_RE.search(html_text)
    return match.group(1) if match else None


def parse_chapter_options(html_text: str, series_key: str) -> list[Chapter]:
    """The complete chapter list from ``/ajax-chapter-option``.

    Options arrive in reading order with real titles, so ``number`` is the
    1-based list POSITION — the same convention as the Royal Road and
    NovelArchive connectors, and the ordering the novel service's prev/next
    already walks.

    Deriving it from the title instead does not survive contact with the
    site (probed live from the VPS 2026-09-04 across the 12 most popular
    novels): 8 of 12 came back non-monotonic and 6 carried duplicate
    numbers. NovelFull repeats numbers outright ("Chapter 2304 - Starlit
    Gate" and "Chapter 2304 - Rank Nine Heavenly Immortal" in Martial God
    Asura), and it front-loads unnumbered entries — Emperor's Domination
    opens with "Side Story 1".."Side Story 7" ahead of Chapter 1, so any
    title-or-position scheme collides seven times over. The title's own
    number still reaches the reader: ``parse_chapter_page`` reads it off the
    chapter itself and the novel service prefers that over the list value.
    """
    series_key = normalize_series_key(series_key)
    return [
        Chapter(
            id=key,
            series_id=series_key,
            title=_clean(title),
            number=float(position),
            page_count=0,
        )
        for position, (key, title) in enumerate(
            _OPTION_RE.findall(html_text), start=1
        )
    ]


def parse_chapter_page(html_text: str) -> NovelChapterText | None:
    body = slice_element(html_text, _CONTENT_OPEN)
    if body is None:
        return None
    hidden = hidden_classes_from_styles(html_text)
    paragraphs = [
        p
        for p in extract_paragraphs(body, hidden_classes=hidden)
        if not is_site_junk_line(p)
    ]

    title_match = _CHAPTER_TITLE_RE.search(html_text) or _CHAPTER_TEXT_SPAN_RE.search(
        html_text
    )
    title = _clean(title_match.group(1)) if title_match else ""

    # The body opens with the bare chapter title repeated as a paragraph —
    # punctuated differently from the header ("Chapter 1 - Starting Over"
    # in the <h2>, "Chapter 1: Starting Over" in the body), so compare on a
    # punctuation-insensitive key.
    title_key = _title_key(title)
    while paragraphs and title_key and _title_key(paragraphs[0]) == title_key:
        paragraphs = paragraphs[1:]
    if not paragraphs:
        return None

    return NovelChapterText(
        title=title,
        paragraphs=tuple(paragraphs),
        chapter_number=chapter_number_from_title(title),
    )
