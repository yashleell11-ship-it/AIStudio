"""Map Elf Toon (Themesia MangaReader) HTML to normalized connector models.

Elftoon.com is WordPress Themesia MangaReader — not Madara. Listing cards use
``div.bs > div.bsx``, chapters live at flat ``/{slug}-chapter-N/`` URLs, and
reader images are embedded in ``ts_reader.run({...})``. Newer chapters may be
coin-locked (``#lockedChapterModal``); those are skipped.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urlparse

from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SITE_BASE = "https://elftoon.com"
PAGE_SIZE = 20
#: WordPress core search returns 10 posts per page regardless of the theme's
#: own archive page size (measured from the VPS: ``?s=demon`` pages hold
#: 10/10/9). Reporting PAGE_SIZE here would misstate ``total`` to the client.
SEARCH_PAGE_SIZE = 10

# Themesia /manga/ filter form ``order`` values.
SORT_TO_ORDER: dict[str, str] = {
    "default": "update",
    "latest": "latest",
    "popular": "popular",
    "rating": "rating",
}

_BSX_CARD_RE = re.compile(
    r'<div class="bsx">\s*'
    r'<a href="(?:https?://[^"]+)?/manga/([^"/]+)/"[^>]*title="([^"]*)"',
    re.I,
)
_CARD_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
_IMG_DATA_SRC_RE = re.compile(r'data-src="\s*([^"]+?)\s*"', re.I)
_IMG_SRC_RE = re.compile(r'(?<!-)\bsrc="\s*([^"]+?)\s*"', re.I)

_CHAPTER_LI_RE = re.compile(
    r'<li[^>]*data-num="([^"]*)"[^>]*>(.*?)</li>',
    re.S | re.I,
)
_FREE_CHAPTER_HREF_RE = re.compile(
    r'href="(https?://[^"]+/(?:[^"/]+-)?chapter-[^"/]+/?)"',
    re.I,
)
_CHAPTER_SLUG_RE = re.compile(
    r"/(?P<slug>[^/]+-chapter-(?P<num>\d+(?:\.\d+)?))/?$",
    re.I,
)

_TS_READER_RE = re.compile(r"ts_reader\.run\((\{.*?\})\);", re.S)

_NEXT_PAGE_RE = re.compile(r'[?&]page=(\d+)', re.I)
# WordPress core's search paginator (``<div class="pagination">``), distinct
# from the Themesia archive's ``hpage`` Prev/Next block.
_PAGINATION_BLOCK_RE = re.compile(r'<div class="pagination">(.*?)</div>', re.S | re.I)
_PAGE_NUMBER_LINK_RE = re.compile(r'class="[^"]*page-numbers"[^>]*/page/(\d+)/', re.I)
_CURRENT_PAGE_RE = re.compile(r'class="page-numbers current"[^>]*>\s*(\d+)', re.I)
_NEXT_PAGE_LINK_RE = re.compile(r'class="next page-numbers"', re.I)
_HPAGE_NEXT_RE = re.compile(
    r'<div class="hpage">[^<]*<a[^>]+href="[^"]*page=(\d+)[^"]*"[^>]*class="r"',
    re.I,
)


def normalize_sort(sort: str | None) -> str:
    if not sort or sort == "default":
        return SORT_TO_ORDER["default"]
    return SORT_TO_ORDER.get(sort, sort)


def listing_path() -> str:
    return "/manga/"


def listing_params(*, page: int, sort: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"order": normalize_sort(sort)}
    if page > 1:
        params["page"] = page
    return params


def search_params(query: str) -> dict[str, Any]:
    """Query string for a WordPress search. Deliberately carries no page.

    ``?page=N`` is WordPress's *within-a-single-post* paginator; on a search
    query it is silently dropped and every request answers page 1. The page
    number belongs in the path -- see :func:`search_path`.
    """
    return {"s": query.strip(), "post_type": "wp-manga"}


def search_path(page: int) -> str:
    """Path for search page ``page``; WordPress paginates search by path."""
    if page <= 1:
        return "/"
    return f"/page/{page}/"


def series_id_to_path(series_id: str) -> str:
    return f"/manga/{series_id.strip().strip('/')}/"


def make_chapter_id(series_id: str, chapter_slug: str) -> str:
    return f"{series_id.strip()}/{chapter_slug.strip().strip('/')}"


def parse_chapter_id(chapter_id: str) -> tuple[str, str] | None:
    normalized = chapter_id.strip().strip("/")
    if "/" not in normalized:
        return None
    series_id, _, slug = normalized.partition("/")
    if not series_id or not slug or "/" in slug:
        return None
    return series_id, slug


def chapter_id_to_path(chapter_id: str) -> str | None:
    """Map ``{series}/{series}-chapter-N`` (or bare chapter slug) to reader path."""
    parsed = parse_chapter_id(chapter_id)
    if parsed is not None:
        _series_id, slug = parsed
        return f"/{slug.strip().strip('/')}/"
    value = chapter_id.strip().strip("/")
    if "-chapter-" in value and "/" not in value:
        return f"/{value}/"
    return None


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def _clean_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def _extract_image_url(img_tag: str) -> str | None:
    data_src = _IMG_DATA_SRC_RE.search(img_tag)
    if data_src:
        url = data_src.group(1).strip()
        if url and not url.startswith("data:"):
            return url
    src = _IMG_SRC_RE.search(img_tag)
    if src:
        url = src.group(1).strip()
        if url and not url.startswith("data:"):
            return url
    return None


def _cover_from_card(segment: str) -> str | None:
    for img_tag in _CARD_IMG_TAG_RE.findall(segment):
        url = _extract_image_url(img_tag)
        if url:
            return url
    return None


def parse_series_cards(html_text: str) -> list[Series]:
    """Parse Themesia ``bsx`` cards from browse/search HTML."""
    items: list[Series] = []
    seen: set[str] = set()
    # Prefer the main listupd block so sidebar "Popular" does not pollute results.
    list_match = re.search(
        r'<div class="listupd">(.*?)(?:<div class="hpage">|<div class="pagination">|$)',
        html_text,
        re.S | re.I,
    )
    scope = list_match.group(1) if list_match else html_text

    for match in _BSX_CARD_RE.finditer(scope):
        series_id = match.group(1).strip()
        if not series_id or series_id in seen:
            continue
        # Skip non-series paths under /manga/
        if series_id in {"list-mode", "page"}:
            continue
        seen.add(series_id)
        title = _clean_text(html.unescape(match.group(2)))
        # Card HTML for cover: from this match to the next bsx / end of small window
        start = match.start()
        end = min(len(scope), start + 1200)
        cover = _cover_from_card(scope[start:end])
        items.append(
            Series(
                id=series_id,
                title=title or series_id.replace("-", " "),
                cover_url=cover,
                canonical_path=series_id_to_path(series_id),
            )
        )
    return items


def _extract_total_pages(html_text: str) -> int:
    pages = [int(value) for value in _NEXT_PAGE_RE.findall(html_text)]
    if pages:
        return max(pages)
    if _HPAGE_NEXT_RE.search(html_text) or 'class="r"' in html_text and "page=" in html_text:
        return 2
    return 1


def parse_series_list(
    html_text: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html_text)
    total_pages = _extract_total_pages(html_text)
    # hpage only exposes "Next" — if we see a next link, assume at least page+1.
    has_next = bool(
        re.search(rf'[?&]page={page + 1}\b', html_text, re.I)
        or re.search(
            rf'<div class="hpage">[^<]*<a[^>]+href="[^"]*page={page + 1}',
            html_text,
            re.I,
        )
    )
    if has_next and total_pages <= page:
        total_pages = page + 1
    total = total_pages * page_size
    if page >= total_pages and not has_next:
        total = (page - 1) * page_size + len(items)
        has_more = False
    else:
        has_more = page < total_pages or has_next
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def parse_search_results(
    html_text: str,
    *,
    page: int,
    page_size: int = SEARCH_PAGE_SIZE,
) -> PaginatedSeriesList:
    """Parse a WordPress search result page.

    Search results come from WP core, not the Themesia archive template, so
    they carry a ``page-numbers`` block instead of the theme's ``hpage``
    Prev/Next pair -- which is why this cannot reuse
    :func:`parse_series_list`, whose "next page" test looks for a ``page=``
    query parameter that a search page never emits.
    """
    items = parse_series_cards(html_text)
    block = _PAGINATION_BLOCK_RE.search(html_text)
    nav = block.group(1) if block else ""
    numbers = [int(value) for value in _PAGE_NUMBER_LINK_RE.findall(nav)]
    current = _CURRENT_PAGE_RE.search(nav)
    numbers.append(int(current.group(1)) if current else page)
    has_more = bool(_NEXT_PAGE_LINK_RE.search(nav))
    if has_more:
        total = max(numbers) * page_size
    else:
        # Last page: the only exact count we ever get, since WP never states
        # a result total. Anything beyond this is a 404 (see the connector).
        total = (page - 1) * page_size + len(items)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def parse_series_detail(html_text: str, series_id: str) -> Series | None:
    title_match = re.search(
        r'<h1 class="entry-title"[^>]*>\s*([^<]+)',
        html_text,
        re.I,
    )
    title = _clean_text(title_match.group(1)) if title_match else ""
    if not title:
        og_title = re.search(
            r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
            html_text,
            re.I,
        )
        if og_title is None:
            return None
        title = _clean_text(og_title.group(1))
        # og:title often appends " - Elf Toon"
        title = re.sub(r"\s*[-|].*$", "", title).strip() or title
    if not title:
        return None

    cover_match = re.search(
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        html_text,
        re.I,
    )
    cover_url = cover_match.group(1).strip() if cover_match else None

    status_match = re.search(
        r'<div class="imptdt">\s*Status\s*<i>\s*([^<]+)',
        html_text,
        re.I,
    )
    status = _clean_text(status_match.group(1)).lower() if status_match else None

    author_match = re.search(
        r'itemprop="author"[^>]*>.*?<i[^>]*itemprop="name"[^>]*>\s*([^<]+)',
        html_text,
        re.S | re.I,
    )
    author = _clean_text(author_match.group(1)) if author_match else None

    mgen = re.search(r'<span class="mgen">(.*?)</span>', html_text, re.S | re.I)
    genres = (
        tuple(
            _clean_text(name)
            for name in re.findall(r"<a[^>]*>([^<]+)</a>", mgen.group(1), re.I)
        )
        if mgen
        else ()
    )

    desc_match = re.search(
        r'itemprop="description"[^>]*>(.*?)</div>',
        html_text,
        re.S | re.I,
    )
    description = None
    if desc_match:
        description = _clean_text(re.sub(r"<[^>]+>", " ", desc_match.group(1))) or None

    return Series(
        id=series_id,
        title=title,
        cover_url=cover_url,
        canonical_path=series_id_to_path(series_id),
        description=description,
        author=author,
        status=status,
        genres=genres,
    )


def _chapter_number_from_slug(slug: str, data_num: str) -> float | None:
    if data_num.strip():
        try:
            return float(data_num.strip())
        except ValueError:
            pass
    match = re.search(r"chapter-(\d+(?:\.\d+)?)", slug, re.I)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def parse_chapters(html_text: str, series_id: str) -> list[Chapter]:
    """Parse free (unlocked) chapters; skip coin-locked modal entries."""
    chapters: list[Chapter] = []
    seen: set[str] = set()
    list_match = re.search(
        r'id="chapterlist"[^>]*>(.*?)</ul>',
        html_text,
        re.S | re.I,
    )
    scope = list_match.group(1) if list_match else html_text

    for data_num, body in _CHAPTER_LI_RE.findall(scope):
        if "lockedChapterModal" in body:
            continue
        href_match = _FREE_CHAPTER_HREF_RE.search(body)
        if href_match is None:
            continue
        href = href_match.group(1)
        path = urlparse(href).path.rstrip("/")
        slug_match = _CHAPTER_SLUG_RE.search(path + "/")
        if slug_match is None:
            # Fallback: last path segment
            slug = path.rsplit("/", 1)[-1]
        else:
            slug = slug_match.group("slug")
        if not slug or slug in seen:
            continue
        # Only accept chapters belonging to this series
        if not slug.startswith(f"{series_id}-chapter-") and series_id not in slug:
            # Some titles may normalize differently; require series_id prefix
            if not slug.startswith(series_id):
                continue
        seen.add(slug)
        title_match = re.search(
            r'<span class="chapternum">\s*([^<]+)',
            body,
            re.I,
        )
        raw_title = _clean_text(title_match.group(1)) if title_match else slug
        title = normalize_chapter_title(raw_title) or raw_title
        number = _chapter_number_from_slug(slug, data_num)
        date_match = re.search(
            r'<span class="chapterdate">\s*([^<]+)',
            body,
            re.I,
        )
        release_date = _clean_text(date_match.group(1)) if date_match else None
        chapters.append(
            Chapter(
                id=make_chapter_id(series_id, slug),
                series_id=series_id,
                title=title,
                number=number,
                page_count=0,
                release_date=release_date,
            )
        )

    chapters.sort(
        key=lambda chapter: (
            chapter.number if chapter.number is not None else 0.0,
            chapter.id,
        )
    )
    return chapters


def parse_chapter_pages(html_text: str, chapter_id: str) -> list[Page]:
    """Extract reader images from ``ts_reader.run`` JSON payload."""
    run = _TS_READER_RE.search(html_text)
    if run is None:
        return []
    try:
        payload = json.loads(run.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        return []
    urls: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        images = source.get("images")
        if isinstance(images, list) and images:
            urls = [str(item).strip() for item in images if str(item).strip()]
            break
    pages: list[Page] = []
    for index, url in enumerate(urls, start=1):
        if url.startswith("data:"):
            continue
        pages.append(
            Page(
                id=make_page_id(chapter_id, index),
                chapter_id=chapter_id,
                number=index,
                remote_url=url,
            )
        )
    return pages
