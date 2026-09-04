"""Map Manga Fox (fanfox.net) HTML pages to normalized connector models.

Markup mapped from captures taken 2026-09-04 FROM THE VPS (production's exact
egress and TLS stack). Fanfox is the long-running MangaFox codebase: server-
rendered HTML with a jQuery reader, so everything here is plain regex over the
document — the house convention for this codebase.

The one non-obvious part is the reader. Fanfox never puts page images in the
markup; it ships them inside a Dean-Edwards ``eval(function(p,a,c,k,e,d))``
packed script, and it does so in TWO different shapes (see ``unpack_packed``
and the two ``parse_*_pages`` functions below).
"""

from __future__ import annotations

import html as html_mod
import re

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://fanfox.net"

#: The directory listing renders exactly 70 cards per page.
PAGE_SIZE = 70
#: ``/search`` renders 12 result rows per page.
SEARCH_PAGE_SIZE = 12

#: Hosts that serve fanfox artwork. ``fmcdn.mfcdn.net`` carries cover art,
#: ``zjcdn.mangafox.me`` the chapter page images. Both are token+ttl signed.
IMAGE_HOSTS = frozenset({"mfcdn.net", "mangafox.me", "fanfox.net"})


# --- sorting / browse modes -------------------------------------------------

#: The directory's own sort links are bare query flags: ``/directory/?latest``.
#: The empty string is the site default (no flag at all).
SORT_TO_FLAG: dict[str, str] = {
    "default": "",
    "latest": "latest",
    "news": "news",
    "rating": "rating",
    "az": "az",
}


def normalize_sort(sort: str | None) -> str:
    if not sort:
        return "default"
    return sort if sort in SORT_TO_FLAG else "default"


#: Genre/status slugs the directory exposes as ``/directory/<slug>/``.
GENRE_SLUGS: tuple[tuple[str, str], ...] = (
    ("action", "Action"),
    ("adventure", "Adventure"),
    ("comedy", "Comedy"),
    ("drama", "Drama"),
    ("fantasy", "Fantasy"),
    ("gender-bender", "Gender Bender"),
    ("harem", "Harem"),
    ("historical", "Historical"),
    ("horror", "Horror"),
    ("josei", "Josei"),
    ("martial-arts", "Martial Arts"),
    ("mecha", "Mecha"),
    ("mystery", "Mystery"),
    ("one-shot", "One Shot"),
    ("psychological", "Psychological"),
    ("romance", "Romance"),
    ("school-life", "School Life"),
    ("sci-fi", "Sci-fi"),
    ("seinen", "Seinen"),
    ("shoujo", "Shoujo"),
    ("shoujo-ai", "Shoujo Ai"),
    ("shounen", "Shounen"),
    ("shounen-ai", "Shounen Ai"),
    ("slice-of-life", "Slice of Life"),
    ("sports", "Sports"),
    ("supernatural", "Supernatural"),
    ("tragedy", "Tragedy"),
    ("webtoons", "Webtoons"),
    ("completed", "Completed"),
    ("ongoing", "Ongoing"),
    ("updated", "Recently Updated"),
)

#: Adult-leaning directory slugs. Kept out of ``GENRE_SLUGS`` so the browse UI
#: of a general-audience source does not advertise them; the connector is not
#: marked MATURE because fanfox is overwhelmingly a mainstream catalog.
_ADULT_GENRE_SLUGS = frozenset(
    {"adult", "doujinshi", "ecchi", "lolicon", "mature", "shotacon", "smut", "yaoi", "yuri"}
)


def listing_path(page: int, *, genre: str | None = None, sort: str | None = None) -> str:
    """Path for the directory listing.

    Page 1 is ``/directory/`` (or ``/directory/<genre>/``); later pages append
    ``<N>.html``. The sort flag is a bare query key appended verbatim.
    """
    page = max(1, page)
    prefix = "/directory/"
    if genre:
        prefix = f"/directory/{genre.strip().strip('/')}/"
    path = prefix if page == 1 else f"{prefix}{page}.html"
    flag = SORT_TO_FLAG.get(normalize_sort(sort), "")
    return f"{path}?{flag}" if flag else path


