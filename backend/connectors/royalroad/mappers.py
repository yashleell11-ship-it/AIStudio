"""Map Royal Road HTML to normalized connector models.

Royal Road (https://www.royalroad.com) is the original-fiction site — clean,
fast, fully server-rendered, and the most reliable novel source reachable
from the VPS egress (probed 2026-09-04: browse/search/fiction/chapter all 200
through production's exact TLS stack; the big "NovelBin-class" aggregators
were NXDOMAIN or Cloudflare-challenged from there).

Views used:

* Browse   -> ``GET /fictions/<view>?page=N`` (``best-rated``, ``trending``,
  ``latest-updates``, ``active-popular``, ``complete``), 20 cards per page,
  ``fiction-list-item`` blocks.
* Search   -> ``GET /fictions/search?title=<q>&page=N`` (same card markup).
* Detail   -> ``GET /fiction/<ID>/<slug>``; the full chapter list is embedded
  as a ``window.chapters = [...]`` JSON array, so series metadata and the
  chapter list are ONE fetch.
* Chapter  -> ``GET /fiction/<ID>/<slug>/chapter/<CID>/<chslug>``; text lives
  in ``<div class="chapter-inner chapter-content">``. Royal Road hides
  anti-theft watermark sentences with per-chapter randomized CSS classes
  styled ``display: none`` in a head ``<style>`` block — the sanitizer reads
  those classes out of the page and drops the elements.

Identity (house law: opaque, stored raw, never parsed):

* ``series_key``  = ``"<ID>/<slug>"``            (e.g. ``21220/mother-of-learning``)
* ``chapter_key`` = ``"<CID>/<chslug>"``         (e.g. ``301778/1-good-morning-brother``)

Both deliberately contain a slash — they are exactly the tail of the site's
own URLs, so a key round-trips as ``/fiction/{series_key}`` and
``/fiction/{series_key}/chapter/{chapter_key}`` with no rebuilding.
"""

from __future__ import annotations

import html as html_lib
import json
import re

from connectors.ids import fully_unquote
from connectors.models import Chapter, NovelChapterText, PaginatedSeriesList, Series
from connectors.novel_text import (
    extract_paragraphs,
    hidden_classes_from_styles,
    slice_element,
)

SITE_BASE = "https://www.royalroad.com"
PAGE_SIZE = 20

#: Browse views exposed as sort modes; ``default`` maps to Best Rated.
BROWSE_VIEWS: dict[str, str] = {
    "": "best-rated",
    "default": "best-rated",
    "best-rated": "best-rated",
    "trending": "trending",
    "latest": "latest-updates",
    "latest-updates": "latest-updates",
    "popular": "active-popular",
    "active-popular": "active-popular",
    "complete": "complete",
}

# Browse renders items as class="fiction-list-item row", search as
# class="row fiction-list-item" — match the class anywhere in the attribute.
_ITEM_SPLIT_RE = re.compile(r'<div class="[^"]*fiction-list-item[^"]*">')
_FICTION_HREF_RE = re.compile(r'href="/fiction/(\d+/[^"/][^"]*)"')
_TITLE_RE = re.compile(
    r'<h2 class="fiction-title">\s*<a href="/fiction/[^"]+"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_COVER_RE = re.compile(r'<img[^>]+src="(https://[^"]+)"')
_TAG_RE = re.compile(r'class="[^"]*fiction-tag"[^>]*>([^<]+)<')
_STATUS_RE = re.compile(
    r">\s*(COMPLETED|ONGOING|HIATUS|STUB|DROPPED)\s*<", re.IGNORECASE
)
_CHAPTER_COUNT_RE = re.compile(r"([\d,]+)\s+Chapters")
_CHAPTER_LINK_RE = re.compile(r'href="/fiction/\d+/[^"]+/chapter/\d+/')
_NEXT_PAGE_RE = re.compile(r"<a data-page='(\d+)'[^>]*>Next\s")
_WINDOW_CHAPTERS_RE = re.compile(r"window\.chapters\s*=\s*(\[.*?\]);", re.DOTALL)
_FICTION_COVER_RE = re.compile(r'window\.fictionCover\s*=\s*"([^"]*)"')
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)
_AUTHOR_META_RE = re.compile(r'property="books:author" content="([^"]*)"')
_OG_IMAGE_RE = re.compile(r'property="og:image" content="([^"]*)"')
_DESCRIPTION_RE = re.compile(
    r'<div class="description">(.*?)</div>\s*</div>', re.DOTALL
)
_CHAPTER_CONTENT_OPEN = r'<div[^>]*class="[^"]*chapter-content[^"]*"[^>]*>'


def normalize_series_key(value: str) -> str:
    """``fiction/21220/slug`` / a full URL / ``21220/slug`` -> ``21220/slug``."""
    cleaned = fully_unquote(value).strip().strip("/")
    if cleaned.startswith("http"):
        cleaned = cleaned.split("royalroad.com/", 1)[-1].strip("/")
    if cleaned.startswith("fiction/"):
        cleaned = cleaned[len("fiction/") :]
    return cleaned


def normalize_chapter_key(value: str) -> str:
    """Accept ``<CID>/<slug>``, ``chapter/<CID>/<slug>`` or a chapter URL."""
    cleaned = fully_unquote(value).strip().strip("/")
    if "/chapter/" in cleaned:
        cleaned = cleaned.split("/chapter/", 1)[1].strip("/")
    elif cleaned.startswith("chapter/"):
        cleaned = cleaned[len("chapter/") :]
    return cleaned


