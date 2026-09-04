"""Map WEBTOON (webtoons.com) HTML pages to normalized connector models.

WEBTOON is a large JavaScript site, but its list / episode-list / viewer pages
are server-rendered HTML, so everything the connector needs is scrapable from
the raw markup.

Identity scheme
---------------
* ``series_id``  = the integer ``title_no`` (as a string). The detail/list page
  can be reached with any genre/slug in the path -- WEBTOON 301-redirects a
  placeholder path to the canonical one -- so a bare ``title_no`` round-trips.
  This redirect only happens for **Originals**; **Canvas** titles need a
  literal ``canvas`` genre segment instead (:func:`canvas_detail_path`), so
  the connector tries the Originals placeholder first and falls back to the
  Canvas placeholder on failure (``WebtoonsConnector._get_series_html``).
  Either way the persisted ``series_id`` itself never encodes section, which
  keeps existing ``followed_series.series_key`` rows valid across this fix.
* ``chapter_id`` = ``"<title_no>:<episode_no>:<genre>:<series_slug>"``. The
  viewer URL needs the series' genre + slug segments; the trailing episode-slug
  segment does not matter (WEBTOON redirects it based on ``episode_no``), so it
  is not stored. ``genre``/``series_slug`` are URL path tokens (lowercase,
  hyphens, no colons) which keeps the colon delimiter unambiguous.
* ``page_id``    = ``"<chapter_id>:<page_number>"``. ``rpartition(':')`` peels
  the page number back off, leaving the chapter_id intact.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://www.webtoons.com"
LOCALE = "en"
PAGE_SIZE = 30

# Image CDN hosts. Page images and list/detail thumbnails are served from
# ``webtoon-phinf.pstatic.net``; the ``og:image`` cover variant is served from
# ``swebtoon-phinf.pstatic.net``. Both enforce hotlink protection (a bare GET
# returns HTTP 403 without a webtoons.com ``Referer``).
IMAGE_HOSTS = frozenset({"webtoon-phinf.pstatic.net", "swebtoon-phinf.pstatic.net"})
IMAGE_REFERER = "https://www.webtoons.com"

# A series card (identical shape across /originals, /genres/<g> and /search):
#   <a href="https://www.webtoons.com/en/<genre>/<slug>/list?title_no=<no>" class="link ...">
#       ... <img ... src="<thumb>" ...>
#       ... <strong class="title"><title></strong>
SERIES_CARD_RE = re.compile(
    r'<a\s+href="https?://www\.webtoons\.com/[a-z]{2}/([^/"]+)/([^/"]+)/list\?title_no=(\d+)[^"]*"'
    r'[^>]*class="[^"]*link[^"]*"'
    r'.*?<img[^>]+src="([^"]+)"'
    r'.*?<strong class="title">([^<]+)</strong>',
    re.S | re.I,
)

# An episode row in the detail/list page:
#   <a href="https://www.webtoons.com/en/<genre>/<slug>/<ep-slug>/viewer?title_no=<no>&episode_no=<m>"
#      class="detail_list_link"> ... <span class="subj"><span><title></span> ...
#      <span class="date"><date></span>
EPISODE_RE = re.compile(
    r'href="https?://www\.webtoons\.com/[a-z]{2}/([^/"]+)/([^/"]+)/[^/"]+/viewer'
    r'\?title_no=(\d+)&(?:amp;)?episode_no=(\d+)"[^>]*class="detail_list_link"'
    r'.*?<span class="subj">(?:<span>)?([^<]*)'
    r'.*?<span class="date">([^<]*)</span>',
    re.S | re.I,
)

# Viewer image: the real URL is in ``data-url`` (``src`` is a transparent
# placeholder until lazy-load swaps it in).
IMAGE_TAG_RE = re.compile(r'<img\b[^>]*class="_images"[^>]*>', re.I)
_DATA_URL_RE = re.compile(r'data-url="([^"]+)"', re.I)
_WIDTH_RE = re.compile(r'\bwidth="([0-9.]+)"', re.I)
_HEIGHT_RE = re.compile(r'\bheight="([0-9.]+)"', re.I)


def _clean_text(value: str) -> str:
    return html_lib.unescape(re.sub(r"\s+", " ", value)).strip()


def _to_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


# -- Identity helpers -------------------------------------------------------

def series_detail_path(series_id: str) -> str:
    """Path to page 1 of an *Originals* series' episode-list page.

    A placeholder genre/slug is fine here: WEBTOON 301-redirects to the
    canonical path (the shared HTTP client follows redirects), so only the
    ``title_no`` query parameter is load-bearing. NOTE: that redirect *drops*
    any ``&page=N`` query param, so paginating deeper episodes MUST use the
    canonical path via :func:`series_page_path`.

    This placeholder shape only works for Originals. Canvas titles are not
    redirected from it -- they 404 -- and need :func:`canvas_detail_path`
    instead. See ``WebtoonsConnector._get_series_html`` for the fallback that
    tries this path first and retries with the Canvas shape on failure.
    """
    title_no = series_id.strip().strip("/")
    return f"/{LOCALE}/_/_/list?title_no={title_no}"


def canvas_detail_path(series_id: str) -> str:
    """Path to page 1 of a *Canvas* series' episode-list page.

    Canvas titles live under a literal ``canvas`` first path segment
    (``/<locale>/canvas/_/list?title_no=N``) rather than the Originals
    ``/<locale>/_/_/list`` placeholder shape -- WEBTOON does not redirect the
    Originals placeholder to a Canvas title's canonical URL, it 404s. The
    trailing slug segment is still a don't-care placeholder here; the real
    slug is learned from the response body (``rel=canonical`` / ``og:url``)
    once this succeeds.
    """
    title_no = series_id.strip().strip("/")
    return f"/{LOCALE}/canvas/_/list?title_no={title_no}"


def series_page_path(genre: str, slug: str, series_id: str, page: int) -> str:
    """Canonical episode-list path for page ``page`` (``&page=N`` preserved).

    Unlike the placeholder path, the canonical ``/<genre>/<slug>/list`` URL is
    served directly (no redirect), so the ``page`` query parameter survives.
    """
    title_no = series_id.strip().strip("/")
    return f"/{LOCALE}/{genre}/{slug}/list?title_no={title_no}&page={max(page, 1)}"


def make_chapter_id(title_no: str, episode_no: int | str, genre: str, slug: str) -> str:
    return f"{title_no}:{episode_no}:{genre}:{slug}"


def parse_chapter_id(chapter_id: str) -> tuple[str, str, str, str] | None:
    """Return ``(title_no, episode_no, genre, series_slug)`` or ``None``."""
    parts = chapter_id.split(":")
    if len(parts) != 4:
        return None
    title_no, episode_no, genre, slug = parts
    if not title_no or not episode_no:
        return None
    return title_no, episode_no, genre, slug


def chapter_viewer_path(chapter_id: str) -> str | None:
    parsed = parse_chapter_id(chapter_id)
    if parsed is None:
        return None
    title_no, episode_no, genre, slug = parsed
    # The trailing "ep" episode-slug is a placeholder; WEBTOON redirects it to
    # the canonical episode slug using ``episode_no``.
    return f"/{LOCALE}/{genre}/{slug}/ep/viewer?title_no={title_no}&episode_no={episode_no}"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _number = page_id.rpartition(":")
    return chapter_id or None


# -- List / search ----------------------------------------------------------

def parse_series_cards(html: str) -> list[Series]:
    seen: set[str] = set()
    items: list[Series] = []
    for genre, slug, title_no, thumb, title in SERIES_CARD_RE.findall(html):
        if title_no in seen:
            continue
        seen.add(title_no)
        items.append(
            Series(
                id=title_no,
                title=_clean_text(title),
                cover_url=thumb,
                canonical_path=f"/{LOCALE}/{genre}/{slug}/list?title_no={title_no}",
            )
        )
    return items


def paginate_cards(
    all_items: list[Series],
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    """Client-side paginate a fully-parsed card list.

    The WEBTOON /originals and /genres/<g> pages return their whole catalog in a
    single server-rendered response (no server pagination), so the connector
    fetches once and slices here.
    """
    page = max(page, 1)
    start = (page - 1) * page_size
    window = all_items[start : start + page_size]
    total = len(all_items)
    return PaginatedSeriesList(
        items=window,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=start + page_size < total,
    )


def parse_search_results(
    html: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(html)
    return paginate_cards(items, page=page, page_size=page_size)


# -- Series detail ----------------------------------------------------------

def _extract_canonical_genre_slug(html: str) -> tuple[str | None, str | None]:
    match = re.search(
        r'(?:rel="canonical"|property="og:url")[^>]*'
        r'https?://www\.webtoons\.com/[a-z]{2}/([^/"]+)/([^/"]+)/list',
        html,
        re.I,
    )
    if match:
        return match.group(1), match.group(2)
    return None, None


def parse_series_detail(html: str, series_id: str) -> Series | None:
    title_match = re.search(r'<h1 class="subj">(.*?)</h1>', html, re.S | re.I)
    if title_match is None:
        og = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html, re.I)
        if og is None:
            return None
        title = _clean_text(og.group(1))
    else:
        title = _clean_text(re.sub(r"<[^>]+>", " ", title_match.group(1)))

    genre_slug = _extract_canonical_genre_slug(html)
    canonical = None
    if genre_slug[0] and genre_slug[1]:
        canonical = f"/{LOCALE}/{genre_slug[0]}/{genre_slug[1]}/list?title_no={series_id}"

    cover_match = re.search(
        r'<div class="detail_header[^"]*">.*?<span class="thmb">\s*<img[^>]+src="([^"]+)"',
        html,
        re.S | re.I,
    )
    if cover_match is None:
        cover_match = re.search(
            r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html, re.I
        )
    cover_url = cover_match.group(1) if cover_match else None

    genre_match = re.search(r'<h2 class="genre[^"]*">([^<]+)</h2>', html, re.I)
    genres: tuple[str, ...] = (_clean_text(genre_match.group(1)),) if genre_match else ()

    author_match = re.search(r'<a[^>]+class="author[^"]*"[^>]*>([^<]+)</a>', html, re.I)
    if author_match is None:
        author_match = re.search(
            r'<meta[^>]+content="([^"]+)"[^>]*property="com-linewebtoon:webtoon:author"',
            html,
            re.I,
        )
    author = _clean_text(author_match.group(1)) if author_match else None

    summary_match = re.search(r'<p class="summary">(.*?)</p>', html, re.S | re.I)
    description = (
        _clean_text(re.sub(r"<[^>]+>", " ", summary_match.group(1)))
        if summary_match
        else None
    )

    # WEBTOON does not label ongoing/completed uniformly; a "day_info"
    # schedule ("EVERY THURSDAY") implies an ongoing series.
    status = None
    if re.search(r'<p class="day_info">', html, re.I):
        status = "Ongoing"
    elif re.search(r'\bcompleted\b', html, re.I):
        status = "Completed"

    return Series(
        id=series_id,
        title=title,
        canonical_path=canonical,
        cover_url=cover_url,
        description=description,
        author=author,
        genres=genres,
        status=status,
    )


def peek_latest_episode(html: str, series_id: str) -> tuple[int, str | None] | None:
    """Return ``(chapter_count_hint, latest_title)`` from the first episode page only."""
    episodes = parse_episodes(html, series_id)
    if not episodes:
        return None
    return len(episodes), episodes[0].title


def extract_slug_from_canonical_path(canonical_path: str | None) -> tuple[str, str] | None:
    if not canonical_path:
        return None
    match = re.search(r"/[a-z]{2}/([^/]+)/([^/]+)/list", canonical_path, re.I)
    if match is None:
        return None
    return match.group(1), match.group(2)


# -- Episodes / chapters ----------------------------------------------------

PAGINATE_BLOCK_RE = re.compile(
    r'<div class="paginate">(?P<body>.*?)</div>', re.I | re.S
)
_PAGINATE_LINK_RE = re.compile(r"[?&]page=(\d+)")


def parse_max_list_page(html: str) -> int:
    """Highest episode-list page number the pagination strip advertises.

    WEBTOON shows ten page links at a time, so this is a *lower bound* on a
    long series -- page 10's strip reveals 11-20, and so on. That is exactly
    what it is used for: it turns "fetch page after page until one comes back
    empty" into "fetch the ten we already know exist, at once". Restricted to
    the paginate block because ``page=`` also appears in unrelated links.
    """
    block = PAGINATE_BLOCK_RE.search(html)
    if block is None:
        return 1
    pages = [int(value) for value in _PAGINATE_LINK_RE.findall(block.group("body"))]
    return max(pages) if pages else 1


def parse_episodes(html: str, series_id: str) -> list[Chapter]:
    """Parse the episode rows on one detail/list page (newest-first)."""
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for genre, slug, title_no, episode_no, subj, date in EPISODE_RE.findall(html):
        if title_no != series_id:
            # Guard against stray links to other titles.
            continue
        if episode_no in seen:
            continue
        seen.add(episode_no)
        chapter_id = make_chapter_id(title_no, episode_no, genre, slug)
        number = _to_int(episode_no)
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=_clean_text(subj) or f"Episode {episode_no}",
                number=float(number) if number is not None else None,
                page_count=0,
                release_date=_clean_text(date) or None,
            )
        )
    return chapters


# -- Viewer / pages ---------------------------------------------------------

def parse_chapter_pages(html: str, chapter_id: str) -> list[Page]:
    start = html.find('id="_imageList"')
    region = html[start:] if start != -1 else html

    pages: list[Page] = []
    number = 0
    for tag in IMAGE_TAG_RE.findall(region):
        data_url = _DATA_URL_RE.search(tag)
        if not data_url:
            continue
        url = html_lib.unescape(data_url.group(1))
        if not url.lower().startswith("http"):
            continue
        number += 1
        width = _WIDTH_RE.search(tag)
        height = _HEIGHT_RE.search(tag)
        pages.append(
            Page(
                id=make_page_id(chapter_id, number),
                chapter_id=chapter_id,
                number=number,
                remote_url=url,
                width=_to_int(width.group(1)) if width else None,
                height=_to_int(height.group(1)) if height else None,
            )
        )
    return pages


# -- Browse endpoints -------------------------------------------------------

def originals_path() -> str:
    return f"/{LOCALE}/originals"


def canvas_path() -> str:
    return f"/{LOCALE}/canvas"


def genre_path(genre_slug: str) -> str:
    return f"/{LOCALE}/genres/{genre_slug.strip().strip('/')}"


def search_path() -> str:
    return f"/{LOCALE}/search"


def search_params(query: str) -> dict[str, Any]:
    return {"keyword": query.strip()}


# The canonical WEBTOON genre catalog (slug -> display label). Slugs match the
# ``/en/genres/<slug>`` browse paths (note: underscored, unlike the hyphenated
# genre tokens that appear inside series URLs).
GENRES: tuple[tuple[str, str], ...] = (
    ("drama", "Drama"),
    ("fantasy", "Fantasy"),
    ("comedy", "Comedy"),
    ("action", "Action"),
    ("slice_of_life", "Slice of life"),
    ("romance", "Romance"),
    ("super_hero", "Superhero"),
    ("sf", "Sci-fi"),
    ("thriller", "Thriller"),
    ("supernatural", "Supernatural"),
    ("mystery", "Mystery"),
    ("sports", "Sports"),
    ("horror", "Horror"),
    ("heartwarming", "Heartwarming"),
    ("historical", "Historical"),
    ("graphic_novel", "Graphic novel"),
    ("tiptoon", "Tiptoon"),
)