def search_path() -> str:
    """robots.txt disallows ``/search.php`` but explicitly allows ``/search``."""
    return "/search"


def search_params(query: str, page: int) -> dict[str, object]:
    params: dict[str, object] = {"title": query.strip()}
    if page > 1:
        params["page"] = page
    return params


# --- identity ---------------------------------------------------------------


def normalize_series_key(value: str) -> str:
    """Reduce any fanfox series reference to its opaque slug.

    Accepts the bare slug, ``manga/<slug>``, a site-relative path, or a full
    URL. The result is stored and passed back raw — never parsed.
    """
    text = html_mod.unescape(value or "").strip()
    text = re.sub(r"^https?://[^/]+", "", text)
    text = text.strip().strip("/")
    if text.startswith("manga/"):
        text = text[len("manga/") :]
    return text.strip("/")


def normalize_chapter_key(value: str) -> str:
    """Reduce a chapter reference to its opaque key.

    A fanfox chapter link is ``/manga/<slug>[/<volume>]/<chapter>/1.html``.
    The key is everything between ``/manga/`` and the trailing page file, so it
    MAY contain slashes (``one_piece/vTBE/c1100``) and is treated as opaque.
    """
    text = html_mod.unescape(value or "").strip()
    text = re.sub(r"^https?://[^/]+", "", text)
    text = text.strip().strip("/")
    if text.startswith("manga/"):
        text = text[len("manga/") :]
    text = re.sub(r"/\d+\.html?$", "", text)
    return text.strip("/")


def series_path(series_key: str) -> str:
    return f"/manga/{normalize_series_key(series_key)}/"


def chapter_path(chapter_key: str, page: int = 1) -> str:
    return f"/manga/{normalize_chapter_key(chapter_key)}/{max(1, page)}.html"


def chapterfun_path(chapter_key: str) -> str:
    """The reader's image endpoint lives beside the chapter's page files."""
    return f"/manga/{normalize_chapter_key(chapter_key)}/chapterfun.ashx"


def make_page_id(chapter_key: str, page_number: int) -> str:
    return f"{chapter_key}:{page_number}"


def page_id_chapter_key(page_id: str) -> str | None:
    """Split ``<chapter_key>:<n>``.

    Chapter keys contain slashes but never a colon, so a right-partition
    recovers the key without parsing its interior.
    """
    if ":" not in page_id:
        return None
    chapter_key, _, number = page_id.rpartition(":")
    if not chapter_key or not number.isdigit():
        return None
    return chapter_key


# --- small helpers ----------------------------------------------------------


def _clean(value: str) -> str:
    return html_mod.unescape(re.sub(r"\s+", " ", value or "")).strip()


def _strip_tags(value: str) -> str:
    return _clean(re.sub(r"<[^>]+>", " ", value or ""))


def _absolute(url: str) -> str:
    url = _clean(url)
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{SITE_BASE}{url}"
    return url


CHAPTER_NUMBER_RE = re.compile(r"c(?:h(?:apter)?)?\.?\s*0*(\d+(?:\.\d+)?)", re.I)


def parse_chapter_number(label: str, chapter_key: str = "") -> float | None:
    """The site's own numbering, e.g. ``Ch.200.5`` -> 200.5.

    Falls back to the trailing ``cNNN`` segment of the key when the visible
    label carries no number.
    """
    for candidate in (label, chapter_key.rpartition("/")[2]):
        match = CHAPTER_NUMBER_RE.search(candidate or "")
        if match:
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            return int(value) if value.is_integer() else value
    return None


# --- the packed reader script -----------------------------------------------

