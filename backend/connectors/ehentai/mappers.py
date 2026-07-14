"""Map E-Hentai HTML to normalized connector models."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://e-hentai.org"
API_BASE = "https://api.e-hentai.org"
PAGE_SIZE = 25
GALLERY_THUMBS_PER_PAGE = 20
ENGLISH_LANGUAGE_QUERY = "language:english"

LISTING_ITEM_RE = re.compile(
    r'href="https://e-hentai\.org/g/(\d+)/([0-9a-f]+)/"[^>]*>\s*'
    r'<div class="glink">([^<]+)</div>',
    re.I,
)
LISTING_THUMB_RE = re.compile(
    r'id="it(\d+)"[^>]*>.*?<img[^>]+src="(https://[^"]+)"',
    re.S | re.I,
)
NEXT_LINK_RE = re.compile(
    r'id="unext"\s+href="([^"]+)"',
    re.I,
)
TITLE_RE = re.compile(r'id="gn">([^<]+)', re.I)
COVER_RE = re.compile(
    r'id="gd1">.*?url\((https://[^)]+)\)',
    re.S | re.I,
)
LENGTH_RE = re.compile(r"Length:</td><td[^>]*>(\d+)\s*pages", re.I)
POSTED_RE = re.compile(r"Posted:</td><td[^>]*>([^<]+)", re.I)
CATEGORY_RE = re.compile(
    r'id="gdc">.*?<div[^>]*>\s*([^<]+?)\s*<',
    re.S | re.I,
)
UPLOADER_RE = re.compile(
    r'id="gdn"><a[^>]+>([^<]+)</a>',
    re.I,
)
TAG_RE = re.compile(r'id="td_([^:]+):([^"]+)"', re.I)
PAGE_TOKEN_RE = re.compile(
    r'href="(?:https://e-hentai\.org)?/s/([0-9a-f]+)/(\d+)-(\d+)"',
    re.I,
)
READER_IMAGE_RE = re.compile(
    r'<img[^>]+id="img"[^>]+src="(https://[^"]+)"',
    re.I,
)
VIEWER_PATH_RE = re.compile(
    r"^/s/([0-9a-f]+)/(\d+)-(\d+)/?$",
    re.I,
)


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _tag_label(raw: str) -> str:
    return _clean_text(unquote(raw.replace("_", " ")))


def make_gallery_id(gid: str | int, token: str) -> str:
    return f"{gid}/{token}"


def parse_gallery_id(gallery_id: str) -> tuple[str, str] | None:
    value = gallery_id.strip().strip("/")
    if value.startswith("g/"):
        value = value.removeprefix("g/")
    if "/" not in value:
        return None
    gid, token = value.split("/", 1)
    token = token.strip("/")
    if not gid.isdigit() or not token:
        return None
    return gid, token


def make_page_id(gallery_id: str, page_number: int) -> str:
    return f"{gallery_id}:{page_number}"


def page_id_gallery_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    gallery_id, _, _page_number = page_id.rpartition(":")
    return gallery_id or None


def viewer_url(gid: str, imgkey: str, page_number: int) -> str:
    return f"{SITE_BASE}/s/{imgkey}/{gid}-{page_number}"


def is_viewer_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.hostname not in {"e-hentai.org", "www.e-hentai.org"}:
        return False
    return bool(VIEWER_PATH_RE.match(parsed.path or ""))


def listing_path(
    *,
    query: str | None = None,
    cursor: str | None = None,
    sort: str | None = None,
) -> str:
    if sort == "popular":
        return "/popular"

    params: list[str] = []
    if query:
        params.append(f"f_search={quote(query)}")
    if cursor:
        params.append(f"next={quote(str(cursor), safe='')}")
    if not params:
        return "/"
    return f"/?{'&'.join(params)}"


def gallery_path(gallery_id: str, *, thumb_page: int = 0) -> str:
    parsed = parse_gallery_id(gallery_id)
    if parsed is None:
        raise ValueError(f"Invalid E-Hentai gallery id: {gallery_id!r}")
    gid, token = parsed
    path = f"/g/{gid}/{token}/"
    if thumb_page > 0:
        return f"{path}?p={thumb_page}"
    return path


def extract_next_cursor(document: str) -> str | None:
    match = NEXT_LINK_RE.search(document)
    if not match:
        return None
    href = html.unescape(match.group(1))
    parsed = urlparse(href)
    values = parse_qs(parsed.query).get("next")
    if not values:
        return None
    return values[0]


def parse_series_list(
    document: str,
    *,
    page: int,
    page_size: int = PAGE_SIZE,
) -> PaginatedSeriesList:
    thumbs = {
        gid: thumb_url
        for gid, thumb_url in LISTING_THUMB_RE.findall(document)
    }
    items: list[Series] = []
    seen: set[str] = set()
    for gid, token, title in LISTING_ITEM_RE.findall(document):
        series_id = make_gallery_id(gid, token)
        if series_id in seen:
            continue
        seen.add(series_id)
        items.append(
            Series(
                id=series_id,
                title=_clean_text(title) or "Untitled",
                chapter_count=1,
                cover_url=thumbs.get(gid),
            )
        )
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        api_has_more=extract_next_cursor(document) is not None,
    )


def parse_series_detail(document: str, *, gallery_id: str) -> Series | None:
    title_match = TITLE_RE.search(document)
    if not title_match:
        return None
    title = _clean_text(title_match.group(1))
    length_match = LENGTH_RE.search(document)
    page_count = int(length_match.group(1)) if length_match else 0
    cover_match = COVER_RE.search(document)
    category_match = CATEGORY_RE.search(document)
    uploader_match = UPLOADER_RE.search(document)
    posted_match = POSTED_RE.search(document)

    genres: list[str] = []
    artists: list[str] = []
    for namespace, raw_name in TAG_RE.findall(document):
        label = _tag_label(raw_name)
        if not label:
            continue
        if namespace == "artist":
            artists.append(label)
        elif namespace in {"female", "male", "parody", "character", "group", "mixed", "other"}:
            genres.append(label)
    if category_match:
        category = _clean_text(category_match.group(1))
        if category:
            genres.insert(0, category)

    author = artists[0] if artists else (
        _clean_text(uploader_match.group(1)) if uploader_match else None
    )
    return Series(
        id=gallery_id,
        title=title or "Untitled",
        chapter_count=1 if page_count > 0 else 0,
        cover_url=cover_match.group(1) if cover_match else None,
        author=author,
        artist=artists[0] if artists else None,
        status="completed",
        genres=tuple(dict.fromkeys(genres)),
        latest_chapter=f"{page_count} pages" if page_count else None,
        description=_clean_text(posted_match.group(1)) if posted_match else None,
    )


def parse_page_count(document: str) -> int:
    match = LENGTH_RE.search(document)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def parse_chapters(document: str, *, gallery_id: str) -> list[Chapter]:
    page_count = parse_page_count(document)
    if page_count <= 0:
        return []
    posted_match = POSTED_RE.search(document)
    release_date = None
    if posted_match:
        release_date = _clean_text(posted_match.group(1))[:10] or None
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


def parse_page_tokens(document: str, *, gid: str) -> dict[int, str]:
    """Return ``{page_number: imgkey}`` from a gallery thumb page."""
    tokens: dict[int, str] = {}
    for imgkey, page_gid, page_number in PAGE_TOKEN_RE.findall(document):
        if page_gid != gid:
            continue
        try:
            number = int(page_number)
        except ValueError:
            continue
        tokens[number] = imgkey
    return tokens


def build_gallery_pages(
    *,
    gallery_id: str,
    gid: str,
    tokens: dict[int, str],
) -> list[Page]:
    pages: list[Page] = []
    for number in sorted(tokens):
        imgkey = tokens[number]
        pages.append(
            Page(
                id=make_page_id(gallery_id, number),
                chapter_id=gallery_id,
                number=number,
                remote_url=viewer_url(gid, imgkey, number),
            )
        )
    return pages


def parse_reader_image_url(document: str) -> str | None:
    match = READER_IMAGE_RE.search(document)
    return match.group(1) if match else None
