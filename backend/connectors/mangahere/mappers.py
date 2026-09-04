"""Map MangaHere HTML pages to normalized connector models.

Everything here was derived from documents captured on the production VPS
(see ``tests/fixtures/mangahere/``). MangaHere runs the long-lived "dm5"
engine, so three things are unusual enough to be worth stating up front:

1. **The sort flag must be a BARE query key.** ``/directory/2.htm?rating``
   re-sorts; ``/directory/2.htm?rating=`` is silently ignored and the site
   serves its default popularity ordering. Verified from the VPS: with the
   trailing ``=`` the first three slugs were identical to the unsorted page.
   That is why sorting lives in the *path* here and never in ``params`` --
   ``httpx`` would render a valueless param as ``rating=``.
2. **A chapter's page images are obfuscated with a packer.** Long-strip
   chapters carry every image URL inline in a ``p,a,c,k,e,d`` block
   (``newImgs``); classic manga instead carry a ``guidkey`` that unlocks
   ``chapterfun.ashx``, which hands back two image URLs per call.
3. **MangaHere appends its own advert as the last image of every chapter.**
   On long-strip chapters the site marks it itself (``_tpimagearr`` entries
   carry ``"d": 2``); on classic chapters nothing marks it, but it is always
   the final image of ``imagecount``. Verified byte-identical (md5
   ``a15f2b2e0ebd6bdda7c338135caa8398``, 206523 bytes) as the last image of
   seven chapters across seven different series.
"""

from __future__ import annotations

import html as html_module
import json
import re
from urllib.parse import quote

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://www.mangahere.cc"

#: Browse/genre listings render 70 cards per page; search renders 12.
PAGE_SIZE = 70
SEARCH_PAGE_SIZE = 12

#: ``sort`` id -> (listing base path, bare query flag or None).
#: The ids are the ``BrowseMode`` ids the connector advertises. Every one of
#: them must produce a genuinely different request, which is what
#: ``test_every_browse_mode_requests_a_distinct_path`` pins down.
SORT_TO_LISTING: dict[str, tuple[str, str | None]] = {
    "default": ("/directory", None),  # popularity (the site's own default)
    "latest": ("/new", None),  # "New Updated"
    "rating": ("/directory", "rating"),
    "chapters": ("/directory", "latest"),  # site labels this "Chapters"
    "alphabetical": ("/directory", "az"),
    "completed": ("/completed", None),
    "ongoing": ("/on_going", None),
}

#: Genre slugs the site exposes on its own filter bar, in its own order.
GENRE_SLUGS: tuple[tuple[str, str], ...] = (
    ("action", "Action"),
    ("adventure", "Adventure"),
    ("comedy", "Comedy"),
    ("fantasy", "Fantasy"),
    ("historical", "Historical"),
    ("horror", "Horror"),
    ("martial-arts", "Martial Arts"),
    ("mystery", "Mystery"),
    ("romance", "Romance"),
    ("shounen-ai", "Shounen Ai"),
    ("supernatural", "Supernatural"),
    ("drama", "Drama"),
    ("shounen", "Shounen"),
    ("school-life", "School Life"),
    ("shoujo", "Shoujo"),
    ("gender-bender", "Gender Bender"),
    ("josei", "Josei"),
    ("psychological", "Psychological"),
    ("seinen", "Seinen"),
    ("slice-of-life", "Slice of Life"),
    ("sci-fi", "Sci-fi"),
    ("ecchi", "Ecchi"),
    ("harem", "Harem"),
    ("shoujo-ai", "Shoujo Ai"),
    ("yuri", "Yuri"),
    ("tragedy", "Tragedy"),
    ("sports", "Sports"),
    ("one-shot", "One Shot"),
    ("mecha", "Mecha"),
    ("webtoons", "Webtoons"),
)

_VALID_GENRES = frozenset(slug for slug, _label in GENRE_SLUGS)

# --- listing cards ----------------------------------------------------------

_CARD_SPLIT_RE = re.compile(r"<li[\s>]")

