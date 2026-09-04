"""Map manhwa18.cc HTML pages to normalized connector models.

manhwa18.cc is a hand-rolled (non-Madara) Laravel-style site. Every surface a
reader needs is plain server-rendered HTML with stable class names, and two of
them are one-shot endpoints that make this source unusually cheap:

* ``/webtoon/<slug>`` carries the full metadata block **and** the complete
  chapter list (227 rows for Return of the Frozen Player) in a single
  document — detail and chapter list must share one fetch, never two.
* ``/webtoon/<slug>/<chapter-ref>`` carries every page image URL inline, so a
  chapter's images cost exactly one request regardless of page count.

Identity keys are opaque strings taken verbatim from the site:
``series_key`` is the slug (``return-of-the-frozen-player``) and
``chapter_key`` is ``<slug>/<chapter-ref>`` (``.../chapter-100-5``) — it
contains a slash and is never parsed apart by the connector.
"""

from __future__ import annotations

import html as html_lib
import re

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://manhwa18.cc"

#: Cards per listing page. Verified from the VPS to be 24 on every catalog
#: view — /webtoons, /raw, /completed, /webtoon-genre/<g> and /search alike.
PAGE_SIZE = 24

#: The listing pager only ever renders a five-wide window plus prev/next, so
#: there is no total-page number to read anywhere on the page. The presence of
#: the ``next`` list item is the site's own "another page exists" signal and is
#: what drives ``has_more``; asking for a page past the end returns a short
#: page with no ``next`` (verified: /webtoons/9999 -> 15 items, no next).
NEXT_PAGE_RE = re.compile(r'<li class="next">', re.I)

#: One listing card. Split-then-parse rather than one giant regex so a card
#: whose optional bits (rating, latest-chapter row) are missing still yields
#: its series instead of desynchronising the match against the next card.
CARD_SPLIT_RE = re.compile(r'<div class="manga-item">', re.I)
CARD_THUMB_RE = re.compile(
    r'<div class="thumb">\s*<a href="/webtoon/([^"/]+)"[^>]*>.*?'
    r'<img[^>]+data-src="([^"]+)"',
    re.S | re.I,
)
CARD_TITLE_RE = re.compile(
    r'<div class="data[^"]*">\s*<h3>\s*<a[^>]*>\s*(.*?)\s*</a>',
    re.S | re.I,
)
CARD_LATEST_CHAPTER_RE = re.compile(
    r'<a href="/webtoon/[^"]+"[^>]*class="btn-link"[^>]*>\s*(.*?)\s*</a>',
    re.S | re.I,
)

#: Series detail. ``<h1>`` carries an ``18+`` badge span before the title on
#: adult entries (which is nearly all of them here), so the badge is stripped.
DETAIL_TITLE_RE = re.compile(
    r'<div class="post-title">\s*<h1>\s*(?:<span>[^<]*</span>)?\s*(.*?)\s*</h1>',
    re.S | re.I,
)
DETAIL_COVER_RE = re.compile(
    r'<div class="summary_image">.*?<img[^>]+data-src="([^"]+)"',
    re.S | re.I,
)
DETAIL_AUTHOR_RE = re.compile(
    r'<div class="author-content">\s*(.*?)\s*</div>', re.S | re.I
)
DETAIL_ARTIST_RE = re.compile(
    r'<div class="artist-content">\s*(.*?)\s*</div>', re.S | re.I
)
DETAIL_GENRES_BLOCK_RE = re.compile(
    r'<div class="genres-content">(.*?)</div>', re.S | re.I
)
DETAIL_GENRE_RE = re.compile(r"<a[^>]*>\s*(.*?)\s*</a>", re.S | re.I)
DETAIL_DESCRIPTION_RE = re.compile(
    r'<div class="dsct">\s*(.*?)\s*</div>', re.S | re.I
)

#: ``Status`` / ``Alternative`` sit in the shared ``post-content_item``
#: heading/value pair shape; the value div holds bare text for both.
DETAIL_FIELD_TEMPLATE = (
    r"<h5>\s*{label}\s*:?\s*</h5>\s*</div>\s*"
    r'<div class="summary-content"[^>]*>\s*(.*?)\s*</div>'
)

