"""Map ComicAsura HTML pages to normalized connector models."""

from __future__ import annotations

import html
import re
from urllib.parse import quote, urlencode

from connectors.ids import fully_unquote
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SITE_BASE = "https://comicasura.net"
PAGE_SIZE = 15
LISTING_PATH = "/advanced-search"

# Grid cards on /advanced-search: cover thumb lives inside the series anchor.
SERIES_CARD_RE = re.compile(
    r'<a href="(?:https://comicasura\.net)?/manga/(?P<slug>[^"/#?]+)">\s*'
    r'<div class="w-full block[\s\S]*?'
    r'<img\s+alt="(?P<title>[^"]+)"\s+title="[^"]+"[\s\S]*?'
    r'src="(?P<cover>https://[^"]+)"',
    re.I,
)

CHAPTER_HREF_RE = re.compile(
    r'href="(?:https://comicasura\.net)?/manga/(?P<series>[^"/]+)/(?P<chslug>chapter-[^"]+)"',
    re.I,
)

# Reader pages use single-quoted src attributes with a CDN fallback in onerror.
PAGE_IMG_RE = re.compile(
    r"<img\s+src='(https://img-r\d*\.2xstorage\.com/[^']+)'",
    re.I,
)

OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
    re.I,
)
H1_RE = re.compile(r"<h1[^>]*>\s*([^<]+?)\s*</h1>", re.I)
AUTHOR_RE = re.compile(r">Author</div>\s*<div[^>]*>\s*([^<]+)", re.I)
STATUS_RE = re.compile(r">Status</div>\s*<div[^>]*>\s*([^<]+)", re.I)
GENRE_RE = re.compile(
    r'href="(?:https://comicasura\.net)?/manga-list/[^"]+"[^>]*>\s*([^<]+)',
    re.I,
)
NEXT_PAGE_RE = re.compile(
    r'href="[^"]*advanced-search\?[^"]*page=(?P<page>\d+)[^"]*"[^>]*>\s*Next',
    re.I,
)


def _clean_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def series_id_from_href(href: str) -> str:
    raw = fully_unquote(href).strip().strip("/")
    if "/manga/" in raw:
        raw = raw.split("/manga/", 1)[1]
    return raw.split("/", 1)[0].strip()


def series_path(series_id: str) -> str:
    return f"/manga/{series_id.strip().strip('/')}"


def chapter_path(chapter_id: str) -> str:
    """Map ``series/chapter-slug`` chapter ids to reader paths."""
    normalized = fully_unquote(chapter_id).strip().strip("/")
    if normalized.startswith("manga/"):
        normalized = normalized[len("manga/") :]
    return f"/manga/{normalized}"


def make_chapter_id(series_id: str, chapter_slug: str) -> str:
    return f"{series_id.strip().strip('/')}/{chapter_slug.strip().strip('/')}"


def parse_chapter_id(chapter_id: str) -> tuple[str, str] | None:
    normalized = fully_unquote(chapter_id).strip().strip("/")
    if normalized.startswith("manga/"):
        normalized = normalized[len("manga/") :]
    if "/chapter-" not in normalized:
        return None
    series_id, _, chapter_slug = normalized.partition("/")
    if not series_id or not chapter_slug.startswith("chapter-"):
        return None
    return series_id, chapter_slug


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def chapter_number_from_slug(chapter_slug: str) -> float | None:
    raw = chapter_slug.strip().removeprefix("chapter-").removeprefix("Chapter-")
    if not raw:
        return None
    # chapter-0-1 → 0.1 ; chapter-176 → 176
    normalized = raw.replace("-", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def listing_path(
    page: int,
    *,
    search: str | None = None,
    sort: str | None = None,
) -> str:
    params: dict[str, str] = {}
    if page > 1:
        params["page"] = str(page)
    if search:
        params["name"] = search
    if sort and sort not in {"default", "latest"}:
        params["sort"] = sort
    elif sort == "latest":
        params["sort"] = "latest"
    if not params:
        return LISTING_PATH
    return f"{LISTING_PATH}?{urlencode(params, quote_via=quote)}"


def parse_series_list(html_text: str, *, page: int, page_size: int = PAGE_SIZE) -> PaginatedSeriesList:
    items: list[Series] = []
    seen: set[str] = set()
    for match in SERIES_CARD_RE.finditer(html_text):
        series_id = _clean_text(match.group("slug"))
        if not series_id or series_id in seen:
            continue
        seen.add(series_id)
        title = _clean_text(match.group("title")) or series_id.replace("-", " ")
        items.append(
            Series(
                id=series_id,
                title=title,
                cover_url=_clean_text(match.group("cover")),
                canonical_path=series_path(series_id),
            )
        )

    next_match = NEXT_PAGE_RE.search(html_text)
    has_more = False
    if next_match:
        try:
            has_more = int(next_match.group("page")) > page
        except ValueError:
            has_more = len(items) >= page_size
    elif len(items) >= page_size:
        has_more = True

    total = (page - 1) * page_size + len(items)
    if has_more:
        total += page_size

    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def parse_series_detail(html_text: str, series_id: str) -> Series | None:
    title_match = H1_RE.search(html_text)
    if not title_match:
        title_match = re.search(r"<title>\s*Read\s+([^|<]+?)\s*\|", html_text, re.I)
    if not title_match:
        return None
    title = _clean_text(title_match.group(1))

    cover_url = None
    og = OG_IMAGE_RE.search(html_text)
    if og:
        cover_url = _clean_text(og.group(1))

    author_match = AUTHOR_RE.search(html_text)
    status_match = STATUS_RE.search(html_text)

    genres: list[str] = []
    seen_genres: set[str] = set()
    for match in GENRE_RE.finditer(html_text):
        name = _clean_text(match.group(1))
        key = name.casefold()
        if not name or key in seen_genres:
            continue
        seen_genres.add(key)
        genres.append(name)

    return Series(
        id=series_id,
        title=title,
        canonical_path=series_path(series_id),
        cover_url=cover_url,
        author=_clean_text(author_match.group(1)) if author_match else None,
        status=_clean_text(status_match.group(1)) if status_match else None,
        genres=tuple(genres),
    )


def parse_chapters(html_text: str, series_id: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for match in CHAPTER_HREF_RE.finditer(html_text):
        if match.group("series") != series_id:
            continue
        chapter_slug = _clean_text(match.group("chslug"))
        chapter_id = make_chapter_id(series_id, chapter_slug)
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        number = chapter_number_from_slug(chapter_slug)
        raw_title = f"Chapter {number}" if number is not None else chapter_slug
        title = normalize_chapter_title(raw_title) or raw_title
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=str(title),
                number=number,
                page_count=0,
            )
        )
    chapters.sort(key=lambda chapter: chapter.number if chapter.number is not None else 0.0)
    return chapters


def parse_chapter_pages(html_text: str, chapter_id: str) -> list[Page]:
    pages: list[Page] = []
    seen: set[str] = set()
    for url in PAGE_IMG_RE.findall(html_text):
        cleaned = _clean_text(url)
        if not cleaned or cleaned in seen:
            continue
        # Skip cover thumbs that appear in sidebars.
        if "/thumb/" in cleaned:
            continue
        seen.add(cleaned)
        index = len(pages) + 1
        pages.append(
            Page(
                id=f"{chapter_id}:{index}",
                chapter_id=chapter_id,
                number=index,
                remote_url=cleaned,
            )
        )
    return pages
