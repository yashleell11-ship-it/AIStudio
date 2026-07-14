"""Map CManhua HTML / search JSON to normalized connector models."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin

from connectors.models import Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://cmanhua.com"
PAGE_SIZE = 24
SEARCH_PATH = "/Modules/Search/SearchHandler.ashx"
ALL_COMICS_PATH = "/AllComics"
MANGA_UPDATE_PATH = "/MangaUpdate"

LISTING_ITEM_RE = re.compile(
    r"href=['\"]/comic/([a-z0-9-]+)['\"][^>]*>.*?<img\b([^>]+)>",
    re.S | re.I,
)
ATTR_SRC_RE = re.compile(r"src=['\"]([^'\"]+)['\"]", re.I)
ATTR_ALT_RE = re.compile(r"alt=['\"]([^'\"]*)['\"]", re.I)
PAGER_PAGE_RE = re.compile(r"rptPager_lnkPage_\d+[^>]*>\s*(\d+)\s*<", re.I)
TITLE_SUFFIX_RE = re.compile(r"\s*漫画\s*在线阅读\s*$")
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
LABEL_RE = re.compile(
    r'id="MainContent_lbl(Title|Description|Author|Status|ChaptersCount)"[^>]*>(.*?)</',
    re.S | re.I,
)
COVER_RE = re.compile(r"/pictures/([a-z0-9-]+)/cover\.(?:webp|jpg|jpeg|png)", re.I)
CHAPTER_LINK_RE = re.compile(
    r"<a\s+class=['\"]cd-chapter-link['\"]\s*href=['\"]/ReadComic\?id=([a-f0-9]+)['\"]>\s*(.*?)\s*</a>",
    re.S | re.I,
)
CHAPTER_NUM_RE = re.compile(r"章节\s*(\d+)\s*:", re.I)
PAGE_IMG_RE = re.compile(r"data-src=['\"](https?://[^'\"]+)['\"]", re.I)
VIEWSTATE_RE = re.compile(
    r'name="(__VIEWSTATE|__VIEWSTATEGENERATOR|__EVENTVALIDATION)"[^>]*value="([^"]*)"',
    re.I,
)

STATUS_MAP = {
    "ongoing": "Ongoing",
    "completed": "Completed",
    "hiatus": "Hiatus",
}


def _clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _absolute_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(f"{SITE_BASE}/", url.lstrip("/"))


def _clean_title(value: str) -> str:
    title = _clean_text(value)
    title = TITLE_SUFFIX_RE.sub("", title).strip()
    title = re.sub(r"\s*漫画\s*-\s*免费在线阅读\s*$", "", title).strip()
    title = re.sub(r"\s*第\d+话\s*-\s*在线阅读\s*$", "", title).strip()
    return title


def series_path(series_id: str) -> str:
    return f"/comic/{series_id.strip().strip('/')}"


def chapter_path(chapter_id: str) -> str:
    return f"/ReadComic?id={chapter_id.strip()}"


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def extract_aspnet_fields(document: str) -> dict[str, str]:
    """Pull ASP.NET WebForms hidden fields needed for AllComics jump POST."""
    fields: dict[str, str] = {}
    for name, value in VIEWSTATE_RE.findall(document):
        fields[name] = html.unescape(value)
    return fields


def jump_page_form(document: str, page: int) -> dict[str, str]:
    fields = extract_aspnet_fields(document)
    return {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": fields.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": fields.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": fields.get("__EVENTVALIDATION", ""),
        "ctl00$MainContent$txtJumpPage": str(page),
        "ctl00$MainContent$btnJumpPage": "跳转",
    }


def _parse_total_pages(document: str) -> int:
    pages = [int(value) for value in PAGER_PAGE_RE.findall(document)]
    return max(pages) if pages else 1


def _series_from_listing(slug: str, cover: str, title: str) -> Series:
    return Series(
        id=slug,
        title=_clean_title(title) or slug,
        cover_url=_absolute_url(cover) if cover else None,
        canonical_path=series_path(slug),
    )


def parse_series_list(document: str, *, page: int, page_size: int = PAGE_SIZE) -> PaginatedSeriesList:
    items: list[Series] = []
    seen: set[str] = set()
    for slug, attrs in LISTING_ITEM_RE.findall(document):
        if slug in seen:
            continue
        seen.add(slug)
        src_match = ATTR_SRC_RE.search(attrs)
        alt_match = ATTR_ALT_RE.search(attrs)
        cover = src_match.group(1) if src_match else ""
        title = alt_match.group(1) if alt_match else slug
        items.append(_series_from_listing(slug, cover, title))

    total_pages = _parse_total_pages(document)
    total = total_pages * page_size if total_pages > 1 else len(items)
    has_more = page < total_pages if total_pages > 1 else False
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        api_has_more=has_more,
    )


def parse_search_results(payload: Any, *, page: int) -> PaginatedSeriesList:
    if not isinstance(payload, list):
        payload = []
    items: list[Series] = []
    seen: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        slug = str(entry.get("slug") or "").strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        title = str(entry.get("title") or slug)
        cover = str(entry.get("cover") or "")
        items.append(_series_from_listing(slug, cover, title))

    if page > 1:
        return PaginatedSeriesList(
            items=[],
            page=page,
            page_size=max(len(items), 1),
            total=len(items),
            api_has_more=False,
        )
    return PaginatedSeriesList(
        items=items,
        page=1,
        page_size=max(len(items), 1),
        total=len(items),
        api_has_more=False,
    )


def parse_series_detail(document: str, *, series_id: str) -> Series | None:
    labels: dict[str, str] = {}
    for name, value in LABEL_RE.findall(document):
        labels[name.casefold()] = _clean_text(value)

    title = labels.get("title") or ""
    if not title:
        h1 = H1_RE.search(document)
        if h1:
            title = _clean_text(h1.group(1))
    if not title:
        title_tag = TITLE_TAG_RE.search(document)
        if title_tag:
            title = _clean_title(title_tag.group(1))
    if not title:
        return None

    cover_url = None
    cover_match = COVER_RE.search(document)
    if cover_match:
        cover_url = _absolute_url(cover_match.group(0))

    status_raw = labels.get("status", "").casefold()
    status = STATUS_MAP.get(status_raw, labels.get("status") or None)

    chapter_count = 0
    count_raw = labels.get("chapterscount", "")
    if count_raw.isdigit():
        chapter_count = int(count_raw)

    return Series(
        id=series_id,
        title=title,
        chapter_count=chapter_count,
        canonical_path=series_path(series_id),
        description=labels.get("description") or None,
        cover_url=cover_url,
        author=labels.get("author") or None,
        status=status,
    )


def parse_chapters(document: str, *, series_id: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    seen: set[str] = set()
    for chapter_id, raw_title in CHAPTER_LINK_RE.findall(document):
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        title = _clean_text(raw_title)
        number: float | None = None
        num_match = CHAPTER_NUM_RE.search(title)
        if num_match:
            try:
                number = float(num_match.group(1))
            except ValueError:
                number = None
        chapters.append(
            Chapter(
                id=chapter_id,
                series_id=series_id,
                title=title,
                number=number,
                page_count=0,
            )
        )
    return chapters


def parse_chapter_pages(document: str, *, chapter_id: str) -> list[Page]:
    pages: list[Page] = []
    for index, url in enumerate(PAGE_IMG_RE.findall(document), start=1):
        pages.append(
            Page(
                id=make_page_id(chapter_id, index),
                chapter_id=chapter_id,
                number=index,
                remote_url=url,
            )
        )
    return pages