#: Fanfox ships reader data through a Dean-Edwards packer. The tail
#: ``,0,{}))`` is matched too so the payload's own quotes cannot end the match
#: early on a chapter whose word list happens to contain ``',<digits>,``.
PACKED_RE = re.compile(
    r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\("
    r"'(?P<payload>.*?)',(?P<base>\d+),(?P<count>\d+),"
    r"'(?P<words>.*?)'\.split\('\|'\)\s*,\s*\d+\s*,\s*\{\}\)\)",
    re.S,
)

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def _packer_token(index: int, base: int) -> str:
    """Reproduce the packer's own base-N symbol for ``index``.

    Mirrors the ``e()`` in the shipped script: digits/letters up to 35, then
    ``String.fromCharCode(c + 29)`` (so 36 -> 'A', 37 -> 'B', ...).
    """
    prefix = "" if index < base else _packer_token(index // base, base)
    index %= base
    return prefix + (chr(index + 29) if index > 35 else _ALPHABET[index])


def unpack_packed(payload: str, base: int, count: int, words: str) -> str:
    """Expand one packed block back into readable JavaScript.

    A word that is empty in the dictionary means "leave the token alone" —
    the shipped unpacker's ``k[c] || e(c)`` fallback. Getting that wrong
    silently corrupts image filenames, because digits are legal tokens.
    """
    table = words.split("|")
    mapping: dict[str, str] = {}
    for index in range(count):
        token = _packer_token(index, base)
        word = table[index] if index < len(table) else ""
        mapping[token] = word or token
    expanded = re.sub(r"\b\w+\b", lambda m: mapping.get(m.group(0), m.group(0)), payload)
    # The payload arrives with its quotes backslash-escaped for the HTML
    # attribute it sat in; undo that so plain quote matching works below.
    return expanded.replace("\\'", "'").replace('\\"', '"')


def unpacked_blocks(document: str) -> list[str]:
    """Every packed block in a document, expanded, in source order."""
    return [
        unpack_packed(m.group("payload"), int(m.group("base")), int(m.group("count")), m.group("words"))
        for m in PACKED_RE.finditer(document or "")
    ]


def _reader_blocks(document: str) -> list[str]:
    """Places reader data can live, most-specific first.

    Expanded packed blocks are searched before the raw document so real data
    always wins. The raw document is included as a fallback because nothing
    about these declarations requires packing — fanfox packs them today, and a
    plain ``var pix=...`` response would otherwise read as an empty chapter.
    """
    return [*unpacked_blocks(document), document or ""]


# --- chapter reader ---------------------------------------------------------

IMAGE_COUNT_RE = re.compile(r"var\s+imagecount\s*=\s*(\d+)")
CHAPTER_ID_RE = re.compile(r"var\s+chapterid\s*=\s*(\d+)")
COMIC_ID_RE = re.compile(r"var\s+comicid\s*=\s*(\d+)")

_NEW_IMGS_RE = re.compile(r"var\s+newImgs\s*=\s*\[(?P<body>.*?)\]", re.S)
_GUIDKEY_RE = re.compile(r"var\s+guidkey\s*=\s*(?P<body>[^;]+);")
_PIX_RE = re.compile(r"var\s+pix\s*=\s*[\"'](?P<pix>[^\"']+)[\"']")
_PVALUE_RE = re.compile(r"var\s+pvalue\s*=\s*\[(?P<body>.*?)\]", re.S)
_QUOTED_RE = re.compile(r"[\"']([^\"']*)[\"']")


def parse_image_count(document: str) -> int:
    match = IMAGE_COUNT_RE.search(document or "")
    return int(match.group(1)) if match else 0


def parse_chapter_ident(document: str) -> tuple[str | None, str | None]:
    """``(chapterid, comicid)`` — the reader's own identifiers."""
    chapter = CHAPTER_ID_RE.search(document or "")
    comic = COMIC_ID_RE.search(document or "")
    return (chapter.group(1) if chapter else None, comic.group(1) if comic else None)


def parse_embedded_image_urls(document: str) -> list[str]:
    """Mode A: the chapter page carries every image URL inline.

    Older/"compressed" chapters define ``var newImgs=[...]`` holding the whole
    chapter, so one GET resolves every page. Returns [] when this chapter uses
    the guidkey handshake instead.
    """
    for block in _reader_blocks(document):
        match = _NEW_IMGS_RE.search(block)
        if not match:
            continue
        urls = [_absolute(u) for u in _QUOTED_RE.findall(match.group("body")) if "/" in u]
        if urls:
            return urls
    return []


def parse_guidkey(document: str) -> str | None:
    """Mode B: the reader gets a key and must call ``chapterfun.ashx``.

    The key is emitted as a concatenation of single characters
    (``''+'c'+'9'+...``) purely to defeat naive scraping; joining the quoted
    fragments reassembles it.
    """
    for block in _reader_blocks(document):
        match = _GUIDKEY_RE.search(block)
        if match:
            key = "".join(_QUOTED_RE.findall(match.group("body")))
            if key:
                return key
    return None


def parse_chapterfun(document: str) -> list[str]:
    """Image URLs from one ``chapterfun.ashx`` response.

    The response defines ``pix`` (a directory prefix) and ``pvalue`` (the
    filenames, each with its own signed token). Fanfox returns the requested
    page and the one after it, so a chapter needs ceil(n/2) of these.
    """
    for block in _reader_blocks(document):
        pix_match = _PIX_RE.search(block)
        values_match = _PVALUE_RE.search(block)
        if not pix_match or not values_match:
            continue
        pix = pix_match.group("pix")
        urls: list[str] = []
        for value in _QUOTED_RE.findall(values_match.group("body")):
            if not value:
                continue
            # pvalue entries are already-absolute on rare chapters; the common
            # case is a leading-slash filename that hangs off pix.
            urls.append(_absolute(value if value.startswith("//") else pix + value))
        if urls:
            return urls
    return []


def pages_from_urls(chapter_key: str, urls: list[str]) -> list[Page]:
    return [
        Page(
            id=make_page_id(chapter_key, index),
            chapter_id=chapter_key,
            number=index,
            remote_url=url,
        )
        for index, url in enumerate(urls, start=1)
    ]


#: Fanfox appends an " [Add]" pseudo-link to the author row — a UI affordance
#: for submitting a missing credit, not a person. Anchors are read individually
#: so it can be dropped instead of landing in the author field.
_ANCHOR_RE = re.compile(r"<a[^>]*>(?P<text>.*?)</a>", re.I | re.S)


def _authors_from_block(body: str) -> str | None:
    names: list[str] = []
    for raw in _ANCHOR_RE.findall(body or ""):
        name = _strip_tags(raw)
        if not name or name.lower() in {"[add]", "add"}:
            continue
        if name not in names:
            names.append(name)
    if names:
        return ", ".join(names)
    text = re.sub(r"^Author:\s*", "", _strip_tags(body)).strip()
    text = re.sub(r"\s*\[Add\]\s*$", "", text).strip()
    return text or None


# --- listings ---------------------------------------------------------------

#: A directory card. The visible anchor text is truncated with an ellipsis, so
#: the full name is taken from the ``title`` attribute instead.
_LIST_ITEM_RE = re.compile(
    r'<li>\s*<a\s+href="/manga/(?P<slug>[^"/]+)/"[^>]*title="(?P<title>[^"]*)"[^>]*>\s*'
    r'<img\s+class="manga-list-1-cover"\s+src="(?P<cover>[^"]+)"',
    re.I | re.S,
)

_LIST_SUBTITLE_RE = re.compile(
    r'<p class="manga-list-1-item-subtitle">\s*<a\s+href="/manga/(?P<key>[^"]+?)/\d+\.html"[^>]*>(?P<label>.*?)</a>',
    re.I | re.S,
)

_PAGER_PAGE_RE = re.compile(r'href="/directory/(?:[a-z0-9-]+/)?(\d+)\.html')


def parse_total_pages(document: str) -> int:
    numbers = [int(value) for value in _PAGER_PAGE_RE.findall(document or "")]
    return max(numbers) if numbers else 1


def parse_series_list(
    document: str, *, page: int, page_size: int = PAGE_SIZE
) -> PaginatedSeriesList:
    """Parse a ``/directory/`` page into a paginated listing."""
    items: list[Series] = []
    seen: set[str] = set()
    # Latest-chapter labels appear once per card, in the same order.
    latest = _LIST_SUBTITLE_RE.findall(document or "")
    for index, match in enumerate(_LIST_ITEM_RE.finditer(document or "")):
        slug = match.group("slug")
        if slug in seen:
            continue
        seen.add(slug)
        label = _clean(latest[index][1]) if index < len(latest) else None
        items.append(
            Series(
                id=slug,
                title=_clean(match.group("title")),
                cover_url=_absolute(match.group("cover")),
                canonical_path=series_path(slug),
                latest_chapter=label or None,
            )
        )
    total_pages = parse_total_pages(document)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total_pages * page_size,
        api_has_more=page < total_pages,
    )


#: A ``/search`` result row. Richer than a directory card: status, author and
#: a description blurb are all present, so search results need no extra fetch.
_SEARCH_ITEM_RE = re.compile(
    r'<li>\s*<a\s+href="/manga/(?P<slug>[^"/]+)/"[^>]*title="(?P<title>[^"]*)"[^>]*>'
    r'\s*<img\s+class="manga-list-4-cover"\s+src="(?P<cover>[^"]+)"'
    r"(?P<rest>.*?)</li>",
    re.I | re.S,
)
_SEARCH_STATUS_RE = re.compile(
    r'<p class="manga-list-4-show-tag-list-2">\s*<a[^>]*>(?P<status>[^<]*)</a>', re.I | re.S
)
_SEARCH_AUTHOR_RE = re.compile(
    r'<p class="manga-list-4-item-tip">Author:(?P<body>.*?)</p>', re.I | re.S
)
_SEARCH_TIP_RE = re.compile(r'<p class="manga-list-4-item-tip">(?P<body>.*?)</p>', re.I | re.S)
_SEARCH_LATEST_RE = re.compile(
    r'<p class="manga-list-4-item-tip">Latest Chapter:<a[^>]*>(?P<label>[^<]*)</a>', re.I | re.S
)
_SEARCH_PAGER_RE = re.compile(r'href="/search\?page=(\d+)')


def parse_search_results(
    document: str, *, page: int, page_size: int = SEARCH_PAGE_SIZE
) -> PaginatedSeriesList:
    items: list[Series] = []
    seen: set[str] = set()
    for match in _SEARCH_ITEM_RE.finditer(document or ""):
        slug = match.group("slug")
        if slug in seen:
            continue
        seen.add(slug)
        rest = match.group("rest")
        status = _SEARCH_STATUS_RE.search(rest)
        author = _SEARCH_AUTHOR_RE.search(rest)
        latest = _SEARCH_LATEST_RE.search(rest)
        # The description is the last plain tip row — the ones before it are
        # the labelled Author/Latest Chapter rows.
        description = None
        for tip in _SEARCH_TIP_RE.findall(rest):
            text = _strip_tags(tip)
            if text and not text.startswith(("Author:", "Latest Chapter:")):
                description = text
        items.append(
            Series(
                id=slug,
                title=_clean(match.group("title")),
                cover_url=_absolute(match.group("cover")),
                canonical_path=series_path(slug),
                status=_clean(status.group("status")) if status else None,
                author=_authors_from_block(author.group("body")) if author else None,
                latest_chapter=_clean(latest.group("label")) if latest else None,
                description=description,
            )
        )
    pages = [int(value) for value in _SEARCH_PAGER_RE.findall(document or "")]
    total_pages = max(pages) if pages else 1
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total_pages * page_size,
        api_has_more=page < total_pages,
    )