_LIST1_COVER_RE = re.compile(r'<img class="manga-list-1-cover" src="([^"]+)"')
_LIST1_TITLE_RE = re.compile(
    r'<p class="manga-list-1-item-title">\s*<a href="/manga/([^"/]+)/?"[^>]*>(.*?)</a>',
    re.S,
)
_LIST1_LATEST_RE = re.compile(
    r'<p class="manga-list-1-item-subtitle">\s*<a href="[^"]*"[^>]*>(.*?)</a>', re.S
)

_LIST4_COVER_RE = re.compile(r'<img class="manga-list-4-cover" src="([^"]+)"')
_LIST4_TITLE_RE = re.compile(
    r'<p class="manga-list-4-item-title">\s*<a href="/manga/([^"/]+)/?"[^>]*>(.*?)</a>',
    re.S,
)
_LIST4_STATUS_RE = re.compile(
    r'<p class="manga-list-4-show-tag-list-2">\s*<a[^>]*>(.*?)</a>', re.S
)
_LIST4_AUTHOR_RE = re.compile(
    r'<p class="manga-list-4-item-tip">Author:(.*?)</p>', re.S
)
_LIST4_LATEST_RE = re.compile(
    r'<p class="manga-list-4-item-tip">Latest Chapter:\s*<a[^>]*>(.*?)</a>', re.S
)
_LIST4_PLAIN_TIP_RE = re.compile(
    r'<p class="manga-list-4-item-tip">((?:(?!<a)[^<])*?)</p>', re.S
)

_ANCHOR_TEXT_RE = re.compile(r"<a[^>]*>(.*?)</a>", re.S)

# --- pager ------------------------------------------------------------------

_PAGER_BLOCK_RE = re.compile(r'<div class="pager-list-left">(.*?)</div>', re.S)
_PAGER_HTM_RE = re.compile(r"/(\d+)\.htm")
_PAGER_QUERY_RE = re.compile(r"[?&]page=(\d+)")

# --- series detail ----------------------------------------------------------

_DETAIL_TITLE_RE = re.compile(
    r'<span class="detail-info-right-title-font">(.*?)</span>', re.S
)
_DETAIL_STATUS_RE = re.compile(
    r'<span class="detail-info-right-title-tip">(.*?)</span>', re.S
)
_DETAIL_COVER_RE = re.compile(r'<img class="detail-info-cover-img" src="([^"]+)"')
_DETAIL_AUTHOR_BLOCK_RE = re.compile(
    r'<p class="detail-info-right-say">(.*?)</p>', re.S
)
_DETAIL_GENRE_BLOCK_RE = re.compile(
    r'<p class="detail-info-right-tag-list">(.*?)</p>', re.S
)
_DETAIL_FULL_DESC_RE = re.compile(
    r'<p[^>]*class="fullcontent"[^>]*>(.*?)</p>', re.S
)
_DETAIL_SHORT_DESC_RE = re.compile(
    r'<p class="detail-info-right-content">(.*?)(?:<a\s|</p>)', re.S
)

_CHAPTER_ROW_RE = re.compile(
    r'<a\s+href="(/manga/[^"]+)"[^>]*>\s*'
    r'<div class="detail-main-list-main">\s*'
    r'<p class="title3">(.*?)</p>\s*'
    r'<p class="title2">(.*?)</p>',
    re.S,
)

_CHAPTER_NUMBER_RE = re.compile(r"(?:^|/)c(\d+(?:\.\d+)?)$", re.I)

#: The notice the site substitutes for a series or chapter it has taken down
#: on a copyright claim (Shueisha titles like Onepunch-Man and Naruto). The
#: chapter page still ships a ``chapterid`` and an ``imagecount``, so nothing
#: except this string distinguishes it from a readable chapter.
_REMOVED_MARKER = "removed all content"

# --- packed page scripts ----------------------------------------------------

#: A JS single-quoted string, honouring backslash escapes. Anchoring on this
#: rather than ``.*?`` is what keeps the payload from being cut short at the
#: first escaped quote inside an image URL.
_JS_STRING = r"(?:[^'\\]|\\.)*"
_PACKED_RE = re.compile(
    r"\}\('(?P<payload>" + _JS_STRING + r")',"
    r"(?P<radix>\d+),(?P<count>\d+),"
    r"'(?P<words>" + _JS_STRING + r")'\.split\('\|'\)",
    re.S,
)
_PACKED_START_RE = re.compile(r"eval\(function\(p,a,c,k,e,d\)")

