"""Map MangaPill HTML pages to normalized connector models.

Endpoint map (verified from the VPS 2026-09-04, production egress):

* ``/search?q=&type=manga&status=&page=N`` -- paginated catalog, 50 cards/page.
  At least one of ``q``/``type``/``status``/``genre`` must be non-empty: an
  all-blank query renders the form with zero results, which is why the
  "All Manga" mode pins ``type=manga`` rather than sending an empty filter.
* ``/search?q=<terms>&page=N``            -- search, same card markup.
* ``/search?genre=<Genre>&page=N``        -- genre browse, same card markup.
* ``/chapters``                           -- the 120 most recently added
  chapters. Single page: ``?page=2`` serves byte-identical content, so this
  view is fetched once and sliced locally (see ``slice_latest``).
* ``/manga/<id>/<slug>``                  -- series detail. Carries the FULL
  chapter list inline, so detail + chapters cost exactly one request.
* ``/chapters/<id>-<num>/<slug>``         -- reader page. Carries every page
  image URL inline with ``width``/``height``, so a chapter costs exactly one
  request and a page image costs zero extra.

Identity keys are the site's own path tails and contain a slash; they are
opaque strings, stored and passed raw (house law).
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://mangapill.com"

#: MangaPill renders exactly 50 cards per catalog/search page.
PAGE_SIZE = 50

#: Every cover AND every page image is served from this CDN, which enforces
#: hotlink protection -- see ``MangaPillConnector.image_fetch_headers``.
IMAGE_CDN_HOST = "cdn.readdetectiveconan.com"

#: Separates the chapter key from the 1-based page index in a page id. The
#: chapter key is a URL path tail (``<id>-<num>/<slug>``); slugs are lowercase
#: alphanumerics, dots and dashes, so a colon never occurs inside one and
#: ``rpartition(":")`` splits unambiguously.
PAGE_ID_SEPARATOR = ":"


# --- markup ----------------------------------------------------------------

#: A catalog/search/genre result card. The cover is lazy-loaded (``data-src``,
#: never ``src``) and the title sits in the card's second anchor.
CARD_RE = re.compile(
    r'<a href="/manga/([^"]+)"[^>]*class="relative block">\s*'
    r'<figure[^>]*>\s*<img[^>]*?data-src="([^"]*)"[^>]*>\s*</figure>\s*</a>'
    r'.*?<div class="mt-3 font-black[^"]*">([^<]*)</div>',
    re.S,
)

#: A card on ``/chapters``: cover, "#<chapter>", then the series link + title.
LATEST_CARD_RE = re.compile(
    r'<figure[^>]*>\s*<img[^>]*?data-src="([^"]*)"[^>]*>\s*</figure>\s*</a>'
    r'.*?<div class="mt-3 text-lg font-black[^"]*">#([^<]*)</div>'
    r'.*?<a href="/manga/([^"]+)"[^>]*>\s*'
    r'<div class="line-clamp-2 text-sm font-bold">([^<]*)</div>',
    re.S,
)

#: The pager renders a literal "Next" anchor only while another page exists --
#: an exact has_more signal, so pagination never depends on a page-count guess.
NEXT_LINK_RE = re.compile(
    r'<a href="/search\?[^"]*page=\d+"[^>]*>\s*Next\s*</a>', re.I
)

TITLE_RE = re.compile(r'<h1 class="font-bold[^"]*">([^<]+)</h1>', re.I)
DESCRIPTION_RE = re.compile(r'<p class="text-sm text--secondary">(.*?)</p>', re.S | re.I)
DETAIL_COVER_RE = re.compile(
    r'<img[^>]*data-src="([^"]+)"[^>]*class="lazy absolute[^"]*"', re.I
)
LABEL_RE = re.compile(
    r'<label class="text-secondary">([^<]+)</label>\s*<div>([^<]*)</div>', re.I
)
DETAIL_GENRE_RE = re.compile(r'href="/search\?genre=[^"]*"[^>]*>([^<]+)</a>', re.I)

#: One chapter row from the series page's ``#chapters`` grid.
CHAPTER_LINK_RE = re.compile(
    r'<a class="border border-border[^"]*" href="/chapters/([^"]+)"[^>]*>([^<]+)</a>',
    re.I,
)

#: A reader page image. ``width``/``height`` come free with the markup, so the
#: reader can reserve layout space without measuring or fetching anything.
PAGE_IMAGE_RE = re.compile(
    r'<img[^>]*class="js-page"[^>]*data-src="([^"]+)"[^>]*'
    r'width="(\d+)"[^>]*height="(\d+)"',
    re.I,
)

CHAPTER_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


# --- browse modes -----------------------------------------------------------

#: Mode id -> (label, extra query params). Every mode rides the one ``/search``
#: endpoint except ``default``, which reads ``/chapters``.
BROWSE_MODES: dict[str, tuple[str, dict[str, str]]] = {
    "default": ("Latest Updates", {}),
    "all": ("All Manga", {"type": "manga"}),
    "manhua": ("Manhua", {"type": "manhua"}),
    "ongoing": ("Ongoing", {"status": "publishing"}),
    "completed": ("Completed", {"status": "finished"}),
    "oneshot": ("One-Shots", {"type": "one-shot"}),
}

LATEST_MODE = "default"

#: MangaPill's genre vocabulary, as linked from its own series pages.
GENRES: tuple[str, ...] = (
    "Action", "Adventure", "Cars", "Comedy", "Crime", "Dementia", "Demons",
    "Doujinshi", "Drama", "Ecchi", "Fantasy", "Game", "Gender Bender",
    "Harem", "Historical", "Horror", "Isekai", "Josei", "Kids", "Magic",
    "Martial Arts", "Mecha", "Military", "Music", "Mystery", "Parody",
    "Police", "Psychological", "Romance", "Samurai", "School", "Sci-Fi",
    "Seinen", "Shoujo", "Shoujo Ai", "Shounen", "Shounen Ai", "Slice of Life",
    "Space", "Sports", "Super Power", "Supernatural", "Thriller", "Vampire",
    "Yaoi", "Yuri",
)


def list_browse_modes() -> list[BrowseMode]:
    return [BrowseMode(id=key, label=label) for key, (label, _) in BROWSE_MODES.items()]


def list_genres() -> list[BrowseMode]:
    return [BrowseMode(id=name, label=name) for name in GENRES]


def normalize_sort(sort: str | None) -> str:
    if not sort:
        return LATEST_MODE
    return sort if sort in BROWSE_MODES else LATEST_MODE


def browse_params(sort: str | None, page: int) -> dict[str, Any]:
    """Query for a catalog mode. ``q``/``status``/``type`` are always sent --
    the site's own pager emits all three, and omitting them changes results."""
    _label, extra = BROWSE_MODES[normalize_sort(sort)]
    params: dict[str, Any] = {"q": "", "type": "", "status": ""}
    params.update(extra)
    params["page"] = max(page, 1)
    return params


