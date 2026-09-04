"""Map MangaTown HTML pages to normalized connector models.

MangaTown is a long-established aggregator on a hand-rolled PHP stack (not
Madara), so everything here is HTML scraping plus one small JSON-ish endpoint
(``chapterfun.ashx``) that hands back page-image URLs in a packed-JS wrapper.

Robots note (verified from the VPS on 2026-09-04): ``/robots.txt`` is
``Allow: /`` with exactly two non-``/directory/`` bans -- ``/search/`` and
``/ajax/``. Nothing here touches ``/ajax/``. The live search endpoint is
``/search?name=`` whose *path* is ``/search`` (no trailing slash), so the
``/search/`` prefix rule does not match it under RFC 9309; ``/search/``
itself answers 404, i.e. the banned prefix is not a real page, and the live
one serves ``<meta name="robots" content="index,follow">``. The ``q``-prefixed
``/directory/qcat...`` bans cover the site's faceted filter URLs, not the
``0-<genre>-0-0-0-0`` form used here.
"""

from __future__ import annotations

import html as html_module
import re

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://www.mangatown.com"

#: ``/directory/``, ``/hot/`` and ``/latest/`` all render 30 cards per page;
#: ``/search`` renders 20. Measured from the VPS fixtures, not assumed.
LIST_PAGE_SIZE = 30
SEARCH_PAGE_SIZE = 20

#: Sent as ``Referer`` on every image GET. Both CDNs (page images on
#: ``zjcdn.mangahere.org``, covers on ``fmcdn.mangahere.com``) answer 403 to a
#: request with no ``Referer``; the bare site root is enough for both, so the
#: header can stay static instead of being rebuilt per chapter.
IMAGE_REFERER = f"{SITE_BASE}/"


# --------------------------------------------------------------------------
# identity keys
#
# series_key is the catalog slug ("naruto"). chapter_key is everything after
# "/manga/" ("naruto/v01/c001") and therefore CONTAINS SLASHES -- it is stored
# and passed raw, never split apart. page_id appends ":<n>", and ":" cannot
# occur in a MangaTown path, so rpartition recovers the chapter key intact.
# --------------------------------------------------------------------------


def series_id_to_path(series_id: str) -> str:
    return f"/manga/{series_id.strip().strip('/')}/"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/manga/{chapter_id.strip().strip('/')}/"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _number = page_id.rpartition(":")
    return chapter_id or None


def page_id_number(page_id: str) -> int | None:
    if ":" not in page_id:
        return None
    _, _, number = page_id.rpartition(":")
    try:
        return int(number)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# browse modes / paths
# --------------------------------------------------------------------------

#: mode id -> (path prefix, raw query string). The sort keys are valueless
#: query flags exactly as the site's own tab strip emits them
#: (``/directory/?rating.za``); appending "=" would be a different URL, so the
#: query is spliced into the path rather than passed through httpx params.
BROWSE_MODES: dict[str, tuple[str, str]] = {
    "default": ("/directory", ""),
    "latest": ("/latest", ""),
    "hot": ("/hot", ""),
    "updated": ("/directory", "last_chapter_time.za"),
    "rating": ("/directory", "rating.za"),
    "alphabetical": ("/directory", "name.az"),
}

BROWSE_MODE_LABELS: list[tuple[str, str]] = [
    ("default", "Most Viewed"),
    ("hot", "Hot Manga"),
    ("latest", "Latest Releases"),
    ("updated", "Recently Updated"),
    ("rating", "Top Rated"),
    ("alphabetical", "A-Z"),
]

#: Genre slugs as they appear in ``/directory/0-<genre>-0-0-0-0/``, harvested
#: from the directory filter UI on the VPS.
GENRES: tuple[tuple[str, str], ...] = (
    ("action", "Action"),
    ("adventure", "Adventure"),
    ("comedy", "Comedy"),
    ("cooking", "Cooking"),
    ("doujinshi", "Doujinshi"),
    ("drama", "Drama"),
    ("ecchi", "Ecchi"),
    ("fantasy", "Fantasy"),
    ("gender_bender", "Gender Bender"),
    ("harem", "Harem"),
    ("historical", "Historical"),
    ("horror", "Horror"),
    ("martial_arts", "Martial Arts"),
    ("mature", "Mature"),
    ("mecha", "Mecha"),
    ("music", "Music"),
    ("mystery", "Mystery"),
    ("one_shot", "One Shot"),
    ("psychological", "Psychological"),
    ("reverse_harem", "Reverse Harem"),
    ("romance", "Romance"),
    ("school_life", "School Life"),
    ("sci_fi", "Sci-fi"),
    ("shotacon", "Shotacon"),
    ("slice_of_life", "Slice of Life"),
    ("smut", "Smut"),
    ("sports", "Sports"),
    ("supernatural", "Supernatural"),
    ("suspense", "Suspense"),
    ("tragedy", "Tragedy"),
    ("vampire", "Vampire"),
    ("webtoons", "Webtoons"),
    ("youkai", "Youkai"),
    ("4_koma", "4-Koma"),
)