#: Guard against a hostile or corrupt payload spinning the dictionary loop.
_MAX_PACKED_WORDS = 20000

_WORD_RE = re.compile(r"\b\w+\b")

_NEWIMGS_URL_RE = re.compile(r"'((?:https?:)?//[^']+)'")
_TPIMAGEARR_RE = re.compile(r"_tpimagearr\s*=\s*(\[.*?\])\s*;", re.S)
_IMAGECOUNT_RE = re.compile(r"var\s+imagecount\s*=\s*(\d+)")
_CHAPTERID_RE = re.compile(r"var\s+chapterid\s*=\s*(\d+)")
_GUIDKEY_RE = re.compile(r"guidkey\s*=\s*([^;]+);")
_QUOTED_FRAGMENT_RE = re.compile(r"'([^']*)'")

_PIX_RE = re.compile(r'var\s+pix\s*=\s*"([^"]*)"')
_FIRST_PREFIX_RE = re.compile(r'i\s*==\s*0\)\s*\{\s*pvalue\[i\]\s*=\s*"([^"]*)"')
_PVALUE_BLOCK_RE = re.compile(r"pvalue\s*=\s*\[(.*?)\]", re.S)
_PVALUE_ITEM_RE = re.compile(r'"([^"]*)"')

#: The placeholder the site returns from ``chapterfun.ashx`` when a chapter is
#: not actually servable (taken down, or the key was rejected). Serving it
#: would show the reader a "warning" graphic instead of failing honestly.
_PLACEHOLDER_MARKERS = ("/images/war.jpg", "/images/nopicture")


# --- small helpers ----------------------------------------------------------


def _clean_text(value: str) -> str:
    """Strip tags, collapse whitespace and decode entities."""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return html_module.unescape(re.sub(r"\s+", " ", without_tags)).strip()


def absolute_url(url: str) -> str:
    """Normalize a site URL to an absolute ``https://`` one.

    MangaHere mixes absolute ``https://fmcdn.mangahere.com/...`` covers with
    protocol-relative ``//zjcdn.mangahere.org/...`` page images; the image
    proxy rejects anything that is not HTTPS.
    """
    url = url.strip()
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("http://"):
        return f"https://{url[len('http://'):]}"
    if url.startswith("https://"):
        return url
    return f"{SITE_BASE}/{url.lstrip('/')}"


def normalize_series_key(series_key: str) -> str:
    """Reduce whatever the caller passed to the bare site slug.

    Identity keys are opaque, so this only trims the wrappers our own URLs
    put around them (a leading ``/manga/``, surrounding slashes) rather than
    interpreting the slug itself.
    """
    value = series_key.strip().strip("/")
    if value.startswith("manga/"):
        value = value[len("manga/") :]
    return value.strip("/")


def normalize_chapter_key(chapter_key: str) -> str:
    """Reduce a chapter identity to ``<slug>[/vNN]/cNNN``."""
    value = chapter_key.strip().strip("/")
    if value.startswith("manga/"):
        value = value[len("manga/") :]
    value = re.sub(r"/\d+\.html?$", "", value)
    return value.strip("/")


def series_path(series_key: str) -> str:
    return f"/manga/{normalize_series_key(series_key)}/"


def chapter_path(chapter_key: str) -> str:
    return f"/manga/{normalize_chapter_key(chapter_key)}/1.html"


def chapterfun_path(chapter_key: str) -> str:
    return f"/manga/{normalize_chapter_key(chapter_key)}/chapterfun.ashx"


def make_page_id(chapter_key: str, page_number: int) -> str:
    return f"{chapter_key}:{page_number}"


