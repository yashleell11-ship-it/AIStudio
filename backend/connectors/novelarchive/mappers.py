"""Map novelarchive.cc's JSON API to normalized connector models.

Novel Archive (https://novelarchive.cc) is the flagship novel source (owner's
call, 2026-09-04): a ~61k-title archive of English webnovel/light-novel
translations behind a REAL JSON API — no HTML scraping. Probed and captured
from the VPS through production's exact egress/TLS the same day:

* Listing/search -> ``GET /api/novels?page=&per_page=&search=&sort=``
  -> ``{novels: [...], pagination: {has_next, ...}, filters: {...}}``.
  Verified sorts: ``popular``, ``recent``.
* Detail        -> ``GET /api/novels/{id}`` -> ``{novel: {..., chapter_names:
  [every chapter title, in order]}}`` — metadata AND the full chapter list
  in one request.
* Chapter       -> ``GET /api/novels/{id}/chapters/{n}`` (1-based) ->
  ``{chapter: {content, name, number}, navigation: {prev, next}, ...}``.
  ``content`` is plain text with blank-line paragraph breaks. Out-of-range
  -> 404 ``{"error": "Chapter does not exist"}``; malformed id -> 400.
* Covers        -> site-relative ``/api/novels/{id}/cover?...``.

Identity: ``series_key`` = the archive's novel id (an opaque hex string),
``chapter_key`` = the 1-based chapter ordinal as a string ("1", "2", ...) —
both verbatim from the API.

Data caveats handled here, not upstream: the archive ingested scraped
block-pages as "novels" (0 chapters, Indonesian titles like "Situs
Terlarang") — listing rows with no chapters are dropped; and although the
API is text-first, chapter content is still run through the shared sanitizer
stack (promo-line blacklist always; the full HTML extractor whenever markup
sneaks in) plus the English guard before anything is cached.
"""

from __future__ import annotations

import re
from typing import Any

from connectors.ids import fully_unquote
from connectors.models import Chapter, NovelChapterText, PaginatedSeriesList, Series
from connectors.novel_text import extract_paragraphs, is_promo_line

SITE_BASE = "https://novelarchive.cc"
PAGE_SIZE = 20

#: Browse views verified live from the VPS; ids are the API's sort values.
BROWSE_SORTS: dict[str, str] = {
    "": "popular",
    "default": "popular",
    "popular": "popular",
    "recent": "recent",
    "latest": "recent",
}

_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")


def normalize_series_key(value: str) -> str:
    return fully_unquote(value).strip().strip("/")


def normalize_chapter_key(value: str) -> str:
    return fully_unquote(value).strip().strip("/")


def sort_param(sort: str | None) -> str:
    return BROWSE_SORTS.get((sort or "").strip().lower(), "popular")


def _int(value: Any) -> int:
    """The API stringifies its numbers ("3173"); tolerate every shape."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _cover_url(row: dict[str, Any]) -> str | None:
    cover = row.get("cover_url") or row.get("image_url") or row.get("novel_image")
    if not cover:
        return None
    cover = str(cover)
    return cover if cover.startswith("http") else f"{SITE_BASE}{cover}"


def _genres(row: dict[str, Any]) -> tuple[str, ...]:
    raw = str(row.get("genres") or "")
    if not raw or raw.strip().lower() == "unknown":
        return ()
    return tuple(g.strip() for g in raw.split(",") if g.strip())


def _series_from_row(row: dict[str, Any]) -> Series | None:
    novel_id = str(row.get("id") or "").strip()
    title = str(row.get("title") or "").strip()
    if not novel_id or not title:
        return None
    author = str(row.get("author") or "").strip()
    status = str(row.get("release_status") or row.get("ongoing") or "").strip()
    return Series(
        id=novel_id,
        title=title,
        chapter_count=_int(row.get("total_chapters")),
        description=str(row.get("description") or "").strip() or None,
        cover_url=_cover_url(row),
        author=author if author and author.lower() != "unknown" else None,
        status=status.lower() or None,
        genres=_genres(row),
        latest_chapter=(
            str(row.get("latest_release")).strip()
            if row.get("latest_release")
            and str(row.get("latest_release")).strip().lower() != "unknown"
            else None
        ),
    )


def parse_listing(payload: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    """One listing/search page. Rows without chapters are DROPPED — the
    archive ingested scraped block-pages as zero-chapter "novels", and a
    reader can do nothing with them."""
    items: list[Series] = []
    for row in payload.get("novels") or []:
        if _int(row.get("total_chapters")) <= 0:
            continue
        series = _series_from_row(row)
        if series is not None:
            items.append(series)
    pagination = payload.get("pagination") or {}
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=_int(pagination.get("per_page")) or PAGE_SIZE,
        total=_int(pagination.get("total")),
        api_has_more=bool(pagination.get("has_next")),
    )


def parse_detail(
    payload: dict[str, Any], series_key: str
) -> tuple[Series | None, list[Chapter]]:
    """Series metadata + the full chapter list from one detail response."""
    row = payload.get("novel") or {}
    series = _series_from_row(row)
    if series is None:
        return None, []
    series_key = normalize_series_key(series_key)

    chapters: list[Chapter] = []
    for position, name in enumerate(row.get("chapter_names") or [], start=1):
        chapters.append(
            Chapter(
                id=str(position),
                series_id=series_key,
                title=str(name).strip() or f"Chapter {position}",
                number=float(position),
                page_count=0,
            )
        )
    if chapters:
        series = Series(
            id=series.id,
            title=series.title,
            chapter_count=len(chapters),
            description=series.description,
            cover_url=series.cover_url,
            author=series.author,
            status=series.status,
            genres=series.genres,
            latest_chapter=chapters[-1].title,
        )
    return series, chapters


def paragraphs_from_content(content: str) -> list[str]:
    """The API's chapter ``content`` -> sanitized plain-text paragraphs.

    Normally plain text with newline paragraph breaks — split, tidy, and run
    the promo-line blacklist. If markup ever appears (the archive scrapes
    upstream sites, so one bad ingest is enough), fall through to the full
    HTML sanitizer instead of serving tags to clients.
    """
    if _TAG_RE.search(content):
        return extract_paragraphs(content)
    paragraphs: list[str] = []
    for block in re.split(r"\n+", content):
        text = re.sub(r"\s+", " ", block).strip()
        if text and not is_promo_line(text):
            paragraphs.append(text)
    return paragraphs


def parse_chapter(payload: dict[str, Any]) -> NovelChapterText | None:
    chapter = payload.get("chapter") or {}
    content = str(chapter.get("content") or "")
    if not content.strip():
        return None
    paragraphs = paragraphs_from_content(content)
    if not paragraphs:
        return None
    number = chapter.get("number")
    return NovelChapterText(
        title=str(chapter.get("name") or "").strip(),
        paragraphs=tuple(paragraphs),
        chapter_number=float(number) if number is not None else None,
    )
