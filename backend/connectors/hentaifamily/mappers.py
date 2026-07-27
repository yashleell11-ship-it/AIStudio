"""Map HentaiFox-family gallery HTML to normalized connector models."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import quote

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

HOME_PAGE_SIZE = 32
SEARCH_PAGE_SIZE = 32

LISTING_CARD_RE = re.compile(
    r'href="(/gallery/(\d+)/)"[^>]*>.*?'
    r'data-src="([^"]+)".*?'
    r'class="(?:g_title|gallery_title)"><a[^>]*>([^<]+)</a>',
    re.S | re.I,
)
NEXT_PAGE_RE = re.compile(r"page-link['\"][^>]*>\s*Next", re.I)
TITLE_H1_RE = re.compile(r'<h1[^>]*>([^<]+)', re.I)
TITLE_TAG_RE = re.compile(r"<title>([^<]+?)\s*-\s*", re.I)
PAGE_COUNT_RE = re.compile(r'id="load_pages"[^>]+value="(\d+)"', re.I)
THUMB_PAGE_RE = re.compile(r'data-src="(https://[^"]+/(\d+)t\.jpg)"', re.I)
READER_IMAGE_RE = re.compile(r'data-src="(https://[^"]+\.(?:webp|png|jpg|jpeg))"', re.I)
TAG_LINK_RE = re.compile(
    r'<a[^>]+class="tag[^"]*"[^>]*>([^<]+)</a>',
    re.I,
)


@dataclass(frozen=True, slots=True)
class HentaiFamilySite:
    source_id: str
    display_name: str
    site_base: str
    reader_segment: str  # ``g`` (hentaifox) or ``view`` (hentaiera)
    image_host_suffix: str  # e.g. hentaifox.com


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def home_listing_path(page: int, *, sort: str | None = None) -> str:
    params: list[str] = []
    if sort == "popular":
        params.append("sort=popular")
    elif sort == "new":
        params.append("sort=new")
    elif sort in {"rating", "top_rated"}:
        params.append("sort=rating")
    if page > 1:
        params.append(f"page={page}")
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
    return f"/gallery/{gallery_id.strip().strip('/')}/"


def reader_path(site: HentaiFamilySite, gallery_id: str, page_number: int) -> str:
    return f"/{site.reader_segment}/{gallery_id.strip().strip('/')}/{page_number}/"


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
    for _href, gallery_id, thumb_url, title in LISTING_CARD_RE.findall(document):
        if gallery_id in seen:
            continue
        seen.add(gallery_id)
        clean_title = _clean_text(title)
        items.append(
            Series(
                id=gallery_id,
                title=clean_title or "Untitled",
                chapter_count=1,
                cover_url=thumb_url.replace("/thumb.jpg", "/cover.jpg"),
            )
        )
    has_next = bool(NEXT_PAGE_RE.search(document))
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        api_has_more=has_next or len(items) >= page_size,
    )


def _page_count(document: str) -> int:
    match = PAGE_COUNT_RE.search(document)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    thumbs = THUMB_PAGE_RE.findall(document)
    return max((int(number) for _url, number in thumbs), default=0)


def _media_base(document: str) -> str | None:
    match = THUMB_PAGE_RE.search(document)
    if match is None:
        return None
    thumb_url = match.group(1)
    return thumb_url.rsplit("/", 1)[0] + "/"


def parse_series_detail(document: str, *, gallery_id: str) -> Series | None:
    title_match = TITLE_H1_RE.search(document) or TITLE_TAG_RE.search(document)
    if title_match is None:
        return None
    title = _clean_text(title_match.group(1))
    page_count = _page_count(document)
    media_base = _media_base(document)
    cover_url = f"{media_base}cover.jpg" if media_base else None
    tags = tuple(_clean_text(name) for name in TAG_LINK_RE.findall(document))
    return Series(
        id=gallery_id,
        title=title or "Untitled",
        chapter_count=1 if page_count > 0 else 0,
        cover_url=cover_url,
        status="completed",
        genres=tags,
        latest_chapter=f"{page_count} pages" if page_count else None,
    )


def parse_chapters(document: str, *, gallery_id: str) -> list[Chapter]:
    page_count = _page_count(document)
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


def parse_gallery_pages_from_detail(document: str, *, gallery_id: str) -> list[Page]:
    """Build page URLs from gallery detail thumbs (webp by default)."""
    page_count = _page_count(document)
    media_base = _media_base(document)
    if page_count <= 0 or not media_base:
        return []
    pages: list[Page] = []
    for number in range(1, page_count + 1):
        pages.append(
            Page(
                id=make_page_id(gallery_id, number),
                chapter_id=gallery_id,
                number=number,
                remote_url=f"{media_base}{number}.webp",
            )
        )
    return pages


def parse_reader_image_url(document: str) -> str | None:
    match = READER_IMAGE_RE.search(document)
    return match.group(1) if match else None
