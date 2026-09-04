"""Map Wattpad's public JSON API to normalized connector models.

Wattpad (https://www.wattpad.com) is the largest serialized-fiction platform
on the web. Unlike the aggregator sources it has a real, unauthenticated JSON
API, so nothing here scrapes rendered HTML except the chapter body itself.
Probed FROM THE VPS on 2026-09-04 through production's exact egress and TLS
stack (the methodology in the novels spec §4): every endpoint below answers
200 with plain httpx, no Cloudflare and no token.

Endpoints used:

* Browse   -> ``GET /api/v3/stories?filter=hot|new|featured&limit=&offset=``
* Search   -> ``GET /api/v3/stories?query=&limit=&offset=``
  Both answer ``{total, nextUrl, stories: [...]}``. ``fields=`` prunes the
  response server-side, which matters: the unpruned payload is many times
  larger and carries data this connector has no use for.
* Detail   -> ``GET /api/v3/stories/<id>?fields=...,parts(...)`` — ONE
  request returns story metadata AND the complete part list, so
  ``get_series``/``get_chapters``/``chapter_text`` share a single fetch.
* Chapter  -> ``GET /apiv2/storytext?id=<partId>`` -> a bare HTML fragment of
  ``<p data-p-id="...">`` elements (no document wrapper).

TWO TRAPS, both confirmed by probing rather than assumed:

1. **Never send ``&page=`` to /apiv2/storytext.** Without it the endpoint
   returns the WHOLE part; with it the endpoint returns a ~4.5 KB slice.
   Measured on a 5,499-word part: no ``page`` -> 36,080 characters, whereas
   ``page=1`` -> 4,661. Adding the parameter "for pagination" would silently
   truncate every long chapter to its first few pages.
2. **A story the API labels English can still serve non-English parts.** A
   story pulled straight from ``filter=hot`` had an entirely Burmese chapter
   body. ``language`` describes the story record, not the text, which is why
   the connector runs ``looks_english()`` over the parsed paragraphs.

Identity (house law: opaque, stored raw, never parsed):

* ``series_key``  = the numeric story id  (e.g. ``26327373``)
* ``chapter_key`` = the numeric part id   (e.g. ``80847228``)

Neither contains a slash — unlike the other novel sources — so nothing may
assume novel keys are path-shaped.
"""

from __future__ import annotations

import re
from typing import Any

from connectors.ids import fully_unquote
from connectors.models import Chapter, NovelChapterText, PaginatedSeriesList, Series
from connectors.novel_text import extract_paragraphs, is_promo_line

SITE_BASE = "https://www.wattpad.com"

#: Stories per listing request. Wattpad accepts larger, but 20 keeps a browse
#: page responsive and matches what the site's own grid requests.
PAGE_SIZE = 20

#: Browse views exposed as sort modes; ``default`` maps to Hot.
BROWSE_FILTERS: dict[str, str] = {
    "": "hot",
    "default": "hot",
    "hot": "hot",
    "popular": "hot",
    "new": "new",
    "latest": "new",
    "featured": "featured",
}

#: Server-side field pruning for listing and detail requests.
STORY_FIELDS = (
    "id,title,description,cover,completed,mature,numParts,tags,"
    "language(name),user(name,fullname),readCount,voteCount,"
    "createDate,modifyDate"
)
LIST_FIELDS = f"total,nextUrl,stories({STORY_FIELDS})"
DETAIL_FIELDS = f"{STORY_FIELDS},parts(id,title,wordCount,length,createDate,modifyDate)"

#: Only English stories are served — the connector declares LANGUAGE = "en".
#: Matched case-insensitively against ``language.name``; a story with NO
#: language field is kept (absent data is not evidence of a foreign language).
ENGLISH_LANGUAGE_NAMES = frozenset({"english"})

#: Tags are free-text and stories carry dozens; keep the listing readable.
MAX_TAGS = 12

_STORY_ID_RE = re.compile(r"(\d+)")


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def normalize_series_key(value: str) -> str:
    """``26327373``, ``/story/26327373-the-dragon``, or a full URL -> the id.

    Wattpad's own URLs append a slug to the id; the id is the only stable
    part, so a pasted URL reduces to it.
    """
    cleaned = fully_unquote(value).strip().strip("/")
    # Matched WITHOUT a leading slash: the strip above has already removed it
    # from "/story/26327373-the-dragon", so a "/story/" test would miss.
    if "story/" in cleaned:
        cleaned = cleaned.split("story/", 1)[1]
    match = _STORY_ID_RE.match(cleaned)
    return match.group(1) if match else cleaned


def normalize_chapter_key(value: str) -> str:
    """``80847228`` or ``/80847228-chapter-1`` -> the part id."""
    cleaned = fully_unquote(value).strip().strip("/")
    if cleaned.startswith("http"):
        cleaned = cleaned.split("wattpad.com/", 1)[-1].strip("/")
    match = _STORY_ID_RE.match(cleaned)
    return match.group(1) if match else cleaned


