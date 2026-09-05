"""Map GuaziManhua (瓜子漫画) pages onto normalized connector models.

Endpoint map (verified from the VPS 2026-09-05, inside
``manhwamaniacs-backend`` so through production's exact egress):

* ``/category.php?page=N``             -- catalog, 36 ``<article class="card">``
  per page over 631 pages. Optional ``sort=daily|hits|update|score``; the
  site's own "全部" chip sends no ``sort`` at all, so the default mode does
  the same.
* ``/category.php?keyword=<terms>``    -- search, same card markup. It is
  NOT paginated: the result grid renders once and the pager collapses to a
  single "1", so ``?page=2`` comes back with zero cards.
* ``/category.php?cid=<id>&page=N``    -- genre browse. The site also accepts
  ``tag=<Chinese name>``, but ``cid`` is the numeric id its own filter chips
  emit and needs no percent-encoded CJK in the query.
* ``/comic.php?id=<n>``                -- detail. Carries a JSON-LD
  ``ComicStory`` (name/author/genre/image/description) AND the FULL chapter
  list in ``data-mobile-chapter-list``, so detail + chapters cost one request.
  The page's JSON-LD ``ItemList`` is NOT usable for chapters: it truncates at
  50 entries where the mobile grid carried all 1,187.
* ``/chapter.php?id=<n>``              -- reader. Every page image is a plain
  ``<img class="reading-image" src="https://img.guazicdn.com/...">`` in the
  server-rendered markup, so a chapter costs one request and a page image
  costs zero extra.

Identity keys are the site's own integer ids, kept as strings and passed raw
(house law).
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://www.guazimanhua.com"

#: Cards per catalog page, counted on ``/category.php`` and every genre page.
PAGE_SIZE = 36

CATEGORY_PATH = "/category.php"
SERIES_PATH = "/comic.php"
CHAPTER_PATH = "/chapter.php"

#: Covers and page images alike come from ``img.guazicdn.com`` -- a distinct
#: domain from the site, so it is a mandatory SSRF-allowlist entry.
IMAGE_HOST_SUFFIX = "guazicdn.com"

#: Separates the chapter id from the 1-based page index in a page id. Chapter
#: ids are digits only, so a colon never occurs inside one.
PAGE_ID_SEPARATOR = ":"


# --- markup ----------------------------------------------------------------

#: One catalog/search/genre card. Cover, score/status badges, then the title
#: anchor and a "author · genre · genre" meta line.
CARD_RE = re.compile(
    r'<article class="card">\s*'
    r'<a class="cover-wrap" href="/comic\.php\?id=(\d+)">'
    r'<img class="cover" src="([^"]*)"[^>]*>'
    r'(?:<span class="score">([^<]*)</span>)?'
    r'(?:<span class="genre">([^<]*)</span>)?'
    r'\s*</a>\s*'
    r'<h3><a href="/comic\.php\?id=\d+">([^<]*)</a></h3>\s*'
    r'<div class="meta">([^<]*)</div>',
    re.S,
)

#: The pager's highest page number. It renders a "..." gap and then the last
#: page, so the largest number in the block is the real page count -- there is
#: no result total published anywhere else on the page.
PAGER_BLOCK_RE = re.compile(r'<nav class="pager".*?</nav>', re.S)
#: ``&amp;`` matters: a genre pager renders "?cid=25&amp;page=2", so a bare
#: ``[?&]page=`` misses every page link on a filtered listing and the source
#: silently claims to have one page.
PAGER_PAGE_RE = re.compile(r"(?:[?&]|&amp;)page=(\d+)")

DETAIL_TITLE_RE = re.compile(r'<div class="mobile-comic-title">([^<]*)</div>')
DETAIL_COVER_RE = re.compile(r'<img class="mobile-comic-cover cover" src="([^"]+)"')
DETAIL_META_RE = re.compile(r'<p class="mobile-comic-meta">(.*?)</p>', re.S)
DETAIL_TAGS_RE = re.compile(r'<p class="mobile-comic-tags">(.*?)</p>', re.S)
DETAIL_DESC_RE = re.compile(r'<p class="mobile-comic-desc">(.*?)</p>', re.S)

LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S
)

#: The full chapter grid. Sliced to the first ``</div>`` because the block
#: holds nothing but anchors -- the desktop copy of the same list follows and
#: would otherwise double every chapter.
CHAPTER_BLOCK_RE = re.compile(r"data-mobile-chapter-list>(.*?)</div>", re.S)
CHAPTER_LINK_RE = re.compile(
    r'<a[^>]*href="/chapter\.php\?id=(\d+)"[^>]*>([^<]*)</a>'
)

#: A reader page image. The reader marks the first one ``is-active`` and lazy
#: loads the rest, but every ``src`` is absolute and present in the markup.
PAGE_IMAGE_RE = re.compile(
    r'<img[^>]*class="reading-image[^"]*"[^>]*src="([^"]+)"', re.S
)

#: Chapter labels are "第1190话 众盼其死之人" / "第12卷" -- the leading run of
#: digits is the chapter number.
CHAPTER_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


# --- browse modes -----------------------------------------------------------

#: Mode id -> (label, ``sort`` value). ``None`` sends no ``sort``, which is
#: what the site's own "全部" chip does.
BROWSE_MODES: dict[str, tuple[str, str | None]] = {
    "default": ("All Comics", None),
    "update": ("Recently Updated", "update"),
    "hits": ("Most Popular", "hits"),
    "daily": ("Trending Today", "daily"),
    "score": ("Top Rated", "score"),
}

DEFAULT_MODE = "default"

#: Genre id -> (Chinese label, ``cid``), read from the site's own filter chips.
#: The labels stay in Chinese because the catalogue is Chinese-language and the
#: site publishes no English names; an invented translation would not match
#: anything a reader sees on a series page.
GENRES: dict[str, tuple[str, int]] = {
    "danmei": ("耽美 Danmei", 41),
    "lianai": ("恋爱 Romance", 9),
    "xiaoyuan": ("校园 School", 29),
    "bazong": ("霸总 CEO", 5),
    "dushi": ("都市 Urban", 42),
    "chuanyue": ("穿越 Isekai", 8),
    "gufeng": ("古风 Historical", 23),
    "xuanhuan": ("玄幻 Xuanhuan", 25),
    "qihuan": ("奇幻 Fantasy", 31),
    "kehuan": ("科幻 Sci-Fi", 22),
    "lingyi": ("灵异 Supernatural", 21),
    "dongzuo": ("动作 Action", 54),
    "xuanyi": ("悬疑 Mystery", 11),
    "maoxian": ("冒险 Adventure", 30),
    "gaoxiao": ("搞笑 Comedy", 15),
    "rexue": ("热血 Shounen", 13),
    "kongbu": ("恐怖 Horror", 14),
    "xitong": ("系统 System", 148),
    "nixi": ("逆袭 Comeback", 97),
    "naodong": ("脑洞 Surreal", 55),
    "fuchou": ("复仇 Revenge", 61),
    "zhenren": ("真人 Live Action", 17),
    "qita": ("其它 Other", 27),
}


def list_browse_modes() -> list[BrowseMode]:
    return [BrowseMode(id=key, label=label) for key, (label, _sort) in BROWSE_MODES.items()]


def list_genres() -> list[BrowseMode]:
    return [BrowseMode(id=key, label=label) for key, (label, _cid) in GENRES.items()]


def normalize_sort(sort: str | None) -> str:
    if not sort:
        return DEFAULT_MODE
    return sort if sort in BROWSE_MODES else DEFAULT_MODE


def browse_params(sort: str | None, page: int) -> dict[str, Any]:
    _label, sort_value = BROWSE_MODES[normalize_sort(sort)]
    params: dict[str, Any] = {}
    if sort_value:
        params["sort"] = sort_value
    if page > 1:
        # The site's own pager omits ``page`` on page 1 and the canonical URL
        # is the bare path; sending ``page=1`` works but points every first
        # page at a second URL for the same document.
        params["page"] = page
    return params


def search_params(query: str, page: int, *, sort: str | None = None) -> dict[str, Any]:
    params = browse_params(sort, page)
    params["keyword"] = query.strip()
    return params


def genre_params(genre: str, page: int, *, sort: str | None = None) -> dict[str, Any] | None:
    """Query for one genre, or ``None`` when the genre is not in the menu.

    ``cid`` is a numeric id, so an unknown key cannot be turned into a
    request; answering empty beats serving the unfiltered catalog under a
    genre heading.
    """
    entry = GENRES.get(genre.strip())
    if entry is None:
        return None
    params = browse_params(sort, page)
    params["cid"] = entry[1]
    return params


# --- identity ---------------------------------------------------------------


def _digits(value: str) -> str:
    match = re.search(r"(\d+)", value or "")
    return match.group(1) if match else ""


def normalize_series_key(value: str) -> str:
    """``18109`` from a bare id, a path, or a full URL."""
    return _digits(str(value or ""))


def normalize_chapter_key(value: str) -> str:
    return _digits(str(value or ""))


def series_params(series_key: str) -> dict[str, Any]:
    return {"id": normalize_series_key(series_key)}


def chapter_params(chapter_key: str) -> dict[str, Any]:
    return {"id": normalize_chapter_key(chapter_key)}


def canonical_path(series_key: str) -> str:
    return f"{SERIES_PATH}?id={normalize_series_key(series_key)}"


def make_page_id(chapter_key: str, number: int) -> str:
    return f"{chapter_key}{PAGE_ID_SEPARATOR}{number}"


def page_id_chapter_key(page_id: str) -> str | None:
    chapter_key, sep, _index = (page_id or "").rpartition(PAGE_ID_SEPARATOR)
    if not sep or not chapter_key:
        return None
    return chapter_key


def parse_chapter_number(label: str, *, fallback: float | None = None) -> float | None:
    """Chapter number from the site's own label ("第1190话 ..." -> 1190).

    Falls back to the caller's position index when a label carries no digits
    (side stories are titled "番外篇"), so every chapter can be ordered.
    """
    match = CHAPTER_NUMBER_RE.search(label or "")
    if match is None:
        return fallback
    try:
        return float(match.group(1))
    except ValueError:
        return fallback


# --- parsing ----------------------------------------------------------------


def _clean(value: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", value or "")).strip()


def _clean_html(value: str) -> str:
    return _clean(re.sub(r"<[^>]+>", " ", value or ""))


def _split_meta(meta: str) -> tuple[str | None, tuple[str, ...]]:
    """A card's "author · genre · genre" line into (author, genres).

    Cards separate the fields with "·" and detail tags use "/", so both are
    treated as separators. Cards without an author show only genres, which is
    indistinguishable from the outside -- the first field is taken as the
    author only when more than one field is present.
    """
    parts = [part for part in (piece.strip() for piece in re.split(r"[·/]", meta)) if part]
    if len(parts) <= 1:
        return None, tuple(parts)
    return parts[0], tuple(parts[1:])


def parse_series_cards(html: str) -> list[Series]:
    seen: set[str] = set()
    items: list[Series] = []
    for series_id, cover, _score, status, title, meta in CARD_RE.findall(html):
        if series_id in seen:
            continue
        seen.add(series_id)
        author, genres = _split_meta(_clean(meta))
        items.append(
            Series(
                id=series_id,
                title=_clean(title),
                cover_url=html_lib.unescape(cover) or None,
                canonical_path=canonical_path(series_id),
                author=author,
                genres=genres,
                status=_clean(status) or None,
            )
        )
    return items


def parse_last_page(html: str) -> int:
    block = PAGER_BLOCK_RE.search(html)
    if block is None:
        return 1
    pages = [int(value) for value in PAGER_PAGE_RE.findall(block.group(0))]
    return max(pages) if pages else 1


def parse_series_list(html: str, *, page: int) -> PaginatedSeriesList:
    items = parse_series_cards(html)
    last_page = parse_last_page(html)
    current = max(page, 1)
    # No result count is published anywhere, so the honest total is the page
    # count the site's own pager admits to, times the page size.
    total = last_page * PAGE_SIZE if last_page > 1 else len(items)
    return PaginatedSeriesList(
        items=items,
        page=current,
        page_size=PAGE_SIZE,
        total=total,
        api_has_more=current < last_page,
    )


def _ld_comic_story(html: str) -> dict[str, Any]:
    """The detail page's JSON-LD ``ComicStory`` node, or ``{}``.

    Preferred over the rendered markup for author/genres/description: the
    site publishes them there already parsed, where the visible chrome shows
    them as a "·"-joined string that would have to be split back apart.
    """
    for block in LD_JSON_RE.findall(html):
        try:
            payload = json.loads(html_lib.unescape(block))
        except (json.JSONDecodeError, ValueError):
            continue
        nodes = payload.get("@graph") if isinstance(payload, dict) else None
        for node in nodes or []:
            if isinstance(node, dict) and node.get("@type") == "ComicStory":
                return node
    return {}


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def parse_series_detail(html: str, series_key: str) -> Series | None:
    title_match = DETAIL_TITLE_RE.search(html)
    if title_match is None:
        return None

    story = _ld_comic_story(html)
    author = story.get("author")
    author_name = _text(author.get("name")) if isinstance(author, dict) else _text(author)
    genres = story.get("genre")
    if not isinstance(genres, list):
        tags_match = DETAIL_TAGS_RE.search(html)
        genres = _split_meta(_clean_html(tags_match.group(1)) if tags_match else "")[1]

    cover_match = DETAIL_COVER_RE.search(html)
    desc_match = DETAIL_DESC_RE.search(html)
    meta_match = DETAIL_META_RE.search(html)
    # The meta line reads "连载·1187话" (serialising / N chapters); only the
    # leading word is a status, the rest is the chapter count shown below.
    status = _clean_html(meta_match.group(1)).split("·")[0].strip() if meta_match else ""

    return Series(
        id=series_key,
        title=_clean(title_match.group(1)),
        canonical_path=canonical_path(series_key),
        description=_text(story.get("description")) or (_clean_html(desc_match.group(1)) if desc_match else None),
        cover_url=(_text(story.get("image")) or (html_lib.unescape(cover_match.group(1)) if cover_match else None)),
        author=author_name,
        # The site credits one "作者" and never distinguishes an artist.
        artist=None,
        status=status or None,
        genres=tuple(_clean(str(name)) for name in genres if _text(name)),
    )


def parse_chapters(html: str, series_key: str) -> list[Chapter]:
    """Chapters from the series page, oldest-first.

    The page lists them newest-first; the app wants ascending, and sorting by
    the parsed number keeps 第9话 before 第10话 where a string sort would not.
    """
    block = CHAPTER_BLOCK_RE.search(html)
    if block is None:
        return []

    chapters: list[Chapter] = []
    seen: set[str] = set()
    rows = CHAPTER_LINK_RE.findall(block.group(1))
    total = len(rows)
    for index, (chapter_id, label) in enumerate(rows):
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        title = _clean(label)
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_key,
                title=title,
                # Rows arrive newest-first, so the fallback index counts down.
                number=parse_chapter_number(title, fallback=float(total - index)),
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
    for url in PAGE_IMAGE_RE.findall(html):
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
            )
        )
    return pages
