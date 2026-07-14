"""Map Bbato (bbato.com) HTML pages to normalized connector models."""

from __future__ import annotations

import html
import json
import re
from urllib.parse import quote, urljoin

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://bbato.com"
IMAGE_HOST = "merrypsycho.xyz"
PAGE_SIZE = 30

POSTER_RE = re.compile(
    r'<a href="(?:https://bbato\.com)?/manga/([^"/]+)" class="poster">.*?'
    r'data-src="(https://[^"]+)"[^>]*alt="([^"]*)"',
    re.S | re.I,
)
H1_RE = re.compile(r'<h1[^>]*itemprop="name"[^>]*>([^<]+)</h1>', re.I)
H1_FALLBACK_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>", re.I)
COVER_RE = re.compile(
    r'<a[^>]*class="poster"[^>]*>.*?'
    r'data-src="(https://[^"]+)"',
    re.S | re.I,
)
STATUS_RE = re.compile(r'<div class="info">\s*<p>([^<]+)</p>', re.I)
LAST_CHAPTER_URL_RE = re.compile(r'window\.lastChapterUrl\s*=\s*"([^"]+)"')
FIRST_CHAPTER_URL_RE = re.compile(r'window\.firstChapterUrl\s*=\s*"([^"]+)"')
SERIES_CHAPTER_RE = re.compile(
    r'<li class="item"[^>]*>\s*'
    r'<a href="(?:https://bbato\.com)?/read/([^"]+/chapter-[^"]+)"[^>]*'
    r'title="([^"]*)"',
    re.I,
)
CHAPTER_OPTION_RE = re.compile(
    r'<option[^>]*value="(?:https://bbato\.com)?/read/([^"]+/chapter-[^"]+)"[^>]*>'
    r"([^<]+)",
    re.I,
)
PAGE_IMG_RE = re.compile(
    r"<img[^>]*data-number=['\"](\d+)['\"][^>]*>",
    re.I,
)
IMG_URL_RE = re.compile(
    r"""(?:data-src|data-fallback|src)=['"](https://[^'"]*merrypsycho[^'"]+)['"]""",
    re.I,
)
TYPE_PAGE_RE = re.compile(r"/type/([a-z]+)/page/(\d+)", re.I)
GENRE_PAGE_RE = re.compile(r"/genre/([a-z0-9-]+)/page/(\d+)", re.I)
FILTER_PAGE_RE = re.compile(
    r"filter\?keyword=[^\"'&]+(?:&amp;|&)page=(\d+)",
    re.I,
)
LD_JSON_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>',
    re.S | re.I,
)
CHAPTER_NUMBER_RE = re.compile(r"chapter-(\d+(?:\.\d+)?)$", re.I)

BROWSE_MODES: tuple[BrowseMode, ...] = (
    BrowseMode(id="manga", label="Manga"),
    BrowseMode(id="manhwa", label="Manhwa"),
    BrowseMode(id="manhua", label="Manhua"),
)

# Genre slugs from bbato.com nav (stable catalog filters).
GENRES: tuple[BrowseMode, ...] = (
    BrowseMode(id="action", label="Action"),
    BrowseMode(id="adventure", label="Adventure"),
    BrowseMode(id="avant-garde", label="Avant Garde"),
    BrowseMode(id="boys-love", label="Boys Love"),
    BrowseMode(id="comedy", label="Comedy"),
    BrowseMode(id="demons", label="Demons"),
    BrowseMode(id="drama", label="Drama"),
    BrowseMode(id="ecchi", label="Ecchi"),
    BrowseMode(id="fantasy", label="Fantasy"),
    BrowseMode(id="girls-love", label="Girls Love"),
    BrowseMode(id="gourmet", label="Gourmet"),
    BrowseMode(id="harem", label="Harem"),
    BrowseMode(id="horror", label="Horror"),
    BrowseMode(id="isekai", label="Isekai"),
    BrowseMode(id="iyashikei", label="Iyashikei"),
    BrowseMode(id="josei", label="Josei"),
    BrowseMode(id="kids", label="Kids"),
    BrowseMode(id="magic", label="Magic"),
    BrowseMode(id="mahou-shoujo", label="Mahou Shoujo"),
    BrowseMode(id="martial-arts", label="Martial Arts"),
    BrowseMode(id="mecha", label="Mecha"),
    BrowseMode(id="military", label="Military"),
    BrowseMode(id="music", label="Music"),
    BrowseMode(id="mystery", label="Mystery"),
    BrowseMode(id="psychological", label="Psychological"),
    BrowseMode(id="racing", label="Racing"),
    BrowseMode(id="romance", label="Romance"),
    BrowseMode(id="samurai", label="Samurai"),
    BrowseMode(id="school", label="School"),
    BrowseMode(id="sci-fi", label="Sci-Fi"),
    BrowseMode(id="seinen", label="Seinen"),
    BrowseMode(id="shoujo", label="Shoujo"),
    BrowseMode(id="shounen", label="Shounen"),
    BrowseMode(id="slice-of-life", label="Slice of Life"),
    BrowseMode(id="space", label="Space"),
    BrowseMode(id="sports", label="Sports"),
    BrowseMode(id="super-power", label="Super Power"),
    BrowseMode(id="supernatural", label="Supernatural"),
    BrowseMode(id="suspense", label="Suspense"),
    BrowseMode(id="vampire", label="Vampire"),
    BrowseMode(id="work-life", label="Work Life"),
)