def story_path(series_key: str) -> str:
    return f"/api/v3/stories/{normalize_series_key(series_key)}"


def list_params(
    page: int, *, sort: str | None = None, query: str | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": PAGE_SIZE,
        "offset": max(page - 1, 0) * PAGE_SIZE,
        "fields": LIST_FIELDS,
    }
    if query:
        params["query"] = query
    else:
        params["filter"] = BROWSE_FILTERS.get((sort or "").strip().lower(), "hot")
    return params


def is_english(story: dict[str, Any]) -> bool:
    language = story.get("language")
    name = _text((language or {}).get("name")) if isinstance(language, dict) else ""
    return not name or name.casefold() in ENGLISH_LANGUAGE_NAMES


def is_servable(story: dict[str, Any]) -> bool:
    """House law: rows that must never reach clients.

    Wattpad is a mixed-audience platform and this connector is NOT marked
    mature, so a story flagged ``mature`` is simply not part of its catalog —
    excluded from listings AND from detail lookups, because a catalog that
    hides a story but still serves it on a guessed key is not a filter.
    """
    if not _text(story.get("id")) or not _text(story.get("title")):
        return False
    if bool(story.get("mature")):
        return False
    return is_english(story)


def _clean_description(raw: str) -> str | None:
    """Wattpad blurbs are plain text with hard line breaks and author notes."""
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in raw.replace("\r\n", "\n").split("\n")
    ]
    kept = [line for line in lines if line and not is_promo_line(line)]
    return "\n\n".join(kept) or None


def series_from_story(story: dict[str, Any], *, chapter_count: int | None = None) -> Series:
    user = story.get("user") if isinstance(story.get("user"), dict) else {}
    author = _text(user.get("fullname")) or _text(user.get("name")) or None
    tags = [
        _text(tag)
        for tag in (story.get("tags") or [])
        if _text(tag)
    ]
    parts = story.get("parts")
    if chapter_count is None:
        chapter_count = int(story.get("numParts") or 0)
    latest = None
    if isinstance(parts, list) and parts:
        latest = _text(parts[-1].get("title")) or None
    return Series(
        id=_text(story.get("id")),
        title=_text(story.get("title")),
        chapter_count=chapter_count,
        description=_clean_description(_text(story.get("description"))),
        cover_url=_text(story.get("cover")) or None,
        author=author,
        status="completed" if story.get("completed") else "ongoing",
        genres=tuple(dict.fromkeys(tags))[:MAX_TAGS],
        latest_chapter=latest,
    )


def parse_story_list(payload: dict[str, Any], *, page: int) -> PaginatedSeriesList:
    """Parse a browse or search response into a page of series."""
    stories = payload.get("stories")
    if not isinstance(stories, list):
        stories = []
    items = [
        series_from_story(story)
        for story in stories
        if isinstance(story, dict) and is_servable(story)
    ]
    total = payload.get("total")
    return PaginatedSeriesList(
        items=items,
        page=page,
        page_size=PAGE_SIZE,
        total=int(total) if isinstance(total, int) else 0,
        # ``nextUrl`` is the API's own answer and stays authoritative even
        # when this page came back short — Wattpad silently drops deleted
        # stories from a window, so a full-page check would end a listing
        # early (the captured ``filter=hot`` page holds 17 of 20).
        api_has_more=bool(payload.get("nextUrl")),
    )


def parse_story_detail(
    payload: dict[str, Any], series_key: str
) -> tuple[Series | None, list[Chapter]]:
    """Story metadata + the complete part list from ONE detail response."""
    series_key = normalize_series_key(series_key)
    if not isinstance(payload, dict) or not is_servable(payload):
        return None, []

    raw_parts = payload.get("parts")
    parts = raw_parts if isinstance(raw_parts, list) else []
    chapters: list[Chapter] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_id = _text(part.get("id"))
        if not part_id:
            continue
        chapters.append(
            Chapter(
                id=part_id,
                series_id=series_key,
                title=_text(part.get("title")),
                # Wattpad numbers nothing: a part's position in the story's
                # own ordered part list is the only chapter number there is.
                number=float(len(chapters) + 1),
                page_count=0,
                release_date=_text(part.get("createDate")) or None,
            )
        )

    series = series_from_story(
        payload, chapter_count=len(chapters) or int(payload.get("numParts") or 0)
    )
    if not series.id:
        return None, []
    return series, chapters


def parse_story_text(fragment: str) -> tuple[str, ...]:
    """Sanitize one part's HTML fragment into plain-text paragraphs.

    The endpoint returns a bare run of ``<p data-p-id="...">`` elements with
    inline markup and, on some parts, embedded images — the shared extractor
    drops the media subtrees and the markup and leaves the prose.
    """
    return tuple(extract_paragraphs(fragment))


def novel_chapter_text(
    fragment: str, *, title: str = "", number: float | None = None
) -> NovelChapterText | None:
    paragraphs = parse_story_text(fragment)
    if not paragraphs:
        return None
    return NovelChapterText(title=title, paragraphs=paragraphs, chapter_number=number)
