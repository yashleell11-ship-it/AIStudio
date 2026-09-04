"""Map Novel Cool HTML pages to normalized connector models.

Novel Cool serves BOTH manga and web novels out of one ``/novel/<slug>.html``
namespace; a card's ``book-type-<kind>`` badge is the only thing that tells
them apart. This connector is the manga half, so every listing parser filters
on that badge (see ``parse_series_cards``).

Two site behaviours drive the shape of everything below:

* **Novel Cool never answers 404.** A slug that does not exist returns HTTP 200
  carrying the homepage. Nothing here may treat a status code as "missing" —
  the connector decides by whether the page parsed (``parse_series_detail``
  returns None, ``parse_chapter_pages`` returns no pages).
* **The reader paginates images.** ``/chapter/<key>.html`` renders ONE image.
  The site's own "Load images" selector offers 1/3/6/10 per view via
  ``/chapter/<key>-<per>-<view>.html``, and values outside that set silently
  fall back to 1 — verified from the VPS, ``-50-1``/``-200-1``/``-1000-1`` all
  returned a single image. 10 is therefore the hard ceiling, and
  ``IMAGES_PER_VIEW`` is that ceiling rather than a tunable.
"""

from __future__ import annotations

import html as html_lib
import re

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://www.novelcool.com"

#: Directory/genre listings render 40 cards; search renders 20.
PAGE_SIZE = 40
SEARCH_PAGE_SIZE = 20

#: Images per reader view. The site clamps to {1, 3, 6, 10}; see module docstring.
IMAGES_PER_VIEW = 10

#: Upstream search pages fetched per app search page.
#:
#: Novel Cool orders search results novels-first. Measured from the VPS, the
#: manga per upstream page for three broad queries were:
#:     "sword"  (0, 1, 18, 13, 13, 19, ...)
#:     "demon"  (1, 1, 12, 20, 19, 13, ...)
#:     "love"   (1, 1, 10, 19, 20, 20, ...)
#: Serving upstream page 1 alone would hand the reader ONE manga for "love" and
#: NONE for "sword". Three pages per app page clears the novel prefix in a
#: single parallel round trip; app page P covers upstream pages
#: 3P-2 .. 3P, so paging stays deterministic and never repeats a result.
SEARCH_PAGES_PER_REQUEST = 3

# --------------------------------------------------------------------------
# Browse modes
# --------------------------------------------------------------------------

#: Listing endpoints that genuinely paginate as ``<stem>_<page>.html``.
#: Verified page counts from the VPS: index 1355, updated 894, completed 394.
_PAGED_STEMS: dict[str, str] = {
    "default": "index",
    "ongoing": "updated",
    "completed": "completed",
}

#: Curated single-page listings. These have NO page 2: requesting
#: ``latest_2.html`` or ``popular_2.html`` does not 404 and does not return the
#: next slice — it silently serves the generic ``index_2`` directory, which
#: would show the reader unrelated titles under a "Latest" heading. The
#: connector refuses to request page 2 of these at all.
_SINGLE_PAGE_STEMS: dict[str, str] = {
    "latest": "latest",
    "popular": "popular",
    "new": "new_list",
}

BROWSE_MODES: tuple[tuple[str, str], ...] = (
    ("default", "Top Rated"),
    ("latest", "Latest Releases"),
    ("popular", "Popular"),
    ("new", "Newly Added"),
    ("ongoing", "Ongoing"),
    ("completed", "Completed"),
)

#: Genres offered by the site's own category sidebar, trimmed to the ones that
#: actually carry manga. Each paginates as ``/category/<Genre>_<page>.html``.
GENRES: tuple[str, ...] = (
    "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Harem",
    "Historical", "Horror", "Isekai", "Josei", "Manhua", "Manhwa",
    "Martial Arts", "Mature", "Mystery", "Psychological", "Romance",
    "School Life", "Sci-fi", "Seinen", "Shoujo", "Shounen", "Slice Of Life",
    "Sports", "Supernatural", "Thriller", "Tragedy", "Webtoons",
)


def normalize_sort(sort: str | None) -> str:
    """Resolve a requested browse mode to one this source implements."""
    if not sort:
        return "default"
    if sort in _PAGED_STEMS or sort in _SINGLE_PAGE_STEMS:
        return sort
    return "default"