_TYPE_SORTS = frozenset({"manga", "manhwa", "manhua", "default", "latest"})


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def series_id_to_path(series_id: str) -> str:
    return f"/manga/{series_id.strip().strip('/')}"


def chapter_id_to_path(chapter_id: str) -> str:
    return f"/read/{chapter_id.strip().strip('/')}"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def parse_chapter_number(chapter_id: str) -> float | None:
    match = CHAPTER_NUMBER_RE.search(chapter_id.strip().strip("/"))
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def normalize_type_sort(sort: str | None) -> str:
    if not sort or sort in {"default", "latest"}:
        return "manga"
    if sort in _TYPE_SORTS:
        return sort
    return "manga"


def listing_path(page: int, *, sort: str | None = None) -> str:
    kind = normalize_type_sort(sort)
    if page <= 1:
        return f"/type/{kind}"
    return f"/type/{kind}/page/{page}"


def search_path(query: str, page: int) -> str:
    encoded = quote(query.strip())
    if page <= 1:
        return f"/filter?keyword={encoded}"
    return f"/filter?keyword={encoded}&page={page}"


def genre_path(genre: str, page: int) -> str:
    slug = genre.strip().strip("/").lower()
    if page <= 1:
        return f"/genre/{slug}"
    return f"/genre/{slug}/page/{page}"


def _extract_total_pages(document: str, *, kind: str = "type", slug: str = "manga") -> int:
    if kind == "filter":
        pages = [int(value) for value in FILTER_PAGE_RE.findall(document)]
    elif kind == "genre":
        pages = [
            int(num)
            for genre_slug, num in GENRE_PAGE_RE.findall(document)
            if genre_slug.lower() == slug.lower()
        ]
    else:
        pages = [
            int(num)
            for type_slug, num in TYPE_PAGE_RE.findall(document)
            if type_slug.lower() == slug.lower()
        ]
    if pages:
        return max(pages)
    return 1


def parse_series_cards(document: str) -> list[Series]:
    seen: set[str] = set()
    items: list[Series] = []
    for series_id, cover_url, title in POSTER_RE.findall(document):
        if series_id in seen:
            continue
        seen.add(series_id)
        items.append(
            Series(
                id=series_id,
                title=_clean_text(title) or series_id,
                cover_url=cover_url,
                canonical_path=series_id_to_path(series_id),
            )
        )
    return items


def parse_series_list(
    document: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
    sort: str | None = None,
) -> PaginatedSeriesList:
    items = parse_series_cards(document)
    kind = normalize_type_sort(sort)
    total_pages = _extract_total_pages(document, kind="type", slug=kind)
    return _paginate(items, page=page, page_size=page_size, total_pages=total_pages)


