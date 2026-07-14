"""Map Doujins.com HTML/JSON to normalized connector models."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import unquote

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://doujins.com"
IMAGE_HOST = "static.doujins.com"
HOME_PAGE_SIZE = 24
TOP_PAGE_SIZE = 24
MAX_DAY_LOOKBACK = 60

GALLERY_LINK_RE = re.compile(
    r'href="(/[^"]+-(\d+))"',
    re.I,
)
THUMBNAIL_CARD_RE = re.compile(
    r'<div class="thumbnail-doujin">\s*'
    r'(?:.*?)'
    r'<a href="(/[^"]+-(\d+))"[^>]*>\s*'
    r'<img[^>]+src="([^"]+)"[^>]*>\s*'
    r'<div class="title">\s*<div class="text">(.*?)</div>',
    re.S | re.I,
)
TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.I)
CANONICAL_RE = re.compile(
    r'rel="canonical"\s+href="https?://doujins\.com(/[^"]+)"',
    re.I,
)
FOLDER_TITLE_BLOCK_RE = re.compile(
    r'<div class="folder-title">(.*?)</div>',
    re.S | re.I,
)
FOLDER_TITLE_LINK_RE = re.compile(r"<a[^>]*>([^<]+)</a>", re.I)
ARTIST_RE = re.compile(
    r'<div class="gallery-artist">\s*Artist:\s*<a[^>]*>([^<]+)</a>',
    re.S | re.I,
)
TAG_LINK_RE = re.compile(
    r'href="/searches\?tag_id=\d+"[^>]*>\s*([^<]+?)\s*<',
    re.I,
)
IMAGE_COUNT_RE = re.compile(
    r"(\d+)\s+images?",
    re.I,
)
PAGE_IMG_RE = re.compile(
    r'<div data-hash="([^"]+)" class="swiper-slide">.*?'
    r'data-src="(https://static\.doujins\.com/[^"]+)"',
    re.S | re.I,
)
CSRF_RE = re.compile(
    r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
    re.I,
)

def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _absolute_url(url: str) -> str:
    value = html.unescape(url.strip())
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("/"):
        return f"{SITE_BASE}{value}"
    return value


def normalize_path(path: str) -> str:
    value = unquote(path.strip()).strip("/")
    if value.startswith("https://doujins.com/"):
        value = value.removeprefix("https://doujins.com/")
    if value.startswith("http://doujins.com/"):
        value = value.removeprefix("http://doujins.com/")
    # Drop tracking query fragments like ?x=13
    value = value.split("?", 1)[0].split("#", 1)[0]
    return value.strip("/")


def folder_id_from_path(path: str) -> str | None:
    normalized = normalize_path(path)
    match = re.search(r"-(\d+)$", normalized)
    return match.group(1) if match else None


def gallery_path(series_id: str) -> str:
    normalized = normalize_path(series_id)
    return f"/{normalized}"


def make_page_id(series_id: str, page_number: int) -> str:
    return f"{normalize_path(series_id)}:{page_number}"


def page_id_series_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    series_id, _, _number = page_id.rpartition(":")
    return series_id or None


def extract_csrf_token(document: str) -> str | None:
    match = CSRF_RE.search(document)
    return match.group(1) if match else None


def is_gallery_suggestion_link(link: str) -> bool:
    normalized = normalize_path(link)
    if not normalized or normalized.startswith("searches"):
        return False
    return bool(re.search(r"-\d+$", normalized)) and "/" in normalized


def series_from_folder_item(item: dict[str, Any]) -> Series | None:
    link = str(item.get("link") or "").strip()
    name = _clean_text(str(item.get("name") or ""))
    if not link or not name:
        return None
    path = normalize_path(link)
    if not path:
        return None
    thumbnail = item.get("thumbnail") or item.get("thumbnail2") or ""
    cover = _absolute_url(str(thumbnail).split()[0]) if thumbnail else None
    artist = _clean_text(str(item.get("artistList") or "")) or None
    series_name = _clean_text(str(item.get("series") or ""))
    tags = item.get("tags") or []
    genres: list[str] = []
    if series_name:
        genres.append(series_name)
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                label = _clean_text(str(tag.get("tag") or ""))
            else:
                label = _clean_text(str(tag))
            if label and label.casefold() not in {g.casefold() for g in genres}:
                genres.append(label)
    page_count = int(item.get("objects_count") or 0)
    return Series(
        id=path,
        title=name,
        chapter_count=1 if page_count > 0 else 0,
        canonical_path=gallery_path(path),
        cover_url=cover,
        author=artist,
        artist=artist,
        status="completed",
        genres=tuple(genres),
        latest_chapter=f"{page_count} pages" if page_count else None,
    )


def parse_folders_payload(payload: dict[str, Any]) -> list[Series]:
    items: list[Series] = []
    seen: set[str] = set()
    for raw in payload.get("folders") or []:
        if not isinstance(raw, dict):
            continue
        series = series_from_folder_item(raw)
        if series is None or series.id in seen:
            continue
        seen.add(series.id)
        items.append(series)
    return items


def parse_html_listing(document: str) -> list[Series]:
    items: list[Series] = []
    seen: set[str] = set()
    for path, _folder_id, thumb, title in THUMBNAIL_CARD_RE.findall(document):
        normalized = normalize_path(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(
            Series(
                id=normalized,
                title=_clean_text(title) or "Untitled",
                chapter_count=1,
                canonical_path=gallery_path(normalized),
                cover_url=_absolute_url(thumb),
                status="completed",
            )
        )
    if items:
        return items
    # Fallback: bare gallery links near static thumbnails
    for path, _folder_id in GALLERY_LINK_RE.findall(document):
        normalized = normalize_path(path)
        if not normalized or normalized in seen or "/" not in normalized:
            continue
        if normalized.startswith(("artists/", "series/", "tags/", "searches")):
            continue
        seen.add(normalized)
        items.append(
            Series(
                id=normalized,
                title=normalized.rsplit("/", 1)[-1],
                chapter_count=1,
                canonical_path=gallery_path(normalized),
                status="completed",
            )
        )
    return items


def paginate_series(
    items: list[Series],
    *,
    page: int,
    page_size: int,
) -> PaginatedSeriesList:
    if page < 1:
        page = 1
    start = (page - 1) * page_size
    chunk = items[start : start + page_size]
    return PaginatedSeriesList(
        items=chunk,
        page=page,
        page_size=page_size,
        total=len(items),
        api_has_more=start + page_size < len(items),
    )


def parse_searchbox_payload(payload: dict[str, Any]) -> list[Series]:
    suggestions = payload.get("suggestions") or []
    items: list[Series] = []
    seen: set[str] = set()
    for raw in suggestions:
        if not isinstance(raw, dict):
            continue
        link = str(raw.get("link") or "")
        if not is_gallery_suggestion_link(link):
            continue
        path = normalize_path(link)
        if not path or path in seen:
            continue
        seen.add(path)
        items.append(
            Series(
                id=path,
                title=_clean_text(str(raw.get("name") or path.rsplit("/", 1)[-1])),
                chapter_count=1,
                canonical_path=gallery_path(path),
                status="completed",
            )
        )
    return items


def parse_series_detail(document: str, *, series_id: str) -> Series | None:
    path = normalize_path(series_id)
    canonical = CANONICAL_RE.search(document)
    if canonical:
        path = normalize_path(canonical.group(1)) or path

    title_match = TITLE_RE.search(document)
    folder_block = FOLDER_TITLE_BLOCK_RE.search(document)
    title = ""
    if folder_block:
        links = FOLDER_TITLE_LINK_RE.findall(folder_block.group(1))
        if links:
            title = _clean_text(links[-1])
    if not title and title_match:
        title = _clean_text(title_match.group(1))
    if not title and not PAGE_IMG_RE.search(document):
        return None
    if not title:
        title = path.rsplit("/", 1)[-1]
    # Strip site suffix / "by artist" from <title>
    title = re.sub(r"\s+by\s+.+$", "", title, flags=re.I).strip()
    title = re.sub(r"\s*\|\s*Doujins\.com.*$", "", title, flags=re.I).strip()

    artist_match = ARTIST_RE.search(document)
    artist = _clean_text(artist_match.group(1)) if artist_match else None

    genres: list[str] = []
    for tag in TAG_LINK_RE.findall(document):
        label = _clean_text(tag)
        if label and label.casefold() not in {g.casefold() for g in genres}:
            genres.append(label)

    pages = parse_gallery_pages(document, series_id=path)
    cover_url = pages[0].remote_url if pages else None
    # Prefer f-/f2- cover from listing-style img if present near top
    cover_match = re.search(
        r'src="(https://static\.doujins\.com/f2?-[^"]+)"',
        document,
        re.I,
    )
    if cover_match:
        cover_url = _absolute_url(cover_match.group(1))

    page_count = len(pages)
    count_match = IMAGE_COUNT_RE.search(document)
    if count_match and page_count <= 0:
        try:
            page_count = int(count_match.group(1))
        except ValueError:
            page_count = 0

    return Series(
        id=path,
        title=title or "Untitled",
        chapter_count=1 if page_count > 0 else 0,
        canonical_path=gallery_path(path),
        cover_url=cover_url,
        author=artist,
        artist=artist,
        status="completed",
        genres=tuple(genres),
        latest_chapter=f"{page_count} pages" if page_count else None,
    )


def parse_chapters(document: str, *, series_id: str) -> list[Chapter]:
    path = normalize_path(series_id)
    pages = parse_gallery_pages(document, series_id=path)
    page_count = len(pages)
    if page_count <= 0:
        count_match = IMAGE_COUNT_RE.search(document)
        if count_match:
            try:
                page_count = int(count_match.group(1))
            except ValueError:
                page_count = 0
    if page_count <= 0:
        return []
    return [
        Chapter(
            id=path,
            series_id=path,
            title="Gallery",
            number=1.0,
            page_count=page_count,
        )
    ]


def parse_gallery_pages(document: str, *, series_id: str) -> list[Page]:
    path = normalize_path(series_id)
    pages: list[Page] = []
    seen_hashes: set[str] = set()
    for image_hash, raw_url in PAGE_IMG_RE.findall(document):
        if image_hash in seen_hashes:
            continue
        seen_hashes.add(image_hash)
        number = len(pages) + 1
        pages.append(
            Page(
                id=make_page_id(path, number),
                chapter_id=path,
                number=number,
                remote_url=_absolute_url(raw_url),
            )
        )
    return pages