def is_single_page_mode(sort: str | None) -> bool:
    """True when the mode has exactly one page of results (see _SINGLE_PAGE_STEMS)."""
    return normalize_sort(sort) in _SINGLE_PAGE_STEMS


def listing_path(sort: str | None, page: int) -> str:
    """Path for a browse listing.

    Page 1 of a paged mode uses the bare ``<stem>.html`` the site links to
    itself; later pages use ``<stem>_<page>.html``.
    """
    mode = normalize_sort(sort)
    if mode in _SINGLE_PAGE_STEMS:
        return f"/category/{_SINGLE_PAGE_STEMS[mode]}.html"
    stem = _PAGED_STEMS[mode]
    return f"/category/{stem}_{max(1, page)}.html"


def genre_path(genre: str, page: int) -> str:
    """Path for a genre listing. Genre names keep their spaces as ``+``."""
    slug = genre.strip().replace(" ", "+")
    return f"/category/{slug}_{max(1, page)}.html"


def search_path() -> str:
    return "/search/"


def search_params(query: str, page: int) -> dict[str, object]:
    return {"name": query.strip(), "page": max(1, page)}


# --------------------------------------------------------------------------
# Identity keys -- OPAQUE strings, never parsed apart by the connector
# --------------------------------------------------------------------------


def series_id_to_path(series_id: str) -> str:
    """``Nano-Machine`` -> ``/novel/Nano-Machine.html``.

    Series keys may contain a slash (``original/id-251898`` is a real one), so
    the key is interpolated whole and never split.
    """
    return f"/novel/{series_id.strip().strip('/')}.html"


def chapter_id_to_path(chapter_id: str, view: int = 1) -> str:
    """``Ch-272/13661864`` -> ``/chapter/Ch-272/13661864-10-<view>.html``.

    Chapter keys always contain a slash (``<title-slug>/<numeric-id>``). The
    ``-<per>-<view>`` suffix is the site's own "Load images" form.
    """
    key = chapter_id.strip().strip("/")
    return f"/chapter/{key}-{IMAGES_PER_VIEW}-{max(1, view)}.html"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    """Split a page id back into its chapter key.

    ``rpartition`` on the LAST colon: chapter keys contain slashes but never a
    colon, so only the trailing ``:<n>`` is removed.
    """
    if ":" not in page_id:
        return None
    chapter_id, _, _number = page_id.rpartition(":")
    return chapter_id or None


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", value)).strip()


def _strip_tags(value: str) -> str:
    return _clean(_TAG_RE.sub(" ", value))


def _absolute(url: str) -> str:
    url = html_lib.unescape(url.strip())
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{SITE_BASE}{url}"
    return url


#: ``/novel/<key>.html`` where <key> may itself contain slashes.
_SERIES_HREF_RE = re.compile(
    r'href="(?:https?://(?:www\.)?novelcool\.com)?/novel/([^"?#]+?)\.html"', re.I
)
_BOOK_TYPE_RE = re.compile(r'class="book-type book-type-(\w+)"', re.I)
_CARD_COVER_RE = re.compile(r'<img\s+src="([^"]+)"\s+cover_url=', re.I)
_CARD_TITLE_RE = re.compile(
    r'<div class="book-name single-line-ellipsis" itemprop="name">([^<]*)</div>', re.I
)
_CARD_PIC_TITLE_RE = re.compile(r'<div class="book-pic" title="([^"]*)"', re.I)
_CARD_TAG_RE = re.compile(r'<div class="book-tag">([^<]*)</div>', re.I)
_CARD_SUMMARY_RE = re.compile(
    r'<div class="book-summary-content" itemprop="description">(.*?)</div>', re.S | re.I
)

#: ``<div class="page-nav-center-num hidden-pm">3/1355</div>`` -- the only
#: place the site states its own total page count.
_TOTAL_PAGES_RE = re.compile(
    r'class="page-nav-center-num[^"]*">\s*(\d+)\s*/\s*(\d+)\s*<', re.I
)
_ALL_PAGES_RE = re.compile(r'all_pages\s*=\s*"(\d+)"', re.I)