def parse_search_results(
    document: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(document)
    pages = [int(value) for value in FILTER_PAGE_RE.findall(document)]
    total_pages = max(pages) if pages else (1 if not items else page)
    if pages and page not in pages and page > 1 and items:
        total_pages = max(total_pages, page)
    return _paginate(items, page=page, page_size=page_size, total_pages=total_pages)


def parse_genre_results(
    document: str,
    *,
    page: int,
    genre: str,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items = parse_series_cards(document)
    slug = genre.strip().strip("/").lower()
    pages = [
        int(num)
        for g, num in GENRE_PAGE_RE.findall(document)
        if g.lower() == slug
    ]
    total_pages = max(pages) if pages else 1
    return _paginate(items, page=page, page_size=page_size, total_pages=total_pages)


def _paginate(
    items: list[Series],
    *,
    page: int,
    page_size: int,
    total_pages: int,
) -> PaginatedSeriesList:
    if total_pages <= 1:
        total = len(items)
        has_more = False
    else:
        total = total_pages * page_size
        if page >= total_pages:
            total = (total_pages - 1) * page_size + len(items)
        has_more = page < total_pages
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def _parse_ld_json(document: str) -> dict:
    for body in LD_JSON_RE.findall(document):
        text = body.strip()
        if '"author"' not in text and '"genre"' not in text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and (
            payload.get("@type") in {"ComicSeries", "Book", "CreativeWork"}
            or "author" in payload
        ):
            return payload
    return {}


def _authors_from_ld(payload: dict) -> str | None:
    authors = payload.get("author")
    names: list[str] = []
    if isinstance(authors, list):
        for item in authors:
            if isinstance(item, dict) and item.get("name"):
                names.append(_clean_text(str(item["name"])))
            elif isinstance(item, str):
                names.append(_clean_text(item))
    elif isinstance(authors, dict) and authors.get("name"):
        names.append(_clean_text(str(authors["name"])))
    elif isinstance(authors, str):
        names.append(_clean_text(authors))
    names = [name for name in names if name]
    return ", ".join(names) if names else None


def _genres_from_ld(payload: dict) -> tuple[str, ...]:
    genres = payload.get("genre")
    if isinstance(genres, list):
        return tuple(_clean_text(str(g)) for g in genres if str(g).strip())
    if isinstance(genres, str) and genres.strip():
        return (_clean_text(genres),)
    return ()


def parse_series_detail(document: str, series_id: str) -> Series | None:
    title_match = H1_RE.search(document) or H1_FALLBACK_RE.search(document)
    ld = _parse_ld_json(document)
    if title_match is None and not ld.get("name"):
        return None
    title = _clean_text(title_match.group(1)) if title_match else _clean_text(str(ld["name"]))

    cover_match = COVER_RE.search(document)
    cover_url = cover_match.group(1) if cover_match else None
    if cover_url is None and isinstance(ld.get("thumbnailUrl"), str):
        cover_url = ld["thumbnailUrl"]
    elif cover_url is None and isinstance(ld.get("image"), str):
        cover_url = ld["image"]

    status_match = STATUS_RE.search(document)
    status = _clean_text(status_match.group(1)) if status_match else None

    description = None
    if isinstance(ld.get("description"), str):
        description = _clean_text(ld["description"])

    episode_count = ld.get("numberOfEpisodes")
    chapter_count = 0
    if isinstance(episode_count, int):
        chapter_count = episode_count
    elif isinstance(episode_count, str) and episode_count.isdigit():
        chapter_count = int(episode_count)

    return Series(
        id=series_id,
        title=title,
        chapter_count=chapter_count,
        canonical_path=series_id_to_path(series_id),
        description=description,
        cover_url=cover_url,
        author=_authors_from_ld(ld),
        status=status,
        genres=_genres_from_ld(ld),
    )


def last_chapter_path(document: str) -> str | None:
    match = LAST_CHAPTER_URL_RE.search(document) or FIRST_CHAPTER_URL_RE.search(document)
    if match is None:
        return None
    url = match.group(1).strip()
    if url.startswith("http"):
        path = urljoin(SITE_BASE, url.replace(SITE_BASE, ""))
        return path[len(SITE_BASE) :] if path.startswith(SITE_BASE) else path
    return url if url.startswith("/") else f"/{url}"


def parse_chapters_from_series(document: str, series_id: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_id, title in SERIES_CHAPTER_RE.findall(document):
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=_clean_text(title) or chapter_id.rsplit("/", 1)[-1],
                number=parse_chapter_number(chapter_id),
                page_count=0,
            )
        )
    chapters.sort(key=lambda item: (item.number is None, item.number or 0.0, item.id))
    return chapters


def parse_chapters_from_reader(document: str, series_id: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_id, title in CHAPTER_OPTION_RE.findall(document):
        if not chapter_id.startswith(f"{series_id}/"):
            # Still accept when series_id matches the path prefix loosely.
            if f"/{series_id}/" not in f"/{chapter_id}":
                continue
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=_clean_text(title) or chapter_id.rsplit("/", 1)[-1],
                number=parse_chapter_number(chapter_id),
                page_count=0,
            )
        )
    chapters.sort(key=lambda item: (item.number is None, item.number or 0.0, item.id))
    return chapters


def parse_chapter_pages(document: str, chapter_id: str) -> list[Page]:
    pages: list[Page] = []
    seen: set[int] = set()
    for match in PAGE_IMG_RE.finditer(document):
        number = int(match.group(1))
        if number in seen:
            continue
        tag = match.group(0)
        url_match = IMG_URL_RE.search(tag)
        if url_match is None:
            # Prefer data-src/data-fallback from a wider window after the tag start.
            window = document[match.start() : match.start() + 500]
            url_match = IMG_URL_RE.search(window)
        if url_match is None:
            continue
        seen.add(number)
        page_number = number + 1  # site is 0-based; app pages are 1-based
        pages.append(
            Page(
                id=make_page_id(chapter_id, page_number),
                chapter_id=chapter_id,
                number=page_number,
                remote_url=url_match.group(1),
            )
        )
    pages.sort(key=lambda item: item.number)
    return pages
