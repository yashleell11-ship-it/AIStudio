"""Map Rawkuma REST payloads and HTML documents to normalized models.

Rawkuma is a WordPress site with a custom (non-Madara) theme. Three of its
surfaces are worth knowing about, because the fast path for every stage of
this connector is a *single* request:

* ``/wp-json/wp/v2/manga`` -- the open WP REST collection. Browse and genre
  filtering come from here as JSON: title, slug, cover thumbnail, genres,
  author, artist and status all arrive in the SAME response, so a catalog
  page costs exactly one request and never fans out per card.
* ``/manga/<slug>/`` -- the series page. It carries JSON-LD metadata *and*
  the complete server-rendered chapter list (verified: One Piece renders all
  193 rows inline, matching the site's own "Chapters (193)" heading), so
  detail + chapter list share one fetch.
* ``/manga/<slug>/chapter-<n>.<id>/`` -- the reader page. Every page image is
  a plain ``<img src>`` inside ``<section data-image-data>``; resolving a
  chapter's images costs one request regardless of page count.

Search runs on the same REST collection (``?search=&orderby=relevance``) with
the returned page re-tiered by title match. The theme also ships a private
``admin-ajax`` search that indexes native Japanese titles, but it is reachable
only by POST and the shared client's ``post_text`` cannot get through the
site's Cloudflare bot check -- see ``connector.py`` for the specifics.

Identity keys are the site's own path fragments and stay OPAQUE:
``series_key`` is the manga slug, ``chapter_key`` is ``<slug>/chapter-<...>``
(it contains a slash and is never split for meaning).
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any
from urllib.parse import urlparse

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

#: rawkuma.com is a static landing page with no catalog on it; every link on
#: it points at rawkuma.net, which is where the manga, the chapter lists and
#: the REST API actually live. Confirmed from the VPS: rawkuma.com/manga/
#: answers 404, rawkuma.net/manga/<slug>/ answers 200.
SITE_BASE = "https://rawkuma.net"

REST_MANGA_PATH = "/wp-json/wp/v2/manga"

#: Trimmed REST projection. The default representation ships the full rendered
#: synopsis for all 24 cards (~1.4 MB/page); this cuts a browse page to ~100 KB
#: while still carrying everything a catalog card renders.
REST_FIELDS = "id,slug,link,title,modified,date,meta"

PAGE_SIZE = 24

#: WP REST exposes no ordering by the theme's popularity meta (its `orderby`
#: enum is author/date/id/include/parent/relevance/slug/title/modified only),
#: so this connector advertises the three orderings the site can genuinely
#: serve rather than aliasing a fake "popular" onto one of them.
SORT_TO_REST: dict[str, tuple[str, str]] = {
    "default": ("modified", "desc"),  # latest chapter uploads
    "latest": ("date", "desc"),  # newest series added to the catalog
    "title": ("title", "asc"),  # A-Z
}

BROWSE_MODES: tuple[BrowseMode, ...] = (
    BrowseMode(id="default", label="Latest Updates"),
    BrowseMode(id="latest", label="Newly Added"),
    BrowseMode(id="title", label="A-Z"),
)

#: WordPress term IDs for the `genre` taxonomy, read from the `searchTerms`
#: bootstrap JSON the site embeds in /library/. The REST collection filters on
#: term IDs (``?genre=6``), not slugs, so the mapping has to live here. Ordered
#: by catalog size; the long tail of one- and two-title genres is left out.
GENRE_TERMS: tuple[tuple[str, str, int], ...] = (
    ("fantasy", "Fantasy", 6),
    ("comedy", "Comedy", 4),
    ("romance", "Romance", 42),
    ("drama", "Drama", 5),
    ("action", "Action", 2),
    ("seinen", "Seinen", 32),
    ("shounen", "Shounen", 7),
    ("slice-of-life", "Slice of Life", 43),
    ("adventure", "Adventure", 3),
    ("school-life", "School Life", 15),
    ("ecchi", "Ecchi", 31),
    ("supernatural", "Supernatural", 12),
    ("harem", "Harem", 48),
    ("shoujo", "Shoujo", 113),
    ("mystery", "Mystery", 24),
    ("mature", "Mature", 23),
    ("josei", "Josei", 357),
    ("sci-fi", "Sci-fi", 16),
    ("psychological", "Psychological", 25),
    ("horror", "Horror", 54),
    ("historical", "Historical", 105),
    ("tragedy", "Tragedy", 26),
    ("sports", "Sports", 143),
    ("gender-bender", "Gender Bender", 100),
    ("yuri", "Yuri", 626),
    ("martial-arts", "Martial Arts", 106),
    ("isekai", "Isekai", 5110),
    ("mecha", "Mecha", 35),
)

GENRE_TERM_IDS: dict[str, int] = {slug: term_id for slug, _label, term_id in GENRE_TERMS}


# --------------------------------------------------------------------------
# ids / paths
# --------------------------------------------------------------------------


def normalize_key(value: str) -> str:
    """Strip the site prefix and surrounding slashes off an identity key.

    Keys stay opaque -- this only removes decoration the caller may have
    round-tripped through a URL, never interprets the remainder.
    """
    text = value.strip()
    for prefix in (f"{SITE_BASE}/", "https://rawkuma.com/", "http://rawkuma.net/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.strip("/")
    if text.startswith("manga/"):
        text = text.removeprefix("manga/")
    return text


def series_id_to_path(series_id: str) -> str:
    return f"/manga/{normalize_key(series_id)}/"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/manga/{normalize_key(chapter_id)}/"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    """Recover the chapter key from a page id built by ``make_page_id``.

    Chapter keys carry slashes and dots but never a colon, so the final colon
    is an unambiguous separator.
    """
    if ":" not in page_id:
        return None
    chapter_id, _, number = page_id.rpartition(":")
    if not chapter_id or not number.isdigit():
        return None
    return chapter_id


def normalize_sort(sort: str | None) -> str:
    if not sort or sort not in SORT_TO_REST:
        return "default"
    return sort


def listing_params(
    page: int,
    *,
    sort: str | None = None,
    genre: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Query for one REST catalog page."""
    orderby, order = SORT_TO_REST[normalize_sort(sort)]
    params: dict[str, Any] = {
        "page": max(1, page),
        "per_page": PAGE_SIZE,
        "orderby": orderby,
        "order": order,
        "_fields": REST_FIELDS,
    }
    if search:
        # Full-text relevance ranking beats the modified-date default for a
        # query, and is the only ordering WP accepts alongside `search`.
        params["search"] = search
        params["orderby"] = "relevance"
        params.pop("order", None)
    if genre:
        term_id = GENRE_TERM_IDS.get(genre)
        if term_id is not None:
            params["genre"] = term_id
    return params


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    return _WS_RE.sub(" ", html_lib.unescape(value)).strip()


def strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    text = re.sub(r"</p\s*>", " ", text, flags=re.I)
    return clean_text(_TAG_RE.sub(" ", text))


# --------------------------------------------------------------------------
# REST catalog
# --------------------------------------------------------------------------


def _tax_names(item: dict[str, Any], taxonomy: str) -> list[str]:
    meta = item.get("meta")
    if not isinstance(meta, dict):
        return []
    terms = meta.get("tax")
    if not isinstance(terms, list):
        return []
    names: list[str] = []
    for term in terms:
        if isinstance(term, dict) and term.get("taxonomy") == taxonomy:
            name = term.get("name")
            if isinstance(name, str) and name.strip():
                names.append(clean_text(name))
    return names


def _inner_meta(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("meta")
    if not isinstance(meta, dict):
        return {}
    inner = meta.get("meta")
    return inner if isinstance(inner, dict) else {}


def series_from_rest(item: dict[str, Any]) -> Series | None:
    """Build a catalog card from one ``/wp/v2/manga`` record.

    Everything here comes out of the record already fetched -- cover, genres,
    author, artist, status -- so a browse page never issues a follow-up
    request per title.
    """
    if not isinstance(item, dict):
        return None
    slug = item.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        return None
    slug = slug.strip()

    title_field = item.get("title")
    raw_title = ""
    if isinstance(title_field, dict):
        raw_title = str(title_field.get("rendered") or "")
    elif isinstance(title_field, str):
        raw_title = title_field
    title = clean_text(raw_title) or slug

    inner = _inner_meta(item)
    cover = inner.get("thumbnail")
    cover_url = cover.strip() if isinstance(cover, str) and cover.strip() else None

    authors = _tax_names(item, "series-author")
    artists = _tax_names(item, "artist")
    statuses = _tax_names(item, "status")

    return Series(
        id=slug,
        title=title,
        canonical_path=series_id_to_path(slug),
        cover_url=cover_url,
        author=", ".join(authors) or None,
        artist=", ".join(artists) or None,
        status=statuses[0] if statuses else None,
        genres=tuple(_tax_names(item, "genre")),
    )


def parse_series_list_json(
    payload: Any,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    """Turn a REST collection page into a paginated listing.

    WordPress reports the collection total only in ``X-WP-Total`` headers,
    which the shared JSON client does not surface, so a full page is taken as
    evidence that another one exists -- the same convention weebcentral uses.
    """
    items: list[Series] = []
    seen: set[str] = set()
    if isinstance(payload, list):
        for entry in payload:
            series = series_from_rest(entry)
            if series is None or series.id in seen:
                continue
            seen.add(series.id)
            items.append(series)
    return PaginatedSeriesList(
        items=items,
        page=max(1, page),
        page_size=page_size,
        total=(max(1, page) - 1) * page_size + len(items),
        api_has_more=len(items) >= page_size,
    )


# --------------------------------------------------------------------------
# search ranking
# --------------------------------------------------------------------------

_RANK_STRIP_RE = re.compile(r"[^0-9a-z\u3000-\u9fff\uff00-\uffef ]+")


def _rank_key(value: str) -> str:
    return _RANK_STRIP_RE.sub(" ", value.casefold()).strip()


def title_relevance_rank(title: str, query: str) -> int:
    """Tier a result by how directly its title answers the query.

    WordPress ranks ``orderby=relevance`` over the whole post body, so a title
    the reader typed verbatim can land below a title that merely mentions the
    word in its synopsis: searching "slime" put "Haisuikou ni Tsumatta Slime"
    above "Tensei Shitara Slime Datta Ken". Re-tiering the page that already
    arrived costs no extra request and cannot disturb paging, because it only
    reorders within the page.
    """
    normalized_title = _rank_key(title)
    normalized_query = _rank_key(query)
    if not normalized_query:
        return 3
    if normalized_title == normalized_query:
        return 0
    if normalized_title.startswith(normalized_query):
        return 1
    if f" {normalized_query} " in f" {normalized_title} ":
        return 2
    return 3


def rerank_by_title(listing: PaginatedSeriesList, query: str) -> PaginatedSeriesList:
    """Stable-sort one search page so verbatim title matches lead it."""
    ranked = sorted(
        enumerate(listing.items),
        key=lambda pair: (title_relevance_rank(pair[1].title, query), pair[0]),
    )
    return PaginatedSeriesList(
        items=[series for _index, series in ranked],
        page=listing.page,
        page_size=listing.page_size,
        total=listing.total,
        api_has_more=listing.api_has_more,
    )


# --------------------------------------------------------------------------
# series detail
# --------------------------------------------------------------------------

LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I,
)

#: The synopsis is rendered twice: a clamped teaser (``data-show="true"``,
#: ending in an ellipsis) and the full body (``data-show="false"``). Prefer
#: the full one; fall back to the teaser only if the markup changes.
FULL_DESCRIPTION_RE = re.compile(
    r'<div\s+data-show="false"\s+itemprop="description"[^>]*>(.*?)</div>',
    re.S | re.I,
)
ANY_DESCRIPTION_RE = re.compile(
    r'<div[^>]*itemprop="description"[^>]*>(.*?)</div>',
    re.S | re.I,
)


def _comic_series_ld(html: str) -> dict[str, Any] | None:
    for body in LD_JSON_RE.findall(html):
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        kind = data.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "ComicSeries" in kinds or "Book" in kinds:
            return data
    return None


def _person_name(value: Any) -> str | None:
    if isinstance(value, dict):
        name = value.get("name")
        return clean_text(str(name)) if name else None
    if isinstance(value, str) and value.strip():
        return clean_text(value)
    if isinstance(value, list):
        names = [n for n in (_person_name(v) for v in value) if n]
        return ", ".join(names) or None
    return None


def parse_series_detail(html: str, series_id: str) -> Series | None:
    """Read series metadata out of the page's JSON-LD block.

    The theme emits a schema.org ``ComicSeries`` object on every series page
    (verified across a VPS sample of 28 titles), which is a far steadier
    target than its Tailwind class soup.
    """
    data = _comic_series_ld(html)
    if data is None:
        return None
    title = clean_text(str(data.get("name") or data.get("headline") or ""))
    if not title:
        return None

    description = None
    full = FULL_DESCRIPTION_RE.search(html) or ANY_DESCRIPTION_RE.search(html)
    if full:
        description = strip_html(full.group(1)) or None
    if not description:
        raw = data.get("description")
        if isinstance(raw, str):
            description = strip_html(raw) or None

    image = data.get("image")
    cover_url = None
    if isinstance(image, dict):
        url = image.get("url")
        cover_url = url.strip() if isinstance(url, str) and url.strip() else None
    elif isinstance(image, str) and image.strip():
        cover_url = image.strip()

    genres_raw = data.get("genre")
    if isinstance(genres_raw, str):
        genres = tuple(clean_text(g) for g in genres_raw.split(",") if g.strip())
    elif isinstance(genres_raw, list):
        genres = tuple(clean_text(str(g)) for g in genres_raw if str(g).strip())
    else:
        genres = ()

    status_raw = data.get("creativeWorkStatus")
    status = clean_text(str(status_raw)) if status_raw else None

    return Series(
        id=series_id,
        title=title,
        canonical_path=series_id_to_path(series_id),
        description=description,
        cover_url=cover_url,
        author=_person_name(data.get("author")),
        artist=_person_name(data.get("illustrator")),
        status=status,
        genres=genres,
    )


# --------------------------------------------------------------------------
# chapters
# --------------------------------------------------------------------------

CHAPTER_LIST_RE = re.compile(r'<div[^>]+id="chapter-list"[^>]*>(.*)', re.S | re.I)
CHAPTER_SPLIT_RE = re.compile(r"(?=<div[^>]+data-chapter-number=)", re.I)
CHAPTER_NUMBER_RE = re.compile(r'data-chapter-number="([^"]*)"', re.I)
CHAPTER_HREF_RE = re.compile(r'href="https?://[^"/]+/manga/([^"]+?)/?"', re.I)
CHAPTER_LABEL_RE = re.compile(r"<span>([^<]+)</span>", re.I)
CHAPTER_TIME_RE = re.compile(r'<time\s+datetime="([^"]+)"', re.I)


def parse_chapter_number(value: str) -> float | None:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return None


def parse_chapters(html: str, series_id: str) -> list[Chapter]:
    """Read the whole chapter list out of the series page.

    The list is fully server-rendered -- there is no second "load chapters"
    endpoint to call and no per-chapter request -- so this is the entire cost
    of the chapter stage once the series page is in hand.
    """
    container = CHAPTER_LIST_RE.search(html)
    if container is None:
        return []
    prefix = f"{normalize_key(series_id)}/"
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for block in CHAPTER_SPLIT_RE.split(container.group(1))[1:]:
        href = CHAPTER_HREF_RE.search(block)
        if href is None:
            continue
        chapter_key = href.group(1).strip("/")
        if not chapter_key.startswith(prefix) or chapter_key in seen:
            continue
        seen.add(chapter_key)
        number_match = CHAPTER_NUMBER_RE.search(block)
        number = parse_chapter_number(number_match.group(1)) if number_match else None
        label_match = CHAPTER_LABEL_RE.search(block)
        label = clean_text(label_match.group(1)) if label_match else ""
        if not label:
            label = f"Chapter {number:g}" if number is not None else chapter_key
        time_match = CHAPTER_TIME_RE.search(block)
        chapters.append(
            Chapter(
                id=chapter_key,
                series_id=normalize_key(series_id),
                title=label,
                number=number,
                # Rawkuma's series page carries no per-chapter page count; the
                # connector backfills it from its page cache once a chapter
                # has been opened.
                page_count=0,
                release_date=time_match.group(1) if time_match else None,
            )
        )
    chapters.sort(key=lambda chapter: (chapter.number is None, chapter.number or 0.0))
    return chapters


# --------------------------------------------------------------------------
# chapter pages
# --------------------------------------------------------------------------

PAGE_SECTION_RE = re.compile(
    r"<section[^>]+data-image-data[^>]*>(.*?)</section>",
    re.S | re.I,
)
PAGE_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)