_GENRE_SLUGS = frozenset(slug for slug, _label in GENRES)


def normalize_sort(sort: str | None) -> str:
    if not sort or sort not in BROWSE_MODES:
        return "default"
    return sort


def listing_path(page: int, *, sort: str | None = None) -> str:
    """Path for one page of a browse mode (``/directory/3.htm?rating.za``)."""
    prefix, query = BROWSE_MODES[normalize_sort(sort)]
    path = f"{prefix}/{max(1, page)}.htm"
    return f"{path}?{query}" if query else path


def genre_path(genre: str, page: int) -> str:
    """Path for one page of a genre listing.

    The six ``0``-separated slots are (type, genre, ...); only the genre slot
    is used here. This is the form the site's own genre links use and is NOT
    covered by the ``/directory/q*`` robots bans, which target the faceted
    ``qcat``/``qat``/``qstatus``/``qyear`` filter URLs.
    """
    slug = genre.strip().strip("/").lower()
    return f"/directory/0-{slug}-0-0-0-0/{max(1, page)}.htm"


def is_known_genre(genre: str) -> bool:
    return genre.strip().lower() in _GENRE_SLUGS


def search_params(query: str, page: int) -> dict[str, str | int]:
    return {"name": query.strip(), "page": max(1, page)}


# --------------------------------------------------------------------------
# shared HTML helpers
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(value: str) -> str:
    return _WS_RE.sub(" ", html_module.unescape(_TAG_RE.sub(" ", value))).strip()


def _absolute(url: str) -> str:
    url = html_module.unescape(url.strip())
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{SITE_BASE}{url}"
    return url


# --------------------------------------------------------------------------
# listing pages (/directory, /hot, /latest, /search, genre) -- one markup
# --------------------------------------------------------------------------

_LIST_UL_RE = re.compile(r'<ul class="manga_pic_list">(.*?)</ul>', re.S | re.I)
_LIST_ITEM_RE = re.compile(r"<li>(.*?)</li>", re.S | re.I)
_COVER_RE = re.compile(
    r'<a class="manga_cover"\s+href="/manga/([^"/]+)/"[^>]*>\s*<img\s+src="([^"]+)"',
    re.S | re.I,
)
_ITEM_TITLE_RE = re.compile(
    r'<p class="title">\s*<a[^>]*>(.*?)</a>', re.S | re.I
)
_KEYWORD_RE = re.compile(r'<p class="keyWord">(.*?)</p>', re.S | re.I)
_ANCHOR_TEXT_RE = re.compile(r"<a[^>]*>(.*?)</a>", re.S | re.I)
_VIEW_FIELD_RE = re.compile(
    r'<p class="view">\s*(Author|Status)\s*:\s*(.*?)</p>', re.S | re.I
)
_NEW_CHAPTER_RE = re.compile(r'<p class="new_chapter">\s*<a[^>]*>(.*?)</a>', re.S | re.I)

#: Page N of M is only ever stated in the paginator's own <option> labels
#: ("3/334"). The <a> hrefs around it are a sliding window (1..8 then 334),
#: so counting them would under-report the total on every page but the last.
_PAGINATION_BLOCK_RE = re.compile(r'<div class="next-page">(.*?)</div>', re.S | re.I)
_PAGINATION_LABEL_RE = re.compile(r"<option[^>]*>\s*(\d+)\s*/\s*(\d+)\s*</option>", re.I)


def parse_total_pages(html: str) -> int:
    block = _PAGINATION_BLOCK_RE.search(html)
    if not block:
        return 1
    labels = _PAGINATION_LABEL_RE.findall(block.group(1))
    if labels:
        return max(int(total) for _current, total in labels)
    return 1


