"""Map FreeWebNovel HTML to normalized connector models.

FreeWebNovel (https://freewebnovel.com) is the big "archive" aggregator of
English-translated webnovels and light novels. Probed from the VPS
(production egress/TLS, 2026-09-04): browse, search, novel and chapter pages
all answer 200 with plain httpx.

Views used:

* Browse  -> ``GET /sort/latest-release[/N]`` and ``/sort/most-popular[/N]``
  (``li-row`` cards, 20 per page, ``jump-pc`` pagination).
* Search  -> ``GET /search?keyword=<q>[&page=N]`` (the site's form is a POST
  that 303s straight to this GET; verified paginated from the VPS — page
  links carry ``page=N`` query params instead of the ``/N`` path style).
* Detail  -> ``GET /novel/<slug>``: metadata, the FIRST 40 chapters with real
  titles (``#idData``), and the newest chapters (``ul-list5``). The full
  chapter index is NOT server-addressable (the pager is JS-driven), but
  chapter URLs are uniformly ``/novel/<slug>/chapter-<n>``, so the list is
  synthesized: real titles where the page shows them, ``Chapter n``
  otherwise, from 1 up to the newest chapter number seen on the page.
* Chapter -> ``GET /novel/<slug>/<chapter-key>``; text in ``<div id="article">``
  with ad ``<div>``/``<script>`` slots interleaved between paragraphs (the
  sanitizer strips them structurally, plus the promo-line blacklist).

Identity: ``series_key`` = the novel slug (``shadow-slave``), ``chapter_key``
= the chapter path segment (``chapter-1``) — both verbatim site URL parts.
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

SITE_BASE = "https://freewebnovel.com"
PAGE_SIZE = 20

BROWSE_SORTS: dict[str, str] = {
    "": "latest-release",
    "default": "latest-release",
    "latest": "latest-release",
    "latest-release": "latest-release",
    "popular": "most-popular",
    "most-popular": "most-popular",
}

_ITEM_SPLIT_RE = re.compile(r'<div class="li-row">')
_NOVEL_HREF_RE = re.compile(r'href="/novel/([^"/]+)"')
_TITLE_RE = re.compile(
    r'<h3 class="tit">\s*<a href="/novel/[^"]+"[^>]*title="([^"]*)"'
)
_IMG_RE = re.compile(r'<img src="([^"]+)"')
_GENRE_RE = re.compile(r'href="/genre/([^"]+)"')
_LATEST_CHAPTER_RE = re.compile(r'href="/novel/[^"/]+/(chapter-[\d.]+)"')
_CURRENT_PAGE_RE = re.compile(r"<strong>(\d+)</strong>")
# Path-style pager links (/sort/latest-release/3) and query-style ones
# (/search?keyword=x&page=3, sometimes &amp;-escaped).
_PAGE_LINK_RE = re.compile(r'href="/sort/[^"?]*?/(\d+)"[^>]*>')
_PAGE_QUERY_RE = re.compile(r'href="/search\?[^"]*?page=(\d+)"')
_H1_TIT_RE = re.compile(r'<h1 class="tit">(?:<a[^>]*>)?([^<]+)')
_OG_IMAGE_RE = re.compile(r'property="og:image"\s+content="([^"]+)"')
# The novel page's own genre row (the header nav also links every /genre/
# on the site, so genre extraction must stay inside this block).
_GENRE_BLOCK_RE = re.compile(
    r'title="Genre"></span>\s*<div class="right">(.*?)</div>', re.DOTALL
)
_AUTHOR_RE = re.compile(r'href="/author/[^"]*"[^>]*title="([^"]*)"')
_AUTHOR_TEXT_RE = re.compile(r'href="/author/[^"]*"[^>]*>([^<]+)<')
_STATUS_RE = re.compile(r'title="(?:Latest Release|Completed) Novels?">([^<]+)<')
_DESC_INNER_RE = re.compile(r'<div class="inner">(.*?)</div>', re.DOTALL)
_CHAPTER_LINK_RE = re.compile(
    r'href="/novel/[^"/]+/(chapter-[\d.]+)"\s+title="([^"]*)"'
)
_CHAPTER_NUM_RE = re.compile(r"chapter-([\d.]+)$")
_SPAN_CHAPTER_RE = re.compile(r'<span class="chapter">([^<]+)</span>')
_ARTICLE_OPEN = r'<div[^>]*id="article"[^>]*>'


def normalize_series_key(value: str) -> str:
    """``novel/shadow-slave`` / a full URL / ``shadow-slave`` -> ``shadow-slave``."""
    cleaned = fully_unquote(value).strip().strip("/")
    if cleaned.startswith("http"):
        cleaned = cleaned.split("freewebnovel.com/", 1)[-1].strip("/")
    if cleaned.startswith("novel/"):
        cleaned = cleaned[len("novel/") :]
    return cleaned.split("/", 1)[0]


def normalize_chapter_key(value: str) -> str:
    cleaned = fully_unquote(value).strip().strip("/")
    return cleaned.rsplit("/", 1)[-1]


def series_path(series_key: str) -> str:
    return f"/novel/{normalize_series_key(series_key)}"


def chapter_path(series_key: str, chapter_key: str) -> str:
    return f"/novel/{normalize_series_key(series_key)}/{normalize_chapter_key(chapter_key)}"


def browse_path(sort: str | None, page: int) -> str:
    view = BROWSE_SORTS.get((sort or "").strip().lower(), "latest-release")
    if page <= 1:
        return f"/sort/{view}"
    return f"/sort/{view}/{page}"


def chapter_number_from_key(chapter_key: str) -> float | None:
    match = _CHAPTER_NUM_RE.search(normalize_chapter_key(chapter_key))
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _clean(text: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def _parse_cards(html_text: str) -> list[Series]:
    items: list[Series] = []
    seen: set[str] = set()
    for block in _ITEM_SPLIT_RE.split(html_text)[1:]:
        href = _NOVEL_HREF_RE.search(block)
        title = _TITLE_RE.search(block)
        if not href or not title or href.group(1) in seen:
            continue
        seen.add(href.group(1))
        cover = _IMG_RE.search(block)
        cover_url = None
        if cover:
            src = cover.group(1)
            cover_url = src if src.startswith("http") else f"{SITE_BASE}{src}"
        genres = tuple(
            dict.fromkeys(_clean(g) for g in _GENRE_RE.findall(block))
        )
        latest = _LATEST_CHAPTER_RE.search(block)
        items.append(
            Series(
                id=href.group(1),
                title=_clean(title.group(1)),
                cover_url=cover_url,
                genres=genres,
                latest_chapter=latest.group(1) if latest else None,
            )
        )
    return items


def _has_more(html_text: str, page: int) -> bool:
    current = _CURRENT_PAGE_RE.search(html_text)
    current_page = int(current.group(1)) if current else page
    linked = [int(p) for p in _PAGE_LINK_RE.findall(html_text)]
    linked += [int(p) for p in _PAGE_QUERY_RE.findall(html_text)]
    return any(p > current_page for p in linked)


def parse_browse_page(html_text: str, *, page: int) -> PaginatedSeriesList:
    return PaginatedSeriesList(
        items=_parse_cards(html_text),
        page=page,
        page_size=PAGE_SIZE,
        total=0,
        api_has_more=_has_more(html_text, page),
    )


def search_params(query: str, page: int) -> dict[str, str]:
    params = {"keyword": query}
    if page > 1:
        params["page"] = str(page)
    return params


def parse_search_results(html_text: str, *, page: int) -> PaginatedSeriesList:
    return PaginatedSeriesList(
        items=_parse_cards(html_text),
        page=page,
        page_size=PAGE_SIZE,
        total=0,
        api_has_more=_has_more(html_text, page),
    )


def parse_novel_page(
    html_text: str, series_key: str
) -> tuple[Series | None, list[Chapter]]:
    """Series metadata + the synthesized full chapter list (see module doc)."""
    series_key = normalize_series_key(series_key)
    title = _H1_TIT_RE.search(html_text)
    if title is None:
        return None, []

    # Real titles where the page shows them (first 40 + the newest strip).
    titles: dict[str, str] = {}
    latest_number = 0.0
    for key, chapter_title in _CHAPTER_LINK_RE.findall(html_text):
        titles.setdefault(key, _clean(chapter_title))
        number = chapter_number_from_key(key)
        if number is not None and number > latest_number:
            latest_number = number

    chapters: list[Chapter] = []
    for n in range(1, int(latest_number) + 1):
        key = f"chapter-{n}"
        chapters.append(
            Chapter(
                id=key,
                series_id=series_key,
                title=titles.get(key, f"Chapter {n}"),
                number=float(n),
                page_count=0,
            )
        )

    author = _AUTHOR_RE.search(html_text) or _AUTHOR_TEXT_RE.search(html_text)
    status = _STATUS_RE.search(html_text)

    # og:image is the cover; the first <img> on the page is the site logo.
    cover = _OG_IMAGE_RE.search(html_text)
    cover_url = None
    if cover:
        src = cover.group(1)
        cover_url = src if src.startswith("http") else f"{SITE_BASE}{src}"

    description = None
    desc_match = _DESC_INNER_RE.search(html_text)
    if desc_match:
        description = "\n\n".join(extract_paragraphs(desc_match.group(1))) or None

    # Only the info block's own genre row — the page header links EVERY genre.
    genre_block = _GENRE_BLOCK_RE.search(html_text)
    genres = tuple(
        dict.fromkeys(
            _clean(g)
            for g in _GENRE_RE.findall(genre_block.group(1) if genre_block else "")
        )
    )

    series = Series(
        id=series_key,
        title=_clean(title.group(1)),
        chapter_count=len(chapters),
        description=description,
        cover_url=cover_url,
        author=_clean(author.group(1)) if author else None,
        status=_clean(status.group(1)).lower() if status else None,
        genres=genres,
        latest_chapter=chapters[-1].title if chapters else None,
    )
    return series, chapters


def parse_chapter_page(html_text: str, chapter_key: str) -> NovelChapterText | None:
    body = slice_element(html_text, _ARTICLE_OPEN)
    if body is None:
        return None
    hidden = hidden_classes_from_styles(html_text)
    paragraphs = extract_paragraphs(body, hidden_classes=hidden)

    title_match = _SPAN_CHAPTER_RE.search(html_text)
    title = _clean(title_match.group(1)) if title_match else ""

    # The article body leads with an <h4> duplicating the chapter title —
    # noise for a reader and for TTS, so drop exact leading duplicates.
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
        chapter_number=chapter_number_from_key(chapter_key),
    )