# --- series detail ----------------------------------------------------------

_DETAIL_TITLE_RE = re.compile(
    r'<span class="detail-info-right-title-font">(?P<title>.*?)</span>', re.I | re.S
)
_DETAIL_STATUS_RE = re.compile(
    r'<span class="detail-info-right-title-tip">(?P<status>.*?)</span>', re.I | re.S
)
_DETAIL_COVER_RE = re.compile(
    r'<img class="detail-info-cover-img"\s+src="(?P<cover>[^"]+)"', re.I
)
_DETAIL_AUTHOR_RE = re.compile(
    r'<p class="detail-info-right-say">(?P<body>.*?)</p>', re.I | re.S
)
_DETAIL_TAGS_RE = re.compile(
    r'<p class="detail-info-right-tag-list">(?P<body>.*?)</p>', re.I | re.S
)
_DETAIL_TAG_RE = re.compile(r'<a[^>]*title="(?P<name>[^"]*)"[^>]*>', re.I)
_DETAIL_FULL_DESC_RE = re.compile(
    r'<p[^>]*class="fullcontent"[^>]*>(?P<body>.*?)</p>', re.I | re.S
)
_DETAIL_SHORT_DESC_RE = re.compile(
    r'<p class="detail-info-right-content">(?P<body>.*?)</p>', re.I | re.S
)