def _parse_item(chunk: str) -> Series | None:
    cover = _COVER_RE.search(chunk)
    if not cover:
        return None
    series_id, cover_url = cover.group(1), _absolute(cover.group(2))

    title_match = _ITEM_TITLE_RE.search(chunk)
    title = _clean(title_match.group(1)) if title_match else ""
    if not title:
        return None

    genres: tuple[str, ...] = ()
    keyword = _KEYWORD_RE.search(chunk)
    if keyword:
        genres = tuple(
            _clean(text) for text in _ANCHOR_TEXT_RE.findall(keyword.group(1)) if _clean(text)
        )

    author: str | None = None
    status: str | None = None
    for field, value in _VIEW_FIELD_RE.findall(chunk):
        cleaned = _clean(value)
        if not cleaned:
            continue
        if field.lower() == "author":
            author = cleaned
        else:
            status = cleaned

    latest_match = _NEW_CHAPTER_RE.search(chunk)
    latest = _clean(latest_match.group(1)) if latest_match else None

    return Series(
        id=series_id,
        title=title,
        canonical_path=series_id_to_path(series_id),
        cover_url=cover_url,
        author=author,
        status=status,
        genres=genres,
        latest_chapter=latest or None,
    )


def parse_series_cards(html: str) -> list[Series]:
    """Every series card on a listing page, in document order."""
    block = _LIST_UL_RE.search(html)
    if not block:
        return []
    items: list[Series] = []
    seen: set[str] = set()
    for chunk in _LIST_ITEM_RE.findall(block.group(1)):
        series = _parse_item(chunk)
        if series is None or series.id in seen:
            continue
        seen.add(series.id)
        items.append(series)
    return items


def parse_series_list(
    html: str, *, page: int, page_size: int = LIST_PAGE_SIZE
) -> PaginatedSeriesList:
    items = parse_series_cards(html)
    total_pages = parse_total_pages(html)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total_pages * page_size,
        api_has_more=page < total_pages and bool(items),
    )


def parse_search_results(
    html: str, *, page: int, page_size: int = SEARCH_PAGE_SIZE
) -> PaginatedSeriesList:
    return parse_series_list(html, page=page, page_size=page_size)


# --------------------------------------------------------------------------
# series detail  (/manga/<slug>/)
# --------------------------------------------------------------------------

_DETAIL_TITLE_RE = re.compile(r'<h1 class="title-top">(.*?)</h1>', re.S | re.I)
_DETAIL_COVER_RE = re.compile(
    r'<div class="detail_info clearfix">\s*<img\s+src="([^"]+)"', re.S | re.I
)
_DETAIL_FIELD_RE = re.compile(
    r"<li>\s*<b>\s*([^<:]+?)\s*:?\s*</b>(.*?)(?=<li>|</ul>)", re.S | re.I
)
_SUMMARY_RE = re.compile(r'<span id="hide"[^>]*>(.*?)</span>', re.S | re.I)
_PLURAL_SUFFIX_RE = re.compile(r"\(s\)$")


def parse_series_detail(html: str, series_id: str) -> Series | None:
    """Parse a series page, or return None when the slug does not exist.

    A missing series is NOT a 404 here: MangaTown 302s ``/manga/<bad>/`` to
    ``/search?stype=1&name=<bad>`` and serves that with HTTP 200, so the only
    honest not-found signal is the absence of the detail markup. Verified from
    the VPS against ``/manga/zzz_no_such_series_xyz/``.
    """
    title_match = _DETAIL_TITLE_RE.search(html)
    if not title_match or '<div class="detail_info' not in html:
        return None
    title = _clean(title_match.group(1))
    if not title:
        return None

    cover_match = _DETAIL_COVER_RE.search(html)
    cover_url = _absolute(cover_match.group(1)) if cover_match else None

    author: str | None = None
    artist: str | None = None
    status: str | None = None
    genres: list[str] = []
    for label, value in _DETAIL_FIELD_RE.findall(html):
        # NB: rstrip("(s)") would be character-wise and turn "status(s)" into
        # "statu" (it keeps eating the trailing "s"), silently dropping the
        # status field. Strip the literal suffix instead.
        key = _PLURAL_SUFFIX_RE.sub("", label.strip().lower()).strip()
        if key.startswith("genre"):
            genres.extend(
                _clean(text) for text in _ANCHOR_TEXT_RE.findall(value) if _clean(text)
            )
        elif key.startswith("demographic"):
            genres.extend(
                _clean(text) for text in _ANCHOR_TEXT_RE.findall(value) if _clean(text)
            )
        elif key.startswith("author"):
            author = _clean(value) or None
        elif key.startswith("artist"):
            artist = _clean(value) or None
        elif key.startswith("status"):
            # The status <li> is not just the status: MangaTown appends a promo
            # blurb inside it ("Ongoing &nbsp;<a>One Piece Green 2</a> will
            # coming soon"). Only the leading bare text is the actual status,
            # so stop at the first nested tag rather than flattening the lot.
            status = _clean(value.split("<", 1)[0].replace("&nbsp;", " ")) or None

    summary_match = _SUMMARY_RE.search(html)
    description = _clean(summary_match.group(1)) if summary_match else None

    deduped: list[str] = []
    for genre in genres:
        if genre not in deduped:
            deduped.append(genre)

    return Series(
        id=series_id,
        title=title,
        canonical_path=series_id_to_path(series_id),
        cover_url=cover_url,
        description=description or None,
        author=author,
        artist=artist,
        status=status,
        genres=tuple(deduped),
    )