def series_path(series_key: str) -> str:
    return f"/fiction/{normalize_series_key(series_key)}"


def chapter_path(series_key: str, chapter_key: str) -> str:
    return (
        f"/fiction/{normalize_series_key(series_key)}"
        f"/chapter/{normalize_chapter_key(chapter_key)}"
    )


def browse_path(sort: str | None) -> str:
    view = BROWSE_VIEWS.get((sort or "").strip().lower(), "best-rated")
    return f"/fictions/{view}"


def _clean(text: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_fiction_list(html_text: str, *, page: int) -> PaginatedSeriesList:
    """Parse a browse or search page's ``fiction-list-item`` cards."""
    items: list[Series] = []
    blocks = _ITEM_SPLIT_RE.split(html_text)[1:]
    for block in blocks:
        href = _FICTION_HREF_RE.search(block)
        title = _TITLE_RE.search(block)
        if not href or not title:
            continue
        cleaned_title = _clean(re.sub(r"<[^>]+>", " ", title.group(1)))
        cover = _COVER_RE.search(block)
        status = _STATUS_RE.search(block)
        count = _CHAPTER_COUNT_RE.search(block)
        chapter_count = int(count.group(1).replace(",", "")) if count else 0
        if chapter_count == 0:
            # Latest Updates cards carry recent chapter LINKS instead of an
            # "N Chapters" total — those links are a lower-bound count.
            chapter_count = len(_CHAPTER_LINK_RE.findall(block))
        # Obviously-broken rows never reach clients (house law): no title, an
        # explicit zero-chapter stub, or a card with no evidence of chapters
        # at all (markup drift) all get dropped.
        if not cleaned_title or chapter_count == 0:
            continue
        genres = tuple(_clean(t) for t in _TAG_RE.findall(block))
        items.append(
            Series(
                id=href.group(1),
                title=cleaned_title,
                chapter_count=chapter_count,
                cover_url=cover.group(1) if cover else None,
                status=_clean(status.group(1)).lower() if status else None,
                genres=genres,
            )
        )
    next_link = _NEXT_PAGE_RE.search(html_text)
    has_more = bool(next_link and int(next_link.group(1)) > page)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=0,
        api_has_more=has_more,
    )


def parse_fiction_page(
    html_text: str, series_key: str
) -> tuple[Series | None, list[Chapter]]:
    """Series metadata + the full chapter list from ONE fiction page."""
    series_key = normalize_series_key(series_key)
    title_match = _H1_RE.search(html_text)
    if title_match is None:
        return None, []
    title = _clean(re.sub(r"<[^>]+>", " ", title_match.group(1)))

    chapters: list[Chapter] = []
    chapters_match = _WINDOW_CHAPTERS_RE.search(html_text)
    if chapters_match:
        try:
            raw_chapters = json.loads(chapters_match.group(1))
        except ValueError:
            raw_chapters = []
        for entry in raw_chapters:
            url = str(entry.get("url") or "")
            if "/chapter/" not in url:
                continue
            order = entry.get("order")
            chapters.append(
                Chapter(
                    id=url.split("/chapter/", 1)[1].strip("/"),
                    series_id=series_key,
                    title=_clean(str(entry.get("title") or "")),
                    number=float(order) + 1.0 if order is not None else None,
                    page_count=0,
                    release_date=str(entry.get("date") or "") or None,
                )
            )

    author = _AUTHOR_META_RE.search(html_text)
    cover = _FICTION_COVER_RE.search(html_text) or _OG_IMAGE_RE.search(html_text)
    status = _STATUS_RE.search(html_text)
    genres = tuple(
        dict.fromkeys(_clean(t) for t in _TAG_RE.findall(html_text))
    )

    description = None
    description_match = _DESCRIPTION_RE.search(html_text)
    if description_match:
        description = (
            "\n\n".join(extract_paragraphs(description_match.group(1))) or None
        )

    series = Series(
        id=series_key,
        title=title,
        chapter_count=len(chapters),
        description=description,
        cover_url=cover.group(1) if cover and cover.group(1) else None,
        author=_clean(author.group(1)) if author else None,
        status=_clean(status.group(1)).lower() if status else None,
        genres=genres,
        latest_chapter=chapters[-1].title if chapters else None,
    )
    return series, chapters


def parse_chapter_page(html_text: str) -> NovelChapterText | None:
    """Sanitized plain-text paragraphs for one chapter page.

    The watermark defense: Royal Road's stolen-content sentences sit in the
    body under randomized classes that a head ``<style>`` block hides —
    ``hidden_classes_from_styles`` reads the whole page (the rule is NOT
    inside the content div), and the extractor drops the elements.
    """
    body = slice_element(html_text, _CHAPTER_CONTENT_OPEN)
    if body is None:
        return None
    hidden = hidden_classes_from_styles(html_text)
    paragraphs = extract_paragraphs(body, hidden_classes=hidden)
    if not paragraphs:
        return None

    title_match = _H1_RE.search(html_text)
    title = (
        _clean(re.sub(r"<[^>]+>", " ", title_match.group(1)))
        if title_match
        else ""
    )
    return NovelChapterText(title=title, paragraphs=tuple(paragraphs))