#: Chapter list. Scoped to the one ``row-content-chapter`` list on the page so
#: sidebar/footer links can never be mistaken for chapters.
CHAPTER_LIST_RE = re.compile(
    r'<ul class="row-content-chapter[^"]*">(.*?)</ul>', re.S | re.I
)
CHAPTER_ROW_SPLIT_RE = re.compile(r"<li\b", re.I)
CHAPTER_LINK_RE = re.compile(
    r'<a class="chapter-name[^"]*" href="/webtoon/([^"/]+)/([^"]+)"[^>]*>\s*(.*?)\s*</a>',
    re.S | re.I,
)
CHAPTER_TIME_RE = re.compile(
    r'<span class="chapter-time[^"]*"[^>]*>\s*(.*?)\s*</span>', re.S | re.I
)

#: Chapter reader. The ``read-content`` div is flat (verified: zero nested
#: divs), so a non-greedy match to the first ``</div>`` is exact. Reading every
#: ``data-src`` inside it — rather than only ``class="loading pN"`` images —
#: keeps working if the site drops its per-page class, and both forms counted
#: identically on every chapter sampled from the VPS.
READ_CONTENT_RE = re.compile(
    r'<div class="read-content[^"]*">(.*?)</div>', re.S | re.I
)
PAGE_IMAGE_RE = re.compile(r'<img[^>]+data-src="([^"]+)"', re.I)

#: "Chapter 100.5" in the row label is the site's own numbering and is the
#: primary source for ``chapter_number``; the URL ref spells the same thing
#: with a dash (``chapter-100-5``) and is the fallback.
CHAPTER_LABEL_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")
CHAPTER_REF_NUMBER_RE = re.compile(r"chapter-(\d+)(?:-(\d+))?", re.I)

#: Placeholder the site prints for unknown author/artist/status.
UNKNOWN_VALUES = frozenset({"", "updating", "n/a", "-", "unknown"})

#: Catalog views. ``/webtoons`` honours ``orderby``; ``/raw`` and ``/completed``
#: are separate curated listings that ignore it (verified from the VPS: the
#: same first cards come back with and without the parameter), so they are
#: exposed as their own modes rather than as sorts that would silently no-op.
BROWSE_MODES: tuple[tuple[str, str, str, str | None], ...] = (
    ("default", "Latest Updates", "/webtoons", "latest"),
    ("trending", "Trending", "/webtoons", "trending"),
    ("rating", "Top Rated", "/webtoons", "rating"),
    ("alphabetical", "A-Z", "/webtoons", "alphabet"),
    ("raw", "Raw", "/raw", None),
    ("completed", "Completed", "/completed", None),
)

_BROWSE_BY_ID = {mode_id: (path, order) for mode_id, _, path, order in BROWSE_MODES}

#: The site's own genre menu, rendered identically into every page's footer.
#: Hardcoded deliberately: it is static site navigation, and fetching a page
#: just to re-read it would add a request to the very first browse call.
GENRES: tuple[tuple[str, str], ...] = (
    ("action", "Action"),
    ("adult", "Adult (18+)"),
    ("adventure", "Adventure"),
    ("bl", "BL"),
    ("comedy", "Comedy"),
    ("comics", "Comics"),
    ("doujinshi", "Doujinshi"),
    ("drama", "Drama"),
    ("ecchi", "Ecchi"),
    ("family", "Family"),
    ("fantasy", "Fantasy"),
    ("gender-bender", "Gender Bender"),
    ("gl", "GL"),
    ("harem", "Harem"),
    ("hentai", "Hentai"),
    ("historical", "Historical"),
    ("horror", "Horror"),
    ("isekai", "Isekai"),
    ("josei", "Josei"),
    ("magic", "Magic"),
    ("martial-arts", "Martial Arts"),
    ("mature", "Mature"),
    ("mecha", "Mecha"),
    ("mystery", "Mystery"),
    ("ntr", "NTR"),
    ("psychological", "Psychological"),
    ("romance", "Romance"),
    ("school-life", "School Life"),
    ("sci-fi", "Sci-fi"),
    ("seinen", "Seinen"),
    ("shoujo", "Shoujo"),
    ("shounen", "Shounen"),
    ("slice-of-life", "Slice of Life"),
    ("smut", "Smut"),
    ("sports", "Sports"),
    ("supernatural", "Supernatural"),
    ("thriller", "Thriller"),
    ("tragedy", "Tragedy"),
    ("yaoi", "Yaoi"),
    ("yuri", "Yuri"),
)