def page_id_chapter_key(page_id: str) -> str | None:
    """Recover the chapter identity a page id was minted from.

    ``rpartition`` (not ``split``) because a chapter key legitimately holds
    slashes and could in principle hold a colon -- only the LAST colon is the
    separator this module wrote.
    """
    if ":" not in page_id:
        return None
    chapter_key, _, number = page_id.rpartition(":")
    if not chapter_key or not number.isdigit():
        return None
    return chapter_key


def parse_chapter_number(chapter_key: str) -> float | None:
    """Read the site's own chapter number off the tail of a chapter key.

    ``solo_leveling/c202`` -> 202.0, ``solo_leveling/c200.5`` -> 200.5, and
    the volume form ``pluto/v08/c065`` -> 65.0. Returns ``None`` when the tail
    is not a ``cNNN`` segment so the caller can fall back to position.
    """
    match = _CHAPTER_NUMBER_RE.search(normalize_chapter_key(chapter_key))
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def normalize_sort(sort: str | None) -> str:
    if not sort or sort not in SORT_TO_LISTING:
        return "default"
    return sort


def listing_path(page: int, *, sort: str | None = None, genre: str | None = None) -> str:
    """Build a browse path, with the sort flag baked in as a BARE query key.

    ``/directory/``, ``/directory/3.htm``, ``/directory/3.htm?rating``,
    ``/action/2.htm``. See the module docstring for why the flag cannot be
    passed through ``params``.
    """
    page = max(1, page)
    if genre:
        base, flag = f"/{genre}", SORT_TO_LISTING[normalize_sort(sort)][1]
    else:
        base, flag = SORT_TO_LISTING[normalize_sort(sort)]
    path = f"{base}/" if page == 1 else f"{base}/{page}.htm"
    return f"{path}?{flag}" if flag else path


def is_valid_genre(genre: str) -> bool:
    return genre.strip().strip("/").lower() in _VALID_GENRES


def search_path(query: str, page: int) -> str:
    """Build the search path.

    Note the endpoint is ``/search`` and NOT ``/search.php``: robots.txt
    disallows ``/search.php`` (and ``/bookmark/``) while allowing everything
    else, so the connector must never reach for the legacy path.
    """
    return f"/search?title={quote(query.strip())}&page={max(1, page)}"


def is_removed(html: str) -> bool:
    """True when the page is MangaHere's copyright-takedown notice."""
    return _REMOVED_MARKER in html


# --- listing parsing --------------------------------------------------------


def _max_pager_page(html: str, *, query_style: bool) -> int:
    block = _PAGER_BLOCK_RE.search(html)
    if block is None:
        return 1
    pattern = _PAGER_QUERY_RE if query_style else _PAGER_HTM_RE
    numbers = [int(value) for value in pattern.findall(block.group(1))]
    return max(numbers) if numbers else 1


def _card_fragments(html: str, marker: str) -> list[str]:
    return [chunk for chunk in _CARD_SPLIT_RE.split(html) if marker in chunk]


def parse_series_cards(html: str) -> list[Series]:
    """Parse the ``manga-list-1`` cards used by directory and genre pages."""
    items: list[Series] = []
    seen: set[str] = set()
    for fragment in _card_fragments(html, "manga-list-1-item-title"):
        title_match = _LIST1_TITLE_RE.search(fragment)
        if title_match is None:
            continue
        series_key, raw_title = title_match.group(1), title_match.group(2)
        if series_key in seen:
            continue
        seen.add(series_key)
        cover_match = _LIST1_COVER_RE.search(fragment)
        latest_match = _LIST1_LATEST_RE.search(fragment)
        items.append(
            Series(
                id=series_key,
                title=_clean_text(raw_title),
                canonical_path=series_path(series_key),
                cover_url=absolute_url(cover_match.group(1)) if cover_match else None,
                latest_chapter=_clean_text(latest_match.group(1)) if latest_match else None,
            )
        )
    return items


def parse_series_list(
    html: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html)
    total_pages = max(_max_pager_page(html, query_style=False), page)
    if page >= total_pages:
        total = (total_pages - 1) * page_size + len(items)
    else:
        total = total_pages * page_size
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=page < total_pages and bool(items),
    )


