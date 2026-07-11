"""Map akuma.moe HTML to normalized connector models."""

from __future__ import annotations

import html
import json
import re
from urllib.parse import parse_qs, quote, urlparse

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://akuma.moe"
PAGE_SIZE = 60
ENGLISH_LANGUAGE_QUERY = "language:english"

LISTING_ITEM_RE = re.compile(
    r'<li id="([a-z0-9]+)" class="category-[^"]*">.*?'
    r'<div class="title"><a href="(?:https://akuma\.moe)?/g/([^"/]+)">([^<]+)</a>',
    re.S | re.I,
)
NEXT_LINK_RE = re.compile(
    r'<a class="page-link" href="([^"]+)" rel="next"',
    re.I,
)
TITLE_RE = re.compile(r"<title>([^<]+?)\s*—\s*akuma\.moe</title>", re.I)
ENTRY_TITLE_RE = re.compile(
    r'<h1 class="entry-title[^"]*">([^<]+)</h1>',
    re.I,
)
COVER_RE = re.compile(
    r'<img class="img-thumbnail" src="(https://[^"]+)"',
    re.I,
)
MEDIA_BASE_RE = re.compile(r"(https://s\d+\.akuma\.moe/\d+)/", re.I)
PAGE_COUNT_RE = re.compile(
    r'<li class="meta-data pages">\s*<span class="data">Pages</span>\s*'
    r'<span class="value">(\d+)</span>',
    re.S | re.I,
)
META_VALUE_RE = re.compile(
    r'<li class="meta-data[^"]*">\s*<span class="data[^"]*">([^<]+)</span>\s*'
    r"(.*?)</li>",
    re.S | re.I,
)
META_TAG_LINK_RE = re.compile(
    r'<a[^>]+>([^<]+)</a>',
    re.I,
)
UPLOADED_RE = re.compile(
    r'<time datetime="([^"]+)"',
    re.I,
)
IMG_PRT_RE = re.compile(r'img_prt\s*=\s*"([^"]+)"', re.I)
THUMBNAILS_ACT_RE = re.compile(
    r'act\s*:\s*"(https://akuma\.moe/g/[^"]+/thumbnails)"',
    re.I,
)
CSRF_RE = re.compile(r'<meta name="csrf-token" content="([^"]+)"', re.I)


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _parse_meta_sections(document: str) -> dict[str, tuple[str, ...]]:
    sections: dict[str, list[str]] = {}
    for match in META_VALUE_RE.finditer(document):
        label = _clean_text(match.group(1)).casefold()
        values = [
            _clean_text(name)
            for name in META_TAG_LINK_RE.findall(match.group(2))
            if _clean_text(name)
        ]
        if values:
            sections[label] = values
    return {key: tuple(values) for key, values in sections.items()}


def gallery_path(gallery_id: str) -> str:
    slug = gallery_id.strip().strip("/")
    if slug.startswith("g/"):
        slug = slug.removeprefix("g/")
    return f"/g/{slug}"


def reader_path(gallery_id: str, page_number: int = 1) -> str:
    return f"{gallery_path(gallery_id)}/{page_number}"


def listing_path(
    page: int,
    *,
    query: str | None = None,
    cursor: str | None = None,
) -> str:
    params: list[str] = []
    if query:
        params.append(f"q={quote(query)}")
    if cursor:
        params.append(f"cursor={quote(cursor)}")
    if not params:
        return "/"
    return f"/?{'&'.join(params)}"


def make_page_id(gallery_id: str, page_number: int) -> str:
    return f"{gallery_id}:{page_number}"


def page_id_gallery_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    gallery_id, _, _page_number = page_id.rpartition(":")
    return gallery_id or None


def extract_next_cursor(document: str) -> str | None:
    match = NEXT_LINK_RE.search(document)
    if not match:
        return None
    parsed = urlparse(match.group(1))
    values = parse_qs(parsed.query).get("cursor")
    if not values:
        return None
    return values[0]


def parse_series_list(
    document: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    items: list[Series] = []
    seen: set[str] = set()
    for _element_id, gallery_id, title in LISTING_ITEM_RE.findall(document):
        if gallery_id in seen:
            continue
        seen.add(gallery_id)
        clean_title = _clean_text(title)
        items.append(
            Series(
                id=gallery_id,
                title=clean_title or "Untitled",
                chapter_count=1,
            )
        )
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        api_has_more=bool(extract_next_cursor(document)),
    )


def parse_series_detail(document: str, *, gallery_id: str) -> Series | None:
    title_match = ENTRY_TITLE_RE.search(document) or TITLE_RE.search(document)
    if not title_match:
        return None
    title = _clean_text(title_match.group(1))
    sections = _parse_meta_sections(document)
    page_count_match = PAGE_COUNT_RE.search(document)
    page_count = int(page_count_match.group(1)) if page_count_match else 0
    cover_match = COVER_RE.search(document)
    cover_url = cover_match.group(1) if cover_match else None
    category = sections.get("category", ())
    languages = sections.get("language", ())
    return Series(
        id=gallery_id,
        title=title or "Untitled",
        chapter_count=1 if page_count > 0 else 0,
        cover_url=cover_url,
        status="completed",
        genres=category,
        latest_chapter=f"{page_count} pages" if page_count else None,
        description=languages[0] if languages else None,
    )


def parse_chapters(document: str, *, gallery_id: str) -> list[Chapter]:
    page_count_match = PAGE_COUNT_RE.search(document)
    if not page_count_match:
        return []
    page_count = int(page_count_match.group(1))
    if page_count <= 0:
        return []
    upload_match = UPLOADED_RE.search(document)
    release_date = upload_match.group(1)[:10] if upload_match else None
    return [
        Chapter(
            id=gallery_id,
            series_id=gallery_id,
            title="Gallery",
            number=1.0,
            page_count=page_count,
            release_date=release_date,
        )
    ]


def extract_media_base(document: str) -> str | None:
    cover_match = COVER_RE.search(document)
    if cover_match:
        media_match = MEDIA_BASE_RE.search(cover_match.group(1))
        if media_match:
            return media_match.group(1).rstrip("/")
    img_prt_match = IMG_PRT_RE.search(document)
    if img_prt_match:
        return img_prt_match.group(1).rstrip("/")
    media_match = MEDIA_BASE_RE.search(document)
    if media_match:
        return media_match.group(1).rstrip("/")
    return None


def extract_thumbnails_path(document: str, *, gallery_id: str) -> str:
    match = THUMBNAILS_ACT_RE.search(document)
    if match:
        parsed = urlparse(match.group(1))
        return parsed.path or gallery_path(gallery_id) + "/thumbnails"
    return f"{gallery_path(gallery_id)}/thumbnails"


def extract_csrf_token(document: str) -> str | None:
    match = CSRF_RE.search(document)
    return match.group(1) if match else None


def parse_image_filenames(payload: str) -> list[str]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    filenames: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            filenames.append(item.strip())
    return filenames


def build_gallery_pages(
    *,
    gallery_id: str,
    media_base: str,
    filenames: list[str],
) -> list[Page]:
    pages: list[Page] = []
    for index, filename in enumerate(filenames, start=1):
        pages.append(
            Page(
                id=make_page_id(gallery_id, index),
                chapter_id=gallery_id,
                number=index,
                remote_url=f"{media_base.rstrip('/')}/{filename.lstrip('/')}",
            )
        )
    return pages