_GENRE_SLUGS = frozenset(slug for slug, _ in GENRES)


def browse_modes() -> list[BrowseMode]:
    return [BrowseMode(id=mode_id, label=label) for mode_id, label, _, _ in BROWSE_MODES]


def genre_modes() -> list[BrowseMode]:
    return [BrowseMode(id=slug, label=label) for slug, label in GENRES]


def clean_text(value: str) -> str:
    """Strip tags, decode entities, collapse whitespace."""
    return html_lib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value))).strip()


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = clean_text(value)
    return None if cleaned.lower() in UNKNOWN_VALUES else cleaned


def series_path(series_key: str) -> str:
    return f"/webtoon/{series_key.strip().strip('/')}"


def chapter_path(chapter_key: str) -> str:
    return f"/webtoon/{chapter_key.strip().strip('/')}"


def listing_path(mode: str | None, page: int) -> str:
    """Path for a catalog view. Page 1 is spelled ``/1`` like the site's pager."""
    path, _order = _BROWSE_BY_ID.get(mode or "default", _BROWSE_BY_ID["default"])
    return f"{path}/{max(page, 1)}"


def listing_params(mode: str | None) -> dict[str, str] | None:
    _path, order = _BROWSE_BY_ID.get(mode or "default", _BROWSE_BY_ID["default"])
    return {"orderby": order} if order else None


def genre_path(genre: str, page: int) -> str:
    return f"/webtoon-genre/{genre.strip().strip('/')}/{max(page, 1)}"


def is_known_genre(genre: str) -> bool:
    return genre.strip().strip("/").lower() in _GENRE_SLUGS


def search_params(query: str, page: int) -> dict[str, str]:
    return {"q": query.strip(), "page": str(max(page, 1))}


def make_page_id(chapter_key: str, page_number: int) -> str:
    """Page identity. Chapter refs never contain ``:``, so the last colon is
    an unambiguous separator even though ``chapter_key`` contains a slash."""
    return f"{chapter_key}:{page_number}"


def page_id_chapter_key(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_key, _, _number = page_id.rpartition(":")
    return chapter_key or None


def parse_chapter_number(label: str, chapter_ref: str) -> float | None:
    """The site's own numbering, as a stable float.

    Prefers the visible row label ("Chapter 100.5") and falls back to the URL
    ref, which spells the same number with a dash (``chapter-100-5``).
    """
    match = CHAPTER_LABEL_NUMBER_RE.search(label or "")
    if match is not None:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    ref_match = CHAPTER_REF_NUMBER_RE.search(chapter_ref or "")
    if ref_match is None:
        return None
    whole, fraction = ref_match.group(1), ref_match.group(2)
    try:
        return float(f"{whole}.{fraction}") if fraction else float(whole)
    except ValueError:
        return None


def _detail_field(html_text: str, label: str) -> str | None:
    match = re.search(
        DETAIL_FIELD_TEMPLATE.format(label=re.escape(label)),
        html_text,
        re.S | re.I,
    )
    return match.group(1) if match else None


def parse_series_cards(html_text: str) -> list[Series]:
    items: list[Series] = []
    seen: set[str] = set()
    for card in CARD_SPLIT_RE.split(html_text)[1:]:
        thumb = CARD_THUMB_RE.search(card)
        if thumb is None:
            continue
        series_key, cover_url = thumb.group(1), thumb.group(2)
        if series_key in seen:
            continue
        seen.add(series_key)
        title_match = CARD_TITLE_RE.search(card)
        title = clean_text(title_match.group(1)) if title_match else series_key
        latest_match = CARD_LATEST_CHAPTER_RE.search(card)
        items.append(
            Series(
                id=series_key,
                title=title or series_key,
                cover_url=cover_url,
                canonical_path=series_path(series_key),
                latest_chapter=clean_text(latest_match.group(1)) if latest_match else None,
            )
        )
    return items


def parse_series_list(
    html_text: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html_text)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        # No total is published anywhere; report what has actually been seen
        # and let the site's own `next` link decide whether more exists.
        total=(page - 1) * page_size + len(items),
        api_has_more=bool(items) and NEXT_PAGE_RE.search(html_text) is not None,
    )