def parse_search_results(
    html: str,
    *,
    page: int,
    page_size: int = SEARCH_PAGE_SIZE,
) -> PaginatedSeriesList:
    """Parse the ``manga-list-4`` cards the search endpoint renders.

    Search cards are richer than browse cards -- author, status, latest
    chapter and a description snippet are all present -- so this fills them
    in and the Sources UI shows a useful result row without a detail fetch.
    """
    items: list[Series] = []
    seen: set[str] = set()
    for fragment in _card_fragments(html, "manga-list-4-item-title"):
        title_match = _LIST4_TITLE_RE.search(fragment)
        if title_match is None:
            continue
        series_key, raw_title = title_match.group(1), title_match.group(2)
        if series_key in seen:
            continue
        seen.add(series_key)
        cover_match = _LIST4_COVER_RE.search(fragment)
        status_match = _LIST4_STATUS_RE.search(fragment)
        latest_match = _LIST4_LATEST_RE.search(fragment)
        author_match = _LIST4_AUTHOR_RE.search(fragment)
        authors = (
            [_clean_text(name) for name in _ANCHOR_TEXT_RE.findall(author_match.group(1))]
            if author_match
            else []
        )
        description = None
        for tip in _LIST4_PLAIN_TIP_RE.findall(fragment):
            text = _clean_text(tip)
            if text and not text.startswith(("Author:", "Latest Chapter:")):
                description = text
                break
        items.append(
            Series(
                id=series_key,
                title=_clean_text(raw_title),
                canonical_path=series_path(series_key),
                cover_url=absolute_url(cover_match.group(1)) if cover_match else None,
                status=_clean_text(status_match.group(1)) if status_match else None,
                latest_chapter=_clean_text(latest_match.group(1)) if latest_match else None,
                author=", ".join(name for name in authors if name) or None,
                description=description,
            )
        )
    total_pages = max(_max_pager_page(html, query_style=True), page)
    if page >= total_pages:
        total = (total_pages - 1) * page_size + len(items)
    else:
        total = total_pages * page_size
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=page < total_pages and bool(items),
    )


# --- series detail ----------------------------------------------------------


def parse_series_detail(html: str, series_key: str) -> Series | None:
    """Parse a ``/manga/<slug>/`` document.

    Returns ``None`` for anything that is not a real detail page -- a
    taken-down series, or the search page the site 302s an unknown slug to.
    """
    if is_removed(html):
        return None
    title_match = _DETAIL_TITLE_RE.search(html)
    if title_match is None:
        return None
    title = _clean_text(title_match.group(1))
    if not title:
        return None

    cover_match = _DETAIL_COVER_RE.search(html)
    status_match = _DETAIL_STATUS_RE.search(html)

    authors: list[str] = []
    author_block = _DETAIL_AUTHOR_BLOCK_RE.search(html)
    if author_block:
        authors = [
            name
            for name in (
                _clean_text(raw) for raw in _ANCHOR_TEXT_RE.findall(author_block.group(1))
            )
            if name
        ]

    genres: tuple[str, ...] = ()
    genre_block = _DETAIL_GENRE_BLOCK_RE.search(html)
    if genre_block:
        genres = tuple(
            name
            for name in (
                _clean_text(raw) for raw in _ANCHOR_TEXT_RE.findall(genre_block.group(1))
            )
            if name
        )

    description = None
    full_desc = _DETAIL_FULL_DESC_RE.search(html)
    if full_desc:
        description = _clean_text(full_desc.group(1))
    else:
        short_desc = _DETAIL_SHORT_DESC_RE.search(html)
        if short_desc:
            description = _clean_text(short_desc.group(1))

    return Series(
        id=series_key,
        title=title,
        canonical_path=series_path(series_key),
        cover_url=absolute_url(cover_match.group(1)) if cover_match else None,
        status=_clean_text(status_match.group(1)) if status_match else None,
        author=", ".join(authors) or None,
        genres=genres,
        description=description or None,
    )


