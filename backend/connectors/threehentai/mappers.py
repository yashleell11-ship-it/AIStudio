"""Map 3Hentai HTML to normalized connector models."""

from __future__ import annotations

import html
import re
from urllib.parse import quote

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://3hentai.net"
HOME_PAGE_SIZE = 30
SEARCH_PAGE_SIZE = 25
ENGLISH_LANGUAGE_QUERY = "language:english"

LISTING_ITEM_RE = re.compile(
    r'<a href="(?:https://3hentai\.net)?/d/(\d+)" class="cover"[^>]*>.*?'
    r'data-src="([^"]+)".*?'
    r'<div class="title[^"]*">([^<]+)</div>',
    re.S | re.I,
)
HAS_MORE_RE = re.compile(r'rel="next"', re.I)
TITLE_RE = re.compile(r"<title>([^<]+?)\s*-\s*3Hentai</title>", re.I)
TAG_SECTION_RE = re.compile(
    r'<div class="tag-container field-name">\s*([^:<]+):\s*(.*?)</div>',
    re.S | re.I,
)
TAG_LINK_RE = re.compile(r'<a class="name"[^>]*>([^<]+)</a>', re.I)
UPLOADED_RE = re.compile(
    r'Uploaded:\s*<time[^>]+datetime="([^"]+)"',
    re.I,
)
# The media CDN moved from ``s<N>.3hentai.net`` to ``s<N>.3hentai.xyz``.
# Every media pattern below matches either host: the gallery HTML is still
# served from 3hentai.net, so only the image URLs changed, and a site that
# renamed its CDN once may well rename it back or run both.
MEDIA_HOST_RE = r"s\d+\.3hentai\.(?:net|xyz)"
GALLERY_THUMB_RE = re.compile(
    r'href="(?:https://3hentai\.net)?/d/(\d+)/(\d+)"[^>]*>.*?'
    r'data-src="(https://' + MEDIA_HOST_RE + r'/d\d+/\d+t\.jpg)"',
    re.S | re.I,
)
MEDIA_PATH_RE = re.compile(r"(https://s(\d+)\.3hentai\.(?:net|xyz)/(d\d+)/)", re.I)
PAGE_IMAGE_RE = re.compile(
    r'https://' + MEDIA_HOST_RE + r'/d\d+/\d+\.jpg',
    re.I,
)


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _parse_tag_sections(document: str) -> dict[str, tuple[str, ...]]:
    sections: dict[str, list[str]] = {}
    for match in TAG_SECTION_RE.finditer(document):
        label = _clean_text(match.group(1)).casefold()
        names = [_clean_text(name) for name in TAG_LINK_RE.findall(match.group(2))]
        values = [name for name in names if name]
        if values:
            sections[label] = values
    return {key: tuple(values) for key, values in sections.items()}


def _page_count(document: str, *, gallery_id: str) -> int:
    sections = _parse_tag_sections(document)
    pages = sections.get("pages")
    if pages:
        try:
            return int(pages[0])
        except ValueError:
            pass
    numbers = [
        int(number)
        for gid, number, _thumb in GALLERY_THUMB_RE.findall(document)
        if gid == gallery_id
    ]
    return max(numbers) if numbers else 0


def _gallery_media_base(document: str, *, gallery_id: str) -> str | None:
    cover_match = re.search(
        rf'href="(?:https://3hentai\.net)?/d/{re.escape(gallery_id)}/1"[^>]*>.*?'
        rf'data-src="(https://s\d+\.3hentai\.(?:net|xyz)/d\d+/)1t\.jpg"',
        document,
        re.S | re.I,
    )
    if cover_match:
        return cover_match.group(1)

    for gid, _number, thumb_url in GALLERY_THUMB_RE.findall(document):
        if gid != gallery_id:
            continue
        media_match = MEDIA_PATH_RE.search(thumb_url)
        if media_match:
            return media_match.group(1)
    return None


def home_listing_path(page: int, *, sort: str | None = None) -> str:
    params: list[str] = []
    if page > 1:
        params.append(f"page={page}")
    if sort == "popular":
        params.append("sort=popular")
    elif sort == "popular-24h":
        params.append("sort=popular-24h")
    elif sort == "popular-7d":
        params.append("sort=popular-7d")
    if not params:
        return "/"
    return f"/?{'&'.join(params)}"


def search_listing_path(
    query: str,
    page: int,
    *,
    sort: str | None = None,
) -> str:
    params = [f"q={quote(query)}"]
    if page > 1:
        params.append(f"page={page}")
    if sort == "popular":
        params.append("sort=popular")
    elif sort == "popular-24h":
        params.append("sort=popular-24h")
    elif sort == "popular-7d":
        params.append("sort=popular-7d")
    return f"/search?{'&'.join(params)}"


def gallery_path(gallery_id: str) -> str:
    return f"/d/{gallery_id.strip()}"


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
    items: list[Series] = []
    for gallery_id, thumb_url, title in LISTING_ITEM_RE.findall(document):
        clean_title = _clean_text(title)
        items.append(
            Series(
                id=gallery_id,
                title=clean_title or "Untitled",
                chapter_count=1,
                cover_url=thumb_url,
            )
        )
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        api_has_more=bool(HAS_MORE_RE.search(document)),
    )


def parse_series_detail(document: str, *, gallery_id: str) -> Series | None:
    title_match = TITLE_RE.search(document)
    if not title_match:
        return None
    title = _clean_text(title_match.group(1))
    sections = _parse_tag_sections(document)
    page_count = _page_count(document, gallery_id=gallery_id)
    media_base = _gallery_media_base(document, gallery_id=gallery_id)
    cover_url = f"{media_base}cover.jpg" if media_base else None
    artists = sections.get("artists", ())
    groups = sections.get("groups", ())
    categories = sections.get("categories", ())
    series_tags = sections.get("series", ())
    upload_match = UPLOADED_RE.search(document)
    return Series(
        id=gallery_id,
        title=title or "Untitled",
        chapter_count=1 if page_count > 0 else 0,
        cover_url=cover_url,
        author=artists[0] if artists else (groups[0] if groups else None),
        artist=artists[0] if artists else None,
        status="completed",
        genres=categories + series_tags,
        latest_chapter=f"{page_count} pages" if page_count else None,
        description=upload_match.group(1) if upload_match else None,
    )


def parse_chapters(document: str, *, gallery_id: str) -> list[Chapter]:
    page_count = _page_count(document, gallery_id=gallery_id)
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


def parse_reader_page(document: str, *, gallery_id: str, page_number: int) -> Page | None:
    match = PAGE_IMAGE_RE.search(document)
    if not match:
        return None
    return Page(
        id=make_page_id(gallery_id, page_number),
        chapter_id=gallery_id,
        number=page_number,
        remote_url=match.group(0),
    )