def parse_series_detail(document: str, series_key: str) -> Series | None:
    """Parse ``/manga/<slug>/``.

    Returns ``None`` for a slug fanfox does not know: rather than a 404 it
    serves its search page with HTTP 200, and the only reliable tell is the
    absence of the detail header. Treating that as a hit would publish an
    empty series named after the search box.
    """
    title_match = _DETAIL_TITLE_RE.search(document or "")
    if not title_match:
        return None
    title = _clean(title_match.group("title"))
    if not title:
        return None

    cover = _DETAIL_COVER_RE.search(document or "")
    status = _DETAIL_STATUS_RE.search(document or "")
    author_block = _DETAIL_AUTHOR_RE.search(document or "")
    author = _authors_from_block(author_block.group("body")) if author_block else None

    genres: tuple[str, ...] = ()
    tags_block = _DETAIL_TAGS_RE.search(document or "")
    if tags_block:
        names = [_clean(n) for n in _DETAIL_TAG_RE.findall(tags_block.group("body"))]
        genres = tuple(dict.fromkeys(n for n in names if n))

    description = None
    full = _DETAIL_FULL_DESC_RE.search(document or "")
    if full:
        description = _strip_tags(full.group("body")) or None
    if not description:
        short = _DETAIL_SHORT_DESC_RE.search(document or "")
        if short:
            # The teaser ends in a "more" toggle link; drop it.
            description = re.sub(r"\s*more$", "", _strip_tags(short.group("body"))) or None

    return Series(
        id=series_key,
        title=title,
        canonical_path=series_path(series_key),
        description=description,
        cover_url=_absolute(cover.group("cover")) if cover else None,
        author=author,
        status=_clean(status.group("status")) if status else None,
        genres=genres,
    )