# --------------------------------------------------------------------------
# chapter list -- shipped inside the SAME series page, so one fetch serves
# both get_series and get_chapters (see connector's _series_page cache).
# --------------------------------------------------------------------------

_CHAPTER_UL_RE = re.compile(r'<ul class="chapter_list">(.*?)</ul>', re.S | re.I)
_CHAPTER_ROW_RE = re.compile(
    r'<a\s+href="/manga/([^"]+?)/"\s+name="([^"]*)"[^>]*>(.*?)</a>(.*?)(?=<li>|\Z)',
    re.S | re.I,
)
_SPAN_RE = re.compile(r'<span(?:\s+class="([^"]*)")?[^>]*>(.*?)</span>', re.S | re.I)
_VOLUME_RE = re.compile(r"^vol\b", re.I)
_NUMBER_FALLBACK_RE = re.compile(r"c(\d+(?:\.\d+)?)/?$", re.I)


def _chapter_number(name_attr: str, chapter_id: str) -> float | None:
    """Chapter number from the site's own ``name`` attribute.

    MangaTown stamps every chapter anchor with ``name="700.6"`` -- the site's
    own numbering, which is exactly what ``chapter_number`` is specified to
    be. The URL tail (``.../c700.6/``) is only a fallback for rows where the
    attribute is blank.
    """
    for candidate in (name_attr.strip(), ""):
        if candidate:
            try:
                return float(candidate)
            except ValueError:
                break
    tail = _NUMBER_FALLBACK_RE.search(chapter_id)
    if tail:
        try:
            return float(tail.group(1))
        except ValueError:
            return None
    return None


def parse_chapters(html: str, series_id: str) -> list[Chapter]:
    """Chapters oldest-first, so ``chapters[-1]`` is the newest release."""
    block = _CHAPTER_UL_RE.search(html)
    if not block:
        return []

    prefix = f"{series_id}/"
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_id, name_attr, link_text, tail in _CHAPTER_ROW_RE.findall(block.group(1)):
        chapter_id = chapter_id.strip()
        # Guard against the "related series" rails that share this markup.
        if chapter_id != series_id and not chapter_id.startswith(prefix):
            continue
        if chapter_id in seen:
            continue
        seen.add(chapter_id)

        label = _clean(link_text)
        subtitle = ""
        release_date: str | None = None
        for span_class, span_text in _SPAN_RE.findall(tail):
            text = _clean(span_text)
            if not text:
                continue
            if "time" in (span_class or "").lower():
                release_date = text
            elif not _VOLUME_RE.match(text) and not subtitle:
                subtitle = text

        title = f"{label} - {subtitle}" if label and subtitle else (label or subtitle)
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=title or chapter_id,
                number=_chapter_number(name_attr, chapter_id),
                page_count=0,
                release_date=release_date,
            )
        )

    # The page lists newest-first, so reversing gives reading order -- but
    # MangaTown's own list is not perfectly ordered (Naruto files v51/c483
    # ahead of v52/c448). Sorting on the site's own chapter numbers fixes the
    # reading order and makes chapters[-1] genuinely the newest release.
    # Python's sort is stable, so equal/unnumbered rows keep document order,
    # and unnumbered rows sink to the end rather than colliding at 0.
    chapters.reverse()
    chapters.sort(key=lambda c: (c.number is None, c.number if c.number is not None else 0.0))
    return chapters


