"""Map 18PornComic (manga-club theme) HTML to normalized connector models."""

from __future__ import annotations

import base64
import html
import re
from urllib.parse import quote

from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SITE_BASE = "https://18porncomic.com"
PAGE_SIZE = 20

STORY_ITEM_RE = re.compile(
    r'<div class="story_item">(.*?)</div>\s*</div>\s*</div>',
    re.S | re.I,
)
STORY_SLUG_RE = re.compile(
    r'href="https?://[^"]+/comic/([^"]+)"[^>]*title="([^"]*)"',
    re.I,
)
STORY_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
STORY_TITLE_RE = re.compile(
    r'<div class="mg_name">\s*<a href="https?://[^"]+/comic/([^"]+)">([^<]+)</a>',
    re.I | re.S,
)

PAGINATION_RE = re.compile(r"/list-manga/(\d+)", re.I)

CHAPTER_LINK_RE = re.compile(
    r'<a[^>]+href="(?:https?://[^"]+)?/comic/([^/]+)/([^"#?]+)"[^>]*class="chapter_num"[^>]*>'
    r"\s*#\s*([^<]+)</a>",
    re.I | re.S,
)
CHAPTER_SEGMENT_NUMBER_RE = re.compile(r"chapter-(\d+)", re.I)
CHAPTER_LABEL_NUMBER_RE = re.compile(r"chapter\s+(\d+)", re.I)

SLIDES_PATH_RE = re.compile(r"slides_p_path\s*=\s*\[(.*?)\];", re.S)
ENCODED_URL_RE = re.compile(r'"([A-Za-z0-9+/=]+)"')

H1_TITLE_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>", re.I)
META_OG_RE = re.compile(
    r'<meta\s+property="og:(description|image)"\s+content="([^"]*)"',
    re.I,
)
INFO_VALUE_RE = re.compile(
    r'<div class="info_label"[^>]*>.*?{label}.*?</div>\s*'
    r'<div class="info_value"[^>]*>(.*?)</div>',
    re.S | re.I,
)
GENRE_LINK_RE = re.compile(r'href="https?://[^"]+/manga-list/[^"]+">([^<]+)</a>', re.I)


def listing_path(page: int, *, sort: str | None = None, query: str | None = None) -> str:
    path = "/list-manga" if page <= 1 else f"/list-manga/{page}"
    params: list[str] = []
    if query:
        params.append(f"search={quote(query)}")
    if sort == "popular":
        params.append("sort=views")
    if params:
        return f"{path}?{'&'.join(params)}"
    return path


def series_id_to_path(series_id: str) -> str:
    slug = series_id.strip().strip("/")
    if slug.startswith("comic/"):
        slug = slug.removeprefix("comic/")
    return f"/comic/{slug}"


def chapter_id_to_path(chapter_id: str) -> str:
    value = chapter_id.strip().strip("/")
    if value.startswith("comic/"):
        value = value.removeprefix("comic/")
    return f"/comic/{value}"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _parse_info_label(block: str, label: str) -> str | None:
    pattern = (
        rf'<div class="info_label"[^>]*>.*?{re.escape(label)}.*?</div>\s*'
        r'<div class="info_value"[^>]*>(.*?)</div>'
    )
    match = re.search(pattern, block, re.S | re.I)
    if not match:
        return None
    value = _clean_text(match.group(1))
    return value or None


def _absolute_url(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if not value or value.startswith("data:"):
        return None
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://"):
        return "https://" + value.removeprefix("http://")
    if value.startswith("https://"):
        return value
    if value.startswith("/"):
        return f"{SITE_BASE}{value}"
    return f"{SITE_BASE}/{value.lstrip('/')}"


def parse_series_list(document: str, *, page: int) -> PaginatedSeriesList:
    items: list[Series] = []
    seen: set[str] = set()
    for block in STORY_ITEM_RE.findall(document):
        title_match = STORY_TITLE_RE.search(block)
        if not title_match:
            slug_match = STORY_SLUG_RE.search(block)
            if not slug_match:
                continue
            slug, title = slug_match.group(1), slug_match.group(2)
        else:
            slug, title = title_match.group(1), title_match.group(2)
        if slug in seen:
            continue
        seen.add(slug)
        img_match = STORY_IMG_RE.search(block)
        cover_url = _absolute_url(img_match.group(1) if img_match else None)
        items.append(
            Series(
                id=slug,
                title=_clean_text(title) or slug,
                cover_url=cover_url,
            )
        )

    page_numbers = [int(value) for value in PAGINATION_RE.findall(document)]
    total_pages = max(page_numbers) if page_numbers else max(page, 1)
    total = total_pages * PAGE_SIZE if total_pages > 1 else len(items)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=total,
        api_has_more=page < total_pages,
    )


def parse_series_detail(document: str, *, series_id: str) -> Series | None:
    title_match = H1_TITLE_RE.search(document)
    title = _clean_text(title_match.group(1)) if title_match else series_id
    og: dict[str, str] = {}
    for key, value in META_OG_RE.findall(document):
        og[key.lower()] = html.unescape(value)
    author = _parse_info_label(document, "Author")
    artist = _parse_info_label(document, "Artist")
    status_raw = _parse_info_label(document, "Status")
    status = status_raw.lower().replace("on going", "ongoing") if status_raw else None
    genres = tuple(dict.fromkeys(GENRE_LINK_RE.findall(document)))
    chapters = parse_chapters(document, series_id=series_id)
    return Series(
        id=series_id,
        title=title,
        chapter_count=len(chapters),
        description=og.get("description"),
        cover_url=_absolute_url(og.get("image")),
        author=author,
        artist=artist,
        status=status,
        genres=genres,
        latest_chapter=chapters[0].title if chapters else None,
    )


def _chapter_number(segment: str, label: str) -> float | None:
    segment_match = CHAPTER_SEGMENT_NUMBER_RE.search(segment)
    if segment_match:
        return float(segment_match.group(1))
    if segment.isdigit():
        return float(segment)
    label_match = CHAPTER_LABEL_NUMBER_RE.search(label)
    if label_match:
        return float(label_match.group(1))
    if segment.lower() == "english":
        return 1.0
    return None


def parse_chapters(document: str, *, series_id: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for slug, segment, label in CHAPTER_LINK_RE.findall(document):
        if slug != series_id:
            continue
        segment = segment.strip().strip("/")
        if not segment:
            continue
        chapter_id = f"{slug}/{segment}"
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        clean_label = _clean_text(label)
        number = _chapter_number(segment, clean_label)
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=normalize_chapter_title(clean_label or segment),
                number=number,
                page_count=0,
            )
        )
    chapters.sort(
        key=lambda item: (
            item.number is None,
            -(item.number or 0.0),
            item.title.casefold(),
        ),
    )
    return chapters


def parse_chapter_pages(document: str, *, chapter_id: str) -> list[Page]:
    match = SLIDES_PATH_RE.search(document)
    if not match:
        return []
    encoded = ENCODED_URL_RE.findall(match.group(1))
    pages: list[Page] = []
    for index, token in enumerate(encoded, start=1):
        try:
            url = base64.b64decode(token).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        remote_url = _absolute_url(url)
        if not remote_url:
            continue
        pages.append(
            Page(
                id=make_page_id(chapter_id, index),
                chapter_id=chapter_id,
                number=index,
                remote_url=remote_url,
            )
        )
    return pages