def parse_search_results(
    html_text: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    return parse_series_list(html_text, page=page, page_size=page_size)


def parse_series_detail(html_text: str, series_key: str) -> Series | None:
    title_match = DETAIL_TITLE_RE.search(html_text)
    if title_match is None:
        return None
    title = clean_text(title_match.group(1))
    if not title:
        return None

    cover_match = DETAIL_COVER_RE.search(html_text)
    genres_block = DETAIL_GENRES_BLOCK_RE.search(html_text)
    genres = (
        tuple(
            genre
            for genre in (
                clean_text(name) for name in DETAIL_GENRE_RE.findall(genres_block.group(1))
            )
            if genre
        )
        if genres_block
        else ()
    )
    description_match = DETAIL_DESCRIPTION_RE.search(html_text)
    author_match = DETAIL_AUTHOR_RE.search(html_text)
    artist_match = DETAIL_ARTIST_RE.search(html_text)

    return Series(
        id=series_key,
        title=title,
        cover_url=cover_match.group(1) if cover_match else None,
        canonical_path=series_path(series_key),
        description=_optional(description_match.group(1)) if description_match else None,
        author=_optional(author_match.group(1)) if author_match else None,
        artist=_optional(artist_match.group(1)) if artist_match else None,
        status=_optional(_detail_field(html_text, "Status")),
        genres=genres,
    )


def parse_chapters(html_text: str, series_key: str) -> list[Chapter]:
    block = CHAPTER_LIST_RE.search(html_text)
    if block is None:
        return []
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for row in CHAPTER_ROW_SPLIT_RE.split(block.group(1))[1:]:
        link = CHAPTER_LINK_RE.search(row)
        if link is None:
            continue
        row_slug, chapter_ref, label = link.group(1), link.group(2), link.group(3)
        if row_slug != series_key:
            continue
        chapter_key = f"{series_key}/{chapter_ref}"
        if chapter_key in seen:
            continue
        seen.add(chapter_key)
        time_match = CHAPTER_TIME_RE.search(row)
        chapters.append(
            Chapter(
                id=chapter_key,
                series_id=series_key,
                title=clean_text(label) or chapter_ref,
                number=parse_chapter_number(label, chapter_ref),
                # The series page publishes no per-chapter page count; the
                # connector backfills it from cache once a chapter is opened.
                page_count=0,
                release_date=_optional(time_match.group(1)) if time_match else None,
            )
        )
    # The site lists newest first; the reader wants oldest first.
    chapters.sort(key=lambda chapter: (chapter.number is None, chapter.number or 0.0))
    return chapters


def parse_chapter_pages(html_text: str, chapter_key: str) -> list[Page]:
    block = READ_CONTENT_RE.search(html_text)
    if block is None:
        return []
    pages: list[Page] = []
    seen: set[str] = set()
    for remote_url in PAGE_IMAGE_RE.findall(block.group(1)):
        url = html_lib.unescape(remote_url).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        pages.append(
            Page(
                id=make_page_id(chapter_key, len(pages) + 1),
                chapter_id=chapter_key,
                number=len(pages) + 1,
                remote_url=url,
            )
        )
    return pages