# --------------------------------------------------------------------------
# chapter pages
# --------------------------------------------------------------------------

_TOTAL_PAGES_RE = re.compile(r"var\s+total_pages\s*=\s*(\d+)", re.I)
_CHAPTER_DBID_RE = re.compile(r"var\s+chapter_id\s*=\s*(\d+)", re.I)


def parse_chapter_meta(html: str) -> tuple[int, int] | None:
    """``(total_pages, chapter_db_id)`` from a chapter page's inline script.

    Both numbers are what make the fast path possible: the reader never has to
    walk the chapter to discover how long it is, and ``chapter_db_id`` is the
    ``cid`` that ``chapterfun.ashx`` wants.
    """
    total = _TOTAL_PAGES_RE.search(html)
    dbid = _CHAPTER_DBID_RE.search(html)
    if not total or not dbid:
        return None
    pages = int(total.group(1))
    if pages <= 0:
        return None
    return pages, int(dbid.group(1))


#: The single page image rendered server-side on a chapter page. Only used as
#: the fallback when chapterfun.ashx is unavailable.
_INLINE_IMAGE_RE = re.compile(r'<img\s+src="([^"]+)"\s+id="image"', re.I)


def parse_inline_image(html: str) -> str | None:
    match = _INLINE_IMAGE_RE.search(html)
    return _absolute(match.group(1)) if match else None


# -- packed-JS image batch --------------------------------------------------
#
# chapterfun.ashx answers with the classic Dean Edwards packer:
#   eval(function(p,a,c,k,e,d){...}('<body>',<radix>,<count>,'w1|w2|...'.split('|'),0,{}))
# Unpacking it is a pure string substitution -- no JS engine involved.

_PACKED_ARGS_RE = re.compile(
    r"\}\s*\(\s*'(.*)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'(.*?)'\s*\.\s*split\s*\(\s*'\|'\s*\)",
    re.S,
)
_WORD_RE = re.compile(r"\b\w+\b")
_PIX_RE = re.compile(r'pix\s*=\s*"([^"]*)"')
_PVALUE_RE = re.compile(r"pvalue\s*=\s*\[([^\]]*)\]")
_QUOTED_RE = re.compile(r'"([^"]*)"')

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def _to_base(number: int, radix: int) -> str:
    if number == 0:
        return "0"
    out = ""
    while number:
        out = _BASE36[number % radix] + out
        number //= radix
    return out


def unpack_packed_js(payload: str) -> str:
    """Reverse the p/a/c/k/e/d packer. Returns "" when the shape is unknown."""
    match = _PACKED_ARGS_RE.search(payload)
    if not match:
        return ""
    body, radix, count, words = (
        match.group(1),
        int(match.group(2)),
        int(match.group(3)),
        match.group(4).split("|"),
    )
    if radix < 2 or radix > 36 or count < 0:
        return ""
    table: dict[str, str] = {}
    for index in range(count):
        key = _to_base(index, radix)
        word = words[index] if index < len(words) else ""
        table[key] = word or key
    body = body.replace("\\'", "'").replace("\\\\", "\\")
    return _WORD_RE.sub(lambda m: table.get(m.group(0), m.group(0)), body)


def parse_image_batch(payload: str) -> list[str]:
    """Absolute image URLs from one ``chapterfun.ashx`` response.

    The endpoint answers with a *look-ahead* batch -- the requested page plus
    the next one -- which is what lets a whole chapter be resolved in
    ceil(pages / 2) tiny requests instead of one full page fetch each.
    """
    script = unpack_packed_js(payload)
    if not script:
        return []
    pix_match = _PIX_RE.search(script)
    pvalue_match = _PVALUE_RE.search(script)
    if not pvalue_match:
        return []
    base = pix_match.group(1) if pix_match else ""
    urls: list[str] = []
    for name in _QUOTED_RE.findall(pvalue_match.group(1)):
        if not name:
            continue
        urls.append(_absolute(f"{base}{name}" if name.startswith("/") else name))
    return urls


def build_pages(chapter_id: str, urls: dict[int, str]) -> list[Page]:
    """Page objects for the resolved image URLs, ordered by page number."""
    return [
        Page(
            id=make_page_id(chapter_id, number),
            chapter_id=chapter_id,
            number=number,
            remote_url=urls[number],
        )
        for number in sorted(urls)
    ]