#: Present on every real listing page (directory, genre, and search alike,
#: including single-page results); absent from the homepage. This is the ONLY
#: reliable way to tell a listing apart from novelcool's soft 404 — see
#: ``is_listing_page``.
_LISTING_MARKER = "book-list-pager"


def is_listing_page(html: str) -> bool:
    """True when the response really is a listing, not the soft-404 homepage.

    Verified from the VPS: ``/category/index_9999.html`` and
    ``/category/Action_9999.html`` answer HTTP 200 with the **homepage**, which
    carries 104 perfectly well-formed ``book-item`` cards. Parsing those cards
    would show the reader 104 unrelated series under whatever heading they had
    asked for, so every listing parse is gated on this marker first.
    """
    return _LISTING_MARKER in html


def parse_total_pages(html: str) -> int | None:
    """Total listing pages the site reports, or None when it reports none."""
    match = _TOTAL_PAGES_RE.search(html)
    if match:
        return max(1, int(match.group(2)))
    match = _ALL_PAGES_RE.search(html)
    if match:
        return max(1, int(match.group(1)))
    return None


# --------------------------------------------------------------------------
# Listings
# --------------------------------------------------------------------------


def parse_series_cards(html: str, *, manga_only: bool = True) -> list[Series]:
    """Parse ``book-item`` cards, keeping only the manga ones by default.

    Novel Cool mixes novels into every listing (measured across three
    directory pages: 81 manga to 39 novels). ``manga_only`` drops anything
    whose badge is not ``book-type-manga`` so this connector never hands the
    manga reader a prose title it cannot render.
    """
    items: list[Series] = []
    seen: set[str] = set()
    # Cards are sibling <div class="book-item"> blocks; splitting on the
    # opening tag bounds each card without needing to balance nested divs.
    for block in html.split('<div class="book-item"')[1:]:
        if manga_only:
            kind = _BOOK_TYPE_RE.search(block)
            if kind is None or kind.group(1).lower() != "manga":
                continue
        href = _SERIES_HREF_RE.search(block)
        if href is None:
            continue
        series_id = html_lib.unescape(href.group(1))
        if series_id in seen:
            continue
        seen.add(series_id)

        title_match = _CARD_TITLE_RE.search(block) or _CARD_PIC_TITLE_RE.search(block)
        title = _clean(title_match.group(1)) if title_match else series_id
        cover = _CARD_COVER_RE.search(block)
        summary = _CARD_SUMMARY_RE.search(block)
        description = _strip_tags(summary.group(1)) if summary else None
        if description in {"", "N/A"}:
            description = None
        genres = tuple(
            dict.fromkeys(_clean(tag) for tag in _CARD_TAG_RE.findall(block) if tag.strip())
        )
        items.append(
            Series(
                id=series_id,
                title=title,
                canonical_path=series_id_to_path(series_id),
                cover_url=_absolute(cover.group(1)) if cover else None,
                description=description,
                genres=genres,
            )
        )
    return items


def _listing(
    html: str,
    *,
    page: int,
    page_size: int,
    single_page: bool = False,
) -> PaginatedSeriesList:
    if not is_listing_page(html):
        # The soft-404 homepage. Its cards are real series but they answer a
        # question nobody asked; an empty page is the honest result.
        return PaginatedSeriesList(
            items=[], page=page, page_size=page_size, total=0, api_has_more=False
        )
    items = parse_series_cards(html)
    if single_page:
        # No page 2 exists; see _SINGLE_PAGE_STEMS.
        return PaginatedSeriesList(
            items=items,
            page=page,
            page_size=max(page_size, len(items)),
            total=len(items),
            api_has_more=False,
        )
    total_pages = parse_total_pages(html)
    if total_pages is None:
        return PaginatedSeriesList(
            items=items,
            page=page,
            page_size=page_size,
            total=(page - 1) * page_size + len(items),
            api_has_more=False,
        )
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total_pages * page_size,
        api_has_more=page < total_pages,
    )


def parse_series_list(
    html: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
    single_page: bool = False,
) -> PaginatedSeriesList:
    return _listing(html, page=page, page_size=page_size, single_page=single_page)


def parse_search_results(
    html: str,
    *,
    page: int,
    page_size: int = SEARCH_PAGE_SIZE,
) -> PaginatedSeriesList:
    return _listing(html, page=page, page_size=page_size)