def search_params(query: str, page: int) -> dict[str, Any]:
    return {
        "q": query.strip(),
        "type": "",
        "status": "",
        "page": max(page, 1),
    }


def genre_params(genre: str, page: int) -> dict[str, Any]:
    return {
        "q": "",
        "type": "",
        "status": "",
        "genre": genre.strip(),
        "page": max(page, 1),
    }


# --- identity ---------------------------------------------------------------


def _strip_site(value: str) -> str:
    text = html_lib.unescape(value or "").strip()
    for prefix in (f"{SITE_BASE}/", "https://mangapill.com/", "http://mangapill.com/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip("/")


def normalize_series_key(value: str) -> str:
    """``2/one-piece`` from any of the shapes the app may hand back."""
    text = _strip_site(value)
    if text.startswith("manga/"):
        text = text.removeprefix("manga/")
    return text.strip("/")


def normalize_chapter_key(value: str) -> str:
    """``2-11192000/one-piece-chapter-1192`` from any inbound shape."""
    text = _strip_site(value)
    if text.startswith("chapters/"):
        text = text.removeprefix("chapters/")
    return text.strip("/")


def series_path(series_key: str) -> str:
    return f"/manga/{normalize_series_key(series_key)}"


def chapter_path(chapter_key: str) -> str:
    return f"/chapters/{normalize_chapter_key(chapter_key)}"


def make_page_id(chapter_key: str, number: int) -> str:
    return f"{chapter_key}{PAGE_ID_SEPARATOR}{number}"


def page_id_chapter_key(page_id: str) -> str | None:
    chapter_key, sep, _index = (page_id or "").rpartition(PAGE_ID_SEPARATOR)
    if not sep or not chapter_key:
        return None
    return chapter_key


def parse_chapter_number(label: str) -> float | None:
    """Chapter number from the site's own label ("Chapter 28.2" -> 28.2).

    Read from the label rather than the key: the key's numeric segment is an
    encoded sort value (chapter 28.2 is ``10028200``), and decoding it would
    mean parsing an opaque identifier.
    """
    match = CHAPTER_NUMBER_RE.search(label or "")
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value


# --- parsing ----------------------------------------------------------------


def _clean(value: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", value or "")).strip()


def _clean_html(value: str) -> str:
    return _clean(re.sub(r"<[^>]+>", " ", value or ""))


def parse_series_cards(html: str) -> list[Series]:
    seen: set[str] = set()
    items: list[Series] = []
    for series_key, cover_url, title in CARD_RE.findall(html):
        key = html_lib.unescape(series_key)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            Series(
                id=key,
                title=_clean(title),
                cover_url=html_lib.unescape(cover_url) or None,
                canonical_path=series_path(key),
            )
        )
    return items


def parse_latest_cards(html: str) -> list[Series]:
    """Series behind the ``/chapters`` recently-updated grid, newest first."""
    seen: set[str] = set()
    items: list[Series] = []
    for cover_url, chapter_label, series_key, title in LATEST_CARD_RE.findall(html):
        key = html_lib.unescape(series_key)
        if key in seen:
            continue
        seen.add(key)
        label = _clean(chapter_label)
        items.append(
            Series(
                id=key,
                title=_clean(title),
                cover_url=html_lib.unescape(cover_url) or None,
                canonical_path=series_path(key),
                latest_chapter=f"Chapter {label}" if label else None,
            )
        )
    return items


def parse_series_list(html: str, *, page: int) -> PaginatedSeriesList:
    items = parse_series_cards(html)
    has_more = NEXT_LINK_RE.search(html) is not None
    consumed = (max(page, 1) - 1) * PAGE_SIZE + len(items)
    # MangaPill never publishes a result count or a last-page number, so the
    # only honest total is a lower bound: what has been seen, plus one more
    # page's worth while the pager still offers a Next.
    total = consumed + PAGE_SIZE if has_more else consumed
    return PaginatedSeriesList(
        items=items,
        page=max(page, 1),
        page_size=PAGE_SIZE,
        total=total,
        api_has_more=has_more,
    )


def slice_latest(series: list[Series], *, page: int) -> PaginatedSeriesList:
    """Page the single-shot ``/chapters`` view locally.

    ``/chapters?page=2`` returns byte-identical HTML, so paging it upstream is
    impossible; slicing the one cached fetch gives real pagination for free.
    """
    current = max(page, 1)
    start = (current - 1) * PAGE_SIZE
    window = series[start : start + PAGE_SIZE]
    return PaginatedSeriesList(
        items=window,
        page=current,
        page_size=PAGE_SIZE,
        total=len(series),
        api_has_more=start + len(window) < len(series),
    )


def parse_series_detail(html: str, series_key: str) -> Series | None:
    title_match = TITLE_RE.search(html)
    if title_match is None:
        return None

    labels = {name.strip().lower(): value for name, value in LABEL_RE.findall(html)}
    cover_match = DETAIL_COVER_RE.search(html)
    description_match = DESCRIPTION_RE.search(html)

    return Series(
        id=series_key,
        title=_clean(title_match.group(1)),
        canonical_path=series_path(series_key),
        description=_clean_html(description_match.group(1)) if description_match else None,
        cover_url=html_lib.unescape(cover_match.group(1)) if cover_match else None,
        # MangaPill's detail page exposes Type / Status / Year / Genres only --
        # it carries no author or artist credit anywhere in the markup.
        author=None,
        artist=None,
        status=_clean(labels.get("status", "")) or None,
        genres=tuple(_clean(name) for name in DETAIL_GENRE_RE.findall(html)),
    )


def parse_chapters(html: str, series_key: str) -> list[Chapter]:
    """Chapters from the series page, returned oldest-first.

    The page lists them newest-first; the app wants ascending order, and
    sorting by the parsed number keeps 28.1 < 28.2 < 29 correct.
    """
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_key, label in CHAPTER_LINK_RE.findall(html):
        key = html_lib.unescape(chapter_key)
        if key in seen:
            continue
        seen.add(key)
        title = _clean(label)
        chapters.append(
            Chapter(
                id=key,
                series_id=series_key,
                title=title,
                number=parse_chapter_number(title),
                # No per-chapter page count exists in this markup; the
                # connector backfills it from cache once a chapter is opened.
                page_count=0,
            )
        )
    chapters.sort(key=lambda chapter: (chapter.number is None, chapter.number or 0.0))
    return chapters


def parse_chapter_pages(html: str, chapter_key: str) -> list[Page]:
    pages: list[Page] = []
    seen: set[str] = set()
    for url, width, height in PAGE_IMAGE_RE.findall(html):
        remote_url = html_lib.unescape(url)
        if remote_url in seen:
            continue
        seen.add(remote_url)
        pages.append(
            Page(
                id=make_page_id(chapter_key, len(pages) + 1),
                chapter_id=chapter_key,
                number=len(pages) + 1,
                remote_url=remote_url,
                width=int(width),
                height=int(height),
            )
        )
    return pages
