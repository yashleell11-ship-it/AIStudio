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
  (``truyen-title`` rows, 20 per page, bootstrap pagination).
* Search  -> ``GET /search?keyword=<q>&page=N`` (same row markup).
* Detail  -> ``GET /<slug>.html`` (title, author, genres, status, rating,
  description, and ``data-novel-id`` — the handle for the chapter index).
* Chapters-> ``GET /ajax-chapter-option?novelId=<id>``: the COMPLETE chapter
  list (thousands of real titles) as one ``<select>`` — a single request,
  unlike the site's 50-per-page HTML index.
* Chapter -> ``GET /<slug>/<chapter-slug>.html``; text in
  ``<div id="chapter-content">`` with iframe/script ad slots interleaved.

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

BROWSE_SORTS: dict[str, str] = {
    "": "most-popular",
    "default": "most-popular",
    "popular": "most-popular",
    "most-popular": "most-popular",
    "latest": "latest-release-novel",
    "latest-release": "latest-release-novel",
    "completed": "completed",
}

_ROW_SPLIT_RE = re.compile(r'<h3 class="truyen-title">')
_NOVEL_HREF_RE = re.compile(r'href="/([^"/]+)\.html"\s+title="([^"]*)"')
_COVER_RE = re.compile(r'<img src="([^"]+)"[^>]*class="cover"')
_AUTHOR_ROW_RE = re.compile(r'glyphicon-pencil"></span>([^<]+)<')
_NEXT_PAGE_RE = re.compile(r'<li class="[^"]*next[^"]*">\s*<a\b')
_LAST_PAGE_RE = re.compile(r'\?page=(\d+)[^"]*"')
_TITLE_H3_RE = re.compile(r'<h3 class="title"[^>]*>([^<]+)</h3>')
_NOVEL_ID_RE = re.compile(r'data-novel-id="(\d+)"')
_INFO_AUTHOR_RE = re.compile(r'href="/author/[^"]*"[^>]*>([^<]+)<')
_GENRE_RE = re.compile(r'href="/genre/[^"]*"[^>]*>([^<]+)<')
_STATUS_RE = re.compile(r'<h3>Status:</h3>\s*(?:<a[^>]*>)?([^<]+)')
_DESC_RE = re.compile(r'<div class="desc-text"[^>]*>(.*?)</div>', re.DOTALL)
_OPTION_RE = re.compile(r'<option value="/[^"/]+/([^"]+)"[^>]*>([^<]*)</option>')
_CHAPTER_TITLE_RE = re.compile(
    r'class="chapter-title"[^>]*title="([^"]*)"'
)
_CHAPTER_TEXT_SPAN_RE = re.compile(r'<span class="chapter-text">\s*([^<]+?)\s*<')
_CONTENT_OPEN = r'<div[^>]*id="chapter-content"[^>]*>'
_LEADING_NUMBER_RE = re.compile(r"chapter[\s\-]*([\d]+(?:\.\d+)?)", re.IGNORECASE)


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
    match = _LEADING_NUMBER_RE.search(title)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _clean(text: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_novel_list(html_text: str, *, page: int) -> PaginatedSeriesList:
    """Parse a browse or search page's ``truyen-title`` rows."""
    items: list[Series] = []
    for block in _ROW_SPLIT_RE.split(html_text)[1:]:
        href = _NOVEL_HREF_RE.search(block)
        if not href:
            continue
        author = _AUTHOR_ROW_RE.search(block)
        items.append(
            Series(
                id=href.group(1),
                title=_clean(href.group(2)),
                author=_clean(author.group(1)) if author else None,
            )
        )
    # Cover images sit in a sibling column before the title split; recover
    # them by pairing in document order.
    covers = _COVER_RE.findall(html_text)
    if len(covers) == len(items):
        items = [
            Series(
                id=item.id,
                title=item.title,
                author=item.author,
                cover_url=(
                    cover if cover.startswith("http") else f"{SITE_BASE}{cover}"
                ),
            )
            for item, cover in zip(items, covers)
        ]
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
    genres = tuple(dict.fromkeys(_clean(g) for g in _GENRE_RE.findall(html_text)))
    cover = _COVER_RE.search(html_text) or re.search(
        r'<div class="book">\s*<img src="([^"]+)"', html_text
    )
    cover_url = None
    if cover:
        src = cover.group(1)
        cover_url = src if src.startswith("http") else f"{SITE_BASE}{src}"
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

    Options arrive in reading order with real titles. ``number`` is parsed
    from the title where it leads with "Chapter N" and falls back to the
    1-based position — NovelFull afterwords/side stories carry no number.
    """
    series_key = normalize_series_key(series_key)
    chapters: list[Chapter] = []
    for position, (key, title) in enumerate(_OPTION_RE.findall(html_text), start=1):
        cleaned_title = _clean(title)
        chapters.append(
            Chapter(
                id=key,
                series_id=series_key,
                title=cleaned_title,
                number=chapter_number_from_title(cleaned_title)
                or float(position),
                page_count=0,
            )
        )
    return chapters


def parse_chapter_page(html_text: str) -> NovelChapterText | None:
    body = slice_element(html_text, _CONTENT_OPEN)
    if body is None:
        return None
    hidden = hidden_classes_from_styles(html_text)
    paragraphs = extract_paragraphs(body, hidden_classes=hidden)

    title_match = _CHAPTER_TITLE_RE.search(html_text) or _CHAPTER_TEXT_SPAN_RE.search(
        html_text
    )
    title = _clean(title_match.group(1)) if title_match else ""

    # The body opens with the bare chapter title repeated as a paragraph.
    while paragraphs and title and (
        normalize_line(paragraphs[0]).casefold()
        == normalize_line(title).casefold()
    ):
        paragraphs = paragraphs[1:]
    if not paragraphs:
        return None

    return NovelChapterText(
        title=title,
        paragraphs=tuple(paragraphs),
        chapter_number=chapter_number_from_title(title),
    )
