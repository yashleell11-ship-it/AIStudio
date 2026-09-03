"""Map BaoZiMH API / HTML payloads to normalized connector models."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from connectors.models import BrowseMode, Chapter, Page, PaginatedSeriesList, Series

SITE_BASE = "https://www.baozimh.com"
COVER_BASE = "https://static-tw.baozimh.com/cover"
PAGE_SIZE = 36
LANGUAGE = "tw"

LIST_API_PATH = "/api/bzmhq/amp_comic_list"

CHAPTER_LINK_RE = re.compile(
    r'<a href="(/user/page_direct\?comic_id=[^"]+section_slot=(\d+)&amp;chapter_slot=(\d+))"'
    r'[^>]*class="[^"]*comics-chapters__item[^"]*"[^>]*>\s*<div[^>]*>\s*<span[^>]*>([^<]+)</span>',
    re.S,
)
TITLE_RE = re.compile(
    r'<h1[^>]*class="[^"]*comics-detail__title[^"]*"[^>]*>(.*?)</h1>',
    re.S,
)
AUTHOR_RE = re.compile(
    r'class="comics-detail__author"[^>]*>(.*?)</(?:div|h2)>',
    re.S,
)
DESC_RE = re.compile(
    r'class="[^"]*comics-detail__desc[^"]*"[^>]*>(.*?)</(?:p|div)>',
    re.S,
)
COVER_RE = re.compile(
    r'src="(https://static-(?:tw|cn)\.baozimh\.com/cover/[^"]+)"',
    re.I,
)
TAG_RE = re.compile(
    r'class="tag[^"]*"[^>]*>\s*([^<]+)',
    re.I,
)
SEARCH_CARD_RE = re.compile(
    r'class="comics-card[^"]*"[^>]*>\s*<a href="/comic/([^"]+)"[^>]*title="([^"]*)"[^>]*>'
    r'\s*<amp-img[^>]+src="([^"]+)"',
    re.S,
)
CHAPTER_IMG_RE = re.compile(
    r'<amp-img[^>]+id="chapter-img-[^"]+"[^>]+src="([^"]+)"',
    re.I,
)
CHAPTER_NUMBER_RE = re.compile(r"第\s*([\d.]+)\s*[話话章]")

_STATUS_ONGOING = ("連載", "连载", "serial", "ongoing")
_STATUS_COMPLETED = ("完結", "完结", "完結", "completed", "完")

# Classify `type=` filters exposed as genres in the browse UI.
GENRE_FILTERS: tuple[tuple[str, str], ...] = (
    ("lianai", "戀愛"),
    ("chunai", "純愛"),
    ("hougong", "後宮"),
    ("nanzhujue", "男主角"),
    ("danuzhu", "大女主"),
    ("xuanyi", "懸疑"),
    ("qihuan", "奇幻"),
    ("kehuan", "科幻"),
    ("xuanhuan", "玄幻"),
    ("wuxia", "武俠"),
    ("xianxia", "仙俠"),
    ("gaoxiao", "搞笑"),
    ("gedou", "格鬥"),
    ("dushi", "都市"),
    ("gufeng", "古風"),
    ("chuanyue", "穿越"),
    ("chongsheng", "重生"),
    ("hanman", "韓漫"),
    ("juqing", "劇情"),
    ("mouxian", "冒險"),
)


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _clean_url(value: str | None) -> str | None:
    if not value:
        return None
    return html.unescape(value).strip() or None


def cover_url_from_topic(topic_img: str | None) -> str | None:
    if not topic_img:
        return None
    name = topic_img.strip().lstrip("/")
    if name.startswith("http://") or name.startswith("https://"):
        return _clean_url(name)
    if name.startswith("cover/"):
        name = name.removeprefix("cover/")
    return f"{COVER_BASE}/{name}"


def make_chapter_id(comic_id: str, section_slot: int | str, chapter_slot: int | str) -> str:
    return f"{comic_id.strip()}/{int(section_slot)}_{int(chapter_slot)}"


def parse_chapter_id(chapter_id: str) -> tuple[str, int, int] | None:
    normalized = chapter_id.strip().strip("/")
    if "/" not in normalized:
        return None
    comic_id, _, slot_part = normalized.partition("/")
    if not comic_id or "_" not in slot_part:
        return None
    section_raw, _, chapter_raw = slot_part.partition("_")
    try:
        return comic_id, int(section_raw), int(chapter_raw)
    except ValueError:
        return None


def page_id_chapter_id(page_id: str) -> str | None:
    if ":" not in page_id:
        return None
    chapter_id, _, _page_number = page_id.rpartition(":")
    return chapter_id or None


def make_page_id(chapter_id: str, page_number: int) -> str:
    return f"{chapter_id}:{page_number}"


def chapter_page_path(comic_id: str, section_slot: int, chapter_slot: int) -> str:
    return (
        f"/user/page_direct?comic_id={comic_id}"
        f"&section_slot={section_slot}&chapter_slot={chapter_slot}"
    )


def listing_params(
    page: int,
    *,
    state: str = "all",
    type_filter: str = "all",
    region: str = "all",
) -> dict[str, Any]:
    return {
        "type": type_filter,
        "region": region,
        "state": state,
        "filter": "*",
        "page": page,
        "limit": PAGE_SIZE,
        "language": LANGUAGE,
    }


def resolve_list_state(sort: str | None) -> str:
    if not sort or sort in {"latest", "default", "all"}:
        return "all"
    if sort in {"serial", "ongoing"}:
        return "serial"
    if sort in {"completed", "pub", "finished"}:
        return "pub"
    return "all"


def genres_to_browse_modes() -> list[BrowseMode]:
    return [BrowseMode(id=genre_id, label=label) for genre_id, label in GENRE_FILTERS]


def series_item_to_series(item: dict[str, Any]) -> Series | None:
    comic_id = str(item.get("comic_id") or "").strip()
    if not comic_id:
        return None
    name = _clean_text(item.get("name") if isinstance(item.get("name"), str) else None) or comic_id
    author = _clean_text(item.get("author") if isinstance(item.get("author"), str) else None)
    genres: list[str] = []
    for entry in item.get("type_names") or []:
        cleaned = _clean_text(entry if isinstance(entry, str) else None)
        if cleaned:
            genres.append(cleaned)
    region_name = _clean_text(
        item.get("region_name") if isinstance(item.get("region_name"), str) else None
    )
    if region_name and region_name not in genres:
        genres.insert(0, region_name)
    topic = item.get("topic_img") if isinstance(item.get("topic_img"), str) else None
    return Series(
        id=comic_id,
        title=name,
        chapter_count=0,
        cover_url=cover_url_from_topic(topic),
        author=author,
        genres=tuple(genres),
    )


def series_list_to_paginated(payload: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    raw_items = payload.get("items") or []
    items: list[Series] = []
    for entry in raw_items:
        if isinstance(entry, dict):
            series = series_item_to_series(entry)
            if series is not None:
                items.append(series)
    has_more = bool(payload.get("next")) or len(items) >= PAGE_SIZE
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=0,
        api_has_more=has_more,
    )


def _status_from_tags(tags: list[str]) -> str | None:
    joined = " ".join(tags)
    if any(token in joined for token in _STATUS_COMPLETED):
        return "completed"
    if any(token in joined for token in _STATUS_ONGOING):
        return "ongoing"
    return None


def parse_series_detail(document: str, *, comic_id: str) -> Series | None:
    title_match = TITLE_RE.search(document)
    title = _clean_text(title_match.group(1) if title_match else None)
    if not title:
        page_title = re.search(r"<title>([^<]+)</title>", document, re.I)
        if page_title:
            raw = _clean_text(page_title.group(1)) or ""
            title = raw.split(" - ")[0].lstrip("🍜").strip() or None
    if not title:
        return None
    author_match = AUTHOR_RE.search(document)
    author = _clean_text(author_match.group(1) if author_match else None)
    desc_match = DESC_RE.search(document)
    description = _clean_text(desc_match.group(1) if desc_match else None)
    cover_match = COVER_RE.search(document)
    cover = _clean_url(cover_match.group(1) if cover_match else None)
    if cover is None:
        cover = cover_url_from_topic(f"{comic_id}.jpg")
    tags = [_clean_text(tag) for tag in TAG_RE.findall(document)]
    genres = tuple(tag for tag in tags if tag and tag not in {"連載中", "连载中", "已完結", "已完结"})
    chapters = parse_chapters(document, comic_id=comic_id)
    latest = chapters[0].title if chapters else None
    return Series(
        id=comic_id,
        title=title,
        chapter_count=len(chapters),
        description=description,
        author=author,
        status=_status_from_tags([tag for tag in tags if tag]),
        genres=genres,
        cover_url=cover,
        latest_chapter=latest,
    )


def _chapter_number(title: str, chapter_slot: int) -> float:
    match = CHAPTER_NUMBER_RE.search(title)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return float(chapter_slot)


def parse_chapters(document: str, *, comic_id: str) -> list[Chapter]:
    seen: set[tuple[int, int]] = set()
    chapters: list[Chapter] = []
    for _href, section_raw, chapter_raw, title_raw in CHAPTER_LINK_RE.findall(document):
        section_slot = int(section_raw)
        chapter_slot = int(chapter_raw)
        key = (section_slot, chapter_slot)
        if key in seen:
            continue
        seen.add(key)
        title = _clean_text(title_raw) or f"Chapter {chapter_slot}"
        chapters.append(
            Chapter(
                id=make_chapter_id(comic_id, section_slot, chapter_slot),
                series_id=comic_id,
                title=title,
                number=_chapter_number(title, chapter_slot),
                page_count=0,
            )
        )
    chapters.sort(
        key=lambda chapter: (
            parse_chapter_id(chapter.id) or (comic_id, 0, -1)
        )[2],
        reverse=True,
    )
    return chapters


def parse_search_listing(document: str) -> list[Series]:
    body = re.sub(r"<style[^>]*>.*?</style>", "", document, flags=re.S | re.I)
    seen: set[str] = set()
    items: list[Series] = []
    for comic_id, title_raw, cover_raw in SEARCH_CARD_RE.findall(body):
        comic_id = comic_id.strip()
        if not comic_id or comic_id in seen:
            continue
        seen.add(comic_id)
        title = _clean_text(title_raw) or comic_id
        items.append(
            Series(
                id=comic_id,
                title=title,
                cover_url=_clean_url(cover_raw),
            )
        )
    return items


#: The reader still emits ``s<N>.bzcdn.net`` page URLs, but that CDN refuses
#: TCP connections (``s1``/``s2`` both resolve to 206.168.190.107 and reject
#: :443; ``s3``/``s5``/apex no longer resolve at all). The operator's other
#: static host serves the identical paths, so page URLs are rehosted onto it.
#: Without this every chapter yields page URLs that cannot be fetched.
DEAD_IMAGE_HOST_RE = re.compile(r"^https://s\d+\.bzcdn\.net/", re.I)
LIVE_IMAGE_HOST = "https://static-tw.baozimh.com/"


def rehost_page_image(url: str) -> str:
    """Point a page image at the static host that is actually reachable."""
    return DEAD_IMAGE_HOST_RE.sub(LIVE_IMAGE_HOST, url)


def parse_chapter_pages(document: str, *, chapter_id: str) -> list[Page]:
    seen: set[str] = set()
    pages: list[Page] = []
    for raw_url in CHAPTER_IMG_RE.findall(document):
        url = _clean_url(raw_url)
        if url:
            url = rehost_page_image(url)
        if not url or url in seen:
            continue
        seen.add(url)
        page_number = len(pages) + 1
        pages.append(
            Page(
                id=make_page_id(chapter_id, page_number),
                chapter_id=chapter_id,
                number=page_number,
                remote_url=url,
            )
        )
    return pages


def comic_id_from_path(series_id: str) -> str:
    value = series_id.strip().strip("/")
    if value.startswith("comic/"):
        value = value.removeprefix("comic/")
    if "/" in value:
        value = value.split("/", 1)[0]
    # Allow pasted page_direct URLs.
    if "comic_id=" in value:
        parsed = urlparse(value if "://" in value else f"https://x/?{value}")
        query = parse_qs(parsed.query)
        comic = query.get("comic_id", [None])[0]
        if comic:
            return unquote(comic)
    return value