def parse_chapters(html: str, series_key: str) -> list[Chapter]:
    """Parse the chapter rows embedded in the series detail document.

    MangaHere ships the WHOLE chapter list inside the detail page (the older
    entries merely carry ``style='display:none'``), so this never needs a
    second request -- the connector shares one fetch between ``get_series``
    and ``get_chapters``.
    """
    series_key = normalize_series_key(series_key)
    prefix = f"{series_key}/"
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for href, raw_title, raw_date in _CHAPTER_ROW_RE.findall(html):
        chapter_key = normalize_chapter_key(href)
        if not chapter_key.startswith(prefix) or chapter_key in seen:
            continue
        seen.add(chapter_key)
        rows.append((chapter_key, _clean_text(raw_title), _clean_text(raw_date)))

    total = len(rows)
    chapters: list[Chapter] = []
    for index, (chapter_key, title, release_date) in enumerate(rows):
        # The site lists newest first, so distance from the bottom is the
        # chapter's ordinal -- the fallback when a key does not end in cNNN.
        ordinal = total - index
        number = parse_chapter_number(chapter_key)
        chapters.append(
            Chapter(
                id=chapter_key,
                series_id=series_key,
                title=title or chapter_key.rsplit("/", 1)[-1],
                number=number if number is not None else float(ordinal),
                page_count=0,
                release_date=release_date or None,
            )
        )
    chapters.sort(key=lambda chapter: (chapter.number if chapter.number is not None else 0.0))
    return chapters


# --- packed chapter scripts -------------------------------------------------