# --------------------------------------------------------------------------
# Series detail
# --------------------------------------------------------------------------

_DETAIL_TITLE_RE = re.compile(
    r'<h1 class="bookinfo-title[^"]*"[^>]*>(.*?)</h1>', re.S | re.I
)
_DETAIL_COVER_RE = re.compile(r'<img class="bookinfo-pic-img" src="([^"]+)"', re.I)
_DETAIL_AUTHOR_RE = re.compile(r'<span\s+itemprop="creator"\s*>([^<]*)</span>', re.I)
#: NOTE the ``\s+``: the detail page emits ``<span  itemprop="keywords">`` with
#: TWO spaces. A single-space pattern matches nothing and every series comes
#: back with no genres at all -- which is exactly what the first draft did.
_DETAIL_GENRE_RE = re.compile(r'<span\s+itemprop="keywords"\s*>([^<]*)</span>', re.I)
_DETAIL_SUMMARY_RE = re.compile(
    r'<div class="bk-summary-txt"[^>]*>(.*?)</div>', re.S | re.I
)
_DETAIL_STATUS_RE = re.compile(
    r'<div class="bk-cate-item bk-cate-type1[^"]*">\s*<a[^>]*>([^<]*)</a>', re.I
)


def parse_series_detail(html: str, series_id: str) -> Series | None:
    """Parse a ``/novel/<key>.html`` page, or None when it is not one.

    Returning None is how a missing series is detected: novelcool answers a
    bad slug with HTTP 200 and its homepage, which carries no
    ``bookinfo-title``, so the absence of that heading — not a status code —
    is the signal.
    """
    title_match = _DETAIL_TITLE_RE.search(html)
    if title_match is None:
        return None
    title = _strip_tags(title_match.group(1))
    if not title:
        return None

    kind = _BOOK_TYPE_RE.search(html)
    cover = _DETAIL_COVER_RE.search(html)
    author = _DETAIL_AUTHOR_RE.search(html)
    summary = _DETAIL_SUMMARY_RE.search(html)
    status = _DETAIL_STATUS_RE.search(html)
    description = _strip_tags(summary.group(1)) if summary else None
    if description in {"", "N/A"}:
        description = None
    genres = tuple(
        dict.fromkeys(
            _clean(genre) for genre in _DETAIL_GENRE_RE.findall(html) if genre.strip()
        )
    )
    return Series(
        id=series_id,
        title=title,
        canonical_path=series_id_to_path(series_id),
        cover_url=_absolute(cover.group(1)) if cover else None,
        author=_clean(author.group(1)) if author else None,
        description=description,
        status=_clean(status.group(1)) if status else None,
        genres=genres,
    )


def parse_book_type(html: str) -> str | None:
    """``"manga"`` / ``"novel"`` badge on a detail page, when present."""
    match = _BOOK_TYPE_RE.search(html)
    return match.group(1).lower() if match else None


# --------------------------------------------------------------------------
# Chapters
# --------------------------------------------------------------------------

_CHAPTER_ROW_RE = re.compile(
    r'<a href="(?:https?://(?:www\.)?novelcool\.com)?/chapter/([^"?#]+?)/?"'
    r'[^>]*target="_blank"[^>]*title="([^"]*)".*?'
    r'<span class="chapter-item-time">([^<]*)</span>',
    re.S | re.I,
)

#: "Ch.272", "Chapter 260", "Ch. 16 This Bastard...", "Vol.TBE Ch.1165",
#: "ch.994" -- the number that follows a Ch/Chapter/Ep token is the chapter's
#: own numbering and is what ``chapter_number`` must be.
_CHAPTER_NUM_RE = re.compile(
    r"(?:chapter|chap|ch|episode|ep)\s*\.?\s*(\d+(?:[.\-]\d+)?)", re.I
)
#: Bare-numbered titles. Novel Cool has plenty ("136.5 {NOTICE}", "0.5"), and
#: the number leads rather than trails, so a trailing-number fallback alone
#: leaves them unnumbered and strands them at the end of the reading order.
_LEADING_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)")
_TRAILING_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*$")