#: Rawkuma serves page images off two hosts, both under kyut.dev
#: (kuma.kyut.dev and rcdn.kyut.dev). Anything else inside the reader section
#: is theme chrome -- a banner, a spacer, a house ad -- and must not be handed
#: to the reader as a page, which would shift every page number after it.
PAGE_HOST_SUFFIX = "kyut.dev"


def is_page_image_url(url: str) -> bool:
    """True when ``url`` points at Rawkuma's page-image CDN.

    Matched on the parsed host, not as a substring of the whole URL: a
    substring test would accept ``https://ads.example/?ref=kyut.dev``.
    """
    host = (urlparse(url).hostname or "").lower()
    return host == PAGE_HOST_SUFFIX or host.endswith(f".{PAGE_HOST_SUFFIX}")


def parse_chapter_pages(html: str, chapter_id: str) -> list[Page]:
    """Collect every page image from one reader document.

    All images are plain ``<img src>`` inside ``<section data-image-data>`` --
    no lazy-load attribute, no per-page JSON call -- so a whole chapter
    resolves in the single fetch that produced ``html``.
    """
    section = PAGE_SECTION_RE.search(html)
    if section is None:
        return []
    chapter_key = normalize_key(chapter_id)
    pages: list[Page] = []
    seen: set[str] = set()
    for url in PAGE_IMG_RE.findall(section.group(1)):
        url = html_lib.unescape(url.strip())
        if not url or url in seen:
            continue
        if not is_page_image_url(url):
            continue
        seen.add(url)
        number = len(pages) + 1
        pages.append(
            Page(
                id=make_page_id(chapter_key, number),
                chapter_id=chapter_key,
                number=number,
                remote_url=url,
            )
        )
    return pages