def _base36(value: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out = ""
    while value:
        out = digits[value % 36] + out
        value //= 36
    return out


def _encode_index(index: int, radix: int) -> str:
    """Reproduce the packer's own ``e(c)`` index->token encoding."""
    head = "" if index < radix else _encode_index(index // radix, radix)
    remainder = index % radix
    tail = chr(remainder + 29) if remainder > 35 else _base36(remainder)
    return head + tail


def _unescape_js(value: str) -> str:
    return value.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")


def unpack_packed_script(source: str) -> str | None:
    """Decode one ``eval(function(p,a,c,k,e,d){...})`` block.

    Faithfully reproduces the packer, including the detail that an EMPTY
    dictionary word means "this token decodes to itself" -- that is what makes
    ``.../202.0/...`` come out right instead of ``.../202./...``.
    """
    match = _PACKED_RE.search(source)
    if match is None:
        return None
    radix = int(match.group("radix"))
    count = int(match.group("count"))
    if radix < 2 or count < 1 or count > _MAX_PACKED_WORDS:
        return None
    words = match.group("words").split("|")
    payload = _unescape_js(match.group("payload"))

    dictionary: dict[str, str] = {}
    for index in range(count):
        token = _encode_index(index, radix)
        word = words[index] if index < len(words) else ""
        dictionary[token] = word or token

    return _WORD_RE.sub(lambda m: dictionary.get(m.group(0), m.group(0)), payload)


def iter_packed_scripts(html: str) -> list[str]:
    """Decode every packed block in a document, in document order."""
    decoded: list[str] = []
    for match in _PACKED_START_RE.finditer(html):
        end = html.find("</script>", match.start())
        block = html[match.start() : end if end != -1 else match.start() + 200000]
        result = unpack_packed_script(block)
        if result:
            decoded.append(result)
    return decoded


def parse_image_info(html: str) -> list[dict]:
    """Parse ``_tpimagearr`` -- the site's own per-image ``{w,h,d}`` metadata.

    ``d == 2`` marks an appended advert rather than a page of the chapter;
    ``w``/``h`` are the real pixel dimensions, which the reader can use to
    reserve layout space before an image arrives.
    """
    match = _TPIMAGEARR_RE.search(html)
    if match is None:
        return []
    try:
        parsed = json.loads(match.group(1))
    except (ValueError, TypeError):
        return []
    return [entry for entry in parsed if isinstance(entry, dict)]


def _is_placeholder(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _trim_trailing_adverts(urls: list[str], info: list[dict]) -> list[str]:
    """Drop the advert images MangaHere staples onto the end of a chapter.

    Uses the site's OWN marker when it is present (``_tpimagearr`` ``d == 2``)
    and only ever trims from the end, so a mid-chapter entry is never lost
    even if ``d`` one day means something else. When there is no metadata the
    caller falls back to ``drop_last_advert`` below.
    """
    if len(info) != len(urls):
        return urls
    end = len(urls)
    while end > 1 and info[end - 1].get("d") == 2:
        end -= 1
    return urls[:end]


def drop_last_advert(urls: list[str]) -> list[str]:
    """Drop the single advert image that ends every classic-manga chapter.

    Classic (``chapterfun.ashx``) chapters carry no ``_tpimagearr``, but the
    site still counts its own advert inside ``imagecount`` as the final
    image. Verified from the VPS across seven chapters of seven different
    series: the last image was byte-identical every time (206523-byte PNG,
    md5 ``a15f2b2e0ebd6bdda7c338135caa8398``, a "MORE WONDERFUL MANGA HERE"
    app advert). Never trims a one-image chapter.
    """
    return urls[:-1] if len(urls) > 1 else urls


def extract_inline_page_urls(html: str) -> list[str]:
    """Return every page image URL a long-strip chapter carries inline.

    This is the fast path and by far the nicer one: the whole chapter costs a
    single HTTP request because the site embeds ``newImgs`` in the reader
    document itself.
    """
    for decoded in iter_packed_scripts(html):
        if "newImgs" not in decoded:
            continue
        urls = [
            absolute_url(url)
            for url in _NEWIMGS_URL_RE.findall(decoded)
            if not _is_placeholder(url)
        ]
        if urls:
            return _trim_trailing_adverts(urls, parse_image_info(html))
    return []


def extract_chapterfun_context(html: str) -> tuple[str, str, int] | None:
    """Return ``(chapter_numeric_id, guidkey, image_count)`` for the slow path.

    Classic manga hide their image URLs behind ``chapterfun.ashx``; the key
    that unlocks it is assembled one character at a time inside a packed
    block so it never appears literally in the document.
    """
    chapter_id = _CHAPTERID_RE.search(html)
    image_count = _IMAGECOUNT_RE.search(html)
    if chapter_id is None or image_count is None:
        return None
    for decoded in iter_packed_scripts(html):
        assignment = _GUIDKEY_RE.search(decoded)
        if assignment is None:
            continue
        key = "".join(_QUOTED_FRAGMENT_RE.findall(assignment.group(1)))
        if key:
            return chapter_id.group(1), key, int(image_count.group(1))
    return None


def parse_chapterfun_response(script: str) -> list[str]:
    """Decode one ``chapterfun.ashx`` reply into absolute image URLs.

    The reply defines ``pix`` (the shared directory) and ``pvalue`` (the file
    names for the requested page and the one after it). Index 0 gets its own
    prefix in the site's own loop, so that prefix is honoured here rather than
    assumed equal to ``pix``.
    """
    decoded = unpack_packed_script(script)
    if not decoded:
        return []
    block = _PVALUE_BLOCK_RE.search(decoded)
    if block is None:
        return []
    names = _PVALUE_ITEM_RE.findall(block.group(1))
    if not names:
        return []
    pix = _PIX_RE.search(decoded)
    first_prefix = _FIRST_PREFIX_RE.search(decoded)
    base = pix.group(1) if pix else ""
    head = first_prefix.group(1) if first_prefix else base
    urls: list[str] = []
    for index, name in enumerate(names):
        prefix = head if index == 0 else base
        candidate = f"{prefix}{name}"
        if _is_placeholder(candidate):
            return []
        urls.append(absolute_url(candidate))
    return urls


def build_pages(chapter_key: str, urls: list[str], info: list[dict]) -> list[Page]:
    """Turn resolved image URLs into ``Page`` models, with dimensions if known."""
    pages: list[Page] = []
    for index, url in enumerate(urls):
        entry = info[index] if index < len(info) else {}
        width = entry.get("w") if isinstance(entry.get("w"), int) else None
        height = entry.get("h") if isinstance(entry.get("h"), int) else None
        pages.append(
            Page(
                id=make_page_id(chapter_key, index + 1),
                chapter_id=chapter_key,
                number=index + 1,
                remote_url=url,
                width=width,
                height=height,
            )
        )
    return pages