def parse_chapter_number(title: str) -> float | None:
    """Stable float from the site's own chapter numbering.

    ``Chapter 0.5`` and ``Ch.28-5`` both appear upstream; the hyphen form is
    the site's own escaping of a decimal point in a URL slug, so it is read as
    one. Titles carrying no number at all ("Chapter", "Prologue") return None
    and the caller sorts them last.
    """
    text = _clean(title)
    match = _CHAPTER_NUM_RE.search(text)
    raw = match.group(1) if match else None
    if raw is None:
        lead = _LEADING_NUM_RE.search(text)
        raw = lead.group(1) if lead else None
    if raw is None:
        tail = _TRAILING_NUM_RE.search(text)
        raw = tail.group(1) if tail else None
    if raw is None:
        return None
    raw = raw.replace("-", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


def parse_chapters(html: str, series_id: str) -> list[Chapter]:
    """Every chapter of a series, oldest first.

    The full list is inline on the series detail page — there is no separate
    chapter endpoint to call, which is why the connector shares one fetch
    between ``get_series`` and ``get_chapters``.
    """
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_key, title, released in _CHAPTER_ROW_RE.findall(html):
        key = html_lib.unescape(chapter_key)
        if key in seen:
            continue
        seen.add(key)
        clean_title = _clean(title) or key
        chapters.append(
            Chapter(
                id=key,
                series_id=series_id,
                title=clean_title,
                number=parse_chapter_number(clean_title),
                page_count=0,
                release_date=_clean(released) or None,
            )
        )
    # Upstream lists newest first. Reverse, then sort by the site's own
    # numbering so unnumbered oddments ("Chapter", "TAL 0") settle at the end
    # instead of scrambling the reading order.
    chapters.reverse()
    chapters.sort(
        key=lambda chapter: chapter.number if chapter.number is not None else float("inf")
    )
    return chapters


# --------------------------------------------------------------------------
# Chapter pages
# --------------------------------------------------------------------------

#: Each rendered image sits in its own ``pic_box`` next to a "<n>/<total>"
#: label. That label is the GLOBAL page number: the ``i="1"`` attribute on the
#: <img> restarts at 1 on every reader view, so reading the number from the
#: attribute would give ten pages numbered 1-10 followed by three more also
#: numbered 1-3. The label is read instead.
_PIC_LABEL_RE = re.compile(r">\s*(\d+)\s*/\s*(\d+)\s*</a>")
_PIC_IMG_RE = re.compile(
    r'<img[^>]+class="mangaread-manga-pic[^"]*"[^>]+src="([^"]+)"', re.I
)
_VIEW_SELECT_RE = re.compile(r'<select class="sl-page".*?</select>', re.S | re.I)
_VIEW_OPTION_RE = re.compile(r"<option", re.I)
_CHAPTER_TITLE_RE = re.compile(r'<h1 class="row-item">([^<]*)</h1>', re.I)


def parse_chapter_pages(html: str, chapter_id: str) -> tuple[list[Page], int, int]:
    """Parse one reader view.

    Returns ``(pages, total_pages, total_views)`` where ``total_pages`` is the
    image count for the whole chapter and ``total_views`` is how many
    ``-10-<view>`` fetches cover it. Both come from the view just parsed, so
    the caller learns the full shape of the chapter from its first request.
    """
    pages: list[Page] = []
    total_pages = 0
    for block in html.split('<div class="pic_box')[1:]:
        img = _PIC_IMG_RE.search(block)
        if img is None:
            continue
        label = _PIC_LABEL_RE.search(block)
        if label is None:
            continue
        number = int(label.group(1))
        total_pages = max(total_pages, int(label.group(2)))
        pages.append(
            Page(
                id=make_page_id(chapter_id, number),
                chapter_id=chapter_id,
                number=number,
                remote_url=_absolute(img.group(1)),
            )
        )

    select = _VIEW_SELECT_RE.search(html)
    total_views = len(_VIEW_OPTION_RE.findall(select.group(0))) if select else 0
    if total_views <= 0 and pages:
        total_views = 1
    return pages, total_pages, total_views


def parse_chapter_title(html: str) -> str | None:
    match = _CHAPTER_TITLE_RE.search(html)
    return _clean(match.group(1)) if match else None
