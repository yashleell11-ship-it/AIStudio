"""Map DemonicScans HTML pages to normalized connector models."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin
from urllib.parse import urlparse

from connectors.ids import fully_unquote
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.titles import normalize_chapter_title

SITE_BASE = "https://demonicscans.org"
PAGE_SIZE = 20
READER_IMAGE_HOST_SUFFIXES = ("demoniclibs.com",)
READER_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
READER_IMAGE_BLOCKLIST_SUBSTRINGS = (
    "/img/free_ads",
    "paypal.svg",
    "flaticon.com/",
    "upload.wikimedia.org/",
)


def _clean_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def _series_id_from_href(href: str) -> str:
    raw = _clean_text(href).removeprefix("/manga/").strip().strip("/")
    return fully_unquote(raw)


# Thumb cards on latest/popular: cover lives inside ``div.thumb > a > img``.
# Matching any manga ``<a>`` then the next ``<img>`` incorrectly pairs the
# title link from one card with the next card's cover.
THUMB_CARD_RE = re.compile(
    r'<div class="thumb">\s*'
    r'<a href="(?P<href>/manga/[^"]+)"[^>]*?\btitle="(?P<title>[^"]*)"[^>]*>\s*'
    r'<img[^>]+src="(?P<cover>[^"]+)"',
    re.I | re.S,
)

SERIES_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>/manga/[^"]+)"[^>]*(?:\btitle="(?P<title_attr>[^"]*)")?[^>]*>'
    r'(?P<title>[^<]+)</a>',
    re.I,
)


def parse_series_cards(html_text: str) -> list[Series]:
    items: list[Series] = []
    seen: set[str] = set()

    for match in THUMB_CARD_RE.finditer(html_text):
        series_id = _series_id_from_href(match.group("href"))
        if not series_id or series_id in seen:
            continue
        seen.add(series_id)
        title = _clean_text(match.group("title")) or series_id.replace("-", " ")
        items.append(
            Series(
                id=series_id,
                title=title,
                cover_url=urljoin(SITE_BASE, _clean_text(match.group("cover"))),
                canonical_path=f"/manga/{series_id}",
            )
        )

    # Fallback: links without images
    for match in SERIES_LINK_RE.finditer(html_text):
        series_id = _series_id_from_href(match.group("href"))
        if not series_id or series_id in seen:
            continue
        seen.add(series_id)
        title = _clean_text(match.group("title_attr") or "") or _clean_text(
            match.group("title")
        )
        items.append(
            Series(
                id=series_id,
                title=title or series_id.replace("-", " "),
                canonical_path=f"/manga/{series_id}",
            )
        )
    return items


def _extract_total_pages(html_text: str) -> int:
    pages = [int(value) for value in re.findall(r"[?&]page=(\d+)", html_text)]
    return max(pages) if pages else 1


def parse_series_list(html_text: str, *, page: int, page_size: int = PAGE_SIZE) -> PaginatedSeriesList:
    items = parse_series_cards(html_text)
    total_pages = _extract_total_pages(html_text)
    total = total_pages * page_size
    if page == total_pages:
        total = (total_pages - 1) * page_size + len(items)
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=page < total_pages,
    )


def _detail_cover_url(html_text: str) -> str | None:
    """Resolve cover art from current DemonicScans detail markup.

    The site dropped ``#manga-cover``; covers now live on ``readermc.org`` via
    ``og:image`` / the primary series thumbnail ``<img>``.
    """
    for pattern in (
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        r'<img[^>]+id="manga-cover"[^>]+src="([^"]+)"',
        r'<img[^>]+class="[^"]*border-box[^"]*"[^>]+src="(https?://[^"]+thumbnails[^"]+)"',
        r'src="(https?://(?:www\.)?readermc\.org/images/thumbnails/[^"]+)"',
    ):
        match = re.search(pattern, html_text, re.I)
        if match:
            return urljoin(SITE_BASE, _clean_text(match.group(1)))
    return None


def parse_series_detail(html_text: str, series_id: str) -> Series | None:
    title_match = re.search(r"<h1[^>]*big-fat-titles[^>]*>([^<]+)</h1>", html_text, re.I)
    if not title_match:
        title_match = re.search(r"<title>\s*([^<]+?)\s*</title>", html_text, re.I)
    if not title_match:
        return None
    title = _clean_text(title_match.group(1))

    cover_url = _detail_cover_url(html_text)

    def _stat(label: str) -> str | None:
        m = re.search(
            rf"<li[^>]*>\s*{re.escape(label)}\s*</li>\s*<li[^>]*>\s*([^<]+)\s*</li>",
            html_text,
            re.I,
        )
        return _clean_text(m.group(1)) if m else None

    author = _stat("Author")
    artist = _stat("Artist")
    status = _stat("Status")

    genres = tuple(
        _clean_text(item)
        for item in re.findall(r'<div class="genres-list">.*?<li>\s*([^<]+)\s*</li>', html_text, re.I | re.S)
    )

    desc_match = re.search(
        r'<div[^>]+class="manga-desc"[^>]*>\s*(.*?)\s*</div>',
        html_text,
        re.I | re.S,
    )
    description = _clean_text(re.sub(r"<[^>]+>", " ", desc_match.group(1))) if desc_match else None

    return Series(
        id=series_id,
        title=title,
        canonical_path=f"/manga/{series_id}",
        cover_url=cover_url,
        author=author,
        artist=artist,
        status=status,
        genres=genres,
        description=description,
    )


CHAPTER_LINK_RE = re.compile(
    r'href="(?:https?://[^"/]+)?/?chaptered\.php\?manga=(?P<manga>\d+)&chapter=(?P<num>[0-9.]+)"'
    r'[^>]*(?:title="(?P<title_attr>[^"]*)")?',
    re.I,
)


def parse_chapters(html_text: str, series_id: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for match in CHAPTER_LINK_RE.finditer(html_text):
        chapter_num = _clean_text(match.group("num"))
        try:
            number = float(chapter_num)
        except ValueError:
            continue
        chapter_id = f"{series_id}:{chapter_num}"
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        raw_title = (
            _clean_text(match.group("title_attr") or "")
            or f"Chapter {chapter_num}"
        )
        title = normalize_chapter_title(raw_title) or raw_title
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=title,
                number=number,
                page_count=0,
            )
        )
    chapters.sort(key=lambda ch: ch.number if ch.number is not None else float("inf"))
    return chapters


def chapter_id_to_reader_path(chapter_id: str) -> str:
    series_id, _, chapter_num = chapter_id.partition(":")
    return f"/title/{series_id}/chapter/{chapter_num}/1"


IMG_ATTR_RE = re.compile(
    r'(?:src|data-src|data-lazy-src)\s*=\s*"([^"]+)"',
    re.I,
)
IMG_TAG_RE = re.compile(r"<img[^>]+>", re.I)
SOURCE_TAG_RE = re.compile(r"<source[^>]+>", re.I)
SRCSET_RE = re.compile(r'srcset\s*=\s*"([^"]+)"', re.I)
NOSCRIPT_RE = re.compile(r"<noscript>(.*?)</noscript>", re.I | re.S)


def _urls_from_srcset(value: str) -> list[str]:
    urls: list[str] = []
    for part in value.split(","):
        token = part.strip().split(" ")[0].strip()
        if token:
            urls.append(token)
    return urls


def extract_image_urls(html_text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def _is_real_reader_image(full_url: str) -> bool:
        parsed = urlparse(full_url)
        if parsed.scheme != "https":
            return False
        if not parsed.netloc:
            return False
        host = parsed.netloc.lower()
        if not any(host == suffix or host.endswith(f".{suffix}") for suffix in READER_IMAGE_HOST_SUFFIXES):
            return False
        path = (parsed.path or "").lower()
        if not path.endswith(READER_IMAGE_EXTENSIONS):
            return False
        full_lower = full_url.lower()
        if any(token in full_lower for token in READER_IMAGE_BLOCKLIST_SUBSTRINGS):
            return False
        return True

    def _add(url: str) -> None:
        full = urljoin(SITE_BASE, url.strip())
        if not full or full in seen:
            return
        if not _is_real_reader_image(full):
            return
        seen.add(full)
        urls.append(full)

    # noscript blocks often contain real <img src=...>
    for block in NOSCRIPT_RE.findall(html_text):
        for tag in IMG_TAG_RE.findall(block):
            for url in IMG_ATTR_RE.findall(tag):
                _add(url)

    for tag in IMG_TAG_RE.findall(html_text):
        if "imgholder" not in tag.lower():
            continue
        for url in IMG_ATTR_RE.findall(tag):
            _add(url)

    for tag in SOURCE_TAG_RE.findall(html_text):
        m = SRCSET_RE.search(tag)
        if not m:
            continue
        for url in _urls_from_srcset(m.group(1)):
            _add(url)

    return urls


def parse_chapter_pages(html_text: str, chapter_id: str) -> list[Page]:
    image_urls = extract_image_urls(html_text)
    pages: list[Page] = []
    for index, remote_url in enumerate(image_urls, start=1):
        pages.append(
            Page(
                id=f"{chapter_id}:{index}",
                chapter_id=chapter_id,
                number=index,
                remote_url=remote_url,
            )
        )
    return pages


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def listing_path(page: int, *, kind: str) -> str:
    if kind == "latest":
        safe_page = max(page, 1)
        # DemonicScans uses `list` as the paging cursor for updates.
        # page 1 -> list=2, page 2 -> list=3, ...
        list_value = min(4, safe_page + 1)
        return f"/lastupdates.php?list={list_value}"
    if kind == "popular":
        return "/"
    if kind == "search":
        safe_page = max(page, 1)
        list_value = min(4, safe_page + 1)
        return f"/advanced.php?list={list_value}"
    return "/"


def listing_params(page: int) -> dict[str, Any]:
    # Site pages don't expose real pagination; we paginate by slicing.
    return {"page": page}

