"""Map FreeAdultComix (WordPress + Justified Gallery) HTML to connector models."""

from __future__ import annotations

import html
import re
from urllib.parse import quote, urljoin

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://freeadultcomix.com"
PAGE_SIZE = 24

RESERVED_SLUGS = frozenset(
    {
        "page",
        "tag",
        "category",
        "author",
        "feed",
        "wp-json",
        "wp-admin",
        "wp-content",
        "wp-includes",
        "xmlrpc.php",
        "comments",
        "search",
        "cdn-cgi",
    }
)

CARD_RE = re.compile(
    r'<div class="video-conteudo">\s*'
    r'<div class="thumb-conteudo">\s*'
    r'<a href="(?P<href>https?://(?:www\.)?freeadultcomix\.com/(?P<slug>[^"/]+)/)"'
    r'[^>]*title="(?P<title>[^"]*)"[^>]*>'
    r"(?P<body>.*?)</a>",
    re.I | re.S,
)
CARD_IMG_RE = re.compile(
    r'<img[^>]+(?:src|data-src)="(?P<src>https?://[^"]+)"',
    re.I,
)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
OG_IMAGE_RE = re.compile(
    r'<meta\s+property="og:image"\s+content="([^"]+)"',
    re.I,
)
OG_DESC_RE = re.compile(
    r'<meta\s+property="og:description"\s+content="([^"]*)"',
    re.I,
)
TAG_LINK_RE = re.compile(
    r'href="https?://(?:www\.)?freeadultcomix\.com/tag/([^"/]+)/"[^>]*>([^<]+)</a>',
    re.I,
)
CATEGORY_LINK_RE = re.compile(
    r'href="https?://(?:www\.)?freeadultcomix\.com/category/([^"/]+)/"[^>]*>([^<]+)</a>',
    re.I,
)
GALLERY_HREF_RE = re.compile(
    r"<figure[^>]*class=['\"]dgwt-jg-item['\"][^>]*>\s*"
    r"<a\s+href=['\"](https?://[^'\"]+)['\"]",
    re.I,
)
PAGE_LINK_RE = re.compile(r"/page/(\d+)/?", re.I)
TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _clean_text(value: str) -> str:
    text = TAG_STRIP_RE.sub("", value)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def listing_path(page: int) -> str:
    if page <= 1:
        return "/"
    return f"/page/{page}/"


def search_listing_path(query: str, page: int) -> str:
    q = quote(query.strip())
    if page <= 1:
        return f"/?s={q}"
    return f"/page/{page}/?s={q}"


def tag_listing_path(tag: str, page: int) -> str:
    slug = tag.strip().strip("/").lower()
    if page <= 1:
        return f"/tag/{slug}/"
    return f"/tag/{slug}/page/{page}/"


def series_id_to_path(series_id: str) -> str:
    slug = series_id.strip().strip("/")
    return f"/{slug}/"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def _extract_total_pages(html_text: str) -> int:
    pages = [int(value) for value in PAGE_LINK_RE.findall(html_text)]
    if pages:
        return max(pages)
    return 1


def parse_series_list(html_text: str, *, page: int = 1) -> PaginatedSeriesList:
    items: list[Series] = []
    seen: set[str] = set()
    for match in CARD_RE.finditer(html_text):
        slug = match.group("slug").strip().lower()
        if slug in RESERVED_SLUGS or slug in seen:
            continue
        seen.add(slug)
        title = _clean_text(match.group("title") or "")
        if not title:
            continue
        img = CARD_IMG_RE.search(match.group("body"))
        cover = img.group("src") if img else None
        items.append(
            Series(
                id=slug,
                title=title,
                chapter_count=1,
                cover_url=cover,
                canonical_path=series_id_to_path(slug),
            )
        )
    total_pages = _extract_total_pages(html_text)
    has_more = page < total_pages if total_pages > 1 else len(items) >= PAGE_SIZE
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        api_has_more=has_more,
    )


def parse_series_detail(html_text: str, series_id: str) -> Series | None:
    slug = series_id.strip().strip("/")
    h1 = H1_RE.search(html_text)
    title = _clean_text(h1.group(1)) if h1 else slug.replace("-", " ").title()
    if not title:
        return None

    og_image = OG_IMAGE_RE.search(html_text)
    cover = og_image.group(1).strip() if og_image else None
    if cover and not cover.startswith("http"):
        cover = urljoin(SITE_BASE + "/", cover)

    og_desc = OG_DESC_RE.search(html_text)
    description = _clean_text(og_desc.group(1)) if og_desc else None

    genres: list[str] = []
    seen_genres: set[str] = set()
    for pattern in (TAG_LINK_RE, CATEGORY_LINK_RE):
        for _tag_slug, label in pattern.findall(html_text):
            name = _clean_text(label).lower()
            if not name or name in seen_genres:
                continue
            seen_genres.add(name)
            genres.append(name)

    page_urls = parse_gallery_image_urls(html_text)
    return Series(
        id=slug,
        title=title,
        chapter_count=1,
        cover_url=cover or (page_urls[0] if page_urls else None),
        description=description,
        genres=tuple(genres),
        canonical_path=series_id_to_path(slug),
        latest_chapter=f"{len(page_urls)} pages" if page_urls else None,
    )


def parse_gallery_image_urls(html_text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for href in GALLERY_HREF_RE.findall(html_text):
        url = href.strip()
        if not url.startswith("http"):
            url = urljoin(SITE_BASE + "/", url)
        if "/wp-content/uploads/" not in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def parse_chapters(html_text: str, series_id: str) -> list[Chapter]:
    slug = series_id.strip().strip("/")
    page_count = len(parse_gallery_image_urls(html_text))
    return [
        Chapter(
            id=slug,
            series_id=slug,
            title="Gallery",
            number=1.0,
            page_count=page_count,
        )
    ]


def parse_chapter_pages(html_text: str, chapter_id: str) -> list[Page]:
    slug = chapter_id.strip().strip("/")
    urls = parse_gallery_image_urls(html_text)
    return [
        Page(
            id=make_page_id(slug, number),
            chapter_id=slug,
            number=number,
            remote_url=url,
        )
        for number, url in enumerate(urls, start=1)
    ]


# Common tags surfaced on the home page for genre browse.
GENRE_CATALOG: tuple[tuple[str, str], ...] = (
    ("anal", "Anal"),
    ("big-ass", "Big Ass"),
    ("big-boobs", "Big Boobs"),
    ("blowjob", "Blowjob"),
    ("creampie", "Creampie"),
    ("group", "Group"),
    ("incest", "Incest"),
    ("milf", "MILF"),
    ("netorare", "Netorare"),
    ("rape", "Rape"),
    ("threesome", "Threesome"),
    ("yuri", "Yuri"),
)
