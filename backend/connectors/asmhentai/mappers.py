"""Map AsmHentai HTML to normalized connector models."""

from __future__ import annotations

import html
import re
from urllib.parse import quote

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://asmhentai.com"
IMAGE_HOST = "images.asmhentai.com"
HOME_PAGE_SIZE = 20
SEARCH_PAGE_SIZE = 20

LISTING_ITEM_RE = re.compile(
    r'<a href="(?:https://asmhentai\.com)?/g/(\d+)/"[^>]*>\s*'
    r'<img[^>]+data-src="([^"]+)"[^>]+alt="([^"]*)"',
    re.S | re.I,
)
TITLE_RE = re.compile(r"<title>([^<]+?)\s*-\s*AsmHentai</title>", re.I)
H1_RE = re.compile(r"<h1>([^<]+)</h1>", re.I)
TAG_SECTION_RE = re.compile(
    r'<div class="tags">\s*<h3>([^:]+):</h3>\s*<div class="tag_list">(.*?)</div>',
    re.S | re.I,
)
TAG_LINK_RE = re.compile(r'<span class="badge tag">([^<]+)', re.I)
PAGE_COUNT_RE = re.compile(r"<h3>\s*Pages:\s*(\d+)\s*</h3>", re.I)
GALLERY_THUMB_RE = re.compile(
    r'href="(?:https://asmhentai\.com)?/gallery/\d+/(\d+)/"[^>]*>.*?'
    r'data-src="(?:https:)?//images\.asmhentai\.com/\d+/\d+/(\d+)t\.jpg"',
    re.S | re.I,
)
MEDIA_BASE_RE = re.compile(
    r'(?:https:)?//images\.asmhentai\.com/(\d+)/(\d+)/',
    re.I,
)


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _absolute_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    return url


def _parse_tag_sections(document: str) -> dict[str, tuple[str, ...]]:
    sections: dict[str, list[str]] = {}
    for match in TAG_SECTION_RE.finditer(document):
        label = _clean_text(match.group(1)).casefold().rstrip(":")
        names = [_clean_text(name) for name in TAG_LINK_RE.findall(match.group(2))]
        values = [name for name in names if name]
        if values:
            sections[label] = values
    return {key: tuple(values) for key, values in sections.items()}


def _page_count(document: str, *, gallery_id: str) -> int:
    match = PAGE_COUNT_RE.search(document)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    numbers = [int(number) for number in GALLERY_THUMB_RE.findall(document)]
    return max(numbers) if numbers else 0


def _gallery_media_base(document: str, *, gallery_id: str) -> str | None:
    cover_match = re.search(
        rf'data-src="(?:https:)?//images\.asmhentai\.com/\d+/{re.escape(gallery_id)}/cover\.jpg"',
        document,
        re.I,
    )
    if cover_match:
        media_match = MEDIA_BASE_RE.search(cover_match.group(0))
        if media_match:
            shard, gid = media_match.groups()
            return f"https://{IMAGE_HOST}/{shard}/{gid}/"

    thumb_match = re.search(
        rf'data-src="(?:https:)?//images\.asmhentai\.com/\d+/{re.escape(gallery_id)}/\d+t\.jpg"',
        document,
        re.I,
    )
    if thumb_match:
        media_match = MEDIA_BASE_RE.search(thumb_match.group(0))
        if media_match:
            shard, gid = media_match.groups()
            return f"https://{IMAGE_HOST}/{shard}/{gid}/"
    return None


def home_listing_path(page: int, *, sort: str | None = None) -> str:
    params: list[str] = []
    if page > 1:
        params.append(f"page={page}")
    if sort == "popular":
        params.append("sort=popular")
    elif sort == "new":
        params.append("sort=new")
    elif sort in {"rating", "top_rated"}:
        params.append("sort=rating")
    if not params:
        return "/"
    return f"/?{'&'.join(params)}"


def search_listing_path(query: str, page: int, *, sort: str | None = None) -> str:
    params = [f"q={quote(query)}"]
    if page > 1:
        params.append(f"page={page}")
    if sort == "popular":
        params.append("sort=popular")
    elif sort == "new":
        params.append("sort=new")
    elif sort in {"rating", "top_rated"}:
        params.append("sort=rating")
    return f"/search/?{'&'.join(params)}"


def gallery_path(gallery_id: str) -> str:
    return f"/g/{gallery_id.strip().strip('/')}/"


def make_page_id(gallery_id: str, page_number: int) -> str:
    return f"{gallery_id}:{page_number}"


def page_id_gallery_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    gallery_id, _, _page_number = page_id.rpartition(":")
    return gallery_id or None


def parse_series_list(
    document: str,
    *,
    page: int,
    page_size: int,
) -> PaginatedSeriesList:
    seen: set[str] = set()
    items: list[Series] = []
    for gallery_id, thumb_url, title in LISTING_ITEM_RE.findall(document):
        if gallery_id in seen:
            continue
        seen.add(gallery_id)
        clean_title = _clean_text(title)
        items.append(
            Series(
                id=gallery_id,
                title=clean_title or "Untitled",
                chapter_count=1,
                cover_url=_absolute_url(thumb_url),
            )
        )
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        api_has_more=len(items) >= page_size,
    )


def parse_series_detail(document: str, *, gallery_id: str) -> Series | None:
    title_match = H1_RE.search(document) or TITLE_RE.search(document)
    if not title_match:
        return None
    title = _clean_text(title_match.group(1))
    sections = _parse_tag_sections(document)
    page_count = _page_count(document, gallery_id=gallery_id)
    media_base = _gallery_media_base(document, gallery_id=gallery_id)
    cover_url = f"{media_base}cover.jpg" if media_base else None
    parodies = sections.get("parodies", ())
    characters = sections.get("characters", ())
    categories = sections.get("category", ()) + sections.get("categories", ())
    tags = sections.get("tags", ())
    languages = sections.get("languages", ())
    artists = sections.get("artists", ())
    groups = sections.get("groups", ())
    return Series(
        id=gallery_id,
        title=title or "Untitled",
        chapter_count=1 if page_count > 0 else 0,
        cover_url=cover_url,
        author=artists[0] if artists else (groups[0] if groups else None),
        artist=artists[0] if artists else None,
        status="completed",
        genres=parodies + categories + tags + languages,
        latest_chapter=f"{page_count} pages" if page_count else None,
        description=", ".join(characters) if characters else None,
    )


def parse_chapters(document: str, *, gallery_id: str) -> list[Chapter]:
    page_count = _page_count(document, gallery_id=gallery_id)
    if page_count <= 0:
        return []
    return [
        Chapter(
            id=gallery_id,
            series_id=gallery_id,
            title="Gallery",
            number=1.0,
            page_count=page_count,
        )
    ]


def parse_gallery_pages(document: str, *, gallery_id: str) -> list[Page]:
    page_count = _page_count(document, gallery_id=gallery_id)
    media_base = _gallery_media_base(document, gallery_id=gallery_id)
    if page_count <= 0 or not media_base:
        return []
    pages: list[Page] = []
    for number in range(1, page_count + 1):
        pages.append(
            Page(
                id=make_page_id(gallery_id, number),
                chapter_id=gallery_id,
                number=number,
                remote_url=f"{media_base}{number}.jpg",
            )
        )
    return pages