# --- chapter list -----------------------------------------------------------

_CHAPTER_LIST_BLOCK_RE = re.compile(
    r'<ul class="detail-main-list">(?P<body>.*?)</ul>', re.I | re.S
)
_CHAPTER_ROW_RE = re.compile(
    r'<li[^>]*>\s*<a\s+href="/manga/(?P<key>[^"]+?)/\d+\.html"[^>]*>.*?'
    r'<p class="title3">(?P<label>.*?)</p>\s*'
    r'(?:<p class="title2">(?P<date>.*?)</p>)?',
    re.I | re.S,
)


def parse_chapters(document: str, series_key: str) -> list[Chapter]:
    """Parse the chapter table embedded in the series detail page.

    Fanfox renders the entire chapter list inline — no pagination, no separate
    endpoint — so ``get_series`` and ``get_chapters`` share a single fetch.
    Rows are newest-first on the page; the returned list is oldest-first.
    """
    block = _CHAPTER_LIST_BLOCK_RE.search(document or "")
    if not block:
        return []
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for match in _CHAPTER_ROW_RE.finditer(block.group("body")):
        key = normalize_chapter_key(match.group("key"))
        if not key or key in seen:
            continue
        seen.add(key)
        label = _clean(match.group("label"))
        date = _clean(match.group("date") or "") or None
        chapters.append(
            Chapter(
                id=key,
                series_id=series_key,
                title=label or key.rpartition("/")[2],
                number=parse_chapter_number(label, key),
                page_count=0,
                release_date=date,
            )
        )
    chapters.reverse()
    return chapters
